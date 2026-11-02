---
name: work
description: "仅在用户显式选择 Nuclio 来创建、恢复或交付 change 时使用；可按项目绑定读取 Open Design 设计交付。"
disable-model-invocation: true
---
# Nuclio Work

`/nuclio:work`（DSH 为 `/nuclio-work`，Codex 为 `$nuclio:work`）仅在用户显式调用或明确选择 Nuclio 交付时启用，不根据普通 change 请求自动调用；不要求项目所有修改强制进入 Nuclio。宿主主会话是唯一控制器，独占用户 Gate、结果合同判断、`delivery.yaml` 维护、Runtime 调用、最终验证、知识决定、`complete` 和 `archive`。主会话按本技能的条件性积极委派合同决定直接执行或使用宿主原生代理；被委派代理只完成有界工作，不调用 Skill、不继续委派，也不接管 Runtime 状态。

## Plan Mode 边界

从调用开始直到完成或停止，Shape、Build、Verify 和 Finish 始终在当前模式执行，不得调用 Claude Code 的 `EnterPlanMode` 或 `ExitPlanMode`。若调用开始时已处于 Claude Code Plan Mode 或 Codex Plan mode，立即 fail closed：不创建或恢复 change、不进行 Git 分支检查或创建、不调用 Runtime、不自行调用 `ExitPlanMode`；报告阻塞，并要求用户先退出 Plan Mode 后重新调用当前宿主入口（Claude `/nuclio:work`、Codex `$nuclio:work`、DSH `/nuclio-work`）。

## 宿主与路径

通过上述模式边界后，先读取 [宿主适配](../../references/host-runtime.md)，固定本次 `NUCLIO_SKILL_DIR` 与 `NUCLIO_PROJECT_DIR` 的绝对路径并选择当前宿主的确认/委派方式；DSH 通过 bundle provider 的 `resourceBase.path` 定位 `NUCLIO_SKILL_DIR`，不会把 bundle 安装目录当作项目根目录；后续命令中的变量是路径记号，必须在每次调用中落实。

路径解析后，第一条针对目标项目的命令必须是下述调用起点快照。普通项目目录清单、workflow 等阶段 reference 和问题调查均后置；不能先读项目再补记起点。

## 调用起点快照

仅在已通过 Plan Mode fail-closed 边界的 `/nuclio:work` 调用中，主会话必须在 active change discovery 前立即执行只读调用起点快照。所有 Git 命令均显式使用 `git -C "${NUCLIO_PROJECT_DIR}" ...`，不依赖当前目录。使用以下命令捕获起点：

```bash
git -C "${NUCLIO_PROJECT_DIR}" status --porcelain=v2 --branch -z --untracked-files=all
```

主会话必须从该输出确定项目是否为 Git 仓库、`HEAD` 是否为 attached；可用时记录当前分支为 `start_branch`、当前 commit 为 `start_head`，并观察调用起点 staged、unstaged、untracked 是否均为空。输出不可解析或命令失败时记录 snapshot unavailable。此时不得写入文件、调用 Runtime，或进行网络、远程和分支操作。

快照不可用、不是 Git 仓库、`HEAD` 未 attached 或调用起点任一工作区状态不为空，均不得阻止 active change discovery。主会话只在本次调用的瞬时控制信息中记录 unavailable 或 dirty。仅当 discovery 结果为无候选且需要新建时，才要求有效的 attached `start_branch`/`start_head` 快照且调用起点的 staged、unstaged、untracked 均为空；否则 fail closed。恰有一个或多个候选时，照既有恢复或歧义路径继续，不因快照不可用或调用起点 dirty 而提前停止。

## Read first

按当前阶段读取一层 reference：[workflow](../../references/workflow.md)、[change format](../../references/change-format.md)、[knowledge](../../references/knowledge.md)、[context hygiene](../../references/context-hygiene.md)。仅当请求明确使用 Open Design 且当前请求或已加载的项目上下文提供绑定 `project-id` 时，读取 [Open Design handoff](../../references/open-design-handoff.md)。

