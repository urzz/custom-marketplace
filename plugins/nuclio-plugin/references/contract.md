# Contract

`contract.yaml` 描述一个 change 的 approved execution contract。其 authority 规则短引用 `authority.md`：`.dev-docs/` 是事实源，artifact existence 不是 approval，Contract approval 必须 fresh，`mutation_targets` 是唯一写授权。机器稳定部分保持原始 protocol token，包括 schema keys、JSON/YAML 字段名、状态枚举、helper action、命令、路径、类名、错误原文与固定协议 section heading；`output_language` 只约束面向维护者的自然语言正文，不翻译这些机器字段或历史 evidence。

## 顶层字段

- `schema_version`：contract schema 版本，必须存在。
- `change_id`：稳定 change identity，必须存在且非空。
- `contract_version`：当前 contract 修订版本，必须存在且非空；任何会影响 approval 的修改都必须提升或更新 identity。
- `output_language`：面向维护者 Markdown 正文的唯一 change-local language authority，必须存在且为显式 language tag，例如 `zh-CN` 或 `en`。新 Contract 由 work Coordinator 根据当前请求主要语言提出默认值，用户可以在 Contract Gate 前修正；任何后续语言变化都必须走 Contract revision 与 fresh Contract Gate。旧 active Contract 缺少该字段时必须 fail closed，并要求正式 Contract revision；Coordinator、agent 或聊天历史不得静默覆盖该值。
- `intent`：目标、非目标与已确认回答。
- `acceptance`：非空数组，列出用户可验证的完成条件。
- `constraints`：非空数组，列出安全、范围、文件、模型、命令或迁移限制。
- `design`：边界、数据流、内部 contract 和 tradeoff。
- `tasks`：非空数组，定义可派发 Task。
- `context_policy`：required、jit、forbidden 与 budget。
- `validation`：focused、full、change_wide 检查。
- `migration_or_rollout`：可选，描述显式迁移或 rollout plan。

## intent

`intent` 必须包含：

- `goals`：非空数组，描述本 change 要达成的结果。
- `non_goals`：数组，描述明确不做的事项。
- `confirmed_answers`：数组，记录用户已确认的关键问题与答案；为空时也必须显式写出空数组。

## acceptance 与 constraints

- `acceptance` 必须非空，且每项应可由 review、静态检查、执行检查或用户检查验证。
- `constraints` 必须表达不可跨越的边界，包括只读路径、禁止命令、migration opt-in、approval requirement 与 helper fail-closed 行为。
- 简单 change 可以少写设计细节，但不能缺 acceptance、owner、checks、rollback 或 validation。

## design

`design` 必须包含：

- `boundaries`：系统边界、读写边界、authority 边界。
- `data_flow`：输入 artifact、helper 派生、packet、evidence、state transition 的流向。
- `contracts`：关键文件格式、schema/helper 责任、agent packet contract。
- `tradeoffs`：已接受的取舍、风险和不采用方案。

## tasks

每个 Task 必须包含：

- `id`：稳定 Task id。
- `name`：人类可读名称。
- `owner`：执行责任或 bounded worker 类型。
- `dependencies`：Task id 数组；无依赖时为空数组。
- `mutation_targets`：非空数组，唯一写授权；helper 负责 path 语义与 overlap 校验。
- `handoffs`：输入、输出、report、evidence 或 review package 描述。
- `checks`：focused 与 full 命令描述；可执行命令必须显式列出。
- `rollback`：如何恢复本 Task 变更或停止后的安全处理。

Task 可以附加 `review`、`fix_budget`、`model` 或 `notes`，但不能省略上述必填字段。

## context_policy

- `required`：稳定 context 条目 id 列表或对象列表，必须可映射到 `context.jsonl`。
- `jit`：允许按 trigger 检索的 bounded context，必须有 budget。
- `forbidden`：禁止读取或携带的 context 类别，例如 full conversation、raw logs、all docs、all source、unrelated tasks。
- `budget`：总读取预算或按 audience 划分的预算；helper 负责 fail closed 解释。

## validation

`validation` 必须包含：

- `focused`：覆盖变更核心 contract 的最小检查。
- `full`：Task 或 change 的完整检查。
- `change_wide`：所有 Task 完成后的整体验证、mutation map、evidence consistency 与 Finish readiness。

## migration_or_rollout

该字段可选。存在时必须说明：

- detection：如何检测 legacy 或 rollout 前置条件。
- preview：如何预览影响。
- opt_in：用户如何显式选择。
- verification：如何证明没有 silent partial conversion。
- rollback：失败或拒绝时如何停止或恢复。
