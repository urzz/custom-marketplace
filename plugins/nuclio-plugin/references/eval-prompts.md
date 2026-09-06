# Nuclio v3 Eval Prompts

以下 fresh-session 场景分别验证 Claude Code 与 Codex 的真实入口行为；Codex 使用 `$nuclio:init` / `$nuclio:work`，路径和交互遵循 `host-runtime.md`。Runtime 合同以 `change-format.md` 和 `change.py` 为准。

## Should Trigger

### 1. 普通 change

- **User Prompt**：`/nuclio:work 修复登录回跳并补测试`
- **Expected**：在当前模式直接进入 Shape；无 active change 的新建路径先按场景 2 完成调用起点快照、只读分析与分支隔离，才把 `create` 的单行种子补全为无需旧聊天也能理解、精简但信息完整的 `change.md`，再用一次宿主确认交互 确认结果合同；随后主会话自主 Build/Verify。
- **Assertions**：不调用 `EnterPlanMode` 或 `ExitPlanMode`；不直接批准只有单句概括的草稿；多个独立边界分别记录、Acceptance 原子且可观察；不要求批准 milestone、路径、Agent 或普通失败修复；检查由 宿主主会话直接执行，再以 `record-check` 记录。

### 2. 无 active change 的 Shape 与新建分支

- **Setup**：fresh-session；`.dev-docs/changes/` 不存在 active change 目录，或只存在 `archive/`；项目是 Git 仓库，当前 `main` 为 attached HEAD，调用起点 staged、unstaged 与 untracked 均为空，且本地和所有已配置 remote 的缓存 remote-tracking ref 均不存在 `fix/auth-redirect`。
- **User Prompt**：`/nuclio:work 修复登录回跳并补测试`
- **Expected**：通过 Plan Mode 边界后、discovery 前，主会话只读尝试捕获 Git/attached HEAD、`start_branch`、`start_head` 及调用起点三类 dirty 状态；不写入、不调用 Runtime、不做分支操作或联网。仅 discovery 确认无候选时，才要求该 snapshot 有效且起点 clean。随后只读调查请求、索引路由知识和仓库事实，确定合法 change ID `auth-redirect` 及 `fix` 类型；Shape 后复核当前 branch/HEAD 分别未偏离 `start_branch`/`start_head`，且工作区仍 clean。精确查询本地 `refs/heads/fix/auth-redirect`，列出全部本地配置 remote 并逐个精确查询 `refs/remotes/<remote>/fix/auth-redirect`，同时只读当前本地 `refs/remotes/**` 缓存快照；不得只查 `origin`、fetch、`ls-remote`、联网或刷新 refs。全部通过后执行：`git -C "${NUCLIO_PROJECT_DIR}" switch -c <type>/<change-id> <start-head>`。仅 post-switch 复核 branch 为 `fix/auth-redirect`、HEAD 为 `start_head` 且工作区 clean 成功后，才调用 Runtime `create`、生成并补全 `change.md`，再以一次宿主确认交互 确认结果合同；最终成功报告包含创建的分支名。
- **Assertions**：该 `git -C` switch 命令可观察地早于 Runtime `create` 和任何本次 change 或产品文件写入；不发起无 `--id` 的 `status --json`；不扫描或读取 archive；不依赖旧聊天或全量知识。

### 3. 恢复与失败修复

- **Setup**：fresh-session；`.dev-docs/changes/` 恰有一个 active change 目录；调用起点的 Git snapshot unavailable、detached HEAD 或工作区 dirty 均可分别覆盖。
- **User Prompt**：`/nuclio:work 恢复当前 change，检查失败则修好后完成`
- **Expected**：即使 snapshot unavailable、detached 或 dirty，也不在 discovery 前阻止恢复；以唯一目录名作为 change ID，先运行 `status --id <change-id> --json`，读取当前合同、milestone/handoff 和索引路由的相关知识；失败回到 Build。
- **Assertions**：不创建、不切换任何分支，不再次调用 `create`；不依赖旧聊天或全量知识；合同不变的修复不再询问用户；合同语义变化才重新确认。

### 4. 多个 active change

