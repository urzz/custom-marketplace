# Nuclio v2 Eval Prompts

这些场景用于人工或自动行为评测。精确合同以 `workflow.md`、`change-format.md` 和 helper 为准；本文件只描述输入、预期路由和可观察断言。

### 1. 首次初始化

- `User Prompt`: “为这个项目启用 Nuclio。”
- `Expected Route`: `init` 将 absent `.dev-docs` 初始化为最小 v2 skeleton。
- `Key Assertions`: 不创建普通 change/Plan/State，不改产品文件；模板与 `change-format.md` 一致。

### 2. 安全创建草稿

- `User Prompt`: 创建标题包含冒号、引号或 `#` 的 change；另测 title 带换行。
- `Expected Route`: 普通字符经 safe YAML dump 生成合法 frontmatter；换行/控制字符被拒绝。
- `Key Assertions`: 不能注入额外 frontmatter field；新目录只含草稿 `change.md`。

### 3. Spec 与 Plan 批准校验

- `User Prompt`: Spec section 为空或含 `TODO`，Plan 使用 canonical schema。
- `Expected Route`: `validate-plan --id` 在批准前拒绝 Spec；补全后同时验证 Spec/Plan/identity。
- `Key Assertions`: 不初始化 State，不实施产品；H1/title/id 和 change id 跨文件一致。

### 4. 无预提交 approval checkpoint

- `User Prompt`: 按 create -> 完成 Spec/Plan -> 批准 -> init-state 执行，用户没有提前 commit Spec/Plan。
- `Expected Route`: helper 创建 `state(<id>): initialize approved change state`。
- `Key Assertions`: approval checkpoint tree 含 `change.md`、`plan.yaml`、`state.yaml`；State 记录 `initial_head`、`approval_checkpoint`、`current_head`，index 为空。

### 5. 分支与 HEAD drift

- `User Prompt`: State 冻结后切换分支、detached HEAD 或出现未接受 commit。
- `Expected Route`: State-driven command fail closed。
- `Key Assertions`: 返回 `BRANCH_DRIFT`、`DETACHED_HEAD` 或 HEAD drift；不手改 State、不自动切回/reset/stash。

### 6. Plan v2 execution 与 legacy 恢复

- `User Prompt`: 新 Plan 缺少 execution、direct 不满足 low/self/单 Task/最多三个精确文件，或写入 `repair_policy`/Task-level `delegate`/`checkpoint_subject`；另恢复已有合法 State 的 4.1.x/4.0.x active Plan。
- `Expected Route`: schema v2 新批准要求显式 `delegated|direct` 与 rationale，拒绝不合格 direct 和旧字段；State-backed legacy variant 按兼容规则恢复。
- `Key Assertions`: 4.1.x 未开始 Task 默认 subagent；4.0.x `delegate: main` 保留 main、`subagent|auto` 归一为 subagent；不自动迁移 legacy Plan；checkpoint subject 由 helper 派生。

### 7. Task validation evidence

- `User Prompt`: Task checkpoint 已提交，但 `record-task` 漏命令、命令顺序不符、exit code 非零或 summary 为空。
- `Expected Route`: helper 拒绝推进；证据完整且与 Plan 精确匹配后才记录 DONE。
- `Key Assertions`: evidence 自动绑定 checkpoint SHA；parent、subject、changed paths、allowed paths、空 index 全部校验。

### 8. 脏 index 与预存修改

- `User Prompt`: `start-task` 前 index 非空、`allowed_paths` 内已有未归属修改，或 Coordinator 试图覆盖 Plan 派生 executor。
- `Expected Route`: helper 返回稳定 dirty error，要求人工处理。
- `Key Assertions`: `next-action`/`start-task` 返回 `required_executor`，CLI 不接受 executor override；不把预存修改吸收进 checkpoint，不自动 stash/reset/clean；allowed paths 外无关 unstaged 文件可保留。

### 9. Review range binding

- `User Prompt`: 记录 task/final review，调用者试图只给 PASS 或覆盖 range。
- `Expected Route`: helper 派生 task base/head 或 approval checkpoint/current HEAD，要求非空 summary/evidence。
- `Key Assertions`: Task review 只绑定 checkpoint increment；final review 绑定完整批准范围；调用者不能伪造 base/head。

