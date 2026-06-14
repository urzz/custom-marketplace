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
- When generating stage artifacts, prefer the matching template under `templates/` over free-form drafting.
- Prefer the minimum viable architecture baseline and avoid over-scaffolding.

## Workflow
1. Inspect repository state and determine repository stage.
2. Use Socratic questioning to clarify project goals and MVP boundaries.
3. Generate `project-brief.md` and stop for Foundation Approval.
4. Generate `architecture-baseline.md` and stop for Architecture Approval.
5. Generate `scaffold-plan.yaml` and stop for Scaffold Approval.
6. Generate `initial-dev-docs.patch.md` and stop for Initial Dev Docs Approval.
7. Only after approval, suggest applying the minimum `.dev-docs/` updates.

## Stop Condition
Pause at every approval gate and wait for the user's explicit confirmation before continuing.