所有 Runtime 调用使用 bundled script 与显式项目根目录，绝不依赖当前目录或插件源码路径：

```bash
python3 "${NUCLIO_SKILL_DIR}/../../scripts/change.py" --project-root "${NUCLIO_PROJECT_DIR}" <command> ...
```

插件安装目录和 Marketplace cache 始终只读；运行时写入只落在 `${NUCLIO_PROJECT_DIR}/.dev-docs/**`。

## Lifecycle

### 1. Shape

通过调用起点快照后，先仅检查 `${NUCLIO_PROJECT_DIR}/.dev-docs/changes/` 的直接子目录，排除 `archive/`，以发现 active change 候选；不得扫描、读取或猜测 archive。

- 恰有一个候选时，丢弃调用起点快照。若用户明确指定的恢复 ID 与候选不一致，报告目标冲突并停止；否则以目录名作为 change ID 调用 `status --id <change-id> --json`，只读核对当前请求与 active 的 Goal、Design、Scope 是否同属一项，再按 `next_action` 恢复；不得创建或切换分支。唯一 active 不代表当前请求归属于它。归属不匹配或不明确时停止实施，展示 active ID、方案版本、批准状态、范围、知识覆盖和剩余项，提供“保留当前现场，本次停止”或“先完成旧项，再处理新请求”；不得自动吸收新请求、跳过 Nuclio、移动资料或宣称已暂停。当前 Runtime 无暂停命令，单 active 约束与工作区保护不因口头暂停而解除。
- 多个候选时，同样丢弃快照并立即 fail closed：不调用 Runtime、不猜测目标，报告候选目录并要求用户先解决歧义；不得创建或切换分支。
- 无候选时，先判断下述显式归档恢复例外；不适用时按新建路径继续。

**显式归档恢复例外**：仅当用户当前明确提供合法 `<change-id>` 并要求恢复或归档该 ID 时，允许定点检查 `.dev-docs/changes/archive/<change-id>/` 是否存在，不列举或读取其他 archive。目标存在时丢弃调用起点快照，直接调用 `archive --id <change-id>`；该恢复不受新建的起点 clean 要求限制，不调用 `status`、不创建分支或 change。Runtime 校验目标确为可恢复或已提交的 v3 完成态后，完成或确认归档；失败时保留现场并报告。目标不存在则报告未找到，不改走新建。用户未提供 ID 时不得从 dirty 路径猜测归档目标；说明恢复归档需要其明确 ID。

无候选时不调用 `status`。以下起点 clean 和分支规则仅适用于新建，不适用于上述显式归档恢复。主会话必须按以下确定性顺序处理：

1. 确认调用起点快照有效：项目是 Git 仓库、`HEAD` 为 attached，且起点的 staged、unstaged、untracked 均为空。快照 unavailable 或起点 dirty 时立即 fail closed；即使 Shape 期间外部清理了工作区也不得继续新建。
2. 只读调查用户请求、仓库事实和通过 `.dev-docs/index.md` 路由的相关长期知识，确定遵守 `change-format.md` 的合法 `<change-id>`、结果合同和固定类型前缀。每个 Shape 调查开始前，主会话按下文 Build 相同的独立性、上下文隔离收益和协调成本标准，显式判断直接调查或积极委派，并由模型自主切成互斥、有停止条件且只回答当前合同缺口的调查包；复用已有结论，不派发重叠调查。活动调查同样适用范围排他、宿主原生等待、短回传和失败恢复合同。类型仅可为 `feat`、`fix`、`refactor`、`docs`、`test`、`chore`，无法明确时为 `feat`。目标分支为 `<type>/<change-id>`。
3. 完成只读 Shape 后、调用 Runtime `create` 或写入任何本次 change 或产品文件前，重新运行以下命令并以其输出重新读取当前 branch、`HEAD` 与 clean 状态：

   ```bash
   git -C "${NUCLIO_PROJECT_DIR}" status --porcelain=v2 --branch -z --untracked-files=all
   ```

   输出必须可解析，当前 branch 与 `HEAD` 必须分别等于 `start_branch` 与 `start_head`，且 staged、unstaged、untracked 必须均为空；任一不满足或命令失败立即 fail closed。
