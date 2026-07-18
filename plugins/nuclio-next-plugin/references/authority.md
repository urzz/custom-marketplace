# Authority

Nuclio Next 的 authority 只来自项目内 `.dev-docs/` 文件和 deterministic helper 可验证的 identity。对话、agent summary、原始 transcript、临时 artifact 是否存在，都不能单独表达 approval、ownership、freshness 或完成状态。

## 唯一事实源

- `.dev-docs/contract.yaml` 是当前 change 的目标、约束、设计边界、Task、mutation_targets、handoff、检查与 rollback 事实源。
- `.dev-docs/context.jsonl` 是允许读取的 bounded context 事实源；它只授权读取，不授权写入。
- `.dev-docs/state.json` 是 lifecycle、Gate ledger、Task 状态、blocker、completion、decision 与 history 的事实源。
- evidence 文件记录 helper 可校验的 hash、fingerprint、snapshot、check output 与 before/after identity；它们不能绕过 Gate。

## Approval 与 freshness

- Artifact existence != approval。存在 contract、packet、evidence、report 或 summary 不代表用户批准。
- Contract Gate 和 Finish Gate 是唯一日常用户 Gate，必须由当前轮 explicit approval 表达。
- Fresh Contract approval 必须绑定 contract artifact hash、context fingerprint、state version 与 approval identity；产品 mutation 前必须存在该 fresh approval。
- Fresh Finish approval 必须绑定 completion proposal、decision identity、state version 与 approval identity；长期知识写入、归档或 finish apply 前必须存在该 fresh approval。
- 如果 contract、context、state version、mutation_targets、decision 或 relevant artifact hash 改变，旧 approval 失效，状态必须转入需要重新决策或 repair 的路径。

## 写授权与读授权

- `mutation_targets` 是唯一写授权来源；implementer、fixer、helper 和 Controller 都不能写出当前 Task ownership 或当前 approved Contract 的 mutation_targets。
- Context 条目只授权读取指定路径或片段，不授权修改，也不授权递归读取未列入内容。
- 路径 allowlist、dirty check、snapshot/fingerprint、ownership overlap、handoff lineage、state transition 与 packet derivation 必须由 helper fail closed 校验。
- Controller 只负责路由、展示 next action、请求用户决策和调用 helper；Controller 不能从对话或 agent claim 推导 Gate、ownership、freshness 或完成状态。

## 角色边界

- Controller：读取 state/helper 输出，推进 init/work/finish 控制流，请求 Contract 或 Finish decision；不能自行授予 approval。
- Implementer：按 packet 执行单个 Task，只写 packet 中的 ownership，提交候选变更并报告 evidence；不能修改 Gate、rubric、state authority 或未授权路径。
- Reviewer：只读检查 Task diff、schema/contract 一致性、evidence identity 与 acceptance；不能写产品文件或状态 authority。
- Fixer：只修复授权 finding 与 Task ownership 内路径；不能扩大 scope 或重写 Contract。
- Completion critic：只读评估 change-wide completion proposal 与 residual risks；不能批准 Finish Gate。
- Helper：以标准库脚本执行 deterministic validation、hash、fingerprint、path allowlist、state transition、packet/evidence identity 与 fail-closed 决策。

## 禁止能力

- 不引入 daemon、background worker、MCP server、runtime hook 或项目本地 `.claude/` 安装。
- 不创建 `.nuclio/` runtime state；Nuclio Next 的运行事实源只在 `.dev-docs/`。
- 不自动 `stash`、`reset`、`clean`、`rebase`、`push` 或批量改写用户 active changes。
- 不把 raw logs、raw transcript、agent summary 或 chat history 作为 authority 字段。
- 不 silent migrate legacy content；migration 必须可检测、可预览、显式 opt-in、可验证。
