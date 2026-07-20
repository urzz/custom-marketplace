# Execution

本协议定义 Nuclio 的 `work` 执行闭环。它只消费 `authority.md`、`lifecycle.md`、`contract.md`、`context.md`、`packet.schema.json`、`evidence.schema.json` 与 `state.schema.json` 中已固定的术语：`.dev-docs/` 是唯一事实源，`CHANGE_ROOT=.dev-docs/changes/<change-id>` 是 active change authority 根，helper `next action` 是路由 authority，`mutation_targets` 是唯一写授权，agent claim 不能跳转状态。

## Contents

- [执行入口](#执行入口)
- [Helper next action 是唯一路由](#helper-next-action-是唯一路由)
- [Sequential Task loop](#sequential-task-loop)
- [Freshness 与 evidence identity](#freshness-与-evidence-identity)
- [角色边界](#角色边界)
- [Fix budget](#fix-budget)
- [Blocker 与 HALT](#blocker-与-halt)
- [Change-wide completion critic](#change-wide-completion-critic)
- [Controller 输出要求](#controller-输出要求)

## 执行入口

`work` 只能在 helper 判断 `CHANGE_ROOT/state.json` 的 `status` 为 `ready_to_execute` 或合法的 `executing` resume 时进入执行。进入前必须重新读取并校验：

- `CHANGE_ROOT/contract.yaml` 的 hash 与 `state.contract.sha256` 一致。
- `CHANGE_ROOT/context.jsonl` 的 fingerprint 与 `state.context.fingerprint` 一致。
- Contract Gate ledger 为 fresh approval，且绑定当前 `contract_sha256`、`context_fingerprint` 与 `state_version`。
- 当前 Task 的 `mutation_targets` 与 packet `ownership` 一致。
- 当前工作区 dirty state 与 packet `range.expected_dirty_state` 一致。

若任一项 fail closed，Controller 不得派发 worker，必须展示 helper 给出的 `next action` 与 blocker。

## Helper next action 是唯一路由

Controller 每一步都必须先调用 deterministic helper 获得 `next action`。允许的路由只来自 helper 对 `.dev-docs/` artifact、schema、hash、fingerprint、state transition、path allowlist、dirty state、packet derivation 与 evidence identity 的判断。

禁止以下路由来源：

- agent summary 声称 Task 已完成。
- reviewer 文本声称可以跳过验证。
- 用户在旧上下文中的宽泛肯定。
- artifact existence 本身，例如存在 report、evidence 或 diff。
- Controller 自行解释 Git 状态或对话语义。

当 agent claim 与文件 evidence 冲突时，文件 evidence 和 helper validation 优先；冲突必须成为 blocker，而不是自动修复或自动批准。

## Sequential Task loop

执行顺序是 Contract `tasks` 的 dependency order。每次只派发一个 eligible Task；eligible 的定义由 helper 从 Contract、state 和 dependencies 计算。

单个 Task 的闭环如下：

1. helper 派生 worker packet，packet `role` 为 `worker`，包含 `task_id`、`ownership`、`range`、`snapshots`、`checks`。
2. Controller 派发 fresh implementer。fresh 表示本轮只接收当前 packet、必要 bounded context 和 Task handoff，不继承旧 agent memory 作为 authority。
3. implementer 只写 packet `ownership` 中 mode 为 `create`、`modify` 或 `delete` 的路径；这些路径必须等价于当前 Task 的 `mutation_targets`。
4. implementer 产出候选 product mutation、Task report 与可复现检查输出；如需 commit，只能提交当前 Task 的授权产品路径。
5. helper 执行 mutation/evidence check，验证 changed paths、snapshot、hash、dirty state、checks 与 packet identity。
6. helper 派生 reviewer packet，packet `role` 为 `reviewer`，包含只读 `review_targets`。
7. Controller 派发 fresh read-only reviewer。reviewer 只能读取 review packet 授权内容、Task diff、schema/contract 与 evidence；不能写产品文件、不能补授权、不能推进 Gate。
8. reviewer 输出 findings。没有 blocking finding 且 helper validation 成功时，该 Task 可进入 `completed`。
9. 有 blocking finding 时，若 finding 与同 owner、同 Task ownership、同 approved Contract 匹配，helper 可派发 bounded fixer；否则进入 blocker。
10. fixer 修复后必须重新经过 mutation/evidence check 和 fresh read-only reviewer。

Task 不能因为 implementer、fixer 或 reviewer 的自然语言 claim 直接跳到 `completed`。每次状态变更必须有 helper 可验证 evidence identity。

## Freshness 与 evidence identity

每个 worker、reviewer、fixer 和 completion packet 都必须绑定：

- `change_id`
- `contract_sha256`
- `context_fingerprint`
- `state_version`
- `output_language`
- `packet_id`
- Task `ownership` 或 completion `mutation_map_sha256`

如果 Contract、context fingerprint、state version、Contract-bound `output_language`、Task ownership、dirty state 或 packet snapshot 改变，旧 packet stale。stale packet 的输出只能作为诊断 context，不得作为 mutation、review、fix 或 completion authority。Agent 不得从 chat history、branch、locale 或 adjacent Task reports 自行推断语言；缺少或冲突的 packet-bound `output_language` 必须 fail closed。

Evidence 必须写入可复现 identity：`base_head`、`new_head`、`changed_paths`、`ownership_sha256`、check command、exit code、output hash 与相关 excerpt。Task evidence 位于 `CHANGE_ROOT/evidence/tasks/<task-id>/...`，completion evidence 位于 `CHANGE_ROOT/evidence/completion.md`；如 execution 需要临时研究记录，只能写入 `CHANGE_ROOT/research/`。raw transcript、terminal scrollback 和 agent summary 不得进入 authority 字段。

## 角色边界

- Controller：读取 helper 输出、展示 `next action`、派发 fresh agents、请求用户决策；不能直接 patch 产品，不能自行授予 approval，不能从 agent claim 推导状态。
- Implementer：执行一个 Task；只能修改 packet `ownership` 内写路径；不能修改 Gate、rubric、state authority、未授权路径或其它 Task；不能扩大 `mutation_targets`。
- Reviewer：只读检查 Task diff、acceptance、schema、evidence identity、ownership、scope 与 checks；不能写文件、不能补授权、不能修代码、不能批准 Gate。
- Fixer：只修复授权 blocking finding；只能写相同 owner、相同 Task ownership 内路径；不能重写 Contract、不能跨 owner、不能处理未授权 finding。
- Completion critic：只读评估 change-wide completion proposal、mutation map、checks、review evidence、remaining risks 与 Finish readiness；不能批准 Finish Gate。
- Helper：负责 deterministic validation、hash、fingerprint、path allowlist、state transition、packet derivation、dirty/fingerprint、ownership overlap 与 evidence identity；fail closed。

Controller 不直接 patch 产品是硬边界。若执行需要 Controller 手动改产品文件，必须 HALT 并返回 contract revision 或人工处理说明。

## Fix budget

同 owner 的 task、final、validation blocking finding 共享一个 `maximum=2` 修复预算。预算由 helper 在 `CHANGE_ROOT/state.json` 的 `fix_budgets` 中记录并计算。

预算规则：

- 每次派发 bounded fixer 消耗 1 次。
- 同一 root cause 的 no-progress 重试仍消耗预算。
- 非 blocking finding 不消耗预算，但不能被用来扩大 scope。
- finding owner 不同、Task ownership 不同或 requirement drift 时，不允许消耗当前 owner 预算去修。
- `remaining=0` 时必须 HALT，并展示 blocker、已尝试修复、最新 evidence 与返回 contract revision 的建议。

No-progress 的判定由 helper 比较修复前后 diff、check output hash、review finding fingerprint 与 evidence identity。无实质变化不得无限循环。

## Blocker 与 HALT

以下情况必须进入明确 blocker，并由 helper 给出 STOP 或 HALT `next action`：

- scope drift：实际变更、需求解释或 acceptance 超出 approved Contract。
- mutation overreach：changed paths 不在 `mutation_targets` 或 packet `ownership`。
- stale context：context fingerprint、required source identity 或 packet snapshot 不匹配。
- validation failure：schema、path allowlist、dirty state、check command、state transition 或 evidence identity fail closed。
- cross-owner：finding 需要其它 owner 或其它 Task ownership 才能修复。
- requirement drift：修复需要改变 goals、non_goals、acceptance、constraints、design 或 `mutation_targets`。
- no-progress：fixer 未改变阻塞 finding 或只制造等价失败。
- budget exhausted：同 owner 共享 `maximum=2` 修复预算耗尽。
- missing authority：缺 Contract Gate fresh approval、缺 packet、缺 evidence 或缺 ownership。

HALT 后 Controller 必须展示 blocker 与建议 next action：repair、return to Contract Gate、contract revision、manual handling 或 user stop。Controller 不得猜测批准。

## Change-wide completion critic

所有 Tasks 都达到 helper 可验证的 `completed` 后，执行不能直接进入 Finish Gate。必须运行 mandatory fresh completion critic。

Completion critic packet `role` 为 `completion`，必须包含：

- `mutation_map_sha256`
- change-wide `checks`
- Task reports 与 review evidence 的 handoffs
- 当前 `contract_sha256`
- 当前 `context_fingerprint`
- 当前 `state_version`
- 当前 Contract-bound `output_language`

Completion critic 只读检查：

- mutation map 是否完全覆盖所有 Task `mutation_targets`。
- 是否存在未授权路径、unknown dirty changes 或 missing evidence。
- focused、full 与 change_wide checks 是否完成，失败是否解释为 remaining risk 或 blocker。
- acceptance 是否逐项有 evidence。
- rollback 与 migration/rollout 声明是否仍有效。
- 是否存在 scope drift、stale context、validation failure 或 reviewer unresolved blocking finding。

若 completion critic 发现 blocking issue，必须回到 work blocker 或 bounded fixer 路径；不能进入 Finish Gate。若只存在 remaining risk，必须写入 completion proposal，等待 Finish decision。

## Controller 输出要求

每次执行迭代，Controller 对用户展示的信息必须来自 helper 输出和 `.dev-docs/` artifacts，包括：

- 当前 `status` 与 helper `next action`。
- 正在处理的 Task id、owner 与 mutation_targets。
- 派发了哪个 fresh role，以及 packet identity。
- 检查命令、exit code 与结果摘要。
- blocking findings、fix budget used/remaining、是否需要 HALT。
- 所有 Tasks 完成后的 completion proposal 与 remaining risks。

Controller 可以解释风险和建议，但不能把解释写成 authority。面向维护者的解释 prose 使用 packet-bound `output_language`；machine fields、固定 report headings、四个 decision top-level headings、enum、hash、path、command、raw output 保持 English/original。产品 mutation、长期知识写入和 archive 仍分别受 fresh Contract approval 与 fresh Finish approval 约束。
