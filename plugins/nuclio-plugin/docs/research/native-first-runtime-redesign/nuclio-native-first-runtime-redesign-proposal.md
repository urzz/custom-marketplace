# Nuclio v3 薄 Runtime 直接替换方案

> 状态：架构方向已确认，实施合同已修订，待评审
> 日期：2026-08-06
> 替换对象：Nuclio v2 4.2.3
> 目标插件版本：5.0.0
> 当前说明：在本方案完成实现以前，现有 Skill、references 与 `change.py` 仍是运行时权威

## 0. 决策摘要

Nuclio v3 直接替换 v2，不增加并行模式、兼容层、迁移器、feature flag 或对照实验。

v3 的目标不是复制 Comet Native，也不是删除所有流程。它只重新划分职责：

```text
用户     决定要交付什么
Agent    决定如何完成
Runtime  保存少量可恢复事实并判断是否可以结束
宿主     提供权限、Subagent、Worktree、上下文和工具执行环境
Git      保存产品事实
项目检查 证明当前结果
```

最终形态：

```text
/nuclio:work
      │
      ├── change.md       用户确认的结果合同
      ├── delivery.yaml   Agent 可随时调整的交付地图
      ├── state.yaml      Runtime 当前事实
      │
      └── Nuclio Runtime
            ├── create
            ├── approve
            ├── status
            ├── record-check
            ├── verify
            ├── complete
            └── archive
```

核心决策：

1. 保留一次需求确认，不再让用户批准 Tasks、文件路径、执行模式或 Agent 选择。
2. 大需求仍然拆分，但 milestone 由 Agent 拥有，可以在合同不变时自行重排。
3. Runtime 是薄的交付控制面，不是 Agent 调度器、权限系统或工作流操作系统。
4. 删除 `allowed_paths`，不以 content hash、receipt store 或动态文件 ownership 替代它。
5. 验证使用 Git HEAD、宿主原生命令结果和 Acceptance 覆盖；Runtime 记录结构化结果，不建设自定义命令执行器或证据身份体系。
6. 上下文问题通过当前 milestone、短 handoff、知识索引的按需路由和宿主原生 Subagent/压缩能力解决。
7. 删除旧 active schema 和所有兼容逻辑；旧 archive 原样保留，但新 Runtime 不解析。

---

## 1. 第一性原理

一个长时间代码交付流程只有四个不可省略的问题：

1. **做什么**：用户和 Agent 是否对结果、边界和完成标准达成一致？
2. **现在做到哪里**：会话中断后，是否能从仓库事实恢复？
3. **结果是否成立**：当前代码是否通过与需求相符的检查？
4. **能否结束**：是否还有未覆盖的 Acceptance、失败检查或真实用户决定？

Nuclio 只应解决宿主、Git 和项目检查不能稳定解决的部分。

| 问题 | 权威 |
|---|---|
| 产品结果和边界 | 用户确认的 `change.md` |
| 实现方法和拆分 | Agent 管理的 `delivery.yaml` |
| 当前恢复游标和验证结果 | Runtime 管理的 `state.yaml` |
| 代码、配置、测试和提交 | Git 与工作区 |
| 跨 change 稳定、非显然且已验证的项目事实 | `.dev-docs/knowledge/**`，由 `.dev-docs/index.md` 路由 |
| 已完成 change 的结果与历史证据 | `.dev-docs/changes/archive/**` 与 Git 历史 |
| 命令权限、Subagent、Worktree、上下文压缩 | 当前 Code Agent 宿主 |
| 测试命令的执行结果 | 宿主原生工具输出与 Runtime 的当前结果记录 |
| 测试是否足够 | Agent、项目约定和必要时的独立审查 |

由此得到两个边界：

> 模型能力越强，Nuclio 越不应固化“怎么做”；模型能力再强，也不能替代明确需求和可观察结果。

> Runtime 只能机械判断事实，不能把产品语义、风险判断或测试充分性伪装成 schema 校验。

---

## 2. 目标与非目标

### 2.1 目标

- 用户只确认结果合同以及后续真实的产品语义变化。
- 小需求可以直接完成，大需求可以稳定拆分、恢复和集成。
- Agent 可以自行决定直接实现、委派、探索、提交和 review 方式。
- 每条 Acceptance 都有当前实现上的验证依据。
- 新会话不依赖旧聊天记录即可恢复当前工作。
- Runtime 输出足够小，可以直接作为下一次 Agent 或 Subagent 的工作包。
- Agent 在 Shape、Build、恢复和 Verify 中只读取当前任务相关的长期知识，不默认装载整个知识目录。
- 普通失败在合同不变时由 Agent 自主修复，不产生例行用户确认。
- 归档保留最终合同、交付摘要、验证结果和残余风险。

### 2.2 非目标

v3 不建设：

- 多宿主抽象层或跨 Code Agent 统一 Runtime；
- Agent scheduler、DAG、wave、owner routing 或并行写入协调器；
- 自动 branch、worktree、push、PR、merge 或远端 controller；
- `allowed_paths`、目录白名单或预测性实现范围；
- 工作区 snapshot、content hash、receipt store、CAS 或事件日志；
- 自定义命令执行器、权限代理或宿主 transcript 解析器；
- 固定 implementer/reviewer/fixer 流水线；
- risk tag DSL、自动风险分类或按文件数量触发的 review policy；
- repair failure key、重试预算或自动循环控制器；
- transcript、完整命令日志、完整 diff 或 Agent message 存档；
- 旧 active change adapter、旧 CLI alias、schema converter 或双栈；
- `cancelled`、`superseded` 或接管终态；
- 对照实验和量化迁移门槛。

这些能力只有在真实使用证明缺失时才单独评估，不能为未来可能性预建。

---

## 3. 职责边界

### 3.1 用户负责

用户决定：

