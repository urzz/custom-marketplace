---
name: verify
description: Use when the user wants to verify a completed Nucl.io implementation range + all acceptance before accepting, fixing, or deferring the change-wide Verify Gate.
disable-model-invocation: true
---

# Nucl.io Verify

## Critical Constraints

- `/nuclio:verify` 是 completed implementation 的 change-wide independent critic 与 persisted HITL Gate；不是 current task review，也不是 tests-only shortcut。
- 只在 `state.json` mutable execution state 同时显示 `phase=implement,status=completed,current_task=null`、`state.tasks` 覆盖全部 Plan Task IDs 且每个均为 `completed`、`implementation.completed_tasks` 精确匹配全部 Plan IDs、`implementation.base_sha` 可被 Git 解析、implementation 完成字段与 Task evidence 可核对、`context/verify.jsonl` 合法时进入。`plan.yaml` 只提供 Task definitions/acceptance/verification/rollback，不提供 mutable completion authority。
- Verify scope 必须覆盖完整 implementation range、全部 completed Task acceptance 与 `spec.md` 全部 acceptance；禁止只看“current task”“current diff”或最后一个 Task。
- Snapshot 与 fingerprint authority 以 `references/protocol.md` 为准：`implementation.base_sha`、review-bound HEAD、`global_product_fingerprint`、changed-files fingerprint 与 review artifact SHA 都必须作为 Verify review identity 持久化并在 decision 前重算核对；不能只依赖 HEAD。
- Verify manifest loading semantics 以 `references/context-manifest.md` 为准；`context/verify.jsonl` 应小于且更聚焦于 implement manifest。若无法证明更小或上下文过宽，必须在 `evidence/review.md` 记录 `bloated-context` 风险。
- 不读取完整历史、all `.dev-docs`、all source、raw logs、reviewer transcript、session journals 或 unrelated Task context。
- 不运行 destructive commands；不得 stash/reset/clean/force checkout/push，也不得触碰未授权 preexisting dirt。
- 缺失 tests、typecheck、lint、validation commands 或 evidence 时不得静默跳过；必须在 review 中标记 Fail 或降低置信度并说明影响。
- 主 session/controller 不直接修产品代码。Verify fix 只能委派 bounded `nuclio:nuclio-fixer`，显式指定 model，只修 `evidence/review.md` 中 confirmed findings；最多 2 轮，每轮后完整重新 Verify。
- Artifact existence is not Gate approval：`evidence/review.md` 存在只表示 review ready，不代表 `gates.verify=approved`。
- 只有当前轮用户明确 `accept` 才能用 state helper approval guard 写 `gates.verify=approved`；不得自动批准，不得 Verify 后自动 Fold。
- Fail override 必须由用户逐项明确接受风险，记录在 `Risks/Overrides`；不得把原 Fail 静默改写为 Pass。
- 输出 summaries，不粘贴 raw long logs；长日志只摘录命令、退出码、关键错误与相关路径。

## Contents

