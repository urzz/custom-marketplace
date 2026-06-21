---
name: design
description: Use after Spec Approval to turn an approved Nucl.io change spec into architecture-grounded design and plan artifacts.
---

# Nucl.io Design

## Goal
Turn an approved change spec into architecture-grounded design artifacts in `.nuclio/changes/<change-id>/design.md` and `.nuclio/changes/<change-id>/plan.yaml`, without implementing application code.

## Inputs
- The approved `.nuclio/changes/<change-id>/spec.md`.
- Current repository architecture, relevant code, and existing project context.
- Existing `.nuclio/changes/<change-id>/state.json` and `events.jsonl` if design work was started before.

## Outputs
- `.nuclio/changes/<change-id>/design.md`
- `.nuclio/changes/<change-id>/plan.yaml`
- `.nuclio/changes/<change-id>/state.json`
- `.nuclio/changes/<change-id>/events.jsonl`

## Rules
- Confirm Spec Approval before starting design work.
- Treat both approvals as hard gates: Spec Approval is required before producing design artifacts, and Design Approval is required before any build, implementation, or execution work.
- Re-ground every design decision in the current codebase and project architecture instead of relying only on the approved spec text.
- If `.dev-docs/index.md` exists, use it as the root index for context selection instead of scanning all `.dev-docs/` files.
- Do not modify application code.
- Do not directly write `.dev-docs/`.
- `plan.yaml` must be an approval-ready task graph with explicit dependencies, acceptance linkage, and execution ordering intent, not a loose TODO list.
- Run Bootstrap Check first with `node plugins/nuclio/scripts/bootstrap-check.mjs` and confirm the target change is the active, valid workflow before design writes.
- `plan.yaml` tasks must include `type`, `risk`, `allowed_paths`, `forbidden_paths`, `acceptance`, `verify`, and `review_focus` when applicable, because Build and guard use those fields for scope control; validate with `node plugins/nuclio/scripts/validate-plan.mjs .nuclio/changes/<change-id>/plan.yaml --section tasks`.
- Design Approval must update canonical change state with `phase: "build"`, `approved.design: true`, and `gate: null` only after explicit user approval; write it through `node plugins/nuclio/scripts/write-state.mjs <state-file> '<json>'`.
- Append typed `design.generated` and `design.approved` events with `node plugins/nuclio/scripts/append-event.mjs .nuclio/changes/<change-id>/events.jsonl '<json>'` when those facts occur.
- Keep design focused on architecture, module boundaries, interfaces, risks, and verification strategy.
- When generating stage artifacts, prefer the matching templates under `templates/` over free-form drafting.

## Workflow
1. Confirm the target change has an approved `spec.md` and inspect the latest change state.
2. Re-read the relevant code, architecture, and repository constraints for codebase-grounded design.
3. Map current architecture, relevant modules, interfaces, and constraints that shape the change.
4. Generate `design.md` from the design template.
5. Generate `plan.yaml` from `templates/plan-template.yaml` as an architecture-grounded task graph, populating path boundaries for every task.
6. Update the minimum change state and stop for Design Approval before any build or implementation work begins.

## Stop Condition
Pause at Design Approval. `design.md` and `plan.yaml` are approval artifacts, not execution authorization. Do not implement code, do not produce build artifacts, and do not advance to execution until the user explicitly approves the design.
