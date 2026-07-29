# Nuclio v2 Knowledge

长期知识只保存跨 change 仍有价值、经验证且有明确归属的事实。它不是执行日志、State 镜像或完成 change 的必然副产品。

## Timing

知识处理发生在产品实施、必要 review 和 whole-change validation 完成之后：

1. 先向用户报告产品结果、changed paths、命令、exit codes 与关键摘要。
2. 始终执行候选分析，即使看起来没有候选。
3. 无合格候选时记录 `NO_OP`，不增加第二 Gate。
4. 有合格候选时展示精简 proposal，等待用户自然语言确认。
5. 根据实际写入结果调用 `complete --knowledge-result ...`。

知识候选被拒绝不改变已验证的产品结果，也不阻止 complete/archive。

## Five Questions

候选必须同时回答“是”：

1. **稳定**：不是临时实现细节、一次性状态或尚未确定的推测。
2. **可复用**：未来 change、维护者或决策会真实受益。
3. **非显然**：不能只靠当前代码名、类型或常规命令轻易推导。
4. **已验证**：有代码、测试、配置、CI、Git 或用户决策证据。
5. **可归属**：有唯一、明确且语义匹配的长期知识位置。

任一问题为否时，不写长期知识。把“这次改了什么”留在 change 的 `Outcome`/`Validation`，不要提升为项目知识。

## Canonical Targets

默认知识入口：

- `.dev-docs/knowledge/project.md`：产品目标、用户、术语、跨领域规则。
- `.dev-docs/knowledge/architecture.md`：系统边界、架构约束、稳定关系、重要决策。
- `.dev-docs/knowledge/engineering.md`：构建、测试、发布、协作和代码实践。
- `.dev-docs/knowledge/<topic>.md`：确有独立、长期主题时使用。
- `.dev-docs/index.md`：只做必要导航，不承载知识正文。

每个语义结论只有一个 authority。已有位置可容纳时不要创建重复文件或镜像段落。

## Candidate Proposal

用户可见 proposal 只包含：

- 可复用的语义结论；
- 恰好一个目标文件或 heading；
- 建议 operation；
- 与现有知识的冲突状态；
- 影响范围；
- 支持证据摘要。

不要展示完整 diff、长命令输出、内部评分、agent transcript 或 State dump。用户可接受全部、接受部分、修改或拒绝。

## Operations

常规维护 operation：

- `NO_OP`：没有合格候选。
- `MERGE`：把新证据合并到同一语义 authority。
- `REFINE`：使已有结论更准确或边界更清楚。
- `REPLACE`：新事实完整替换旧事实。
- `SCOPE_SPLIT`：一个旧结论实际覆盖多个边界，需要拆分。
- `NEW_ADR`：需要保留重要架构选择、理由与后果。
- `SUPERSEDE_ADR`：新决策替代旧 ADR，但保留历史关系。
- `DEPRECATE`：内容仍有历史价值但不应作为当前指导。
- `DELETE`：内容已错误且没有保留价值；必须有强证据和明确用户确认。
- `HALT`：冲突、归属或证据无法确定，停止知识写入。

operation 只指导正文维护；State 的 finish result 使用下节四个固定枚举。

## Finish Result

`complete` 强制写入紧凑 `knowledge.result`：

| Result | 含义 | paths |
|---|---|---|
| `NO_OP` | 没有合格候选 | 必须为空 |
| `APPLIED` | 用户确认的知识全部实际写入 | 必须非空 |
| `PARTIAL` | 只写入一部分，或按用户修改后写入 | 必须非空 |
| `REJECTED` | 有候选但用户拒绝写入 | 必须为空 |

允许路径仅为 `.dev-docs/knowledge/**` 和必要的 `.dev-docs/index.md`。声明路径必须去重、存在、repo-relative，并精确对应实际 working-tree change。知识正文、proposal 与拒绝理由不进入 State；这些语义在 `change.md` 的 `Knowledge Updates` 中做短摘要。

archive 会把 `APPLIED`/`PARTIAL` 的精确 paths 与完整 change 目录一起 selective stage 到同一个归档 commit，从而让结果、证据与实际知识写入共享 Git 事实。

## Conflict Handling

写入前比较目标位置：

- 语义一致但证据更强：`MERGE` 或 `REFINE`。
- 新事实改变当前结论：`REPLACE` 或 `SUPERSEDE_ADR`，明确旧结论为什么不再适用。
- 作用域不同：先 `SCOPE_SPLIT`，避免互相覆盖。
- 无法确认谁正确：`HALT` 或标记 `review-needed`，不静默覆盖。

不要因为新 change 更近、agent 更自信或测试数量更多就自动覆盖长期知识。关键冲突需要用户决定。

## Freshness

确有生命周期管理价值的知识文件或条目可使用可选 metadata：

```yaml
status: current
sources:
  - .dev-docs/changes/archive/example-change/change.md
related_paths:
  - src/example/
last_reviewed: 2026-07-29
```

`status` 可为 `current|deprecated|historical|review-needed`。这是指导约定，不是 helper 强制 schema，也不触发全仓扫描。

当前 change 的 knowledge analysis 在以下情况应重新审查相关知识：

- `related_paths` 被删除、重命名或发生实质行为变化；
- public API、数据模型、架构边界、权限或发布方式改变；
- 新验证证据与已有结论冲突；
- ADR 的前提或结论被新决策替代；
- 用户明确指出文档可能过期。

无法确认时标记 `review-needed`，不要自动删除。

## Evidence And Attribution

合格证据可以来自已提交代码、测试、配置、CI、Git checkpoint、经确认的用户决策或已验证的外部合同。归档追溯优先引用完整 archive 中的 `change.md`；需要批准范围时再读 `plan.yaml`，需要执行证据时再读 `state.yaml`。

不要把以下内容写入长期知识：完整日志、完整 diff、Plan/State 副本、一次性 task 状态、agent prompt/return、聊天 transcript、未验证猜测或仅对当前 change 有意义的结果列表。

## Residual Risk

知识正文不能替代 completion document 的 `Residual Risks`。已知风险属于 change 结果，必须在 `change.md` 明确记录；只有风险本身是稳定、可复用且经过确认的项目约束时，才另行进入长期知识。
