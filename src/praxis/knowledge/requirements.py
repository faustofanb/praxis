from __future__ import annotations

import json
import re
from pathlib import Path

from praxis.result import Result
from praxis.workspace.service import WorkspaceService, _quote


class RequirementService:
    def __init__(self, root: Path | str):
        self.root = Path(root)

    def create(
        self,
        requirement_id: str,
        title: str,
        request: str,
        domain_tags: list[str],
    ) -> Result:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", requirement_id):
            raise ValueError("requirement_id must be path-safe")
        workspace = WorkspaceService(self.root).load()
        vault = self.root / workspace["vault"]
        self._ensure_types(vault)
        target = vault / "requirements" / requirement_id
        target.mkdir(parents=True, exist_ok=False)
        (target / "artifacts").mkdir()
        domain_links = [f"[[domains/{tag}]]" for tag in domain_tags]
        for tag in domain_tags:
            domain = vault / "domains" / f"{tag}.md"
            domain.parent.mkdir(parents=True, exist_ok=True)
            if not domain.exists():
                domain.write_text(
                    self._frontmatter(type="BusinessDomain", id=tag, title=tag) + f"# {tag}\n",
                    encoding="utf-8",
                )
        tags = ", ".join(_quote(tag) for tag in domain_tags)
        (target / "requirement.toml").write_text(
            f"id = {_quote(requirement_id)}\ntitle = {_quote(title)}\ndomain_tags = [{tags}]\n",
            encoding="utf-8",
        )
        documents = {
            "request.md": self._frontmatter(
                type="Requirement",
                id=requirement_id,
                title=title,
                domains=domain_links,
                status="active",
            )
            + f"# {title}\n\n{request.rstrip()}\n",
            "analysis.md": self._section(requirement_id, title, "Analysis", "## Findings\n\n"),
            "plan.md": self._section(requirement_id, title, "Plan", "## Phases\n\n"),
            "progress.md": self._section(
                requirement_id, title, "Progress", "## Current status\n\nNot started.\n"
            ),
        }
        for name, body in documents.items():
            (target / name).write_text(body, encoding="utf-8")
        return Result(True, data={"requirement_id": requirement_id, "path": str(target)})

    @staticmethod
    def _frontmatter(**fields: object) -> str:
        lines = ["---"]
        for key, value in fields.items():
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
        return "\n".join([*lines, "---", ""])

    @classmethod
    def _section(cls, requirement_id: str, title: str, section: str, body: str) -> str:
        return (
            cls._frontmatter(
                type="RequirementSection",
                requirement=f"[[requirements/{requirement_id}/request]]",
                section=section.lower(),
            )
            + f"# {title} — {section}\n\n{body}"
        )

    @classmethod
    def _ensure_types(cls, vault: Path) -> None:
        definitions = {
            "requirement.md": ("Requirement", "clipboard-text"),
            "requirement-section.md": ("RequirementSection", "list-checks"),
            "business-domain.md": ("BusinessDomain", "factory"),
        }
        vault.mkdir(parents=True, exist_ok=True)
        for name, (title, icon) in definitions.items():
            path = vault / name
            if not path.exists():
                path.write_text(
                    cls._frontmatter(type="Type", title=title, icon=icon) + f"# {title}\n",
                    encoding="utf-8",
                )
