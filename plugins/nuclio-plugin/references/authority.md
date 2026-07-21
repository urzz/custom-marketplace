# Authority

Nuclio 的 authority 只来自项目内 `.dev-docs/` 文件和 deterministic helper 可验证的 identity。对话、agent summary、原始 transcript、临时 artifact 是否存在，都不能单独表达 approval、ownership、freshness 或完成状态。

## 唯一事实源

- Project-level `.dev-docs/` 只保留 index、knowledge 和 changes/index：`.dev-docs/index.md`、`.dev-docs/index.json`、`.dev-docs/knowledge/` 与 `.dev-docs/changes/index.md`。
- 每个 active change 必须先定义 `CHANGE_ROOT=.dev-docs/changes/<change-id>`；所有 change authority、helper state 与 evidence 都必须位于该目录下。
- `CHANGE_ROOT/contract.yaml` 是当前 change 的目标、约束、设计边界、Task、mutation_targets、handoff、检查、rollback 与 Contract-bound `output_language` 事实源。
- `CHANGE_ROOT/context.jsonl` 是允许读取的 bounded context 事实源；它只授权读取，不授权写入。
- `CHANGE_ROOT/state.json` 是 lifecycle、Gate ledger、Task 状态、blocker、completion、decision 与 history 的事实源。
- `CHANGE_ROOT/research/` 只保存当前 change 的 bounded research artifact；它不能扩展 context 读授权或写授权。
- Evidence authority 只在 `CHANGE_ROOT/evidence/`：Task evidence 位于 `CHANGE_ROOT/evidence/tasks/<task-id>/...`，completion、decision、finish apply 分别位于 `CHANGE_ROOT/evidence/completion.md`、`CHANGE_ROOT/evidence/decision.md`、`CHANGE_ROOT/evidence/finish-apply.md`。
- Evidence 文件记录 helper 可校验的 hash、fingerprint、snapshot、check output 与 before/after identity；它们不能绕过 Gate。
- Worker packet artifact existence、packet hash 或 bare SHA 不是 dispatch authority。`packet.schema.json is the only packet shape/role authority`；state-helper is the state-specific packet identity and transition authority for packet id, current state identity, freshness, Task, ownership, and atomic bind/start.

## Approval 与 freshness

- Artifact existence != approval。存在 contract、packet、evidence、report 或 summary 不代表用户批准。
- Contract Gate 和 Finish Gate 是唯一日常用户 Gate，必须由当前轮 explicit approval 表达。
- Fresh Contract approval 必须绑定 `CHANGE_ROOT/contract.yaml` artifact hash、`CHANGE_ROOT/context.jsonl` fingerprint、`CHANGE_ROOT/state.json` version、mutation_targets、Contract-bound `output_language` 与 approval identity；产品 mutation 前必须存在该 fresh approval。
- Fresh Finish approval 必须绑定 `CHANGE_ROOT/evidence/completion.md` proposal、`CHANGE_ROOT/evidence/decision.md` identity、`CHANGE_ROOT/state.json` version 与 approval identity；长期知识写入、归档或 `CHANGE_ROOT/evidence/finish-apply.md` 写入前必须存在该 fresh approval。
- Contract Gate 只接受 helper 定义的 trim-only exact aliases `approve`、`批准`、`同意`、`继续` 并存储 canonical `approve`；Finish Gate 只接受 `accept`/`同意`、`request_changes`/`要求修改`、`defer`/`暂缓`、`reject`/`拒绝` 并存储 canonical English decision。不要把所有中文肯定词都视为 accept；Finish 中 `继续`、`可以`、`我同意` 等不是 exact accept。
- 如果 contract、context、state version、mutation_targets、`output_language`、decision 或 relevant artifact hash 改变，旧 approval 失效，状态必须转入需要重新决策或 repair 的路径。

## 写授权与读授权

- `mutation_targets` 是唯一写授权来源；implementer、fixer、helper 和 Controller 都不能写出当前 Task ownership 或当前 approved Contract 的 mutation_targets。
- Context 条目只授权读取指定路径或片段，不授权修改，也不授权递归读取未列入内容。
- Packet-bound `output_language` 必须由 helper 从当前 Contract 派生并传给 worker、reviewer、fixer、completion critic 与 Finish packet；agent 只能消费 packet/envelope 值，不能从 chat history、branch name、用户记忆、邻近 Task 或仓库 locale 自行推断语言。
- Finish target language metadata 是长期 knowledge/archive 写入时的目标语言 authority：existing target 保持既有主要语言，new target 使用 Contract-bound `output_language`，unknown/missing metadata 必须 STOP。
- 路径 allowlist、dirty check、snapshot/fingerprint、ownership overlap、handoff lineage、state transition、target language metadata 与 packet derivation 必须由 helper fail closed 校验。
- Work implementer dispatch 的唯一正常路径是 `derive/write → schema+identity bind/start → dispatch`：packet-helper 写入 worker packet artifact，state-helper 通过 canonical packet schema 与 current state identity 完成首次绑定和 start-task，成功后才派发 fresh implementer。stale, wrong Task, wrong ownership, wrong role, cross-role, tampered, replacement, or unbound evidence fail closed；`INVALID_PACKET_SCHEMA` 或 identity/transition 错误均不得改变 state bytes。
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
- 不创建 `.nuclio/` runtime state；Nuclio 的运行事实源只在 `.dev-docs/` 和 change-local `CHANGE_ROOT`。
- 不自动 `stash`、`reset`、`clean`、`rebase`、`push` 或批量改写用户 active changes。
- 不把 raw logs、raw transcript、agent summary 或 chat history 作为 authority 字段。
- 不 silent migrate legacy content；migration 必须可检测、可预览、显式 opt-in、可验证，migration target authority 必须写入 selected `CHANGE_ROOT`。
- 不自动翻译、重写或迁移 historical archives、prior reports、accepted evidence、hash-chain inputs、archived `completion.md`/`decision.md` 或长期 knowledge，只因当前 `output_language` 改变而改写历史是禁止的。
