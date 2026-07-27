# cc-marketplace

一个用于组织和分发 Claude Code 插件的轻量级 marketplace 仓库。

## Contents

- [仓库结构](#仓库结构)
- [维护方式](#维护方式)
- [本地校验](#本地校验)

当前仓库包含：

- `openclaw-plugin`：提供 `/openclaw-skill-creator` 技能，用于帮助用户起草 OpenClaw skill。
- `dev-stack`：提供 `/skill-forge` 与 `/commit` 技能；`/skill-forge` 用于创建、设计、修改、审查和验证 Claude Code skill，采用 L0-L3 风险自适应路径、deterministic-first 校验、单 Controller 顺序执行、L2/L3 file-backed 状态、conditional review/eval 和 L3 strict 高风险治理；`/commit` 用于自包含分析当前 Git 变更、生成单个 Conventional Commit，并在安全门禁下选择性暂存和提交。`/commit` 不调用 `/verify`、其他 skill、agent、workflow、MCP、网络或外部服务；最终 commit message 的 type、scope、summary 与 body 的唯一语义来源是选择性暂存后重新读取的最终 staged diff。
- `nuclio`：提供 Nuclio v2 4.0.3：`/nuclio:init` 只负责 v2 `.dev-docs` skeleton setup、repair 和整个旧目录移动到 `legacy/v1`；`/nuclio:work` 是日常入口，active change 只有 `change.md`（人类可读 Spec 角色）、`plan.yaml` 批准合同、`state.yaml` 当前恢复状态三层 artifact，结合 file-first approval、单一 PyYAML `change.py` helper、每 Task checkpoint commit、change-level `allowed_paths`、风险驱动委派/review、bounded subagent 不得调用 TaskStop/Stop Task 或停止/接管 Controller/task-tracking 任务且阻塞时只返回 Coordinator、简化的 successor/predecessor fail-closed supersede 收口（successor `change.md` backlink predecessor；active predecessor relation 写入 `state.superseded_by`；predecessor archive `related_changes` 与 State 校验一致；不 pre-link frozen predecessor、不新增 link-related/hash refresh/手改 State）、验证、知识优先 finish，以及只保留精简 `change.md` 的轻量 archive；不声称迁移 petgo 或已有 archive。

## 仓库结构

- `.claude-plugin/marketplace.json`：市场清单，声明当前 marketplace 暴露的插件。
- `plugins/<plugin-name>/.claude-plugin/plugin.json`：插件元数据。
- `plugins/<plugin-name>/skills/<skill-name>/SKILL.md`：技能定义。
- `plugins/<plugin-name>/skills/<skill-name>/references/`：skill 级协议、设计约束或参考资料（如 dev-stack/skill-forge 的 review-state 协议、模板和校验清单；`plugins/dev-stack/skills/commit/references/` 存放 `/commit` 的变更分析和提交策略）。
- `plugins/<plugin-name>/skills/<skill-name>/agents/`：skill 级 agent 定义（如 dev-stack/skill-forge 的 `skill-creator-eval.md`，仅在明确 flag gate 下做 simulation-only eval）。
- `plugins/<plugin-name>/skills/<skill-name>/scripts/`：skill 级确定性辅助脚本与测试（如 dev-stack/skill-forge 的 `review-state-helper.py`、`plan_contract.py`、`plan-task-query.py` 与 unittest；`/commit` 自包含执行，不使用 skill-forge agents、scripts 或 review-state helper，也不新增 runtime hook、daemon、MCP 或本地状态机制）。
- `plugins/<plugin-name>/references/`：插件级共享参考资料。Nuclio v2 的当前运行时权威位于 `plugins/nuclio-plugin/references/`，包括 `workflow.md`、`change-format.md`、`knowledge.md`、`context-hygiene.md` 和 `eval-prompts.md`。
- `plugins/<plugin-name>/scripts/`：插件级确定性辅助脚本与测试。Nuclio v2 只有一个 runtime helper：`plugins/nuclio-plugin/scripts/change.py`；`test_change.py` 和 `test_static_plugin.py` 覆盖三层 artifact、YAML safety、allowed_paths、checkpoint/repair、禁止机制和静态语义。
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

Nuclio v2 的当前运行时只暴露 `/nuclio:init` 与 `/nuclio:work`，并且 4.0.3 起保留 active 三层工作流、知识优先 finish、破坏性的单文件 archive retention、successor 成功归档后对 predecessor 的显式 supersede 收口，以及 bounded subagent 不得停止/接管任务且阻塞时返回 Coordinator 的生命周期边界：

- `/nuclio:init` 只负责创建或修复最小 v2 `.dev-docs` 骨架，并且只能把旧 `.dev-docs` 整体移动到 `.dev-docs/legacy/v1/`；不得创建普通 change、写入 `plan.yaml`、初始化 `state.yaml`、批准 Plan、实施产品、执行 validation/review/repair、complete 或 archive。
- `/nuclio:work` 是日常唯一入口。每个 active change 只使用 `.dev-docs/changes/<change-id>/change.md`、`plan.yaml`、`state.yaml` 三个 runtime artifact：`change.md` 是人类可读 Spec 角色与权威，`plan.yaml` 是用户自然语言批准后的执行合同权威，`state.yaml` 是唯一动态恢复状态权威；Spec 不是单独文件。
- `plugins/nuclio-plugin/scripts/change.py` 是唯一 runtime helper 和唯一 State writer，负责 `create`、`list`、`show`、`validate-plan`、`init-state`、`status`、`next-action`、`start-task`、`record-task`、`record-review`、`start-repair`、`record-repair`、`record-validation`、`complete`、`archive` 和 `legacy-move`。
- Nuclio runtime 明确依赖 PyYAML。`plan.yaml` / `state.yaml` 使用原生 YAML；helper 使用拒绝重复 mapping keys 的受限 `SafeLoader`、安全 dump、输入大小限制、显式 schema/type checks，并在 PyYAML 缺失时返回稳定 dependency error。
- 产品 mutation 前必须 file-first：完整 `change.md` Spec 角色与 `plan.yaml` Plan 写入文件并通过 `validate-plan` 后，终端默认只展示路径、1–3 行摘要、风险/review policy、Task count、`allowed_paths` 摘要和关键 exit code；用户用自然语言批准、拒绝、修订或要求指定片段。
- Plan 使用 change-level `allowed_paths` 作为写入边界；不引入 runtime per-Task files ownership、owner mapping、finding owner routing 或 behavioral eval owner。
- 每个实施 Task 和每个批准的 in-scope repair 恰好一个 selective-stage 本地 checkpoint commit。helper 校验 parent、subject、changed paths、空 index、PASS validation 和 allowed-path 边界；不自动 squash、reset、rebase、stash 或改写历史。
- `state.yaml` 只保存当前恢复状态：phase、当前 Task、review、validation、repair、blocker、`next_action`、checkpoint SHA 和必要 identity。它不保存完整 transition history、完整 diff、transcript、测试日志、agent 消息、文件内容 snapshot 或重复 Git 历史。
- finish 在产品结果与验证证据报告之后始终执行长期知识候选分析；无合格候选记录 `NO_OP`，有候选时只在用户确认后写入知识。`complete` 后将 `change.md` 蒸馏为精简历史记录，再 archive。
- 当范围扩大需要 successor 接管 frozen predecessor 时，successor 创建/修订阶段必须让 successor `change.md.related_changes` 引用 predecessor；不要 pre-link frozen predecessor，不新增 link-related，也不通过 hash refresh/rebaseline 或手改 State 绕过冻结 identity。successor 成功归档后，Coordinator 顺序运行 `supersede`，进入 `SUPERSEDED`/`ARCHIVE_SUPERSEDED` 并由 helper 写入 predecessor `state.superseded_by`，再蒸馏 predecessor 为 `related_changes` 与 State successor 一致的 superseded 历史记录并 archive。不得按 `-v2` 名称、recency、聊天记录或 predecessor 单向关联猜测，不得把旧 acceptance 伪装为成功；失败必须报告残留 active predecessor 路径。
- 新的成功 archive 只在 `.dev-docs/changes/archive/<change-id>/` 保留精简 `change.md`；active `plan.yaml` 与 `state.yaml` 会被 pruning，不进入长期 archive。现有 archives 不迁移，后续追溯依赖精简 Outcome/Validation/Knowledge Updates 与 Git checkpoint history。
- 小型单 Task 可由主 Session 直接实施；跨模块、多 Task、广泛探索、较多读写路径、长验证输出或明显上下文压力时默认使用有界 generic subagent 单元。bounded subagent 不得调用 TaskStop/Stop Task，不得创建、更新、停止或接管 Controller/task-tracking 任务，也不得尝试停止自身、父任务、兄弟任务或后台任务；完成、阻塞、超时或需要决策时只向 Coordinator 返回 compact result。产品写入保持顺序，只有无写入冲突的只读探索或审查可按需并发。
- review/validation 的 in-scope repair 可在原批准范围内形成 repair checkpoint；超出 `allowed_paths`、改变 Spec/Plan 合同、提高风险、引入依赖/API/迁移或不可逆/外向动作时必须提高 revision 并重新 file-first 批准。

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

Nuclio v2 不新增第二 helper、`workflow.py`、runtime hook、daemon、MCP、network service、项目级 `.claude/` 安装、`.nuclio/` state 目录、持久过程 JSON、changes index、archive manifest、隐藏备份、DAG scheduler、并行产品写入引擎、内容 snapshot、完整 State history、自动 fixer、owner routing、owner budget、外部 Superpowers 依赖、v1 compatibility converter 或 v1/v2 双栈。不要恢复 archive 保留 `plan.yaml`/`state.yaml` 的旧 promise，也不要迁移现有 archives。面向用户的 prose 默认使用用户当前主要语言；代码、命令、路径、字段名和原始输出保持原文。

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
python3 -c 'import yaml; print(yaml.__version__)'
python3 plugins/nuclio-plugin/scripts/change.py --help >/dev/null
python3 -m unittest discover -s plugins/nuclio-plugin/scripts -p 'test_*.py'
claude plugin validate plugins/nuclio-plugin --strict
```

如需检查 skill 文件，可重点审阅：

```bash
find plugins -path '*/skills/*/SKILL.md' -type f | sort
```
