# Nuclio v2 Change Format

Nuclio v2 使用 Markdown + YAML docs-as-code。普通 active change 由同一目录下的三层 artifact 表达：`.dev-docs/changes/<change-id>/change.md`、`plan.yaml`、`state.yaml`。代码、配置、测试、CI、Git working tree 和 checkpoint commits 仍是产品执行事实。

## Contents

- [最小项目骨架](#最小项目骨架)
- [三层 artifact authority](#三层-artifact-authority)
- [根索引职责](#根索引职责)
- [可选知识目录](#可选知识目录)
- [禁止的项目结构](#禁止的项目结构)
- [Active change 路径](#active-change-路径)
- [change.md Spec](#changemd-spec)
- [plan.yaml 批准合同](#planyaml-批准合同)
- [allowed_paths 写入边界](#allowed_paths-写入边界)
- [state.yaml 当前状态](#stateyaml-当前状态)
- [checkpoint commit](#checkpoint-commit)
- [review、validation 与 repair](#reviewvalidation-与-repair)
- [完成格式](#完成格式)
- [Archive 路径](#archive-路径)
- [Legacy 整体移动](#legacy-整体移动)
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

`changes/archive/` 保存完成后的轻量历史记录；未来成功 archive 的每个 `<change-id>/` 只保留精简 `change.md`。`legacy/` 只保存整体移动的历史树或用户明确要求保留的旧资料。

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

Active changes live in `.dev-docs/changes/<change-id>/` with `change.md`, `plan.yaml`, and `state.yaml`.

Completed changes move to `.dev-docs/changes/archive/<change-id>/` as a concise one-file `change.md` record; active `plan.yaml` and `state.yaml` are not retained in long-term archive.

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

This file records confirmed build, test, release, collaboration, and code practice knowledge that remain useful across changes.

## Confirmed Knowledge

No confirmed engineering knowledge has been recorded yet.
```

## 三层 artifact authority

每个 active change 使用：

```text
.dev-docs/changes/<change-id>/
├── change.md
├── plan.yaml
└── state.yaml
```

三层职责固定：

- `change.md` 是人类可读 Spec 权威，表达 Goal、Context、Constraints、Non-goals、Acceptance Criteria、重要 Decisions 和最终 Outcome。
- `plan.yaml` 是用户自然语言批准后的执行合同权威，表达 revision、risk、review policy、repair policy、change-level `allowed_paths`、有序 Tasks、验证命令和 checkpoint subject。
- `state.yaml` 是唯一动态状态权威，只由 `plugins/nuclio-plugin/scripts/change.py` 写入，保存当前恢复状态。
- Git commits、working tree、代码、配置、测试和 CI 是产品事实；每个实施或 repair checkpoint commit 保存实际增量历史。

冲突处理 fail closed：Spec hash、Plan hash、revision、HEAD、checkpoint parent、checkpoint subject、commit range 或 allowed-path 边界不匹配时，不自动猜测或同步，必须回到人类判断。

## 根索引职责

`.dev-docs/index.md` 是稳定导航页，应说明：

- 当前文档库的目的。
- 三个全局 knowledge 文件的职责。
- 常用可选目录的含义。
- active changes 位于 `.dev-docs/changes/<change-id>/`。
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

不要创建 `.dev-docs/changes/index.md`。根索引不枚举 changes；active/resume 通过扫描 `.dev-docs/changes/*/change.md` 和读取同目录 Plan/State 完成。

不要创建持久过程 JSON、隐藏运行时目录、项目级 `.claude/` 安装、`.nuclio/` 状态目录、daemon 文件、runtime hook 或外部服务依赖。

不要保留 v1/v2 双栈。清晰 v1 `.dev-docs` 只能整体移动到 `.dev-docs/legacy/v1/`。

不得新增第二个 runtime helper、`workflow.py`、subprocess 状态协议、owner routing、per-Task files ownership、DAG scheduler 或并行产品写入引擎。

## Active change 路径

active change 路径为：

```text
.dev-docs/changes/<change-id>/change.md
.dev-docs/changes/<change-id>/plan.yaml
.dev-docs/changes/<change-id>/state.yaml
```

`change-id` 应稳定、可读、适合路径名。普通 change 不需要额外过程文件。若用户或任务确实需要研究材料，可在同一 change 目录下创建简短 Markdown，但默认不要这样做；优先把恢复所需摘要写回 `change.md` 或由 `state.yaml` 保存当前机器状态。

## change.md Spec

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

`status` 只表达人类文档状态，动态执行状态不再由 `change.md` 承担。完成时可改为 `completed`，但 helper 推进依赖 `state.yaml`。

最小正文：

```markdown
# <title>

## Goal

<one concise goal>

## Context

<why this change exists>

## Constraints

<confirmed constraints>

## Non-goals

<explicit exclusions>

## Acceptance Criteria

<observable acceptance>
```

可选章节仅在非空且有恢复价值时出现：

- `## Decisions`
- `## Validation`
- `## Outcome`
- `## Knowledge Updates`
- `## Blockers`

不要把动态 Task checklist、完整 transcript、完整 diff、长命令输出、全部测试日志或 agent 对话复制进 `change.md`。

## plan.yaml 批准合同

`plan.yaml` 使用原生 YAML，并由唯一 helper 的 `validate-plan` 校验。PyYAML 是明确依赖；helper 使用拒绝重复 mapping keys 的受限 `SafeLoader`、安全 dump、输入大小限制和显式 schema/type checks。PyYAML 缺失时返回稳定 dependency error。

最小结构：

```yaml
schema_version: 1
change_id: example-change
revision: 1
risk_level: medium
review_policy: final
repair_policy: in-scope
summary: >
  One or two sentence execution summary.
allowed_paths:
  - src/
  - tests/example_test.py
tasks:
  - id: 1
    name: Implement core behavior
    steps:
      - Edit source in allowed paths.
    acceptance:
      - Behavior is observable through validation.
    validation:
      - python3 -m unittest discover -s tests -p 'test_*.py'
    delegate: subagent
    review: final
    checkpoint_subject: 'feat(example): implement core behavior'
```

顶层字段固定：`schema_version`、`change_id`、`revision`、`risk_level`、`review_policy`、`repair_policy`、`summary`、`allowed_paths`、`tasks`。

Task 字段固定：唯一正整数 `id`、`name`、非空 `steps`、非空 `acceptance`、`validation` 命令列表、`delegate`、`review`、`checkpoint_subject`。

`risk_level` 允许 `low|medium|high`。`review_policy` 允许 `self|final|task-and-final`。`repair_policy` 当前仅允许 `in-scope`。`high` 风险必须使用 `task-and-final`。

Plan 禁止 placeholder、重复 key、错误类型、不安全 YAML tag、动态 State 字段、runtime owner mapping 和 per-Task files ownership。Goal、Constraints、Non-goals、Acceptance、allowed paths、Task 合同、验证、风险或 review policy 变化时，必须提高 revision、重新校验并重新获得用户批准。

## allowed_paths 写入边界

`allowed_paths` 是 change-level 写入边界，不分配给具体 Task，也不用于 finding owner routing。

规则：

- project-relative POSIX path。
- 以 `/` 结尾表示目录前缀，否则表示 exact file。
- 禁止 absolute path、`.`、`..`、反斜杠、glob、空白、空字符串和重复项。
- `start-task` 与 `start-repair` 要求 Git index 为空，且 allowed paths 内没有预存 tracked/untracked 修改。
- allowed paths 外 unrelated unstaged/untracked changes 可保留，但不得进入 checkpoint commit。
- 每个 checkpoint commit 的所有 changed paths 必须落在 `allowed_paths` 内。

## state.yaml 当前状态

`state.yaml` 只保存当前恢复所需事实：

- `schema_version`、`change_id`
- `plan_revision`、`plan_sha256`、`spec_sha256`
- `repo_root`、`initial_head`、`current_head`
- `status`、`phase`、`current_task_id`、`next_action`
- 每个 Task 的 `status`、`task_base`、`task_head`、`checkpoint_commit`、`executor` 和验证摘要
- 当前 task/final review 状态
- 当前 validation 状态
- 当前 repair 的编号、来源 gate、具体路径、证据摘要和 checkpoint commit
- 单个当前 `blocker` 或 `null`

State 不保存完整 transcript、完整 diff、测试日志、agent 消息、文件内容 snapshot、append-only transition history 或重复 Git 历史。写入必须使用同目录临时文件加 `os.replace`。

核心 `next_action` 值：

```text
DISPATCH_TASK
RUN_TASK_REVIEW
RUN_FINAL_REVIEW
RUN_VALIDATION
REQUEST_REPAIR_DECISION
COMPLETE
HALT
```

恢复时先运行 `status` 和 `next-action`，再结合 Git HEAD、diff/status、checkpoint commits 和验证证据判断下一步。不要依据 transcript 或 agent claim 推进。

## checkpoint commit

每个实施 Task 恰好一个 selective-stage 本地 checkpoint commit。流程为：

1. `start-task` 冻结 `task_base=HEAD`、executor 和 Plan 中的 checkpoint subject。
2. 实施者只修改 allowed paths 内与 Task 有关的产品文件。
3. 实施者运行 Task validation。
4. 实施者只 selective stage 本 Task changed paths。
5. 实施者创建恰好一个 commit，subject 精确等于 `checkpoint_subject`。
6. `record-task` 校验 `task_base` 是 `HEAD` 的直接父提交、subject 精确匹配、changed paths 非空且全部在 allowed paths 内、index 为空、validation 为 PASS。

Helper 不自动 reset、rebase、squash、stash 或改写历史。完成后保留 checkpoint commits 作为可审阅、可回滚的普通 Git 历史。

## review、validation 与 repair

`self` 可跳过独立 reviewer，但不能跳过适用 validation。`final` 在全部 Tasks 后运行 whole-change review。`task-and-final` 对每个 Task 与 whole change 都独立 review。

Review 或 validation FAIL 时，只记录违反合同、具体路径、证据和 decision，`next_action` 进入 `REQUEST_REPAIR_DECISION`。Helper 不做 owner mapping、budget 分配、自动 fixer 或自动循环。

`repair_policy: in-scope` 的修复条件：

- 修复仍满足原 Goal、Constraints、Non-goals 和 Acceptance。
- 修复 paths 全部在 `allowed_paths` 内。
- 不新增依赖、API、迁移、不可逆或外向动作。
- 不提高风险，不改变 Plan 合同。
- 人类判断明确允许当前 in-scope repair。

`start-repair` 生成稳定 repair checkpoint subject。修复后 `record-repair` 校验一个直接父 commit、subject、allowed paths、空 index 和 closure validation PASS，然后返回原 review/validation gate。

超出 allowed paths、改变 Spec/Plan 合同、提高风险或涉及不可逆/外向动作时，必须提高 Plan revision 并重新批准。

## 完成格式

`complete` 仅在以下条件全部满足时进入终态：

- 所有 Tasks 状态为 `DONE`。
- 必要的 task review 与 final review 全部 PASS。
- whole-change validation 为 PASS。
- HEAD、State、Spec hash、Plan hash 和 revision 一致。
- 没有 unresolved blocker。
- 已报告产品结果并完成 mandatory knowledge-candidate analysis；无合格候选时记录 `NO_OP`，有候选时记录实际写入、部分接受、修改或拒绝结果。

`complete` 后、`archive` 前，`change.md` 必须从 active Spec 蒸馏为精简历史记录。它的职责是轻量追溯，不是长期知识库；长期知识只来自用户确认后的 `.dev-docs/knowledge/**` 写入。

精简历史 `change.md` 必备 frontmatter：

```yaml
---
id: <change-id>
title: <human readable title>
status: completed
created: YYYY-MM-DD
updated: YYYY-MM-DD
related_changes: []
---
```

精简历史 `change.md` 必备非空 headings：

```markdown
# <title>

## Goal

<original concise goal>

## Outcome

<verified product result, key changed paths, residual risks or none, and checkpoint commit references when useful>

## Validation

<commands, exit codes, and short result summaries>

## Knowledge Updates

<actual confirmed writes, partial writes, modified writes, rejected candidates, or NO_OP>
```

不得把过程日志、Plan、State、完整 diff、transcript、agent 消息、完整测试输出或旧式授权内容复制进精简历史记录。未来 related change 可通过 change id、Outcome、Validation、Knowledge Updates 和 Git checkpoint commits 追溯。

## Archive 路径

完成并蒸馏 `change.md` 后使用：

```bash
python3 plugins/nuclio-plugin/scripts/change.py --project-root <repo> archive --id <change-id>
```

helper 直接读取终态 State，并先验证 completed State、Plan/Spec/HEAD identity、精简历史记录形态和 exact artifact set。active 目录必须恰好只有：

```text
.dev-docs/changes/<change-id>/change.md
.dev-docs/changes/<change-id>/plan.yaml
.dev-docs/changes/<change-id>/state.yaml
```

验证通过后移动 change 目录到：

```text
.dev-docs/changes/archive/<change-id>/
```

然后 pruning active execution artifacts。Archive 成功后 archive 目录只保留：

```text
.dev-docs/changes/archive/<change-id>/change.md
```

`plan.yaml` 和 `state.yaml` 是 active 执行/恢复 artifact，不进入长期 archive，也不得复制到隐藏备份、manifest 或第二状态位置。Git checkpoint commits 保留实际实施历史；不自动 squash、reset、rebase、stash 或改写历史。

Archive failure 必须 fail closed：undistilled record、unexpected artifact、identity drift 或 target conflict 在移动/pruning 前失败并保持源目录不变。若移动后 pruning 失败，返回稳定 error，包含 archive path 和 remaining artifacts；不得报告成功。现有 archive 不迁移，新 retention policy 只应用于未来成功的 archive 调用。相关回归或扩展创建新 active change，并通过 `related_changes` 指向 archive 中的历史 change。

## Legacy 整体移动

清晰 v1 `.dev-docs` 只能整体移动到：

```text
.dev-docs/legacy/v1/
```

`legacy-move` 在移动前检查 v1/v2 冲突、临时目录冲突和目标冲突；中途失败时尽量恢复原 `.dev-docs`，并以 JSON stderr 报告稳定错误码和残留状态。Nuclio 不提供 v1 compatibility converter，不把 v1 artifact 转换为三层 artifact。

## 非目标

`change.md` 不是状态机数据库、审计录像、helper ledger、聊天记录、测试日志仓库或长期知识文件。`plan.yaml` 不是项目管理系统、owner map 或 agent 路由表。`state.yaml` 不替代 Git、代码和测试事实。

本格式不新增 Nuclio 专用 agent 流水线、第二 helper、MCP、network service、daemon、runtime hook、项目级 `.claude/`、`.nuclio/`、changes index、DAG scheduler、并行写入引擎、内容 snapshot、完整 State history、自动 fixer、owner budget 或 squash 流程。
