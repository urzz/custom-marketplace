---
name: spec
description: Use when the user provides a feature, bugfix, refactor, or maintenance request that needs requirement clarification before implementation.
---

# Nucl.io Spec

## Goal
Turn one requested change into an approved requirement contract in `.nuclio/changes/<change-id>/spec.md`, grounded in user intent, first-principles reasoning, and repository evidence before any implementation planning begins.

## Inputs
- The user's raw change request, expected outcome, and constraints.
- Current repository context, including relevant code, docs, and existing Nucl.io change artifacts.
- Existing `.nuclio/changes/<change-id>/state.json` and `events.jsonl` if the change was started before.

## Outputs
- `.nuclio/changes/<change-id>/spec.md`
- `.nuclio/changes/<change-id>/state.json`
- `.nuclio/changes/<change-id>/events.jsonl`
- `.nuclio/changes/<change-id>/context-report.md` when `.dev-docs/` context is consulted

## Rules
- Use Socratic Clarification to remove ambiguity before drafting the spec.
- Use First-Principles reasoning to separate the essential problem, minimum value, and invariants from preferences.
- Use Codebase Grounding: inspect the repository, cite concrete files or structure, and avoid repo-agnostic speculation.
- If `.dev-docs/index.md` exists, use it as the root index for context selection instead of scanning all `.dev-docs/` files.
- Run Bootstrap Check first with `node plugins/nuclio/scripts/bootstrap-check.mjs` and use its JSON `ok/foundation/project_state/active_changes/next_action` result before creating or resuming a change.
- Record SelectContext decisions in `context-report.md` using `templates/context-report-template.md`, then validate it with `node plugins/nuclio/scripts/validate-context-report.mjs .nuclio/changes/<change-id>/context-report.md`, or mirror them as typed `context.root_loaded`, `context.index_loaded`, `context.doc_loaded`, and `context.doc_skipped` events.
- Use `templates/state-template.json` as the canonical change state shape; approvals must live under `approved.*`, and state writes must go through `node plugins/nuclio/scripts/write-state.mjs <state-file> '<json>'`.
- Append typed events with `node plugins/nuclio/scripts/append-event.mjs .nuclio/changes/<change-id>/events.jsonl '<json>'`.
- If project foundation is missing, you may recommend `/nuclio:project-init`, but do not force it as a blocking prerequisite unless the user chooses to pause.
- Only produce the spec artifact and the minimum workflow state for this change.
- Spec Approval is a hard gate: do not start design, draft `design.md`, draft `plan.yaml`, or describe an execution task graph before the user explicitly approves the spec.
- Do not implement code.
- Do not produce `design.md` or `plan.yaml`.
- Do not jump to build, verification, or execution work.
- When generating the stage artifact, prefer the matching template under `templates/` over free-form drafting.

## Workflow
1. Inspect the request, repository context, and any existing change state.
2. Ask focused Socratic clarification questions if key intent, constraints, or acceptance boundaries are unclear.
3. Distill the request with first-principles thinking: essential problem, minimal value, invariants, and minimum verification loop.
4. Ground the spec in current codebase evidence, relevant modules, and repository constraints.
5. Generate `spec.md` from the spec template, write any required `context-report.md`, append typed context/spec events, and update canonical change state from `templates/state-template.json`.
6. Stop for Spec Approval and wait for explicit user confirmation before any design work begins.

## Stop Condition
Pause at Spec Approval. Do not create design artifacts, implementation tasks, or code changes until the user explicitly approves the spec.