- Goal 和可观察结果；
- Constraints 与 Non-goals；
- Acceptance Criteria；
- public API、兼容性、迁移结果和默认行为；
- 外部副作用、不可逆动作和无法由已有需求推导的新语义；
- 最终知识候选是否写入。

用户不再批准：

- Task 或 milestone 数量；
- `allowed_paths`；
- `delegated` 或 `direct`；
- 使用哪个 Agent；
- 中间 commit 数量；
- 普通实现文件变化；
- 合同不变的修复方法。

### 3.2 Agent 负责

Agent 负责：

- 调查仓库和澄清需求；
- 生成、维护和重排 milestone；
- 保证每条 Acceptance 被 milestone 与验证覆盖；
- 选择实现方法、测试和 review 深度；
- 使用宿主能力委派、隔离和压缩上下文；
- 在合同不变时持续修复；
- 识别何时出现新的用户决定。

Agent 对 `delivery.yaml` 的 `done` 声明只是交付进度，不构成最终完成证据。

### 3.3 Runtime 负责

Runtime 只负责：

- 验证三件套结构与 change identity；
- 保存原始基线、批准 Git HEAD、当前阶段和验证 HEAD；
- 从批准提交读取并比较用户合同；
- 验证 milestone 对 Acceptance 的覆盖；
- 校验宿主检查结果与当前定义、HEAD 和工作区事实一致；
- 保存当前检查结果、完整规范化定义和简短手工观察；
- 拒绝失败、缺失或已经过期的完成结论；
- 返回紧凑的当前工作包；
- 完成知识结果和可恢复归档。

Runtime 不理解产品语义，不选择 Agent，不评价架构品味，也不判断某条测试在语义上是否充分。

### 3.4 宿主负责

Claude Code、Codex 或实际承载 Nuclio 的宿主继续负责：

- 文件和命令权限；
- 直接执行项目检查并返回 exit code 与输出；
- sandbox；
- Subagent 和独立上下文；
- Worktree 和并行隔离；
- 上下文压缩、恢复与运行时长控制；
- 网络、提权和破坏性操作的用户授权。

Nuclio 不复制这些能力。v3 只面向当前实际支持的宿主；未来增加第二宿主时，只适配 Skill 入口，不预先抽象一套公共 Agent API。

---

## 4. 用户工作流

### 4.1 生命周期

```text
Shape
  调查、澄清、形成 change.md
        │
        └── 用户确认一次结果合同
                ↓
Build
  Agent 创建并维护 delivery.yaml
  自主实现、拆分、委派、提交和定向检查
                ↓
Verify
  宿主在当前 Git HEAD 上运行检查，Runtime 记录并判定
        ├── FAIL：回到 Build，自主修复
        ├── 新产品决定：回到 Shape，重新确认
        └── PASS：进入完成
                ↓
Complete / Archive
  报告结果、处理一次知识决定、归档
```

阶段只用于恢复和路由，不限制 Agent 必须采用固定步骤。Build 与 Verify 可以反复往返，Runtime 不记录每一轮历史。

### 4.2 用户中断点

正常 change 只在以下情况中断用户：

1. 首次确认结果合同；
2. 实现发现新的产品语义、兼容性、外部副作用或不可逆决定；
3. 测试需要用户独有的真实环境或主观判断；
4. Agent 已无法形成新的可执行假设，或环境真实阻塞；
5. 存在长期知识候选时，选择写入并归档或跳过并归档。

Agent 选择文件、拆分 milestone、改用 Subagent、增加测试或修复失败不构成用户 Gate。

### 4.3 合同变化

以下变化必须提升 `change.md` revision 并重新确认：

- Goal、Constraints、Non-goals 或 Acceptance 的语义变化；
- 用户可见默认行为、错误语义或兼容性变化；
- 新增外部副作用或不可逆结果；
- 原合同无法覆盖的新产品范围。

以下变化不需要重新确认：

- milestone 拆分、顺序或描述；
- 普通实现文件增删；
- 实现方案、库选择或内部算法；
- 检查命令增强或替换；
- commit、Subagent 或 review 组织方式。

`revision` 是 `change.md` frontmatter 中从 `1` 开始的正整数。合同语义变化时必须恰好加一；`delivery.yaml` 单独变化不提升 revision。重新 `approve` 会创建新的 approval 元数据提交、替换 `approval_head`、清空全部旧检查/手工观察/review 与 `verified_head`，然后回到 Build。

---

## 5. Artifact 设计

### 5.1 目录

```text
.dev-docs/
├── nuclio.yaml                         # 可选项目级检查
└── changes/
    ├── <change-id>/
    │   ├── change.md
    │   ├── delivery.yaml
    │   └── state.yaml
    └── archive/
        └── <change-id>/
            ├── change.md
            ├── delivery.yaml
            └── state.yaml
```

保持三件套不是为了增加文档，而是为了隔离写入所有权：

- `change.md` 是用户合同；
- `delivery.yaml` 是 Agent 工作记忆；
- `state.yaml` 是 Runtime 事实。

把三者合并会让用户确认、Agent 重规划和 Runtime 写入互相污染。

### 5.2 change.md

`change.md` 保留人类可读格式，并以最小 frontmatter 保存机械 identity：

```markdown
---
schema_version: 1
change_id: auth-redirect
revision: 1
---

# <title>

## Goal

## Context

## Constraints

## Non-goals

## Acceptance Criteria

- AC-1: <可观察结果>
- AC-2: <可观察结果>

## Decisions
```

完成时追加：

```markdown
## Outcome

## Validation

## Knowledge Updates

## Residual Risks
```

规则：

