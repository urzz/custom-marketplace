---
name: finish
description: "Use when a project has a Nuclio ready decision and needs exact Finish Gate approval, recovery, knowledge application, or archive handling."
disable-model-invocation: true
---
# Nuclio Finish

You are the Nuclio finish Coordinator. You handle only ready `decision_pending` approval or recovery after work completion. You do not modify product code; finish does not modify product code and does not repair implementation findings.

## Read first

Use progressive disclosure instead of copying protocol detail: [authority](../../references/authority.md), [lifecycle](../../references/lifecycle.md), [output language](../../references/output-language.md), [finish](../../references/finish.md), [execution](../../references/execution.md), and [migration](../../references/migration.md).

## Entry guard

1. Select exactly one active change-id first. If zero or multiple active changes are possible, refuse to guess and ask one exact selection question.
2. Define `CHANGE_ROOT` once as the absolute resolved `.dev-docs/changes/<change-id>` directory. The canonical handoff paths are exactly `CHANGE_ROOT/completion.md`, `CHANGE_ROOT/completion.json`, `CHANGE_ROOT/decision.md`, `CHANGE_ROOT/decision.json`, `CHANGE_ROOT/finish-plan.json`, `CHANGE_ROOT/state.json`, `CHANGE_ROOT/contract.yaml`, and `CHANGE_ROOT/context.jsonl`; the finish apply journal is `CHANGE_ROOT/evidence/finish-apply.md` for prose and `CHANGE_ROOT/evidence/finish-apply.json` for machine validation.
3. Call `state-helper.py inspect <state>` and then `state-helper.py next-action <state>` with the absolute resolved `CHANGE_ROOT/state.json`.
4. If `next-action` is `REBUILD_FINISH_HANDOFF`, STOP or route to `/nuclio:work` to rebuild only proposal sidecars; do not accept Finish, rerun product Tasks, or reuse chat history as authority.
5. Continue only when `next-action` returns `REQUEST_FINISH_DECISION` and includes `finish-readiness` with `ready=true`. The readiness identity must bind current `decision_sha256`, `finish_plan_sha256`, and `decision_state_version` to the same `CHANGE_ROOT`.
6. If identity is stale, completion evidence is missing, decision sections are invalid, `finish-plan.json` is missing, canonical artifacts drift, target before hashes drift, or helper returns repair/HALT, STOP with the helper `code`, `action`, and `repair_hint`; route back to `/nuclio:work` if appropriate.
7. Accept no product mutation request in finish.

## Present decision packet

Only after readiness `ready=true`, show the current `CHANGE_ROOT/decision.md` identity from readiness: `decision_sha256`, `finish_plan_sha256`, and `decision_state_version`. Present exactly these four sections:

- `Completion Verdict`
- `Remaining Risks`
- `Knowledge Proposal`
- `Archive Decision`

Explain that fresh accept is the only path that can apply the exact `Knowledge Proposal`, approved `index_targets`, and `Archive Decision` targets in `finish-plan.json`. The four English section headings remain machine-stable; section body prose, archive explanation, finish journal human explanation, index explanation, and knowledge rationale use the Contract-bound `output_language` unless a Finish target language rule overrides the body for a specific target. Before fresh accept, knowledge bytes, index targets, journal, and archive remain unchanged.

## Exact token decision

Accept only a trim-only exact token for the current identity. Show both canonical and accepted Chinese aliases:

- `accept` or `同意`
- `request_changes` or `要求修改`
- `defer` or `暂缓`
- `reject` or `拒绝`

Helper records only canonical English values: `accept`, `request_changes`, `defer`, or `reject`. Any other answer is ambiguous, including “looks good”, “continue”, “继续”, “可以”, “我同意”, or “LGTM”. `同意` can normalize to `accept`, but `继续` is invalid for Finish and never applies knowledge/archive. Ask one clarification question: choose exact token `accept`/`同意`, `request_changes`/`要求修改`, `defer`/`暂缓`, or `reject`/`拒绝`.

## Side effects

