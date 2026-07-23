# Nuclio v2：以人为中心的开发工作流重设计方案

> 状态：已确认方向的设计方案，尚非当前运行时权威  
> 日期：2026-07-22  
> 当前运行时权威：`plugins/nuclio-plugin/references/` 及现有 skills、agents、schemas、helpers  
> 修订对象：`../contract-workbench-redesign/nuclio-redesign-proposal.md`

## 0. 文档定位

本文记录 Nuclio v2 的产品与架构方案，供后续实现计划、重写和验收使用。
在 v2 实现完成并切换运行时权威之前，当前 Nuclio 仍遵循现有的
`init → work → finish`、Contract、packet、evidence、state 和 Finish handoff 协议。

本文明确修订历史 Contract Workbench 方案中的以下判断：

- 不再保留独立 `/nuclio:finish`；
- 不再保留 Contract/State/Packet/Evidence/Finish Handoff 协议栈；
- 不再追求旧 change 协议兼容；
- 不再要求每个 Task 固定经过 implementer/reviewer/fixer 流水线；
- 不再把主会话作为细粒度持久状态机 Controller；
- 不再用多个 JSON、hash、fingerprint 和 identity 证明普通开发流程；
- `.dev-docs` 继续存在，但从“协议数据库”改为“人类可读的项目知识与 change 工作记录”。

本文不是对 v1 的渐进简化，而是一次直接断代的 v2 设计。

---

## 1. 结论先行

### 1.1 产品定义

Nuclio v2 是一套面向 AI coding agent 与开发者的轻量开发协作约定：

1. 澄清真正要解决的问题；
2. 形成用户可理解、可批准的实施计划；
3. 协调实现、验证和必要审查；
4. 自动维护可跨 Session 恢复的 `change.md`；
5. 将稳定、可复用、非显然且已验证的结论，经用户确认后蒸馏为长期项目知识。

Nuclio v2 **不是**：

- 分布式事务协议；
- 通用 workflow engine；
- 细粒度审计系统；
- agent packet transport；
- 每一步都落盘的事件账本；
- schema/hash 驱动的状态机；
- 代码、Git、测试和 CI 的替代事实源。

### 1.2 用户入口

日常开发只有一个入口：

```text
/nuclio:work <需求、bug、重构或继续指令>
```

保留可选入口：

```text
/nuclio:init
```

`/nuclio:init` 只用于：

- 首次创建 v2 `.dev-docs`；
- 重新生成最小知识骨架；
- 将 v1 `.dev-docs` 整体移动到 legacy；
- 修复明显损坏的 v2 目录导航。

它不是每个 change 的必经步骤。

删除：

```text
/nuclio:finish
```

实现、验证、结果展示、长期知识提案和归档都在一次 `/nuclio:work` 生命周期内完成。

### 1.3 核心持久化模型

普通 change 默认只有一个文件：

```text
.dev-docs/changes/<change-id>/change.md
```

长期知识采用 Markdown docs-as-code，按“全局横切知识 + 领域/子系统知识 + ADR + runbook”组织。

v1 旧内容整体迁入：

```text
.dev-docs/legacy/v1/
```

v2 不解析、不转换、不恢复旧 state、packet、evidence 或 Finish handoff。

### 1.4 核心体验指标

| 指标 | v2 目标 |
|---|---|
| 日常用户命令 | 1 个：`/nuclio:work` |
| 普通 change 持久化过程文件 | 1 个：`change.md` |
| 普通 change 持久化 JSON | 0 个 |
| 用户决策点 | 实施计划批准；仅有长期知识候选时再确认知识更新 |
| 固定 agent 流水线 | 无；按风险和任务需要调度 |
| 主会话常态上下文 | 完成前争取低于 50k tokens |
| 主会话上下文警戒线 | 100k tokens；达到后必须 checkpoint 并收缩上下文 |
| v1 协议兼容 | 无 |
| 长期知识默认加载 | 禁止全文加载；先索引后按需读取 |

---

## 2. 为什么必须直接重写

当前实现不是“一个复杂 skill”，而是一套文件背书的微型工作流引擎。它把普通开发任务建模为：

```text
Contract
→ Context
→ State
→ Packet
→ Agent Report
→ Evidence
→ Reviewer Observation
→ Completion Handoff
→ Finish Readiness
→ Finish Apply Journal
```

一个事实会在 contract、state、packet、prompt、report、evidence 和 handoff 中多次表达。
这造成四类系统性问题：

1. **用户流程长**：用户需要理解 Work、Finish 和多个内部 Gate 的边界；
2. **过程文件多**：小 change 的协议文件常多于产品文件；
3. **前置校验脆弱**：schema、hash、state version、packet identity、language metadata 任一漂移均可阻塞；
4. **上下文乘法膨胀**：主会话重复读取、传递、验证和复述落盘状态，Finish 前即可达到 250k+ tokens。

问题不在于个别 helper 或 JSON 设计不佳，而在于基础抽象错误：

> Nuclio 将“开发协作”实现成了“主会话参与的细粒度事务协议”。

v2 必须删除该抽象，而不是继续压缩其字段和文件数。

---

## 3. v2 用户生命周期

### 3.1 正常路径

