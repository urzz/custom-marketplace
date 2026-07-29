# Nuclio v2 Eval Prompts

本文件定义 Nuclio v2 行为评估语料。每个 case 都从用户可见工作台视角验证 `init` 或 `work` 的路由、允许写入、禁止写入和关键断言。Eval 不要求真实修改产品代码，但必须能检查运行时指令是否维持轻量三层 docs-as-code 工作流。

## Contents

- [评估原则](#评估原则)
- [固定字段](#固定字段)
- [审查效率场景矩阵](#审查效率场景矩阵)
- [18 个 v2 cases](#18-个-v2-cases)
- [全局断言](#全局断言)

## 评估原则

- 日常入口是 `work`；`init` 只做 v2 skeleton、根导航修复和清晰 legacy 整体移动。
- 每个普通 active change 使用 `.dev-docs/changes/<change-id>/change.md`、`plan.yaml`、`state.yaml` 三层 artifact。
- `change.md` 是 Spec 权威，`plan.yaml` 是用户自然语言批准后的执行合同权威，`state.yaml` 是唯一动态恢复状态权威。
- 唯一 runtime helper 是 `plugins/nuclio-plugin/scripts/change.py`；它不调用模型、不修改产品文件、不替用户批准。
- 产品 mutation 和 `init-state` 前必须先把完整 Spec/Plan 写入文件、运行 `validate-plan`，并获得用户自然语言批准。
- Nuclio runtime Plan 使用 change-level `allowed_paths`；不使用 per-Task files ownership、owner mapping 或 finding owner routing。
- 每个实施 Task 和每个 approved in-scope repair 恰好一个 selective-stage 本地 checkpoint commit。
- State 只保存当前恢复事实；Git checkpoint commits 保存实际历史，不把 transcript、完整 diff、完整日志或 State history 复制进 State。
- 小型、边界清晰的单 Task 可由主会话直做；大型、多 Task、跨模块或上下文压力明显的 change 默认委派有界 generic subagent 单元。
- bounded subagent 不得调用 TaskStop/Stop Task，不得创建、更新、停止或接管 Controller/task-tracking 任务，不得尝试停止自身、父任务、兄弟任务或后台任务；完成、阻塞、超时或需要决策时只能返回 compact result 给主会话。
- 产品写入按 Task/repair 顺序执行；只读探索或审查才可按需并发。
- 终端默认 compact：路径、1–3 行摘要、risk/review/repair policy、Task count、`allowed_paths` 摘要和关键 exit code；用户明确要求时才显示指定 artifact 或 section。
- 验证、风险审查、in-scope repair、mandatory knowledge-candidate analysis、confirmed knowledge maintenance、complete 和 archive 都在 `work` 生命周期内完成。
- 长期知识只在产品结果验证后、有合格候选且用户确认时写入；无合格候选时记录 `NO_OP`；拒绝知识不影响产品完成或 archive，但精简历史记录必须说明拒绝结果。
- File-first implementation Gate 必须披露 retention policy：成功 archive 只保留精简 `change.md`，active `plan.yaml`/`state.yaml` 不进入长期 archive。
- Archive 和 legacy 默认不读；只有当前目标需要时才按路径读取。未来成功 archive 是 one-file archive，历史读取不依赖 archived Plan/State。
- 当范围扩大需要 successor 接管 predecessor 时，successor `change.md.related_changes` 必须引用 predecessor；active predecessor→successor relation 在 successor 成功归档后由 `supersede` 写入 `state.superseded_by`，再蒸馏 predecessor `change.md` 写入与 State 一致的 archive `related_changes`、superseded Outcome/Validation，并 archive。不得 pre-link frozen predecessor、不得新增 link-related、不得手改 State 或 hash refresh/rebaseline，不得按 `-v2` 名称猜测 successor，不得把 predecessor 旧 acceptance 伪装为成功，失败必须报告残留 active predecessor 路径。

## 固定字段

每个 case 必须显式包含以下五个字段；不得增加运行时 owner、finding owner、per-Task files ownership 或 behavioral eval owner 字段：

| 字段 | 含义 |
| --- | --- |
| `User Prompt` | 用户输入和必要项目状态摘要。 |
| `Expected Route` | 应进入的 v2 路由和主要下一步。 |
| `Allowed Writes` | 允许写入的路径或类别。 |
| `Forbidden Writes` | 禁止写入的路径或类别。 |
| `Key Assertions` | 必须满足的行为断言。 |

## 审查效率场景矩阵

审查策略由场景、失败后果、耦合和验证强度决定，不按编程语言决定。Eval 必须覆盖语言无关四类场景，并同时保护 integration-focused final、增量 commit range、证据复用条件和 mandatory deep-read triggers：

| 场景 | 推荐审查合同 | 关键断言 |
| --- | --- | --- |
| 普通多模块且强验证 | change-level `final`，final review 以 integration-focused final 为主 | Task 通过增量 commit range、task base、checkpoint commit 和 deterministic validation 提供可复核证据；final 聚焦 whole-change 集成语义、接口衔接、用户可见行为和未覆盖风险，不按规模机械全量重审每行。 |
| 选择性风险 Task | change-level `final` 加指定 `task.review=task-and-final` | 只有失败后果、耦合或验证缺口明显的指定 Task 进入 Task review gate；其他 Task 不产生 Task review gate，仍由 checkpoint commit、validation 与 final review 覆盖。 |
| 高风险严格路径 | change-level `task-and-final` | 每个 Task 都必须 task-and-final，final review mandatory；L3/high risk 不降级为 final-only。 |
| repair 或重复触碰 | 依据源 gate 回到 review/validation，并触发 final 深读 | repair、同一路径重复触碰、跨 Task 交叉修改、checkpoint/HEAD/Spec/Plan 漂移、失败后果升高或证据缺口属于 mandatory deep-read triggers；final 不得复用已漂移证据。 |

证据复用条件：final review 保持 mandatory，但可复用未漂移的 Task review 与 validation 证据；可复用证据必须绑定 task base、增量 commit range、checkpoint commit、changed paths、命令 exit code、result summary、Spec/Plan/HEAD identity 和未发生 repair 或重复触碰后的漂移。任何 repair、重复触碰、路径交叉、验证失败后修复、identity drift、checkpoint mismatch 或 acceptance/risk 变化都会使相关 Task review/validation 证据不可直接复用，并要求 final 深读相关 diff、合同和验证证据。

## 18 个 v2 cases

### 1. 小型单 Task 主会话直做

- `User Prompt`: “修复 README 中一个错误链接”，项目已有清晰 v2 `.dev-docs`，没有匹配 active change。
- `Expected Route`: `work` 创建新 change，写入 `change.md` Spec 与低风险单 Task `plan.yaml`，运行 `validate-plan`，compact 展示文件路径、摘要和 archive retention disclosure，获自然语言批准后 `init-state`，主会话直接实施、验证、checkpoint、self review、报告产品结果、分析知识候选、complete/archive。
- `Allowed Writes`: `.dev-docs/changes/<id>/change.md`、`.dev-docs/changes/<id>/plan.yaml`、批准后由 helper 写 `.dev-docs/changes/<id>/state.yaml`、批准范围内 README、确认后的知识文件、完成后的 one-file archive 目录。
- `Forbidden Writes`: 未批准产品路径、知识确认前的知识文件、legacy、持久过程 JSON、第二 helper、`.dev-docs/changes/index.md`。
- `Key Assertions`: 简单任务可由主会话直做；产品 mutation 前必须展示 file-first Gate、获得自然语言批准，并披露成功 archive 不保留 Plan/State；批准后每个实施 Task 恰好一个 checkpoint commit。

### 2. 普通多 Task 功能

- `User Prompt`: “给 CLI 增加 dry-run 选项并更新文档”，涉及实现、测试和文档；其中默认行为保持不变的普通 Task 验证充分，但修改执行路径的少数风险 Task 失败后果更高。
- `Expected Route`: `work` 创建或恢复唯一 active change，按需读取源码/测试，写入多 Task Plan；若普通多模块变更具备强验证且多数失败后果可控，采用 change-level `final`，但对少数风险 Task 设置 `task.review=task-and-final`；使用 change-level `allowed_paths` 覆盖 CLI、测试和文档，批准后按 `next-action` 顺序执行每个 Task，最终执行 integration-focused final。
- `Allowed Writes`: active change 的 `change.md`、`plan.yaml`、helper 写入的 `state.yaml`、批准的 CLI/测试/文档路径、archive 路径。
- `Forbidden Writes`: 未列入 `allowed_paths` 的子系统、per-Task files ownership、owner mapping、知识候选确认前的 knowledge 文件、legacy。
- `Key Assertions`: 多 Task 通过有序 Tasks 与 checkpoint commits 控制增量；选择性风险 Task 可用 `task.review=task-and-final` 提升为 Task review gate，其他 Task 不产生 Task review gate；每个 Task 的 task base、增量 commit range、checkpoint commit、changed paths 和 validation 为 final 提供可复核证据；integration-focused final 聚焦 whole-change 集成语义、接口衔接和用户可见行为，不按规模机械全量重审每行；Plan 不创建 runtime owner routing；每个 checkpoint changed paths 必须全部在 change-level `allowed_paths` 内。

### 3. 大型跨模块默认委派

- `User Prompt`: “调整认证中间件和数据访问层的权限模型”。
- `Expected Route`: `work` 推荐澄清风险边界，写入高风险 high risk、change-level `task-and-final`、多 Task Plan；批准后大型/跨模块单元默认委派有界 generic subagent 或说明为何直做更安全。
- `Allowed Writes`: active change 三层 artifact、批准范围内认证/数据访问/测试路径、确认后的知识更新、archive 路径。
- `Forbidden Writes`: 无批准直接实施、无 task review 直接完成、Nuclio 专用 agent 流水线、递归委派、并行产品写入、自动 owner fixer。
- `Key Assertions`: 高风险严格路径必须每个 Task 都执行 task-and-final review，final review mandatory，不能因语言或文件数量降级为 final-only；大型变更默认委派有界单元；subagent dispatch 必含 `allowed_paths`、task base、expected checkpoint subject、validation、TaskStop/Stop Task 与 Controller/task-tracking 生命周期控制禁令、以及 compact return；主会话只以 Git/helper/确定性证据推进。

### 4. file-first 指定片段查看

- `User Prompt`: 用户看到 compact Gate 后说“只给我看 plan.yaml 的第二个 Task 和 allowed_paths”。
- `Expected Route`: `work` 只显示用户指定 artifact 片段，必要时补充短解释，然后继续等待批准、修订或拒绝。
- `Allowed Writes`: 已处于准备阶段的 `change.md` 和 `plan.yaml` 修订；若用户仅查看片段则不新增写入。
- `Forbidden Writes`: `init-state`、产品路径、完整 Plan/State/diff 默认回显、要求固定批准 token 或 hash。
- `Key Assertions`: 完整 Spec/Plan 存在于文件；终端默认 compact，但用户明确要求的指定 section 必须可查看；查看片段不等于批准。

### 5. 计划未批准禁止 init-state

- `User Prompt`: 用户看到计划后说“先别改，我再想想”。
- `Expected Route`: `work` 停止在批准前，可保留或修订准备阶段 Spec/Plan，不运行 `init-state`，不修改产品。
- `Allowed Writes`: active change 的 `change.md` 或 `plan.yaml` 准备阶段内容。
- `Forbidden Writes`: `.dev-docs/changes/<id>/state.yaml`、产品路径、checkpoint commit、知识文件、archive。
- `Key Assertions`: 用户自然语言拒绝或暂缓不授权 mutation；helper 不能替用户批准；未批准不得初始化 State。

### 6. session recovery 使用 status 与 next-action

- `User Prompt`: “继续上次那个导出性能优化”，存在唯一 active change，已有 `state.yaml` 和部分 checkpoint commits。
- `Expected Route`: `work` 读取必要 Spec/Plan 摘要，先运行 `change.py status` 与 `change.py next-action`，再检查 Git HEAD/status/diff 和 checkpoint subjects，执行最小下一步。
- `Allowed Writes`: 根据当前 `next_action` 允许的三层 artifact 摘要更新、批准范围内产品路径、验证后 archive。
- `Forbidden Writes`: 重放 transcript 作为事实、读取 agent claim 直接推进、手写 `state.yaml`、默认读取全部 archive/legacy。
- `Key Assertions`: 恢复依赖 `state.yaml` 当前状态、Git 和确定性证据；若 Spec/Plan hash、revision、HEAD 或 checkpoint drift，fail closed。

### 7. 非空 index 与预存 allowed-path 修改

- `User Prompt`: 批准后准备开始 Task，但 Git index 非空，且 `allowed_paths` 内已有未归属修改。
- `Expected Route`: `work` 在 `start-task` 阶段由 helper 拒绝，报告 `DIRTY_INDEX` 或 `DIRTY_ALLOWED_PATH`，要求人工清理或决策。
- `Allowed Writes`: none，除非用户随后明确处理脏状态。
- `Forbidden Writes`: 在脏 index 上继续实施、把预存 allowed-path 修改纳入当前 checkpoint、自动 stash/reset/clean。
- `Key Assertions`: Task base 必须在干净 index 与无预存 allowed-path dirty 的状态冻结；allowed paths 外 unrelated unstaged/untracked 可保留但不能提交。

### 8. Spec/Plan/HEAD 一致性漂移 drift

- `User Prompt`: 恢复时发现 `plan.yaml` revision 被改、`change.md` hash 变化，或 Git HEAD 与 State 不一致。
- `Expected Route`: `work` 停止推进，报告 drift 类型、相关 artifact 路径和建议的人类决策；必要时提高 Plan revision 并重新 file-first approval。
- `Allowed Writes`: 用户确认后的 Spec/Plan revision 更新；重新批准后 helper 写 State。
- `Forbidden Writes`: 自动同步 hash、猜测最新聊天覆盖文件合同、继续实施产品、跳过重新批准。
- `Key Assertions`: Spec hash、Plan hash、revision 和 HEAD 是 fail-closed 一致性漂移；drift 不能由 agent claim 或 terminal 摘要覆盖。

### 9. checkpoint parent/subject/count/range mismatch

- `User Prompt`: Task 后存在两个 commits、commit parent 不是 task base、subject 与 Plan 不一致，或 commit range 为空。
- `Expected Route`: `work` 调用 `record-task` 时 helper 拒绝，返回具体 checkpoint mismatch，并要求人工处理。
- `Allowed Writes`: none；只有用户明确决定后才可按普通 Git 操作处理。
- `Forbidden Writes`: 自动 squash/reset/rebase/stash、接受错误 subject、把多个 commits 当一个 Task checkpoint、记录空 checkpoint。
- `Key Assertions`: 每个实施 Task 恰好一个 selective-stage 本地 checkpoint commit；parent、subject、count、range、index 和 validation 必须全部匹配。

### 10. 超出 allowed_paths

- `User Prompt`: 实施中需要修改 Plan 未列出的公共 API 文件。
- `Expected Route`: `work` 停止当前实施，说明超出 change-level `allowed_paths`，更新 Spec/Plan revision、重新 `validate-plan` 并重新审批。
- `Allowed Writes`: 准备阶段 Spec/Plan revision 更新；重新批准后新增路径才可写。
- `Forbidden Writes`: 在旧批准下修改公共 API、给新增路径分配 runtime owner、由 reviewer/fixer 自动扩范围。
- `Key Assertions`: `allowed_paths` 是 change-level 写入边界；超出边界必须重新批准，不能通过 owner routing 或 agent claim 放行。

### 11. State 手改或轻量 State 违规

- `User Prompt`: 用户或工具直接编辑了 `state.yaml`，或 State 被塞入完整 diff/日志/history。
- `Expected Route`: `work` 通过 helper 读取时发现 一致性漂移 或 schema/状态异常即停止，要求人工恢复或重新批准；不把手写 State 当事实。
- `Allowed Writes`: 仅 helper 在合法 transition 中原子写 `state.yaml`；人工决定后的 Spec/Plan 修订。
- `Forbidden Writes`: 手写 `state.yaml`、State transition history、完整 diff、完整测试日志、agent transcript、文件内容 snapshot。
- `Key Assertions`: `state.yaml` 是 helper-only 当前恢复状态；Git commits 保存历史，State 不复制历史。

### 12. subagent claim 无证据

- `User Prompt`: subagent 返回“已完成并通过”，但没有 checkpoint SHA、changed paths、commands/exit codes 或 Git 证据；或 subagent 遇到阻塞后试图调用 TaskStop/Stop Task、停止父任务/兄弟任务/后台任务，或接管 Controller/task-tracking task ownership。
- `Expected Route`: `work` 不推进 helper State，要求补足证据或由主会话用 Git/status/diff/validation 核验；对 task ownership error 类行为必须视为违反 dispatch 合同，要求 subagent 只返回 compact result 给主会话。
- `Allowed Writes`: none，除非核验证明仍需 in-scope repair 且获决策。
- `Forbidden Writes`: 凭 agent claim 运行 `record-task`、跳过 validation、跳过 checkpoint、跳过 review、让 subagent 创建/更新/停止/接管 Controller/task-tracking 任务或停止任何自身/父级/兄弟/后台任务。
- `Key Assertions`: compact return 必含 checkpoint SHA、changed paths、commands/exit codes、风险/blocker；完成、阻塞、超时或需要决策时 subagent 只能返回 compact result，不能调用 TaskStop/Stop Task 或控制任务生命周期；主会话只以确定性证据推进。

### 13. in-scope repair

- `User Prompt`: task review 发现已批准范围内某测试漏了边界条件，修复路径仍在 `allowed_paths` 内。
- `Expected Route`: `work` 记录 review FAIL 后进入 `REQUEST_REPAIR_DECISION`，请求人工判断是否 in-scope；同意后 `start-repair`、实施、closure validation、一个 repair checkpoint、`record-repair` 返回原 gate；若 repair 造成同一路径重复触碰或跨 Task 交叉修改，后续 final 必须对相关 diff、合同与证据深读。
- `Allowed Writes`: helper 写 State repair 字段、批准范围内 repair paths、一个 repair checkpoint commit。
- `Forbidden Writes`: 自动 repair 循环、owner budget、fixer routing、Plan 未变却强制重新审批、超出 `allowed_paths` 的 repair。
- `Key Assertions`: in-scope repair 不改变 Goal/Constraints/Acceptance/risk/Plan 合同；每次 repair 前必须有 `REQUEST_REPAIR_DECISION` 和人工判断；repair、重复触碰、跨 Task 交叉修改、验证失败后修复或失败后果升高属于 mandatory deep-read triggers，相关 Task 的旧证据不可无条件复用，final 深读必须覆盖受影响 diff、合同和验证证据。

### 14. 范围扩大 successor 收口

- `User Prompt`: 批准单文件修复并冻结 State 后，用户要求“顺便改公共 API 并迁移调用方”；Coordinator 判断原 predecessor 无法在旧合同中安全继续，创建 successor。successor 已完成并成功 archive，但 predecessor 仍在 active 目录；演练分支分别覆盖真实 frozen predecessor、successor change.md 缺少 predecessor backlink、active Spec drift、以及 predecessor archive `related_changes` 与 `state.superseded_by` 不一致。
- `Expected Route`: `work` 先在 successor 创建/修订阶段让 successor `change.md.related_changes` 引用 predecessor 并重新 file-first approval；不要修改 frozen predecessor 来预建关系。successor 成功归档后必须继续收口 predecessor：运行 `supersede --id <predecessor> --successor-id <successor>`，由 helper 写入 predecessor `state.superseded_by`，蒸馏 predecessor 的 `change.md` 使 archive `related_changes` 与 State successor 一致并写入 superseded Outcome/Validation，再调用 `archive`。若 successor backlink、successor identity、predecessor State/Plan、HEAD、active Spec drift、archive relation mismatch 或 artifact pruning 任一失败，则 fail closed，保留 predecessor active，并报告残留 active predecessor 路径。
- `Allowed Writes`: 准备阶段 successor `change.md` backlink 修订、successor 的 `plan.yaml` revision、重新批准后的新增路径、helper 写 predecessor `SUPERSEDED`/`ARCHIVE_SUPERSEDED` State 与 `state.superseded_by`、predecessor superseded `change.md` distillation（含 archive `related_changes`）、成功后的 one-file archive。
- `Forbidden Writes`: 在旧批准下修改 public API、迁移调用方、按 `-v2` 名称或聊天记录猜测 successor、缺少 successor backlink 时 supersede、pre-link frozen predecessor、link-related 命令、通用 hash refresh/rebaseline、手写 `state.yaml`、无 successor 强制归档、把 predecessor 旧 acceptance 伪装为成功、失败后宣称完全收口。
- `Key Assertions`: public API、架构、依赖、迁移或产品语义变化必须重新计划和重新批准；successor 成功归档后必须收口 predecessor；successor `change.md` backlink 是 fail-closed 前置条件；active predecessor relation 只由 `state.superseded_by` 表达；archive predecessor `related_changes` 必须与 State successor 一致；不得按名称猜测 successor；不得 pre-link frozen predecessor、link-related、hash refresh 或手写 State；不得把旧 acceptance 伪装为成功；失败必须报告残留 active predecessor 路径。

### 15. whole-change validation FAIL

- `User Prompt`: 所有 Tasks 和 reviews 完成后，whole-change validation 失败。
- `Expected Route`: `work` 记录 validation FAIL、具体命令/exit code/路径/证据，进入 `REQUEST_REPAIR_DECISION`；in-scope 时按 repair 流程，否则回到 Plan revision。
- `Allowed Writes`: helper 写 validation/blocker/repair 状态、批准范围内 repair paths、closure validation 证据摘要。
- `Forbidden Writes`: 用 reviewer PASS 替代失败 deterministic validation、无证据完成、把长日志复制进 State 或 knowledge。
- `Key Assertions`: deterministic-first；validation FAIL 不能完成，repair 后必须 closure validation PASS 并返回原 gate。

### 16. 知识候选确认

- `User Prompt`: “完成插件验证修复后，把可复用的验证约定记到项目知识里”，产品验证已通过且候选满足五问。
- `Expected Route`: `work` 先报告产品结果与验证证据，再执行 mandatory knowledge-candidate analysis，展示知识候选的语义结论、唯一目标 heading、操作类型、冲突、影响和支持证据，等待用户确认。
- `Allowed Writes`: active change Outcome/Knowledge Updates、用户确认的唯一 knowledge target、必要导航链接、archive 路径中的精简 `change.md`。
- `Forbidden Writes`: 用户确认前写 knowledge、把命令长日志写入知识、把 Plan/State/diff/transcript/agent 消息写入长期知识、把 knowledge 作为第四状态权威、因知识被拒绝而阻止 complete/archive。
- `Key Assertions`: 知识分析在产品验证后始终发生；知识确认只在候选合格时出现；无合格候选必须记录 `NO_OP` 且不制造第二 Gate；拒绝不影响已验证产品结果、`complete` 或 `archive`，但 `Knowledge Updates` 必须记录候选被拒绝。

### 17. complete 与 archive

- `User Prompt`: “验证和审查都通过了，完成并归档这个 change”。
- `Expected Route`: `work` 先报告产品结果、changed paths、commands/exit codes 和关键输出摘要；完成 mandatory knowledge-candidate analysis 并记录写入、拒绝或 `NO_OP`；调用 `complete` 后把 `change.md` 蒸馏为含 frontmatter、Goal、Outcome、Validation、Knowledge Updates 的精简历史记录，再调用 fail-closed `archive`。
- `Allowed Writes`: active `change.md` 精简 Outcome/Validation/Knowledge Updates、helper 写终态 `state.yaml`、`.dev-docs/changes/archive/<id>/change.md`。
- `Forbidden Writes`: 未满足 Tasks/reviews/validation 就 complete、archive 前未披露 retention policy、archive 前未蒸馏 `change.md`、复制完整日志、把 Plan/State 长期保留到 archive 或隐藏备份、自动 squash/reset/rebase/stash。
- `Key Assertions`: complete 要求 Tasks、必要 task/final review、whole-change validation、HEAD/State/Spec/Plan identity 和 blocker 条件全部满足；archive 前验证 completed State、identity、精简历史形态和 exact artifact set；成功 archive 只保留精简 `change.md`，unexpected artifact 或 undistilled record fail closed。

### 18. 多个 active change 与 legacy 边界

- `User Prompt`: “继续做那个导入修复”，存在两个 active change 都可能匹配；另有旧 v1 legacy 资料。
- `Expected Route`: `work` 停止猜测，列出候选并询问用户选择；legacy 默认不读。若目标是启用新版且 `.dev-docs` 清晰 v1，则 `init` 或准备阶段使用 `legacy-move` 整体移动。
- `Allowed Writes`: 用户选择后才可写选中 active change；清晰 legacy move 时写 `.dev-docs/legacy/v1/**` 和最小 v2 skeleton。
- `Forbidden Writes`: 选择最新目录、合并两个 active changes、默认读取全部 archive/legacy、解析或转换 v1 artifact、保留 v1/v2 双栈。
- `Key Assertions`: 多候选必须人类选择；legacy 只能整体移动；不提供 v1 compatibility converter，不恢复旧式运行时权威。

## 全局断言

- Runtime 入口只呈现 `init` 和 `work`。
- `init` 不创建普通 change、不实施产品、不归档普通 change。
- `work` 负责计划、实现、验证、风险审查、in-scope repair、可选知识、complete 和 archive。
- 普通 active change 使用 `change.md`、`plan.yaml`、`state.yaml` 三层 artifact。
- `change.md` 是 Spec 权威，`plan.yaml` 是批准合同权威，`state.yaml` 是唯一动态恢复状态权威。
- 唯一 runtime helper 是 `plugins/nuclio-plugin/scripts/change.py`；不得新增 `workflow.py` 或第二套 State writer。
- 产品 mutation 和 `init-state` 前必须有用户可理解的 file-first Spec/Plan、`validate-plan` 成功结果和自然语言批准。
- 固定 token、哈希、approval JSON 和身份短语都不是 v2 日常批准要求。
- Plan 使用 change-level `allowed_paths`，不创建 per-Task files ownership、owner mapping 或 finding owner routing。
- 每个实施 Task 和每个 approved repair 恰好一个 selective-stage checkpoint commit。
- State 只保存当前恢复事实，不保存完整 transition history、diff、测试日志、agent transcript 或文件内容 snapshot。
- 恢复先使用 `change.py status` 与 `change.py next-action`，再结合 Git 和确定性证据。
- 不创建 `.dev-docs/changes/index.md`。
- 不创建持久过程 JSON、隐藏运行时目录、MCP、daemon、runtime hook、项目级 `.claude/` 或 `.nuclio/`。
- 小型单 Task 可主会话直做；大型、多 Task 或跨模块 change 默认委派有界 generic subagent 单元。
- bounded subagent 不得调用 TaskStop/Stop Task，不得创建、更新、停止或接管 Controller/task-tracking 任务，不得尝试停止自身、父任务、兄弟任务或后台任务；完成、阻塞、超时或需要决策时只能返回 compact result 给主会话。
- 产品写入顺序执行；不得新增 DAG scheduler 或并行产品写入引擎。
- 不凭 agent claim 宣告完成或推进 State。
- deterministic validation 先于完成；review 不能替代失败的确定性校验。
- 产品结果报告后必须始终分析长期知识候选；长期知识必须通过稳定、可复用、非显然、已验证、可归属五问。
- 无合格知识候选时记录 `NO_OP` 且不显示第二 Gate。
- 有合格知识候选时必须等待用户确认；知识拒绝不影响产品完成、`complete` 或 archive，但精简历史 `change.md` 记录拒绝结果。
- File-first implementation Gate 必须披露 successful archive 只保留精简 `change.md`，active `plan.yaml`/`state.yaml` 不进入长期 archive。
- `complete` 后、`archive` 前必须把 `change.md` 蒸馏为含 completed frontmatter、Goal、Outcome、Validation、Knowledge Updates 的精简历史记录。
- Archive 成功后只保留 `.dev-docs/changes/archive/<id>/change.md`；不得长期保留 archived `plan.yaml`/`state.yaml`、隐藏备份或 archive manifest。
- Archive 必须在 destructive pruning 前验证 completed 或 superseded State、Plan/HEAD identity、精简历史形态、superseded successor takeover 语义、archive `related_changes` 与 `state.superseded_by` 一致和 exact artifact set；失败 fail closed 或报告 precise remaining artifacts。
- successor 成功归档后必须收口 predecessor：successor `change.md` backlink、`supersede` 写入 `state.superseded_by`、`ARCHIVE_SUPERSEDED`、与 State 一致的 predecessor archive `related_changes`、superseded Outcome/Validation 和 one-file archive 都必须成立。
- 不得按 `-v2` 名称、recency、聊天 transcript 或 predecessor 单向关联猜测 successor，不得 pre-link frozen predecessor、link-related、hash refresh/rebaseline 或手写 State，不得无 successor 强制归档，不得把 predecessor 旧 acceptance 伪装为成功。
- predecessor 收口失败必须报告残留 active predecessor 路径，不得宣称完全收口。
- Archive 和 legacy 默认不读；legacy 只能整体移动，不保留双栈。
