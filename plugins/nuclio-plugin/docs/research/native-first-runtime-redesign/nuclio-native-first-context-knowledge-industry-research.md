# Nuclio v3 上下文工程与知识机制业界对比

> 状态：调研完成，结论已纳入 native-first Runtime 提案
> 日期：2026-08-06
> 研究对象：Comet Native、OpenSpec、BMAD-METHOD、GSD Core、gstack、Trellis，以及主流 Code Agent 的上下文装配机制
> 关联提案：[Nuclio v3 薄 Runtime 直接替换方案](nuclio-native-first-runtime-redesign-proposal.md)

## 1. 研究问题与结论

本次调研回答三个问题：

1. Nuclio v3 是否应保留现有长期知识机制？
2. 长期知识应如何参与 Shape、Build、Verify、恢复和 Finish，而不退回重型 context manifest？
3. 现有三个全局文件增长后，如何按主题拆分并维护索引？

结论：

- 保留 `.dev-docs/index.md` 与 `.dev-docs/knowledge/**`，不迁移为完整 capability spec、外部 memory store 或知识图谱；
- 把知识读取正式纳入阶段化上下文装配，采用“索引先行、相关正文按需读取”；
- 区分当前合同、实现事实、执行状态、长期知识和历史证据，不让任一层镜像另一层；
- Finish 同时处理新知识候选和受本次变更影响的存量知识，继续使用现有一次用户决策；
- 定义人工提出、用户确认的 `SCOPE_SPLIT`，不由 Runtime 按行数自动拆分；
- 不新增 Runtime 命令、State 字段、context manifest、向量库、memlog 或自动知识晋升流水线。

这意味着 native-first 总方向不需要调整，只需补齐提案原先缺失的知识读取与维护合同。

## 2. Nuclio 当前基线与缺口

现有 [knowledge reference](../../../references/knowledge.md) 已经具备较完整的写入治理：

- 五问门槛：稳定、可复用、非显然、已验证、可归属；
- 默认入口：`project.md`、`architecture.md`、`engineering.md` 与按需 `<topic>.md`；
- 单一语义 authority；
- `MERGE`、`REFINE`、`REPLACE`、`SCOPE_SPLIT`、ADR supersede 等维护操作；
- `sources`、`related_paths`、`last_reviewed` 等可选 freshness metadata；
- 产品验证后的一次知识确认，以及 `NO_OP/APPLIED/PARTIAL/REJECTED` 完成结果。

原提案的缺口不是“没有知识系统”，而是只规定了 Finish 写入和 Archive 路径，没有规定日常读取：

- Shape 不知道应在调查代码前读取哪些长期约束；
- Build 和新会话恢复只拿到 milestone/handoff，没有知识路由；
- Subagent 工作包没有说明如何获得相关长期知识；
- Verify 没有明确知识是约束背景而非完成证据；
- Finish 只强调新候选，没有明确检查存量知识是否被当前 change 破坏；
- `<topic>.md` 和 `SCOPE_SPLIT` 没有可执行的拆分及索引规则。

## 3. 研究方法与快照

本研究优先检查官方文档和官方仓库当前实现，不依赖产品介绍或二手总结。版本与提交只用于固定本次观察，不表示 Nuclio 需要追随其后续变化。

| 对象 | 调研快照 |
|---|---|
| Comet | `0.4.0-beta.16`，`07c5b64b02dc00fffa6d66da70014bfb0f9ebca0` |
| OpenSpec | `1.8.0`，`d57889664cab4f2f061d236ec3ff82a5578701bb` |
| BMAD-METHOD | `05e295f48e9176de4e457204325b0444ab185a0f` |
| GSD Core | `077028584f73a5f2a64c1dceda2a08f0d2c65045` |
| gstack | `a3259400a366593e0c909dd9ac3e59752efd2488` |
| Trellis | `ca92175f0b4efd37dfe149c592063954eb306a2e` |

“事实”指文档或代码中可直接观察的行为；“对 Nuclio 的判断”是基于其目标和现有机制做出的取舍，不把别人的实现自动视为最佳实践。

## 4. 主要实现对比

### 4.1 Comet Native

