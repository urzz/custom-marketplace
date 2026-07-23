# Nuclio v2 Knowledge

Nuclio v2 把长期知识作为可持续项目文档维护，而不是把每次 change 的过程材料永久化。知识写入只在产品结果完成验证后、存在合格候选、并获得用户确认时发生；它不创建第四状态权威，也不替代 `change.md`、`plan.yaml`、`state.yaml`、Git、代码或测试事实。

## Contents

- [知识组织](#知识组织)
- [三层工作流中的位置](#三层工作流中的位置)
- [领域拆分策略](#领域拆分策略)
- [候选五问](#候选五问)
- [收集来源](#收集来源)
- [验证依据](#验证依据)
- [分类与权威位置](#分类与权威位置)
- [长期化改写](#长期化改写)
- [冲突处理](#冲突处理)
- [用户确认](#用户确认)
- [写后核对](#写后核对)
- [操作类型](#操作类型)
- [不得提升的内容](#不得提升的内容)

## 知识组织

默认全局知识文件：

- `.dev-docs/knowledge/project.md`：产品目标、用户、术语、业务规则、跨领域事实。
- `.dev-docs/knowledge/architecture.md`：系统边界、架构约束、组件关系、重要设计原则。
- `.dev-docs/knowledge/engineering.md`：开发、测试、发布、代码风格、仓库约定、协作实践。

按需扩展：

- `.dev-docs/knowledge/domains/<domain>.md`：领域主轴知识。
- `.dev-docs/knowledge/decisions/<adr-id>.md`：ADR，记录重要决策及取舍。
- `.dev-docs/knowledge/runbooks/<name>.md`：可重复操作步骤。
- `.dev-docs/knowledge/glossary.md`：稳定术语表。

同一事实只能有一个权威位置。其他文件可以链接或摘要，但不得复制成第二份长期权威。

## 三层工作流中的位置

知识确认位于产品结果之后：Task checkpoint、必要 task/final review、whole-change validation 和 in-scope repair 均完成后，先向用户报告产品结果与证据，再判断是否存在长期知识候选。

知识文件不是第四层 change 状态：

- `change.md` 仍是当前 change 的 Spec 与最终 Outcome 权威。
- `plan.yaml` 仍是已批准执行合同权威。
- `state.yaml` 仍是唯一动态恢复状态权威，并且只由 `change.py` 写入。
- Git、代码、配置、测试和 CI 仍是产品事实。
- knowledge 只保存经确认、可复用、面向未来的项目事实。

拒绝、跳过或部分接受知识写入不影响已经验证的产品结果，不阻止 `complete`，也不阻止 `archive`。若知识候选本身暴露产品结果未验证或合同未满足，应回到 validation/review/repair，而不是用知识确认替代产品 Gate。

## 领域拆分策略

领域知识先使用单文件。只有出现人工信号时才拆分：文件过长且维护困难、多个团队/子系统共同编辑、用户要求分离、或知识具有不同生命周期。

拆分时保留旧文件导航和链接，明确每个子文件的边界。不要为一次小修复创建新领域结构。

## 候选五问

知识候选必须同时满足：

1. 稳定：短期内不太会因实现细节变化而失效。
2. 可复用：未来 change、维护、排障或决策会用到。
3. 非显然：不能从文件名、接口名或局部代码一眼看出。
4. 已验证：由代码、测试、配置、用户确认或运行结果支持。
5. 可归属：能放到唯一合适文件/heading，并说明来源。

任一问题答案为否，则不长期化。一次性 repair、当前 Plan revision 的临时选择、checkpoint subject、`next_action`、短期 blocker 或验证日志通常不合格。

## 收集来源

候选可来自：

- 用户明确说明的长期约束或业务规则。
- 实施中验证过的架构关系。
- 测试、构建、发布或运行环境的稳定实践。
- 多次出现的排障步骤。
- 重要设计取舍或 ADR 级决策。
- 归档 change 中对未来有复用价值的压缩结论。

来源必须能追溯到当前 change、代码路径、测试命令、配置文件、用户确认或已存在知识。不要把 subagent claim、聊天 transcript、完整 diff 或临时日志作为独立长期事实；它们最多是提示，必须由可核验来源支持。

## 验证依据

验证依据可以是：

- 相关代码或配置路径。
- 测试命令、exit code 和通过结果。
- 用户确认的业务事实。
- 已存在知识文件中的权威段落。
- 运行手册执行结果。
- 已完成 change 的 concise Outcome 与 checkpoint commit，可用于指向已验证事实。

未经验证的猜测不能写入长期知识。若事实重要但未验证，记录为当前 change 的 blocker、follow-up 或 Plan 修订候选，而不是长期知识。

## 分类与权威位置

选择权威位置时按顺序判断：

1. 跨领域产品或业务规则：`project.md`。
2. 系统结构或设计约束：`architecture.md`。
3. 开发、测试、发布实践：`engineering.md`。
4. 单一领域规则：`domains/<domain>.md`。
5. 决策及取舍：`decisions/<adr-id>.md`。
6. 可重复操作：`runbooks/<name>.md`。
7. 稳定术语：`glossary.md`。

写入前检索目标文件和可能重复位置，确认唯一权威。若候选需要同时改多个知识位置，先说明主权威位置和辅助链接位置，避免复制事实。

## 长期化改写

长期知识应写成面向未来维护的结论：

- 使用稳定名称、边界和原因。
- 链接关键路径、配置、测试命令或 ADR，而不是复制长 diff。
- 保留约束与适用范围。
- 避免“今天修了”“本次 change”之类过程措辞。
- 避免易漂移版本快照，除非它本身是长期约束。
- 避免记录 Plan revision、State phase、`next_action`、checkpoint subject 或临时 review finding。

## 冲突处理

重复事实是 `NO_OP`。兼容补充可 `MERGE` 或 `REFINE`。冲突不得静默覆盖；必须向用户展示冲突位置、候选语义、影响和建议操作。

ADR 被新决策取代时使用 supersede，保留历史和链接，不删除旧 ADR 的上下文。只有用户确认废弃、合并或删除时，才执行相应操作。

若冲突意味着产品实现或批准合同需要变化，停止知识写入，回到 Plan revision、validation、review 或 repair 决策，而不是通过知识更新改变产品语义。

## 用户确认

只有存在合格候选时才出现知识确认。展示内容应精简：

- 语义结论。
- 唯一目标文件/heading。
- 操作类型。
- 冲突状态。
- 影响和风险。
- 支撑证据摘要，例如代码路径、命令 exit code 或用户确认来源。

用户可自然语言接受全部、部分、修改或拒绝。拒绝不影响产品结果、验证结论、`complete` 或 `archive`。不要要求固定 token、hash、approval JSON 或身份短语。

## 写后核对

写入后核对：

- 同一事实是否仍只有一个权威位置。
- 是否产生重复或矛盾。
- 链接是否存在且一层即可到达。
- 根索引或领域导航是否需要更新。
- `change.md` 的 `Knowledge Updates` 是否记录实际写入，而不是候选草案。
- `state.yaml` 未被手写修改，knowledge 没有承担动态执行状态。

知识写入后的验证应使用适合文档变更的 focused check 或静态检查；不要为知识候选重新跑与产品无关的昂贵基线，除非该知识本身依赖该基线。

## 操作类型

- `NO_OP`：目标知识已完整表达同一事实，不写入。
- `MERGE`：把兼容补充合并到现有段落。
- `REFINE`：澄清范围、条件或措辞，不改变核心事实。
- `REPLACE`：用已确认的新事实替换旧事实；需说明旧事实为何过时。
- `SCOPE_SPLIT`：拆分适用范围，让多个事实并存。
- `NEW_ADR`：新增 ADR 记录重要取舍。
- `SUPERSEDE_ADR`：新 ADR 取代旧 ADR，旧 ADR 保留历史并链接新 ADR。
- `DEPRECATE`：标记事实或做法不再推荐，但保留背景。
- `DELETE`：删除已确认错误或无效知识；需要用户确认和冲突说明。
- `HALT`：冲突、归属、验证不足或产品合同影响不清，停止知识写入。

## 不得提升的内容

不要长期化：

- 聊天 transcript、agent 消息或逐步日志。
- 完整 diff、临时命令输出或低价值代码事实。
- 未验证猜测。
- 一次性待办。
- 很快漂移的依赖版本、环境快照或局部实现细节副本。
- 仅对当前 change 有意义的 checkpoint、repair decision、review finding 或 blocker。
- `plan.yaml` 的临时 Task 拆分、`allowed_paths`、checkpoint subject 或 review policy，除非用户明确把它们提升为长期项目约定。
- `state.yaml` 的 status、phase、current_task、`next_action`、repair id 或 validation 摘要。
- 任何旧式包、身份、批准指纹、helper 状态、状态路由或过程授权内容。

这些内容如有恢复价值，压缩进当前 `change.md` Outcome/Blockers/Validation；没有恢复价值则不记录。
