# cc-marketplace

一个用于组织和分发 Claude Code 插件的轻量级 marketplace 仓库。

## Contents

- [仓库结构](#仓库结构)
- [维护方式](#维护方式)
- [本地校验](#本地校验)

当前仓库包含：

- `openclaw-plugin`：提供 `/openclaw-skill-creator` 技能，用于帮助用户起草 OpenClaw skill。
- `dev-stack`：提供 `/skill-forge` 与 `/commit` 技能；`/skill-forge` 用于创建、设计、修改、审查和验证 Claude Code skill，采用 L0-L3 风险自适应路径、deterministic-first 校验、单 Controller 顺序执行、L2/L3 file-backed 状态、conditional review/eval 和 L3 strict 高风险治理；`/commit` 用于自包含分析当前 Git 变更、生成单个 Conventional Commit，并在安全门禁下选择性暂存和提交。`/commit` 不调用 `/verify`、其他 skill、agent、workflow、MCP、网络或外部服务；最终 commit message 的 type、scope、summary 与 body 的唯一语义来源是选择性暂存后重新读取的最终 staged diff。
- `nuclio`：提供 Nuclio v2：`/nuclio:init` 负责 v2 `.dev-docs` setup、repair 和整个旧目录移动到 `legacy/v1`，`/nuclio:work` 是日常入口，围绕单一 `change.md` 执行可恢复的人类可读 change 工作流。

## 仓库结构

- `.claude-plugin/marketplace.json`：市场清单，声明当前 marketplace 暴露的插件。
- `plugins/<plugin-name>/.claude-plugin/plugin.json`：插件元数据。
- `plugins/<plugin-name>/skills/<skill-name>/SKILL.md`：技能定义。
- `plugins/<plugin-name>/skills/<skill-name>/references/`：skill 级协议、设计约束或参考资料（如 dev-stack/skill-forge 的 review-state 协议、模板和校验清单；`plugins/dev-stack/skills/commit/references/` 存放 `/commit` 的变更分析和提交策略）。
- `plugins/<plugin-name>/skills/<skill-name>/agents/`：skill 级 agent 定义（如 dev-stack/skill-forge 的 `skill-creator-eval.md`，仅在明确 flag gate 下做 simulation-only eval）。
- `plugins/<plugin-name>/skills/<skill-name>/scripts/`：skill 级确定性辅助脚本与测试（如 dev-stack/skill-forge 的 `review-state-helper.py`、`plan_contract.py`、`plan-task-query.py` 与 unittest；`/commit` 自包含执行，不使用 skill-forge agents、scripts 或 review-state helper，也不新增 runtime hook、daemon、MCP 或本地状态机制）。
- `plugins/<plugin-name>/references/`：插件级共享参考资料。Nuclio v2 的当前运行时权威位于 `plugins/nuclio-plugin/references/`，包括 `workflow.md`、`change-format.md`、`knowledge.md`、`context-hygiene.md` 和 `eval-prompts.md`。
- `plugins/<plugin-name>/scripts/`：插件级确定性辅助脚本与测试。Nuclio v2 使用 `plugins/nuclio-plugin/scripts/change.py`，并由 `test_change.py` 与 `test_static_plugin.py` 覆盖。
- `plugins/nuclio-plugin/docs/research/contract-workbench-redesign/`：Nuclio 早期重构的历史研究与设计材料；用于追溯设计依据，不是 runtime authority。
- `plugins/nuclio-plugin/docs/research/human-centered-workflow-redesign/`：Nuclio v2 人本工作流的历史研究与设计输入；其中 proposal 保留原始设计语境，不是 runtime authority，最终行为以 skills、references 和 scripts 为准。

## 维护方式

新增或修改插件时，通常需要同时更新：

1. `plugins/` 下对应插件目录
2. 根目录 `.claude-plugin/marketplace.json`
3. 相关 README / CLAUDE 说明与本地校验命令

新增或修改 skill 时，保持当前目录约定：

```text
plugins/<plugin-name>/skills/<skill-name>/SKILL.md
```

Dev-stack 的 `/skill-forge` 是风险自适应 skill 创建与维护入口：

- L0 Mechanical：主 Session 直接做可逆、局部、机械变更，运行目标确定性检查，不派发 agent。
- L1 Routine：默认主 Session 实施；需要时最多使用一个有界 implementation unit，并做相关确定性检查和一次 whole-diff review。
- L2 Structural：使用 file-backed helper flow；Plan 中的 `risk_level` / `review_policy` 由 `plan_contract.py` 校验，可采用 `final-only` 或 `task-and-final`，只对风险任务进行 task review，并保留 mandatory final review 与至多一次行为 eval。
- L3 High Risk：使用 strict file-backed path；所有 Task 都必须 `task-and-final`，保留 per-task review、mandatory final review、structural validation 和适用的 behavioral validation。
- 所有级别都遵循 deterministic-first：能本地运行的 JSON/schema/static/test 检查必须先于 LLM review；失败时先修复或按协议报告，而不是用 reviewer 代替确定性校验。
- 主 Session 是唯一 Controller，产品写入在第一版仍顺序执行；L2/L3 中 `review-state-helper.py` 是 `review-state.json` 唯一写入者，`next-action` 是状态跳转唯一权威。
- Review/eval 是 conditional review/eval：L0 不派发，L1 只做 whole-diff review，L2 按 `review_policy` 和风险选择 task review/final review/eval，L3 走严格 task-and-final；行为 eval 只在用户行为、Routing、Gate、Pattern 或 Architecture 改动时运行。
- 用户会在实施前遇到确认：L2/L3 对正式 Spec 与 YAML Plan 做一次联合批准；L0/L1 若用户已明确授权可逆有界变更且没有待选项，不重复确认，但不可逆、外向、扩范围或需用户选择的动作必须先确认。
- 第一版不实现并行产品写入、DAG scheduler、外部 orchestration、MCP、daemon、runtime hook 或新的项目外状态体系。

修改 `/skill-forge` 时需要保持以下内容同步：

- `plugins/dev-stack/skills/skill-forge/SKILL.md`
- `plugins/dev-stack/skills/skill-forge/references/*.md`
- `plugins/dev-stack/agents/*.md`
- `plugins/dev-stack/skills/skill-forge/agents/skill-creator-eval.md`
- `plugins/dev-stack/skills/skill-forge/scripts/*.py`
- `plugins/dev-stack/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `README.md` 与 `CLAUDE.md`

Dev-stack 的 `/commit` 由 `plugins/dev-stack/skills/commit/SKILL.md` 定义主流程，并由 `plugins/dev-stack/skills/commit/references/change-analysis.md` 与 `plugins/dev-stack/skills/commit/references/commit-policy.md` 维护变更分析和提交策略；修改 `/commit` 时需同步这些文件、`plugins/dev-stack/.claude-plugin/plugin.json` 的版本、README / CLAUDE 说明与本地校验命令。`/commit` 必须维持自包含执行边界：不调用 `/verify`、其他 skill、agent、workflow、MCP、网络或外部服务，不绑定 skill-forge 的 agents、scripts 或 review-state helper，也不新增 runtime hook、daemon 或本地状态机制。最终 commit message 的 type、scope、summary 与 body 的唯一语义来源是选择性暂存后重新读取的最终 staged diff；未进入最终 staged diff 的内容不得影响最终消息。内部协议更新不应误写成 marketplace source、plugin name 或外部依赖变化。

Nuclio v2 的当前运行时只暴露 `/nuclio:init` 与 `/nuclio:work`：

- `/nuclio:init` 负责创建或修复最小 v2 `.dev-docs` 骨架，并且只能把旧 `.dev-docs` 整体移动到 `.dev-docs/legacy/v1/`；不得解析、转换或恢复旧状态。
- `/nuclio:work` 是日常唯一入口，按顺序定位或创建 change、澄清目标、形成用户可理解计划、获得用户批准、实现、验证、按风险审查、处理可选长期知识候选并归档。
- 普通 change 默认只有 `.dev-docs/changes/<change-id>/change.md` 一个持久过程文件；`change.md` 只保存恢复所需的压缩状态，Git working tree、代码、配置、测试和 CI 才是执行事实。
- 计划 Human-in-the-Loop 是实施前固定保护；长期知识写入只在存在合格候选并经用户确认后执行，用户拒绝知识写入不影响已验证产品结果或归档。
- 主会话按复杂度与风险协调执行路径，可直接处理或委派通用 subagent；只有风险矩阵或用户要求触发时才做额外 critic/review，不描述固定流水线。

维护 Nuclio v2 时需要保持以下内容同步：

- `plugins/nuclio-plugin/skills/init/SKILL.md`
- `plugins/nuclio-plugin/skills/work/SKILL.md`
- `plugins/nuclio-plugin/references/workflow.md`
- `plugins/nuclio-plugin/references/change-format.md`
- `plugins/nuclio-plugin/references/knowledge.md`
- `plugins/nuclio-plugin/references/context-hygiene.md`
- `plugins/nuclio-plugin/references/eval-prompts.md`
- `plugins/nuclio-plugin/scripts/change.py`
- `plugins/nuclio-plugin/scripts/test_change.py`
- `plugins/nuclio-plugin/scripts/test_static_plugin.py`
- `plugins/nuclio-plugin/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `README.md` 与 `CLAUDE.md`

Nuclio v2 不新增 runtime hook、daemon、MCP、外部依赖、项目级 `.claude/` 安装或 `.nuclio/` state 目录；不声明外部 Superpowers 依赖；不提供 v1 compatibility converter；不保留 v1/v2 双栈；不创建 `changes/index.md`。面向用户的 prose 默认使用用户当前主要语言；代码、命令、路径、字段名和原始输出保持原文。

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
python3 plugins/dev-stack/skills/skill-forge/scripts/plan_contract.py --help >/dev/null
claude plugin validate plugins/dev-stack --strict
python3 -m unittest discover -s plugins/nuclio-plugin/scripts -p 'test_*.py'
claude plugin validate plugins/nuclio-plugin --strict
```

如需检查 skill 文件，可重点审阅：

```bash
find plugins -path '*/skills/*/SKILL.md' -type f | sort
```
