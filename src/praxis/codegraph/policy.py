from __future__ import annotations

from dataclasses import dataclass

_HIGH_RISK_INTENT_MARKERS = (
    "调用链",
    "影响范围",
    "blast radius",
    "事务",
    "transaction",
    "for update",
    "原生 sql",
    "raw sql",
    "锁",
    "lock",
    "并发",
    "concurrency",
    "跨模块",
    "cross-module",
    "共享",
    "shared",
    "公共接口",
    "public api",
    "高扇出",
    "fan-out",
    "结构迁移",
    "schema migration",
)


@dataclass(frozen=True, slots=True)
class CodeGraphUsageDecision:
    required: bool
    reasons: tuple[str, ...]


def decide_codegraph_usage(
    intent: str, *, explicit_required: bool = False
) -> CodeGraphUsageDecision:
    normalized = intent.casefold()
    matched = tuple(
        marker for marker in _HIGH_RISK_INTENT_MARKERS if marker in normalized
    )
    reasons = (("explicit",) if explicit_required else ()) + tuple(
        f"intent:{marker}" for marker in matched
    )
    return CodeGraphUsageDecision(bool(reasons), reasons)
