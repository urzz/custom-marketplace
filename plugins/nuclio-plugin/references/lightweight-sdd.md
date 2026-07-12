# Nucl.io Lightweight SDD Protocol

## Contents
- [Purpose](#purpose)
- [Preconditions](#preconditions)
- [Single vs Multi-Task Routing](#single-vs-multi-task-routing)
- [Pre-Flight](#pre-flight)
- [Per-Task Loop](#per-task-loop)
- [Worker Status Contract](#worker-status-contract)
- [Reviewer and Fix Loop](#reviewer-and-fix-loop)
- [State and Evidence Updates](#state-and-evidence-updates)
- [Git Scope](#git-scope)
- [Stop Conditions](#stop-conditions)
- [Explicit Exclusions](#explicit-exclusions)
- [Dispatch Templates](#dispatch-templates)

## Purpose

本协议是 Nucl.io Implement 阶段唯一的原生 lightweight SDD authority。它把已批准 Design 中的 Tasks 交给 bounded subagents，并通过 fresh implementer、validation、fresh reviewer 与最多两轮 fixer/re-review 形成 Generator-Critic 闭环。

它不是完整 Superpowers SDD，也不是通用 multi-agent runtime。Controller 负责顺序编排、持久状态与 evidence 合并；workers 只处理单 Task 的自包含 package。

本文件只定义 bounded worker orchestration，不定义 snapshot 或 transition authority。所有 `task_scope_fingerprint`、`global_product_fingerprint`、`implementation.product_fingerprint` 生命周期、artifact hash 外部 metadata、Design reapproval whole-map replacement、Implement complete evidence 与 Verify/Fold freshness decision points 均只引用 File Protocol，不在此复制第二套规则。状态、evidence、context 与生命周期 transition 分别遵循以下纯路径引用：

```text
plugins/nuclio-plugin/references/protocol.md
plugins/nuclio-plugin/references/context-manifest.md
```

## Preconditions

进入本协议前必须同时满足：

1. 当前 change 已明确定位，且 `state.json` 可解析。
2. Design Gate 已持久为 `approved`，或用户在当前轮给出 explicit Design Gate approval；仅允许 provisional continuation 不满足此前置条件。
3. `plan.yaml` 与两个 context manifests 已存在。
4. Task 1 helpers 可运行。
5. 当前目录位于 Git repository，HEAD 可解析。
6. Dirty worktree 已按 File Protocol fail-closed 处理。
7. 每个 Task 可从 Plan 提取为 bounded、可验证、可回滚的 brief。

任何 artifact existence 都不能代替 Gate approval。

## Single vs Multi-Task Routing

### Single Task

Plan 只有一个 Task 时，采用 single-task bounded path：

- 不建立不必要的并行或额外 orchestration 层。
- 仍必须 dispatch 一个 fresh implementer。
- 实现与 validation 后仍必须 dispatch 一个 fresh reviewer。
- Implementer 不能自审后直接把 Task 标为 completed。

### Multiple Tasks

多个 mostly-independent Tasks 时：

- 按 dependency graph 顺序选择 eligible Task。
- 一次只允许一个 Task 在同一 working tree 进行 mutation。
- 可以提前分析 eligibility，但不得并行 dispatch 两个会修改同一 working tree 的 implementers/fixers。
- 每个 Task 使用独立 brief、evidence package、attempt 和 review loop。

### Coupled Tasks

若 Tasks 高度耦合，以至于任何单 Task brief 都无法自包含 acceptance、allowed context、verification 与 rollback：

- STOP。
- 返回 Design 拆分或重写 Tasks/依赖。
- 不得把多个 Tasks 合并交给一个 worker 绕过 bounded contract。

## Pre-Flight

Controller 在首次 mutation 前按顺序执行：

1. **Design Gate**：用 `state-helper.py check-gate` 检查持久 approval。只有当前轮 explicit Design Gate approval 可替代持久值并进入 Implement；provisional continuation 只能继续完善/审查 Design，不能进入 Implement。当前轮 explicit approval 必须在 Implement entry 通过 `merge-state --allow-approval` 持久写入 `gates.design=approved`；只有 merge 成功后才可 dispatch，不留下 `phase=implement` 与 pending Gate 的组合，也不宣称 helper direct write 具备 filesystem atomicity。
2. **Change validation**：每次 Implement pre-flight 都运行 `task-helper.py validate-change --change <change-dir>`，校验整个 change 的固定输入，包含 `state.json`、Plan、Implement manifest 与 Verify manifest、Task ids 和 dependency graph；失败即 STOP。本轮安全合同不缓存、不跳过，也不在 Tasks 间共享一个已加载 context snapshot。
3. **Dependency graph**：读取 helper 返回的 Plan order，确认 dependency-eligible selection；不得凭聊天记忆重建依赖。
4. **Git repository/HEAD**：确认 Git repo。仅首次 Implement 且任何 product mutation 前将当前 HEAD 初始化为 `implementation.base_sha`；resume/re-entry 不得覆盖。
5. **Dirty ownership**：首次 entry 与 resume 都按 File Protocol 将路径精确归类为 immutable approved control-plane、workflow-owned mutable control-plane、workflow-owned product mutations 或 preexisting dirt。记录 immutable hashes 与 preexisting Git-status/content fingerprints；mutable control-plane 合法变化和四类排除项不进入 product diff/changed_files。分类不唯一、preexisting fingerprint 变化或无法证据归属的产品 overlap 都 STOP。
6. **Initialize `state.tasks`**：按 Plan Task ids 补齐缺失项，安全默认 status=pending/attempts=0。Legacy completed/in_progress/blocked 只存 audit metadata，不参与 eligibility，不得无 snapshot-bound evidence 直接迁移完成；之后不得回写 Plan。
7. **Canonical Task shape**：Task 1 parser 已支持 Design 产物中的 canonical `status`、`files_hint`、`context_refs`，以及 `verification.commands: []` + non-empty `notes`。这些字段必须遵守 helper 的严格 shape；`files_hint` 仍只是 hints。
8. **Implement entry**：调用 File Protocol canonical Implement entry transition；只持久化当前 transition 所需 fields。

Controller 不执行 stash、reset、clean，也不通过自动 commit 制造 checkpoint。

## Per-Task Loop

对每个 Task 严格执行以下顺序：

1. **Select eligible**：只选择自身为 `pending` 且所有 dependencies 已 completed 的下一个 Task；Plan order 用于稳定 tie-break。Blocked Task 只排除自身及 transitive dependents，不阻止无依赖关系的独立 eligible Tasks。
2. **Extract brief and pre-dispatch checks**：将输出固定为 `evidence/tasks/<task-id>/task-brief.md`，运行 `task-helper.py extract-task`；不读取 target content、不修改 state。Controller 计算 brief immutable content hash，逐一检查 matching required targets，并复核 immutable control-plane hashes/preexisting fingerprints。Task-only required target 缺失时，在 attempt 递增前追加 blocker evidence，按 Context Manifest 执行 pre-dispatch Task-local blocked（attempt 保持当前值），继续独立 eligible Tasks；shared/change-wide 缺失、manifest invalid、hash/fingerprint drift 则 change-level STOP。
3. **Merge running state**：只有 pre-dispatch checks 通过才调用 canonical **Task dispatch** transition并递增 attempt。目的只是持久化 selected Task、attempt 与 running 状态，避免 worker 已启动但 state 仍显示 pending。本文件不复制第二套 state patch。只有 helper merge 成功持久化后才 dispatch；失败即 STOP，不宣称 helper direct write 具备 filesystem atomicity。
4. **Dispatch implementer**：使用 Dispatch Templates；worker 是 fresh Agent，只收到 brief path、implementer report path、exact model 与 allowed context。
5. **Validation**：Controller 或 bounded implementer append 真实结果到 `validation.md`，并按 File Protocol 的 Task-scope evidence 合同绑定当前 cycle。Task complete、失效条件与重验只以 File Protocol 的 `task_scope_fingerprint` authority 为准；本文件不复制 global snapshot 或 exact patch 规则。含 commands 时该 cycle 全部 required commands 成功；`commands: []` + notes 或 notes-only 统一走 no-command static branch，要求 static acceptance + reviewer PASS。产品 validation failure（命令可执行但 assertion/acceptance 不通过）必须引用 File Protocol 的 fixer/re-review budget；即使初始 validation failure 尚无 reviewer finding，也由 Controller 用 validation evidence 形成 fixer input，且每轮 fix 后仍必须生成新的 authoritative validation 并 dispatch fresh reviewer/re-review。Infrastructure failure（命令无法执行、权限/环境/外部依赖或 validation/reviewer infrastructure 无法取得 authoritative result）引用 File Protocol 的 canonical `resolved_evidence` Task blocker，且不消耗产品 `fix_cycle`。历史失败保留，可被后续完整成功 cycle supersede，但不能跨 cycle 拼接成功结果。
6. **Read reports**：Controller 读取 implementer status、`Loaded Context`、changed files、validation evidence；缺失任一 required evidence 时，按 File Protocol 区分 Task-local canonical blocker 与 change-level STOP，不得跳过分类。
7. **Dispatch reviewer**：使用 fresh reviewer；只传 task brief、implementer report、validation、review output path、exact model、allowed diff/context。
8. **Fix/re-review**：如有普通产品 validation failure（即使尚无 reviewer finding）或 reviewer Critical/Important，均按 Reviewer and Fix Loop 进入同一个 File Protocol fixer/re-review budget：dispatch fixer，随后执行 authoritative validation，再 dispatch fresh reviewer；最多 2 次 re-review。
9. **Merge result**：按 File Protocol 合并三种互斥结果之一：canonical **Task complete**、canonical **Task blocked**、或 change-level **manual escalation**。本文件只编排并引用对应 Protocol transition，不形成第二套 state authority。
10. **Next Task**：只有当前 Task completed 或 canonical Task blocked 后才重新计算 eligibility。Task-local blocked 只排除其 transitive dependents；独立 eligible Tasks 可继续。若结果是 change-level manual escalation，或出现 change-level invalid/Gate/dirty/global blocker，则立即 STOP，不得继续其他 Tasks。用户随后只有两条互斥恢复路径：若明确授权额外 bounded repair attempt，只引用 File Protocol 的 manual-escalation repair-attempt authorization record、exact transition 与 reconciliation；若选择 Design/Plan/acceptance/scope/context 修改，只引用 File Protocol 的 `MANUAL_ESCALATION_DESIGN_REVISION` choice record、Design-revision exact transition、Design draft/pending reconciliation 与后续 Design reapproval helper 清理，不创建 repair attempt。

所有 Tasks status completed 后，Controller 必须按 File Protocol 的 Implement complete evidence 与 fingerprint lifecycle 完成逐 Task freshness 检查，再计算 change-wide snapshot；不得信任 legacy status 或跳过 evidence 进入 Verify。本文件不另行定义其 snapshot 算法。

## Worker Status Contract

Implementer 与 fixer 最终 status 只允许以下四个 exact values：

| Status | 含义 | Controller action |
|---|---|---|
| `DONE` | acceptance 已实现，required validation 可执行，未发现 concern | 进入 validation/review |
| `DONE_WITH_CONCERNS` | 工作已完成，但有必须透明保留的非阻塞 concern | 记录 concerns，仍进入 validation/review |
| `NEEDS_CONTEXT` | manifest/brief 缺少完成 acceptance 所必需的 context | canonical Task blocked；回 Design/context 修订并重新批准 Design Gate；独立 eligible Tasks 可继续 |
| `BLOCKED` | 技术、权限、依赖或 validation blocker 使 Task 无法完成 | canonical Task blocked；只阻止其 transitive dependents；dirty/global blocker 则全局 STOP |

不得使用 `SUCCESS`、`PARTIAL`、`IN_PROGRESS`、自由文本或空值作为 worker final status。

`DONE`/`DONE_WITH_CONCERNS` 不是 reviewer approval，也不直接授权 `tasks.<id>.status=completed`。

## Reviewer and Fix Loop

Reviewer 必须是未参与该 attempt 实现的 fresh Agent，并在一份 review 中同时判断：

1. **Spec compliance**：Task acceptance、Design constraints、allowed scope、verification 与 rollback 是否满足。
2. **Code quality**：正确性、回归风险、可维护性、测试质量与不必要 scope 是否可接受。

Finding severity 至少区分 `Critical`、`Important` 与非阻塞建议：

- 任一未解决 Critical 或 Important 都阻塞 Task completed。
- 非阻塞建议可随 `DONE_WITH_CONCERNS` 保留，但必须写 evidence。
- Reviewer 不得修改实现。

Fix loop：

1. 普通产品 validation failure（命令可执行但 assertion/acceptance 不通过）或 reviewer Critical/Important 均引用 File Protocol 的同一个 bounded fixer/re-review budget；本文件不复制 exact patch。
2. 初始 validation failure 可能尚无 reviewer finding；Controller 必须按 File Protocol 由 validation evidence 形成 fixer input，但仍必须在 fix 后执行 authoritative validation 与 fresh reviewer/re-review，不能跳过 reviewer。
3. Fixer 只收到 task brief、implementer report、validation、latest review（若已有）、fix report path、exact model 与 matching minimal context。
4. 若 File Protocol 的 `fix_cycle` budget 未耗尽且仍有普通产品 failure/finding，继续下一轮 fixer + authoritative validation + fresh re-review。
5. **最多 2 轮产品 fixer/re-review**，计数以 File Protocol 的 `fix_cycle=1..2` 为准；第二轮 post-fix authoritative validation + fresh re-review 后仍有普通产品 correctness/quality/acceptance failure/finding 时，必须引用 File Protocol 的 manual escalation：Task 与 `current_task` pointer 保持 `in_progress`，change-level `status=blocked`，不创建 Task blocker/BLOCKED record，立即 STOP 且不继续其他 Tasks。只有 reviewer/validation infrastructure、context、权限、环境、外部依赖等真正 canonical Task blocker 才继续走 Task-local blocked 路径，且不消耗产品 `fix_cycle`。若用户明确授权额外 bounded repair attempt，恢复只引用 File Protocol 的 authorization record、canonical `tasks.<id>.manual_repair_authorization` applied identity、exact transition 与 reconciliation：authorization 必须绑定 latest authoritative validation outcome（`PASS|PRODUCT_FAILURE`）和 latest fresh review outcome，二者同 exhausted tuple 且至少一个是 escalation authority；append 成功且 merge 成功后才 dispatch fresh repair worker；新 attempt 重新从 `fix_cycle=0/review_cycle=0` 开始，并按 fresh path 先持久化 `review_cycle=1` 再生成新 authoritative validation/review。若用户选择修改 Design/Plan/acceptance/scope，则转 Design revision/Gate，不创建 repair attempt。

Reviewer status 不复用 Worker Status Contract；review 必须给出明确 blocking/non-blocking verdict 和 findings。

## State and Evidence Updates

Task evidence 固定为：

```text
evidence/tasks/<task-id>/task-brief.md
evidence/tasks/<task-id>/implementer.md
evidence/tasks/<task-id>/validation.md
evidence/tasks/<task-id>/review.md
```

状态与 evidence 更新规则：

- Dispatch 前先写 running state，避免 worker 已启动但 state 仍显示 pending。
- Worker 不直接决定 change phase/gates；Controller 读取 evidence 后用 `state-helper.py merge-state` 合并。
- `implementation.changed_files` 使用 project-relative paths；每次 canonical Task blocked/complete、manual escalation 停止点和 Implement complete 都由 Controller 从 worker reports + Git reconciliation 生成完整去重数组，Git diff 是 Verify 的真实范围。
- `implementation.completed_tasks` 只在 reviewer 无 blocking findings 且最新 snapshot validation cycle 满足 complete 条件后 append 一次。Verify fix 默认将 direct affected + completed transitive dependents 退回 pending 并从数组移除；只有 persisted explicit unaffected analysis 才可保留 dependent completed。
- Canonical Task blocked 只按 File Protocol 为真正 Task-local blocker 保留 `current_task={id,attempt,status}` 与对应 `tasks.<id>.attempts/status`；pre-dispatch blocker 不递增 attempt，可记录当前 attempts（首次为 0）。Manual escalation 不写 Task blocker，且必须保持 Task 与 `current_task` pointer 为 `in_progress`，同时用 change-level `status=blocked` 表示 orchestration STOP。Task complete 后清空 current task。
- Design/Plan/context 变更后的 approval、whole-map replacement、canonical `blocked→pending` 与 manual escalation 后的两条互斥恢复顺序都只引用 File Protocol。普通 resume 不刷新；临时权限/环境/依赖/validation-reviewer infrastructure blocker 的恢复同样引用 File Protocol 的 resolved-evidence exact recovery。Task-local blocked 的下一次 dispatch 才递增 attempt，旧 blocker/history 保留；Design reapproval 或 resolved-evidence recovery 把 Task 返回 pending 时必须同时清空 stale `manual_repair_authorization` 与 `design_revision_authorization`。manual escalation 的用户授权 repair 恢复则只通过 File Protocol 的 fixed authorization record + canonical applied authorization identity + single preserve/merge new-attempt transition，不复制 patch，不重复执行 Task dispatch；reconciliation 只能用 state 中 applied ID 与 exact new-attempt shape 判断 merge 成功。manual escalation 的 Design/Plan/acceptance/scope/context 修改选择则只通过 File Protocol 的 `MANUAL_ESCALATION_DESIGN_REVISION` choice record + canonical `design_revision_authorization` applied identity + single preserve/merge Design draft/pending transition，并由 Design reapproval helper 对完整 Design-eligible 集合清理；任一 Task 上 `manual_repair_authorization` 与 `design_revision_authorization` 同时 non-null 都必须 fail closed，普通 dispatch、repair、Design revision 或 resolved pending recovery 不得彼此误认。
- Task evidence 固定路径但 append-only cycles：每个 Attempt/Fix/Review cycle 记录 brief immutable content hash 与 relevant summary。固定 `task-brief.md` 被重提取后，旧 evidence 仍保留但不能伪装成适用于新 hash；必须新 attempt/validation/review。
- Change-wide `evidence/review.md` 与 Fold proposal 不属于 Per-Task loop，分别由 Verify/Fold 生成。
- 所有 exact transitions 只以 File Protocol 为 authority，本文件不复制 exact patch，不另造 phase/status 值。

## Git Scope

- `plan.yaml files_hint` 只是预期修改/navigation hints，不是封闭 allowlist，也不单独授予写权限。
- Worker 可为满足 Task acceptance 做 bounded discovery；实际 mutation 必须保持在 acceptance 必需范围。任何不在 `files_hint` 的新增/修改路径都必须在 implementer report 解释原因，由 reviewer 明确判定是否仍在 scope。
- Context Manifest 管理 stable project/change knowledge 且始终只读。Task-local source discovery 只能沿 acceptance/files_hint/known symbol/import/direct caller chain 读取最小源码并记录 Loaded Context 来源；禁止 root/module/broad sibling scan。需要未声明 stable knowledge、跨边界源码或 broad discovery 时返回 `NEEDS_CONTEXT` 回 Design。
- Git reconciliation、Task/global fingerprints、changed-files fingerprint 与 freshness 全部引用 File Protocol；HEAD/path set 不足。本文件不复述 snapshot 算法。
- Worker 必须保护 `implementation.preexisting_paths`；Controller 在每个 Task/Verify/Fold mutation 边界复核其 Git-status/content fingerprints，变化即 STOP。Immutable approved artifacts 同样按 hash 复核；mutable control-plane 只允许合法 transition/evidence append。
- 首次 entry 与 Resume 都按四类 ownership 归属。Resume 依据首次 `base_sha`、brief-hash-bound completed evidence 与累计 `changed_files` 识别 workflow-owned product mutations；无法归属且与产品范围重叠的 dirty path 始终 STOP。
- 同一 working tree 不允许并行 mutation。
- 不得 stash、reset、clean、强制 checkout 或改写用户已有工作。
- 默认 **不自动 commit**。
- 只有 `plan.yaml` 或用户当前轮明确授权 commit 时，Controller 才可创建 scoped commit。
- Commit 必须只包含当前 Task/change 授权文件；不得捎带 preexisting paths。
- Worker 不因“方便回滚”自行创建 branch、worktree 或 checkpoint commit。

## Stop Conditions

Stop scope 必须区分 Task-local 与 change-level。Task-local canonical blocked 只停止该 Task 及其 transitive dependents，随后继续计算独立 eligibility；change-level manual escalation 不进入 Next Task，并立即停止整个 dispatch/merge-next-task orchestration。以下条件会触发 change-level STOP：

- invalid `state.json`、Plan、manifest 或 helper input。
- Design Gate pending/missing/ambiguous，且当前轮无 explicit Design Gate approval；provisional continuation 不满足此条件。
- 非 Git repo、无法解析 HEAD。
- dirty worktree 未授权、dirty path 与 change scope 重叠且无法由 base snapshot + completed evidence + changed_files 证明为 workflow-owned，或无法证明其他 preexisting dirt 与 scope 不相交。
- Shared/change-wide required target 缺失/不可读、manifest invalid、immutable hash drift 或 preexisting fingerprint 变化。Task-only required target 缺失走 pre-dispatch Task-local blocked，不在此 change-level list。
- dependency graph 无 eligible Task 但仍有未完成 Tasks。
- 所有剩余 Tasks 均 blocked 或依赖 blocked，因而不存在独立 eligible Task。
- change-level required evidence 缺失，或无法将 evidence 缺陷限定到单一 Task。
- reviewer infrastructure/global evidence 缺失，或无法同时覆盖 spec compliance/code quality。
- 某 Task 按 File Protocol 的 `fix_cycle=1..2` 完整使用最多 2 轮产品 fixer/re-review 后，仍有普通产品 validation failure 或 correctness/quality/acceptance 的 Critical/Important，按 File Protocol 进入 manual escalation：Task 与 `current_task` pointer 保持 `in_progress`，change-level `status=blocked`，不写 Task blocker/BLOCKED record，并立即 STOP。后续恢复只有两条互斥 File Protocol 路径：用户明确授权额外 bounded repair attempt 时引用 manual-escalation repair-attempt transition、完整 authorization identity 与 applied state field；用户选择 Design/Plan/acceptance/scope/context 修改时引用 `MANUAL_ESCALATION_DESIGN_REVISION` choice record、Design-revision exact transition、Design draft/pending reconciliation 与后续 reapproval helper；validation/reviewer infrastructure 没有 authoritative result 时转 canonical Task blocker，不创建新 attempt。
- Worker 请求扩大为完整历史、全仓 context、并行 mutation、worktree 或自动 commit。

Task-local canonical blocker 有具体 evidence 时按 File Protocol 的 canonical Task blocked transition 持久化，并只阻止该 Task 及其 transitive dependents；reviewer/validation infrastructure、context、权限、环境、外部依赖等真正 blocker 若不影响独立 eligibility，可继续其他 eligible Tasks。change-level STOP 若源于 manual escalation 或其他 global condition，不得把当前 Task 改写为 blocked；若尚未 dispatch Task，则保持已有状态并请求澄清，不得发明 blocker。

## Explicit Exclusions

本 MVP lightweight SDD 明确不做：

- 不调用完整 Superpowers SDD 流程。
- 不使用 `.superpowers/sdd/progress.md`。
- 不增加第二个 final review；change-wide verdict 属于 Verify。
- 不执行 branch finish 或 finishing-development-branch 流程。
- 不创建或使用 worktree。
- 不自动 commit。
- 不向 Agent 注入完整 plan、完整聊天、完整 session/review history。
- 不实现 `status`/`resume` Skills。
- 不实现 hooks、runtime automation、daemon、CLI product、MCP 或 cross-project RAG。
- 不在本 Task 消除现有 Implement/Verify/Fold Skill 与目标协议的冲突；本 reference 是目标 authority，Skill 对齐属于 Tasks 5–7。

## Dispatch Templates

每次 Agent call 都必须显式传 `model`。实际 dispatch model 合同只有：

- 默认 implementer/reviewer/fixer：`model: "sonnet"`。
- 只有当前 Task brief 明确标记 `architecture-heavy`：可显式使用 `model: "opus"`。
- 不得省略 `model`，不得以 `implicit`、`inherit` 或“沿用 controller model”作为实际 dispatch model。

下列模板描述允许传入的 package；路径均为 project-relative，Agent prompt 不得把文件全文、完整 Plan 或历史粘贴进去。

### Implementer dispatch

```yaml
subagent_type: nuclio:nuclio-implementer
model: sonnet # architecture-heavy brief only: opus
description: implement bounded task
prompt_inputs:
  task_brief: .dev-docs/changes/<change-id>/evidence/tasks/<task-id>/task-brief.md
  report_output: .dev-docs/changes/<change-id>/evidence/tasks/<task-id>/implementer.md
  allowed_context: matching required entries, acceptance-driven jit, then only minimal source discovery allowed by Context Manifest Worker Loading Contract
constraints:
  - source reads follow acceptance/files_hint/symbol/import/direct-caller chain; no broad scan
  - mutate only acceptance-necessary bounded scope; files_hint is navigation, not an allowlist
  - treat manifest context as read-only; explain every mutation beyond files_hint for reviewer scope judgment
  - record task-brief content hash and report exact Worker Status Contract value
  - record Loaded Context project-relative paths and jit skip reasons
```

### Reviewer dispatch

```yaml
subagent_type: nuclio:nuclio-task-reviewer
model: sonnet # architecture-heavy brief only: opus
description: review bounded task
prompt_inputs:
  task_brief: .dev-docs/changes/<change-id>/evidence/tasks/<task-id>/task-brief.md
  implementer_report: .dev-docs/changes/<change-id>/evidence/tasks/<task-id>/implementer.md
  validation: .dev-docs/changes/<change-id>/evidence/tasks/<task-id>/validation.md
  review_output: .dev-docs/changes/<change-id>/evidence/tasks/<task-id>/review.md
  allowed_context: task-scoped diff, matching manifest entries, and only minimal source chain allowed by Context Manifest
constraints:
  - verify report/review cycles bind the current task-brief hash and implementation snapshot
  - judge spec compliance, code quality, and beyond-files_hint mutation scope
  - identify Critical and Important findings explicitly
  - treat context as read-only and do not modify files
```

### Fixer dispatch

```yaml
subagent_type: nuclio:nuclio-fixer
model: sonnet # architecture-heavy brief only: opus
description: fix reviewed task
prompt_inputs:
  task_brief: .dev-docs/changes/<change-id>/evidence/tasks/<task-id>/task-brief.md
  implementer_report: .dev-docs/changes/<change-id>/evidence/tasks/<task-id>/implementer.md
  validation: .dev-docs/changes/<change-id>/evidence/tasks/<task-id>/validation.md
  latest_review: .dev-docs/changes/<change-id>/evidence/tasks/<task-id>/review.md
  report_output: .dev-docs/changes/<change-id>/evidence/tasks/<task-id>/implementer.md
  allowed_context: matching stable context plus only the minimal source chain needed to resolve blocking findings
constraints:
  - fix Critical and Important findings within acceptance-necessary bounded scope
  - treat context as read-only; explain beyond-files_hint mutations for re-review
  - append a new snapshot-bound validation cycle and update changed-files evidence
  - do not broaden scope or commit
```

Controller 必须在每次实际 Agent call 中把模板中的 `sonnet` 或符合条件的 `opus` 作为显式 `model` 参数传入；模板注释不等于运行时继承。
