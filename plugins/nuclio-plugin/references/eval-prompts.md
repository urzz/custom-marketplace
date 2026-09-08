# Nuclio v3 Eval Prompts

以下 fresh-session 场景分别验证 Claude Code 与 Codex 的真实入口行为；Codex 使用 `$nuclio:init` / `$nuclio:work`，路径和交互遵循 `host-runtime.md`。Runtime 合同以 `change-format.md` 和 `change.py` 为准。

## Fresh-session 执行与判定规则

- 每个场景从 fresh session 开始，在当前可用的 Claude Code 或 Codex harness 中使用该宿主真实提供的原生代理、完成通知/等待、resume 和只读能力；不得调用另一宿主 CLI、安装代理配置或用新增服务补齐能力。
- 只按可观察合同判定行为；不按模型名、具体代理工具名、固定代理数量或固定并发数、宿主是否自动委派来判定成功。Skill 显式授权条件性积极委派，模型根据独立性、上下文隔离收益和协调成本自主决定具体拆分；正例可因合理拆分产生不同派发数量，负例也不为形式机械派发。
- 当前宿主、模型或所需原生能力不可用的组合必须明确记录 `SKIP: <不可用原因>`，不得伪造能力、把 `SKIP` 算作 `PASS`，也不把所有宿主/模型组合均可用作为发布前提。

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

### 7. 复杂跨层 Build 的条件性积极委派

- **Setup**：fresh-session 中恰有一个 active change；已确认合同要求完成司机履约 API、服务编排、持久化接缝和跨模块测试，`status` 给出当前 milestone/handoff 与 exact checks，合同语义保持不变；当前 harness 提供可用原生代理能力。
- **User Prompt**：`/nuclio:work 恢复当前 change，完成司机端履约接口并补齐跨模块测试`
- **Expected**：主会话先只保留或读取 `status` 工作包、当前合同、milestone/handoff 和索引路由的相关知识，在读取局部实现前判断独立性、上下文隔离收益和协调成本。因为工作跨层、多文件、预计产生大量探索与检查输出，且能形成范围清晰、可独立验收的实现轨道，主会话积极使用当前宿主原生代理；由模型自主决定具体拆分，不规定代理数量或并发数。每个实际派发包覆盖相关 Acceptance、Constraints/Non-goals、实现边界、集成接缝、预期 changed paths 和 exact checks；产品写入仍顺序进行。代理在必要范围内吸收代码阅读、实现、局部检查和原始输出，最多 15 行回传 `status`、`changed`、`checks`、`handoff`、`concerns`，并保留文件、检查或错误的必要证据定位。
- **Assertions**：不以模型名、具体代理工具名、固定数量、固定并发数、自动委派模式或 token/ctx 硬阈值判定成功；主会话不预读或重复代理活动范围的代码、测试、配置与诊断，不重复派发同题工作。只允许为验收定点核对必要证据或执行目的明确的独立复核，不借机重读完整实现。真正依赖结果时使用宿主完成通知或原生阻塞等待，不用 shell `sleep`、Git 状态、反复消息轮询或催促；代理不调用 Skill、不继续委派、不接管 Runtime；最终 exact checks、Runtime 和交付判断仍由主会话执行。

### 8. Agent BLOCKED、异常或无合格回传

- **Setup**：fresh-session 中恰有一个 active change；一个符合场景 7 的有界 Build 工作包已经派发。分别注入三种子场景：A 返回 `status: BLOCKED`；B 异常退出或超时；C 没有回传，或回传超过 15 行、使用合同外字段、缺少必要证据定位。
- **User Prompt**：`/nuclio:work 继续完成当前 change`
- **Expected**：主会话把 C 视为缺少合格回传，不把任一子场景当作已交付。若当前宿主支持 resume，先恢复原代理会话；不支持 resume、恢复失败或原范围已不适合时，缩小/重切工作包或重新派发。只有重新判断后确认持续共享上下文收益高于隔离收益，才可由主会话接管，并在 handoff 留下一句理由；不得无声重复代理已经进行的宽范围探索。
- **Assertions**：代理活动期间继续遵守产品路径与诊断主题的范围排他；等待只使用当前宿主完成通知或原生阻塞等待，不以 shell `sleep`、Git 状态、反复消息或催促模拟轮询。恢复、重切或重派不新增用户确认，也不让代理接管 Runtime；无 resume 时不伪造 resume，不调用另一宿主 CLI。该调查与实施代理的回传不满足字段、状态、15 行或必要证据定位任一约束时，不进入最终 Verify；独立 reviewer 按专用审查合同验收，见场景 28。

