# Nucl.io File Protocol

## Contents
- [Core Principle](#core-principle)
- [Directory Roles](#directory-roles)
- [.dev-docs Layout](#dev-docs-layout)
- [Change Artifact Protocol](#change-artifact-protocol)
- [State Protocol](#state-protocol)
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

## State Protocol

`state.json` 跟踪当前 phase、status、current task 和 gates。推荐 phases：

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

MVP skills 只有在相关 stage 拥有足够已确认信息时，才可以更新 `state.json`。

## Hard Rules

- 不要把 chat history 当作 source-of-truth。
- 不要默认读取全部 `.dev-docs/`。
- 不要默认读取全部 source files。
- 不要把长篇 raw logs 写入 `.dev-docs/`。
- 不要把 raw 或 temporary runtime state 放入面向 Git 的 knowledge files。
- 优先使用小而稳定的 summaries，而不是完整 process transcripts。