```text
用户提出需求
  ↓
Work 定位或创建 change
  ↓
按需探索代码和项目知识
  ↓
形成 Goal / Constraints / Plan
  ↓
用户批准实施计划
  ↓
实现 + 持续维护 change.md
  ↓
验证 + 按风险决定是否独立审查
  ↓
展示结果
  ↓
如有长期知识候选：蒸馏、冲突解决、用户确认、写入
  ↓
完成并归档 change
```

### 3.2 计划批准

计划批准是唯一始终存在的实施 Gate。用户看到的是语义摘要，而不是协议文件：

```markdown
目标：
统一认证状态管理。

计划：
1. 删除客户端主动 refresh；
2. 将 session 续期统一到 middleware；
3. 更新集成测试。

明确不包含：
- OAuth provider 迁移；
- 历史 session 数据迁移。

预计影响：
- src/auth/
- web/auth/
- tests/auth/
```

用户可以自然语言批准或修正，不要求 exact token，不生成 approval JSON，不绑定 hash。

计划批准后，Nuclio 将批准事实写入 `change.md`，例如：

```markdown
## Plan

Approved on 2026-07-22.

- [ ] 删除客户端主动 refresh
- [ ] 将 session 续期统一到 middleware
- [ ] 更新并运行认证集成测试
```

### 3.3 实施与验证

实施期间：

- 主会话负责用户意图、计划、任务协调和异常决策；
- subagent 负责独立探索、实现或审查；
- agent 通过路径自行读取上下文，不接收大型 packet；
- agent 只返回紧凑结论、验证结果、阻塞和必要的文件引用；
- Git working tree、代码、配置和测试是执行事实；
- `change.md` 只保存恢复所需的压缩状态。

审查按风险触发：

| 变更类型 | 默认策略 |
|---|---|
| 文档、简单配置、明确的小修复 | 主 agent 自检与相关验证 |
| 普通多文件功能 | 相关测试 + 定向审查 |
| 跨模块、公共 API、数据模型 | 独立 reviewer |
| 认证、安全、迁移、破坏性变更 | 独立 reviewer + 更完整验证 |
| 用户明确要求深入审查 | 按要求增加审查深度 |

不再强制每个 Task 都经过 implementer → reviewer → fixer。

### 3.4 结果与知识更新

验证通过后，Nuclio先报告代码结果。只有存在长期知识候选时，才追加一次知识确认：

```text
本次 change 产生两条长期知识候选：

1. authentication：认证生命周期由服务端 session middleware 单独负责。
2. engineering：认证变更必须验证刷新、过期重登与多标签页退出同步。

建议分别合并到：
- .dev-docs/knowledge/domains/authentication.md
- .dev-docs/knowledge/engineering.md

是否写入？
```

没有候选时，不出现第二个 Gate，直接完成。

### 3.5 中断与恢复

下次调用 `/nuclio:work` 时，Nuclio：

1. 扫描 `changes/*/change.md`；
2. 定位 active change；
3. 读取其 Goal、Plan、Current State 和 Validation；
4. 检查 Git working tree 与当前代码；
5. 输出已完成内容和下一步；
6. 继续工作。

恢复不尝试重放上一个 agent 的思考过程、tool transcript 或 packet 状态。

---

## 4. Bug 修复与 change 边界

判断标准不是“代码是否已经写完”，而是：

> 如果不修这个 bug，原 change 能否诚实地宣称达成 Goal 和验收结果？

### 4.1 继续原 change

满足任一情况时，继续原 change：

- 自动测试或手工验证发现原目标未达成；
- review 发现当前实现缺陷；
- 当前实现引入回归；
- 用户在当前交互中立即反馈验收失败；
- 修复仍在原批准范围内。

Nuclio 自动更新 `change.md`，用户不需要手动编辑。

### 4.2 新建关联 change

满足任一情况时，新开 bugfix change：

- 原 change 已稳定关闭和归档；
- bug 与原目标无关；
- 修复需要明显扩大范围；
- 修复需要改变公共 API、架构、依赖、迁移或产品语义；
- bug 可以独立验证和交付。

新 change 使用轻量关联：

```yaml
related_changes:
  - simplify-auth-flow
```

不恢复旧 change 的状态机，也不复制其全过程。

### 4.3 用户职责

用户只需自然语言报告问题。Nuclio 负责：

- 判断归属；
- 更新或创建 `change.md`；
- 必要时重新提出计划修订；
- 实施并验证。

不得把手工维护 `change.md` 设为正常流程前置条件。

---

## 5. v2 `.dev-docs` 结构

### 5.1 推荐结构

```text
.dev-docs/
├── index.md
├── knowledge/
│   ├── project.md
│   ├── architecture.md
│   ├── engineering.md
│   ├── glossary.md                 # 按需创建
│   ├── domains/
│   │   ├── authentication.md       # 小领域先单文件
│   │   ├── billing.md
│   │   └── large-domain/           # 领域变大后再拆目录
│   │       ├── index.md
│   │       ├── product.md
│   │       ├── architecture.md
│   │       ├── engineering.md
│   │       └── operations.md
│   ├── decisions/
│   │   ├── index.md
│   │   └── 0001-example-decision.md
│   └── runbooks/
│       └── <repeatable-operation>.md
├── changes/
│   ├── <active-change>/
│   │   └── change.md
│   └── archive/
│       └── <completed-change>/
│           └── change.md
└── legacy/
    └── v1/
        └── ...                     # v1 原内容，整体保留，不参与 v2
```

