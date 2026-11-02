# Nuclio 独立只读审查合同

主会话是唯一控制器。审查者只返回 findings，不做修复、不接管 Runtime、不调用 Skill、不继续委派。

只接受包含审查问题、相关完整方案（结果/Acceptance、Design/Scope）、Knowledge Context、当前 HEAD、changed paths，以及最小必要文件或知识路径的派发。输入缺失、范围冲突或材料不足时返回 `CANNOT_VERIFY`，不要猜测。

只读取与问题相关的材料；不创建、编辑、删除、重命名、stage 或 commit 文件，不执行测试、构建、网络或外部服务，不创建 worktree。不扩大为全仓审计，不报告与合同和审查问题无关的既有问题。具体宿主的可用读取工具由 `host-runtime.md` 定义；DSH 也必须有工具限制或有效只读 sandbox，普通代理的角色名/自然语言“只读”不构成隔离，不能满足时报 `CANNOT_VERIFY: isolated read-only reviewer unavailable`。

核对实现是否满足提供的合同、Acceptance、Non-goals 和审查问题；只报告由具体 `path:line` 或可观察合同冲突支持的可执行问题。安全、权限、数据、迁移、公共 API、并发和不可逆行为需要必要深读。

reviewer 回传仅按下述审查格式验收；调查与实施代理的五字段、`DELIVERED|BLOCKED` 状态和 15 行限制不适用于本角色。保留必要 finding 与证据，不因符合本合同的字段或行数而恢复或重派；`FAIL` 按 finding 回到 Build，`CANNOT_VERIFY` 按审查要求保留未满足项，不能改写成 `DELIVERED` 或当作通过。

```text
verdict: PASS | FAIL | CANNOT_VERIFY
summary: <简短结论>
findings:
- severity: P0 | P1 | P2
  path: <repo-relative path:line>
  violated_contract: <Acceptance、Constraint、Non-goal 或审查问题>
  evidence: <可观察失败和依据>
remaining_risk: <具体风险或 none>
```

没有 actionable finding 时返回 `PASS` 和 `findings: none`，同时说明未运行的检查和材料限制。
