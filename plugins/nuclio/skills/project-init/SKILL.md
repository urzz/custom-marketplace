---
name: project-init
description: Use when the repository is new, lacks architecture foundation, or the user wants to establish project baseline before feature work.
---

# Nucl.io Project Init

## Goal
Establish the minimum project foundation in `.nuclio/project/` before feature work begins, with explicit approval gates between each initialization artifact.

## Inputs
- The user's raw project idea, intended outcome, and repository context.
- Current repository state, including existing docs, structure, and constraints.
- Any existing `.nuclio/project/` artifacts if initialization was partially started before.

## Outputs
- `.nuclio/project/project-brief.md`
- `.nuclio/project/architecture-baseline.md`
- `.nuclio/project/scaffold-plan.yaml`
- `.nuclio/project/init-state.json`
- `.nuclio/project/events.jsonl`
- `.nuclio/project/initial-dev-docs.patch.md`

## Rules
- Do not treat project initialization as a feature spec.
- Do not create `.claude/skills`, `.claude/agents`, `.claude/hooks`, or `.claude/rules`.
- Do not write `.dev-docs/` before Initial Dev Docs Approval.
- Use `templates/init-state-template.json` as the canonical Project Init state shape; approvals must live under `approved.foundation`, `approved.architecture`, `approved.scaffold`, and `approved.initial_dev_docs`.
- Scaffold writes require Scaffold Approval and must stay within `scaffold-plan.yaml` task `allowed_paths` while avoiding `forbidden_paths`.
- Initial `.dev-docs/` writes require `approved.initial_dev_docs === true` plus a scoped `approved.initial_dev_docs_scope.target_paths` or accepted/edited targets in `.nuclio/project/initial-dev-docs.patch.md`.
- Run Bootstrap Check first with `node "$CLAUDE_PLUGIN_ROOT/scripts/bootstrap-check.mjs" --requested-skill project-init` and use its JSON `ok/foundation/project_state/active_changes/next_action` result to choose the safe next step.
- Write state through `node "$CLAUDE_PLUGIN_ROOT/scripts/write-state.mjs" <state-file> '<json>'` so `validate-state.mjs` runs before the target is written.
- Append typed `project_init.*` events with `node "$CLAUDE_PLUGIN_ROOT/scripts/append-event.mjs" .nuclio/project/events.jsonl '<json>'`.
- When generating stage artifacts, prefer the matching template under `templates/` over free-form drafting.
- Prefer the minimum viable architecture baseline and avoid over-scaffolding.

## Workflow
1. Inspect repository state and determine repository stage.
2. Use Socratic questioning to clarify project goals and MVP boundaries.
3. Generate `project-brief.md` and stop for Foundation Approval.
4. Generate `architecture-baseline.md` and stop for Architecture Approval.
5. Generate `scaffold-plan.yaml` and stop for Scaffold Approval.
6. Generate `initial-dev-docs.patch.md` and stop for Initial Dev Docs Approval.
7. Only after approval, apply the minimum `.dev-docs/` updates directly or delegate to `/nuclio:apply-memory`; in both cases record canonical approval state and events first.

## Stop Condition
Pause at every approval gate and wait for the user's explicit confirmation before continuing.
