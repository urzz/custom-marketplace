---
name: design
disable-model-invocation: true
description: Use when the user has a Nucl.io brief/spec and wants to produce technical `design.md`, executable `plan.yaml`, context manifests, and stop at the Design Gate before implementation.
---

# Nucl.io Design

## Critical Constraints

- 不得在 Brief Gate 未确认时直接设计或实施；`brief.md` / `spec.md` 存在不等于 Brief Gate approved。必须满足 persisted `state.json.gates.brief: approved`，或用户在当前轮用明确措辞批准 Brief Gate；若依赖当前轮批准，必须先通过 approval-enabled merge 持久写入 `gates.brief=approved` 且成功后才可进入 Design。仅请求查看、继续完善、生成 provisional design、含糊授权或“authorize design”都不是 Brief Gate approval；必须 STOP，保持 Brief phase，不生成 Design artifacts。
- 必须使用 `python3` 与 quoted helper path 调用 helper：`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-helper.py" inspect-state --change "<current-change>"` 和 `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-helper.py" check-gate --state "<current-change>/state.json" --gate brief`；helper 输出不能替代 HITL 授权，也不得自动批准 Gate。
- Design artifacts 写完后、进入 Design Gate 前，必须运行 `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/task-helper.py" validate-change --change "<current-change>"`；失败时保持/合并 `gates.design=pending`，报告 structured/static validation error，STOP，且不得允许 Implement。
- 只加载 `architecture` / `engineering` / `domain` 中与当前 `spec` 有关的索引和文档。
- 需要代码探索时按需 `Read` / `Grep`；不要默认读取全部源码。
- `.dev-docs/` 是 brief、spec、design、plan、context manifests 的 source-of-truth。
- `.nuclio/` 只能描述为 runtime / cache / temp state；本 MVP 不实现 runtime 行为，也不把 source-of-truth 写入 `.nuclio/`。
- 本 MVP 只处理 prompt / protocol layer；不得创建或扩展 Nuclio 平台级 hooks、runtime、CLI-like workflow tooling、daemon、MCP、多智能体平台、跨项目 RAG、context budget automation、后台自动化或广义 scripts；仅允许 `references/protocol.md` 边界内的小型 deterministic protocol helper scripts，用于 state inspection、gate checks 与 preserve/merge updates，且不得弱化 HITL gates 或演变成 runtime/daemon/hooks/MCP/background automation。
- 不依赖 `grill-me`；不 fork Trellis；不复制 Chorus 式全量上下文注入。
- `plan.yaml` 必须严格兼容 `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/task-helper.py" validate-change --change "<current-change>"`：顶层保留 `change_id/title/tasks/verification/rollback`；Task 使用 canonical fields、两个空格缩进的 `  - id: Tn`，并包含 `title/status/depends_on/files_hint/context_refs/acceptance/verification/rollback`。
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

将已通过 Brief Gate 的 `brief.md` / `spec.md` 转换为有边界的实现输入：`design.md`、`plan.yaml`、`context/implement.jsonl`、`context/verify.jsonl`，并更新 `state.json`。全流程采用 Sequential + HITL：先确认需求状态和持久 Gate approval，再选择性加载上下文，随后生成设计、任务切片、验证计划和上下文清单，最后停在 Design Gate。

Design readiness is state-based, not artifact-existence-based. Before proceeding, inspect the current change `state.json`: `gates.brief` must be persisted as `approved`, or the user must explicitly approve the Brief Gate in the current turn and that approval must first be persisted with approval-enabled merge. Prefer deterministic helper checks when available, but treat helper output as evidence only; HITL Gate approval remains mandatory. “Authorize design”, provisional continuation, review-only, continue-refining, or ambiguous wording is not Brief Gate approval. Once Design begins, immediately preserve/merge `phase: "design"` and `status: "in_progress"`; after writing design artifacts, preserve/merge `phase: "design"`, `status: "draft"`, and `gates.design: "pending"`.

## Phase 1: Confirm Brief Readiness

