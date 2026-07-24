# Nuclio v2 Context Hygiene

Nuclio v2 用路径、heading、helper JSON 摘要和短证据保持上下文可控。默认只读完成当前 change 所需的材料，不把 `.dev-docs`、Git 历史、agent 返回或测试日志当成必须全文加载的数据库。

## Contents

- [读取顺序](#读取顺序)
- [默认禁止全文读取](#默认禁止全文读取)
- [按需读取](#按需读取)
- [终端输出预算](#终端输出预算)
- [Subagent prompt 预算](#subagent-prompt-预算)
- [Subagent return 预算](#subagent-return-预算)
- [100k 警戒线](#100k-警戒线)
- [status 与 next-action 恢复](#status-与-next-action-恢复)
- [非 Gate 声明](#非-gate-声明)

## 读取顺序

推荐读取顺序：

1. `.dev-docs/index.md` 根索引。
2. 匹配领域的知识文件或 heading。
3. 相关全局知识章节：`project.md`、`architecture.md`、`engineering.md`。
4. 必要 ADR。
5. 当前 active `change.md` 的 Goal、Constraints、Non-goals、Acceptance、Decisions、Outcome 等相关 heading。
6. 当前 `plan.yaml` 的 revision、risk/review/repair policy、`allowed_paths`、当前 Task、validation 与 `checkpoint_subject`。
7. 当前 `state.yaml` 只通过 `change.py status` 和 `change.py next-action` 读取；需要排障时才查看指定字段。
8. 相关源码、配置、测试和 CI 文件。
9. 仅在历史必要时读取 archive 中的精简 `change.md`。
10. 仅在用户明确要求时读取 legacy。

顺序不是强制命令脚本；它用于避免先吞入大量历史资料。若 helper JSON 已能回答当前恢复问题，不要再全文读取 `state.yaml`。

## 默认禁止全文读取

默认不要全文读取：

- 整个 `.dev-docs`。
- 所有 active `change.md`、`plan.yaml` 或 `state.yaml`。
- 完整 `state.yaml`，除非 helper JSON 不足以诊断。
- 所有 `knowledge/domains/**`。
- 所有 ADR。
- 所有 runbook。
- `.dev-docs/changes/archive/**`。
- `.dev-docs/legacy/**`。
- 全仓库源码。
- 完整 Git diff、完整 commit history 或所有 checkpoint diffs。
- 所有测试输出、CI 日志、agent 消息或聊天 transcript。

需要历史、长 diff 或日志时，先定位具体路径、commit range、heading 或失败片段，再读取必要片段。

## 按需读取

读取前先说明要回答的问题：目标、约束、接口、`allowed_paths`、验证方法、风险、review/repair 决策、恢复状态或知识归属。读完后把结果压缩为可用于 Plan、实施、审查或恢复的结论。

若文件很大，优先读取目录、frontmatter、Contents、相关 heading、符号定义、测试名、helper JSON 字段或命令摘要。避免复制整份长文档到对话中。

用户明确要求查看某 section 时，只显示指定 artifact 与 heading；若请求“全部”，先提醒可能较长并按需分段。

## 终端输出预算

默认终端输出保持 compact：

- Locate/resume：列出 change id、title、路径、State status/phase/next_action；每个候选 1 行。
- Spec/Plan approval：只给 `change.md`/`plan.yaml` 路径、1–3 行摘要、risk/review/repair policy、Task count、`allowed_paths` 摘要、`validate-plan` exit code 和批准提示。
- Task dispatch/checkpoint：给 Task id/name、executor、task base、expected checkpoint subject、validation command 摘要和后续 helper command；不贴长 prompt。
- Review/validation：给 command、exit code、PASS/FAIL、关键失败片段或路径；长日志按用户要求显示。
- Repair decision：给 source gate、违反合同、路径、证据摘要、是否仍在 `allowed_paths` 和建议决策。
- Completion/archive：给产品结果、changed paths、validation summary、mandatory knowledge analysis 结果（写入、拒绝或 `NO_OP`）、retention disclosure、archive path 和最终 artifact set。

默认不回显完整 `change.md`、完整 `plan.yaml`、完整 `state.yaml`、完整 diff、transcript、agent 原文或长日志。用户明确要求时显示指定 section。

## Subagent prompt 预算

单次 subagent prompt 目标低于约 4k tokens。只包含：

- 当前 Task Goal 与 non-goals。
- change-level `allowed_paths` 和本 Task 实施意图。
- 必要 read paths/headings，避免一层 references 以外的阅读链。
- Acceptance 与 validation commands。
- `task_base` 与 expected `checkpoint_subject`。
- selective staging/commit 合同。
- 禁止编辑 `change.md`、`plan.yaml`、`state.yaml`，禁止递归委派、扩范围、自动 fixer routing、reset/rebase/squash/stash/history rewrite。
- compact return 格式。

不要传大型 packet、完整知识全文、完整 Spec/Plan/State、完整 transcript、全量 archive、legacy、长 diff 或长日志。

## Subagent return 预算

单次 subagent 返回目标低于约 2k tokens，包含：

- status：完成、阻塞或需要主会话决策。
- checkpoint SHA；没有 commit 时写 none 并说明原因。
- changed paths。
- commands、exit codes 和短输出摘要。
- 风险、blocker、超出 `allowed_paths` 或合同变化迹象。
- report/notes 路径仅当主会话明确要求且该路径在授权范围内。

不要要求 subagent 返回完整 diff、完整日志、过程 transcript 或自我 Gate 通过声明。主会话必须用 Git、helper State 和确定性证据核验。

## 100k 警戒线

当会话达到约 100k tokens，必须先收缩：

1. 用 `change.py status` 和 `change.py next-action` 捕获当前 status/phase/current_task/next_action。
2. 若需要写恢复摘要，只在 `change.md` 中压缩记录 Goal、批准 Plan revision、已完成 checkpoint commits、未完成 next_action、验证结果、blocker 和下一步；不要复制 State history 或日志。
3. 停止无关读取。
4. 改用路径、heading、commit SHA 和摘要。
5. 必要时委派小范围 subagent 或建议用户在新 Session 用 `work` 恢复。

不要继续全文读取 archive、legacy、所有领域知识、所有源码、完整 diff 或所有测试输出来“保险”。

## status 与 next-action 恢复

恢复依赖三类事实：

1. `change.py status` 与 `change.py next-action` 返回的当前 State。
2. Git HEAD、status/diff、checkpoint commits 和 commit subjects。
3. 代码、配置、测试、CI 与实际 validation/review evidence。

恢复步骤：

1. 定位唯一 active change；多候选时让用户选择。
2. 运行 `status` 和 `next-action`，记录 change id、plan revision、phase、current_task_id、next_action、blocker 摘要。
3. 检查 Git status，确认 index、allowed-path dirty 状态和 HEAD 是否与 State 一致。
4. 根据 `next_action` 执行最小下一步：dispatch Task、run review、run validation、request repair decision、complete、或 halt。
5. 若出现 Spec/Plan hash、revision、HEAD、checkpoint parent/subject/range、allowed-path 边界或 validation evidence drift，停止并向用户报告具体冲突。

不要重放 transcript、读取 agent claim 作为完成事实、把 `change.md` frontmatter `status` 当动态状态、或猜测最新聊天必然覆盖文件合同。

Archive 默认不参与恢复。只有用户提到历史 change、回归、类似问题或 `related_changes` 时才读取相关 archive 的精简 `change.md`；不要期待 archived `plan.yaml` 或 `state.yaml` 存在。Legacy 仅在用户明确要求历史材料或 init 需要整体移动时读取。

## 非 Gate 声明

上下文预算不是身份、hash、状态版本或授权机制。计划批准是用户可理解的自然语言确认；知识确认只在候选存在时出现。不要把上下文指纹、包绑定、证据身份、旧式状态路由、agent 声明或 helper 之外的状态文件作为当前 v2 运行时权威。
