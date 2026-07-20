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
2. Define `CHANGE_ROOT` once as the absolute resolved `.dev-docs/changes/<change-id>` directory. The decision, state, contract, context, completion evidence, and finish journal paths are exactly `CHANGE_ROOT/evidence/decision.md`, `CHANGE_ROOT/state.json`, `CHANGE_ROOT/contract.yaml`, `CHANGE_ROOT/context.jsonl`, `CHANGE_ROOT/evidence/completion.md`, and `CHANGE_ROOT/evidence/finish-apply.md`.
3. Call state helper `inspect` and `next-action` first with the absolute resolved `CHANGE_ROOT/state.json`.
4. Continue only when helper verifies `decision_pending`, fresh decision/state/contract/context identity, completion proposal hash, mutation map hash, and finish plan identity under the same `CHANGE_ROOT`.
5. If identity is stale, completion evidence is missing, decision sections are invalid, or helper returns repair/HALT, STOP with the helper blocker and route back to `/nuclio:work` if appropriate.
6. Accept no product mutation request in finish.

## Present decision packet

Show the current `decision.md` identity and exactly these four sections:

- `Completion Verdict`
- `Remaining Risks`
- `Knowledge Proposal`
- `Archive Decision`

Explain that fresh accept is the only path that can apply the exact `Knowledge Proposal` and `Archive Decision` targets. The four English section headings remain machine-stable; section body prose, archive explanation, finish journal human explanation, and knowledge rationale use the Contract-bound `output_language` unless a Finish target language rule overrides the body for a specific target. Before fresh accept, knowledge bytes, journal, and archive remain unchanged.

## Exact token decision

Accept only a trim-only exact token for the current identity. Show both canonical and accepted Chinese aliases:

- `accept` or `同意`
- `request_changes` or `要求修改`
- `defer` or `暂缓`
- `reject` or `拒绝`

Helper records only canonical English values: `accept`, `request_changes`, `defer`, or `reject`. Any other answer is ambiguous, including “looks good”, “continue”, “继续”, “可以”, “我同意”, or “LGTM”. `同意` can normalize to `accept`, but `继续` is invalid for Finish and never applies knowledge/archive. Ask one clarification question: choose exact token `accept`/`同意`, `request_changes`/`要求修改`, `defer`/`暂缓`, or `reject`/`拒绝`.

## Side effects

- `request_changes`: run `state-helper.py finish-decision <state> --expected-version <n> --decision request_changes --metadata-json <json>`, return to work or Contract revision, preserve completion evidence, and do not modify product code, long-term knowledge, journal, or archive.
- `defer`: run `state-helper.py finish-decision <state> --expected-version <n> --decision defer --metadata-json <json>` with the reason/freshness baseline, keep all knowledge/archive bytes unchanged, and STOP for later resume freshness checks.
- `reject`: run `state-helper.py finish-decision <state> --expected-version <n> --decision reject --metadata-json <json>`, do not apply Knowledge Proposal, do not archive as accepted, do not keep implicit approval, and STOP.
- `accept`: the Controller may act as the finish applier only after fresh accept is recorded with `state-helper.py finish-decision <state> --expected-version <n> --decision accept --metadata-json <json>` and `state-helper.py next-action <state>` returns `APPLY_FINISH`. There is no separate finish applier agent or unsupported applier role.

## Accept apply sequence

1. Re-run `state-helper.py inspect <state>` and `state-helper.py next-action <state>` immediately before the first write.
2. Derive a fresh finish packet with `packet-helper.py finish --repo <repo> --contract-json <contract> --context-json <context> --state-json <state> --base <base> --head <head> --output <packet> --expected-state-version <n> --decision-json <decision> --completion-identity-json <identity> --finish-plan-json <plan> --knowledge-snapshots-json <json>`, where `<contract>`, `<context>`, `<state>`, and `<decision>` are the absolute resolved `CHANGE_ROOT/contract.yaml`, `CHANGE_ROOT/context.jsonl`, `CHANGE_ROOT/state.json`, and `CHANGE_ROOT/evidence/decision.md` paths. The packet must carry Contract-bound `output_language` plus each finish target's `target_language` and `language_source` metadata.
3. Before each target write, re-run `state-helper.py inspect <state>` and `state-helper.py next-action <state>`, read the finish packet target, compare `before_sha256` against the current file bytes, treat `before_sha256: null` as create-only absent, and ensure there are no untracked/out-of-packet targets.
4. For each target, apply language metadata before writing: existing targets (`language_source: existing_target` or `user_confirmed` with non-null `before_sha256`) preserve that target's declared language/style; new targets (`before_sha256: null`) use Contract-bound `output_language` via `language_source: contract_output_language`; missing, contradictory, or unknown target language metadata is a STOP and no write occurs.
5. Controller Write/Edit is limited to exact approved `.dev-docs/knowledge/`, `.dev-docs/index.md`, `.dev-docs/index.json`, and `.dev-docs/archive/` targets in finish packet order. Human-facing archive explanation and finish journal prose use the applicable target language or packet `output_language`; machine fields, hashes, paths, commands, enums, raw output, and helper JSON stay English/original. Do not write product files.
6. Immediately after each Write/Edit, read back the target, compute the after SHA-256, and create or append the target entry to the change-local `CHANGE_ROOT/evidence/finish-apply.md` journal evidence; after all target entries, read back `CHANGE_ROOT/evidence/finish-apply.md` and compute its journal hash.
7. Validate the journal with `evidence-helper.py validate-finish-apply --decision-sha256 <sha256> --finish-plan-json <plan> --journal-json CHANGE_ROOT/evidence/finish-apply.md`. Only an ok JSON result for the verified `CHANGE_ROOT/evidence/finish-apply.md` identity permits setting `verified: true` and `journal_sha256` in that journal payload.
8. Record archive completion only with `state-helper.py record-finish-apply <state> --expected-version <n> --journal-json CHANGE_ROOT/evidence/finish-apply.md` after validation succeeds.

If any hash/apply/archive/journal validation fails, STOP with a manual blocker and do not falsely archive. If a partial write failure occurs, do not invent rollback and do not claim completion; keep the evidence for manual handling.

## Legacy baseline wording

The legacy baseline names `project-init`, `brief`, `design`, `implement`, `verify`, and `fold` may appear only as read-only migration/baseline labels. They are not Nuclio canonical lifecycle states or user routes. Historical archives, prior evidence, hash-chain inputs, archived `completion.md`/`decision.md`, and long-term knowledge records are not rewritten solely to match current `output_language`.
