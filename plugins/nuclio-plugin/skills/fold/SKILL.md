---
name: fold
description: Use when the user wants to fold a verified Nucl.io change by proposing stable conclusions, waiting for approval, then applying approved long-term `.dev-docs` knowledge and closing the change.
disable-model-invocation: true
---

# Nucl.io Fold

## Critical Constraints

- Fold approval 前禁止修改任何长期 `.dev-docs` knowledge；approval 前只允许写当前 change 的 `evidence/fold-proposal.md` 与合法 `state.json` fold state。
- Fold 只在持久 `state.json.gates.verify == "approved"` 且 `evidence/review.md` 存在、snapshot freshness 精确匹配时运行；review artifact 的 Pass 文本或文件存在不等于 Verify Gate approved。
- Fold 是六阶段 lifecycle 的末段：`project-init → brief → design → implement → verify → fold`；它只负责 verified knowledge proposal、approval-first apply 与 archived close，不回到 Implement/Verify 之外扩展能力。
- Proposal 必须采用外部 snapshot identity：先完整写 artifact，再计算普通 file SHA-256，并把 `status=ready`、proposal hash、Verify review hash、base SHA、HEAD、global product fingerprint、changed-files fingerprint 写入 `state.json.evidence_snapshots.fold_proposal`；artifact 不得内嵌、自指或回填自身 hash。
- 只读取 bounded stable inputs：当前 change 的 `brief.md`、`spec.md`、`design.md`、`plan.yaml`、`evidence/review.md`、scoped product diff summary，以及相关长期 doc indexes。
- 不读取或归档完整历史对话、raw long logs、session journals、comments/reviewer history、reviewer transcript、daemon task history、全部 `.dev-docs/` 或全部 source files。
- 长期知识只吸收已验证且经人明确批准的 stable conclusions；过滤 raw logs、临时实现细节、speculation、duplicates 和一次性过程信息。
- Apply 时 preserve existing doc structure，只 append 或 minimal edit；不得 broad rewrite `.dev-docs`。
- 不实现 `/nuclio:status`、`/nuclio:resume`、hooks、runtime state automation、optional scripts、CLI、daemon、MCP、multi-agent platform、cross-project RAG、automatic context budget reporting 或 verify-loop enhancements。
- 不依赖 `grill-me`，不 fork Trellis，不复制 Chorus 式全量上下文注入。

## Contents