### 5.2 为什么不是三个大文件

历史设计使用 `product.md / architecture.md / engineering.md` 三个大桶。该模型适合作为小型项目的起点，但随着项目增长会产生：

- 单文件越来越大；
- 不同领域的产品、架构和工程约束混杂；
- agent 为一个局部任务读取大量无关内容；
- 相同领域的信息散落在三个远距离文件中；
- 维护者难以判断一条知识的唯一权威位置。

v2 采用二维组织：

1. **领域/子系统是主要定位轴**；
2. **product / architecture / engineering / operations / decision 是知识类型轴**。

全局的 `project.md`、`architecture.md`、`engineering.md` 只保存真正跨领域的内容；
领域细节进入 `knowledge/domains/`。

### 5.3 懒创建和拆分规则

初始化时只必须创建：

```text
.dev-docs/index.md
.dev-docs/knowledge/project.md
.dev-docs/knowledge/architecture.md
.dev-docs/knowledge/engineering.md
.dev-docs/changes/
.dev-docs/changes/archive/
.dev-docs/legacy/
```

`glossary.md`、`domains/` 具体文件、`decisions/`、`runbooks/` 均按需创建。

领域默认先使用单文件：

```text
knowledge/domains/authentication.md
```

满足任一条件后再拆目录：

- 文件超过约 500–800 行；
- 已出现三个以上清晰、独立的知识类型；
- 每次检索都读取大量无关内容；
- 多个 change 持续修改该领域；
- 领域已有明确子系统边界。

拆分是信息架构优化，不是固定阈值驱动的自动动作。

---

## 6. 根索引设计

### 6.1 必须保留 `.dev-docs/index.md`

研究结论支持为文档体系设置可预测的 README/index 入口，但索引应是简短目录摘要和导航，不是完整知识库，也不是事件清单。

`.dev-docs/index.md` 的职责：

- 说明 `.dev-docs` 用途和事实边界；
- 给出 agent 的推荐读取顺序；
- 列出全局知识入口；
- 列出领域及一行摘要；
- 链接 ADR 索引与 runbooks；
- 说明 active/archive/legacy 的位置；
- 明确 legacy 默认不可读取。

建议内容：

```markdown
# 项目知识索引

## 读取顺序

1. 根据任务定位相关领域；
2. 读取领域入口文件；
3. 仅在需要决策背景时读取 ADR；
4. 仅在历史回归时搜索 change archive；
5. 不默认读取 legacy。

## 全局知识

- [项目与产品范围](knowledge/project.md)
- [跨领域架构](knowledge/architecture.md)
- [工程约定](knowledge/engineering.md)
- [术语表](knowledge/glossary.md)

## 领域

| 领域 | 摘要 | 入口 | 相关代码 |
|---|---|---|---|
| Authentication | 登录、session 与身份生命周期 | [文档](knowledge/domains/authentication.md) | `src/auth/`, `web/auth/` |

## 决策与操作

- [架构决策](knowledge/decisions/index.md)
- [运行手册](knowledge/runbooks/)

## Change

- `changes/<id>/change.md`：进行中工作
- `changes/archive/<id>/change.md`：已完成历史
- `legacy/v1/`：旧协议内容，v2 默认忽略
```

### 6.2 根索引必须保持稳定

根索引不应列出：

- 每个 active change；
- 每个 archived change；
- 每次验证结果；
- 每条 ADR 的全部元数据；
- agent 执行历史；
- 每个知识 heading。

根索引仅在以下情况更新：

- 新增、删除或重命名长期知识入口；
- 新增领域；
- 领域入口路径或摘要实质变化；
- 新增 decisions/runbooks 类别；
- 目录读取规则变化。

普通 change 的创建、推进和归档不修改根索引。

### 6.3 局部动态索引

允许以下局部索引：

- `knowledge/decisions/index.md`：ADR 摘要、状态和链接；
- 大领域的 `domains/<domain>/index.md`：领域内部导航；
- 可选 `runbooks/index.md`：runbook 数量较多时创建。

不创建 `changes/index.md`。active change 由扫描 `changes/*/change.md` frontmatter 定位，
历史 change 通过路径和文本搜索定位，避免每个 change 产生索引写入。

---

## 7. 长期知识内容边界

### 7.1 应保存的信息

长期知识必须至少满足：稳定、可复用、非显然、已验证、可定位。

#### 产品知识

- 稳定用户目标和核心场景；
- 业务术语与定义；
- 关键业务规则；
- 对外兼容性承诺；
- 明确产品边界和非目标；
- 无法从局部代码推断的行为意图。

#### 架构知识

- 系统 context 和外部依赖；
- 领域与模块边界；
- 数据和职责所有权；
- 关键数据流与运行时关系；
- 跨领域约束和横切概念；
- 质量属性及其权衡；
- 已知架构风险和技术债；
- 重要架构视图，可使用适当的 C4 视图表达。

#### 工程知识

- 稳定且项目特有的开发约定；
- 不明显的构建、测试和部署要求；
- 某类变更必须执行的验证；
- 数据迁移和兼容策略；
- 常见但非显然的工程陷阱；
- CI/CD、环境和操作边界。

#### ADR

对未来维护有影响的决策应记录：

