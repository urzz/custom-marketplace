# Nuclio v3 Workflow

Nuclio v3 是面向 Claude Code 的薄 Runtime。主会话是唯一控制器；`change.py` 是唯一 State writer。用户确认结果合同，主会话管理交付，Runtime 只保存可恢复事实、绑定当前验证并判断是否可完成。

## Plan Mode 边界

Nuclio 生命周期始终在调用开始时的当前模式内运行，不调用 Claude Code 的 `EnterPlanMode` 或 `ExitPlanMode`。若显式调用 `/nuclio:init` 或 `/nuclio:work` 时已处于 Claude Code Plan Mode，立即 fail closed：不创建或恢复 change，不执行 Runtime，也不自行退出；要求用户先退出 Plan Mode 后重新显式调用。`delivery.yaml` 的 delivery milestone 是 Nuclio 的交付跟踪，不等于也不触发 Claude Code Plan Mode。

## Lifecycle

```text
Shape -> 一次 AskUserQuestion 结果合同确认 -> Build <-> Verify -> Finish -> complete -> archive
```

- **Shape**：从 `.dev-docs/index.md` 路由相关知识，调查请求与仓库，创建或更新 `change.md`。合同包含 Goal、Context、Constraints、Non-goals 与可观察 Acceptance。
- **确认**：只确认结果合同。milestone、路径、实现、Agent、review、检查增强和合同不变的失败修复由主会话自主决定。新产品语义、兼容性、外部副作用或不可逆结果才提升 revision 并重新确认。
- **Build**：主会话创建和维护 `delivery.yaml`，用 milestone 覆盖所有 Acceptance；多 milestone 时最后一项为覆盖全部 Acceptance 的 integration。可直接工作或使用有界 Claude Code Agent，但 agent 不调用 Skill、不继续委派、不写 Runtime 状态。
- **Verify**：主会话在当前 HEAD 直接执行 exact argv，并以 `record-check` 记录结果，随后调用 `verify`。失败、缺失或过期依据回到 Build；不引入旧的修复审批或用户确认。
- **Finish**：验证通过后，从索引读取受影响知识，同时审查新增候选和存量失效。无候选使用 `NO_OP`；有候选只作一次“写入并归档（推荐）/跳过并归档”决定，再连续 complete/archive。

## Runtime

Runtime 只提供 `create`、`approve`、`status`、`record-check`、`verify`、`complete`、`archive` 七个命令。每次均以：

```bash
python3 "${CLAUDE_SKILL_DIR}/../../scripts/change.py" --project-root "${CLAUDE_PROJECT_DIR}" <command> ...
```

调用。`${CLAUDE_SKILL_DIR}` 只定位 bundled script；`${CLAUDE_PROJECT_DIR}` 是唯一写入根目录。插件源码和 Marketplace cache 只读。

`status --id <change-id> --json` 是已知唯一 active change 的恢复入口：先仅检查 `.dev-docs/changes/` 的直接子目录并排除 `archive/`。无候选时不调用 `status`，进入 Shape；恰有一个候选时，以目录名作为 change ID 调用 `status`；多个候选时 fail closed，报告歧义而不猜测或调用 Runtime。随后读取紧凑工作包、当前合同、milestone/handoff、由索引路由的相关知识及相关代码/测试，并按当前 evidence 计算的 `next_action` 恢复到合同确认、Build、Verify、Finish 或 archive；`review_blocker` 非空时先在 Build 处理 finding。complete 后若 HEAD、check 或 Acceptance evidence 漂移，按同一 Build/Verify 路径重建依据，不重新确认未变化的合同。不要以旧聊天、全部 archive 或整个知识库恢复工作。v2 active 输入（包括 `plan.yaml`）必须 fail closed；旧 archive 不扫描、不解析、不修改。

## Verification and review

`delivery.yaml` 定义 check argv；Claude Code 直接运行它们，Runtime 的 `record-check` 绝不执行 argv。合同、HEAD、check 定义或未登记的产品工作区漂移均使旧验证失效。正常 `verify` 要求当前合同、完整覆盖、当前检查和干净产品工作区；stale complete 恢复仅允许 State 已精确登记的 `APPLIED|PARTIAL` knowledge 路径保持 dirty，其他 dirty 路径继续 fail closed。`complete` 还要求完成 section 与明确知识结果。

主会话始终 self-review。独立审查只在用户/项目要求或安全、权限、迁移、并发、公共 API、不可逆行为或弱 oracle 等实际需要时使用。可选 `nuclio:readonly-reviewer` 只能读文件并返回 findings；它不运行 shell、不写文件、不调用 Skill 或 Agent，不决定 Runtime。

## Git and archive

Runtime 可创建 approval 与 archive 元数据提交；主会话自行决定普通产品提交。Runtime 不规定任务级提交，不保存固定任务、路径 ownership、agent transcript、完整日志或验证历史。它不 push、merge、stash、reset、clean、切换分支或创建 worktree。

archive 仅处理显式且已完成的 change，完整保留 `change.md`、`delivery.yaml`、`state.yaml`，并可从移动/提交中断恢复。无关 dirty work 不得被吸收。