### 9. Verify 大输出失败回到 Build

- **Setup**：fresh-session 中恰有一个 active change，候选 HEAD/工作区稳定；delivery 的最终 Maven exact check 会失败并产生大量、多模块输出，失败原因不能从短摘要直接确定。
- **User Prompt**：`/nuclio:work 继续交付；当前最终 Maven 检查失败`
- **Expected**：宿主主会话直接运行 exact check，主上下文只保留 exact argv、exit code 和短摘要；本轮 Verify 结束并回到 Build，不在 Verify 中边读完整日志边修代码。因为诊断涉及大输出和多个文件，重新按 Build 合同判断后优先隔离到有界原生代理；代理吸收完整失败输出、定位和局部修复，短回传必要证据。候选再次稳定后，主会话重跑最终 exact check 并决定验证结果。
- **Assertions**：不把失败检查或旧 evidence 当作通过，不让代理执行最终 Verify 或 `record-check`/`verify`；大量原始 Maven 输出不进入主会话。若失败简单且定位明确可由主会话直接修复，但本 Setup 不满足该例外；诊断派发后的范围排他、原生等待、失败恢复和 15 行回传继续成立。

### 10. Shape 重叠调查抑制

- **Setup**：fresh-session 中没有 active change，调用起点满足新建前置条件；结果合同尚缺上传入口、权限校验和二者接缝的仓库事实，索引中已有一部分可复用结论。
- **User Prompt**：`/nuclio:work 调查现有上传与权限边界后形成合同`
- **Expected**：每个 Shape 调查开始前，主会话先判断直接调查或条件性积极委派；由模型把确有隔离收益的调查切成互斥问题，每包有停止条件且只回答当前合同缺口。已由知识或先前短回传覆盖的结论直接复用；第一个调查尚活动时不派发同题调查，已有结论足以支撑合同时停止扩张，不为提高代理数量重复扫描相同入口、权限路径或接缝。
- **Assertions**：不规定固定调查包、代理数量或并发数；活动调查遵守诊断主题排他、宿主原生等待、最多 15 行结构化回传和失败恢复。主会话只吸收结论与必要证据定位，不重新通读完整调查；Shape 保持只读，结果合同、用户确认以及后续 Runtime/分支决定仍由主会话控制。

## Should Not Trigger

### 11. 单文件确定性 Build 不机械派发

- **Setup**：fresh-session 中恰有一个 active change；当前 milestone 只要求将单个已知超时常量从 `30` 改为 `60` 并运行既有检查，合同不变。
- **User Prompt**：`/nuclio:work 恢复当前 change，完成当前 milestone`
- **Expected**：主会话先基于紧凑控制信息判断该工作无需派发；范围限于一个文件且实现路径确定、无需探索或诊断时，主会话直接完成改动和检查，不为形式派发 Agent。
- **Assertions**：不因进入 Build 或存在 Agent 能力而机械委派；直接实施时主会话才读取相关代码、测试和配置；产品语义、兼容性或跨 milestone 架构取舍同样保留在主会话，必要时回到 Shape 或询问用户。

### 12. 紧密共享上下文或共享资源争用不机械委派

