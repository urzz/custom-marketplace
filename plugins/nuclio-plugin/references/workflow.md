# Nuclio v3 Workflow

Nuclio v3 是面向 Claude Code 与 Codex 的薄 Runtime。主会话是唯一控制器，独占用户 Gate、结果合同判断、`delivery.yaml` 维护、Runtime 调用、最终验证、知识决定、`complete` 和 `archive`；`change.py` 是唯一 State writer。用户确认结果合同，主会话管理交付，Runtime 只保存可恢复事实、绑定当前验证并判断是否可完成。

路径、显式调用、确认与代理能力遵循 [宿主适配](host-runtime.md)。

## Plan Mode 边界

Nuclio 生命周期始终在调用开始时的当前模式内运行，不调用 Claude Code 的 `EnterPlanMode` 或 `ExitPlanMode`。若显式调用 `/nuclio:init` 或 `/nuclio:work` 时已处于 Claude Code Plan Mode 或 Codex Plan mode，立即 fail closed：不创建或恢复 change，不执行 Runtime，也不自行退出；要求用户先退出 Plan Mode 后重新显式调用。`delivery.yaml` 的 delivery milestone 是 Nuclio 的交付跟踪，不等于也不触发宿主 Plan Mode。

## Lifecycle

```text
Shape -> 一次明确的结果合同确认 -> Build <-> Verify -> Finish -> complete -> archive
```

- **Shape**：无 active change 时，从 `.dev-docs/index.md` 路由相关知识并只读调查请求与仓库，确定合法 change ID、类型和结果合同；仅在下述分支隔离成功后创建 `change.md`。已有 active change 按恢复路径继续，不重复分支操作。合同包含 Goal、Context、Constraints、Non-goals 与可观察 Acceptance。
- **确认**：只确认结果合同。milestone、路径、实现、Agent、review、检查增强和合同不变的失败修复由主会话自主决定。新产品语义、兼容性、外部副作用或不可逆结果才提升 revision 并重新确认。
- **Build**：主会话创建和维护 `delivery.yaml`，用 milestone 覆盖所有 Acceptance；多 milestone 时最后一项为覆盖全部 Acceptance 的 integration。开始当前 milestone 时，主会话先保留或读取紧凑控制信息：`status --id <change-id> --json` 工作包、当前合同、milestone/handoff，以及经 `.dev-docs/index.md` 路由的相关知识；派发时仅将当前控制信息、相关知识路径及读取理由和必要范围交给 Agent，不复制知识正文。随后以读取广度、预期实现/诊断迭代、原始命令输出体量、必要范围能否清楚界定和已确认结果合同是否保持不变为启发式，先作出派发判断。保护主会话上下文是优先使用一个有界原生 Agent 的判断条件，不使用 token 或 ctx 数值硬阈值。阅读或诊断密集、合同稳定、范围清晰且可由预期检查验证的局部工作优先派发 Agent；若派发，主会话不预读该委派范围的局部代码、测试、配置或测试诊断，Agent 在必要范围内读取代码、测试和配置，并吸收局部探索、测试诊断和原始输出；主会话只处理短回传、milestone/handoff、Runtime 和 Verify。极小、单一且实现路径明确的工作，以及产品语义、兼容性、权限、外部副作用、不可逆结果、跨 milestone 架构取舍、用户交互、Runtime、Verify、Finish 等控制决定仍由主会话直接处理，不为形式而派发；若直接实施，主会话才读取相关代码、测试和配置并完成实现和检查。dispatch 只含当前 milestone、相关 Acceptance、Constraints/Non-goals、handoff、相关知识路径及读取理由、必要范围和预期检查，不复制完整知识正文；agent 只短回传改动、检查和未完成项，不调用 Skill、不继续委派、不写 Runtime 状态。
- **Verify**：主会话在当前 HEAD 直接执行 exact argv，并以 `record-check` 记录结果，随后调用 `verify`。失败、缺失或过期依据回到 Build；不引入旧的修复审批或用户确认。
- **Finish**：验证通过后，从索引读取受影响知识，同时审查新增候选和存量失效。无候选使用 `NO_OP`；有候选只作一次“写入并归档（推荐）/跳过并归档”决定，再连续 complete/archive。

## Runtime

Runtime 只提供 `create`、`approve`、`status`、`record-check`、`verify`、`complete`、`archive` 七个命令。每次均以：

```bash
python3 "${NUCLIO_SKILL_DIR}/../../scripts/change.py" --project-root "${NUCLIO_PROJECT_DIR}" <command> ...
```

调用。`${NUCLIO_SKILL_DIR}` 只定位 bundled script；`${NUCLIO_PROJECT_DIR}` 是唯一写入根目录。插件源码和 Marketplace cache 只读。

