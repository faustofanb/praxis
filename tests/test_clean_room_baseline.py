from __future__ import annotations

import json

from praxis import __version__
from praxis.cli import main


def test_version_is_2() -> None:
    assert __version__ == "2.0.0"


def test_cli_version_is_machine_readable(capsys) -> None:
    assert main(["version", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True, "data": {"version": "2.0.0"}}


def test_cli_version_is_human_readable(capsys) -> None:
    assert main(["version"]) == 0
    assert capsys.readouterr().out == "2.0.0\n"