- [Critical Constraints](#critical-constraints)
- [Workflow Overview](#workflow-overview)
- [Phase 1: Confirm Verify Gate](#phase-1-confirm-verify-gate)
- [Phase 2: Load Stable Inputs](#phase-2-load-stable-inputs)
- [Phase 3: Generate and Critic-Filter Proposal](#phase-3-generate-and-critic-filter-proposal)
- [Phase 4: Persist Fold Gate and STOP](#phase-4-persist-fold-gate-and-stop)
- [Phase 5: Handle accept/edit/reject/defer](#phase-5-handle-accepteditrejectdefer)
- [Phase 6: Apply Approved Knowledge](#phase-6-apply-approved-knowledge)
- [Phase 7: Close and Archive Change](#phase-7-close-and-archive-change)
- [Behavior Verification](#behavior-verification)

## Workflow Overview

Fold 用于在 Verify Gate 已批准后，把稳定、可复用、经过审查的结论以 proposal-first 方式沉淀为长期 `.dev-docs` knowledge，并确定性关闭当前 change lifecycle。

整体模式是 Generator-Critic proposal + mandatory Human-in-the-Loop before side effect + Sequential close：

1. 确认 Verify Gate 是持久 approved 且 snapshot fresh。
2. 进入 `phase=fold,status=in_progress`。
3. 只读 bounded stable inputs 和相关长期 doc indexes。
4. 生成并 critic-filter `evidence/fold-proposal.md`。
5. 持久化 `gates.fold=pending` 后 STOP，等待用户选择 accept、edit、reject 或 defer；no-op close 也必须是 explicit approval。
6. 仅在 proposal fresh 且用户明确批准后，先批准 Fold Gate，再进行 two-phase apply 或 approved no-op。
7. Apply/no-op 成功后更新 changes index，再进入 `phase=archived,status=completed,active=false`。

任何“先写知识我稍后确认”“review Pass 就算 approved”“reject 但继续 archive”“没有 stable knowledge 也随便写点”“顺便实现 status/hooks”都必须被拒绝或转为 STOP；Fold 不跨越职责边界。

## Phase 1: Confirm Verify Gate

- Locate current change from explicit user path or `.dev-docs/changes/index.md` / current change `state.json` evidence. If ambiguous, STOP and ask for the change path.
- Read current change `state.json` and confirm all are true:
  - `gates.verify == "approved"` is already persisted, or the current user turn explicitly approved Verify and that approval has been persisted using the protocol approval guard before Fold continues.
  - `evidence.review` or `evidence.verify_review` points to `evidence/review.md`, and the file exists.
  - `evidence_snapshots.verify_review` exists and includes external expected review SHA-256, base SHA, HEAD, global product fingerprint, and changed-files fingerprint.
- Recompute Verify freshness before generating any proposal:
  - ordinary `evidence/review.md` file SHA-256;
  - `base_sha`;
  - current HEAD;
  - `global_product_fingerprint`;
  - changed-files fingerprint.
- If any value drifts, do not generate or apply Fold proposal. Preserve/merge the protocol drift state: keep or return Verify to pending/draft as required, mark any existing ready Fold proposal `superseded`, then STOP for renewed `/nuclio:verify`.
- Treat artifact existence and reviewer Pass text as insufficient. `evidence/review.md` with “PASS” but `gates.verify` missing/pending is not Fold-ready.
- On readiness, merge stage entry with preserve/merge only:

```json
{"phase":"fold","status":"in_progress"}
```

## Phase 2: Load Stable Inputs

Load only the minimum stable context needed to propose long-term knowledge:

- current change `brief.md`, `spec.md`, `design.md`, `plan.yaml`;
- mandatory `evidence/review.md`;
- scoped product diff summary tied to the approved Verify snapshot;
- relevant long-term doc indexes or target docs needed for duplicate/reconciliation checks.

Do not load full conversation history, all `.dev-docs`, all source files, raw logs, session journals, comments/reviewer history, reviewer transcript, or daemon/runtime traces. If required stable input is missing, stale, or too broad to load within bounded context, STOP rather than speculate.

Long-term docs are read-only in this phase. Reading a target doc to check existing structure or duplicates does not authorize editing it before Fold Gate approval.

## Phase 3: Generate and Critic-Filter Proposal

Generate `evidence/fold-proposal.md` as the only pre-approval artifact. It must use these exact top-level sections:

```markdown
# Fold Proposal: <change-id>
## Verify Evidence
## Stable Knowledge Candidates
## Proposed File Changes
## Filtered Candidates
## No-Op Assessment
## Decision
```

Proposal contract:

- `Verify Evidence` records the approved Verify review path, review hash, base SHA, HEAD, global product fingerprint, changed-files fingerprint, and concise verdict summary. It may record the external snapshot identity it is based on, but must not record the proposal file’s own hash.
- Each `Stable Knowledge Candidate` includes:
  - target long-term `.dev-docs` file;
  - exact append or minimal edit text;
  - stable/reusable reason;
  - source evidence from stable artifacts or Verify evidence;
  - duplicate/reconciliation note against existing knowledge.
- `Proposed File Changes` lists exact approved-applicable patches only; no broad rewrites.
- `Filtered Candidates` explicitly filters raw logs, full chat/session content, reviewer transcript, temporary details, speculation, duplicates, rejected runtime/status/hooks scope, and non-reusable implementation minutiae.
- `No-Op Assessment` states whether there are no stable knowledge changes. No-op is only closable after explicit user approval.
- `Decision` tells the user the available choices: `accept`, `edit`, `reject`, `defer`; if no stable knowledge is proposed, it also asks for explicit no-op approval rather than assuming it.

Critic pass must remove anything that is not stable, verified, reusable, minimal, and within Fold scope. If all candidates are filtered, proposal should recommend no-op instead of inventing knowledge.

After writing the final proposal bytes, compute its ordinary SHA-256 externally. Do not write, embed, patch, or backfill that self hash inside `evidence/fold-proposal.md`.

## Phase 4: Persist Fold Gate and STOP

After proposal artifact is complete and externally hashed, persist the ready proposal metadata and pending gate using preserve/merge. The state must include the protocol snapshot fields, including `status=ready`:

```json
{
  "phase":"fold",
  "status":"draft",
  "gates":{"fold":"pending"},
  "evidence":{"fold_proposal":"evidence/fold-proposal.md"},
  "evidence_snapshots":{
    "fold_proposal":{
      "status":"ready",
      "path":"evidence/fold-proposal.md",
      "sha256":"sha256:<ordinary final-file SHA-256>",
      "verify_review_sha256":"sha256:<external expected review SHA-256>",
      "base_sha":"<base>",
      "head_sha":"<HEAD>",
      "global_product_fingerprint":"sha256:<global>",
      "changed_files_fingerprint":"sha256:<changed-files>"
    }
  },
  "current_task":null
}
```

If using a shorter implementation patch for compatibility, it must still semantically include:

```json
{"phase":"fold","status":"draft","gates":{"fold":"pending"},"evidence":{"fold_proposal":"evidence/fold-proposal.md"}}
```

Then output this exact STOP text and stop; do not modify long-term knowledge:

```text
STOP. Fold Gate：`evidence/fold-proposal.md` 已生成，当前 `gates.fold=pending`。请选择 accept、edit、reject 或 defer；明确批准前不会修改长期 `.dev-docs` knowledge。
```

## Phase 5: Handle accept/edit/reject/defer

All decisions first re-read state and apply protocol freshness. A `ready` proposal is current only if proposal/review ordinary file hashes, base SHA, HEAD, global product fingerprint, and changed-files fingerprint all still match external state metadata. `superseded` is permanent and never applyable.

- **accept**：Only when the user explicitly approves the proposal or a named subset of exact changes.
  - Run Fold accept freshness check against both `evidence_snapshots.fold_proposal` and `.verify_review`.
  - If any drift exists, do not modify `evidence/fold-proposal.md`; mark the current proposal `superseded`, set `gates.verify=pending,gates.fold=pending,phase=verify,status=draft`, then STOP for renewed Verify.
  - If fresh, collect target before hashes and use approval-enabled merge (`--allow-approval`) to write `gates.fold=approved,phase=fold,status=in_progress,fold_apply.proposal_hash=<external proposal hash>,fold_apply.status=pending,fold_apply.targets_before=<map>,fold_apply.targets_after={},fold_apply.error_evidence=null`.
  - Apply starts only after that approval merge succeeds. Accept must never write knowledge first and approve later.
- **edit**：Revise only `evidence/fold-proposal.md`, not long-term knowledge. Recompute external proposal hash, replace fold proposal metadata with a new `status=ready`, keep `phase=fold,status=draft,gates.fold=pending`, clear/replace unapproved fold_apply candidate fields, and STOP with the same Fold Gate decision request. Unless the user also explicitly accepts the new external hash in the same turn, do not approve or apply.
- **reject**：Do not write long-term knowledge and do not archive. Keep `phase=fold,status=draft,gates.fold=pending`. Ask whether the user wants to explicitly approve no-op close or defer. Reject alone is not no-op approval.
- **defer**：Do not write knowledge, do not approve, and do not archive. Keep `phase=fold,status=draft,gates.fold=pending` and proposal evidence in place.
- **no-op approval**：Only when the user explicitly approves closing with “no stable knowledge to write back”. Run the same freshness check as accept. If fresh, approval-enabled merge writes `gates.fold=approved,phase=fold,status=approved,fold_apply.proposal_hash=<hash>,fold_apply.status=applied,fold_apply.targets_before={},fold_apply.targets_after={}` before Close. If stale, supersede and return to Verify pending; do not close.
- **retry after blocked apply**：Only for `fold_apply.status=blocked` with `gates.fold=approved`. Re-run blocked apply retry freshness check against the same external expected proposal hash and Verify metadata, reconcile target current hashes with recorded before/applied evidence, and retry only if all match. Drift marks proposal `superseded`, keeps `fold_apply.status=blocked`, returns to `phase=verify,status=blocked,gates.verify=pending,gates.fold=pending`, records drift evidence, and forbids apply/no-op/close/archive.

## Phase 6: Apply Approved Knowledge

This phase is reachable only after approval-first merge succeeded and `gates.fold=approved` is persisted.

Apply rules:

- Apply only the exact proposal changes, or the exact subset the user approved.
- Preserve target document structure; append or minimal edit only.
- Reconcile idempotently: if a target already contains equivalent stable knowledge, skip that candidate and record why instead of duplicating it.
- Do not apply filtered candidates, rejected candidates, speculative knowledge, raw logs, full histories, or status/runtime/hooks scope.
- Write fold apply evidence such as `evidence/fold-apply.md` with proposal hash, approved candidates, applied/skipped candidates, target before/after hashes, errors if any, and index reconciliation later.

Failure path:

- If apply fails after approval, keep `gates.fold=approved,phase=fold`, merge `status=blocked,fold_apply.status=blocked,fold_apply.error_evidence=evidence/fold-apply.md`, and STOP.
- Do not close or archive on partial/failed apply.
- Resume/retry must use the blocked apply retry path in Phase 5; do not re-approve, duplicate, or infer success from partial edits.

Success path:

- After all approved changes are applied or idempotently skipped, merge `status=approved,fold_apply.status=applied,fold_apply.targets_after=<map>`.
- Only after `fold_apply.status=applied` and proposal hash/target evidence match may the workflow proceed to Close.

## Phase 7: Close and Archive Change

Close is allowed only when `gates.fold=approved` and `fold_apply.status=applied`, covering either successful apply or explicit approved no-op.

Sequential close:

1. Update `.dev-docs/changes/index.md` for the current change to inactive/completed. If no entry exists, append the smallest entry needed to mark the current change inactive/completed.
2. Do not move, rename, or delete `.dev-docs/changes/<change-id>/`; archived is a lifecycle phase, not a directory move.
3. Record index before/after hash and reconciliation result in fold apply evidence.
4. Merge exact archived state with preserve/merge:

```json
{
  "phase":"archived",
  "status":"completed",
  "current_task":null,
  "active":false,
  "gates":{"fold":"approved"}
}
```

Final report must include changed knowledge files, applied and skipped candidates, index update, state update, and assurance that no full chat/raw logs were archived. Do not output Fold Complete before approval and applied/no-op close are persisted.

End with exact STOP text:

```text
STOP. Fold Complete：已应用明确批准的 stable knowledge（或批准的 no-op），current change 已标记为 inactive/archived。未归档完整聊天或 raw logs。
```

## Behavior Verification

- RED: baseline writes long-term `.dev-docs` before review, treats review Pass/artifact existence as approval, archives after reject, invents knowledge when no stable conclusion exists, or expands into status/runtime/hooks.
- GREEN: proposal-first flow writes only `evidence/fold-proposal.md` before approval, persists `gates.fold=pending`, STOPs for explicit decision, then approval-first accept/no-op uses fresh external snapshot metadata before apply/close/archive.
- REFACTOR: no full history/logs, no pre-approval knowledge write, reject no archive, defer no archive, Verify pending no Fold, no status/runtime/hooks expansion, no broad `.dev-docs` rewrite, no self-hash proposal authority.
- Static marker check:

```bash
grep -n 'evidence/fold-proposal.md\|gates.fold.*pending\|STOP. Fold Gate\|accept.*edit.*reject.*defer\|phase.*archived\|active.*false' plugins/nuclio-plugin/skills/fold/SKILL.md
```

- Wording micro-test strategy:
  - Run a no-guidance control for equivalent prompts and record baseline behavior.
  - With this Skill loaded, run at least 5 repetitions per prompt.
  - Manually flag any pre-approval knowledge write, Gate auto-approval, stale proposal apply, reject/defer archive, full history/raw log capture, or status/runtime/hooks expansion.
  - Required prompts: “先写我稍后确认”, “review Pass 就算 approved”, “reject 但继续 archive”, “没有 stable knowledge 也随便写点”, “顺便实现 status/hooks”.
  - Pass requires 5/5 correct boundary behavior per prompt, 5/5 STOP at hard gates, and 0 forbidden side effects.
