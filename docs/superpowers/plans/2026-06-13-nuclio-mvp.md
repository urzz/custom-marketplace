# Nucl.io MVP Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在当前 marketplace 仓库中落地一个首版 `nuclio` plugin，同时跑通 `project-init` 与 `spec → design → build → close` 两条最小可信闭环。

**Architecture:** 采用 plugin-first 结构：marketplace 只负责发现 `nuclio`，插件内部承载 skills / agents / hooks / scripts，运行时 artifact 写入用户项目的 `.nuclio/` 与 `.dev-docs/`。首版优先实现 artifact、gate、state、review、guard 的最小可信闭环，再补轻量增强项。

**Tech Stack:** JSON、Markdown、JavaScript (`.mjs` hooks/scripts)、Claude Code plugin manifests、现有 marketplace 目录结构。

---

## File Map

- `.claude-plugin/marketplace.json`
  - 现有 marketplace 注册表；需要新增 `nuclio` plugin 条目。
- `plugins/nuclio/.claude-plugin/plugin.json`
  - `nuclio` 插件元数据入口。
- `plugins/nuclio/README.md`
  - 说明 plugin 的目标、目录结构、MVP 边界与使用入口。
- `plugins/nuclio/skills/*/SKILL.md`
  - 7 个核心 workflow skill：`project-init`、`spec`、`design`、`build`、`close`、`resume`、`apply-memory`。
- `plugins/nuclio/skills/*/templates/*`
  - 各 phase 生成 artifact 的最小模板集合。
- `plugins/nuclio/agents/reviewer.md`
  - build 阶段独立审查视角。
- `plugins/nuclio/agents/debugger.md`
  - 失败定位建议器（首版轻量）。
- `plugins/nuclio/agents/browser-verifier.md`
  - UI 验证代理（首版轻量，依赖 `dev-browser` skill）。
- `plugins/nuclio/hooks/hooks.json`
  - hook 注册入口。
- `plugins/nuclio/hooks/guard.mjs`
  - `.dev-docs/` 写入审批、build 路径约束、危险 bash 拦截。
- `plugins/nuclio/hooks/event-log.mjs`
  - 关键事件记录到 `.nuclio/.../events.jsonl`。
- `plugins/nuclio/hooks/output-filter.mjs`
  - 首版轻量输出裁剪器。
- `plugins/nuclio/scripts/read-state.mjs`
  - 读取 project/change state 的统一入口。
- `plugins/nuclio/scripts/write-state.mjs`
  - 写入 state 的统一入口。
- `plugins/nuclio/scripts/append-event.mjs`
  - 追加事件的统一入口。

---

### Task 1: 注册 `nuclio` plugin 并建立目录骨架

**Files:**
- Modify: `.claude-plugin/marketplace.json`（`plugins` 数组）
- Create: `plugins/nuclio/.claude-plugin/plugin.json`
- Create: `plugins/nuclio/README.md`
- Create: `plugins/nuclio/skills/.gitkeep`
- Create: `plugins/nuclio/agents/.gitkeep`
- Create: `plugins/nuclio/hooks/.gitkeep`
- Create: `plugins/nuclio/scripts/.gitkeep`

**Steps:**
- [ ] **Step 1: 修改 marketplace 注册表，加入 `nuclio` 条目**

```json
{
  "name": "jade-tools-marketplace",
  "owner": {
    "name": "Jade Liu",
    "email": "[redacted-email]"
  },
  "plugins": [
    {
      "name": "openclaw-plugin",
      "source": "./plugins/openclaw-plugin",
      "description": "Adds a /openclaw-skill-creator skill for drafting OpenClaw skills"
    },
    {
      "name": "dev-stack",
      "source": "./plugins/dev-stack",
      "description": "Dev stack plugin with dev rel skills"
    },
    {
      "name": "nuclio",
      "source": "./plugins/nuclio",
      "description": "Nucl.io workflow plugin for project initialization and spec-driven change delivery"
    }
  ]
}
```

- [ ] **Step 2: 创建 `plugins/nuclio/.claude-plugin/plugin.json`**

```json
{
  "name": "nuclio",
  "description": "Nucl.io workflow plugin for project initialization and spec-driven change delivery",
  "version": "0.1.0"
}
```

- [ ] **Step 3: 创建 `plugins/nuclio/README.md`，说明首版边界与目录职责**

```md
# Nucl.io Plugin

Nucl.io 是一个 Claude Code marketplace plugin，提供：

- `/nuclio:project-init`
- `/nuclio:spec`
- `/nuclio:design`
- `/nuclio:build`
- `/nuclio:close`
- `/nuclio:resume`
- `/nuclio:apply-memory`

## 首版 MVP

首版同时覆盖两条闭环：

1. Project Init
2. Change Workflow: Spec → Design → Build → Close

首版优先保证：
- plugin 可发现
- artifact 可产出
- gate 会停住
- build 有 verify/review
- `.dev-docs/` 写入受 guard 约束

## 目录职责

- `skills/`：workflow entrypoints
- `agents/`：独立视角代理
- `hooks/`：deterministic enforcement
- `scripts/`：底层状态/事件协议辅助
```

