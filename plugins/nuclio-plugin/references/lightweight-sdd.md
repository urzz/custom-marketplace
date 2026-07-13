# Nucl.io Lightweight SDD Protocol

## Contents
- [Purpose and Authority](#purpose-and-authority)
- [Preconditions](#preconditions)
- [Pre-Flight](#pre-flight)
- [Eligibility and Per-Task Loop](#eligibility-and-per-task-loop)
- [Worker and Reviewer Contracts](#worker-and-reviewer-contracts)
- [Completion and Git Scope](#completion-and-git-scope)
- [Stop Conditions](#stop-conditions)
- [Explicit Exclusions](#explicit-exclusions)
- [Dispatch Templates](#dispatch-templates)

## Purpose and Authority

本协议摘要 Nucl.io Implement 的 bounded lightweight SDD orchestration：Controller顺序调度 fresh implementer、authoritative validation、fresh reviewer及最多两轮fixer/re-review；单Task也必须委派和review，同一working tree不得并行mutation。

本文件不复制易漂移的ownership、contract identity、snapshot record/hash、fingerprint、Design revision closure或state transition算法。以下文件是authority：

```text
plugins/nuclio-plugin/references/protocol.md          # state/evidence/ownership/snapshot/fingerprint/transition
plugins/nuclio-plugin/references/context-manifest.md  # bounded context/read/JIT loading
```

`task-helper.py validate-change`是canonical `task_contract`与derived `ownership_table` producer；persisted authority是 `state.implementation.approved_task_contract`。Worker、reviewer与本摘要都不得重算或改变authority。

## Preconditions

进入或恢复Implement必须走互斥分支：当前轮explicit Design approval且state尚无persisted approved contract时，Controller **MUST**归类为initial approval candidate；不得重复请求同一Design approval，不得仅因approved contract尚未persisted、工具尚未执行或处于无tools/模拟trajectory环境而STOP或删除entry路径。Approved resume/re-entry/dispatch必须先有persisted Gate与approved contract并精确匹配current helper contract。两者都要求current change唯一、`state.json`可解析、Plan和两个context manifests存在、Git HEAD可解析、dirty ownership可闭合且每个Task可形成bounded brief。

Artifact existence、provisional continuation或static validation PASS不等于Gate approval。

## Pre-Flight

Preflight严格分为“全程只读/内存候选”与“唯一transition”两段：

1. Phase 1只执行`state-helper.py inspect-state`、`check-gate --gate design`与`task-helper.py validate-change --change <change-dir>`，读取helper contract/topology并识别一个互斥分支；不得写Gate、contract、phase/status或entry：
   - **Initial approval candidate：** 当前轮explicit Design approval且state尚无persisted approved contract时必须选择此分支；helper contract只作candidate reconciliation，不预先要求persisted contract。不得再次请求同一approval，不得仅因contract尚不存在或工具尚未执行而STOP。
   - **Approved resume/re-entry/dispatch：** persisted Gate与approved contract必须存在且well-formed，并与helper current完整contract identity精确一致；缺失、malformed或drift立即STOP回Design。
2. Phase 2在任何写入前完成Git status、dirty ownership classification、immutable approved-control-plane map、preexisting Git-status/content fingerprints、canonical Task defaults、overlap/control-path检查、entry HEAD/base candidate、snapshot refs及blocked/resolved/manual/revision reconciliation。Handoff chain只由dependency topology与explicit Plan edges`{path,from_task,to_task}`派生；snapshot`incoming_edge`只用`{path,from,to}`。
3. Dirty、ownership、fingerprint、topology或reconciliation任一失败即STOP，且`state.json`/Design Gate bytes保持Phase 1开始时原样（Design pending、未entry）；不得stash/reset/clean，也不得写blocked/entry state来记录该preflight失败。
4. 全部只读/内存验证成功后，才执行本次首次且唯一的canonical transition；Phase 1/Phase 2不存在第二次entry。路径保持条件式：preflight成功进入唯一transition，真实preflight失败才STOP：
   - Initial candidate使用现有approval-enabled canonical merge transition（`merge-state --allow-approval`只作为recursive preserve/merge写边界），在同一patch持久化Gate、完整approved control plane、helper完整normalized approved contract，以及Protocol真实initial categories：phase/status、首次base/head、dirty/preexisting fingerprints、Task defaults、current pointer与active state。
   - Resume/re-entry执行一次对应的非approval resume transition，只写当前transition所需字段，禁止approval并preserve base、approved contract/control plane、preexisting与snapshot history。
   - 无tools/模拟trajectory必须描述上述待执行成功分支及post-write exact check，不能声称已经执行，也不能把“工具尚未执行”改写成协议禁止entry。
5. Transition后立即重新inspect/check/validate，精确核对branch identity、state fields与current/persisted contract；写入、重读或exact check任一失败即STOP，无dispatch/product mutation。

Design contract revision只引用Protocol/Task3流程：冻结artifacts并`validate-change` → `validate-design-revision`只读preflight → 展示summary并STOP等待用户explicit approval → 相同参数执行`approve-design-revision --allow-approval`。Revision approval由Design流程写完；Implement只按approved resume/re-entry消费persisted结果，不能自行approval，也不能混入initial candidate。Task2 helper负责affected current refs invalidation与legacy context-only隔离；历史snapshot files保留。

## Eligibility and Per-Task Loop

1. 新dispatch的基础eligibility是Task pending且所有dependencies completed；helper Plan order只作tie-break。已persisted tuple但尚无worker产出的`in_progress` Task按步骤5的resume checkpoint处理。
2. Controller从persisted approved contract切出当前Task的`approved_ownership_slice`，包含targets、Plan ownership handoffs `{path,from_task,to_task}`与helper ownership row派生的per-path terminal final owner；不得传完整ownership table。
3. Eligibility阶段对每条incoming Plan edge只经上游persisted completion ref验证upstream completed、completion ref/record/evidence/lineage与当前live bytes，构造pending incoming inputs；不得在此阶段生成downstream dependency record/ref。
4. 运行`extract-task`到固定`evidence/tasks/<task-id>/task-brief.md`并计算brief hash。新dispatch先持久并重读downstream `status=in_progress,attempt=previous+1,fix_cycle=0,review_cycle=0`及完整dispatch tuple。
5. Controller随后按已persisted tuple生成或幂等验证每path dependency snapshot，使用snapshot edge `{path,from,to}`与helper-derived terminal final owner；record全部成功后通过合法preserve/merge transition完整替换current refs，并重读验证filename/record/hash/tuple/parent/edge。任一record/ref写入或验证失败都STOP且不dispatch；Task保持`in_progress`、未worker dispatch。Resume以同tuple的current refs加固定worker evidence/report是否存在匹配tuple产出判定checkpoint：缺失/部分refs且无匹配worker产出时补齐同tuple snapshots，**不得增加attempt**；存在匹配worker产出则不重复dispatch；含糊即STOP。
6. Current refs闭合后再次读取live bytes并匹配snapshot `path_hash`，通过后才dispatch fresh worker。
7. Worker/fixer后Controller用Git reconciliation构造完整 **actual mutation map**。在review-cycle authoritative validation和reviewer dispatch前，每条actual product mutation必须存在于当前Task approved `mutation_targets`。
8. 未声明path立即append canonical `design_revision` blocker并STOP回Design；不运行authoritative validation、不dispatch reviewer。`files_hint`、acceptance、context/JIT/read、worker解释都不授权mutation，reviewer不能动态批准新path，fixer不能扩大slice。
9. 合法actual mutation map才进入authoritative validation；随后fresh reviewer同时判断spec compliance与code quality。`PRODUCT_FAILURE`或Critical/Important进入同一个最多两轮fix budget；每轮fix后重新执行actual mutation boundary、authoritative validation和fresh re-review。
10. 第二轮仍阻塞时按Protocol manual escalation并STOP。Task-local blocker只排除自身和transitive dependents；独立eligible Tasks可继续。Change-level blocker立即停止整个orchestration。

## Worker and Reviewer Contracts

Worker final status只允许：`DONE`、`DONE_WITH_CONCERNS`、`NEEDS_CONTEXT`、`BLOCKED`。前两者不等于review approval或Task completed。

Reviewer必须fresh，只返回structured spec/code-quality verdict与findings，不写文件、不决定Gate/state/ownership。Reviewer只能核验actual mutations是否已处于既有approved slice；不能补授path。Fixer只修复当前Task既有slice内的blocking failure/findings。

Controller是以下事项的唯一authority：state transitions、actual mutation reconciliation、canonical per-path snapshot生成/验证、current refs、Task completion和global fingerprint。Worker report中的hash只作audit输入。

## Completion and Git Scope

Reviewer clean/PASS后，Controller按Protocol为每个owned path生成completion snapshot。Handoff source保存outgoing lineage parent；downstream completion链接incoming dependency snapshot，并提供fresh acceptance-preservation evidence。合法downstream mutation不得覆盖历史completion snapshots。

Implement completion必须先验证：

- 独占path：current completion ref = live ref = live bytes。
- Handoff path：完整approved chain、每段incoming snapshot与parent lineage、acceptance preservation、历史snapshot不变，以及derived final owner的current completion/live identity与最终bytes一致。
- 每个Task的brief hash、persisted tuple、authoritative validation和fresh reviewer仍fresh。

只有上述per-path checks全部通过，才按Protocol以最终change-wide bytes计算 `global_product_fingerprint` 并持久 `implementation.product_fingerprint`。Global fingerprint证明最终bytes，不替代handoff lineage。

Git scope补充：

- `files_hint`仅navigation hint，既非ownership也非mutation allowlist。
- Context manifests管理只读stable knowledge；JIT/minimal source discovery授权读取，不授权mutation。
- `implementation.changed_files`来自Controller Git reconciliation，排除合法control-plane和unchanged preexisting paths。
- 同一working tree不并行mutation；默认不自动commit。若获授权，commit必须scoped且不得捎带preexisting paths。

## Stop Conditions

- Gate未approved或revision/re-entry未按authority完成。
- `validate-change`失败、current/persisted contract identity mismatch、ownership/handoff topology invalid。
- Dirty ownership不唯一、immutable/preexisting drift。
- Snapshot ref/record/path/hash/lineage invalid，incoming snapshot或final-owner live mismatch。
- Actual mutation超出当前Task approved targets；必须在review前转 `design_revision` blocker。
- Context/manifest invalid、dependency deadlock、coupled graph或无合法eligible Task。
- Agent请求full history、完整repo context、跨slice mutation、并行mutation、worktree、destructive Git或自动commit。
- 两轮产品fixer/re-review耗尽。

## Explicit Exclusions

本MVP不调用完整Superpowers SDD，不写`.superpowers/sdd/progress.md`，不增加第二个change-wide final review，不执行Verify approval/Fold/branch finish/worktree/auto commit，不实现hooks/daemon/MCP/runtime automation，也不向Agent注入完整Plan/history。

## Dispatch Templates

每次Agent call都显式传 `model: sonnet`；只有brief明确 `architecture-heavy` 才用 `opus`。以下是允许的package shape，exact snapshot/identity算法仍只引用Protocol。

### Implementer dispatch

```yaml
subagent_type: nuclio:nuclio-implementer
model: sonnet
prompt_inputs:
  task_brief: .dev-docs/changes/<change-id>/evidence/tasks/<task-id>/task-brief.md
  report_output: .dev-docs/changes/<change-id>/evidence/tasks/<task-id>/implementer.md
  state_tuple: <persisted attempt/fix/review tuple>
  validation_mode: exploratory
  approved_ownership_slice:
    mutation_targets: [<canonical product paths>]
    incoming_handoffs: [{path: <path>, from_task: <upstream>, to_task: <task-id>}]
    outgoing_handoffs: [{path: <path>, from_task: <task-id>, to_task: <downstream>}]
    final_owners: [{path: <path>, final_owner: <helper-derived-terminal-owner>}]
  incoming_handoff_snapshots:
    - path: <path>
      evidence_path: <persisted dependency snapshot ref>
      record_hash: sha256:<hash>
      incoming_edge: {path: <path>, from: <upstream>, to: <task-id>}
  allowed_context: <matching bounded manifest entries and permitted minimal reads>
constraints:
  - mutate only approved_ownership_slice.mutation_targets
  - files_hint and context/read/JIT are non-authoritative for mutation
  - report mutations and evidence; do not compute authoritative snapshot hashes
```

### Reviewer dispatch

```yaml
subagent_type: nuclio:nuclio-task-reviewer
model: sonnet
prompt_inputs:
  task_brief: <fixed task brief path>
  implementer_report: <fixed implementer path>
  validation: <fixed authoritative validation path>
  review_output: <fixed review path>
  state_tuple: <persisted tuple>
  approved_ownership_slice: <same bounded slice>
  incoming_handoff_snapshots: <same validated per-path refs>
  actual_mutation_map: {<approved path>: <sha256-or-deleted>}
  bounded_diff: <controller-produced package path>
constraints:
  - judge spec compliance and code quality within the existing slice
  - do not approve new paths, change ownership/state/Gate, or write files
```

### Fixer dispatch

```yaml
subagent_type: nuclio:nuclio-fixer
model: sonnet
prompt_inputs:
  task_brief: <fixed task brief path>
  validation: <latest authoritative validation path>
  latest_review: <latest review path>
  report_output: <fixed implementer/fix append target>
  state_tuple: <persisted fix tuple>
  approved_ownership_slice: <same bounded slice>
  incoming_handoff_snapshots: <same validated per-path refs>
  blocking_inputs: <bounded validation/review failure package>
constraints:
  - fix only blocking inputs inside approved targets
  - do not broaden ownership; return NEEDS_CONTEXT/BLOCKED when the slice is insufficient
  - after mutation the Controller reruns actual mutation, validation, and fresh review gates
```
