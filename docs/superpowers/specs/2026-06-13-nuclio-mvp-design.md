# Nucl.io 首版 MVP 设计

> 日期：2026-06-13  
> 状态：已确认的首版设计稿  
> 适用仓库：`cc-marketplace`  
> 目标插件：`nuclio`

## 1. 设计目标

Nucl.io 首版不是单个 skill，而是一个可被 Claude Code Marketplace 发现的 workflow plugin。它要在首版同时提供两条都能走通的最小可信闭环：

1. **Project Init 闭环**
   - `/nuclio:project-init`
2. **Change Workflow 闭环**
   - `/nuclio:spec`
   - `/nuclio:design`
   - `/nuclio:build`
   - `/nuclio:close`
   - `/nuclio:resume`
   - `/nuclio:apply-memory`

本设计面向首版 MVP，不追求一次性把 Nucl.io 的所有智能化和自动化能力做满，而是优先证明下面三件事：

- plugin-first 的分发方式成立；
- project-init 与 change workflow 两条闭环都可运行；
- 关键 artifact、gate、state、review、hook guard 都具备最小可信约束。

## 2. MVP 范围定义

### 2.1 首版策略

首版采用：**双闭环同级进入 MVP + 关键节点可运行**。

这意味着：

- `project-init` 与 `spec → design → build → close` 两条闭环都进入首版范围；
- 不要求所有能力都高度自动化；
- 但关键节点必须真实执行，不能只停留在文档描述层；
- 次要能力允许先轻量实现、协议化，或明确后置。

### 2.2 首版必须真实成立的能力

首版必须真实成立的能力如下：

1. **Plugin Discovery**
   - marketplace 中能注册并发现 `nuclio`；
   - plugin metadata、目录结构、skill namespace 一致。

2. **Artifact-first Workflow**
   - 两条闭环都围绕真实文件协议工作；
   - 输出不是单纯会话文本，而是 `.nuclio/` 与 `.dev-docs/` 相关 artifact。

3. **Hard Gates**
   - project-init 至少包含：
     - Foundation Approval
     - Architecture Approval
     - Scaffold Approval
     - Initial Dev Docs Approval
   - change workflow 至少包含：
     - Spec Approval
     - Design Approval
     - Memory Approval
   - 如遇高风险操作，可进入 Risk Approval。

4. **Build 最小闭环**
   - `build` 不能退化成“直接写完”；
   - 必须具备最小的 `implement → verify → review → patch` 结构；
   - 必须产出 `verify.md` 与 `review.md`。

5. **Deterministic Guard**
   - 至少一层 hook 守卫必须生效；
   - 不能只依靠 skill 提醒和模型自觉。

### 2.3 首版允许轻量实现或后置的能力

以下能力不要求在首版做强：

- 深度智能化 `SelectContext`；
- 完整的 `.dev-docs` 多级索引自动校验；
- 高成熟度 `debugger` / `browser-verifier`；
- 完整 `attempts/` 审计体系；
- release / archive / stale-check 增强能力；
- 很复杂的 patch 合并、回写和 schema 校验器。

首版可以保留协议、最小实现或明确后置，但不能影响两条闭环成立。

## 3. 推荐方案与取舍

在 MVP 切分上，存在三种可选方案：

### 方案 A：双闭环协议版

两条闭环都齐，但大量能力先停留在协议和提示层。

- 优点：结构完整，便于后续扩展；
- 缺点：首版真实可运行感偏弱。

### 方案 B：双闭环执行版

两条闭环都尽量做到真实可执行、自动化更强。

- 优点：首版体验强，演示效果好；
- 缺点：范围过大，首版返工和复杂度显著上升。

### 方案 C：双闭环关键节点可运行版（推荐）

两条闭环都进入 MVP，但只要求关键节点真实执行，次要能力先轻量实现。

- 优点：平衡、可落地、返工成本低；
- 缺点：必须明确哪些节点属于“关键节点”。

**推荐结论：选择方案 C。**

原因：它最符合当前目标——既要让两条闭环都成立，又要控制首版复杂度，优先验证 Nucl.io 的核心价值。

## 4. 首版待创建内容

### 4.1 MVP 必做

#### Plugin 与 Marketplace

- `.claude-plugin/marketplace.json`：新增 `nuclio` 注册项；
- `plugins/nuclio/.claude-plugin/plugin.json`。

#### 核心 Skills

- `plugins/nuclio/skills/project-init/SKILL.md`
- `plugins/nuclio/skills/spec/SKILL.md`
- `plugins/nuclio/skills/design/SKILL.md`
- `plugins/nuclio/skills/build/SKILL.md`
- `plugins/nuclio/skills/close/SKILL.md`
- `plugins/nuclio/skills/resume/SKILL.md`
- `plugins/nuclio/skills/apply-memory/SKILL.md`

#### 最小 Templates

- `project-init/templates/project-brief-template.md`
- `project-init/templates/architecture-baseline-template.md`
- `project-init/templates/scaffold-plan-template.yaml`
- `project-init/templates/initial-dev-docs-patch-template.md`
- `spec/templates/spec-template.md`
- `design/templates/design-template.md`
- `design/templates/plan-template.yaml`
- `build/templates/verify-template.md`
- `build/templates/review-template.md`
- `close/templates/close-template.md`
- `close/templates/memory-patch-template.md`

