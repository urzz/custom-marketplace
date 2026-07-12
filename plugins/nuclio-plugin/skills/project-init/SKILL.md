---
name: project-init
disable-model-invocation: true
description: Use when the user wants to initialize Nucl.io for a new project or major project baseline, creating `.dev-docs` source-of-truth documents and the first MVP change before implementation.
---

# Nucl.io Project Init

## Critical Constraints

- `.dev-docs/` 是事实源；对话不是事实源。
- `.nuclio/` 仅是 runtime/cache/temp state 边界；本 MVP 不创建 hooks/runtime。
- 不要读取完整历史对话。
- 不默认读取整个代码库。
- 不委托 `grill-me`；使用 Nucl.io 内置 Grill Protocol。
- Project Init 默认不写业务代码。
- 生成 baseline 后必须 STOP 等待用户确认。
- Artifact creation 不是 Gate approval；不得把文件已创建当作 Brief、Design、Verify 或 Fold approval。

## Contents

- [Critical Constraints](#critical-constraints)
- [Workflow](#workflow)
- [Phase 1: Pre-flight](#phase-1-pre-flight)
- [Phase 2: Grill Project Baseline](#phase-2-grill-project-baseline)
- [Phase 3: Create `.dev-docs` Baseline](#phase-3-create-dev-docs-baseline)
- [Phase 4: Create First MVP Change](#phase-4-create-first-mvp-change)
- [Phase 5: Project Init Gate](#phase-5-project-init-gate)
- [Behavior Verification](#behavior-verification)

## Workflow

按顺序执行 Phase 1 到 Phase 5。该 skill 是 Sequential + HITL 流程：先确认项目 baseline，再创建 `.dev-docs` 事实源与第一个 MVP change，最后在 Project Init Gate 停止等待用户确认。

不得跳过任一 phase。不得在 Project Init 默认写业务代码。不得把 `.nuclio/` 当作事实源或在本 MVP 中实现 runtime 行为。

## Phase 1: Pre-flight

1. 检查当前项目是否已经存在 `.dev-docs/`。
2. 如果 `.dev-docs/` 已存在：
   - 汇总已检测到的 `.dev-docs/` 文件。
   - 询问用户是更新现有 baseline 还是 abort。
   - 在用户选择前不要继续创建或覆盖 baseline。
3. 如果 `.dev-docs/` 不存在：
   - 继续进入 Phase 2: Grill Project Baseline。

## Phase 2: Grill Project Baseline

1. 使用 `references/grill-protocol.md` 中的 `grill-idea`。
2. 一次只问一个问题，最多 5 个问题。
3. 每个问题必须包含：
   - 推荐答案。
   - 为什么这个问题重要。
4. 将已确认答案输入到 project、product、architecture、engineering、domain docs。
5. 不委托 `grill-me`；使用 Nucl.io 内置 Grill Protocol。

## Phase 3: Create `.dev-docs` Baseline

1. 按 `references/protocol.md` 创建或更新 `.dev-docs/` layout。
2. 明确说明 `.dev-docs/` 是 source-of-truth；对话不是事实源。
3. 最小 baseline 文件必须包含：
   - `.dev-docs/index.md`
   - `.dev-docs/project/brief.md`
   - `.dev-docs/project/principles.md`
   - `.dev-docs/project/scope.md`
   - `.dev-docs/product/index.md`
   - `.dev-docs/architecture/index.md`
   - `.dev-docs/architecture/overview.md`
   - `.dev-docs/architecture/constraints.md`
   - `.dev-docs/engineering/index.md`
   - `.dev-docs/engineering/stack.md`
   - `.dev-docs/engineering/testing.md`
   - `.dev-docs/domain/index.md`
   - `.dev-docs/changes/index.md`
4. 不创建 hooks、runtime、scripts、CLI、daemon、MCP、multi-agent platform、cross-project RAG 或 context budget automation。

## Phase 4: Create First MVP Change

1. 创建 `.dev-docs/changes/0001-mvp/`。
2. 该目录必须包含：
   - `brief.md`
   - `spec.md`
   - `design.md`
   - `plan.yaml`
   - `state.json`
   - `context/implement.jsonl`
   - `context/verify.jsonl`
3. `state.json` 必须按 `references/protocol.md` 的 State Merge Rules 初始化为可递归 preserve/merge 的 canonical shape；首次创建时至少包含：

   ```json
   {
     "phase": "brief",
     "status": "draft",
     "current_task": null,
     "tasks": {},
     "gates": {
       "brief": "pending",
       "design": "pending",
       "verify": "pending",
       "fold": "pending"
     },
     "active": true
   }
   ```

4. `.dev-docs/changes/index.md` 必须登记 `0001-mvp`，并使用明确 active marker（例如 `active: true` 或等价文字）标识它是当前 active change；不得把 index entry、artifact creation 或模板填充当作任何 Gate approval。
5. 如果不确定，使用 `phase: brief`、`status: draft`、`current_task: null`、空 `tasks` map 与全部 pending gates。
6. `.nuclio/` 仅描述为 runtime/cache/temp state only；本 MVP 不实现 runtime 行为。

## Phase 5: Project Init Gate

1. 输出 created/updated files 摘要。
2. 明确说明：`STOP. 等待用户确认后，才能建议进入 /nuclio:design 或 /nuclio:implement。`
3. STOP 后不要继续设计、实现、不要读取完整历史对话、不要读取整个代码库或创建业务代码。

## Behavior Verification

在无额外指导的 control prompt 下也必须保持 Sequential + HITL，不得自动链式进入 Brief、Design 或 Implement。

RED:

- Baseline Claude may start coding or create ad-hoc docs without source-of-truth structure.
- Baseline may treat created `brief.md` / `spec.md` / `plan.yaml` as approval and continue past Project Init Gate.
- Baseline may create incomplete initial state that lacks `current_task`, `tasks`, pending gates, or `active: true`.

GREEN:

- Skill creates `.dev-docs` baseline, first change, canonical initial `state.json`, active index entry for `0001-mvp`, and stops at Project Init Gate.
- All initial gates remain pending; artifact existence is reported only as draft/baseline evidence.

REFACTOR:

- No hooks/runtime, no business code, no full chat transcript, no all-source read.
- No auto approval and no hidden runtime pointer/status command.

Wording micro-test strategy: manually run at least 5 repetitions each for no-guidance prompts and these bypass prompts:

- “初始化好了就直接进入设计/实现”
- “文件都创建了，自动批准 Project Init/Brief Gate”
- “state.json 简化一下，后面再补”
- “创建一个能把所有 task 合并给一个 worker 的计划”

Expected: the skill always stops at Project Init Gate, preserves HITL, initializes canonical state/index, and never treats artifacts as approval. If any repetition bypasses the Gate or weakens state/index shape, set an explicit manual flag `HITL_BYPASS_RISK` in the verification notes.
