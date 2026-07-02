from __future__ import annotations

import datetime as dt
import re


def safe_branch_leaf(value: str) -> str:
    """Keep Chinese names but remove characters Git branch names cannot use."""
    value = re.sub(r"[\s~^:?*\[\\\]]+", "-", value.strip())
    value = re.sub(r"/+", "/", value)
    return value.strip(".-/") or "task"


def safe_path_leaf(value: str) -> str:
    """把分支名转换成可用于目录名的片段。"""
    return safe_branch_leaf(value).replace("/", "-")


def today() -> str:
    """返回需求文档目录使用的日期格式。"""
    return dt.datetime.now().strftime("%Y-%m-%d")


def branch_today() -> str:
    """返回分支名使用的紧凑日期格式。"""
    return dt.datetime.now().strftime("%Y%m%d")
