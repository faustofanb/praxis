from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import task as task_module  # noqa: E402
from momlib import praxis_contracts  # noqa: E402
from praxislib import codegraph_adapter  # noqa: E402


class CodeGraphAdapterTest(unittest.TestCase):
    def test_run_codegraph_fails_cleanly_when_cli_is_missing(self) -> None:
        with (
            patch.object(codegraph_adapter.shutil, "which", return_value=None),
            redirect_stderr(io.StringIO()) as error_output,
            self.assertRaises(SystemExit) as raised,
        ):
            codegraph_adapter.run_codegraph(Path("/repo"), ["status"])

        self.assertEqual(raised.exception.code, 1)
        self.assertIn("codegraph CLI not found", error_output.getvalue())

    def test_run_codegraph_forwards_allowed_command_in_workspace(self) -> None:
        completed = Mock(returncode=7)
        with (
            patch.object(codegraph_adapter.shutil, "which", return_value="/bin/codegraph"),
            patch.object(codegraph_adapter, "run_command", return_value=completed) as run,
        ):
            exit_code = codegraph_adapter.run_codegraph(Path("/repo"), ["explore", "auth flow"])

        self.assertEqual(exit_code, 7)
        run.assert_called_once_with(["/bin/codegraph", "explore", "auth flow"], cwd=Path("/repo"), check=False)

    def test_run_codegraph_init_excludes_local_index_from_git_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            exclude = root / ".git" / "info" / "exclude"
            exclude.parent.mkdir(parents=True)
            exclude.write_text("# local excludes\n", encoding="utf-8")
            completed = Mock(returncode=0)

            with (
                patch.object(codegraph_adapter.shutil, "which", return_value="/bin/codegraph"),
                patch.object(codegraph_adapter, "run_command", return_value=completed),
            ):
                exit_code = codegraph_adapter.run_codegraph(root, ["init"])

            self.assertEqual(exit_code, 0)
            self.assertIn(".codegraph/", exclude.read_text(encoding="utf-8"))

    def test_task_system_dispatches_codegraph(self) -> None:
        with patch.object(task_module, "run_codegraph", return_value=0) as run:
            exit_code = task_module.run_praxis_system_action("codegraph", ["query", "UserService"])

        self.assertEqual(exit_code, 0)
        run.assert_called_once_with(Path.cwd(), ["query", "UserService"])

    def test_task_top_level_codegraph_dispatches(self) -> None:
        with (
            patch.object(task_module, "run_codegraph", return_value=0) as run,
            self.assertRaises(SystemExit) as raised,
        ):
            task_module.main(["codegraph", "status"])

        self.assertEqual(raised.exception.code, 0)
        run.assert_called_once_with(Path.cwd(), ["status"])

    def test_command_contract_lists_codegraph_commands(self) -> None:
        commands = praxis_contracts.praxis_commands()

        self.assertIn("system codegraph init", commands)
        self.assertIn("system codegraph explore <query>", commands)
        self.assertIn("system codegraph impact <symbol>", commands)


if __name__ == "__main__":
    unittest.main()
