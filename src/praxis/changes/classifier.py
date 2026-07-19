from __future__ import annotations


def classify_paths(paths: list[str]) -> dict:
    categories: set[str] = set()
    risk = "quick_allowed"
    for path in paths:
        lower = path.lower()
        if "migration" in lower or lower.endswith(".sql"):
            categories.add("migration")
            risk = "formal_required"
        if (
            lower.endswith((".vue", ".ts", ".tsx", ".js"))
            or "/web/" in lower
            or lower.startswith("web/")
        ):
            categories.add("frontend")
        if lower.endswith((".md", ".mdx")) or lower.startswith("docs/"):
            categories.add("docs")
    return {"categories": sorted(categories), "risk": risk}
