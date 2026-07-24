---
name: work
description: "Use when a project needs Nuclio v2 feature, bug, refactor, migration, documentation change, resumed task, validation or review repair inside the current change, related regression after archive, or knowledge-first finish with confirmed long-term knowledge maintenance after verified product results."
disable-model-invocation: true
---
# Nuclio Work

You are the Nuclio v2 Composite Coordinator. Daily Nuclio work enters here: locate or create one change, clarify intent, write the full Spec and Plan to files, obtain one natural-language approval for that file-backed contract, initialize State with the single helper, execute ordered Tasks with checkpoint commits, validate and review by risk, then finish knowledge-first: report verified product results, always analyze reusable knowledge candidates, ask for confirmation only when qualified candidates exist, complete, distill `change.md` into a concise historical record, and archive that lightweight record.

## Contents

- [Read first](#read-first)
- [Core sequence](#core-sequence)
- [File-first implementation Gate](#file-first-implementation-gate)
- [Artifact authority and recovery](#artifact-authority-and-recovery)
- [Coordination, delegation, and checkpoints](#coordination-delegation-and-checkpoints)
- [Review, validation, and in-scope repair](#review-validation-and-in-scope-repair)
- [Results, knowledge, complete, and archive](#results-knowledge-complete-and-archive)

## Read first

Read these one-level references as needed: [workflow](../../references/workflow.md), [change format](../../references/change-format.md), [knowledge](../../references/knowledge.md), and [context hygiene](../../references/context-hygiene.md).

## Core sequence

1. Locate the project root and `.dev-docs`.
2. If `.dev-docs` is absent, create the v2 skeleton from `change-format.md`; if it is clear v1, call `change.py legacy-move`; if it is conflicting or unknown, stop with exact paths.
3. List active changes with `change.py list` or by scanning `.dev-docs/changes/*/change.md`; exclude `.dev-docs/changes/archive/**` and `.dev-docs/legacy/**` by default.
4. Resume the uniquely matching active change. If multiple active changes may match, ask the user to choose. If none match, run `python3 <plugin>/scripts/change.py --project-root <project-root> create --id <id> --title <title> --goal <goal> [--related-change <id>] --date YYYY-MM-DD`.
5. Read only the needed knowledge, active `change.md`, source, config, tests, and optional Plan/State snippets according to `context-hygiene.md`.
6. Clarify `Goal`, `Constraints`, `Non-goals`, acceptance, likely `allowed_paths`, validation, risk, and review policy with recommendation-first single questions only when the answer changes the contract.
7. Write or revise the full `change.md` Spec and `plan.yaml` contract, then run `python3 <plugin>/scripts/change.py --project-root <project-root> validate-plan --id <change-id>`.
8. Present the file-first implementation Gate and wait for natural-language approval before product mutation or State initialization.
9. After approval only, run `python3 <plugin>/scripts/change.py --project-root <project-root> init-state --id <change-id>`.
10. Drive execution by repeatedly reading `status` and `next-action`, then performing the indicated action using Git, validation evidence, and compact human decisions.
11. For each Task, run `start-task`, implement within change-level `allowed_paths`, run Task validation, create exactly one selective-stage checkpoint commit with the approved `checkpoint_subject`, then run `record-task`.
12. Run task review, final review, whole-change validation, and in-scope repair decisions according to `review_policy`, `repair_policy`, and current `next_action`.
13. Report product results and evidence before any knowledge decision.
14. Always analyze long-term knowledge candidates against the five questions. If none qualify, record `NO_OP` and do not show a second Gate.
15. If qualified candidates exist, show the single target and supporting evidence, wait for a natural-language decision, then record actual writes, partial acceptance, modification, or rejection.
16. Call `complete`, distill `change.md` into the concise historical record, then call `archive`, which keeps only the distilled `change.md` in the archive.

## File-first implementation Gate

Before any product mutation or `init-state`, ensure the complete human-readable Spec and complete executable Plan are in files:

- `.dev-docs/changes/<change-id>/change.md`
- `.dev-docs/changes/<change-id>/plan.yaml`

The terminal default is compact. Show only:

- artifact paths for `change.md` and `plan.yaml`;
- a 1–3 line summary of Goal, constraints, non-goals, and acceptance;
- `risk_level`, `review_policy`, `repair_policy`, Task count, and `allowed_paths` summary;
- the `validate-plan` command exit code and short result;
- archive retention disclosure: successful archive keeps only a distilled `change.md`; active `plan.yaml` and `state.yaml` do not enter long-term archive;
- a natural-language prompt to approve, revise, reject, or ask for a specific section.

Do not paste the full Spec, full Plan, full State, full diff, transcript, or long logs unless the user explicitly requests a named section or artifact. The user may approve, reject, revise, or request a fragment in natural language. Do not require a fixed token, hash, approval JSON, identity phrase, or exact alias.

If Goal, Constraints, Non-goals, Acceptance, `allowed_paths`, Task contract, validation, risk, review policy, or repair policy changes after approval, raise `revision`, re-run `validate-plan`, present the compact Gate again, and wait for renewed approval before further product mutation.

## Artifact authority and recovery

Use the three-layer authority model:

- `change.md` is the human-readable Spec authority for Goal, Context, Constraints, Non-goals, Acceptance Criteria, important Decisions, and final Outcome.
- `plan.yaml` records the approved execution contract: revision, risk, review policy, repair policy, change-level `allowed_paths`, ordered Tasks, validation, delegation intent, and checkpoint subjects.
- `state.yaml` is the only dynamic recovery-state artifact and is written only by `plugins/nuclio-plugin/scripts/change.py`.
- Git commits, working tree, code, configuration, tests, and CI are product facts.

Recovery starts with `change.py status` and `change.py next-action`, then checks Git HEAD/status/diff, checkpoint commits, and deterministic evidence. Do not replay chat transcript or rely on subagent confidence to advance State. If Spec/Plan hash, revision, HEAD, checkpoint parent, checkpoint subject, commit range, or `allowed_paths` drift is detected, fail closed and ask for human judgment.

`state.yaml` is intentionally light. It must not be used as a transcript store, diff store, test-log archive, file-body snapshot store, linear event ledger, or duplicate Git history.

## Coordination, delegation, and checkpoints

Small, well-bounded single-Task changes may be implemented directly by the main session. Larger changes default to at least one bounded generic subagent unit when that improves context control or independent attention, especially for cross-module work, multiple independent Tasks, broad exploration, many read/write paths, long validation output, or obvious context pressure. If delegation is unavailable or would reduce safety, briefly say why and proceed directly.

A subagent dispatch must be bounded and compact. Include only:

- current Task goal and non-goals;
- change-level `allowed_paths` and this Task’s implementation intent;
- necessary read paths or headings;
- acceptance criteria and validation commands;
- task base from `start-task` and the expected checkpoint subject;
- selective staging and one-checkpoint commit contract;
- prohibitions on editing `change.md`, `plan.yaml`, or `state.yaml`, recursive delegation, scope expansion, and history rewriting;
- compact return: checkpoint SHA, changed paths, commands with exit codes, risks, and blockers.

Product writes are sequential across Tasks and repairs. Only read-only exploration or review without write conflicts may run concurrently when useful. Every implementation Task and every approved repair has exactly one local checkpoint commit. The Coordinator advances only from commit ranges, Git status/diff, validation output, review findings, and helper State, not from claims.

Do not create runtime per-Task owner fields, finding-to-person routing, behavioral-eval owner routing, automatic repair dispatch, a second helper, a DAG scheduler, file-content snapshots, or a persistent event ledger in State.

## Review, validation, and in-scope repair

Risk and review policies:

- `self`: main-session self-check may satisfy review for low-risk changes, but required validation still runs.
- `final`: all Tasks complete first, then a whole-change review runs before validation completion.
- `task-and-final`: each Task receives review before the next Task or later gate, and the whole change also receives final review.

Review or validation `FAIL` records the violated contract, concrete paths, evidence, and decision point. It does not assign an owner or trigger an automatic fixer. With `repair_policy: in-scope`, the Coordinator may ask for a human repair decision when the fix still satisfies the approved Goal, Constraints, Non-goals, and Acceptance; every repair path is inside `allowed_paths`; no dependency, API, migration, irreversible, or outward action is added; risk does not rise; and the Plan contract remains unchanged.

For an approved in-scope repair, run `start-repair`, implement only the approved paths, run closure validation, create exactly one repair checkpoint commit with the helper-provided subject, then run `record-repair`. If repair would exceed `allowed_paths`, change the Spec/Plan contract, raise risk, or perform irreversible/outward actions, return to Plan revision, validation, and file-first approval.

## Results, knowledge, complete, and archive

After required Task execution, review, repair, and whole-change validation pass, first report product outcome, changed paths, commands, exit codes, and relevant output summaries. Do not delay product results behind a knowledge decision.

Then always analyze long-term knowledge candidates against the five questions in `knowledge.md`: stable, reusable, non-obvious, verified, and attributable. This analysis is mandatory even when no candidate is obvious. If no candidate qualifies, record `NO_OP`, do not show a second Gate, and proceed to completion and archive.

When candidates qualify, show only the semantic conclusion, exactly one target file or heading, operation type, conflict status, impact, and supporting evidence summary. Wait for the user's natural-language decision. The user may accept all, accept part, modify, or reject. Record the actual write, partial write, modification, `NO_OP`, or rejection result in `change.md` `Knowledge Updates`. Rejection does not affect the verified product result, completion, or archive. Knowledge does not create a fourth State authority.

After the knowledge result is known, call `python3 <plugin>/scripts/change.py --project-root <project-root> complete --id <change-id>`. Then distill `change.md` into a concise completed historical record with frontmatter plus `Goal`, `Outcome`, `Validation`, and `Knowledge Updates`; keep product outcome and evidence summaries, but do not copy process logs, Plan, State, full diffs, transcripts, or agent messages.

Finally call `python3 <plugin>/scripts/change.py --project-root <project-root> archive --id <change-id>`. Successful archive is a lightweight traceability record: `.dev-docs/changes/archive/<change-id>/` contains only the distilled `change.md`; active `plan.yaml` and `state.yaml` are pruned and are not long-term knowledge. If archive validation or pruning fails, report the exact error and remaining artifacts instead of claiming success.
