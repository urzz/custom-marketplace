# Nuclio v2 Context Hygiene

Nuclio 的上下文原则是按决策需要取证。文件存在不等于必须全文读取；State 与 Git identity 优先于 transcript 和 agent claim。

## Default Read Order

普通 active change：

1. 用户当前请求。
2. `change.py status` 与 `next-action` 的紧凑输出。
3. `change.md` 中与当前决策相关的 headings。
4. Plan 中 risk、review policy、execution、`allowed_paths` 与当前 Task。
5. 当前 Task 涉及的源码、配置和测试。
6. 只有发生 drift、review、repair 或恢复诊断时读取更多 State/Git 证据。

不要默认读取全部 active changes、所有 archive、整个 legacy tree、完整知识库或历史研究文档。

## Artifact Budgets

- **change.md**：准备/批准时读必要 Spec sections；完成时读完整 Spec 与四个完成 sections。
- **plan.yaml**：只取当前 Task 和 change-level contract；validator 负责完整机械校验。
- **state.yaml**：优先用 helper 的 `status`/`next-action`，只在诊断时读取原文件片段。
- **Git**：优先精确 range、status、name-only 和 commit metadata；不要默认粘贴完整 diff。
- **validation**：保留 command、exit code、短摘要和关键失败片段，不复制长日志。

## Archive Read Budget

archive 默认不进入日常 prompt。需要历史追溯时：

1. 先读取目标 archived `change.md` 的相关 heading。
2. 只有要确认批准范围、risk、Task 合同时读取 archived `plan.yaml`。
3. 只有要审计 checkpoint、review、validation 或 knowledge result 时读取 archived `state.yaml`。
4. 旧 4.0.x 单文件 archive 缺少 Plan/State 是兼容事实，不要推测或伪造。

完整三件套 retention 是审计能力，不是默认上下文预算。

## Approval Output

file-first Gate 默认输出：artifact paths、1-3 行 Spec 摘要、risk/review policy、execution mode/rationale、Task 数、`allowed_paths` 摘要、验证 exit code 和完整三件套 archive disclosure。不要粘贴全 Spec、全 Plan、全 State 或完整日志，除非用户请求明确 section。

## Task Dispatch

先读取 helper 的 `required_executor`。`subagent` 必须实际派发 `nuclio:task-implementer`；不可用时报告 blocker，不得让主会话或 generic subagent 接管。`main` 只可能来自已批准且通过 helper 硬门槛的 `execution.mode: direct`。

implementer agent 文件已保存稳定边界；dispatch 只包含：

- repo root、change id、`change.md`/`plan.yaml` 路径；
- action，以及 Task id 或 repair id/source gate；
- helper base、expected checkpoint subject、frozen branch；
- 必要 read paths；
- repair finding、closure goal、允许路径与精确 closure validation commands（如适用）。

agent 自行从批准 artifact 读取相关 Spec、Task 合同和 change-level `allowed_paths`，不在 prompt 复制长合同。Task validation 来自 Plan；repair closure validation 来自获批 repair dispatch。返回只需 checkpoint SHA、changed paths、commands/exit codes、关键摘要、风险和 blocker。Coordinator 必须用 Git 与 helper 核验，不凭返回文本推进 State。

产品写入顺序执行。`final`/`task-and-final` 使用 fresh `nuclio:readonly-reviewer`，不与其他 Nuclio agent 并发；不引入 DAG scheduler、parallel product write、owner routing 或 automatic fixer。

## Review Budget

Task review 聚焦 helper 固定的 `task_base..task checkpoint` 和该 Task 合同。Final review 聚焦 `approval_checkpoint..current_head` 的集成语义、跨 Task 交叉触碰、repair 增量、失败后修复与高后果区域。

未漂移且已独立审查的 Task evidence 可以作为 final review 输入，但以下情况必须深读相关 diff、合同和验证证据：

- repair 或同一路径重复触碰；
- 跨 Task 交叉修改；
- validation 失败后修复；
- public API、数据、权限、并发、迁移或不可逆动作；
- 风险上升或验证覆盖不足。

reviewer dispatch 只传 scope、Task id/expected checkpoint subject（Task review）、artifact paths、helper base/head、changed paths、validation evidence、repair/交叉触碰热点和可复用 evidence 摘要。稳定的只读、工具、读取顺序和返回合同不重复注入 prompt。review 输出保留 summary、evidence、violated contract 和 paths，不保存 reviewer transcript。

同一 `next-action` 只 dispatch 一次。429、spawn limit、agent/工具不可用、`NEEDS_CONTEXT`、`CANNOT_VERIFY` 或 worktree/isolation 丢失时停止并报告；不自动重试、不恢复失败 agent、不切换 generic agent 或主会话。失败或中断的 review 不形成 evidence。

## Recovery Budget

恢复先回答四个问题：

1. 当前 attached branch 是否等于 frozen `state.git_branch`？
2. HEAD 是否等于 State 允许的 checkpoint？
3. index 与 `allowed_paths` 工作树是否满足当前动作前置条件？
4. helper 的 `next_action` 是什么？

只有答案指向 drift 或中断时，才扩展读取 commit parent/subject/path range、archived State 或完整 diff。不要回放聊天记录来重建 State。

## User-Facing Results

结果报告先给 outcome，再给最小证据：changed paths、commands、exit codes、关键摘要、archive path/commit 或 blocker。知识 proposal 与产品结果分开，不能让知识决策遮蔽已完成的产品验证。

## Forbidden Context Stores

不得把完整 diff、测试日志、transcript、agent messages、file snapshots 或 linear event ledger 写入 `state.yaml`。不得创建 persistent process JSON、archive manifest、hidden archive backup、第二状态目录、`workflow.py` 或外部运行时服务来保存这些内容。