4. 以以下本地精确查询检查 `refs/heads/<type>/<change-id>`：

   ```bash
   git -C "${NUCLIO_PROJECT_DIR}" show-ref --verify --quiet refs/heads/<type>/<change-id>
   ```

   exit `0` 表示冲突，exit `1` 表示不存在，其他 exit 均 fail closed。再运行 `git -C "${NUCLIO_PROJECT_DIR}" remote` 列出全部本地配置 remote。对每个 `<remote>`，使用相同 `show-ref --verify --quiet` 语义检查精确 `refs/remotes/<remote>/<type>/<change-id>`。最后运行以下命令读取本地缓存全集，并将每个输出 refname 与已构造的完整目标 refname 集合精确比较，确保不只检查 `origin`：

   ```bash
   git -C "${NUCLIO_PROJECT_DIR}" for-each-ref --format="%(refname)" refs/remotes/
   ```

5. remote-tracking 只指当前本地缓存的 `refs/remotes/**` 快照。所有 Git/ref 检查只读取本地 Git metadata，不联系 remote；命令或解析异常均 fail closed。绝不调用 `git fetch`、`git ls-remote` 或任何网络或远程操作，也不得静默刷新 refs。
6. 仅在全部前置检查通过后执行以下命令，其中 `<start-head>` 是已捕获的 `start_head`：

   ```bash
   git -C "${NUCLIO_PROJECT_DIR}" switch -c <type>/<change-id> <start-head>
   ```

7. switch 成功后、调用 `create` 前，再运行步骤 3 的 `git -C "${NUCLIO_PROJECT_DIR}" status --porcelain=v2 --branch -z --untracked-files=all`。输出必须可解析，当前 branch 必须精确为 `<type>/<change-id>`、`HEAD` 必须精确为 `start_head`，且 staged、unstaged、untracked 必须仍均为空。还必须再次运行 `git -C "${NUCLIO_PROJECT_DIR}" for-each-ref --format="%(refname)" refs/remotes/`，并将结果与全部已配置 remote 构造的完整目标 refname 集合精确比较；不得把 `foo<type>/<change-id>` 等非精确 ref 当作冲突。若检查期间新出现任何属于已配置 remote 的精确目标 ref，或任一命令/解析/状态检查异常，按“分支可能已创建”的部分成功路径停止：不调用 `create`、不写本次 change 或产品文件、不自动回滚，并报告分支事实。
8. 仅在 post-switch 校验成功后，以 `create` 创建三件套。`create` 的单行参数只是种子；创建后必须重新读取并按调查事实补全 `change.md`，使其无需旧聊天也能说明 Goal、必要 Context、每项独立 Constraint/Non-goal 和可观察 Acceptance。多个独立边界使用列表，不得压成一句同义概括，补全必需非空 `Design`、`Scope`、`Knowledge Context`：前两者记录关键设计与影响面并冻结，后者只记录知识覆盖和处理事实、可持续更新；若新知识冲突推翻已批准假设，必须同步更新 Design/Scope/Constraints、提升 revision 重批，不能借可变 section 绕过 Gate；不复制知识正文或逐函数实施步骤。

这些 Git 操作仅由 宿主主会话直接执行，不加入 Runtime command、State、artifact 或用户 Gate；Runtime 仍不创建或切换分支。switch 前的任一前置检查或 `git switch -c` 失败时立即 fail closed：不调用 `create`，不写本次 change 或产品文件。不得自动 stash、commit、reset、clean、删除分支、切回原分支、push、merge、rebase 或创建 worktree。

