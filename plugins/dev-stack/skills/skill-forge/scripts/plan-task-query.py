#!/usr/bin/env python3
"""plan-task-query.py — 从 plan YAML 中提取单个 Task 的稳定 brief 文档。

用法:
    python3 plan-task-query.py <plan_yaml_path> <task_id>
        --output PATH [--format markdown|json]

行为:
    1. 读取 <plan_yaml_path>（YAML 格式，schema 含 goal/architecture/global_constraints/tasks）
    2. 使用 plan_contract.py 执行共享 Plan 合同校验与 legacy risk 默认映射
    3. 在 tasks 列表中查找 id == <task_id> 的节点
    4. 将该 Task 节点全部字段与顶层 global_constraints 合并为稳定 brief 文档
    5. 成功调用把输出文件绝对路径打印到 stdout

错误处理:
    - Plan 文件不存在或 YAML 解析失败 → 打印 "ERROR: invalid plan: <原因>" 到 stderr，exit 1
    - task_id 不存在 → 打印 "ERROR: task <id> not found in plan" 到 stderr，exit 1
    - 未提供 --output → 打印 "ERROR: --output is required" 到 stderr，exit 1
    - 输出不在同一 .skill-forge run 目录 → 打印 "ERROR: output must be inside plan run directory"，exit 1
    - 稳定输出已存在 → 拒绝覆盖，打印 "ERROR: output already exists"，exit 1
"""

import argparse
import json
from pathlib import Path
import sys

from plan_contract import PlanContractError, find_skill_forge_run_dir, load_plan_contract, path_is_within


class PlanTaskQueryError(Exception):
    """User-facing plan-task-query failure."""


def _format_value(value, indent=0):
    """将任意 YAML 值格式化为可读文本（递归处理 dict/list/scalar）。"""
    pad = "  " * indent
    lines = []
    if isinstance(value, dict):
        for k, v in value.items():
            if isinstance(v, (dict, list)):
                lines.append(f"{pad}**{k}:**")
                lines.append(_format_value(v, indent + 1))
            else:
                lines.append(f"{pad}**{k}:** {v}")
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}-")
                lines.append(_format_value(item, indent + 1))
            else:
                lines.append(f"{pad}- {item}")
    else:
        lines.append(f"{pad}{value}")
    return "\n".join(lines)


def _format_constraints(constraints):
    """格式化 global_constraints 列表。"""
    if not constraints:
        return "_(none)_"
    if isinstance(constraints, list):
        lines = []
        for i, item in enumerate(constraints, 1):
            if isinstance(item, (dict, list)):
                lines.append(f"{i}. ")
                lines.append(_format_value(item, 1))
            else:
                lines.append(f"{i}. {item}")
        return "\n".join(lines)
    return _format_value(constraints, 0)


def _format_task_brief(task, global_constraints):
    """生成 Task brief 文档（markdown 格式）。"""
    task_id = task.get("id", "?")
    task_name = task.get("name", "Unnamed Task")

    sections = []
    sections.append("## Global Constraints")
    sections.append(_format_constraints(global_constraints))
    sections.append("")
    sections.append(f"## Task {task_id}: {task_name}")
    sections.append("")

    for key, val in task.items():
        sections.append(f"### {key}")
        if isinstance(val, (dict, list)):
            sections.append(_format_value(val, 0))
        else:
            sections.append(str(val))
        sections.append("")

    return "\n".join(sections)


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="从 plan YAML 中提取单个 Task 的稳定 brief。",
    )
    parser.add_argument("plan_yaml_path")
    parser.add_argument("task_id")
    parser.add_argument("--output", required=True, help="稳定输出路径；必须位于同一 .skill-forge run 目录；已存在时拒绝覆盖")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    return parser.parse_args(argv)


def _load_task(plan_path, task_id_str):
    try:
        contract = load_plan_contract(plan_path)
    except PlanContractError as exc:
        detail = f": {exc.detail}" if exc.detail else ""
        raise PlanTaskQueryError(f"invalid plan: {exc.code}{detail}") from exc
    matched_task = contract.tasks.get(str(task_id_str))
    if matched_task is None:
        raise PlanTaskQueryError(f"task {task_id_str} not found in plan")
    return contract.plan, matched_task


def _render(plan, task, output_format):
    if output_format == "markdown":
        return _format_task_brief(task, plan.get("global_constraints", []))
    payload = {
        "schema_version": 1,
        "goal": plan.get("goal"),
        "architecture": plan.get("architecture"),
        "global_constraints": plan.get("global_constraints", []),
        "task": task,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _write_stable_output(plan_path, output_path, content):
    run_dir = find_skill_forge_run_dir(plan_path)
    if run_dir is None:
        raise PlanTaskQueryError("plan must be inside a .skill-forge run directory")
    output = Path(output_path).expanduser().resolve()
    if not path_is_within(output, run_dir):
        raise PlanTaskQueryError("output must be inside plan run directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8") as handle:
            handle.write(content)
    except FileExistsError as exc:
        raise PlanTaskQueryError(f"output already exists: {output}") from exc
    return output


def main(argv=None):
    args = _parse_args(argv)
    try:
        plan, task = _load_task(args.plan_yaml_path, args.task_id)
        content = _render(plan, task, args.format)
        output = _write_stable_output(args.plan_yaml_path, args.output, content)
        print(output)
        return 0
    except PlanTaskQueryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
