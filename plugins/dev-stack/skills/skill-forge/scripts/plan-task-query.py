#!/usr/bin/env python3
"""plan-task-query.py — 从 plan YAML 中提取单个 Task 的 brief 文档。

用法:
    python3 plan-task-query.py <plan_yaml_path> <task_id>

行为:
    1. 读取 <plan_yaml_path>（YAML 格式，schema 含 goal/architecture/global_constraints/tasks）
    2. 在 tasks 列表中查找 id == <task_id> 的节点
    3. 将该 Task 节点全部字段与顶层 global_constraints 合并为一个 brief 文档
    4. 写入唯一命名临时文件（tempfile.mkstemp，后缀 .md），打印文件绝对路径到 stdout

错误处理:
    - Plan 文件不存在 → 打印 "ERROR: plan file not found" 到 stderr，exit 1
    - task_id 不存在 → 打印 "ERROR: task <id> not found in plan" 到 stderr，exit 1
    - YAML 解析失败 → 打印 "ERROR: invalid YAML: <原因>" 到 stderr，exit 1
"""

import os
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


def main():
    if len(sys.argv) != 3:
        print("usage: python3 plan-task-query.py <plan_yaml_path> <task_id>", file=sys.stderr)
        sys.exit(1)

    plan_path = sys.argv[1]
    task_id_str = sys.argv[2]

    # Step 1: 检查文件存在性
    if not os.path.isfile(plan_path):
        print("ERROR: plan file not found", file=sys.stderr)
        sys.exit(1)

    # Step 2: 读取并解析 YAML
    try:
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"ERROR: invalid YAML: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: invalid YAML: {e}", file=sys.stderr)
        sys.exit(1)

    if plan is None or not isinstance(plan, dict):
        print("ERROR: invalid YAML: plan root is empty or not a mapping", file=sys.stderr)
        sys.exit(1)

    # Step 3: 提取 global_constraints
    global_constraints = plan.get("global_constraints", [])

    # Step 4: 在 tasks 列表中查找 id == task_id 的节点
    tasks = plan.get("tasks", [])
    if not isinstance(tasks, list):
        tasks = []

    # 支持 task_id 为数字或字符串，做宽松匹配
    matched_task = None
    for t in tasks:
        if not isinstance(t, dict):
            continue
        tid = t.get("id")
        # 尝试字符串比较和数字比较
        if str(tid) == str(task_id_str):
            matched_task = t
            break

    if matched_task is None:
        print(f"ERROR: task {task_id_str} not found in plan", file=sys.stderr)
        sys.exit(1)

    # Step 5: 生成 brief 文档
    brief = _format_task_brief(matched_task, global_constraints)

    # Step 6: 写入唯一命名临时文件
    fd, tmp_path = tempfile.mkstemp(suffix=".md", prefix="plan-task-brief-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(brief)
    except Exception as e:
        print(f"ERROR: failed to write temp file: {e}", file=sys.stderr)
        sys.exit(1)

    # Step 7: 打印绝对路径到 stdout
    print(os.path.abspath(tmp_path))


if __name__ == "__main__":
    main()