post-switch 校验成功后，丢弃 `start_branch` 与 `start_head`；创建的分支名只保留在主会话的瞬时控制信息中，不写入 Runtime、State、artifact 或 knowledge。若 `create` 失败，保留新分支、不自动回滚 Git 状态，并在部分成功报告中包含分支名。同一调用最终成功完成时，最终报告也必须包含创建的分支名；恢复调用未创建分支时不得声称创建了分支。

Open Design 输入在 Shape 只通过用户已配置的 MCP 读取；当前请求中的显式绑定优先，其次使用已加载项目上下文中的绑定，不得从知识库或活动页面猜测项目。合同批准前不把设计文件写入产品仓库；MCP 不可用、绑定无效、项目上下文冲突或交付不完整时按 reference 报告 blocker。

展示“结果 + 关键设计 + 影响面”的完整 proposal 摘要及完整文档位置，使用一次宿主确认交互，等待用户明确批准当前 change ID/revision。必需包含目标/非目标/Acceptance、当前系统与架构增量（没有时明确无）、关键方案及重要备选取舍、影响模块/目录与接口/数据迁移/部署/权限/外部副作用、不动边界、验证策略与风险；在 `Knowledge Context` 记录已读主题和 authority/heading、尚未核对主题、冲突/过期/缺失项及处理。精简不等于单句；小修可紧凑说明，不省略关键决定。用户不逐文件、milestone、Agent 或普通返修审批。只有关键架构、协议/数据兼容、权限、事务/事实源、不可逆副作用或实质范围变化才回 Shape、提升 revision 并重批；新测试文件或相同方案内代码组织调整不触发重批。

批准前仅调查和 proposal 草稿，不写产品、不迁移或部署；保留上述既有分支前置流程。无回答、空回复、取消或超时立即停止依赖批准的动作，不把工具权限许可当作业务批准。已有明确回复仅在指向同一完整 proposal 时复用。记录可定位的宿主会话/消息来源；`--approval-source` 是主会话可追溯声明，不是宿主认证凭据或抗绕过写入隔离。

确认后创建或调整 `delivery.yaml`，保证 milestone 和检查覆盖全部 Acceptance，然后执行：

```bash
python3 "${NUCLIO_SKILL_DIR}/../../scripts/change.py" --project-root "${NUCLIO_PROJECT_DIR}" approve --id <change-id> --approval-source '<宿主会话/消息定位及明确决定>'
```

### 2. Build

主会话对每个 Build 或返修工作包都获得**条件性积极委派**的明确授权；具体是否委派及如何拆分由模型根据工作独立性、上下文隔离收益与协调成本自主决定，不按模型名、具体代理工具、固定代理数量或宿主自动委派模式分支，也不使用 token 或 ctx 数值硬阈值。多文件或多模块调查、日志/测试失败等大输出诊断、可独立验收的实现轨道、只需结论的工作和 fresh-context review，在预期改善速度、覆盖或上下文质量时应积极委派。少量工具调用即可完成、单文件小改、紧密顺序依赖、共享资源争用、需要持续共享上下文，或涉及产品语义、兼容性、权限、外部副作用、不可逆结果、跨 milestone 架构取舍、用户交互、Runtime、Verify、Finish 等控制决定时直接执行，不为形式机械委派。当前宿主没有可用原生代理时，主会话按同一工作包顺序直做；不得新增代理配置或服务、调用另一宿主 CLI 或模拟缺失能力。

主会话自主维护 milestone、状态和短 handoff；合同不变时可重排、拆分或合并 milestone，产品写入始终顺序进行。开始工作包前只保留或读取紧凑控制信息：`status --id <change-id> --json` 工作包、当前合同、milestone/handoff，以及经 `.dev-docs/index.md` 路由的相关知识。实际委派必须形成可独立验收的工作包，覆盖相关 Acceptance、Constraints/Non-goals、实现边界、集成接缝、预期 changed paths 与 exact checks；只传当前控制信息、相关知识路径及读取理由和必要范围，不复制知识正文。代理在必要范围内读取代码、测试和配置，吸收局部探索、测试诊断和原始输出；不调用 Skill、不继续委派、不接管 Runtime。