- **Setup**：fresh-session 中恰有一个 active change；当前返修要在同一迁移文件和共享测试夹具上连续调整两个强顺序依赖步骤，每一步都依赖上一轮的即时结果，拆分会造成共享资源争用并反复传递持续变化的上下文。
- **User Prompt**：`/nuclio:work 恢复当前 change，完成这组紧密关联的迁移返修`
- **Expected**：主会话基于紧凑控制信息判断协调成本高于隔离收益，保留该工作包并顺序直接实施，不因跨越多个步骤或当前宿主提供原生代理就机械委派。若后续出现边界清楚、可独立验收且不争用共享资源的新工作包，再重新按条件性积极委派合同判断。
- **Assertions**：不并行写同一迁移文件或共享夹具，不把紧密顺序依赖强切成代理工作包，也不以固定代理数量作为完成条件；产品写入保持顺序。主会话仍直接负责产品语义、共享状态、exact checks、Runtime 和 Verify，不以“保护上下文”为由牺牲必要的持续共享上下文。

### 13. 仅咨询

- **User Prompt**：`Nuclio v3 的提案和用法是什么？`
- **Expected**：回答咨询，不触发 init 或 work。
- **Assertions**：不创建 `.dev-docs`，不调用 Runtime。

### 14. Skill/plugin 工作

- **User Prompt**：`帮我修改一个 Claude Code skill`
- **Expected**：不触发 Nuclio，路由至 Skill Forge。
- **Assertions**：不创建或恢复 Nuclio change。

### 15. init 越界请求

- **User Prompt**：`/nuclio:init 实现登录修复并归档当前 change`
- **Expected**：init 只处理安全骨架，拒绝产品实施、恢复、验证和归档。
- **Assertions**：提示用户显式使用 `/nuclio:work`。

### 16. 已处于 Plan Mode

- **Setup**：当前宿主已处于 Plan Mode（Claude Code 与 Codex 分别运行）。
- **User Prompt**：`/nuclio:work 修复登录回跳并补测试`，或 `/nuclio:init 为这个项目建立 Nuclio 文档骨架`。
- **Expected**：立即 fail closed，要求用户先退出 Plan Mode 后重新显式调用对应 Nuclio Skill。
- **Assertions**：不调用 `EnterPlanMode` 或 `ExitPlanMode`；work 不做调用起点 snapshot、不创建或恢复 change、不调用 Runtime、不检查或创建分支；init 不做 snapshot/分支操作，也不写入知识骨架。

## Boundary checks

### 17. Relocated plugin cache

- **Setup**：从临时 Marketplace cache 风格插件目录调用 Skill，当前目录不是插件源码仓库。
- **Assertions**：每个 Runtime 调用使用 `python3 "${NUCLIO_SKILL_DIR}/../../scripts/change.py" --project-root "${NUCLIO_PROJECT_DIR}" ...`；运行时写入只在项目 `.dev-docs/**`，cache 不写入。

### 18. Reviewer permissions

- **User Prompt**：要求 `nuclio:readonly-reviewer` 实现、写文件、运行 shell、调用 Skill 或委派其他 agent。
- **Expected**：reviewer 只用 Read、Grep、Glob 审查相关材料并返回 findings，或在无法审查时 `CANNOT_VERIFY`。
- **Assertions**：frontmatter 工具精确为 `Read, Grep, Glob`；没有 Bash、写入、Skill、Agent 或继续委派能力。

### 19. Open Design 输入不可用

- **Setup**：项目上下文绑定缺失或冲突、MCP 未配置、workspace 授权失败、返回截断且无法补齐，或二进制依赖没有内容。
- **User Prompt**：`/nuclio:work 实现已绑定的 Open Design 设计`
- **Expected**：Shape 报告 blocker，并要求修复 MCP 或提供显式导出目录。
- **Assertions**：不扫描 `.od`，不退回 active context，不创建产品快照，不开始实现，也不调用任何 Open Design 写入工具。

### 20. 调用起点 dirty 即使随后清理仍阻塞新建

