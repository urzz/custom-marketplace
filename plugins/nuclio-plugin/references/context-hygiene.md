# Nuclio v3 Context Hygiene

按问题读取权威，不用聊天记录、完整知识库或 Runtime State 副本填充上下文。`.dev-docs/index.md` 是长期知识的唯一入口：索引说明路径、摘要和读取时机，不承载知识正文。

## Phase read order

- **Shape**：用户请求与项目规则 -> `index.md` -> 有明确相关性的知识文件/heading -> 相关代码、测试、配置。
- **Build / recovery**：`status --json` 紧凑工作包 -> 当前 `change.md` -> milestone/handoff -> `index.md` 路由的相关知识 -> 当前实现和测试。
- **Verify**：批准合同、delivery、当前 diff、检查与观察优先；相关知识仅提供稳定约束，不能替代验证依据。
- **Finish**：产品结果与 diff -> 索引路由的受影响知识，用同一次分析判断新增候选和既有结论是否失效。

除非问题明确需要，不读取整个 `.dev-docs/knowledge/**`、archive、legacy、全部 State 或完整 Git diff。先使用 `status --json`，只在漂移或诊断时扩展到精确 Git 状态和相关 artifact。

## Recovery

fresh session 先运行：

```bash
python3 "${CLAUDE_SKILL_DIR}/../../scripts/change.py" --project-root "${CLAUDE_PROJECT_DIR}" status --id <change-id> --json
```

随后核对当前合同、milestone/handoff、HEAD、工作区和相关检查。Runtime 工作包、Git、代码、合同和长期知识各自回答不同问题；冲突时回到对应权威，而非采信旧消息。

## Agent and reviewer

主会话可按需使用 Claude Code Agent，并只传递当前 milestone、相关 Acceptance、Constraints/Non-goals、handoff、相关知识路径及读取理由、必要仓库范围和预期检查。不要复制知识正文或派发固定实现流水线。agent 只返回简短结果与未完成项，不调用 Skill、不继续委派、不接管 Runtime。

可选 `nuclio:readonly-reviewer` 只接受明确审查问题、合同、当前 HEAD、changed paths 和必要材料；它只返回 findings。它没有 Bash、写入、Skill、Agent 或继续委派能力。独立审查是按风险和 oracle 需要选择，不是 per-milestone 协议。

## Output

优先报告产品 outcome、changed paths、检查/exit code、关键失败或 archive 事实。知识 proposal 与产品结果分开；一次知识决定后连续完成和归档。不要向 `state.yaml` 写完整 diff、日志、transcript、agent message、snapshot 或事件账本。