- **Setup**：fresh-session；`.dev-docs/changes/` 存在多个非 `archive/` 的 active change 目录；调用起点 snapshot unavailable、detached 或 dirty 不影响该场景。
- **User Prompt**：`/nuclio:work 继续交付`
- **Expected**：discovery 后报告候选目录并 fail closed。
- **Assertions**：不猜测 change ID、不调用 Runtime、不读取或修改 archive；不创建或切换分支；要求用户先解决歧义。

### 5. Open Design 绑定交付

- **Setup**：已加载的项目上下文保存一致且有效的 Open Design `project-id`，用户已配置对应 MCP。
- **User Prompt**：`/nuclio:work 按项目绑定的 Open Design 最终设计实现前端`
- **Expected**：Shape 条件读取 `open-design-handoff.md`，使用显式 ID 调用只读 `get_project` 与 `get_artifact(include="all")`，结合仓库事实形成结果合同；批准后才把交付固化到固定目录 `.dev-docs/artifacts/open-design/` 并实施。
- **Assertions**：不从 `.dev-docs/knowledge/`、active context 或项目名猜测绑定；不调用 Open Design 写入/生成工具；artifact 路径不含 UUID；完整交付不进入 knowledge；原型数据不成为生产事实；固化后恢复只读取仓库快照；视觉观察作为当前 HEAD 的 manual evidence。

### 6. 首次初始化

- **User Prompt**：`/nuclio:init 为这个项目建立 Nuclio 文档骨架`
- **Expected**：在当前模式仅在 `${NUCLIO_PROJECT_DIR}/.dev-docs/` 创建或安全修复索引、三个知识入口和 `changes/archive`。
- **Assertions**：不调用 `EnterPlanMode` 或 `ExitPlanMode`；不做调用起点 snapshot 或分支检查/创建，不调用 Runtime，不创建 change 三件套，不实现功能；完成后停止并建议显式使用 `/nuclio:work`。

### 7. 多文件阅读与测试诊断的 Build 派发

- **Setup**：fresh-session 中恰有一个 active change；`status` 表明当前 milestone 的支付回调修复与现有检查边界明确，已确认结果合同保持不变。
- **User Prompt**：`/nuclio:work 恢复当前 change，修复支付回调集成测试失败`
- **Expected**：主会话先只保留或读取 `status` 工作包、当前合同、milestone/handoff 和索引路由的相关知识，并先判断派发；保留合同、`delivery.yaml`、Runtime 和 Verify 控制。当前 milestone 需要阅读多个回调、服务、配置和测试文件，预计反复运行诊断检查并产生较多原始输出；支付子系统范围清晰且可验证，因此优先派发一个有界原生 Agent。主会话不预读委派范围的局部材料；agent 在支付子系统必要范围内吸收局部探索、测试诊断和原始输出，只短回传改动、检查和未完成项。
- **Assertions**：不以 token 或 ctx 数值硬阈值决定派发；主会话不预读委派范围的局部材料，包括局部代码、测试、配置或测试诊断；dispatch 仅含当前 milestone、相关 Acceptance、Constraints/Non-goals、handoff、相关知识路径及读取理由、必要范围和预期检查，不复制知识正文；agent 不调用 Skill、不继续委派、不接管 Runtime；主会话只处理短回传、milestone/handoff、Runtime 和 Verify，并执行最终验证和决定后续。

## Should Not Trigger

### 8. 单文件确定性 Build 不机械派发

- **Setup**：fresh-session 中恰有一个 active change；当前 milestone 只要求将单个已知超时常量从 `30` 改为 `60` 并运行既有检查，合同不变。
- **User Prompt**：`/nuclio:work 恢复当前 change，完成当前 milestone`
- **Expected**：主会话先基于紧凑控制信息判断该工作无需派发；范围限于一个文件且实现路径确定、无需探索或诊断时，主会话直接完成改动和检查，不为形式派发 Agent。
- **Assertions**：不因进入 Build 或存在 Agent 能力而机械委派；直接实施时主会话才读取相关代码、测试和配置；产品语义、兼容性或跨 milestone 架构取舍同样保留在主会话，必要时回到 Shape 或询问用户。

### 9. 仅咨询