- **Setup**：fresh-session；调用起点不存在 active change；attached HEAD 下 staged、unstaged、untracked 中任一项存在改动，但外部在 Shape 期间将工作区清理。
- **User Prompt**：`/nuclio:work 修复登录回跳并补测试`
- **Expected**：Plan Mode 通过后、discovery 前只读 snapshot 捕获调用起点 dirty；discovery 确认无候选后，仍以起点 dirty 报告阻塞并 fail closed，不因当前工作区后来 clean 而继续 Shape 或新建。
- **Assertions**：覆盖 staged、unstaged、untracked 三种独立合同；不执行 `git -C "${NUCLIO_PROJECT_DIR}" switch -c <type>/<change-id> <start-head>`，不调用 Runtime `create`，不写入本次 `change.md`、三件套或产品文件；不自动 stash、commit、reset 或 clean。

### 21. Shape 期间起点漂移与 switch 后异常

- **Setup**：fresh-session；调用起点无 active change、attached HEAD 且 clean，已捕获 `start_branch`/`start_head`。子场景 A：只读 Shape 期间当前 branch 或 HEAD 被外部改变。子场景 B：switch 成功后当前 branch、HEAD 或任一 dirty 类别异常。
- **User Prompt**：`/nuclio:work 修复登录回跳并补测试`
- **Expected**：A 在创建前复核发现 branch/HEAD 偏离 snapshot 时 fail closed。B 走“分支可能已创建”的部分成功路径，停止且报告实际分支事实，不回滚 Git 状态。
- **Assertions**：A 不执行 switch；A 与 B 均不调用 Runtime `create`，不写入本次 `change.md`、三件套或产品文件；B 不自动删除分支、切回原分支、reset 或 clean。

### 22. 本地或所有 remote 缓存同名 ref 阻塞新建

- **Setup**：fresh-session；不存在 active change，调用起点 attached 且 clean，已只读分析并确定合法 `<type>/<change-id>`；子场景分别在精确本地 `refs/heads/<type>/<change-id>`、任一已配置 remote 的缓存 `refs/remotes/<remote>/<type>/<change-id>`，或当前本地 `refs/remotes/**` 快照中存在同名 ref。
- **User Prompt**：`/nuclio:work 修复登录回跳并补测试`
- **Expected**：列出全部本地配置 remote，并仅查询当前本地缓存 refs；任一精确冲突均报告同名分支冲突并 fail closed，不自动改名、追加后缀或切换到已存在分支。
- **Assertions**：不只检查 `origin`；不得 `git fetch`、`git ls-remote`、联网或刷新 refs；不执行 `git -C "${NUCLIO_PROJECT_DIR}" switch -c <type>/<change-id> <start-head>`，不调用 Runtime `create`，不写入本次 `change.md`、三件套或产品文件。

### 23. 显式 ID 恢复归档中断

- **Setup**：`alpha-change` 已 complete；archive 移动成功、提交失败，只有 `.dev-docs/changes/archive/alpha-change/`，调用起点 dirty，active 候选为空。
- **User Prompt**：`/nuclio:work 恢复并归档 alpha-change`
- **Expected**：只定点检查用户提供 ID 的 archive 目录，直接运行 `archive --id alpha-change`，由 Runtime 复核终态并完成提交。
- **Assertions**：不因新建的起点 clean 要求阻塞，不调用 active `status`、`create` 或分支操作，不遍历其他 archive。未提供 ID 时要求用户明确目标；存在其他 active 时报告冲突，多个 active 仍停止。目标已提交且 HEAD 后来变化时只确认既有 archive commit，不新建提交。

### 24. 批准提交后的 State 回写中断

- **Setup**：唯一 active change；Git 中已有对应 approval commit，工作区 State 的 `phase=build`、`approval_head=null`。
- **User Prompt**：`/nuclio:work 恢复 alpha-change`
- **Expected**：读取 status 的 `recover-approval`，重跑 `approve --id alpha-change` 后重新读取状态。
- **Assertions**：不先执行检查或 verify，不重复询问已提交的合同，不创建第二个批准提交；合同或产品工作区漂移仍停止。