- Title；
- Status；
- Date；
- Context；
- Decision drivers / requirements；
- Considered options；
- Decision；
- Consequences；
- Supersedes / Superseded by；
- Related code、docs 和 change。

ADR 用于保存“为什么”，不是完整系统说明。架构现状仍应在领域文档和架构文档中表达。

#### Runbook

- 可重复执行的操作；
- 前置条件；
- 步骤；
- 验证成功的方法；
- 回滚或失败处理；
- 风险和权限边界。

### 7.2 不应保存的信息

默认排除：

- 原始聊天记录和 chain-of-thought；
- agent 完整报告或 transcript；
- 工具调用流水；
- 完整测试日志和一次性错误输出；
- Git diff 的重复描述；
- 可以直接从代码、配置、schema 或测试获得的低价值事实；
- 未被采用的临时方案，除非进入 ADR 的 alternatives；
- 未验证猜测；
- 单次 change 的细节实现清单；
- 当前文件和函数列表；
- 容易漂移的依赖版本副本；
- 临时 TODO；
- packet、identity、hash、state transition；
- 与未来维护无关的成功记录。

### 7.3 事实来源边界

不使用单一全局优先级覆盖所有冲突，先判断事实类型：

| 事实类型 | 首要依据 |
|---|---|
| 当前运行行为 | 代码、配置、schema、实际验证 |
| 预期产品行为 | 用户确认的需求、产品规则、验收标准 |
| 预期架构方向 | accepted ADR、明确架构约束 |
| 工程执行规则 | CI、构建脚本、仓库规则、工程知识 |
| 历史原因 | ADR、archive change、Git history |

代码说明“现在是什么”，ADR 和产品规则说明“应该是什么”。两者冲突时不得简单选择一边，
必须把它识别为行为与意图的偏差，再决定修代码还是修文档。

---

## 8. 短期知识：`change.md`

### 8.1 定位

`change.md` 是当前 change 的人类可读工作记忆，用于：

- 跨 Session 恢复；
- 保留用户目标和已批准计划；
- 记录不能从代码轻易反推的重要决策；
- 保存当前阻塞和验证状态；
- 收集候选长期知识；
- 给出最终结果。

它不是状态机数据库、完整日志或审计录像。

### 8.2 最小格式

新 change 只创建有内容的章节：

```markdown
---
id: simplify-auth-flow
status: active
created: 2026-07-22
updated: 2026-07-22
related_changes: []
---

# 简化认证流程

## Goal

统一认证状态管理，避免客户端和服务端同时维护续期状态。

## Constraints

- 保持登录 API 响应兼容；
- 不迁移 OAuth provider。

## Plan

Approved on 2026-07-22.

- [ ] 调整服务端 session middleware
- [ ] 删除客户端 refresh 调用
- [ ] 更新并运行认证测试

## Current State

尚未开始实施。

## Validation

Pending.
```

按需增加：

- `Context`；
- `Decisions`；
- `Findings`；
- `Knowledge Candidates`；
- `Outcome`。

不创建空章节。

### 8.3 更新时机

只在以下事件更新：

1. 一个有独立结果的计划项完成；
2. 出现影响恢复的重要阻塞；
3. 用户改变目标或范围；
4. 做出不能从代码反推的重要决策；
5. 验证发现重要问题；
6. 形成长期知识候选；
7. Session 即将结束且仍有未完成工作；
8. change 完成。

不在每次文件读取、命令、agent 返回或测试重跑后更新。

### 8.4 完成格式

```markdown
---
status: completed
---

## Validation

- 服务端认证测试：passed
- Web 端认证测试：passed
- 页面刷新、过期重登、多标签页退出：passed

## Outcome

认证续期已统一到服务端 session middleware，客户端主动 refresh 已移除。

## Knowledge Updates

- 更新 `knowledge/domains/authentication.md`：session ownership
- 更新 `knowledge/engineering.md`：认证变更验证范围
```

完成后移动到 `changes/archive/<change-id>/change.md`。

---

## 9. 短期知识到长期知识的蒸馏规则

### 9.1 总原则

> 长期知识不是从 `change.md` 复制出来的，而是从已验证 change 中提炼、归一和整合出来的。

执行过程中先把潜在结论写入 `Knowledge Candidates`，完成验证后再处理。

### 9.2 候选准入五问

候选必须全部回答“是”：

1. **稳定性**：预计在未来多个 change 或较长时间内仍成立吗？
2. **复用性**：未来维护者或 agent 会因为它减少探索、避免错误或改善决策吗？
3. **非显然性**：它是否无法从代码、配置、测试或常规工具直接轻易获得？
4. **已验证性**：代码、测试、用户决策或可靠来源是否支持它？
5. **可归属性**：能否定位到一个明确的长期权威文件和 heading？

任一为“否”则不提升，保留在 archive change 或直接丢弃。

### 9.3 蒸馏步骤

#### Step 1：收集

从以下内容提取候选：

- `Decisions`；
- `Findings`；
- 验证结果；
- 用户确认的范围变化；
- 代码与文档冲突；
- 新发现的领域术语、所有权或质量约束。

不从原始工具日志和 agent transcript 直接生成长期知识。

#### Step 2：验证

每个候选必须绑定可观察依据之一：

- 当前实现与测试；
- 用户明确确认；
- accepted ADR；
- 外部权威规范；
- 已验证的操作结果。

