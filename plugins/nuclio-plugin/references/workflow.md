# Nuclio v2 Workflow

Nuclio v2 是以用户可理解的 `change.md` 为中心的工作台。它把日常工作组织成顺序生命周期，同时保留必要的人类计划批准、按风险触发的审查、以及仅在存在合格候选时出现的知识确认。

## Contents

- [角色模型](#角色模型)
- [生命周期总览](#生命周期总览)
- [Locate/Create/Resume](#locatecreateresume)
- [澄清方式](#澄清方式)
- [计划批准](#计划批准)
- [实施与 checkpoint](#实施与-checkpoint)
- [Bug 与新 change 边界](#bug-与新-change-边界)
- [风险驱动验证与审查](#风险驱动验证与审查)
- [知识候选](#知识候选)
- [完成与 archive](#完成与-archive)
- [禁止恢复的 v1 模式](#禁止恢复的-v1-模式)

## 角色模型

主会话是 Coordinator/Orchestrator：它维护用户目标、批准过的计划、上下文预算、验证证据和最终汇报。它不是细粒度持久状态机，也不把 agent claim 当作完成事实。

当任务简单且边界清晰时，主会话可以直接实施和自检。当任务复杂、需要独立探索、或风险矩阵要求审查时，主会话可以委派通用 subagent。subagent 只得到目标、允许路径、必要读取路径或 heading、验证命令和紧凑返回要求，不接收大型全文知识库或历史 transcript。

## 生命周期总览

Nuclio v2 的日常入口是 `work`。标准顺序如下：

1. 定位项目根与 `.dev-docs`。
2. 确保 v2 骨架存在；必要时移动清晰 legacy 树。
3. 定位、恢复或创建一个 active change。
4. 按需读取知识、源码、配置和测试。
5. 澄清 Goal 与 Constraints。
6. 展示实施计划并等待用户批准。
7. 实施、记录 checkpoint、运行验证。
8. 按风险触发审查与修复。
9. 先报告产品结果和证据。
10. 如有合格知识候选，再请求知识确认。
11. 标记 completed 并 archive。

该顺序是用户体验流程，不是要求每一步都写入持久状态的协议。

## Locate/Create/Resume

先确认项目根。若 `.dev-docs` 不存在，可创建最小 v2 骨架；若清晰 legacy 树存在，使用 `change.py legacy-move` 整体移动；若分类不确定，停止并报告冲突路径。

扫描 active change 时，只看 `.dev-docs/changes/*/change.md`，默认排除 `.dev-docs/changes/archive/**` 和 `.dev-docs/legacy/**`。若用户请求与唯一 active change 明确匹配，则恢复该 change。若多个候选可能匹配，必须让用户选择。若没有匹配项，则用 `change.py create` 创建新的 change。

创建新 change 时给出人类可读 title 和 goal。归档后出现相关回归或后续扩展时创建新 change，并在 `related_changes` 中引用已归档 change。

## 澄清方式

澄清采用 recommendation-first：先给出当前建议，再问一个会改变计划的问题。不要把用户拖入问卷。简单安全任务可零问。

每次只问一个问题。问题必须影响 Goal、Constraints、Non-goals、影响路径、验证方法或风险判断。若问题不改变实施计划，直接继续。

## 计划批准

产品 mutation 前必须展示可理解计划。计划必须包括：

- Goal。
- 可执行 checklist。
- Non-goals。
- 预计影响路径或子系统。
- 验证方法。
- 风险级别。
- 拟采用的审查深度。

用户可以用自然语言批准、拒绝或修正。禁止要求固定 token、哈希、approval JSON 或身份短语。若用户修正范围，更新计划并重新展示。批准后，在 `change.md` 的 `Plan` 中写入 `Approved on YYYY-MM-DD.` 和 checklist。

计划批准只授权展示过的范围。新增 public API、架构、依赖、迁移、产品语义或独立可交付内容时，必须返回计划批准。

## 实施与 checkpoint

实施期间优先依赖工作树、代码、配置、测试和 CI。`change.md` 保存恢复所需压缩状态，而不是实时日志。

只在以下情况更新 `change.md`：

- 一个计划项有独立结果。
- 出现重要阻塞。
- 范围或 non-goal 发生变化。
- 做出无法从最终代码反推的重要决策。
- 验证发现影响下一步。
- 出现知识候选。
- Session 将未完成地结束。
- change 完成。

不要为每次文件编辑、命令尝试或 agent 消息写日志。

## Bug 与新 change 边界

继续当前 change 的条件：

- 原 Goal 尚未达成。
- 当前实现引入缺陷或回归。
- 当前交互验收失败且仍在批准范围内。
- 审查发现同范围问题。

创建新 change 的条件：

- 原 change 已归档。
- 请求与原 Goal 无关。
- 明显扩展范围。
- 改变 public API、架构、依赖、迁移、数据模型或产品语义。
- 可独立交付。

新 change 应在 frontmatter 中记录 `related_changes`，而不是重新打开 archive 内容作为 active 工作。

## 风险驱动验证与审查

风险矩阵决定验证和审查深度：

- 文档、简单配置、明确一文件修复：主会话自检和 focused check 通常足够。
- 普通多文件功能：focused check、必要的集成 check、定向审查。
- 跨模块、public API、数据模型：独立 reviewer 加更完整验证。
- 认证、安全、迁移、破坏性变更：独立 reviewer、完整回归或等价风险覆盖、明确回滚说明。

Generator-Critic 只在风险或用户要求触发。Nuclio v2 不强制固定 agent 流水线。

## 知识候选

产品验证通过后才处理长期知识。知识候选必须同时稳定、可复用、非显然、已验证、可归属。若没有合格候选，不显示第二个 Gate，直接完成和归档。

有候选时只展示语义结论、唯一目标文件/heading、操作类型、冲突与影响。用户可自然语言接受全部、部分、修改或拒绝。拒绝知识写入不影响已经验证的产品结果或 archive。

## 完成与 archive

完成时先报告产品结果、变更路径、验证命令、退出码和关键输出。随后在 `change.md` 中更新 `Validation`、`Outcome`、必要的 `Knowledge Updates`，用 `change.py set-status --status completed` 标记完成，再用 `change.py archive` 移动到 `.dev-docs/changes/archive/<change-id>/change.md`。

Archive 保存恢复线索和结果摘要，不是审计录像。后续相关问题创建带关联的新 change。

## 禁止恢复的 v1 模式

Nuclio v2 禁止恢复旧的完成交接、包绑定、证据身份、状态驱动授权、固定 Nuclio 专用 agent 流水线、持久过程 JSON、或以新名称复刻旧 helper 路由。也禁止要求 exact token、哈希或 approval JSON 作为日常实施批准。

历史 v1 资料只能在明确 legacy 语境中整体移动或按用户要求只读查看；不得解析、转换或恢复为当前运行时权威。