委派一经启动，工作包的产品路径与诊断主题在其活动期间对主会话排他：主会话不得读取、编辑、写入或运行诊断命令重复该范围，也不得重复派发同题工作；可继续明确不重叠的控制工作或其他顺序工作包。仅允许为验收定点核对必要证据，或执行目的明确的独立复核，不得借此重新通读实现范围或吸收完整调查。真正依赖结果时，使用宿主原生完成通知或等待机制；不得以 shell `sleep`、Git 状态或反复消息轮询、催促进度。

调查与实施代理（含返修）的回传最多 15 行，只使用 `status`、`changed`、`checks`、`handoff`、`concerns` 字段；`status` 仅为 `DELIVERED` 或 `BLOCKED`。不粘贴代码、搜索过程、完整日志或测试输出，但 `changed`、`checks` 或 `concerns` 必须保留 Controller 判断所需的文件、检查、错误等必要证据定位。主会话只吸收该短回传和定点证据。收到 `BLOCKED`、代理异常/超时或缺少合格回传时，先按宿主实际能力继续原线程（resume）；仅当该能力不可用、宿主明确拒绝恢复或原工作包不再合适时，才缩小/重切或重新委派。仅当重新判断共享上下文收益确实高于隔离收益时才由主会话接管，并在 handoff 留下一句理由；不得无声重复代理已做的宽范围探索。能力降级细节见宿主适配。

独立 reviewer 的回传仅按 [只读审查合同](../../references/readonly-review.md) 验收，使用 `verdict`、`summary`、`findings`、`remaining_risk`；上述五字段、`DELIVERED|BLOCKED` 状态和 15 行限制不适用于 reviewer。不得因其使用审查格式而按缺少合格回传恢复或重派。

Open Design change 在批准后的首个相关 milestone 中把已接受的设计交付固化到固定目录 `.dev-docs/artifacts/open-design/`，随后只以仓库快照恢复和实施；不得按 UUID 分层、把完整交付写入 knowledge，也不得在同一合同下静默拉取更新后的外部设计。

普通检查失败、实现缺陷或检查定义调整时，继续 Build 自主修复；不引入旧的修复审批、固定实现流水线、任务级提交或证据协议。只有真实产品语义变化、用户独有环境、无法形成新假设或环境阻塞才中断用户。

### 3. Verify

先执行 `status --id <change-id> --json`，读取工作包、当前合同、milestone/handoff，并经索引读取相关知识。`next_action=recover-approval` 时先重跑 `approve --id <change-id>`，恢复已经提交但尚未写回的批准，再重新读取 status；不重复确认同一合同。只在候选实现及 HEAD/工作区稳定后进入 Verify；宿主主会话按 check 的 `cwd` 和 `timeout_seconds` 直接执行 delivery 中的 exact argv，并只在主上下文保留命令、exit code 和短摘要，随后为每项检查调用 `record-check`，再调用 `verify`。Runtime 不执行检查。

```bash
python3 "${NUCLIO_SKILL_DIR}/../../scripts/change.py" --project-root "${NUCLIO_PROJECT_DIR}" status --id <change-id> --json
python3 "${NUCLIO_SKILL_DIR}/../../scripts/change.py" --project-root "${NUCLIO_PROJECT_DIR}" record-check --id <change-id> --check-id <id> --head <head> --exit-code <code> --summary <summary> -- <exact-argv>
python3 "${NUCLIO_SKILL_DIR}/../../scripts/change.py" --project-root "${NUCLIO_PROJECT_DIR}" verify --id <change-id>
```