- [ ] **Step 4: 创建基础目录占位文件**

```text
plugins/nuclio/skills/.gitkeep
plugins/nuclio/agents/.gitkeep
plugins/nuclio/hooks/.gitkeep
plugins/nuclio/scripts/.gitkeep
```

- [ ] **Step 5 (验证): 校验 JSON、目录和 README 已就位**

Run:
```bash
jq . .claude-plugin/marketplace.json >/dev/null && \
jq . plugins/nuclio/.claude-plugin/plugin.json >/dev/null && \
find plugins/nuclio -maxdepth 2 -type f | sort
```

Expected:
- 命令退出码为 0
- 输出包含 `plugin.json`、`README.md` 和四个 `.gitkeep`

- [ ] **Step 6: 提交本任务**

```bash
git add .claude-plugin/marketplace.json plugins/nuclio
git commit -m "feat(nuclio): add plugin skeleton"
```

**Acceptance Criteria:**
- 保持 marketplace manifest、plugin 名称、插件目录三者一致，满足 plugin-first 架构约束。
- 本任务只建立容器与入口，不提前实现 workflow 逻辑，避免 project facts 混入 plugin 层。
- 完成后仓库必须能够静态表达一个合法的 `nuclio` marketplace plugin。

---

### Task 2: 实现 `/nuclio:project-init` 与初始化模板

**Files:**
- Create: `plugins/nuclio/skills/project-init/SKILL.md`
- Create: `plugins/nuclio/skills/project-init/templates/project-brief-template.md`
- Create: `plugins/nuclio/skills/project-init/templates/architecture-baseline-template.md`
- Create: `plugins/nuclio/skills/project-init/templates/scaffold-plan-template.yaml`
- Create: `plugins/nuclio/skills/project-init/templates/initial-dev-docs-patch-template.md`

**Steps:**
- [ ] **Step 1: 创建 `project-brief-template.md` 与 `architecture-baseline-template.md`**

```md
# Project Brief: <project name>

## Raw Idea
## Problem Statement
## Target Users
## Jobs To Be Done
## MVP Scope
## Non-MVP Scope
## Success Criteria
## Operating Constraints
## Product Risks
## Open Questions
## Foundation Decisions
```

```md
# Architecture Baseline: <project name>

## Architecture Drivers
## Technology Stack Decision
## System Shape
## Module Boundaries
## Directory Baseline
## Data Model Baseline
## API / Interface Boundary
## Configuration and Secrets
## Error Handling Baseline
## Testing Baseline
## Build and Run Baseline
## Deployment Baseline
## Decision Log
## Deferred Decisions
```

- [ ] **Step 2: 创建 `scaffold-plan-template.yaml` 与 `initial-dev-docs-patch-template.md`**

```yaml
project_id: <project-name>
version: 1
mode: project_initialization

foundation:
  brief: .nuclio/project/project-brief.md
  architecture: .nuclio/project/architecture-baseline.md

scaffold_tasks: []

initial_dev_docs:
  patch: .nuclio/project/initial-dev-docs.patch.md
  apply_after_approval: true

global_acceptance:
  - project has a clear architecture baseline
  - project has initial .dev-docs after approval
```

```md
# Initial Dev Docs Patch: <project name>

## Source
- Project Brief: `.nuclio/project/project-brief.md`
- Architecture Baseline: `.nuclio/project/architecture-baseline.md`
- Scaffold Plan: `.nuclio/project/scaffold-plan.yaml`

## Summary

## Proposed Files

## Deferred Docs

## Approval Checklist
- [ ] Files are useful now, not empty placeholders.
- [ ] Index routing is minimal and clear.
- [ ] Architecture decisions match approved baseline.
- [ ] No secrets or local-only accidental data.
```

- [ ] **Step 3: 创建 `/nuclio:project-init` 的 `SKILL.md`**

