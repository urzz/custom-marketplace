# Nuclio v2 Workflow

Nuclio v2 4.2.1 是 file-first、Git-backed 的三层 change 工作流。`change.md` 保存用户意图和完成叙述，`plan.yaml` 保存批准合同与执行策略，`state.yaml` 保存当前恢复 cursor 与紧凑证据。主会话是唯一 Coordinator，`change.py` 是唯一 State writer。

本文件是生命周期、状态迁移、repair、finish、archive 和 supersede 的权威；精确 schema 见 `change-format.md`。

## Lifecycle

```text
locate/create
  -> complete Spec + canonical Plan
  -> validate-plan
  -> natural-language approval
  -> init-state / approval checkpoint
  -> ordered Tasks / checkpoint evidence
  -> required reviews
  -> whole-change validation
  -> knowledge analysis and decision
  -> complete / next_action: ARCHIVE
  -> append completion sections
  -> archive complete directory
```

核心命令顺序：

1. `create`、`list`、`show` 定位或创建 change。
2. `validate-plan --id <id>` 同时验证 Spec、Plan 与 identity。
3. 用户批准后，`init-state --id <id>` 创建 approval checkpoint。
4. 每个 Task 调用 `start-task`，完成 checkpoint 后调用 `record-task`。
5. 按 `next-action` 调用 `record-review`、`record-validation`，失败时执行 repair decision 与 `start-repair`/`record-repair`。
6. 产品结果报告后分析 knowledge，调用带显式 knowledge result 的 `complete`。
7. 补全完成文档并调用 `archive`。

## Locate, Create, Resume

默认只扫描 `.dev-docs/changes/<id>/`，排除 `archive/` 与 `legacy/`。多个 active change 可能匹配时必须让用户选择，不能按新旧、名字或聊天上下文猜测。

`create` 只创建草稿 Spec。Coordinator 必须补全 `Goal`、`Context`、`Constraints`、`Non-goals`、`Acceptance Criteria`，并写入 canonical Plan。`validate-plan --id` 通过以前，不得把草稿视为可批准合同。

恢复先执行：

```bash
python3 plugins/nuclio-plugin/scripts/change.py --project-root <repo> status --id <id>
python3 plugins/nuclio-plugin/scripts/change.py --project-root <repo> next-action --id <id>
```

随后核对 attached branch、HEAD、index、working tree、Plan/Spec identity 和 helper 返回的最小动作。`BRANCH_DRIFT`、`DETACHED_HEAD`、hash/revision drift 或不合法 checkpoint 都必须停止并请求人工判断。

## File-First Gate

产品 mutation 与 `init-state` 前必须把完整 Spec/Plan 写到文件并通过 `validate-plan`。终端默认只展示：

- `change.md`、`plan.yaml` 路径；
- Goal、Constraints、Non-goals、Acceptance 的 1-3 行摘要；
- risk、review policy、`execution.mode`/rationale、Task 数与 `allowed_paths` 摘要；
- 验证命令 exit code 与短结果；
- 成功 archive 会完整保留 `change.md`、`plan.yaml`、`state.yaml`；
- 批准、修订、拒绝或查看指定 section 的自然语言提示。

用户不需要固定 token、hash、JSON 或身份短语。合同字段变化必须提升 revision、重新验证和重新批准；execution 不能在批准后静默改变。

## Approval Checkpoint

`init-state` 在 attached branch 和空 index 上运行。它再次验证 Spec/Plan，写初始 State，selective stage 三件套，并创建：

```text
state(<change-id>): initialize approved change state
```

helper 验证 parent、subject、commit tree 中三件套、Spec/Plan bytes 和空 index。State 区分 approval checkpoint 前的 `initial_head`、批准提交 `approval_checkpoint` 与当前已接受 checkpoint `current_head`。正常 `create` 路径无需用户提前提交 Spec/Plan。

批准 checkpoint 失败不得留下可推进的部分 State，也不得吸收用户无关 staged change。

## Task Execution

产品 Task 默认使用 `execution.mode: delegated`。只有同时满足下列全部条件，Plan 才能使用 `direct`：

- `risk_level: low`、`review_policy: self`、恰好一个 Task；
- `allowed_paths` 最多三个，且全部是精确文件而不是以 `/` 结尾的目录前缀；
- 修改位置在批准前已确定，无需批准后广泛探索；
- 不涉及公共 API、数据模型、dependency、安全、权限、migration、并发、外部副作用或不可逆动作；
- 有明确、定向、可重复的 validation。

