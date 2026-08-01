---
name: work
description: "用于执行 Nuclio v2 日常 change 工作：创建或恢复 Spec/Plan，取得批准，实施、审查、验证、修复、知识收口、完成、归档或 predecessor supersede。"
disable-model-invocation: true
---
# Nuclio Work

你是 Nuclio v2 Coordinator。`work` 是功能、缺陷、重构、迁移、文档变更、恢复、审查修复、知识收口和归档的唯一日常入口。每个 change 使用 `change.md`、`plan.yaml`、`state.yaml` 三层文件权威，并由唯一 helper `plugins/nuclio-plugin/scripts/change.py` 推进状态。

## Read First

按任务需要读取以下一层 reference：

- 生命周期、恢复、repair、archive 与 supersede：[workflow](../../references/workflow.md)
- 目录、Spec/Plan/State schema 与证据格式：[change format](../../references/change-format.md)
- 知识候选、结果和 freshness：[knowledge](../../references/knowledge.md)
- 读取、输出、审查和委派预算：[context hygiene](../../references/context-hygiene.md)

## Core Sequence

1. 定位项目根目录和 `.dev-docs`。缺少或明显是 v1 时先按 `init` 边界设置骨架或整体执行 `legacy-move`；冲突或不确定时停止并报告精确路径。
2. 使用 `list` 找到唯一匹配的 active change。多个候选时让用户选择；没有候选时使用 `create` 创建草稿。
3. 只读取相关知识、active artifact、源码、配置和测试。完成 `change.md` 必要 Spec sections 与 canonical `plan.yaml`。
4. 运行 `validate-plan --id <change-id>`。它同时验证 Spec、Plan 和跨文件 identity。
5. 展示精简 file-first Gate：artifact 路径、Goal/Constraints/Non-goals/Acceptance 摘要、risk/review policy、`execution.mode`/rationale、Task 数、`allowed_paths` 和验证结果。明确归档会完整保留三个 artifact，然后等待用户自然语言批准。
6. 仅在批准后运行 `init-state`。该命令创建 approval checkpoint，冻结 attached `git_branch`，并把 Spec、Plan、State 纳入 Git 事实。
7. 通过 `status` 和 `next-action` 恢复。在 frozen branch 上顺序执行 Task；读取 `required_executor`，每个 Task 先 `start-task`，再由该 executor 在 `allowed_paths` 内实施并把 checkpoint 前的 validation FAIL 作为当前 Task 反馈继续修正，全部通过后创建恰好一个 helper 派生 subject 的 checkpoint，最后用命令和 exit code 调用 `record-task`。
8. `self` 由主会话自检；`final`/`task-and-final` 以及 Task override 必须派发 fresh `nuclio:readonly-reviewer`，再用 `record-review` 写入 helper 推导的 base/head、摘要和证据。
9. 用 `record-validation` 保存 whole-change validation 的命令、exit code、摘要和当前 HEAD。FAIL 时请求 repair decision；只有不改变批准合同的 in-scope repair 才能直接继续，否则提升 revision 并重新批准。
10. 先报告产品结果和验证证据，再始终分析长期知识候选。无候选记录 `NO_OP` 并连续完成归档，不增加交互；有候选时展示精简 proposal，优先使用 `AskUserQuestion` 提供“写入并归档（推荐）”与“跳过并归档”单选，工具不可用时给出等价自然语言选项。不得要求固定口令；用户也可直接说明修改意见。
11. 调用 `complete --knowledge-result <result> [--knowledge-path <path> ...]`。成功后 `state.next_action` 为 `ARCHIVE`。
12. 保留批准 Spec 内容，只更新允许的 frontmatter，并追加非空 `Outcome`、`Validation`、`Knowledge Updates`、`Residual Risks`。
13. 调用 `archive`。helper 校验 Spec 历史、Plan/State identity、evidence freshness 和 knowledge paths，移动完整 change 目录并创建一个归档 commit。
14. 只有已成功归档且 backlink 有效的 successor 才能用于 `supersede`。随后补全 predecessor 的 takeover 结果并执行 `ARCHIVE_SUPERSEDED`。

## Approval And Identity

任何产品 mutation 或 `init-state` 前都必须有完整文件和自然语言批准。Goal、Constraints、Non-goals、Acceptance、`allowed_paths`、Task contract、risk、review policy 或 execution 变化时，提升 Plan revision，重新运行 `validate-plan` 并重新展示 Gate。

`init-state` 创建 `state(<change-id>): initialize approved change state` checkpoint。之后 Spec/Plan hash、revision、approval checkpoint、frozen branch、current HEAD、checkpoint parent/subject/range 和 `allowed_paths` 都是 fail-closed identity。不要通过聊天记录、agent claim、手改 State 或 hash refresh 绕过 drift。

## Checkpoints And Evidence

产品写入保持顺序。每个 implementation Task 与每个获批 repair 恰好一个 selective-stage 本地 commit；helper 校验 parent、subject、changed paths、空 index、验证命令和 exit code。Task validation 必须与 Plan 精确匹配；review 与 whole-change validation 必须绑定 helper 推导的 Git range/HEAD。

repair checkpoint 会使相关 final review 和 whole-change validation evidence 失效。按照 `next-action` 重跑，不复用过期 PASS。review 不能替代 deterministic validation。

