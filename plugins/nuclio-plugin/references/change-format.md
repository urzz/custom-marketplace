# Nuclio v2 Change Format

本文件是 `.dev-docs` 目录、`change.md`、`plan.yaml`、`state.yaml`、checkpoint evidence 与 archive artifact 的格式权威。生命周期决策见 `workflow.md`。

## Project Skeleton

```text
.dev-docs/
├── index.md
├── knowledge/
│   ├── project.md
│   ├── architecture.md
│   └── engineering.md
├── changes/
│   └── archive/
└── legacy/
```

不得创建 `.dev-docs/changes/index.md`、隐藏运行时目录、archive manifest 或 hidden archive backup。

`.dev-docs/index.md` 模板：

```markdown
# Project Knowledge Index

Nuclio v2 文档库用于保存可恢复的 change 摘要和经确认的长期项目知识；代码、配置、测试、CI 和 Git working tree 仍是执行事实。

## Knowledge

- `knowledge/project.md`: 产品目标、用户、术语和跨领域事实。
- `knowledge/architecture.md`: 架构约束、系统边界和重要设计关系。
- `knowledge/engineering.md`: 构建、测试、发布、协作和代码实践。

## Changes

Active changes live in `.dev-docs/changes/<change-id>/` with `change.md`, `plan.yaml`, and `state.yaml`.

Completed changes move to `.dev-docs/changes/archive/<change-id>/` with the complete `change.md`, `plan.yaml`, and terminal `state.yaml` record.

Do not create `.dev-docs/changes/index.md`; root index does not enumerate active or archived changes.

## Legacy

Legacy material lives under `.dev-docs/legacy/` and is not read by default.
```

三个知识文件分别使用以下标题和说明；初始 `Confirmed Knowledge` 内容均为明确的 “No confirmed ... has been recorded yet.”，不得替换为含糊 placeholder：

```markdown
# Project Knowledge

This file records confirmed product goals, users, terminology, and cross-domain facts that remain useful across changes.

## Confirmed Knowledge

No confirmed project knowledge has been recorded yet.
```

```markdown
# Architecture Knowledge

This file records confirmed architecture constraints, system boundaries, and important design relationships that remain useful across changes.

## Confirmed Knowledge

No confirmed architecture knowledge has been recorded yet.
```

```markdown
# Engineering Knowledge

This file records confirmed build, test, release, collaboration, and code practice knowledge that remain useful across changes.

## Confirmed Knowledge

No confirmed engineering knowledge has been recorded yet.
```

## Three-Layer Authority

Active change 必须位于：

```text
.dev-docs/changes/<change-id>/
├── change.md
├── plan.yaml
└── state.yaml
```

- `change.md`：人类可读 Spec authority，保存 Goal、Context、Constraints、Non-goals、Acceptance 和完成结果。
- `plan.yaml`：批准合同 authority，保存 revision、风险、review policy、写路径、Tasks 和 validation。
- `state.yaml`：当前恢复 State，由 `change.py` 独占写入。
- Git、代码、配置、测试、CI：产品事实。

State 不保存完整 diff、长日志、transcript、agent messages、文件内容 snapshot 或完整 transition history。

## Change ID And Paths

`change-id` 只允许小写字母、数字与单个连字符分隔的段，不能使用 `archive`、`.`、`..`，不能包含斜杠、反斜杠、控制字符或 symlink escape。

所有 Plan/knowledge path 必须是 repo-relative 正向路径，不得使用绝对路径、`..` 或跳出项目根目录。`allowed_paths` 是 change-level 产品写边界，不是 per-Task ownership。

## Active change.md

frontmatter exact fields：

```yaml
id: example-change
title: Example change
status: active
created: 2026-07-29
updated: 2026-07-29
related_changes: []
```

正文最小形态：

```markdown
# Example change

## Goal

<明确目标>

## Context

<必要背景>

## Constraints

<明确约束，或明确说明无额外约束>

## Non-goals

<明确非目标，或明确说明无额外非目标>

## Acceptance Criteria

- <可观察验收>
```

规则：

- frontmatter 由 PyYAML safe dump 生成；title 中的冒号、引号、`#` 必须安全，换行和控制字符被拒绝。
- `id` 必须与目录名和 Plan `change_id` 一致；H1 必须与 title 一致。
- `related_changes` 是无重复、无 self-reference 的合法 id list。
- 五个必要 section 必须唯一且非空；`Decisions` 可选，存在时也必须非空。
- `TODO`、`TBD`、`placeholder`、`待补充`、`待确认` 和 `<...>` 等草稿标记不能进入批准 checkpoint。
- `validate-plan --id` 与 `init-state` 使用同一 Spec validator。

## Canonical plan.yaml

4.2.0 及之后版本新建或重新批准的 Plan 只接受以下 exact schema：

```yaml
schema_version: 2
change_id: example-change
revision: 1
risk_level: medium
review_policy: final
execution:
  mode: delegated
  rationale: The change spans implementation and tests and requires an independent executor.
summary: Implement the approved behavior and cover it with tests.
allowed_paths:
  - src/
  - tests/
tasks:
  - id: 1
    name: Implement behavior
    steps:
      - Update the implementation.
      - Add focused tests.
    acceptance:
      - The requested behavior is observable.
    validation:
      - python3 -m unittest tests.test_example
    review: task-and-final
```