```md
---
name: project-init
description: Use when the repository is new, lacks architecture foundation, or the user wants to establish project baseline before feature work.
---

# Nucl.io Project Init

## Goal
生成或更新 `.nuclio/project/` 下的项目初始化产物，并在每个关键 gate 停止等待确认。

## Inputs
- 用户对项目的原始描述
- 当前仓库结构与关键配置文件
- 已存在的 `.nuclio/project/` 产物（如有）

## Outputs
- `.nuclio/project/project-brief.md`
- `.nuclio/project/architecture-baseline.md`
- `.nuclio/project/scaffold-plan.yaml`
- `.nuclio/project/init-state.json`
- `.nuclio/project/events.jsonl`
- `.nuclio/project/initial-dev-docs.patch.md`

## Rules
- 不要把 project initialization 当成 feature spec。
- 不要创建 `.claude/skills`、`.claude/agents`、`.claude/hooks`、`.claude/rules`。
- 未获得 Initial Dev Docs Approval 前，不要写 `.dev-docs/`。
- 优先最小架构基线，不做过度脚手架。

## Workflow
1. Inspect repository state and determine repository stage.
2. 通过苏格拉底式提问澄清项目目标与 MVP 边界。
3. 生成 `project-brief.md`，等待 Foundation Approval。
4. 生成 `architecture-baseline.md`，等待 Architecture Approval。
5. 生成 `scaffold-plan.yaml`，等待 Scaffold Approval。
6. 生成 `initial-dev-docs.patch.md`，等待 Initial Dev Docs Approval。
7. Approval 后才允许建议应用最小 `.dev-docs/` 更新。

## Stop Condition
每个 approval gate 都必须暂停，等待用户明确确认。
```

- [ ] **Step 4 (验证): 确认 skill 与模板同时覆盖 project-init 闭环的四个 gate 和六个 artifact**

Run:
```bash
grep -n "Foundation Approval\|Architecture Approval\|Scaffold Approval\|Initial Dev Docs Approval" plugins/nuclio/skills/project-init/SKILL.md && \
find plugins/nuclio/skills/project-init -maxdepth 2 -type f | sort
```

Expected:
- `SKILL.md` 中能找到四个 gate 名称
- 目录输出包含 `SKILL.md` 和 4 个模板文件

- [ ] **Step 5: 提交本任务**

```bash
git add plugins/nuclio/skills/project-init
git commit -m "feat(nuclio): add project-init skill"
```

**Acceptance Criteria:**
- 本任务必须建立 project-init 的最小闭环骨架：目标是项目级基础建设，而不是单次变更 spec。
- Pattern 结构约束：skill body 负责流程、gate、输入输出；模板承载 artifact 结构；不得把 `.dev-docs/` 直接写入流程中。
- 验收标准：`project-init` 必须显式覆盖 4 个 approval gate 和 6 个 project artifact，且说明“未批准前不写 `.dev-docs/`”。

---

### Task 3: 实现 `/nuclio:spec` 与 `/nuclio:design` skills

**Files:**
- Create: `plugins/nuclio/skills/spec/SKILL.md`
- Create: `plugins/nuclio/skills/spec/templates/spec-template.md`
- Create: `plugins/nuclio/skills/design/SKILL.md`
- Create: `plugins/nuclio/skills/design/templates/design-template.md`
- Create: `plugins/nuclio/skills/design/templates/plan-template.yaml`

**Steps:**
- [ ] **Step 1: 创建 `spec-template.md`**

```md
# Spec: <change title>

## Raw Requirement
## Clarification Notes
## First-Principles Summary
- Essential problem:
- Minimal value:
- Invariants:
- Non-essential preferences:
- Minimal verification loop:

## Interpreted Goal
## User Outcomes
## Non-Goals
## Acceptance Criteria
## Open Questions
## Codebase Evidence
## Business Context
## Constraints
## Assumptions
## Risks
```

- [ ] **Step 2: 创建 `/nuclio:spec` 的 `SKILL.md`**

```md
---
name: spec
description: Use when the user provides a feature, bugfix, refactor, or maintenance request that needs requirement clarification before implementation.
---

# Nucl.io Spec

## Goal
将单次变更需求收敛为可审批的 `spec.md`，并记录最小状态与上下文证据。

## Rules
- 先做 Socratic Clarification，再做 First-Principles Convergence。
- 若仓库缺少 foundation，可建议 `/nuclio:project-init`，但不要强制阻塞。
- 不实现代码，不产出 design，不跳到 build。
- 如存在 `.dev-docs/index.md`，先从根索引开始选择上下文，不全量扫描。

## Outputs
- `.nuclio/changes/<change-id>/spec.md`
- `.nuclio/changes/<change-id>/state.json`
- `.nuclio/changes/<change-id>/events.jsonl`

## Stop Condition
生成 `spec.md` 后必须停在 Spec Approval。
```

- [ ] **Step 3: 创建 `design-template.md` 与 `plan-template.yaml`**

```md
# Design: <change title>

## Current Architecture
## Relevant Existing Modules
## Architecture Constraints
## Proposed Design
## Alternatives
## Module Boundaries
## Data Model Impact
## API / Interface Impact
## Error Handling
## Security Considerations
## Implementation Plan Summary
## Test Strategy
## Risks and Mitigations
```

```yaml
change_id: <change-id>
version: 1

source:
  spec: .nuclio/changes/<change-id>/spec.md
  design: .nuclio/changes/<change-id>/design.md

tasks: []

global_acceptance:
  - all Spec acceptance criteria are satisfied
  - no forbidden paths are modified
  - verification evidence exists
  - review passes
```