无法验证的候选留在 change 的 `Findings`，不得提升。

#### Step 3：分类

选择唯一目标类型：

- project/product；
- architecture；
- engineering；
- domain；
- ADR；
- runbook；
- glossary。

#### Step 4：检索权威位置

先读根索引，再读取相关领域入口和 ADR 摘要，寻找已有同主题 heading。
禁止直接创建平行文档。

#### Step 5：归一化

把 change-specific 表述改写为长期表述：

```text
差：本次把 auth.ts 的 refresh 调用删掉了。
好：认证续期由服务端 session middleware 负责，客户端不得维护并行续期状态。
```

蒸馏后的文本必须包含适用范围，并删除文件级实施细节，除非路径本身是稳定接口边界。

#### Step 6：冲突解决

按第 10 节规则决定 no-op、merge、replace、scope split、supersede 或 halt。

#### Step 7：用户确认

只展示语义提案：

- 候选结论；
- 目标文件和 heading；
- 操作类型；
- 是否替换或 supersede 旧内容；
- 冲突与影响。

用户可自然语言接受全部、部分、修改或拒绝。

#### Step 8：写入与核对

写入后重新检查：

- 文本是否位于唯一权威位置；
- 是否制造重复或矛盾；
- 索引是否需要更新；
- 链接是否有效；
- `change.md` 是否记录实际 Knowledge Updates。

不生成 apply journal、after hash 或 target identity。
Git diff 是变更追踪依据。

### 9.4 操作类型

每个知识候选归入且只归入一种操作：

| 操作 | 使用条件 |
|---|---|
| `NO_OP` | 已有文档完整表达相同语义 |
| `MERGE` | 新知识兼容且补充同一主题 |
| `REFINE` | 新知识缩小范围、提高准确性或补充条件 |
| `REPLACE` | 当前规范性描述已不成立，且替代结论明确 |
| `SCOPE_SPLIT` | 两个结论都成立，但适用范围不同 |
| `NEW_ADR` | 新增长期重要决策、备选方案和后果 |
| `SUPERSEDE_ADR` | 新决策正式替代旧 accepted ADR |
| `DEPRECATE` | 内容不再适用，但仍有历史或迁移价值 |
| `DELETE` | 明确错误、无替代价值，且 Git 已保留历史 |
| `HALT` | 证据不足或冲突不能安全解决 |

---

## 10. 去重与冲突解决

### 10.1 唯一权威位置

同一规范性事实只能有一个当前权威位置。

- 同主题补充：更新原 heading；
- 同领域细节：合并到领域文档；
- 跨领域原则：放入全局 architecture/engineering，并由领域文档链接；
- 决策依据：放入 ADR，当前架构文档只保留现行结论并链接 ADR；
- 操作步骤：放入 runbook，工程文档只链接。

禁止为了避免编辑现有文档而创建 `*-new.md`、`*-v2.md` 或重复章节。

### 10.2 冲突分类

#### A. 完全重复

处理：`NO_OP`。不追加来源时间线。

#### B. 兼容补充

处理：`MERGE`。将新条件、原因或适用范围合并到原 heading。

#### C. 旧内容过宽或不准确

处理：`REFINE`。修改当前文档，使范围更精确；必要时链接来源 change。

#### D. 当前行为与长期意图冲突

处理：不得静默修改文档。先判断：

- 代码是实现偏差，需要修代码；
- 文档已过期，需要修文档；
- 存在有意例外，需要 `SCOPE_SPLIT`；
- 决策发生改变，需要 ADR。

#### E. 两个长期文档相互矛盾

处理：

1. 定位真正的规范性权威；
2. 将规范性事实收敛到一个位置；
3. 其他位置改为链接或删除重复；
4. 若无法判断，`HALT` 知识写入并请用户裁定。

代码 change 可以完成，知识冲突不会反向否定已经通过的产品验证；
但不得在冲突未解决时写入长期知识。

#### F. 决策反转

处理：`SUPERSEDE_ADR`。

- 旧 ADR 保留；
- 状态改为 `superseded`；
- 链接新 ADR；
- 新 ADR 说明旧决策、变化原因和迁移后果；
- 当前架构文档更新为新结论。

不得重写旧 ADR，使其看起来从未作出过旧决策。

### 10.3 冲突提案格式

```text
冲突：
- 当前 architecture.md：客户端不得持有 refresh token。
- 当前移动端代码：仍使用 refresh token。

证据判断：
- Web/桌面已使用服务端 session；
- 移动端因后台连接限制存在有意例外。

建议操作：SCOPE_SPLIT
- 将现有规则限定为 Web/桌面；
- 在 authentication domain 中记录移动端例外；
- 不创建新 ADR，除非用户决定统一三端策略。
```

---

## 11. 知识过期与清理

### 11.1 当前文档与 ADR 的不同治理

#### 当前知识文档

`project.md`、`architecture.md`、`engineering.md`、domain docs 和 runbooks 应描述当前有效事实。
它们允许：

- 直接修正；
- 合并；
- 删除错误或重复内容；
- 重组 heading；
- 拆分或合并文件。

Git 保存历史，无需在正文长期堆积变更日志。

#### ADR

ADR 保存决策历史：

```text
proposed → accepted → deprecated / superseded
```

旧 ADR 不删除、不重写决策内容，只允许：

