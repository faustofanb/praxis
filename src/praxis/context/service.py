from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import blake2b
from pathlib import Path
from uuid import uuid4

from praxis.documents.atomic_writer import atomic_write_text
from praxis.naming.requirement import RequirementPathPolicy, requirement_document
from praxis.portraits.service import PortraitService
from praxis.result import Result
from praxis.skills.registry import SkillRegistry
from praxis.skills.routing import NodeSkillRouter, NodeSkillRoutingRequest
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import WorkspaceService

_SECRET = re.compile(
    r"(?i)\b(password|secret|token|api[_-]?key)\s*=\s*(['\"])(.*?)\2"
)


@dataclass(frozen=True, slots=True)
class ContextFragment:
    fragment_id: str
    source_type: str
    title_zh: str
    content: str
    priority: int
    estimated_tokens: int
    content_hash: str
    source_path: str | None = None
    evidence_level: str = "工具检测"
    sensitive: bool = False

    @classmethod
    def create(
        cls,
        fragment_id: str,
        source_type: str,
        title_zh: str,
        content: str,
        priority: int,
        *,
        source_path: str | None = None,
        evidence_level: str = "工具检测",
    ) -> ContextFragment:
        return cls(
            fragment_id,
            source_type,
            title_zh,
            content,
            priority,
            _estimate_tokens(content),
            _content_hash(content),
            source_path,
            evidence_level,
        )


@dataclass(frozen=True, slots=True)
class ContextBuildRequest:
    requirement_id: str
    project_id: str
    stage: str
    agent_role: str
    intent: str = ""
    token_budget: int = 24_000
    allowed_paths: tuple[str, ...] = ()
    forbidden_paths: tuple[str, ...] = ()
    workflow_node: str = "in_progress"
    artifact_types: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    available_skills: tuple[str, ...] = ()
    approved_skills: tuple[str, ...] = ()


