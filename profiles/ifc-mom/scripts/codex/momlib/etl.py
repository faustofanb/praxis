from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from .docs import docs_root, find_requirement_dir, tolaria_frontmatter, timestamp, write_file_once
from .names import safe_path_leaf, today
from .process import fail


APP_NAMES = (
    "运营平台",
    "基础平台",
    "仓库管理",
    "供应协同",
    "生产制造",
    "质量管理",
    "设备管理",
    "计划排程",
)

MES_MENU_PATHS = (
    "00-系统业务建模",
    "工厂建模/厂区信息",
    "工厂建模/车间信息",
    "工厂建模/工位信息",
    "工厂建模/产线信息",
    "工厂建模/班次信息",
    "工厂建模/班组信息",
    "工厂建模/生产日历",
    "工厂建模/工艺建模/工序信息",
    "工厂建模/工艺建模/工序类型",
    "工厂建模/工艺建模/工艺路线",
    "工厂建模/排班管理/人员排班管理",
    "工厂建模/排班管理/班组排班管理",
    "工厂建模/作业时间/作业时间管理",
    "工厂建模/作业时间/作业状态维护管理",
    "生产工艺/工艺参数",
    "生产工艺/工艺配方",
    "生产计划/制造工单",
    "生产计划/生产任务",
    "生产计划/流程卡管理",
    "生产报工/挤压报工",
    "生产报工/抛丸报工",
    "生产报工/时效入炉",
    "生产报工/时效出炉",
    "生产报工/氧化上排",
    "生产报工/氧化下排",
    "生产报工/熔铸报工",
    "交班管理/交班方案",
    "交班管理/交班记录",
    "交班管理/交班报工记录",
    "生产报表/投入产出/挤压产出明细",
    "生产报表/投入产出/挤压产出汇总",
    "生产报表/投入产出/挤压产出趋势图（月）",
    "生产报表/投入产出/时效产出明细",
    "生产报表/投入产出/时效产出查询",
    "生产报表/投入产出/抛丸产出汇总",
    "生产报表/投入产出/抛丸产出查询",
    "生产报表/投入产出/抛丸投入查询",
    "生产报表/投入产出/氧化产出对比",
    "生产报表/人员作业/上岗记录",
    "生产报表/人员作业/岗位资质",
    "生产报表/人员作业/工时采集",
    "生产报表/人员作业/工时分摊",
    "工模管理/模具管理",
    "工模管理/冲具管理",
    "工模管理/工模保养",
    "工模管理/模具盘盈",
    "安灯呼叫/安灯记录",
    "安灯呼叫/异常配置",
    "能源管理",
    "平板指令/功能命令",
    "ESOP文档/产品作业SOP",
    "ESOP文档/设备作业SOP",
    "99-未归类",
)

