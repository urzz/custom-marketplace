---
name: skill-creator
description: Use when creating, designing, or implementing a new Claude Code skill from scratch, or when modifying, improving, auditing, or reviewing an existing skill.
---

# UG Skill Creator

End-to-end workflow for creating and iterating Claude Code skills. Enforces Anthropic best practices and Google 8 Agent Design Patterns.

## Critical Constraints

⚠️ **MANDATORY: 禁止跳过路由直接执行操作。**

无论用户指令看起来多么"简单"或"明确"，必须：
1. 先匹配 Routing Table 确定路径（CREATE / MODIFY / AUDIT）
2. 执行该路径对应的流程（Phase 1 或 Phase 1A 起步）
3. 只有在路径流程中明确允许的步骤内，才能执行实际操作

**禁止的行为：**
- 路由未匹配就直接执行操作（必须 HALT 并询问）
- 看到"检查变更"就直接跑 git diff 并给出结论（必须走 AUDIT 路径）
- 看到"修改 X"就直接编辑文件（必须走 MODIFY 路径）
- 跳过 Phase 1/1A 直接进入实现
- 将 AUDIT 请求当作简单问答处理
- 在任何阶段使用 EnterPlanMode（Phase 3 直接写入文件供用户 review，不切换模式）
- 以 fallback 为由降级为自行实现（superpowers 不可用 → 停止并等待用户指示，唯一选项）

