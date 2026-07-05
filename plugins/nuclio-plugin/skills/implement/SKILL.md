---
name: implement
description: Use when a Nucl.io change has `plan.yaml` and a pending task, and the user wants to implement exactly one task slice using `context/implement.jsonl` without loading full history.
---

# Nucl.io Implement

## Critical Constraints

- 实现阶段不得读取完整历史对话。
- 不得默认读取整个 `.dev-docs/`。
- 不得默认读取全部 source files。
- 不得跳过 `plan.yaml` 中的 task acceptance。
- 一次只实现一个 pending task。
- 如果 `state.json`、`plan.yaml` 或 `context/implement.jsonl` 缺失，STOP 并询问用户。
- 如果没有明确 pending task，STOP 并报告状态，不自行发明任务。
- 只有按需探索源码；探索结果必须服务于当前 task acceptance。
- Shared references 是协议细节 authority；本 skill 只保留执行阶段硬性约束，凡涉及协议语义的解释按对应 shared reference 执行，避免漂移。
- `references/protocol.md` 是 `.dev-docs/`、`.nuclio/`、change artifacts 与 State Protocol 的 authority。
- `references/context-manifest.md` 是 `context/implement.jsonl` loading semantics、entry mode semantics 与 forbidden inputs 的 authority。
- `references/roadmap.md` 是 Nuclio MVP deferred/runtime capabilities 的 authority。
- `/nuclio:implement` 不实现 Nuclio 自身 runtime、hooks、scripts、CLI、daemon、MCP、multi-agent platform、cross-project RAG 或 context budget automation；这些 Nuclio platform/runtime capability 是否属于 MVP 或 deferred，以 `references/roadmap.md` 为准。
- 如果 selected task 的 `plan.yaml` acceptance 明确要求为用户项目创建 CLI、script、MCP、server、runtime 等 artifact，且该 task 已通过明确 Design Gate approval，可作为用户项目产物实现；仍必须限于当前 task slice、manifest 和 acceptance，不得扩展为 Nuclio 平台能力。
- Design Gate approval 必须明确；pending、missing 或 ambiguous 时 STOP，不得开始修改代码。
- 不依赖 `grill-me`，不 fork Trellis，不复制 Chorus 式全量上下文注入。
- 实现范围必须限制为 current task slice、`context/implement.jsonl` 和按需 source discovery。

STOP. 缺少明确 task slice 或 manifest；不要从聊天历史补全实现上下文。

## Contents