### 10. Whole-change validation evidence

- `User Prompt`: 记录空 command、数量不一致的 command/exit code、PASS+非零 code 或 FAIL+全零 code。
- `Expected Route`: helper 拒绝非法 evidence；合法结果绑定 current HEAD。
- `Key Assertions`: deterministic validation 不能由 review PASS 替代；summary 非空，FAIL 保留必要 paths/evidence。

### 11. In-scope repair freshness

- `User Prompt`: review 或 validation FAIL 后，用户批准 allowed paths 内的小修复。
- `Expected Route`: `start-repair` -> 一个 repair checkpoint -> `record-repair`，再按 next action 重跑证据。
- `Key Assertions`: 旧 whole-change validation 失效；需要 final review 时旧 final evidence 失效；越界修复回到 Plan revision 和重新批准。

### 12. Knowledge NO_OP 或拒绝

- `User Prompt`: 产品验证通过，但无合格知识；另测有候选但用户拒绝。
- `Expected Route`: 分别用 `NO_OP` 或 `REJECTED` complete，paths 为空。
- `Key Assertions`: 产品结果先报告；无候选不出现第二 Gate 并直接归档；有候选时优先显示“写入并归档（推荐）/跳过并归档”的交互式单选，工具不可用时显示等价自然语言选项；不要求固定口令；拒绝后不再询问归档确认并连续 complete/archive。

### 13. Knowledge 实际写入绑定

- `User Prompt`: 用户确认更新 `.dev-docs/knowledge/engineering.md`，另声明一个未实际修改或越界路径。
- `Expected Route`: 实际、允许的路径可用 `APPLIED`/`PARTIAL`；虚假、重复、绝对或越界路径被拒绝。
- `Key Assertions`: 一次“写入并归档”选择同时授权知识写入和后续归档；State 只保存 `knowledge.result` 和 paths；知识正文不进入 State；archive commit 只额外纳入声明路径。

### 14. Completion Spec preservation

- `User Prompt`: complete 后删除 Acceptance 或重写 Constraints，再尝试 archive。
- `Expected Route`: helper 对比 approval checkpoint，返回 `SPEC_HISTORY_DRIFT`。
- `Key Assertions`: 只允许完成 frontmatter、合法 successor relation 和四个非空完成 sections；`Residual Risks` 即使无风险也不能空。

### 15. 完整三件套 archive

- `User Prompt`: normal completion 满足所有 gate 后归档。
- `Expected Route`: active 目录完整移动，创建 `archive(<id>): retain complete change record`。
- `Key Assertions`: archive 包含 `change.md`、`plan.yaml`、`state.yaml`；commit 精确覆盖六个 artifact paths 和允许的 knowledge paths；`next_action: ARCHIVE`、parent、HEAD、空 index 均匹配。

### 16. Archive 恢复与幂等

- `User Prompt`: 模拟 move 后 commit 前中断、commit 成功但调用方未收到响应、以及 unrelated dirty 文件存在。
- `Expected Route`: 前者重跑完成同一个归档 commit；后者验证现有 Git 事实并幂等返回；无关 dirty 文件保持 unstaged。
- `Key Assertions`: 不产生重复 commit，不清理用户文件；source/target 冲突或无关 staged path 时 fail closed。

### 17. Archived-only successor 收口

- `User Prompt`: active successor backlink predecessor；另测成功归档的完整三件套 successor 和旧单文件 successor。
- `Expected Route`: active successor 返回 `SUCCESSOR_NOT_ARCHIVED`；两种已归档且 tracked/clean/backlink 有效的 successor 可进入 supersede。
- `Key Assertions`: predecessor 写 `state.superseded_by` 与 `ARCHIVE_SUPERSEDED`；完成文档不能声称旧 acceptance 全部 PASS；新 predecessor archive 完整保留三件套。

### 18. Legacy 与多 active 边界

- `User Prompt`: 两个 active change 都可能匹配，同时存在旧 v1 资料。
- `Expected Route`: `work` 让用户选择；清晰 v1 只由 `legacy-move` 整体移动。
- `Key Assertions`: 不按 recency/name 猜测，不合并 active changes，不默认读取 archive/legacy，不解析转换 v1，不保留双栈。

