# Templates

Output format templates used by Skill Forge. This file owns template shapes only. The canonical L2/L3 state, transition, budget, recovery, and completion authority is review-state-protocol.md, especially the Authority, State Schema, Finding Schema, Review Observation, Fix Authorization, Recovery, and Completion and Squash anchors.

## Contents

- [Phase 1 Output](#phase-1-output)
- [Full Spec](#full-spec)
- [Delta Spec](#delta-spec)
- [Joint Implementation Approval](#joint-implementation-approval)
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

```markdown
## First Principles Statement

**根本问题：** [the essential problem this skill solves]
**最小必要能力：** [must-have capabilities after stripping nice-to-have]
**不可变约束：** [rules that cannot be violated regardless of design]
**触发场景：** [when a user needs this skill]
**明确非目标：** [what this change will not solve]
```

### MODIFY — Change First Principles

```markdown
## Change First Principles

**当前状态：** [current skill capability and pattern in one sentence]
**根本问题：** [root cause of the requested change]
**最小变更：** [minimum change scope]
**不可动约束：** [behaviors and boundaries to preserve]
**变更边界：** [explicitly out of scope]
```

---

## Full Spec

CREATE path:

```markdown
## Skill Spec: <name>

### 1. Identity
- Name:
- Description (trigger text):
- Should-trigger scenarios:
- Should-NOT-trigger scenarios:

### 2. Contract
- Inputs:
- Outputs:
- Side effects:
- Ownership paths:

### 3. Architecture
- Primary Pattern:
- Selection rationale:
- Secondary Patterns:
- Risk level: L0 | L1 | L2 | L3
- Why lower levels are insufficient:
- Workflow skeleton:
- Hard Gates:

### 4. Boundaries
- Will NOT do:
- Prerequisites:
- Known limitations:
- Upgrade triggers:

### 5. Validation
- Deterministic checks:
- Semantic review needs:
- Behavioral eval needs:
- Recovery/rollback expectations:

### 6. Success Criteria
- Trigger accuracy target:
- Key behavior assertions:
- Eval cases draft:
```

---

## Delta Spec

MODIFY path:

```markdown
## Delta Spec: <name>

### Changed
- [Section]: [from X → to Y]

### Added
- [what is new]

### Removed
- [what is dropped]

### Unchanged (explicit)
- [what stays the same]

### Risk and Review
- Risk level: L0 | L1 | L2 | L3
- Review policy: none | whole-diff | final-only | task-and-final
- Why lower levels are insufficient:
- Upgrade triggers:

### Non-goals
- [explicit exclusions]

### Validation
- Deterministic checks:
- Semantic review needs:
- Behavioral eval needs:
```

---

## Joint Implementation Approval

For L2/L3, present the confirmed Spec and YAML Plan together and ask for one implementation approval:

```markdown
## Implementation Contract Review

**Spec path:** `.skill-forge/<run>/spec.md`
**Plan path:** `.skill-forge/<run>/plan.yaml`
**Risk:** [run risk and per-Task risk summary]
**Review policy:** [final-only/task-and-final summary]

### Scope
- In scope:
- Out of scope:
- Exact ownership paths:

### Acceptance
- [criterion]

### Deterministic evidence before LLM review
- [command/check]

### Escalation conditions
- Scope expansion:
- Ownership ambiguity:
- Irreversible/outward-facing action:
- Unobservable validation:

Please review both files. If approved, say “继续/确认/可以” and implementation will begin. If anything should change, describe the change and the Plan will be rewritten before implementation.
```

---

## Plan Document Header

Phase 3 Plan files are YAML:

~~~yaml
goal: "一句话描述本次变更目标"
architecture: "2-3 句描述方法、风险自适应路径和验证策略"
global_constraints:
  - 'description: starts with "Use when", third person, ≤ 1024 chars'
  - 'Body (SKILL.md): < 500 lines'
  - 'Progressive disclosure: content > 100 lines → move to references/'
  - 'References: one level deep only'
  - 'Stable logic → scripts/'
  - 'Files > 100 lines → must include ## Contents with anchor links'
  - 'name format: ≤ 64 chars, only letters/numbers/hyphens'
  - 'Controller owns state/Gate/rubric; bounded agents must not modify them'
tasks:
  - id: 1
    name: "任务名称"
    files:
      create: []
      modify: []
      delete: []
    interfaces:
      consumes: ""
      produces: ""
    steps: []
    acceptance_criteria: []
    meta:
      model: sonnet
      file_type: markdown
      requires_execution_check: false
      risk_level: L2
      review_policy: final-only
~~~

---

## Task Format

Task nodes must match scripts/plan_contract.py. `files.create`, `files.modify`, and `files.delete` contain only exact repo-relative paths: no globs, no spaces, no absolute paths, no `..`, no inline descriptions.

~~~yaml
- id: N
  name: "任务名称"
  files:
    create:
      - "plugins/example-plugin/skills/example/SKILL.md"
    modify:
      - "plugins/example-plugin/skills/example/references/contract.md"
    delete: []
  interfaces:
    consumes: "本 Task 使用的来自之前 Task 或当前仓库接口的真实输入"
    produces: "后续 Task 依赖的产物或契约"
  steps:
    - "Step N.1: 具体动作，包含完整内容，不用 placeholder"
    - "Step N.2 (验证): 运行相关静态/样例检查并记录命令、exit code、输出摘要"
  acceptance_criteria:
    - "criterion 1"
    - "criterion 2"
  meta:
    model: sonnet
    file_type: markdown
    requires_execution_check: true
    risk_level: L2
    review_policy: final-only
~~~

Supported `meta` values:

- `model`: non-empty string chosen by the Controller, commonly `haiku`, `sonnet`, or `opus`.
- `file_type`: non-empty string, commonly `markdown`, `script`, or `mixed`.
- `requires_execution_check`: boolean.
- `risk_level`: `L2` or `L3`. Omitted legacy value normalizes to `L3`; new Plans should set it explicitly.
- `review_policy`: `final-only` or `task-and-final`. Omitted legacy value normalizes to `task-and-final`; L3 requires `task-and-final`; L2 `final-only` is rejected when Task text indicates routing/gate/authority/cross-task/interface/state/helper or nondeterministic risk.

Task writing rules:

- Steps are self-contained and contain enough detail for a bounded implementer.
- Acceptance criteria include pattern constraints, business intent, and verifiable success criteria.
- The final step is validation.
- Ownership entries are exact path strings only; put explanations in steps or acceptance criteria.
- Stable briefs are generated from the approved run Plan by scripts/plan-task-query.py and written to Controller-specified output paths inside the same run directory.

---

## Review Observation JSON

Reviewer, final reviewer, structural validation, and behavioral validation write one schema v1 JSON object with no Markdown wrapper. Full field semantics are canonical in review-state-protocol.md Review Observation and Finding Schema.

```json
{
  "schema_version": 1,
  "gate": "TASK_REVIEW",
  "verdict": "PASS",
  "task_id": 2,
  "base_sha": "1111111111111111111111111111111111111111",
  "head_sha": "2222222222222222222222222222222222222222",
  "rubric_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "attempt": 1,
  "findings": [],
  "cannot_verify": [],
  "controller_resolutions": []
}
```

PASS uses `verdict: "PASS"` with no actionable findings. FAIL must include actionable findings or an explicit cannot_verify/decision path that helper can HALT deterministically.

---

## Finding JSON

```json
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
    "command": "python3 check_toc.py --base 1111111111111111111111111111111111111111",
    "exit_code": 0,
    "output": "base evidence summary"
  },
  "head_evidence": {
    "command": "python3 check_toc.py --head 2222222222222222222222222222222222222222",
    "exit_code": 1,
    "output": "missing ## Contents"
  },
  "closure_test": {
    "expected": {
      "command": "python3 check_toc.py --head 2222222222222222222222222222222222222222",
      "exit_code": 0,
      "output": "all anchors valid"
    },
    "actual": null
  },
  "observations": [
    {
      "risk": "读者无法定位协议章节",
      "check": "检查二级标题与 Contents anchor"
    }
  ],
  "resolution": null
}
```

`contract_ref` and `rubric_ref` are mutually exclusive; keep exactly one non-empty. Final/validation findings start with `owner_task_id: null`; helper maps exact `required_fix_paths` to one owner or HALTs.

---

## Fix Report JSON

FIXED reports contain the complete helper-authorized finding set:

```json
{
  "status": "FIXED",
  "attempt": 1,
  "base_head_sha": "2222222222222222222222222222222222222222",
  "new_head_sha": "3333333333333333333333333333333333333333",
  "findings": [
    {
      "id": "T2-RULE-ANCHOR",
      "action": "增加 Contents 并修正 anchor",
      "changed_paths": [
        "plugins/dev-stack/skills/skill-forge/references/review-state-protocol.md"
      ],
      "closure_test": {
        "command": "python3 check_toc.py --head 3333333333333333333333333333333333333333",
        "exit_code": 0,
        "output": "all anchors valid"
      }
    }
  ]
}
```

Non-success reports are minimal and use one of `BLOCKED`, `NO_PROGRESS`, or `NEEDS_CONTEXT`:

```json
{
  "status": "BLOCKED"
}
```

---

## Controller Resolution JSON

```json
{
  "id": "CV-T2-001",
  "action": "ACCEPT",
  "reason": "Controller ran the cited command, exit 0, and verified the claim"
}
```

Resolution IDs must belong to the same observation's `cannot_verify` array and must not have been used in state before.

---

## Intermediate Artifacts

Run artifacts are flat under `.skill-forge/<skill-name>-<change-topic>/`:

| Artifact | Filename |
|---|---|
| Spec | `spec.md` |
| Plan | `plan.yaml` |
| State | `review-state.json` |
| Frozen rubric | `rubric-snapshot.md` |
| Stable task brief | `task<N>-brief.md` or `task<N>-brief.json` |
| Task implementation report | `task<N>-report.md` |
| Task observation | `task<N>-review-attempt<M>.json` |
| Fix report | `task<N>-fix-attempt<M>-report.json` |
| Final observation | `final-review-attempt<M>.json` |
| Validation observation | `validation-<gate>-attempt<M>.json` |
| Review package | `review-<base7>..<head7>-attempt<M>.diff` |
| Eval input | `eval-prompts.md` |

Artifact attempt numbers advance only after helper state advances. API/transport retry artifacts use `-retry<N>` filenames and do not advance schema attempt.

---

## Eval Prompts Template

Generate eval prompts before mandatory final review when behavioral validation may be needed, then Phase 5 uses explicit flags to run or SKIP dimensions.

```markdown
## Eval Prompts: <skill-name>

### 1. 行为验证（Trajectory）

| # | Owner Task | Prompt | Expected behavior | Run when |
|---|---|---|---|---|
| T1 | <task-id> | [模拟用户输入] | [expected route/gate/output] | user behavior, Routing, Gate, Pattern, or Architecture changed |

### 2. 边界验证（Adversarial）

| # | Owner Task | Prompt | Expected behavior | Run when |
|---|---|---|---|---|
| A1 | <task-id> | [模糊输入] | [clarify or refuse safely] | same as above |

### 3. 一致性与基线

- `run_consistency=true` only for Routing/Gate changes; each selected prompt gets at most one additional rerun.
- `run_baseline=true` only for Pattern/Architecture changes.
- False dimensions output SKIP and do not spawn eval.
```