- **User Prompt**：`Nuclio v3 的提案和用法是什么？`
- **Expected**：回答咨询，不触发 init 或 work。
- **Assertions**：不创建 `.dev-docs`，不调用 Runtime。

### 10. Skill/plugin 工作

- **User Prompt**：`帮我修改一个 Claude Code skill`
- **Expected**：不触发 Nuclio，路由至 Skill Forge。
- **Assertions**：不创建或恢复 Nuclio change。

### 11. init 越界请求

- **User Prompt**：`/nuclio:init 实现登录修复并归档当前 change`
- **Expected**：init 只处理安全骨架，拒绝产品实施、恢复、验证和归档。
- **Assertions**：提示用户显式使用 `/nuclio:work`。

### 12. 已处于 Plan Mode

- **Setup**：当前宿主已处于 Plan Mode（Claude Code 与 Codex 分别运行）。
- **User Prompt**：`/nuclio:work 修复登录回跳并补测试`，或 `/nuclio:init 为这个项目建立 Nuclio 文档骨架`。
- **Expected**：立即 fail closed，要求用户先退出 Plan Mode 后重新显式调用对应 Nuclio Skill。
- **Assertions**：不调用 `EnterPlanMode` 或 `ExitPlanMode`；work 不做调用起点 snapshot、不创建或恢复 change、不调用 Runtime、不检查或创建分支；init 不做 snapshot/分支操作，也不写入知识骨架。

## Boundary checks

### 13. Relocated plugin cache

- **Setup**：从临时 Marketplace cache 风格插件目录调用 Skill，当前目录不是插件源码仓库。
- **Assertions**：每个 Runtime 调用使用 `python3 "${NUCLIO_SKILL_DIR}/../../scripts/change.py" --project-root "${NUCLIO_PROJECT_DIR}" ...`；运行时写入只在项目 `.dev-docs/**`，cache 不写入。

### 14. Reviewer permissions

- **User Prompt**：要求 `nuclio:readonly-reviewer` 实现、写文件、运行 shell、调用 Skill 或委派其他 agent。
- **Expected**：reviewer 只用 Read、Grep、Glob 审查相关材料并返回 findings，或在无法审查时 `CANNOT_VERIFY`。
- **Assertions**：frontmatter 工具精确为 `Read, Grep, Glob`；没有 Bash、写入、Skill、Agent 或继续委派能力。

### 15. Open Design 输入不可用

- **Setup**：项目上下文绑定缺失或冲突、MCP 未配置、workspace 授权失败、返回截断且无法补齐，或二进制依赖没有内容。
- **User Prompt**：`/nuclio:work 实现已绑定的 Open Design 设计`
- **Expected**：Shape 报告 blocker，并要求修复 MCP 或提供显式导出目录。
- **Assertions**：不扫描 `.od`，不退回 active context，不创建产品快照，不开始实现，也不调用任何 Open Design 写入工具。

### 16. 调用起点 dirty 即使随后清理仍阻塞新建

- **Setup**：fresh-session；调用起点不存在 active change；attached HEAD 下 staged、unstaged、untracked 中任一项存在改动，但外部在 Shape 期间将工作区清理。
- **User Prompt**：`/nuclio:work 修复登录回跳并补测试`
- **Expected**：Plan Mode 通过后、discovery 前只读 snapshot 捕获调用起点 dirty；discovery 确认无候选后，仍以起点 dirty 报告阻塞并 fail closed，不因当前工作区后来 clean 而继续 Shape 或新建。
- **Assertions**：覆盖 staged、unstaged、untracked 三种独立合同；不执行 `git -C "${NUCLIO_PROJECT_DIR}" switch -c <type>/<change-id> <start-head>`，不调用 Runtime `create`，不写入本次 `change.md`、三件套或产品文件；不自动 stash、commit、reset 或 clean。

### 17. Shape 期间起点漂移与 switch 后异常

