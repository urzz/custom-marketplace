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

### 6. Canonical 与 legacy Plan

- `User Prompt`: 新 Plan 写入 `repair_policy`/`delegate`/`checkpoint_subject`；另恢复一个已有合法 State 的 4.0.x active Plan。
- `Expected Route`: 新批准拒绝旧字段；恢复路径按精确 legacy variant 兼容。
- `Key Assertions`: 不接受混合 schema，不自动迁移 legacy Plan；checkpoint subject 对新 Plan 由 helper 派生。

### 7. Task validation evidence

- `User Prompt`: Task checkpoint 已提交，但 `record-task` 漏命令、命令顺序不符、exit code 非零或 summary 为空。
- `Expected Route`: helper 拒绝推进；证据完整且与 Plan 精确匹配后才记录 DONE。
- `Key Assertions`: evidence 自动绑定 checkpoint SHA；parent、subject、changed paths、allowed paths、空 index 全部校验。

### 8. 脏 index 与预存修改

- `User Prompt`: `start-task` 前 index 非空，或 `allowed_paths` 内已有未归属修改。
- `Expected Route`: helper 返回稳定 dirty error，要求人工处理。
- `Key Assertions`: 不把预存修改吸收进 checkpoint，不自动 stash/reset/clean；allowed paths 外无关 unstaged 文件可保留。

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
- `Key Assertions`: 产品结果先报告；无候选不出现第二 Gate；拒绝不阻止 complete/archive。

### 13. Knowledge 实际写入绑定

- `User Prompt`: 用户确认更新 `.dev-docs/knowledge/engineering.md`，另声明一个未实际修改或越界路径。
- `Expected Route`: 实际、允许的路径可用 `APPLIED`/`PARTIAL`；虚假、重复、绝对或越界路径被拒绝。
- `Key Assertions`: State 只保存 `knowledge.result` 和 paths；知识正文不进入 State；archive commit 只额外纳入声明路径。

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

## Global Assertions

- Runtime 入口只有 `init` 与 `work`，唯一 helper 是 `change.py`。
- active 与新 archive 都使用完整三件套；旧单文件 archive 只作为兼容输入。
- file-first approval、approval checkpoint、frozen branch、Git checkpoint 与 evidence freshness 均 fail closed。
- Plan 使用 change-level `allowed_paths`，不引入 per-Task ownership、owner routing、automatic fixer、DAG scheduler 或 parallel product write。
- 不新增 `workflow.py`、runtime hook、daemon、MCP、archive manifest、hidden archive backup 或隐藏状态目录。
- State 保持轻量，不凭 transcript、agent claim 或长日志推进。
