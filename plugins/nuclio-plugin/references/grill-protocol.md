# Nucl.io Grill Protocol

## Contents
- [Purpose](#purpose)
- [Core Rules](#core-rules)
- [Modes](#modes)
- [Question Format](#question-format)
- [Stop Conditions](#stop-conditions)
- [Artifact Rule](#artifact-rule)

## Purpose

Grill 是 Nucl.io 内置的 clarification protocol。它借用了先询问再处理 ambiguity 的交互策略，但 Nucl.io 不依赖 `grill-me`。

## Core Rules

1. 一次只问一个问题。
2. 询问当前 stage 最阻塞的问题。
3. 不要询问可以从 `.dev-docs/` 或 codebase 推断出的内容。
4. 每个问题都必须包含 recommended answer。
5. 用户可以直接接受 recommendation。
6. 默认每个 stage 最多询问 5 个问题。
7. 如果 5 个问题后仍不清楚，创建带有 explicit open questions 的 provisional artifact。
8. 每个 confirmed answer 都必须写入当前 change artifact。
9. 优化目标是获得足够继续推进的 clarity，而不是追求 perfect certainty。

## Modes

| Mode | Stage | Focus |
|---|---|---|
| `grill-idea` | Project Init / Brief | goal, users, boundary, success criteria |
| `grill-design` | Design | architecture choices, risks, data flow, alternatives |
| `grill-plan` | Before Implement | task slices, validation commands, rollback strategy |

## Question Format

使用以下格式：

```markdown
**问题 N：** <single blocking question>

推荐答案：<one concrete recommended answer>

为什么问：<one sentence explaining how the answer changes the artifact>
```

## Stop Conditions

任一条件满足时停止提问：

- artifact 可以在明确 assumptions 下起草。
- 当前 stage 已经询问 5 个问题。
- 用户确认 recommended answer，且没有新的 blocker。
- 下一个问题只会优化措辞，而不会改变 scope、architecture 或 acceptance。

## Artifact Rule

Confirmed answers 必须根据当前 stage 写入 `brief.md`、`spec.md`、`design.md`、`plan.yaml` 或 `state.json`。
