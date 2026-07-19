from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)


def require_ok(proc: subprocess.CompletedProcess[str], label: str) -> None:
    if proc.returncode != 0:
        raise SystemExit(f"{label} 失败\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")


def main() -> int:
    dist = ROOT / "dist"
    if dist.exists():
        shutil.rmtree(dist)
    require_ok(run([sys.executable, "-m", "build"], cwd=ROOT), "wheel build")
    wheels = sorted(dist.glob("*.whl"))
    if not wheels:
        raise SystemExit("未生成 wheel")
    wheel = wheels[-1]
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        venv = tmp_path / "venv"
        require_ok(run([sys.executable, "-m", "venv", str(venv)], cwd=tmp_path), "创建临时环境")
        scripts = venv / ("Scripts" if os.name == "nt" else "bin")
        py = scripts / ("python.exe" if os.name == "nt" else "python")
        praxis = scripts / ("praxis.exe" if os.name == "nt" else "praxis")
        require_ok(run([str(py), "-m", "pip", "install", str(wheel)], cwd=tmp_path), "安装 wheel")
        outside = tmp_path / "outside"
        outside.mkdir()
        for label, args in [
            ("doctor", [str(praxis), "doctor", "--json"]),
            ("python module help", [str(py), "-m", "praxis", "--help"]),
            ("workspace init", [str(praxis), "workspace", "init", "--profile", "base", "--json"]),
            ("profile mom", [str(praxis), "profile", "resolve", "mom", "--json"]),
            ("profile aotu", [str(praxis), "profile", "resolve", "aotu", "--json"]),
        ]:
            proc = run(args, cwd=outside)
            require_ok(proc, label)
            if args[-1] == "--json":
                payload = json.loads(proc.stdout)
                if not payload.get("ok"):
                    raise SystemExit(f"{label} JSON ok=false")
    print(f"wheel 验证通过：{wheel.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