- frontmatter 只包含 `schema_version`、`change_id` 和 `revision`；`change_id` 必须与目录、delivery 和 State 一致；
- `schema_version` 固定为 `1`，`revision` 为正整数；State 中的 revision 只是当前批准 revision 的镜像，不是合同 authority；
- Acceptance 使用稳定的 `AC-*` ID；
- 每条 Acceptance 描述结果，不描述实现步骤；
- Runtime 从批准提交读取 Goal、Constraints、Non-goals、Acceptance 和批准时的 Decisions；
- Decisions 只记录用户确认的产品决定，实施决定写入 delivery/handoff 或代码；
- 完成段落不属于批准合同，可以在终态追加；
- 不生成合同 hash，也不在 State 复制合同正文。

### 5.3 delivery.yaml

`delivery.yaml` 由 Agent 创建和维护，不需要用户批准：

```yaml
schema_version: 1
change_id: auth-redirect
milestones:
  - id: M1
    kind: delivery
    outcome: 修正登录回跳并补充定向测试
    covers: [AC-1, AC-2]
    status: in_progress
    handoff:
      summary: 已定位回跳参数丢失发生在 callback 归一化阶段
      remaining: 完成实现并运行 auth-tests

  - id: M2
    kind: integration
    outcome: 验证认证流程和现有导航没有回归
    covers: [AC-1, AC-2, AC-3]
    status: pending
    handoff: null

verification:
  checks:
    - id: auth-tests
      run: [python3, -m, unittest, tests.auth]
      cwd: .
      timeout_seconds: 300
      covers: [AC-1, AC-2, AC-3]
```

最小规则：

- 至少一个 milestone；
- 每条 Acceptance 至少被一个 milestone 覆盖；
- 多 milestone change 的最后一项必须是 `integration`，并覆盖全部 Acceptance；
- milestone 使用有序列表，不建设 DAG；
- `status` 和 `handoff` 是 Agent 工作记忆，不是 Runtime 完成证据；
- 每个 milestone 只保存当前 handoff，不保存历史；
- handoff 只写已完成事实、剩余工作和必要决定，不复制日志或 diff；
- 检查使用 argv 数组，不接受 shell 字符串；`cwd` 和 `timeout_seconds` 可选；
- `cwd` 必须是解析后仍位于项目根目录内的 repo-relative 路径，`timeout_seconds` 必须是正整数；
- 每条检查声明覆盖的 Acceptance；
- change-specific 与项目级检查 ID 在合并后的当前定义中必须全局唯一；
- Agent 可以在 Verify 前调整 delivery 和 checks；`source`、`id`、`run`、`cwd`、`timeout_seconds` 或 `covers` 任一变化都会使旧结果过期，但不触发用户批准。

小需求仍然使用一个 milestone。这样不需要 `quick`、`full` 或其他模式。

### 5.4 state.yaml

`state.yaml` 只由 Runtime 写入，只保存当前事实：

```yaml
schema_version: 1
change_id: auth-redirect
revision: 1
phase: build
base_head: <git-sha>
approval_head: <git-sha>
verified_head: null
verification:
  checks: []
  acceptance:
    AC-1: missing
    AC-2: missing
    AC-3: missing
  manual: []
  review: null
knowledge:
  result: null
  paths: []
```

检查通过后保存当前结果：

```yaml
verification:
  checks:
    - id: auth-tests
      source: change
      run: [python3, -m, unittest, tests.auth]
      cwd: .
      timeout_seconds: 300
      covers: [AC-1, AC-2, AC-3]
      head: <git-sha>
      exit_code: 0
      summary: 18 tests passed
  acceptance:
    AC-1: passed
    AC-2: passed
    AC-3: passed
```

State 不保存：

- 自定义 content hash；
- 文件 snapshot、完整 diff 或 changed-path ledger；
- stdout/stderr 全文；
- Agent 名称、attempt、transcript 或消息；
- 所有历史验证轮次；
- repair failure key 或重试预算；
- milestone 状态副本；
- approval 合同正文；
- archive commit SHA 或可从 Git 推导的 archive 状态。

Runtime 每次从 Git 和当前 artifacts 重新派生可得到的事实，不在 State 重复缓存。

`create` 创建 `revision: null`、`phase: shape`、`base_head: null`、`approval_head: null`、`verified_head: null` 的初始 State。首次 `approve` 把提交前 HEAD 保存为不再变化的 `base_head`；`approve` 后 revision 必须与 `change.md` 一致。每条检查结果保存当次完整规范化定义，因此不需要 definition hash。

### 5.5 项目级 nuclio.yaml

只有项目存在稳定通用检查时才创建：

```yaml
schema_version: 1
checks:
  - id: repository-tests
    run: [python3, -m, unittest, discover, -s, tests]
    cwd: .
    timeout_seconds: 600
```

第一版只支持无条件检查，不支持 glob、路径匹配、继承、模板、hook 或 policy DSL。项目没有统一检查时不创建空配置。

`.dev-docs/nuclio.yaml` 是用户/团队所有的长期项目策略，修改时需要确认；change-specific checks 仍由 Agent 自主维护。项目级检查的 `source` 为 `project` 且不声明 Acceptance 覆盖；两类检查均由宿主直接执行，再通过 `record-check` 记录。项目配置不建立额外 hash、版本或迁移机制，Git 已保存其历史。

---

## 6. 大需求拆分与需求对齐

### 6.1 对齐不依赖固定 Task

需求对齐由以下闭环保证：

```text
用户确认 change.md
        ↓
delivery.yaml 覆盖全部 AC
        ↓
每个 milestone 交付可检查结果
        ↓
integration milestone 验证整体行为
        ↓
Runtime 检查全部 AC 当前均有依据
```

固定 Task 不是需求对齐的必要条件。真正必要的是：

- 用户合同稳定；
- 每条 Acceptance 有明确 ID；
- milestone 覆盖完整；
- 最终验证回到 Acceptance，而不是只检查任务是否做完。

### 6.2 拆分规则

Agent 根据以下信号拆分 milestone：

- 单一上下文无法可靠完成；
- 存在可独立验证的业务切片；
- 前置能力需要先落地；
- 多模块修改需要最终集成；
- 某部分适合交给独立 Subagent。