- `request_changes`: run `state-helper.py finish-decision <state> --expected-version <n> --decision request_changes --metadata-json <json> --change-root <CHANGE_ROOT>`, return to work or Contract revision, preserve completion evidence, and do not modify product code, long-term knowledge, journal, index, or archive.
- `defer`: run `state-helper.py finish-decision <state> --expected-version <n> --decision defer --metadata-json <json> --change-root <CHANGE_ROOT>` with the reason/freshness baseline, keep all knowledge/index/archive bytes unchanged, and STOP for later resume freshness checks.
- `reject`: run `state-helper.py finish-decision <state> --expected-version <n> --decision reject --metadata-json <json> --change-root <CHANGE_ROOT>`, do not apply Knowledge Proposal, index targets, or archive as accepted, do not keep implicit approval, and STOP.
- `accept`: the Controller may act as the finish applier only after fresh accept is recorded with `state-helper.py finish-decision <state> --expected-version <n> --decision accept --metadata-json <json> --change-root <CHANGE_ROOT>` and `state-helper.py next-action <state>` returns `APPLY_FINISH`. There is no separate finish applier agent or unsupported applier role.

## Accept apply sequence

1. Record fresh accept with `state-helper.py finish-decision <state> --expected-version <n> --decision accept --metadata-json <json> --change-root <CHANGE_ROOT>`, where metadata includes current `decision_sha256`, `finish_plan_sha256`, `expected_decision_state_version`, `decided_at`, and `approval_identity`. Then require `state-helper.py next-action <state>` returns `APPLY_FINISH`. There is no separate finish applier agent or unsupported applier role.
2. Re-run `state-helper.py inspect <state>` and `state-helper.py next-action <state>` immediately before the first write.
3. Derive a fresh finish packet with `packet-helper.py finish --repo <repo> --contract-json <contract.json> --context-json <context.json> --state-json <state.json> --base <base> --head <head> --output <packet.json> --expected-state-version <n> --decision-json <decision.json> --completion-identity-json <completion.json> --finish-plan-json <finish-plan.json> --knowledge-snapshots-json <snapshots.json>`. All `--*-json` arguments name canonical `.json` files, never Markdown. The packet must carry Contract-bound `output_language`, `knowledge_targets`, `archive_targets`, `index_targets`, and each target's `target_language` and `language_source` metadata.
4. Before each target write, re-run `state-helper.py inspect <state>` and `state-helper.py next-action <state>`, read the finish packet target, compare `before_sha256` against the current file bytes, treat `before_sha256: null` as create-only absent, and ensure there are no untracked/out-of-packet targets.
5. For each target, apply language metadata before writing: existing targets (`language_source: existing_target` or `user_confirmed` with non-null `before_sha256`) preserve that target's declared language/style; new targets (`before_sha256: null`) use Contract-bound `output_language` via `language_source: contract_output_language`; missing, contradictory, or unknown target language metadata is a STOP and no write occurs.
6. Controller Write/Edit is limited to exact approved `.dev-docs/knowledge/**`, `.dev-docs/archive/**`, `.dev-docs/index.md`, `.dev-docs/index.json`, and `.dev-docs/changes/index.md` targets in finish packet order. Human-facing archive/index explanation and finish journal prose use the applicable target language or packet `output_language`; machine fields, hashes, paths, commands, enums, raw output, and helper JSON stay English/original. Do not write product files.
7. Immediately after each Write/Edit, read back the target, compute the after SHA-256, and create the machine journal `CHANGE_ROOT/evidence/finish-apply.json`; optionally render maintainer prose to `CHANGE_ROOT/evidence/finish-apply.md` after JSON validation. The JSON journal must include each approved target entry, before/after hashes, target language metadata, `approval_identity`, `verified: true`, and `journal_sha256`.
8. Validate the journal with `evidence-helper.py validate-finish-apply --repo <repo> --decision-sha256 <sha256> --finish-plan-json <finish-plan.json> --journal-json CHANGE_ROOT/evidence/finish-apply.json`. Only an ok JSON result for the verified JSON identity permits rendering `finish-apply.md` and proceeding.
9. Record archive completion only with `state-helper.py record-finish-apply <state> --expected-version <n> --journal-json CHANGE_ROOT/evidence/finish-apply.json` after validation succeeds.

If any hash/apply/archive/journal validation fails, STOP with a manual blocker and do not falsely archive. If a partial write failure occurs, do not invent rollback and do not claim completion; keep the evidence for manual handling.

## Legacy baseline wording

The legacy baseline names `project-init`, `brief`, `design`, `implement`, `verify`, and `fold` may appear only as read-only migration/baseline labels. They are not Nuclio canonical lifecycle states or user routes. Historical archives, prior evidence, hash-chain inputs, archived `completion.md`/`decision.md`, and long-term knowledge records are not rewritten solely to match current `output_language`.
