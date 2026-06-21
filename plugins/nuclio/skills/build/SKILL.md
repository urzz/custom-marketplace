---
name: build
description: Use after Design Approval to execute Nucl.io plan tasks, produce verification evidence, review the diff, and patch issues before close.
---

# Nucl.io Build

## Goal
Execute the current change strictly from `.nuclio/changes/<change-id>/plan.yaml`, implement the approved tasks in dependency order, and produce `verify.md` plus `review.md` evidence for the minimum implement → verify → review → patch loop.

## Inputs
- The approved `.nuclio/changes/<change-id>/design.md` and its upstream approved `spec.md`.
- `.nuclio/changes/<change-id>/plan.yaml` as the execution source of truth.
- Task-local repository context needed for the current plan task.
- Existing `.nuclio/changes/<change-id>/state.json` and `events.jsonl` if build work was started before.
- Allowed execution boundaries such as `allowed_paths` and `forbidden_paths` when the plan defines them.

## Outputs
- code changes
- `.nuclio/changes/<change-id>/evidence/verify.md`
- `.nuclio/changes/<change-id>/evidence/review.md`
- `.nuclio/changes/<change-id>/state.json`
- `.nuclio/changes/<change-id>/events.jsonl`

## Rules
- Confirm Design Approval before starting build work.
- Execute only the approved `plan.yaml`; do not rewrite the scope in `spec.md`, `design.md`, or `plan.yaml` during build.
- Execute tasks in dependency order and do not skip verification or review.
- Load only task-local context for the active plan task instead of broad unrelated repository context.
- Respect `allowed_paths` and `forbidden_paths` for every implementation step.
- Run Bootstrap Check first with `node plugins/nuclio/scripts/bootstrap-check.mjs`, then validate the approved task graph with `node plugins/nuclio/scripts/validate-plan.mjs .nuclio/changes/<change-id>/plan.yaml --section tasks`.
- Before each write, set or verify `state.current_task` matches the active `plan.yaml` task so guard can enforce `allowed_paths` and `forbidden_paths`; write state through `node plugins/nuclio/scripts/write-state.mjs <state-file> '<json>'`.
- Treat guard path failures and ambiguous Bash blocks as blocking scope violations; use Write/Edit/MultiEdit or obtain a scoped `risk_approvals[]` entry instead of working around them.
- Append typed `task.started`, `task.verified`, `task.reviewed`, `task.patched`, and `task.completed` events with `node plugins/nuclio/scripts/append-event.mjs .nuclio/changes/<change-id>/events.jsonl '<json>'` as the task progresses.
- Patch loop maximum is 2 attempts per task before stopping for human decision.
- Build must not modify `.dev-docs/`.
- Build must not edit approval artifacts under `.nuclio/changes/<change-id>/spec.md` or `design.md`.
- Use the build templates under `templates/` for `verify.md` and `review.md` instead of free-form evidence.
- Review must be produced from an independent read-only perspective, such as the `nuclio-reviewer` agent, against the current diff and evidence.
- If verify or review fails, you must either enter the patch loop immediately or stop and request human decision. When the failure is patchable and the approved design still stands, patch the implementation, re-run the necessary verification, and re-run review.
- If verification reveals the approved design is no longer valid, or the patch loop reaches its retry limit, stop and request human decision instead of improvising a redesign.

## Workflow
1. Confirm the target change has Design Approval and inspect the latest build state.
2. Read `plan.yaml`, select the next ready task by dependency order, and update `state.current_task` before implementation.
3. Load only the task-local context required for that task and implement within guard-enforced path boundaries.
4. Record local and global checks in `.nuclio/changes/<change-id>/evidence/verify.md`.
5. Run an independent diff review and write `.nuclio/changes/<change-id>/evidence/review.md`.
6. If verify or review returns patchable issues, run the patch loop: implement the smallest fix, refresh `verify.md`, and re-run review.
7. Update `.nuclio/changes/<change-id>/state.json` and `events.jsonl` with build progress, evidence status, and whether the change is ready to close or blocked for human input.

## Stop Condition
Stop when either:
- all planned tasks are complete and both verify and review pass; or
- a blocking condition requires human intervention, including missing approval, forbidden-path pressure, invalidated design, or patch-loop exhaustion.
