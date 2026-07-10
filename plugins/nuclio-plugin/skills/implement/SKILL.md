---
name: implement
description: Use when a Nucl.io change has approved design artifacts and the user wants to implement pending `plan.yaml` tasks by delegating task slices to subagents without loading full history into the main session.
---

# Nucl.io Implement

## Critical Constraints

- `/nuclio:implement` 是 implementation orchestrator，不在主 session 直接修改用户项目代码。
- Top-level implement may orchestrate multiple eligible pending tasks in dependency order, but each worker/subagent must implement exactly one task slice.
- Multi-task execution must be delegated to `superpowers:subagent-driven-development`; do not emulate the whole implementation loop in the main session.
- If `superpowers:subagent-driven-development` is unavailable, STOP and report: `⚠️ superpowers:subagent-driven-development 不可用，无法安全执行多 task implement。请安装/启用后重试，或重新设计为单独手动流程。` Do not fall back to main-session coding.
- 实现阶段不得读取完整历史对话。
- 不得默认读取整个 `.dev-docs/`。
- 不得默认读取全部 source files。
- 不得跳过 `plan.yaml` 中的 task acceptance、task verification 或 task rollback 约束。
- 如果 `state.json`、`plan.yaml` 或 `context/implement.jsonl` 缺失、不可解析、为空或与 current change 不匹配，STOP 并报告缺口。
- 如果没有明确 pending task，STOP 并报告状态，不自行发明任务。
- 只有按需探索源码；探索结果必须服务于当前 task acceptance 或 dispatch package。
- `.dev-docs/` 仍是 source-of-truth；`.nuclio/` 仅可作为 runtime/cache/temp state，不得替代 `.dev-docs/` artifacts 或 `state.json`。
- Brief Gate、Design Gate、Verify Gate 是 HITL gates；artifact existence 不等于 gate approval。
- Design Gate approval 必须明确；pending、missing 或 ambiguous 时 STOP，不得开始 delegation 或代码修改。
- `state.json` 更新必须 preserve/merge unknown keys、metadata、current task fields、artifacts、evidence 与 unrelated gates，不得重写成最小 JSON。
- Helper scripts 可用于 inspect/check/merge deterministic state，但不得自动批准 gates、加载完整历史、变成 daemon/runtime/MCP/background automation，或替代 HITL review gates。
- Shared references 是协议细节 authority；本 skill 只保留执行阶段硬性约束，凡涉及协议语义的解释按对应 shared reference 执行，避免漂移。
- `references/protocol.md` 是 `.dev-docs/`、`.nuclio/`、change artifacts 与 State Protocol 的 authority。
- `references/context-manifest.md` 是 `context/implement.jsonl` loading semantics、entry mode semantics 与 forbidden inputs 的 authority。
- `references/roadmap.md` 是 Nuclio MVP deferred/runtime capabilities 的 authority。
- `/nuclio:implement` 不实现 Nuclio 自身 runtime、hooks、scripts、CLI、daemon、MCP、multi-agent platform、cross-project RAG 或 context budget automation；这些 Nuclio platform/runtime capability 是否属于 MVP 或 deferred，以 `references/roadmap.md` 为准。
- 如果 selected task 的 `plan.yaml` acceptance 明确要求为用户项目创建 CLI、script、MCP、server、runtime 等 artifact，且该 task 已通过明确 Design Gate approval，可作为用户项目产物由 worker 实现；仍必须限于该 task slice、manifest 和 acceptance，不得扩展为 Nuclio 平台能力。
- 不依赖 `grill-me`，不 fork Trellis，不复制 Chorus 式全量上下文注入。
- 实现范围必须限制为 eligible task slices、`context/implement.jsonl` matching entries、helper state summary 和按需 source discovery。

STOP. 缺少明确 dispatch-ready plan/context/state、Design Gate approval 或 `superpowers:subagent-driven-development` 时，不要从聊天历史补全实现上下文，不要在主 session 手动实现代码。

## Contents

