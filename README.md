# cc-marketplace

用于组织和分发 Claude Code 插件的轻量级 Marketplace 仓库。

## 插件

| 插件 | 技能 | 用途 |
|---|---|---|
| `openclaw-plugin` | `/openclaw-skill-creator` | 起草和维护 OpenClaw skill |
| `dev-stack` | `/skill-forge`、`/commit` | 创建、修改或审查 Claude Code skill；基于当前 staged diff 生成 Conventional Commit |
| `nuclio` | `/nuclio:init`、`/nuclio:work` | Nuclio v2 4.2.1 的 `.dev-docs` 初始化与 file-first change 工作流 |

Nuclio 的 active change 和新 archive 都完整保留 `change.md`、`plan.yaml`、`state.yaml`。Plan v2 默认把产品 Task 和 repair 委派给 subagent，只有通过 low/self/单 Task/精确文件硬门槛并经用户批准后才允许主会话直接实施；独立 review 使用 fresh read-only subagent。工作流同时包含自然语言批准、approval checkpoint、Git-bound validation/review evidence、一次选择即可写入或跳过知识并归档的收尾交互、显式 knowledge result、可恢复 archive，以及只接受已归档 successor 的 predecessor 收口。

## 仓库结构

```text
.claude-plugin/marketplace.json
plugins/
└── <plugin-name>/
    ├── .claude-plugin/plugin.json
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
