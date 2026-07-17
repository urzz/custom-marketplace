# Templates

Output format templates referenced by SKILL.md. Each section is an anchor target.

## Contents
- [Phase 1 Output](#phase-1-output)
- [Full Spec](#full-spec)
- [Delta Spec](#delta-spec)
- [Plan Document Header](#plan-document-header)
- [Task Format](#task-format)
- [Review Observation JSON](#review-observation-json)
- [Finding JSON](#finding-json)
- [Fix Report JSON](#fix-report-json)
- [Controller Resolution JSON](#controller-resolution-json)
- [Intermediate Artifacts](#intermediate-artifacts)
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

## Plan Document Header

Phase 3 — 每个 Plan 文件必须为 YAML 格式，以此结构开头：

~~~yaml
goal: "一句话描述本次变更目标"
architecture: "2-3 句描述方法"
global_constraints:
  - 'description: starts with "Use when", third person, ≤ 1024 chars'
  - 'Body (SKILL.md): < 500 lines'
  - 'Progressive disclosure: content > 100 lines → 移入 references/'
  - 'References: one level deep only'
  - 'Stable logic → scripts/'
  - 'Files > 100 lines → must include ## Contents with anchor links'
  - 'name format: ≤ 64 chars, only letters/numbers/hyphens'
  - '禁止 git 操作：implementer 仅可执行本 Task 范围内单次 commit，禁止 push/rebase'
  # + Spec 中其他项目特定约束，逐字复制
tasks:
  - id: 1
    name: "任务名称"
    ...
~~~

---

## Task Format

Phase 3 — 每个 Plan 中的 Task 使用以下 YAML 结构：

~~~yaml
- id: N
  name: "任务名称"
  files:
    create: ["exact/path/to/file.md"]
    modify: ["exact/path/to/existing.md (说明改动章节)"]
    delete: []
  interfaces:
    consumes: "本 Task 使用的来自之前 Task 的产物"
    produces: "后续 Task 依赖的产物"
  steps:
    - "Step N.1: 具体动作，包含完整内容，不用 placeholder"
    - "Step N.2 (验证): 验证条件"
  acceptance_criteria:
    - "criterion 1"
    - "criterion 2"
  meta:
    model: haiku   # haiku | sonnet | opus
    file_type: markdown # markdown | script | mixed
    requires_execution_check: false  # true 时 implementer 必须跑样例并贴输出
~~~

**格式规则：**
- Steps 必须自包含（不引用外部文件，不用 placeholder 如 "implement later" / "similar to Task N"）
- 重复代码也要完整写出（sub agent 可能不按顺序读 Task）
- 最后一步必须是验证步骤（implementer 自检）
- Acceptance Criteria 写明通过标准，供 reviewer 做 compliance check
- Acceptance Criteria 必须包含三类信息（Phase 3 输出时直接写入，不需要 implementer 去查外部文件）：
  1. **Pattern 结构约束**（来自 Spec Section 3 Architecture — 该 Task 涉及的架构模式、文件结构、命名规范）
  2. **业务意图**（来自 Spec Section 1 First Principles — 该 Task 解决什么问题、不可削减的核心是什么）
  3. **验收标准**（来自 Spec Section 5 Success Criteria — 与该 Task 相关的具体可验证条件）
- Plan 是 self-contained 的执行文档 — Acceptance Criteria 必须包含 subagent 判断完成所需的全部信息，禁止引用外部 Spec 文件
- YAML 结构节点（非 Markdown 标题分节）定义每个 Task 的字段边界，`meta` 节点的三字段为强制数据，供 `scripts/plan-task-query.py` 结构化提取

**CREATE 拆分参考：**
- Task 1: 创建 SKILL.md 骨架（frontmatter + workflow overview + step 标题）
- Task 2: 填充各 Step 详细指令
- Task 3: 创建 references/ 文件（如需要）
- Task 4: 创建 agents/ 文件（如需要）

**MODIFY 拆分参考：**
- 按 Delta Spec 的 Changed/Added/Removed 逐项拆分
- 相关联的变更合并为一个 Task

---

## Review Observation JSON

Reviewer、final reviewer 与 Phase 5 validation 都输出单个 schema v1 JSON object，
无 Markdown 前后文。示例中的 SHA 为 40 位，实际值必须与 state 精确一致：

```json
{
  "schema_version": 1,
  "gate": "TASK_REVIEW",
  "verdict": "FAIL",
  "task_id": 2,
  "base_sha": "1111111111111111111111111111111111111111",
  "head_sha": "2222222222222222222222222222222222222222",
  "rubric_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "attempt": 1,
  "findings": [
    {
      "id": "T2-RULE-ANCHOR",
      "owner_task_id": 2,
      "source_gate": "TASK_REVIEW",
      "attempt": 1,
      "rule_id": "large-file-toc",
      "contract_ref": "Task 2 acceptance: all large Markdown has Contents",
      "failure_key": "missing-contents-anchor",
      "severity": "IMPORTANT",
      "blocking": true,
      "origin": "NEW",
      "status": "OPEN",
      "summary": "新增协议超过 100 行但缺少 Contents 锚点",
      "path": "plugins/dev-stack/skills/skill-forge/references/review-state-protocol.md",
      "required_fix_paths": [
        "plugins/dev-stack/skills/skill-forge/references/review-state-protocol.md"
      ],
      "base_evidence": {
        "command": "git cat-file -e 1111111111111111111111111111111111111111:plugins/dev-stack/skills/skill-forge/references/review-state-protocol.md",
        "exit_code": 128,
        "output": "path does not exist in base"
      },
      "head_evidence": {
        "command": "python3 check_toc.py",
        "exit_code": 1,
        "output": "missing ## Contents"
      },
      "closure_test": {
        "expected": {
          "command": "python3 check_toc.py",
          "exit_code": 0,
          "output": "all anchors valid"
        },
        "actual": null
      },
      "observations": [
        {
          "risk": "读者无法从目录定位协议章节",
          "check": "检查所有二级标题都有 Contents 锚点"
        }
      ],
      "resolution": null
    }
  ],
  "cannot_verify": [],
  "controller_resolutions": []
}
```

Final/validation observation 的 `task_id` 和 finding 初始 `owner_task_id` 使用 `null`；
helper 根据 `required_fix_paths` 求唯一 owner。PASS 使用空 actionable findings；
`cannot_verify` 必须在 import 前由 Controller resolution、完整 finding 或 HALT 处理。

## Finding JSON

独立 finding 模板如下。`contract_ref` 与 `rubric_ref` 恰好保留一个；本示例用 rubric：

```json
{
  "id": "FINAL-TOOLS-001",
  "owner_task_id": null,
  "source_gate": "FINAL_REVIEW",
  "attempt": 1,
  "rule_id": "reviewer-read-only-tools",
  "rubric_ref": "Frozen rubric: reviewer tool boundary",
  "failure_key": "reviewer-has-write-tool",
  "severity": "CRITICAL",
  "blocking": true,
  "origin": "NEW",
  "status": "OPEN",
  "summary": "Task reviewer frontmatter 包含 Write",
  "path": "plugins/dev-stack/agents/skill-file-reviewer.md",
  "required_fix_paths": [
    "plugins/dev-stack/agents/skill-file-reviewer.md"
  ],
  "base_evidence": {
    "command": "git cat-file -e 1111111111111111111111111111111111111111:plugins/dev-stack/agents/skill-file-reviewer.md",
    "exit_code": 128,
    "output": "path does not exist in base"
  },
  "head_evidence": {
    "command": "python3 check_agent_tools.py",
    "exit_code": 1,
    "output": "unexpected tool: Write"
  },
  "closure_test": {
    "expected": {
      "command": "python3 check_agent_tools.py",
      "exit_code": 0,
      "output": "reviewer tools are read-only"
    },
    "actual": null
  },
  "observations": [
    {
      "risk": "Reviewer 可修改被审对象，破坏 Generator-Critic 独立性",
      "check": "解析 frontmatter tools 的精确集合"
    }
  ],
  "resolution": null
}
```

RESOLVED 复审必须保持 canonical `id`，将 `status` 改为 `RESOLVED`，并把实际执行的
`{command,exit_code,output}` 写入 `closure_test.actual`。Agent 不提供 fingerprint；helper 重算。

## Fix Report JSON

Fixer 只能报告 helper 已授权的完整 finding 集。FIXED 示例：

```json
{
  "status": "FIXED",
  "attempt": 1,
  "base_head_sha": "2222222222222222222222222222222222222222",
  "new_head_sha": "3333333333333333333333333333333333333333",
  "findings": [
    {
      "id": "T2-RULE-ANCHOR",
      "action": "增加 Contents 并修正所有 anchor",
      "changed_paths": [
        "plugins/dev-stack/skills/skill-forge/references/review-state-protocol.md"
      ],
      "closure_test": {
        "command": "python3 check_toc.py",
        "exit_code": 0,
        "output": "all anchors valid"
      }
    }
  ]
}
```

`status` 只允许 `FIXED`、`BLOCKED`、`NO_PROGRESS`、`NEEDS_CONTEXT`。只有 FIXED
使用上面的 attempt/head/findings 合同；后三者的 helper 合同只含具体 status，例如：

```json
{
  "status": "BLOCKED"
}
```

Agent 的自然语言解释属于 claim，不是自由 `additional` 协议字段，不能替代 state transition。

## Controller Resolution JSON

`cannot_verify` item 使用稳定 ID；Controller 只有取得独立 evidence 后才能在 observation
的 `controller_resolutions` 中加入：

```json
{
  "id": "CV-T2-001",
  "action": "ACCEPT",
  "reason": "Controller 运行 python3 -m json.tool，exit 0，确认该 JSON 合法"
}
```

Resolution 必须含非空 `id/action/reason`，ID 必须属于同一 observation 的
`cannot_verify` 且未在 state 中使用。若不能 resolution，Controller 要求 reviewer 转成
完整 finding，或保留该项让 helper 确定性 `HALTED_NEEDS_DECISION`；不得静默删除。

## Intermediate Artifacts

同一 run 的中间产物全部平铺在 `.skill-forge/<skill-name>-<change-topic>/`：

| Artifact | Filename |
|---|---|
| State | `review-state.json` |
| Frozen rubric | `rubric-snapshot.md` |
| Stable task briefs | `task<N>-brief.md`, `task<N>-brief.json` |
| Task implementation report | `task<N>-report.md` |
| Task observation | `task<N>-review-attempt<M>.json` |
| Fix report | `task<N>-fix-attempt<M>-report.json` |
| Final observation | `final-review-attempt<M>.json` |
| Validation observation | `validation-<gate>-attempt<M>.json` |
| Review package | `review-<base7>..<head7>-attempt<M>.diff` |
| Eval input | `eval-prompts.md` |

Attempt artifact 不覆盖。只有 helper 推进后的新 review/fix attempt 才增加 `<M>`；无合法
handoff 的 API/transport retry 保持相同 schema `attempt` 与 `<M>`，仅将原始 artifact 另存为
带 `-retry<N>` 的新文件且不得覆盖旧文件。不得创建 artifact 子目录。

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
