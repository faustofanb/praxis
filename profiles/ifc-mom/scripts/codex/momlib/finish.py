from __future__ import annotations

import re
from typing import Any

from .config import project_config, project_dir
from .delivery_policy import delivery_policy_issues
from .docs import find_requirement_dir
from .git_worktree import action_repo_dir, project_worktree_dirs
from . import praxis_contracts
from .names import safe_branch_leaf, safe_path_leaf
from .paths import ROOT_DIR
from .process import capture, command_succeeds, fail, run_checked


def git_lines(command: list[str]) -> list[str]:
    """运行 Git 命令并按行返回非空输出。"""
    output = capture(command, ROOT_DIR)
    return [line for line in output.splitlines() if line]


def delivery_commits(commits: list[str]) -> tuple[list[str], list[str]]:
    """拆分交付提交和收尾阶段不应进入 feature 的测试提交。"""
    included: list[str] = []
    excluded: list[str] = []
    for line in commits:
        subject = line.split(maxsplit=1)[1] if len(line.split(maxsplit=1)) > 1 else ""
        if subject.startswith(("test:", "tests:", "测试:")) or "临时测试" in subject:
            excluded.append(line)
        else:
            included.append(line)
    return included, excluded


def is_test_path(path: str) -> bool:
    """识别测试文件路径，用于收尾阶段拆分本地验证提交。"""
    normalized = path.replace("\\", "/").lower()
    return (
        normalized.startswith(("test/", "tests/"))
        or "/test/" in normalized
        or "/tests/" in normalized
        or "/src/test/" in normalized
        or normalized.endswith(("_test.py", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx", ".test.js", ".spec.js"))
    )


def diff_added_lines(diff_text: str) -> list[str]:
    """提取普通 unified diff 中新增的内容行。"""
    return [line[1:].strip() for line in diff_text.splitlines() if line.startswith("+") and not line.startswith("+++")]


def diff_removed_lines(diff_text: str) -> list[str]:
    """提取普通 unified diff 中删除的内容行。"""
    return [line[1:].strip() for line in diff_text.splitlines() if line.startswith("-") and not line.startswith("---")]


def is_test_scope_dependency_pom_change(repo_dir: Any, path: str) -> bool:
    """识别仅为本地测试新增 test-scope 依赖的 Maven pom 变更。"""
    normalized = path.replace("\\", "/").lower()
    if not normalized.endswith("/pom.xml") and normalized != "pom.xml":
        return False

    diff_text = "\n".join(
        [
            capture(["git", "-C", str(repo_dir), "diff", "--", path], ROOT_DIR),
            capture(["git", "-C", str(repo_dir), "diff", "--cached", "--", path], ROOT_DIR),
        ]
    )
    added_lines = [line for line in diff_added_lines(diff_text) if line]
    removed_lines = [line for line in diff_removed_lines(diff_text) if line]
    if not added_lines or removed_lines or "<scope>test</scope>" not in added_lines:
        return False

    allowed_patterns = [
        re.compile(r"^<dependency>$"),
        re.compile(r"^</dependency>$"),
        re.compile(r"^<groupId>[^<>]+</groupId>$"),
        re.compile(r"^<artifactId>[^<>]+</artifactId>$"),
        re.compile(r"^<version>[^<>]+</version>$"),
        re.compile(r"^<scope>test</scope>$"),
        re.compile(r"^<optional>(true|false)</optional>$"),
        re.compile(r"^<type>[^<>]+</type>$"),
        re.compile(r"^<classifier>[^<>]+</classifier>$"),
    ]
    # 只允许新增一段依赖声明本身；混入插件、生产依赖或属性变更时仍进入生产提交。
    return all(any(pattern.match(line) for pattern in allowed_patterns) for line in added_lines)


def is_test_commit_file(repo_dir: Any, path: str) -> bool:
    """识别应进入本地测试提交、不得进入生产提交的文件。"""
    return is_test_path(path) or is_test_scope_dependency_pom_change(repo_dir, path)


def normalize_commit_message(message: str) -> str:
    """支持命令行传入字面量 \\n，便于生成多行提交信息。"""
    return message.replace("\\n", "\n").strip()


def validate_production_commit_message(message: str) -> str:
    """校验收尾生产提交信息：type(scope): subject + 空行 + 编号明细。"""
    normalized = normalize_commit_message(message)
    lines = normalized.splitlines()
    subject_pattern = re.compile(r"^(feat|refactor|fix|chore)\([^()\s]+\):\s+\S.*$")
    detail_pattern = re.compile(r"^\d+\.\s+\S.*$")
    if (
        len(lines) < 3
        or not subject_pattern.match(lines[0])
        or lines[1] != ""
        or not all(detail_pattern.match(line) for line in lines[2:] if line.strip())
        or any(not line.strip() for line in lines[2:])
    ):
        fail(
            "production commit message must use: "
            "'feat|refactor|fix|chore(scope): 主要信息\\n\\n1. 主要改动明细'"
        )
    return normalized


def porcelain_changed_files(status_output: str) -> list[str]:
    """从 `git status --short -z` 的输出中提取文件路径。"""
    files: list[str] = []
    records = status_output.split("\0")
    i = 0
    while i < len(records):
        token = records[i]
        i += 1
        if not token:
            continue
        status = token[:2]
        if len(token) < 3:
            continue
        path = token[3:] if token[2] == " " else token[2:] if token[1] == " " else token[3:]

        # Rename/Copy lines in -z mode are emitted as `XY<old>\0<new>\0`.
        # 按“落盘路径”语义保留目标路径，避免使用旧路径重放。
        if status[0] in {"R", "C"} and i < len(records):
            path = records[i]
            i += 1

        if path:
            files.append(path)
    return files


def upstream_branch(project_data: dict[str, Any]) -> str:
    """Return the upstream branch used to create delivery feature branches."""
    upstream = project_data.get("upstreamBranch")
    if upstream:
        return upstream
    kind = project_data.get("kind", "")
    if kind in {"java-maven", "pnpm-web"}:
        return "develop"
    if kind in {"npm-dashboard", "docs"}:
        return project_data.get("defaultBranch") or "main"
    if kind == "pnpm-uniapp":
        return "develop"
    if project_data.get("defaultBranch") == "local":
        return "develop"
    return project_data.get("defaultBranch") or "develop"


def included_commit_hashes(config: dict[str, Any], project: str, repo_dir: Any) -> list[str]:
    """返回需要进入正式 feature 的需求提交哈希，按 cherry-pick 顺序排列。"""
    default_branch = project_config(config, project).get("defaultBranch") or "local"
    commits = git_lines(["git", "-C", str(repo_dir), "log", "--oneline", f"{default_branch}..HEAD"])
    included_commits, _ = delivery_commits(commits)
    return [line.split()[0] for line in reversed(included_commits)]


def safe_git_lines(command: list[str]) -> list[str]:
    """Run a Git read command and convert failures into a readable status line."""
    try:
        return git_lines(command)
    except Exception as exc:  # pragma: no cover - exact subprocess exception is not important to callers.
        return [f"ERROR: {exc}"]


def safe_capture(command: list[str]) -> str:
    """Run a Git read command and return an empty string on failure."""
    try:
        return capture(command, ROOT_DIR)
    except Exception:
        return ""


def git_ref_exists(repo_dir: Any, ref: str) -> bool:
    """Return whether a local Git ref exists without printing fatal errors."""
    return command_succeeds(["git", "-C", str(repo_dir), "show-ref", "--verify", "--quiet", ref], ROOT_DIR)


def current_upstream(repo_dir: Any) -> str:
    """Return current branch upstream name, or empty when no upstream is configured."""
    return safe_capture(["git", "-C", str(repo_dir), "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"])


def delivery_status(config: dict[str, Any], project: str, requirement_name: str) -> None:
    """Print a read-only closeout status summary for one project requirement."""
    repo_dir = project_dir(config, project)
    project_data = project_config(config, project)
    default_branch = project_data.get("defaultBranch") or "local"
    upstream = upstream_branch(project_data)
    feature_branch = f"feature/{safe_branch_leaf(requirement_name)}"

    print(f"Delivery status: {project} / {requirement_name}")
    req_dir = find_requirement_dir(config, requirement_name)
    print(f"Requirement docs: {req_dir} ({'exists' if req_dir.is_dir() else 'missing'})")
    print(f"Main repo: {repo_dir}")
    for line in safe_git_lines(["git", "-C", str(repo_dir), "status", "-sb"]):
        print(f"  {line}")

    requirement_worktrees = project_worktree_dirs(config, project, requirement_name, include_feature=False)
    feature_worktrees = [
        path
        for path in project_worktree_dirs(config, project, requirement_name, include_feature=True)
        if path.resolve() == repo_dir.resolve() or path not in requirement_worktrees
    ]
    print("Requirement worktrees:")
    if requirement_worktrees:
        for path in requirement_worktrees:
            print(f"  - {path}")
    else:
        print("  - none")

    print("Feature worktrees:")
    if feature_worktrees:
        for path in feature_worktrees:
            print(f"  - {path}")
    else:
        print("  - none")

    print(f"Default branch: {default_branch}")
    print(f"Upstream branch: origin/{upstream}")
    print(f"Feature branch: {feature_branch}")
    remote_feature_ref = f"refs/remotes/origin/{feature_branch}"
    if git_ref_exists(repo_dir, remote_feature_ref):
        print("Feature ahead/behind:")
        for line in safe_git_lines(["git", "-C", str(repo_dir), "rev-list", "--left-right", "--count", f"origin/{feature_branch}...{feature_branch}"]):
            print(f"  origin...local {line}")
    else:
        print("Feature ahead/behind:")
        print("  remote feature: not pushed")

    print("Push: user-only; Codex must not push.")


def split_commit_requirement(
    config: dict[str, Any], project: str, requirement_name: str, production_message: str | None = None
) -> None:
    """把需求 worktree 变更按生产文件和测试文件分开提交。"""
    repo_dir = action_repo_dir(config, project, [requirement_name])
    files = porcelain_changed_files(capture(["git", "-C", str(repo_dir), "status", "--short", "-z"], ROOT_DIR))
    test_files = [path for path in files if is_test_commit_file(repo_dir, path)]
    production_files = [path for path in files if path not in test_files]
    if not files:
        fail("no changed files to commit")

    print("Production commit files:")
    if production_files:
        for path in production_files:
            print(f"  - {path}")
    else:
        print("  - none")
    print("Test commit files:")
    if test_files:
        for path in test_files:
            print(f"  - {path}")
    else:
        print("  - none")

    if production_files:
        if not production_message:
            fail(
                "production commit message is required; example: "
                f"'feat(mes): {requirement_name}\\n\\n1. 完成本次主要业务改动'"
            )
        message = validate_production_commit_message(production_message)
        run_checked(["git", "-C", str(repo_dir), "add", "--", *production_files], ROOT_DIR)
        run_checked(["LEFTHOOK=0", "HUSKY=0", "git", "-C", str(repo_dir), "commit", "-m", message], ROOT_DIR)

    if test_files:
        run_checked(["git", "-C", str(repo_dir), "add", "--", *test_files], ROOT_DIR)
        run_checked(
            ["LEFTHOOK=0", "HUSKY=0", "git", "-C", str(repo_dir), "commit", "-m", f"test: {requirement_name} 本地验证 不推送"],
            ROOT_DIR,
        )

    print(f"Split commit finished: {repo_dir}")
    print(f"Production files committed: {len(production_files)}")
    print(f"Test files committed as local-only: {len(test_files)}")


def finish_requirement(config: dict[str, Any], project: str, requirement_name: str) -> None:
    """Print the review-to-feature handoff commands.

    This intentionally does not merge to local and does not push; it is a
    checklist generator for the user's reviewed workflow.
    """
    project_data = project_config(config, project)
    repo_dir = project_dir(config, project) if project == "docs" else action_repo_dir(config, project, [requirement_name])
    current_branch = capture(["git", "-C", str(repo_dir), "branch", "--show-current"], ROOT_DIR)
    default_branch = project_data.get("defaultBranch") or "local"
    feature_base = f"origin/{upstream_branch(project_data)}"
    upstream = upstream_branch(project_data)
    feature_branch = f"feature/{safe_branch_leaf(requirement_name)}"
    status = git_lines(["git", "-C", str(repo_dir), "status", "--short"])
    commits = git_lines(["git", "-C", str(repo_dir), "log", "--oneline", f"{default_branch}..HEAD"])
    included_commits, excluded_commits = delivery_commits(commits)

    print(f"Project: {project}")
    print(f"Repo: {repo_dir}")
    print(f"Current branch: {current_branch or '(detached)'}")
    print(f"Base branch for local testing: {default_branch}")
    print(f"Feature branch to create from {feature_base}: {feature_branch}")
    print()

    if status:
        print("Working tree has uncommitted changes:")
        for line in status:
            print(f"  {line}")
        print()
        print("先使用脚本拆分提交，再进行 feature cherry-pick。示例：")
        print(
            f"  {praxis_contracts.praxis_usage(f'delivery commit-split {project} {requirement_name}')}"
            f"$'feat(mes): {requirement_name}\\n\\n1. 完成本次主要业务改动'"
        )
    else:
        print("Working tree is clean.")

    print()
    print("Finish scope: 不默认运行编译验证；编译、统一分发或集成验证应在开发阶段完成。")
    print()
    print("Readiness command before feature delivery:")
    print(f"  {praxis_contracts.praxis_usage(f'gate ready {project} {requirement_name}')}")
    print(f"  {praxis_contracts.praxis_usage(f'gate ready-all {requirement_name}')}")
    print("  # Review the changed files and confirmed commit list; delivery actions still require user confirmation.")
    print()
    print(f"Commits not in {default_branch}:")
    if commits:
        for line in commits:
            print(f"  {line}")
    else:
        print("  No commits detected. 确认需求改动是否已经提交。")

    if excluded_commits:
        print()
        print("Excluded from feature cherry-pick by default:")
        for line in excluded_commits:
            print(f"  {line}")

    print()
    print("Feature delivery commands after review and development-stage verification:")
    print(f"  {praxis_contracts.praxis_usage(f'delivery deliver {project} {requirement_name}')}")
    print("  # equivalent low-level commands:")
    print("  # Keep reviewed requirement commits in the local codex worktree; create feature in the main project repo.")
    print("  cd <project-main-repo>")
    print(f"  /usr/bin/git fetch origin {upstream}")
    print(f"  /usr/bin/git switch -c {feature_branch} {feature_base}")
    print("  /usr/bin/git branch --unset-upstream")
    print("  /usr/bin/git branch -vv")
    print(f"  # Confirm the feature branch does not show [origin/{upstream}: ahead N].")
    if included_commits:
        hashes = " ".join(line.split()[0] for line in reversed(included_commits))
        print(f"  /usr/bin/git cherry-pick {hashes}")
    else:
        print("  /usr/bin/git cherry-pick <需求提交哈希>")
    print("  # Push is intentionally omitted. Codex must not push; the user pushes after review.")
    print(f"  # user-only: /usr/bin/git push -u origin {feature_branch}")
    print()
    print("Requirement worktree cleanup after feature delivery is confirmed:")
    print("  /usr/bin/git -C <requirement-worktree-path> status --short")
    print(f"  {praxis_contracts.praxis_usage(f'delivery cleanup {project} {requirement_name}')}")
    print("  # equivalent low-level cleanup:")
    print("  /usr/bin/git worktree remove <requirement-worktree-path>")
    print("  /usr/bin/git worktree remove <legacy-feature-worktree-path>  # only if an older deliver created one")
    if current_branch.startswith("codex/"):
        print(f"  /usr/bin/git branch -D {current_branch}")
    print("  /usr/bin/git worktree prune")


def deliver_requirement(config: dict[str, Any], project: str, requirement_name: str) -> None:
    """在项目主仓从上游分支创建正式 feature，并 cherry-pick 非测试需求提交。"""
    requirement_repo_dir = action_repo_dir(config, project, [requirement_name])
    main_repo_dir = project_dir(config, project)
    project_data = project_config(config, project)
    upstream = upstream_branch(project_data)
    feature_base = f"origin/{upstream}"
    feature_branch = f"feature/{safe_branch_leaf(requirement_name)}"
    requirement_status = git_lines(["git", "-C", str(requirement_repo_dir), "status", "--short"])
    if requirement_status:
        fail("working tree is not clean; run change-check and commit or clean changes before delivery")
    main_status = git_lines(["git", "-C", str(main_repo_dir), "status", "--short"])
    if main_status:
        fail("main project repository is not clean; commit, stash, or clean it before delivery")

    hashes = included_commit_hashes(config, project, requirement_repo_dir)
    if not hashes:
        fail("no delivery commits detected; test commits are excluded and will not be cherry-picked")
    policy_issues = delivery_policy_issues(requirement_repo_dir, hashes)
    if policy_issues:
        fail("delivery policy check failed:\n  - " + "\n  - ".join(policy_issues))

    run_checked(["git", "-C", str(main_repo_dir), "fetch", "origin", upstream], ROOT_DIR)
    run_checked(["git", "-C", str(main_repo_dir), "switch", "--no-track", "-c", feature_branch, feature_base], ROOT_DIR)
    run_checked(["git", "-C", str(main_repo_dir), "cherry-pick", *hashes], ROOT_DIR)
    current_branch = safe_capture(["git", "-C", str(main_repo_dir), "branch", "--show-current"]) or feature_branch
    upstream_after = current_upstream(main_repo_dir)
    changed_files = git_lines(["git", "-C", str(main_repo_dir), "diff", "--name-only", f"{feature_base}...HEAD"])
    if not changed_files:
        changed = set()
        for commit_hash in hashes:
            changed.update(
                git_lines(["git", "-C", str(requirement_repo_dir), "diff-tree", "--no-commit-id", "--name-only", "-r", commit_hash])
            )
        changed_files = sorted(changed)

    print(f"Project: {project}")
    print(f"Feature branch: {feature_branch}")
    print(f"Feature base: {feature_base}")
    print(f"Delivery repository: {main_repo_dir}")
    print(f"Cherry-picked commits: {' '.join(hashes)}")
    print(f"Current branch: {current_branch}")
    print(f"Upstream: {upstream_after or 'none'}")
    print(f"{feature_base}...HEAD changed files:")
    if changed_files:
        for path in changed_files:
            print(f"  - {path}")
    else:
        print("  - none")


def cleanup_requirement(config: dict[str, Any], project: str, requirement_name: str) -> None:
    """删除需求 worktree、需求 codex 分支，并 prune Git worktree 元数据。"""
    repo_dir = project_dir(config, project)
    worktree_dirs = [
        path
        for path in project_worktree_dirs(config, project, requirement_name, include_feature=True)
        if path.resolve() != repo_dir.resolve()
    ]
    if not worktree_dirs:
        candidate = action_repo_dir(config, project, [requirement_name])
        if candidate.resolve() == repo_dir.resolve():
            fail("cleanup target resolves to the main project repository; no requirement worktree to remove")
        worktree_dirs = [candidate]

    codex_branches: list[str] = []
    for worktree_dir in worktree_dirs:
        current_branch = capture(["git", "-C", str(worktree_dir), "branch", "--show-current"], ROOT_DIR)
        status = git_lines(["git", "-C", str(worktree_dir), "status", "--short"])
        if status:
            fail(f"worktree is not clean; cleanup aborted: {worktree_dir}")
        run_checked(["git", "-C", str(repo_dir), "worktree", "remove", str(worktree_dir)], ROOT_DIR)
        if current_branch.startswith("codex/") and current_branch not in codex_branches:
            codex_branches.append(current_branch)

    for branch in codex_branches:
        run_checked(["git", "-C", str(repo_dir), "branch", "-D", branch], ROOT_DIR)
    run_checked(["git", "-C", str(repo_dir), "worktree", "prune"], ROOT_DIR)
    print("Requirement worktree cleanup finished:")
    for worktree_dir in worktree_dirs:
        print(f"  {worktree_dir}")