class ContextCompiler:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.store = StateStore(self.root)

    def build(self, request: ContextBuildRequest) -> Result:
        critical_facts = self._critical_facts(request)
        fragments = self.collect(request, critical_facts=critical_facts)
        selected, omitted = self.select(fragments, request.token_budget)
        required_tokens = sum(item.estimated_tokens for item in selected if item.priority == 0)
        if required_tokens > request.token_budget:
            return Result(
                False,
                "CONTEXT_BUDGET_TOO_SMALL",
                data={"required_tokens": required_tokens, "token_budget": request.token_budget},
            )
        estimated_tokens = sum(item.estimated_tokens for item in selected)
        identity = {
            "requirement_id": request.requirement_id,
            "project_id": request.project_id,
            "stage": request.stage,
            "workflow_node": request.workflow_node,
            "agent_role": request.agent_role,
            "intent": request.intent.strip(),
        }
        identity_json = json.dumps(identity, ensure_ascii=False, sort_keys=True)
        fingerprint = _content_hash(
            identity_json + "\0" + "\0".join(item.content_hash for item in selected)
        )
        current_key = _content_hash(identity_json)
        current = self.store.get("context_current", current_key)
        if current and current["fingerprint"] == fingerprint:
            return Result(True, "CONTEXT_UNCHANGED", data=current)

        context_id = f"CTX-{datetime.now(UTC):%Y%m%dT%H%M%S}-{uuid4().hex[:8].upper()}"
        path = self._path(context_id)
        data = {
            "context_id": context_id,
            "requirement_id": request.requirement_id,
            "project_id": request.project_id,
            "stage": request.stage,
            "workflow_node": request.workflow_node,
            "agent_role": request.agent_role,
            "intent": request.intent.strip(),
            "identity": identity,
            "critical_facts": critical_facts,
            "token_budget": request.token_budget,
            "estimated_tokens": estimated_tokens,
            "fingerprint": fingerprint,
            "sources": [self._source(item) for item in selected],
            "omitted": omitted,
            "path": str(path),
        }
        skills = [
            item.fragment_id.removeprefix("skill-")
            for item in selected
            if item.source_type == "skill"
        ]
        data["skill_audit_id"] = self.store.audit(
            "skill.routed",
            "OK",
            {
                "context_id": context_id,
                "requirement_id": request.requirement_id,
                "project_id": request.project_id,
                "skills": skills,
            },
        )
        atomic_write_text(path, self._render(data, selected))
        if current:
            self.store.set("context_previous", current_key, current)
        self.store.set("context", context_id, data)
        self.store.set("context_current", current_key, data)
        self.store.audit(
            "context.built",
            "OK",
            {"context_id": context_id, "requirement_id": request.requirement_id},
        )
        return Result(True, data=data)

    def collect(
        self,
        request: ContextBuildRequest,
        *,
        critical_facts: dict[str, object] | None = None,
    ) -> list[ContextFragment]:
        workspace = WorkspaceService(self.root).load()
        requirement = self.store.requirement(request.requirement_id)
        if not requirement:
            raise KeyError(request.requirement_id)
        project = WorkspaceService(self.root).project(request.project_id)
        facts = critical_facts or self._critical_facts(request)
        requirement_root = RequirementPathPolicy(
            self.root / workspace["knowledge_root"]
        ).requirement_path(request.requirement_id, requirement["short_name"])
        original_request_path = requirement_root / requirement_document("original_request")
        original_request = (
            self._file_fragment(
                "original-request",
                "original_request",
                "用户原始需求",
                original_request_path,
                0,
            )
            if original_request_path.is_file()
            else ContextFragment.create(
                "original-request",
                "original_request",
                "用户原始需求",
                str(requirement["original_request"]),
                0,
                evidence_level="Praxis结构化事实",
            )
        )
        fragments = [
            ContextFragment.create(
                "project-facts",
                "project_facts",
                "项目、数据库与治理关键事实",
                self._render_critical_facts(facts),
                0,
                evidence_level="Praxis结构化事实",
            ),
            original_request,
            ContextFragment.create(
                "task-stage",
                "task_stage",
                "当前任务阶段",
                f"阶段：{request.stage}\nAgent角色：{request.agent_role}",
                0,
            ),
            ContextFragment.create(
                "scope-and-gates",
                "gate",
                "修改范围与门禁",
                "允许路径："
                + (", ".join(request.allowed_paths) or "未指定")
                + "\n禁止路径："
                + (", ".join(request.forbidden_paths) or ".git, .praxis, .env")
                + "\n自动安全门禁：修改范围、秘密和工作树绑定"
                + "\n需用户明确批准：质量复核、类型检查和测试",
                0,
            ),
        ]
        analysis = requirement_root / requirement_document("analysis")
        if analysis.is_file():
            fragments.append(
                self._file_fragment(
                    "requirement-analysis",
                    "requirement_analysis",
                    "需求调查分析",
                    analysis,
                    1,
                )
            )
        portrait = PortraitService(self.root).path(request.project_id)
        if portrait.is_file():
            fragments.append(
                self._file_fragment(
                    "system-portrait",
                    "system_portrait",
                    "相关系统画像",
                    portrait,
                    1,
                )
            )
        intent = request.intent.strip() or str(requirement["original_request"])
        route = NodeSkillRouter(self.root).route(
            NodeSkillRoutingRequest(
                node=request.workflow_node,
                intent=intent,
                requirement_id=request.requirement_id,
                project_id=request.project_id,
                system_id=project.system_id,
                business_domains=tuple(requirement["domains"]),
                repository_kind=project.kind,
                agent_role=request.agent_role,
                artifact_types=request.artifact_types,
                risks=request.risks,
                available_skills=request.available_skills,
                approved_skills=request.approved_skills,
                token_budget=max(0, request.token_budget // 4),
            )
        )
        route_summary = "\n".join(
            f"- {item['id']}: {item['status']} ({item['mode']}; "
            f"{', '.join(item['reasons'])})"
            for item in route.data["decisions"]
        )
        fragments.append(
            ContextFragment.create(
                "skill-route-plan",
                "skill_route",
                "节点 Skill 路由计划",
                route_summary or "当前节点没有匹配的 Skill。",
                1,
                evidence_level="Praxis节点策略",
            )
        )
        registry = SkillRegistry.workspace(self.root)
        for decision in route.data["decisions"]:
            if decision["status"] != "available":
                continue
            try:
                skill = registry.inspect(decision["id"])
            except KeyError:
                installed_path = Path(decision.get("installed_path", ""))
                if not installed_path.is_file():
                    continue
                fragments.append(
                    self._file_fragment(
                        f"skill-{decision['id']}",
                        "skill",
                        f"技能：{decision['id']}",
                        installed_path,
                        3,
                        evidence_level="已安装且哈希已记录",
                    )
                )
                continue
            fragments.append(
                self._file_fragment(
                    f"skill-{skill.id}",
                    "skill",
                    f"技能：{skill.id}",
                    skill.path,
                    3,
                    evidence_level="已验证",
                )
            )
        return fragments

    def _critical_facts(self, request: ContextBuildRequest) -> dict[str, object]:
        project = WorkspaceService(self.root).project(request.project_id)
        project_path = (self.root / project.path).resolve()
        constraints = [
            item
            for item in self.store.list_scope("requirement_constraint")
            if item.get("requirement_id") == request.requirement_id
            and item.get("status") == "active"
        ]
        approvals = [
            item
            for item in self.store.list_scope("approval_receipt")
            if item.get("requirement_id") == request.requirement_id
            and _approval_active(item)
        ]
        declines = [
            item
            for item in self.store.list_scope("verification_decline")
            if item.get("requirement_id") == request.requirement_id
        ]
        return {
            "requirement_id": request.requirement_id,
            "project": {
                "id": project.id,
                "system_id": project.system_id,
                "kind": project.kind,
                "path": str(project_path),
            },
            "database": {
                "registered": list(project.database_connections),
                "production": list(project.production_database_connections),
                "selection_required": True,
                "precheck_sql": "select current_database()",
            },
            "constraints": sorted(
                constraints,
                key=lambda item: (
                    str(item.get("created_at", "")),
                    str(item.get("constraint_id", "")),
                ),
            ),
            "verification": {
                "approvals": sorted(
                    approvals,
                    key=lambda item: (
                        str(item.get("created_at", "")),
                        str(item.get("receipt_id", "")),
                    ),
                ),
                "declines": sorted(
                    declines,
                    key=lambda item: (
                        str(item.get("created_at", "")),
                        str(item.get("receipt_id", "")),
                    ),
                ),
            },
        }

    @staticmethod
    def _render_critical_facts(facts: dict[str, object]) -> str:
        database = facts["database"]
        assert isinstance(database, dict)
        return (
            json.dumps(facts, ensure_ascii=False, indent=2)
            + "\n\n数据库使用规则：必须显式选择上方已登记连接；禁止依赖默认数据库连接。"
            + "在对表结构或数据作出判断前，必须执行 `select current_database()` 核对目标数据库。"
        )

    def select(
        self, fragments: list[ContextFragment], token_budget: int
    ) -> tuple[list[ContextFragment], list[dict[str, str]]]:
        deduplicated: list[ContextFragment] = []
        omitted: list[dict[str, str]] = []
        seen: set[str] = set()
        for fragment in sorted(fragments, key=lambda item: (item.priority, item.fragment_id)):
            if fragment.content_hash in seen:
                omitted.append({"fragment_id": fragment.fragment_id, "reason": "内容重复"})
                continue
            seen.add(fragment.content_hash)
            content, sensitive = _sanitize(fragment.content)
            deduplicated.append(
                replace(
                    fragment,
                    content=content,
                    estimated_tokens=_estimate_tokens(content),
                    sensitive=sensitive,
                )
            )

        required = [item for item in deduplicated if item.priority == 0]
        selected = list(required)
        used = sum(item.estimated_tokens for item in required)
        for fragment in (item for item in deduplicated if item.priority != 0):
            if used + fragment.estimated_tokens <= token_budget:
                selected.append(fragment)
                used += fragment.estimated_tokens
            else:
                omitted.append({"fragment_id": fragment.fragment_id, "reason": "超出Token预算"})
        return selected, omitted

    def show(self, context_id: str) -> Result:
        data = self.store.get("context", context_id)
        return Result(bool(data), "OK" if data else "CONTEXT_NOT_FOUND", data=data or {})

    def diff(self, context_id: str, previous_context_id: str) -> Result:
        current = self.store.get("context", context_id)
        previous = self.store.get("context", previous_context_id)
        if not current or not previous:
            return Result(False, "CONTEXT_NOT_FOUND")
        current_sources = {item["fragment_id"]: item for item in current["sources"]}
        previous_sources = {item["fragment_id"]: item for item in previous["sources"]}
        return Result(
            True,
            data={
                "added": sorted(current_sources.keys() - previous_sources.keys()),
                "removed": sorted(previous_sources.keys() - current_sources.keys()),
                "changed": sorted(
                    key
                    for key in current_sources.keys() & previous_sources.keys()
                    if current_sources[key]["content_hash"]
                    != previous_sources[key]["content_hash"]
                ),
            },
        )

    def _file_fragment(
        self,
        fragment_id: str,
        source_type: str,
        title_zh: str,
        path: Path,
        priority: int,
        *,
        evidence_level: str = "工具检测",
    ) -> ContextFragment:
        try:
            source_path = str(path.relative_to(self.root))
        except ValueError:
            source_path = str(path)
        return ContextFragment.create(
            fragment_id,
            source_type,
            title_zh,
            path.read_text(encoding="utf-8"),
            priority,
            source_path=source_path,
            evidence_level=evidence_level,
        )

    def _path(self, context_id: str) -> Path:
        workspace = WorkspaceService(self.root).load()["workspace"]
        return self.root / workspace["generated_root"] / "上下文包" / f"{context_id}.md"

    @staticmethod
    def _source(fragment: ContextFragment) -> dict[str, object]:
        return {
            "fragment_id": fragment.fragment_id,
            "source_type": fragment.source_type,
            "title_zh": fragment.title_zh,
            "priority": fragment.priority,
            "estimated_tokens": fragment.estimated_tokens,
            "content_hash": fragment.content_hash,
            "source_path": fragment.source_path,
            "evidence_level": fragment.evidence_level,
            "sensitive": fragment.sensitive,
        }

    @staticmethod
    def _render(data: dict[str, object], fragments: list[ContextFragment]) -> str:
        lines = [
            "---",
            f"上下文编号: {data['context_id']}",
            f"需求编号: {data['requirement_id']}",
            f"项目编号: {data['project_id']}",
            f"任务阶段: {data['stage']}",
            f"工作流节点: {data['workflow_node']}",
            f"Agent角色: {data['agent_role']}",
            f"任务意图: {data['intent']}",
            f"Token预算: {data['token_budget']}",
            f"预计Token: {data['estimated_tokens']}",
            f"内容指纹: {data['fingerprint']}",
            "---",
            "",
            "# Agent最小上下文包",
        ]
        for fragment in fragments:
            lines.extend(
                [
                    "",
                    f"## {fragment.title_zh}",
                    "",
                    f"来源：`{fragment.source_path or fragment.source_type}`",
                    "",
                    fragment.content,
                ]
            )
        return "\n".join(lines) + "\n"


def _content_hash(content: str) -> str:
    return "blake2b:" + blake2b(content.encode(), digest_size=20).hexdigest()


def _estimate_tokens(content: str) -> int:
    return max(1, len(content))


def _sanitize(content: str) -> tuple[str, bool]:
    sanitized, count = _SECRET.subn(r"\1=\2[已脱敏]\2", content)
    return sanitized, count > 0


def _approval_active(receipt: dict[str, object]) -> bool:
    if receipt.get("status") != "active":
        return False
    expires_at = str(receipt.get("expires_at", ""))
    if not expires_at:
        return True
    try:
        return datetime.fromisoformat(expires_at) >= datetime.now(UTC)
    except ValueError:
        return False