- [ ] **Step 4: 创建 `/nuclio:design` 的 `SKILL.md`**

```md
---
name: design
description: Use after Spec Approval to turn an approved Nucl.io change spec into architecture-grounded design and plan artifacts.
---

# Nucl.io Design

## Goal
基于已批准 spec 和真实代码库结构生成 `design.md` 与 `plan.yaml`。

## Rules
- 开始前先确认 Spec Approval。
- 重新基于代码与项目架构接地，不做空想设计。
- 不改应用代码，不直接写 `.dev-docs/`。
- `plan.yaml` 必须是任务图，不是松散 TODO。

## Outputs
- `.nuclio/changes/<change-id>/design.md`
- `.nuclio/changes/<change-id>/plan.yaml`
- `.nuclio/changes/<change-id>/state.json`
- `.nuclio/changes/<change-id>/events.jsonl`

## Stop Condition
生成 design 与 plan 后必须停在 Design Approval。
```

- [ ] **Step 5 (验证): 静态检查 spec/design 技能是否覆盖各自 artifact 与 gate**

Run:
```bash
grep -n "Spec Approval" plugins/nuclio/skills/spec/SKILL.md && \
grep -n "Design Approval" plugins/nuclio/skills/design/SKILL.md && \
find plugins/nuclio/skills/spec plugins/nuclio/skills/design -maxdepth 2 -type f | sort
```

Expected:
- 两个 gate 都能被 grep 到
- 输出包含 2 个 `SKILL.md` 和 3 个模板文件

- [ ] **Step 6: 提交本任务**

```bash
git add plugins/nuclio/skills/spec plugins/nuclio/skills/design
git commit -m "feat(nuclio): add spec and design skills"
```

**Acceptance Criteria:**
- 业务意图：把单次变更分成“需求澄清契约”与“实现设计/任务图”两步，避免 spec/design 混责。
- Pattern 结构约束：`spec` 只产出 `spec.md` 与最小状态；`design` 只产出 `design.md` + `plan.yaml`；两者都必须停在各自 approval gate。
- 验收标准：`spec` 明确 Socratic Clarification、First-Principles、Codebase Grounding；`design` 明确 architecture-grounded plan，不实现代码。

---

### Task 4: 实现 `/nuclio:build`、模板与 `reviewer` agent

**Files:**
- Create: `plugins/nuclio/skills/build/SKILL.md`
- Create: `plugins/nuclio/skills/build/templates/verify-template.md`
- Create: `plugins/nuclio/skills/build/templates/review-template.md`
- Create: `plugins/nuclio/agents/reviewer.md`

**Steps:**
- [ ] **Step 1: 创建 `verify-template.md` 与 `review-template.md`**

```md
# Verify Evidence

## Local Verification
| Task | Check | Result | Notes |
|---|---|---|---|

## Global Verification
| Check | Result | Notes |
|---|---|---|

## Failed Checks

## Coverage Notes

## Browser Verification
```

```md
# Review Evidence

## Scope Review
## Spec Compliance
## Design Compliance
## Correctness Review
## Security Review
## Maintainability Review
## Test Quality Review
## Result
pass | needs_patch | needs_redesign | blocked
## Required Patches
```

- [ ] **Step 2: 创建 `/nuclio:build` 的 `SKILL.md`**

```md
---
name: build
description: Use after Design Approval to execute Nucl.io plan tasks, produce verification evidence, review the diff, and patch issues before close.
---

# Nucl.io Build

## Goal
按 `plan.yaml` 执行当前 change 的任务，并产出 `verify.md` 与 `review.md` 证据。

## Rules
- 开始前先确认 Design Approval。
- 按任务依赖顺序执行，不跳过验证与审查。
- 只加载 task-local context。
- 尊重 `allowed_paths` 与 `forbidden_paths`。
- Build 阶段禁止修改 `.dev-docs/`。
- 若 verify 或 review 失败，可进入 patch loop；若设计失效或达到重试上限，必须停下并请求人工决策。

## Outputs
- code changes
- `.nuclio/changes/<change-id>/evidence/verify.md`
- `.nuclio/changes/<change-id>/evidence/review.md`
- `.nuclio/changes/<change-id>/state.json`
- `.nuclio/changes/<change-id>/events.jsonl`

## Stop Condition
所有任务完成且 verify/review 通过，或出现需要人工介入的阻塞。
```

- [ ] **Step 3: 创建 `agents/reviewer.md`**

