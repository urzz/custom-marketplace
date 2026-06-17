---
name: close
description: Use when build work is done and evidence exists, to summarize the change and prepare a memory patch for approval.
---

# Nucl.io Close

## Goal
Generate `.nuclio/changes/<change-id>/close.md` and `.nuclio/changes/<change-id>/memory.patch.md` from the completed change evidence, update workflow state, and stop at Memory Approval.

## Inputs
- The completed change diff and any final repository context needed to summarize it accurately.
- `.nuclio/changes/<change-id>/spec.md`, `design.md`, and `plan.yaml`.
- `.nuclio/changes/<change-id>/evidence/verify.md` and `evidence/review.md`.
- Existing `.nuclio/changes/<change-id>/state.json` and `events.jsonl`.

## Outputs
- `.nuclio/changes/<change-id>/close.md`
- `.nuclio/changes/<change-id>/memory.patch.md`
- `.nuclio/changes/<change-id>/state.json`
- `.nuclio/changes/<change-id>/events.jsonl`

## Rules
- Confirm the change has enough evidence to close before drafting final artifacts.
- If verify or review evidence is missing, incomplete, or failed, do not claim the change is complete.
- `close.md` is the final workflow summary artifact; keep it grounded in the approved scope and actual evidence.
- `memory.patch.md` is a candidate patch for Memory Approval, not a direct instruction to write `.dev-docs/`.
- Memory Approval must be represented as canonical `approved.memory === true` in `.nuclio/changes/<change-id>/state.json` after explicit user approval.
- Use typed events and/or `context-report.md` to identify which `.dev-docs` knowledge was loaded, skipped, stale, or missing before proposing memory updates.
- Append typed `close.generated`, `memory_patch.generated`, and `memory_patch.approved` events when those facts occur.
- Only capture stable, verified, reusable project knowledge in `memory.patch.md`.
- Do not write `.dev-docs/` during close.
- Do not reopen spec, design, or build scope during close; if evidence invalidates completion, stop and request human direction.
- When generating stage artifacts, prefer the matching templates under `templates/` over free-form drafting.

## Workflow
1. Inspect the target change, final diff, and latest change state.
2. Confirm verify and review evidence exists and reflects the current change state.
3. Generate `.nuclio/changes/<change-id>/close.md` from the close template, summarizing final outcome, acceptance mapping, verification, review, and follow-up limits.
4. Generate `.nuclio/changes/<change-id>/memory.patch.md` from the memory patch template, limited to approved-memory candidates only.
5. Update `.nuclio/changes/<change-id>/state.json` and `events.jsonl` to record that close artifacts are prepared and waiting for Memory Approval.
6. Stop for Memory Approval. Close only prepares the summary and candidate patch; it does not apply memory updates.

## Stop Condition
Pause at Memory Approval. Do not write `.dev-docs/`, do not auto-apply memory updates, and do not advance beyond close until the user explicitly approves the memory patch and chooses the next step.