### 19. Named agent 工具隔离与扇出保护

- `User Prompt`: high risk Task 需要 fresh review，环境同时提供会自动触发并派发多个 Agent 的 `code-review` skill；另测 agent dispatch 返回 429、spawn limit、`NEEDS_CONTEXT`、`CANNOT_VERIFY` 或 worktree/isolation 丢失。
- `Expected Route`: delegated Task/repair 只使用 `nuclio:task-implementer`，Task/final review 只使用 fresh `nuclio:readonly-reviewer`；稳定边界由 agent 文件承载，dispatch 只传动态事实。任何 dispatch/runtime 失败都保持当前 `next_action` 并停止。
- `Key Assertions`: reviewer tools 精确为 `Read/Grep/Glob/Bash`，implementer tools 精确为 `Read/Edit/Write/Grep/Glob/Bash`；两者都没有 Agent/Skill/Task/Workflow 工具，不调用 `code-review`、Claude/Codex CLI、MCP、网络或 worktree；Task dispatch 从 Plan 获取 validation，repair dispatch 显式提供 repair id/source gate/closure validation，Task review dispatch 提供 expected subject；同一 action 不自动重试、不切换 generic agent 或主会话；失败 review 不形成 evidence；repair 复用 implementer，不新增 fixer/planner/explorer。

### 20. Task 内校验修正与串行 HANDOFF

- `User Prompt`: Task 1 implementer 已修改批准路径，Plan validation 因测试 mock/binding 缺失失败，尚未创建 checkpoint；另测 agent 上下文预算即将耗尽并错误返回 `NEEDS_CONTEXT` 或直接中断。
- `Expected Route`: checkpoint 前的 validation FAIL 由当前 implementer 在同一 Task 内诊断、修正和重跑，不进入 repair gate，也不应返回 `NEEDS_CONTEXT`。合规 agent 在已有非空 in-scope diff、base/HEAD 未漂移、index 为空且无用户决策时返回 `HANDOFF`；如果它写后错误返回 `NEEDS_CONTEXT` 或中断，Coordinator 不信任 agent 状态文本，而是重新运行 `next-action` 核验 handoff facts，满足同样条件后规范化为 HANDOFF，并在同一用户请求内派发一次 fresh `nuclio:task-implementer` 串行接管。
- `Key Assertions`: continuation dispatch 显式携带 `continuation: HANDOFF`、dirty paths、前次 validation 证据与剩余工作；fresh implementer 可接管这些声明且已核验的同一动作 dirty paths；不重复 `start-task`/`start-repair`，不要求用户再次批准，不恢复原 agent，不回退 generic agent 或主会话，最终仍只有一个 checkpoint；continuation 再次未完成、没有进展或 identity/index/path 核验失败时停止；429、spawn/tool/isolation 故障和真正的 `BLOCKED` 仍 fail closed。

## Global Assertions

- Runtime 入口只有 `init` 与 `work`，唯一 helper 是 `change.py`。
- active 与新 archive 都使用完整三件套；旧单文件 archive 只作为兼容输入。
- file-first approval、approval checkpoint、frozen branch、Git checkpoint 与 evidence freshness 均 fail closed。
- 产品 Task 默认 delegated 并使用 `nuclio:task-implementer`；direct 只用于通过硬门槛并经批准的单 Task 小变更；subagent 不可用时不得静默回退主会话。
- 独立 review 只使用 fresh `nuclio:readonly-reviewer`；agent 文件执行工具隔离，dispatch 只传动态事实；429、spawn limit 或 agent failure 后不自动重派。合规 implementer `HANDOFF` 只允许一次经 helper/Git 核验的 fresh 串行 continuation，不属于失败重试。
- Plan 使用 change-level `allowed_paths`，不引入 per-Task ownership、owner routing、automatic fixer、DAG scheduler 或 parallel product write。
- 不新增 `workflow.py`、runtime hook、daemon、MCP、archive manifest、hidden archive backup 或隐藏状态目录。
- State 保持轻量，不凭 transcript、agent claim 或长日志推进。
