# Lifecycle

本 lifecycle 使用 `authority.md` 中的 authority 术语：`.dev-docs/` 是事实源，artifact existence 不是 approval，Contract/Finish approval 必须 fresh，`mutation_targets` 是唯一写授权。

## 日常 Gate

- Contract Gate：用户批准当前 `contract.yaml`、context fingerprint、state version 和 mutation_targets 后，才允许产品 mutation。
- Finish Gate：用户批准 completion proposal、decision identity 与 state version 后，才允许长期知识写入、归档或 finish apply。

除这两个日常 Gate 外，Controller 可以要求澄清或修复，但不能把对话同意、agent claim 或 artifact 存在解释为 Gate approval。

## 状态与 next action

| status | 含义 | 允许的 next action |
| --- | --- | --- |
| `idle` | 没有 active change，或上一个 change 已归档。 | 启动 init；创建 draft contract；读取 project context。 |
| `drafting_contract` | 正在形成或修订 `contract.yaml` 与 `context.jsonl`。 | 询问澄清；生成/更新 contract draft；运行 schema 与 context 检查；转入 `contract_pending`。 |
| `contract_pending` | Contract draft 已可展示，等待用户 Contract Gate decision。 | 展示摘要、风险、mutation_targets、validation；等待 explicit approve/defer/reject；不得执行 mutation。 |
| `ready_to_execute` | 存在 fresh Contract approval，且 state/context/contract identity 未变。 | 派发 Task packet；重新校验 dirty/fingerprint；开始执行；转入 `executing`。 |
| `executing` | 一个或多个 Task 正在实现、review 或修复。 | 按 packet 派发 fresh implementer/reviewer/fixer；记录 evidence；更新 Task 状态；完成后转入 `completing`。 |
| `completing` | 所有 Task 候选实现完成，正在做 change-wide completion。 | 汇总 mutation map、checks、review evidence、risk；生成 completion proposal；转入 `decision_pending`。 |
| `decision_pending` | Completion proposal 已可展示，等待 Finish Gate decision。 | 展示 before/after、residual risk、finish apply plan；等待 explicit approve/defer/reject；不得写长期知识或归档。 |
| `folding` | 存在 fresh Finish approval，正在执行长期知识写入或归档。 | 应用 approved finish plan；记录 before/after evidence；归档 state；转入 `archived`。 |
| `archived` | Change 已结束且历史可追溯。 | 回到 `idle`；只允许只读审计或显式新 change。 |
| `repair_required` | helper 发现 state、hash、ownership、dirty、schema 或 evidence 不一致。 | 停止自动推进；展示原因；执行授权 repair；必要时重新请求 Gate。 |
| `context_stale` | context fingerprint 或 required source identity 与 approval/packet 不匹配。 | 停止执行；刷新 context；重新生成 packet 或回到 Contract Gate。 |
| `deferred` | 用户选择暂缓 Contract 或 Finish decision。 | 保留 state；允许 resume 前重新校验 freshness；不得假设继续批准。 |
| `rejected` | 用户拒绝 Contract 或 Finish decision。 | 停止当前路径；允许重开 drafting 或归档为 rejected；不得执行被拒绝 mutation。 |

## Resume 规则

- Resume 必须先读取 `.dev-docs/state.json`，再由 helper 校验 contract hash、context fingerprint、state version、dirty state、Task ownership 与 pending Gate identity。
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
- 工作区存在未知 dirty changes，或 snapshot/fingerprint 无法证明变更归属。
- Helper schema validation、path allowlist、state transition 或 check command fail closed。
- Agent claim 与文件 evidence 冲突，或 agent summary 被当成 authority。
- 用户 defer/reject Gate decision，或用户要求停止。
