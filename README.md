# cc-marketplace

一个用于组织和分发 Claude Code 插件的轻量级 marketplace 仓库。

当前仓库包含：

- `openclaw-plugin`：提供 `/openclaw-skill-creator` 技能，用于帮助用户起草 OpenClaw skill。
- `dev-stack`：提供 `/skill-creator` 技能，用于创建、设计和改进 Claude Code skill。

## 仓库结构

- `.claude-plugin/marketplace.json`：市场清单，声明当前 marketplace 暴露的插件。
- `plugins/<plugin-name>/.claude-plugin/plugin.json`：插件元数据。
- `plugins/<plugin-name>/skills/<skill-name>/SKILL.md`：技能定义。

## 维护方式

新增或修改插件时，通常需要同时更新：

1. `plugins/` 下对应插件目录
2. 根目录 `.claude-plugin/marketplace.json`

## 本地校验

当前仓库没有独立的构建流程，但可以先做基础静态校验：

```bash
jq . .claude-plugin/marketplace.json >/dev/null \
  && jq . plugins/openclaw-plugin/.claude-plugin/plugin.json >/dev/null \
  && jq . plugins/dev-stack/.claude-plugin/plugin.json >/dev/null
```

如需检查 `skill-creator` 内容，可重点审阅：

```bash
find plugins/dev-stack/skills/skill-creator -maxdepth 3 -type f | sort
```