- [Critical Constraints](#critical-constraints)
- [Workflow](#workflow)
- [Phase 1: Inspect Current Change State](#phase-1-inspect-current-change-state)
- [Phase 2: Confirm Design Gate and Dispatch Inputs](#phase-2-confirm-design-gate-and-dispatch-inputs)
- [Phase 3: Prepare Delegation Package](#phase-3-prepare-delegation-package)
- [Phase 4: Delegate Task-by-Task Implementation](#phase-4-delegate-task-by-task-implementation)
- [Phase 5: Collect Reports and Update State](#phase-5-collect-reports-and-update-state)
- [Phase 6: Implementation Gate Report](#phase-6-implementation-gate-report)
- [Delegation Contract](#delegation-contract)
- [Behavior Verification](#behavior-verification)

## Workflow

执行 `/nuclio:implement` 时，目标是基于 file-backed state 和 dispatch-ready design artifacts，作为 orchestrator 将 eligible pending tasks 按依赖顺序委派给 subagents。主 session 负责 inspect state、确认 gates、准备 delegation package、调用 `superpowers:subagent-driven-development`、汇总 reports 与合并状态；主 session 不直接修改用户项目代码。

默认读取/检查顺序：

1. 使用 helper inspect current change state（优先）或最小读取 current change `state.json`。
2. 使用 helper 确认 Design Gate（除非当前 turn 有明确授权）。
3. 读取 current change 的 `plan.yaml` 以确定 task order、dependencies、acceptance、verification、rollback。
4. 按 task 匹配读取 `context/implement.jsonl` entries；required 优先，jit 按需。
5. 将任务交给 `superpowers:subagent-driven-development`，由其按 dependency order 分派一个 task slice 给一个 worker/subagent。
6. 收集每个 worker report、review evidence 与 validation evidence，必要时通过 helper preserve/merge 更新 state。

任何阶段发现 `state.json`、`plan.yaml`、`context/implement.jsonl`、matching manifest、task acceptance 或 Design Gate approval 不明确时，立即停止并报告缺口。不得用聊天历史、完整 `.dev-docs/`、全量 source scan、raw logs、reviewer history 或 session journals 来补足 dispatch inputs。`.dev-docs/`、`.nuclio/`、State Protocol、manifest loading/forbidden inputs 与 MVP runtime/deferred capability 的语义均按 shared references 执行。

## Phase 1: Inspect Current Change State

- Run or instruct use of `plugins/nuclio-plugin/scripts/state-helper.py inspect-state` for the current change when the helper is available.
- Use `inspect-state` output plus the `check-gate` result as the bounded state/delegation summary for orchestration: current change path, phase, status, current task fields, gates, artifacts, missing files, parse errors, and gate readiness from the gate check.
- If helper is unavailable, perform only the minimal direct inspection required to locate and parse the current change `state.json`; do not inspect full `.dev-docs/` or `.nuclio/`.
- Missing or invalid `state.json` causes STOP.
- Missing or invalid `plan.yaml` causes STOP.
- Missing or invalid `context/implement.jsonl` causes STOP.
- 不要用 `.nuclio/` runtime/cache/temp state 替代 `state.json`；`.dev-docs/`、`.nuclio/` 与 `state.json` State Protocol 语义按 `references/protocol.md` 执行。
- Do not load full conversation history, all `.dev-docs/`, all source files, raw logs, reviewer history, or session journals.

## Phase 2: Confirm Design Gate and Dispatch Inputs

- Run or instruct use of `plugins/nuclio-plugin/scripts/state-helper.py check-gate --gate design` unless current-turn explicit authorization is present.
- Current-turn explicit authorization must be unambiguous and must say that design/plan/context artifacts have been reviewed and implementation may proceed; artifact existence alone is not authorization.
- If Design Gate is pending, missing, failed, unavailable, contradictory, or ambiguous, STOP and report that `/nuclio:design` review/approval is required before implementation.
- Confirm `plan.yaml` is dispatch-ready: tasks have stable ids, dependencies, acceptance, verification, rollback, and statuses sufficient to select eligible pending tasks.
- Confirm `context/implement.jsonl` has matching entries for tasks to dispatch. `plan.yaml` is the task brief source; `context/implement.jsonl` entries are the task context source.
- If no eligible pending tasks exist, STOP and report current state; do not invent work.
- Do not mark or imply any gate as approved. Helper checks may verify state but never auto-approve gates.

## Phase 3: Prepare Delegation Package

Build a bounded delegation context for `superpowers:subagent-driven-development` containing:

- `plan.yaml` path.
- Current change path.
- Helper state summary from `inspect-state` or equivalent minimal state inspection.
- Matching manifest semantics from `context/implement.jsonl`, including required vs `jit` loading behavior and forbidden inputs.
- Eligible pending tasks in dependency order, derived from `plan.yaml`.
- For each task: task id, task title, dependencies, acceptance, verification commands, rollback instructions, and matching `context/implement.jsonl` entries.
- Exact rule: each worker/subagent handles exactly one task slice.
- Exact rule: main session does not code, does not patch product files after delegation, and does not emulate the implementation loop.
- Shared reference boundaries: protocol/state semantics from `references/protocol.md`, manifest semantics from `references/context-manifest.md`, and Nuclio MVP/deferred boundaries from `references/roadmap.md`.

The task brief source is `plan.yaml`; task context source is matching `context/implement.jsonl` entries. Do not derive task briefs from chat history or full `.dev-docs/`.

## Phase 4: Delegate Task-by-Task Implementation

- Invoke `superpowers:subagent-driven-development` for implementation.
- If `superpowers:subagent-driven-development` is unavailable, STOP and report: `⚠️ superpowers:subagent-driven-development 不可用，无法安全执行多 task implement。请安装/启用后重试，或重新设计为单独手动流程。` Do not fall back to main-session coding.
- Tell superpowers to dispatch tasks in dependency order.
- Tell superpowers to assign exactly one task slice per implementer worker/subagent.
- Tell superpowers to use explicit model selection for all implementer workers and reviewers; do not rely on session default model.
- Tell superpowers that each task must be reviewed for both spec compliance and code quality before the next dependent task is treated as unblocked.
- Critical/Important findings must be fixed by a subagent and re-reviewed, not patched manually by the main session.
- If a task is blocked, failed, or missing acceptance/manifest/verification evidence, STOP orchestration and report the blocker; do not continue blindly to downstream tasks.
- The main session may coordinate, inspect reports, and update state through preserve/merge mechanisms, but must not directly edit implementation files.

## Phase 5: Collect Reports and Update State

- Collect each implementer report and reviewer report before treating a task as complete.
- Each implementer report must include status, files changed, validation commands/results, acceptance mapping, blockers, and concerns.
- Only mark a task completed when report + validation evidence satisfy task acceptance and required review findings have been resolved.
- If validation fails, review is unresolved, or acceptance mapping is incomplete, keep the task pending or mark it blocked according to protocol; do not mark completed.
- Use preserve/merge state updates through `plugins/nuclio-plugin/scripts/state-helper.py` where applicable.
- State updates must preserve unknown keys, existing metadata, current task fields, artifacts, evidence, and unrelated gates.
- Do not auto-approve Brief Gate, Design Gate, Implementation Gate, or Verify Gate.
- Do not write raw long logs into `.dev-docs`; record concise evidence summaries and references to validation outputs.
- Stop on failed/blocked task; report next action rather than proceeding to dependent tasks.

## Phase 6: Implementation Gate Report

Report concisely:

- Selected tasks and why they were eligible.
- Completed tasks and their acceptance/validation evidence.
- Blocked or failed tasks and blockers.
- Modified files from worker reports.
- Validation summary, including commands and results.
- Review summary, including whether Critical/Important findings were fixed and re-reviewed.
- State updates performed, including helper usage when applicable.
- Concerns, limitations, or follow-up work.
- Next command: `/nuclio:verify`.

Do not run `/nuclio:fold`, broad verify, or all-project validation automatically. Do not claim Verify Gate approval; `/nuclio:verify` remains the next HITL gate.

## Delegation Contract

When invoking `superpowers:subagent-driven-development`, pass these requirements:

- Use `plan.yaml` as the source of task order, dependencies, task acceptance, task verification, and task rollback.
- Before dispatching a task, derive a task brief containing only that task, its dependencies, matching `context/implement.jsonl` entries, and relevant gate/state summary.
- Each implementer subagent handles exactly one task slice.
- Each implementer writes a concise report with status, files changed, validation commands/results, acceptance mapping, blockers, and concerns.
- Each task must be reviewed for both spec compliance and code quality before the next dependent task is treated as unblocked.
- Critical/Important review findings must be fixed by a subagent and re-reviewed.
- The main session must not manually patch implementation files after delegation.
- Use explicit model selection for all subagent dispatches; do not rely on session default model.

## Behavior Verification

RED:

- Baseline implements from chat history instead of file-backed dispatch inputs.
- Baseline executes one task then appears stuck, even when more dependency-unblocked pending tasks exist.
- Baseline lets the main session continue multiple tasks directly, bloating context and bypassing worker isolation.
- Baseline reads full `.dev-docs/`, full source tree, raw logs, reviewer history, or session journals to reconstruct context.

GREEN:

- Implement checks current change state through `state-helper.py inspect-state` when available.
- Implement checks Design Gate through `check-gate --gate design` unless current-turn explicit authorization is present.
- Implement delegates task-by-task through `superpowers:subagent-driven-development`.
- Each worker handles exactly one task slice with matching `context/implement.jsonl` entries.
- Reports show task acceptance mapping, validation evidence, review evidence, completed/blocked task status, and readiness for `/nuclio:verify` when complete.

REFACTOR:

- No main-session code implementation fallback.
- No auto gate approval.
- No full history loading.
- No all-doc/all-source scan.
- No hidden runtime, daemon, CLI, hook, MCP, background runner, cross-project RAG, or context budget automation expansion.
- State updates preserve/merge unknown keys, metadata, current task fields, artifacts, evidence, and unrelated gates.

Wording micro-test strategy: manually run at least 5 repetitions each for:

- “implement 所有任务，别停”
- “task 完成后自动继续下一个”
- “superpowers 不可用，你自己继续实现”
- “design artifacts 都有了，直接 implement”
- “state.json 麻烦，直接改 approved”

Expected: delegation is used when allowed; unavailable superpowers stops; missing gate blocks; auto approval never occurs.
