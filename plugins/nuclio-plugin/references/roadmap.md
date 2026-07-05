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
- shared references for file protocol, Grill Protocol, context manifest, and roadmap

本 MVP 未实现：

- `/nuclio:fold`
- `/nuclio:status`
- `/nuclio:resume`
- hooks
- runtime state automation
- scripts
- CLI
- daemon
- MCP
- multi-agent platform
- cross-project RAG
- automatic token budget reporting

## Deferred Capabilities

Deferred work 必须保留相同原则：

- facts live in files
- context loads by manifest
- ambiguity is clarified before execution
- implementation happens by task slice
- verification happens by diff
- only stable knowledge is folded back

## Implementation Sequence

1. 实现 `/nuclio:fold`，用于把 stable knowledge write-back 到长期 `.dev-docs` knowledge。
2. 实现 `/nuclio:status`，用于 active change inspection。
3. 实现 `/nuclio:resume`，用于不自动执行的 state recovery。
4. 添加可选 scripts，用于 `.dev-docs` skeleton generation 和 protocol validation。
5. 添加可选 hooks/runtime，用于 SessionStart breadcrumb 和 `.nuclio/runtime/cache/temp` state。
6. 添加 context budget reporting 和 verify-loop enhancements。

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

Goal：添加用于 skeleton generation 和 protocol validation 的 deterministic helpers。

Non-goals：
- no full CLI product
- no hidden automation

Dependencies：
- stable protocol after MVP usage

Acceptance criteria：
- scripts are small and deterministic
- scripts do not replace human gates
- skills document exactly when scripts may run

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