`status --id <change-id> --json` 是已知唯一 active change 的恢复入口：先仅检查 `.dev-docs/changes/` 的直接子目录并排除 `archive/`。无候选时不调用 `status`，进入 Shape；恰有一个候选时，以目录名作为 change ID 调用 `status`；多个候选时 fail closed，报告歧义而不猜测或调用 Runtime。随后先保留或读取紧凑工作包、当前合同、milestone/handoff 和由索引路由的相关知识，并按当前 evidence 计算的 `next_action` 恢复到合同确认、Build、Verify、Finish 或 archive。进入 Build 时遵循上述先判断后读取的分支：若派发，主会话不预读该委派范围的局部代码、测试、配置或测试诊断，由 Agent 在必要范围内读取并吸收局部探索、测试诊断和原始输出；若直接实施，主会话才读取相关代码、测试和配置。`review_blocker` 非空时先在 Build 处理 finding。complete 后若 HEAD、check 或 Acceptance evidence 漂移，按同一 Build/Verify 路径重建依据，不重新确认未变化的合同。不要以旧聊天、全部 archive 或整个知识库恢复工作。v2 active 输入（包括 `plan.yaml`）必须 fail closed；旧 archive 不扫描、不解析、不修改。

两种中断有专门恢复路径。`status.next_action=recover-approval` 表示批准提交已存在、State 尚未写回，主会话重跑 `approve --id <change-id>` 后重新读取 status，不重复确认。无 active 候选且用户当前明确提供恢复/归档 ID 时，Shape 先定点检查该 ID 的 archive 目录；存在则直接 `archive --id <change-id>`，不进入新建的起点 clean 检查或分支流程。目标缺失或与现有 active ID 冲突时停止；没有 ID 时要求用户明确目标，不扫描或猜测 archive。多个 active 仍 fail closed。此例外适用于移动后提交失败及确认既有归档，仅由 Runtime 验证指定 v3 完成态。

## Verification and review

`delivery.yaml` 定义 check argv；宿主主会话直接运行它们，Runtime 的 `record-check` 绝不执行 argv。合同、HEAD、check 定义或未登记的产品工作区漂移均使旧验证失效。正常 `verify` 要求当前合同、完整覆盖、当前检查和干净产品工作区；stale complete 恢复仅允许 State 已精确登记的 `APPLIED|PARTIAL` knowledge 路径保持 dirty，其他 dirty 路径继续 fail closed。`complete` 还要求完成 section 与明确知识结果。

手工观察使用 `verify --manual`，必须明确 `status: PASS|FAIL`，完整字段见 `change-format.md`。只有当前 `PASS` 贡献 Acceptance 依据，当前 `FAIL` 优先阻断对应验收，并通过 `manual_blocker` 路由回 Build；新的完整批次可替换旧观察。无 `status` 的旧 v3 记录可读取，但不能作为通过依据，不能根据 `result` 自由文本补猜结论。

主会话始终 self-review。独立审查只在用户/项目要求或安全、权限、迁移、并发、公共 API、不可逆行为或弱 oracle 等实际需要时使用。独立 reviewer 遵循 [只读审查合同](readonly-review.md) 与宿主适配的有效权限检查。Claude Code 使用 `nuclio:readonly-reviewer`，不运行 shell；Codex 只使用已提供有效只读限制的原生代理。主会话传入共享合同的绝对路径或完整正文，以及必要审查材料。能力不足时按宿主适配报告 CANNOT_VERIFY，不以主会话自检冒充独立审查。

## 新 change 分支隔离

通过 Plan Mode fail-closed 边界后、active change discovery 前，主会话立即只读尝试捕获调用起点快照。所有 Git 命令均显式使用 `git -C "${NUCLIO_PROJECT_DIR}" ...`，不依赖当前目录。运行 `git -C "${NUCLIO_PROJECT_DIR}" status --porcelain=v2 --branch -z --untracked-files=all`，从可解析输出记录 Git 仓库和 attached `HEAD` 是否可用；可用时记录 `start_branch` 与 `start_head`，并记录 staged、unstaged、untracked 是否均为空。命令或解析异常为 snapshot unavailable。这一步不写文件、不调用 Runtime，也不进行网络、远程或分支操作。快照不可用或起点 dirty 不得阻止 discovery。

随后仅检查 `.dev-docs/changes/` 的非 archive 直接子目录。若有唯一或多个 active change，丢弃该快照并遵循既有恢复或歧义路径；恢复调用绝不创建或切换分支，也不因快照不可用、non-Git、detached HEAD 或调用起点 dirty 而提前阻止恢复。仅无 active change 且需要新建时，才要求有效 attached `start_branch`/`start_head` 快照且调用起点 staged、unstaged、untracked 均为空；任一不满足即 fail closed，即使 Shape 期间外部清理了工作区也不得继续新建。之后主会话从调用起点的当前分支只读调查需求、`.dev-docs/index.md` 路由的知识和仓库事实，确定遵守 change format 的合法 `<change-id>` 与类型。类型仅可为 `feat`、`fix`、`refactor`、`docs`、`test`、`chore`，无法明确时为 `feat`；目标分支固定为 `<type>/<change-id>`。

