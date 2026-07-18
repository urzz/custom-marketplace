# Grill Protocol

Grill 是 Contract drafting 前后的澄清协议。它 recommendation-first、严格一次一问、只问会改变 Contract 的问题；可从项目事实、bounded context 或已确认回答推导的问题不得再问。简单 change 可以零问并直接产出可审 Contract。

## Contents

- [原则](#原则)
- [问题资格](#问题资格)
- [Recommendation-first](#recommendation-first)
- [一次一问](#一次一问)
- [复杂度与问题上限](#复杂度与问题上限)
- [零问路径](#零问路径)
- [Hard unknown blocker](#hard-unknown-blocker)
- [记录到 Contract](#记录到-contract)

## 原则

Grill 的目标不是采访用户，而是减少会改变 Contract authority 的未知数。Controller 必须先尝试用当前项目事实、bounded context、用户原始 intent 与 deterministic helper validation 形成 recommendation。

Grill 必须遵守：

- recommendation-first。
- 严格一次一问。
- 每个问题必须会改变 `contract.yaml` 的目标、非目标、acceptance、constraints、design、Task、`mutation_targets`、context_policy、validation 或 migration_or_rollout。
- 已能从项目事实推导的问题不问。
- 已能用 safe default 表达且不扩大 mutation 的问题不问。
- 不能为了填充模板而提问。

## 问题资格

一个问题只有同时满足以下条件才允许提问：

1. 答案会改变 Contract 字段或 Gate readiness。
2. 不能从 bounded context、现有 artifact、用户 intent 或安全默认值推导。
3. 不问会导致 scope drift、错误 ownership、不可验证 acceptance、危险 migration 或不可恢复 rollback。
4. 该问题比继续起草 Contract 更低成本。

不允许的问题：

- 纯偏好但不影响 Contract 的措辞问题。
- 可由 helper schema 或 path allowlist 自动判断的问题。
- 可通过 preview 展示而非提前询问的问题。
- 要求用户重复已确认答案的问题。
- 多个问题合并成一个长列表。

## Recommendation-first

每次需要澄清时，Controller 必须先给出建议答案与原因，再问用户是否接受或选择替代方案。

格式：

```text
建议：<recommended answer>。
原因：<bounded reason that references contract impact>。
问题：是否采用该建议？如果不采用，请给出会改变 Contract 的替代答案。
```

推荐必须基于项目事实或安全默认值，不能伪造用户意图。若没有安全推荐，必须说明为什么这是 hard unknown。

## 一次一问

Controller 每轮只能问一个必要问题。用户回答后，Controller 必须：

1. 记录到 draft Contract 的 `intent.confirmed_answers` 或相关字段。
2. 重新运行 helper validation 或静态 contract check。
3. 重新评估是否仍有会改变 Contract 的未知数。
4. 若仍有必要问题，再提出下一个。

不得一次列出多个独立问题。不得将一个多选题设计成覆盖多个 Contract 字段的隐藏批量问题，除非这些选项互斥且共同决定同一个字段。

## 复杂度与问题上限

简单 change：

- mutation_targets 明确。
- acceptance 可直接验证。
- context bounded。
- 无 legacy migration 或高风险 rollout。
- rollback 明确。

简单 change 可以零问，直接产出可审 Contract。

复杂 change 最多 5 个必要问题。计数规则：

- 每个用户轮次最多计 1 个问题。
- 因用户答复模糊而重复同一问题，不增加新问题计数，但必须保持一次一问。
- 超过 5 个不同必要问题仍有 hard unknown 时，停止 Grill 并写 blocker。

达到上限后仍存在 hard unknown，不得猜测、不得用宽泛 placeholder 通过 Contract Gate。

## 零问路径

当 Controller 能形成可审 Contract 时，应走零问路径：

1. 写明 inferred assumptions。
2. 把安全默认值写入 constraints 或 design。
3. 明确 mutation_targets 和 non_goals。
4. 展示 acceptance、checks、rollback 与 risks。
5. 请求 Contract Gate decision，而不是继续提问。

零问路径不等于自动 approval。Artifact existence 仍不是 approval，产品 mutation 仍需要 fresh Contract approval。

## Hard unknown blocker

Hard unknown 是无法从项目事实推导、会改变 Contract 且超出安全默认值的问题。示例：

- 用户未明确选择多个 active change 中的哪一个。
- 目标路径 ownership 与只读约束冲突。
- migration apply 是否 opt-in 未确认。
- required validation 无法运行且 acceptance 依赖该验证。
- rollback 会删除用户 active changes，且无法安全替代。

Hard unknown blocker 必须包含：

- unknown id
- 会影响的 Contract 字段
- 已尝试推导的 source
- 为什么不能安全默认
- 用户需要做的 exact choice

## 记录到 Contract

用户回答必须以稳定文本写入 `contract.yaml`：

- 直接影响目标或非目标的，写入 `intent.goals` 或 `intent.non_goals`。
- 澄清答案写入 `intent.confirmed_answers`。
- 安全边界写入 `constraints`。
- 技术取舍写入 `design.tradeoffs`。
- ownership 或文件范围写入 Task `mutation_targets`。
- migration 选择写入 `migration_or_rollout.opt_in` 或 blocker。

Controller 不得把 chat history 当作长期 authority。只有写入 `.dev-docs/contract.yaml` 并通过 helper identity 绑定的回答，才能参与 Contract Gate freshness。