- [Critical Constraints](#critical-constraints)
- [Workflow](#workflow)
- [Phase 1: Load Current Change State](#phase-1-load-current-change-state)
- [Phase 2: Select One Pending Task](#phase-2-select-one-pending-task)
- [Phase 3: Load Implement Manifest](#phase-3-load-implement-manifest)
- [Phase 4: Implement Task Slice](#phase-4-implement-task-slice)
- [Phase 5: Task-Level Validation](#phase-5-task-level-validation)
- [Phase 6: Update State and Report](#phase-6-update-state-and-report)
- [Behavior Verification](#behavior-verification)

## Workflow

执行 `/nuclio:implement` 时，目标是基于 file-backed state 实现一个、且仅一个 pending task slice。不要从聊天历史、完整 `.dev-docs/`、全量源码扫描或外部运行时状态中推断任务。

默认读取顺序：

1. 当前 change 的 `state.json`。
2. 当前 change 的 `plan.yaml`。
3. 当前 change 的 `context/implement.jsonl`。
4. 只在当前 task acceptance 需要时，按需探索相关 source files。

任何阶段发现 manifest、task slice、acceptance 或 Design Gate approval 不明确时，立即停止并向用户报告缺口。`.dev-docs/`、`.nuclio/`、State Protocol、manifest loading/forbidden inputs 与 MVP runtime/deferred capability 的语义均按 shared references 执行。

## Phase 1: Load Current Change State

- Read current change `state.json`.
- Confirm explicit Design Gate approval evidence before changing code: `state.json.gates.design` is `approved`, or `state.json.phase` is already `implement`, or the user explicitly confirms in the current turn that design/plan/context manifests have been reviewed and implementation may proceed.
- If Design Gate approval evidence is pending, missing, or ambiguous, STOP and report that `/nuclio:design` review/approval is required before implementation; do not start code changes.
- 如果 `state.json` 缺失、不可解析或无法定位当前 change，STOP 并询问用户。
- 不要用 `.nuclio/` runtime/cache/temp state 替代 `state.json`；`.dev-docs/`、`.nuclio/` 与 `state.json` State Protocol 语义按 `references/protocol.md` 执行。

## Phase 2: Select One Pending Task

- Read `plan.yaml`.
- Select the first `status: pending` task whose dependencies are completed.
- If multiple eligible tasks exist, recommend the lowest id and ask only if task choice affects user intent.
- 必须读取并遵守选中 task 的 acceptance；不得跳过或改写 acceptance。
- 如果没有明确 pending task，STOP 并报告状态，不自行发明任务。
- 一次执行只处理一个 task；完成后报告结果，不继续实现下一个 task。

## Phase 3: Load Implement Manifest

- Read `context/implement.jsonl` line by line.
- Load required entries first; load `jit` entries only when needed.
- `required` 优先、`jit` 按需是本 skill 的加载顺序约束；entry mode semantics、允许内容与 forbidden inputs 以 `references/context-manifest.md` 为准。
- 如果 `context/implement.jsonl` 缺失、为空或与选中 task 无法建立关系，STOP 并询问用户。
- 不要读取完整历史对话来补足 manifest。
- 不要默认读取整个 `.dev-docs/`；只能按当前 task slice 需要读取 manifest 或 acceptance 明确引用的文件，具体 forbidden inputs 按 `references/context-manifest.md` 执行。

## Phase 4: Implement Task Slice

- Implement only files needed for selected task.
- Keep changes within task acceptance.
- Source discovery 必须按需、最小化，并且每次探索都要服务于当前 task acceptance。
- 不得默认读取全部 source files，不得进行跨任务重构或顺手实现未来 task。
- 不得创建 Nuclio 自身 hooks、runtime、scripts、CLI、daemon、MCP、multi-agent platform、cross-project RAG 或 context budget automation；Nuclio MVP deferred/runtime capability 边界按 `references/roadmap.md` 执行。
- 如果 selected task 的 approved Design Gate 与 `plan.yaml` acceptance 明确要求用户项目 CLI、script、MCP、server、runtime 等 artifact，将其作为用户项目产物实现；不得因为关键词自动拒绝，也不得超出当前 task slice。
- 若 acceptance 需要的实现与 manifest 或 shared references 冲突，STOP 并报告冲突，不自行扩大范围。

## Phase 5: Task-Level Validation

- Run task-level verification commands from `plan.yaml` when present.
- If commands are absent, run the smallest static validation available and report that no project test command was defined.
- 验证必须覆盖当前 task acceptance；如果只能做静态检查，报告限制。
- 如果验证失败，停止后续状态推进，保留 task 为 pending 或 blocked，并报告失败摘要与下一步。

## Phase 6: Update State and Report

- Mark task completed only if acceptance and validation pass.
- If partial/failing, keep task pending or blocked and report blockers.
- Write concise evidence summary; do not write raw long logs to `.dev-docs`.
- 只在有充分证据时更新 `plan.yaml` 或 `state.json`；更新内容必须反映实际完成状态。
- `state.json` 与 `plan.yaml` 更新行为必须遵守 `references/protocol.md` 的 State Protocol：preserve/merge existing state metadata，保留未知字段和已有 metadata，只更新当前 task/status/gate/evidence 所需字段，不得把现有 state 重写成最小 JSON。
- 报告应包含：选中的 task id、修改文件、验证命令、验证结果、acceptance 对照、任何 blockers 或 concerns。
- 不要把 `.nuclio/` 当作 source-of-truth；相关边界按 `references/protocol.md` 执行，且 Nuclio MVP runtime/deferred capability 按 `references/roadmap.md` 执行。

## Behavior Verification

RED: baseline may implement from chat history and touch broad files.

GREEN: skill selects one task, loads manifest, implements bounded diff, validates, updates state.

REFACTOR: no multi-task implementation, no full docs/source scan, no invented task state.
