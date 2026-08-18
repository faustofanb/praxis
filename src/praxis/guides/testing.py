"""测试命令指引：检测 Maven surefire/maven.test.skip 默认跳过属性并输出可复制命令。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from praxis.result import Result

_SKIP_SUFFIXES = ("surefire.skiptests", "surefire.skip")
_SKIP_EXACT = {"maven.test.skip"}

_PROPERTY_BLOCK = re.compile(r"<properties\b[^>]*>(.*?)</properties>", re.DOTALL)
_PROPERTY_ENTRY = re.compile(r"<([A-Za-z][\w.-]*)\s*>([^<]*)</\1\s*>", re.DOTALL)
_SUREFIRE_CONFIG = re.compile(
    r"maven-surefire-plugin\b.{0,2000}?<configuration\b[^>]*>(.*?)</configuration>",
    re.DOTALL | re.IGNORECASE,
)
_HARDCODED_SKIP_TAGS = ("skipTests", "skip")


def maven_skip_properties(repository: Path) -> list[str]:
    """返回仓库 pom.xml 中默认值为 true 的 surefire/maven.test.skip 属性名。"""

    skipped: list[str] = []
    for pom in sorted(repository.rglob("pom.xml")):
        try:
            content = pom.read_text(encoding="utf-8")
        except OSError:
            continue
        for block in _PROPERTY_BLOCK.finditer(content):
            for match in _PROPERTY_ENTRY.finditer(block.group(1)):
                name, value = match.group(1), match.group(2)
                normalized = name.strip().lower()
                is_skip = normalized in _SKIP_EXACT or any(
                    normalized.endswith(suffix) for suffix in _SKIP_SUFFIXES
                )
                if is_skip and value.strip().lower() == "true":
                    skipped.append(name.strip())
    return list(dict.fromkeys(skipped))


def maven_hardcoded_surefire_skips(repository: Path) -> list[str]:
    """返回 surefire 插件配置中硬编码 skipTests/skip=true 的 pom 及标签。

    硬编码配置优先于命令行属性，-D 无法覆盖；与属性化配置区分报告。
    """

    found: list[str] = []
    for pom in sorted(repository.rglob("pom.xml")):
        try:
            content = pom.read_text(encoding="utf-8")
        except OSError:
            continue
        for config in _SUREFIRE_CONFIG.finditer(content):
            for tag in _HARDCODED_SKIP_TAGS:
                if re.search(rf"<{tag}\s*>\s*true\s*</{tag}\s*>", config.group(1)):
                    found.append(f"{pom.relative_to(repository).as_posix()}#{tag}")
    return list(dict.fromkeys(found))


def maven_test_hint(repository: Path | str, *, module: str = "") -> Result:
    repository = Path(repository)
    if not repository.is_dir():
        return Result(
            False,
            "TEST_HINT_REPOSITORY_NOT_FOUND",
            data={"repository": str(repository)},
        )
    skipped = maven_skip_properties(repository)
    hardcoded = maven_hardcoded_surefire_skips(repository)
    parts = ["mvn", "test"]
    if module.strip():
        parts.append(f"-pl {module.strip()}")
    for name in skipped:
        parts.append(f"-D{name}=false")
    data: dict[str, Any] = {
        "command": " ".join(parts),
        "skipped_by_default": skipped,
        "hardcoded_skips": hardcoded,
    }
    if skipped:
        data["note"] = (
            "仓库 pom.xml 默认跳过测试，直接运行只会输出 Tests are skipped；"
            "使用上方命令（含 -D 覆盖）才会真正执行测试。"
        )
    if hardcoded:
        data["note"] = (
            "pom 在 surefire 插件配置中硬编码了 skipTests/skip=true，-D 属性无法覆盖"
            "（Maven 显式配置优先于命令行属性）；需先把配置改为 ${属性} 插值"
            "（如 <skipTests>${ifc.surefire.skipTests}</skipTests> 并在 properties 默认 true）"
            "或切到已参数化的分支，再用 -D<属性>=false 运行，不得把 Tests are skipped 当作测试通过。"
        )
    return Result(True, data=data)
