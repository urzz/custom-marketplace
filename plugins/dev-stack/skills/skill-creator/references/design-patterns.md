# Google 8 Agent Design Patterns

来源：Google Agent Development Kit (ADK) 2025 / Antonio Gullí "Agentic Design Patterns"

基于三个基础原语：`SequentialAgent`、`ParallelAgent`、`LoopAgent`

Reference framework for selecting the appropriate architecture pattern when designing a Claude Code skill. Use the decision flowchart to select a pattern, then use the corresponding SKILL.md structure template as your implementation skeleton.

## Contents
- [Decision Flowchart](#decision-flowchart)
- [Pattern 1: Sequential Pipeline](#pattern-1-sequential-pipeline)
- [Pattern 2: Coordinator/Dispatcher](#pattern-2-coordinatordispatcher)
- [Pattern 3: Parallel Fan-Out/Gather](#pattern-3-parallel-fan-outgather)
- [Pattern 4: Hierarchical Decomposition](#pattern-4-hierarchical-decomposition)
- [Pattern 5: Generator-Critic](#pattern-5-generator-critic)
- [Pattern 6: Iterative Refinement](#pattern-6-iterative-refinement)
- [Pattern 7: Human-in-the-Loop](#pattern-7-human-in-the-loop)
- [Pattern 8: Composite](#pattern-8-composite)
- [选型决策流程](#选型决策流程)
- [与 Claude Code Skill 设计的映射](#与-claude-code-skill-设计的映射)

---

## Decision Flowchart

Work through these questions in order. Stop at the first "yes".

1. **Does the skill have multiple independent sub-tasks that can run simultaneously?**
   → Yes: **Parallel (3)**

2. **Does the input type vary significantly, requiring different processing paths?**
   → Yes: **Router/Coordinator (2)**

3. **Does output quality require iterative refinement against objective criteria?**
   → Yes: **Evaluator-Optimizer (5/6)**

4. **Is the task complex and open-ended, where the plan adapts based on intermediate results?**
   → Yes: **Orchestrator (4)**

5. **Is human approval required at a critical decision point?**
   → Yes: **HITL (7)**

6. **Otherwise** → **Sequential (1)**

Real production systems are usually **Composite (8)** — nested combinations of the above.

---

## Pattern 1: Sequential Pipeline（顺序管道）

**别名：** The Assembly Line / Prompt Chaining

**核心概念：** 任务线性流动，Agent A 的输出成为 Agent B 的输入。

**适用场景：**
- 有明确检查点的工作流，每步在继续前需验证
- 顺序重要的线性推进
- 中间结果影响下一步

**实现要点：**
- 数据通过 `session.state` 的特定 `output_key` 传递
- 确保确定性和可调试性
- 将长 prompt 拆分为小的、元数据驱动的"技能"

**示例：** 文档处理（解析器 → 提取器 → 摘要器）、git-commit-helper、代码审查

### SKILL.md Structure Template

````markdown
## Workflow

Copy this checklist and check off as you go:
- [ ] Step 1: [First action]
- [ ] Step 2: [Second action — uses Step 1 output]
- [ ] Step 3: [Validation]
- [ ] Step 4: [Final output]

---

### Step 1: [Name]

[Instructions for step 1. What to do, what to check, what constitutes success.]

**Exit condition:** [What must be true before moving to Step 2]

### Step 2: [Name]

[Instructions for step 2. Reference Step 1 output explicitly.]

**Exit condition:** [What must be true before moving to Step 3]

### Step 3: [Validation]

[Validation instructions. If failed, return to Step N.]

### Step 4: [Final Output]

[Delivery instructions. Format, location, confirmation message.]
````

---

## Pattern 2: Coordinator/Dispatcher（协调/分发 - 路由）

**别名：** The Concierge / Router

**核心概念：** 中央"大脑"分析用户意图，将请求路由到专门的子 Agent。

**适用场景：**
- 输入类型差异大，需要不同处理路径
- 需要根据分类选择最佳专业 Agent
- 成本优化（简单查询路由到小模型，复杂查询路由到大模型）

**实现要点：**
- 不管理复杂多步计划（区别于 Orchestrator）
- 使用 `AgentTool` 进行委托
- 是动态规划的第一步

**示例：** 客服分流（计费 Agent vs 技术支持 Agent）

### SKILL.md Structure Template

````markdown
## Routing

Determine input type before proceeding:

| Input Type | Indicator | Handler |
|------------|-----------|---------|
| Type A | [how to identify] | See [references/handler-a.md](references/handler-a.md) |
| Type B | [how to identify] | See [references/handler-b.md](references/handler-b.md) |
| Type C | [how to identify] | See [references/handler-c.md](references/handler-c.md) |

## Classification

[Step-by-step instructions to determine input type. Be specific — ambiguous cases should have a default.]

**If uncertain:** [Default behavior or how to ask user for clarification]
````

---

## Pattern 3: Parallel Fan-Out/Gather（并行扇出/聚合）

**别名：** The Octopus

**核心概念：** 多个 Agent 同时执行独立任务以减少延迟，最终由"合成器"Agent 汇总结果。

**适用场景：**
- 多源研究（同时搜索网页 + 内部文档 + 查询SQL）
- 代码审查（同时运行安全、风格、性能检查）
- 任何可独立并行的子任务集

**实现要点：**
- 各 Agent 完全独立运行
- 最终需要一个聚合/合成步骤
- 显著减少总耗时（wall-clock time）

**示例：** 多维度代码审查、多源信息检索

### SKILL.md Structure Template

````markdown
## Workflow

Spawn these subagents simultaneously in a single message:

**Subagent A — [Role]:**
```
Task: [specific task A]
Input: [what to analyze]
Output: Save findings to [workspace]/analysis-a/result.md
```

**Subagent B — [Role]:**
```
Task: [specific task B]
Input: [what to analyze]
Output: Save findings to [workspace]/analysis-b/result.md
```

**Subagent C — [Role]:**
```
Task: [specific task C]
Input: [what to analyze]
Output: Save findings to [workspace]/analysis-c/result.md
```

Wait for all subagents to complete, then aggregate:

## Aggregation

Read all result files and synthesize:
1. [Synthesis instruction 1]
2. [Synthesis instruction 2]
3. Output final report as: [format]
````

---

## Pattern 4: Hierarchical Decomposition（层级分解 - 编排器）

**别名：** The Russian Doll / Orchestrator-Worker

**核心概念：** 高层级"管理者"Agent 将复杂目标分解为结构化任务列表，委派给工作者 Agent 队列。

**适用场景：**
- 复杂开放式任务，计划需根据中间结果调整
- 子任务相互依赖，可能需要重新规划
- 需要维护全局状态和监控子目标进度

**实现要点：**
- Manager 创建"Plan"对象存入 session state
- 子 Agent 完成任务后更新计划状态
- 区别于 Router：Manager 维护全局状态并协调多步执行

**示例：** 软件工程（架构 Agent → 编码 Agent → 测试 Agent）、旅行规划

### SKILL.md Structure Template

````markdown
## Orchestration Workflow

### Step 1: Analyze and Plan

Read the input thoroughly. Identify:
- What sub-tasks are needed?
- What order must they run in? (dependencies)
- Which agent from [agents/](agents/) handles each?

Create an execution plan before proceeding.

### Step 2: Execute Sub-tasks

For each planned sub-task:
1. Select the appropriate agent from [agents/](agents/)
2. Spawn it with specific context and a clear output format
3. Review its output before spawning the next agent
4. If output is insufficient, re-spawn with corrected instructions

### Step 3: Synthesize

Combine all sub-task outputs into the final deliverable:
[Synthesis instructions and output format]

## Available Agents

See [agents/](agents/) directory. Each agent file contains its trigger conditions and instructions.
````

---

## Pattern 5: Generator-Critic（生成-批评）

**别名：** The Editor's Desk / Reflection

**核心概念：** 一个 Agent 生成草稿，另一个"批评家"Agent 根据检查清单审查。

**适用场景：**
- 需要"第二双眼睛"的强制审查
- 输出有明确的合规/质量标准
- 简单的通过/失败判断或一步改进

**实现要点：**
- 组合两个 `LlmAgent` 在 `SequentialAgent` 中
- Critic 使用严格的系统指令（如"作为高级审计师"）
- 使用结构化输出（JSON）使批评可执行

**示例：** 品牌指南合规检查、安全审查

### SKILL.md Structure Template

````markdown
## Generation-Evaluation Loop

### Step 1: Generate

[Generation instructions. What to produce, what format, what constraints.]

Save output to: `[workspace]/output-iteration-[N].md`

### Step 2: Evaluate

Check output against each criterion:

| Criterion | Check | Pass |
|-----------|-------|------|
| [Criterion A] | [How to check] | [Pass condition] |
| [Criterion B] | [How to check] | [Pass condition] |
| [Criterion C] | [How to check] | [Pass condition] |

**If all pass** → proceed to Step 3.
**If any fail** → note specific failures, return to Step 1 with feedback. Maximum 3 iterations.

### Step 3: Deliver

[Delivery instructions. Format, location, confirmation.]
````

---

## Pattern 6: Iterative Refinement（迭代精化）

**别名：** The Sculptor / Evaluator-Optimizer

**核心概念：** 生成 → 批评 → 精化的持续循环，直到满足质量阈值或达到最大迭代次数。

**适用场景：**
- 输出质量需要客观标准的迭代优化
- 创意写作、代码生成等需要多轮打磨
- 有明确"足够好"标准的任务

**实现要点：**
- 使用 `LoopAgent` 原语
- 使用 `escalate=True` 信号提前中断循环
- 已证明在编码基准测试中提升 10%+ 准确率

**示例：** 代码质量优化、文档精化、Prompt 调优

### SKILL.md Structure Template

````markdown
## Generation-Evaluation Loop

### Step 1: Generate (Iteration N)

[Generation instructions. What to produce, what format, what constraints.]

Save output to: `[workspace]/output-iteration-[N].md`

Start at N=1. Increment N on each retry.

### Step 2: Score Against Rubric

Evaluate the generated output against each criterion below.
Assign PASS or FAIL to each. Record specific failure reasons.

| Criterion | Weight | Check Method | Pass Condition |
|-----------|--------|--------------|----------------|
| [Criterion A] | High | [How to check] | [Pass condition] |
| [Criterion B] | Medium | [How to check] | [Pass condition] |
| [Criterion C] | Low | [How to check] | [Pass condition] |

**Overall pass:** All High-weight criteria pass AND ≥ 50% of remaining criteria pass.

### Step 3: Loop or Exit

**If overall pass** → proceed to Step 4 (Deliver).
**If N < 3 and overall fail** → compile failure summary, return to Step 1 with:
  - Which criteria failed
  - Specific issues found
  - Suggested fix direction

**If N = 3 and still failing** → deliver best iteration, note unresolved issues in output.

### Step 4: Deliver

[Delivery instructions. Format, location, confirmation.]
Include iteration count and any known remaining issues.
````

---

## Pattern 7: Human-in-the-Loop（人机协作）

**别名：** The Safety Valve / HITL

**核心概念：** Agent 在关键节点暂停执行，等待人类批准或额外上下文。

**适用场景：**
- 高风险决策（资金转移、生产部署、数据删除）
- 需要人类纠正反馈的学习循环
- 企业级 AI 安全合规要求

**实现要点：**
- 调用 `ApprovalTool` 触发 webhook/UI 通知并暂停状态
- 人类不仅批准，还提供修正反馈
- Agent 使用反馈更新内部上下文或长期记忆

**示例：** 金融交易执行、代码部署到生产环境

### SKILL.md Structure Template

````markdown
## Workflow

### Phase 1: Preparation

Gather all information needed for the decision:
1. [What to collect/analyze]
2. [What to validate before presenting]
3. Summarize into a structured proposal:
   - **Action:** [What will be done]
   - **Scope:** [What will be affected]
   - **Risks:** [Known risks and mitigations]
   - **Reversibility:** [Can this be undone? How?]

### Phase 2: Present for Approval

Present the proposal to the user clearly. Include:
- The full proposal from Phase 1
- Explicit ask: "Do you approve? (yes/no/modify)"
- What happens on each answer

**STOP. Wait for explicit user response before proceeding.**

If user responds "modify" or provides corrections:
- Update the proposal accordingly
- Return to start of Phase 2 with revised proposal

If user responds "no":
- Acknowledge, summarize what was NOT done, exit.

### Phase 3: Execute

User has approved. Proceed with the approved action:
1. [Execution step 1]
2. [Execution step 2]
3. [Execution step 3]

If any step fails mid-execution:
- Stop immediately
- Report partial completion state
- Describe manual steps needed to complete or roll back

### Phase 4: Report

Confirm completion to the user:
- **Done:** [What was executed]
- **Result:** [Outcome / where to find output]
- **Next steps:** [Any follow-up actions required]
````

---

## Pattern 8: Composite（组合模式）

**别名：** The Mix-and-Match / Pattern Composition

**核心概念：** 嵌套组合多种模式构建复杂系统。现实世界的企业系统很少只用单一模式。

**适用场景：**
- 大规模复杂工作流
- 需要突破单一模式局限
- 避免"上下文窗口墙"（monolithic prompt 的限制）

**组合示例：**
- Coordinator → Parallel 搜索 → Iterative Refinement 循环
- Sequential 管道中嵌套 Parallel 工作流
- 每个子 Agent 本身可以是另一个 Composite

**关键原则：** 像微服务架构一样，每个组合单元处理自己的内存和内部逻辑，对外呈现单一接口。

### SKILL.md Structure Template

````markdown
## Workflow Overview

This skill composes multiple patterns. Each phase below is a self-contained pattern.

```
Phase 1: [Router/Sequential] → classify input and validate
Phase 2: [Parallel]          → fan-out independent analyses
Phase 3: [Orchestrator]      → plan and execute dependent tasks
Phase 4: [Evaluator-Loop]    → refine output to quality threshold
Phase 5: [HITL]              → human approval gate (if high-risk)
Phase 6: [Sequential]        → deliver and report
```

---

### Phase 1: [Name] — [Pattern Used]

[Phase instructions. Treat this phase as if it were a standalone skill of the stated pattern.
Reference the corresponding pattern template for structure guidance.]

**Output contract:** [What this phase produces and where it stores it for the next phase]

---

### Phase 2: [Name] — [Pattern Used]

[Phase instructions.]

**Input:** Output from Phase 1
**Output contract:** [What this phase produces]

---

### Phase 3: [Name] — [Pattern Used]

[Phase instructions.]

**Input:** Outputs from Phase 1 and Phase 2
**Output contract:** [What this phase produces]

---

### Phase N: [Name] — [Pattern Used]

[Continue for each phase.]

---

## Phase Handoff Rules

- Each phase writes its output to a defined location before the next phase starts.
- If a phase fails, report which phase failed and what partial outputs exist.
- Phases may be skipped only if their skip condition is explicitly stated here: [skip conditions]

## Composition Notes

[Explain WHY this particular combination of patterns was chosen.
What single pattern couldn't handle this alone? What tradeoffs does this composition introduce?]
````

---

## 选型决策流程

按顺序回答，第一个"是"即停止：

1. **任务是否有多个独立子任务可同时执行？** → Parallel (3)
2. **输入类型是否差异大，需要不同处理路径？** → Router (2)
3. **输出质量是否需要根据客观标准迭代优化？** → Evaluator-Optimizer (5/6)
4. **任务是否复杂开放，计划需根据中间结果调整？** → Orchestrator (4)
5. **是否需要人类在关键节点干预？** → HITL (7)
6. **否则** → Sequential (1)

实际生产系统通常是 **Composite (8)** — 多种模式的嵌套组合。

---

## 与 Claude Code Skill 设计的映射

| Pattern | Skill 设计中的典型应用 |
|---------|----------------------|
| Sequential | 大多数 Skill 的主工作流（Step 1 → Step 2 → Step 3） |
| Router | Step 0 的路径分支（CREATE vs MODIFY） |
| Parallel | 多维度并行分析（安全 + 性能 + 风格同时检查） |
| Orchestrator | 复杂需求分解后动态分配子任务 |
| Generator-Critic | 实现后的质量审查阶段 |
| Iterative Refinement | 质量不达标时的修复循环 |
| HITL | 用户确认门禁（Hard Gate） |
| Composite | 完整的 Skill Creator 工作流本身 |
