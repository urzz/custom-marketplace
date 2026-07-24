# Nuclio v2 Workflow

Nuclio v2 是轻量三层 docs-as-code 工作流。每个 active change 使用 `change.md` 作为人类可读 Spec、`plan.yaml` 作为用户批准的执行合同、`state.yaml` 作为当前恢复状态；唯一 runtime helper 是 `plugins/nuclio-plugin/scripts/change.py`。主会话仍是唯一 Coordinator，用户自然语言批准仍是产品 mutation 前的强制 Gate。

## Contents

- [角色模型](#角色模型)
- [三层 authority](#三层-authority)
- [生命周期总览](#生命周期总览)
- [Locate/Create/Resume](#locatecreateresume)
- [澄清方式](#澄清方式)
- [file-first 计划批准](#file-first-计划批准)
- [State 初始化与恢复](#state-初始化与恢复)
- [实施、checkpoint 与顺序写入](#实施checkpoint-与顺序写入)
- [有界委派](#有界委派)
- [Bug、repair 与新 change 边界](#bugrepair-与新-change-边界)
- [风险驱动验证与审查](#风险驱动验证与审查)
- [知识候选](#知识候选)
- [完成与 archive](#完成与-archive)
- [禁止恢复的 v1 与重型模式](#禁止恢复的-v1-与重型模式)

## 角色模型

主会话是 Coordinator/Controller：它维护用户目标、文件化 Spec/Plan、上下文预算、Git checkpoint、验证证据、review/repair 决策和最终汇报。主会话不是细粒度持久状态机，也不把 agent claim 当作完成事实。

`change.py` 是唯一 runtime helper。它创建 change、校验 Plan、初始化和推进 `state.yaml`、返回 `status`/`next-action`、记录 Task/checkpoint/review/repair/validation、完成和归档。它不调用模型、不修改产品文件、不替用户批准。

通用 subagent 只能作为有界执行或只读探索/审查单元。Nuclio 不新增专用 agent 流水线、自动 fixer、owner routing 或递归委派机制。

## 三层 authority

每个 active change 位于：

```text
.dev-docs/changes/<change-id>/
├── change.md
├── plan.yaml
└── state.yaml
```

职责固定：

- `change.md`：Spec 权威，表达 Goal、Context、Constraints、Non-goals、Acceptance Criteria、重要 Decisions 和最终 Outcome；不保存动态 Task checklist、完整 transcript、完整 diff、长测试日志或 agent 消息。
- `plan.yaml`：批准合同权威，表达 revision、`risk_level`、`review_policy`、`repair_policy`、change-level `allowed_paths`、有序 Tasks、validation、delegate 意图和 `checkpoint_subject`。
- `state.yaml`：唯一动态恢复状态权威，只由 `change.py` 原子写入，保存当前 phase、Task、review、validation、repair、blocker 和 `next_action`。
- Git commits、working tree、代码、配置、测试和 CI：产品执行事实；每个 Task/repair checkpoint commit 保存实际增量历史。

冲突处理 fail closed。Spec hash、Plan hash、revision、HEAD、checkpoint parent、checkpoint subject、commit range 或 allowed-path 边界不匹配时，不自动猜测、同步或继续推进。

## 生命周期总览

Nuclio v2 的日常入口是 `work`。标准顺序如下：

1. 定位项目根与 `.dev-docs`。
2. 确保 v2 skeleton 存在；必要时用 `change.py legacy-move` 整体移动清晰 legacy 树。
3. 定位、恢复或创建一个 active change。
4. 按需读取知识、源码、配置、测试、`change.md`、`plan.yaml` 和 `state.yaml` 摘要。
5. 澄清 Goal、Constraints、Non-goals、Acceptance、`allowed_paths`、validation、risk 和 review policy。
6. 写入或更新完整 `change.md` Spec 与 `plan.yaml` Plan。
7. 运行 `change.py validate-plan`，修复合同问题直到通过。
8. file-first 展示路径、短摘要、风险/review policy、关键 exit code、archive retention disclosure 和批准提示；等待用户自然语言批准。
9. 批准后才运行 `change.py init-state`。
10. 通过 `change.py status` 与 `change.py next-action` 顺序执行 Task、checkpoint、task review、final review、validation、repair decision、complete。
11. 先报告产品结果与证据。
12. 始终分析长期知识候选；无合格候选时记录 `NO_OP` 且不显示第二 Gate。
13. 有合格候选时展示唯一目标与证据，等待自然语言确认，并记录实际写入、部分接受、修改或拒绝结果。
14. 调用 `complete`，将 `change.md` 蒸馏为精简历史记录，再调用 `archive`；成功 archive 只保留该精简 `change.md`。

该顺序既是用户体验流程，也是恢复语义：动态推进以 helper 的当前 `next_action`、Git 和确定性证据为准，不依赖聊天 transcript。

## Locate/Create/Resume

先确认项目根。若 `.dev-docs` 不存在，可创建最小 v2 skeleton；若清晰 legacy 树存在，使用 `change.py legacy-move` 整体移动；若分类不确定，停止并报告冲突路径。

扫描 active change 时，只看 `.dev-docs/changes/*/change.md` 及同目录 `plan.yaml`/`state.yaml` 是否存在，默认排除 `.dev-docs/changes/archive/**` 和 `.dev-docs/legacy/**`。若用户请求与唯一 active change 明确匹配，则恢复该 change。若多个候选可能匹配，必须让用户选择。若没有匹配项，则用 `change.py create` 创建新的 change。

创建新 change 时给出人类可读 title 和 goal。归档后出现相关回归或后续扩展时创建新 change，并在 `related_changes` 中引用已归档 change。

## 澄清方式

澄清采用 recommendation-first：先给出当前建议，再问一个会改变合同的问题。不要把用户拖入问卷。简单安全任务可零问。

每次只问一个问题。问题必须影响 Goal、Constraints、Non-goals、Acceptance、`allowed_paths`、Task 拆分、验证方法、风险判断、review policy 或 repair 判断。若问题不改变执行合同，直接继续。

## file-first 计划批准

产品 mutation 前必须把完整 Spec 和完整 Plan 写入文件，并运行：

```bash
python3 plugins/nuclio-plugin/scripts/change.py --project-root <repo> validate-plan --id <change-id>
```

终端默认只展示：

- `change.md` 与 `plan.yaml` 路径；
- 1–3 行 Goal/Constraints/Non-goals/Acceptance 摘要；
- `risk_level`、`review_policy`、`repair_policy`、Task count 和 `allowed_paths` 摘要；
- `validate-plan` exit code 与短结果；
- retention disclosure：成功 archive 只保留精简 `change.md`，active `plan.yaml`/`state.yaml` 不进入长期 archive；
- 请求用户批准、修订、拒绝或指定查看某 section 的提示。

默认不回显完整 `change.md`、完整 `plan.yaml`、完整 `state.yaml`、完整 diff、transcript 或长日志。用户明确要求时，只显示指定 artifact 或 heading/section。

用户可以用自然语言批准、拒绝或修正。禁止要求 fixed token、哈希、approval JSON、身份短语或精确别名。批准只授权该 revision 的 Spec/Plan 合同。Goal、Constraints、Non-goals、Acceptance、`allowed_paths`、Task 合同、validation、risk、review policy 或 repair policy 变化时，必须提高 `revision`、重新 `validate-plan` 并重新获得批准。

候选 Spec/Plan 写入属于准备阶段；`init-state` 和产品 mutation 必须等用户批准后发生。

## State 初始化与恢复

批准后运行：

```bash
python3 plugins/nuclio-plugin/scripts/change.py --project-root <repo> init-state --id <change-id>
```

`init-state` 冻结 Spec hash、Plan hash、revision 和 HEAD，并创建 `state.yaml`。已有 State 不被覆盖。

恢复或继续工作时先运行：

```bash
python3 plugins/nuclio-plugin/scripts/change.py --project-root <repo> status --id <change-id>
python3 plugins/nuclio-plugin/scripts/change.py --project-root <repo> next-action --id <change-id>
```

核心 `next_action`：

```text
DISPATCH_TASK
RUN_TASK_REVIEW
RUN_FINAL_REVIEW
RUN_VALIDATION
REQUEST_REPAIR_DECISION
COMPLETE
HALT
```

恢复判断还必须结合 Git HEAD、`git status`/diff、checkpoint commits 和验证证据。不要重放 transcript，不以 agent claim 推进，也不要把 `change.md` frontmatter `status` 当动态执行状态。

State 只保存当前恢复状态。它不保存完整 transition history、完整 diff、完整日志、agent 消息、文件内容 snapshot 或重复 Git 历史。

## 实施、checkpoint 与顺序写入

实施 Task 的标准顺序：

1. 在 `next_action=DISPATCH_TASK` 时运行 `start-task`，冻结 `task_base`、executor 和 Plan 中的 `checkpoint_subject`。
2. 实施者只修改 change-level `allowed_paths` 内与当前 Task 有关的产品文件。
3. 运行该 Task 的 validation 命令。
4. selective stage 本 Task changed paths。
5. 创建恰好一个本地 checkpoint commit，subject 精确等于批准的 `checkpoint_subject`。
6. 运行 `record-task`，让 helper 校验 parent、subject、changed paths、空 index 和 PASS validation。

每个实施 Task 和每个 repair 单元恰好一个 checkpoint commit。Helper 不自动 reset、rebase、squash、stash 或改写历史；完成后保留 checkpoint commits 作为普通 Git 历史。

产品写入按 Task/repair 顺序执行。不得新增 DAG scheduler 或并行产品写入引擎。只有无写入冲突的只读探索或审查可按需并发。

## 有界委派

小型、边界明确、单 Task 的低风险 change 可由主会话直接实施和自检。以下情况默认委派至少一个 bounded generic subagent 单元，除非委派不可用或降低安全性：跨模块或多子系统、多个有独立验收的 Tasks、广泛探索、较多读写路径、长验证输出、明显上下文压力、或 review policy 要求独立关注。

每个 subagent dispatch 仅包含：

- 当前 Task 的 Goal 与 non-goals；
- change-level `allowed_paths` 与本 Task 实施意图；
- 必要 read paths 或 headings；
- acceptance 与 validation commands；
- `task_base` 与 expected `checkpoint_subject`；
- selective staging/commit 合同；
- 禁止编辑 `change.md`、`plan.yaml`、`state.yaml`，禁止递归委派、扩范围、reset/rebase/squash/stash/history rewrite；
- compact return：checkpoint SHA、changed paths、commands/exit codes、风险和 blocker。

主会话以实际 commit range、Git diff/status、validation、review findings 和 helper State 为准，不以 subagent claim 推进。

## Bug、repair 与新 change 边界

继续当前 change 的条件：

- 原 Goal 尚未达成。
- 当前实现引入缺陷或回归。
- 当前交互验收失败且仍在批准范围内。
- 审查或 validation 发现同范围问题。

`repair_policy: in-scope` 的 repair 可继续当前批准，只在人工判断同时满足以下条件时执行：修复仍满足原 Goal、Constraints、Non-goals 和 Acceptance；所有 repair paths 在 `allowed_paths` 内；不新增依赖、API、迁移、不可逆或外向动作；不提高风险；不改变 Plan 合同。每次 repair 前 `next_action` 必须是 `REQUEST_REPAIR_DECISION`，不得自动循环。

Review/validation FAIL 只记录违反合同、具体路径、证据和 decision，不做 owner mapping、owner budget、自动 fixer 或 finding owner routing。

创建新 change 或返回 Plan revision 的条件：原 change 已归档、请求与原 Goal 无关、明显扩展范围、改变 public API/架构/依赖/迁移/数据模型/产品语义、提高风险、超出 `allowed_paths`、或形成独立可交付内容。

## 风险驱动验证与审查

Risk guidance: `plan.yaml` 使用 `risk_level` 与 `review_policy` 组合控制审查：

- `self`：低风险文档、简单配置、明确一文件修复可由主会话自检；仍必须运行适用 deterministic validation。
- `final`：普通多文件功能可先完成所有 Tasks，再运行 whole-change review 与验证。
- `task-and-final`：高风险、跨模块、public API、数据模型、安全、迁移、破坏性或用户要求的工作，每个 Task 独立 review，全部 Tasks 后再 final review。

`high` 风险必须使用 `task-and-final`。deterministic validation FAIL、identity drift、checkpoint mismatch、allowed-path violation 或 unresolved blocker 都不能完成。

Review 不能替代失败的确定性校验。Validation 和 review 结果应以命令、exit code、关键输出、路径和具体合同为证据，终端只展示短摘要，长日志按用户要求显示。

## 知识候选

产品验证通过并报告产品结果后，必须始终分析长期知识候选。知识候选必须同时稳定、可复用、非显然、已验证、可归属；不能因为“暂时没想到”而跳过分析。

无合格候选时记录 `NO_OP`，不显示第二个 Gate，直接继续 `complete` 与 `archive`。`NO_OP` 表示没有可长期化的新事实，不能伪造知识条目，也不能制造额外批准要求。

有合格候选时只展示语义结论、唯一目标文件/heading、操作类型、冲突与影响，以及支持证据摘要。用户可自然语言接受全部、部分、修改或拒绝。拒绝知识写入不影响已经验证的产品结果、`complete` 或 `archive`，但精简历史 `change.md` 必须记录候选被拒绝。

知识是 finish 的主要长期价值：只有经确认且可复用的事实进入 `.dev-docs/knowledge/**`。Archive 只是轻量追溯记录，不替代长期知识。知识文件不是动态状态权威；知识写入不创建第四 artifact，不替代 `state.yaml`、Git、代码或测试事实。

## 完成与 archive

完成前先报告产品结果、变更路径、验证命令、退出码和关键输出摘要；随后完成 mandatory knowledge-candidate analysis，并在 `change.md` 中记录实际知识结果：写入、部分写入、修改、拒绝或 `NO_OP`。不要复制完整日志。

当所有 Tasks、必要 task/final review、whole-change validation、HEAD/State/Spec/Plan identity 和 blocker 条件都满足时运行：

```bash
python3 plugins/nuclio-plugin/scripts/change.py --project-root <repo> complete --id <change-id>
```

`complete` 后、`archive` 前，Coordinator 将 `change.md` 蒸馏为精简完成记录。必备形态为 completed frontmatter 加以下非空 headings：

```markdown
## Goal
## Outcome
## Validation
## Knowledge Updates
```

精简历史记录只保留可追溯结论：目标、产品结果、关键 changed paths、验证命令/exit code 摘要、剩余风险、知识写入或 `NO_OP`/拒绝结果，以及必要 Git checkpoint SHA。不得复制 Plan、State、完整 diff、transcript、agent 消息或长日志。

再运行：

```bash
python3 plugins/nuclio-plugin/scripts/change.py --project-root <repo> archive --id <change-id>
```

Archive 成功后 `.dev-docs/changes/archive/<change-id>/` 只保留精简 `change.md`；active `plan.yaml` 和 `state.yaml` 会被 pruning，不进入长期 archive。Git checkpoint commits 保留实际实施历史，后续相关问题创建带关联的新 active change，并通过 archive 的 Outcome/Validation/Knowledge Updates 与 Git history 追溯。

Archive 是 fail-closed 的不可逆 retention 操作：执行前必须验证 completed State、Plan/Spec/HEAD identity、精简历史记录形态和 exact artifact set（active 目录只能含 `change.md`、`plan.yaml`、`state.yaml`）。undistilled record、unexpected artifact 或 identity drift 必须在移动/pruning 前失败且保持 active 目录不变；若移动后 pruning 失败，必须报告 archive path 与 remaining artifacts，不得报告成功。现有 archive 不迁移；新 retention policy 只适用于未来成功的 archive 调用。

## 禁止恢复的 v1 与重型模式

Nuclio v2 禁止恢复旧的完成交接、包绑定、证据身份、固定 Nuclio 专用 agent 流水线、持久过程 JSON、旧式状态路由、内容 snapshot、append-only State history、自动 fixer、owner routing、owner budget、第二 helper、`workflow.py`、DAG scheduler 或并行产品写入引擎。

也禁止新增 MCP、network service、daemon、runtime hook、项目级 `.claude/`、`.nuclio/`、`.dev-docs/changes/index.md`、v1 compatibility converter、v1/v2 双栈、自动 squash/reset/rebase/stash/history rewrite，或要求 exact token、哈希、approval JSON 作为日常实施批准。

历史 v1 资料只能在明确 legacy 语境中整体移动或按用户要求只读查看；不得解析、转换或恢复为当前运行时权威。
