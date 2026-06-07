---
name: skill-creator
description: Use when creating, designing, or implementing a new Claude Code skill from scratch, or when modifying, improving, optimizing, or updating an existing skill. Guides through Socratic discovery with first-principles thinking, spec definition with Google 8 pattern selection, implementation planning, code generation following Anthropic best practices, and dual-layer quality validation. Triggers on skill creation requests, skill improvement requests, packaging workflows into reusable skills, or explicit invocation.
---

# UG Skill Creator

End-to-end workflow for creating and iterating Claude Code skills. Enforces Anthropic best practices and Google 8 Agent Design Patterns.

## Contents
- [Routing](#routing)
- [Phase 1: Socratic Discovery](#phase-1-socratic-discovery)
- [Phase 2: Spec](#phase-2-spec)
- [Phase 3: Plan](#phase-3-plan)
- [Phase 4: Implement](#phase-4-implement)
- [Phase 5: Validate](#phase-5-validate)

## Routing

| Signal | Path |
|--------|------|
| User describes new capability, no existing skill referenced | **CREATE** |
| User points to existing skill + modification verb ("improve", "fix", "update", "优化", "修改", "修复") | **MODIFY** |
| CWD contains SKILL.md | **MODIFY** |
| Ambiguous | Ask: "是创建新 skill，还是改进已有的？" |

---

## Phase 1: Socratic Discovery

**Goal:** Approach the user's need through structured questioning to reach first principles.

### CREATE Path

#### Step 1.1 — Clarify Intent (What)
- "你想让这个 skill 做什么？现在是怎么手动做的？"
- Goal: understand the surface requirement

#### Step 1.2 — Challenge Assumptions (Why)
- "为什么需要 X？如果去掉 X 会怎样？"
- "这个能力是每次都需要，还是偶尔用到？"
- Goal: strip nice-to-have, find must-have

#### Step 1.3 — First Principles
- "这个 skill 解决的根本问题是什么？"
- "最小必要能力是什么？"
- Goal: reduce to irreducible core

#### Questioning Rules (CREATE)
1. **Pace:** 每轮 ≤ 2 个问题，等待用户回答后再继续
2. **Pre-filter:** 每个问题前自问"答案会改变 Spec 吗？"——不会则不问
3. **Info priority:** 可从代码/上下文推导的 → 不问；需确认意图的 → 带判断地问；完全未知的 → 开放提问
4. **Exit:** 满足任一即退出当前步骤：
   - 累计已问 ≥ 7 个问题
   - 连续 1 轮未获得新信息（当前步骤收敛 → 进入下一步）
   - 三步（What → Why → First Principles）均完成

### MODIFY Path

#### Step 1.0 — Self-Diagnosis (no user interaction)
- Read all skill files (SKILL.md + references/ + agents/ + scripts/)
- Assess: current Pattern, structural compliance, description quality

#### Step 1.1 — Intent Routing

| User Input | Sub-flow |
|------------|----------|
| Specific change target ("改 description", "加一个步骤") | → Step 1.2a |
| Vague ("优化", "改进", no specific direction) | → Step 1.2b |

#### Step 1.2a — Root Cause (specific target)
- "这个问题的根本原因是流程设计问题、prompt 表述问题、还是缺少某个能力？"

#### Step 1.2b — OPTIMIZE (no specific direction)

⚠️ **硬性约束：Step 1.2b 必须至少产生 1 轮用户交互后，才能输出最终诊断报告。禁止直接输出诊断。**

**1.2b-i: 追问（必须执行）** — 基于 Step 1.0 诊断，生成 ≤ 3 个追问（变更意图确认 / 根因方向选择 / 优先级排序）

**1.2b-ii: 诊断输出（用户回答后）** — 按用户确认的优先级输出诊断报告，涵盖：structural compliance / pattern fit / trigger accuracy / token efficiency / flow completeness

#### Questioning Rules (MODIFY)
1. **Pace:** 每轮 ≤ 2 个问题，等待用户回答后再继续
2. **Pre-filter:** 每个问题前自问"答案会明确根因或改变范围吗？"——不会则不问
3. **Exit:** 满足任一即收敛输出 Change First Principles：
   - 累计已问 ≥ 4 个问题
   - 连续 1 轮未获得新信息

### Phase 1 Output

Output format templates: [references/templates.md#phase-1-output](references/templates.md#phase-1-output)

**Gate:** User confirms the statement before proceeding to Phase 2.

---

## Phase 2: Spec

**Goal:** Define the complete skill specification. The Spec is a contract — subsequent phases must not deviate unless user explicitly requests.

### Step 2.1 — Full Spec (CREATE)

Fill the template from [references/templates.md#full-spec](references/templates.md#full-spec) with content derived from Phase 1.

### Step 2.1 — Delta Spec (MODIFY)

Fill the template from [references/templates.md#delta-spec](references/templates.md#delta-spec).

### Step 2.2 — Pattern Selection

1. Recommend pattern + one-sentence rationale based on First Principles Statement
2. User agrees → write into Spec
3. User challenges → expand to 2-3 candidates with tradeoffs, user picks

Reference: [references/design-patterns.md](references/design-patterns.md) for pattern details and templates.

**Gate:** User confirms Spec / Delta Spec before proceeding to Phase 3.

### Persist (MUST)

Gate 通过后，**立即**执行：
1. Write 确认的 Spec 到 `.claude/plans/<skill-name>-spec.md`（已存在则覆盖）
2. 输出确认："✅ Spec 已保存到 `.claude/plans/<skill-name>-spec.md`"

---

## Phase 3: Plan

**Goal:** Translate Spec into an executable Task list — bite-sized, checkboxed, directly dispatchable to sub agents.

### Step 3.1 — Analyze and Decompose

Read the confirmed Spec. Identify files to create/modify/delete, logical grouping, and dependencies.

### Step 3.2 — Output Task List

Use the format from [references/templates.md#task-format](references/templates.md#task-format).

**格式要求：**
- Steps 必须自包含（完整内容，不用 placeholder，不引用外部文件）
- Pattern 结构约束直接写入对应 Task 的 Acceptance Criteria（sub agent 不需要查 design-patterns.md）
- 最后一步必须是验证步骤（implementer 自检）
- Acceptance Criteria 供 superpowers spec reviewer 做 compliance check

### Step 3.3 — User Confirmation

Present in conversation (do NOT use EnterPlanMode). User confirms → proceed; adjustments → revise and re-confirm.

**Gate:** User confirms Plan before proceeding to Phase 4.

### Persist (MUST)

Gate 通过后，**立即**执行：
1. Write 确认的 Plan 到 `.claude/plans/<skill-name>-plan.md`（已存在则覆盖）
2. 输出确认："✅ Plan 已保存到 `.claude/plans/<skill-name>-plan.md`"

---

## Phase 4: Implement

**Goal:** 委托 superpowers 执行 Plan，获得 dev→spec review→code quality review→fix 循环。

### Step 4.1 — 准备委托上下文

组装以下信息：
1. Plan 文件路径: `.claude/plans/<skill-name>-plan.md`
2. Spec 文件路径: `.claude/plans/<skill-name>-spec.md`
3. 领域约束: 使用 [references/templates.md#delegation-context](references/templates.md#delegation-context) 模板，填入当前 skill 信息

### Step 4.2 — 委托 superpowers:subagent-driven-development

通过 Skill tool 调用 `superpowers:subagent-driven-development`，传入：
- Plan 路径
- 领域约束（作为 spec reviewer 的验证标准）
- Spec 路径（作为 context 参考）

**Fallback:** 如果 superpowers 插件不可用，输出："⚠️ superpowers 插件未安装，无法执行 Phase 4。请安装后重试，或手动按 Plan 逐 Task 执行。"

### Step 4.3 — 生成 Eval Prompts

superpowers 完成后（所有 Task PASS），基于 Spec Section 3 (Architecture) 和 Section 5 (Success Criteria) 生成 Eval Prompts。

Use the format from [references/templates.md#eval-prompts-template](references/templates.md#eval-prompts-template).

三类验证 prompts：
1. **行为验证（Trajectory）** — 2-3 个：路径选择、Gate 暂停、输出结构
2. **边界验证（Adversarial）** — 1-2 个：模糊输入、跨领域输入
3. **质量基线（LLM-as-Judge）** — 1-2 个：with-skill vs baseline 对比

**Auto-transition to Phase 5（no user gate）。**

---

## Phase 5: Validate

**Goal:** 双 Hard Gate 验证 — 结构合规 + 行为正确。全部通过才算 Skill ready to use。

### Step 5.1 — Structural Validation (Hard Gate)

Read [references/validation-checklist.md](references/validation-checklist.md) and run Dimensions 1-5:

1. Spec Conformance
2. Pattern Consistency
3. Flow Completeness
4. Structural Compliance
5. Token Efficiency

**If any fail:**
- List failures with evidence + fix suggestions
- 回 Phase 4 Step 4.2 修复（通过 superpowers 重新执行相关 Task）
- Maximum 2 fix cycles; after 2 failures → stop, report to user, await instructions

### Step 5.2 — Behavioral Validation (Hard Gate)

**Precondition:** Step 5.1 all pass.

使用 Step 4.3 生成的 Eval Prompts，spawn eval agent（instructions: [agents/skill-creator-eval.md](agents/skill-creator-eval.md)）执行模拟验证。

**验证维度（详见 [references/validation-checklist.md#dimension-6-behavioral-correctness](references/validation-checklist.md#dimension-6-behavioral-correctness)）：**

| 维度 | 通过标准 |
|------|----------|
| 路径正确性 | 100% 路径匹配预期 |
| Gate 完整性 | 所有 Hard Gate 均触发暂停 |
| 边界处理 | 正确澄清或拒绝 |
| 输出格式 | description 格式、行数、TOC 合规 |
| 一致性 | 同一 prompt 多次执行路径一致 |

**If any fail:**
- List failures: 失败维度 + 具体 prompt + 实际行为 vs 预期行为
- 回 Phase 4 Step 4.2 修复
- Maximum 2 fix cycles; after 2 failures → stop, report to user, await instructions

### 完成条件

Step 5.1 + Step 5.2 均通过 → 输出：
- "✅ Skill 验证通过，ready to use"
- 验证报告摘要（各维度结果一行总结）
