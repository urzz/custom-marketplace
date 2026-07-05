# Context Manifest Protocol

## Contents
- [Purpose](#purpose)
- [Files](#files)
- [Implement Manifest](#implement-manifest)
- [Verify Manifest](#verify-manifest)
- [Context Budget](#context-budget)
- [Forbidden Inputs](#forbidden-inputs)

## Purpose

Context manifest 声明某个 stage 可以加载哪些 stable context。它防止 implementation 和 verification 继承完整 conversation history 或每个 project document。

## Files

```text
.dev-docs/changes/<change-id>/context/
  implement.jsonl
  verify.jsonl
```

每一行都是 JSONL：

```json
{"path":".dev-docs/project/brief.md","kind":"project","mode":"required","reason":"理解项目目标和边界"}
```

## Implement Manifest

`implement.jsonl` 可以包含：

- 当前 task 需要的 project brief 或 principles
- 当前 task 需要的 architecture constraints
- engineering testing guidance
- 当前 change 的 spec/design/plan
- focused research notes
- 作为 navigation hints 的关键 contract/schema/interface files

它不得包含 full chat history、raw logs、all `.dev-docs` documents、all source files、comments 或 reviewer history。

## Verify Manifest

`verify.jsonl` 应小于 `implement.jsonl`，并且通常包含：

- testing guidance
- 当前 change spec acceptance criteria
- plan task acceptance criteria
- verification 必须检查的 explicit architecture constraints

Verification 也应检查当前 diff。

## Context Budget

推荐 context budget：

| Stage | Recommended upper bound |
|---|---:|
| SessionStart breadcrumb | < 1k |
| Brief | 20k-40k |
| Design | 40k-80k |
| Implement single task | 30k-60k |
| Verify | 20k-40k |
| Fold | 20k-40k |

MVP 不自动化 token counting；budget 是行为约束。

## Forbidden Inputs

默认不要加载以下内容：

- full conversation history
- all `.dev-docs/`
- all source files
- proposal/comment/reviewer history
- raw long logs
- session journals
- daemon task history
