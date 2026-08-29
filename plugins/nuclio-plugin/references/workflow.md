# Nuclio v3 Workflow

Nuclio v3 是面向 Claude Code 的薄 Runtime。主会话是唯一控制器，独占用户 Gate、结果合同判断、`delivery.yaml` 维护、Runtime 调用、最终验证、知识决定、`complete` 和 `archive`；`change.py` 是唯一 State writer。用户确认结果合同，主会话管理交付，Runtime 只保存可恢复事实、绑定当前验证并判断是否可完成。

## Plan Mode 边界

Nuclio 生命周期始终在调用开始时的当前模式内运行，不调用 Claude Code 的 `EnterPlanMode` 或 `ExitPlanMode`。若显式调用 `/nuclio:init` 或 `/nuclio:work` 时已处于 Claude Code Plan Mode，立即 fail closed：不创建或恢复 change，不执行 Runtime，也不自行退出；要求用户先退出 Plan Mode 后重新显式调用。`delivery.yaml` 的 delivery milestone 是 Nuclio 的交付跟踪，不等于也不触发 Claude Code Plan Mode。

## Lifecycle

```text
Shape -> 一次 AskUserQuestion 结果合同确认 -> Build <-> Verify -> Finish -> complete -> archive
```

- **Shape**：从 `.dev-docs/index.md` 路由相关知识，调查请求与仓库，创建或更新 `change.md`。合同包含 Goal、Context、Constraints、Non-goals 与可观察 Acceptance。
- **确认**：只确认结果合同。milestone、路径、实现、Agent、review、检查增强和合同不变的失败修复由主会话自主决定。新产品语义、兼容性、外部副作用或不可逆结果才提升 revision 并重新确认。
- **Build**：主会话创建和维护 `delivery.yaml`，用 milestone 覆盖所有 Acceptance；多 milestone 时最后一项为覆盖全部 Acceptance 的 integration。开始当前 milestone 时，主会话先保留或读取紧凑控制信息：`status --id <change-id> --json` 工作包、当前合同、milestone/handoff，以及经 `.dev-docs/index.md` 路由的相关知识；派发时仅将当前控制信息、相关知识路径及读取理由和必要范围交给 Agent，不复制知识正文。随后以读取广度、预期实现/诊断迭代、原始命令输出体量、必要范围能否清楚界定和已确认结果合同是否保持不变为启发式，先作出派发判断。保护主会话上下文是优先使用一个有界 Claude Code Agent 的判断条件，不使用 token 或 ctx 数值硬阈值。阅读或诊断密集、合同稳定、范围清晰且可由预期检查验证的局部工作优先派发 Agent；若派发，主会话不预读该委派范围的局部代码、测试、配置或测试诊断，Agent 在必要范围内读取代码、测试和配置，并吸收局部探索、测试诊断和原始输出；主会话只处理短回传、milestone/handoff、Runtime 和 Verify。极小、单一且实现路径明确的工作，以及产品语义、兼容性、权限、外部副作用、不可逆结果、跨 milestone 架构取舍、用户交互、Runtime、Verify、Finish 等控制决定仍由主会话直接处理，不为形式而派发；若直接实施，主会话才读取相关代码、测试和配置并完成实现和检查。dispatch 只含当前 milestone、相关 Acceptance、Constraints/Non-goals、handoff、相关知识路径及读取理由、必要范围和预期检查，不复制完整知识正文；agent 只短回传改动、检查和未完成项，不调用 Skill、不继续委派、不写 Runtime 状态。
- **Verify**：主会话在当前 HEAD 直接执行 exact argv，并以 `record-check` 记录结果，随后调用 `verify`。失败、缺失或过期依据回到 Build；不引入旧的修复审批或用户确认。
- **Finish**：验证通过后，从索引读取受影响知识，同时审查新增候选和存量失效。无候选使用 `NO_OP`；有候选只作一次“写入并归档（推荐）/跳过并归档”决定，再连续 complete/archive。

## Runtime

Runtime 只提供 `create`、`approve`、`status`、`record-check`、`verify`、`complete`、`archive` 七个命令。每次均以：

```bash
python3 "${CLAUDE_SKILL_DIR}/../../scripts/change.py" --project-root "${CLAUDE_PROJECT_DIR}" <command> ...
```

调用。`${CLAUDE_SKILL_DIR}` 只定位 bundled script；`${CLAUDE_PROJECT_DIR}` 是唯一写入根目录。插件源码和 Marketplace cache 只读。

`status --id <change-id> --json` 是已知唯一 active change 的恢复入口：先仅检查 `.dev-docs/changes/` 的直接子目录并排除 `archive/`。无候选时不调用 `status`，进入 Shape；恰有一个候选时，以目录名作为 change ID 调用 `status`；多个候选时 fail closed，报告歧义而不猜测或调用 Runtime。随后先保留或读取紧凑工作包、当前合同、milestone/handoff 和由索引路由的相关知识，并按当前 evidence 计算的 `next_action` 恢复到合同确认、Build、Verify、Finish 或 archive。进入 Build 时遵循上述先判断后读取的分支：若派发，主会话不预读该委派范围的局部代码、测试、配置或测试诊断，由 Agent 在必要范围内读取并吸收局部探索、测试诊断和原始输出；若直接实施，主会话才读取相关代码、测试和配置。`review_blocker` 非空时先在 Build 处理 finding。complete 后若 HEAD、check 或 Acceptance evidence 漂移，按同一 Build/Verify 路径重建依据，不重新确认未变化的合同。不要以旧聊天、全部 archive 或整个知识库恢复工作。v2 active 输入（包括 `plan.yaml`）必须 fail closed；旧 archive 不扫描、不解析、不修改。

## Verification and review

`delivery.yaml` 定义 check argv；Claude Code 直接运行它们，Runtime 的 `record-check` 绝不执行 argv。合同、HEAD、check 定义或未登记的产品工作区漂移均使旧验证失效。正常 `verify` 要求当前合同、完整覆盖、当前检查和干净产品工作区；stale complete 恢复仅允许 State 已精确登记的 `APPLIED|PARTIAL` knowledge 路径保持 dirty，其他 dirty 路径继续 fail closed。`complete` 还要求完成 section 与明确知识结果。

主会话始终 self-review。独立审查只在用户/项目要求或安全、权限、迁移、并发、公共 API、不可逆行为或弱 oracle 等实际需要时使用。可选 `nuclio:readonly-reviewer` 只能读文件并返回 findings；它不运行 shell、不写文件、不调用 Skill 或 Agent，不决定 Runtime。

## Git and archive

Runtime 可创建 approval 与 archive 元数据提交；主会话自行决定普通产品提交。Runtime 不规定任务级提交，不保存固定任务、路径 ownership、agent transcript、完整日志或验证历史。它不 push、merge、stash、reset、clean、切换分支或创建 worktree。

archive 仅处理显式且已完成的 change，完整保留 `change.md`、`delivery.yaml`、`state.yaml`，并可从移动/提交中断恢复。无关 dirty work 不得被吸收。