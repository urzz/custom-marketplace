#!/usr/bin/env python3
"""plan-task-query.py — 从 plan YAML 中提取单个 Task 的 brief 文档。

用法:
    python3 plan-task-query.py <plan_yaml_path> <task_id>
        [--output PATH] [--format markdown|json]

行为:
    1. 读取 <plan_yaml_path>（YAML 格式，schema 含 goal/architecture/global_constraints/tasks）
    2. 在 tasks 列表中查找 id == <task_id> 的节点
    3. 将该 Task 节点全部字段与顶层 global_constraints 合并为一个 brief 文档
    4. 默认写入唯一命名临时 Markdown；指定 --output 时写稳定 Markdown/JSON 路径
    5. 所有成功调用都把输出文件绝对路径打印到 stdout

错误处理:
    - Plan 文件不存在 → 打印 "ERROR: plan file not found" 到 stderr，exit 1
    - task_id 不存在 → 打印 "ERROR: task <id> not found in plan" 到 stderr，exit 1
    - YAML 解析失败 → 打印 "ERROR: invalid YAML: <原因>" 到 stderr，exit 1
    - 稳定输出已存在 → 拒绝覆盖，打印 "ERROR: output already exists"，exit 1
"""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

try:
    import yaml
except ImportError:
    sys.exit("requires pyyaml")


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
        for i, item in enumerate(value):
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
    # 如果是 dict 或其他结构，走通用格式化
    return _format_value(constraints, 0)


def _format_task_brief(task, global_constraints):
    """生成 Task brief 文档（markdown 格式）。"""
    task_id = task.get("id", "?")
    task_name = task.get("name", "Unnamed Task")

    sections = []

    # Section: Global Constraints
    sections.append("## Global Constraints")
    sections.append(_format_constraints(global_constraints))
    sections.append("")

    # Section: Task
    header = f"## Task {task_id}: {task_name}"
    sections.append(header)
    sections.append("")

    # 输出 task 中除 id/name 之外的全部字段（id/name 已在 header 中）
    # 但也保留 id/name 以确保 "全部字段" 的要求
    # 按照 task 字段出现顺序输出
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
    parser.add_argument("--output", help="稳定输出路径；已存在时拒绝覆盖")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    return parser.parse_args(argv)


def _load_task(plan_path, task_id_str):
    if not os.path.isfile(plan_path):
        raise ValueError("plan file not found")
    try:
        with open(plan_path, "r", encoding="utf-8") as handle:
            plan = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"invalid YAML: {exc}") from exc
    if not isinstance(plan, dict):
        raise ValueError("invalid YAML: plan root is empty or not a mapping")
    tasks = plan.get("tasks", [])
    if not isinstance(tasks, list):
        tasks = []
    matched_task = next(
        (
            task for task in tasks
            if isinstance(task, dict) and str(task.get("id")) == str(task_id_str)
        ),
        None,
    )
    if matched_task is None:
        raise ValueError(f"task {task_id_str} not found in plan")
    return plan, matched_task


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


def _write_stable_output(path, content):
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8") as handle:
            handle.write(content)
    except FileExistsError as exc:
        raise ValueError(f"output already exists: {output}") from exc
    return output


def main(argv=None):
    args = _parse_args(argv)
    try:
        plan, task = _load_task(args.plan_yaml_path, args.task_id)
        content = _render(plan, task, args.format)
        if args.output:
            output = _write_stable_output(args.output, content)
        else:
            if args.format != "markdown":
                raise ValueError("--format json requires --output")
            job_dir = os.environ.get("CLAUDE_JOB_DIR")
            temp_dir = Path(job_dir) / "tmp" if job_dir else None
            if temp_dir is not None:
                temp_dir.mkdir(parents=True, exist_ok=True)
            fd, temp_path = tempfile.mkstemp(
                suffix=".md", prefix="plan-task-brief-", dir=temp_dir,
            )
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
            output = Path(temp_path).resolve()
        print(output)
        return 0
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