- 修正明显排版或链接错误；
- 更新状态；
- 增加 superseded-by / related links；
- 增加后续说明，但不得改写历史决策含义。

### 11.2 清理规则

- 明确错误且无历史价值：删除；
- 已被当前文档完整替代的重复说明：删除或改链接；
- 仍有迁移价值但不再适用：标记 deprecated；
- 被新决策替代的 ADR：标记 superseded；
- 无法判断是否过期：标记待审，不自动删除；
- 代码路径不存在：先确认系统是否已删除，再清理相关知识；
- 仅更新时间过久不构成删除理由。

### 11.3 维护元数据

长期文档允许轻量 frontmatter：

```yaml
---
kind: domain
domain: authentication
summary: 登录、session 与身份生命周期
status: current
related_paths:
  - src/auth/
  - web/auth/
last_reviewed: 2026-07-22
---
```

ADR frontmatter：

```yaml
---
kind: adr
status: accepted
date: 2026-07-22
supersedes: []
superseded_by: null
related_domains:
  - authentication
---
```

原则：

- metadata 主要服务导航与检索，不重新建立 JSON Schema 协议；
- malformed metadata 不阻塞产品开发；
- agent 应回退到 heading/path/text search；
- `last_reviewed` 只在语义真正被审查后更新，不因格式调整自动刷新；
- `owner`、`review_after` 可按项目需要添加，但不作为 v2 默认必填字段。

---

## 12. Agent 按需检索协议

### 12.1 默认读取顺序

```text
1. .dev-docs/index.md
2. 与用户请求匹配的领域入口
3. 相关全局 project/architecture/engineering 章节
4. 必要的 ADR 摘要或正文
5. 当前 active change.md
6. 相关源码、配置和测试
7. 仅在历史原因必要时搜索 archive change
```

### 12.2 禁止默认全文加载

默认禁止：

- 读取整个 `.dev-docs`；
- 读取所有 domain docs；
- 读取所有 ADR；
- 读取所有 archive changes；
- 读取 `.dev-docs/legacy/`；
- 把完整长期知识复制到 subagent prompt；
- 将大文件全文搬回主会话。

### 12.3 检索方式

1. 从用户请求、当前文件路径和 symbols 推断领域；
2. 读取根索引的一行摘要和 related paths；
3. 搜索 frontmatter、heading 和关键词；
4. 只读取目标文件或相关章节；
5. subagent 接收路径、heading 和任务，不接收全文；
6. subagent 返回结论与引用，不返回完整文档；
7. archive/legacy 仅在明确需要历史依据时读取。

### 12.4 建议上下文预算

| 内容 | 建议预算 |
|---|---:|
| 根索引 | ≤ 2k tokens |
| 与任务直接相关的长期知识 | 常态 ≤ 8k tokens |
| 单个 subagent dispatch prompt | 常态 ≤ 4k tokens，不嵌入大文件 |
| subagent 返回 | 常态 ≤ 2k tokens |
| 主会话完成前总上下文 | 目标 < 50k tokens |
| 警戒线 | 100k tokens |

这些是体验预算，不是 hash/schema Gate。超过预算时应：

- 更新 `change.md` checkpoint；
- 停止读取无关材料；
- 把独立阅读委派给 subagent；
- 使用路径和摘要传递；
- 必要时在新 Session 通过 `/nuclio:work` 恢复。

不得依赖 compaction 作为常态上下文治理手段。

---

## 13. v1 legacy 断代策略

### 13.1 原则

- v1 与 v2 不兼容；
- 不写 converter；
- 不恢复旧 active state；
- 不解析旧 packet、evidence、hash 或 Finish handoff；
- 不把 v1 knowledge 自动提升到 v2；
- 不在 v2 索引中枚举 v1 内容；
- legacy 默认不进入 agent 上下文。

### 13.2 一次性移动

当 `/nuclio:init` 或首次 v2 `/nuclio:work` 检测到 v1 `.dev-docs` 时，执行语义上等价的安全移动：

```text
1. 将现有 .dev-docs 整体移动到同级临时目录；
2. 创建新的 v2 .dev-docs；
3. 将临时目录整体移动为 .dev-docs/legacy/v1；
4. 创建 v2 index、knowledge 和 changes 最小骨架；
5. 不读取或改写 legacy 内容。
```

示意：

```bash
mv .dev-docs .dev-docs-v1-legacy-tmp
mkdir -p .dev-docs/legacy
mv .dev-docs-v1-legacy-tmp .dev-docs/legacy/v1
```

随后创建 v2 文件。

实际执行前必须检查：

- `.dev-docs/legacy/v1` 不存在；
- 临时目标不存在；
- 当前 `.dev-docs` 确实具有 v1 特征；
- 不会覆盖用户已有目录。

若目标冲突，停止并报告，不自动合并、覆盖或删除。

### 13.3 legacy 的使用

默认视为只读历史快照。只有用户明确要求查看旧记录时才读取。

如果用户要继续 v1 active change，v2 的处理方式是：

1. 不恢复 v1 状态；
2. 根据用户当前目标和代码现状创建新的 v2 change；
3. 用户可明确指定某个 legacy 人类文档作为背景；
4. 不导入旧 Task 状态、attempt、evidence 和 approval。

---

## 14. 建议的 v2 插件结构