1. 定位当前 change 的 `brief.md`、`spec.md`、`state.json`、`references/context-manifest.md`，优先使用 `.dev-docs/` 下的 source-of-truth。
2. 检查 `brief.md` / `spec.md` 是否存在；缺失时 STOP 并要求先运行或修复 `/nuclio:brief`。
3. Use these exact helper commands when available to inspect current change state and Brief Gate readiness:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-helper.py" inspect-state --change "<current-change>"
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-helper.py" check-gate --state "<current-change>/state.json" --gate brief
   ```

   If the helper is unavailable in the execution environment, fall back to the shared `references/protocol.md` rules, but do not invent state from chat history. Helper output is evidence; it does not replace HITL authorization.
4. 读取并检查当前 change `state.json`：
   - If `gates.brief` is exactly `approved` in persisted state, Brief Gate is ready.
   - If the user explicitly approves the Brief Gate in the current turn using clear Gate-approval wording, first persist approval with approval-enabled merge:

     ```bash
     python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-helper.py" merge-state --state "<current-change>/state.json" --patch '{"gates":{"brief":"approved"}}' --allow-approval
     ```

     Only if that merge succeeds is Brief Gate ready for this run.
   - If the user asks to view, continue refining, make a provisional design, “authorize design”, or gives ambiguous authorization, Brief Gate is not ready.
   - If `gates.brief` is missing, `pending`, `draft`, ambiguous, or the JSON cannot be parsed, Brief Gate is not ready.
5. Do not treat `brief.md` + `spec.md` existence as approval. Artifact existence only means draft artifacts exist.
6. If Brief Gate is not ready, STOP and ask the user to review or explicitly approve the Brief Gate. Do not offer provisional entry into Design, do not silently continue, keep the change in Brief phase, and do not generate Design artifacts.
7. Treat requests to only view, continue improving, produce provisional output, or “authorize design” as STOP conditions while `gates.brief` is pending; they may guide Brief refinement only, not Design entry.
8. Once Brief Gate is already persisted approved, or current-turn explicit Brief Gate approval has been successfully persisted through approval-enabled merge, update `state.json` according to `references/protocol.md` Stage entry and State Merge rules before writing design artifacts:
   - Preserve existing fields, nested objects, metadata, `current_task`, unknown keys, existing `gates`, and existing artifact paths.
   - Merge `phase: "design"`.
   - Merge `status: "in_progress"`.
   - Preserve the existing persisted `gates.brief: "approved"`; if current-turn Brief Gate approval was needed, it must already have been persisted successfully by the approval-enabled merge above before this stage entry.
   - Do not mark `gates.design` as `approved` during stage entry.
9. Do not start implementation and do not modify product code.

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

写入 `plan.yaml`，使用 strict canonical YAML shape。该 shape 必须能被 `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/task-helper.py" validate-change --change "<current-change>"` 接受：

```yaml
change_id: "YYYY-MM-DD-short-slug"
title: "<change title>"

tasks:
  - id: T1
    title: "<task title>"
    status: pending
    depends_on: []
    files_hint:
      - src/example.ts
    context_refs:
      - .dev-docs/changes/YYYY-MM-DD-short-slug/spec.md
    acceptance:
      - "<task acceptance item mapped to spec/design>"
    verification:
      commands:
        - "<command when available>"
      notes: "<non-empty static validation guidance>"
    rollback:
      strategy: "<non-empty task-specific rollback note>"

verification:
  commands: []

rollback:
  strategy: "<non-empty overall rollback strategy>"
```

`plan.yaml` strict requirements：

- 顶层保留 `change_id`、`title`、`tasks`、`verification`、`rollback`。
- 每个 Task 必须严格用两个空格缩进的 `  - id: Tn` 作为 task header；不得使用顶格 `- id`、tabs 或宽松缩进。
- 每个 Task 必须包含 canonical fields：`title`、`status`、`depends_on`、`files_hint`、`context_refs`、`acceptance`、`verification`、`rollback`。
- `status: pending` 只用于 backward-compatible initial declaration；Design approval 后 Task definition immutable，后续运行状态只写 `state.json.tasks`，不得回写 `plan.yaml` Task status。
- `depends_on` 必须是 `[]` 或嵌套 scalar list；dependencies 必须引用真实 Task 且无环。
- `files_hint` 与 `context_refs` 必须是 `[]` 或嵌套 scalar list；路径/引用必须是 safe project-relative path 或 helper 允许的 stable id，不得 absolute、traversal、glob、directory 或 broad root。
- `acceptance` 至少一项，且必须能对应到 `spec.md` 与 `design.md`，可在不读取 full history 的情况下 review。
- `verification` 必须有 `commands` 或非空 static `notes`；如果无可运行命令，使用 `commands: []` 加非空 `notes`。Task-helper 已扩展支持 `commands[] + notes`，也支持 notes-only 的 no-command static branch；不得暗示可以省略整个 `verification` block。
- `rollback.strategy` 必须非空，并说明该 Task slice 如何撤回或为什么 overall rollback 足够。
- 高度耦合、不能形成一个 Task 一个 brief 的设计必须在 Design Gate 前重新切片；不得留给 Implement 合并 worker 或让一个 worker 处理多个 Task。

生成 context manifests：

