#!/usr/bin/env python3
"""校验本仓库的双平台本地插件合同；不替代客户端加载或公共目录上架校验。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
VERSION = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")


class Invalid(ValueError):
    """可操作的本地包校验错误。"""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Invalid(message)


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(isinstance(key, str), "配置键必须为字符串")
        require(key not in result, f"重复配置键：{key}")
        result[key] = value
    return result


class UniqueLoader(yaml.SafeLoader):
    pass


def yaml_mapping(loader, node):
    return unique_pairs(loader.construct_pairs(node, deep=True))


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, yaml_mapping)


def read_object(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
        value = (json.loads(text, object_pairs_hook=unique_pairs) if path.suffix == ".json"
                 else yaml.load(text, Loader=UniqueLoader))
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise Invalid(f"{path}: {error}") from error
    require(isinstance(value, dict), f"{path}: 必须是对象")
    return value


def frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---(?:\n|$)", text, re.S)
    require(match is not None, f"{path}: 缺少合法 frontmatter")
    try:
        value = yaml.load(match.group(1), Loader=UniqueLoader)
    except (ValueError, yaml.YAMLError) as error:
        raise Invalid(f"{path}: {error}") from error
    require(isinstance(value, dict), f"{path}: frontmatter 必须是对象")
    return value


def nonempty(obj: dict, key: str, label: str) -> str:
    value = obj.get(key)
    require(isinstance(value, str) and bool(value.strip()), f"{label}: {key} 必须是非空字符串")
    return value


def local_path(root: Path, value: str) -> Path:
    require(isinstance(value, str) and value.startswith("./"), f"source 必须以 ./ 开始：{value}")
    require("\\" not in value and ".." not in PurePosixPath(value).parts, f"source 路径越界：{value}")
    path = (root / value).resolve()
    require(path.is_relative_to(root.resolve()), f"source 路径越界：{value}")
    require(path.is_dir(), f"source 目录不存在：{value}")
    return path


def entries(market: dict, label: str) -> dict:
    name = nonempty(market, "name", label)
    require(NAME.fullmatch(name) is not None, f"{label}: 无效 marketplace 名称")
    plugins = market.get("plugins")
    require(isinstance(plugins, list) and bool(plugins), f"{label}: plugins 必须为非空列表")
    result = {}
    for entry in plugins:
        require(isinstance(entry, dict), f"{label}: plugin entry 必须为对象")
        name = nonempty(entry, "name", label)
        require(name not in result, f"{label}: 重复插件 {name}")
        result[name] = entry
    return result


def validate_links(path: Path, boundary: Path) -> None:
    """检查正文链接的资源随插件分发；忽略代码示例、URL 和页内锚点。"""
    fence = None
    for line in path.read_text(encoding="utf-8").splitlines():
        marker = re.match(r"\s*(`{3,}|~{3,})", line)
        if marker:
            current = marker.group(1)
            if fence is None:
                fence = current
            elif current[0] == fence[0] and len(current) >= len(fence):
                fence = None
            continue
        if fence:
            continue
        for target in re.findall(r"\[[^\]\n]+\]\(([^)\n]+)\)", line):
            if target.startswith("#") or re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target):
                continue
            target = target.split("#", 1)[0]
            resolved = (path.parent / target).resolve()
            require(resolved.is_relative_to(boundary.resolve()), f"{path}: 链接越出包目录：{target}")
            require(resolved.is_file(), f"{path}: 链接资源不存在：{target}")


def validate_skill(skill: Path) -> None:
    metadata = frontmatter(skill)
    allowed = {"name", "description", "license", "allowed-tools", "metadata", "disable-model-invocation"}
    require(not (metadata.keys() - allowed), f"{skill}: 未校验的 frontmatter 字段 {metadata.keys() - allowed}")
    name = nonempty(metadata, "name", str(skill))
    require(name == skill.parent.name and NAME.fullmatch(name) is not None and len(name) <= 64,
            f"{skill}: 技能名称与目录不匹配或不合法")
    require(len(nonempty(metadata, "description", str(skill))) <= 1024, f"{skill}: description 过长")
    explicit = metadata.get("disable-model-invocation", False)
    require(type(explicit) is bool, f"{skill}: disable-model-invocation 必须为布尔值")
    config_path = skill.parent / "agents" / "openai.yaml"
    config = read_object(config_path)
    require(not (config.keys() - {"interface", "policy", "dependencies"}), f"{config_path}: 未知字段")
    interface = config.get("interface")
    require(isinstance(interface, dict), f"{config_path}: 缺少 interface")
    nonempty(interface, "display_name", str(config_path))
    nonempty(interface, "short_description", str(config_path))
    policy = config.get("policy")
    require(isinstance(policy, dict), f"{config_path}: 缺少 policy")
    implicit = policy.get("allow_implicit_invocation")
    require(type(implicit) is bool and implicit is (not explicit), f"{skill}: 两端调用策略不一致")


def validate(root: Path) -> dict[str, int]:
    root = root.resolve()
    claude = read_object(root / ".claude-plugin" / "marketplace.json")
    codex = read_object(root / ".agents" / "plugins" / "marketplace.json")
    cc_entries = entries(claude, "Claude marketplace")
    cx_entries = entries(codex, "Codex marketplace")
    require(claude["name"] == codex["name"], "两端 marketplace 名称不一致")
    require(list(cc_entries) == list(cx_entries), "两端插件集合或展示顺序不一致")
    count = 0
    declared = set()
    for name, entry in cc_entries.items():
        require(NAME.fullmatch(name) is not None, f"无效插件名称：{name}")
        plugin = local_path(root, entry.get("source"))
        require(plugin.is_relative_to(root / "plugins"), f"{name}: 插件必须位于 plugins/ 下")
        declared.add(plugin)
        cx_entry = cx_entries[name]
        source = cx_entry.get("source")
        require(isinstance(source, dict) and set(source) == {"source", "path"} and source["source"] == "local",
                f"{name}: Codex source 必须为 local 对象")
        require(local_path(root, source["path"]) == plugin, f"{name}: 两端 source 不一致")
        require(cx_entry.get("policy") == {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                f"{name}: marketplace policy 与当前分发合同不一致")
        cc = read_object(plugin / ".claude-plugin" / "plugin.json")
        cx = read_object(plugin / ".codex-plugin" / "plugin.json")
        for key in ("name", "version", "description"):
            value = nonempty(cc, key, name)
            require(value == cx.get(key) == entry.get(key), f"{name}: {key} 在两端清单与索引中不一致")
        require(cc["name"] == name, f"{name}: manifest name 不一致")
        require(VERSION.fullmatch(cc["version"]) is not None, f"{name}: 版本必须为稳定 semver")
        require(cx.get("skills") == "./skills/", f"{name}: 两端必须共用 skills/")
        require(isinstance(cx.get("author"), dict), f"{name}: 缺少 author")
        nonempty(cx["author"], "name", name)
        interface = cx.get("interface")
        require(isinstance(interface, dict), f"{name}: 缺少 Codex interface")
        for key in ("displayName", "shortDescription", "longDescription", "developerName", "category"):
            nonempty(interface, key, name)
        require(interface["category"] == cx_entry.get("category"), f"{name}: category 不一致")
        skills = sorted((plugin / "skills").glob("*/SKILL.md"))
        require(bool(skills), f"{name}: 未发现技能")
        for skill in skills:
            validate_skill(skill)
            count += 1
        for directory in ("skills", "references", "agents"):
            for document in (plugin / directory).rglob("*.md"):
                validate_links(document, plugin)
    actual = {p.parent.parent.resolve() for p in (root / "plugins").glob("*/.claude-plugin/plugin.json")}
    actual |= {p.parent.parent.resolve() for p in (root / "plugins").glob("*/.codex-plugin/plugin.json")}
    require(actual == declared, "存在未注册或重复指向的插件目录")
    for name in ("README.md", "AGENTS.md", "CLAUDE.md"):
        validate_links(root / name, root)
    require("@AGENTS.md" in (root / "CLAUDE.md").read_text(encoding="utf-8"), "CLAUDE.md 未引用共享 AGENTS.md")
    return {"plugins": len(cc_entries), "skills": count}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Marketplace 仓库根目录")
    args = parser.parse_args()
    try:
        result = validate(args.root)
    except (Invalid, OSError, yaml.YAMLError) as error:
        print(f"验证失败：{error}", file=sys.stderr)
        return 1
    print(f"本地双平台合同通过：{result['plugins']} 个插件，{result['skills']} 个技能。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