拆分遵循四条约束：

1. milestone 描述可观察中间结果，不写逐文件操作清单；
2. 每个 milestone 小到可以由一个 fresh context 理解和完成；
3. 所有 Acceptance 都被覆盖；
4. 多 milestone change 最后必须有整体集成检查。

Agent 可以在 Build 中重排、合并或拆分 milestone。只要用户合同不变，就不需要重新确认。

### 6.3 milestone 完成不等于 change 完成

`status: done` 只表示 Agent 认为该交付单元已经结束。Runtime 最终只认可：

- 当前 Git HEAD；
- 当前完整规范化 check definition；
- 宿主观察到的 exit code；
- Acceptance 覆盖；
- 必要的手工观察或 review；
- 无产品工作区漂移。

因此，Agent 可以自由重规划，而不会削弱最终完成门禁。

---

## 7. 验证与交付质量

### 7.1 验证模型

质量保证分为三层：

1. **合同完整性**：所有 Acceptance 必须被 delivery 和验证覆盖；
2. **机械绑定**：宿主在当前 HEAD 上执行项目和 change checks，Runtime 将结果绑定到当前定义、HEAD 与工作区事实；
3. **语义评价**：Agent self-review，必要时使用独立 reviewer 或用户观察。

宿主工具输出是命令执行 authority；Runtime 不解析 transcript，也不独立证明调用者提交的 exit code，而是拒绝与当前定义、HEAD 或工作区不一致的记录。测试充分性仍由仓库约定、Agent 判断和必要的独立审查共同承担。

### 7.2 Runtime verify

验证分为显式检查和最终判定：

1. 验证当前 `change.md` 的批准部分与 `approval_head` 一致；
2. 验证 delivery 对 Acceptance 的 milestone 和 check 覆盖；
3. 要求当前产品工作区没有未提交变化；当前 active change artifacts 可以由 Runtime 管理；
4. `status` 返回尚未通过检查的完整规范化定义、当前 HEAD、exact argv、cwd 与 timeout；
5. Agent 通过宿主原生命令工具在指定 cwd/timeout 下直接执行 exact argv，使权限和 sandbox 对实际命令生效；
6. 命令结束后调用 `record-check <id> --head <status-head> --exit-code <code> --summary <text> -- <argv>`；
7. Runtime 重新读取当前定义和 Git，要求传入 HEAD 仍等于当前 HEAD、argv 精确匹配、产品工作区仍干净，然后保存当前完整定义、HEAD、exit code 和有界摘要；
8. `verify` 合并检查结果、必要的手工观察和 review；
9. 只有所有 required checks 通过、全部 Acceptance 有当前依据时设置 `verified_head`。

任何失败、缺失、HEAD 变化或完整规范化 check definition 变化都会使当前完成结论无效。Runtime 直接比较结构化内容和 Git SHA，不计算额外 hash。

### 7.3 手工 Acceptance

无法可靠自动化的 Acceptance 可以使用简短手工观察，例如真实 OAuth、设备行为或主观视觉质量。记录至少包含：

- Acceptance ID；
- 操作步骤；
- 观察结果；
- 执行者；
- 当前 HEAD。

Runtime 只验证记录完整且绑定当前 HEAD，不声称观察本身真实。安全、权限、数据迁移等具有客观失败后果的要求不能只靠一句手工 PASS；Agent 必须提供可重复的自动检查或明确向用户报告无法证明的残余风险。

第一版不建设 manual receipt 类型系统、签名或证据附件仓库。

### 7.4 Review 策略

所有 change 在最终 Verify 前由主 Agent 做一次整体 self-review。独立 reviewer 只在以下情况使用：

- 用户或项目规则明确要求；
- 安全、权限、迁移、并发、公共 API 或不可逆行为具有较高后果；
- 结果主要依赖主观评价，缺少强机械 oracle；
- Agent 认为需要第二视角检查测试盲区。

多 milestone 本身不自动触发独立 review，文件数量也不是风险代理。

Runtime 不调度 reviewer，也不验证 reviewer 身份。Verify 保存当前整体 review 的类型（self/independent）、覆盖的 Acceptance、HEAD、PASS/FAIL 和简短摘要；执行独立 review 时用其替代 self-review 记录。产品修改后该结果自然过期。

### 7.5 Repair

Verify FAIL 后：

- 合同不变：Agent 读取失败结果，继续 Build 和修复；
- 检查不充分：Agent 可以增强或替换 delivery checks；
- 出现新产品决定：回到 Shape 并请求用户；
- 工具、环境或判断真实阻塞：报告 blocker。

Runtime 不计算 failure key、不限制固定轮次、不自动 spawn fixer，也不要求每轮 repair 获得用户批准。宿主的运行预算和 Agent 的专业判断足以处理循环；真实重复失效再以实际案例决定是否增加停止机制。

---

## 8. 上下文与恢复

### 8.1 Runtime 工作包

`status --json` 不返回完整 State，而是返回下一步需要的最小信息：

```yaml
phase: build
disposition: continue
goal: 修正登录回跳
constraints:
  - 保持现有会话兼容
non_goals:
  - 不重构认证框架
milestone:
  id: M1
  outcome: 修正登录回跳并补充定向测试
  acceptance: [AC-1, AC-2]
handoff:
  summary: 已定位 callback 归一化阶段
  remaining: 完成实现并运行 auth-tests
git:
  base_head: <git-sha>
  approval_head: <git-sha>
  current_head: <git-sha>
failed_checks: []
next_action: implement-current-milestone
```

稳定 disposition 只有：

- `continue`：当前合同下可以继续；
- `await-user`：存在真实用户决定；
- `blocked`：事实或环境无法安全解释；
- `done`：归档完成。

不为每种错误建立复杂 transition graph。`next_action` 是建议，不是 Agent 调度指令。