顶层必要且唯一字段：

```text
schema_version
change_id
revision
risk_level
review_policy
execution
summary
allowed_paths
tasks
```

Task 必要字段为 `id`、`name`、`steps`、`acceptance`、`validation`；唯一可选字段为 `review`。

约束：

- `schema_version` 当前为 `2`，revision 为正整数，Task id 从 `1` 连续递增。
- `risk_level` 为 `low|medium|high`；`review_policy` 为 `self|final|task-and-final`。
- `execution` exact fields 为 `mode` 与非空 `rationale`；`mode` 为 `delegated|direct`。
- `high` 必须使用 `task-and-final`。
- change-level `final` 下，少数 Task 可写 `review: task-and-final`；其他组合拒绝冗余或无意义 override。
- `allowed_paths`、steps、acceptance、validation 均为非空、去重、无 placeholder 的 string list。
- Task checkpoint subject 由 helper 派生：`task(<change-id>): complete task <task-id>`。
- canonical Plan 不含 `repair_policy`、Task-level `delegate`/`executor` 或显式 `checkpoint_subject`。

`delegated` 是默认执行策略，所有 Task 与 repair 使用 `subagent`。`direct` 是受控例外，helper 要求：

- `risk_level: low`；
- `review_policy: self`；
- Plan 恰好一个 Task；
- `allowed_paths` 最多三个，全部为不以 `/` 结尾的精确文件。

Coordinator 还必须确认并在 rationale/Gate 中展示：目标文件在批准前已确定、不需要批准后广泛探索、不涉及公共 API、数据模型、dependency、安全、权限、migration、并发、外部副作用或不可逆动作，并且存在明确的定向 validation。语义条件变化时必须改为 `delegated` 或修订 Plan 后重新批准。

YAML loader 拒绝 duplicate key，限制文件大小，使用 safe load/dump，并进行 exact keys、类型、路径和跨文件 identity 校验。不要增加 requirement graph、DAG scheduler、owner routing 或第二个 validator。

### Legacy Active Plan

已有合法 `state.yaml` 的 4.1.x schema v1 active Plan 可在恢复命令中读取；其未开始 Task 与后续 repair 默认要求 `subagent`。已有合法 State 的 4.0.x active change 也可读取旧 exact schema，包括固定 `repair_policy: in-scope`、legacy `delegate`、`review`、`checkpoint_subject`；Task 的 `delegate: main` 保持 main，`subagent|auto` 归一为 subagent。这些 variant 只用于兼容既有冻结 State，不自动重写 Plan，也不能用于新的 `validate-plan`/`init-state` 批准。未初始化 State 的 schema v1 草稿必须升级为 schema v2 后才能批准。

## Initial state.yaml

`init-state` 创建的 State 至少保存：

```yaml
schema_version: 1
change_id: example-change
plan_revision: 1
plan_sha256: <sha256>
spec_sha256: <sha256>
git_branch: main
initial_head: <pre-approval-head>
approval_checkpoint: <approval-commit-sha>
current_head: <approval-commit-sha>
status: ACTIVE
phase: READY
current_task_id: null
next_action: DISPATCH_TASK
```

State 不保存绝对 `repo_root`。approval checkpoint subject 固定为：

```text
state(<change-id>): initialize approved change state
```

`initial_head` 是提交前 HEAD；`approval_checkpoint` 是批准提交；`current_head` 是最近已接受的 Task/repair checkpoint。批准 commit tree 必须含完整三件套并匹配批准 Spec/Plan bytes。

## Task Evidence

Task 开始后 State 保存 `task_base`、从 Plan 派生的 `executor` 和 helper 派生 subject。调用方不能覆盖 executor。`record-task` 的 validation evidence 形态：

```yaml
validation:
  status: PASS
  head: <task-checkpoint-sha>
  commands:
    - command: python3 -m unittest tests.test_example
      exit_code: 0
  summary: 12 tests passed.
```

CLI 必须为每条 Plan validation 提供一个 `--validation-command` 与对应 `--validation-exit-code`。顺序和值精确匹配；PASS 的 exit codes 全为 `0`；summary 非空。helper 自动绑定 checkpoint SHA，并验证 parent、subject、changed paths、allowed paths 与空 index。

## Review Evidence

Task review：

```yaml
status: PASS
base: <task-base>
head: <task-checkpoint>
reviewer: subagent
summary: No blocking findings.
evidence:
  - src/example.py:42
```

Final review：

```yaml
status: PASS
base: <approval-checkpoint>
head: <current-head>
reviewer: subagent
summary: Whole-change integration review passed.
evidence:
  - Reviewed the complete approved range.
```

base/head 由 helper 推导；需要 `record-review` 的 task/final review 必须来自 fresh `nuclio:readonly-reviewer`，State 为 schema 兼容仍记录 `reviewer: subagent`，不保存 agent 名称或 transcript。调用者只提供 scope、status、summary、evidence，以及 FAIL 所需 contract/paths。PASS 的 summary/evidence 不得同时为空。

