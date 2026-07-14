---
name: skill-forge
description: Use when creating, designing, or implementing a new Claude Code skill from scratch, or when modifying, improving, auditing, or reviewing an existing skill.
---

# Skill Forge

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
- Phase 4 审查环节不可跳过：per-task review 和 final review subagent 均为硬性环节，无论 Task 大小
- Phase 4 全程不产生最终多 commit：squash 由主 session 在 Phase 5 全部通过后统一执行，implementer/reviewer 不得自行 squash 或 rebase

## Contents
- [Routing](#routing)
- [中间文档目录命名规则](#中间文档目录命名规则)
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

## 中间文档目录命名规则

本 skill 在 Phase 2/3/4 产生的中间产物（Spec / Plan / Task 报告 / Eval Prompts）统一存放到
`.skill-forge/<skill-name>-<变更主题>/` 子目录，目录内平铺，无子目录嵌套：

| 产物 | 文件名 |
|------|--------|
| Spec | `spec.md` |
| Plan | `plan.yaml` |
| 每个 Task 的实现报告 | `task<N>-report.md` |
| Eval Prompts | `eval-prompts.md` |

**规则：**
- `<变更主题>` ≤ 3 个单词，kebab-case，沿用 Phase 2/3 Spec 保存时确定的 slug（同一次变更全程使用同一 slug，不可中途改名）。
- 工作目录内自带 `.gitignore`（内容 `*`），该 `.gitignore` 自身也不入库（git 读取未跟踪的 `.gitignore` 作忽略规则，`*` 忽略同目录所有产物含自身），跨项目通用，不污染所在仓库根 `.gitignore`（对标 superpowers `.superpowers/sdd/.gitignore` 机制）。
- **首次创建 `.skill-forge/` 工作目录时，skill 必须检查 `.skill-forge/.gitignore` 是否存在，不存在则写入内容 `*`。** 此机制确保忽略规则自动建立，无需手动配置，跨项目通用。
- 旧版本曾使用共享 plans 目录下的扁平命名（`<skill-name>-<变更主题>-*.md`），已废弃；新变更一律使用上述新路径。

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
1. **Pace:** 严格一次一问 —— 每次只问 1 个问题，等待用户回答后再继续。
   禁止在同一轮列出多个问题。
2. **Recommendation-First:** 每个问题必须附带你自己的推荐答案（基于已读
   代码/上下文的判断），让用户对着"同意/修正"做判断题而非从零构思。
   格式：<问题>？我的推荐是 <推荐答案>（理由：<一句话依据>）。
3. **Pre-filter:** 每个问题前自问"答案会改变 Spec 吗？"——不会则不问
4. **Info priority:** 可从代码/上下文推导的 → 不问；需确认意图的 →
   带判断地问；完全未知的 → 开放提问
5. **Exit（收敛为主，计数为安全阀）:**
   - **主信号:** 同一 Step 内连续 2 次用户对推荐答案"直接接受、无修正"
     → 判定该 Step 收敛，退出当前 Step
   - **安全阀（仅防止无限循环，不作为主逻辑）:** 累计已问 ≥ 15 个问题
   - 三步（What → Why → First Principles）均收敛或触发安全阀 → 进入 Phase 1 Output

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
1. **Pace:** 严格一次一问 —— 每次只问 1 个问题，等待用户回答后再继续。
   禁止在同一轮列出多个问题。
2. **Recommendation-First:** 每个问题必须附带你自己的推荐答案。
   格式：<问题>？我的推荐是 <推荐答案>（理由：<一句话依据>）。
3. **Pre-filter:** 每个问题前自问"答案会明确根因或改变范围吗？"——不会则不问
4. **Exit（收敛为主，计数为安全阀）:**
   - **主信号:** 连续 2 次用户对推荐答案"直接接受、无修正"→ 收敛输出 Change First Principles
   - **安全阀:** 累计已问 ≥ 10 个问题

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

对变更后的完整 skill 按 [references/validation-checklist.md](references/validation-checklist.md) 的 6 个维度逐一审查：

1. **Spec Conformance** — 新增路由/步骤是否与已有 Spec 一致
2. **Pattern Consistency** — 是否引入了与主 Pattern 冲突的结构
3. **Flow Completeness** — 新增路径是否有完整的 Gate、退出条件、错误处理
4. **Structural Compliance** — description 是否覆盖新增触发词、body 行数、TOC 完整性
5. **Token Efficiency** — 是否有冗余重复、过长 inline 内容
6. **Cross-reference Integrity** — 被引用的 references/agents 文件是否存在且内容匹配

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
| Cross-reference Integrity | ✅/⚠️/❌ | 具体描述 |

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

### Step 2.2 — Pattern Selection

1. Recommend pattern + one-sentence rationale based on First Principles Statement
2. User agrees → write into Spec
3. User challenges → expand to 2-3 candidates with tradeoffs, user picks

Reference: [references/design-patterns.md](references/design-patterns.md) for pattern details and templates.

### Hard Gate: Spec 确认（Phase 2 → Phase 3 唯一出口）

⚠️ **Direct Write + Review Gate 模式：**

1. **前置：建立忽略规则** — 保存 spec 前，若 `.skill-forge/.gitignore` 不存在，先写入内容 `*`（首次创建工作目录时自动建立忽略规则）
2. **直接保存** — 使用 Write 工具将 Spec 写入 `.skill-forge/<skill-name>-<变更主题>/spec.md`（已存在则覆盖，目录不存在则创建）
3. **输出摘要** — 使用以下固定模板：
   ```
   ✅ Spec 已保存到 `.skill-forge/<skill-name>-<变更主题>/spec.md`

   **摘要：** [3-5 行核心要点]

   请 review 文件内容，确认后说"继续"进入下一阶段。如需调整请直接说明。
   ```
4. **等待用户** — 用户说"继续"/"确认"/"可以" → 进入 Phase 3；用户提出调整 → 修改后重新保存

**文件命名规则：** `<变更主题>` ≤ 3 个单词，kebab-case，概括本次变更核心。

自检清单（进入 Phase 3 前必须全部为 YES）：
- [ ] 已确认 `.skill-forge/.gitignore` 存在（内容 `*`）？
- [ ] 已执行 Write 工具保存 Spec 文件？
- [ ] 已输出保存确认模板（含摘要 + review 提示）？
- [ ] 用户说了肯定词？

全部 YES → 进入 Phase 3。任一 NO → 停留在 Phase 2。

---

## Phase 3: Plan

**Goal:** Translate Spec into an executable YAML Task list — bite-sized, directly dispatchable to sub agents. Plan 输出为 YAML 格式（路径 `.skill-forge/<skill-name>-<变更主题>/plan.yaml`）。

### Step 3.1 — Analyze and Decompose

Read the confirmed Spec. Identify files to create/modify/delete, logical grouping, and dependencies.

### Step 3.2 — Output Task List (YAML)

Use the YAML format from [references/templates.md#task-format](references/templates.md#task-format).

**Plan 结构要求：**
- Plan 必须为 YAML 格式，以 [references/templates.md#plan-document-header](references/templates.md#plan-document-header) 结构开头
- Global Constraints 从已确认的 Spec 中逐字提取项目级约束

**YAML Schema 说明（详见 [references/templates.md#task-format](references/templates.md#task-format)）：**
- 顶层字段：`goal` / `architecture` / `global_constraints[]` / `tasks[]`
- 每个 task 含：`id` / `name` / `files` / `interfaces` / `steps[]` / `acceptance_criteria[]` / `meta`
- `meta` 三字段取值规则：
  - `model`: `haiku`（单文件 mechanical 实现）| `sonnet`（多文件协调 / pattern judgment）| `opus`（复杂结构性变更）
  - `file_type`: `markdown`（skill 文件）| `script`（scripts/）| `mixed`（含两者）
  - `requires_execution_check`: `true` 时 implementer 必须跑样例验证并贴输出；`false` 时自检即可

**Task Right-Sizing：**
- 一个 Task 是最小的、拥有独立测试/验证周期的单元
- 将 setup、scaffolding、文档步骤折入需要它们的 Task（不单独成 Task）
- 仅在 reviewer 可以独立拒绝一个 Task 而不影响另一个时才拆分
- 每个 Task 以可独立验证的 deliverable 结束

**格式要求：**
- Steps 必须自包含（完整内容，不用 placeholder，不引用外部文件）
- Spec 关键信息（业务意图 + Pattern 结构 + 验收标准）直接写入对应 Task 的 acceptance_criteria（sub agent 不需要查外部文件）
- 最后一步必须是验证步骤（implementer 自检）
- Acceptance Criteria 供 reviewer 做 compliance check

### Step 3.3 — Self-Review (YAML 结构)

Plan 写完后、用户 review 前，对 YAML 结构执行以下三项自检：

1. **Spec Coverage** — 遍历 `tasks[].acceptance_criteria`，逐项对照 Spec 的 Section 2 (Contract) 和 Section 5 (Success Criteria)，确认每项都能指向一个 Task。发现遗漏 → 补充 Task。
2. **Placeholder Scan** — 搜索 YAML 字符串值中的 red flags：`TBD`、`TODO`、`implement later`、`similar to Task N`、`fill in details`、缺少代码的代码步骤。发现 → 原地修复。
3. **Type Consistency** — 检查跨 Task 引用的路径字符串逐字一致（Task 1 用的文件路径 / 锚点名在 Task 3 中是否完全相同）。发现不一致 → 原地修复。

自检发现问题 → 直接修复，无需重新 review。三项均通过 → 进入 Step 3.4。

### Step 3.4 — User Confirmation

Present in conversation (do NOT use EnterPlanMode). YAML 本身可读，直接展示原文或输出简化列表摘要供用户 review。User confirms → proceed; adjustments → revise and re-confirm.

### Hard Gate: Plan 确认（Phase 3 → Phase 4 唯一出口）

⚠️ **Direct Write + Review Gate 模式：**

1. **直接保存** — 使用 Write 工具将 Plan 写入 `.skill-forge/<skill-name>-<变更主题>/plan.yaml`（已存在则覆盖，目录不存在则创建；Phase 2 已建立 `.gitignore`，此处沿用，无需重复写入）
2. **输出摘要** — 使用以下固定模板：
   ```
   ✅ Plan 已保存到 `.skill-forge/<skill-name>-<变更主题>/plan.yaml`

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

⚠️ MANDATORY: 本 Phase 通过本 skill 自建的轻量 implement→review 闭环执行，
不委托外部 skill。审查环节（per-task review + final review）不可跳过。

**Red Flags — 以下想法出现时立即停止，你正在绕过流程：**

| 你的想法 | 现实 |
|---------|------|
| "这只是改一行，不值得 spawn agent" | 无论变更大小，Phase 4 唯一路径是 dispatch 自建 agent |
| "任务太简单了，直接改更快" | 简单 ≠ 可以绕过流程；流程保证一致性 |
| "这个 Task 很简单，review 环节可以跳过" | 无论大小，per-task review 是硬性环节，不可跳过 |
| "各 Task 都过了，最后 diff 应该没问题，不用 final review" | Final review 检查跨 Task 一致性，是 per-task review 覆盖不到的维度，不可省略 |
| "sub agent 已经完成了，我补充一点小修改" | 追加修改 → 必须重新进入 Phase 4 Step 4.1 |
| "我先预处理一下文件再 dispatch 自建 agent" | 预处理 = 违规修改，禁止 |

**Goal:** 自建 Sequential + Generator-Critic 组合执行 Plan，获得 implement→review→fix 循环。

### Step 4.0 — 记录基准
INITIAL_BASE=$(git rev-parse HEAD)，记录用于 Task 1 的 diff 基准和最终 rebase 基准。

### Step 4.1 — 逐 Task 循环
对 Plan YAML 中每个 tasks[] 项，按 id 顺序执行：
1. dispatch agents/skill-file-implementer.md（model 取自该 Task 的 meta.model，值直接作为 Agent tool 的 model 参数），
   prompt 含 Plan YAML 绝对路径 + Task ID + 上一 Task 产生的接口信息 + scripts/plan-task-query.py 绝对路径 + 报告输出路径 `.skill-forge/<skill-name>-<变更主题>/task<N>-report.md`。
   **dispatch prompt 必须显式包含 `scope` 与 `ticket` 两个字段**：
   - `scope` = 被改 skill 名(如 `skill-forge`)
   - `ticket` 由主 session 从当前分支名提取后传入（如 `feature/UG-883685-xxx` → `UG-883685`）
   - implementer 直接使用这两个字段，**不得自行解析分支名或硬编码**
   implementer 自行调用该脚本取 brief（脚本路径由主 session 解析为绝对路径注入，不依赖 subagent CWD），完成后将报告写到指定的报告路径。
2. implementer 完成后在当前分支执行一次 commit，commit message 格式为
   `feat(<scope>): [Task N] <name>`（scope/ticket 取自 dispatch prompt），
   记录 TASK_N_HEAD。`[Task N]` 保留为 subject 前缀，维持任务边界可追溯。
   Task 1 对比基准 = INITIAL_BASE；Task N>1 对比基准 = TASK_(N-1)_HEAD。
3. dispatch agents/skill-file-reviewer.md，对比 TASK_(N-1)_HEAD..TASK_N_HEAD 的 diff，
   做 spec compliance + structural compliance 审查（无 TDD/Tests 维度；
   meta.requires_execution_check 为 true 时额外检查执行证据）。
4. reviewer 报告问题 → dispatch fix subagent → 追加 commit → 重新审查，直至通过。
5. 标记 Task 完成，进入下一 Task。

### Step 4.2 — Final Review
全部 Task 通过后，dispatch agents/skill-file-final-reviewer.md，对比
git diff INITIAL_BASE..HEAD 的完整 diff，做跨 Task 一致性 + Spec Section 2/5 覆盖度检查。

### Step 4.3 — 生成 Eval Prompts
基于 Spec Section 3 和 Section 5 生成 Eval Prompts（格式沿用 references/templates.md#eval-prompts-template）。

### Step 4.4 — Squash（仅 Phase 5 全部通过后执行）
执行前向用户说明："即将把本次 Phase 4 产生的 N 个小 commit 合并为 1 个，
commit message 将替换为 `feat(<scope>): <汇总>`（scope/ticket 与 per-task commit 一致），是否继续？"
> <INITIAL_BASE_SHA> 替换为 Step 4.0 记录的实际 commit SHA（$(git rev-parse HEAD) 的输出）。
合并命令（macOS BSD sed 兼容，Linux 同样可用）：GIT_SEQUENCE_EDITOR="sed -i '' -e '1!s/^pick/squash/'" git rebase -i <INITIAL_BASE_SHA>
合并后 commit message 由主 session 生成一句话汇总，格式为 `feat(<scope>): <汇总>`，
覆盖 rebase 默认拼接 message。

### Post-delegation Constraint
final review 通过后，主 session 禁止直接 Edit/Write skill 文件；如需追加修改必须重新
进入 Phase 4 Step 4.1 委托。
唯一例外：Phase 5 验证失败后的修复循环（重新 dispatch implementer）。
Auto-transition to Phase 5（no user gate）。

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

**执行方式：** 结构合规检查（Dimension 1-5）使用 Bash 命令（`wc -l`、`grep -c`、`grep -rn`）做机械检查，不整段 Read 文件内容，减少主 session 上下文占用。各 Dimension 的 How to Verify 列已给出对应命令；纯语义判定项标注 Manual check。Dimension 1-5 的判定标准本身不变。

**If any fail:**
- List failures with evidence + fix suggestions
- 回 Phase 4 Step 4.1 修复（重新 dispatch implementer 执行相关 Task）
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
| 一致性 | 同一 prompt 执行 1 次；若 Step 5.1 结构检查全部通过，视为高置信度，不重复验证一致性；仅当本次变更涉及 Routing/Gate 逻辑改动时才追加 1 次重跑 |
| 质量基线（LLM-as-Judge） | 仅当 Delta Spec 的 Changed 部分包含 Pattern/Architecture 级改动时才执行 with-skill vs baseline 双跑；纯内容/文案微调（无结构变化）跳过该维度，标记为 SKIP |

**If any fail:**
- List failures: 失败维度 + 具体 prompt + 实际行为 vs 预期行为
- 回 Phase 4 Step 4.1 修复
- Maximum 2 fix cycles; after 2 failures → stop, report to user, await instructions

### 完成条件

Step 5.1 + Step 5.2 均通过 → 输出：
- "✅ Skill 验证通过，ready to use"
- 验证报告摘要（各维度结果一行总结）
