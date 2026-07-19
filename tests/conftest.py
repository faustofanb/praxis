from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_praxis(*args: str, cwd: Path | None = None, env: dict[str, str] | None = None):
    merged = os.environ.copy()
    merged["PYTHONPATH"] = str(ROOT / "src")
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, "-m", "praxis", *args],
        cwd=cwd or ROOT,
        text=True,
        capture_output=True,
        env=merged,
        check=False,
    )


def read_json(proc: subprocess.CompletedProcess[str]):
    return json.loads(proc.stdout)