### 8.2 阶段化上下文装配

Runtime 工作包、长期知识、当前合同和仓库事实承担不同职责，不能互相复制或替代。Agent 按当前问题装配上下文：

- **Shape**：先理解用户请求并遵守宿主已按作用域装载的项目规则，再读取 `.dev-docs/index.md` 和相关长期知识，随后调查代码、测试与配置，最后形成 `change.md`；
- **Build/恢复**：先读取 `status --json`、当前合同、milestone 和 handoff，再通过 `.dev-docs/index.md` 定位相关知识，最后读取当前实现与测试；
- **Verify**：以批准合同、delivery、实际 diff、当前检查和观察结果为主；相关知识只提供约束和判断背景，不能替代完成证据；
- **Finish**：在产品验证通过后，结合本次 diff、结果和受影响的现有知识，统一判断新增候选与存量失效。

`.dev-docs/index.md` 是路由入口，不承载知识正文。Agent 默认只读取能够说明“为何相关”的知识文件或 heading，不递归读取 `.dev-docs/knowledge/**`，也不默认搜索 archive。代码、测试、配置与 Git 回答“当前实现是什么”；批准合同回答“本次要交付什么”；长期知识回答“哪些稳定约束、术语、决策理由或陷阱不能仅靠当前代码可靠推导”；State 只回答“现在做到哪里”。发生冲突时按问题对应的权威重新核验，不能用较新的聊天记忆静默覆盖磁盘事实。

知识路径由 Agent 根据索引和仓库调查选择，不进入 Runtime State，也不由 `status` 生成 context manifest。只有真实使用证明原生检索持续遗漏必要知识时，才评估更强的自动路由。

### 8.3 Subagent

主 Agent 需要委派时，只传递：

- 当前 milestone；
- 相关 Acceptance；
- Constraints 和 Non-goals；
- 当前 handoff；
- 相关长期知识的精确路径或 heading；
- 必要仓库路径或调查范围；
- 预期验证。

主 Agent 传递路径和读取理由，不复制长期知识正文；Subagent 在 fresh context 中自行读取。Subagent 返回结果摘要和未完成项，不回传完整日志。Runtime 不保存 Agent ID、transcript、attempt 或 dispatch history。

### 8.4 会话恢复

新会话按以下顺序恢复：

1. `status --json`；
2. 读取当前合同、milestone 和 handoff；
3. 通过 `.dev-docs/index.md` 读取当前阶段相关的长期知识；
4. 检查 Git HEAD、工作区、相关代码和测试；
5. 继续当前 milestone，或在事实漂移时重新规划；
6. 已通过验证但 HEAD 改变时回到 Build/Verify。

恢复依赖当前 artifacts 与 Git，不依赖旧聊天、隐藏 memory 或完整执行轨迹。

---

## 9. Git 与工作区边界

### 9.1 Git 是产品事实

Runtime 只持久化三个 Git 身份：

- `base_head`：首次批准前的原始基线，重新批准时保持不变；
- `approval_head`：用户合同确认后的提交；
- `verified_head`：最近一次完整验证通过的产品提交。

当前 HEAD 改变时，旧验证直接失效。无需 `scope_hash`、`policy_hash`、`output_hash` 或文件 content hash。

实际 changed paths 由 `git diff <base-head>..<current-head>` 派生，只用于展示和 review，不写入用户合同。重新批准只替换 `approval_head`，不会缩短 change 的实现范围。

### 9.2 提交职责

- Runtime 可以创建 approval 与 archive 的元数据提交；
- Agent/宿主负责普通产品提交和可选中间 checkpoint；
- Runtime 不规定每个 milestone 必须 commit，也不规定 commit subject；
- Verify 前所有产品变化必须进入 Git；
- Archive 只暂存当前 change artifacts 和已确认知识路径，不吸收其他文件。

`approve` 使用一个可恢复事务，避免让 Git commit SHA 自引用：

1. 重新验证合同、delivery、空 index 和干净产品工作区；
2. 首次批准把当前 HEAD 写为 `base_head`，重新批准保留原值；同时写入待批准 revision、`approval_head: null`、`verified_head: null` 和空验证结果；
3. 只暂存三件套并创建 `approve(<change-id>): confirm revision <n>` 元数据提交；
4. 验证 commit parent、subject、精确 paths 和提交中的合同内容；
5. 再原子回写 `approval_head` 为刚创建的 commit SHA。

如果进程在提交成功后、回写 State 前中断，重跑 `approve` 必须通过当前 HEAD 的 subject、paths、revision 和 committed State 识别该提交，并只完成第 5 步。重新批准执行同一事务，并清空旧验证事实。active State 的提交后回写在 archive 前属于允许存在的 active artifact 修改。

提交成功前的任何失败都必须只取消本次三件套暂存并恢复事务前 State；不得吸收、修改或清理其他路径。

Archive 不把自己的 commit SHA 写入 State。终态 State 保存 `verified_head`；archive commit 的 parent 必须等于该值。归档重跑通过当前 HEAD 的 parent、subject、精确 paths 和 archived 三件套验证已经成功的 archive commit，沿用现有可恢复 archive 模式。

### 9.3 干净工作区假设

删除 `allowed_paths` 且不建设文件 hash/ownership 状态后，Runtime 无法可靠区分同一工作区中的“本 change 未提交内容”和“用户并发内容”。因此 v3 明确采用一个简单边界：

> approval、检查记录、Verify 和 complete 在产品工作区干净时执行；当前 active change artifacts 的写入可以例外，complete 还允许本次已确认的精确知识路径。

如果当前目录含 unrelated dirty product work，Agent 使用宿主原生 Worktree 隔离，或让用户先自行收口。Runtime 不自动 stash、reset、clean、checkout 或创建 Worktree。

