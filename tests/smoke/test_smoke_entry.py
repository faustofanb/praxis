from __future__ import annotations

import os
import subprocess
import sys

from conftest import ROOT


def test_praxis_smoke_entry_runs():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    proc = subprocess.run(
        [sys.executable, "-m", "praxis.smoke"],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0
    assert "ok" in proc.stdout
