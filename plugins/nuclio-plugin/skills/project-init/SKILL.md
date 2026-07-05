---
name: project-init
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
3. `state.json` 的 phase 应根据已确认信息设置为 `brief` 或 `design`。
4. 如果不确定，使用 `brief` 和 `draft`。
5. `.nuclio/` 仅描述为 runtime/cache/temp state only；本 MVP 不实现 runtime 行为。

## Phase 5: Project Init Gate

1. 输出 created/updated files 摘要。
2. 明确说明：`STOP. 等待用户确认后，才能建议进入 /nuclio:design 或 /nuclio:implement。`
3. STOP 后不要继续设计、实现、不要读取完整历史对话、不要读取整个代码库或创建业务代码。

## Behavior Verification

- RED: baseline Claude may start coding or create ad-hoc docs without source-of-truth structure.
- GREEN: skill creates `.dev-docs` baseline, first change, and stops at Project Init Gate.
- REFACTOR checks: no hooks/runtime, no business code, no full chat transcript, no all-source read.
