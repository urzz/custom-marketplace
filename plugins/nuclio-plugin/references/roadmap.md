# Nucl.io Post-MVP Roadmap

## Contents
- [MVP Scope](#mvp-scope)
- [Deferred Capabilities](#deferred-capabilities)
- [Implementation Sequence](#implementation-sequence)
- [Acceptance Criteria by Item](#acceptance-criteria-by-item)

## MVP Scope

本 MVP 已实现：

- `/nuclio:project-init`
- `/nuclio:brief`
- `/nuclio:design`
- `/nuclio:implement`
- `/nuclio:verify`
- `/nuclio:fold`（prompt / protocol layer）
- state/task deterministic helpers，用于状态检查、Gate 检查、recursive merge、change validation 与 Task brief extraction
- task-scoped context manifests 与 deterministic validation/extraction contract；stable manifest context 和 bounded source-chain discovery 边界明确
- 原生 lightweight SDD protocol：Implement 内 sequential、bounded、fresh implementer/reviewer/fixer subagents
- File Protocol 唯一管理分层 snapshots：Task complete 使用 task-scope fingerprint，Implement complete/Verify/Fold 使用 staging-invariant 的 final path→content map global fingerprint；Fold proposal 以 state 外部 metadata 区分 ready/superseded，Verify/Fold 在全部 decision/retry/resume 时点复核 freshness，旧 verdict/proposal 不能跨 drift 批准或 apply
- Fold proposal approval，包括 accept/edit/reject/no-op/defer、approval-before-apply、recoverable two-phase apply 与 apply/no-op 后 close
- Fold focused inputs 与 quality：只读取 stable brief/spec/design/plan artifacts、Verify evidence/verdict 和 scoped product diff summary；适用时提炼 architecture decisions/engineering constraints，apply 前与长期知识去重
- Fold boundaries：verified-only（仅 Verify approved 后进入）、stable-only（只写稳定长期知识）、no raw/full-history（不折叠 raw logs、完整聊天或完整 review/session history）、proposal-first approval（先生成 proposal，再由用户明确批准，最后 idempotent apply/no-op/close）
- shared authorities for file/state protocol、Grill Protocol、context manifest、lightweight SDD 与 roadmap

MVP 边界说明：通用 multi-agent platform/runtime deferred；Implement 内的 bounded task subagents 属于 MVP workflow contract。

目标协议已在 references 中确立。现有 Implement/Verify/Fold Skills 与该 authority 的残余冲突不在 Task 2 修改范围内，明确由 Tasks 5–7 对齐；在完成前不得把当前 Skill 文本当成覆盖 protocol 的 authority。

## Deferred Capabilities

以下能力继续 deferred：

- `/nuclio:status` Skill
- `/nuclio:resume` Skill
- hooks
- runtime automation
- broader CLI product / CLI-like workflow tooling
- daemon 或 background automation
- MCP
- 通用 multi-agent platform/runtime
- cross-project RAG
- automated token/context reporting

Deferred work 必须保留相同原则：

- facts live in files
- context loads by task-scoped manifest
- ambiguity is clarified before execution
- implementation happens by bounded task slice
- verification happens by diff and persisted evidence
- only stable, approved knowledge is folded back
- Fold remains verified-only、stable-only、no raw/full-history、proposal-first approval

Small deterministic protocol helpers 已属于 MVP，但必须保持 bounded：它们只检查/转换显式文件声明，不成为 runtime、hook、daemon、通用 CLI 产品或 hidden automation。

Fold 的长期质量合同保持在 MVP：proposal 由 focused stable inputs 生成，考虑适用的 architecture decisions 与 engineering constraints；apply 前对目标长期文档做等价知识 reconciliation/去重。Raw/full history、未通过 Verify 的结论和过程性噪音不进入长期知识。

## Implementation Sequence

1. 设计并实现 `/nuclio:status`，只做 active change inspection。
2. 设计并实现 `/nuclio:resume`，只做显式 state recovery，不自动继续执行。
3. 在协议稳定后评估可选 broader CLI tooling，例如 `.dev-docs` skeleton generation；不得扩大现有 deterministic helpers 的 authority。
4. 评估可选 hooks/runtime，用于最小 SessionStart breadcrumb 与 `.nuclio/runtime/cache/temp`，但不得隐式推进 workflow。
5. 评估 context reporting 与 verify-loop enhancements；token reporting 不得成为 MVP 隐式依赖。
6. 仅在独立设计后评估通用 multi-agent runtime、MCP 或 cross-project RAG；不得把 Implement bounded subagents 演变为后台平台。

## Acceptance Criteria by Item

### `/nuclio:status`

Goal：显示 active change phase、gate、Task progress 和 blockers。

Non-goals：
- no automatic task execution
- no context injection
- no gate approval

Dependencies：
- active change pointer or user-provided change path
- `state.json`
- `plan.yaml`

Acceptance criteria：
- reports phase/status/current task/gates
- lists pending/blocking Tasks
- distinguishes persisted state from artifact existence
- suggests next command without executing it

### `/nuclio:resume`

Goal：在 session break 后恢复 current working state。

Non-goals：
- no automatic continuation
- no broad context loading
- no reconstruction from full chat history

Dependencies：
- active change pointer or user-provided change path
- `state.json`
- `plan.yaml`
- persisted Task/change evidence

Acceptance criteria：
- summarizes where work stopped from file authority
- lists only manifest-approved files required for the next stage
- asks for confirmation before continuing
- never converts pending Gates to approved

### Optional broader CLI tooling

Goal：在协议经过实际使用后，评估 `.dev-docs` skeleton generation 与 broader protocol tooling。

Non-goals：
- no hidden automation
- no replacement of HITL Gates
- no mutation outside explicit command scope

Dependencies：
- stable protocol after MVP usage
- explicit product design

Acceptance criteria：
- existing state/task helpers remain deterministic and bounded
- broader CLI product behavior is separately specified
- commands state exactly which files they may read/write
- no automatic phase/gate advancement

### Hooks/runtime

Goal：添加最小 SessionStart breadcrumb 和 runtime state tracking。

Non-goals：
- no Chorus-style context injection
- no daemon task pool
- no automatic resume or Gate approval

Dependencies：
- proven status/resume protocol
- explicit runtime authority boundary

Acceptance criteria：
- breadcrumb stays under 1k context
- breadcrumb includes only active change id、phase、status、current task、state path、plan path
- no brief/design full text injection
- runtime cache never supersedes `.dev-docs` state/evidence authority

### Context reporting

Goal：在 stage execution 期间使 context budget 风险可见。

Non-goals：
- no automatic token counting requirement
- no hard dependency on external RAG
- no automatic cross-project knowledge loading

Dependencies：
- stable manifest format
- stable Loaded Context evidence

Acceptance criteria：
- reports loaded context categories and project-relative paths
- flags manifest overgrowth and bloated Verify context
- suggests splitting or summarizing docs when needed
- does not introduce runtime loading or raw history capture

### 通用 multi-agent platform/runtime

Goal：如未来确有需求，提供跨 workflow 的通用 agent scheduling、isolation 与 lifecycle 能力。

Non-goals：
- no reinterpretation of MVP Implement bounded task loop
- no same-working-tree parallel mutation
- no implicit model inheritance or unbounded context sharing

Dependencies：
- separate architecture and safety design
- proven bounded subagent workflow
- explicit state/evidence integration contract

Acceptance criteria：
- remains optional and outside MVP
- preserves file/state/evidence authorities
- defines isolation, scheduling, model and context contracts explicitly
