---
name: design
description: Use when the user has a Nucl.io brief/spec and wants to produce technical `design.md`, executable `plan.yaml`, context manifests, and stop at the Design Gate before implementation.
---

# Nucl.io Design

## Critical Constraints

- 不得在 Brief Gate 未确认时直接设计或实施；`brief.md` / `spec.md` 存在不等于 Brief Gate approved。必须满足 `state.json.gates.brief: approved`，或用户在当前轮明确授权继续；否则 STOP 并要求用户确认是否继续使用 provisional design。
- 只加载 `architecture` / `engineering` / `domain` 中与当前 `spec` 有关的索引和文档。
- 需要代码探索时按需 `Read` / `Grep`；不要默认读取全部源码。
- `.dev-docs/` 是 brief、spec、design、plan、context manifests 的 source-of-truth。
- `.nuclio/` 只能描述为 runtime / cache / temp state；本 MVP 不实现 runtime 行为，也不把 source-of-truth 写入 `.nuclio/`。
- 本 MVP 只处理 prompt / protocol layer；不得创建 hooks、runtime、scripts、CLI、daemon、MCP、多智能体平台、跨项目 RAG、context budget automation。
- 不依赖 `grill-me`；不 fork Trellis；不复制 Chorus 式全量上下文注入。
- `plan.yaml` 必须包含 `tasks`、`acceptance`、`verification commands`、`rollback strategy`。
- `context/implement.jsonl` 和 `context/verify.jsonl` 必须显式列出后续阶段允许加载的稳定上下文。
- Design 阶段必须在 Design Gate STOP；确认前不得进入实现。

## Contents