## Contents
- [Routing](#routing)
- [Phase 1: Socratic Discovery](#phase-1-socratic-discovery)
- [Phase 1A: Audit Analysis](#phase-1a-audit-analysis)
- [Phase 2: Spec](#phase-2-spec)
- [Phase 3: Plan](#phase-3-plan)
- [Phase 4: Implement](#phase-4-implement)
- [Phase 5: Validate](#phase-5-validate)

## Routing

| Signal | Path |
|--------|------|
| User describes new capability, no existing skill referenced | **CREATE** |
| User points to existing skill + modification verb ("improve", "fix", "update", "优化", "修改", "修复") | **MODIFY** |
| User asks to review/check/audit/validate existing changes ("检查", "查看遗漏", "对比", "review", "validate", "是否完整", "是否有遗漏") | **AUDIT** |
| CWD contains SKILL.md + modification verb | **MODIFY** |
| CWD contains SKILL.md + review/check/audit verb | **AUDIT** |
| Ambiguous (multiple paths plausible) | Ask: "是创建新 skill、改进已有的、还是审查现有变更？" |
| **No match (兜底)** | **HALT — 禁止直接执行。输出："无法匹配路径，请明确你的意图：创建 / 修改 / 审查？" 等待用户回答后重新路由** |

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

## Phase 1A: Audit Analysis

**Goal:** 对已有变更进行结构化完整性审查，产出 Gap Report。AUDIT 路径不修改任何文件，只产出诊断报告。

### 适用场景
- 用户已完成一轮修改，想验证是否有遗漏
- 用户要求对比当前分支与 main 的变更
- 用户要求 review skill 变更的完整性

### Step A.1 — Scope Determination (no user interaction)

1. **确定审查目标：** 从用户指令中提取 skill 名称或分支名称
2. **确定对比基准：** 默认 `main`，用户指定则用指定值
3. **获取变更清单：** `git diff --name-only <base>...<head>` + `git diff <base>...<head>`
4. **分类变更文件：** 按 skill 结构分组（SKILL.md / references/ / agents/ / scripts/）

### Step A.2 — Structural Completeness Check

对变更后的完整 skill 按 [references/validation-checklist.md](references/validation-checklist.md) 的 8 个维度逐一审查：

1. **Spec Conformance** — 新增路由/步骤是否与已有 Spec 一致
2. **Pattern Consistency** — 是否引入了与主 Pattern 冲突的结构
3. **Flow Completeness** — 新增路径是否有完整的 Gate、退出条件、错误处理
4. **Structural Compliance** — description 是否覆盖新增触发词、body 行数、TOC 完整性
5. **Token Efficiency** — 是否有冗余重复、过长 inline 内容
6. **SDD 6.1.1 Handoff Compatibility** — Plan / delegation context / reviewer inputs 是否保持可交接与可审查
7. **Skill TDD and Wording Coverage** — 是否覆盖 RED / GREEN / REFACTOR 与 wording micro-test 策略
8. **Behavioral Correctness** — 路由、Gate、边界处理与输出行为是否符合预期

### Step A.3 — Functional Gap Analysis

针对变更的语义意图，检查：
- 新增的路由信号是否有对应处理路径
- 新增的步骤是否在 Contents/TOC 中注册
- 新增的动词/触发词是否在 description 中覆盖
- 模板/引用的新增字段是否在所有调用方同步更新
- 上下游 skill 的联动是否受影响（参考 CLAUDE.md 联动检查清单）

### Step A.4 — Gap Report (structured output)

输出格式：

~~~markdown
## Audit Report: <skill-name>

**对比基准：** <base>...<head>
**变更文件数：** N

### 变更摘要
- [列出关键变更点]

### 完整性审查

| 维度 | 状态 | 发现 |
|------|------|------|
| Spec Conformance | ✅/⚠️/❌ | 具体描述 |
| Pattern Consistency | ✅/⚠️/❌ | 具体描述 |
| Flow Completeness | ✅/⚠️/❌ | 具体描述 |
| Structural Compliance | ✅/⚠️/❌ | 具体描述 |
| Token Efficiency | ✅/⚠️/❌ | 具体描述 |
| SDD 6.1.1 Handoff Compatibility | ✅/⚠️/❌ | 具体描述 |
| Skill TDD and Wording Coverage | ✅/⚠️/❌ | 具体描述 |
| Behavioral Correctness | ✅/⚠️/❌ | 具体描述 |

### 功能遗漏项（如有）
1. [遗漏描述 + 建议修复方向]

### 结论
- ✅ 变更完整，无遗漏
- ⚠️ 存在 N 项建议改进（非阻塞）
- ❌ 存在 N 项必须修复的遗漏
~~~

### 硬性约束
- **AUDIT 路径禁止执行任何文件修改操作（Edit/Write）**
- 只输出诊断报告 + 建议修复项
- 如果发现需要修改，输出建议后**等待用户确认**
- 用户确认修复 → 切换到 MODIFY 路径（从 Phase 1 Step 1.2a 开始，root cause 已知）
- 用户确认无需修复 → 流程结束

---

## Phase 2: Spec

**Goal:** Define the complete skill specification. The Spec is a contract — subsequent phases must not deviate unless user explicitly requests.

### Step 2.1 — Full Spec (CREATE)

Fill the template from [references/templates.md#full-spec](references/templates.md#full-spec) with content derived from Phase 1.

### Step 2.1 — Delta Spec (MODIFY)

Fill the template from [references/templates.md#delta-spec](references/templates.md#delta-spec).

**Skill TDD requirement:** CREATE/MODIFY Spec 必须说明如何验证 skill 行为变化：RED baseline（无 guidance/control 下的失败或当前缺口）、GREEN expected behavior、REFACTOR/loophole checks。若变更属于 behavior-shaping guidance，必须包含 wording micro-test strategy。

### Step 2.2 — Pattern Selection

1. Recommend pattern + one-sentence rationale based on First Principles Statement
2. User agrees → write into Spec
3. User challenges → expand to 2-3 candidates with tradeoffs, user picks

Reference: [references/design-patterns.md](references/design-patterns.md) for pattern details and templates.

### Hard Gate: Spec 确认（Phase 2 → Phase 3 唯一出口）

⚠️ **Direct Write + Review Gate 模式：**

1. **直接保存** — 使用 Write 工具将 Spec 写入 `.claude/plans/<skill-name>-<变更主题>-spec.md`（已存在则覆盖）
2. **输出摘要** — 使用以下固定模板：
   ```
   ✅ Spec 已保存到 `.claude/plans/<skill-name>-<变更主题>-spec.md`

   **摘要：** [3-5 行核心要点]

   请 review 文件内容，确认后说"继续"进入下一阶段。如需调整请直接说明。
   ```
3. **等待用户** — 用户说"继续"/"确认"/"可以" → 进入 Phase 3；用户提出调整 → 修改后重新保存

**文件命名规则：** `<变更主题>` ≤ 3 个单词，kebab-case，概括本次变更核心。

自检清单（进入 Phase 3 前必须全部为 YES）：
- [ ] 已执行 Write 工具保存 Spec 文件？
- [ ] 已输出保存确认模板（含摘要 + review 提示）？
- [ ] 用户说了肯定词？

全部 YES → 进入 Phase 3。任一 NO → 停留在 Phase 2。

---

## Phase 3: Plan

**Goal:** Translate Spec into an executable Task list — bite-sized, checkboxed, directly dispatchable to sub agents.

### Step 3.1 — Analyze and Decompose

Read the confirmed Spec. Identify files to create/modify/delete, logical grouping, and dependencies.

### Step 3.2 — Output Task List

Use the format from [references/templates.md#task-format](references/templates.md#task-format).

**格式要求：**
- Steps 必须自包含（完整内容，不用 placeholder，不引用外部文件）；exact values 必须写入 Plan / task brief，而不是留给后续 dispatch prompt 重新补全或解释。
- Spec 关键信息（业务意图 + Pattern 结构 + 验收标准）直接写入对应 Task 的 Acceptance Criteria（sub agent 不需要查外部文件）
- 最后一步必须是验证步骤（implementer 自检）
- Acceptance Criteria 供 superpowers spec reviewer 做 compliance check

**SDD 6.1.1 compatibility requirements:**
- Plan 必须包含 header：Goal / Architecture / Tech Stack / Global Constraints。
- Global Constraints 必须复制本次 Spec 中跨 Task 生效的约束，供 reviewer 直接使用。
- 每个 Task 必须包含 `Interfaces`：`Consumes` 和 `Produces`，说明与前后 Task 的依赖关系。
- 每个 Task 必须使用 checkbox steps（`- [ ]`），并保持 `### Task N:` 标题格式，确保 `superpowers:subagent-driven-development` 的 `scripts/task-brief PLAN_FILE N` 可提取单个 Task。
- 每个 Task 的 Acceptance Criteria 必须继续包含：Pattern 结构约束、业务意图、验收标准。
- Plan 可以继续保存到 `.claude/plans/<skill-name>-<变更主题>-plan.md`；这是本 skill 的项目约定路径，覆盖 `superpowers:writing-plans` 默认路径，但不得降低 SDD 6.1.1 的格式兼容性。

### Step 3.3 — User Confirmation

Present in conversation (do NOT use EnterPlanMode). User confirms → proceed; adjustments → revise and re-confirm.

### Hard Gate: Plan 确认（Phase 3 → Phase 4 唯一出口）

⚠️ **Direct Write + Review Gate 模式：**

1. **直接保存** — 使用 Write 工具将 Plan 写入 `.claude/plans/<skill-name>-<变更主题>-plan.md`（已存在则覆盖）
2. **输出摘要** — 使用以下固定模板：
   ```
   ✅ Plan 已保存到 `.claude/plans/<skill-name>-<变更主题>-plan.md`

   **摘要：** [3-5 行核心要点]

   请 review 文件内容，确认后说"继续"进入下一阶段。如需调整请直接说明。
   ```
3. **等待用户** — 用户说"继续"/"确认"/"可以" → 进入 Phase 4；用户提出调整 → 修改后重新保存

**文件命名规则：** 与 Phase 2 一致，使用相同的 `<变更主题>` slug。

自检清单（进入 Phase 4 前必须全部为 YES）：
- [ ] 已执行 Write 工具保存 Plan 文件？
- [ ] 已输出保存确认模板（含摘要 + review 提示）？
- [ ] 用户说了肯定词？

全部 YES → 进入 Phase 4。任一 NO → 停留在 Phase 3。

---

## Phase 4: Implement

⚠️ **MANDATORY: 禁止自行实现。本 Phase 的唯一执行方式是委托 superpowers:subagent-driven-development。**

**禁止的行为：**
- 直接使用 Edit/Write 工具修改 skill 文件（SKILL.md、references/、agents/）
- 以"先改一下试试"为由跳过委托
- 部分委托 + 部分自行修改
- 在委托前"预先"修改文件

**Red Flags — 以下想法出现时立即停止，你正在绕过流程：**

| 你的想法 | 现实 |
|---------|------|
| "这只是改一行，不值得 spawn agent" | 无论变更大小，Phase 4 唯一路径是委托 |
| "任务太简单了，直接改更快" | 简单 ≠ 可以绕过流程；流程保证一致性 |
| "superpowers 加载失败，我先手动改" | 不可用 → 停止等待用户指示，不可降级 |
| "sub agent 已经完成了，我补充一点小修改" | 追加修改 → 必须重新进入 Phase 4 Step 4.2 |
| "我先预处理一下文件再委托" | 预处理 = 违规修改，禁止 |

**唯一合法路径：** Phase 3 Hard Gate 通过 → Step 4.1 准备上下文 → Step 4.2 调用 superpowers → superpowers 完成后 Step 4.3 生成 Eval Prompts。

**Goal:** 委托 superpowers 执行 Plan，获得 implementer → task reviewer（spec compliance + code quality）→ fix/re-review → final whole-branch review 的 SDD 6.1.1 流程。

### Step 4.1 — 准备委托上下文

组装以下信息：
1. Plan 文件路径: `.claude/plans/<skill-name>-<变更主题>-plan.md`
2. 领域约束: 使用 [references/templates.md#delegation-context](references/templates.md#delegation-context) 模板，填入当前 skill 信息

额外组装 SDD 6.1.1 执行约束：
1. 执行 Task 1 前进行 Pre-Flight Plan Review，检查 Task 之间是否互相矛盾、是否与 Global Constraints 冲突。
2. 每个 Task dispatch 前使用 `scripts/task-brief PLAN_FILE N` 生成 task brief，brief 是 implementer 的需求单一来源。
3. 每个 implementer 必须写详细 report file，只在最终回复中返回短状态、commit、测试摘要、concerns、report path。
4. 每个 Task 完成后使用 `scripts/review-package BASE HEAD` 生成 diff package，再交给 task reviewer。
5. task reviewer 使用单个 review gate 同时判断 spec compliance 与 code quality。
6. Critical/Important findings 必须由 fix subagent 修复并 re-review；fix report 必须追加覆盖测试命令与输出。
7. 每个完成的 Task 必须写入 `.superpowers/sdd/progress.md` ledger，支持 compaction/resume。
8. 全部 Task 完成后运行 final whole-branch review。
9. 所有 subagent dispatch 必须显式指定 model；不要依赖 session 默认 model。

### Step 4.2 — 委托 superpowers:subagent-driven-development

通过 Skill tool 调用 `superpowers:subagent-driven-development`，传入：
- Plan 路径
- SDD 6.1.1 执行约束（pre-flight review / task brief / report file / review package / task reviewer / ledger / final review / explicit model selection）
- 领域约束（作为 task reviewer 的 Global Constraints / spec reviewer attention lens）

**Fallback:** 如果 superpowers 插件不可用，输出："⚠️ superpowers 插件未安装，无法执行 Phase 4。请安装后重试。" 然后停止并等待用户指示；禁止手动按 Plan 执行或降级为主 session 自行实现。

### Step 4.3 — 生成 Eval Prompts

superpowers 完成后（所有 Task PASS），基于 Spec Section 3 (Architecture) 和 Section 5 (Success Criteria) 生成 Eval Prompts。

Use the format from [references/templates.md#eval-prompts-template](references/templates.md#eval-prompts-template).

三类验证 prompts：
1. **行为验证（Trajectory）** — 2-3 个：路径选择、Gate 暂停、输出结构
2. **边界验证（Adversarial）** — 1-2 个：模糊输入、跨领域输入
3. **质量基线（LLM-as-Judge）** — 1-2 个：with-skill vs baseline 对比

### Post-delegation Constraint

⚠️ **superpowers 返回后禁止追加修改：**
- 禁止主 session 使用 Edit/Write 修改 skill 文件（SKILL.md、references/、agents/）
- 如需追加修改 → 必须重新进入 Phase 4 Step 4.2 委托
- 唯一例外：Phase 5 验证失败后的修复循环（通过 Step 4.2 重新委托执行）

**Auto-transition to Phase 5（no user gate）。**

---

## Phase 5: Validate

**Goal:** 双 Hard Gate 验证 — 结构合规 + 行为正确。全部通过才算 Skill ready to use。

### Step 5.1 — Structural Validation (Hard Gate)

Read [references/validation-checklist.md](references/validation-checklist.md) and run structural Dimensions 1-7:

1. Spec Conformance
2. Pattern Consistency
3. Flow Completeness
4. Structural Compliance
5. Token Efficiency
6. SDD 6.1.1 Handoff Compatibility
7. Skill TDD / Micro-test Coverage

**If any fail:**
- List failures with evidence + fix suggestions
- 回 Phase 4 Step 4.2 修复（通过 superpowers 重新执行相关 Task）
- Maximum 2 fix cycles; after 2 failures → stop, report to user, await instructions

### Step 5.2 — Behavioral Validation (Hard Gate)

**Precondition:** Step 5.1 all pass.

使用 Step 4.3 生成的 Eval Prompts，spawn eval agent（instructions: [agents/skill-creator-eval.md](agents/skill-creator-eval.md)）执行模拟验证。

**验证维度（详见 [references/validation-checklist.md#dimension-8-behavioral-correctness](references/validation-checklist.md#dimension-8-behavioral-correctness)）：**

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