## Whole-Change Validation

```yaml
validation:
  status: PASS
  head: <current-head>
  commands:
    - command: python3 -m unittest discover -s tests
      exit_code: 0
  summary: Full suite passed.
```

至少一个 command；command 与 exit code 数量一致；PASS 全为 `0`。FAIL 至少有一个非零 code，并保存短 summary 与必要 paths/evidence。`complete` 检查 evidence head 仍等于 State current HEAD。

## Repair Evidence

每个获批 repair 使用 helper 返回的 base 与 subject 创建一个 checkpoint。`record-repair` 同样要求 validation command、exit code 与 summary。repair 后旧 whole-change validation 失效；受影响 final review 也按 `next_action` 重置。State 不增加 finding ledger、owner mapping 或 automatic fixer 状态。

## Knowledge Result

`complete` 写入紧凑结果：

```yaml
knowledge:
  result: NO_OP
  paths: []
```

`knowledge.result` 只允许 `NO_OP|APPLIED|PARTIAL|REJECTED`：

- `NO_OP`、`REJECTED` 的 paths 必须为空。
- `APPLIED`、`PARTIAL` 的 paths 必须非空、去重，并精确对应 working-tree change。
- path 只允许 `.dev-docs/knowledge/**` 和必要的 `.dev-docs/index.md`。
- State 不保存知识正文。

成功完成后的关键 State：

```yaml
status: COMPLETED
phase: COMPLETED
next_action: ARCHIVE
current_task_id: null
blocker: null
knowledge:
  result: NO_OP
  paths: []
```

## Completion change.md

完成记录保留批准 Spec 原文和顺序，只允许 frontmatter `status: completed`、`updated` 更新，以及 superseded 情况下由 State 派生的 successor relation。随后追加四个非空 section：

```markdown
## Outcome

<实际结果与 changed paths 摘要>

## Validation

<命令、exit codes 与关键结果摘要>

## Knowledge Updates

<NO_OP、APPLIED、PARTIAL 或 REJECTED 及相关路径>

## Residual Risks

<已知残余风险；没有时明确写无>
```

archive 会从 approval checkpoint 读取批准 Spec，结构化比较 `id`、`title`、`created`、normal relation、Goal、Context、Constraints、Non-goals、Acceptance Criteria 与批准时存在的 Decisions。除允许的终态更新外发生删除或改写时返回 `SPEC_HISTORY_DRIFT`。

## Complete Archive

新归档路径完整保留三件套：

```text
.dev-docs/changes/archive/<change-id>/
├── change.md
├── plan.yaml
└── state.yaml
```

归档 subject：

```text
archive(<change-id>): retain complete change record
```

无知识写入时，commit changed paths 必须精确覆盖：

```text
.dev-docs/changes/<id>/change.md
.dev-docs/changes/<id>/plan.yaml
.dev-docs/changes/<id>/state.yaml
.dev-docs/changes/archive/<id>/change.md
.dev-docs/changes/archive/<id>/plan.yaml
.dev-docs/changes/archive/<id>/state.yaml
```

`APPLIED`/`PARTIAL` 时只额外允许 `state.knowledge.paths` 中的精确路径。active 和 archive 目录都必须是 exact artifact set，regular files 且非 symlink。archive commit 验证 parent、subject、paths、HEAD 和空 index；不自动 push、删除分支、切换分支、squash、reset、rebase、stash 或改写历史。

`show --archived --artifact change|plan|state` 对新 archive 可读取三件套。旧 4.0.x 单文件 archive 仍可读取 `change`；请求不存在的 legacy `plan|state` 返回稳定 `MISSING_ARTIFACT`，不得伪造。

## Superseded Record

`supersede` 仅接受已成功归档的 successor。成功后 predecessor State：

```yaml
status: SUPERSEDED
phase: SUPERSEDED
next_action: ARCHIVE_SUPERSEDED
superseded_by:
  successor_id: successor-change
  successor_location: archive
  successor_path: .dev-docs/changes/archive/successor-change
  decision: Scope continued in the verified successor.
```

predecessor completion document 仍保留原 Spec，`related_changes` 与 successor id 一致；`Outcome` 说明 takeover、真实 checkpoints 与未完成范围；`Validation` 明确旧 acceptance 未完整 PASS；`Knowledge Updates` 和 `Residual Risks` 非空。新 predecessor archive 仍完整保留三件套。

## Legacy Move

清晰 v1 tree 只能整体移动到 `.dev-docs/legacy/v1/`，随后创建最小 v2 skeleton。不得解析、转换或部分复制旧 runtime artifact；目标存在、混合 v1/v2、symlink 或不安全路径时 fail closed。

## Non-Goals

Nuclio 不提供 `workflow.py`、第二 State writer、DAG scheduler、parallel product write、per-Task ownership、owner routing、automatic fixer、archive manifest、hidden archive backup、runtime hook、daemon、MCP、network service、persistent process JSON、v1 converter 或双栈 runtime。