```md
---
name: nuclio-reviewer
description: Independent Nucl.io reviewer for build output.
tools: Read, Bash
model: sonnet
maxTurns: 12
disallowedTools: Write, Edit, MultiEdit
---

# Nucl.io Reviewer

## Read
- `.nuclio/changes/<change-id>/spec.md`
- `.nuclio/changes/<change-id>/design.md`
- `.nuclio/changes/<change-id>/plan.yaml`
- `.nuclio/changes/<change-id>/evidence/verify.md`
- current git diff

## Review Dimensions
- Scope control
- Spec compliance
- Design compliance
- Correctness
- Security
- Maintainability
- Test quality

## Output
生成适合写入 `evidence/review.md` 的审查结论，结果必须是：`pass`、`needs_patch`、`needs_redesign` 或 `blocked`。
```

- [ ] **Step 4 (验证): 确认 build 技能明确要求 verify/review evidence，且 reviewer 为只读代理**

Run:
```bash
grep -n "verify.md\|review.md\|patch loop" plugins/nuclio/skills/build/SKILL.md && \
grep -n "disallowedTools: Write, Edit, MultiEdit" plugins/nuclio/agents/reviewer.md
```

Expected:
- `build/SKILL.md` 中可见 evidence 与 patch loop 规则
- `reviewer.md` 显示 reviewer 不允许写文件

- [ ] **Step 5: 提交本任务**

```bash
git add plugins/nuclio/skills/build plugins/nuclio/agents/reviewer.md
git commit -m "feat(nuclio): add build skill and reviewer"
```

**Acceptance Criteria:**
- 业务意图：证明 Nucl.io 不是“写完即完成”，而是“实现 → 验证 → 审查 → 修复”的最小可信闭环。
- Pattern 结构约束：build 只执行 plan，不越权改 spec/design 或 `.dev-docs/`；reviewer 必须是独立只读视角。
- 验收标准：必须存在 `verify.md`、`review.md` 模板与 reviewer agent；`build` 必须说明 patch loop 与人工介入条件。

---

### Task 5: 实现 `/nuclio:close`、`/nuclio:resume` 与 `/nuclio:apply-memory`

**Files:**
- Create: `plugins/nuclio/skills/close/SKILL.md`
- Create: `plugins/nuclio/skills/close/templates/close-template.md`
- Create: `plugins/nuclio/skills/close/templates/memory-patch-template.md`
- Create: `plugins/nuclio/skills/resume/SKILL.md`
- Create: `plugins/nuclio/skills/apply-memory/SKILL.md`

**Steps:**
- [ ] **Step 1: 创建 `close-template.md` 与 `memory-patch-template.md`**

```md
# Close: <change title>

## Final Outcome
## Final Diff Summary
## Acceptance Mapping
## Verification Summary
## Review Summary
## Known Limitations
## Manual QA Notes
## Memory Candidates
```

```md
# Memory Patch: <change-id>

## Source
- Spec: `spec.md`
- Design: `design.md`
- Plan: `plan.yaml`
- Verify: `evidence/verify.md`
- Review: `evidence/review.md`
- Close: `close.md`
- Events: `events.jsonl`

## Summary
## Proposed Updates
## Rejected Candidates
## Stale Checks
```

- [ ] **Step 2: 创建 `/nuclio:close` 的 `SKILL.md`**

```md
---
name: close
description: Use when build work is done and evidence exists, to summarize the change and prepare a memory patch for approval.
---

# Nucl.io Close

## Goal
生成 `close.md` 与 `memory.patch.md`，并在 Memory Approval 停止。

## Rules
- 没有 verify/review 证据时，不要声称完成。
- `memory.patch.md` 是候选补丁，不是直接写入 `.dev-docs/` 的指令。
- 仅允许沉淀稳定、已验证、可复用的项目知识。

## Outputs
- `.nuclio/changes/<change-id>/close.md`
- `.nuclio/changes/<change-id>/memory.patch.md`
- `.nuclio/changes/<change-id>/state.json`
- `.nuclio/changes/<change-id>/events.jsonl`

## Stop Condition
生成 memory patch 后必须等待 Memory Approval。
```

- [ ] **Step 3: 创建 `/nuclio:resume` 与 `/nuclio:apply-memory` 的 `SKILL.md`**

