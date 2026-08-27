# cc-marketplace

用于组织和分发 Claude Code 插件的轻量级 Marketplace 仓库。

## 插件

| 插件 | 技能 | 用途 |
|---|---|---|
| `openclaw-plugin` | `/openclaw-skill-creator` | 起草和维护 OpenClaw skill |
| `dev-stack` | `/skill-forge`、`/commit`、`/commit-and-push` | 创建、修改或审查 Claude Code skill；安全创建单个 Conventional Commit，并可在验证后普通推送当前分支 |
| `nuclio` | `/nuclio:init`、`/nuclio:work` | Nuclio v3 5.1.4 的 `.dev-docs` 知识骨架与 file-first change 交付工作流 |

Nuclio v3 5.1.4 的 active change 和新 archive 都完整保留 `change.md`、`delivery.yaml`、`state.yaml`。`/nuclio:init` 与 `/nuclio:work` 始终在调用开始时的当前模式内运行，不进入或退出 Claude Code Plan Mode；若调用时已经处于 Plan Mode，则停止并要求退出后重新显式调用。`/nuclio:work` 通过 Plan Mode 边界后先发现非 archive 的直接 active change 候选：无候选时进入 Shape，唯一候选时才以目录名调用 `status --id <change-id> --json`，多个候选则停止并报告歧义。用户只确认一次结果合同；Claude Code 主会话自主维护 delivery milestone、直接实施或按需使用有界 Agent，并直接运行定义的检查，再由 Runtime 记录和验证当前依据。当前请求或已加载项目上下文绑定 Open Design `project-id` 时，`/nuclio:work` 可在 Shape 通过用户已配置的 MCP 只读获取设计，批准后将完整交付固化到固定目录 `.dev-docs/artifacts/open-design/` 再实施，knowledge 只接收提炼后的稳定项目事实。可选 `nuclio:readonly-reviewer` 的工具精确限制为 `Read`、`Grep`、`Glob`，只返回 findings。Runtime 仍只提供 `create`、`approve`、`status`、`record-check`、`verify`、`complete`、`archive` 七个命令；工作流采用 index-first 知识读取、一次知识决定、明确知识结果与可恢复完整 archive。

## 仓库结构

```text
.claude-plugin/marketplace.json
plugins/
└── <plugin-name>/
    ├── .claude-plugin/plugin.json
    ├── agents/*.md                  # 可选：tool-scoped agent 定义
    ├── skills/<skill-name>/SKILL.md
    ├── references/                  # 可选：插件级参考资料
    └── scripts/                     # 可选：确定性 helper 与测试
```

skill 也可以在自身目录下使用 `references/`、`scripts/` 等辅助目录。Nuclio 的当前运行时权威位于 `plugins/nuclio-plugin/skills/`、`references/` 和 `scripts/`；`plugins/nuclio-plugin/docs/research/` 仅保留历史设计背景。

仓库维护规则见 `CLAUDE.md`。

## 本地验证

仓库没有独立的应用构建流程。修改后按影响范围运行以下检查：

```bash
python3 -m json.tool .claude-plugin/marketplace.json >/dev/null
python3 -m json.tool plugins/openclaw-plugin/.claude-plugin/plugin.json >/dev/null
python3 -m json.tool plugins/dev-stack/.claude-plugin/plugin.json >/dev/null
python3 -m json.tool plugins/nuclio-plugin/.claude-plugin/plugin.json >/dev/null
```

```bash
python3 -m unittest discover -s plugins/dev-stack/skills/skill-forge/scripts -p 'test_*.py'
python3 plugins/dev-stack/skills/skill-forge/scripts/plan_contract.py --help >/dev/null
claude plugin validate plugins/dev-stack --strict
```

```bash
python3 plugins/nuclio-plugin/scripts/change.py --help >/dev/null
python3 -m unittest discover -s plugins/nuclio-plugin/scripts -p 'test_*.py'
claude plugin validate plugins/nuclio-plugin --strict
```
