# Lifecycle

本 lifecycle 使用 `authority.md` 中的 authority 术语：`.dev-docs/` 是事实源，active change authority 位于 `CHANGE_ROOT=.dev-docs/changes/<change-id>`，artifact existence 不是 approval，Contract/Finish approval 必须 fresh，`mutation_targets` 是唯一写授权。

## 日常 Gate

- Contract Gate：用户批准当前 `CHANGE_ROOT/contract.yaml`、`CHANGE_ROOT/context.jsonl` fingerprint、`CHANGE_ROOT/state.json` version、mutation_targets 和 Contract-bound `output_language` 后，才允许产品 mutation。helper trim-only exact aliases 为 `approve`、`批准`、`同意`、`继续`，存储 canonical `approve`。
- Finish Gate：helper 校验并展示 `CHANGE_ROOT/completion.md` 与 `CHANGE_ROOT/decision.md` maintainer prose，同时用户只批准 `CHANGE_ROOT/completion.json`、`CHANGE_ROOT/decision.json`、`CHANGE_ROOT/finish-plan.json` 的 machine identity 与 `CHANGE_ROOT/state.json` version 后，才允许长期知识写入、归档或 finish apply。helper trim-only exact aliases 为 `accept`/`同意`、`request_changes`/`要求修改`、`defer`/`暂缓`、`reject`/`拒绝`，存储 canonical English decision；`继续` 不是 Finish accept。

除这两个日常 Gate 外，Controller 可以要求澄清或修复，但不能把对话同意、agent claim 或 artifact 存在解释为 Gate approval。

## 状态与 next action

| status | 含义 | 允许的 next action |
| --- | --- | --- |
| `idle` | 没有 active change，或上一个 change 已归档。 | 启动 init；选择或创建 change-local `CHANGE_ROOT=.dev-docs/changes/<change-id>`；读取 project context。 |
| `drafting_contract` | 正在形成或修订 `CHANGE_ROOT/contract.yaml` 与 `CHANGE_ROOT/context.jsonl`。 | 询问澄清；生成/更新 contract draft，包括 `output_language`；运行 schema 与 context 检查；转入 `contract_pending`。 |
| `contract_pending` | Contract draft 已可展示，等待用户 Contract Gate decision。 | 展示摘要、风险、mutation_targets、validation；等待 explicit approve/defer/reject；不得执行 mutation。 |
| `ready_to_execute` | 存在 fresh Contract approval，且 state/context/contract identity 未变。pending/ready tasks may be legally unbound；合法未绑定并不等于可派发。 | 先 packet-helper derive/write worker artifact，再由 state-helper 用 canonical packet schema 和 state identity 绑定并 start；重新校验 dirty/fingerprint；成功后才转入 `executing` 并派发 fresh implementer。 |
| `executing` | 一个或多个 Task 正在实现、review 或修复。 | 按 bound packet 派发 fresh implementer/reviewer/fixer；记录 `CHANGE_ROOT/evidence/tasks/<task-id>/...`；更新 Task 状态；完成后转入 `completing`。 |
| `completing` | 所有 Task 候选实现完成，正在做 change-wide completion。 | 汇总 mutation map、checks、review evidence、risk；用 packet-bound `output_language` 写五文件 canonical handoff：`CHANGE_ROOT/completion.md`、`CHANGE_ROOT/completion.json`、`CHANGE_ROOT/decision.md`、`CHANGE_ROOT/decision.json`、`CHANGE_ROOT/finish-plan.json`；helper 验证 projected identity 后才转入 `decision_pending`。 |
| `decision_pending` | Completion proposal 已可展示，等待 Finish Gate decision。 | 展示 before/after、residual risk、finish apply plan；等待 exact `accept`/`request_changes`/`defer`/`reject`；不得写长期知识或归档。 |
| `folding` | 存在 fresh Finish approval，正在执行长期知识写入或归档。 | 应用 approved finish plan；按 finish target language metadata 处理 existing/new targets，unknown 时 STOP；记录 `CHANGE_ROOT/evidence/finish-apply.json` machine before/after evidence；helper 验证 JSON identity 后才可渲染可选 `CHANGE_ROOT/evidence/finish-apply.md` prose；归档 state；转入 `archived`。 |
| `archived` | Change 已结束且历史可追溯。 | 回到 `idle`；只允许只读审计或显式新 change。 |
| `repair_required` | helper 发现 state、hash、ownership、dirty、schema 或 evidence 不一致。 | 停止自动推进；展示原因；执行授权 repair；必要时重新请求 Gate。 |
| `context_stale` | context fingerprint 或 required source identity 与 approval/packet 不匹配。 | 停止执行；刷新 context；重新生成 packet 或回到 Contract Gate。 |
| `deferred` | 用户选择暂缓 Contract 或 Finish decision。 | 保留 state；允许 resume 前重新校验 freshness；不得假设继续批准。 |
| `rejected` | 用户拒绝 Contract 或 Finish decision。 | 停止当前路径；允许重开 drafting 或归档为 rejected；不得执行被拒绝 mutation。 |

