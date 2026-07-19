# cc-marketplace

一个用于组织和分发 Claude Code 插件的轻量级 marketplace 仓库。

当前仓库包含：

- `openclaw-plugin`：提供 `/openclaw-skill-creator` 技能，用于帮助用户起草 OpenClaw skill。
- `dev-stack`：提供 `/skill-forge` 与 `/commit` 技能；`/skill-forge` 用于创建、设计和改进 Claude Code skill，`/commit` 用于分析当前 Git 变更、生成单个 Conventional Commit，并在安全门禁下选择性暂存和提交。
- `nuclio`：提供 Nucl.io 文件驱动 Contract Workbench：`/nuclio:init`、`/nuclio:work`、`/nuclio:finish`。

## 仓库结构

- `.claude-plugin/marketplace.json`：市场清单，声明当前 marketplace 暴露的插件。
- `plugins/<plugin-name>/.claude-plugin/plugin.json`：插件元数据。
- `plugins/<plugin-name>/skills/<skill-name>/SKILL.md`：技能定义。
- `plugins/<plugin-name>/skills/<skill-name>/references/`：skill 级协议、设计约束或参考资料（如 dev-stack/skill-forge 的 review-state 协议与模板；`plugins/dev-stack/skills/commit/references/` 存放 `/commit` 的变更分析和提交策略）。
- `plugins/<plugin-name>/skills/<skill-name>/scripts/`：skill 级确定性辅助脚本与测试（如 dev-stack/skill-forge 的 `review-state-helper.py`、`plan-task-query.py` 与 unittest；`/commit` 当前不使用 skill-forge agents、scripts 或 review-state helper）。
- `plugins/<plugin-name>/references/`：插件级共享协议、设计约束或参考资料（如 Nuclio）。
- `plugins/<plugin-name>/agents/`：插件级有界子代理定义（如 dev-stack/skill-forge 的 bounded implementer/reviewer/fixer/final reviewer，以及 Nuclio agents）。
- `plugins/<plugin-name>/scripts/`：插件级确定性辅助脚本与测试（如 Nuclio contract/context/state/packet/evidence/migration helpers）。
- `plugins/nuclio-plugin/docs/research/contract-workbench-redesign/`：Nuclio Contract Workbench 重构的历史研究与设计材料；它们用于追溯设计依据，不是运行时行为权威，运行协议仍以 `plugins/nuclio-plugin/references/` 为准。

## 维护方式

新增或修改插件时，通常需要同时更新：

1. `plugins/` 下对应插件目录
2. 根目录 `.claude-plugin/marketplace.json`
3. 相关 README / CLAUDE 说明与本地校验命令

新增或修改 skill 时，保持当前目录约定：

```text
plugins/<plugin-name>/skills/<skill-name>/SKILL.md
```

Dev-stack 的 `/commit` 由 `plugins/dev-stack/skills/commit/SKILL.md` 定义主流程，并由一层 references 维护变更分析与提交策略；修改 `/commit` 时需保持这些文件同步，且不要把它绑定到 skill-forge 的 agents、scripts 或 review-state helper。

Nuclio 的 Contract Workbench 行为还需要与以下内容保持一致：

- `plugins/nuclio-plugin/skills/{init,work,finish}/SKILL.md`
- `plugins/nuclio-plugin/references/*.md`
- `plugins/nuclio-plugin/agents/*.md`
- `plugins/nuclio-plugin/schemas/*.json`
- `plugins/nuclio-plugin/scripts/*.py`

## 本地校验

当前仓库没有独立的 package/build 工作流，但可以先做基础静态校验：

```bash
python3 -m json.tool .claude-plugin/marketplace.json >/dev/null
python3 -m json.tool plugins/openclaw-plugin/.claude-plugin/plugin.json >/dev/null
python3 -m json.tool plugins/dev-stack/.claude-plugin/plugin.json >/dev/null
python3 -m json.tool plugins/nuclio-plugin/.claude-plugin/plugin.json >/dev/null
```

Dev-stack / Nuclio helper 与插件严格校验：

```bash
python3 -m unittest discover -s plugins/dev-stack/skills/skill-forge/scripts -p 'test_*.py'
claude plugin validate plugins/dev-stack --strict
python3 -m unittest discover -s plugins/nuclio-plugin/scripts -p 'test_*.py'
claude plugin validate plugins/nuclio-plugin --strict
```

如需检查 skill 文件，可重点审阅：

```bash
find plugins -path '*/skills/*/SKILL.md' -type f | sort
```
