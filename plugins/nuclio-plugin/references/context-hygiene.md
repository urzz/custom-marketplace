# Nuclio v3 Context Hygiene

按问题读取权威，不用聊天记录、完整知识库或 Runtime State 副本填充上下文。`.dev-docs/index.md` 是长期知识的唯一入口：索引说明路径、摘要和读取时机，不承载知识正文。

## Phase read order

- **Shape**：所有 Git 命令均显式使用 `git -C "${NUCLIO_PROJECT_DIR}" ...`，不依赖当前目录。通过 Plan Mode fail-closed 边界后、active change discovery 前，立即只读运行 `git -C "${NUCLIO_PROJECT_DIR}" status --porcelain=v2 --branch -z --untracked-files=all`：从可解析输出记录 Git 仓库与 attached `HEAD` 是否可用；可用时捕获 `start_branch`、`start_head`，并观察起点 staged、unstaged、untracked 是否均为空。命令或解析异常为 snapshot unavailable。不写文件、不调用 Runtime、也不进行网络、远程或分支操作 -> 仅检查 active change 候选。快照 unavailable 或起点 dirty 不得阻止 discovery。若有唯一或多个候选，丢弃快照并走既有恢复或歧义路径，绝不创建或切换分支。无候选时先处理显式归档恢复例外；需要新建时，才要求有效 attached snapshot 和调用起点 staged、unstaged、untracked 均为空；否则 fail closed，即使 Shape 期间外部清理工作区也不得新建。然后继续：用户请求与项目规则 -> `index.md` -> 有明确相关性的知识文件/heading -> 相关代码、测试、配置和仓库事实 -> 确定合法 `<change-id>` 和类型（仅 `feat`、`fix`、`refactor`、`docs`、`test`、`chore`，无法明确时为 `feat`）。每个调查开始前按独立性、上下文隔离收益和协调成本判断直接调查或积极委派；由模型自主拆成互斥、有停止条件且只回答当前合同缺口的调查包，复用已有结论而不派发重叠调查。委派后的范围排他、原生等待、短回传和失败恢复遵循下文。这全程只读；完成 Shape 后，重新运行同一 `git -C ... status` 命令，核对 branch/HEAD 分别仍等于快照且工作区仍 clean；完成本地精确 ref 检查并成功执行 `git -C "${NUCLIO_PROJECT_DIR}" switch -c <type>/<change-id> <start-head>` 前，不写本次 change 或产品文件。switch 成功后还必须按 workflow 完成 post-switch branch/HEAD/clean 与 remote-ref 校验，才能 `create`。
- **Build / recovery**：主会话先保留或读取紧凑控制信息：`status --id <change-id> --json` 工作包、当前合同、milestone/handoff 和由 `.dev-docs/index.md` 路由的相关知识 -> 在读取局部实现或诊断前，按独立性、隔离收益和协调成本判断直接执行或积极委派，由模型自主拆分。派发只传当前控制信息、相关知识路径及读取理由和可独立验收的必要范围，不复制知识正文。若派发：代理读取必要代码、测试和配置，吸收局部探索、测试诊断和原始输出；活动范围对主会话排他，主会话只接收短回传并做定点验收或目的明确的独立复核。若直接实施：主会话才读取相关代码、测试和配置并实施。
- **Verify**：批准合同、delivery、稳定候选的当前 diff、检查与观察优先；主会话运行 exact checks，只保留命令、exit code 和短摘要。失败即回 Build；需要大输出或多文件诊断时优先隔离委派，简单明确失败可直接修复。相关知识仅提供稳定约束，不能替代验证依据。
- **Finish**：产品结果与 diff -> 索引路由的受影响知识，用同一次分析判断新增候选和既有结论是否失效。

除非问题明确需要，不读取整个 `.dev-docs/knowledge/**`、archive、legacy、全部 State 或完整 Git diff。先使用 `status --json`，只在漂移或诊断时扩展到精确 Git 状态和相关 artifact。

## Shape 与 recovery 路由

通过 Plan Mode 边界后，fresh session 先完成上述只读调用起点 snapshot，再检查 `${NUCLIO_PROJECT_DIR}/.dev-docs/changes/` 的直接子目录并排除 `archive/`；snapshot 不得提前阻塞已有 active change 的发现与恢复：

先处理显式归档恢复例外：无 active 候选且用户当前明确提供恢复/归档 ID 时，仅定点检查 `.dev-docs/changes/archive/<change-id>/`，存在则直接执行 `archive --id <change-id>`；不进入下述新建的起点 clean 和分支流程，也不调用 active `status`。不存在则报告未找到，不改走新建。用户没有明确 ID 时要求其给出，不从 Git dirty 路径、旧聊天或 archive 列表猜测；多个 active 仍 fail closed，显式 ID 与唯一 active 不一致时报告冲突。

