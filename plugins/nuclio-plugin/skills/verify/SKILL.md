---
name: verify
description: Use when the user wants to validate a Nucl.io change against the current diff, `context/verify.jsonl`, spec acceptance criteria, and plan task acceptance before accepting or fixing it.
---

# Nucl.io Verify

## Critical Constraints

- Verify 只读取 current diff、`context/verify.jsonl`、`spec.md` acceptance、`plan.yaml` task acceptance，以及 verify manifest 明确列出的 engineering testing docs；不得读取完整历史。
- `context/verify.jsonl` 应小于 implement manifest，只携带验证当前 diff 所需的精简上下文。
- 不运行 destructive commands，例如删除、重置、强推、迁移破坏性数据或修改外部状态的命令。
- 不得静默忽略缺失测试或缺失 validation commands；必须在 review 中明确报告缺失项及其影响。
- 默认 self-fix loop 最多 2 轮；MVP skill 在进行 broad fixes 前必须询问用户确认。
- 输出 summaries，不粘贴 raw long logs；长日志只摘录关键错误、命令、退出状态和相关路径。
- `.dev-docs/` 是 Nuclio 项目的 source-of-truth；`.nuclio/` 仅是 runtime/cache/temp state，MVP 不实现 runtime 行为。
- 本 MVP 只验证 prompt/protocol layer；不得要求 hooks、runtime、scripts、CLI、daemon、MCP、multi-agent platform、cross-project RAG 或 context budget automation 已实现。
- 不依赖 `grill-me`；不 fork Trellis；不复制 Chorus 式全量上下文注入。

## Contents

- [Critical Constraints](#critical-constraints)
- [Workflow](#workflow)
- [Phase 1: Determine Verification Scope](#phase-1-determine-verification-scope)
- [Phase 2: Load Verify Context](#phase-2-load-verify-context)
- [Phase 3: Inspect Diff and Acceptance](#phase-3-inspect-diff-and-acceptance)
- [Phase 4: Run Validation Commands](#phase-4-run-validation-commands)
- [Phase 5: Write Verification Review](#phase-5-write-verification-review)
- [Phase 6: Verify Gate](#phase-6-verify-gate)
- [Behavior Verification](#behavior-verification)

## Workflow

使用 Generator-Critic style verification：实现者提供 current diff 与证据，verify 作为 critic 独立核对 diff、verify manifest、acceptance criteria 和 validation commands，并给出 accept / fix / defer 建议。

1. 限定验证范围为 current diff + acceptance criteria + `context/verify.jsonl` + validation commands。
2. 读取 verify manifest 与 acceptance，不展开完整计划或完整历史。
3. 检查 diff 是否满足 spec 与 task acceptance，并确认没有越界实现。
4. 运行非破坏性 validation commands；缺失命令必须记录。
5. 写入 verification review summary，可选写入 `evidence/test-output.md` 或 `evidence/review.md`。
6. 触发 HITL Verify Gate，让用户选择接受、修复或暂缓。

## Phase 1: Determine Verification Scope

验证范围只包含：

- current diff，例如 `git diff` / `git diff --stat` / staged diff（按用户上下文选择）。
- `context/verify.jsonl` 中列出的精简验证上下文。
- `spec.md` acceptance criteria。
- `plan.yaml` 中当前 task acceptance。
- `context/verify.jsonl` 明确列出的 engineering testing docs。
- brief 或用户明确要求的 validation commands。

如果 acceptance criteria、task acceptance 或 validation commands 缺失，不要补造；在 review 中标记为缺失，并说明验证置信度下降。

## Phase 2: Load Verify Context

1. 读取 `context/verify.jsonl`。
2. 只加载 manifest 指向的验证必要文件或片段。
3. 确认 verify manifest 比 implement manifest 更小、更聚焦；如果它过大，报告 bloated context 风险。
4. 将 `.dev-docs/` 视为 source-of-truth。
5. 将 `.nuclio/` 视为 runtime/cache/temp state only；MVP 不验证 runtime 行为是否存在。

## Phase 3: Inspect Diff and Acceptance

检查 current diff 是否：

- 覆盖 `spec.md` acceptance criteria。
- 覆盖 `plan.yaml` 当前 task acceptance。
- 保持 prompt/protocol layer 范围，没有引入 hooks/runtime/scripts/CLI/daemon/MCP/multi-agent platform/cross-project RAG/context budget automation。
- 没有依赖 `grill-me`、fork Trellis、或复制 Chorus 式全量上下文注入。
- 没有把 `.nuclio/` 描述成 source-of-truth，也没有把 `.dev-docs/` 降级为缓存。
- 没有通过无关重构扩大 diff 风险。

## Phase 4: Run Validation Commands

运行 brief、verify manifest 或 acceptance 中列出的非破坏性 validation commands。

命令行为规则：

- 优先运行 exact commands；如命令不可用，记录 command、失败原因和影响。
- 不运行 destructive commands。
- 不静默跳过 tests、typecheck、lint 或 grep marker checks；缺失就报告缺失。
- 输出摘要：命令、退出状态、关键 stdout/stderr 摘录、结论。
- 如发现可小范围修复的问题，可建议 fix；如需要 broad fixes，先询问用户。
- self-fix loop 最多 2 轮，且每轮后重新运行相关 validation commands。

## Phase 5: Write Verification Review

可将验证结论写入 `evidence/review.md`。如果命令输出较长，可将摘要写入 `evidence/test-output.md`。不要写 raw long logs。

使用以下 review 模板：

````markdown
# Verification Review

## Summary

Pass / Fail

## Checked Items

- [ ] Acceptance Criteria
- [ ] Tests
- [ ] Typecheck
- [ ] Lint
- [ ] Regression Risk
- [ ] Architecture Constraints

## Findings

| Severity | Finding | Suggested Fix |
|---|---|---|

## Commands Run

```bash
<commands>
```

## Final Verdict

...
````

Final Verdict 必须给出 recommendation：accept、fix 或 defer。

## Phase 6: Verify Gate

输出 review 后必须停止并等待用户决策：

```text
STOP. Verify Gate：请确认是接受当前结果、进入修复、还是暂缓处理。
```

不要在 Verify Gate 后自动继续 broad fixes、扩大验证范围或读取完整历史。

## Behavior Verification

RED: baseline may rely on tests only or informal review.

GREEN: skill checks diff, manifests, acceptance, commands, and produces verdict.

REFACTOR: no full history, no silent missing tests, no unbounded self-fix, no raw log dumping.