helper 机械验证前三项中可结构化的部分；语义边界由 Coordinator 写入 execution rationale，并在 file-first Gate 中交由用户批准。`delegated` 下 subagent 不可用时必须停止并报告，不能回退主会话。改变 execution 必须提升 revision、重新验证和重新批准。

Task 按 Plan 顺序执行：

1. `next-action` 返回 `required_executor`；`start-task --id <id> --task-id <n>` 从批准 Plan 派生同一 executor、冻结 `task_base`，并返回 helper 派生的 `checkpoint_subject`。
2. `delegated` 必须派发 bounded subagent；`direct` 才由主会话实施。两者都只在 change-level `allowed_paths` 内写入并保持 index 可控。
3. 精确执行 Task `validation` 中的全部命令并保存 exit code 与短摘要。
4. selective stage Task 路径并创建恰好一个 checkpoint commit。
5. `record-task` 传入每个 validation command/exit code。helper 验证直接 parent、subject、非空 changed paths、allowed-path 边界、空 index和 branch identity，再自动绑定 checkpoint SHA。

Task validation command 的顺序与内容必须和 Plan 精确一致；PASS 的 exit codes 必须全为 `0`。agent claim、只写“测试通过”或没有 checkpoint 的工作均不能推进 State。

## Review And Validation

review policy 由失败后果、耦合、变更性质和验证强度决定：

- `self`：低风险可由主会话自检，仍必须运行 deterministic validation。
- `final`：所有 Task 后派发 fresh read-only subagent 做 whole-change review；个别 Task 可用 `review: task-and-final` 提前审查。
- `task-and-final`：每个 Task checkpoint 后派发 fresh read-only subagent 审查，所有 Task 后再派发 final reviewer；`high` 风险必须使用此策略。

Task review 的 range 由 helper 固定为 `task_base..task checkpoint`；final review 固定为 `approval_checkpoint..current_head`。`record-review` 记录 PASS/FAIL、summary、evidence，FAIL 还应记录 violated contract 与 paths。调用者不能覆盖 base/head。

`record-validation` 至少包含一个非空 command 及对应 exit code，绑定当前 HEAD。PASS 要求所有 exit code 为 `0`；FAIL 记录失败命令、非零 code、摘要和必要路径/证据。review PASS 不能覆盖 validation FAIL。

## In-Scope Repair

review 或 validation FAIL 后，State 进入 `REQUEST_REPAIR_DECISION`。只有以下条件全部成立，Coordinator 才能建议并在用户同意后直接 repair：

- 修复仍满足批准的 Goal、Constraints、Non-goals 与 Acceptance；
- 所有写路径在 `allowed_paths` 内；
- 不增加 dependency、public API、migration、不可逆或外向动作；
- risk 不上升，Plan 合同无需变化。

获批后调用 `start-repair`；repair 继承批准 Plan 的 execution，helper 返回 `required_executor`。由该 executor 实施并运行 closure validation，创建一个 repair checkpoint，再用命令和 exit code调用 `record-repair`。越界修复必须回到 Plan revision 和 file-first Gate。

repair 改变 HEAD 后，旧 whole-change validation 必定失效。Task review repair 返回该 Task review；final review repair 重新要求 final review 和 validation；validation repair 在需要 final review 时先返回 final review，否则返回 validation。不要复用与新 HEAD 不一致的 final evidence。

## Next Actions

State 对外使用以下主要 action：

```text
DISPATCH_TASK
RUN_TASK_REVIEW
RUN_FINAL_REVIEW
RUN_VALIDATION
REQUEST_REPAIR_DECISION
COMPLETE
ARCHIVE
ARCHIVE_SUPERSEDED
HALT
```

始终按 `next-action` 执行最小一步。不要通过手改 `state.yaml` 跳转 phase。

## Finish And Knowledge

所有 Task、必要 review 和 whole-change validation 通过后，先向用户报告产品结果、changed paths、命令、exit codes 与关键摘要。随后始终执行知识候选五问；具体准入与 freshness 见 `knowledge.md`。

结果映射：

- 无合格候选：`NO_OP`，不增加第二 Gate。
- 用户接受并全部写入：`APPLIED`。
- 仅部分写入或按用户修改写入：`PARTIAL`。
- 候选存在但用户拒绝：`REJECTED`。