MES_ORDERED_MENU_PATHS = {
    "00-系统业务建模": "00-系统业务建模",
    "工厂建模/厂区信息": "04-工厂建模/01-厂区信息",
    "工厂建模/车间信息": "04-工厂建模/02-车间信息",
    "工厂建模/产线信息": "04-工厂建模/03-产线信息",
    "工厂建模/工位信息": "04-工厂建模/04-工位信息",
    "工厂建模/工艺建模/工序信息": "04-工厂建模/05-工艺建模/01-工序信息",
    "工厂建模/工艺建模/工序类型": "04-工厂建模/05-工艺建模/02-工序类型",
    "工厂建模/工艺建模/工艺路线": "04-工厂建模/05-工艺建模/03-工艺路线",
    "工厂建模/班次信息": "04-工厂建模/06-班次信息",
    "工厂建模/班组信息": "04-工厂建模/07-班组信息",
    "工厂建模/生产日历": "04-工厂建模/08-生产日历",
    "工厂建模/作业时间/作业时间管理": "04-工厂建模/09-作业时间/01-作业时间管理",
    "工厂建模/作业时间/作业状态维护管理": "04-工厂建模/09-作业时间/02-作业状态维护管理",
    "工厂建模/排班管理/班组排班管理": "04-工厂建模/10-排班管理/01-班组排班管理",
    "工厂建模/排班管理/人员排班管理": "04-工厂建模/10-排班管理/02-人员排班管理",
    "工厂建模/99-未归类": "04-工厂建模/99-未归类",
    "生产工艺/工艺参数": "05-生产工艺/01-工艺参数",
    "生产工艺/工艺配方": "05-生产工艺/02-工艺配方",
    "生产计划/制造工单": "07-生产计划/01-制造工单",
    "生产计划/生产任务": "07-生产计划/02-生产任务",
    "生产计划/流程卡管理": "07-生产计划/03-流程卡管理",
    "交班管理/交班方案": "08-交班管理/01-交班方案",
    "交班管理/交班报工记录": "08-交班管理/02-交班报工记录",
    "交班管理/交班记录": "08-交班管理/04-交班记录",
    "工模管理/模具管理": "10-工模管理/01-模具管理",
    "工模管理/冲具管理": "10-工模管理/02-冲具管理",
    "工模管理/工模保养": "10-工模管理/03-工模保养",
    "工模管理/模具盘盈": "10-工模管理/04-模具盘盈",
    "平板指令/功能命令": "13-平板指令/01-功能命令",
    "生产报工/挤压报工": "18-生产报工/02-挤压报工",
    "生产报工/时效入炉": "18-生产报工/03-时效入炉",
    "生产报工/时效出炉": "18-生产报工/04-时效出炉",
    "生产报工/抛丸报工": "18-生产报工/05-抛丸报工",
    "生产报工/氧化上排": "18-生产报工/06-氧化上排",
    "生产报工/氧化下排": "18-生产报工/07-氧化下排",
    "生产报工/熔铸报工": "18-生产报工/08-熔铸报工",
    "能源管理": "22-能源管理",
    "ESOP文档/产品作业SOP": "23-ESOP文档/01-产品作业SOP",
    "ESOP文档/设备作业SOP": "23-ESOP文档/02-设备作业SOP",
    "生产报表/投入产出/挤压产出明细": "24-生产报表/01-投入产出/02-挤压产出明细",
    "生产报表/投入产出/挤压产出汇总": "24-生产报表/01-投入产出/03-挤压产出汇总",
    "生产报表/投入产出/挤压产出趋势图（月）": "24-生产报表/01-投入产出/04-挤压产出趋势图（月）",
    "生产报表/投入产出/时效产出明细": "24-生产报表/01-投入产出/05-时效产出明细",
    "生产报表/投入产出/时效产出查询": "24-生产报表/01-投入产出/06-时效产出查询",
    "生产报表/投入产出/抛丸产出汇总": "24-生产报表/01-投入产出/07-抛丸产出汇总",
    "生产报表/投入产出/抛丸产出查询": "24-生产报表/01-投入产出/08-抛丸产出查询",
    "生产报表/投入产出/抛丸投入查询": "24-生产报表/01-投入产出/09-抛丸投入查询",
    "生产报表/投入产出/氧化产出对比": "24-生产报表/01-投入产出/10-氧化产出对比",
    "生产报表/人员作业/上岗记录": "24-生产报表/02-人员作业/01-上岗记录",
    "生产报表/人员作业/岗位资质": "24-生产报表/02-人员作业/02-岗位资质",
    "生产报表/人员作业/工时采集": "24-生产报表/02-人员作业/03-工时采集",
    "生产报表/人员作业/工时分摊": "24-生产报表/02-人员作业/04-工时分摊",
    "安灯呼叫/安灯记录": "25-安灯呼叫/01-安灯记录",
    "安灯呼叫/异常配置": "25-安灯呼叫/02-异常配置",
    "99-未归类": "99-未归类",
}

TOPIC_FILES = (
    "指标口径卡.md",
    "ETL草案.sql",
    "对账说明.md",
    "MagicAPI契约.md",
    "积木报表契约.md",
    "验证SQL.sql",
)


def etl_root(config: dict[str, Any]) -> Path:
    root = docs_root(config) / "03-etl"
    root.mkdir(parents=True, exist_ok=True)
    return root


def ensure_etl_init(config: dict[str, Any]) -> Path:
    root = etl_root(config)
    write_file_once(
        root / "README.md",
        """# ETL资产中心

本目录沉淀 MOM 报表、统计、驾驶舱、MagicAPI 和积木报表可复用口径资产。

## 应用分类

- 运营平台
- 基础平台
- 仓库管理
- 供应协同
- 生产制造
- 质量管理
- 设备管理
- 计划排程

## 目录规则

```text
docs/03-etl/<应用>/<系统>/<一级菜单>/<二级菜单>/.../<中文主题>/
```

新主题优先按真实菜单路径建目录：

```text
docs/03-etl/<应用>/<系统>/<一级菜单>/<二级菜单>/.../<中文主题>/
```

口径资产优先沉淀参数化 PostgreSQL 函数；大表和日期范围报表必须让日期、租户、产线等条件进入源表查询分支。
""",
    )
    for app_name in APP_NAMES:
        app_dir = root / app_name
        app_dir.mkdir(parents=True, exist_ok=True)
        write_file_once(app_dir / "README.md", f"# {app_name}\n\n按系统和菜单路径沉淀 ETL 资产。\n")

    mes_root = root / "生产制造" / "MES"
    mes_root.mkdir(parents=True, exist_ok=True)
    write_file_once(
        mes_root / "README.md",
        """# MES

MES 报表与驾驶舱 ETL 资产按真实菜单路径归档。

## 建模入口

- [系统业务建模](00-系统业务建模/)
""",
    )
    for menu_path in MES_MENU_PATHS:
        menu_dir = mes_root.joinpath(*safe_ordered_menu_path_parts(menu_path))
        menu_dir.mkdir(parents=True, exist_ok=True)
        if not any(menu_dir.iterdir()):
            write_file_once(menu_dir / ".gitkeep", "")

    print(f"ETL root: {root}")
    return root


