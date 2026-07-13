---
name: implement
disable-model-invocation: true
description: Use when a Nucl.io change has an approved Design and pending Tasks, or when blocked work is resumed after evidence recovery or an approved Design revision/re-entry.
---

# Nucl.io Implement

## Critical Constraints

- 本 Skill 是 native lightweight SDD Controller。主 session 只定位 change、运行 helpers、执行 ownership preflight、计算 authoritative fingerprints、顺序 dispatch、读取并持久化 state/evidence；不得 coding 或 manual product patch。
- Implement readiness必须走互斥分支：若用户当前轮已明确批准Design且state尚无persisted approved contract，Controller **MUST** classify as **initial approval candidate**；**MUST NOT**再次请求同一Design approval，**MUST NOT**仅因persisted approved contract尚不存在而STOP，**MUST NOT**把工具尚未执行、无tools模拟或trajectory输出等同为协议禁止entry。此分支只把只读helper contract作为内存candidate做reconciliation，不预先要求persisted contract，也不得在preflight完成前写Gate/entry；完成全部只读与dirty/ownership/fingerprint preflight后，成功则走本轮唯一approval-enabled initial entry并post-write exact check，真实preflight失败才STOP。**Approved resume/re-entry/dispatch**必须先有well-formed persisted approved contract，并在任何dispatch前把helper current contract与其canonical identity精确比较。Contract drift、ownership overlap、dangling handoff或invalid topology一律在product mutation/dispatch前STOP。
- 在模拟、无tools或eval trajectory环境中，Controller **MUST**把上述条件式initial entry路径保留在`route`/`actions`/`state_writes`/`next path`中：先列出必须完成的只读与dirty preflight，成功分支写唯一approval-enabled initial entry及post-write exact check，失败分支STOP；**MUST NOT**声称已经执行工具或写入，且**MUST NOT**删除该条件式entry路径或改为重复请求同一approval。
- Ownership 只来自 persisted approved contract 的 `mutation_targets`、dependency topology 与 explicit `ownership_handoffs`。`files_hint`、acceptance、context manifest、JIT discovery、read access、worker explanation、validation 或 reviewer verdict都不授权 product mutation。
- 每条 actual product mutation 必须属于当前 Task 的 approved `mutation_targets`。未声明路径必须在 authoritative validation/reviewer 前形成 canonical `design_revision` blocker并 STOP；Reviewer不能补授 ownership，fixer不能扩大 ownership slice。
- Handoff chain 由 dependency topology + explicit edges决定；Plan order只用于多个 dependency-eligible Tasks的稳定 tie-break。Plan handoff schema是 `{path,from_task,to_task}`；snapshot `incoming_edge` schema是 `{path,from,to}`，不得混用。
- Controller生成并验证 canonical per-path completion/dependency/live snapshots及 current refs；worker报告的 hash 不是 authoritative。合法 downstream mutation不得改写历史 snapshots。
- 每个 fresh implementer/fixer只处理一个 Task；单 Task也必须委派并由 fresh reviewer审查。同一 working tree不并行 mutation。无法形成自包含 brief 的 coupled graph必须 STOP回 Design重切片。
- 每次 Agent dispatch显式指定 `subagent_type` 和 `model`：默认 `sonnet`；仅 Task brief明确标记 `architecture-heavy` 时使用 `opus`并报告理由。
- Gate、state、contract revision、snapshot、fingerprint、recovery与 exact transitions以 `references/protocol.md` 为唯一 authority；context loading以 `references/context-manifest.md` 为 authority；编排摘要以 `references/lightweight-sdd.md` 为准。
- 不做 change-wide final review、Verify approval、Fold、branch finish、worktree或自动 commit；不得 stash/reset/clean/强制 checkout。Plan或用户当前轮明确授权时才可 scoped commit，且不得包含 preexisting paths。

## Contents