- 无候选：不存在 active change 时，不调用 `status`；先要求调用起点的有效 attached snapshot 以及起点 staged、unstaged、untracked 均为空，再继续只读 Shape 调查并确定 `<change-id>` 与类型。随后用 `git -C "${NUCLIO_PROJECT_DIR}" status --porcelain=v2 --branch -z --untracked-files=all` 重新读取 branch 和 `HEAD`；输出必须可解析，二者必须分别仍等于 `start_branch` 和 `start_head`，且 staged、unstaged、untracked 仍均为空。以 `git -C "${NUCLIO_PROJECT_DIR}" show-ref --verify --quiet refs/heads/<type>/<change-id>` 检查本地精确 ref（exit `0` 冲突、exit `1` 不存在、其他 exit fail closed）。用 `git -C "${NUCLIO_PROJECT_DIR}" remote` 读取全部本地配置 remote，并对每个 remote 以相同 `show-ref --verify --quiet` 语义检查精确缓存 remote-tracking ref。再以 `git -C "${NUCLIO_PROJECT_DIR}" for-each-ref --format="%(refname)" refs/remotes/` 读取本地缓存全集，并与全部已配置 remote 构造的完整目标 refname 集合精确比较，不能只检查 `origin`。命令或解析异常 fail closed；不刷新 refs，也不调用网络或远程操作。成功执行 `git -C "${NUCLIO_PROJECT_DIR}" switch -c <type>/<change-id> <start-head>` 后，还须用同一 `status` 与 `for-each-ref` 命令完成 post-switch 当前 branch、`HEAD`、clean 与 remote-ref 校验，才可在需要时 `create`。
- 恰有一个候选：以其目录名作为 `<change-id>`，再运行：

  ```bash
  python3 "${NUCLIO_SKILL_DIR}/../../scripts/change.py" --project-root "${NUCLIO_PROJECT_DIR}" status --id <change-id> --json
  ```

- 多个候选：fail closed，报告候选目录并要求用户解决歧义；不得猜测 ID、调用 Runtime 或读取 archive。

唯一候选的 `status` 返回后，再核对当前合同、milestone/handoff、HEAD、工作区和相关检查。Runtime 工作包、Git、代码、合同和长期知识各自回答不同问题；冲突时回到对应权威，而非采信旧消息。

`next_action=recover-approval` 时直接重跑 `approve --id <change-id>` 恢复已提交批准，再读取 status；不得沿用缺失批准时的检查或重复确认同一合同。`manual_blocker` 与 `review_blocker` 一样先回到 Build 处理。手工记录缺少显式 `PASS|FAIL` 状态时不作为通过依据，按 `change-format.md` 重做观察。

## Agent and reviewer

主会话仍是唯一控制器，独占用户 Gate、结果合同判断、`delivery.yaml` 维护、Runtime 调用、最终验证、知识决定、`complete` 和 `archive`；产品写入保持顺序。每个 Shape 调查和 Build/返修工作包开始前，主会话都获得条件性积极委派的明确授权，由模型按工作独立性、上下文隔离收益和协调成本自主决定拆分，不使用 token/ctx 硬阈值，也不依赖模型名、具体工具、固定代理数量或自动委派模式。多文件/多模块调查、大输出失败诊断、可独立验收实现轨道、只需摘要的工作和 fresh-context review，在能改善速度、覆盖或上下文质量时应积极委派；少量工具调用、单文件小改、紧密顺序依赖、共享资源争用或需要持续共享上下文时直接执行。产品语义、兼容性、权限、外部副作用、不可逆结果、跨 milestone 架构取舍、用户交互、Runtime、Verify、Finish 等控制决定也由主会话处理，不为形式而派发。

工作包必须覆盖相关 Acceptance、Constraints/Non-goals、必要路径边界、实现、集成接缝、预期 changed paths 和 exact checks，使其可独立交付与验收；dispatch 只传紧凑控制信息、相关知识路径及读取理由，不复制完整知识正文。代理不调用 Skill、不继续委派、不接管 Runtime。代理活动期间，其产品路径和诊断主题对主会话排他：主会话不读取、编辑、写入、运行同题诊断或重复派发；可以处理明确不重叠的控制工作，并可为验收定点核对必要证据或执行目的明确的独立复核，但不得借机吸收完整调查。真正依赖结果时使用宿主完成通知或原生等待，禁止 shell `sleep`、Git 状态或反复消息轮询和催促。

代理回传最多 15 行，只使用 `status`、`changed`、`checks`、`handoff`、`concerns`；`status` 仅为 `DELIVERED|BLOCKED`。代码、搜索过程、日志和完整测试输出留在代理上下文，但必须保留 Controller 决策所需的文件、检查和错误定位。`BLOCKED`、异常、超时或缺少合格回传时优先 resume；不可 resume 或范围不再合适时缩小/重切或重新委派。主会话只有在重新判断共享上下文收益高于隔离收益后才能接管，并在 handoff 写一句理由，不得静默重复宽范围探索。无原生代理时按同一工作包顺序直做；其他能力降级遵循 `host-runtime.md`，不得跨宿主调用 CLI 或模拟能力。

独立 reviewer 派发前，主会话必须确定性预检明确审查问题、合同、当前 HEAD、changed paths、`readonly-review.md` 和必要材料均已提供；reviewer 只返回 findings。只读限制必须由宿主真实强制；无法满足时报告 `CANNOT_VERIFY: isolated read-only reviewer unavailable`，不得以自然语言约束或主会话自检冒充独立审查。独立审查按风险和 oracle 需要选择，不是 per-milestone 协议。

## Output

优先报告产品 outcome、changed paths、检查/exit code、关键失败或 archive 事实。switch 成功后，先保留 `start_branch` 与 `start_head` 完成 post-switch 校验；只有校验成功后才丢弃它们。创建的分支名只保留在主会话本次调用的瞬时控制信息中，不写入 Runtime、State、artifact 或 knowledge。post-switch 异常或 `create` 失败的部分成功报告，以及同一调用最终成功报告，都必须包含该分支名；恢复调用没有创建分支时不得声称创建了分支。Finish 最终报告还包含新建调用所创建的分支名（如适用）。知识 proposal 与产品结果分开；一次知识决定后连续完成和归档。不要向 `state.yaml` 写完整 diff、日志、transcript、agent message、snapshot 或事件账本。