def validate_app_name(app_name: str) -> None:
    if app_name not in APP_NAMES:
        fail("应用必须是：" + "、".join(APP_NAMES))


def safe_menu_path_parts(menu_path: str) -> list[str]:
    parts = [part.strip() for part in menu_path.replace(">", "/").split("/") if part.strip()]
    if not parts:
        fail("菜单路径不能为空")
    return [safe_path_leaf(part) for part in parts]


def safe_ordered_menu_path_parts(menu_path: str) -> list[str]:
    ordered_path = MES_ORDERED_MENU_PATHS.get(menu_path, menu_path)
    return safe_menu_path_parts(ordered_path)


def topic_dir(
    config: dict[str, Any],
    app_name: str,
    system_name: str,
    menu_path: str,
    topic_name: str,
) -> Path:
    validate_app_name(app_name)
    return (
        etl_root(config)
        / app_name
        / safe_path_leaf(system_name)
        / Path(*safe_ordered_menu_path_parts(menu_path))
        / safe_path_leaf(topic_name)
    )


def relative_link(from_dir: Path, to_path: Path) -> str:
    return os.path.relpath(to_path, from_dir).replace(os.sep, "/")


def requirement_link(config: dict[str, Any], requirement_name: str | None, topic_path: Path) -> str:
    if not requirement_name:
        return "待补充"
    req_dir = find_requirement_dir(config, requirement_name)
    return f"[{requirement_name}]({relative_link(topic_path, req_dir)}/)"


def write_requirement_etl_link(config: dict[str, Any], requirement_name: str, topic_path: Path) -> None:
    req_dir = find_requirement_dir(config, requirement_name)
    output_dir = req_dir / "04-产出物"
    link = relative_link(output_dir, topic_path)
    write_file_once(
        output_dir / "ETL资产链接.md",
        tolaria_frontmatter(
            "requirement-etl-link",
            "ETL资产链接",
            timestamp(),
            ["ifc-mom/requirement", "ifc-mom/etl"],
            {"requirement": requirement_name},
        )
        + f"""# ETL资产链接

- [{topic_path.name}]({link}/)
- [[{topic_path.name}]]
""",
    )