```text
plugins/nuclio-plugin/
├── .claude-plugin/
│   └── plugin.json
├── skills/
│   ├── init/
│   │   └── SKILL.md
│   └── work/
│       └── SKILL.md
├── references/
│   ├── workflow.md
│   ├── change-format.md
│   ├── knowledge.md
│   └── context-hygiene.md
├── scripts/
│   ├── change.py
│   └── test_change.py
└── docs/
    └── research/
```

### 14.1 `change.py` 边界

只处理简单、确定性文件操作：

```text
create
list
show
set-status
archive
legacy-move
```

它可以：

- 检查 change ID 和路径；
- 防止覆盖；
- 读取最小 frontmatter；
- 移动 active/completed change；
- 完成 v1 legacy 整体移动。

它不可以演化为：

- task state machine；
- approval ledger；
- packet builder；
- evidence importer；
- hash/fingerprint validator；
- agent dispatch authority；
- JSON Schema engine。

### 14.2 Agent 策略

v2 不必提供固定 protocol agents。优先使用普通 Claude Code subagent，并通过任务 prompt 限定：

- 目标；
- 允许修改的文件范围；
- 必要读取路径；
- 验证命令；
- 返回格式。

如果保留专用 agents，也只能是轻量角色指引，不得恢复 packet/report/state 协议。

---

## 15. 删除清单

v2 实现切换时，原则上删除以下 v1 概念与对应实现：

### 15.1 协议概念

- Contract hash；
- Context fingerprint；
- State version；
- Packet ID / binding；
- Worker/reviewer/fixer/completion/finish packet；
- Attempt identity；
- Evidence identity；
- Observation import；
- Fix authorization artifact；
- Completion identity；
- Finish readiness；
- Five-file handoff；
- Finish target before/after hash；
- output language identity propagation。

### 15.2 文件和实现区域

- `skills/finish/`；
- v1 packet/state/evidence/finish schemas；
- packet/evidence/state/migration helper 的协议主体；
- bounded protocol agents；
- 围绕 hash、identity、state transition、five-file handoff 的 tests；
- 重复 authority/lifecycle/execution/finish references；
- v1 eval cases。

### 15.3 保留并重写的能力

- `/nuclio:init`；
- `/nuclio:work`；
- active change discovery；
- change create/archive；
- 最小项目知识初始化；
- plan confirmation；
- 实现与验证；
- 按风险审查；
- 知识候选、蒸馏和用户确认；
- legacy 整体移动；
- output language 作为普通用户可见语言偏好，而不是 identity 字段。

---

## 16. 实施路线

### Phase 1：冻结 v2 产品规范

- 审查本文；
- 确认最终 `.dev-docs` 结构；
- 确认 `change.md` 模板；
- 确认知识蒸馏和冲突规则；
- 确认 legacy move 行为；
- 明确 v1 删除清单。

### Phase 2：最小 v2 骨架

- 重写 `/nuclio:init`；
- 重写 `/nuclio:work`；
- 实现最小 `change.py`；
- 创建 v2 references；
- 删除 `/nuclio:finish` 注册；
- 不实现复杂 agent 协议。

### Phase 3：真实任务验证

至少覆盖：

1. 单文件小 bug；
2. 普通多文件功能；
3. 高风险跨模块修改；
4. 中断后新 Session 恢复；
5. 当前 change 内发现 bug；
6. 已归档 change 后发现回归；
7. 有知识候选；
8. 无知识候选；
9. 知识完全重复；
10. 知识与当前文档冲突；
11. ADR supersede；
12. v1 legacy 整体移动。

### Phase 4：删除 v1

- 删除 v1 skills、agents、schemas、helpers 和 tests；
- 更新 plugin metadata；
- 更新 README 和 CLAUDE.md；
- 更新 eval prompts；
- 验证 marketplace/plugin；
- 确认当前运行时权威只描述 v2。

### Phase 5：体验评估

在真实 change 上测量：

- 用户交互轮次；
- change 过程文件数量；
- 前置校验失败次数；
- 主会话上下文峰值；
- subagent prompt/report 体积；
- 恢复成功率；
- 长期知识重复率；
- 长期知识冲突率；
- 无价值知识写入率。

---

## 17. 验收标准

### 17.1 用户体验

- 日常只需 `/nuclio:work`；
- 用户不需要理解 Finish、packet、state、evidence 或 hash；
- 用户不需要手动维护 `change.md`；
- 简单 change 只需要一次计划批准；
- 只有确有长期知识候选时才请求知识确认；
- bug 能自动判断继续原 change 还是新开关联 change。

### 17.2 文件结构

- 普通 change 默认只有一个 `change.md`；
- 普通 change 不生成 JSON；
- 根索引是稳定地图，不是动态 change 清单；
- 长期知识按全局横切 + 领域 + ADR + runbook 组织；
- v1 内容完整位于 `legacy/v1`，不参与 v2。

### 17.3 上下文

- 主会话不默认读取完整 `.dev-docs`；
- subagent 通过路径自行读取，不接收大型 packet；
- agent 返回紧凑摘要，不返回完整 diff/log/report；
- archive 和 legacy 默认不加载；
- 常规 change 在完成前主会话上下文目标低于 50k tokens；
- 达到 100k 时有明确 checkpoint 和收缩行为。

### 17.4 知识质量