## Change-local artifact map

- Project-level `.dev-docs/` 只保留 index、knowledge、archive 和 changes/index：`.dev-docs/archive/**` 是 project-level archive authority，`.dev-docs/changes/index.md` 是受控 `index_targets`。
- Active change contract、context、state、research 与 evidence 必须位于 `CHANGE_ROOT=.dev-docs/changes/<change-id>`。
- Exact active paths are `CHANGE_ROOT/contract.yaml`, `CHANGE_ROOT/context.jsonl`, `CHANGE_ROOT/state.json`, `CHANGE_ROOT/research/`, `CHANGE_ROOT/evidence/tasks/<task-id>/...`, canonical Finish handoff `CHANGE_ROOT/completion.md`, `CHANGE_ROOT/completion.json`, `CHANGE_ROOT/decision.md`, `CHANGE_ROOT/decision.json`, `CHANGE_ROOT/finish-plan.json`, and finish apply evidence `CHANGE_ROOT/evidence/finish-apply.json` plus optional `CHANGE_ROOT/evidence/finish-apply.md` prose.
- Migration target authority must use the selected `CHANGE_ROOT`; a legacy source path may be user-specified, but migrated contract/context/state/evidence must be change-local.

## Resume 规则

- Resume 必须先读取 `CHANGE_ROOT/state.json`，再由 helper 校验 contract hash、context fingerprint、state version、dirty state、Task ownership 与 pending Gate identity。
- 从 `deferred` resume 时，不能沿用过期 approval；若 artifact identity 或 state version 变化，必须回到相应 Gate。
- 从 `executing` resume 时，必须用 packet/evidence 中的 snapshot 与 current tree 对比；dirty 或 unknown changes 触发 `repair_required`。
- 从 `context_stale` resume 时，必须重新构造 context identity，并重新派发依赖该 context 的 packet。
- 从 `repair_required` resume 时，只允许执行 helper 给出的 fail-closed repair action 或重新请求用户决策。

## STOP 条件

遇到以下任一条件必须停止自动推进并展示 next action：

- 缺少 fresh Contract approval 却要执行产品 mutation。
- 缺少 fresh Finish approval 却要写长期知识、归档或执行 finish apply。
- `mutation_targets` 缺失、为空、越界、重叠冲突或与 Task ownership 不一致。
- Context 条目包含未授权绝对路径、路径穿越、glob、宽泛目录根、raw logs、full conversation、all docs、all source 或 unrelated tasks。
- Artifact hash、context fingerprint、state version、packet identity 或 evidence identity 不匹配。
- Worker packet 未经 `state-helper.py start-task ... --packet-json <packet>` 成功绑定，或 artifact existence、bare SHA、agent claim、Controller inference 被当作 dispatch authority。
- 工作区存在未知 dirty changes，或 snapshot/fingerprint 无法证明变更归属。
- Helper schema validation、path allowlist、state transition 或 check command fail closed。
- Agent claim 与文件 evidence 冲突，或 agent summary 被当成 authority。
- 用户 defer/reject Gate decision，或用户要求停止。
- Finish target language metadata 缺失、冲突或为 unknown，导致 existing/new knowledge/archive 目标无法安全确定正文语言。
- 请求把 historical archives、prior evidence、hash-chain inputs、archived decision/completion 或已有长期知识仅因当前 `output_language` 改变而整体翻译或重写。
