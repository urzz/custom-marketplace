# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 仓库定位

这是一个 Claude Code 插件市场仓库，不是传统应用仓库。当前代码的主要职责是声明“有哪些插件可被发现”和“每个插件暴露哪些技能”。

核心层级只有三层：

1. `/.claude-plugin/marketplace.json`：市场入口，注册插件列表。
2. `/plugins/<plugin-name>/.claude-plugin/plugin.json`：单个插件的元数据入口。
3. `/plugins/<plugin-name>/skills/<skill-name>/SKILL.md`：技能定义，使用 frontmatter + 提示词正文。

当前仓库当前已注册插件：`openclaw-plugin`，它提供 `/openclaw-skill-creator` 技能。

## 关键文件

- `.claude-plugin/marketplace.json`：决定 Claude Code 能发现哪些插件。
- `plugins/openclaw-plugin/.claude-plugin/plugin.json`：定义插件名称、描述、版本。
- `plugins/openclaw-plugin/skills/<skill-name>/SKILL.md`：定义技能描述与实际提示词。

## 修改时要同步的地方

### 新增或修改插件

如果插件目录或插件元数据有变化，通常需要同时检查两处：

- `plugins/<plugin-name>/...`
- `.claude-plugin/marketplace.json`

也就是说，插件实现和市场注册信息必须保持一致，尤其是：

- 插件 `name`
- 市场里的 `source`
- 插件目录名

### 新增或修改技能

技能以文件系统目录组织，沿用当前模式：

```text
plugins/<plugin-name>/skills/<skill-name>/SKILL.md
```

`SKILL.md` 当前采用的约定是：

- frontmatter 描述技能元信息
- 正文直接作为技能提示词

## 常用命令

这个仓库当前没有 `package.json`，也没有独立的 build / lint / test 流程。日常开发主要是编辑清单和技能文件，并做最小静态校验。

```bash
git status --short
```

```bash
git ls-tree -r --name-only HEAD
```

```bash
jq . .claude-plugin/marketplace.json >/dev/null && jq . plugins/openclaw-plugin/.claude-plugin/plugin.json >/dev/null
```

```bash
claude --version
```

## 当前已知约束

- 仓库当前没有应用代码、测试代码或构建脚本；不要假设存在 npm / pnpm / bun 工作流。
- 仓库当前没有 `.cursorrules`、`.cursor/rules/` 或 `.github/copilot-instructions.md`。
- 若后续新增更多插件，优先保持现有“市场清单 → 插件元数据 → 技能目录”的层级不变。