这是移除 `allowed_paths` 和自定义 hash 后必须接受的因果约束，不用更复杂的 ownership 协议掩盖。

### 9.4 检查产生文件变化

如果验证命令修改 tracked 或新的非 ignored 产品文件，本次检查不能形成 PASS。Agent 应把生成结果作为 Build 内容接受、提交后重新 Verify。

cache 和临时输出应使用项目已有 `.gitignore` 或工具临时目录。Runtime 不提供 broad exclude 配置。

---

## 10. Runtime 能力面

保持一个 CLI 入口和一个 State writer。第一版只需要：

| 命令 | 作用 |
|---|---|
| `create` | 创建三件套草稿 |
| `approve` | 验证合同和 delivery，记录 approval HEAD |
| `status` | 返回当前事实、disposition 和紧凑工作包 |
| `record-check` | 校验并记录宿主直接执行的一个检查结果 |
| `verify` | 汇总当前检查并更新 Acceptance 结果 |
| `complete` | 写入知识结果并验证可完成状态 |
| `archive` | 移动终态目录、创建或恢复 archive commit |

取消独立的：

- `validate-plan`；
- `init-state`；
- `start-task` / `record-task`；
- `record-review`；
- `start-repair` / `record-repair`；
- `record-validation`；
- legacy/supersede 专用状态命令。

需要手工观察或独立 review 时，作为 `verify` 的结构化输入处理，不为每种证据增加命令族。

Runtime 实现原则：

- Python 本地 CLI，优先复用现有可靠 Git/archive 代码；
- 不增加 daemon、数据库、网络和新依赖；
- 成功与失败使用结构化 JSON；
- mutation 前重新读取 Git 和 artifacts；
- State 使用临时文件加原子替换；
- 只保存有界摘要，不保存完整命令输出；
- 模块只在真实职责需要时拆分，不预先创建一组空 package 层。

---

## 11. 完成、知识与归档

### 11.1 完成条件

`complete` 只在以下条件全部成立时成功：

- 当前 `change.md` 批准合同未漂移；
- delivery 覆盖全部 Acceptance；
- 当前 HEAD 等于 `verified_head`；
- 项目级和 change-specific checks 当前均通过；
- 每条 Acceptance 均有自动检查、完整手工观察或明确 review 依据；
- 除 active change artifacts 和本次已确认的精确知识路径外，工作区干净；
- `Outcome`、`Validation`、`Knowledge Updates` 和 `Residual Risks` 已填写；
- 知识结果已明确。

milestone 全部 `done`、Agent 自述完成或一次 review PASS 都不能替代这些条件。

### 11.2 知识闭环

保留现有 `.dev-docs/index.md`、`.dev-docs/knowledge/project.md`、`architecture.md`、`engineering.md` 与按需 topic 文件，不迁移为 Comet/OpenSpec 式完整行为规格，也不增加第二套 memory/store。代码、测试和配置仍是当前实现事实；知识层只保存跨 change 稳定、可复用、非显然、已验证且有唯一归属的项目事实。

知识日常读取遵循 8.2 的阶段化装配；写入与维护只在产品验证通过后执行。Finish 必须同时检查：

- 本次 change 是否产生合格的新知识候选；
- 本次 diff、API、数据模型、架构边界、权限、发布方式或用户决定是否使现有知识失效。

当前指导类知识可以 `MERGE`、`REFINE`、`REPLACE`、`DEPRECATE` 或在强证据下 `DELETE`；已接受 ADR 不覆写历史，通过新 ADR 或 `SUPERSEDE_ADR` 表达替代关系。无法确认时标记 `review-needed` 或停止该项写入，不自动删除。

收尾结果仍只有：

- 无长期价值：记录 `NO_OP`，不打断用户；
- 有新增、修订、失效或拆分候选：合并成一个 proposal，只询问一次“写入并归档”或“跳过并归档”；
- Runtime 只允许已确认的 `.dev-docs/knowledge/**` 精确路径和必要的 `.dev-docs/index.md` 进入 archive commit。

不增加知识评分、自动合并或第二套审批流程。

#### 11.2.1 主题拆分与索引合同

初始化仍只创建三个全局文件。全局文件只保存真正跨主题的内容；某个长期主题先使用 `.dev-docs/knowledge/<topic>.md`，不预建 domain、decision 或 runbook 目录。

只有当能够给出稳定主题名、唯一语义 authority 和明确“何时读取”说明，并出现以下至少一个信号时，Agent 才提出 `SCOPE_SPLIT`：

- 一个文件已经包含多个可独立检索、面向不同任务的长期主题；
- 局部任务反复需要读取大量无关内容；
- 不同主题被多个 change 独立维护，继续共用文件会造成归属不清或冲突；
- 文件已明显难以扫描；约 500-800 行只能触发复审，不能单独决定拆分。

拆分必须作为一次知识候选由用户确认，并在同一知识更新中完成：

1. 把完整语义移动到新的 topic authority，不在原文件保留正文副本；
2. 原全局文件只保留仍然跨主题的结论，必要时保留一条导航链接；
3. 同步修复相关链接、`sources` 和 `related_paths`；
4. 同步更新 `.dev-docs/index.md`，为新入口记录标题、精确路径、一行摘要和读取时机；只有确有路由价值时才记录相关代码范围；
5. 确认每个结论仍只有一个 authority，索引不包含知识正文、每个 heading、change 列表或执行历史。

索引示例保持紧凑：

```markdown
- [身份认证](knowledge/authentication.md)：登录、会话和身份生命周期；修改认证流程或 `src/auth/` 时读取。
```

普通正文修改不要求改索引；只有新增、删除、重命名入口，或摘要、读取时机、相关范围发生实质变化时才更新。单个 topic 文件仍无法提供聚焦读取时，才可创建 `.dev-docs/knowledge/<topic>/index.md` 和语义明确的子文件，并应用同一套无重复、按需路由规则。Runtime 不按行数自动拆分，也不校验知识分类语义。