有候选时只发起一次结果导向的收尾决策：优先通过 `AskUserQuestion` 提供“写入并归档（推荐）”与“跳过并归档”；工具不可用时给出等价自然语言选项，并允许用户直接说明修改意见。不得要求固定口令。用户选择写入或跳过后，连续执行对应知识处理、`complete`、完成文档更新与 `archive`，不得另行请求归档确认。无候选时直接以 `NO_OP` 连续完成并归档。

调用：

```bash
python3 plugins/nuclio-plugin/scripts/change.py --project-root <repo> complete \
  --id <id> \
  --knowledge-result <NO_OP|APPLIED|PARTIAL|REJECTED> \
  [--knowledge-path <repo-relative-path> ...]
```

helper 检查 Task/review/validation evidence freshness、HEAD 和 knowledge paths 后写入 `knowledge.result`，并设置 `status: COMPLETED`、`phase: COMPLETED`、`next_action: ARCHIVE`。

## Completion Document

`complete` 后允许修改 `change.md` 的终态窗口不是自由重写。Coordinator 必须保留批准 checkpoint 中的 Spec sections，只允许更新完成 frontmatter，并追加或更新非空：

- `Outcome`
- `Validation`
- `Knowledge Updates`
- `Residual Risks`

无残余风险也必须明确说明。archive 从 approval checkpoint 读取已批准 Spec 并结构化比较；不把 Spec snapshot 复制进 State。

## Complete Archive

`archive` 的 normal 前置状态是 `COMPLETED/COMPLETED/ARCHIVE`；superseded 前置状态是 `SUPERSEDED/SUPERSEDED/ARCHIVE_SUPERSEDED`。helper 在 move 前校验 frozen branch、Plan/State identity、HEAD/evidence freshness、完整 completion sections、Spec 历史、knowledge paths 和 active exact artifact set。

成功操作：

1. 将 active `<id>/` 完整移动到 `changes/archive/<id>/`。
2. selective stage 三个 active 路径的删除、三个 archive 路径的新增，以及 State 声明的 knowledge paths。
3. 创建 `archive(<id>): retain complete change record`。
4. 验证 parent、subject、六个 artifact paths、允许的 knowledge paths、HEAD 与空 index。
5. 返回 archive path、commit SHA 和 retained artifacts。

归档目录完整保留：

```text
.dev-docs/changes/archive/<id>/
├── change.md
├── plan.yaml
└── state.yaml
```

move 后、commit 前中断时，同一命令可以根据 archived State 恢复。commit 已成功但调用方未收到结果时，重跑会验证现有 commit 并幂等返回。source/target 冲突、artifact 不完整、无关 staged path、wrong branch 或验证失败都 fail closed；不得自动 reset、stash、清理无关 dirty 文件或制造第二份 backup/manifest。

## Successor Closure

当 scope expansion 无法在 frozen predecessor 合同内安全继续时，创建 successor，并让 successor `change.md.related_changes` backlink predecessor。不要预改 frozen predecessor，也不要手动 refresh hash/State。

`supersede` 只接受已成功归档、Git tracked/clean、completed 且 backlink 有效的 successor。4.1.0+ 完整三件套 archive 会额外验证 Plan/State identity、terminal status 与 archive commit；旧 4.0.x 单文件 archive 只按兼容规则验证完成记录。active 或半归档 successor 均被拒绝。

成功后 predecessor 进入 `SUPERSEDED/ARCHIVE_SUPERSEDED`，`state.superseded_by` 记录 successor id、archive location/path 和 decision。完成文档必须保留旧 Spec，明确 takeover、真实 checkpoints、未完成范围、旧 acceptance 未完全 PASS 和 residual risks，再调用 `archive`。任一步失败都报告残留 active predecessor 路径，不能宣称完全收口。

## Recovery And Prohibitions

Git commits、working tree、代码、配置、测试和 CI 是产品事实；State 只保存当前恢复事实。恢复不得依赖 transcript 或 agent 信心。

Nuclio 不引入第二 helper、`workflow.py`、DAG scheduler、parallel product write、owner routing、automatic fixer、archive manifest、hidden archive backup、runtime hook、daemon、MCP、network service、项目级 `.claude/`、`.nuclio/` 状态或 v1/v2 双栈。产品写入顺序执行，只允许无写冲突的只读探索或审查并发。
