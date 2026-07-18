from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import call, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import task as task_module  # noqa: E402
import backend_run  # noqa: E402
import verify  # noqa: E402
from momlib import finish, git_worktree, praxis, process, project_actions, requirements  # noqa: E402


class WorkflowPolicyTest(unittest.TestCase):
    def test_start_requirement_rejects_automatic_cross_name_reuse_before_worktree_creation(self) -> None:
        requested = "形态转换包装收货按新条码联动报工"
        reused_dir = Path("/docs/02-req/2026-07/2026-07-14-弹簧包装收货入库超收校验")
        with (
            patch.object(requirements, "doc_init", return_value=reused_dir),
            patch.object(requirements, "create_worktree") as create_worktree,
            patch.object(requirements, "update_context_index"),
            patch.object(requirements, "context_command"),
            redirect_stderr(io.StringIO()) as error,
            self.assertRaises(SystemExit) as raised,
        ):
            requirements.start_requirement({}, "wms-pda", requested, "用户要求：形态转换收货联动报工。")

        self.assertEqual(raised.exception.code, 1)
        self.assertIn("禁止自动跨名称复用", error.getvalue())
        self.assertIn(requested, error.getvalue())
        self.assertIn("弹簧包装收货入库超收校验", error.getvalue())
        create_worktree.assert_not_called()

    def test_start_requirement_rejects_worktree_branch_not_bound_to_requested_requirement(self) -> None:
        requirement_name = "形态转换包装收货按新条码联动报工"
        req_dir = Path(f"/docs/02-req/2026-07/2026-07-17-{requirement_name}")
        worktree = Path(f"/worktrees/2026-07-17-{requirement_name}-dev")
        with (
            patch.object(requirements, "doc_init", return_value=req_dir),
            patch.object(requirements, "create_worktree", return_value=worktree),
            patch.object(requirements, "capture", return_value="codex/20260716-弹簧包装收货入库超收校验", create=True),
            patch.object(requirements, "update_context_index") as update_context_index,
            patch.object(requirements, "context_command") as context_command,
            self.assertRaises(SystemExit) as raised,
        ):
            requirements.start_requirement({}, "wms-pda", requirement_name, "用户要求：形态转换收货联动报工。")

        self.assertEqual(raised.exception.code, 1)
        update_context_index.assert_not_called()
        context_command.assert_not_called()

    def test_run_requires_requirement_name_for_code_project(self) -> None:
        config = {
            "projects": {
                "backend": {
                    "kind": "code",
                    "path": "ifc-mom-column-max",
                    "defaultBranch": "local",
                }
            }
        }

        with (
            patch.object(project_actions, "action_repo_dir") as action_repo_dir,
            patch.object(project_actions, "run_exit") as run_exit,
            self.assertRaises(SystemExit) as raised,
        ):
            project_actions.run_project(config, "backend", [])

        self.assertEqual(raised.exception.code, 1)
        action_repo_dir.assert_not_called()
        run_exit.assert_not_called()

    def test_shell_requires_requirement_name_for_code_project(self) -> None:
        config = {
            "projects": {
                "web": {
                    "kind": "code",
                    "path": "ifc-web-mom-max",
                    "defaultBranch": "local",
                }
            }
        }

        with (
            patch.object(project_actions, "action_repo_dir") as action_repo_dir,
            self.assertRaises(SystemExit) as raised,
        ):
            project_actions.shell_project(config, "web", [])

        self.assertEqual(raised.exception.code, 1)
        action_repo_dir.assert_not_called()

    def test_status_without_requirement_name_still_checks_main_project(self) -> None:
        config = {
            "projects": {
                "backend": {
                    "kind": "code",
                    "path": "ifc-mom-column-max",
                    "defaultBranch": "local",
                }
            }
        }

        with (
            patch.object(project_actions, "action_repo_dir", return_value=Path("/repo")),
            patch.object(project_actions, "run_exit") as run_exit,
        ):
            project_actions.status_project(config, "backend", [])

        run_exit.assert_called_once_with(
            ["git", "-C", "/repo", "status", "--short", "--branch"],
            project_actions.ROOT_DIR,
        )

    def test_default_worktree_path_lives_under_workspace_worktrees(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            docs_root = Path(tmp_dir) / "docs"
            config = {
                "worktreeRoot": ".worktrees",
                "projects": {
                    "docs": {"path": str(docs_root)},
                    "backend": {
                        "path": "ifc-mom-column-max",
                        "defaultBranch": "local",
                    },
                }
            }

            with patch.object(
                git_worktree,
                "find_requirement_dir",
                return_value=Path("/docs/02-req/2026-05/2026-05-14-氧化上下梁识别问题"),
            ):
                path = git_worktree.new_worktree_path(config, "backend", "氧化上下梁识别问题")

            self.assertEqual(
                path,
                git_worktree.ROOT_DIR / ".worktrees" / "ifc-mom-column-max" / "2026-05-14-氧化上下梁识别问题-dev",
            )

    def test_web_worktree_syncs_ignored_local_env_and_npmrc_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_dir = Path(tmp_dir) / "repo"
            worktree_dir = Path(tmp_dir) / "worktree"
            (repo_dir / "apps/web-antd").mkdir(parents=True)
            (repo_dir / "apps/web-antd/.env.development").write_text("VITE_API=/api\n", encoding="utf-8")
            (repo_dir / "apps/web-antd/.env.production").write_text("VITE_API=/prod\n", encoding="utf-8")
            (repo_dir / ".npmrc").write_text("@ifc:registry=https://example.invalid/npm/\n", encoding="utf-8")
            (repo_dir / "README.md").write_text("tracked\n", encoding="utf-8")

            with patch.object(
                git_worktree,
                "capture",
                return_value=".npmrc\napps/web-antd/.env.development\napps/web-antd/.env.production\nREADME.md",
            ):
                copied = git_worktree.sync_web_local_configs(repo_dir, worktree_dir)

            self.assertEqual(
                copied,
                [
                    worktree_dir / ".npmrc",
                    worktree_dir / "apps/web-antd/.env.development",
                    worktree_dir / "apps/web-antd/.env.production",
                ],
            )
            self.assertEqual((worktree_dir / ".npmrc").read_text(encoding="utf-8"), "@ifc:registry=https://example.invalid/npm/\n")
            self.assertEqual((worktree_dir / "apps/web-antd/.env.development").read_text(encoding="utf-8"), "VITE_API=/api\n")
            self.assertFalse((worktree_dir / "README.md").exists())

    def test_create_worktree_syncs_default_branch_from_upstream_before_add(self) -> None:
        config = {
            "projects": {
                "backend": {
                    "path": "ifc-mom-column-max",
                    "defaultBranch": "local",
                    "upstreamBranch": "develop",
                }
            }
        }
        commands: list[list[str]] = []

        def fake_run_checked(command: list[str], cwd: Path) -> None:
            commands.append(command)

        with (
            patch.object(git_worktree, "project_dir", return_value=Path("/repo")),
            patch.object(git_worktree, "find_requirement_dir", return_value=Path("/docs/02-req/2026-06/2026-06-10-需求")),
            patch.object(git_worktree, "capture", return_value=""),
            patch.object(git_worktree, "run_checked", side_effect=fake_run_checked),
            patch.object(git_worktree, "branch_today", return_value="20260610"),
            redirect_stdout(io.StringIO()) as output,
        ):
            worktree_path = git_worktree.create_worktree(config, "backend", "需求", None)

        self.assertIn("origin/develop -> local", output.getvalue())
        self.assertEqual(worktree_path, git_worktree.ROOT_DIR / ".worktrees" / "ifc-mom-column-max" / "2026-06-10-需求-dev")
        self.assertEqual(
            commands,
            [
                ["git", "-C", "/repo", "fetch", "origin", "develop"],
                ["git", "-C", "/repo", "switch", "local"],
                ["git", "-C", "/repo", "merge", "--no-edit", "origin/develop"],
                [
                    "git",
                    "-C",
                    "/repo",
                    "worktree",
                    "add",
                    str(worktree_path),
                    "-b",
                    "codex/20260610-需求",
                    "local",
                ],
            ],
        )

    def test_create_worktree_rejects_path_that_is_not_a_registered_worktree(self) -> None:
        config = {
            "projects": {
                "backend": {
                    "path": "ifc-mom-column-max",
                    "defaultBranch": "local",
                    "upstreamBranch": "develop",
                }
            }
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "cached-worktree"
            path.mkdir()
            with (
                patch.object(git_worktree, "project_dir", return_value=Path("/repo")),
                patch.object(git_worktree, "project_worktree_dirs", return_value=[]),
                patch.object(git_worktree, "new_worktree_path", return_value=path),
                patch.object(git_worktree, "capture", return_value=""),
                patch.object(git_worktree, "run_checked") as run_checked,
                redirect_stderr(io.StringIO()) as error,
                self.assertRaises(SystemExit) as raised,
            ):
                git_worktree.create_worktree(config, "backend", "需求", None)

        self.assertEqual(raised.exception.code, 1)
        self.assertIn("已存在但不是已注册 Git worktree", error.getvalue())
        run_checked.assert_not_called()

    def test_create_worktree_mounts_existing_branch_from_an_earlier_date_without_syncing_base(self) -> None:
        config = {
            "projects": {
                "backend": {
                    "path": "ifc-mom-column-max",
                    "defaultBranch": "local",
                    "upstreamBranch": "develop",
                }
            }
        }
        commands: list[list[str]] = []

        def fake_run_checked(command: list[str], cwd: Path) -> None:
            commands.append(command)

        def fake_capture(command: list[str], cwd: Path) -> str:
            if "for-each-ref" in command:
                return "codex/20260609-需求"
            return ""

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "worktree"
            with (
                patch.object(git_worktree, "project_dir", return_value=Path("/repo")),
                patch.object(git_worktree, "project_worktree_dirs", return_value=[]),
                patch.object(git_worktree, "new_worktree_path", return_value=path),
                patch.object(git_worktree, "capture", side_effect=fake_capture),
                patch.object(git_worktree, "run_checked", side_effect=fake_run_checked),
                patch.object(git_worktree, "branch_today", return_value="20260610"),
                redirect_stdout(io.StringIO()),
            ):
                worktree_path = git_worktree.create_worktree(config, "backend", "需求", None)

        self.assertEqual(worktree_path, path)
        self.assertEqual(
            commands,
            [
                ["git", "-C", "/repo", "worktree", "prune"],
                ["git", "-C", "/repo", "worktree", "add", str(path), "codex/20260609-需求"],
            ],
        )

    def test_create_worktree_aborts_when_main_repo_has_uncommitted_changes(self) -> None:
        config = {
            "projects": {
                "backend": {
                    "path": "ifc-mom-column-max",
                    "defaultBranch": "local",
                    "upstreamBranch": "develop",
                }
            }
        }
        commands: list[list[str]] = []

        def fake_capture(command: list[str], cwd: Path) -> str:
            if command[-2:] == ["status", "--short"]:
                return " M src/manifest.json"
            return ""

        def fake_run_checked(command: list[str], cwd: Path) -> None:
            commands.append(command)

        with (
            patch.object(git_worktree, "project_dir", return_value=Path("/repo")),
            patch.object(git_worktree, "capture", side_effect=fake_capture),
            patch.object(git_worktree, "run_checked", side_effect=fake_run_checked),
            redirect_stdout(io.StringIO()),
            self.assertRaises(SystemExit) as raised,
        ):
            git_worktree.create_worktree(config, "backend", "需求", None)

        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(commands, [])

    def test_create_worktree_syncs_even_when_default_branch_is_explicit(self) -> None:
        config = {
            "projects": {
                "mes-pad": {
                    "path": "ifc-mes-pad",
                    "defaultBranch": "Local",
                    "upstreamBranch": "station/base",
                }
            }
        }
        commands: list[list[str]] = []

        def fake_run_checked(command: list[str], cwd: Path) -> None:
            commands.append(command)

        with (
            patch.object(git_worktree, "project_dir", return_value=Path("/repo")),
            patch.object(git_worktree, "find_requirement_dir", return_value=Path("/docs/02-req/2026-06/2026-06-10-需求")),
            patch.object(git_worktree, "capture", return_value=""),
            patch.object(git_worktree, "run_checked", side_effect=fake_run_checked),
            patch.object(git_worktree, "branch_today", return_value="20260610"),
            redirect_stdout(io.StringIO()) as output,
        ):
            worktree_path = git_worktree.create_worktree(config, "mes-pad", "需求", "Local")

        self.assertIn("origin/station/base -> Local", output.getvalue())
        self.assertEqual(worktree_path, git_worktree.ROOT_DIR / ".worktrees" / "ifc-mes-pad" / "2026-06-10-需求-dev")
        self.assertEqual(
            commands,
            [
                ["git", "-C", "/repo", "fetch", "origin", "station/base"],
                ["git", "-C", "/repo", "switch", "Local"],
                ["git", "-C", "/repo", "merge", "--no-edit", "origin/station/base"],
                [
                    "git",
                    "-C",
                    "/repo",
                    "worktree",
                    "add",
                    str(worktree_path),
                    "-b",
                    "codex/20260610-需求",
                    "Local",
                ],
            ],
        )

    def test_finish_output_excludes_compile_verification_step_and_checks_feature_upstream(self) -> None:
        config = {
            "projects": {
                "backend": {
                    "path": "ifc-mom-column-max",
                    "defaultBranch": "local",
                }
            }
        }

        def fake_capture(command: list[str], cwd: Path) -> str:
            text = " ".join(command)
            if "branch --show-current" in text:
                return "codex/20260512-氧化上下梁识别问题"
            if "status --short" in text:
                return ""
            if "log --oneline" in text:
                return "abc123 feat: 需求提交\nbad999 test: 临时测试"
            return ""

        with (
            patch.object(finish, "project_dir", return_value=Path("/repo")),
            patch.object(finish, "action_repo_dir", return_value=Path("/worktree")),
            patch.object(finish, "capture", side_effect=fake_capture),
            redirect_stdout(io.StringIO()) as output,
        ):
            finish.finish_requirement(config, "backend", "氧化上下梁识别问题")

        text = output.getvalue()
        self.assertIn("Readiness command", text)
        self.assertIn("task gate -- ready backend 氧化上下梁识别问题", text)
        self.assertNotIn("task project -- change-check backend 氧化上下梁识别问题", text)
        self.assertIn("/usr/bin/git branch --unset-upstream", text)
        self.assertIn("/usr/bin/git branch -vv", text)
        self.assertIn("cd <project-main-repo>", text)
        self.assertIn("/usr/bin/git switch -c feature/氧化上下梁识别问题 origin/develop", text)
        self.assertIn("/usr/bin/git cherry-pick abc123", text)
        self.assertIn("Push is intentionally omitted", text)
        self.assertIn("user-only: /usr/bin/git push -u origin feature/氧化上下梁识别问题", text)
        self.assertNotIn("\n  git push", text)
        self.assertNotIn("/usr/bin/git cherry-pick abc123 bad999", text)
        self.assertNotIn("worktree add", text)
        self.assertNotIn("task.py backend verify", text)

    def test_finish_cleanup_includes_deleting_requirement_branch(self) -> None:
        config = {
            "projects": {
                "backend": {
                    "path": "ifc-mom-column-max",
                    "defaultBranch": "local",
                }
            }
        }

        def fake_capture(command: list[str], cwd: Path) -> str:
            text = " ".join(command)
            if "branch --show-current" in text:
                return "codex/20260512-氧化上下梁识别问题"
            if "status --short" in text or "log --oneline" in text:
                return ""
            return ""

        with (
            patch.object(finish, "project_dir", return_value=Path("/repo")),
            patch.object(finish, "action_repo_dir", return_value=Path("/worktree")),
            patch.object(finish, "capture", side_effect=fake_capture),
            redirect_stdout(io.StringIO()) as output,
        ):
            finish.finish_requirement(config, "backend", "氧化上下梁识别问题")

        text = output.getvalue()
        self.assertIn("git branch -D codex/20260512-氧化上下梁识别问题", text)

    def test_delivery_status_prints_readonly_closeout_summary(self) -> None:
        config = {
            "projects": {
                "backend": {
                    "path": "ifc-mom-column-max",
                    "defaultBranch": "local",
                }
            }
        }

        def fake_git_lines(command: list[str]) -> list[str]:
            text = " ".join(command)
            if "status -sb" in text:
                return ["## feature/氧化上下梁识别问题...origin/feature/氧化上下梁识别问题"]
            if "rev-list --left-right --count" in text:
                return ["0\t1"]
            return []

        with (
            patch.object(finish, "project_dir", return_value=Path("/repo")),
            patch.object(finish, "find_requirement_dir", return_value=Path("/docs/02-req/2026-06/需求")),
            patch.object(
                finish,
                "project_worktree_dirs",
                side_effect=[[Path("/requirement-worktree")], [Path("/requirement-worktree"), Path("/repo")]],
            ),
            patch.object(finish, "git_lines", side_effect=fake_git_lines),
            patch.object(finish, "git_ref_exists", return_value=True),
            redirect_stdout(io.StringIO()) as output,
        ):
            finish.delivery_status(config, "backend", "氧化上下梁识别问题")

        text = output.getvalue()
        self.assertIn("Delivery status: backend / 氧化上下梁识别问题", text)
        self.assertIn("Requirement worktrees:", text)
        self.assertIn("/requirement-worktree", text)
        self.assertIn("Feature branch: feature/氧化上下梁识别问题", text)
        self.assertIn("origin...local 0\t1", text)
        self.assertIn("Push: user-only; Codex must not push.", text)

    def test_delivery_status_reports_unpushed_feature_without_remote_diff_error(self) -> None:
        config = {
            "projects": {
                "backend": {
                    "path": "ifc-mom-column-max",
                    "defaultBranch": "local",
                }
            }
        }
        git_commands: list[list[str]] = []

        def fake_git_lines(command: list[str]) -> list[str]:
            git_commands.append(command)
            if "status" in command:
                return ["## local"]
            return []

        with (
            patch.object(finish, "project_dir", return_value=Path("/repo")),
            patch.object(finish, "find_requirement_dir", return_value=Path("/docs/02-req/2026-06/需求")),
            patch.object(finish, "project_worktree_dirs", side_effect=[[], []]),
            patch.object(finish, "git_lines", side_effect=fake_git_lines),
            patch.object(finish, "git_ref_exists", return_value=False),
            redirect_stdout(io.StringIO()) as output,
        ):
            finish.delivery_status(config, "backend", "分层审核优化")

        text = output.getvalue()
        self.assertIn("remote feature: not pushed", text)
        self.assertNotIn("ERROR:", text)
        self.assertFalse(any("rev-list" in command for command in git_commands))

    def test_delivery_plan_creates_feature_branch_in_main_repo_from_develop_and_excludes_test_commits(self) -> None:
        config = {
            "projects": {
                "backend": {
                    "path": "ifc-mom-column-max",
                    "defaultBranch": "local",
                }
            }
        }

        commands: list[list[str]] = []

        def fake_capture(command: list[str], cwd: Path) -> str:
            text = " ".join(command)
            if "branch --show-current" in text:
                return "codex/20260512-氧化上下梁识别问题"
            if "status --short" in text:
                return ""
            if "log --oneline" in text:
                return "abc123 feat: 需求提交\nbad999 test: 本地验证 不推送"
            if "log -1 --format=%B" in text:
                return "feat(mes): 氧化上下梁识别\n\n1. 新增业务接口"
            if "diff-tree" in text:
                return "lamp-mes/src/main/java/Demo.java"
            return ""

        def fake_run_checked(command: list[str], cwd: Path) -> None:
            commands.append(command)

        with (
            patch.object(finish, "action_repo_dir", return_value=Path("/requirement-worktree")),
            patch.object(finish, "project_dir", return_value=Path("/repo")),
            patch.object(finish, "capture", side_effect=fake_capture),
            patch("momlib.delivery_policy.capture", side_effect=fake_capture),
            patch.object(finish, "run_checked", side_effect=fake_run_checked),
            redirect_stdout(io.StringIO()) as output,
        ):
            finish.deliver_requirement(config, "backend", "氧化上下梁识别问题")

        self.assertIn("Delivery repository: /repo", output.getvalue())
        self.assertEqual(
            commands,
            [
                ["git", "-C", "/repo", "fetch", "origin", "develop"],
                ["git", "-C", "/repo", "switch", "--no-track", "-c", "feature/氧化上下梁识别问题", "origin/develop"],
                ["git", "-C", "/repo", "cherry-pick", "abc123"],
            ],
        )
        text = output.getvalue()
        self.assertIn("Current branch:", text)
        self.assertIn("Upstream: none", text)
        self.assertIn("origin/develop...HEAD changed files:", text)
        self.assertIn("lamp-mes/src/main/java/Demo.java", text)

    def test_delivery_blocks_unstructured_production_commit_message(self) -> None:
        config = {
            "projects": {
                "backend": {
                    "path": "ifc-mom-column-max",
                    "defaultBranch": "local",
                }
            }
        }

        commands: list[list[str]] = []

        def fake_capture(command: list[str], cwd: Path) -> str:
            text = " ".join(command)
            if "status --short" in text:
                return ""
            if "log --oneline" in text:
                return "abc123 feat: 需求提交"
            if "log -1 --format=%B" in text:
                return "feat: 需求提交"
            if "diff-tree" in text:
                return "lamp-mes/src/main/java/Demo.java"
            return ""

        def fake_run_checked(command: list[str], cwd: Path) -> None:
            commands.append(command)

        with (
            patch.object(finish, "action_repo_dir", return_value=Path("/requirement-worktree")),
            patch.object(finish, "project_dir", return_value=Path("/repo")),
            patch.object(finish, "capture", side_effect=fake_capture),
            patch("momlib.delivery_policy.capture", side_effect=fake_capture),
            patch.object(finish, "run_checked", side_effect=fake_run_checked),
            self.assertRaises(SystemExit),
        ):
            finish.deliver_requirement(config, "backend", "氧化上下梁识别问题")

        self.assertEqual(commands, [])

    def test_delivery_blocks_pad_controller_without_menu_authorization_migration(self) -> None:
        config = {
            "projects": {
                "backend": {
                    "path": "ifc-mom-column-max",
                    "defaultBranch": "local",
                }
            }
        }

        commands: list[list[str]] = []

        def fake_capture(command: list[str], cwd: Path) -> str:
            text = " ".join(command)
            if "status --short" in text:
                return ""
            if "log --oneline" in text:
                return "abc123 feat: PAD接口"
            if "log -1 --format=%B" in text:
                return "feat(mes): PAD接口\n\n1. 新增 PAD 查询接口"
            if "diff-tree" in text:
                return (
                    "lamp-mes-bff/lamp-mes-bff-controller/src/main/java/"
                    "top/tangyh/lamp/mes/pad/controller/task/MesMoldManagementPadController.java"
                )
            return ""

        def fake_run_checked(command: list[str], cwd: Path) -> None:
            commands.append(command)

        with (
            patch.object(finish, "action_repo_dir", return_value=Path("/requirement-worktree")),
            patch.object(finish, "project_dir", return_value=Path("/repo")),
            patch.object(finish, "capture", side_effect=fake_capture),
            patch("momlib.delivery_policy.capture", side_effect=fake_capture),
            patch.object(finish, "run_checked", side_effect=fake_run_checked),
            self.assertRaises(SystemExit),
        ):
            finish.deliver_requirement(config, "backend", "PAD接口授权检查")

        self.assertEqual(commands, [])

    def test_split_commit_commits_production_and_test_files_separately(self) -> None:
        config = {
            "projects": {
                "backend": {
                    "path": "ifc-mom-column-max",
                    "defaultBranch": "local",
                }
            }
        }

        commands: list[list[str]] = []

        def fake_capture(command: list[str], cwd: Path) -> str:
            text = " ".join(command)
            if "status --short -z" in text:
                return " M lamp-mes/src/main/java/Demo.java\0?? lamp-mes/src/test/java/DemoTest.java\0"
            return ""

        def fake_run_checked(command: list[str], cwd: Path) -> None:
            commands.append(command)

        with (
            patch.object(finish, "action_repo_dir", return_value=Path("/requirement-worktree")),
            patch.object(finish, "capture", side_effect=fake_capture),
            patch.object(finish, "run_checked", side_effect=fake_run_checked),
            redirect_stdout(io.StringIO()) as output,
        ):
            finish.split_commit_requirement(
                config,
                "backend",
                "氧化上下梁识别问题",
                "feat(mes): 氧化上下梁识别\n\n1. 调整氧化上下梁识别逻辑",
            )

        self.assertIn("Split commit finished", output.getvalue())
        self.assertIn("Production commit files:", output.getvalue())
        self.assertIn("Test commit files:", output.getvalue())
        self.assertEqual(
            commands,
            [
                ["git", "-C", "/requirement-worktree", "add", "--", "lamp-mes/src/main/java/Demo.java"],
                [
                    "LEFTHOOK=0",
                    "HUSKY=0",
                    "git",
                    "-C",
                    "/requirement-worktree",
                    "commit",
                    "-m",
                    "feat(mes): 氧化上下梁识别\n\n1. 调整氧化上下梁识别逻辑",
                ],
                ["git", "-C", "/requirement-worktree", "add", "--", "lamp-mes/src/test/java/DemoTest.java"],
                [
                    "LEFTHOOK=0",
                    "HUSKY=0",
                    "git",
                    "-C",
                    "/requirement-worktree",
                    "commit",
                    "-m",
                    "test: 氧化上下梁识别问题 本地验证 不推送",
                ],
            ],
        )

    def test_split_commit_classifies_root_test_directory_as_test_commit(self) -> None:
        config = {
            "projects": {
                "mes-pda": {
                    "path": "ifc-mes-pda",
                    "defaultBranch": "local",
                }
            }
        }

        commands: list[list[str]] = []

        def fake_capture(command: list[str], cwd: Path) -> str:
            text = " ".join(command)
            if "status --short -z" in text:
                return " M src/pages/audit.vue\0?? test/auditDisplay.test.ts\0?? tests/auditDisplay.spec.ts\0"
            return ""

        def fake_run_checked(command: list[str], cwd: Path) -> None:
            commands.append(command)

        with (
            patch.object(finish, "action_repo_dir", return_value=Path("/requirement-worktree")),
            patch.object(finish, "capture", side_effect=fake_capture),
            patch.object(finish, "run_checked", side_effect=fake_run_checked),
            redirect_stdout(io.StringIO()) as output,
        ):
            finish.split_commit_requirement(
                config,
                "mes-pda",
                "分层审核优化",
                "feat(mes): 分层审核优化\n\n1. 优化审核展示逻辑",
            )

        text = output.getvalue()
        self.assertIn("src/pages/audit.vue", text)
        self.assertIn("test/auditDisplay.test.ts", text)
        self.assertIn("tests/auditDisplay.spec.ts", text)
        self.assertEqual(
            commands,
            [
                ["git", "-C", "/requirement-worktree", "add", "--", "src/pages/audit.vue"],
                [
                    "LEFTHOOK=0",
                    "HUSKY=0",
                    "git",
                    "-C",
                    "/requirement-worktree",
                    "commit",
                    "-m",
                    "feat(mes): 分层审核优化\n\n1. 优化审核展示逻辑",
                ],
                ["git", "-C", "/requirement-worktree", "add", "--", "test/auditDisplay.test.ts", "tests/auditDisplay.spec.ts"],
                [
                    "LEFTHOOK=0",
                    "HUSKY=0",
                    "git",
                    "-C",
                    "/requirement-worktree",
                    "commit",
                    "-m",
                    "test: 分层审核优化 本地验证 不推送",
                ],
            ],
        )

    def test_split_commit_keeps_test_scope_pom_dependency_with_test_commit(self) -> None:
        config = {
            "projects": {
                "backend": {
                    "path": "ifc-mom-column-max",
                    "defaultBranch": "local",
                }
            }
        }

        commands: list[list[str]] = []

        def fake_capture(command: list[str], cwd: Path) -> str:
            text = " ".join(command)
            if "status --short -z" in text:
                return (
                    " M lamp-mdm/lamp-mdm-biz/pom.xml\0"
                    "?? lamp-mdm/lamp-mdm-biz/src/test/java/DemoTest.java\0"
                )
            if "diff --" in text and "pom.xml" in text:
                return """
@@ -83,5 +83,10 @@
+        <dependency>
+            <groupId>org.springframework.boot</groupId>
+            <artifactId>spring-boot-starter-test</artifactId>
+            <scope>test</scope>
+        </dependency>
        </dependencies>
    </project>
"""
            return ""

        def fake_run_checked(command: list[str], cwd: Path) -> None:
            commands.append(command)

        with (
            patch.object(finish, "action_repo_dir", return_value=Path("/requirement-worktree")),
            patch.object(finish, "capture", side_effect=fake_capture),
            patch.object(finish, "run_checked", side_effect=fake_run_checked),
            redirect_stdout(io.StringIO()),
        ):
            finish.split_commit_requirement(
                config,
                "backend",
                "物料批号自动维护",
                "feat(mdm): 物料批号自动维护\n\n1. 新增批号自动维护",
            )

        self.assertEqual(
            commands,
            [
                [
                    "git",
                    "-C",
                    "/requirement-worktree",
                    "add",
                    "--",
                    "lamp-mdm/lamp-mdm-biz/pom.xml",
                    "lamp-mdm/lamp-mdm-biz/src/test/java/DemoTest.java",
                ],
                [
                    "LEFTHOOK=0",
                    "HUSKY=0",
                    "git",
                    "-C",
                    "/requirement-worktree",
                    "commit",
                    "-m",
                    "test: 物料批号自动维护 本地验证 不推送",
                ],
            ],
        )

    def test_split_commit_rejects_unstructured_production_message(self) -> None:
        config = {
            "projects": {
                "backend": {
                    "path": "ifc-mom-column-max",
                    "defaultBranch": "local",
                }
            }
        }

        def fake_capture(command: list[str], cwd: Path) -> str:
            text = " ".join(command)
            if "status --porcelain" in text:
                return " M lamp-mes/src/main/java/Demo.java"
            return ""

        with (
            patch.object(finish, "action_repo_dir", return_value=Path("/requirement-worktree")),
            patch.object(finish, "capture", side_effect=fake_capture),
            patch.object(finish, "run_checked") as run_checked,
        ):
            with self.assertRaises(SystemExit):
                finish.split_commit_requirement(config, "backend", "氧化上下梁识别问题", "feat: 氧化上下梁识别")

        run_checked.assert_not_called()

    def test_cleanup_removes_requirement_worktree_and_codex_branch(self) -> None:
        config = {
            "projects": {
                "backend": {
                    "path": "ifc-mom-column-max",
                    "defaultBranch": "local",
                }
            }
        }

        commands: list[list[str]] = []

        def fake_capture(command: list[str], cwd: Path) -> str:
            text = " ".join(command)
            if "branch --show-current" in text:
                return "codex/20260512-氧化上下梁识别问题"
            if "status --short" in text:
                return ""
            return ""

        def fake_run_checked(command: list[str], cwd: Path) -> None:
            commands.append(command)

        with (
            patch.object(finish, "action_repo_dir", return_value=Path("/requirement-worktree")),
            patch.object(finish, "project_worktree_dirs", return_value=[Path("/requirement-worktree")]),
            patch.object(finish, "project_dir", return_value=Path("/repo")),
            patch.object(finish, "capture", side_effect=fake_capture),
            patch.object(finish, "run_checked", side_effect=fake_run_checked),
            redirect_stdout(io.StringIO()) as output,
        ):
            finish.cleanup_requirement(config, "backend", "氧化上下梁识别问题")

        self.assertIn("Requirement worktree cleanup finished", output.getvalue())
        self.assertEqual(
            commands,
            [
                ["git", "-C", "/repo", "worktree", "remove", "/requirement-worktree"],
                ["git", "-C", "/repo", "branch", "-D", "codex/20260512-氧化上下梁识别问题"],
                ["git", "-C", "/repo", "worktree", "prune"],
            ],
        )

    def test_cleanup_removes_feature_worktree_without_deleting_feature_branch(self) -> None:
        config = {
            "projects": {
                "backend": {
                    "path": "ifc-mom-column-max",
                    "defaultBranch": "local",
                }
            }
        }

        commands: list[list[str]] = []
        branches = {
            "/requirement-worktree": "codex/20260512-氧化上下梁识别问题",
            "/feature-worktree": "feature/氧化上下梁识别问题",
        }

        def fake_capture(command: list[str], cwd: Path) -> str:
            text = " ".join(command)
            if "branch --show-current" in text:
                return branches.get(command[2], "")
            if "status --short" in text:
                return ""
            return ""

        def fake_run_checked(command: list[str], cwd: Path) -> None:
            commands.append(command)

        with (
            patch.object(
                finish,
                "project_worktree_dirs",
                return_value=[Path("/requirement-worktree"), Path("/feature-worktree")],
            ),
            patch.object(finish, "project_dir", return_value=Path("/repo")),
            patch.object(finish, "capture", side_effect=fake_capture),
            patch.object(finish, "run_checked", side_effect=fake_run_checked),
        ):
            finish.cleanup_requirement(config, "backend", "氧化上下梁识别问题")

        self.assertEqual(
            commands,
            [
                ["git", "-C", "/repo", "worktree", "remove", "/requirement-worktree"],
                ["git", "-C", "/repo", "worktree", "remove", "/feature-worktree"],
                ["git", "-C", "/repo", "branch", "-D", "codex/20260512-氧化上下梁识别问题"],
                ["git", "-C", "/repo", "worktree", "prune"],
            ],
        )

    def test_cleanup_does_not_remove_main_project_repository_when_feature_branch_matches_requirement(self) -> None:
        config = {
            "projects": {
                "backend": {
                    "path": "ifc-mom-column-max",
                    "defaultBranch": "local",
                }
            }
        }

        commands: list[list[str]] = []
        branches = {
            "/repo": "feature/氧化上下梁识别问题",
            "/requirement-worktree": "codex/20260512-氧化上下梁识别问题",
        }

        def fake_capture(command: list[str], cwd: Path) -> str:
            text = " ".join(command)
            if "branch --show-current" in text:
                return branches.get(command[2], "")
            if "status --short" in text:
                return ""
            return ""

        def fake_run_checked(command: list[str], cwd: Path) -> None:
            commands.append(command)

        with (
            patch.object(
                finish,
                "project_worktree_dirs",
                return_value=[Path("/repo"), Path("/requirement-worktree")],
            ),
            patch.object(finish, "project_dir", return_value=Path("/repo")),
            patch.object(finish, "capture", side_effect=fake_capture),
            patch.object(finish, "run_checked", side_effect=fake_run_checked),
        ):
            finish.cleanup_requirement(config, "backend", "氧化上下梁识别问题")

        self.assertEqual(
            commands,
            [
                ["git", "-C", "/repo", "worktree", "remove", "/requirement-worktree"],
                ["git", "-C", "/repo", "branch", "-D", "codex/20260512-氧化上下梁识别问题"],
                ["git", "-C", "/repo", "worktree", "prune"],
            ],
        )

    def test_praxis_req_project_gate_delivery_commands_route_existing_capabilities(self) -> None:
        config = {"projects": {"backend": {"path": "ifc-mom-column-max", "defaultBranch": "local"}}}
        with (
            patch.object(task_module, "load_config", return_value=config),
            patch.object(task_module, "doc_init") as doc_init,
            patch.object(task_module, "verify_project") as verify_project,
            patch.object(task_module, "praxis_context_packet") as context_packet,
            patch.object(task_module, "guard_check", return_value=0) as guard_check,
            patch.object(task_module, "finish_requirement") as finish_requirement,
            patch.object(task_module, "write_execution_compliance_evidence"),
        ):
            self.assertEqual(task_module.run_praxis_action("req", ["init", "重构", "原始需求"]), 0)
            self.assertEqual(task_module.run_praxis_action("project", ["verify", "backend", "重构"]), 0)
            self.assertEqual(task_module.run_praxis_action("gate", ["guard", "backend", "重构"]), 0)
            self.assertEqual(task_module.run_praxis_action("delivery", ["finish", "backend", "重构"]), 0)

        doc_init.assert_called_once_with(config, "重构", "原始需求")
        verify_project.assert_called_once_with(config, "backend", ["重构"])
        self.assertEqual(context_packet.call_count, 2)
        context_packet.assert_has_calls([call(config, "backend", "重构"), call(config, "backend", "重构")])
        guard_check.assert_called_once_with(config, "backend", "重构")
        finish_requirement.assert_called_once_with(config, "backend", "重构")

    def test_praxis_req_iter_accepts_body_file(self) -> None:
        config = {"projects": {"docs": {"path": "docs"}}}
        with tempfile.TemporaryDirectory() as tmp_dir:
            body_file = Path(tmp_dir) / "body.md"
            body_file.write_text("# 正文\n\n已完成。\n", encoding="utf-8")
            with (
                patch.object(task_module, "load_config", return_value=config),
                patch.object(task_module, "doc_iter") as doc_iter,
            ):
                self.assertEqual(
                    task_module.run_praxis_action(
                        "req",
                        ["iter", "需求", "progress", "完成记录", "--body-file", str(body_file)],
                    ),
                    0,
                )

        doc_iter.assert_called_once_with(config, "需求", "progress", "完成记录", "# 正文\n\n已完成。\n")

    def test_cli_rejects_cross_group_compatibility_aliases(self) -> None:
        config = {
            "projects": {
                "backend": {"path": "ifc-mom-column-max", "defaultBranch": "local"},
                "docs": {"path": "docs"},
            }
        }
        aliases = [
            ("project", ["guard", "backend", "需求"]),
            ("project", ["deliver", "backend", "需求"]),
            ("project", ["init", "docs", "需求", "原始需求"]),
            ("req", ["tolaria-check", "需求"]),
            ("docs", ["index-all"]),
        ]
        with (
            patch.object(task_module, "load_config", return_value=config),
            patch.object(task_module, "praxis_context_packet"),
            patch.object(task_module, "guard_check", return_value=0),
            patch.object(task_module, "deliver_requirement"),
            patch.object(task_module, "doc_init"),
            patch.object(task_module, "tolaria_check"),
            patch.object(task_module, "write_requirement_global_index"),
        ):
            for group, args in aliases:
                with self.subTest(group=group, action=args[0]), redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as error:
                        task_module.run_praxis_action(group, args)
                    self.assertEqual(error.exception.code, 1)

    def test_project_command_accepts_documented_action_first_order(self) -> None:
        config = {"projects": {"backend": {"path": "ifc-mom-column-max", "defaultBranch": "local"}}}
        with (
            patch.object(task_module, "load_config", return_value=config),
            patch.object(task_module, "verify_project") as verify_project,
        ):
            task_module.main(["project", "verify", "backend", "重构"])

        verify_project.assert_called_once_with(config, "backend", ["重构"])

    def test_main_rejects_removed_legacy_command_groups(self) -> None:
        with redirect_stderr(io.StringIO()) as error:
            with self.assertRaises(SystemExit) as exc:
                task_module.main(["workflow", "check"])

        self.assertEqual(exc.exception.code, 1)
        self.assertIn("unknown task group: workflow", error.getvalue())

    def test_project_preflight_action_first_routes_to_preflight(self) -> None:
        config = {"projects": {"backend": {"path": "ifc-mom-column-max", "defaultBranch": "local"}}}
        with (
            patch.object(task_module, "load_config", return_value=config),
            patch.object(task_module, "praxis_context_packet") as context_packet,
            patch.object(task_module, "preflight", return_value=0) as preflight,
        ):
            task_module.main(["project", "preflight", "backend", "重构"])

        context_packet.assert_called_once_with(config, "backend", "重构")
        preflight.assert_called_once_with(config, "backend", "重构")

    def test_project_preflight_action_first_propagates_failure_code(self) -> None:
        config = {"projects": {"backend": {"path": "ifc-mom-column-max", "defaultBranch": "local"}}}
        with (
            patch.object(task_module, "load_config", return_value=config),
            patch.object(task_module, "praxis_context_packet"),
            patch.object(task_module, "preflight", return_value=1),
        ):
            with self.assertRaises(SystemExit) as exc:
                task_module.main(["project", "preflight", "backend", "重构"])

        self.assertEqual(exc.exception.code, 1)

    def test_missing_project_run_command_reports_workflow_gap(self) -> None:
        config = {"projects": {"docs": {"kind": "docs", "path": "."}}}

        with redirect_stderr(io.StringIO()) as error:
            with self.assertRaises(SystemExit) as exc:
                project_actions.run_project(config, "docs", [])

        self.assertEqual(exc.exception.code, 1)
        self.assertIn("工作流缺口", error.getvalue())

    def test_workflow_git_subprocesses_disable_fsmonitor(self) -> None:
        env = process.command_env(["git", "status"])

        self.assertIsNotNone(env)
        assert env is not None
        self.assertEqual(env["GIT_CONFIG_KEY_0"], "core.fsmonitor")
        self.assertEqual(env["GIT_CONFIG_VALUE_0"], "false")
        self.assertIsNone(process.command_env(["uv", "run", "script.py"]))

    def test_workflow_git_subprocesses_support_shell_free_env_prefixes(self) -> None:
        env = process.command_env(["LEFTHOOK=0", "HUSKY=0", "git", "commit", "-m", "msg"])

        self.assertIsNotNone(env)
        assert env is not None
        self.assertEqual(env["LEFTHOOK"], "0")
        self.assertEqual(env["HUSKY"], "0")
        self.assertEqual(env["GIT_CONFIG_KEY_0"], "core.fsmonitor")
        self.assertEqual(process.command_argv(["LEFTHOOK=0", "HUSKY=0", "git", "status"]), ["/usr/bin/git", "status"])

    def test_workflow_git_subprocesses_use_system_git(self) -> None:
        completed = __import__("subprocess").CompletedProcess(["/usr/bin/git", "status"], 0, stdout="")

        with patch.object(process.subprocess, "run", return_value=completed) as run:
            process.run_checked(["git", "status"], Path("/tmp"))

        command = run.call_args.args[0]
        self.assertEqual(command[0], "/usr/bin/git")
        self.assertEqual(command[1:], ["status"])

    def test_standalone_verify_scripts_disable_git_fsmonitor(self) -> None:
        completed = __import__("subprocess").CompletedProcess(["git", "status"], 0, stdout="")
        with patch.object(process.subprocess, "run", return_value=completed) as run:
            verify.capture(["git", "status"], Path("/tmp"))

        command = run.call_args.args[0]
        env = run.call_args.kwargs["env"]
        self.assertEqual(command[0], "/usr/bin/git")
        self.assertEqual(env["GIT_CONFIG_KEY_0"], "core.fsmonitor")
        self.assertEqual(env["GIT_CONFIG_VALUE_0"], "false")

        with patch.object(process.subprocess, "run", return_value=completed) as run:
            backend_run.capture(["git", "status"], Path("/tmp"))

        command = run.call_args.args[0]
        env = run.call_args.kwargs["env"]
        self.assertEqual(command[0], "/usr/bin/git")
        self.assertEqual(env["GIT_CONFIG_KEY_0"], "core.fsmonitor")
        self.assertEqual(env["GIT_CONFIG_VALUE_0"], "false")

    def test_workflow_commands_only_run_through_process_wrapper(self) -> None:
        scripts_dir = Path(__file__).resolve().parents[1]
        offenders = []
        for path in scripts_dir.rglob("*.py"):
            relative = path.relative_to(scripts_dir).as_posix()
            if relative.startswith("tests/") or relative == "momlib/process.py":
                continue
            if "subprocess.run(" in path.read_text(encoding="utf-8"):
                offenders.append(relative)

        self.assertEqual(offenders, [])

    def test_praxis_relative_keeps_external_artifact_paths_absolute(self) -> None:
        self.assertEqual(praxis.relative(Path("/private/tmp/praxis/report.json")), "/private/tmp/praxis/report.json")

    def test_command_audit_supports_engine_flag(self) -> None:
        with patch.object(task_module, "command_audit") as command_audit:
            self.assertEqual(task_module.run_praxis_system_action("command-audit", ["bun"]), 0)
            self.assertEqual(task_module.run_praxis_system_action("command-audit", ["auto"]), 0)
            self.assertEqual(task_module.run_praxis_system_action("command-audit", []), 0)

            with self.assertRaises(SystemExit) as exc:
                task_module.run_praxis_system_action("command-audit", ["invalid"])
            self.assertEqual(exc.exception.code, 1)

        command_audit.assert_has_calls([
            call("bun"),
            call("auto"),
            call("auto"),
        ])

    def test_system_praxis_profile_writes_report(self) -> None:
        with (
            patch.object(task_module, "praxis_profile_report", return_value=Path("/tmp/praxis-profile.json")) as profile,
            redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(task_module.run_praxis_system_action("praxis-profile", []), 0)

        profile.assert_called_once()
        self.assertIn("/tmp/praxis-profile.json", output.getvalue())

    def test_system_template_check_writes_report(self) -> None:
        with (
            patch.object(task_module, "template_check_report", return_value=Path("/tmp/template-report.json"), create=True) as report,
            redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(task_module.run_praxis_system_action("template-check", []), 0)

        report.assert_called_once()
        self.assertIn("/tmp/template-report.json", output.getvalue())

    def test_praxis_context_writes_ai_context_packet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            docs_root = Path(tmp_dir) / "docs"
            config = {
                "projects": {
                    "docs": {"path": str(docs_root)},
                    "backend": {"path": "ifc-mom-column-max", "defaultBranch": "local"},
                }
            }
            requirements.doc_init(config, "上下文包", "需要调整后端接口并验证。")

            with patch.object(task_module, "load_config", return_value=config), redirect_stdout(io.StringIO()) as output:
                exit_code = task_module.run_praxis_action("context", ["backend", "上下文包"])

            packet_path = praxis.PRAXIS_CONTEXT_DIR / "backend-上下文包.json"
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 0)
            self.assertIn("Praxis context packet:", output.getvalue())
            self.assertEqual(packet["schemaVersion"], 1)
            self.assertEqual(packet["project"], "backend")
            self.assertEqual(packet["requirementName"], "上下文包")
            self.assertEqual(packet["controlPlane"]["primaryCommand"], "task")
            self.assertIn("task context -- --brief backend 上下文包", packet["nextCommands"])
            self.assertIn("task gate -- ready backend 上下文包", packet["nextCommands"])
            self.assertNotIn("task gate -- guard backend 上下文包", packet["nextCommands"])
            self.assertNotIn("task gate -- change-check backend 上下文包", packet["nextCommands"])
            self.assertNotIn("roleVerdicts", packet)
            self.assertIn("explicit-confirmation-before-delivery-actions", packet["evidenceGates"])
            self.assertTrue(packet["facts"]["requirementDir"].endswith("上下文包"))
            packet_path.unlink(missing_ok=True)

    def test_praxis_preflight_and_all_gates_refresh_context_packet(self) -> None:
        config = {"projects": {"backend": {"path": "ifc-mom-column-max", "defaultBranch": "local"}}}
        with (
            patch.object(task_module, "load_config", return_value=config),
            patch.object(task_module, "praxis_context_packet") as context_packet,
            patch.object(task_module, "preflight", return_value=0) as preflight,
            patch.object(task_module, "guard_check", return_value=0) as guard_check,
            patch.object(task_module, "change_check", return_value=0) as change_check,
            patch.object(task_module, "migration_check", return_value=0) as migration_check,
        ):
            self.assertEqual(task_module.run_praxis_action("project", ["preflight", "backend", "上下文包"]), 0)
            self.assertEqual(task_module.run_praxis_action("gate", ["guard", "backend", "上下文包"]), 0)
            self.assertEqual(task_module.run_praxis_action("gate", ["change-check", "backend", "上下文包"]), 0)
            self.assertEqual(task_module.run_praxis_action("gate", ["migration-check", "backend", "上下文包"]), 0)

        self.assertEqual(context_packet.call_count, 4)
        preflight.assert_called_once_with(config, "backend", "上下文包")
        guard_check.assert_called_once_with(config, "backend", "上下文包")
        change_check.assert_called_once_with(config, "backend", "上下文包")
        migration_check.assert_called_once_with(config, "backend", "上下文包")

    def test_praxis_gate_ready_runs_aggregate_guard_once_and_writes_readiness_report(self) -> None:
        config = {"projects": {"backend": {"path": "ifc-mom-column-max", "defaultBranch": "local"}}}
        readiness_path = praxis.PRAXIS_CONTEXT_DIR.parent / "readiness" / "backend-重构.json"
        readiness_path.unlink(missing_ok=True)
        with (
            patch.object(task_module, "load_config", return_value=config),
            patch.object(
                task_module,
                "praxis_context_packet",
                return_value=praxis.PRAXIS_CONTEXT_DIR / "backend-重构.json",
            ) as context_packet,
            patch.object(task_module, "preflight", return_value=0) as preflight,
            patch.object(task_module, "guard_check", return_value=1) as guard_check,
            patch.object(task_module, "change_check", return_value=0) as change_check,
            patch.object(task_module, "migration_check", return_value=0) as migration_check,
            redirect_stdout(io.StringIO()) as output,
        ):
            exit_code = task_module.run_praxis_action("gate", ["ready", "backend", "重构"])

        report = json.loads(readiness_path.read_text(encoding="utf-8"))
        self.assertEqual(exit_code, 1)
        self.assertIn("Praxis readiness: FAIL", output.getvalue())
        self.assertEqual(report["schemaVersion"], 1)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["results"]["preflight"]["exitCode"], 0)
        self.assertEqual(report["results"]["guard"]["exitCode"], 1)
        self.assertNotIn("change-check", report["results"])
        self.assertNotIn("migration-check", report["results"])
        self.assertEqual(report["contextPacket"], praxis.relative(praxis.PRAXIS_CONTEXT_DIR / "backend-重构.json"))
        context_packet.assert_called_once_with(config, "backend", "重构")
        preflight.assert_called_once_with(config, "backend", "重构")
        guard_check.assert_called_once_with(config, "backend", "重构")
        change_check.assert_not_called()
        migration_check.assert_not_called()
        readiness_path.unlink(missing_ok=True)

    def test_praxis_delivery_status_dispatches_readonly_summary(self) -> None:
        config = {"projects": {"backend": {"path": "ifc-mom-column-max"}}}
        with (
            patch.object(task_module, "load_config", return_value=config),
            patch.object(task_module, "praxis_context_packet"),
            patch.object(task_module, "delivery_status") as delivery_status,
        ):
            exit_code = task_module.run_praxis_action("delivery", ["status", "backend", "重构"])

        self.assertEqual(exit_code, 0)
        delivery_status.assert_called_once_with(config, "backend", "重构")

    def test_praxis_gate_ready_all_groups_projects_and_returns_partial_failure(self) -> None:
        config = {
            "projects": {
                "backend": {"path": "ifc-mom-column-max"},
                "web": {"path": "ifc-web-mom-max"},
                "docs": {"path": "docs"},
            }
        }
        with (
            patch.object(task_module, "load_config", return_value=config),
            patch.object(task_module, "delivery_target_projects", return_value=["backend", "web"]),
            patch.object(task_module, "run_praxis_gate_single_action", side_effect=[0, 1]) as gate_action,
            redirect_stdout(io.StringIO()) as output,
        ):
            exit_code = task_module.run_praxis_action("gate", ["ready-all", "分层审核优化"])

        self.assertEqual(exit_code, 1)
        self.assertIn("backend: PASS", output.getvalue())
        self.assertIn("web: FAIL", output.getvalue())
        gate_action.assert_has_calls(
            [
                call(config, ["ready", "backend", "分层审核优化"]),
                call(config, ["ready", "web", "分层审核优化"]),
            ]
        )

    def test_praxis_delivery_all_actions_group_projects_and_return_partial_failure(self) -> None:
        config = {
            "projects": {
                "backend": {"path": "ifc-mom-column-max"},
                "web": {"path": "ifc-web-mom-max"},
            }
        }
        with (
            patch.object(task_module, "load_config", return_value=config),
            patch.object(task_module, "delivery_target_projects", return_value=["backend", "web"]),
            patch.object(task_module, "run_praxis_delivery_single_action", side_effect=[0, 1]) as delivery_action,
            redirect_stdout(io.StringIO()) as output,
        ):
            exit_code = task_module.run_praxis_action("delivery", ["deliver-all", "分层审核优化"])

        self.assertEqual(exit_code, 1)
        self.assertIn("backend: PASS", output.getvalue())
        self.assertIn("web: FAIL", output.getvalue())
        delivery_action.assert_has_calls(
            [
                call(config, ["deliver", "backend", "分层审核优化"]),
                call(config, ["deliver", "web", "分层审核优化"]),
            ]
        )

if __name__ == "__main__":
    unittest.main()