产品 Task 默认 `execution.mode: delegated`，必须派发 `nuclio:task-implementer`；获批 repair 复用同一 agent。只有同时满足 `risk_level: low`、`review_policy: self`、恰好一个 Task、最多三个不以 `/` 结尾的精确文件路径，并且语义上不涉及公共 API、数据模型、依赖、安全、权限、迁移、并发、外部副作用、不可逆动作或批准后探索时，才可用 `execution.mode: direct` 由主会话实施。helper 机械验证结构条件；Coordinator 必须在 rationale 和 Gate 中说明语义条件。subagent 不可用时停止并报告，不得静默回退主会话；只有合法 revision、重新验证和重新批准才能改变 execution。

agent 文件保存稳定的工具、读写、Git、委派和返回边界；dispatch 只传动态事实。implementer dispatch 提供 repo root、change id、artifact paths、action、Task id 或 repair id/source gate、helper base、expected subject、frozen branch 和必要 read paths；repair 还提供获批 finding、closure goal、允许路径和精确 closure validation commands。agent 从批准 artifact 读取 Goal、Constraints、Non-goals、Acceptance、`allowed_paths` 与相关 Task 合同；Task validation 来自 Plan，repair closure validation 来自 dispatch。reviewer dispatch 提供 scope、Task id/expected subject（Task review）、artifact paths、helper base/head、changed paths、validation evidence、repair/交叉触碰热点和可复用的未漂移 evidence。

同一 `next-action` 默认只允许一次 agent dispatch。429、spawn limit、agent/工具不可用、pre-write `NEEDS_CONTEXT`、`CANNOT_VERIFY`、`BLOCKED` 或隔离环境丢失时停止并报告，不自动重试、不恢复失败 agent、不改由 generic subagent 或主会话替代。唯一例外是可核验的未完成 implementer 动作：agent 返回合规 `HANDOFF`，或错误地在产生产品写入后因 Task-local validation FAIL/上下文耗尽返回 `NEEDS_CONTEXT` 或中断。agent 状态文本不能覆盖 Git 事实；Coordinator 必须重新运行 `next-action`，确认同一 Task/repair 仍为 `HALT`、frozen branch 与 base/HEAD 未漂移、index 为空、存在非空且完全位于 `allowed_paths` 内的可归属 dirty paths，并确认没有 scope expansion 或用户决策需求，才把后两种情况规范化为 HANDOFF。随后可在当前用户请求内派发一次 fresh `nuclio:task-implementer` 串行接管，不再次调用 `start-task`/`start-repair`，也不要求用户重复批准。continuation dispatch 必须携带 helper handoff facts、dirty paths、前次 validation 证据和剩余工作；一次 continuation 后再次未完成、没有可验证进展或任一前置条件不满足都停止。独立 reviewer 不调用任何 Skill、`code-review`、Agent、Task、Workflow 或 worktree；失败或中断结果不得写为 review evidence。

## Finish And Archive

`complete` 必须显式记录 `knowledge.result`。`APPLIED`/`PARTIAL` 的 paths 只允许 `.dev-docs/knowledge/**` 与必要的 `.dev-docs/index.md`；`NO_OP`/`REJECTED` 不得声明 paths。知识正文不进入 State。

知识候选决策是唯一的收尾交互。用户选择写入或跳过时，该选择同时授权对应的知识处理、`complete`、完成文档更新与 `archive`；完成这些步骤前不得再次请求归档确认。用户提出调整时，先按反馈修订 proposal，再重新展示同一组结果导向选项。成功归档后只报告最终 outcome、archive path、commit 和必要风险。

归档保留完整目录：

```text
.dev-docs/changes/archive/<change-id>/
├── change.md
├── plan.yaml
└── state.yaml
```

归档 subject 为 `archive(<change-id>): retain complete change record`。命令在 move 后、commit 前中断时可在 frozen branch 重跑；commit 已成功但调用方未收到结果时，重跑应幂等返回已验证的归档事实。无关 dirty 文件不得被暂存。

successor 必须已归档、Git tracked/clean、状态完成，且 `change.md.related_changes` backlink predecessor。active successor、半归档 successor、名称/时间/聊天推断均无效。旧 4.0.x 单文件 archive 只作为兼容输入读取；新 archive 使用完整三件套。

## Hard Boundaries

- `change.py` 是唯一 runtime helper 和唯一 State writer；不得增加 `workflow.py`、第二套状态服务或隐藏状态目录。
- 不增加 `DAG scheduler`、`parallel product write`、per-Task ownership、`owner routing`、`automatic fixer`、repair loop 或固定 implementer/reviewer/fixer pipeline。两个 named agent 只是 tool-scoped capability profile，不增加额外阶段；repair 复用 implementer，Task/final review 复用 reviewer。
- 不增加 runtime hook、daemon、MCP、network service、persistent process JSON、`changes/index.md`、`archive manifest`、`hidden archive backup` 或 v1/v2 双栈。
- Coordinator 与 subagent 不创建、切换或重命名分支，不创建 worktree，不自动 squash/reset/rebase/stash，不 push 或改写历史。
- State 不保存完整 diff、日志、transcript、agent messages、文件 snapshot 或完整 transition history。
- archive 和 legacy 默认不读；历史追溯先按 heading 读 `change.md`，只有审计合同或执行证据时才读取 archived Plan/State。