手工观察通过 `verify --manual` 记录，JSON 必须包含 `acceptance`、`status: PASS|FAIL`、`steps`、`result`、`executor`。仅 `PASS` 贡献通过依据；当前 `FAIL` 使对应 Acceptance 保持未通过，即使其他检查或 reviewer 覆盖它。`manual_blocker` 非空时回到 Build 修复，并以新的完整手工批次复验。旧 v3 manual 记录缺少 `status` 时可读取恢复，但不再贡献通过依据；补做观察后替换，不推测旧 `result` 文本的结论。

恢复时先展示 change ID/revision、批准状态、Design/Scope、知识覆盖和下一步。旧 active 缺少完整 proposal 或批准来源时，`next_action=revise-proposal`/等待用户：补齐必需 section、提升 revision，展示完整方案并重新取得批准；不得给旧批准补造来源。完整新批准提交回写中断仍走 `recover-approval`，可不传来源且不重问。其余按 `status --json` 基于当前 evidence 给出的 `next_action` 继续到合同确认、Build、Verify、Finish 或 archive；`review_blocker` 非空时先在 Build 处理 finding。complete 后若 HEAD、check 或 Acceptance evidence 漂移，按同一 Build/Verify 路径重建依据，不重新确认未变化的合同。Verify FAIL、缺失或过期依据时结束本轮 Verify 并回到 Build，不在 Verify 中边诊断边修代码；简单明确的失败可由主会话直接修复，需要大量失败输出或多文件诊断时按 Build 合同优先隔离委派，再在稳定候选上重跑最终 exact check。向 Runtime 提交当前 reviewer `FAIL` 同样回到 Build。HEAD、合同或 check 定义变化会使旧依据失效。先进行主会话整体自检；用户或项目要求、较高后果或验证不足时，派发 fresh reviewer 前必须确定性预检输入包已包含审查问题、当前合同、当前 HEAD、changed paths、只读审查合同和必要材料，再按 [宿主适配](../../references/host-runtime.md) 选择具有有效只读限制的 reviewer。reviewer 只返回 findings，主会话自行决定后续工作和 Runtime 输入。代理不可用时主会话继续自检并明确独立审查未执行；无法强制有效只读权限时报告 `CANNOT_VERIFY`，不得以自然语言约束冒充隔离。若独立审查为用户或项目要求，则保留未满足项，不宣称完成。

### 4. Finish

验证通过后，先报告产品结果与最小证据。通过索引只读取受影响的知识，同时检查本次是否产生新候选以及现有知识是否失效。将最终 diff、批准决定与 `Knowledge Context` 交叉核对；无候选时 `NO_OP` 必须说明已核对主题/authority、为何无新增或失效，再连续补全完成 section、`complete` 和 `archive`。已知失效不能伪装 `NO_OP`；跳过时记录 `REJECTED|PARTIAL`、待处理风险与可从 index/主题入口发现的定位（不得未经批准写知识）。有候选时只使用一次宿主确认交互：“如何处理以上知识候选并完成本次 change？”，选项为“写入并归档（推荐）”和“跳过并归档”。该选择同时授权知识处理、complete 和 archive；不得再次请求归档确认。

按 `change-format.md` 追加信息完整的 `Outcome`、`Validation`、`Knowledge Updates`、`Residual Risks`，再调用 `complete --knowledge-assessment '<主题核对依据、新增/失效结论及跳过风险>'` 与 `archive`；知识路径内容摘要由 Runtime 绑定，complete 后同路径正文变化也不能沿用旧结果。归档记录必须脱离聊天仍能说明实际交付范围、验证所绑定的 HEAD 与检查结果、知识处理结果和残余风险。只报告最终 outcome、archive 路径/commit、剩余风险，以及新建调用所创建的分支名（如适用）。

归档移动或提交中断时保留目录与 Git 现场，报告精确 change ID；同一调用在原因解除后可直接重跑 `archive --id <change-id>`，新会话按 Shape 的显式归档恢复例外进入。不得手工改写 State、删除目录或回滚提交来伪造完成。
