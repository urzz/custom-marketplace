# cc-marketplace

一个用于组织和分发 Claude Code 插件的轻量级 marketplace 仓库。

当前仓库包含：

- `openclaw-plugin`：提供 `/openclaw-skill-creator` 技能，用于帮助用户起草 OpenClaw skill。
- `dev-stack`：提供 `/skill-forge` 技能，用于创建、设计和改进 Claude Code skill。
- `nuclio`：提供 Nucl.io 文件驱动生命周期技能：`/nuclio:project-init`、`/nuclio:brief`、`/nuclio:design`、`/nuclio:implement`、`/nuclio:verify`、`/nuclio:fold`。

## 仓库结构

- `.claude-plugin/marketplace.json`：市场清单，声明当前 marketplace 暴露的插件。
- `plugins/<plugin-name>/.claude-plugin/plugin.json`：插件元数据。
- `plugins/<plugin-name>/skills/<skill-name>/SKILL.md`：技能定义。
- `plugins/<plugin-name>/references/`：插件级共享协议、设计约束或参考资料（如 Nuclio）。
- `plugins/<plugin-name>/agents/`：插件随附的子代理定义（如 Nuclio implementer/reviewer/fixer）。
- `plugins/<plugin-name>/scripts/`：插件随附的确定性辅助脚本与测试（如 Nuclio state/task helper）。

## 维护方式

新增或修改插件时，通常需要同时更新：

1. `plugins/` 下对应插件目录
2. 根目录 `.claude-plugin/marketplace.json`
3. 相关 README / CLAUDE 说明与本地校验命令

新增或修改 skill 时，保持当前目录约定：

```text
plugins/<plugin-name>/skills/<skill-name>/SKILL.md
```

Nuclio 的 skill 行为还需要与以下内容保持一致：

- `plugins/nuclio-plugin/references/protocol.md`
- `plugins/nuclio-plugin/references/context-manifest.md`
- `plugins/nuclio-plugin/references/lightweight-sdd.md`
- `plugins/nuclio-plugin/agents/*.md`
- `plugins/nuclio-plugin/scripts/*.py`

## 本地校验

当前仓库没有独立的 package/build 工作流，但可以先做基础静态校验：

```bash
python3 -m json.tool .claude-plugin/marketplace.json >/dev/null
python3 -m json.tool plugins/openclaw-plugin/.claude-plugin/plugin.json >/dev/null
python3 -m json.tool plugins/dev-stack/.claude-plugin/plugin.json >/dev/null
python3 -m json.tool plugins/nuclio-plugin/.claude-plugin/plugin.json >/dev/null
```

Nuclio helper 与插件严格校验：

```bash
python3 -m unittest discover -s plugins/nuclio-plugin/scripts -p 'test_*.py'
claude plugin validate plugins/nuclio-plugin --strict
```

如需检查 skill 文件，可重点审阅：

```bash
find plugins -path '*/skills/*/SKILL.md' -type f | sort
```
