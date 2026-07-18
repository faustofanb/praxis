#!/usr/bin/env python3
"""项目最小验证入口。

verify.py 负责统一“Git 变更 -> 受影响范围 -> 项目验证命令”的策略。
前端/PDA 的文件分类交给 frontend_changed.ts，因为读取 package.json 和
Node 生态路径判断用 Bun/TypeScript 更直接。
"""

from __future__ import annotations

import json
import os
import sys
import argparse
import datetime as dt
from pathlib import Path
from subprocess import PIPE
from typing import Any

from momlib.config import load_config, project_config, project_dir
from momlib.paths import ROOT_DIR
from momlib.process import capture, command_env, fail, run_command


FRONTEND_CLASSIFIER = ROOT_DIR / "scripts" / "codex" / "frontend_changed.ts"
EXECUTED_COMMANDS: list[list[str]] = []


def shell_join(command: list[str]) -> str:
    """用于验证证据展示的简易命令拼接。"""
    return " ".join(command)


def run(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    """打印并执行验证命令，失败时透传退出码。"""
    EXECUTED_COMMANDS.append(command)
    print()
    print("+ " + " ".join(command))
    completed = run_command(command, cwd, env=env or command_env(command))
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def pnpm_dependencies_installed(repo_dir: Path) -> bool:
    """判断 pnpm 项目依赖是否已在当前 worktree 安装。"""
    return (repo_dir / "node_modules" / ".modules.yaml").is_file()


def has_pnpm_dependency_change(files: list[str]) -> bool:
    """判断变更是否影响 pnpm 依赖安装状态。"""
    return any(file == "package.json" or file.endswith("/package.json") or file in {"pnpm-lock.yaml", "pnpm-workspace.yaml"} for file in files)


def ensure_pnpm_dependencies(repo_dir: Path, force: bool = False) -> None:
    """pnpm 验证命令执行前自动补齐 worktree 依赖。"""
    if pnpm_dependencies_installed(repo_dir) and not force:
        return
    if not (repo_dir / "package.json").is_file():
        return
    print()
    if force:
        print("pnpm dependency manifest changed. Running pnpm install first.")
    else:
        print("pnpm dependencies not installed in this worktree. Running pnpm install first.")
    run(["pnpm", "install"], repo_dir)


def changed_files(repo_dir: Path) -> list[str]:
    """列出当前工作树相对 HEAD 的已跟踪和未跟踪变更。"""
    # 变更范围固定为当前工作树相对 HEAD，适配需求 worktree 的独立验证。
    tracked = capture(["git", "diff", "--name-only", "--diff-filter=ACMRTUXB", "HEAD"], repo_dir)
    untracked = capture(["git", "ls-files", "--others", "--exclude-standard"], repo_dir)
    files = sorted({line for line in [*tracked.splitlines(), *untracked.splitlines()] if line})
    return files


def print_changed_files(files: list[str]) -> None:
    """打印变更文件；无变更时直接说明无需验证。"""
    if not files:
        print("No git changes found. Nothing to verify.")
        return
    print("Git changed files:")
    for file in files:
        print(f"  {file}")


def is_sql_only_change(files: list[str]) -> bool:
    """判断是否只有 SQL 文件变更，用于跳过不必要的 Java/Maven 编译。"""
    return bool(files) and all(file.lower().endswith(".sql") for file in files)


def backend_compile_files(files: list[str]) -> list[str]:
    """筛选会触发后端 Maven 编译的文件类型。"""
    return [
        file
        for file in files
        if file.endswith((".java", ".xml", ".yml", ".yaml", ".properties")) or file == "pom.xml" or file.endswith("/pom.xml")
    ]


def module_for_file(repo_dir: Path, file: str) -> str | None:
    """根据文件路径向上查找所属 Maven 模块。"""
    # Maven 多模块项目以最近的 pom.xml 作为模块边界；找不到模块时才退回根 pom。
    path = repo_dir / file
    current = path if path.is_dir() else path.parent

    while current != repo_dir and current != current.parent:
        if (current / "pom.xml").is_file():
            return current.relative_to(repo_dir).as_posix()
        current = current.parent

    if (repo_dir / "pom.xml").is_file():
        return "."
    return None


def verify_backend(repo_dir: Path, files: list[str]) -> None:
    """根据后端变更文件执行最小 Maven compile。"""
    threads = os.environ.get("MAVEN_THREADS", "1C")
    profile = os.environ.get("MAVEN_PROFILE", "dev")
    modules: list[str] = []

    if is_sql_only_change(files):
        print("SQL-only changes detected. Skipping Java/Maven compile.")
        print("Review SQL content, path naming, Flyway version/order, and execution instructions manually.")
        return

    # 只有 Java/Maven 配置类变更才触发后端编译，避免文档或前端资源误触发 Maven。
    for file in backend_compile_files(files):
        module = module_for_file(repo_dir, file)
        if module:
            modules.append(module)

    modules = sorted(set(modules))
    if not modules:
        print("No Java/Maven related changes found.")
        return

    if "." in modules:
        # 根级 Maven 变更影响依赖图，不能只编译局部模块。
        print("Root pom or repository-level Maven change detected. Running root compile.")
        run(
            [
                "mvn",
                "-B",
                "-T",
                threads,
                "-Dmaven.compile.fork=true",
                "-Dmaven.test.skip=true",
                "-P",
                profile,
                "-f",
                "pom.xml",
                "compile",
            ],
            repo_dir,
        )
        return

    print()
    print("Changed Maven modules:")
    for module in modules:
        print(f"  {module}")
    print()
    print(f"Running minimal compile with Maven threads: {threads}")
    run(
        [
            "mvn",
            "-B",
            "-T",
            threads,
            "-pl",
            ",".join(modules),
            "-am",
            "-Dmaven.compile.fork=true",
            "-Dmaven.test.skip=true",
            "-P",
            profile,
            "-f",
            "pom.xml",
            "compile",
        ],
        repo_dir,
    )


def classify_frontend(repo_dir: Path, kind: str, files: list[str]) -> dict[str, Any]:
    """调用 Bun/TypeScript 分类器，返回前端/PDA 验证范围。"""
    # Python 只负责调用；具体分类规则在 frontend_changed.ts 中维护。
    payload = json.dumps({"kind": kind, "files": files}, ensure_ascii=False)
    completed = run_command(
        ["bun", "run", str(FRONTEND_CLASSIFIER)],
        cwd=repo_dir,
        input=payload,
        text=True,
        stdout=PIPE,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)
    return json.loads(completed.stdout)


def verify_pnpm_web(repo_dir: Path, kind: str, files: list[str]) -> None:
    """执行 Web 后台的最小 lint，包级 typecheck 默认显式 opt-in。"""
    result = classify_frontend(repo_dir, kind, files)
    lint_files = result.get("lintFiles", [])
    packages = result.get("packages", [])
    dependency_change = has_pnpm_dependency_change(files)
    should_typecheck = os.environ.get("MOM_WEB_PACKAGE_TYPECHECK") == "1"

    if result.get("fullCheck"):
        print()
        print("Repository-level frontend config changed. Keeping ESLint scoped to changed source files.")

    if lint_files or dependency_change or (packages and should_typecheck):
        ensure_pnpm_dependencies(repo_dir, force=dependency_change)

    if lint_files:
        print()
        print("Linting changed source files.")
        run(["pnpm", "exec", "eslint", *lint_files], repo_dir)

    if not packages:
        print()
        print("No package/app typecheck target detected.")
        return

    if not should_typecheck:
        print()
        print("Skipping Web package typecheck by default; set MOM_WEB_PACKAGE_TYPECHECK=1 when explicitly required.")
        return

    print()
    print("Running package typecheck where available:")
    for package in packages:
        print(f"  {package}")
    for package in packages:
        run(["pnpm", "-F", package, "run", "--if-present", "typecheck"], repo_dir)


def verify_pnpm_uniapp(repo_dir: Path, kind: str, files: list[str]) -> None:
    """执行 PDA 项目的 lint/type-check 验证。"""
    result = classify_frontend(repo_dir, kind, files)
    lint_files = result.get("lintFiles", [])
    dependency_change = has_pnpm_dependency_change(files)

    if result.get("fullCheck"):
        print("Repository-level frontend config changed. Keeping ESLint scoped to changed source files.")

    should_typecheck = os.environ.get("MOM_PDA_FULL_TYPECHECK") == "1"
    if lint_files or should_typecheck or dependency_change:
        ensure_pnpm_dependencies(repo_dir, force=dependency_change)

    if lint_files:
        run(["pnpm", "exec", "eslint", *lint_files], repo_dir)
    else:
        print("No lintable source file changes found.")

    if should_typecheck:
        run(["pnpm", "type-check"], repo_dir)
    else:
        print("Skipping PDA project-wide type-check by default; set MOM_PDA_FULL_TYPECHECK=1 when explicitly required.")


def verification_evidence_markdown(project: str, repo_dir: Path, files: list[str], commands: list[list[str]], status: str) -> str:
    """生成可复制到需求文档的验证证据 Markdown。"""
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    command_lines = "\n".join(f"- `{shell_join(command)}`" for command in commands) or "- 未执行外部命令（无相关变更或仅需人工复核）"
    changed_lines = "\n".join(f"- `{file}`" for file in files) or "- 无 Git 变更"
    unverified = "无" if status == "PASS" and commands else "请结合上方输出人工确认跳过原因/失败命令"
    return f"""## 验证记录

- 时间：{now}
- 项目：{project}
- 目录：`{repo_dir}`
- 结果：{status}

### 变更范围

{changed_lines}

### 命令

{command_lines}

### 未验证项

- 未验证项：{unverified}
""".rstrip()


def print_verification_evidence(project: str, repo_dir: Path, files: list[str], status: str) -> None:
    """打印验证证据，便于粘贴到 docs/02-req 的开发进度或产出物。"""
    print()
    print(verification_evidence_markdown(project, repo_dir, files, EXECUTED_COMMANDS, status))


def main(argv: list[str]) -> None:
    """解析项目短名和可选 worktree 路径，分发到对应验证策略。"""
    parser = argparse.ArgumentParser(description="Verify one IFC MOM project")
    parser.add_argument("project")
    parser.add_argument("--repo", help="Override project repository/worktree path")
    args = parser.parse_args(argv)

    EXECUTED_COMMANDS.clear()
    config = load_config()
    project = project_config(config, args.project)
    repo_dir = Path(args.repo).resolve() if args.repo else project_dir(config, args.project)
    kind = project.get("kind", "")
    files = changed_files(repo_dir)
    print_changed_files(files)
    status = "PASS"
    try:
        if not files:
            return
        if kind == "java-maven":
            verify_backend(repo_dir, files)
        elif kind == "pnpm-web":
            verify_pnpm_web(repo_dir, kind, files)
        elif kind == "pnpm-uniapp":
            verify_pnpm_uniapp(repo_dir, kind, files)
        else:
            fail(f"project has no standard verify implementation: {args.project}")
    except SystemExit as error:
        status = f"FAIL({error.code})"
        raise
    finally:
        print_verification_evidence(args.project, repo_dir, files, status)


if __name__ == "__main__":
    main(sys.argv[1:])