#### 最小 Agent 与 Hook

- `agents/reviewer.md`
- `hooks/hooks.json`
- `hooks/guard.mjs`
- `hooks/event-log.mjs`

#### 最小状态与产物协议

Project Init：
- `.nuclio/project/project-brief.md`
- `.nuclio/project/architecture-baseline.md`
- `.nuclio/project/scaffold-plan.yaml`
- `.nuclio/project/init-state.json`
- `.nuclio/project/initial-dev-docs.patch.md`
- `.nuclio/project/events.jsonl`

Change Workflow：
- `.nuclio/changes/<change-id>/spec.md`
- `.nuclio/changes/<change-id>/design.md`
- `.nuclio/changes/<change-id>/plan.yaml`
- `.nuclio/changes/<change-id>/state.json`
- `.nuclio/changes/<change-id>/events.jsonl`
- `.nuclio/changes/<change-id>/evidence/verify.md`
- `.nuclio/changes/<change-id>/evidence/review.md`
- `.nuclio/changes/<change-id>/close.md`
- `.nuclio/changes/<change-id>/memory.patch.md`

### 4.2 首版轻量实现

以下内容进入首版，但允许先做轻量版：

- `agents/debugger.md`
- `agents/browser-verifier.md`
- `hooks/output-filter.mjs`
- `scripts/read-state.mjs`
- `scripts/write-state.mjs`
- `scripts/append-event.mjs`
- 最小 `.dev-docs` apply 能力
- 最小 `memory.patch.md` apply 能力

### 4.3 明确后置

首版不纳入核心范围：

- `scripts/validate-plan.mjs`
- `scripts/validate-dev-docs-index.mjs`
- 深度 JIT / `SelectContext` 智能化
- 完整 `attempts/attempt-xxx/` 审计体系
- release 相关技能和流程
- 更复杂的 archive / stale-check 自动化

## 5. 架构与职责边界

### 5.1 Plugin 内推荐结构

```text
plugins/nuclio/
  .claude-plugin/
    plugin.json
  skills/
    project-init/
    spec/
    design/
    build/
    close/
    resume/
    apply-memory/
  agents/
    reviewer.md
    debugger.md
    browser-verifier.md
  hooks/
    hooks.json
    guard.mjs
    event-log.mjs
    output-filter.mjs
  scripts/
    read-state.mjs
    write-state.mjs
    append-event.mjs
    validate-plan.mjs
    validate-dev-docs-index.mjs
  README.md
```

### 5.2 五层职责划分

1. **Marketplace 注册层**
   - 负责 plugin 发现与入口声明。
2. **Plugin 能力层**
   - 负责 skills、agents、hooks、scripts。
3. **Project 运行产物层**
   - 负责 `.nuclio/` 过程状态与 artifact。
4. **长期知识层**
   - 负责 `.dev-docs/` 长期项目知识。
5. **宿主仓库说明层（可选）**
   - 负责 README 或简要项目说明。

### 5.3 关键边界原则

- plugin 负责可复用 workflow 能力；
- `.nuclio/` 负责当前项目过程；
- `.dev-docs/` 负责当前项目长期知识；
- skill 负责流程与 artifact 约束；
- hook 负责 deterministic enforcement；
- script 负责底层协议与复用逻辑；
- agent 负责独立视角，不负责主流程控制。

### 5.4 各核心 skill 的职责边界

#### `/nuclio:project-init`
只负责项目级初始化、artifact 生成和 approval gate，不替代 `spec` 或 `build`。

#### `/nuclio:spec`
只负责单次变更澄清、第一性原理收敛、codebase grounding 和 `spec.md` 输出，不负责实现。

#### `/nuclio:design`
只负责基于已批准 spec 生成 `design.md` 与 `plan.yaml`，不负责写代码。

#### `/nuclio:build`
只负责按 `plan.yaml` 执行任务、verify/review/patch，不负责改写 spec/design，也不负责直接维护 `.dev-docs/`。

#### `/nuclio:close`
只负责产出 `close.md` 与 `memory.patch.md`，等待 Memory Approval，不直接绕过审批回写长期知识。

#### `/nuclio:resume`
只负责读状态与建议下一步，不自动越过 gate。

#### `/nuclio:apply-memory`
只负责应用已批准 patch，不负责替用户做批准决策。

## 6. 数据流与状态流

### 6.1 Project Init 数据流

```text
/nuclio:project-init
  ↓
Inspect Repository
  ↓
project-brief.md
  ↓ Foundation Approval
architecture-baseline.md
  ↓ Architecture Approval
scaffold-plan.yaml
  ↓ Scaffold Approval
initial-dev-docs.patch.md
  ↓ Initial Dev Docs Approval
Apply minimal .dev-docs updates
```

Project Init 最小状态体现在 `.nuclio/project/init-state.json`，最小事件流记录在 `.nuclio/project/events.jsonl`。

### 6.2 Change Workflow 数据流

