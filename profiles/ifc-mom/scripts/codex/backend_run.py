#!/usr/bin/env python3
"""后端交互式编译/启动辅助脚本。

这个脚本复刻原 java-build-run.sh 的交互行为，但把“变更文件 -> Maven 模块”
的识别逻辑放到 Python 中，便于后续复用和维护。
"""

from __future__ import annotations

import os
import sys
import tomllib
import argparse
from pathlib import Path
from subprocess import PIPE
from typing import Any

from momlib.paths import CONFIG_FILE, LEGACY_CONFIG_FILE, ROOT_DIR
from momlib.process import run_command


BOOT_MODULE = "lamp-support/lamp-boot-server"
BOOT_JAR = Path(BOOT_MODULE) / "target" / "lamp-boot-server.jar"


def fail(message: str) -> None:
    """输出统一错误格式并终止后端辅助脚本。"""
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_config() -> dict[str, Any]:
    """读取聚合工作区项目映射。"""
    config_file = CONFIG_FILE if CONFIG_FILE.is_file() else LEGACY_CONFIG_FILE
    with config_file.open("rb") as file:
        return tomllib.load(file)


def repo_dir_for(project_name: str) -> Path:
    """根据项目短名返回后端仓库目录。"""
    project = load_config().get("projects", {}).get(project_name)
    if not project:
        fail(f"unknown project: {project_name}")
    return ROOT_DIR / project["path"]


def capture(command: list[str], cwd: Path) -> str:
    """执行命令并返回 stdout；命令失败时抛出异常。"""
    completed = run_command(
        command,
        cwd=cwd,
        check=True,
        text=True,
        stdout=PIPE,
    )
    return completed.stdout


def changed_files(repo_dir: Path) -> list[str]:
    """列出当前后端工作树相对 HEAD 的已跟踪和未跟踪变更。"""
    # 只看当前工作树相对 HEAD 的变更；需求 worktree 中运行时就是该需求的变更范围。
    tracked = capture(["git", "diff", "--name-only", "--diff-filter=ACMRTUXB", "HEAD"], repo_dir)
    untracked = capture(["git", "ls-files", "--others", "--exclude-standard"], repo_dir)
    return sorted({line for line in [*tracked.splitlines(), *untracked.splitlines()] if line})


def module_for_file(repo_dir: Path, file: str) -> str | None:
    """根据文件路径向上查找所属 Maven 模块。"""
    # 从文件所在目录向上找最近的 pom.xml，得到 Maven 模块路径。
    # 如果一路找不到但根目录有 pom.xml，说明是根级 Maven 变更。
    path = repo_dir / file
    current = path if path.is_dir() else path.parent
    while current != repo_dir and current != current.parent:
        if (current / "pom.xml").is_file():
            return current.relative_to(repo_dir).as_posix()
        current = current.parent
    return "." if (repo_dir / "pom.xml").is_file() else None


def changed_modules(repo_dir: Path) -> list[str]:
    """把后端相关变更文件归并为 Maven 模块列表。"""
    # 只把会影响 Java/Maven 编译的文件纳入模块识别，前端资源或文档变更不触发 Maven。
    modules: list[str] = []
    for file in changed_files(repo_dir):
        if file.endswith((".java", ".xml", ".yml", ".yaml", ".properties")) or file == "pom.xml" or file.endswith("/pom.xml"):
            module = module_for_file(repo_dir, file)
            if module:
                modules.append(module)
    return sorted(set(modules))


def module_csv(repo_dir: Path, include_boot: bool) -> str:
    """生成 Maven -pl 参数需要的逗号分隔模块列表。"""
    # 构建启动 jar 时必须把 boot 模块加入 -pl，否则只改了依赖模块时不会产出可运行 jar。
    modules = changed_modules(repo_dir)
    if include_boot:
        modules.append(BOOT_MODULE)
    modules = sorted(set(modules))
    if not modules:
        return BOOT_MODULE if include_boot else ""
    if "." in modules:
        return "."
    return ",".join(modules)


