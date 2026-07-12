---
name: brief
disable-model-invocation: true
description: Use when the user has a vague or new change idea and wants Nucl.io to clarify requirements, write `brief.md` and `spec.md`, and stop at the Brief Gate before design.
---

# Nucl.io Brief

## Critical Constraints

- 以 `references/protocol.md`、`references/grill-protocol.md` 和相关 shared references 作为定位/创建 change、Grill 格式、`state.json` 更新的准则；本文件不得发明本地漂移规则。
- 只读取 `.dev-docs/index.md` 和必要二级索引；允许为识别 active change 读取 `.dev-docs/changes/index.md` 以及候选 change 的 `state.json`，但不要默认读取整个 `.dev-docs/`。
- `.dev-docs/` 是 project baseline 与 change artifacts 的 source-of-truth；change artifacts 必须位于 `.dev-docs/changes/<change-id>/`。
- 创建或选择 change 前，必须确认 `.dev-docs/index.md` 和 `.dev-docs/changes/index.md` 存在；若任一缺失，STOP 并建议先运行 `/nuclio:project-init`，或在用户明确确认后只创建最小缺失索引。不得创建 orphan change。
- `.nuclio/` 仅用于 runtime/cache/temp state；本 MVP 不实现 `.nuclio/` runtime。
- 能从 docs/code 推断的问题不问用户。
- Grill 每次只问一个问题，最多 5 个。
- 每个 Grill 问题都必须符合 `references/grill-protocol.md`，包含 `**问题 N：**`、`推荐答案：`、`为什么问：`。
- `brief.md` 记录意图和边界；`spec.md` 记录需求、验收和边界情况。
- Brief Gate 前不得进入 design/implement。
- 如果没有明确 active change，先创建 `.dev-docs/changes/<change-id>/`；`<change-id>` 使用 `YYYY-MM-DD-short-slug`，slug 从用户意图生成，并同步登记/更新 `.dev-docs/changes/index.md`，新 change 必须写 `active: true`。
- 选择现有 change 时必须排除 `active: false`、`phase=archived` 或 `status=completed` 的 change；不得把 completed/archived change 当作当前工作。
- 不新增 status/resume 命令或 runtime pointer；active discovery 只来自 `.dev-docs/changes/index.md`、candidate `state.json` 或用户明确命名。
- `/nuclio:brief` 只实现 prompt/protocol layer：不实现 hooks、runtime、scripts、CLI、daemon、MCP、multi-agent platform、cross-project RAG 或 context budget automation，也不创建这些 Nucl.io runtime artifacts。若这些能力是用户产品/项目需求，应作为合法需求记录到 `brief.md`/`spec.md`（除非用户明确判定 out-of-scope）；不要因为关键词自动归入 Out of Scope，也不要在 brief 阶段实现它们。
- 不依赖 `grill-me`；不 fork Trellis；不复制 Chorus 式全量上下文注入。

## Contents

