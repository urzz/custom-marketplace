---
name: skill-forge
description: Use when creating, designing, or implementing a new Claude Code skill from scratch, or when modifying, improving, auditing, or reviewing an existing skill.
---

# Skill Forge

End-to-end workflow for creating and iterating Claude Code skills. The workflow uses a Risk-Adaptive Composite: route first, classify risk deterministically, then select the lightest path that preserves user approval, deterministic evidence, ownership isolation, and review independence.

## Critical Constraints

Mandatory rules:

1. Route before every action. Never edit, audit, dispatch, or validate before matching CREATE, MODIFY, CHANGE_AUDIT, or FULL_AUDIT.
2. AUDIT paths are read-only. They may run read-only commands and produce findings, but must not Edit/Write product files or commit.
3. Risk classification is deterministic and conservative: use the highest matching level; if required facts are missing, raise one level; never silently downgrade during a run.
4. Deterministic checks run before LLM review. If a schema/static/test check fails and can be run locally, fix or report that failure before any reviewer dispatch.
5. Main Session is the only Controller. Bounded agents never modify state, Gate, rubric, review-state.json, helper ledgers, or Controller decisions.
6. L2/L3 file-backed flow uses scripts/review-state-helper.py as the only review-state.json writer and next-action as the only transition authority.
7. L2/L3 implementation/fix writes remain sequential in this version. Do not introduce parallel product writes.
8. Do not use EnterPlanMode. Specs and Plans are written to files for user review.
9. Do not call other skills, agents, workflows, MCP, network services, hooks, daemons, or worktrees unless this skill explicitly dispatches its owned bounded agents in the L2/L3 flow.
10. Squash/reset/rebase/history rewrite is never placed in bounded-agent prompts and requires the current user's explicit approval after validation.

## Contents

