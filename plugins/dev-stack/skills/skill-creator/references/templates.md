# Templates

Output format templates referenced by SKILL.md. Each section is an anchor target.

## Contents
- [Templates](#templates)
  - [Contents](#contents)
  - [Phase 1 Output](#phase-1-output)
    - [CREATE — First Principles Statement](#create--first-principles-statement)
    - [MODIFY — Change First Principles](#modify--change-first-principles)
  - [Full Spec](#full-spec)
  - [Delta Spec](#delta-spec)
  - [Task Format](#task-format)
  - [Delegation Context](#delegation-context)
  - [Eval Prompts Template](#eval-prompts-template)

---

## Phase 1 Output

### CREATE — First Principles Statement

```
## First Principles Statement

**根本问题：** [the essential problem this skill solves]
**最小必要能力：** [must-have capabilities after stripping nice-to-have]
**不可变约束：** [rules that cannot be violated regardless of design]
**触发场景：** [when a user needs this skill]
```

### MODIFY — Change First Principles

```
## Change First Principles

**当前状态：** [current skill's core capability and pattern in one sentence]
**根本问题：** [root cause of user's dissatisfaction]
**最小变更：** [minimum change scope to meet the goal]
**不可动约束：** [capabilities/behaviors that must be preserved]
**变更边界：** [explicitly out of scope for this change]
```

---

## Full Spec

CREATE path — present filled with content derived from Phase 1:

```
## Skill Spec: <name>

### 1. Identity
- Name:
- Description (trigger text):
- Should-trigger scenarios:
- Should-NOT-trigger scenarios:

### 2. Contract
- Input: what user provides
- Output: what skill produces
- Side effects: what gets created/modified/deleted

### 3. Architecture
- Primary Pattern: [from Google 8 patterns]
- Selection rationale: [one sentence]
- Secondary Pattern(s): [if any]
- Workflow skeleton:
  - Step 1: [what] → produces what
  - Step 2: [what] → produces what
  - ...
- Hard Gates: [which steps require user confirmation]

### 4. Boundaries
- Will NOT do:
- Prerequisites:
- Known limitations:

### 5. Success Criteria
- Trigger accuracy target:
- Key behavior assertions: [3-5 things the skill must do]
- Eval cases draft: [2-3 positive + 1-2 negative]
```

---

## Delta Spec

MODIFY path:

```
## Delta Spec: <name>

### Changed
- [Section]: [from X → to Y]

### Added
- [what's new]

### Removed
- [what's dropped]

### Unchanged (explicit)
- [what stays the same]
```

---

## Task Format

Phase 3 — Plan 必须以此 header 开头，并使用 `.claude/plans/<skill-name>-<变更主题>-plan.md` 保存：

```markdown
# <Feature Name> Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** [one sentence]

**Architecture:** [2-3 sentences]

**Tech Stack:** [markdown / skill files / validation commands]

## Global Constraints

- [constraint copied from Spec; exact values only]
- [constraint copied from Spec; exact values only]

---
```

Use this format for every Task:

```markdown
### Task N: [名称]

**Files:**
- Create: `exact/path/to/file.md`
- Modify: `exact/path/to/existing.md` (section or line range)
- Delete: `exact/path/to/remove.md`

**Interfaces:**
- Consumes: [inputs from Spec or previous Tasks; exact section names / file paths]
- Produces: [outputs later Tasks rely on; exact section names / file paths]

- [ ] **Step N.1: [具体动作]**

[完整动作说明；如修改文案，给出要插入或替换的准确文本。]

- [ ] **Step N.2: [验证动作]**

Run: `[exact command]`
Expected: `[exact expected output shape]`

**Acceptance Criteria:**
- Pattern 结构约束: [来自 Spec Section 3 Architecture]
- 业务意图: [来自 First Principles / Delta Spec]
- 验收标准: [可验证条件]
```

**SDD 6.1.1 格式规则：**
- `### Task N:` 标题和 checkbox steps 是 mandatory；`scripts/task-brief PLAN_FILE N` 依赖这个结构提取任务。
- `Global Constraints` 是 reviewer 的 attention lens；必须包含跨 Task 的 exact constraints。
- `Interfaces` 是 implementer 理解相邻 Task 依赖的唯一入口；即使无依赖也写 `Consumes: None` / `Produces: ...`。
- Task brief 必须包含 exact values；dispatch prompt 不应粘贴完整历史或重复完整 plan。
- 每个 Task 必须包含一个 focused validation step；文档任务可使用 `grep` / `wc` / markdown link scan。

**CREATE 拆分参考：**
- Task 1: 创建 SKILL.md 骨架（frontmatter + workflow overview + step 标题）
- Task 2: 填充各 Step 详细指令
- Task 3: 创建 references/ 文件（如需要）
- Task 4: 创建 agents/ 文件（如需要）

**MODIFY 拆分参考：**
- 按 Delta Spec 的 Changed/Added/Removed 逐项拆分
- 相关联的变更合并为一个 Task

---

## Delegation Context

Phase 4 — 委托 superpowers:subagent-driven-development 时注入的领域约束模板。

```markdown
请执行 Plan（路径: `.claude/plans/<skill-name>-<变更主题>-plan.md`）。

该路径是本 skill 的项目约定，覆盖 `superpowers:writing-plans` 的默认 `docs/superpowers/plans/...`；但 Plan 格式必须兼容 `superpowers:subagent-driven-development` 6.1.1。

**SDD 6.1.1 执行约束：**
- 执行 Task 1 前进行 Pre-Flight Plan Review；发现 Plan 内冲突或与 Global Constraints 冲突时，批量询问用户后再执行。
- 每个 Task dispatch 前运行 `scripts/task-brief PLAN_FILE N`，将生成的 brief path 交给 implementer；不要把完整 Plan 粘贴给 implementer。
- 每个 implementer 必须写 report file，并在短回复中返回 Status / commits / one-line test summary / concerns / report file path。
- 每个 Task 完成后运行 `scripts/review-package BASE HEAD`，将 diff package path、task brief path、report file path、Global Constraints 交给 task reviewer。
- task reviewer 是单个 gate，同时返回 spec compliance 与 code quality verdict。
- Critical/Important findings 必须通过 fix subagent 修复，并在 report file 追加覆盖测试命令与输出；修复后必须 re-review。
- 每个 Task review clean 后写入 `.superpowers/sdd/progress.md` ledger。
- 所有 Task 完成后运行 final whole-branch review；final review 也使用 `scripts/review-package MERGE_BASE HEAD`。
- 所有 subagent dispatch 必须显式指定 model（explicit model selection），按任务复杂度选择 cheap / standard / most capable，不依赖 session 默认 model。

**领域约束（task reviewer 须验证）：**
- description: starts with "Use when", third person, ≤ 1024 chars
- Body (SKILL.md): < 500 lines
- Progressive disclosure: content > 100 lines → 移入 references/
- References: one level deep only (SKILL.md → file, file must NOT reference another file)
- Stable logic (regex, validation, shell commands) → scripts/
- Files > 100 lines → must include `## Contents` with anchor links
- name format: ≤ 64 chars, only letters/numbers/hyphens
- Plan 每个 Task 的 Acceptance Criteria 必须包含业务意图、Pattern 结构约束、验收标准
- CREATE/MODIFY skill 文档变更必须包含 Skill TDD 验证策略：RED baseline / GREEN expected behavior / REFACTOR loophole checks
- Behavior-shaping guidance 必须包含 wording micro-test strategy：no-guidance control、5+ reps、人工检查 flagged matches

**MODIFY 额外约束：**
- 只修改 Plan 中明确列出的内容
- 发现的 scope 外问题 → 记录到输出，不做修改
```

---

## Eval Prompts Template

Phase 4 Step 4.3 — 生成 Eval Prompts 的输出格式模板。

```markdown
## Eval Prompts: <skill-name>

### 1. 行为验证（Trajectory）

| # | Prompt | 预期行为 |
|---|--------|----------|
| T1 | [模拟用户输入] | 走 CREATE/MODIFY 路径 |
| T2 | [模拟用户输入] | 在 [Phase N Gate] 暂停，等待用户确认 |
| T3 | [模拟用户输入] | 产出包含 [结构X], 符合 [Pattern 模板] |

### 2. 边界验证（Adversarial）

| # | Prompt | 预期行为 |
|---|--------|----------|
| A1 | [模糊/歧义输入] | 主动澄清 "是创建还是修改？" |
| A2 | [跨领域/不相关输入] | 不触发 skill，或正确拒绝 |

### 3. 质量基线（LLM-as-Judge）

| # | Prompt | 评分维度 |
|---|--------|----------|
| Q1 | [标准需求输入] | with-skill vs baseline: 结构化程度 |
| Q2 | [标准需求输入] | with-skill vs baseline: Pattern 遵循 / 无 placeholder |
```