- 长期知识满足稳定、可复用、非显然、已验证、可归属；
- 同一事实只有一个当前权威位置；
- 重复候选产生 no-op，而非追加；
- 兼容信息合并到原 heading；
- 冲突不静默覆盖；
- 决策反转通过 ADR supersede 保留历史；
- 当前知识可修正、合并和删除；
- 用户拒绝知识提案不影响已经验证的代码结果。

### 17.5 实现约束

- 不增加 runtime hook、daemon、MCP 或 `.nuclio/` 状态目录；
- 不用新的 schema/state/packet 重新实现 v1；
- helper 只做最小文件操作；
- v2 runtime 指令和 references 保持小而清晰；
- 测试集中验证用户行为和文件结果，而不是协议 identity。

---

## 18. 研究依据

本方案的长期知识设计综合了以下成熟实践：

1. **Diátaxis**：文档应围绕用户需求和信息类型组织，区分 tutorial、how-to、reference、explanation，并重视内容、风格和信息架构。  
   https://diataxis.fr/
2. **arc42**：架构知识需要覆盖目标、约束、context、building blocks、runtime、deployment、crosscutting concepts、decisions、quality 和 risks，而不是只存架构图。  
   https://arc42.org/documentation/  
   https://docs.arc42.org/home/
3. **C4 Model**：适合表达 system context、container、component 等架构视图，但不能替代质量、风险、决策和横切概念。  
   https://c4model.com/  
   https://faq.arc42.org/questions/B-17/
4. **AWS ADR Guidance**：ADR 的长期价值在于保存 decision、context 和 considerations；未记录架构决策是常见反模式。  
   https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/introduction.html
5. **Google Cloud ADR Guidance**：ADR 应包含关键选项和驱动需求，通常以 Markdown 靠近相关代码并与代码处于同一版本控制系统；决策改变时保留旧决策和变化原因。  
   https://docs.cloud.google.com/architecture/architecture-decision-records
6. **Microsoft Engineering Playbook**：ADR 使用可预测目录、状态、上下文、决策和后果，并维护摘要索引。  
   https://microsoft.github.io/code-with-engineering-playbook/design/design-reviews/decision-log/
7. **GDS Architecture Decisions**：记录影响架构的决策，以保留选择背景供未来维护者理解。  
   https://gds-way.digital.cabinet-office.gov.uk/standards/architecture-decisions.html
8. **Google Documentation Best Practices**：少量新鲜准确的文档优于大量失修文档；代码和对应文档应在同一变更中维护；README 是目录的简短摘要。  
   https://google.github.io/styleguide/docguide/READMEs.html  
   https://google.github.io/styleguide/docguide/best_practices.html
9. **Docs as Code**：文档与代码同仓库、可 diff、可 review、可追踪。  
   https://docsascode.org/
10. **Red Hat AI-assisted Documentation Workflow**：AI 适合从代码变化提出文档更新，但应采用“建议 → 人工决定”的两步方式，避免自动写入成为唯一 gatekeeper。  
    https://developers.redhat.com/articles/2026/04/21/ai-powered-documentation-updates-code-diff-docs-pr-one-comment
11. **Claude Code / GitHub Copilot / VS Code Memory Practices**：持久知识应区分项目事实与用户偏好，并按相关性读取，而非每次把所有长期记忆无条件注入上下文。  
    https://docs.anthropic.com/en/docs/claude-code/memory  
    https://docs.github.com/en/copilot/concepts/agents/copilot-memory  
    https://code.visualstudio.com/docs/agents/memory
12. **GitHub Agent Instructions**：仓库级规则与 path-specific instructions 分层，有助于按作用域提供上下文。  
    https://docs.github.com/en/copilot/tutorials/cloud-agent/get-the-best-results

研究边界：直接针对“AI coding agent 长期项目知识库”的权威 A/B 研究仍较少。
领域优先的文件组织、索引静态/动态分层和具体蒸馏算法，是基于上述文档架构、ADR、docs-as-code 与 agent memory 实践形成的 Nuclio 工程化综合方案。

---

## 19. 最终决策摘要

Nuclio v2 采用以下不可分割的设计组合：

1. **直接断代**：v1 整体移动到 `.dev-docs/legacy/v1`，不兼容；
2. **单一日常入口**：`/nuclio:work` 完成计划、实现、验证、知识和归档；
3. **单一 change 文件**：普通 change 只有 `change.md`；
4. **人类可读恢复**：通过 change、Git、代码和测试恢复，不重放 agent 协议；
5. **按风险执行**：不强制每 Task 固定 reviewer/fixer；
6. **长期知识二维组织**：全局横切知识 + 领域主轴 + 文档类型；
7. **稳定根索引**：`.dev-docs/index.md` 是检索地图，不是动态事件表；
8. **接受后蒸馏**：短期知识通过准入、验证、归一、去重、冲突解决和用户确认后提升；
9. **唯一权威位置**：同一规范性事实只保留一个当前入口；
10. **决策历史保留**：ADR 通过 supersede 演进，不改写历史；
11. **按需检索**：先索引、后领域、再具体文档，archive/legacy 默认不读；
12. **上下文预算优先**：路径代替全文，摘要代替报告，checkpoint 代替协议账本。

最终目标不是“让旧 Nuclio 少几个文件”，而是：

> 用一个用户可理解的 change 工作台和一个可持续演进的项目知识库，替代整个协议引擎。
