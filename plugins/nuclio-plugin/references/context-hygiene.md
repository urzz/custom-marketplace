# Nuclio v3 Context Hygiene

按问题读取权威，不用聊天记录、完整知识库或 Runtime State 副本填充上下文。`.dev-docs/index.md` 是长期知识的唯一入口：索引说明路径、摘要和读取时机，不承载知识正文。

## Phase read order

- **Shape**：用户请求与项目规则 -> `index.md` -> 有明确相关性的知识文件/heading -> 相关代码、测试、配置。
- **Build / recovery**：主会话先保留或读取紧凑控制信息：`status --id <change-id> --json` 工作包、当前合同、milestone/handoff 和由 `.dev-docs/index.md` 路由的相关知识；派发时仅将当前控制信息、相关知识路径及读取理由和必要范围交给 Agent，不复制知识正文 -> 先作出派发判断。若派发：主会话不预读该委派范围的局部代码、测试、配置或测试诊断，Agent 在必要范围内读取代码、测试和配置并吸收局部探索、测试诊断和原始输出；主会话只处理短回传、milestone/handoff、Runtime 和 Verify。若直接实施：主会话才读取相关代码、测试和配置并实施。
- **Verify**：批准合同、delivery、当前 diff、检查与观察优先；相关知识仅提供稳定约束，不能替代验证依据。
- **Finish**：产品结果与 diff -> 索引路由的受影响知识，用同一次分析判断新增候选和既有结论是否失效。

除非问题明确需要，不读取整个 `.dev-docs/knowledge/**`、archive、legacy、全部 State 或完整 Git diff。先使用 `status --json`，只在漂移或诊断时扩展到精确 Git 状态和相关 artifact。

## Shape 与 recovery 路由

通过 Plan Mode 边界后，fresh session 先仅检查 `${CLAUDE_PROJECT_DIR}/.dev-docs/changes/` 的直接子目录并排除 `archive/`：

- 无候选：不存在 active change 时，不调用 `status`，继续 Shape 调查并在需要时 `create`。
- 恰有一个候选：以其目录名作为 `<change-id>`，再运行：

  ```bash
  python3 "${CLAUDE_SKILL_DIR}/../../scripts/change.py" --project-root "${CLAUDE_PROJECT_DIR}" status --id <change-id> --json
  ```

- 多个候选：fail closed，报告候选目录并要求用户解决歧义；不得猜测 ID、调用 Runtime 或读取 archive。

唯一候选的 `status` 返回后，再核对当前合同、milestone/handoff、HEAD、工作区和相关检查。Runtime 工作包、Git、代码、合同和长期知识各自回答不同问题；冲突时回到对应权威，而非采信旧消息。

## Agent and reviewer

主会话仍是唯一控制器，独占用户 Gate、结果合同判断、`delivery.yaml` 维护、Runtime 调用、最终验证、知识决定、`complete` 和 `archive`。保护主会话上下文是优先使用一个有界 Claude Code Agent 的判断条件：开始当前 milestone 前，以读取广度、预期实现/诊断迭代、原始命令输出体量、必要范围能否清楚界定和已确认结果合同是否保持不变为启发式；不使用 token 或 ctx 数值硬阈值。阅读或诊断密集、合同稳定、范围清晰且可由预期检查验证的局部工作，优先派发 Agent，让其吸收局部探索、测试诊断和原始输出。极小、单一且实现路径明确的工作，以及产品语义、兼容性、权限、外部副作用、不可逆结果、跨 milestone 架构取舍、用户交互、Runtime、Verify、Finish 等控制决定，仍由主会话直接处理，不为形式而派发。agent dispatch 只传递当前 milestone、相关 Acceptance、Constraints/Non-goals、handoff、相关知识路径及读取理由、必要仓库范围和预期检查；不得复制完整知识正文。agent 仅短回传改动、检查和未完成项，不调用 Skill、不继续委派、不接管 Runtime。不新增专用 implementer、固定任务流水线、任务级路径 ownership 或 Runtime 状态。

可选 `nuclio:readonly-reviewer` 只接受明确审查问题、合同、当前 HEAD、changed paths 和必要材料；它只返回 findings。它没有 Bash、写入、Skill、Agent 或继续委派能力。独立审查是按风险和 oracle 需要选择，不是 per-milestone 协议。

## Output

优先报告产品 outcome、changed paths、检查/exit code、关键失败或 archive 事实。知识 proposal 与产品结果分开；一次知识决定后连续完成和归档。不要向 `state.yaml` 写完整 diff、日志、transcript、agent message、snapshot 或事件账本。