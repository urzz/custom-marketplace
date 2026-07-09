# Nucl.io File Protocol

## Contents
- [Core Principle](#core-principle)
- [Directory Roles](#directory-roles)
- [.dev-docs Layout](#dev-docs-layout)
- [Change Artifact Protocol](#change-artifact-protocol)
- [State Protocol](#state-protocol)
- [State Transition Rules](#state-transition-rules)
- [Gate Readiness Rules](#gate-readiness-rules)
- [State Merge Rules](#state-merge-rules)
- [Future Deterministic Helper Boundary](#future-deterministic-helper-boundary)
- [Hard Rules](#hard-rules)

## Core Principle

Nucl.io 的事实源是文件，不是对话。

- 对话用于澄清。
- `.dev-docs/` 保存稳定项目知识和当前 change 事实。
- `.nuclio/` 只保存工具运行态、缓存和临时状态。
- MVP 不实现 `.nuclio/` runtime，只在协议中保留该边界。

## Directory Roles

| Path | Role | Git |
|---|---|---|
| `.dev-docs/` | source-of-truth for project knowledge and current change facts | yes |
| `.nuclio/` | runtime/cache/temp state only | usually gitignored |

## .dev-docs Layout

Project Init 使用以下 baseline layout：

```text
.dev-docs/
  index.md
  project/
    brief.md
    principles.md
    scope.md
  product/
    index.md
    glossary.md
    personas.md
    use-cases.md
  architecture/
    index.md
    overview.md
    constraints.md
    decisions.md
  engineering/
    index.md
    stack.md
    coding-style.md
    testing.md
    deployment.md
  domain/
    index.md
    model.md
    workflows.md
  changes/
    index.md
```

## Change Artifact Protocol

每个结构化 change 使用：

```text
.dev-docs/changes/<change-id>/
  brief.md
  spec.md
  design.md
  plan.yaml
  state.json
  context/
    implement.jsonl
    verify.jsonl
  research/
    notes.md
  evidence/
    test-output.md
    review.md
```

`<change-id>` 应使用 `YYYY-MM-DD-short-slug`；第一个 MVP change 可以使用 `0001-mvp`。

Artifact existence is not gate approval:

- `brief.md`、`spec.md`、`design.md`、`plan.yaml` 或 context manifests 存在，只表示草稿产物存在。
- 后续阶段不得仅因 artifact 存在而判断上一阶段已通过。
- Gate readiness 必须来自 `state.json.gates.<stage>: approved`，或来自当前轮用户对该 gate 的明确授权。

## State Protocol

`state.json` 跟踪当前 phase、status、current task、gates 和可审查产物路径。推荐 phases：

```text
brief
design
implement
verify
fold
archived
```

推荐 statuses：

```text
draft
in_progress
blocked
approved
completed
```

`state.json` 是 workflow progress 的显式状态机。MVP skills 在定位 current change 后，应使用本协议更新状态；不得依赖对话记忆或 artifact existence 推断 gate approval。

推荐最小 shape：

```json
{
  "phase": "brief",
  "status": "draft",
  "current_task": null,
  "gates": {
    "brief": "pending",
    "design": "pending"
  },
  "artifacts": {
    "brief": "brief.md",
    "spec": "spec.md",
    "design": "design.md",
    "plan": "plan.yaml",
    "implement_context": "context/implement.jsonl",
    "verify_context": "context/verify.jsonl"
  }
}
```

The shape is intentionally extensible. Skills must preserve unknown keys, nested metadata, existing gate values, current task tracking, and evidence fields.

## State Transition Rules

Use these transitions for prompt/protocol stages:

1. **Stage entry** — once a skill has located the current change and is about to execute that stage, merge:
   - `phase: "<stage>"`
   - `status: "in_progress"`
   - preserve existing `gates`, `artifacts`, `current_task`, metadata, and unknown keys
2. **Gate pending** — after the stage writes its reviewable artifacts but before user approval, merge:
   - `phase: "<stage>"`
   - `status: "draft"`
   - `gates.<stage>: "pending"`
   - artifact paths for outputs produced by that stage
3. **Gate approval** — only when the user explicitly confirms the gate in the current turn, merge:
   - `gates.<stage>: "approved"`
   - `status: "approved"` only if no next stage is being entered in the same turn
   - if immediately entering the next stage, the next stage entry may set `phase` to the next stage and `status: "in_progress"`
4. **Failure or blocker** — if required artifacts, manifests, validation commands, or approvals are missing, merge `status: "blocked"` only when the skill has concrete blocker evidence; otherwise STOP and ask without inventing state.

## Gate Readiness Rules

- `brief.md` + `spec.md` existence does not mean Brief Gate is approved.
- `design.md` + `plan.yaml` + context manifests existence does not mean Design Gate is approved.
- A stage may proceed past the previous gate only when one of these is true:
  - `state.json.gates.<previous-stage>` is exactly `"approved"`.
  - The user explicitly approves that previous gate in the current turn.
  - The skill explicitly asks whether to continue with a provisional artifact, and the user explicitly chooses to continue.
- If artifacts exist but the previous gate is `missing`, `pending`, `draft`, or ambiguous, STOP and ask for confirmation; do not silently proceed.
- Provisional continuation must be labeled in generated artifacts and reported as risk.

## State Merge Rules

All `state.json` updates must be preserve/merge updates:

- Do not rewrite `state.json` as a minimal object.
- Do not delete unknown top-level keys.
- Do not delete nested metadata, evidence, current task details, or existing gate values unrelated to the current transition.
- Do not convert a gate to `approved` because an artifact exists.
- Only update fields required by the current transition.
- If JSON is invalid or cannot be parsed, STOP and report the parse problem instead of overwriting the file.

## Future Deterministic Helper Boundary

A future script may be added only as a small deterministic validate/merge helper for `state.json`. Such a helper may validate allowed transitions and preserve/merge fields, but it must not:

- auto-advance gates without user confirmation;
- become a Nuclio runtime, daemon, CLI product, hook, MCP server, or background automation;
- replace HITL review gates;
- read full conversation history or inject broad context.

## Hard Rules

- 不要把 chat history 当作 source-of-truth。
- 不要默认读取全部 `.dev-docs/`。
- 不要默认读取全部 source files。
- 不要把长篇 raw logs 写入 `.dev-docs/`。
- 不要把 raw 或 temporary runtime state 放入面向 Git 的 knowledge files。
- 优先使用小而稳定的 summaries，而不是完整 process transcripts。
- 不要把 artifact existence 当作 gate approval。
- 不要仅因 `brief.md`、`spec.md`、`design.md`、`plan.yaml` 或 context manifests 存在就推进下一阶段。
- 不要把 `state.json` 重写成最小 JSON；必须 preserve/merge existing fields。
- 不要在没有当前轮用户明确确认的情况下把任何 `gates.<stage>` 设置为 `approved`。