def create_etl_topic(
    config: dict[str, Any],
    app_name: str,
    system_name: str,
    menu_path: str,
    topic_name: str,
    requirement_name: str | None = None,
    menu_code: str | None = None,
    menu_name: str | None = None,
    status: str = "草案",
) -> Path:
    ensure_etl_init(config)
    path = topic_dir(config, app_name, system_name, menu_path, topic_name)
    path.mkdir(parents=True, exist_ok=True)
    created_at = timestamp()
    menu_code_text = menu_code or "待确认"
    menu_name_text = menu_name or "待确认"
    req_text = requirement_link(config, requirement_name, path)

    write_file_once(
        path / "README.md",
        tolaria_frontmatter(
            "etl-asset",
            topic_name,
            created_at,
            ["ifc-mom/etl", f"ifc-mom/{system_name}"],
            {
                "app": app_name,
                "system": system_name,
                "menu_path": menu_path,
                "status": status,
            },
        )
        + f"""# {topic_name}

## 基本信息

- 应用：{app_name}
- 系统：{system_name}
- 菜单路径：{menu_path}
- 菜单编码：{menu_code_text}
- 菜单名称：{menu_name_text}
- 当前状态：{status}
- 需求来源：{req_text}

## 资产文件

- [指标口径卡](指标口径卡.md)
- [ETL草案](ETL草案.sql)
- [对账说明](对账说明.md)
- [MagicAPI契约](MagicAPI契约.md)
- [积木报表契约](积木报表契约.md)
- [验证SQL](验证SQL.sql)

## Tolaria 知识链接

- 当前资产：[[{topic_name}]]
- 指标口径卡：[[{topic_name} 指标口径卡]]
- 需求来源：{req_text}

## 建模原则

- 大表和日期范围报表优先使用 `fn_rpt_api_*` 参数化函数。
- 日期、租户、产线、班次、物料等参数必须进入源表查询分支，禁止全量查出后外层过滤。
- 核心口径沉淀在 PostgreSQL 函数/视图，MagicAPI 和积木报表只消费稳定契约。
""",
    )
    write_file_once(
        path / "指标口径卡.md",
        tolaria_frontmatter(
            "etl-metric-card",
            f"{topic_name} 指标口径卡",
            created_at,
            ["ifc-mom/etl", "ifc-mom/metric"],
            {
                "asset": topic_name,
                "version": "v1",
                "system": system_name,
            },
        )
        + f"""# {topic_name} 指标口径卡

## 归属

- 应用：{app_name}
- 系统：{system_name}
- 菜单路径：{menu_path}
- 菜单编码：{menu_code_text}
- 菜单名称：{menu_name_text}

## 知识链接

- ETL资产：[[{topic_name}]]
- 资产README：[README](README.md)

## 指标定义

- 指标名称：待补充
- 指标版本：v1
- 统计粒度：待补充
- 时间口径：待补充
- 单位口径：待补充
- 数据范围：待补充
- 排除规则：待补充
- 公式：待补充

## 参数边界

- tenant_id：必须下推到源表过滤。
- 日期范围：必须下推到源表过滤，使用半开区间 `[start_date, end_date)`。
- 其他业务参数：待补充。

## 证据

- 菜单证据：待补充。
- 表字段证据：待补充。
- 样例数据：待补充。
- 对账报表：待补充。
""",
    )
    write_file_once(
        path / "ETL草案.sql",
        f"""-- {topic_name} ETL 草案
-- 约束：大表和日期范围报表必须使用参数化函数，并在源表分支内过滤。

-- create or replace function public.fn_rpt_api_<topic>(
--   p_tenant_id bigint,
--   p_start_date date,
--   p_end_date date
-- )
-- returns table (
--   tenant_id bigint
-- )
-- language sql
-- stable
-- as $$
--   select src.tenant_id
--   from <source_table> src
--   where src.tenant_id = p_tenant_id
--     and src.<time_column> >= p_start_date
--     and src.<time_column> < p_end_date
-- $$;
""",
    )
    write_file_once(path / "对账说明.md", f"# {topic_name} 对账说明\n\n## 对账目标\n\n待补充。\n")
    write_file_once(path / "MagicAPI契约.md", f"# {topic_name} MagicAPI契约\n\n## 接口\n\n待补充。\n")
    write_file_once(path / "积木报表契约.md", f"# {topic_name} 积木报表契约\n\n## 数据集\n\n待补充。\n")
    write_file_once(
        path / "验证SQL.sql",
        f"""-- {topic_name} 验证 SQL
-- 固定同一数据源、同一统计时刻、同一参数范围对账。
""",
    )
    for filename in TOPIC_FILES:
        (path / filename).touch(exist_ok=True)

    if requirement_name:
        write_requirement_etl_link(config, requirement_name, path)

    print(f"ETL topic: {path}")
    return path


def print_etl_tree(config: dict[str, Any], max_depth: int = 4) -> None:
    root = etl_root(config)
    print(root)
    root_depth = len(root.parts)
    for current, dirs, _files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        current_path = Path(current)
        depth = len(current_path.parts) - root_depth
        if depth >= max_depth:
            dirs[:] = []
            continue
        if current_path == root:
            continue
        indent = "  " * depth
        print(f"{indent}- {current_path.name}/")


def etl_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="task etl")
    subparsers = parser.add_subparsers(dest="action", required=True)

    subparsers.add_parser("init", help="初始化 ETL 应用分类和 MES 模块骨架")

    subject = subparsers.add_parser("subject", help="创建一个 ETL 主题资产目录")
    subject.add_argument("app_name")
    subject.add_argument("system_name")
    subject.add_argument("menu_or_module_name")
    subject.add_argument("topic_name")
    subject.add_argument("--menu-path", help="真实菜单路径，支持 / 或 > 分隔；优先于位置参数")
    subject.add_argument("--requirement")
    subject.add_argument("--menu-code")
    subject.add_argument("--menu-name")
    subject.add_argument("--status", default="草案")

    tree = subparsers.add_parser("tree", help="打印 ETL 目录树")
    tree.add_argument("--max-depth", type=int, default=4)

    return parser


def run_etl_action(config: dict[str, Any], args: list[str]) -> None:
    parser = etl_parser()
    parsed = parser.parse_args(args)
    if parsed.action == "init":
        ensure_etl_init(config)
    elif parsed.action == "subject":
        create_etl_topic(
            config,
            parsed.app_name,
            parsed.system_name,
            parsed.menu_path or parsed.menu_or_module_name,
            parsed.topic_name,
            parsed.requirement,
            parsed.menu_code,
            parsed.menu_name,
            parsed.status,
        )
    elif parsed.action == "tree":
        print_etl_tree(config, parsed.max_depth)
    else:
        fail(f"unknown etl action: {parsed.action}")
