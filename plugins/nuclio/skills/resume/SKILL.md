---
name: resume
description: Use when a Nucl.io session was interrupted or the user asks to continue and recover the next valid workflow step.
---

# Nucl.io Resume

## Goal
Read `.nuclio/project/init-state.json` and `.nuclio/changes/*/state.json`, summarize the current workflow state, identify active gates or missing prerequisites, and recommend the next valid step without advancing the workflow.

## Inputs
- `.nuclio/project/init-state.json` if project initialization has started.
- `.nuclio/changes/*/state.json` for one or more changes.
- Related `.nuclio/project/events.jsonl` or `.nuclio/changes/<change-id>/events.jsonl` when needed to clarify the latest state.
- Current repository context only as needed to explain workflow risk or the next recommended skill.

## Outputs
- A workflow status summary for project initialization or the active change.
- The current gate, missing prerequisite, or blocking condition if one exists.
- The recommended next Nucl.io skill or human action.

## Rules
- Resume is read-only workflow recovery; do not create new workflow artifacts while resuming.
- Do not automatically advance past any gate.
- If the workflow is in `waiting_human`, explicitly name the gate and the next required skill or user action.
- If project foundation is missing, explain the risk and recommend `/nuclio:project-init` when appropriate.
- If there is no active change, explain the risk and recommend starting a new change with `/nuclio:spec` when appropriate.
- If multiple change states exist, identify the active or most recently relevant change instead of merging them into one ambiguous status.
- Resume may recommend a next step, but it must not produce `spec.md`, `design.md`, `plan.yaml`, build evidence, close artifacts, or memory updates.

## Workflow
1. Read `.nuclio/project/init-state.json` if present to determine project-foundation status.
2. Read available `.nuclio/changes/*/state.json` files and identify whether there is an active, blocked, or completed change.
3. Use relevant `events.jsonl` files only when the latest state needs clarification.
4. Summarize the current workflow state, current gate, missing prerequisite, and workflow risk.
5. Recommend the next valid Nucl.io skill or human action without changing workflow phase or approval state.

## Stop Condition
Stop after reporting the current workflow state and the next valid step. Do not auto-resume execution, do not clear waiting states, and do not transition phases on behalf of the user.
