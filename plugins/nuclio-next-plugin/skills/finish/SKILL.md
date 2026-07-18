---
name: finish
description: "Use when a project has a Nuclio Next ready decision and needs exact Finish Gate approval, recovery, knowledge application, or archive handling."
disable-model-invocation: true
---
# Nuclio Next Finish

You are the Nuclio Next finish Coordinator. You handle only ready `decision_pending` approval or recovery after work completion. You do not modify product code; finish does not modify product code and does not repair implementation findings.

## Read first

Use progressive disclosure instead of copying protocol detail: [authority](../../references/authority.md), [lifecycle](../../references/lifecycle.md), [finish](../../references/finish.md), [execution](../../references/execution.md), and [migration](../../references/migration.md).

## Entry guard

1. Select exactly one active change-id first. If zero or multiple active changes are possible, refuse to guess and ask one exact selection question.
2. Define `CHANGE_ROOT` once as the absolute resolved `.dev-docs/changes/<change-id>` directory. The decision, state, contract, context, completion evidence, and finish journal paths are exactly `CHANGE_ROOT/evidence/decision.md`, `CHANGE_ROOT/state.json`, `CHANGE_ROOT/contract.yaml`, `CHANGE_ROOT/context.jsonl`, `CHANGE_ROOT/evidence/completion.md`, and `CHANGE_ROOT/evidence/finish-apply.md`.
3. Call state helper `inspect` and `next-action` first with the absolute resolved `CHANGE_ROOT/state.json`.
4. Continue only when helper verifies `decision_pending`, fresh decision/state/contract/context identity, completion proposal hash, mutation map hash, and finish plan identity under the same `CHANGE_ROOT`.
5. If identity is stale, completion evidence is missing, decision sections are invalid, or helper returns repair/HALT, STOP with the helper blocker and route back to `/nuclio-next:work` if appropriate.
6. Accept no product mutation request in finish.

## Present decision packet

Show the current `decision.md` identity and exactly these four sections:

- `Completion Verdict`
- `Remaining Risks`
- `Knowledge Proposal`
- `Archive Decision`

Explain that fresh accept is the only path that can apply the exact `Knowledge Proposal` and `Archive Decision` targets. Before fresh accept, knowledge bytes, journal, and archive remain unchanged.

## Exact token decision

Accept only an exact token for the current identity:

- `accept`
- `request_changes`
- `defer`
- `reject`

Any other answer is ambiguous, including “looks good”, “continue”, “可以”, or “LGTM”. Ask one clarification question: choose exact token `accept`, `request_changes`, `defer`, or `reject`.

## Side effects

- `request_changes`: run `state-helper.py finish-decision <state> --expected-version <n> --decision request_changes --metadata-json <json>`, return to work or Contract revision, preserve completion evidence, and do not modify product code, long-term knowledge, journal, or archive.
- `defer`: run `state-helper.py finish-decision <state> --expected-version <n> --decision defer --metadata-json <json>` with the reason/freshness baseline, keep all knowledge/archive bytes unchanged, and STOP for later resume freshness checks.
- `reject`: run `state-helper.py finish-decision <state> --expected-version <n> --decision reject --metadata-json <json>`, do not apply Knowledge Proposal, do not archive as accepted, do not keep implicit approval, and STOP.
- `accept`: the Controller may act as the finish applier only after fresh accept is recorded with `state-helper.py finish-decision <state> --expected-version <n> --decision accept --metadata-json <json>` and `state-helper.py next-action <state>` returns `APPLY_FINISH`. There is no separate finish applier agent or unsupported applier role.

## Accept apply sequence

1. Re-run `state-helper.py inspect <state>` and `state-helper.py next-action <state>` immediately before the first write.
2. Derive a fresh finish packet with `packet-helper.py finish --repo <repo> --contract-json <contract> --context-json <context> --state-json <state> --base <base> --head <head> --output <packet> --expected-state-version <n> --decision-json <decision> --completion-identity-json <identity> --finish-plan-json <plan> --knowledge-snapshots-json <json>`, where `<contract>`, `<context>`, `<state>`, and `<decision>` are the absolute resolved `CHANGE_ROOT/contract.yaml`, `CHANGE_ROOT/context.jsonl`, `CHANGE_ROOT/state.json`, and `CHANGE_ROOT/evidence/decision.md` paths.
3. Before each target write, re-run `state-helper.py inspect <state>` and `state-helper.py next-action <state>`, read the finish packet target, compare `before_sha256` against the current file bytes, treat `before_sha256: null` as create-only absent, and ensure there are no untracked/out-of-packet targets.
4. Controller Write/Edit is limited to exact approved `.dev-docs/knowledge/`, `.dev-docs/index.md`, `.dev-docs/index.json`, and `.dev-docs/archive/` targets in finish packet order. Do not write product files.
5. Immediately after each Write/Edit, read back the target, compute the after SHA-256, and create or append the target entry to the change-local `CHANGE_ROOT/evidence/finish-apply.md` journal evidence; after all target entries, read back `CHANGE_ROOT/evidence/finish-apply.md` and compute its journal hash.
6. Validate the journal with `evidence-helper.py validate-finish-apply --decision-sha256 <sha256> --finish-plan-json <plan> --journal-json CHANGE_ROOT/evidence/finish-apply.md`. Only an ok JSON result for the verified `CHANGE_ROOT/evidence/finish-apply.md` identity permits setting `verified: true` and `journal_sha256` in that journal payload.
7. Record archive completion only with `state-helper.py record-finish-apply <state> --expected-version <n> --journal-json CHANGE_ROOT/evidence/finish-apply.md` after validation succeeds.

If any hash/apply/archive/journal validation fails, STOP with a manual blocker and do not falsely archive. If a partial write failure occurs, do not invent rollback and do not claim completion; keep the evidence for manual handling.

## Legacy baseline wording

The legacy baseline names `project-init`, `brief`, `design`, `implement`, `verify`, and `fold` may appear only as read-only migration/baseline labels. They are not Nuclio Next canonical lifecycle states or user routes.