这里的 Comet 指 [rpamis Comet Native](https://docs.comet.rpamis.com/zh/native/quickstart)，不是 Comet ML，也不是由 OpenSpec 与 Superpowers 组成的 Comet Classic。

#### 已实现机制

- Native 使用单个 `/comet-native` Skill 跨 Shape、Build、Verify、Archive；
- 每次进入都从配置、selection、State、`brief.md`、完整 target specs 和仓库状态恢复，不依赖聊天记忆；
- 确认当前阶段后才加载对应 reference，属于明确的 progressive disclosure；
- checkpoint 只保存事实摘要、下一动作和 artifact manifest，不替代正式合同；
- target spec 描述归档后的完整 capability 行为，不是 delta；
- Archive 按 `create/replace/remove` 把 target spec 晋升为 canonical capability spec；
- canonical spec 基线、实现范围、验证和 archive preflight 通过 hash 绑定，输入变化会使旧证据失效。

依据：[Native 工作流](https://docs.comet.rpamis.com/zh/concepts/native-workflow)、[产物与状态](https://docs.comet.rpamis.com/zh/native/artifacts-and-state)、[Skills 与路由](https://docs.comet.rpamis.com/zh/native/skills-and-routing)、[连续推进与 Checkpoint](https://docs.comet.rpamis.com/zh/native/continuation-and-checkpoints)、[当前 Native Skill](https://github.com/rpamis/comet/blob/07c5b64b02dc00fffa6d66da70014bfb0f9ebca0/assets/skills-zh/comet-native/SKILL.md)。

#### 对 Nuclio 的判断

Comet 的 canonical spec 回答“产品能力当前应该如何行为”，不是通用的工程知识层。其 Native 实现没有独立的 ADR、runbook、工程约定或非显然项目事实系统，Build 仍依赖仓库规则和代码调查。

Nuclio 应借鉴单 Skill、磁盘恢复和阶段按需加载，但不应把现有 knowledge 替换为完整 capability specs，也不需要复制整仓快照、内容寻址 evidence 或 spec rebase Runtime。

### 4.2 OpenSpec

#### 已实现机制

OpenSpec 把上下文分为：

- `openspec/specs/`：当前行为的主规格；
- `openspec/changes/<name>/`：proposal、delta specs、design 和 tasks；
- `changes/archive/`：已完成 change 的历史上下文；
- `config.yaml context`：注入 artifact 操作的项目背景；
- Apply CLI 返回的 `contextFiles`：当前 schema 和阶段要求读取的精确文件。

生成 artifact 时必须从磁盘重读依赖；恢复依靠当前 artifacts 和未完成 task。Archive 可以先把 delta 同步到 main specs，再移动 change。[团队工作流](https://openspec.dev/docs/team-workflow)建议在实现合并后归档，使 main specs 描述已交付现实。

当前 Stores/References beta 把跨仓库规格放在独立 Git checkout，只把 spec ID、Purpose 摘要和精确 fetch 方法放进索引；正文由 Agent 按需读取。OpenSpec 不负责自动 clone、pull 或验证本地 checkout 新鲜度。

依据：[Overview](https://openspec.dev/docs/overview)、[Customization](https://openspec.dev/docs/customization)、[Apply Skill](https://github.com/Fission-AI/OpenSpec/blob/d57889664cab4f2f061d236ec3ff82a5578701bb/skills/openspec-apply-change/SKILL.md)、[Stores](https://openspec.dev/docs/stores)。

#### 对 Nuclio 的判断

最值得借鉴的是“入口索引只描述用途和精确路径，正文按需读”以及“验证后再晋升”。OpenSpec main specs 同样是产品行为规格，不应与 Nuclio 的长期工程知识混为一层。Nuclio 也不需要为了知识检索引入 store checkout 或 CLI 生成的 context manifest。

### 4.3 BMAD-METHOD

#### 已实现机制

BMAD 的 `bmad-project-context` 与 Nuclio 的长期知识问题最接近：

- tiny `kernel.md` 保存极少量始终适用、会改变 Agent 行为的事实；
- bundle 由生成的 `index.md` 路由，Agent 只读取匹配 entry；
- monorepo 子系统可通过 compass 和嵌套 `AGENTS.md` 路由；
- 代码可以直接推导的技术栈、仓库地图和摘要不进入长期知识；
- brownfield 信任顺序优先代码/配置，已有文档必须核对；
- 人工确认或路径核验后标记 `verified`，headless 生成内容标记 `generated`；
- source drift、路径消失、`stale_after` 和 supersede 由 sweep/refresh/audit 维护；
- Audit 要求总量不增长，并删除已经能从代码直接推导的内容。

依据：[Project Context Skill](https://github.com/bmad-code-org/BMAD-METHOD/blob/05e295f48e9176de4e457204325b0444ab185a0f/src/bmm-skills/plan/bmad-project-context/SKILL.md)、[Kernel Contract](https://github.com/bmad-code-org/BMAD-METHOD/blob/05e295f48e9176de4e457204325b0444ab185a0f/src/bmm-skills/plan/bmad-project-context/references/kernel-contract.md)、[Bundle Contract](https://github.com/bmad-code-org/BMAD-METHOD/blob/05e295f48e9176de4e457204325b0444ab185a0f/src/bmm-skills/plan/bmad-project-context/references/bundle-contract.md)、[Context Mechanics](https://github.com/bmad-code-org/BMAD-METHOD/blob/05e295f48e9176de4e457204325b0444ab185a0f/src/bmm-skills/plan/bmad-project-context/scripts/context.py)。

#### 对 Nuclio 的判断

Nuclio 应采用相同原则：小入口、相关 bundle、非推导事实、来源和失效检查。但没有必要复制 BMAD 的 managed `AGENTS.md` block、memlog、完整 frontmatter schema、脚本化 sweep 和 `generated/verified` 双态。

Nuclio 当前只有用户确认后才能写入权威知识，等价于只允许 verified 内容进入，因此现在增加 generated 状态没有收益。将来若引入自动提取，生成结果应先留在非权威候选区，再重新评估 trust 模型。

### 4.4 GSD Core

#### 已实现机制

这里研究当前 [open-gsd/gsd-core](https://github.com/open-gsd/gsd-core)，不使用已迁移的旧 GSD 仓库。GSD Core 的核心是磁盘上的阶段上下文和 fresh subagent：

- `.planning/STATE.md` 是当前位置、下一动作、近期决定和阻塞的短 spine；
- `PROJECT/ROADMAP/REQUIREMENTS/CONTEXT/RESEARCH/PLAN/SUMMARY/VERIFICATION/UAT` 等产物分别承担长期目标、阶段决定、执行计划和证据；
- Planner、researcher、executor、checker、verifier 从 fresh context 启动，通过明确路径读取需要的产物；
- PLAN 的 `<context>` 和每个任务的 `<read_first>` 提供执行范围；
- `/gsd-extract-learnings` 从阶段产物提取 decisions、lessons、patterns 和 surprises；
- graduation 默认从最近五阶段寻找至少三阶段重复的学习，经人工选择后晋升到 `PROJECT.md` 或 `PATTERNS.md`；
- global learnings、项目 knowledge graph 和 MemPalace 都是可选层。

依据：[Context Engineering](https://github.com/open-gsd/gsd-core/blob/077028584f73a5f2a64c1dceda2a08f0d2c65045/docs/explanation/context-engineering.md)、[Planning Artifacts](https://github.com/open-gsd/gsd-core/blob/077028584f73a5f2a64c1dceda2a08f0d2c65045/docs/reference/planning-artifacts.md)、[Learnings Extraction](https://github.com/open-gsd/gsd-core/blob/077028584f73a5f2a64c1dceda2a08f0d2c65045/gsd-core/workflows/extract-learnings.md)、[Graduation](https://github.com/open-gsd/gsd-core/blob/077028584f73a5f2a64c1dceda2a08f0d2c65045/gsd-core/workflows/graduation.md)、[MemPalace](https://github.com/open-gsd/gsd-core/blob/077028584f73a5f2a64c1dceda2a08f0d2c65045/docs/how-to/enable-cross-session-memory-with-mempalace.md)。

#### 对 Nuclio 的判断

GSD 证明 fresh context、短 State 与正式磁盘产物可以支撑长任务，但它的 artifact surface 和可选 memory 层明显大于 Nuclio 所需。重复出现也不等于事实已验证，graduation 不能替代 Nuclio 的五问和用户确认。

Nuclio 只借当前 milestone、短 handoff、路径化上下文和 fresh subagent，不引入阶段产物树、LEARNINGS/graduation、global store、知识图谱或 MemPalace。

### 4.5 Trellis

#### 已实现机制

Trellis 明确分离三类信息：

- `.trellis/spec/`：团队共享的项目规范和约定；
- `.trellis/tasks/`：当前任务的 PRD、design、implement、check 和 research；
- `.trellis/workspace/`：个人 session journal，记录发生过什么，但不是当前事实权威。

任务通过 `implement.jsonl` 和 `check.jsonl` 列出不同角色需要的 spec/research 路径。Hook 在 session、turn 和 subagent 边界注入上下文；`trellis-session-insight` 只在过去会话可能有价值时检索日志，并明确代码事实仍应通过 Git 和搜索核验。

依据：[Context Injection](https://github.com/mindfold-ai/Trellis/blob/ca92175f0b4efd37dfe149c592063954eb306a2e/packages/cli/src/templates/common/bundled-skills/trellis-meta/references/local-architecture/context-injection.md)、[Spec System](https://github.com/mindfold-ai/Trellis/blob/ca92175f0b4efd37dfe149c592063954eb306a2e/packages/cli/src/templates/common/bundled-skills/trellis-meta/references/local-architecture/spec-system.md)、[Task System](https://github.com/mindfold-ai/Trellis/blob/ca92175f0b4efd37dfe149c592063954eb306a2e/packages/cli/src/templates/common/bundled-skills/trellis-meta/references/local-architecture/task-system.md)、[Workspace Memory](https://github.com/mindfold-ai/Trellis/blob/ca92175f0b4efd37dfe149c592063954eb306a2e/packages/cli/src/templates/common/bundled-skills/trellis-meta/references/local-architecture/workspace-memory.md)。

#### 对 Nuclio 的判断

“规范、当前任务、会话日志的 authority 不同”值得保留。JSONL context manifest、Hook 注入和 session log 索引解决的是 Trellis 的多角色平台问题；Nuclio v3 已决定依赖 Agent 原生检索和宿主上下文能力，不应重新引入这些机制。

### 4.6 gstack

#### 已实现机制

gstack 以多个角色 Skill 组成工作流，并维护数个跨会话存储：

- append-only decisions event log 和 active snapshot，支持 decide、supersede、redact 与 scope；
- checkpoint 保存分支、文件、摘要、决定、剩余工作和尝试；
- learnings 记录 pattern、pitfall、preference、architecture、tool 等内容及 confidence/source；
- Skill preamble 检索最近计划、checkpoint、决定和 learning；
- 可选 GBrain 提供代码语义索引和跨机器 artifact 同步。

依据：[Context Save](https://github.com/garrytan/gstack/blob/a3259400a366593e0c909dd9ac3e59752efd2488/context-save/SKILL.md)、[Learn](https://github.com/garrytan/gstack/blob/a3259400a366593e0c909dd9ac3e59752efd2488/learn/SKILL.md)、[Decision Store](https://github.com/garrytan/gstack/blob/a3259400a366593e0c909dd9ac3e59752efd2488/lib/gstack-decision.ts)。

#### 对 Nuclio 的判断

事件化决定的 supersede 语义和 checkpoint 内容值得参考，但 Nuclio 已有 ADR supersede、State/handoff、change archive 和 Git。再增加 repo 外的 decision/checkpoint/learning stores 会形成重复 authority，也会把个人工作流设施带入团队仓库协议。

## 5. 主流 Code Agent 的共同做法

| 工具 | 机制 | 共同信号 |
|---|---|---|
| [Codex AGENTS](https://learn.chatgpt.com/docs/agent-configuration/agents-md)、[Skills](https://learn.chatgpt.com/docs/build-skills)、[Memories](https://learn.chatgpt.com/docs/customization/memories) | 全局、仓库和嵌套 `AGENTS.md`；Skill 元数据先加载、正文和 references 按需加载；必须共享的规则保存在仓库，memory 只辅助召回 | 分层作用域、progressive disclosure、仓库权威优先 |
| [Claude Code](https://code.claude.com/docs/en/memory) | `CLAUDE.md` 层级、path-scoped rules、nested instructions 和按需 memory topic | 小型常驻规则与局部正文分离 |
| [Cursor](https://docs.cursor.com/context/rules) | Always、Auto Attached、Agent Requested、Manual 四种 rule 装载方式 | 由 scope 和 description 决定是否进入上下文 |
| [Kiro](https://kiro.dev/docs/steering/) | baseline steering 与 always、fileMatch、manual、auto 自定义规则 | 全局基线加按路径装载 |
| [Windsurf](https://docs.windsurf.com/zh/windsurf/cascade/memories) | 本地自动 memories 用于召回，团队持久知识要求写入 Rules 或 `AGENTS.md` | 自动记忆不是团队权威 |

这些宿主并未形成统一的知识 schema，但实现收敛于同一原则：少量始终适用信息、按任务选择正文、路径作用域、仓库可见权威，以及将个人会话记忆降级为辅助信息。

## 6. 跨实现归纳

### 6.1 必须按问题区分权威

| 问题 | Nuclio 权威 | 默认装载 |
|---|---|---|
| Agent 在仓库中必须如何工作 | 项目规则与 Skill | 宿主按作用域装载 |
| 本次要交付什么 | 批准的 `change.md` | 当前 change 始终读取 |
| 如何拆分和继续 | `delivery.yaml`、`state.yaml`、handoff | Build/恢复读取 |
| 当前实现是什么 | 代码、测试、配置、Git | 按任务调查 |
| 哪些稳定事实不能可靠地从代码推导 | `.dev-docs/knowledge/**` | 通过 index 按需读取 |
| 过去发生了什么 | change archive 与 Git 历史 | 只有追溯时搜索 |

Comet/OpenSpec 的 canonical specs 属于“当前产品应该如何行为”，不是 Nuclio knowledge 的同义词。Nuclio 当前以代码、测试、批准 change 和 archive 为产品事实，不应在没有明确需求时再复制一套完整行为规格。

### 6.2 恢复依赖正式磁盘产物，不依赖聊天记忆

Comet、OpenSpec、GSD、Trellis 和 gstack 都通过不同形式的 State、task artifact 或 checkpoint 支撑恢复。区别在于持久化多少。Nuclio 已有三件套、Git 和短 handoff，只需补知识路由，不需要保存 transcript、Agent ID、完整日志或每轮尝试。

### 6.3 索引应路由，不应复制

BMAD bundle index、OpenSpec References、Trellis context paths 和宿主 path-scoped rules 都支持相同判断：索引只需回答“有什么、为何相关、从哪里读取”。把正文、每个 heading 或所有 archive 写进索引会制造第二 authority，并使每次变更都产生无价值索引 churn。

### 6.4 知识晋升必须有验证和人工边界

OpenSpec/Comet 在完成与归档时晋升正式规格；BMAD 区分 generated 和 verified；GSD graduation 仍需要人工选择。Nuclio 已有更严格且更小的五问与一次确认，应保留，而不是增加自动评分或重复门槛。

### 6.5 Freshness 不能完全机械证明

Hash 可以证明 Comet 的输入发生变化，BMAD sweep 可以发现源文件漂移，但都不能仅靠机械规则证明一条工程结论在语义上仍然正确。Nuclio 应在相关路径、API、模型、边界或决策变化时触发复审；无法确定时标记 `review-needed`，不自动删除或信任。

## 7. 纳入提案的决定

### 7.1 保留

- 三个最小全局入口和按需 topic；
- `.dev-docs/index.md` 作为唯一知识路由入口；
- 五问、单一 authority、现有 operation 和一次知识确认；
- `sources`、`related_paths`、`last_reviewed` 等可选 metadata；
- ADR 通过新记录或 supersede 保存历史关系；
- archive 与 Git 作为来源和历史证据。

### 7.2 补充

- Shape、Build/恢复、Verify、Finish 的知识读取顺序；
- Subagent 只接收相关知识路径和读取理由；
- Finish 同时分析新增候选与受影响的存量知识；
- 主题拆分信号、迁移规则和索引最小字段；
- 架构验收和静态一致性测试覆盖上述合同。

### 7.3 明确不采用

- Comet 的整仓 snapshot、content-addressed evidence 和完整 capability spec ontology；
- OpenSpec store checkout 与 CLI context manifest；
- BMAD managed `AGENTS.md`、memlog、全量 frontmatter schema 和自动 sweep；
- GSD 阶段 artifact tree、LEARNINGS/graduation、global store、knowledge graph 和 MemPalace；
- Trellis JSONL context manifests、Hook 注入和 session log 索引；
- gstack repo 外 decision/checkpoint/learning stores 与 GBrain；
- 新 Runtime 命令、State knowledge body、向量库或自动分类器。

这些能力都可以在真实遗漏、规模或跨项目需求出现后重新评估，但不应成为 v3 首版前置条件。

## 8. 主题拆分决策摘要

主题拆分属于知识维护，不属于 Runtime 自动整理：

1. 默认先写入现有全局文件或单个 `<topic>.md`；
2. 只有存在稳定主题、唯一 authority、明确读取时机和真实检索/维护问题时才提出 `SCOPE_SPLIT`；
3. 行数只是复审信号，不是自动阈值；
4. 拆分移动语义，不复制正文；
5. 新入口与 `.dev-docs/index.md` 在同一次用户确认的知识更新中提交；
6. 索引只记录标题、精确路径、一行摘要、读取时机和可选相关范围；
7. 单个 topic 再次失去聚焦性时，才引入 `<topic>/index.md` 和语义明确的子文件。

完整规范以关联提案的“11.2.1 主题拆分与索引合同”为准。

## 9. 最终判断

Nuclio v3 应继续采用 native-first 薄 Runtime。知识不是 Runtime State，也不是每个 change 的完整结果镜像；它是由索引路由、经验证后晋升、跨 change 仍有价值的少量项目事实。

最小正确闭环是：

```text
索引定位相关知识
  -> 当前合同与仓库事实驱动交付
  -> 验证当前结果
  -> 检查新增知识与存量失效
  -> 一次用户决定
  -> 精确更新知识与索引
  -> complete + archive
```

在没有真实失败证明需要更多机制以前，不再增加新的上下文基础设施。