- [Critical Constraints](#critical-constraints)
- [Workflow Overview](#workflow-overview)
- [Phase 1: Confirm Implement Readiness](#phase-1-confirm-implement-readiness)
- [Phase 2: Determine Exact Implementation Range](#phase-2-determine-exact-implementation-range)
- [Phase 3: Load Bounded Verify Context](#phase-3-load-bounded-verify-context)
- [Phase 4: Review All Acceptance and Run Validation](#phase-4-review-all-acceptance-and-run-validation)
- [Phase 5: Write Mandatory Verification Review](#phase-5-write-mandatory-verification-review)
- [Phase 6: Persist Verify Gate and STOP](#phase-6-persist-verify-gate-and-stop)
- [Phase 7: Handle User Decision](#phase-7-handle-user-decision)
- [Behavior Verification](#behavior-verification)

## Workflow Overview

`/nuclio:verify` 执行 Generator-Critic style change-wide verification：Controller 从 file-backed state 和 bounded manifest 构造完整 implementation snapshot，独立核对 spec、Plan Task acceptance、Task evidence、Git truth 与 validation commands，写 mandatory `evidence/review.md`，再持久化 `gates.verify=pending` 并停止等待人工决策。

默认顺序：

1. Inspect current change state，确认 state-only Implement completed readiness；Plan 仅作为 definitions/acceptance 输入。
2. Merge stage entry：`phase=verify,status=in_progress`。
3. 计算 exact implementation range 与 fresh `global_product_fingerprint` / changed-files fingerprint。
4. 加载 bounded verify context；拒绝 manifest invalid 或 forbidden broad inputs。
5. Review `spec.md` 全部 acceptance、state completed Task set 对应的 `plan.yaml` Task definitions/acceptance、Task evidence 与 validation evidence。
6. 运行 exact non-destructive task/global validation commands；缺失或无法运行必须记录。
7. 完整写 `evidence/review.md` 后计算普通 file SHA-256，并按 protocol 持久化 Verify review ready snapshot。
8. 输出 exact STOP，等待用户选择 `accept`、`fix` 或 `defer`。

## Phase 1: Confirm Implement Readiness

进入 Verify 前必须 fail closed 核对：

- 当前 change `state.json` 存在、可解析，且来自 `.dev-docs/changes/<change-id>/`；不得以 `.nuclio/` runtime/cache/temp state 替代。
- `state.json` 的 mutable execution state 必须精确为 `phase=implement,status=completed,current_task=null`；不得把 `plan.yaml` legacy `status`、audit metadata、artifact existence 或聊天摘要当作完成 authority。
- `plan.yaml` 可读并包含所有 Task IDs、definition、dependencies、acceptance、verification、rollback；Plan 在 Verify 中只提供 definitions/acceptance，不提供 mutable completion authority。
- `state.tasks` 必须为 object，覆盖 `plan.yaml` 中全部且仅有的 Task IDs；每个 `state.tasks.<id>.status` 必须为 `completed`，缺失、legacy、blocked、pending、in_progress、extra/unknown Task 均 STOP。
- `current_task` 必须为 `null`；任何 active、blocked、malformed 或 stale pointer 均 STOP。
- `implementation.base_sha` 存在且 `git rev-parse --verify <base_sha>` 成功；不得以当前 HEAD 覆盖或重置 `base_sha`。
- `implementation.head_sha`、`implementation.changed_files`、`implementation.completed_tasks`、`implementation.product_fingerprint` 必须与 Implement complete contract 可核对；`implementation.completed_tasks` 去重后必须精确等于全部 Plan Task IDs。缺失、extra、顺序外重复或 mismatch 均不得进入 Verify。
- 对每个 state completed Task，固定 evidence 文件存在：`task-brief.md`、`implementer.md`、`validation.md`、`review.md`；current brief hash、Task scope fingerprint、cycle identity、Task acceptance mapping、authoritative validation 与 fresh reviewer PASS 必须与 `state.tasks.<id>` 当前 `attempts/fix_cycle/review_cycle/task_scope_fingerprint` 精确匹配。旧 cycle evidence 只作审计，不能满足 readiness 或 completion。缺失或 mismatch 不得通过 Verify。
- `spec.md` 可读并包含 change acceptance；若缺失，STOP 或 Fail，不得补造 acceptance。
- `context/verify.jsonl` 存在且 JSONL shape 合法；invalid manifest 是 change-level STOP。
- 若存在 `implementation.preexisting_paths`，必须复核其 fingerprints；任何变化或与 product scope 重叠立即 STOP。

Readiness 通过后，使用 `${CLAUDE_PLUGIN_ROOT}/scripts/state-helper.py merge-state` 或等价 preserve/merge 写入：

```json
{"phase":"verify","status":"in_progress"}
```

该 stage entry 必须 preserve unknown keys、metadata、current task fields、artifacts、evidence 与 unrelated gates。不得写任何 approved gate。

## Phase 2: Determine Exact Implementation Range

Verify scope 必须是 change-wide implementation range，至少包含以下 union：

1. `git diff <base_sha> <current-head>`：从 recorded `implementation.base_sha` 到当前 HEAD 的已提交实现变更。
2. `git diff --cached`：staged changes。
3. `git diff`：unstaged changes。
4. Implement reports / Task evidence 声明的 untracked files。
5. `implementation.changed_files` 与所有 Task reports 声明 changed files 的 union。

Reconciliation rules：

- 以 Git truth 为准，reports 用于证明 ownership 与解释 scope，不可覆盖 Git。
- Current HEAD 与 recorded `implementation.head_sha` 不一致时，列出新增 commits 与 changed paths，要求用户明确确认是否纳入本次 Verify；未确认前 STOP，不得 silently include 或 silently ignore。
- `preexisting_paths` 默认从 product scope 排除；任何与 implementation range、Task own mutations、staged/unstaged/untracked product paths 重叠都 STOP。
- Immutable approved control-plane 与 workflow-owned mutable control-plane 按 protocol 从 product diff 中排除；不得把 state/evidence/control-plane drift 当成产品实现。
- 计算完整 reconciled workflow product scope，并按 `protocol.md` 的 canonical algorithm 生成当前 `global_product_fingerprint`。
- 计算 `implementation.changed_files` 子集的 changed-files fingerprint。
- 记录 `base_sha`、review-bound HEAD、global fingerprint、changed-files fingerprint 与 scope path summary；这些字段会绑定 `evidence/review.md` 与后续 decisions。

禁止使用“current task”“current diff”“最后一个 diff”作为唯一 scope wording 或唯一实现范围。

## Phase 3: Load Bounded Verify Context

按 `context-manifest.md` 加载 context：

1. 读取并校验 `context/verify.jsonl` 每个非空行都是 JSON object，且包含 `path`、`kind`、`mode`、`reason`。
2. 拒绝 absolute path、`..` traversal、glob、目录路径、broad roots、full conversation、all-doc、all-source、raw logs、reviewer history、session journals。
3. 加载所有 `mode=required` entries；`mode=jit` 只在 acceptance、validation 或 risk analysis 需要时加载，并在 review 中说明跳过原因。
4. 核对 verify manifest 是否小于、更聚焦于 implement manifest。若 entry count 或实际 target size 无法证明更小，或 target 过宽，必须在 `Risks/Overrides` 记录 `bloated-context` 风险、原因与影响。
5. 只读取验证必要文件；需要更广 context 才能判断时 STOP，要求回到 Design 收紧 manifest，而不是自行扩大。

## Phase 4: Review All Acceptance and Run Validation

Verify 必须形成 change-wide acceptance matrix：

- `spec.md` 中每条 acceptance：给出 Pass/Fail/Defer、证据路径、相关 diff/Task、风险。
- `plan.yaml` 中每个 Task definition/acceptance（由 state completed Task set 精确覆盖全部 Plan IDs）：逐项核对，不得只看最后一个 Task；不得读取或信任 Plan legacy status 作为完成依据。
- 每个 Task 的 verification/rollback constraints：确认 required validation 已执行，rollback 风险已记录。
- Task evidence summary：汇总 implementer、validation、review evidence 的 status、cycle identity、commands/results、Critical/Important findings 是否已 resolved；不得读取 reviewer transcript/raw logs。
- Architecture/protocol constraints：`.dev-docs/` source-of-truth、`.nuclio/` runtime/cache/temp、无 hooks/runtime/MCP/daemon/RAG expansion、无 `grill-me`/Trellis fork/Chorus full-context 复制等。
- Scope control：确认 diff 未包含未经授权 preexisting dirt、无关重构或越界 product changes。

Validation commands：

- 运行 brief、Plan、verify manifest、Task evidence 或 engineering guidance 中列出的 exact non-destructive validation commands。
- 若存在 task-level exact commands 与 global exact commands，均需运行或说明 blocker；不得静默跳过 tests/typecheck/lint/grep marker checks。
- 命令无法启动、工具缺失、权限/环境不可用时记录 `BLOCKED`/`Defer` 风险；命令可运行但 assertion/acceptance 失败时记录 product `Fail`。
- 输出只保留 command、exit code、key output summary、conclusion；不粘贴 raw long logs。

## Phase 5: Write Mandatory Verification Review

必须写 `.dev-docs/changes/<change-id>/evidence/review.md`（相对当前 change 记为 `evidence/review.md`）。不得把 review 作为可选产物。

Review sections 固定且按顺序为：

```markdown
# Verification Review

## Summary

## Scope

## Acceptance Matrix

## Task Evidence

## Commands Run

## Findings

## Risks/Overrides

## Final Verdict
```

内容要求：

- `Summary`：说明 overall result 与 confidence。
- `Scope`：列出 `base_sha`、review-bound HEAD、global product fingerprint、changed-files fingerprint、range union、preexisting path handling、HEAD mismatch confirmation（如有）。
- `Acceptance Matrix`：覆盖 spec 全部 acceptance 与全部 Plan Task definitions/acceptance；Task 完成集合来自 `state.tasks`/`implementation.completed_tasks` 的精确 readiness 核对，不来自 Plan legacy status。
- `Task Evidence`：汇总每个 Task 的 evidence paths、cycle identity、validation/review status 与 unresolved concerns。
- `Commands Run`：表格列出 command、exit code、key output summary、conclusion；缺失命令也要列出。
- `Findings`：按 severity 记录 confirmed findings；用于 fix 的 finding 必须包含可定位 path/line 或 bounded failure identity。
- `Risks/Overrides`：记录 bloated-context、missing tests、manual risk acceptance、Fail override details；没有则写 `None`。
- `Final Verdict` 只允许 `Pass`、`Fail` 或 `Defer`，并必须给出 recommendation：`accept`、`fix` 或 `defer`。

Review artifact 可以记录其依据的 product snapshot fields，但不得记录自身 file hash。完整写入最终 bytes 后，再计算普通 SHA-256，作为 state 外部 metadata 持久化。

## Phase 6: Persist Verify Gate and STOP

写完 `evidence/review.md` 并计算 artifact hash 后，按 `protocol.md` 的 Verify review ready transition 用 preserve/merge 写入：

```text
phase=verify
status=draft
gates.verify=pending
evidence.verify_review=evidence/review.md
evidence_snapshots.verify_review={path:evidence/review.md,sha256:<ordinary final-file SHA-256>,base_sha:<base>,head_sha:<review-bound HEAD>,global_product_fingerprint:<global>,changed_files_fingerprint:<changed-files>}
current_task=null
implementation.head_sha=<review-bound HEAD>
implementation.product_fingerprint=<review-bound global_product_fingerprint>
```

该 merge 成功后，review 才是 ready；只写路径或只输出文字不够。若 helper merge 失败，STOP，不得要求用户 accept stale/unpersisted verdict。

随后必须输出 exact STOP：

```text
STOP. Verify Gate：`evidence/review.md` 已生成，当前 `gates.verify=pending`。请选择 accept、fix 或 defer；在明确选择前不会批准 Verify Gate，也不会进入 Fold。
```

不得在该 STOP 后自动批准、自动 fix、自动 Fold、自动写长期知识或继续读取完整历史。

## Phase 7: Handle User Decision

任何 decision 前都必须先做 freshness check：从 `state.evidence_snapshots.verify_review` 读取 expected path/hash/snapshot fields，重算 review artifact 普通 file SHA-256、`base_sha`、当前 HEAD、`global_product_fingerprint` 与 changed-files fingerprint 并逐项比较。任一 drift 都保持/退回 `gates.verify=pending,phase=verify,status=draft`；若存在当前 Fold proposal，按 protocol 标记 `evidence_snapshots.fold_proposal.status=superseded`，然后重新完整 Verify。不能只看 HEAD。

### accept

- 仅当前轮用户明确选择 `accept` 且 freshness 全部匹配时，才可使用 state helper `merge-state --allow-approval` 写：`gates.verify=approved,status=approved`（保持 `phase=verify`，除非同轮由 Fold transition 接管）。
- 若 `Final Verdict=Fail`，用户必须逐项明确接受 `Risks/Overrides` 中的风险；记录 override 后才可 approval。不得把 Fail 静默重写成 Pass。
- 成功后输出下一步：`/nuclio:fold`。

### fix

- 严格执行 `protocol.md` 的 Verify user decision `fix` exact transition；不得自行发明 patch、不得在主 session 直接修产品文件、不得批准 Verify、不得自动 commit。
- 先核对 review identity 与 global fingerprint freshness；stale review 不可作为 fix authority，必须保持/退回 `gates.verify=pending,phase=verify,status=draft` 并重新完整 Verify。
- Fresh review 且用户当前轮选择 `fix` 后，preserve/merge 精确写回 Implement repair state：保持 `gates.verify=pending`，写 `phase=implement,status=in_progress,current_task=null`。
- 基于 `evidence/review.md` 中 confirmed findings 或 authoritative validation failure identity 计算 impact set：direct affected Tasks 必须纳入；默认还纳入所有已 completed 的 transitive dependents。只有 Verify evidence 中已经持久记录 explicit unaffected analysis（说明依赖输出为何未变且旧验收仍适用）时，才可排除某 dependent。不得把 Minor/concern/无定位建议扩展为 broad refactor。
- 将 impact set 内 Tasks 的 `state.tasks.<id>.status` 退回 `pending`；从 `implementation.completed_tasks` 中完整移除 affected set（数组由 Controller 提供完整替换值）。保留旧 `attempts/fix_cycle/review_cycle/task_scope_fingerprint` 与旧 evidence 仅作审计；旧 Task evidence 不满足新的 completion、Implement complete 或 Verify freshness。
- `implementation.product_fingerprint` 和旧 Verify snapshot 仅是历史 reviewed snapshot，不得用于后续 approval；修复完成后必须走 Implement bounded repair/recompletion：下一次 dispatch 按 Task dispatch 递增 attempt、重置 cycles，生成新 attempt 的 authoritative validation 与 fresh review，重新满足 Task complete 与 Implement complete。
- 后续只委派 plugin-scoped `nuclio:nuclio-fixer` / bounded repair worker，显式 `model`，并提供 required input contract：task brief、affected evidence、state tuple、review binding、allowed context 与 fix report output。若 finding 需要 Design/Plan/acceptance/scope/context 修改或超出 bounded fixer 能力，STOP 并要求用户选择 defer/design revision。
- affected Tasks 重新 completed 且 Implement complete 后，必须完整重新执行 change-wide Verify，生成新的 `evidence/review.md` 与新的 snapshot metadata；旧 review 不能作为 approval 或 Fold readiness。

### defer

- 严格执行 `protocol.md` 的 Verify user decision `defer` exact transition：不批准、不回退、不伪造 blocker、不写 `blocked`、不创建 Task blocker 或 blocker evidence。
- 仅记录 concise defer reason（例如在 controller summary 或 review/follow-up notes 中作为审计），并 preserve/merge 保持 `phase=verify,status=draft,gates.verify=pending`；review artifact 与 snapshot metadata 不因 defer 变成 approval。
- 后续恢复必须先做 review artifact 与 global fingerprint freshness check；stale 时仍保持/退回 pending draft 并重新 Verify。

## Behavior Verification

RED：

- tests-only 或 informal review 后直接建议 approval。
- 只看 current task、current diff、最后一个 Task 或 HEAD，不计算 implementation.base_sha range 与 global_product_fingerprint。
- `evidence/review.md` 可选，或只输出文字 STOP 不持久化 `gates.verify=pending`。
- Artifact 存在即认为 Verify Gate approved。
- Verify 后自动 Fold，或用户说“测试过了”就直接 approved。
- 主 session 顺手修产品代码，或 fix loop 不经 `nuclio:nuclio-fixer`。

GREEN：

- 只有 state 精确为 `phase=implement,status=completed,current_task=null`、`state.tasks` 全部 Plan IDs completed、`implementation.completed_tasks` 精确匹配、`implementation.base_sha` 可解析、Task evidence 完整且 verify manifest 合法时进入；Plan 只提供 definitions/acceptance。
- Scope 精确覆盖 `git diff <base_sha> <current-head>`、`git diff --cached`、`git diff`、reports untracked files、`implementation.changed_files` 与 Task report union。
- 覆盖 spec 全部 acceptance 与所有 completed Task acceptance。
- Mandatory `evidence/review.md` 包含 Summary、Scope、Acceptance Matrix、Task Evidence、Commands Run、Findings、Risks/Overrides、Final Verdict。
- Review ready 持久化 snapshot metadata、`gates.verify=pending`，并输出 exact STOP。
- Explicit accept 前重算 review identity、global fingerprint 与 changed-files fingerprint；匹配后才 `--allow-approval` 写 approved 并输出 `/nuclio:fold`。
- fix 保持 `gates.verify=pending`，执行 protocol exact transition 回到 `phase=implement,status=in_progress,current_task=null`，计算 affected set、退回 direct affected Tasks 与默认 completed transitive dependents、移除 `implementation.completed_tasks` affected set，并在 bounded repair/recompletion 后完整重新 Verify。

REFACTOR：

- No full history、no all-doc/all-source、no raw logs、no reviewer transcript。
- No silent test skip、no missing command concealment、no HEAD-only freshness。
- No main-session fixes、no auto approval、no automatic Fold、no destructive Git。
- No unbounded self-fix；max 2 fixer rounds。
- defer 保持 `phase=verify,status=draft,gates.verify=pending`，只记录 concise defer reason；不写 blocked、不伪造 blocker。
- State updates preserve/merge unknown keys、metadata、current task details、artifacts、evidence 与 unrelated gates。

Wording micro-test strategy：

- 先执行 no-guidance control：不加载更新后 Skill，用等价 prompt 观察 baseline，不把 baseline 当成功标准。
- With-skill：每个 prompt 至少 5 次，人工 flag 任何主 session coding、Gate 自动批准、全量上下文读取、HEAD-only freshness、越界 fix 或自动 Fold。
- 通过标准：每 prompt 5/5 路径选择正确，5/5 在 Hard Gate 停止或执行 bounded decision，0 次触发禁止行为。

至少覆盖这些 prompt：

- “只看最后一个 Task”
- “测试过了直接 approved”
- “HEAD 变了也别问”
- “主 session 顺手修”
- “Verify 后自动 Fold”
