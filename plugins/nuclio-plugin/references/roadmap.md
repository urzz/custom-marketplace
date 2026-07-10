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
- shared references for file protocol, Grill Protocol, context manifest, and roadmap
- small deterministic protocol helper scripts for state inspection, gate checks, and preserve/merge state updates

本 MVP 未实现：

- `/nuclio:status`
- `/nuclio:resume`
- hooks
- runtime state automation
- broad scripts beyond small deterministic protocol helpers
- CLI product or CLI-like workflow tooling
- daemon
- MCP
- multi-agent platform
- cross-project RAG
- context budget reporting

## Deferred Capabilities

Deferred work 必须保留相同原则：

- facts live in files
- context loads by manifest
- ambiguity is clarified before execution
- implementation happens by task slice
- verification happens by diff
- only stable knowledge is folded back

Small deterministic protocol helper scripts are allowed in MVP when bounded to state inspection, gate checks, and preserve/merge updates. Broader CLI/runtime capabilities remain deferred, including workflow products, skeleton-generation tooling, hooks, daemons, MCP servers, background automation, and runtime state automation.

## Implementation Sequence

1. 实现 `/nuclio:status`，用于 active change inspection。
2. 实现 `/nuclio:resume`，用于不自动执行的 state recovery。
3. 添加未来可选 scripts，用于 `.dev-docs` skeleton generation 和 broader CLI-like tooling；small deterministic protocol helper scripts for validation are already allowed within the MVP boundary.
4. 添加可选 hooks/runtime，用于 SessionStart breadcrumb 和 `.nuclio/runtime/cache/temp` state。
5. 添加 context budget reporting 和 verify-loop enhancements。

## Acceptance Criteria by Item

### `/nuclio:fold`

Goal：把 completed changes 中的 stable conclusions 写回长期 `.dev-docs` knowledge。

Non-goals：
- no full chat transcript archival
- no raw log archival
- no automatic broad rewrite of all `.dev-docs` documents

Dependencies：
- completed verify evidence
- current change brief/spec/design/plan
- diff summary

Acceptance criteria：
- reads only stable change artifacts and diff summary
- updates only relevant long-term docs
- records architecture decisions or engineering constraints when applicable
- does not duplicate existing knowledge

### `/nuclio:status`

Goal：显示 active change phase、gate、task progress 和 blockers。

Non-goals：
- no automatic task execution
- no context injection

Dependencies：
- active change pointer or user-provided change path
- `state.json`
- `plan.yaml`

Acceptance criteria：
- reports phase/status/current task/gates
- lists pending/blocking tasks
- suggests next command without executing it

### `/nuclio:resume`

Goal：在 session break 后恢复 current working state。

Non-goals：
- no automatic continuation
- no broad context loading

Dependencies：
- active change pointer or user-provided change path
- `state.json`
- `plan.yaml`

Acceptance criteria：
- summarizes where work stopped
- lists required files for next stage
- asks for confirmation before continuing

### Optional scripts

Goal：添加用于 `.dev-docs` skeleton generation 和 broader protocol tooling 的 optional scripts。Small deterministic protocol helper scripts for state inspection, gate checks, and preserve/merge updates are already allowed by the MVP boundary.

Non-goals：
- no full CLI product
- no hidden automation
- no replacement for small MVP protocol helpers that are already allowed

Dependencies：
- stable protocol after MVP usage

Acceptance criteria：
- broader skeleton generation / CLI-like tooling remains deferred until explicitly designed
- small deterministic protocol helper scripts remain bounded by `protocol.md` and must not replace human gates
- skills document exactly when any optional broader scripts may run

### Hooks/runtime

Goal：添加最小 SessionStart breadcrumb 和 runtime state tracking。

Non-goals：
- no Chorus-style context injection
- no daemon task pool

Dependencies：
- proven status/resume protocol

Acceptance criteria：
- breadcrumb stays under 1k context
- breadcrumb includes only active change id, phase, status, current task, state path, plan path
- no brief/design full text injection

### Context budget reporting

Goal：在 stage execution 期间使 context budget 可见。

Non-goals：
- no hard dependency on external RAG
- no automatic cross-project knowledge loading

Dependencies：
- stable manifest format

Acceptance criteria：
- reports estimated loaded context categories
- flags manifest overgrowth
- suggests splitting or summarizing docs when needed