- [Critical Constraints](#critical-constraints)
- [Routing](#routing)
- [Risk Classification](#risk-classification)
- [Intermediate Artifacts](#intermediate-artifacts)
- [Phase 1: Discovery or Audit](#phase-1-discovery-or-audit)
- [Phase 2: Spec](#phase-2-spec)
- [Phase 3: Plan and Approval](#phase-3-plan-and-approval)
- [Phase 4: Implement](#phase-4-implement)
- [Phase 5: Validate and Complete](#phase-5-validate-and-complete)

## Routing

| Signal | Path |
|---|---|
| User describes a new skill/capability and no existing skill is referenced | CREATE |
| User points to an existing skill plus a modification verb such as improve/fix/update/优化/修改/修复 | MODIFY |
| User asks to review/check/audit/validate a bounded change set | CHANGE_AUDIT |
| User asks for full skill/plugin completeness, release readiness, or cross-file drift audit | FULL_AUDIT |
| CWD contains SKILL.md plus a modification verb | MODIFY |
| CWD contains SKILL.md plus a review/check/audit verb | CHANGE_AUDIT unless the user asks for full coverage |
| Ambiguous | Ask: “是创建新 skill、改进已有 skill、审查当前变更，还是做完整审计？” |
| No match | HALT and ask the user to choose CREATE / MODIFY / CHANGE_AUDIT / FULL_AUDIT |

Audit boundaries:

- CHANGE_AUDIT examines the user-specified change range, changed product paths, relevant contracts, and directly affected neighbors. It is not limited to git diff when affected contracts require reading stable files.
- FULL_AUDIT reads the complete skill-local files, one-level references, skill-local agents, scripts/tests, relevant plugin-level agents, plugin metadata, marketplace/README/CLAUDE synchronization points, and validation commands. It must not treat git diff as the only scope.
- Both audit paths are read-only and may recommend a later MODIFY path only after user confirmation.

## Risk Classification

Classify after Routing and before Spec/Plan/implementation.

General rules:

1. Evaluate all matching conditions and select the highest risk level.
2. If information is insufficient to prove a lower level, raise one level.
3. The user may request a stricter path; honor it.
4. Stop and upgrade when scope expands, ownership becomes unclear, validation is not observable, or an irreversible/outward-facing action appears.
5. File count is only a signal. Prefer behavior impact, reversibility, coupling, validation quality, authority surface, and failure consequence.

| Level | Conditions | Successful path |
|---|---|---|
| L0 Mechanical | No behavior/control-plane change; local reversible edit; deterministic validation is obvious; no irreversible or outward-facing action; no pending user choice | Compact contract, Main Session implements directly, targeted deterministic checks, diff self-review, dispatch 0 agents, no extra confirmation except pending choices/irreversible actions |
| L1 Routine | Clear bounded scope; reversible; adequate tests/static checks; does not touch L2/L3 control plane; no cross-owner ambiguity | Simplified change contract, default Main Session implementation, optional at most one bounded implementation unit, all relevant deterministic checks, one whole-diff review; upgrade if cross-context, multiple owners, or file-backed recovery is needed |
| L2 Structural | Routing/Gate/Pattern/Architecture changes; agent contract; shared templates; public workflow docs; multi-caller behavior; ordinary scripts; structural coupling where deterministic evidence is strong enough for some tasks | File-backed helper flow. Dispatch T implementation units, R task reviewers where R ≤ T for risk tasks only, one mandatory final reviewer, and E behavioral eval where E is 0 or 1 |
| L3 High Risk | State schema/transition/ownership/ledger/budget/hash/recovery/completion; write authority; destructive Git; security-sensitive or irreversible behavior; high failure impact; legacy strict run | Strict file-backed path with every Task using task-and-final review, mandatory final review, structural validation, and applicable behavioral validation |

Runtime upgrade is allowed; silent downgrade is forbidden. If an L0/L1 run discovers L2/L3 conditions, stop before further product edits, summarize evidence, and obtain an updated contract.

## Intermediate Artifacts

Use `.skill-forge/<skill-name>-<change-topic>/` with flat files only and a local `.gitignore` containing `*`. The run directory stores `spec.md`, `plan.yaml`, stable briefs, reports, observations, review packages, eval prompts, `rubric-snapshot.md`, and `review-state.json` when L2/L3 initializes state. Stable brief paths are created inside the run by the Controller; do not rely on temporary/default brief names.

For L2/L3 protocol details, use the canonical authority: [Review State Protocol](references/review-state-protocol.md). Templates live in [Templates](references/templates.md); validation dimensions live in [Internal Validation Checklist](references/validation-checklist.md); pattern selection uses [Google 8 Agent Design Patterns](references/design-patterns.md).

## Phase 1: Discovery or Audit

### CREATE

Ask one recommendation-first question at a time until the core problem, minimum capability, non-goals, triggers, side effects, and validation needs are clear. Skip questions whose answers can be inferred from local files. Output the Phase 1 template and wait for user confirmation before Spec.

### MODIFY

Read the existing skill surface needed to understand the requested change. For vague optimization requests, ask at least one recommendation-first question before diagnosing. Output the Change First Principles template and wait for user confirmation before Spec unless the user has already provided an explicit reversible L0/L1 contract with no pending choice.

### CHANGE_AUDIT and FULL_AUDIT

Produce a structured audit report with scope, files read, deterministic checks run, semantic findings, baseline/existing debt separation, and recommended next path. Do not modify files. If fixes are requested, re-route to MODIFY and classify risk from the proposed fix, not from the audit label.

## Phase 2: Spec

Goal: create the user-readable contract.

1. CREATE uses Full Spec. MODIFY uses Delta Spec.
2. Include risk level, why lower levels are insufficient, non-goals, validation plan, rollback/recovery expectations, and upgrade triggers.
3. Pattern Selection runs only for CREATE, Pattern/Architecture changes, or genuine design choices. Otherwise preserve the existing pattern and state that no selection was needed.
4. For L2/L3, Spec and Plan share one joint implementation approval Gate in Phase 3; Phase 2 saves the Spec for review but does not ask for a separate implementation approval.
5. For L0/L1, do not repeat confirmation when the user's request already clearly authorizes a reversible bounded change and no choices remain. Still confirm irreversible, outward-facing, or expanded-scope work.

Save Spec to `.skill-forge/<skill-name>-<change-topic>/spec.md`; create `.skill-forge/.gitignore` with `*` if missing. If the user requests changes, update the Spec before Plan.

## Phase 3: Plan and Approval

Goal: turn the Spec into executable work.

1. Use the Plan YAML template with exact repo-relative ownership paths only.
2. For L0/L1, a compact or simplified plan may be embedded in conversation/report if no file-backed recovery is needed.
3. For L2/L3, write `plan.yaml` and include Task `meta.model`, `meta.file_type`, `meta.requires_execution_check`, `meta.risk_level`, and `meta.review_policy` exactly as supported by scripts/plan_contract.py: risk_level is L2 or L3; review_policy is final-only or task-and-final; L3 requires task-and-final.
4. Run Plan self-review before approval: Spec coverage, placeholder scan, exact path consistency, ownership uniqueness, risk/review policy consistency, and deterministic validation observability.
5. L2/L3 require one joint implementation approval Gate covering the formal Spec and YAML Plan. The review summary must include risk, non-goals, acceptance, deterministic checks, escalation conditions, and any irreversible/outward-facing actions.
6. User changes after approval return to Phase 3, rewrite the Plan, and re-confirm before implementation.

## Phase 4: Implement

### L0 Mechanical

Main Session performs the minimal edit directly, runs targeted deterministic checks, reviews the final diff for ownership/contract drift, and reports results. Dispatch count: 0 agents.

### L1 Routine

Default to Main Session implementation. If a bounded implementation unit is useful, dispatch at most one implementation agent with explicit ownership and report path; otherwise do it directly. Run all relevant deterministic checks and one whole-diff review before reporting. Do not initialize review-state.json.

### L2/L3 File-Backed Controller

Use the canonical protocol in review-state-protocol.md. Summary:

1. Record initial base and run one bounded Pre-Flight Contract Review for contradictions, rubric conflicts, ownership gaps, and eval ownership ambiguity.
2. Resolve an existing read-only rubric source. Helper `init` creates both `rubric-snapshot.md` and `review-state.json`; Controller does not pre-create them.
3. Loop: call `next-action`, execute only the returned action, save raw agent JSON/report, call the matching helper `record-*` or `import-review`, then call `next-action` again.
4. Before reviewer/final-reviewer dispatch, run deterministic schema/static/test checks that are applicable. A deterministic FAIL blocks reviewer dispatch until fixed or reported through the protocol.
5. Implementation commits are exactly one per Task and use `feat(<scope>): [Task N] <name>`. L2 `final-only` tasks must provide deterministic evidence to `record-implementation`; L2 risk tasks and all L3 tasks use task-and-final review.
6. Task review uses `task_base..task_head`; final review and validation use `initial_base..current_head` packages generated by helper.
7. Findings, owner mapping, shared maximum=2 budget, HALT, no-progress, recovery, and completion follow helper state only.

## Phase 5: Validate and Complete

Validation is deterministic-first.

- L0/L1 run the checks relevant to the change and keep whole-diff evidence in the final report.
- L2/L3 run mandatory final review after Tasks, then structural validation, then the helper `BEHAVIORAL_VALIDATION` gate. Every L2/L3 run records/imports that helper gate before squash approval.
- Structural validation distinguishes scriptable checks from semantic checks and records base/head evidence for the same applicable commands.
- Behavioral eval-agent dispatch is conditional: spawn eval only when user-visible behavior, Routing, Gate, Pattern, or Architecture changed. Routing/Gate changes enable one consistency rerun; Pattern/Architecture changes enable baseline comparison. When all behavioral flags are false, the Controller creates/imports a helper-compatible PASS/SKIP observation with all flags false, `spawned=0`, and SKIP evidence, without dispatching eval, then advances by helper to `SQUASH_APPROVAL`. Do not delete the helper gate.
- LLM reviewers judge contract, semantics, and cross-Task consistency. They do not replace deterministic schema/static/test checks and cannot close findings without helper import.
- Squash is offered only when helper returns `REQUEST_SQUASH_APPROVAL`; user refusal can still complete as unsquashed.