```md
---
name: resume
description: Use when a Nucl.io session was interrupted or the user asks to continue and recover the next valid workflow step.
---

# Nucl.io Resume

## Goal
读取 `.nuclio/project/init-state.json` 与 `.nuclio/changes/*/state.json`，总结当前 workflow 状态并建议下一步。

## Rules
- 不自动越过任何 gate。
- 如果处于 waiting_human，明确指出 gate 与下一步 skill。
- 如果缺少 foundation 或 active change，说明风险与建议动作。
```

```md
---
name: apply-memory
description: Use when the user has approved an initial dev docs patch or memory patch and wants those updates applied to .dev-docs.
---

# Nucl.io Apply Memory

## Goal
只应用已经获得批准的 `.nuclio/project/initial-dev-docs.patch.md` 或 `.nuclio/changes/<change-id>/memory.patch.md` 更新。

## Rules
- 没有 approval 时禁止写 `.dev-docs/`。
- 只应用 `accept` 或 `edit` 后确认的更新。
- 如需更新索引，必须与新文档一起同步。
```

- [ ] **Step 4 (验证): 检查 close/resume/apply-memory 是否覆盖 memory approval、状态恢复、审批后回写三件事**

Run:
```bash
grep -n "Memory Approval" plugins/nuclio/skills/close/SKILL.md && \
grep -n "不自动越过任何 gate" plugins/nuclio/skills/resume/SKILL.md && \
grep -n "没有 approval 时禁止写 `.dev-docs/`" plugins/nuclio/skills/apply-memory/SKILL.md
```

Expected:
- 三个 grep 都匹配成功

- [ ] **Step 5: 提交本任务**

```bash
git add plugins/nuclio/skills/close plugins/nuclio/skills/resume plugins/nuclio/skills/apply-memory
git commit -m "feat(nuclio): add close resume and apply-memory skills"
```

**Acceptance Criteria:**
- 业务意图：把 change workflow 收尾、状态恢复、知识回写拆成独立步骤，防止 build/close/resume/apply-memory 混责。
- Pattern 结构约束：`close` 只生成总结与 patch，`resume` 只读状态给建议，`apply-memory` 只应用已批准更新。
- 验收标准：必须显式出现 Memory Approval、不得绕过 approval 写 `.dev-docs/`、不得由 `resume` 自动推进 phase。

---

### Task 6: 实现最小 scripts，用于状态与事件协议复用

**Files:**
- Create: `plugins/nuclio/scripts/read-state.mjs`
- Create: `plugins/nuclio/scripts/write-state.mjs`
- Create: `plugins/nuclio/scripts/append-event.mjs`

**Steps:**
- [ ] **Step 1: 创建 `read-state.mjs`，统一读取 project/change state**

```js
import fs from 'node:fs';
import path from 'node:path';

const target = process.argv[2];
if (!target) {
  console.error('usage: node read-state.mjs <state-file>');
  process.exit(1);
}

const filePath = path.resolve(process.cwd(), target);
if (!fs.existsSync(filePath)) {
  console.log('null');
  process.exit(0);
}

const raw = fs.readFileSync(filePath, 'utf8');
console.log(raw.trim() || 'null');
```

- [ ] **Step 2: 创建 `write-state.mjs`，统一覆盖写入 JSON state**

```js
import fs from 'node:fs';
import path from 'node:path';

const target = process.argv[2];
const payload = process.argv[3];
if (!target || !payload) {
  console.error('usage: node write-state.mjs <state-file> <json-string>');
  process.exit(1);
}

const filePath = path.resolve(process.cwd(), target);
fs.mkdirSync(path.dirname(filePath), { recursive: true });
const parsed = JSON.parse(payload);
fs.writeFileSync(filePath, `${JSON.stringify(parsed, null, 2)}\n`);
console.log(filePath);
```

- [ ] **Step 3: 创建 `append-event.mjs`，统一追加 JSONL 事件**

```js
import fs from 'node:fs';
import path from 'node:path';

const target = process.argv[2];
const payload = process.argv[3];
if (!target || !payload) {
  console.error('usage: node append-event.mjs <events-file> <json-string>');
  process.exit(1);
}

const filePath = path.resolve(process.cwd(), target);
fs.mkdirSync(path.dirname(filePath), { recursive: true });
const parsed = JSON.parse(payload);
fs.appendFileSync(filePath, `${JSON.stringify(parsed)}\n`);
console.log(filePath);
```

- [ ] **Step 4 (验证): 用临时文件验证三个脚本可读、可写、可追加**

Run:
```bash
node plugins/nuclio/scripts/write-state.mjs /tmp/nuclio-state.json '{"workflow":"change","phase":"spec"}' && \
node plugins/nuclio/scripts/read-state.mjs /tmp/nuclio-state.json && \
node plugins/nuclio/scripts/append-event.mjs /tmp/nuclio-events.jsonl '{"type":"change.created"}' && \
cat /tmp/nuclio-events.jsonl
```

Expected:
- 第一条输出 `/tmp/nuclio-state.json`
- 第二条输出包含 `"workflow": "change"`
- 第三条后 `nuclio-events.jsonl` 包含一行 `{"type":"change.created"}`

- [ ] **Step 5: 提交本任务**

```bash
git add plugins/nuclio/scripts
git commit -m "feat(nuclio): add state and event scripts"
```

**Acceptance Criteria:**
- 业务意图：把 state 与 event 的底层协议抽到可复用脚本，避免 skill/hook 重复拼 JSON。
- Pattern 结构约束：scripts 只做确定性文件读写，不承载 workflow 推理或交互逻辑。
- 验收标准：三个脚本都能通过命令行读写本地临时文件，并分别完成“读状态 / 写状态 / 追加事件”单一职责。

---

### Task 7: 实现 hooks 注册、`guard.mjs` 与 `event-log.mjs`

**Files:**
- Create: `plugins/nuclio/hooks/hooks.json`
- Create: `plugins/nuclio/hooks/guard.mjs`
- Create: `plugins/nuclio/hooks/event-log.mjs`

**Steps:**
- [ ] **Step 1: 创建 `hooks.json` 注册 PreToolUse / PostToolUse**

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit|Bash",
        "hooks": [
          {
            "type": "command",
            "command": "node ${CLAUDE_PLUGIN_ROOT}/hooks/guard.mjs"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit|Bash",
        "hooks": [
          {
            "type": "command",
            "command": "node ${CLAUDE_PLUGIN_ROOT}/hooks/event-log.mjs"
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 2: 创建 `guard.mjs`，先实现首版最小阻断规则**

```js
const input = process.env.CLAUDE_TOOL_INPUT || '';
const cwd = process.cwd();

const touchesDevDocs = input.includes('.dev-docs/');
const isDangerousBash = /(git push|kubectl|terraform apply|rm -rf|drop database)/.test(input);

if (touchesDevDocs) {
  console.error('Blocked: writing .dev-docs requires explicit Nucl.io approval state.');
  process.exit(2);
}

if (isDangerousBash) {
  console.error('Blocked: dangerous bash command requires human approval.');
  process.exit(2);
}

console.log(`guard ok: ${cwd}`);
```

- [ ] **Step 3: 创建 `event-log.mjs`，记录最小工具事件摘要**

```js
const tool = process.env.CLAUDE_TOOL_NAME || 'unknown';
const input = process.env.CLAUDE_TOOL_INPUT || '';
const output = process.env.CLAUDE_TOOL_OUTPUT || '';

const summary = {
  tool,
  input: input.slice(0, 500),
  output: output.slice(0, 500)
};

console.log(JSON.stringify(summary));
```

- [ ] **Step 4 (验证): 静态校验 hooks JSON，并手动触发 guard 的阻断逻辑**

Run:
```bash
jq . plugins/nuclio/hooks/hooks.json >/dev/null && \
CLAUDE_TOOL_INPUT='Write .dev-docs/index.md' node plugins/nuclio/hooks/guard.mjs ; test $? -eq 2
```

Expected:
- `hooks.json` 解析成功
- `guard.mjs` 对 `.dev-docs/` 写入返回退出码 `2`

- [ ] **Step 5: 提交本任务**

```bash
git add plugins/nuclio/hooks
git commit -m "feat(nuclio): add hook guard and event logging"
```

**Acceptance Criteria:**
- 业务意图：为 `.dev-docs/` 审批约束与危险 bash 提供 deterministic enforcement，而不是只靠 prompt 自觉。
- Pattern 结构约束：hook 只做确定性检查与记录，不在 hook 内实现需求理解、Spec 或 Design 决策。
- 验收标准：`hooks.json` 合法；`guard.mjs` 至少能拦 `.dev-docs/` 与危险 bash；`event-log.mjs` 至少输出工具事件摘要。

---

### Task 8: 补齐轻量 agents 与输出过滤器

**Files:**
- Create: `plugins/nuclio/agents/debugger.md`
- Create: `plugins/nuclio/agents/browser-verifier.md`
- Create: `plugins/nuclio/hooks/output-filter.mjs`

**Steps:**
- [ ] **Step 1: 创建 `debugger.md`**

```md
---
name: nuclio-debugger
description: Read-only debugger for failed Nucl.io build checks.
tools: Read, Bash
model: sonnet
maxTurns: 12
disallowedTools: Write, Edit, MultiEdit
---

# Nucl.io Debugger

## Input
- failing log
- current task from `plan.yaml`
- relevant diff

## Output
- root cause
- smallest next patch
- checks to rerun
```

- [ ] **Step 2: 创建 `browser-verifier.md`**

```md
---
name: nuclio-browser-verifier
description: Read-only browser verifier for UI-related Nucl.io build tasks.
tools: Read, Bash
model: sonnet
maxTurns: 12
disallowedTools: Write, Edit, MultiEdit
skills:
  - dev-browser
---

# Nucl.io Browser Verifier

## Goal
当任务涉及 UI 或端到端用户流时，调用 `dev-browser` 收集验证证据。

## Output
- tested flow
- environment
- steps performed
- observed result
- remaining manual QA notes
```

- [ ] **Step 3: 创建 `output-filter.mjs`**

```js
const input = process.env.CLAUDE_TOOL_OUTPUT || '';
const lines = input.split('\n');
const filtered = lines.filter((line) => /FAIL|ERROR|Traceback|Expected|Actual/.test(line));
console.log((filtered.length ? filtered : lines.slice(-20)).join('\n'));
```

- [ ] **Step 4 (验证): 确认两个 agent 是只读的，且 output filter 能提取失败摘要**

Run:
```bash
grep -n "disallowedTools: Write, Edit, MultiEdit" plugins/nuclio/agents/debugger.md plugins/nuclio/agents/browser-verifier.md && \
CLAUDE_TOOL_OUTPUT=$'line1\nFAIL example\nline3' node plugins/nuclio/hooks/output-filter.mjs
```

Expected:
- 两个 agent 文件都匹配只读限制
- `output-filter.mjs` 输出至少包含 `FAIL example`

- [ ] **Step 5: 提交本任务**

```bash
git add plugins/nuclio/agents/debugger.md plugins/nuclio/agents/browser-verifier.md plugins/nuclio/hooks/output-filter.mjs
git commit -m "feat(nuclio): add helper agents and output filter"
```

**Acceptance Criteria:**
- 业务意图：为 build 失败修复和 UI 验证提供最小独立视角，但不把这些增强项做成首版重心。
- Pattern 结构约束：debugger、browser-verifier 都必须是只读代理；output-filter 只做输出裁剪，不做流程判断。
- 验收标准：两个代理都明确输入/输出与只读限制；output-filter 至少能从失败日志中保留关键信息。

---

### Task 9: 进行首版静态验收与 smoke checklist

**Files:**
- Modify: `plugins/nuclio/README.md`（补充“验收方式”一节）
- Modify: `plugins/nuclio/skills/project-init/SKILL.md`（如需补全遗漏的 artifacts/gates）
- Modify: `plugins/nuclio/skills/spec/SKILL.md`（如需补全 gate/state 说明）
- Modify: `plugins/nuclio/skills/design/SKILL.md`（如需补全 gate/plan 说明）
- Modify: `plugins/nuclio/skills/build/SKILL.md`（如需补全 verify/review/patch 说明）
- Modify: `plugins/nuclio/skills/close/SKILL.md`（如需补全 memory approval 说明）
- Modify: `plugins/nuclio/hooks/guard.mjs`（如验收发现明显缺口）

**Steps:**
- [ ] **Step 1: 在 README 补充首版静态验收清单**

```md
## 验收方式

首版 MVP 通过的最低标准：

1. marketplace 能发现 `nuclio`
2. `project-init` 闭环 artifact 与 gate 齐全
3. `spec → design → build → close` 闭环 artifact 与 gate 齐全
4. `build` 明确 verify/review/patch
5. `.dev-docs/` 写入与危险 bash 受 guard 约束
```

- [ ] **Step 2: 运行一次全量静态检查，定位遗漏后立即补齐对应文件**

Run:
```bash
jq . .claude-plugin/marketplace.json >/dev/null && \
jq . plugins/nuclio/.claude-plugin/plugin.json >/dev/null && \
find plugins/nuclio -type f | sort && \
grep -R "Spec Approval\|Design Approval\|Memory Approval\|Foundation Approval\|Architecture Approval\|Scaffold Approval\|Initial Dev Docs Approval" plugins/nuclio/skills
```

Expected:
- JSON 均合法
- 输出列出所有 skill/agent/hook/script/template 文件
- grep 结果能覆盖两条闭环要求的全部 gate

- [ ] **Step 3: 手动执行一次 cross-reference review，修复以下常见问题**

```text
- README 中列出的 skill 名称与实际目录不一致
- hook 文件名与 hooks.json 中 command 路径不一致
- build skill 未提及 reviewer 或 verify/review evidence
- apply-memory 允许绕过 approval
- project-init 提前写 `.dev-docs/`
```

- [ ] **Step 4 (验证): 复跑静态检查并确认没有新缺口**

Run:
```bash
jq . .claude-plugin/marketplace.json >/dev/null && \
jq . plugins/nuclio/.claude-plugin/plugin.json >/dev/null && \
find plugins/nuclio -type f | sort | wc -l && \
grep -R "do not\|禁止\|Approval" plugins/nuclio/skills | wc -l
```

Expected:
- 所有命令退出码为 0
- 文件总数大于 15
- skills 中存在足够多的 gate/约束语句，说明闭环和 guard 不是空壳

- [ ] **Step 5: 提交本任务**

```bash
git add plugins/nuclio .claude-plugin/marketplace.json
git commit -m "chore(nuclio): validate mvp static workflow coverage"
```

**Acceptance Criteria:**
- 业务意图：在没有应用构建系统的仓库里，用静态 smoke checklist 验证 Nucl.io 首版闭环确实成形。
- Pattern 结构约束：优先修复命名、gate、cross-reference、guard 约束等结构缺口，不做超出 MVP 的扩展开发。
- 验收标准：`project-init` 与 `change workflow` 两条链路所需文件、gate、guard、evidence 关键字都能通过静态检查被验证到。
