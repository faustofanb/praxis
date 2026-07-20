from __future__ import annotations

import re
from dataclasses import dataclass

_TITLE_PATTERN = re.compile(
    r"^(?P<type>feat|fix|refactor|perf|test|docs|build|ci|chore|revert)"
    r"\((?P<scope>[a-z][a-z0-9-]*)\): "
    r"\[(?P<requirement>REQ-\d{8}-\d{3})\] (?P<summary>.+)$"
)
_TRAILER_PATTERN = re.compile(r"^(Praxis-[A-Za-z]+):\s*(\S.*)$", re.MULTILINE)


@dataclass(slots=True, frozen=True)
class CommitMessage:
    type: str
    scope: str
    requirement_id: str
    summary: str
    trailers: dict[str, str]


def parse_commit_message(message: str, allowed_scopes: frozenset[str]) -> CommitMessage:
    title, _, body = message.strip().partition("\n")
    match = _TITLE_PATTERN.fullmatch(title)
    if not match:
        raise ValueError("提交标题格式不符合 Praxis 规范")
    fields = match.groupdict()
    if fields["scope"] not in allowed_scopes:
        raise ValueError(f"未登记的提交范围：{fields['scope']}")
    summary = fields["summary"]
    if len(summary) > 40 or not any("\u4e00" <= char <= "\u9fff" for char in summary):
        raise ValueError("提交摘要必须包含中文且不超过40个字符")
    if summary.endswith(("。", ".")):
        raise ValueError("提交摘要不能以句号结尾")
    trailers = dict(_TRAILER_PATTERN.findall(body))
    if trailers.get("Praxis-Requirement") != fields["requirement"]:
        raise ValueError("Praxis-Requirement Trailer 缺失或与标题不一致")
    if not trailers.get("Praxis-Stage"):
        raise ValueError("缺少 Praxis-Stage Trailer")
    if trailers.get("Praxis-Agent") and not trailers.get("Praxis-Session"):
        raise ValueError("Agent 提交缺少 Praxis-Session Trailer")
    return CommitMessage(
        fields["type"],
        fields["scope"],
        fields["requirement"],
        summary,
        trailers,
    )