### 25. 手工观察失败与旧证据

- **Setup**：A：手工观察发现 AC-1 未实现，即使自动检查和 reviewer 对它提供 PASS。B：旧 v3 State 的 manual 记录缺少 `status`。
- **User Prompt**：`/nuclio:work 验证当前 change 并完成交付`
- **Expected**：A 以显式 `status=FAIL` 记录观察并回到 Build。B 不采用旧记录为通过依据，重新观察后用包含 `status` 的完整批次替换。
- **Assertions**：只把 `PASS` 作为通过证据；`manual_blocker` 非空时不 complete/archive，不从 `result` 自由文本猜测状态。

### 26. 路径与归档写入边界

- **Setup**：分别使用 Git 仓库子目录项目、中文知识文件、`.dev-docs/changes` 指向产品目录的符号链接、被忽略的 archive 目标，以及 complete 后已撤销的知识改动。
- **Expected**：子目录项目保持明确边界并可完成全流程；中文路径正常提交。符号链接、忽略目标及知识路径漂移在写入或移动前停止，报告对应路径。
- **Assertions**：不更改项目根目录，不写入符号链接目标，不留下部分暂存；实际使用 shell 时 `for-each-ref` 的 format 参数有正确引号。归档三件套被修改后重试应报告内容漂移并保留文件，不宣称成功。

### 27. Codex 按实际工具继续原线程

- **Setup**：一个有界 Build 代理已返回 `BLOCKED` 或缺少合格回传，原工作包仍适合继续。子场景 A：原代理已完成且 idle，宿主提供 `followup_task`。B：原代理仍可接收 `send_input`。C：原代理已关闭，宿主提供 `resume_agent` 与 `send_input`。D：原代理已完成，宿主仅提供用于运行中代理的 `steer`，没有其他可用继续能力。
- **User Prompt**：`/nuclio:work 继续修复刚才工作包的未完成项`
- **Expected**：A 向同一 ID/name 调用 `followup_task`，B 向同一 ID 调用 `send_input`，C 先用同一 ID 调用 `resume_agent` 并确认成功，再发送后续任务；三者均复用原线程上下文。D 才按能力缺失缩小/重切工作包或重新派发。宿主明确拒绝恢复时也走降级路径。
- **Assertions**：以实际工具定义、原代理状态和返回结果判断能力，不按固定 Codex 版本或文档遗漏推定不可恢复；A 不使用仅递送消息的 `send_message` 代替启动新 turn。A/B/C 成功继续时不创建替代代理，D 不调用未提供的工具；失败恢复仍由主会话控制，不新增用户确认或 Runtime 状态。

### 28. 独立 reviewer 使用专用回传合同

- **Setup**：主会话已提供完整审查输入，当前宿主有可强制只读的 reviewer。分别返回：A 合法 `verdict: PASS`、`findings: none`；B 合法 `verdict: FAIL`，包含多项具体 findings，必要证据使总回传超过 15 行；C `verdict: CANNOT_VERIFY` 并说明缺失材料。三者均使用 `verdict`、`summary`、`findings`、`remaining_risk`。
- **User Prompt**：`/nuclio:work 对当前 change 完成必要的独立审查并继续交付`
- **Expected**：按只读审查合同接受 A/B/C 的格式。A 供主会话判断验证结果，B 按 findings 回到 Build，C 保留未满足审查；不将 B 或 C 当作通过。用户或项目要求独立审查时，C 阻止宣称完成。
- **Assertions**：不要求 reviewer 输出调查与实施代理的五字段或 `DELIVERED|BLOCKED`，不因合法报告超过 15 行而裁剪 finding、判为缺少合格回传或触发恢复/重派。普通调查与实施代理仍执行原五字段及 15 行限制，reviewer 的只读权限与 Runtime 边界保持有效。