收尾顺序固定为：先报告产品结果并完成知识决定；再按决定写入知识文件和四个完成 section；随后调用带显式 knowledge result 与精确 knowledge paths 的 `complete`；最后立即 `archive`。`complete` 要求 `APPLIED/PARTIAL` 的 paths 与当前知识 dirty paths 精确一致，`NO_OP/REJECTED` 不得带 paths，并在成功后写 terminal State。知识正文不进入 State。

### 11.3 Archive

Archive 保留完整三件套，并满足：

- 只处理显式 change ID；
- 不扫描或解析旧 archive；
- move 后中断可以重跑；
- commit 成功但调用方未收到结果时，重跑幂等返回；
- 不暂存 unrelated dirty work；
- 不 push、merge、删除分支或清理 Worktree。

第一版只归档已验证完成的 change，不实现 `cancelled`、`superseded` 或接管终态。未完成 change 可以保留 active，或由用户显式决定删除；出现真实的可恢复取消/接管需求后再单独设计。

---

## 12. 直接替换策略

### 12.1 前提

所有项目均无旧 active change，旧 change 已归档。因此：

- 不迁移 active `plan.yaml`；
- 不读取旧 State；
- 不保留旧 CLI；
- 不保留 v2/v3 双栈；
- 不提供 converter；
- 不为旧 archive 维护 parser fixture。

切换时若意外发现旧 active change，直接停止并报告路径。新 Runtime 不为这个异常补兼容代码。

### 12.2 同一变更内完成

替换必须在一个实现变更中完成：

1. 重写 active artifacts 为 `change.md + delivery.yaml + state.yaml`；
2. 实现最小 Runtime 命令；
3. 重写 `/nuclio:work`；
4. 删除固定 implementer、Task、review 和 repair 协议；
5. 更新 workflow、format、context 和 knowledge references；
6. 删除 `allowed_paths`、Plan schema、旧 CLI 和兼容测试；
7. 更新 init、README、plugin metadata 和静态检查；
8. 运行新 Runtime 测试和仓库测试；
9. 用新流程完成一次普通真实 change，修正明显可用性问题；
10. 将插件版本从 `4.2.3` 提升为 `5.0.0`，发布唯一 v3 行为。

没有中间可发布双栈。开发分支可以逐步提交，但合并结果必须完整。

### 12.3 不做对照实验

本次不建立 v2/v3 A/B harness，也不设置 Token、turn、pass@k 或人工确认次数的发布阈值。原因是样本、模型、环境和裁判难以稳定控制，实验成本高于当前决策价值。

这不取消正常工程验证。切换仍必须通过：

- Runtime 单元测试；
- CLI 行为测试；
- Git/工作区集成测试；
- archive 中断和幂等测试；
- Skill/reference 静态一致性测试；
- 仓库现有测试；
- 一次新流程实际使用。

---

## 13. 最小测试范围

实现至少覆盖：

1. `change.md` 缺少合法 identity、revision、必要 section 或 Acceptance ID 时拒绝 approve；
2. delivery 未覆盖全部 Acceptance 时拒绝 approve/complete；
3. 多 milestone 缺 integration milestone 时拒绝；
4. 用户合同在 approval 后漂移时要求重新确认；重新 approve 清空旧验证、保留原始 `base_head`，提交后中断可幂等恢复；
5. `record-check` 拒绝与当前定义不一致的 argv、HEAD 或 dirty 产品工作区，从不执行传入 argv，并保存宿主观察到的 exit code；
6. check FAIL、missing AC 或手工记录不完整时不能 complete；
7. HEAD 或 `source/id/run/cwd/timeout_seconds/covers` 任一变化后旧验证失效；
8. complete 拒绝缺失完成 section、未确认知识路径或其他 dirty 产品路径；
9. `status` 只返回当前 milestone、相关 AC、handoff 和失败检查；
10. archive 不吸收 unrelated path，move 中断可恢复，成功重跑幂等；
11. 旧 archive 不被扫描、解析、修改或删除；
12. 静态扫描确认权威运行时不再引用 `allowed_paths`、`execution.mode`、固定 Tasks 或旧 CLI；
13. Skill/reference 静态一致性确认 Shape、Build、恢复、Verify 和 Finish 采用 index-first、relevant-only 的知识合同，Subagent 只接收相关知识路径，Finish 同时检查新增候选与存量失效；
14. init 生成的索引可表达路径、摘要和读取时机，主题拆分不由 Runtime 自动触发或维护。

不为每个字段建立测试矩阵。围绕完成错误、数据损失和恢复边界保留最小高价值测试。

---

## 14. 风险与明确限制

### 14.1 项目测试不足

宿主工具输出证明命令运行结果，Runtime 只证明记录仍绑定当前定义、HEAD 和工作区事实；两者都不能证明检查充分。缓解方式是明确 Acceptance、项目 required checks、Agent self-review，以及在高后果或主观场景使用独立评价。v3 不试图用更多 schema 解决语义问题。

### 14.2 弱模型执行质量下降

v3 假设当前目标宿主使用能够自主规划、调用工具和修复的强模型。它不为较弱模型保留 Classic 流水线。需要支持弱模型时，应选择更强模型或在宿主层提供更明确提示，不恢复双工作流。

### 14.3 干净工作区要求产生摩擦

这是删除 `allowed_paths`、dirty hash 和 ownership 状态后的明确代价。优先使用宿主 Worktree 隔离；只有真实使用证明这是主要阻塞，才重新讨论工作区策略。

### 14.4 Runtime 再次膨胀

任何新增持久字段或命令必须回答：

1. 哪个已经发生的失败需要它？
2. Git、宿主或现有 artifact 为什么不能解决？
3. 它能删除哪条现有流程规则？

没有具体答案就不增加。

### 14.5 Agent 通过更换检查绕过失败

