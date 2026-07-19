from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from .paths import CONFIG_FILE, LEGACY_CONFIG_FILE, ROOT_DIR
from .process import fail

ROOT_PROJECTS_FILE = ROOT_DIR / "praxis.projects.toml"


def load_config() -> dict[str, Any]:
    """读取 Praxis 项目索引，优先使用根目录配置。

    `.praxis/projects.toml` 只作为旧版本兼容入口；新项目应使用根目录
    `praxis.projects.toml`，让第一次接入 Praxis 的用户可以直接看到
    需要维护的项目边界。
    """
    config_file = ROOT_PROJECTS_FILE if ROOT_PROJECTS_FILE.is_file() else CONFIG_FILE
    if not config_file.is_file():
        config_file = LEGACY_CONFIG_FILE
    if not config_file.is_file():
        fail(f"missing config: {ROOT_PROJECTS_FILE}")
    with config_file.open("rb") as file:
        payload = tomllib.load(file)
    payload.setdefault("_praxis", {})["configSource"] = str(config_file.relative_to(ROOT_DIR))
    return payload


def projects(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """返回所有项目短名到项目配置的映射。"""
    return config.get("projects", {})


def project_config(config: dict[str, Any], name: str) -> dict[str, Any]:
    """按项目短名读取项目配置，不存在时给出明确错误。"""
    project = projects(config).get(name)
    if not project:
        fail(f"unknown project: {name}")
    return project


def local_database_config(config: dict[str, Any]) -> dict[str, str]:
    """读取当前 workspace 的本地数据库目标。

    同一个 dbx 连接可能挂多个本地库；库名是 workspace 事实，不能从共享
    workflow profile 推导。
    """
    local = config.get("database", {}).get("local", {})
    connection = str(local.get("connection") or "LOCAL").strip() or "LOCAL"
    database = str(local.get("database") or "").strip()
    schema = str(local.get("schema") or "public").strip() or "public"
    return {"connection": connection, "database": database, "schema": schema}


def project_dir(config: dict[str, Any], name: str) -> Path:
    """把项目短名解析为真实子仓库路径。"""
    project = project_config(config, name)
    path = project.get("path")
    if not path:
        fail(f"project has no path: {name}")
    repo_dir = ROOT_DIR / path
    if not repo_dir.is_dir():
        fail(f"project path not found: {path}")
    return repo_dir