```text
/nuclio:spec
  ↓
spec.md
  ↓ Spec Approval
/nuclio:design
  ↓
design.md + plan.yaml
  ↓ Design Approval
/nuclio:build
  ↓
verify.md + review.md
  ↓
/nuclio:close
  ↓
close.md + memory.patch.md
  ↓ Memory Approval
/nuclio:apply-memory
```

Change Workflow 最小状态体现在 `.nuclio/changes/<change-id>/state.json`，事件记录在 `.nuclio/changes/<change-id>/events.jsonl`。

## 7. 错误处理与风险控制

### 7.1 关键风险

首版需要优先控制以下风险：

1. **流程越界风险**
   - project-init 与 spec 混责；
   - build 未批准就改应用代码；
   - close 绕过 memory approval。

2. **知识库污染风险**
   - 未批准直接写 `.dev-docs/`；
   - 把未验证信息写入长期知识。

3. **伪闭环风险**
   - build 没有 verify/review 证据；
   - review 只是主会话自评；
   - state 与 events 没有真实推进。

4. **确定性不足风险**
   - 完全依赖 prompt discipline，没有 hook guard 兜底。

### 7.2 最小 Guard 要求

`guard.mjs` 首版至少要守住：

- 未批准前禁止写 `.dev-docs/`；
- design 未批准前禁止改应用代码；
- build 阶段受 `allowed_paths` / `forbidden_paths` 约束；
- 危险 bash 至少触发阻断或人工确认。

### 7.3 最小事件记录要求

`event-log.mjs` 首版至少要记录：

- 关键文件写入；
- 关键 workflow 事件；
- 关键阻断事件（若可行）。

## 8. 实现顺序与分批落地

### Batch 1：Plugin 骨架可发现

交付：
- marketplace 注册；
- `plugin.json`；
- 基础目录结构；
- 可选 README。

### Batch 2：两条闭环的 artifact-first skills 成立

交付：
- 7 个核心 skills；
- 最小模板体系；
- 明确输入、输出、gate、禁止行为。

### Batch 3：phase/state/events 推进成立

交付：
- project-init state/events 最小推进；
- change workflow state/events 最小推进；
- build 最小 task/verify/review 结构；
- close 最小 memory patch 结构。

### Batch 4：reviewer + hook guard 成立

交付：
- `agents/reviewer.md`；
- `hooks/hooks.json`；
- `guard.mjs`；
- `event-log.mjs`；
- 让 deterministic enforcement 真正生效。

### Batch 5：轻量增强项补齐

交付：
- `debugger.md`
- `browser-verifier.md`
- `output-filter.mjs`
- `read-state.mjs`
- `write-state.mjs`
- `append-event.mjs`
- 轻量 `.dev-docs` / memory apply 能力。

### 实现顺序原则

- 先稳定协议，再强化执行；
- 先让闭环成立，再做增强体验；
- 先做最难返工的边界，再补工具化细节。

## 9. 测试与验收策略

### 9.1 验收分层

首版验收按以下四层判断：

1. plugin 可发现；
2. `project-init` 闭环可走通；
3. `change workflow` 闭环可走通；
4. guard 与 evidence 可成立。

### 9.2 五组测试

#### 结构与清单测试
- JSON 合法；
- 目录存在；
- 注册信息一致；
- 关键文件齐全。

#### Artifact 生成测试
- project-init 能产出核心 artifact；
- change workflow 能产出 spec/design/plan/evidence/close/memory patch。

#### Gate 行为测试
- project-init 四个 approval gate 会停住；
- spec/design/close 各自会停在正确 gate；
- resume 不自动越 gate。

#### Guard 行为测试
- 未批准写 `.dev-docs/` 被阻止；
- 非 build 阶段改应用代码被阻止；
- build 越 path 边界被阻止；
- 危险 bash 被阻断或要求确认。

#### Evidence / Review 测试
- `verify.md` 有真实检查项；
- `review.md` 有独立审查视角；
- `close.md` 能引用前序 artifact；
- `memory.patch.md` 作为候选补丁存在。

### 9.3 推荐验收场景

#### 场景 A：空仓库 / 新项目初始化
验证 `project-init` 闭环是否成立。

#### 场景 B：已有仓库的单次变更
验证 `spec → design → build → close` 闭环是否成立。

### 9.4 首版“通过”的定义

Nucl.io 首版通过，不代表所有智能化能力都成熟；它只代表：

- 两条主闭环都能围绕真实 artifact 运行；
- 关键 gate 会停住；
- `.dev-docs/` 写入受 approval 约束；
- build 能产出 verify/review 证据；
- close 能产出 memory patch；
- 至少一层 hook guard 生效。

## 10. 最终结论

Nucl.io v0 MVP 应被定义为：

> 一个 plugin-first 的 Claude Code workflow plugin，它同时提供 project-init 与 change workflow 两条最小可信闭环，并以 artifact、gate、state、review、hook guard 为核心，而不是只靠 prompt 说明。

换句话说，首版的成功标准不是“文件建全”，而是：

- workflow 能走；
- 文件能产出；
- gate 能停住；
- guard 能兜底；
- evidence 能回看。