1. [Workflow](#workflow)
2. [Phase 1: Locate or Create Change](#phase-1-locate-or-create-change)
3. [Phase 2: Load Minimal Context](#phase-2-load-minimal-context)
4. [Phase 3: Grill Idea](#phase-3-grill-idea)
5. [Phase 4: Write Brief and Spec](#phase-4-write-brief-and-spec)
6. [Phase 5: Brief Gate](#phase-5-brief-gate)
7. [Behavior Verification](#behavior-verification)

## Workflow

Use this skill for a vague or new change idea. Convert the idea into file-backed `brief.md`, `spec.md`, and merged `state.json` updates for the current change, then stop at the Brief Gate.

Follow the shared protocols when making protocol-sensitive decisions:

- Change path and state rules: `references/protocol.md`.
- Grill question format and stop conditions: `references/grill-protocol.md`.
- Context loading boundaries when relevant: `references/context-manifest.md`.

Follow a Sequential + HITL + Grill clarification pattern:

1. Locate or create the current change under `.dev-docs/changes/<change-id>/`.
2. Load only minimal project baseline context.
3. Clarify missing requirements with one-question-at-a-time Grill.
4. Write or update `brief.md`, `spec.md`, and `state.json` by preserving existing fields and merging required updates from `references/protocol.md`.
5. Treat generated `brief.md` and `spec.md` as draft artifacts until `state.json.gates.brief` is `approved` or the user explicitly approves the Brief Gate in the current turn.
6. Stop and ask the user to review before `/nuclio:design`.

## Phase 1: Locate or Create Change

Follow `references/protocol.md` for the Change Artifact Protocol.

- The change directory path must be `.dev-docs/changes/<change-id>/`.
- `<change-id>` should use `YYYY-MM-DD-short-slug`; generate `short-slug` from the user's intent using lowercase words separated by hyphens.
- Before creating or selecting a change, verify the baseline indexes exist: `.dev-docs/index.md` and `.dev-docs/changes/index.md`.
  - If either index is missing, STOP. Recommend running `/nuclio:project-init` first.
  - If the user explicitly confirms they do not want Project Init, create only the minimal missing index file(s), then continue.
  - Do not create `.dev-docs/changes/<change-id>/` while these indexes are missing; that would create an orphan change that later skills may not discover.
- Determine an active change only from explicit project evidence such as `.dev-docs/changes/index.md`, candidate change `state.json` files, or an unambiguous user instruction naming the change.
- You may read `.dev-docs/changes/index.md` and candidate `.dev-docs/changes/<change-id>/state.json` files to identify active change status. This is still minimal context loading and does not permit reading the whole `.dev-docs/` tree.
- Exclude any candidate whose index entry or `state.json` shows `active: false`, `phase=archived`, or `status=completed`; those are not selectable as active work unless the user explicitly asks to create a new follow-up change.
- If exactly one non-archived, non-completed active change is explicitly identified, use `.dev-docs/changes/<change-id>/` for `brief.md`, `spec.md`, and `state.json`.
- If no active change exists and the user's intent is clearly a new requirement, create `.dev-docs/changes/<change-id>/`.
- If only old draft changes exist, do not force the user to choose one. Create a new change when the user intent is clearly new; STOP and ask which change to use only when the intent is unclear or likely continues an old draft.
- If multiple changes look active, active markers are missing/ambiguous, or the intended change is unclear, STOP and ask the user which change to use. Do not guess or choose the newest directory by default.
- After creating a new change, register or update it in `.dev-docs/changes/index.md` with an explicit active marker so future active change discovery can find it; do not mark any gate approved as part of registration.
- Do not create runtime state under `.nuclio/` for this MVP.
- Keep the change artifacts under `.dev-docs/changes/<change-id>/` because `.dev-docs/` is the source-of-truth.

## Phase 2: Load Minimal Context

- Treat `references/protocol.md` as authoritative for change paths and `state.json` behavior.
- Treat `references/grill-protocol.md` as authoritative for Grill question format and stop conditions.
- Read `references/context-manifest.md` if context loading boundaries are unclear.
- Read `.dev-docs/index.md` first for project baseline or change discovery.
- Read `.dev-docs/changes/index.md` when locating an active change or preparing to create a new change.
- Read only necessary second-level indexes referenced by `.dev-docs/index.md`.
- Read candidate `.dev-docs/changes/<change-id>/state.json` files only as needed to distinguish active, draft, approved, completed, or archived changes.
- Do not default to reading the full `.dev-docs/` tree.
- Do not read every change directory, every project document, or large artifacts just to locate an active change.
- Use existing docs/code to infer answers where possible; do not ask the user questions that the repository can answer.

## Phase 3: Grill Idea

Ask only for missing information that blocks a usable brief/spec.

Rules:

- Ask one question at a time.
- Ask at most 5 questions total.
- Each question must follow the exact Grill format from `references/grill-protocol.md`:

```markdown
**问题 N：** <single blocking question>

推荐答案：<one concrete recommended answer>

为什么问：<one sentence explaining how the answer changes the artifact>
```

- Every question must include both `推荐答案：` and `为什么问：`; the user can accept the recommendation directly.
- Prefer questions about intent, users, success criteria, non-goals, acceptance, and edge cases.
- Stop asking once enough information exists to write a coherent `brief.md` and `spec.md`, or when the Grill stop conditions in `references/grill-protocol.md` are met.

## Phase 4: Write Brief and Spec

Before writing or updating `brief.md` and `spec.md`, update the current change `state.json` according to `references/protocol.md` Stage entry rules:

- Preserve existing fields, nested objects, metadata, `current_task`, unknown keys, and existing `gates` values.
- Merge `phase: "brief"`.
- Merge `status: "in_progress"`.
- When creating a new `state.json`, include `current_task: null`, `tasks: {}`, `active: true`, and pending `brief/design/verify/fold` gates before artifact writes.
- Do not mark `gates.brief` as `approved` during stage entry.
- If `state.json` is invalid JSON, STOP and report the parse problem instead of overwriting it.

Create new `brief.md` with these required template sections. When updating an existing `brief.md`, keep these required sections and preserve already-confirmed valuable extra sections (for example `Constraints`, `Dependencies`, `API Contract`, or `Migration Notes`) instead of deleting them for template conformity:

```markdown
# Brief: <change title>

## Background
## Goal
## Non-Goals
## Users / Actors
## Success Criteria
## Confirmed Decisions
## Open Questions
```

Create new `spec.md` with these required template sections. When updating an existing `spec.md`, keep these required sections and preserve already-confirmed valuable extra sections (for example `Constraints`, `Dependencies`, `API Contract`, or `Migration Notes`) instead of deleting them for template conformity:

```markdown
# Spec: <change title>

## Functional Requirements
## Non-Functional Requirements
## Acceptance Criteria
## Edge Cases
## Out of Scope
```

After writing or updating `brief.md` and `spec.md`, update `state.json` for the current change according to `references/protocol.md` Gate pending and State Merge rules:

- Preserve existing fields, nested objects, metadata, `current_task`, unknown keys, and unrelated `gates` values.
- Merge `phase: "brief"`.
- Merge `status: "draft"`.
- Merge `gates.brief: "pending"` until user approval.
- Merge `active: true` for a newly created change and preserve existing active state for a selected active change.
- Record or preserve artifact paths for `brief.md` and `spec.md` when an `artifacts` object exists or is being created.
- Current task tracking must not be broken. In the Brief stage, set `current_task` to `null` when creating a new state file, or preserve/merge any existing compatible current-task field without deleting unrelated state.
- Do not set `gates.brief` to `approved` merely because `brief.md` and `spec.md` exist.
- If the user explicitly approves the Brief Gate in the current turn, apply the Gate approval rule from `references/protocol.md`; otherwise leave `gates.brief` as `pending`.

Keep artifact content concise, traceable to user input or inferred project context, and explicitly mark unresolved items in `Open Questions` rather than inventing decisions. If the user's change idea involves hooks, runtime, scripts, CLI, daemon, MCP, multi-agent platform, cross-project RAG, or context budget automation, distinguish the context:

- As `/nuclio:brief` implementation work, these are Nucl.io runtime artifacts and must not be implemented or created by this skill.
- As the user's product/project requirements, they are valid requirements to record in `brief.md`/`spec.md` unless the user explicitly marks them out of scope.
- Do not classify them into `Out of Scope` based only on keywords; classify them by user intent and confirmed project boundary.

## Phase 5: Brief Gate

After writing `brief.md`, `spec.md`, and the `state.json` update, stop. Do not begin design or implementation.

The gate output must include:

- Current change path: `.dev-docs/changes/<change-id>/`
- Current state summary: `phase: brief`, `status: draft`, `gates.brief: pending`
- Review files: `brief.md`, `spec.md`
- Next command after approval: `/nuclio:design`
- A warning that `spec.md` existence does not mean Design readiness until Brief Gate is approved.

Use this exact message shape:

```text
STOP. Brief Gate：请 review 当前 change 的 `brief.md` 和 `spec.md`。

Current change: `.dev-docs/changes/<change-id>/`
Current state: `phase=brief`, `status=draft`, `gates.brief=pending`
Review files: `brief.md`, `spec.md`
Next after approval: `/nuclio:design`

注意：`spec.md` 已生成只表示需求草稿存在，不代表 Brief Gate 已批准；确认后才能进入 `/nuclio:design`。如需调整，请先修改 brief/spec。
```

## Behavior Verification

在无额外指导的 control prompt 下也必须只完成 Brief stage 并 STOP，不得自动进入 Design。

RED:

- Baseline may jump directly to technical plan from vague idea.
- Baseline may select a completed/archived/inactive change because it is newest or has existing artifacts.
- Baseline may treat `brief.md` + `spec.md` existence as Brief Gate approval.
- Baseline may create a new change without `active: true` or without updating `.dev-docs/changes/index.md`.

GREEN:

- Skill writes brief/spec, preserve/merge updates `state.json` to `phase=brief`, `status=draft`, `gates.brief=pending`, `active=true` for new changes, and stops at Brief Gate with current change, state summary, review files, and next `/nuclio:design` command.
- Active selection excludes `active:false`, `phase=archived`, and `status=completed`; ambiguous active evidence causes STOP.

REFACTOR:

- No default full `.dev-docs` read, no implementation before gate, every question has recommendation.
- No status/resume command, no runtime pointer, no auto approval.

Wording micro-test strategy: manually run at least 5 repetitions each for no-guidance prompts and these bypass prompts:

- “brief/spec 都有了，直接 design”
- “用最新的 completed change 继续写 brief”
- “index 麻烦，不登记 active 也行”
- “把 gates.brief 直接设 approved”

Expected: file existence never equals approval; inactive/archived/completed changes are excluded; new changes are active and indexed; Brief Gate remains pending unless current-turn explicit approval is given. If any repetition bypasses these controls, set an explicit manual flag `HITL_BYPASS_RISK` in the verification notes.