Runtime 会让 check definition 变化后的旧结果失效，但不能判断新检查是否更弱。项目 required checks、Acceptance 语义和 review 是这里的防线。第一版不建设 check replacement ledger；发生真实绕过案例后再处理。

### 14.6 Runtime 不是安全沙箱

验证命令只在用户信任的本地仓库运行，并由宿主命令工具直接执行，使实际 argv 继续受宿主权限与 sandbox 约束。Runtime 的 `record-check` 不执行传入 argv，只记录宿主观察结果，因此不会成为绕过命令级权限的 Python subprocess wrapper。结构化 argv 避免定义歧义，但 Runtime 不解析宿主 transcript，也不提供防篡改执行证明；若未来确实需要，应通过宿主原生集成单独设计，而不是给本地 Runtime 增加权限代理。

---

## 15. 架构验收标准

完成实现后必须满足：

### 15.1 用户体验

- 日常入口仍只有 `/nuclio:work`；
- Build 前只有一次结果合同确认；
- 不展示或批准 `allowed_paths`、Tasks、execution mode 或 Agent 选择；
- 合同不变的失败不会例行询问 repair permission；
- 用户只因真实产品决定、独有验证环境、阻塞或知识候选被打断。

### 15.2 大需求与上下文

- 每个 change 至少一个 Agent-owned milestone；
- 多 milestone change 有最终 integration milestone；
- 所有 Acceptance 被 milestone 和验证覆盖；
- Agent 可在不重新确认合同的情况下重排 delivery；
- `status` 可为 fresh context 返回当前 milestone 和短 handoff；
- Shape、Build 和恢复通过 `.dev-docs/index.md` 只读取相关长期知识，不默认装载全部 knowledge 或 archive；
- Subagent 接收相关知识路径和读取理由，不接收复制的知识正文；
- Runtime 不保存 transcript、完整日志或 Agent 调度历史。

### 15.3 质量与完成

- 宿主在当前 HEAD 上直接执行 required checks，Runtime 记录并校验当前绑定；
- 失败、缺失或 stale 结果不能 complete；
- 每条 Acceptance 都有当前依据；
- 产品 HEAD 变化后旧验证自动失效；
- 独立 review 是风险和 oracle 驱动的可选能力，不是固定每 Task 流程；
- Finish 在同一次知识决策中处理新知识候选和受本次变更影响的存量知识；
- Archive 保留 Outcome、Validation、Knowledge Updates 和 Residual Risks。

### 15.4 复杂度

- 只有一个 Runtime 和一个 State writer；
- active change 只有三件套；
- 项目配置仅在有稳定检查时存在；
- 不存在兼容 adapter、双栈、feature flag 或 converter；
- 不存在 custom content hash、snapshot、receipt store、failure key 或 risk DSL；
- 不存在 Runtime Agent scheduler、Worktree manager 或权限系统；
- 旧 `change.py` 和固定流程测试被删除，而不是包一层继续保留。

---

## 16. 实施顺序

实施按一个 vertical slice 推进，不按长期平台路线拆分：

1. **Artifact 与 Runtime 核心**：三件套、approve、status、record-check、verify、complete、archive。
2. **工作流替换**：重写 Skill/references，删除 Plan、Task、path、execution 和固定 review/repair 协议。
3. **验证与收口**：补最小高价值测试，更新 init/README/metadata，执行一次新流程并直接发布。

实现过程中优先复用当前 `change.py` 中已经证明可靠的 ID/path 校验、原子文件写入和 archive 恢复代码。其余逻辑按新合同重写；不为了复用而保留旧 schema 或命令结构。

---

## 17. 参考依据

- [Nuclio v3 上下文工程与知识机制业界对比](nuclio-native-first-context-knowledge-industry-research.md)：Comet Native、OpenSpec、BMAD、GSD Core、gstack、Trellis 与主流宿主的实现对比及本方案取舍；
- [Comet Native 工作流](https://docs.comet.rpamis.com/zh/concepts/native-workflow)：结果约束、四阶段和 Runtime completion authority；
- [Comet Native 与 Classic 实验](https://docs.comet.rpamis.com/zh/eval/comet-native-vs-040-experiment)：流程缩短的方向性证据及其因果限制；
- [Codex Long-running work](https://learn.chatgpt.com/docs/long-running-work)：Outcome、Constraints、Verification 和宿主 Goal；
- [Codex Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)：bounded work、fresh context 和 summary return；
- [Claude Opus 5 prompting](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5)：长任务、自主验证以及删除旧式过度验证脚手架；
- [Anthropic long-running harness](https://www.anthropic.com/engineering/harness-design-long-running-apps)：结构化 handoff、上下文重置和独立评价；
- [OpenSpec](https://github.com/Fission-AI/OpenSpec)：轻量 artifact 与非刚性阶段；
- [Spec Kit complex features](https://github.github.io/spec-kit/concepts/complex-features.html)：大需求的浅层拆分与独立切片。

---

## 18. 最终结论

Nuclio 应建立自己的 Runtime，但只拥有交付协议中必须持久和机械判断的部分：

```text
Nuclio Runtime
  = 用户合同确认
  + Agent 交付地图的结构校验
  + 当前 Git/宿主验证记录
  + 紧凑恢复工作包
  + 完成与归档
```

它不应成为：

```text
Agent 调度器
+ 文件权限系统
+ 多宿主兼容层
+ 内容快照数据库
+ 审计证据平台
+ 固定研发流水线
```

v3 的长期正确性不来自更多协议，而来自清晰的职责边界：用户锁定结果，Agent 自主收敛，Runtime 只拒绝没有当前事实支持的“完成”。

Agent 的有效上下文同样不来自更多持久状态，而来自问题对应的权威：当前合同和 Runtime 工作包说明目标与进度，知识索引路由少量长期知识，代码、测试与 Git 提供当前实现事实。
