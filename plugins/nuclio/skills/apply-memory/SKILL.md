---
name: apply-memory
description: Use when the user has approved an initial dev docs patch or memory patch and wants those updates applied to .dev-docs.
---

# Nucl.io Apply Memory

## Goal
Apply only approved updates from `.nuclio/project/initial-dev-docs.patch.md` or `.nuclio/changes/<change-id>/memory.patch.md` into `.dev-docs/`, while preserving the approval boundary between proposing knowledge and writing persistent project memory.

## Inputs
- An approved `.nuclio/project/initial-dev-docs.patch.md` or `.nuclio/changes/<change-id>/memory.patch.md`.
- The relevant approval context from the user, including any accepted edits.
- Existing `.dev-docs/` files and `.dev-docs/index.md` when updates need to be merged into the current memory set.

## Outputs
- Approved `.dev-docs/` document updates.
- `.dev-docs/index.md` updates when new or renamed memory files change navigation.

## Rules
- Do not write `.dev-docs/` without approval.
- Only apply updates that were explicitly accepted or edited and then confirmed by the user.
- Require an explicit approval decision for each proposed memory change: `accept`, `reject`, `edit`, or `defer`.
- Run Bootstrap Check first with `node plugins/nuclio/scripts/bootstrap-check.mjs` and confirm the approved source maps to a valid project init or active close workflow.
- Validate the patch before applying it: use `node plugins/nuclio/scripts/validate-memory-patch.mjs .nuclio/changes/<change-id>/memory.patch.md` for change memory patches, and ensure Project Init patches expose accepted/edited `.dev-docs` targets.
- Apply only accepted or explicitly edited memory changes after canonical `approved.memory === true` or Project Init `approved.initial_dev_docs === true`, with matching scoped target paths.
- When adding or changing leaf docs, update the relevant second-level index and frontmatter consistency in the same change.
- Append typed `memory.applied` events to the relevant `.nuclio/project/events.jsonl` or `.nuclio/changes/<change-id>/events.jsonl` using `node plugins/nuclio/scripts/append-event.mjs <events-file> '<json>'`.
- Treat patch files as proposed changes, not automatic write instructions.
- If a proposed update is rejected, omit it instead of partially applying it.
- If index or navigation changes are needed, update `.dev-docs/index.md` in the same step as the new document changes.
- Do not generate new requirement, design, build, or close artifacts while applying memory.
- Keep updates scoped to approved memory content; do not smuggle in unrelated doc edits.

## Workflow
1. Confirm whether the approved source is `.nuclio/project/initial-dev-docs.patch.md` or `.nuclio/changes/<change-id>/memory.patch.md`.
2. Confirm which proposed updates were accepted as-is and which were edited before approval.
3. Apply only the approved `.dev-docs/` updates.
4. If navigation changed, update `.dev-docs/index.md` together with the applied memory files.
5. Stop after the approved memory updates are written.

## Stop Condition
Stop after applying the approved memory updates. If approval is missing, ambiguous, or only partial, do not write `.dev-docs/`; instead, report what still needs confirmation.