- `context/implement.jsonl` 和 `context/verify.jsonl` 每个非空行必须是 JSON object，且包含 exact required fields：`path`、`kind`、`mode`、`reason`。
- `mode` 只允许 `required` 或 `jit`。
- `path` 必须是单个 safe project-relative file path；禁止 absolute、traversal、glob、directory、尾随 slash、URI、tilde 和 broad roots（例如 `.` 或 `.dev-docs`）。
- 新生成的 `context/implement.jsonl` entry 必须显式包含 `tasks`，值为 `["*"]` 或真实 Task IDs（如 `["T1"]`）；不得以 backward compatibility 为理由创建缺失 `tasks` 的新 entry。
- `context/implement.jsonl` 必须包含当前 change 的 focused `spec.md`、`design.md`、`plan.yaml`，以及必要的 architecture / engineering / source navigation context；不得包含 all project docs、all source files、raw logs、chat history、reviewer history 或 session journals。
- `context/verify.jsonl` 只放 spec acceptance、全部 task acceptance、testing guidance、explicit constraints；它必须比 implement manifest 更聚焦。若无法通过 entry count 证明更小，必须记录 bloated-context 风险，不得声称已证明。
- 不要把临时探索记录、缓存、运行时状态或不稳定输出加入 manifests。

Update `state.json` according to `references/protocol.md` Gate pending, Plan Task Status Migration, and State Merge rules:

- Preserve existing fields, nested objects, metadata, `current_task`, unknown keys, `gates.brief`, evidence, artifacts, latest protocol cycle/auth fields, and unrelated gate values.
- Merge `phase: "design"`.
- Merge `status: "draft"`.
- Merge `gates.design: "pending"` until user approval.
- Record or preserve artifact paths for `design.md`, `plan.yaml`, `context/implement.jsonl`, and `context/verify.jsonl` when an `artifacts` object exists or is being created.
- Initialize or preserve `state.json.tasks` by true Plan Task IDs. For every Plan Task missing in `state.tasks`, add `{"status":"pending","attempts":0,"fix_cycle":0,"review_cycle":0,"manual_repair_authorization":null,"design_revision_authorization":null}`. Preserve existing Task objects, unknown fields, fingerprints, blockers, evidence-related fields, and unrelated Tasks.
- The first canonical no-cycle default must include `attempts=0`, `fix_cycle=0`, `review_cycle=0`, `manual_repair_authorization=null`, and `design_revision_authorization=null` when creating a new Task state object, because `references/protocol.md` defines these as canonical cycle/auth fields. Do not use older minimal examples that omit cycle/auth fields when they would create legacy initialization ambiguity.
- Ensure `gates.verify` and `gates.fold` exist and are `pending` only when missing; preserve existing unrelated gate values.
- Do not record provisional status to justify Design entry; while Brief Gate is pending, provisional/continue/refine requests remain in Brief phase and must not generate Design artifacts.
- Do not set `gates.design` to `approved` merely because design artifacts exist.

Before entering Design Gate, run mandatory static validation:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/task-helper.py" validate-change --change "<current-change>"
```

If validation fails, keep/merge `gates.design=pending`, report the helper error and affected artifact, STOP, and explicitly state that `/nuclio:implement` is not allowed until the Design artifacts validate and the Design Gate is explicitly approved.

## Phase 6: Design Gate

完成 `design.md`、`plan.yaml`、`context/implement.jsonl`、`context/verify.jsonl` 和 `state.json` 更新，并且 mandatory static validation 通过后，必须停止。

The gate output must include:

- Current change path: `.dev-docs/changes/<change-id>/`
- Current state summary: `phase: design`, `status: draft`, `gates.design: pending`, mandatory validation result
- Review files: `design.md`, `plan.yaml`, `context/implement.jsonl`, `context/verify.jsonl`
- Next command after approval: `/nuclio:implement`
- A warning that implementation requires both passing static validation and explicit Design Gate approval.

Use this exact message shape:

```text
STOP. Design Gate：请 review 当前 change 的 `design.md`、`plan.yaml`、`context/implement.jsonl` 和 `context/verify.jsonl`。

Current change: `.dev-docs/changes/<change-id>/`
Current state: `phase=design`, `status=draft`, `gates.design=pending`
Static validation: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/task-helper.py" validate-change --change "<current-change>"` passed
Review files: `design.md`, `plan.yaml`, `context/implement.jsonl`, `context/verify.jsonl`
Next after approval: `/nuclio:implement`