1. [Workflow Overview](#workflow-overview)
2. [Phase 1: Locate and Validate Current Change](#phase-1-locate-and-validate-current-change)
3. [Phase 2: Ownership and Resume Preflight](#phase-2-ownership-and-resume-preflight)
4. [Phase 3: Select an Eligible Task](#phase-3-select-an-eligible-task)
5. [Phase 4: Execute Per-Task Loop](#phase-4-execute-per-task-loop)
6. [Phase 5: Complete Implement State](#phase-5-complete-implement-state)
7. [Phase 6: Implementation Report](#phase-6-implementation-report)
8. [Stop Conditions](#stop-conditions)
9. [Behavior Verification](#behavior-verification)

## Workflow Overview

采用 Coordinator routing + per-task Generator-Critic：先验证 Design Gate、current canonical contract、Git ownership与snapshot freshness，再按 dependency topology选择 Task，依次执行 fresh implementer → actual mutation boundary → authoritative validation → fresh reviewer → bounded fixer/re-review。Controller是唯一 state、ownership、snapshot与evidence persistence authority；worker/reviewer不决定 Gate、Task completion或 mutation权限。

每次 state写入必须 recursive preserve/merge，只 patch Protocol transition要求字段并保留 unknown keys、metadata、artifacts、evidence、unrelated gates/Tasks。不得回写 `plan.yaml` Task status。

## Phase 1: Locate and Validate Current Change

1. 从 `.dev-docs/changes/index.md` 或用户给出的唯一 change定位 `<current-change>`；不得从聊天历史猜测。确认 `state.json`、`plan.yaml`、两个 context manifests及 Task evidence roots可定位。
2. 每次 enter/resume/re-entry先执行只读检查：

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-helper.py" inspect-state --change "<current-change>"
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-helper.py" check-gate --state "<current-change>/state.json" --gate design
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/task-helper.py" validate-change --change "<current-change>"
   ```

   Initial approval candidate中`check-gate`可报告尚未approved；这不等于resume，也不得先以persisted contract缺失阻断。若当前轮已有明确Design approval且无persisted approved contract，Controller **MUST**继续做initial candidate preflight；**NEVER**再次请求同一Design approval，**NEVER**仅因尚未执行工具/尚未写contract就把entry判为协议禁止。
3. 从validate output只读获取完整`task_order`、`task_contract`、`ownership_table`，按可观察state识别且只识别一个分支：
   - **Initial approval candidate：** 用户当前轮明确批准Design，且state尚无persisted approved contract时，Controller **MUST**选择此分支。将helper验证的current contract保留为内存candidate，供Phase 2 reconciliation；此时不要求persisted contract预先存在，也**禁止**写`gates.design`、approved contract、phase/status或任何entry字段。不得再次请求同一Design approval，不得仅因persisted approved contract尚不存在而STOP。
   - **Approved resume/re-entry：** persisted `gates.design=approved`与`state.implementation.approved_task_contract`必须已存在且well-formed；将helper current完整contract与persisted contract canonical identity精确比较。缺失、malformed或drift均STOP回Design，普通resume不得从current Plan、prose、`files_hint`或reports重建或覆盖contract。
4. Phase 1仅执行inspect/check/validate与分支识别；不存在entry、Gate/contract持久化或第二次entry。Artifact existence、provisional/ambiguous continuation都不构成initial candidate或approved resume。
5. Revision approval已由Design流程写完，Implement只按approved resume/re-entry消费其persisted结果；不得把revision approval混入initial candidate，也不得在Implement自行approval。Design revision选择轮仍按Protocol持久化选择与draft/pending transition后立即STOP回`/nuclio:design`。

**Exit condition：** change唯一；initial candidate已获得只读validated candidate contract，或resume/re-entry已有完整persisted approval且current/persisted contract identity一致；Phase 1未执行Implement entry且没有dispatch或产品mutation。

## Phase 2: Ownership and Resume Preflight

1. 记录preflight HEAD并只读分类staged/unstaged/untracked paths：immutable approved control-plane、workflow-owned mutable control-plane、workflow-owned product mutations、preexisting dirt；建立immutable approved control-plane candidate map与preexisting Git-status/content fingerprints。Unknown、overlap、归属不唯一、未获授权dirty或drift一律STOP。若dirty preflight失败，`state.json`（含Design Gate）的bytes必须与Phase 1开始时完全相同，保持Design pending/未entry，不得用blocked/entry merge记录失败。
2. 只在内存按helper `task_order`构造canonical Task defaults与initial patch候选；复核overlap/control paths、entry HEAD/base candidate、complete approved control-plane map、preexisting paths/fingerprints、Task集合/defaults/current pointer及Protocol要求的全部initial字段。Initial candidate不得使用尚不存在的persisted contract作前置条件；其helper contract candidate必须与上述只读候选一起完成reconciliation。若在无tools/模拟环境输出initial approval / ownership reconciliation trajectory，且case facts已给出helper `ownership_table`，`actions`/摘要 **MUST**显式报告对应helper-derived ownership row（例如共享path的`owners=[T1,T4]`与`final_owner=T4`），并同时说明Plan handoff edge `{path,from_task,to_task}` 与后续snapshot `incoming_edge={path,from,to}` 是不同schema；不得把`final_owner`写回Plan或把两个edge schema混用。
3. 对approved resume/re-entry的persisted current snapshot refs执行Protocol防御性检查：
   - `completion_snapshot_refs`、`live_snapshot_refs`逐path canonical order；
   - `dependency_handoff_snapshot_refs`按`(path,from,to)`canonical order；
   - refs必须指向固定Task snapshots目录并匹配kind/task/path/path_id/record_hash identity；
   - dependency ref的`incoming_edge`只接受`{path,from,to}`；legacy`{from_task,to_task}`隔离并拒绝。
4. 所有blocked/resolved evidence、manual repair authorization与Design revision reconciliation严格引用Protocol；applied authorization路由优先于普通resume，不得覆盖`current_task`。Revision approval结果只按resume验证；affected refs/evidence invalidation由Task2 helper完成，Implement不近似清理。
5. 在任何写入前最后一次运行`validate-change`：initial candidate与内存candidate identity精确匹配；resume/re-entry与persisted approved contract identity精确匹配。普通resume不得刷新`base_sha`、approved contract、approved control-plane map、preexisting snapshots或历史snapshot files。
6. 步骤1–5全部成功后才执行本次首次且唯一的canonical transition；Phase 1/Phase 2此前不存在第二次entry。路径是条件式且不可删除：完成全部只读/dirty preflight并成功，则走当前轮唯一approval-enabled initial entry或对应resume transition；真实preflight失败才STOP。
   - **Initial candidate：** Controller使用现有approval-enabled canonical merge transition（当前helper即`merge-state --allow-approval`的recursive preserve/merge边界），一次patch同时持久化`gates.design=approved`、完整`implementation.approved_control_plane`、helper完整normalized `implementation.approved_task_contract`、`phase=implement`、`status=in_progress`、首次`base_sha`/`head_sha`、`started_clean`、`preexisting_paths`/`preexisting_fingerprints`、canonical Task defaults、`current_task=null`、`active=true`及Protocol要求的其他既有initial fields；不得虚构专用entry命令或字段。若在无tools/模拟环境输出trajectory，`state_writes`/`actions` **MUST**描述此成功分支的待执行approval-enabled write与post-write exact check，但不得声称已执行。
   - **Approved resume/re-entry：** 执行一次对应的非approval canonical resume transition，只写Protocol当前transition所需字段并preserve initial authority；禁止`--allow-approval`，禁止重写initial snapshots/base/contract。
7. Transition成功后立即重新`inspect-state`、`check-gate`、`validate-change`，并对branch identity、phase/status/current、initial/resume字段与current/persisted contract做exact check；任一写入、重读或exact check失败即STOP，不得dispatch或product mutation。

**Exit condition：** Git dirty ownership、immutable/control/preexisting fingerprints、Task defaults、overlap/control paths、base/reconciliation与contract identity先以只读/内存方式闭合；随后唯一transition成功且post-write重读验证精确通过。

## Phase 3: Select an Eligible Task

1. 每次selection/dispatch前重新运行 `validate-change`并比较persisted approved contract identity。
2. 基础eligibility：新dispatch要求`state.tasks.<id>.status=pending`且所有`depends_on`已`completed`；resume checkpoint允许该Task已是`in_progress`且尚无worker-dispatch evidence。Plan order仅对同时eligible Tasks做稳定tie-break。
3. 从persisted approved contract切出当前Task的`approved_ownership_slice`；其语义与extracted brief的`Approved Ownership Slice`一致：`mutation_targets`、incoming/outgoing **Plan ownership handoffs** `{path,from_task,to_task}`、helper ownership rows派生的per-path terminal final owners。不得传完整ownership table，也不得把Plan edge schema混作snapshot edge schema。
4. Eligibility阶段对每条incoming Plan edge只构造pending incoming snapshot inputs：
   - 只通过上游persisted completion snapshot ref定位record，不扫描目录、不按mtime或文件名猜测；
   - 验证上游Task已completed、completion ref/record/state tuple/path/path_id/hash、completion evidence、parent lineage与approved edge；
   - 读取当前live bytes并要求其hash等于上游completion `path_hash`；
   - 保留用于后续record的path、helper-derived terminal `final_owner`、snapshot `incoming_edge={path,from,to}`与parent record identity，但此阶段**不得**写downstream dependency record或current ref。
5. Task只有在dependencies及全部pending incoming inputs合法且初次live-byte检查通过时才eligible。Mismatch视为未归属/外部mutation，change-level STOP，不得持久dispatch tuple或dispatch worker。
6. blocked Task只排除自身与transitive dependents；独立eligible Tasks可继续。无eligible但仍有未完成Tasks、coupled graph或dependency deadlock则STOP回Design。

## Phase 4: Execute Per-Task Loop

### 4.1 Extract, persist snapshots, dispatch

1. 固定evidence路径并提取brief：

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/task-helper.py" extract-task --change "<current-change>" --task "<task-id>" --output "<current-change>/evidence/tasks/<task-id>/task-brief.md"
   ```

2. 计算brief bytes hash，复核required context、immutable/preexisting fingerprints、approved slice与Phase 3的pending incoming inputs。Task-only context failure走canonical Task blocker；shared/change-wide或fingerprint failure全局STOP。
3. 按Protocol分支持久dispatch checkpoint：
   - **新dispatch：** 先通过现有preserve/merge boundary一次持久化Task `status=in_progress`、`attempt=previous+1`、`fix_cycle=0`、`review_cycle=0`、`current_task`及Protocol要求的完整dispatch tuple；merge成功并重读精确核对后才继续。
   - **未派worker的resume：** 若Task已`in_progress`，且state current dependency refs为空或只部分覆盖该已persisted tuple，同时固定worker evidence/report不存在、为空或不含匹配该tuple的dispatch后产出，则这是“tuple已持久化但worker尚未dispatch”的checkpoint；必须复用同一attempt/review tuple，**不得再次increment attempt**。若存在匹配tuple的worker evidence，则按普通in-progress resume处理，不重复dispatch；证据状态含糊即STOP。
4. 仅使用步骤3已持久化并重读确认的tuple，由Controller为每个pending incoming input幂等重建或验证per-path dependency snapshot：filename、record的`attempt/review_cycle`、path/path_id/hash、helper-derived terminal `final_owner`、snapshot `incoming_edge={path,from,to}`及parent identity必须全部匹配Protocol。已存在的同tuple record只有bytes与重算hash完全一致才可复用；不得覆盖历史record。
5. 所有record完整写入并重算成功后，Controller通过一次合法preserve/merge transition完整替换该Task的current `dependency_handoff_snapshot_refs`数组，随后重读每个ref并复核filename/record/hash/tuple/parent/edge。任一record或ref写入、merge、重读或验证失败都立即STOP且**不得dispatch worker**；Task保持`in_progress`但未worker dispatch，下一次resume按步骤3的checkpoint规则复用同一tuple并幂等补齐/验证，绝不新增attempt。
6. Snapshot refs全部成功后，再次读取每个path的当前live bytes并与dependency snapshot `path_hash`精确比较；任何漂移立即STOP且不得dispatch。
7. 仅在步骤3–6全部闭合后dispatch fresh `nuclio:nuclio-implementer`，显式model。Package必须包含：
   - `task_brief`及hash、reports、persisted `state_tuple`、`validation_mode=exploratory`；
   - matching bounded `allowed_context`；
   - `approved_ownership_slice`；
   - `incoming_handoff_snapshots`（per-path refs/record identities）；
   - evidence binding与dependency output fingerprints。

   不得传完整Plan、完整ownership table、full history或让worker计算authoritative snapshot hash。Worker只能在approved `mutation_targets`内修改；`files_hint`仅导航。

### 4.2 Actual mutation boundary

1. Worker/fixer返回后，Controller用Git reconciliation与reports构造当前Task完整 **actual mutation map**（`path→sha256|deleted`），排除合法control-plane evidence变化并保护preexisting paths。
2. 在任何 authoritative validation、review-cycle PASS判断或reviewer dispatch前，将每条actual product mutation与persisted approved contract中当前Task的 `mutation_targets`逐项比较。
3. 若存在未声明路径：立即停止后续mutation；向固定Task evidence append canonical `design_revision` blocker（记录path、candidate Task/owner及需修订的contract fields）；执行Protocol canonical blocked transition；STOP回Design。不得运行authoritative validation、不得dispatch reviewer、不得以acceptance必要、`files_hint`、context/JIT/read、worker解释或reviewer判断继续。在无tools/模拟trajectory中，若case facts已提供actual mutation boundary判定输入（当前Task、未声明path、approved slice/contract mismatch），`actions`/`state_writes` **MUST**把 canonical blocker evidence append 与 canonical blocked transition 表达为STOP前当前trajectory必须形成的transition；同时不得声称物理append/merge已经执行，`state_non_writes`只能列禁止的非blocker写入（validation、reviewer dispatch、product继续修改、非canonical state patch等），不得否定canonical blocker formation，也不得要求在revised contract尚不存在时猜测exact affected closure、handoff或未来owner。
4. 只有actual mutation map完全落在approved slice内，才持久下一`review_cycle`并计算当前task scope binding。

### 4.3 Authoritative validation, review and fix

1. Controller运行Task exact commands/static branch并append authoritative `validation.md`，或bounded dispatch同一role执行 `validation_mode=authoritative`；必须绑定persisted tuple、brief hash、approved slice、incoming snapshots及actual mutation map。历史/探索结果不能跨cycle拼PASS。
2. Authoritative result产生后dispatch fresh `nuclio:nuclio-task-reviewer`。Reviewer只判断acceptance/spec、code quality与actual mutations是否已落在既有approved slice；不能批准新path、改变ownership/state/Gate或写文件。
3. `PRODUCT_FAILURE`或任一Critical/Important进入同一Protocol fix budget。每次fixer前先持久`fix_cycle`；fixer收到相同 `approved_ownership_slice`和`incoming_handoff_snapshots`，不得扩大slice。Fixer后重新执行actual mutation boundary → authoritative validation → fresh re-review。最多自动`fix_cycle=1..2`。
4. 第二轮仍阻塞则按Protocol进入manual escalation并立即STOP；额外bounded repair必须有fixed authorization record与new attempt transition。若用户选择修改Design/Plan/acceptance/scope/context，只走Design revision选择轮并STOP，不在Implement自行批准。

### 4.4 Completion snapshots and Task transition

1. 只有implementer status合格、actual mutation map合法、当前tuple authoritative validation PASS/static PASS、fresh reviewer双PASS且无Critical/Important时，Controller才可创建completion evidence。
2. Controller为当前Task每个owned path生成/验证canonical per-path completion snapshot，并更新对应current completion/live refs；worker hash只能作audit输入。
3. 若当前Task是handoff source，completion snapshot成为outgoing lineage parent，供下游per-path dependency snapshot引用；不得覆盖或重算历史record。
4. 若当前Task是handoff downstream owner，其completion snapshot必须parent-chain回incoming snapshot，并携带Protocol要求的fresh `acceptance_preservation_refs`，证明上游接口/行为与相关acceptance在下游mutation后仍成立。
5. 非handoff owner完成时，completion/live/current bytes必须一致。Handoff中间owner完成时保存当时bytes；未来合法下游变化不使其历史completion失效。Terminal `final_owner`承担最终live freshness与最终completion/live identity。
6. Snapshot、validation与review均闭合后，才执行canonical Task complete transition。Canonical blocked或manual escalation使用各自互斥transition；只有completed/blocked可重算下一Task eligibility。

## Phase 5: Complete Implement State

只有 `current_task=null` 且Plan/state Task集合精确闭合时：

1. 按helper `task_order`构造去重 `completed_ids`，要求Plan IDs、state completed set与`implementation.completed_tasks`精确相等；拒绝duplicate/unknown。
2. 对每个Task重算current `task_scope_fingerprint`并匹配brief hash、persisted tuple、authoritative validation与fresh reviewer PASS。
3. 对每个独占path验证current owner completion ref、live ref与live bytes精确一致。
4. 对每个handoff path验证：完整approved chain；每段incoming dependency snapshot与当时live bytes/parent lineage；fresh acceptance preservation；历史completion snapshots未变；derived `final_owner` current live ref匹配当前bytes，且final-owner current completion/live identity一致。不得要求历史owner snapshot等于最终bytes，也不得忽略任何fingerprint mismatch。
5. 只有per-path freshness全部成立后，才以首次`base_sha`和完整最终change-wide product bytes按Protocol计算 `global_product_fingerprint`。它证明最终bytes，不替代handoff lineage。
6. 一次canonical Implement complete merge写 `phase=implement,status=completed,current_task=null`、完整completed Tasks/changed files/current HEAD与 `implementation.product_fingerprint=<global_product_fingerprint>`；merge后重新inspect并逐项核对。

**Exit condition：** 独占freshness、handoff lineage/final-owner freshness、Task evidence和global fingerprint全部闭合；否则Implement未完成且不得建议Verify。

## Phase 6: Implementation Report

输出current change；selected/completed/blocked Tasks；attempt/fix/review摘要；ownership/handoff completion摘要；完整changed files；`base_sha..head_sha`与product fingerprint；state update；concerns；architecture-heavy model理由；下一步 `/nuclio:verify`。

明确声明：未做change-wide review、未批准Verify Gate、未Fold、未finish branch、未自动commit。

## Stop Conditions

- Gate missing/pending/ambiguous且不满足initial candidate。若当前轮Design approval明确且无persisted approved contract，必须先按initial candidate完成只读/dirty preflight，成功后走唯一approval-enabled entry；不得再次请求同一approval或因contract尚未persisted而STOP。Revision approval/re-entry未由Design按Task3 exact flow完成时仍STOP，且不得混入initial approval。
- `validate-change`失败；resume/re-entry/dispatch的persisted approved contract缺失/invalid；unique initial/resume transition写入或post-write重读exact check失败；contract drift；Task IDs/topology/ownership/handoff invalid。
- 非Git repo、HEAD不可解析、ownership overlap/unknown、immutable或preexisting fingerprint drift；preflight失败时Gate/state bytes必须保持原样且未entry。
- Snapshot ref/record/filename/path_id/hash/parent lineage/incoming edge invalid；incoming snapshot与live bytes不匹配；final-owner freshness mismatch。
- Actual product mutation不在当前Task approved `mutation_targets`；必须形成 `design_revision` blocker，不能交reviewer补授。
- Shared context/manifest invalid、dependency deadlock、coupled graph、无合法eligible Task。
- Agent请求full context、跨Task/ownership slice、并行mutation、destructive Git、worktree或自动commit。
- 两轮产品fixer/re-review耗尽后的manual escalation。

## Behavior Verification

RED baseline：缺少persisted contract identity preflight、incoming snapshots与actual mutation hard boundary；mutation authorization被错误委托给事后review；completion只看Task/global fingerprint而未证明handoff lineage/final-owner freshness。

GREEN markers应覆盖：互斥initial candidate与persisted-approved resume/dispatch分支；当前轮Design approval明确且无persisted approved contract时MUST classify initial candidate、NEVER重复请求同一approval、NEVER因contract尚未persisted或tools未执行而STOP；initial candidate在Phase 1/Phase 2不写入；dirty/ownership/fingerprint preflight先于唯一initial/resume transition且失败保持Gate/state bytes原样；initial同一approval-enabled transition持久化完整initial categories，resume transition不approval；无tools/模拟trajectory保留条件式entry成功/失败路径且不声称已执行；transition后重读并exact check；revision reapproval与initial approval区分；eligibility只构造pending incoming inputs；先持久tuple、后写snapshot record/ref；写入失败STOP且无worker；未派workerresume复用tuple且不增加attempt；snapshot refs成功后再次live-byte复核；dispatch package；authoritative validation前actual mutation map；completion snapshots/handoff lineage；独占与terminal final-owner freshness；global fingerprint最后计算。

REFACTOR反向检查：不存在worker/reviewer决定ownership、动态path事后放行、fixer扩大slice、Plan order推导chain、worker hash成为authority、覆盖历史snapshot或忽略fingerprint mismatch的捷径。

Task7/8执行实际5+次LLM eval；本Task只做静态/wording验证，不运行这些eval。
