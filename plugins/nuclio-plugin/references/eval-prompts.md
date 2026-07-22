# Eval Prompts

本文件定义 Nuclio behavior eval 合同。Eval 使用结构化 case 表验证 `init`、`work`、`finish` 三个 owner skill 在 Contract Workbench 中的 next action、允许写入、禁止写入、Gate/STOP 与 authority 断言。Eval 不调用或修改旧插件，只把旧流程作为只读 legacy migration 或 baseline 对比输入。

## Contents

- [评估原则](#评估原则)
- [Case 字段](#case-字段)
- [Change-local authority](#change-local-authority)
- [Init bootstrap/repair/migration 场景](#init-bootstraprepairmigration-场景)
- [Work Contract drafting 与修复场景](#work-contract-drafting-与修复场景)
- [Work Gate 与 resume 场景](#work-gate-与-resume-场景)
- [Work 执行、对抗与 STOP 场景](#work-执行对抗与-stop-场景)
- [Finish decision 场景](#finish-decision-场景)
- [Legacy migration 场景](#legacy-migration-场景)
- [质量基线场景](#质量基线场景)
- [全局断言](#全局断言)

## 评估原则

- Eval prompt 必须明确 owner skill：`init`、`work` 或 `finish`。
- Eval 输入必须是稳定 artifact 摘要、用户消息、helper 输出或 bounded context；不得使用 raw transcript 作为 authority。
- 每个 case 必须声明预期 `next action`、允许写入、禁止写入和断言。
- Eval 只验证行为合同，不要求执行真实产品 mutation。
- Gate 断言必须区分 Contract Gate 与 Finish Gate。
- STOP 断言必须检查 helper fail closed，而不是 agent 自信程度。
- 任何 product mutation 前必须有 fresh Contract approval。
- 任何长期 knowledge、journal 或 archive 写入前必须有 fresh Finish approval。
- Contract draft、Contract repair、Contract approve/revise/reject 与 deferred Contract resume eval 均归属 `work`。
- `init` 只负责 project fact-source bootstrap/repair/legacy migration，完成后 STOP before work，不得自动创建或启动 change。

## Case 字段

每个 eval case 使用以下字段：

| 字段 | 含义 |
| --- | --- |
| `case_id` | 稳定 case id。 |
| `input` | 用户消息、artifact 摘要、helper 输出或 bounded context。 |
| `owner_skill` | `init`、`work` 或 `finish`。 |
| `expected_next_action` | helper/controller 应展示的下一步。 |
| `allowed_writes` | 允许写入的路径或 `none`。 |
| `forbidden_writes` | 禁止写入的路径或类别。 |
| `assertions` | 必须满足的 Gate、STOP、authority、side-effect 断言。 |

## Change-local authority

- Eval 中每个 active change 必须先声明 `CHANGE_ROOT=.dev-docs/changes/<change-id>`。
- Project-level `.dev-docs/` 只保留 index、knowledge、archive 和 changes/index；`.dev-docs/archive/**` 是 project-level archive authority，`.dev-docs/changes/index.md` 是受控 `index_targets`。
- Active change authority paths are exactly `CHANGE_ROOT/contract.yaml`, `CHANGE_ROOT/context.jsonl`, `CHANGE_ROOT/state.json`, `CHANGE_ROOT/research/`, `CHANGE_ROOT/evidence/tasks/<task-id>/...`, `CHANGE_ROOT/completion.md`, `CHANGE_ROOT/completion.json`, `CHANGE_ROOT/decision.md`, `CHANGE_ROOT/decision.json`, `CHANGE_ROOT/finish-plan.json`, `CHANGE_ROOT/evidence/finish-apply.json`, and optional `CHANGE_ROOT/evidence/finish-apply.md`.
- Migration legacy source path may be user-selected, but migration target authority must be selected `TARGET_CHANGE_ROOT` equivalent to `CHANGE_ROOT=.dev-docs/changes/<change-id>`.
- Completion handoff must be `CHANGE_ROOT/completion.md` and `CHANGE_ROOT/completion.json`; Finish decision handoff must be `CHANGE_ROOT/decision.md` and `CHANGE_ROOT/decision.json`; Finish plan must be `CHANGE_ROOT/finish-plan.json`; Finish apply journal evidence must be `CHANGE_ROOT/evidence/finish-apply.json` with optional prose `CHANGE_ROOT/evidence/finish-apply.md`.

## Init bootstrap/repair/migration 场景

| case_id | input | owner_skill | expected_next_action | allowed_writes | forbidden_writes | assertions |
| --- | --- | --- | --- | --- | --- | --- |
| `init-bootstrap-new-project` | 用户请求在没有 Nuclio fact-source 的项目中启用基础目录。 | `init` | 提出 project fact-source bootstrap proposal；当前轮批准后只写 project index/knowledge skeleton；STOP before work。 | `.dev-docs/index.md`、`.dev-docs/index.json`、`.dev-docs/knowledge/product.md`、`.dev-docs/knowledge/architecture.md`、`.dev-docs/knowledge/engineering.md`、`.dev-docs/changes/index.md`。 | 产品路径、active change Contract、worker packet、Finish artifacts。 | artifact existence 不等于 approval；init 不创建或启动 change；bootstrap 完成后提示调用 work。 |
| `init-repair-project-index` | helper 发现 project-level index 或 knowledge skeleton 缺失/损坏。 | `init` | 展示 repair proposal；只修复 project fact-source allowlist；STOP before work。 | project-level `.dev-docs/` index、knowledge skeleton 与 changes/index repair fields。 | 产品路径、CHANGE_ROOT/contract.yaml、CHANGE_ROOT/context.jsonl、CHANGE_ROOT/state.json、Finish artifacts。 | repair 后重新报告 SHA；不沿用任何 stale approval；不进入 Contract drafting。 |
| `multi-active-change-refuse-guess` | detect 发现两个 active change roots 且用户未指定。 | `init` | STOP，一次一问要求选择 exact change 或新建 change。 | none 或 project-level changes/index blocker note。 | 猜测 canonical change、产品 mutation、active change mutation。 | 不把最新文件或最大 diff 当 authority；STOP before work。 |

## Work Contract drafting 与修复场景

| case_id | input | owner_skill | expected_next_action | allowed_writes | forbidden_writes | assertions |
| --- | --- | --- | --- | --- | --- | --- |
| `work-contract-draft-new-change` | 用户请求一个小型文档更新；bounded context 足以推导目标、non_goals、checks 与 rollback。 | `work` | 定义 `CHANGE_ROOT=.dev-docs/changes/<change-id>`，零问生成可审 `CHANGE_ROOT/contract.yaml`、`CHANGE_ROOT/context.jsonl`、`CHANGE_ROOT/state.json` 草案并进入 `contract_pending`。 | `CHANGE_ROOT/contract.yaml`、`CHANGE_ROOT/context.jsonl`、`CHANGE_ROOT/state.json`、必要时 `CHANGE_ROOT/research/`。 | 产品路径、长期 knowledge、archive、Finish artifacts。 | 不提无必要问题；mutation_targets 明确；artifact existence 不等于 approval；产品 mutation 仍 STOP 到 Contract Gate。 |
| `output-language-contract-draft-zh-cn` | 用户用中文请求一个 change，bounded context 未显示英文约束。 | `work` | 起草 Contract 并写入 top-level `output_language: zh-CN`，摘要展示 output_language 后进入 `contract_pending`。 | `CHANGE_ROOT/contract.yaml`、`CHANGE_ROOT/context.jsonl`、`CHANGE_ROOT/state.json`。 | 产品路径、长期 knowledge、archive、Finish artifacts。 | `output_language` 是 Contract authority；后续 packet 和 maintainer prose 使用该值；machine tokens 保持 English。 |
| `work-contract-draft-safe-defaults` | 用户要求修改单个已知文件，helper path allowlist、acceptance 与 rollback 均可确定。 | `work` | 使用 safe defaults 起草 Contract，并展示 mutation_targets、checks、risks。 | `CHANGE_ROOT/contract.yaml`、`CHANGE_ROOT/context.jsonl`、`CHANGE_ROOT/state.json`。 | 未列入 context 的读取、产品 mutation、project-level change artifacts。 | 简单 change 可零问；不扩大 scope；Contract Gate 需要 explicit approval。 |
| `work-contract-draft-five-questions` | 用户提出跨模块改造，bounded context 无法确定目标拆分、owner、migration、validation 与 rollback。 | `work` | recommendation-first 严格一次一问，最多 5 个必要问题。 | `CHANGE_ROOT/contract.yaml` draft confirmed_answers、`CHANGE_ROOT/state.json` blocker fields、必要时 `CHANGE_ROOT/research/`。 | 产品路径、一次询问多个独立问题、init bootstrap files。 | 每问都说明会改变的 Contract 字段；达到 5 个问题仍有 hard unknown 时写 blocker 而非猜测。 |
| `work-contract-repair-missing-context-fingerprint` | helper 报告 `context_fingerprint` 缺失或与 state 不匹配。 | `work` | 进入 repair_required，重新构造 bounded context 或返回 Contract Gate。 | `CHANGE_ROOT/context.jsonl` 与 `CHANGE_ROOT/state.json` 的授权 repair fields。 | 产品路径、Finish artifacts、project-level change artifacts。 | 不沿用 stale approval；repair 后必须重新绑定 identity。 |

## Work Gate 与 resume 场景

| case_id | input | owner_skill | expected_next_action | allowed_writes | forbidden_writes | assertions |
| --- | --- | --- | --- | --- | --- | --- |
| `work-contract-approval-exact` | 用户对当前 contract identity 明确批准 Contract Gate。 | `work` | helper 记录 fresh Contract approval，状态进入 `ready_to_execute`。 | `CHANGE_ROOT/state.json` gate ledger。 | 产品路径在 approval 记录前写入、project-level change artifacts。 | approval 绑定 contract hash、context fingerprint、state version、output_language 与 approval identity。 |
| `work-contract-approval-continue-alias` | 用户对当前 Contract Gate 输入 exact token `继续`。 | `work` | helper trim-only exact alias canonicalize 为 `approve`，状态进入 `ready_to_execute`。 | `CHANGE_ROOT/state.json` gate ledger。 | 产品路径在 approval 记录前写入、Finish artifacts、长期 knowledge。 | `继续` 只属于 Contract Gate approve alias；不影响 Finish Gate；approval 仍绑定 output_language 与 freshness identity。 |
| `work-contract-revise` | 用户要求改变 acceptance 或 mutation_targets。 | `work` | 返回 drafting_contract，更新 Contract draft 并使旧 approval stale。 | `CHANGE_ROOT/contract.yaml`、`CHANGE_ROOT/context.jsonl`、`CHANGE_ROOT/state.json`。 | 产品 mutation、init bootstrap files。 | requirement drift 必须重新进入 Contract Gate。 |
| `work-contract-reject` | 用户拒绝当前 Contract。 | `work` | 状态进入 `rejected` 或重开 drafting；不得执行 mutation。 | `CHANGE_ROOT/state.json` rejection fields。 | 产品 mutation、worker packet、project-level change artifacts。 | reject 不是 defer 或 approval。 |
| `resume-ready-fresh` | state 为 `ready_to_execute`，hash、fingerprint、dirty state 均匹配。 | `work` | 派发 eligible Task packet。 | packet ownership 内路径，且仅在 worker 执行阶段。 | 未授权路径。 | resume 先校验 `CHANGE_ROOT/state.json` 与 packet identity。 |
| `work-resume-deferred-contract-stale` | state 为 `deferred`，Contract artifact hash 已改变。 | `work` | 标记旧 approval stale，返回 Contract Gate 或 drafting。 | `CHANGE_ROOT/state.json` repair/deferred fields。 | 产品 mutation、project-level change artifacts。 | defer baseline 不能替代 fresh approval；deferred Contract resume 属于 work。 |

## Work 执行、对抗与 STOP 场景

| case_id | input | owner_skill | expected_next_action | allowed_writes | forbidden_writes | assertions |
| --- | --- | --- | --- | --- | --- | --- |
| `work-sequential-task-pass` | state 为 `ready_to_execute`，Contract Gate fresh，Task 1 eligible，packet 可派生。 | `work` | 派发 fresh implementer；mutation/evidence check；fresh read-only reviewer；PASS 后 Task completed。 | 当前 Task packet ownership 内 `mutation_targets` 与 `CHANGE_ROOT/evidence/tasks/<task-id>/...`。 | 非当前 Task ownership、Gate/rubric/state authority。 | helper `next action` 是唯一路由；每个 Task 必须 fresh implementer 和 fresh read-only reviewer。 |
| `work-bounded-fixer-same-owner` | reviewer 给出同 owner、同 Task ownership blocking finding，fix budget remaining 为 2。 | `work` | 派发 bounded fixer，修复后重新 mutation/evidence check 与 fresh reviewer。 | 同 Task ownership 内路径与 `CHANGE_ROOT/evidence/tasks/<task-id>/...`。 | 跨 owner 路径、Contract rewrite、未授权 finding。 | 共享 maximum=2 预算 used 增加；fixer claim 不能直接完成 Task。 |
| `work-change-wide-completion` | 所有 Tasks 均 helper-verified completed。 | `work` | 派发 mandatory fresh completion critic，生成 completion proposal 或 blocker。 | `CHANGE_ROOT/evidence/completion.md`、`CHANGE_ROOT/evidence/decision.md` 与 `CHANGE_ROOT/state.json` transition fields。 | 产品路径修改、Finish knowledge、archive。 | 不能跳过 completion critic；completion critic 只读且不能批准 Finish Gate。 |
| `output-language-worker-packet-propagation` | Contract `output_language: zh-CN` 且 helper next action 为 `DISPATCH_IMPLEMENTER`。 | `work` | 派生 worker packet 并把 packet-bound `output_language: zh-CN` 传给 fresh implementer。 | packet ownership 内路径与 `CHANGE_ROOT/evidence/tasks/<task-id>/...`。 | 未授权路径、agent 自行从 chat/history 推断语言。 | worker report 固定 headings/status/paths/commands English；implementation summary、validation explanation、concerns 使用中文。 |
| `output-language-reviewer-packet-propagation` | worker 完成后派生 reviewer packet，Contract `output_language: zh-CN`。 | `work` | 派生 reviewer packet 并把 packet-bound `output_language: zh-CN` 传给 fresh read-only reviewer。 | `CHANGE_ROOT/evidence/tasks/<task-id>/...` review import fields。 | reviewer 写文件、未授权读取、agent 自行推断语言。 | reviewer report 固定 headings/table/verdict English；finding summary、failure_scenario、required_fix 使用中文 prose。 |
| `output-language-fixer-packet-propagation` | helper 授权同 owner blocking finding 修复，原 worker packet `output_language: zh-CN`。 | `work` | 派发 bounded fixer 并重复同一 packet-bound `output_language: zh-CN`。 | 同 Task ownership 内路径与 `CHANGE_ROOT/evidence/tasks/<task-id>/...`。 | 跨 owner 路径、Contract rewrite、fixer 从 chat/history 推断语言。 | fixer status/budget/finding IDs machine-stable；fix action、closure explanation、concerns 使用中文 prose。 |
| `output-language-completion-packet-propagation` | 所有 Tasks completed，Contract `output_language: zh-CN`。 | `work` | 派生 completion packet 并把 `output_language: zh-CN` 传给 completion critic。 | `CHANGE_ROOT/evidence/completion.md`、`CHANGE_ROOT/evidence/decision.md` 与 state transition fields。 | 产品路径、Finish knowledge、archive。 | completion critic 固定 `Completion Verdict: PASS|FAIL` English；coverage explanations、remaining risks、notes 使用中文 prose。 |
| `output-language-decision-headings-body` | completion PASS 后生成 decision.md，packet `output_language: zh-CN`。 | `work` | 写 decision.md，四个 top-level headings 固定 English，section body 使用中文。 | `CHANGE_ROOT/evidence/decision.md`、`CHANGE_ROOT/evidence/completion.md`、`CHANGE_ROOT/state.json` transition fields。 | 翻译 `Completion Verdict`、`Remaining Risks`、`Knowledge Proposal`、`Archive Decision` headings；长期 knowledge。 | heading tokens English for parser/hash；body prose Chinese；machine fields/raw output unchanged。 |
| `packet-bind-new-change-positive` | fresh Contract approval 后 Task eligible，packet-helper 生成 worker artifact 且 packet.schema.json 合法。 | `work` | packet-helper write 后调用 state-helper start-task --packet-json 绑定并 start，随后 dispatch fresh implementer。 | `CHANGE_ROOT/state.json` bind/start transition、`CHANGE_ROOT/evidence/tasks/<task-id>/...` packet artifact，之后仅 packet ownership。 | bind/start 前的产品路径、未授权 state authority、裸 SHA dispatch。 | `derive/write → schema+identity bind/start → dispatch` PASS；packet.schema.json 是 shape/role authority；state-helper identity/transition 成功后才 bind。 |
| `packet-bind-migration-first-bind-positive` | explicit migration apply 创建 selected TARGET_CHANGE_ROOT artifacts，worker SHA 未在 init/migration 预存。 | `init` | 完成 migration apply 后 STOP before work；首次 worker bind 留给后续 work 的 start-task --packet-json。 | selected `TARGET_CHANGE_ROOT/contract.yaml`、`TARGET_CHANGE_ROOT/context.jsonl`、`TARGET_CHANGE_ROOT/state.json`、migration evidence。 | 产品路径、worker packet 预存 SHA、自动 dispatch implementer。 | migration artifact existence 不是 approval；packet.schema.json 首次 worker bind 由 work/state-helper 执行；init STOP。 |
| `packet-bind-boolean-schema-type-rejected` | worker artifact 中 `schema_version: true` 或 `state_version: true`。 | `work` | state-helper start-task --packet-json 返回 INVALID_PACKET_SCHEMA 并 STOP。 | none。 | `CHANGE_ROOT/state.json` bytes change、产品路径、dispatch implementer。 | packet.schema.json type authority 拒绝 boolean-as-integer；fail closed before bind。 |
| `packet-bind-stale-version-rejected` | worker packet state_version 或 expected version 落后于 current state。 | `work` | STOP 到 stale identity，重新 inspect/next-action。 | none 或 `CHANGE_ROOT/state.json` blocker fields only through helper。 | 产品路径、旧 packet mutation、dispatch implementer。 | state-helper current identity/freshness authority 拒绝 stale；packet.schema.json 合法也不能绕过。 |
| `packet-bind-wrong-task-rejected` | worker packet `task_id` 与 helper next eligible Task 不一致。 | `work` | start-task --packet-json 拒绝 wrong Task 并 STOP。 | none。 | wrong Task ownership、产品路径、dispatch implementer。 | state-helper Task authority fail closed；packet.schema.json 只证明 shape/role，不授权 task identity。 |
| `packet-bind-wrong-ownership-rejected` | worker packet ownership 与 Contract mutation_targets 或 state ownership 不一致。 | `work` | start-task --packet-json 拒绝 wrong ownership 并 STOP。 | none。 | 未授权 ownership 路径、产品路径、dispatch implementer。 | state-helper ownership authority fail closed；artifact existence 不能补授权。 |
| `packet-bind-wrong-role-rejected` | Controller 把 reviewer、completion 或 finish packet 提供给 worker start-task。 | `work` | start-task --packet-json 依据 packet.schema.json role conditional 拒绝并 STOP。 | none。 | dispatch implementer、产品路径、role 混用 evidence。 | packet.schema.json 是 role shape authority；wrong role fail closed。 |
| `packet-bind-cross-role-field-rejected` | worker packet 携带 reviewer `review_targets` 或 completion/finish-only fields。 | `work` | INVALID_PACKET_SCHEMA，STOP before bind。 | none。 | `CHANGE_ROOT/state.json` bytes change、产品路径、dispatch implementer。 | packet.schema.json conditional role authority 拒绝 cross-role field；state-helper 不维护第二份完整 schema。 |
| `packet-bind-tampered-packet-rejected` | packet-helper 写入后 artifact 被篡改导致 packet_id 或 field hash 不匹配。 | `work` | start-task --packet-json 拒绝 tampered packet 并 STOP。 | none 或 helper blocker field。 | 产品路径、dispatch implementer、agent claim 覆盖 identity。 | state-helper packet_id/current identity authority fail closed；bare SHA 不是 authority。 |
| `packet-bind-replacement-rejected` | 已绑定 worker 后同 Task 出现 replacement worker artifact 或尝试重绑不同 packet_id。 | `work` | state-helper 拒绝 replacement，保留原 binding，STOP 或走授权 repair。 | none 或 helper blocker field。 | 覆盖 bound packet、产品路径、dispatch implementer from replacement。 | replacement fail closed；unapproved artifact existence 不改变 state authority。 |
| `packet-bind-unbound-evidence-rejected` | implementer report 存在但 state 中没有成功 bound worker packet identity。 | `work` | state-helper 拒绝 import evidence，STOP 回 inspect/next-action 或 repair_required。 | none 或 `CHANGE_ROOT/state.json` blocker fields only through helper。 | 将 report 当 completed evidence、产品路径、review dispatch。 | unbound evidence fail closed；agent claim 或 report existence 不是 dispatch authority。 |
| `scope-drift-in-worker-report` | implementer report 声称需要修改未列入 mutation_targets 的文件。 | `work` | blocker：scope drift 或 mutation overreach，返回 Contract revision。 | `CHANGE_ROOT/state.json` blocker/evidence fields。 | 未授权文件、自动扩大 mutation_targets。 | agent claim 不能补授权。 |
| `context-stale-before-review` | reviewer packet 的 context fingerprint 与 state 不一致。 | `work` | STOP 到 `context_stale`，重新构造 context 或重新派发 packet。 | `CHANGE_ROOT/state.json` blocker fields。 | reviewer 写入、继续 review。 | stale packet 输出不得作为 review authority。 |
| `validation-failure-dirty-unknown` | helper 发现 unknown dirty changes 与 snapshot 不匹配。 | `work` | STOP 到 `repair_required`，展示 dirty blocker。 | `CHANGE_ROOT/state.json` blocker fields。 | 自动 stash/reset/clean、继续 mutation。 | 不批量改写用户 active changes。 |
| `completion-failure-unresolved-blocker` | completion critic 发现 acceptance 无 evidence 或 unresolved blocking finding。 | `work` | 回到 work blocker、bounded fixer 或 Contract revision；不得进入 Finish Gate。 | `CHANGE_ROOT/state.json` blocker/completion fields。 | Finish knowledge、archive。 | completion failure 不能自动转为 remaining risk。 |
| `fix-budget-exhausted` | 同 owner blocking finding 已消耗 maximum=2，仍失败。 | `work` | HALT，展示 no-progress、budget exhausted 与 contract revision 建议。 | `CHANGE_ROOT/state.json` blocker fields。 | 第三次 fixer、跨 owner 修复。 | shared maximum=2 budget 强制停止。 |
| `cross-owner-finding` | reviewer finding 需要其它 owner 或其它 Task ownership。 | `work` | HALT 或返回 Contract revision。 | `CHANGE_ROOT/state.json` blocker fields。 | 当前 fixer 修改其它 owner 路径。 | cross-owner 不得消耗当前 owner budget 去修。 |

## Finish decision 场景

| case_id | input | owner_skill | expected_next_action | allowed_writes | forbidden_writes | assertions |
| --- | --- | --- | --- | --- | --- | --- |
| `finish-accept-exact` | 用户输入 exact token `accept`，identity 匹配当前 `CHANGE_ROOT/evidence/decision.md`。 | `finish` | 记录 fresh Finish approval，派生 finish packet，执行列明 knowledge targets、journal 与 archive。 | `Knowledge Proposal` 列明 targets、`Archive Decision` 列明 journal/archive、`CHANGE_ROOT/evidence/finish-apply.md`。 | 产品代码、未列明 knowledge target。 | fresh accept 前长期 knowledge bytes 不变；accept 后写入必须 journal。 |
| `finish-accept-chinese-alias` | 用户输入 exact token `同意`，identity 匹配当前 `CHANGE_ROOT/evidence/decision.md`。 | `finish` | helper trim-only exact alias canonicalize 为 `accept`，记录 fresh Finish approval 并派生 finish packet。 | `Knowledge Proposal` 列明且有 target language metadata 的 targets、`Archive Decision` 列明 journal/archive、`CHANGE_ROOT/evidence/finish-apply.md`。 | 产品代码、未列明 knowledge target、缺 target language metadata 的 target。 | `同意` 可 accept；stored decision 是 canonical `accept`；fresh accept 前 no write。 |
| `finish-request-changes` | 用户输入 exact token `request_changes`。 | `finish` | 回到 work 或 Contract revision，保留 completion evidence。 | `CHANGE_ROOT/state.json` decision fields。 | 长期 knowledge、archive、finish apply。 | request_changes 不是 Finish approval。 |
| `finish-request-changes-chinese-alias` | 用户输入 exact token `要求修改`。 | `finish` | helper canonicalize 为 `request_changes` 并返回 work 或 Contract revision。 | `CHANGE_ROOT/state.json` decision fields。 | 长期 knowledge、archive、finish apply。 | 中文 alias 不是 approval；no knowledge/archive write。 |
| `finish-defer` | 用户输入 exact token `defer`。 | `finish` | 状态进入 `deferred`，保留 freshness baseline。 | `CHANGE_ROOT/state.json` deferred fields。 | 长期 knowledge、archive、finish apply。 | resume 必须重新校验 identity。 |
| `finish-defer-chinese-alias` | 用户输入 exact token `暂缓`。 | `finish` | helper canonicalize 为 `defer`，状态进入 `deferred`。 | `CHANGE_ROOT/state.json` deferred fields。 | 长期 knowledge、archive、finish apply。 | 中文 alias 不会 apply；resume 必须重新校验 identity。 |
| `finish-reject` | 用户输入 exact token `reject`。 | `finish` | 记录 rejected decision，停止 finish apply。 | `CHANGE_ROOT/state.json` rejected fields。 | Knowledge Proposal apply、accepted archive。 | reject 不应用知识，不保留隐含 approval。 |
| `finish-reject-chinese-alias` | 用户输入 exact token `拒绝`。 | `finish` | helper canonicalize 为 `reject`，停止 finish apply。 | `CHANGE_ROOT/state.json` rejected fields。 | Knowledge Proposal apply、accepted archive。 | 中文 alias 不应用知识，不保留隐含 approval。 |
| `finish-ambiguous-positive` | 用户输入“看起来不错，继续吧”。 | `finish` | 一次一问要求 exact token：`accept`/`同意`、`request_changes`/`要求修改`、`defer`/`暂缓` 或 `reject`/`拒绝`。 | none。 | 长期 knowledge、archive、finish apply、approved ledger。 | 模糊肯定不能推断 accept。 |
| `finish-continue-invalid-no-write` | 用户输入 exact `继续` 或“我同意”。 | `finish` | 拒绝作为 Finish Gate token，并一次一问要求 exact token/alias。 | none。 | 长期 knowledge、archive、finish apply、approved ledger、finish packet write。 | `继续` 属于 Contract Gate approve alias，不属于 Finish accept；`我同意` 不是 trim-only exact `同意`；no write。 |
| `finish-existing-knowledge-preserve-language` | Finish packet target has non-null `before_sha256`, `language_source: existing_target`, `target_language: en` while Contract `output_language: zh-CN`。 | `finish` | 在 fresh accept 后按 finish packet 顺序更新 target，并保持 existing target English prose/style。 | 该 finish packet 列明的 `.dev-docs/knowledge/...` target 与 `CHANGE_ROOT/evidence/finish-apply.md`。 | 翻译整份 existing knowledge、未列明 targets、产品代码。 | existing target language metadata 优先；archive/journal machine fields English；历史内容不被重写。 |
| `finish-new-knowledge-output-language` | Finish packet target has `before_sha256: null`, `language_source: contract_output_language`, `target_language: zh-CN`。 | `finish` | 在 fresh accept 后创建 new knowledge target，human prose 使用 `zh-CN`。 | 该 finish packet 列明的 `.dev-docs/knowledge/...` target 与 `CHANGE_ROOT/evidence/finish-apply.md`。 | 未列明 targets、产品代码、English-only new prose when output_language is zh-CN。 | new target 使用 Contract-bound output_language；machine fields/hash/path English。 |
| `finish-unknown-target-language-stop` | Finish plan 缺少 target_language 或 `language_source` unknown/contradictory。 | `finish` | STOP before write，报告 missing target language metadata blocker。 | none 或 `CHANGE_ROOT/state.json` blocker/decision fields only through helper。 | 长期 knowledge、archive、finish apply、产品代码。 | unknown language fail closed；不得猜测 existing/new target 语言。 |
| `finish-english-flow-regression` | Contract `output_language: en`，用户输入 `accept`，targets metadata all en。 | `finish` | 保持 canonical English machine protocol，human prose English，fresh accept 后按 finish packet apply。 | packet 列明 knowledge/archive/index targets 与 `CHANGE_ROOT/evidence/finish-apply.json`、可选 `CHANGE_ROOT/evidence/finish-apply.md`。 | 未列明 target、产品代码、localized machine tokens。 | 英文流程不退化；decision headings English；canonical FINISH_DECISIONS only English values。 |
| `finish-cross-session-success` | `/nuclio:work` 已在旧 Session 写 `CHANGE_ROOT/completion.md/json`、`CHANGE_ROOT/decision.md/json`、`CHANGE_ROOT/finish-plan.json`，新 Session `/nuclio:finish` 读取磁盘。 | `finish` | 依次 inspect、next-action、finish-readiness；ready=true 后展示 bound `decision_sha256`、`finish_plan_sha256`、`decision_state_version` 并请求 exact token。 | fresh `accept` 后仅写 finish packet targets、`CHANGE_ROOT/evidence/finish-apply.json`、可选 `CHANGE_ROOT/evidence/finish-apply.md` 和 helper state archive。 | 产品代码、未列明 target、fresh accept 前 knowledge/index/archive/journal。 | 不依赖聊天历史；五文件 handoff 是跨 Session authority；packet→apply/read-back→record-finish-apply→archived 顺序成立。 |
| `finish-missing-plan-fail-closed` | `completion.md/json` 与 `decision.md/json` 存在但 `CHANGE_ROOT/finish-plan.json` 缺失。 | `finish` | STOP，报告 helper `MISSING_FINISH_HANDOFF` / `rebuild_missing_finish_handoff`，返回 `/nuclio:work` 重建 handoff。 | none。 | accept、finish packet、knowledge/index/archive/journal、产品代码。 | missing finish-plan 不能从 Markdown 或 chat 推断；不得写长期 target。 |
| `finish-stale-decision-fail-closed` | `decision.json` 的 `decision_sha256` 或 `decision_state_version` 与 state/readiness 不一致。 | `finish` | STOP/HALT，报告 `STALE_DECISION`，要求 rebuild canonical handoff或人工处理。 | none。 | accept、finish packet、knowledge/index/archive/journal。 | stale decision 不能被 fresh accept 覆盖。 |
| `finish-markdown-as-json-rejected` | Controller 将 `decision.md` 或 `finish-apply.md` 传给 `--decision-json` / `--journal-json`。 | `finish` | helper 返回 `INVALID_JSON_ARGUMENT` 或 `INVALID_FINISH_JOURNAL` 并 STOP。 | none。 | packet derivation、record-finish-apply、knowledge/index/archive。 | 所有 `--*-json` 只传 `.json`；Markdown 仅为 prose 展示层。 |
| `finish-changes-index-group-positive` | `finish-plan.json` 将 `.dev-docs/changes/index.md` 放入 `index_targets`，target metadata 完整。 | `finish` | fresh accept 后按 packet 顺序更新 changes index 并 journal/read-back。 | `.dev-docs/changes/index.md`、`CHANGE_ROOT/evidence/finish-apply.json`。 | 将 changes index 放入 knowledge_targets 或 archive_targets。 | `.dev-docs/changes/index.md` 是受控 `index_targets`；不是 active change evidence。 |
| `finish-changes-index-wrong-group-rejected` | `finish-plan.json` 将 `.dev-docs/changes/index.md` 放入 `knowledge_targets`。 | `finish` | helper 返回 `KNOWLEDGE_TARGET_OVERREACH` 并 STOP。 | none。 | changes index write、knowledge/archive、finish apply。 | target classification 越权 fail closed。 |
| `finish-target-before-drift-rejected` | fresh accept 前 `.dev-docs/knowledge/...` 当前 bytes 与 `before_sha256` 不同。 | `finish` | STOP/HALT，报告 `STALE_TARGET`，不得写任何 target。 | none。 | 覆盖 drift target、archive、journal、产品代码。 | target before drift 必须重新生成 handoff/decision。 |
| `finish-journal-after-mismatch-rejected` | `finish-apply.json` 的 `after_sha256` 与 actual target bytes 不一致。 | `finish` | `validate-finish-apply` 返回 `STALE_TARGET`，不得 record-finish-apply。 | none 或保留未验证 evidence 供人工处理。 | archived transition、claim complete。 | read-back actual after hash 是 archive authority。 |

## Legacy migration 场景

| case_id | input | owner_skill | expected_next_action | allowed_writes | forbidden_writes | assertions |
| --- | --- | --- | --- | --- | --- | --- |
| `migration-complete-preview` | detect 找到 legacy `brief.md`、`spec.md`、`design.md`、`plan.yaml`、context manifests、state 与 evidence，字段足以映射。 | `init` | 只读 preview 输出逐字段映射、target `CHANGE_ROOT/contract.yaml`、`CHANGE_ROOT/context.jsonl`、`CHANGE_ROOT/state.json`、apply plan 与 blockers 空列表；STOP before work。 | none。 | 目标 CHANGE_ROOT artifacts、产品代码、legacy files。 | preview 默认只读；不把 legacy artifact existence 当 approval。 |
| `migration-incomplete-authority` | legacy inputs 缺 ownership、validation 或 approval identity。 | `init` | preview 输出字段级 blocker，拒绝 partial conversion；STOP before work。 | none 或 blocker artifact。 | 部分 target authority、产品代码。 | 缺 authority 字段时不得生成部分 Contract 或 state。 |
| `migration-apply-explicit-opt-in` | 用户对当前 preview hash 给出 explicit opt-in。 | `init` | 重新 detect/preview/validate，原子写 selected `TARGET_CHANGE_ROOT` 新 artifacts，不覆盖 legacy；STOP before work。 | selected `TARGET_CHANGE_ROOT/contract.yaml`、`TARGET_CHANGE_ROOT/context.jsonl`、`TARGET_CHANGE_ROOT/state.json`、`TARGET_CHANGE_ROOT/research/`、migration evidence under target evidence directory。 | legacy files、产品代码、未列明 targets。 | apply 必须 source hash fresh、完整 validate、target non-overwrite；TARGET_CHANGE_ROOT 等价于 CHANGE_ROOT。 |
| `migration-apply-source-changed` | preview 后 source hash 改变。 | `init` | STOP，要求重新 preview。 | none 或 blocker artifact。 | 写 target artifacts、产品代码。 | opt-in 绑定旧 preview hash，不能 silent partial conversion。 |

## 质量基线场景

这些 case 只把旧六阶段作为只读 baseline 对比；不得调用或修改旧插件，不得把旧名称作为 Nuclio canonical lifecycle。

| case_id | input | owner_skill | expected_next_action | allowed_writes | forbidden_writes | assertions |
| --- | --- | --- | --- | --- | --- | --- |
| `baseline-user-entry-count` | 只读比较旧 baseline 的 `project-init`、`brief`、`design`、`implement`、`verify`、`fold` 入口与新 workbench 入口。 | `work` | 报告新 canonical lifecycle 只有 `init`、`work`、`finish`，并说明旧名称仅为 baseline。 | none。 | 旧插件路径、marketplace、产品代码。 | 不把 baseline 名称写入新 canonical path；用户入口更少且 Gate 更清晰。 |
| `baseline-gate-coverage` | 只读比较旧 baseline Gate 与新 Contract Gate、Finish Gate。 | `work` | 断言新 workbench 覆盖 product mutation 前 approval 与 finish apply 前 approval。 | none。 | 旧插件路径、产品代码。 | artifact existence != approval；freshness 绑定 hash/fingerprint/state version。 |
| `baseline-review-file-count` | 只读比较旧 baseline 审查需要读取的文件数与新 packet/context bounded 读取。 | `work` | 断言 reviewer/completion critic 只消费 packet、bounded context、diff、schema 与 evidence。 | none。 | 宽泛 all docs/all source、旧插件路径。 | prompt progressive disclosure 减少 reviewer 必读面。 |
| `baseline-authority-coverage` | 只读比较旧 baseline authority 覆盖与新 helper deterministic validation。 | `work` | 断言 helper 覆盖 schema、hash、ownership、state transition、dirty/fingerprint 与 evidence identity。 | none。 | 旧插件路径、产品代码。 | agent claim 不能跳转；helper next action 是唯一路由 authority。 |
| `baseline-progressive-disclosure` | 只读比较旧 baseline 长 prompt 与新 references 分层。 | `finish` | 断言 skill body 只路由到 references，稳定逻辑进入 scripts。 | none。 | 嵌套 reference Markdown、旧插件路径。 | 内容 >100 行有 Contents；references 保持一层深。 |

## 全局断言

所有 eval case 都必须满足：

- Canonical lifecycle 仅为 `init`、`work`、`finish`。
- Active change authority 必须位于 `CHANGE_ROOT=.dev-docs/changes/<change-id>`。
- Project-level `.dev-docs/` 只保留 index、knowledge 和 changes/index。
- Product mutation 前必须有 fresh Contract approval。
- 长期 knowledge、journal、archive 前必须有 fresh Finish approval。
- `mutation_targets` 是唯一写授权。
- helper `next action` 是唯一路由 authority。
- Controller 不直接 patch 产品。
- Implementer/fixer 只能写 packet ownership 中的写路径。
- Reviewer/completion critic 只读且不能补授权。
- 同 owner 的 task/final/validation blocking finding 共享 `maximum=2` 修复预算。
- Scope drift、mutation overreach、stale context、validation failure、no-progress、budget exhausted、cross-owner 与 requirement drift 必须 STOP/HALT。
- Migration 默认只读 preview；apply 必须 explicit opt-in、完整 validate、原子写入、不覆盖 legacy、不改产品代码。
- Grill recommendation-first、严格一次一问、复杂 change 最多 5 个必要问题。
- Contract-bound `output_language` 必须写入 Contract、传播到 worker/reviewer/fixer/completion/finish packet，并控制 maintainer-facing prose；agent 不得自行从 chat/history 推断语言。
- `decision.md` 四个 top-level headings 固定为 `Completion Verdict`、`Remaining Risks`、`Knowledge Proposal`、`Archive Decision`；section body 使用 `output_language`。
- Finish target language metadata 必须区分 existing/new/unknown；existing 保持目标既有语言，new 使用 Contract-bound `output_language`，unknown 必须 STOP。
- Machine fields、status enum、helper actions、schema keys、hash、path、command、raw output 与 canonical decision values 保持 English/original。
- Finish 只接受 exact `accept`、`request_changes`、`defer`、`reject` 及 helper 定义中文 aliases `同意`、`要求修改`、`暂缓`、`拒绝`；模糊答复和 `继续` 不能推断 accept。
