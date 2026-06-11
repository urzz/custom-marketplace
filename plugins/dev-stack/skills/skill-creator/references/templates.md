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

Phase 3 — use this format for every Task in the Plan:

```markdown
### Task N: [名称]

**Files:**
- Create: `exact/path/to/file.md`
- Modify: `exact/path/to/existing.md` (which section)
- Delete: `exact/path/to/remove.md`

**Steps:**
- [ ] Step N.1: [具体动作，包含完整内容，不用 placeholder]
- [ ] Step N.2: [具体动作]
- [ ] Step N.3 (验证): [验证条件作为可执行的检查步骤]

**Acceptance Criteria:**
- [criterion 1 — spec reviewer 用此判断 compliance]
- [criterion 2]
```

**格式规则：**
- Steps 必须自包含（不引用外部文件，不用 placeholder 如 "implement later" / "similar to Task N"）
- 重复代码也要完整写出（sub agent 可能不按顺序读 Task）
- 最后一步必须是验证步骤（implementer 自检）
- Acceptance Criteria 写明通过标准，供 superpowers spec reviewer 做 compliance check
- Acceptance Criteria 必须包含三类信息（Phase 3 输出时直接写入，不需要 implementer 去查外部文件）：
  1. **Pattern 结构约束**（来自 Spec Section 3 Architecture — 该 Task 涉及的架构模式、文件结构、命名规范）
  2. **业务意图**（来自 Spec Section 1 First Principles — 该 Task 解决什么问题、不可削减的核心是什么）
  3. **验收标准**（来自 Spec Section 5 Success Criteria — 与该 Task 相关的具体可验证条件）
- Plan 是 self-contained 的执行文档 — Acceptance Criteria 必须包含 subagent 判断完成所需的全部信息，禁止引用外部 Spec 文件

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

```
请执行 Plan（路径: `.claude/plans/<skill-name>-<变更主题>-plan.md`）。

**领域约束（spec reviewer 须验证）：**
- description: starts with "Use when", third person, ≤ 1024 chars
- Body (SKILL.md): < 500 lines
- Progressive disclosure: content > 100 lines → 移入 references/
- References: one level deep only (SKILL.md → file, file must NOT reference another file)
- Stable logic (regex, validation, shell commands) → scripts/
- Files > 100 lines → must include `## Contents` with anchor links
- name format: ≤ 64 chars, only letters/numbers/hyphens
- 业务意图、Pattern 结构约束、验收标准均已编码到 Plan 每个 Task 的 Acceptance Criteria 中，subagent 无需查阅外部 Spec 文件

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