1. [Workflow](#workflow)
2. [Phase 1: Confirm Brief Readiness](#phase-1-confirm-brief-readiness)
3. [Phase 2: Load Design Context](#phase-2-load-design-context)
4. [Phase 3: Grill Design](#phase-3-grill-design)
5. [Phase 4: Write Design](#phase-4-write-design)
6. [Phase 5: Write Plan and Context Manifests](#phase-5-write-plan-and-context-manifests)
7. [Phase 6: Design Gate](#phase-6-design-gate)
8. [Behavior Verification](#behavior-verification)

## Workflow

将已确认或用户允许继续的 `brief.md` / `spec.md` 转换为有边界的实现输入：`design.md`、`plan.yaml`、`context/implement.jsonl`、`context/verify.jsonl`，并更新 `state.json`。全流程采用 Sequential + HITL：先确认需求状态，再选择性加载上下文，随后生成设计、任务切片、验证计划和上下文清单，最后停在 Design Gate。

Design readiness is state-based, not artifact-existence-based. Before proceeding, inspect the current change `state.json`: `gates.brief` must be `approved`, or the user must explicitly authorize provisional design in the current turn. Once design begins, immediately preserve/merge `phase: "design"` and `status: "in_progress"`; after writing design artifacts, preserve/merge `phase: "design"`, `status: "draft"`, and `gates.design: "pending"`.

## Phase 1: Confirm Brief Readiness

1. 定位当前 change 的 `brief.md`、`spec.md`、`state.json`、`references/context-manifest.md`，优先使用 `.dev-docs/` 下的 source-of-truth。
2. 检查 `brief.md` / `spec.md` 是否存在；缺失时 STOP 并要求先运行或修复 `/nuclio:brief`。
3. 读取并检查当前 change `state.json`：
   - If `gates.brief` is exactly `approved`, Brief Gate is ready.
   - If the user explicitly approves the Brief Gate or explicitly authorizes design in the current turn, Brief Gate is ready for this run.
   - If `gates.brief` is missing, `pending`, `draft`, ambiguous, or the JSON cannot be parsed, Brief Gate is not ready.
4. Do not treat `brief.md` + `spec.md` existence as approval. Artifact existence only means draft artifacts exist.
5. If Brief Gate is not ready, STOP and ask whether the user wants to review/approve Brief Gate now or continue with provisional design. Do not silently continue.
6. If the user chooses provisional design, all outputs must be marked provisional, and risks / validation plan must mention unapproved requirements.
7. Once Brief Gate is approved or current-turn authorization is explicit, update `state.json` according to `references/protocol.md` Stage entry and State Merge rules before writing design artifacts:
   - Preserve existing fields, nested objects, metadata, `current_task`, unknown keys, existing `gates`, and existing artifact paths.
   - Merge `phase: "design"`.
   - Merge `status: "in_progress"`.
   - If current-turn approval is being recorded, merge `gates.brief: "approved"`; otherwise preserve the existing `gates.brief` value.
   - Do not mark `gates.design` as `approved` during stage entry.
8. Do not start implementation and do not modify product code.

## Phase 2: Load Design Context

1. 读取当前 change 的 `brief.md`、`spec.md` 和 `references/context-manifest.md`。
2. 根据 `spec.md` 涉及的功能、接口、数据、运行环境，只加载相关的 architecture、engineering、domain 索引与文档。
3. 需要代码探索时，按问题定向使用 `Read` / `Grep`；只读取与当前设计决策直接相关的文件。
4. 不要默认读取全部源码，不要做 Chorus 式全量上下文注入。
5. 明确记录哪些上下文会被后续 implement / verify 阶段允许加载。

## Phase 3: Grill Design

在写入设计前，对候选方案进行自我质询：

- 需求是否能追溯到 `brief.md` / `spec.md`？
- 当前系统状态是否足以支持该方案？
- 接口、数据模型、依赖、边界条件是否明确？
- 任务是否能被切分为可验证、可回滚的步骤？
- 验证命令是否能证明 acceptance 已满足？
- 回滚策略是否覆盖失败路径？
- 是否误把 `.nuclio/` 当成 source-of-truth，或引入了 MVP 禁止的 runtime / automation？

如果答案不明确，先补充设计问题或请求用户澄清；不要猜测后进入实现。

## Phase 4: Write Design

在 source-of-truth 位置写入 `design.md`。必须使用以下结构：

```markdown
# Design: <change title>

## Overview
## Current State
## Proposed Design
## Data Flow
## API / Interface Changes
## Data Model Changes
## Alternatives Considered
## Risks
## Rollback Plan
## Validation Plan
```

内容要求：

- `Overview`：说明 change 目标和设计边界。
- `Current State`：总结当前相关实现、文档和约束。
- `Proposed Design`：描述目标方案，不包含实现代码。
- `Data Flow`：说明输入、处理、输出和状态流转。
- `API / Interface Changes`：列出用户可见接口、文件接口、协议字段或命令变化；无变化时写明 none。
- `Data Model Changes`：列出数据结构、manifest、state 字段变化；无变化时写明 none。
- `Alternatives Considered`：记录至少一个备选方案及取舍。
- `Risks`：列出需求、实现、验证、回滚风险。
- `Rollback Plan`：说明如何安全撤回本 change。
- `Validation Plan`：列出验证思路和命令来源。

## Phase 5: Write Plan and Context Manifests

写入 `plan.yaml`，使用以下 YAML shape：

```yaml
change_id: "YYYY-MM-DD-short-slug"
title: "<change title>"

tasks:
  - id: T1
    title: "<task title>"
    status: pending
    depends_on: []
    files_hint: []
    acceptance: []

verification:
  commands: []

rollback:
  strategy: "<rollback strategy>"
```

`plan.yaml` 要求：

- `tasks`：每个任务要有明确边界、依赖、文件提示和 acceptance。
- `verification.commands`：列出后续阶段应运行的 verification commands。
- `rollback.strategy`：描述失败时如何撤回。
- acceptance 必须能对应到 `spec.md` 与 `design.md`。

生成 context manifests：

- `context/implement.jsonl` 必须包含当前 change 的 `spec.md`、`design.md`、`plan.yaml`，以及必要的 architecture / engineering 文档。
- `context/verify.jsonl` 必须更小，只包含 spec acceptance、plan acceptance、测试指导，以及验证所需的 architecture constraints。
- 每行 JSONL 应表达一个允许后续阶段加载的稳定上下文项，至少包含路径或标识、用途、适用阶段。
- 不要把临时探索记录、缓存、运行时状态或不稳定输出加入 manifests。

Update `state.json` according to `references/protocol.md` Gate pending and State Merge rules:

- Preserve existing fields, nested objects, metadata, `current_task`, unknown keys, `gates.brief`, and unrelated gate values.
- Merge `phase: "design"`.
- Merge `status: "draft"`.
- Merge `gates.design: "pending"` until user approval.
- Record or preserve artifact paths for `design.md`, `plan.yaml`, `context/implement.jsonl`, and `context/verify.jsonl` when an `artifacts` object exists or is being created.
- Record provisional status only when the user explicitly chose provisional design.
- Do not set `gates.design` to `approved` merely because design artifacts exist.

## Phase 6: Design Gate

完成 `design.md`、`plan.yaml`、`context/implement.jsonl`、`context/verify.jsonl` 和 `state.json` 更新后，必须停止。

The gate output must include:

- Current change path: `.dev-docs/changes/<change-id>/`
- Current state summary: `phase: design`, `status: draft`, `gates.design: pending`
- Review files: `design.md`, `plan.yaml`, `context/implement.jsonl`, `context/verify.jsonl`
- Next command after approval: `/nuclio:implement`
- A warning that implementation requires Design Gate approval.

Use this exact message shape:

```text
STOP. Design Gate：请 review 当前 change 的 `design.md`、`plan.yaml`、`context/implement.jsonl` 和 `context/verify.jsonl`。

Current change: `.dev-docs/changes/<change-id>/`
Current state: `phase=design`, `status=draft`, `gates.design=pending`
Review files: `design.md`, `plan.yaml`, `context/implement.jsonl`, `context/verify.jsonl`
Next after approval: `/nuclio:implement`

注意：Design artifacts 已生成只表示设计草稿存在，不代表 Design Gate 已批准；确认后才能进入 `/nuclio:implement`。
```

在用户确认前，不得执行 `/nuclio:implement`，不得修改实现文件，不得创建 runtime、hook、script、CLI、daemon、MCP 或自动化平台。

## Behavior Verification

在结束前自检：

- `description` 以 `Use when` 开头，且 frontmatter 只描述触发条件。
- `design.md` 模板包含所有必需 section。
- `plan.yaml` shape 包含 `tasks`、`acceptance`、`verification.commands` 和 `rollback.strategy`。
- `context/implement.jsonl` 与 `context/verify.jsonl` 的生成规则明确，且 `verify` 更小。
- `.dev-docs/` 被描述为 source-of-truth；`.nuclio/` 被限制为 runtime / cache / temp state only，且未实现 runtime 行为。
- Brief readiness 依赖 `state.json.gates.brief: approved` 或当前轮明确授权；不得仅因 `brief.md` + `spec.md` 存在而继续。
- Design stage entry 必须 preserve/merge `phase=design` 和 `status=in_progress`。
- Design Gate 必须 preserve/merge `phase=design`、`status=draft`、`gates.design=pending`。
- 输出包含 Design Gate STOP 文案、current change、state summary、review files、next `/nuclio:implement` command，并在 STOP 后等待用户确认。

可用以下命令检查关键 marker：

```bash
grep -n '^description: Use when' plugins/nuclio-plugin/skills/design/SKILL.md && grep -n 'STOP. Design Gate' plugins/nuclio-plugin/skills/design/SKILL.md
```

```bash
grep -n 'brief.md.*spec.md.*存在不等于 Brief Gate approved' plugins/nuclio-plugin/skills/design/SKILL.md && grep -n 'phase: "design"' plugins/nuclio-plugin/skills/design/SKILL.md && grep -n 'gates.design: "pending"' plugins/nuclio-plugin/skills/design/SKILL.md
```
