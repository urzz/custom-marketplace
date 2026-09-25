# Skill Forge 模板

只使用当前任务需要的模板。方括号内容必须在写入正式产物时替换，不得把 placeholder 留在已确认 Spec 或 Plan 中。

## Contents

- [Spec](#spec)
- [Plan](#plan)
- [影响标记](#影响标记)
- [轻量 State](#轻量-state)
- [Subagent 返回](#subagent-返回)
- [最终报告](#最终报告)

## Spec

```markdown
# Spec: [Skill 名称与变更主题]

## 目标

[完成后用户能够获得什么]

## 第一性原理

### 根本问题

[真正需要解决的问题]

### 最小必要能力

[去除可选功能后的最小能力]

### 不可变约束

[必须保持的行为和边界]

### 关键假设

[仍依赖但已向用户说明的假设]

## 目标平台

[Claude Code、Codex、DeepSeek Harness 或多平台；说明与当前执行宿主的关系，以及显式/自动调用策略]

## 当前问题

[当前行为、根因和证据]

## 预期行为

- [可观察行为或工作流变化]

## Should Trigger

- [应触发 Skill 的真实用户请求]

## Should Not Trigger

- [相邻但不应触发的真实用户请求]

## 非目标

- [明确不处理的范围]

## 验收标准

- [可验证的完成条件]

## 验证场景

- [确定性检查]
- [仅在行为变化时列出 fresh-session cases]

## 特殊约束

- [仅在适用时记录权限、外部副作用、依赖、不可逆操作或发布要求；否则写“无”]
```

## Plan

`spec_sha256` 使用 `plan_contract.py hash-spec` 的原样输出。每个 `files` 条目必须是无 glob、无注释的精确 repo-relative 文件路径。

```yaml
schema_version: 1
spec: spec.md
spec_sha256: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

impacts:
  trigger_or_behavior_changed: false
  script_changed: false
  agent_permissions_changed: false
  external_side_effects_changed: false

tasks:
  - id: 1
    name: 更新触发与核心工作流
    files:
      create: []
      modify:
        - plugins/example/skills/example/SKILL.md
      delete: []
    steps:
      - 调整 description 的正向与负向触发边界
      - 更新核心工作流并保持 supporting files 可发现
    acceptance:
      - Should Trigger 请求进入目标流程
      - Should Not Trigger 请求不会误触发
    checks:
      - claude plugin validate plugins/example --strict
```

Plan 不得包含：

- `model`、`file_type`、`requires_execution_check`；
- `risk_level`、`review_policy` 或风险关键词分类；
- 通用 rubric 或重复仓库规则；
- Task brief/report、review observation、finding ledger 或修复预算；
- commit、squash 或历史改写步骤；
- Gate 或 State transition。

## 影响标记

| 标记 | 设为 `true` 的条件 | 额外验证 |
|---|---|---|
| `trigger_or_behavior_changed` | description、routing、确认点、核心步骤或用户可观察输出变化 | 3-5 个 fresh-session cases |
| `script_changed` | 新增、删除或修改 bundled script 行为 | 单元测试、`--help` 和真实 CLI 示例 |
| `agent_permissions_changed` | agent tools、写入边界或 delegation 合同变化 | 静态权限检查与独立 reviewer |
| `external_side_effects_changed` | 新增或改变网络、发布、生产、消息或不可逆动作 | 用户明确确认、受控验证与独立 reviewer |

影响标记只决定验证强度，不决定另一套工作流。不能通过修改 Task 文案规避真实影响。

## 轻量 State

只有跨会话的多 Task 工作确实需要恢复时才创建 `state.json`：

```json
{
  "schema_version": 1,
  "current_task_id": 2,
  "completed_task_ids": [1],
  "base_sha": "<sha-or-null>",
  "head_sha": "<sha-or-null>",
  "last_result": "Task 1 checks passed"
}
```

不要添加完整 diff、finding、日志、agent transcript、测试输出或 transition history。恢复时从 Spec、Plan、Git status/diff 和实际文件重建上下文。

## Subagent 返回

```text
status: DONE | BLOCKED | NEEDS_CONTEXT
changed: <paths or none>
checks: <command + PASS/FAIL summary>
concerns: <remaining concern or none>
```

总计不超过 15 行。不写中间 report 文件，不声称整个 Plan、最终审查或行为评测已经通过。

## 最终报告

```markdown
完成：[一句话结果]

- 修改：[关键路径与行为]
- 确定性检查：[命令与结果]
- 行为评测：[PASS/FAIL/SKIP 及原因]
- 独立审查：[PASS/发现摘要/SKIP 及原因]
- 剩余风险：[无或具体风险]
```
