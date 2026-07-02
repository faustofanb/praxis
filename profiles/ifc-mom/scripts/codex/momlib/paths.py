from pathlib import Path


# 所有脚本都从聚合工作区根目录解析路径，避免在子项目目录运行时路径漂移。
ROOT_DIR = Path(__file__).resolve().parents[3]
PRAXIS_CONFIG_DIR = ROOT_DIR / ".praxis"
PRAXIS_OUTPUT_DIR = PRAXIS_CONFIG_DIR / "out"
CONFIG_FILE = ROOT_DIR / "praxis.projects.toml"
LEGACY_CONFIG_FILE = ROOT_DIR / ".codex" / "workspace-projects.toml"
