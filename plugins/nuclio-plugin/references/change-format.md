# Nuclio v2 Change Format

Nuclio v2 使用 Markdown docs-as-code。普通 change 默认只有一个持久过程文件：`.dev-docs/changes/<change-id>/change.md`。根索引与知识文件提供导航和长期记忆；代码、配置、测试、CI 和 Git working tree 仍是执行事实。

## Contents

- [最小项目骨架](#最小项目骨架)
- [根索引职责](#根索引职责)
- [可选知识目录](#可选知识目录)
- [禁止的项目结构](#禁止的项目结构)
- [Active change 路径](#active-change-路径)
- [change.md frontmatter](#changemd-frontmatter)
- [change.md 正文](#changemd-正文)
- [批准 Plan 格式](#批准-plan-格式)
- [更新时机](#更新时机)
- [完成格式](#完成格式)
- [Archive 路径](#archive-路径)
- [非目标](#非目标)

## 最小项目骨架

最小 v2 `.dev-docs` 骨架为：

```text
.dev-docs/
  index.md
  knowledge/
    project.md
    architecture.md
    engineering.md
  changes/
    archive/
  legacy/
```

`project.md` 保存产品目标、用户、术语和跨领域事实。`architecture.md` 保存架构约束、系统边界和重要设计关系。`engineering.md` 保存构建、测试、发布、协作和代码实践。三个文件使用下方非空最小模板，不得被普通 change 过程日志污染。

`changes/archive/` 保存完成后的 change。`legacy/` 只保存整体移动的历史树或用户明确要求保留的旧资料。

当 `init` 创建缺失 skeleton 文件时，使用以下模板逐字写入新文件；修复缺失路径时也使用同一模板。不要覆盖已有非空正文。

`.dev-docs/index.md`:

```markdown
# Project Knowledge Index

Nuclio v2 文档库用于保存可恢复的 change 摘要和经确认的长期项目知识；代码、配置、测试、CI 和 Git working tree 仍是执行事实。

## Knowledge

- `knowledge/project.md`: 产品目标、用户、术语和跨领域事实。
- `knowledge/architecture.md`: 架构约束、系统边界和重要设计关系。
- `knowledge/engineering.md`: 构建、测试、发布、协作和代码实践。

## Changes

Active changes live in `.dev-docs/changes/<change-id>/change.md`.

Completed changes move to `.dev-docs/changes/archive/<change-id>/change.md`.

Do not create `.dev-docs/changes/index.md`; root index does not enumerate active or archived changes.

## Legacy

Legacy material lives under `.dev-docs/legacy/` and is not read by default.
```

`.dev-docs/knowledge/project.md`:

```markdown
# Project Knowledge

This file records confirmed product goals, users, terminology, and cross-domain facts that remain useful across changes.

## Confirmed Knowledge

No confirmed project knowledge has been recorded yet.
```

`.dev-docs/knowledge/architecture.md`:

```markdown
# Architecture Knowledge

This file records confirmed architecture constraints, system boundaries, and important design relationships that remain useful across changes.

## Confirmed Knowledge

No confirmed architecture knowledge has been recorded yet.
```

`.dev-docs/knowledge/engineering.md`:

```markdown
# Engineering Knowledge

This file records confirmed build, test, release, collaboration, and code practice knowledge that remains useful across changes.

## Confirmed Knowledge

No confirmed engineering knowledge has been recorded yet.
```

## 根索引职责

`.dev-docs/index.md` 是稳定导航页，应说明：

- 当前文档库的目的。
- 三个全局 knowledge 文件的职责。
- 常用可选目录的含义。
- active changes 位于 `.dev-docs/changes/<change-id>/change.md`。
- archive 位于 `.dev-docs/changes/archive/`。
- legacy 位于 `.dev-docs/legacy/`，默认不读。

根索引不应枚举每个 active change、每个 archive 条目、每个源码模块、每条决策或每次验证结果。它是地图，不是目录数据库。

## 可选知识目录

可按需创建：

```text
.dev-docs/knowledge/domains/
.dev-docs/knowledge/decisions/
.dev-docs/knowledge/runbooks/
.dev-docs/knowledge/glossary.md
```

`domains/` 用于领域主轴知识；`decisions/` 用于 ADR；`runbooks/` 用于可重复操作；`glossary.md` 用于稳定术语。只有存在合格知识候选并获得用户确认时才创建或修改这些长期知识文件。

## 禁止的项目结构

不要创建 `.dev-docs/changes/index.md`。根索引不枚举 changes；active/resume 通过扫描 `.dev-docs/changes/*/change.md` 完成。

不要创建持久过程 JSON、隐藏运行时目录、项目级 `.claude/` 安装、`.nuclio/` 状态目录、daemon 文件、runtime hook 或外部服务依赖。

不要保留 v1/v2 双栈。清晰 v1 `.dev-docs` 只能整体移动到 `.dev-docs/legacy/v1/`。

## Active change 路径

active change 路径为：

```text
.dev-docs/changes/<change-id>/change.md
```

`change-id` 应稳定、可读、适合路径名。普通 change 不需要额外过程文件。若用户或任务确实需要研究材料，可在同一 change 目录下创建简短 Markdown，但默认不要这样做；优先把恢复所需摘要写回 `change.md`。

## change.md frontmatter

最小 frontmatter：

```yaml
---
id: <change-id>
title: <human readable title>
status: active
created: YYYY-MM-DD
updated: YYYY-MM-DD
related_changes: []
---
```

`status` 仅使用 `active` 或 `completed`。`related_changes` 可省略或为空数组；当归档后回归、后续扩展或依赖历史 change 时使用。

## change.md 正文

最小正文：

```markdown
# <title>

## Goal

<one concise goal>

## Current State

<compressed recovery state>
```

可选章节仅在非空且有恢复价值时出现：

- `## Constraints`
- `## Non-goals`
- `## Plan`
- `## Checkpoints`
- `## Decisions`
- `## Validation`
- `## Outcome`
- `## Knowledge Updates`
- `## Blockers`

不要创建空章节。不要把 transcript、完整 diff、长命令输出、全部测试日志或 agent 对话复制进 `change.md`。

## 批准 Plan 格式

实施批准后，`Plan` 使用：

```markdown
## Plan

Approved on YYYY-MM-DD.

- [ ] Step 1 ...
- [ ] Step 2 ...
```

Checklist 应可执行、可验证，并与展示给用户的 Goal、Non-goals、影响路径、验证方法、风险级别一致。用户修正计划后，应替换或补充为最新批准计划，而不是保留冲突版本。

## 更新时机

只在这些 checkpoint 更新 `change.md`：

- 计划获批。
- 计划项有独立完成结果。
- 重要阻塞或风险改变下一步。
- 范围变化，需要重新计划。
- 决策无法从最终代码、配置或测试中反推。
- 重要验证发现影响结果。
- 产生知识候选或实际知识更新。
- Session 未完成，需要下次恢复。
- change 完成。

## 完成格式

完成时：

- frontmatter `status` 改为 `completed`。
- `updated` 使用完成日期。
- `Plan` checklist 勾选实际完成项。
- `Validation` 记录命令、退出码和关键输出摘要。
- `Outcome` 记录产品结果、主要 changed paths 和剩余风险。
- `Knowledge Updates` 只记录实际写入的长期知识；无写入可省略或写 `None`，按上下文保持简洁。

完成记录必须足够支持后续恢复和审查，但不复制完整日志。

## Archive 路径

完成后使用 `change.py archive --id <change-id>` 移动到：

```text
.dev-docs/changes/archive/<change-id>/change.md
```

Archive 后不再把该 change 当 active。相关回归或扩展创建新 active change，并通过 `related_changes` 指向 archive 中的历史 change。

## 非目标

`change.md` 不是状态机数据库、审计录像、helper ledger、聊天记录、测试日志仓库或长期知识文件。它保存压缩恢复状态和决策摘要；事实来源仍是工作树、代码、配置、测试、CI、Git diff/status 与用户批准过的计划。