- **Setup**：fresh-session；调用起点无 active change、attached HEAD 且 clean，已捕获 `start_branch`/`start_head`。子场景 A：只读 Shape 期间当前 branch 或 HEAD 被外部改变。子场景 B：switch 成功后当前 branch、HEAD 或任一 dirty 类别异常。
- **User Prompt**：`/nuclio:work 修复登录回跳并补测试`
- **Expected**：A 在创建前复核发现 branch/HEAD 偏离 snapshot 时 fail closed。B 走“分支可能已创建”的部分成功路径，停止且报告实际分支事实，不回滚 Git 状态。
- **Assertions**：A 不执行 switch；A 与 B 均不调用 Runtime `create`，不写入本次 `change.md`、三件套或产品文件；B 不自动删除分支、切回原分支、reset 或 clean。

### 18. 本地或所有 remote 缓存同名 ref 阻塞新建

- **Setup**：fresh-session；不存在 active change，调用起点 attached 且 clean，已只读分析并确定合法 `<type>/<change-id>`；子场景分别在精确本地 `refs/heads/<type>/<change-id>`、任一已配置 remote 的缓存 `refs/remotes/<remote>/<type>/<change-id>`，或当前本地 `refs/remotes/**` 快照中存在同名 ref。
- **User Prompt**：`/nuclio:work 修复登录回跳并补测试`
- **Expected**：列出全部本地配置 remote，并仅查询当前本地缓存 refs；任一精确冲突均报告同名分支冲突并 fail closed，不自动改名、追加后缀或切换到已存在分支。
- **Assertions**：不只检查 `origin`；不得 `git fetch`、`git ls-remote`、联网或刷新 refs；不执行 `git -C "${NUCLIO_PROJECT_DIR}" switch -c <type>/<change-id> <start-head>`，不调用 Runtime `create`，不写入本次 `change.md`、三件套或产品文件。

### 19. 显式 ID 恢复归档中断

- **Setup**：`alpha-change` 已 complete；archive 移动成功、提交失败，只有 `.dev-docs/changes/archive/alpha-change/`，调用起点 dirty，active 候选为空。
- **User Prompt**：`/nuclio:work 恢复并归档 alpha-change`
- **Expected**：只定点检查用户提供 ID 的 archive 目录，直接运行 `archive --id alpha-change`，由 Runtime 复核终态并完成提交。
- **Assertions**：不因新建的起点 clean 要求阻塞，不调用 active `status`、`create` 或分支操作，不遍历其他 archive。未提供 ID 时要求用户明确目标；存在其他 active 时报告冲突，多个 active 仍停止。目标已提交且 HEAD 后来变化时只确认既有 archive commit，不新建提交。

### 20. 批准提交后的 State 回写中断

- **Setup**：唯一 active change；Git 中已有对应 approval commit，工作区 State 的 `phase=build`、`approval_head=null`。
- **User Prompt**：`/nuclio:work 恢复 alpha-change`
- **Expected**：读取 status 的 `recover-approval`，重跑 `approve --id alpha-change` 后重新读取状态。
- **Assertions**：不先执行检查或 verify，不重复询问已提交的合同，不创建第二个批准提交；合同或产品工作区漂移仍停止。

### 21. 手工观察失败与旧证据

- **Setup**：A：手工观察发现 AC-1 未实现，即使自动检查和 reviewer 对它提供 PASS。B：旧 v3 State 的 manual 记录缺少 `status`。
- **User Prompt**：`/nuclio:work 验证当前 change 并完成交付`
- **Expected**：A 以显式 `status=FAIL` 记录观察并回到 Build。B 不采用旧记录为通过依据，重新观察后用包含 `status` 的完整批次替换。
- **Assertions**：只把 `PASS` 作为通过证据；`manual_blocker` 非空时不 complete/archive，不从 `result` 自由文本猜测状态。

### 22. 路径与归档写入边界

- **Setup**：分别使用 Git 仓库子目录项目、中文知识文件、`.dev-docs/changes` 指向产品目录的符号链接、被忽略的 archive 目标，以及 complete 后已撤销的知识改动。
- **Expected**：子目录项目保持明确边界并可完成全流程；中文路径正常提交。符号链接、忽略目标及知识路径漂移在写入或移动前停止，报告对应路径。
- **Assertions**：不更改项目根目录，不写入符号链接目标，不留下部分暂存；实际使用 shell 时 `for-each-ref` 的 format 参数有正确引号。归档三件套被修改后重试应报告内容漂移并保留文件，不宣称成功。
