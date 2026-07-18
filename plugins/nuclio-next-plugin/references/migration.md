# Migration

Migration 定义 Nuclio Next 对 legacy `.dev-docs/` 或其它旧工作流 artifact 的 detect、preview、apply 合同。默认路径只读 preview；apply 必须显式 opt-in、完整验证、原子写入新 artifacts、不覆盖 legacy、不改产品代码。任何 authority 字段缺失都拒绝 partial conversion。

## Contents

- [目标与边界](#目标与边界)
- [Detect](#detect)
- [Preview](#preview)
- [Apply](#apply)
- [字段级映射](#字段级映射)
- [Blockers](#blockers)
- [验证与 evidence](#验证与-evidence)
- [禁止事项](#禁止事项)

## 目标与边界

Migration 的目标是把已有 change 事实转换成 Nuclio Next 可验证的 selected `TARGET_CHANGE_ROOT`。`TARGET_CHANGE_ROOT` 必须等价于 `CHANGE_ROOT=.dev-docs/changes/<change-id>`，迁移后的 target authority 是 `CHANGE_ROOT/contract.yaml`、`CHANGE_ROOT/context.jsonl`、`CHANGE_ROOT/state.json`、`CHANGE_ROOT/research/` 和 change-local evidence identity。Project-level `.dev-docs/` 只保留 index、knowledge 和 changes/index。Legacy source path 可由用户指定，但迁移后的 target authority 必须 change-local。Migration 不恢复来源不明的历史内容，不制造缺失 approval，不把旧 artifact existence 当成 authority。

边界：

- detect 只读。
- preview 只读且不写目标 artifacts。
- apply 只在用户 exact opt-in 后运行。
- apply 不覆盖 legacy 文件。
- apply 不修改产品代码。
- apply 不生成部分 authority；缺字段时必须 blocker。

## Detect

Detect 只读识别可能的 legacy 或半成品 artifacts。允许识别的输入包括：

- `brief.md`
- `spec.md`
- `design.md`
- `plan.yaml`
- context manifests
- state 文件
- evidence 文件
- review 或 validation summary 的稳定文件引用

Detect 输出必须包含：

- detected artifact path
- artifact type
- content hash
- inferred role
- confidence
- missing required fields
- whether artifact can participate in preview

Detect 不允许：

- 写 target `CHANGE_ROOT/contract.yaml`。
- 写 target `CHANGE_ROOT/context.jsonl`。
- 写 target `CHANGE_ROOT/state.json`。
- 写 target `CHANGE_ROOT/research/`。
- 写 target `CHANGE_ROOT/evidence/completion.md`、`CHANGE_ROOT/evidence/decision.md` 或 `CHANGE_ROOT/evidence/finish-apply.md`。
- 修改 legacy 文件。
- 读取 raw transcript 或 full conversation。
- 递归读取整个仓库。

Detect 发现多个 active change 时，必须停止并要求用户选择；不得猜测 canonical change。

## Preview

Preview 基于 detect 输出生成只读迁移计划。Preview 必须输出逐字段映射、目标 contract/context/state 草案摘要与 blockers，但不写目标 artifacts。

Preview 必须包含：

- source artifact map：每个 source path、sha256、type、line range 或 object path。
- target `CHANGE_ROOT/contract.yaml` field map。
- target `CHANGE_ROOT/context.jsonl` entry map。
- target `CHANGE_ROOT/state.json` status、gates、tasks、blockers、fix_budgets、history 草案。
- target `CHANGE_ROOT/research/` mapping for bounded research artifacts that can be verified.
- evidence mapping：哪些 source evidence 可成为 `CHANGE_ROOT/evidence/tasks/<task-id>/...`、`CHANGE_ROOT/evidence/completion.md`、`CHANGE_ROOT/evidence/decision.md` 或 `CHANGE_ROOT/evidence/finish-apply.md`，哪些只能成为 diagnostic note。
- blockers：字段级缺失、冲突、stale、ownership unknown 或 validation impossible。
- apply plan：将要创建的新 artifacts、不会覆盖的 legacy artifacts、rollback/stop 行为。

Preview 必须显式标注哪些字段不能从 legacy 推导。不能为了让 preview 看起来完整而填入 guessed authority。

## Apply

Apply 必须由用户对当前 preview identity 给出显式 opt-in。Opt-in 必须绑定 preview hash、source artifact hashes、target paths、state version plan 与 apply command identity。Target paths must all be under the selected `TARGET_CHANGE_ROOT` / `CHANGE_ROOT=.dev-docs/changes/<change-id>` except project-level indexes explicitly maintained outside migration authority.

Apply 顺序：

1. 重新运行 detect，并确认 source hashes 未变。
2. 重新生成 preview，并确认 preview hash 与用户 opt-in 绑定一致。
3. 完整 validate 目标 `CHANGE_ROOT/contract.yaml`、`CHANGE_ROOT/context.jsonl`、`CHANGE_ROOT/state.json`、`CHANGE_ROOT/research/` 与 evidence identity。
4. 检查目标路径不存在，或只存在 apply plan 明确允许的临时文件。
5. 原子写入新 artifacts。
6. 写入 migration evidence，记录 source hashes、target hashes、blocked fields、apply result。
7. 校验写后 hashes 与 preview target identity 一致。

Apply 失败时必须 fail closed：

- 未写任何目标时，报告 blocker。
- 已写部分目标但无法完成 journal 时，报告 manual handling blocker。
- 不得继续执行产品 mutation。
- 不得覆盖 legacy artifact 试图恢复。

## 字段级映射

Preview 至少必须覆盖以下 Nuclio Next 字段，且逐项说明 source 或 blocker。

### contract.yaml

- `schema_version`
- `change_id`
- `contract_version`
- `intent.goals`
- `intent.non_goals`
- `intent.confirmed_answers`
- `acceptance`
- `constraints`
- `design.boundaries`
- `design.data_flow`
- `design.contracts`
- `design.tradeoffs`
- `tasks[].id`
- `tasks[].name`
- `tasks[].owner`
- `tasks[].dependencies`
- `tasks[].mutation_targets`
- `tasks[].handoffs`
- `tasks[].checks`
- `tasks[].rollback`
- `context_policy.required`
- `context_policy.jit`
- `context_policy.forbidden`
- `context_policy.budget`
- `validation.focused`
- `validation.full`
- `validation.change_wide`
- `migration_or_rollout`

### context.jsonl

- `id`
- `audience`
- `mode`
- `path`
- `reason`
- `sha256` for stable entries
- `line_range` when bounded by lines
- `retrieval_trigger` for jit entries
- `budget` for jit entries

### state.json

- `schema_version`
- `state_version`
- `change_id`
- `status`
- `contract`
- `context`
- `gates.contract`
- `gates.finish`
- `tasks`
- `blockers`
- `fix_budgets`
- `completion`
- `decision`
- `history`

### evidence

- `schema_version`
- `evidence_id`
- `kind`
- `change_id`
- `contract_sha256`
- `context_fingerprint`
- `state_version`
- `created_at`
- Task id when relevant
- implementation, validation, review, mutation_map, completion, decision 或 finish_apply_journal object when relevant

字段映射中的 artifact path 必须指向 selected `CHANGE_ROOT`：`CHANGE_ROOT/contract.yaml`、`CHANGE_ROOT/context.jsonl`、`CHANGE_ROOT/state.json`、`CHANGE_ROOT/research/`、`CHANGE_ROOT/evidence/completion.md`、`CHANGE_ROOT/evidence/decision.md` 与 `CHANGE_ROOT/evidence/finish-apply.md`。

## Blockers

以下字段或情况缺失时必须产生字段级 blocker，且不生成部分 authority：

- 无法确定 `change_id`。
- 无法确定 `mutation_targets` 或 ownership。
- 缺 acceptance 或 constraints。
- 缺 rollback 或 validation checks。
- 无法构造 bounded `context.jsonl`。
- context 包含绝对路径、glob、路径穿越、宽泛目录根、raw logs 或 full conversation。
- 旧 state 与 target lifecycle status 无法合法映射。
- approval identity 缺失或不能绑定 artifact hash、context fingerprint 与 state version。
- evidence 缺 before/after identity、check output hash 或 review package identity。
- 多个 active change 冲突。
- legacy artifact hash 在 preview 与 apply 之间改变。

Blocker 必须说明 field、source path、reason、required user action 与是否可通过 contract revision 解决。

## 验证与 evidence

Migration helper 的验证必须覆盖：

- schema validation。
- path allowlist 与 no path traversal。
- target path non-overwrite。
- source hash freshness。
- preview hash identity。
- state transition legality。
- context fingerprint。
- evidence identity。
- no product code mutation。

Migration evidence 必须能证明 detect/preview/apply 的输入、输出和 stop reason。Raw transcript、agent summary 和 artifact existence 不得成为 authority 字段。Migration evidence 的 target authority 必须 under selected `CHANGE_ROOT=.dev-docs/changes/<change-id>`，包括 `CHANGE_ROOT/contract.yaml`、`CHANGE_ROOT/context.jsonl`、`CHANGE_ROOT/state.json`、`CHANGE_ROOT/research/`、`CHANGE_ROOT/evidence/completion.md`、`CHANGE_ROOT/evidence/decision.md` 与 `CHANGE_ROOT/evidence/finish-apply.md`。

## 禁止事项

Migration 禁止：

- silent partial conversion。
- 未经 explicit opt-in 写目标 artifacts。
- 覆盖或删除 legacy 文件。
- 修改产品代码。
- 从 raw transcript、chat history 或 agent summary 恢复 authority。
- 猜测 ownership、approval、freshness、acceptance 或 validation。
- 将旧 workflow 名称写成 Nuclio Next canonical lifecycle。
- 在 authority 字段缺失时继续执行 work。
- 将 migration target authority 写到 project-root `.dev-docs/` change artifacts；target contract/context/state/research/evidence 必须位于 selected `CHANGE_ROOT`。