完成只读 Shape 后、在调用 Runtime `create` 或写入任何本次 change 或产品文件前，重新运行 `git -C "${NUCLIO_PROJECT_DIR}" status --porcelain=v2 --branch -z --untracked-files=all`。输出必须可解析，当前 branch 与 `HEAD` 必须分别等于 `start_branch` 与 `start_head`，且 staged、unstaged、untracked 均为空；任一异常 fail closed。使用 `git -C "${NUCLIO_PROJECT_DIR}" show-ref --verify --quiet refs/heads/<type>/<change-id>` 检查精确本地 ref：exit `0` 为冲突、exit `1` 为不存在、其他 exit fail closed。运行 `git -C "${NUCLIO_PROJECT_DIR}" remote` 列出全部本地配置 remote，并对每个 remote 用相同 `show-ref --verify --quiet` 语义检查精确 `refs/remotes/<remote>/<type>/<change-id>`。再运行 `git -C "${NUCLIO_PROJECT_DIR}" for-each-ref --format="%(refname)" refs/remotes/` 读取本地缓存全集，和由全部已配置 remote 构造的完整目标 refname 集合精确比较，确保不只查 `origin`。remote-tracking 仅指当前本地缓存的 `refs/remotes/**` 快照。所有检查只读取本地 Git metadata，不联系 remote；命令或解析异常 fail closed；不得调用 `git fetch`、`git ls-remote` 或任何网络或远程操作，也不得静默刷新 refs。随后执行：

```bash
git -C "${NUCLIO_PROJECT_DIR}" switch -c <type>/<change-id> <start-head>
```

switch 成功后、调用 `create` 前，重新运行上述 `git -C "${NUCLIO_PROJECT_DIR}" status --porcelain=v2 --branch -z --untracked-files=all`。输出必须可解析，当前 branch 精确为 `<type>/<change-id>`、`HEAD` 精确为 `start_head`，且 staged、unstaged、untracked 均为空。还必须再次运行 `git -C "${NUCLIO_PROJECT_DIR}" for-each-ref --format="%(refname)" refs/remotes/`，将输出与全部已配置 remote 的完整目标 refname 集合精确比较；不得把 `foo<type>/<change-id>` 等非精确 ref 当作冲突。若检查期间新出现任何属于已配置 remote 的精确目标 ref，或任一命令、解析或状态检查异常，按“分支可能已创建”的部分成功路径停止：不调用 `create`、不写本次 change 或产品文件、不自动回滚，并报告分支事实。仅 post-switch 校验成功后才能调用 `create` 创建三件套；随后才丢弃 `start_branch` 与 `start_head`。创建的分支名只保留在主会话的瞬时控制信息中。

switch 前的任一前置检查或该命令失败均 fail closed：不调用 `create`，不写本次 change 或产品文件。若 `create` 失败，保留已创建的分支并在部分成功报告中包含分支名，不自动回滚。同一调用最终成功完成时，最终报告也必须包含创建的分支名；恢复调用未创建分支时不得声称创建了分支。不得自动 stash、commit、reset、clean、删除分支、切回原分支、push、merge、rebase 或创建 worktree。

分支操作仅由 宿主主会话执行，不加入 Runtime command、State、artifact、knowledge 或用户 Gate；Runtime 仍不创建或切换分支，也不保存 branch identity。多个 active change、Plan Mode 阻塞和 `/nuclio:init` 保持原有 fail-closed 或初始化行为。Finish 的最终报告包含 outcome、archive 路径/commit、剩余风险，以及新建调用所创建的分支名（如适用）。

## Git and archive

Runtime 可创建 approval 与 archive 元数据提交；主会话自行决定普通产品提交。Runtime 不规定任务级提交，不保存固定任务、路径 ownership、agent transcript、完整日志或验证历史。它不 push、merge、stash、reset、clean、切换分支或创建 worktree。

archive 仅处理显式且已完成的 change，完整保留 `change.md`、`delivery.yaml`、`state.yaml`，并可从移动/提交中断恢复。无关 dirty work 不得被吸收。

移动前和未提交归档的恢复均复核知识路径仍精确匹配实际改动，并拒绝被 Git 忽略的 archive 目标。暂存、提交失败只撤销该 transition 实际已暂存的路径，保留目录供按 ID 重跑。已提交归档可在后续 HEAD 上幂等确认；三件套必须与指定 ID 的归档提交一致，历史 evidence 使用原验证 HEAD 的检查定义。Git 文件路径按 NUL 分隔读取并转换到显式项目边界；`.dev-docs` 下路径不允许符号链接重定向。详细错误和边界见 `change-format.md`。