def run_mvn(repo_dir: Path, *args: str) -> None:
    """打印并执行 Maven 命令，失败时透传退出码。"""
    print()
    print("+ mvn " + " ".join(args))
    completed = run_command(["mvn", *args], repo_dir)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def minimal_compile(repo_dir: Path, threads: str, profile: str) -> None:
    """只编译本次变更影响的最小 Maven 模块集合。"""
    modules = module_csv(repo_dir, False)
    if not modules:
        print("No Java/Maven related changes found. Skipping compile.")
        return
    if modules == ".":
        # 根 pom 或仓库级 Maven 变更无法安全缩小模块范围，退回根 compile。
        run_mvn(repo_dir, "-B", "-T", threads, "-Dmaven.compile.fork=true", "-Dmaven.test.skip=true", "-P", profile, "-f", "pom.xml", "compile")
    else:
        run_mvn(repo_dir, "-B", "-T", threads, "-pl", modules, "-am", "-Dmaven.compile.fork=true", "-Dmaven.test.skip=true", "-P", profile, "-f", "pom.xml", "compile")


def build_boot_jar(repo_dir: Path, threads: str, profile: str) -> None:
    """构建可启动的 lamp-boot-server jar，并包含变更依赖模块。"""
    modules = module_csv(repo_dir, True)
    if modules == ".":
        run_mvn(repo_dir, "-B", "-T", threads, "-Dmaven.compile.fork=true", "-Dmaven.test.skip=true", "-P", profile, "-f", "pom.xml", "package")
    else:
        run_mvn(repo_dir, "-B", "-T", threads, "-pl", modules, "-am", "-Dmaven.compile.fork=true", "-Dmaven.test.skip=true", "-P", profile, "-f", "pom.xml", "package")


def full_install(repo_dir: Path, threads: str, profile: str) -> None:
    """执行后端全量 clean install。"""
    run_mvn(repo_dir, "-B", "-T", threads, "clean", "install", "-Dmaven.compile.fork=true", "-Dmaven.test.skip=true", "-P", profile, "-f", "pom.xml")


def run_boot_jar(repo_dir: Path) -> None:
    """运行已存在的 lamp-boot-server jar。"""
    boot_jar = repo_dir / BOOT_JAR
    if not boot_jar.is_file():
        fail(f"Boot jar not found: {boot_jar}. Build it first with option 2 or 5.")
    java_opts = os.environ.get("JAVA_OPTS", "").split()
    spring_args = os.environ.get("SPRING_ARGS", "--spring.profiles.active=dev").split()
    # JAVA_OPTS 和 SPRING_ARGS 保留环境变量入口，方便本地调试时临时覆盖参数。
    command = ["java", *java_opts, "-jar", str(boot_jar), *spring_args]
    print()
    print("+ " + " ".join(command))
    completed = run_command(command, repo_dir)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def print_changes(repo_dir: Path) -> None:
    """打印变更文件和推导出的 Maven 模块，方便执行前确认范围。"""
    files = changed_files(repo_dir)
    if not files:
        print("No git changes found.")
    else:
        print("Git changed files:")
        for file in files:
            print(f"  {file}")
    modules = changed_modules(repo_dir)
    if modules:
        print()
        print("Detected Maven modules:")
        for module in modules:
            print(f"  {module}")


def main(argv: list[str]) -> None:
    """解析交互参数并执行用户选择的后端编译/启动动作。"""
    parser = argparse.ArgumentParser(description="Build or run backend project")
    parser.add_argument("project", nargs="?", default="backend")
    parser.add_argument("--repo", help="Override backend repository/worktree path")
    args = parser.parse_args(argv)

    repo_dir = Path(args.repo).resolve() if args.repo else repo_dir_for(args.project)
    threads = os.environ.get("MAVEN_THREADS", "4")
    profile = os.environ.get("MAVEN_PROFILE", "dev")

    print_changes(repo_dir)
    print(
        """
Choose an action:
  1) Minimal compile changed Maven modules
  2) Build lamp-support/lamp-boot-server jar with changed modules
  3) Full clean install
  4) Run existing lamp-boot-server jar
  5) Build boot jar, then run it
"""
    )
    action = input("Action [1]: ").strip() or "1"
    if action == "1":
        minimal_compile(repo_dir, threads, profile)
    elif action == "2":
        build_boot_jar(repo_dir, threads, profile)
    elif action == "3":
        full_install(repo_dir, threads, profile)
    elif action == "4":
        run_boot_jar(repo_dir)
    elif action == "5":
        build_boot_jar(repo_dir, threads, profile)
        run_boot_jar(repo_dir)
    else:
        fail(f"Unknown action: {action}")


if __name__ == "__main__":
    main(sys.argv[1:])