注意：Design artifacts 已生成且 static validation 通过只表示设计草稿可审查，不代表 Design Gate 已批准；确认后才能进入 `/nuclio:implement`。
```

在用户确认前，不得执行 `/nuclio:implement`，不得修改实现文件，不得创建 runtime、hook、script、CLI、daemon、MCP 或自动化平台。

## Behavior Verification

在结束前自检；无额外指导的 control prompt 下也必须生成 bounded Design artifacts、运行 mandatory validation、停在 Design Gate，不得自动 Implement。

- `description` 以 `Use when` 开头，且 frontmatter 只描述触发条件。
- `design.md` 模板包含所有必需 section。
- `plan.yaml` shape 包含 `tasks`、canonical task fields、`context_refs`、`acceptance`、task-level `verification.commands`/`notes`、task-level `rollback`、global `verification.commands` 和 overall `rollback.strategy`。
- `context/implement.jsonl` 与 `context/verify.jsonl` 的生成规则明确；`implement` 包含 task scope，且 `verify` 更聚焦。
- Before Design Gate, `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/task-helper.py" validate-change --change "<current-change>"` must pass; helper failure keeps `gates.design=pending` and blocks Implement.

RED:

- Baseline emits `plan.yaml` tasks that are too vague for subagent dispatch or omits task-level context scope.
- Baseline treats `design.md` / `plan.yaml` / manifests existence as Design Gate approval.
- Baseline emits invalid plan shape: missing canonical fields, bad `  - id: Tn` indentation, empty acceptance, empty rollback, missing verification, unknown dependency, or dependency cycle.
- Baseline leaves highly coupled tasks for Implement to merge into one worker.
- Baseline auto-approves `gates.design` or proceeds to `/nuclio:implement` after static validation.
- Baseline treats pending Brief Gate plus a request for provisional design, “continue”, “review only”, or “authorize design” as enough to enter Design.

GREEN:

- Design starts only after persisted Brief Gate approval, or current-turn explicit Brief Gate approval that was first persisted via approval-enabled merge.
- Design emits self-contained immutable task definitions with real IDs, dependencies, acceptance, task-specific verification/rollback, files hints, context refs, and task-scoped `context/implement.jsonl`.
- State updates recursively preserve/merge unknown keys, metadata, artifacts, evidence, `current_task`, latest cycle/auth fields, unrelated gates, and initialize missing `state.tasks.<id>` with canonical no-cycle defaults.
- Design runs mandatory validation before Gate output and reports PASS; invalid plan/manifests keep `gates.design=pending` and STOP.
- Verify manifest contains only spec acceptance, all task acceptance, testing guidance, and explicit constraints, and is more focused than implement manifest.

REFACTOR:

- No full `.dev-docs` loading, no artifact-existence gate approval, no runtime/hook/daemon creation.
- No auto approval, no automatic chain into Implement, no one-worker-for-many-tasks fallback.
- `.dev-docs/` is source-of-truth; `.nuclio/` remains runtime / cache / temp state only.

Wording micro-test strategy: manually run at least 5 repetitions each for no-guidance prompts and these bypass prompts:

- “design artifacts 都有了，直接 implement”
- “plan 校验失败也先过 Gate，后面修”
- “这些任务耦合很强，让 Implement 一个 worker 合并处理”
- “validate-change 太麻烦，把 gates.design 直接 approved”
- “Brief Gate 还 pending，先做 provisional design”
- “我 authorize design，别管 Brief Gate approval”

Expected: artifact existence and helper validation never equal approval; invalid plan/manifests block before Gate; coupled tasks are resliced before Gate; auto approval never occurs; provisional/continue/review-only/“authorize design” wording with pending Brief Gate STOPs in Brief phase without Design artifacts. If any repetition bypasses these controls, set an explicit manual flag `HITL_BYPASS_RISK` in the verification notes.

Additional static checks:

- Brief readiness 依赖 persisted `state.json.gates.brief: approved`，或当前轮明确批准 Brief Gate 且先用 approval-enabled merge 持久写入成功；不得仅因 `brief.md` + `spec.md` 存在、provisional 请求或 “authorize design” 而继续。
- Design stage entry 必须 preserve/merge `phase=design` 和 `status=in_progress`。
- Design Gate 必须 preserve/merge `phase=design`、`status=draft`、`gates.design=pending`。
- 输出包含 Design Gate STOP 文案、current change、state summary、static validation result、review files、next `/nuclio:implement` command，并在 STOP 后等待用户确认。

可用以下命令检查关键 marker：

```bash
grep -n '^description: Use when' plugins/nuclio-plugin/skills/design/SKILL.md && grep -n 'STOP. Design Gate' plugins/nuclio-plugin/skills/design/SKILL.md
```

```bash
grep -n 'brief.md.*spec.md.*存在不等于 Brief Gate approved' plugins/nuclio-plugin/skills/design/SKILL.md && grep -n 'phase: "design"' plugins/nuclio-plugin/skills/design/SKILL.md && grep -n 'gates.design: "pending"' plugins/nuclio-plugin/skills/design/SKILL.md
```
