# Finish

Finish 定义 Nuclio Next 在 `work` 完成候选实现后，如何形成 completion proposal、收集用户 Finish Gate decision，并在 fresh accept 后才执行长期知识写入、journal 与 archive。Finish 不修产品代码，不自动批准失败风险，不把模糊肯定推断为 accept。

## Contents

- [入口与事实源](#入口与事实源)
- [decision.md 四段](#decisionmd-四段)
- [允许的 decision token](#允许的-decision-token)
- [accept](#accept)
- [request changes](#request-changes)
- [defer](#defer)
- [reject](#reject)
- [模糊答复](#模糊答复)
- [Finish apply](#finish-apply)
- [禁止事项](#禁止事项)

## 入口与事实源

Finish 只能在 helper 判定 `.dev-docs/state.json` 的 `status` 为 `decision_pending`，且存在 fresh completion identity 时启动。Completion identity 必须绑定：

- `.dev-docs/contract.yaml` 的 `contract_sha256`
- `.dev-docs/context.jsonl` 的 `context_fingerprint`
- `.dev-docs/state.json` 的 `state_version`
- completion proposal hash
- mutation map hash
- change-wide check summary hash

Finish Gate 的用户 decision 只对这些 identity 生效。任何 artifact hash、state version、context fingerprint、completion proposal 或 finish plan 改变，都必须重新请求 decision。

## decision.md 四段

Finish 展示给用户的 `decision.md` 必须只包含以下四个顶层决策段，段名固定：

1. `Completion Verdict`
2. `Remaining Risks`
3. `Knowledge Proposal`
4. `Archive Decision`

### Completion Verdict

该段说明 Contract acceptance 的逐项结果、change-wide checks、review evidence、mutation map 与 residual failure。它必须明确区分：

- 已有 evidence 支持的完成项。
- 仍失败但可接受为 remaining risk 的项。
- 阻塞 Finish 的未解决 blocker。

存在 unresolved blocking finding、missing evidence、scope drift、stale context 或 validation failure 时，不得请求 accept；必须回到 `work` 或 `repair_required`。

### Remaining Risks

该段列出 completion critic 仍能识别但不阻塞的风险。每个风险必须包含：

- risk id
- 影响范围
- evidence 来源
- 为什么不阻塞 Finish Gate
- 用户可选择的 mitigation 或 request changes 建议

Remaining risk 不能自动批准，也不能被隐藏到 agent summary。

### Knowledge Proposal

该段列出 fresh accept 后允许写入的长期 knowledge targets。每个 target 必须包含：

- path
- before identity
- proposed after summary
- reason
- source evidence

Knowledge Proposal 只是 proposal；在 fresh accept 前，长期 knowledge bytes 必须保持不变。

### Archive Decision

该段列出 fresh accept 后允许执行的 archive 行为，包括 state archive、finish apply journal 与 evidence link。Archive Decision 必须说明：

- archive target
- before identity
- apply order
- rollback 或 stop 行为
- journal evidence identity

Archive Decision 不是 approval。只有 Finish Gate fresh accept 才能使 helper 进入 `folding`。

## 允许的 decision token

Finish 只接受用户以 exact token 表达的四种 decision：

- `accept`
- `request changes`
- `defer`
- `reject`

这些 token 必须针对当前展示的 `decision.md` identity。Controller 可以要求用户选择其中之一，但不能把“看起来不错”、“继续吧”、“可以”、“LGTM”或其它模糊肯定推断为 `accept`。

## accept

`accept` 表示用户批准当前 completion proposal、decision identity、state version 与列明的 finish apply plan。helper 必须记录 Finish Gate ledger 为 fresh approval，并派生 finish packet。

Fresh accept 后允许的写入仅限：

- `Knowledge Proposal` 中逐项列明的 knowledge targets。
- `Archive Decision` 中列明的 journal、state archive 或 archive target。
- finish apply evidence 中列明的 `finish_apply_journal`。

Accept 不允许：

- 修改产品代码。
- 新增未列明 knowledge target。
- 覆盖未在 proposal 中列明的长期知识。
- 改写 Contract acceptance 或 Task evidence。
- 忽略 finish apply validation failure。

如果 finish apply validation fail closed，必须停止并进入 `repair_required` 或返回 Finish Gate；不能部分归档。

## request changes

`request changes` 表示用户不接受当前 completion proposal，要求回到 `work`。Controller 必须要求用户说明变更方向，或将 request changes 转成 blocker 返回 Contract revision。

规则：

- 不写长期 knowledge。
- 不归档。
- 不执行 finish apply。
- 保留当前 completion evidence 供诊断。
- 若 requested change 仍在 approved Contract 内，helper 可回到 bounded fixer 或 work loop。
- 若 requested change 改变 goals、acceptance、constraints、design 或 `mutation_targets`，必须回到 Contract Gate 或 contract revision。

`request changes` 不是新的 Contract approval。

## defer

`defer` 表示用户暂缓 Finish decision。helper 必须将状态转为 `deferred`，保留 freshness baseline，但不得执行 finish apply。

规则：

- 长期 knowledge bytes 不变。
- Archive target 不变。
- Completion proposal 与 decision identity 可保留为 resume baseline。
- Resume 时必须重新校验 contract hash、context fingerprint、state version、dirty state、completion proposal hash 与 finish plan identity。
- 任一 identity 改变，旧 defer baseline 只能用于说明历史，不能直接恢复为 accept。

## reject

`reject` 表示用户拒绝当前 completion proposal 或拒绝应用知识。helper 必须记录 rejected decision，并停止 finish apply。

规则：

- 不应用 Knowledge Proposal。
- 不归档为 accepted change。
- 不写 finish apply journal，除非 journal 只记录 rejected decision 且不改变长期知识。
- 可以保留只读 evidence 供审计。
- 若用户之后要继续，必须启动新的 Contract revision 或新 change。

Reject 不能被 Controller 转换为 request changes，也不能保留隐含 approval。

## 模糊答复

任何不完全等于 `accept`、`request changes`、`defer` 或 `reject` 的答复都是 ambiguous。Controller 必须一次只问一个澄清问题：

“请选择 exact Finish decision：`accept`、`request changes`、`defer` 或 `reject`。”

在用户给出 exact token 前：

- Finish Gate ledger 不得变为 approved。
- 不写长期 knowledge。
- 不归档。
- 不执行 finish apply。
- 不把自然语言肯定写入 decision authority。

## Finish apply

Fresh accept 后，helper 派生 finish packet，packet `role` 为 `finish`，包含 `completion_sha256`、`decision_sha256`、`finish_plan_sha256` 与 `snapshots`。Finish apply 的执行必须满足：

1. 重新校验 state version、decision identity、completion proposal hash 与 finish plan hash。
2. 读取所有 knowledge target 的 before identity。
3. 按 `Archive Decision` 的 apply order 写入列明 targets。
4. 写入 `finish_apply_journal` evidence，包含每个 target 的 before/after hash 与 reason。
5. 原子更新 state 到 `archived`，或在失败时停止并报告未应用步骤。

如果任一步骤失败，helper 必须 fail closed。已写入但未 journal 的情况必须进入 manual handling blocker，Controller 不得声称完成。

## 禁止事项

Finish 阶段禁止：

- 修产品代码或继续实现 Task。
- 把 failed checks 自动降级为 accepted risk。
- 在 fresh accept 前改变长期 knowledge bytes、journal 或 archive。
- 把模糊肯定推断为 accept。
- 写出 `Knowledge Proposal` 和 `Archive Decision` 未列明的路径。
- 使用 raw transcript、agent summary 或 chat history 作为 decision authority。
- 因 artifact existence 推断 Finish approval。
