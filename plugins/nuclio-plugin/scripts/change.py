#!/usr/bin/env python3
"""
Nuclio v2 change.md helper.

## Contents
- [CLI](#cli)
- [Path safety](#path-safety)
- [Frontmatter](#frontmatter)
- [Commands](#commands)
- [Legacy move](#legacy-move)
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

COMMANDS = ("create", "list", "show", "set-status", "archive", "legacy-move")
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
GLOB_CHARS = set("*?[]{}")
FRONTMATTER_KEYS = {"id", "status", "created", "updated", "related_changes"}
V1_MARKER_FILES = {"contract.yaml", "context.jsonl", "state.json"}
V1_MARKER_DIRS = {"packets", "evidence"}
SKELETON_TEMPLATES = {
    "index.md": (
        "# Project Knowledge Index\n"
        "\n"
        "Nuclio v2 文档库用于保存可恢复的 change 摘要和经确认的长期项目知识；代码、配置、测试、CI 和 Git working tree 仍是执行事实。\n"
        "\n"
        "## Knowledge\n"
        "\n"
        "- `knowledge/project.md`: 产品目标、用户、术语和跨领域事实。\n"
        "- `knowledge/architecture.md`: 架构约束、系统边界和重要设计关系。\n"
        "- `knowledge/engineering.md`: 构建、测试、发布、协作和代码实践。\n"
        "\n"
        "## Changes\n"
        "\n"
        "Active changes live in `.dev-docs/changes/<change-id>/change.md`.\n"
        "\n"
        "Completed changes move to `.dev-docs/changes/archive/<change-id>/change.md`.\n"
        "\n"
        "Do not create `.dev-docs/changes/"
        "index.md`; root index does not enumerate active or archived changes.\n"
        "\n"
        "## Legacy\n"
        "\n"
        "Legacy material lives under `.dev-docs/legacy/` and is not read by default.\n"
    ),
    "knowledge/project.md": (
        "# Project Knowledge\n"
        "\n"
        "This file records confirmed product goals, users, terminology, and cross-domain facts that remain useful across changes.\n"
        "\n"
        "## Confirmed Knowledge\n"
        "\n"
        "No confirmed project knowledge has been recorded yet.\n"
    ),
    "knowledge/architecture.md": (
        "# Architecture Knowledge\n"
        "\n"
        "This file records confirmed architecture constraints, system boundaries, and important design relationships that remain useful across changes.\n"
        "\n"
        "## Confirmed Knowledge\n"
        "\n"
        "No confirmed architecture knowledge has been recorded yet.\n"
    ),
    "knowledge/engineering.md": (
        "# Engineering Knowledge\n"
        "\n"
        "This file records confirmed build, test, release, collaboration, and code practice knowledge that remains useful across changes.\n"
        "\n"
        "## Confirmed Knowledge\n"
        "\n"
        "No confirmed engineering knowledge has been recorded yet.\n"
    ),
}


class ChangeError(Exception):
    pass


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def docs(self) -> Path:
        return self.root / ".dev-docs"

    @property
    def changes(self) -> Path:
        return self.docs / "changes"

    @property
    def archive(self) -> Path:
        return self.changes / "archive"

    @property
    def legacy(self) -> Path:
        return self.docs / "legacy"

    @property
    def legacy_v1(self) -> Path:
        return self.legacy / "v1"

    @property
    def tmp(self) -> Path:
        return self.root / ".dev-docs-v1-legacy-tmp"


@dataclass
class Frontmatter:
    lines: list[str]
    close_index: int
    values: dict[str, str]
    positions: dict[str, int]


@dataclass(frozen=True)
class LegacyFeatures:
    is_v2: bool
    has_v1: bool
    has_changes_index: bool
    protocol_paths: tuple[str, ...]


# CLI

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Nuclio v2 change.md file helper")
    parser.add_argument("--project-root", default=".", help="project root path; defaults to current directory")
    subparsers = parser.add_subparsers(dest="command", metavar="{" + ",".join(COMMANDS) + "}", required=True)

    create = subparsers.add_parser("create", help="create one active change.md")
    create.add_argument("--id", required=True)
    create.add_argument("--title", required=True)
    create.add_argument("--goal", required=True)
    create.add_argument("--related-change", action="append", default=[])
    create.add_argument("--date")
    create.set_defaults(func=cmd_create)

    list_cmd = subparsers.add_parser("list", help="list active change directories")
    list_cmd.set_defaults(func=cmd_list)

    show = subparsers.add_parser("show", help="show one change.md")
    show.add_argument("--id", required=True)
    show.add_argument("--archived", action="store_true")
    show.set_defaults(func=cmd_show)

    set_status = subparsers.add_parser("set-status", help="set active change status")
    set_status.add_argument("--id", required=True)
    set_status.add_argument("--status", required=True, choices=("active", "completed"))
    set_status.add_argument("--date")
    set_status.set_defaults(func=cmd_set_status)

    archive = subparsers.add_parser("archive", help="archive a completed active change")
    archive.add_argument("--id", required=True)
    archive.set_defaults(func=cmd_archive)

    legacy = subparsers.add_parser("legacy-move", help="move a clear v1 .dev-docs tree under v2 legacy/v1")
    legacy.set_defaults(func=cmd_legacy_move)
    return parser


# Path safety

def resolve_root(path: str) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def validate_id(change_id: str) -> str:
    if not change_id:
        raise ChangeError("change id is required")
    if any(ch in change_id for ch in GLOB_CHARS):
        raise ChangeError(f"invalid change id: {change_id}")
    if any(part in change_id for part in ("/", "\\")):
        raise ChangeError(f"invalid change id: {change_id}")
    if Path(change_id).is_absolute() or ".." in change_id:
        raise ChangeError(f"invalid change id: {change_id}")
    if not ID_RE.fullmatch(change_id):
        raise ChangeError(f"invalid change id: {change_id}")
    return change_id


def ensure_under_root(path: Path, root: Path) -> Path:
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ChangeError(f"path escapes project root: {path}") from exc
    return path


def active_change_dir(paths: Paths, change_id: str) -> Path:
    validate_id(change_id)
    return ensure_under_root(paths.changes / change_id, paths.root)


def archive_change_dir(paths: Paths, change_id: str) -> Path:
    validate_id(change_id)
    return ensure_under_root(paths.archive / change_id, paths.root)


def rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


# Frontmatter

def line_body_and_newline(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    if line.endswith("\r"):
        return line[:-1], "\r"
    return line, ""


def parse_frontmatter_text(text: str) -> Frontmatter:
    lines = text.splitlines(keepends=True)
    if not lines:
        raise ChangeError("missing frontmatter")
    first, _ = line_body_and_newline(lines[0])
    if first != "---":
        raise ChangeError("missing frontmatter")
    close_index = -1
    for index in range(1, len(lines)):
        body, _ = line_body_and_newline(lines[index])
        if body == "---":
            close_index = index
            break
    if close_index == -1:
        raise ChangeError("unclosed frontmatter")

    values: dict[str, str] = {}
    positions: dict[str, int] = {}
    for index in range(1, close_index):
        body, _ = line_body_and_newline(lines[index])
        if ":" not in body:
            continue
        key, value = body.split(":", 1)
        if key in FRONTMATTER_KEYS:
            if key in values:
                raise ChangeError(f"duplicate frontmatter key: {key}")
            values[key] = value.strip()
            positions[key] = index
    return Frontmatter(lines=lines, close_index=close_index, values=values, positions=positions)


def read_frontmatter(path: Path) -> tuple[str, Frontmatter]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ChangeError(f"missing change.md: {path}") from exc
    return text, parse_frontmatter_text(text)


def rewrite_frontmatter(path: Path, updates: dict[str, str]) -> None:
    text, fm = read_frontmatter(path)
    _ = text
    missing = [key for key in updates if key not in fm.positions]
    if missing:
        raise ChangeError(f"missing frontmatter key: {', '.join(missing)}")
    new_lines = list(fm.lines)
    for key, value in updates.items():
        index = fm.positions[key]
        _, newline = line_body_and_newline(new_lines[index])
        new_lines[index] = f"{key}: {value}{newline}"
    path.write_text("".join(new_lines), encoding="utf-8")


def frontmatter_status(path: Path) -> str:
    _, fm = read_frontmatter(path)
    status = fm.values.get("status")
    if status not in {"active", "completed"}:
        return "unknown"
    return status


def h1_title_from_text(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# ") and line[2:].strip():
            return line[2:].strip()
    return "unknown"


# Commands

def date_arg(value: str | None) -> str:
    if value is None:
        return _dt.date.today().isoformat()
    try:
        _dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ChangeError(f"invalid date: {value}") from exc
    return value


def require_v2_skeleton(paths: Paths) -> None:
    required_files = [
        paths.docs / "index.md",
        paths.docs / "knowledge" / "project.md",
        paths.docs / "knowledge" / "architecture.md",
        paths.docs / "knowledge" / "engineering.md",
    ]
    required_dirs = [paths.archive, paths.legacy]
    for path in required_files:
        ensure_under_root(path, paths.root)
        if not path.is_file():
            raise ChangeError(f"required file missing: {path}")
    for path in required_dirs:
        ensure_under_root(path, paths.root)
        if not path.is_dir():
            raise ChangeError(f"required directory missing: {path}")


def cmd_create(args: argparse.Namespace, paths: Paths) -> int:
    change_id = validate_id(args.id)
    for related in args.related_change:
        validate_id(related)
    title = args.title.strip()
    goal = args.goal.strip()
    if not title:
        raise ChangeError("title must be non-empty")
    if not goal:
        raise ChangeError("goal must be non-empty")
    today = date_arg(args.date)
    require_v2_skeleton(paths)
    active_dir = active_change_dir(paths, change_id)
    archived_dir = archive_change_dir(paths, change_id)
    if active_dir.exists():
        raise ChangeError(f"active change already exists: {active_dir}")
    if archived_dir.exists():
        raise ChangeError(f"archived change already exists: {archived_dir}")
    active_dir.mkdir(parents=False)
    related = ", ".join(args.related_change)
    change = active_dir / "change.md"
    content = (
        "---\n"
        f"id: {change_id}\n"
        "status: active\n"
        f"created: {today}\n"
        f"updated: {today}\n"
        f"related_changes: {related}\n"
        "---\n\n"
        f"# {title}\n\n"
        "## Goal\n\n"
        f"{goal}\n\n"
        "## Current State\n\n"
        "新建 change，等待计划、实现和验证记录。\n"
    )
    change.write_text(content, encoding="utf-8")
    print(rel(change, paths.root))
    return 0


def cmd_list(args: argparse.Namespace, paths: Paths) -> int:
    _ = args
    if not paths.changes.is_dir():
        raise ChangeError(f"changes directory missing: {paths.changes}")
    entries: list[tuple[str, str, str, str]] = []
    for item in sorted(paths.changes.iterdir(), key=lambda p: p.name):
        if item.name == "archive":
            continue
        try:
            ensure_under_root(item, paths.root)
        except ChangeError:
            continue
        if not item.is_dir():
            continue
        change_id = item.name
        change = item / "change.md"
        try:
            ensure_under_root(change, paths.root)
        except ChangeError:
            continue
        status = "unknown"
        title = "unknown"
        if change.is_file():
            try:
                text = change.read_text(encoding="utf-8")
                fm = parse_frontmatter_text(text)
                parsed_status = fm.values.get("status")
                if parsed_status in {"active", "completed"}:
                    status = parsed_status
                title = h1_title_from_text(text)
            except (OSError, UnicodeDecodeError, ChangeError):
                status = "unknown"
                title = "unknown"
        entries.append((change_id, status, title, rel(change, paths.root)))
    for row in entries:
        print("\t".join(row))
    return 0


def cmd_show(args: argparse.Namespace, paths: Paths) -> int:
    directory = archive_change_dir(paths, args.id) if args.archived else active_change_dir(paths, args.id)
    change = directory / "change.md"
    if not change.is_file():
        raise ChangeError(f"missing change.md: {change}")
    sys.stdout.write(change.read_text(encoding="utf-8"))
    return 0


def cmd_set_status(args: argparse.Namespace, paths: Paths) -> int:
    change_id = validate_id(args.id)
    change = active_change_dir(paths, change_id) / "change.md"
    today = date_arg(args.date)
    _, fm = read_frontmatter(change)
    for key in ("status", "updated"):
        if key not in fm.positions:
            raise ChangeError(f"missing frontmatter key: {key}")
    rewrite_frontmatter(change, {"status": args.status, "updated": today})
    return 0


def cmd_archive(args: argparse.Namespace, paths: Paths) -> int:
    source = active_change_dir(paths, args.id)
    target = archive_change_dir(paths, args.id)
    change = source / "change.md"
    if not source.is_dir():
        raise ChangeError(f"active change missing: {source}")
    if target.exists():
        raise ChangeError(f"archive target already exists: {target}")
    status = frontmatter_status(change)
    if status != "completed":
        raise ChangeError(f"change must be completed before archive: {source}")
    source.rename(target)
    print(rel(target, paths.root))
    return 0


# Legacy move

def v2_skeleton_exists(paths: Paths) -> bool:
    return (
        (paths.docs / "index.md").is_file()
        and (paths.docs / "knowledge" / "project.md").is_file()
        and (paths.docs / "knowledge" / "architecture.md").is_file()
        and (paths.docs / "knowledge" / "engineering.md").is_file()
        and paths.archive.is_dir()
        and paths.legacy.is_dir()
    )


def inspect_legacy_features(paths: Paths) -> LegacyFeatures:
    docs = paths.docs
    if not docs.exists() or not docs.is_dir():
        raise ChangeError(f".dev-docs directory missing: {docs}")
    protocol_paths: list[str] = []
    changes = paths.changes
    if changes.is_dir():
        for change_dir in sorted(changes.iterdir(), key=lambda p: p.name):
            if not change_dir.is_dir() or change_dir.name == "archive":
                continue
            for marker in V1_MARKER_FILES:
                marker_path = change_dir / marker
                if marker_path.exists():
                    protocol_paths.append(rel(marker_path, paths.root))
            for marker in V1_MARKER_DIRS:
                marker_path = change_dir / marker
                if marker_path.is_dir():
                    protocol_paths.append(rel(marker_path, paths.root))
    changes_index = (changes / "index.md").is_file()
    has_protocol = bool(protocol_paths)
    has_v1 = has_protocol or (changes_index and has_protocol)
    return LegacyFeatures(
        is_v2=v2_skeleton_exists(paths),
        has_v1=has_v1,
        has_changes_index=changes_index,
        protocol_paths=tuple(protocol_paths),
    )


def create_v2_skeleton(paths: Paths) -> list[Path]:
    created: list[Path] = []

    def make_dir(path: Path) -> None:
        if not path.exists():
            path.mkdir()
            created.append(path)

    def write_file(path: Path, content: str) -> None:
        if path.exists():
            raise ChangeError(f"unexpected existing skeleton file: {path}")
        path.write_text(content, encoding="utf-8")
        created.append(path)

    make_dir(paths.docs)
    make_dir(paths.docs / "knowledge")
    make_dir(paths.changes)
    make_dir(paths.archive)
    make_dir(paths.legacy)
    for relative_path, content in SKELETON_TEMPLATES.items():
        write_file(paths.docs / relative_path, content)
    return created


def remove_empty_parents(path: Path, stop: Path) -> None:
    current = path
    while current != stop and current.exists():
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def cleanup_created_skeleton(created: Iterable[Path], paths: Paths) -> None:
    for path in reversed(list(created)):
        try:
            ensure_under_root(path, paths.root)
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        except (OSError, ChangeError):
            continue
    remove_empty_parents(paths.docs, paths.root)


def status_report(paths: Paths) -> str:
    return (
        f".dev-docs exists={paths.docs.exists()} "
        f".dev-docs-v1-legacy-tmp exists={paths.tmp.exists()} "
        f".dev-docs/legacy/v1 exists={paths.legacy_v1.exists()}"
    )


def cmd_legacy_move(args: argparse.Namespace, paths: Paths) -> int:
    _ = args
    features = inspect_legacy_features(paths)
    if features.is_v2 and features.has_v1:
        raise ChangeError("conflicting v1 and v2 .dev-docs features")
    if features.is_v2:
        raise ChangeError(".dev-docs is already v2")
    if not features.has_v1:
        raise ChangeError(".dev-docs is not a clear v1 tree")
    if paths.tmp.exists():
        raise ChangeError(f"temporary target exists: {paths.tmp}")
    if paths.legacy_v1.exists():
        raise ChangeError(f"legacy target exists: {paths.legacy_v1}")

    created: list[Path] = []
    moved_to_tmp = False
    try:
        paths.docs.rename(paths.tmp)
        moved_to_tmp = True
        created = create_v2_skeleton(paths)
        paths.tmp.rename(paths.legacy_v1)
        print(rel(paths.legacy_v1, paths.root))
        return 0
    except Exception as exc:
        if moved_to_tmp:
            cleanup_created_skeleton(created, paths)
            if paths.tmp.exists() and not paths.docs.exists():
                try:
                    paths.tmp.rename(paths.docs)
                except OSError:
                    pass
        raise ChangeError(f"legacy-move failed; {status_report(paths)}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = resolve_root(args.project_root)
    paths = Paths(root=root)
    try:
        return args.func(args, paths)
    except ChangeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"filesystem error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
