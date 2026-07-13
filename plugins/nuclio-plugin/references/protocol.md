# Nucl.io File Protocol

## Contents
- [Core Principle](#core-principle)
- [Directory Roles](#directory-roles)
- [.dev-docs Layout](#dev-docs-layout)
- [Change Artifact Protocol](#change-artifact-protocol)
- [Authority Boundaries](#authority-boundaries)
- [Canonical Plan Ownership Contract](#canonical-plan-ownership-contract)
- [Handoff Lineage and Snapshot Lifecycle](#handoff-lineage-and-snapshot-lifecycle)
- [Task and Implement Completion Freshness](#task-and-implement-completion-freshness)
- [Dynamic Undeclared Product Mutation](#dynamic-undeclared-product-mutation)
- [Design Revision Closure](#design-revision-closure)
- [Canonical State Protocol](#canonical-state-protocol)
- [Generic State Transition Rules](#generic-state-transition-rules)
- [Implement/Verify/Fold Exact State Transitions](#implementverifyfold-exact-state-transitions)
- [Gate Readiness Rules](#gate-readiness-rules)
- [Plan Task Status Migration](#plan-task-status-migration)
- [Dirty Worktree Protocol](#dirty-worktree-protocol)
- [State Merge Rules](#state-merge-rules)
- [Deterministic Helper Boundary](#deterministic-helper-boundary)
- [Change Index and Archival](#change-index-and-archival)
- [Hard Rules](#hard-rules)

## Core Principle

Nucl.io 的事实源是文件，不是对话。

- 对话用于澄清和记录当前轮明确授权，不承担持久状态职责。
- `.dev-docs/` 保存稳定项目知识和当前 change 事实。
- `.nuclio/` 只保存未来工具运行态、缓存和临时状态。
- MVP 不实现 `.nuclio/` runtime，只保留目录边界。
- `plan.yaml`、`state.json` 与 `evidence/` 各有单一职责，不互相复制或竞争 authority。

## Directory Roles

| Path | Role | Git |
|---|---|---|
| `.dev-docs/` | 项目知识与当前 change 事实的 source of truth | yes |
| `.nuclio/` | 未来 runtime/cache/temp state；不是 MVP 状态源 | usually gitignored |

## .dev-docs Layout

Project Init 使用以下 baseline layout：

```text
.dev-docs/
  index.md
  project/
    brief.md
    principles.md
    scope.md
  product/
    index.md
    glossary.md
    personas.md
    use-cases.md
  architecture/
    index.md
    overview.md
    constraints.md
    decisions.md
  engineering/
    index.md
    stack.md
    coding-style.md
    testing.md
    deployment.md
  domain/
    index.md
    model.md
    workflows.md
  changes/
    index.md
```

## Change Artifact Protocol

每个结构化 change 使用：

```text
.dev-docs/changes/<change-id>/
  brief.md
  spec.md
  design.md
  plan.yaml
  state.json
  context/
    implement.jsonl
    verify.jsonl
  research/
    notes.md
  evidence/
    test-output.md
    review.md
    fold-proposal.md
    fold-apply.md
    tasks/
      <task-id>/
        task-brief.md
        implementer.md
        validation.md
        review.md
        snapshots/
          completion-<task-id>-<path-id>-a<attempt>-r<review-cycle>.json
          dependency-<from-task>-to-<task-id>-<path-id>-a<attempt>-r<review-cycle>.json
          live-<task-id>-<path-id>-a<attempt>-r<review-cycle>.json
```

`<change-id>` 应使用 `YYYY-MM-DD-short-slug`；第一个 MVP change 可以使用 `0001-mvp`。

Task evidence 使用固定路径但 append-only cycles，不覆盖旧证据：

- `implementer.md`：追加 `## Attempt N`；fixer cycle 追加 `## Fix Cycle N`。
- `validation.md`：追加对应 `## Attempt N / Review Cycle M` 或 `## Fix Cycle N / Review Cycle M` 的真实验证命令、退出码与关键输出；只有在该 cycle identity 已成功持久化到 `state.json` 后生成的完整 validation，才是 authoritative final validation evidence。
- `review.md`：每次 fresh reviewer/re-review 追加 `## Review Cycle N`，并使用已由 final validation 绑定的同一 persisted tuple；reviewer 或 re-review dispatch 不递增 cycle。
- 每个 Attempt/Fix/Review cycle 必须记录当时 `task-brief.md` 的 immutable content hash 与 relevant brief summary；validation/review 绑定当前 `task_scope_fingerprint` 的完整 cycle identity：`task_id`、`attempt`、`fix_cycle`、`review_cycle`、brief hash、own mutation map、dependency/output fingerprints（HEAD 与当时 global fingerprint 仅辅助审计）。中间开发测试、探索性命令或 cycle identity 持久化前的验证输出只可作为审计材料，不构成 authoritative final validation evidence。固定 brief path 被重提取后，旧 cycles 保留但不再适用于新 hash 或新 cycle identity，不能伪装成新版 brief evidence，也不能用于 Task completion、Implement complete、Verify fix 或 resume。

Artifact existence is not gate approval：

- `brief.md`、`spec.md`、`design.md`、`plan.yaml` 或 context manifests 存在，只表示草稿产物存在。
- 后续阶段不得仅因 artifact 存在而判断上一阶段已通过。
- Gate readiness 只来自 `state.json.gates.<stage> == "approved"`，或当前轮用户对该 gate 的明确授权。

## Authority Boundaries

| Concern | 唯一 authority | 说明 |
|---|---|---|
| Task definition、依赖、acceptance、verification、rollback | `plan.yaml` | 定义计划，不保存执行进度 |
| Mutable task state、phase、status、current task、Gates | `state.json` | 唯一可恢复 workflow 状态机 |
| 单 Task brief、实现、验证、reviewer 与 snapshot 证据 | `evidence/tasks/<task-id>/` | 固定四个 Markdown 文件加固定 `snapshots/` 结构化附件目录 |
| Change-wide Verify verdict | `evidence/review.md` | Verify 的 change-wide 审查结论 |
| Fold candidate | `evidence/fold-proposal.md` | 待用户选择 accept/edit/reject/no-op/defer 的候选，不是长期知识 |
| Fold apply evidence | `evidence/fold-apply.md` + `state.json.fold_apply` | Two-phase apply attempts、errors、target reconciliation 与 hashes |
| Long-term project knowledge | 相关 `.dev-docs/project/`、`product/`、`architecture/`、`engineering/`、`domain/` 文件 | 仅 Fold approval 后写入稳定结论 |

`evidence/` 保存可审查证据，不替代 `state.json` 的状态；`state.json` 只引用 evidence 路径和 verdict，不复制长报告。

本文件是 ownership、handoff lineage、snapshot freshness、dynamic mutation 与 Design revision transition 的唯一状态和证据算法 authority。其他 references 只能引用本文件并摘要行为边界，不得复制 closure、fingerprint 或 transition 算法形成第二套 authority。

## Canonical Plan Ownership Contract

Design 产出的每个 canonical Task 必须同时声明 `mutation_targets` 与 `ownership_handoffs`；`task-helper.py validate-change` 从这些字段和 `depends_on` 派生 `ownership_table` 与 normalized `task_contract`。`task_contract` 的顶层字段精确为 `plan_order`、`tasks`、`ownership_table`；每个 Task contract 包含 `id`、`depends_on`、`acceptance`、`verification`、`context_refs`、排序后的 `mutation_targets` 与按 `(path,from_task,to_task)` 排序的 `ownership_handoffs`，排除 mutable `status`、`files_hint`、title 与 rollback 文案。`ownership_table` 按 path 排序；每行包含 `path`、派生 `owners`、派生 `handoffs` 与派生 `final_owner`。

- `mutation_targets` 是 Task 实际可修改的 product path 集。路径必须是规范化、安全、repo-relative 的单文件路径；同一 Task 内不得重复，并拒绝 `.git`、`.dev-docs/changes`、`.superpowers/sdd` 本身及其后代。默认 ownership 独占：同一路径只允许一个 owner。
- 多 Task 修改同一路径时，每个后继 Task 在自身 `ownership_handoffs` 中声明 exact `{path,from_task,to_task}`，且 `to_task` 必须等于当前 Task。每条 edge 要求 `to_task` 直接或传递依赖 `from_task`；共享基础文件没有例外，也必须声明 ownership 和 handoff。
- Handoff chain 只由显式 edges 与 dependency topology 决定。每个共享 path 必须形成覆盖所有声明 owners 的无 cycle、无 branch、无 gap 线性链；唯一 terminal owner 是 helper 派生的 `final_owner`，Plan 不得增加可编辑 `final_owner`。当case facts足够（例如helper row显示某path `owners=[T1,T4]` 且 `final_owner=T4`）时，Controller/trajectory必须显式报告该helper-derived ownership row；不得只报告Plan文本顺序、`files_hint`或自由文本handoff。Plan 文本顺序不决定 chain，只在多个 dependency-eligible Tasks 同时可运行时作为 eligible tie-break。
- `files_hint`、context manifest、JIT discovery 与 read permission 都只是 navigation/read contract，不是 ownership、mutation allowlist 或 fingerprint input。Task brief 的 `Approved Ownership Slice` 只摘录当前 Task targets、incoming/outgoing handoffs 与相关 final owners，不创造新权限。
- Design 首次获得 explicit approval 时，Controller 必须持久化 helper 产出的 normalized `task_contract` 为 `state.implementation.approved_task_contract`；后续 dispatch、review 与 revision 只消费这份 approved contract，不从 prose 或 `files_hint` 推断 ownership。

## Handoff Lineage and Snapshot Lifecycle

每个 canonical owned path 有三类不同 snapshot；三者不得混用。Canonical path 是通过 ownership path 安全校验并规范化后的单个 repo-relative 文件路径。对其 UTF-8 bytes 计算完整 lowercase hex SHA-256，得到无原文泄漏且无截断碰撞的 `path_id=sha256(UTF-8(canonical path))`（精确为 64 个 lowercase hex 字符）。每个 snapshot record **只表示一个** `path`、一个 `path_id`、一个 `path_hash` 和该 path 的一个派生 `final_owner`；禁止在单 record 中放置多 path map。Snapshot 文件是现有 Task evidence 的结构化附件，不是 `.nuclio/` runtime、helper 生成物或第二状态 authority：

- `completion_snapshot`：某 Task 在 authoritative final validation 与 fresh reviewer clean/PASS 后，由 Controller 为每个 owned path 分别写入 `evidence/tasks/<task-id>/snapshots/completion-<task-id>-<path-id>-a<attempt>-r<review-cycle>.json`。它固定该 owner 当时该 path 的 bytes（删除使用 canonical `deleted` marker）及同一 evidence cycle；文件与 identity append-only。合法下游 handoff 后不要求历史 completion 与最终 live bytes 相等，也不得覆盖、重写或废弃旧 cycle。
- `dependency_handoff_snapshot`：Controller 在下游 owner dispatch 前，为每条 exact incoming edge 的单个 path 写入 `evidence/tasks/<to-task>/snapshots/dependency-<from-task>-to-<to-task>-<path-id>-a<attempt>-r<review-cycle>.json`。它只固定该 path 的 exact `incoming_edge={from,to,path}` 与直接父 snapshot identity；文件与 identity append-only。Plan handoff edge schema始终是 `{path,from_task,to_task}`，snapshot `incoming_edge` schema始终是 `{path,from,to}`；二者语义关联但字段shape不同，记录、state refs、trajectory与报告均不得混用。只有当时 live bytes 的 `path_hash` 与 incoming snapshot 相等时才能开始下游 mutation。
- `live_snapshot`：Controller 在每个 mutation/reconciliation 边界为每个 path 写入新的 current record `evidence/tasks/<current-owner>/snapshots/live-<current-owner>-<path-id>-a<attempt>-r<review-cycle>.json`，并只移动 state current ref；旧文件保留为历史。Handoff 后 current owner 更新，链完成后只能由派生 `final_owner` 的 current record 表示最终 live bytes。

三类文件使用同一个 per-path canonical record contract。每个 record 的字段 key set 精确为：`schema="nuclio.snapshot"`、`version=2`、`kind=completion_snapshot|dependency_handoff_snapshot|live_snapshot`、`path`、`path_id`、`path_hash=sha256:<64 lowercase hex>|deleted`、`task`、`attempt`、`review_cycle`、`final_owner`、`incoming_edge`、`parent_snapshot`、`acceptance_preservation_refs` 与 `record_hash`；禁止缺少、增加或重命名字段。`incoming_edge` 对 dependency record 必须是且只可以是该 path 的 exact `{from,to,path}`；completion/live record 为 `null`。`parent_snapshot` 精确为 `{record_hash:<sha256:...>}` 或首个无父 record 的 `null`。`acceptance_preservation_refs` 是对象数组，每项精确标识固定 validation/review `evidence_path` 与其 ordinary-file `record_hash`；Controller 按 `(evidence_path,record_hash)` 的 UTF-8 lexicographic 顺序规范化。`record_hash` 对排除 `record_hash` 字段后的整个 record，使用 object keys UTF-8 lexicographic 排序、数组保持上述 canonical 顺序、无无意义空白的 canonical JSON 序列化为 UTF-8，再计算 `"sha256:"+SHA-256(payload bytes)`。Controller 唯一负责 canonical path/path_id、读取 bytes、构造 records、排序 refs、计算/重算 hashes 与持久化；worker/reviewer只能提供 evidence locations，绝不能计算 authoritative snapshot/fingerprint。现有 helper 尚不生成或验证这些文件；这是 Controller file protocol，不得虚构 helper capability。

State 的 current refs 使用固定字段名与对象 shape：`state.tasks.<id>.completion_snapshot_refs`、`dependency_handoff_snapshot_refs`、`live_snapshot_refs` 都是对象数组，而不是 hash 数组。前两者分别按 approved ownership path、approved incoming edge `(path,from_task,to_task)` 的 canonical 顺序排列；live refs 按 approved ownership path 排列。每项至少包含 `{evidence_path,record_hash,path,path_id}`；dependency 项还必须包含 `incoming_edge:{from,to,path}`。每次 completion、handoff dispatch 或 live reconciliation，Controller 先完整写 record并重算成功，再通过现有 preserve/merge完整替换相应 current refs数组。Task complete产生该 Task所有 approved paths的 current completion refs；没有对应 kind/path的 current record时不得省略或用裸 hash代替。

Task 2 contract-revision invalidation 对每个 affected Task 清空 `completion_snapshot_refs=[]`、`dependency_handoff_snapshot_refs=[]`、`live_snapshot_refs=[]`，同时清除当前 `task_scope_fingerprint`/review-clean marker；旧 attempts/cycles、旧 state audit 与所有 snapshot 历史文件都保留且不得删除。不受影响 Task 的 current refs保持不变。Verify-fix invalidation采用同样的 current-ref清理语义；普通 resume只验证，不刷新或清理 refs。

Resume 只能逐项从 state ref 的 `evidence_path` 精确读取 record；禁止扫描 `snapshots/` 目录、按最新 mtime/文件名猜测或从 Markdown 自由文本重建。Controller 必须先验证 `evidence_path` 是 safe canonical repo-relative file path且位于 exact `evidence/tasks/<task-id>/snapshots/`，再验证 filename 中的 kind、task/from/to、`path_id`、attempt 与 review-cycle tuple均匹配 state/record。随后重算并核对 record `schema/version/kind/path/path_id/path_hash/task/attempt/review_cycle/final_owner/record_hash`，确认 `path_id=sha256(UTF-8(canonical path))`、当前 bytes匹配需要 current freshness 的 `path_hash`、dependency 的 `incoming_edge` 精确等于 approved contract edge、`parent_snapshot.record_hash` 可由父 state ref精确到达，以及 acceptance refs存在且适用。缺失、tuple/filename/path/path_id/hash/edge mismatch、lineage gap、stale cycle或state/file identity mismatch一律fail closed。

以同一共享路径 `src/service.ts` 的 `T1 → T4 → T9` 为例：T1 review clean为该path产生 `H1=completion_snapshot(T1,src/service.ts)`；T4 dispatch前为同一path以 `H1` 建立incoming dependency record，完成后产生 `H4=completion_snapshot(T4,src/service.ts)`；T9 dispatch前为同一path以 `H4` 建立incoming record，完成后产生最终 `H9=live_snapshot(T9,src/service.ts)`。`H1`、`H4` 是append-only历史，合法downstream mutation允许 `H1.path_hash != H9.path_hash` 且 `H4.path_hash != H9.path_hash`；但该path的 `H1 → H4 → H9` incoming lineage、依赖关系、每段acceptance preservation与evidence identity必须完整。若T4开始前该path live bytes不等于incoming `H1.path_hash`，或T9开始前不等于incoming `H4.path_hash`，该差异是未归属mutation，必须阻断dispatch。

文件身份不会因同 owner pair 复用而碰撞：若 approved `T1 → T4` 同时交接 `src/a.ts` 与 `src/b.ts`，Controller 必须生成两个 dependency files，分别包含两个不同完整 `path_id`，每个文件只含自身 path 的 exact incoming edge。Owner也按path独立：同一Task T2可拥有 `src/c.ts`（`final_owner=T2`）并作为 `src/d.ts` 的中间owner（该path的 `final_owner=T7`）；Controller为两条path生成不同records并分别写各自 `final_owner`，禁止用Task级单一final owner覆盖二者。

## Task and Implement Completion Freshness

Task complete、Implement complete 与 resume 的 freshness 按 ownership 类型分别判断：

1. **非 handoff path**：唯一 owner 的 `completion_snapshot_refs` 与 `live_snapshot_refs` 中该 path 对象所指 per-path records，其 `path/path_id/path_hash/final_owner` 必须彼此一致并精确匹配当前 live bytes；该路径不得因为其他路径存在 handoff 而获得豁免。Own path、brief、dependency/output 或 cycle identity drift 均使当前 validation/review 失效。
2. **Handoff path**：历史 owner 的 per-path `completion_snapshot` 是 append-only history，合法下游 mutation后不失效。Controller必须验证该path每条incoming edge的 `dependency_handoff_snapshot` 在下游开始前匹配当时live bytes、从首owner到`final_owner`的parent lineage完整、edge dependency成立、每段`acceptance_preservation_refs` fresh，且`final_owner`的current per-path live ref精确匹配当前live bytes及其current completion record。禁止用最终bytes重算历史owner的`own_mutations`、覆盖历史snapshot、使旧review cycle失效，或要求历史completion与final live相等；任一incoming snapshot、lineage、acceptance preservation或final-owner freshness缺口才触发重验或阻断。
3. **Task evidence**：`task_scope_fingerprint` 的canonical input对每个非handoff own path引用按path排序的current completion/live ref对象；对每个handoff path引用当前Task的per-path completion ref、按approved edge排序的incoming dependency ref对象与parent record identities。`own_mutations`不再是从当前最终bytes独立重算的第二份map，而是这些per-path records中与该Task cycle绑定的`path_hash`引用；Controller用固定cycle/brief/dependency字段加这些refs计算fingerprint。Worker不计算authoritative fingerprint，历史owner snapshot也不得被重解释为final-live assertion。
4. **Implement complete**：逐 Task/逐 path 应用以上规则后，才计算完整 reconciled workflow product scope 的 `global_product_fingerprint`。它独立表示最终 change-wide bytes，供 Implement/Verify/Fold freshness 使用；不编码、替代或证明 handoff lineage。

## Dynamic Undeclared Product Mutation

每次 worker report、Git reconciliation、authoritative validation 和 review 前都必须构造 actual product mutation map，并与 `approved_task_contract` 的 `mutation_targets`/当前 ownership slice 比较。发现实际修改了未声明 product path 时：

1. 立即停止 implementer/fixer 对该 path 及当前 Task 的继续修改；reviewer 不得以“改动合理”事后放行。
2. 在 authoritative validation/review 前，按 Task blocker evidence records 向固定 Task evidence append canonical `kind=design_revision` BLOCKED record，再执行对应 blocked transition。Blocker 至少明确未声明 `path`、当前候选 Task、候选 owner，以及必须修订的 Plan fields（`mutation_targets`、必要的 `ownership_handoffs`/`depends_on`/acceptance/context refs）。无tools/模拟trajectory不得虚构物理append/merge已经执行；但当actual mutation boundary事实已足以判定未声明path时，`actions`/`state_writes`必须把canonical BLOCKED evidence append和canonical blocked transition列为STOP前当前trajectory必须形成的transition，而非仅作为未来pending建议。`state_non_writes`只能列validation/reviewer dispatch、继续product mutation、非canonical state patch等禁止写入，不得否定canonical blocker formation。
3. 回到 Design 修订并重新 explicit approval；动态未声明 mutation 必然改变 `mutation_targets`/ownership contract，因此必须使用 contract revision 模式，按 Design Revision Closure 先通过 `validate-design-revision` 只读 preflight、再请求用户明确 reapproval、最后在用户批准后以相同参数加 `--allow-approval` 调用一次 `approve-design-revision`。只有新的 normalized `approved_task_contract`、exact `affected_tasks`、non-empty reason 与 approved control-plane 成功持久化后才能恢复。此处绝不允许 legacy `--unblock-tasks` context-only 模式。`files_hint`、manifest entry、JIT read、worker解释或 reviewer verdict 均不能补授 mutation ownership。

无法在证据 append 前唯一确定候选 owner 或修订字段时 STOP 请求 Design 澄清，不得猜测。当前未声明mutation blocker formation不要求、也不得猜测尚未存在的revised contract exact affected closure、handoff或未来owner；这些只属于后续Design revision + helper preflight。未声明 mutation 即使已发生，也不因被读取、测试通过或 review clean 而合法化。

## Design Revision Closure

首次 Design approval 必须把 normalized contract 持久化为 `state.implementation.approved_task_contract`。Design reapproval 有且仅有两个互斥模式，判定 authority 是 old/new normalized Task contract identity，而不是 blocker 文案：

- **Contract revision mode**：任何 canonical Task contract 字段变化——`depends_on`、`acceptance`、`verification`、`context_refs`、`mutation_targets`、`ownership_handoffs` 或派生 `ownership_table/final_owner`——以及 dynamic undeclared mutation、completed Task invalidation，都必须走只读 preflight → 用户明确 reapproval → 单次 write transition 的固定顺序。禁止新增、删除或重命名 Task ID；old/new Task ID set 必须完全一致，否则 bytes unchanged 并要求关闭或另起 change。
- **Context-only legacy mode**：仅当 old/new normalized Task contract identity 精确相同、没有 dynamic undeclared mutation、没有 completed Task invalidation，且修改只涉及 approved control-plane/context bytes 时，才可按现有 approval semantics 使用 `approve-design-revision ... --unblock-tasks <complete-design-eligible-set> --allow-approval`。CLI 名称是 legacy compatibility，不代表所有 Design revision 的通用 action；不得混用 contract preflight 参数或把 legacy mode 伪装成 contract mode。

Contract revision mode 的顺序必须精确为：

1. Controller 完整写出并固定新的 Design artifacts、Plan、context manifests 与 approved control-plane map，先运行 `task-helper.py validate-change --change <change-dir>` 并通过；任何 artifact/manifest/helper validation 失败都 STOP，`gates.design` 保持 `pending`，不得请求 reapproval。
2. 调用只读 `state-helper.py validate-design-revision --task-contract <new-approved-task-contract> --affected-tasks <exact-json-array> --revision-reason <non-empty> --approved-control-plane <complete-map>`。该 preflight 只做 exact closure/candidate state validation，复用 approval 的 full validation 与 candidate serialization；它不得接受 `--allow-approval`，不得写 state，成功或失败都必须保持 state bytes 与 `gates.design=pending` 不变。
3. Preflight 成功后，Controller 向用户展示摘要并请求当前轮明确 reapproval。Preflight 输出的 required/declared affected set、contract identities 或 approved-control-plane identity 只是候选摘要，不构成 approval，不证明 evidence freshness，也不能授权后续写入；用户拒绝、犹豫或只要求继续修改时，不得调用 approval helper，不得写 state。
4. 只有用户当前轮明确批准该 contract revision 后，Controller 才用与 preflight **完全相同的参数值**（除新增 `--allow-approval` 外）调用一次 `state-helper.py approve-design-revision --task-contract <same-new-approved-task-contract> --affected-tasks <same-exact-json-array> --revision-reason <same-non-empty> --approved-control-plane <same-complete-map> --allow-approval` 执行 write transition。Approve 不消费或信任 preflight 缓存；它必须重新读取当前 state、重新运行同一 validation/closure/candidate construction，处理 TOCTOU。若 state、Gate、contract、blocked/current-pointer、snapshot refs、completed Tasks 或其他 guard 在 preflight 与 approve 之间漂移，approval fail closed、state bytes unchanged、Gate pending。Contract drift / approved contract identity mismatch 的 `next_allowed_transition` 必须完整描述：回Design contract revision并固定新artifacts/contract → exact四参数只读`validate-design-revision` preflight → preflight成功后STOP请求未来当前轮explicit reapproval → 获批后用相同四参数加`--allow-approval`执行一次`approve-design-revision` → approve成功后才返回Implement；不得把preflight成功当approval，也不得由Implement自批。

Preflight 失败必须 STOP，保持 Gate pending，不得请求用户批准、不得降级到 legacy mode、不得手工拼 patch。Helper 已强制模式互斥：contract preflight/approval 出现任一 contract 参数时，`--task-contract`、`--affected-tasks`、`--revision-reason` 必须一起提供，并拒绝同时出现 `--unblock-tasks`；legacy context-only approval 不接受 contract 参数。Controller 在调用前必须重算 old/new contract identity；identity 变化却选择 legacy mode，identity 不变却混用两套参数，或在 legacy context-only 分支调用 contract preflight，均 STOP 且不得调用 approval helper。

`affected_tasks` 的唯一算法 authority 是 helper 的 deterministic required closure：

1. 对 old/new contract 做完整 defensive canonical validation，包括 fields/types、排序、dependency graph、mutation paths、ownership rows、linear handoff topology、owner/final-owner references 与 control/VCS mutation target边界；任一 malformed input 在 serialization/write 前 fail closed。
2. 比较既有 Task 的 canonical dependency、acceptance、verification、context refs、mutation targets、handoffs，以及 ownership row/final owner。变化 Task、变化 dependency edge 的 old/new 端点、变化 handoff/ownership chain 的 old/new owners 与 edge endpoints 进入 direct affected。
3. 在 old 与 new dependency reverse graph 的 union 上加入所有 transitive dependents，按新 `plan_order` 输出 required closure。`plan_order` 自身、title、mutable status、`files_hint` 与 rollback 文案不触发 closure。
4. Caller 声明集合忽略输入顺序，但必须与 required closure 精确相等；duplicate、unknown、missing 或 extra ID 均返回 structured mismatch，state bytes unchanged。不得同时使用旧 `--unblock-tasks` 形成第二套集合 authority。

所有 validation 与候选 state construction 必须先在内存完成；`validate-design-revision` 在序列化验证候选 state 后丢弃候选并只输出摘要，`approve-design-revision --allow-approval` 重新 read/revalidate 后才进入一次现有 write boundary，不宣称 filesystem atomic rename。成功 approval transition 完整替换 `approved_control_plane` 与 `approved_task_contract`、写 `gates.design=approved`，并 append `implementation.design_revisions[]` audit（reason、declared/required set、old/new contract identity、invalidated current evidence）。Affected completed/blocked/pending Tasks 回到 `pending`/revalidation，从 `implementation.completed_tasks` 移除 affected completed IDs，清除当前有效 fingerprint/review-clean markers；attempts、cycles、reports、旧 fingerprints 与 append-only snapshots 保留为历史但不满足新版 completion。Unaffected completed Tasks 保持有效；affected `in_progress` Task fail closed，不能静默中断。

## Canonical State Protocol

Canonical `state.json` 至少支持以下字段；允许扩展，但不得删除未知字段：

```json
{
  "phase": "implement",
  "status": "in_progress",
  "current_task": {
    "id": "T1",
    "attempt": 1,
    "status": "in_progress"
  },
  "gates": {
    "brief": "approved",
    "design": "approved",
    "verify": "pending",
    "fold": "pending"
  },
  "tasks": {
    "T1": {
      "status": "in_progress",
      "attempts": 1,
      "fix_cycle": 0,
      "review_cycle": 0,
      "manual_repair_authorization": null,
      "design_revision_authorization": null,
      "task_scope_fingerprint": "sha256:<task-scope-snapshot>",
      "completion_snapshot_refs": [
        {"evidence_path":"evidence/tasks/T1/snapshots/completion-T1-<path-id>-a1-r1.json","record_hash":"sha256:<record-hash>","path":"src/example.ts","path_id":"<64-lowercase-hex>"}
      ],
      "dependency_handoff_snapshot_refs": [],
      "live_snapshot_refs": [
        {"evidence_path":"evidence/tasks/T1/snapshots/live-T1-<path-id>-a1-r1.json","record_hash":"sha256:<record-hash>","path":"src/example.ts","path_id":"<64-lowercase-hex>"}
      ]
    }
  },
  "implementation": {
    "base_sha": "<git-sha>",
    "head_sha": "<git-sha>",
    "completed_tasks": [],
    "changed_files": [],
    "product_fingerprint": "sha256:<global-product-fingerprint>",
    "started_clean": true,
    "preexisting_paths": [],
    "preexisting_fingerprints": {
      "path/to/preexisting-file": {
        "status": "<git-status>",
        "content_hash": "sha256:<content-hash>"
      }
    },
    "approved_control_plane": {
      ".dev-docs/changes/<change-id>/design.md": "sha256:<content-hash>"
    },
    "approved_task_contract": {
      "plan_order": [],
      "tasks": [],
      "ownership_table": []
    }
  },
  "evidence": {
    "verify_review": null,
    "fold_proposal": null
  },
  "evidence_snapshots": {
    "verify_review": {
      "path": "evidence/review.md",
      "sha256": "sha256:<review-file-hash>",
      "base_sha": "<git-sha>",
      "head_sha": "<git-sha>",
      "global_product_fingerprint": "sha256:<global-product-fingerprint>",
      "changed_files_fingerprint": "sha256:<changed-files-fingerprint>"
    },
    "fold_proposal": {
      "status": "ready",
      "path": "evidence/fold-proposal.md",
      "sha256": "sha256:<proposal-file-hash>",
      "verify_review_sha256": "sha256:<review-file-hash>",
      "base_sha": "<git-sha>",
      "head_sha": "<git-sha>",
      "global_product_fingerprint": "sha256:<global-product-fingerprint>",
      "changed_files_fingerprint": "sha256:<changed-files-fingerprint>"
    }
  },
  "fold_apply": {
    "proposal_hash": null,
    "status": null,
    "targets_before": {},
    "targets_after": {},
    "error_evidence": null
  },
  "active": true,
  "artifacts": {
    "brief": "brief.md",
    "spec": "spec.md",
    "design": "design.md",
    "plan": "plan.yaml",
    "implement_context": "context/implement.jsonl",
    "verify_context": "context/verify.jsonl"
  }
}
```

字段合同：

- `tasks`：按 Task id 保存 mutable `status`、`attempts`、`fix_cycle`、`review_cycle` 与最近一次成功 Task complete 的 `task_scope_fingerprint`；Task 定义仍来自 `plan.yaml`。Canonical Task status allowlist 只有 `pending`、`in_progress`、`completed`、`blocked`。任何 `state.tasks.<id>` 缺失 object shape、缺失 string `status`、`status=null|array|object` 或未知字符串，均不是可恢复状态，Controller/helper 必须在写入前 fail closed，不得把它当作 non-blocked Task 跳过。新写入的 canonical blocked Task 必须使用 structured `blocker` object：`kind` 仅允许 `design_revision` 或 `resolved_evidence`，`code` 与 `reason` 必须为 non-empty string，`evidence` 必须为 non-empty safe project-relative path，`blocker_occurrence` 必须为该 evidence 文件内对应 BLOCKED occurrence 的 positive integer，`blocker_record_id` 必须为该 BLOCKED record 的 canonical `sha256:<hex>` ID。Legacy `blocker=null|string|array`、缺失/未知 `kind`、空或非 string `code/reason/evidence/blocker_record_id`、缺失或非 positive integer `blocker_occurrence`、ASCII control chars（含 embedded NUL）、absolute path、Windows absolute/UNC、URI、tilde、`.`/`..` traversal、empty segment、trailing separator、顶层 Task `reason` 缺失/非 non-empty string 或不等于 `blocker.reason`，均不是可恢复的 blocked state；Controller 和 Design reapproval helper 都必须对 state 内所有 blocked Tasks fail closed。Blocker object 可保留未知 extra fields，但 extra fields 不得替代必填 canonical identity 字段；不得从旧自由文本 `reason`、evidence 内容或其他 legacy 字段推断 blocker kind、occurrence 或 record id。
- `current_task`：只能为 `null` 或 exact canonical pointer object；object 的 key set 必须精确等于 `{id,attempt,status}`，不得缺字段或包含额外字段。
- `current_task.attempt` 与 `tasks.<id>.attempts` 的关系：`current_task` 只保存当前正在处理或刚 blocked 的 Task 指针，使用 singular `attempt` 表示该 Task 当前 dispatch attempt 编号；`tasks.<id>.attempts` 是同一编号的持久 Task-local counter。二者不是两套语义；当 `current_task.id == <id>` 时二者必须相等。不存在第三种 `attempt` 字段。
- `tasks.<id>.attempts`：canonical non-negative integer，bool、negative、float、string 或 missing 均不是可恢复 attempts 值。无 cycle/尚未 dispatch 表示为 `0`。首次 dispatch 从 `0` 递增到 `1`，Task redispatch、Verify fix invalidation 后的下一次 dispatch、以及 blocked→pending 后的下一次 dispatch 均递增；pre-dispatch blocked、blocked→pending 自身、普通 resume 与 Design reapproval 不递增。
- `tasks.<id>.fix_cycle`：canonical non-negative integer。无 fixer cycle 表示为 `0`。每个 attempt 开始时初始化/重置为 `0`；同一 attempt 内每轮 fixer dispatch 前递增为 `1..N`，并且该值必须在 post-fix final validation 开始前已成功持久化。Task redispatch/新 attempt 重新从 `0` 开始；blocked→pending、普通 resume 与 Design reapproval 保留当前值直到下一次 dispatch 重置。
- `tasks.<id>.review_cycle`：canonical non-negative integer。无 reviewer cycle 表示为 `0`。每轮 review cycle 的开始边界必须在该轮 authoritative final validation 生成之前，而不是 reviewer dispatch 时：fresh path 在 implementer 完成产品修改后、开始 final validation 前从 `0` 递增到 `1`；fix path 在 fixer 完成产品修改后、开始 post-fix final validation 前递增到下一值。对应 state merge 成功后，final validation、fresh reviewer/re-review、Task completion 使用同一 persisted `attempt/fix_cycle/review_cycle` tuple。Task redispatch/新 attempt 重新从 `0` 开始；blocked→pending、普通 resume 与 Design reapproval 保留当前值直到下一次 dispatch 重置。
- `tasks.<id>.manual_repair_authorization`：manual-escalation repair-attempt transition 的窄身份字段，只允许为 `null` 或 canonical `authorization_record_id=sha256:<hex>`。普通 Task dispatch、Design revision/reapproval、blocked→pending recovery、Verify fix redispatch 等路径不得写非 null；manual-escalation repair-attempt merge 成功时必须写入所应用 authorization record 的 ID。它记录最近一次 attempt 是否由 fixed authorization record 派生；不能替代 validation/review freshness，也不能单独授权再次 repair。该 ID 在该 new attempt 的后续 validation/review/fix cycles 及 Task completion 中 preserve 作为 audit；每次普通 Task dispatch、Verify fix invalidation 后的下一次 dispatch、blocked→pending recovery、blocked→pending 后的下一次 dispatch、或 Design/Plan/acceptance/scope revision 创建的新 attempt/返回 pending 时，必须清为 `null`；普通 resume 保留并核验；旧 completed/history evidence 仍 append-only 保留。未知 extra fields 继续 preserve，但不得替代此 canonical field。
- `tasks.<id>.design_revision_authorization`：manual-escalation Design-revision transition 的窄身份字段，只允许为 `null` 或 canonical `design_revision_record_id=sha256:<hex>`。它仅记录某个 active manual escalation Task 已按固定 `MANUAL_ESCALATION_DESIGN_REVISION` record 分流到 Design draft/pending；不得替代 Design Gate approval、Plan/context 变更审查、validation/review freshness 或 Task dispatch authority。该字段与 `manual_repair_authorization` 互斥：同一 Task 上二者不得同时为 non-null，任何 status 都不例外；repair-attempt exact transition 不得写 `design_revision_authorization`，Design-revision exact transition 必须清 `manual_repair_authorization` 并写入 applied Design record ID。Controller/helper 遍历 Tasks 时只要发现两个 authorization 字段同时 non-null，必须 structured fail closed 且保持 state bytes unchanged。成功 Design reapproval helper 必须对所有恢复的 Design-eligible Tasks 清为 `null`；未恢复的 resolved/other/completed Tasks 只能保留其中一个 authorization 字段作审计，若两个字段同时存在则不是可恢复状态。下一次普通 Task dispatch 才递增 attempt 并重置 cycles，且同时保持/清理规则按 Task dispatch 执行。
- `tasks.<id>.task_scope_fingerprint`：canonical input 是固定 JSON object：`task_id`、state 中的 `attempt/fix_cycle/review_cycle`、最终 `task_brief_sha256`、按 approved path 排序的 `completion_snapshot_refs`、按 approved edge 排序的 `dependency_handoff_snapshot_refs`、按 approved path 排序的 `live_snapshot_refs`（只有 current/final owner 的对应 path 有 current 项）和直接 dependency/output fingerprints。每个 ref 必须以 `evidence_path/record_hash/path/path_id` 精确指向上节 per-path canonical record；dependency ref 另含 exact `incoming_edge`。`own_mutations` 的内容身份来自对应 record 的 `path_hash`，不得另从最终 live bytes重算历史 owner map。Controller读取state/records后用固定key顺序、无无意义空白的UTF-8 canonical JSON计算SHA-256；worker/reviewer不得计算authoritative fingerprint，也不得从evidence文本推断cycle或字段。非handoff owner的completion/live refs必须共同匹配当前bytes；handoff历史owner只要求append-only completion、incoming lineage与acceptance-preservation fresh，最终live freshness由final owner refs承担。Cycle/brief/dependency或所引用snapshot identity drift才使当前值失效；合法downstream mutation不废弃历史owner cycle，后续无关Task mutation也不使其自然过期。
- `implementation.base_sha`：Implement 首次进入、任何 Task mutation 之前的 HEAD。
- `implementation.head_sha`：最近一次已审查状态合并时观察到的 HEAD；未产生 commit 时可与 `base_sha` 相同。
- `implementation.completed_tasks`：按完成顺序保存 Task id，不重复。
- `implementation.changed_files`：相对仓库根目录、去重后的本 change 已观察变更路径；每次 Task blocked/complete 和 Implement complete 都必须从 worker reports 与 Git reconciliation 更新，Git diff 是 Verify 的真实范围。
- `implementation.product_fingerprint`：最近一次成功持久化的 change-wide reviewed snapshot，即 `global_product_fingerprint`。它是完整 reconciled workflow product scope 的 canonical SHA-256，不能用 HEAD 或 path 集合代替。Implement complete 写入初始值；Verify review ready 用当前完整 Verify 绑定值更新；普通 Task dispatch/complete 不更新。Verify fix 或任何 product drift 后旧值不得用于 approval，只有新的完整 Verify review ready 才能更新。Snapshot 规范见 Dirty Worktree Protocol。
- `implementation.started_clean`：pre-flight 时 worktree 是否干净。
- `implementation.preexisting_paths`：仅在当前轮 explicit authorization 下保留的、不与 change scope 重叠的既有 dirty product/other paths。
- `implementation.preexisting_fingerprints`：每个 preexisting path 在首次 Implement entry 观察到的 Git status + content hash（删除路径使用明确 deleted/missing marker）；每个 Task/Verify/Fold mutation 边界必须复核，任何变化立即 STOP。
- `implementation.approved_control_plane`：immutable approved control-plane（approved brief/spec/design/plan/manifests 等）path → SHA-256 content hash map；这些路径从 product diff/Verify scope 排除，只有重新 Design approval 才可更新 hash。
- `implementation.approved_task_contract`：首次或最近一次 explicit Design approval 固定的 normalized `task_contract`，包含 canonical `plan_order/tasks/ownership_table`。它是 dispatch、ownership、handoff 与 Design revision old-contract 输入；不得从当前 Plan prose、`files_hint`、context manifest 或 worker report重建替代。
- Workflow-owned mutable control-plane 不另混入 `changed_files`：current-change `state.json`、固定 `evidence/tasks/`、`evidence/review.md`、`evidence/fold-proposal.md`、fold apply evidence，以及仅 Fold Close 可改的 `.dev-docs/changes/index.md` current-change entry，可按固定路径、shape 和合法 transition 变化。
- `evidence.verify_review`：`evidence/review.md` 或 `null`。
- `evidence.fold_proposal`：`evidence/fold-proposal.md` 或 `null`。
- `evidence_snapshots.verify_review`：Verify review 的外部 immutable metadata，至少保存 path、普通 file SHA-256、base SHA、HEAD、global product fingerprint 与 changed-files fingerprint。
- `evidence_snapshots.fold_proposal`：Fold proposal 的外部 immutable metadata，至少保存 `status=ready|superseded`、path、普通 file SHA-256、所依据的 Verify review SHA-256、base SHA、HEAD、global product fingerprint 与 changed-files fingerprint。`ready` 表示可能成为当前候选但仍须 freshness check；`superseded` 是永久不可操作的历史候选。
- Artifact hash 顺序固定为：先完整写 artifact，再对最终文件 bytes 计算普通 SHA-256，最后通过同一个 ready state transition 把 hash 与 snapshot fields 持久化到对应 `evidence_snapshots`。Artifact 可记录其依据的 product fingerprint 或 Verify review identity，但不得内嵌、占位、回填或自指其自身 file hash；修改 artifact 后必须重新计算并完整替换外部 metadata。
- `fold_apply`：用户批准后的 two-phase apply journal；保存 proposal hash、pending/blocked/applied status、targets before/after hashes 与失败 evidence。
- `active`：change 是否仍是 active change；关闭时必须为 `false`。

## Generic State Transition Rules

以下通用规则仍是 Brief、Design，以及任何未被后续 exact transition 覆盖 stage 的 authority。后半段 Implement/Verify/Fold exact transitions 只能在更具体处补充或细化这些规则，不能替代原有 Stage entry、Gate pending、Gate approval、Failure/blocker authority。Brief/Design references 对本节规则的引用继续有效。

1. **Stage entry** — 一旦 skill 已定位 current change 且即将执行该 stage，合并：
   - `phase=<stage>`
   - `status=in_progress`
   - preserve existing `gates`、`artifacts`、`current_task`、metadata、evidence 和 unknown keys。
2. **Gate pending** — stage 写出 reviewable artifacts 后、用户批准前，合并：
   - `phase=<stage>`
   - `status=draft`
   - `gates.<stage>=pending`
   - 该 stage 产物的 artifact/evidence path references。
3. **Gate approval** — 只有用户当前轮明确确认该 gate，才可用 approval-enabled merge 写：
   - `gates.<stage>=approved`
   - 若同轮不进入下一 stage，可写 `status=approved`。
   - 若同轮立即进入下一 stage，下一 stage entry 可设置新的 `phase` 与 `status=in_progress`。
   - 只有用户当前轮对 **Design Gate 的 explicit approval** 才能用于进入 Implement；Implement stage entry patch 必须同时通过 `merge-state --allow-approval` 持久写入 `gates.design=approved`，merge 成功后才可 dispatch。用户只允许查看/继续完善 provisional Design 时不构成 Gate approval，不得进入 Implement、不得写 approved。不得留下 `phase=implement` 与 `gates.design=pending` 的组合，也不得宣称该 direct write 具有 filesystem atomicity。
4. **Failure/blocker authority** — 缺少 required artifacts、manifests、validation evidence、context、approval 或存在明确 blocker 时，只有具备具体 blocker evidence 才合并 `status=blocked`；否则 STOP 并请求澄清，不得发明状态。Task-local blocker 的 change-level `status` 还必须遵守后文 Task blocked 条件，不得因单一 Task blocked 就阻止独立 eligible Tasks。

## Implement/Verify/Fold Exact State Transitions

以下 transitions 是 Implement、Verify、Fold 后半段生命周期的更具体 authority。它们继承上方通用规则；当本节有更精确字段要求时，以本节为准。所有写入均使用 preserve/merge，不得用近似状态代替。

### Implement entry

通过 Design Gate、helper validation 与 dirty-worktree pre-flight 后，在任何 product mutation 之前合并。只有持久 approved 或当前轮 explicit Design Gate approval 可进入；provisional continuation 不能进入 Implement。若依赖当前轮 explicit approval，必须在这次 stage entry 使用 `merge-state --allow-approval` 同步持久写入 `gates.design=approved`；merge 失败不得 dispatch，且不得留下 `phase=implement` 与 pending Design Gate 的不一致组合。`implementation.base_sha` 只在 change **首次进入 Implement** 且该字段尚未初始化时写入；resume/re-entry 必须保留原值，绝不以当前 HEAD 覆盖。首次 entry 合并：

```text
phase=implement
status=in_progress
current_task=null
implementation.base_sha=<first Implement pre-flight HEAD>
implementation.head_sha=<pre-flight HEAD>
implementation.started_clean=<true|false>
implementation.preexisting_paths=<explicitly authorized disjoint product/other paths or []>
implementation.preexisting_fingerprints=<path to entry Git-status/content-hash map or {}>
implementation.approved_control_plane=<Design-approved immutable path to content-hash map or {}>
active=true
```

Resume/re-entry 仅写当前 transition 所需字段（例如 `phase/status/head_sha/current_task`），不重写 `base_sha`、既有 hashes 或无关 state。保留现有 `tasks`；首次执行时按 Plan Task Status Migration 初始化。

### Task blocker evidence records

Task-local blocked/unblock 只使用 `evidence/tasks/<task-id>/` 下既有固定四个 Markdown 文件；`snapshots/` 只承载上文 canonical snapshot records，不能承载 BLOCKED/RESOLVED。不得新增第五个 Markdown Task evidence 文件、helper/runtime/journal 或第二状态 authority。Canonical `blocker.evidence` 必须精确指向承载 BLOCKED/RESOLVED append records 的同一个 project-relative evidence 文件；`state.json` 只保存该文件路径和 structured blocker，不复制 record 正文。

触发源到 evidence 文件的唯一映射如下；BLOCKED record 与后续 RESOLVED record 必须追加到同一文件：

| Trigger source | BLOCKED/RESOLVED record file | Notes |
|---|---|---|
| Pre-dispatch required context/target 缺失、不可读，且仅影响单 Task | `evidence/tasks/<task-id>/implementer.md` | 尚未产生 worker attempt；不得写 Attempt N。 |
| Worker/implementer 返回 `NEEDS_CONTEXT` 或 `BLOCKED` | `evidence/tasks/<task-id>/implementer.md` | Worker observed facts 写入 implementer evidence。 |
| Validation 命令无法执行、缺失 required validation evidence、validation infrastructure blocker | `evidence/tasks/<task-id>/validation.md` | Validation 结果与 blocker summary 同源。 |
| Reviewer dispatch/re-review infrastructure blocker | `evidence/tasks/<task-id>/validation.md` | Reviewer 详细 verdict 仍写 `review.md`；canonical blocker recovery record 写 `validation.md`，避免第三种 recovery authority。普通产品 correctness/quality findings 耗尽修复预算不使用此 blocker path。 |

BLOCKED record 必须在任何 blocked state merge 前成功 append；append 失败即 STOP，不得写 `state.json`。每条 BLOCKED occurrence 的 canonical `blocker_occurrence` 是同一 Task evidence 文件内按 append 顺序计数的第 N 条 `record_type=BLOCKED`，从 `1` 开始、严格递增；计数范围只限该具体文件（例如同一 Task 的 `implementer.md` 与 `validation.md` 各自独立计数），不得使用时间戳、随机数、hash 截断、对话轮次或 wall-clock 作为 occurrence。追加前 Controller 必须扫描该文件已有 BLOCKED records 计算下一个 positive integer；若此前 BLOCKED append 已成功但 state merge 失败，后续 resume/retry 必须复用该已存在 occurrence，禁止为同一 observed blocker 再 append 一个新 occurrence。

每条 BLOCKED record 至少包含以下字段：`record_type=BLOCKED`、`task_id`、`attempt`、`fix_cycle`、`review_cycle`、`kind`、`code`、`reason`、`evidence_path`、`blocker_occurrence`、`blocker_record_id`、`observed_facts`、`trigger_source`。其 canonical identity 是固定 key 顺序 JSON `{task_id,attempt,fix_cycle,review_cycle,kind,code,evidence_path,blocker_occurrence}` 的 SHA-256，记为 `blocker_record_id=sha256:<hex>` 并写入 record；`reason` 和 observed facts 是必填审计字段，但不得替代 identity。随后 state patch 中的 `tasks.<id>.blocker={kind,code,evidence:<same evidence_path>,reason,blocker_occurrence:<same positive integer>,blocker_record_id:<same id>}`、`tasks.<id>.reason=<same reason>` 必须与该 BLOCKED record 精确一致。Controller 不得先写 state 再补 evidence，也不得让 `blocker.evidence` 指向目录、其他 Task、raw log、reviewer history、session journal 或不存在的第五文件。

Blocker kind 必须按下表确定；无法唯一分类时 STOP，不 append、不写 state、不猜测：

| Cause class | `kind` | Examples | Recovery authority |
|---|---|---|---|
| 必须修改或重新批准 Design、Plan、context manifest、required context/target 声明或内容后才能继续 | `design_revision` | pre-dispatch required context/target 缺失且需要补充 approved control-plane；worker `NEEDS_CONTEXT` 指向 Plan/context 不足；immutable approved control-plane drift | explicit Design Gate reapproval；contract identity 变化时先 `validate-design-revision` 只读 preflight，再用户明确 reapproval，最后同参数 `approve-design-revision --allow-approval` exact transition；legacy context-only 仅限 identity 不变 |
| 可由新证据证明已恢复的权限、环境、外部依赖、validation infrastructure 或 reviewer infrastructure 临时问题 | `resolved_evidence` | 权限授予、环境变量/工具安装恢复、外部服务可用、validation/reviewer infrastructure 恢复 | 同一 evidence 文件中的 matching RESOLVED record + resolved-evidence exact recovery |

RESOLVED record 只有在 state 已成功引用 `kind=resolved_evidence` blocker 时才具有 blocked→pending recovery 权限；若用于下方 pending evidence reconciliation，它只是关闭“evidence 已 append 但 state 从未 blocked”的 audit record，不执行 state recovery。RESOLVED 必须追加在同一个 `blocker.evidence` 文件中且位于被恢复/关闭的 BLOCKED occurrence 之后。每条 RESOLVED record 至少包含：`record_type=RESOLVED`、`resolved_for.blocker_record_id`、完整 `resolved_for` identity fields（`task_id/attempt/fix_cycle/review_cycle/kind/code/evidence_path/blocker_occurrence`）、`resolution_facts`。选择 record 时必须使用 latest applicable 规则：先在该文件中找到最新一条 identity 精确匹配当前 canonical Task cycle、当前 state blocker 与 `blocker_record_id` 的 BLOCKED occurrence；只考虑其后续追加且 `resolved_for` 完整引用同一 `blocker_record_id` 与完整 identity 的 RESOLVED records；若多条匹配，选择最后一条；位于最新匹配 BLOCKED 之前、引用旧 occurrence、旧 cycle、旧 code、旧 evidence path、旧 reason、其他 Task、或仅自由文本声明“已解决”的 RESOLVED 均为 stale/mismatch，必须拒绝。文件内允许多个 append records；旧 occurrence 的延迟 RESOLVED 即便排在新 BLOCKED occurrence 之后，也只能引用旧 `blocker_occurrence/blocker_record_id`，永远不得恢复新的 blocker。

### Pending BLOCKED evidence reconciliation before dispatch/resume

每次 resume/re-entry、以及任何可能 dispatch Task 的 pre-dispatch 检查之前，Controller 必须先按当前 state 中每个 candidate/current Task 的 canonical tuple `{task_id,attempts,fix_cycle,review_cycle}` 扫描该 Task 的固定 `implementer.md` 与 `validation.md`。若发现某文件中存在 latest unmatched BLOCKED occurrence（没有后续 matching RESOLVED，且当前 state 未以 `status=blocked` + matching `blocker.evidence/blocker_occurrence/blocker_record_id/kind/code/reason` 引用它），说明上轮可能已成功 append evidence 但 blocked state merge 失败；此时必须在任何 dispatch 前完成 reconciliation。

Reconciliation exact rule：

1. 若 state 已引用某 BLOCKED occurrence，则必须验证该 evidence file 中存在 matching BLOCKED record，且 state blocker 的 `kind/code/evidence/reason/blocker_occurrence/blocker_record_id` 与 record 完全一致；record 缺失、ID mismatch、occurrence mismatch 或 reason mismatch 均 fail closed，STOP，不得 dispatch。
2. 若存在 latest unmatched BLOCKED occurrence，则重新验证该 occurrence 的 `observed_facts/trigger_source` 对应的实际 blocker 是否仍存在。
   - 仍存在：不得重复 append BLOCKED；必须重试持久化同一 canonical blocked state，使用原 `blocker_occurrence` 与 `blocker_record_id`。只有该 blocked state merge 成功后，才允许继续选择其他独立 eligible Task；该 Task 本身不得 dispatch。
   - 已解除：在同一 evidence 文件追加 matching RESOLVED audit record，`resolved_for` 完整引用原 occurrence identity 与 `blocker_record_id`；该 record 只关闭悬空 evidence，不代表 resolved-evidence recovery。因为 state 从未成功进入 blocked，不得执行 blocked→pending recovery，也不得清理 Task blocker。保持原 state，然后重新运行全部 pre-dispatch checks；若 checks 通过才可按正常 Task dispatch 递增 attempt。
   - 无法确定是否仍存在、无法验证 trigger、或无法安全 append RESOLVED：STOP，不得写 state、不得 dispatch。
3. 若同一 candidate tuple 在多个固定 evidence 文件都有 unmatched BLOCKED occurrence，或最新 occurrence 的 trigger 与当前 Task/state tuple 无法唯一对应，fail closed，STOP，要求人工检查 append-only evidence。

任何 Task dispatch 的前置条件包括：该 Task 当前 tuple 没有 unresolved/unreferenced BLOCKED occurrence，若 state 为 blocked 则必须已成功引用 matching record；state 成功 blocked 前不得 dispatch。该 reconciliation 不引入第五文件、runtime helper 或 journal，只把固定 Task evidence 与 `state.json` 重新对齐。

### Pre-dispatch Task-local blocked

选择 eligible Task、重提取 brief 并计算 brief hash 后，若仅该 Task matching required target 缺失/不可读，必须在 dispatch/attempt increment 前按 Task blocker evidence records 追加 `evidence/tasks/<task-id>/implementer.md` BLOCKED record。只有 append 成功且 kind 可确定，才可合并；该 transition 的分类通常为：required context/target 声明或内容必须补充/修正并重新批准时写 `kind=design_revision`；若只是临时权限、环境或外部依赖导致目标暂不可读且可由后续证据证明恢复时写 `kind=resolved_evidence`；无法分类 STOP。Blocked state patch 必须写 canonical blocker object 与相同顶层 Task reason：

```text
tasks.<task-id>.status=blocked
tasks.<task-id>.attempts=<unchanged current count; first undispatched task is 0>
tasks.<task-id>.blocker={kind:<design_revision|resolved_evidence>,code:<stable code>,evidence:evidence/tasks/<task-id>/implementer.md,reason:<same reason>,blocker_occurrence:<positive integer>,blocker_record_id:<sha256:...>}
tasks.<task-id>.reason=<same reason>
current_task={id:<task-id>,attempt:<same current count>,status:blocked}
phase=implement
status=<in_progress when an independent eligible Task remains; otherwise blocked>
```

这不是一次 worker attempt。不得写新的 Attempt N、不得递增计数；跳过该 Task 的 transitive dependents，继续独立 eligible Tasks。Shared/change-wide required target 缺失、manifest invalid、immutable hash drift 或 preexisting fingerprint drift 是 change-level STOP，不使用此 transition。Evidence append 失败、BLOCKED record 与 state blocker/reason 不一致、或 `blocker.evidence` 不指向上述固定文件时，不得写 state。

### Task dispatch

选择 dependency-eligible Task 且全部 pre-dispatch checks 通过后，先将 attempt 设为前次 attempt + 1（首次为 1），再用一次 helper merge 同步合并：

```text
current_task={id:<task-id>,attempt:<n>,status:in_progress}
tasks.<task-id>.status=in_progress
tasks.<task-id>.attempts=<n>
tasks.<task-id>.fix_cycle=0
tasks.<task-id>.review_cycle=0
tasks.<task-id>.manual_repair_authorization=null
tasks.<task-id>.design_revision_authorization=null
phase=implement
status=in_progress
```

只有 helper 成功持久化这个 transition 后才可 dispatch implementer；helper 失败即 STOP。`state-helper.py` 是 recursive merge + direct write，不宣称 filesystem atomic write。

### Fix and review cycle updates

同一 attempt 内，cycle state 只由 Controller 在对应边界显式更新，不能从 evidence 文本倒推。每轮 review cycle 的开始边界是“该轮 authoritative final validation 开始前”，不是 reviewer/re-review dispatch；cycle identity 必须先成功持久化到 `state.json`。任何 cycle update merge 失败都必须 STOP，不得生成该 cycle 的 authoritative validation 或 review evidence。

- Fresh path：implementer 完成产品修改后、开始该轮 final validation 前，合并 `tasks.<task-id>.review_cycle=1`，`fix_cycle` 保持 `0`。只有 helper 成功持久化后，才运行并追加绑定 tuple `(attempt=<current>,fix_cycle=0,review_cycle=1)` 的完整 final validation；随后 fresh reviewer dispatch 读取同一 persisted tuple，不再递增 `review_cycle`。
- Product validation failure path：当 authoritative validation 命令本身已成功启动并运行到可判定结果，但产品 assertion、acceptance 或 expected-output 不通过时，该失败属于普通产品修复输入，进入本节唯一 bounded fixer/re-review budget；不得立即 STOP、不得创建 Task-local blocker、不得追加 BLOCKED record。若这是 implementer 初始 cycle 的 validation failure，可能尚无 reviewer finding；Controller 必须把 `validation.md` 中的失败命令、退出码、关键输出、expected-vs-actual 与 task acceptance summary 作为 fixer input/evidence，并结合 task brief、implementer/fixer report、当前 diff/scope 以及已有 reviewer findings（若有）。该路径仍必须在每轮 fixer 后生成新的 authoritative final validation，并 dispatch fresh reviewer/re-review；不能因为 validation 已经提供失败证据就跳过 reviewer。
- Fix budget counting：同一 attempt 的“最多 2 轮”按现有 `tasks.<task-id>.fix_cycle` 计数，避免 off-by-one：`fix_cycle=0` 表示尚未 dispatch fixer；每次产品 fixer dispatch 前先把 `fix_cycle` 递增为 `1` 或 `2`；当当前 persisted `fix_cycle < 2` 且仍有普通产品 validation failure 或 reviewer Critical/Important finding 时，必须进入下一轮 fixer/re-review；当 `fix_cycle == 2` 且该第二轮 post-fix authoritative validation + fresh re-review 后仍有普通产品 failure/finding 时，预算才耗尽并进入 manual escalation。Task redispatch/new attempt 按 Task dispatch 重置为 `0`。
- Fix path：进入 fixer cycle 时，在 fixer dispatch 前先合并 `tasks.<task-id>.fix_cycle=<previous+1>`；helper 失败即 STOP，不得 dispatch fixer。fixer 完成产品修改后、开始 post-fix final validation 前，合并 `tasks.<task-id>.review_cycle=<previous+1>`；helper 成功后，post-fix final validation、fresh re-review 和 Task completion 都使用同一 persisted `(attempt,fix_cycle,review_cycle)` tuple。re-review dispatch 不再递增 `review_cycle`。
- Infrastructure failure path：validation 命令无法启动、缺少工具/权限/环境变量、外部依赖不可用、超出环境许可而无法取得 authoritative result，或 reviewer/validation infrastructure 无法执行时，不是产品 failure，不进入上述产品 fix budget，也不得递增 `fix_cycle`。Controller 必须按 Task blocker evidence records 追加对应 fixed evidence file 的 BLOCKED record，并在可分类时使用 `kind=resolved_evidence` 的 canonical Task blocked 路径；无法分类则 STOP。
- 中间开发测试、局部 smoke test、fixer 自查或 cycle identity 持久化前的命令输出不构成 authoritative final validation evidence；它们可记录在 implementer/fixer evidence 中作审计，但不能满足 Task completion、Implement complete、Verify fix 或 resume freshness。
- Reviewer PASS 后用于 Task complete 的 fingerprint 必须读取当前 state 中的 `attempts/fix_cycle/review_cycle`，并精确匹配最新 authoritative validation 与 review evidence 的 cycle identity。缺少同 tuple 的完整 final validation 或 reviewer PASS 时不得完成。
- Verify fix invalidation 将 affected completed Tasks 退回 `pending` 并移出 `implementation.completed_tasks` 时，保留旧 `attempts/fix_cycle/review_cycle/task_scope_fingerprint` 仅作审计；旧 cycle 不再满足 completion。下一次 Task dispatch 按 Task dispatch 规则递增 `attempts` 并重置 `fix_cycle/review_cycle=0`。
- Task redispatch/new attempt、blocked→pending、普通 resume 与 Design reapproval 不会把旧 evidence 重新变为当前 evidence。Resume 只读取并比较这些字段；不得初始化为新值、递增、或从 evidence headings 推断缺失字段。缺失 cycle 字段的 legacy state 在首次安全初始化时只能使用 canonical no-cycle 值 `0`，并且必须在任何 completion/freshness 判断前写入或 STOP。

### Manual escalation after product fix budget exhaustion

只有同一 attempt 内产品修复预算已按 `fix_cycle` 完整耗尽后，才允许进入 manual escalation：初始 authoritative validation 产品 failure 或 reviewer Critical/Important 不直接升级；`fix_cycle < 2` 时的普通产品 correctness/quality/acceptance failure 必须继续走 Fix and review cycle updates；`fix_cycle == 2` 的第二轮 post-fix authoritative validation + fresh re-review 后，若 validation 命令已成功执行但产品 assertion/acceptance 仍失败，或 reviewer/re-review 仍保留普通产品 correctness/quality 的 Critical/Important findings，才表示当前 approved scope 下自动修复预算耗尽，需要 change-level manual escalation。该“最多 2 轮”与 `fix_cycle=1..2` 一一对应；`fix_cycle=0` 不计为已用 fixer 轮次。

Manual escalation 不得创建 Task-local canonical blocker，不得追加 BLOCKED record，也不得把该 Task 写为 `status=blocked`。这类情况不是权限、环境、外部依赖或 reviewer/validation infrastructure blocker；相反，validation/reviewer infrastructure 无法执行必须走 `resolved_evidence` Task blocker 且不消耗产品 `fix_cycle`。

Manual escalation 必须保留 Task 为可恢复的 active work：Task `status` 保持 `in_progress`，`current_task` 保持 exact `{id:<task-id>,attempt:<n>,status:in_progress}` pointer，change-level `phase=implement,status=blocked` 表示 orchestration STOP，并可写 concise top-level `reason` 指向第二轮 post-fix validation/review evidence。不得写 `tasks.<id>.blocker`，不得触发 dependent Task 的 canonical blocked 传播，也不得把独立 Task 继续 dispatch，因为当前 change-level STOP 正等待用户选择。

恢复只能来自当前轮 explicit user decision。用户若选择修改 Design、Plan、acceptance、scope 或 context 声明/内容，不创建 repair attempt，必须转入对应 Design revision/Gate 路径；若重新分析发现根因其实是 Design/Plan/context 必须变化，同样转 Design revision，不得把普通产品 finding 耗尽预算本身伪装成 `resolved_evidence` 或 Task-local blocked。用户若明确授权“额外 bounded repair attempt”，必须走下方唯一 manual-escalation repair-attempt transition；不得写 `fix_cycle=3`，不得在同一 attempt 内把 `fix_cycle/review_cycle` 重置为 0 后继续，也不得先执行本 transition 再执行 canonical Task dispatch 导致 attempt 递增两次。

#### Manual-escalation Design-revision choice record

Design/Plan/acceptance/scope/context 修改选择的授权 record 只允许追加到固定文件 `evidence/tasks/<task-id>/implementer.md`，不新增 evidence 文件、runtime、journal 或第二状态 authority。仅自由文本、聊天记录、top-level `reason`、review 摘要或 repair authorization record 都不能授权进入 Design revision；record append 成功后才允许尝试 state merge，append 失败即 STOP。该 record 的 `record_type` 必须为 `MANUAL_ESCALATION_DESIGN_REVISION`，并且至少包含以下字段：

- `task_id`。
- `previous_attempt`、`previous_fix_cycle`、`previous_review_cycle`：必须等于当前 state tuple，且 previous tuple 必须为已耗尽预算的 `fix_cycle=2`。
- `evidence_path`：固定为同一 Task 的 `evidence/tasks/<task-id>/implementer.md`。
- `validation_evidence`：latest authoritative validation 的固定文件 path、同一 `validation.md` 内 occurrence/heading 或等价稳定位置、ordinary file `sha256:<hex>`、完整 cycle identity `{task_id,attempt,fix_cycle,review_cycle,task_brief_sha256,task_scope_fingerprint}`、以及 outcome（只允许 `PASS` 或 `PRODUCT_FAILURE`）。Reviewer-only escalation 时 validation outcome 可以是 `PASS`，但 validation record 仍必须存在、fresh、authoritative 且绑定同一 exhausted tuple；validation infrastructure 无法取得 authoritative result 时不能使用此路径。
- `review_evidence`：latest fresh review/re-review 的固定文件 path、同一 `review.md` 内 occurrence/heading 或等价稳定位置、ordinary file `sha256:<hex>`、完整 cycle identity `{task_id,attempt,fix_cycle,review_cycle,task_brief_sha256,task_scope_fingerprint}`、以及 outcome（至少区分 `PASS` 与 `CRITICAL_OR_IMPORTANT`）。
- `escalation_authority`：必须为 `validation_product_failure`、`review_critical_or_important`，或二者组成且顺序固定为 `["validation_product_failure","review_critical_or_important"]` 的双值数组；至少一个成立，且与 validation/review outcomes 精确一致。
- `task_brief_sha256`：当前 `task-brief.md` bytes 的 hash；必须与 validation/review evidence 绑定的 brief hash 一致。
- `current_task_scope_fingerprint`：当前 exhausted attempt 的 Task scope fingerprint。
- `user_choice_summary`：当前轮用户明确选择修改 Design、Plan、acceptance、scope 或 context 的简明摘要；不能包含额外 bounded repair attempt 授权。
- `user_choice_summary_sha256`：对规范化用户选择摘要 bytes 计算的 SHA-256。规范化规则与 repair authorization 摘要相同：Unicode NFC；CRLF/CR 统一为 LF；每行去除 trailing spaces/tabs；首尾空白行删除；内部行顺序和内容不重排；最终 UTF-8 bytes 以单个 LF 结尾。该 hash 进入 identity，摘要自由文本的任何语义变更或规范化后 bytes 变更都会使 record ID 失效。
- `design_revision_occurrence`：同一 `implementer.md` 内 `MANUAL_ESCALATION_DESIGN_REVISION` records 的 append 顺序 positive integer。
- `design_revision_record_id`：record canonical identity hash。

`design_revision_record_id` 的 canonical identity 是固定 key 顺序 JSON 的 SHA-256，记为 `sha256:<hex>` 并写入 record；canonical payload 必须只包含 record fields 的规范化身份值，不包含 `design_revision_record_id` 自身，也不 hash 整个 implementer 文件，避免 self-hash。固定 payload 为 `{record_type,task_id,previous_attempt,previous_fix_cycle,previous_review_cycle,evidence_path,validation_evidence:{path,occurrence_or_heading,task_id,attempt,fix_cycle,review_cycle,task_brief_sha256,task_scope_fingerprint,outcome,file_sha256},review_evidence:{path,occurrence_or_heading,task_id,attempt,fix_cycle,review_cycle,task_brief_sha256,task_scope_fingerprint,outcome,file_sha256},escalation_authority,task_brief_sha256,current_task_scope_fingerprint,user_choice_summary_sha256,design_revision_occurrence}`，使用 UTF-8 canonical JSON（固定 key 顺序、无无意义空白）序列化；当两个 authority 同时成立时，`escalation_authority` 必须按 validation-first/review-second 的 canonical 数组顺序进入 payload。Controller 必须重算完整 payload；用户选择摘要变更、validation/review occurrence 改指、tuple/outcome/path/file hash 变化、双 authority 数组反序或其他非 canonical 顺序、或只修改自由文本但未更新 hash，均使 record mismatch 并 STOP。追加前必须扫描同一 `implementer.md` 中已有 Design-revision records 计算下一个 occurrence；如果此前 Design-revision record append 已成功但 state merge 失败，后续 resume/retry 必须复用同一 applicable occurrence 与 `design_revision_record_id`，禁止为同一 previous tuple 与用户选择重复 append。

Design choice record 与 repair authorization record 互斥：同一当前轮用户选择不能同时生成 `MANUAL_ESCALATION_DESIGN_REVISION` 和 `MANUAL_ESCALATION_AUTHORIZATION`；若摘要同时表达额外 repair attempt 与 Design/Plan/acceptance/scope/context 修改，STOP 要求用户重新选择。repair record 不得满足 Design-revision exact transition；Design choice record 不得满足 repair-attempt exact transition。

#### Manual-escalation Design-revision exact transition

写入前必须全部验证，任一失败即 STOP，不修改 Design artifacts、不 dispatch、不修改 state bytes、不追加替代 record：

1. 当前 state 中目标 Task 存在且 canonical；`tasks.<task-id>.status=in_progress`；`tasks.<task-id>.attempts=<previous_attempt>`；`tasks.<task-id>.fix_cycle=2`；`tasks.<task-id>.review_cycle=<previous_review_cycle>`；`tasks.<task-id>.manual_repair_authorization` 必须为 `null` 或 absent；`tasks.<task-id>.design_revision_authorization` 必须为 `null` 或 absent；不得存在 `tasks.<task-id>.blocker` 或 Task-local blocked reason。
2. `current_task` 必须是 exact `{id:<task-id>,attempt:<previous_attempt>,status:in_progress}`，且 `current_task.attempt == tasks.<task-id>.attempts`；pointer 缺失、额外字段、status/attempt mismatch 或指向其他 Task 均 STOP。
3. change-level 必须是 manual escalation active state：`phase=implement,status=blocked`，且顶层 `reason`（若存在）只能指向本次预算耗尽的 manual escalation；不能同时存在 Design/Gate/dirty/global blocker reason。
4. Latest authoritative validation 与 latest fresh review/re-review evidence 必须同时存在于固定 `validation.md`/`review.md`，并且各自 path、occurrence/heading、ordinary file hash、outcome 与完整 cycle identity 精确匹配当前 tuple `{task_id,attempt:<previous_attempt>,fix_cycle:2,review_cycle:<previous_review_cycle>}`、当前 `task-brief.md` hash 与当前 `task_scope_fingerprint`。至少一个 escalation authority 必须成立；旧 attempt、旧 brief hash、旧 fingerprint、infrastructure failure、缺失 authoritative result、缺失 fresh review 或仅自由文本摘要均 STOP。
5. `MANUAL_ESCALATION_DESIGN_REVISION` record 必须已经成功 append 到 `evidence/tasks/<task-id>/implementer.md`，其 previous tuple、validation/review evidence identity、outcome、file hashes、brief hash、scope fingerprint、规范化用户选择摘要 hash、occurrence 与 `design_revision_record_id` 必须按上节 canonical payload 重新计算并与 record 完全一致；record 的用户摘要必须明确要求 Design/Plan/acceptance/scope/context 修订，且不得授权额外 bounded repair attempt。

验证通过后，只允许一次 preserve/merge 写入精确字段：

```text
phase=design
status=draft
gates.design=pending
tasks.<task-id>.status=pending
tasks.<task-id>.manual_repair_authorization=null
tasks.<task-id>.design_revision_authorization=<design_revision_record_id>
current_task=null
reason=null   # only when the existing top-level reason is the manual-escalation reason for this same previous tuple
```

该 transition 只把 active manual escalation 分流回 Design draft/pending，允许随后修改 Design artifacts 并进行 explicit Design reapproval；它不是 Task blocked、不是 repair attempt、也不是 ordinary Task dispatch。它必须 preserve `attempts`、`fix_cycle`、`review_cycle`、`task_scope_fingerprint`、implementation evidence/changed files/head/preexisting/approved control-plane、artifacts、metadata、unknown keys 与其他 Tasks/Gates 作为审计；不得递增 attempt，不得重置 cycles，不得创建 blocker，不得追加 BLOCKED，不得批准 Design Gate，不得清理无关 reason。Merge 成功后才可修改 Design artifacts；Merge 失败即 STOP，已 append 的 Design choice record 保留为审计但不得进入 Design。后续 explicit Design reapproval 若进入 contract revision mode，必须先 `validate-design-revision` 只读 preflight、再请求用户明确 reapproval、最后同参数 `approve-design-revision --allow-approval`；若 contract identity 不变才可使用 legacy context-only approval。成功 reapproval 对该 Task 清 `design_revision_authorization`；下一次普通 dispatch 才按 Task dispatch 递增 attempt并重置 cycles，旧 exhausted evidence/fingerprint 不满足新 attempt。

#### Pending manual-escalation Design-revision reconciliation before recovery/dispatch

每次 resume/re-entry、以及 manual escalation active state 或 Design draft/pending 下任何 recovery/dispatch 前，Controller 必须扫描当前/相关 Task 的 `evidence/tasks/<task-id>/implementer.md` 并按以下互斥分支处理；该 reconciliation 不引入新 helper/runtime/journal，只把固定 Task evidence 与 `state.json` 重新对齐，并保证不会重复 apply 或重复 Design choice record：

1. **已应用身份 + exact Design draft/pending shape**：若 `tasks.<task-id>.design_revision_authorization=<design_revision_record_id>` 为 non-null，必须找到 matching `MANUAL_ESCALATION_DESIGN_REVISION` record 并重算 canonical payload；state 还必须是 exact Design draft/pending shape：`phase=design,status=draft,gates.design=pending`、`tasks.<id>.status=pending`、`manual_repair_authorization=null`、`current_task=null`。只有同时满足 applied ID + exact Design draft/pending shape，才能判定 previous Design-revision merge 已成功，并继续/恢复 Design artifact 修改与 reapproval；不得再次 apply record、不得再次 append。若 applied ID 存在但 record 缺失、payload mismatch、或 Design draft/pending shape 不匹配，fail closed，STOP。若之后 Design artifacts 已修改但 Gate 仍 pending，本分支仍成立；Controller 继续 Design review，不得回退到 implement 或 dispatch。
2. **previous escalation 可重试**：若 state 仍是 previous manual escalation active state（Task/current pointer 为 previous attempt、`fix_cycle=2`、`phase=implement,status=blocked`、`manual_repair_authorization` 和 `design_revision_authorization` 均为 `null` 或 absent），并且 latest applicable Design choice record 的 `previous_*` 精确匹配当前 manual escalation tuple、record identity 重算通过、validation/review evidence identity 与当前 latest authoritative validation/fresh review 仍完全匹配，则说明上轮可能已成功 append record 但 Design-revision merge 失败；此时必须复用该 occurrence 与 `design_revision_record_id` 重试上方 exact transition，不得重复 append，也不得 dispatch。已存在 applied Design-revision ID 的 state 绝不进入本重试分支。
3. **repair/other path audit-only**：若 state 已应用 `manual_repair_authorization`、已进入 repair-attempt new attempt、Task blocked、普通 Task dispatch、Verify/Fold/archived、其他 attempt、其他 current pointer，或 Design choice record 与当前 latest validation/review evidence 的 freshness/identity mismatch，则该 record 仅保留审计，不授权自动恢复；不得用“phase 已变”或自由文本 reason 推断 merge 成功。若用户选择额外 repair attempt，则只走 repair-attempt record 与 transition；若用户选择或事实需要 Design/Plan/acceptance/scope/context 修改，则只走本 Design-revision record 与 transition。

#### Manual-escalation repair-attempt authorization record

额外 repair attempt 的授权 record 只允许追加到固定文件 `evidence/tasks/<task-id>/implementer.md`，不新增 evidence 文件、runtime、journal 或第二状态 authority。仅自由文本、聊天记录、top-level `reason`、review 摘要或任意其他文件都不能单独授权恢复；record append 成功后才允许尝试 state merge，append 失败即 STOP。该 record 的 `record_type` 必须为 `MANUAL_ESCALATION_AUTHORIZATION`，并且至少包含以下字段：

- `task_id`。
- `previous_attempt`、`previous_fix_cycle`、`previous_review_cycle`：必须等于当前 state tuple，且 previous tuple 必须为已耗尽预算的 `fix_cycle=2`。
- `new_attempt`：必须严格等于 `previous_attempt + 1`。
- `evidence_path`：固定为同一 Task 的 `evidence/tasks/<task-id>/implementer.md`。
- `validation_evidence`：latest authoritative validation 的固定文件 path、同一 `validation.md` 内 occurrence/heading 或等价稳定位置、ordinary file `sha256:<hex>`、完整 cycle identity `{task_id,attempt,fix_cycle,review_cycle,task_brief_sha256,task_scope_fingerprint}`、以及 outcome（只允许 `PASS` 或 `PRODUCT_FAILURE`）。Reviewer-only escalation 时 validation outcome 可以是 `PASS`，但 validation record 仍必须存在、fresh、authoritative 且绑定同一 exhausted tuple；validation infrastructure 无法取得 authoritative result 时不能使用此路径。
- `review_evidence`：latest fresh review/re-review 的固定文件 path、同一 `review.md` 内 occurrence/heading 或等价稳定位置、ordinary file `sha256:<hex>`、完整 cycle identity `{task_id,attempt,fix_cycle,review_cycle,task_brief_sha256,task_scope_fingerprint}`、以及 outcome（至少区分 `PASS` 与 `CRITICAL_OR_IMPORTANT`）。本流程始终要求 validation 与 fresh review 同时存在；不允许 `none`、空值或仅自由文本代替任一 evidence identity。
- `escalation_authority`：必须为 `validation_product_failure`、`review_critical_or_important`，或二者组成且顺序固定为 `["validation_product_failure","review_critical_or_important"]` 的双值数组；至少一个成立。validation authority 要求 `validation_evidence.outcome=PRODUCT_FAILURE`；reviewer-only authority 要求 `review_evidence.outcome=CRITICAL_OR_IMPORTANT`。二者都为 PASS、双值数组反序或其他非 canonical 顺序、infrastructure failure、缺失 authoritative result 或非普通产品 correctness/quality/acceptance finding 均 STOP。
- `task_brief_sha256`：当前 `task-brief.md` bytes 的 hash；必须与 validation/review evidence 绑定的 brief hash 一致。
- `current_task_scope_fingerprint`：当前 exhausted attempt 的 Task scope fingerprint。
- `user_authorization_summary`：当前轮用户授权额外 bounded repair attempt 的简明摘要；不能包含新的 Design/Plan/acceptance/scope/context 要求。
- `user_authorization_summary_sha256`：对规范化用户授权摘要 bytes 计算的 SHA-256。规范化规则固定为：Unicode NFC；CRLF/CR 统一为 LF；每行去除 trailing spaces/tabs；首尾空白行删除；内部行顺序和内容不重排；最终 UTF-8 bytes 以单个 LF 结尾。该 hash 进入 identity，摘要自由文本的任何语义变更或规范化后 bytes 变更都会使 record ID 失效。
- `authorization_occurrence`：同一 `implementer.md` 内 `MANUAL_ESCALATION_AUTHORIZATION` records 的 append 顺序 positive integer。
- `authorization_record_id`：record canonical identity hash。

`authorization_record_id` 的 canonical identity 是固定 key 顺序 JSON 的 SHA-256，记为 `sha256:<hex>` 并写入 record；canonical payload 必须只包含 record fields 的规范化身份值，不包含 `authorization_record_id` 自身，也不 hash 整个 authorization 文件，避免 self-hash。固定 payload 为 `{record_type,task_id,previous_attempt,previous_fix_cycle,previous_review_cycle,new_attempt,evidence_path,validation_evidence:{path,occurrence_or_heading,task_id,attempt,fix_cycle,review_cycle,task_brief_sha256,task_scope_fingerprint,outcome,file_sha256},review_evidence:{path,occurrence_or_heading,task_id,attempt,fix_cycle,review_cycle,task_brief_sha256,task_scope_fingerprint,outcome,file_sha256},escalation_authority,task_brief_sha256,current_task_scope_fingerprint,user_authorization_summary_sha256,authorization_occurrence}`，使用 UTF-8 canonical JSON（固定 key 顺序、无无意义空白）序列化；当两个 authority 同时成立时，`escalation_authority` 必须按 validation-first/review-second 的 canonical 数组顺序进入 payload。Controller 必须重算完整 payload；authorization summary 变更、validation/review occurrence 改指、tuple/outcome/path/file hash 变化、双 authority 数组反序或其他非 canonical 顺序、或只修改自由文本但未更新 hash，均使 record mismatch 并 STOP。追加前必须扫描同一 `implementer.md` 中已有 authorization records 计算下一个 occurrence；如果此前 authorization append 已成功但 state merge 失败，后续 resume/retry 必须复用同一 applicable authorization occurrence 与 `authorization_record_id`，禁止为同一 previous tuple 与用户授权重复 append。

#### Manual-escalation repair-attempt exact transition

写入前必须全部验证，任一失败即 STOP，不 dispatch、不修改 state bytes、不追加替代 record：

1. 当前 state 中目标 Task 存在且 canonical；`tasks.<task-id>.status=in_progress`；`tasks.<task-id>.attempts=<previous_attempt>`；`tasks.<task-id>.fix_cycle=2`；`tasks.<task-id>.review_cycle=<previous_review_cycle>`；`tasks.<task-id>.manual_repair_authorization` 必须为 `null` 或 absent（旧 state 可 absent）；不得存在 `tasks.<task-id>.blocker` 或 Task-local blocked reason。
2. `current_task` 必须是 exact `{id:<task-id>,attempt:<previous_attempt>,status:in_progress}`，且 `current_task.attempt == tasks.<task-id>.attempts`；pointer 缺失、额外字段、status/attempt mismatch 或指向其他 Task 均 STOP。
3. change-level 必须是 manual escalation active state：`phase=implement,status=blocked`，且顶层 `reason`（若存在）只能指向本次预算耗尽的 manual escalation；不能同时存在 Design/Gate/dirty/global blocker reason。
4. Latest authoritative validation 与 latest fresh review/re-review evidence 必须同时存在于固定 `validation.md`/`review.md`，并且各自 path、occurrence/heading、ordinary file hash、outcome 与完整 cycle identity 精确匹配当前 tuple `{task_id,attempt:<previous_attempt>,fix_cycle:2,review_cycle:<previous_review_cycle>}`、当前 `task-brief.md` hash 与当前 `task_scope_fingerprint`。validation outcome 只允许 `PASS|PRODUCT_FAILURE`；review outcome 必须能证明 PASS 或仍有普通产品 correctness/quality/acceptance 的 Critical/Important。至少一个 escalation authority 必须成立：`validation_evidence.outcome=PRODUCT_FAILURE` 或 `review_evidence.outcome=CRITICAL_OR_IMPORTANT`。旧 attempt、旧 brief hash、旧 fingerprint、infrastructure failure、缺失 authoritative result、缺失 fresh review 或仅自由文本摘要均 STOP。
5. `MANUAL_ESCALATION_AUTHORIZATION` record 必须已经成功 append 到 `evidence/tasks/<task-id>/implementer.md`，其 `previous_*`、`new_attempt`、validation/review evidence identity、outcome、file hashes、brief hash、scope fingerprint、规范化用户授权摘要 hash、occurrence 与 `authorization_record_id` 必须按上节 canonical payload 重新计算并与 record 完全一致；record 的用户摘要若表示 Design/Plan/acceptance/scope/context 修改，STOP 并转 Design revision/Gate。

验证通过后，只允许一次 preserve/merge 写入精确字段：

```text
tasks.<task-id>.status=in_progress
tasks.<task-id>.attempts=<previous_attempt+1>
tasks.<task-id>.fix_cycle=0
tasks.<task-id>.review_cycle=0
tasks.<task-id>.manual_repair_authorization=<authorization_record_id>
current_task={id:<task-id>,attempt:<previous_attempt+1>,status:in_progress}
phase=implement
status=in_progress
reason=null   # only when the existing top-level reason is the manual-escalation reason for this same previous tuple
```

该 transition 是 manual recovery 的 canonical redispatch 等价物：它与 Task dispatch 使用同一个 Task-local counter/cycle 语义（new attempt 严格 `previous+1`、cycles 从 0 开始），但不是一次普通 eligible Task dispatch。Merge 成功后不得再次调用 canonical Task dispatch；否则会把 attempt 错误递增到 `previous+2` 并清掉 applied authorization identity。Merge 失败即 STOP，已 append 的 authorization record 保留为审计但不得 dispatch。Preserve/merge 必须保留 `implementation.changed_files`、`implementation.head_sha`、`implementation.preexisting_paths`、`implementation.preexisting_fingerprints`、approved control-plane、gates、artifacts、evidence、metadata、unknown keys、旧 attempts/cycles/evidence history，以及任何非 manual-escalation 的状态信息；只能清理属于本 same previous tuple manual escalation 的 top-level `reason`，不得删除未知字段、Task evidence 或 changed-files 归属。新 attempt 运行期间必须保留 `tasks.<id>.manual_repair_authorization=<authorization_record_id>`；下一次普通 Task dispatch、Verify fix redispatch、blocked→pending recovery、blocked→pending 后的 dispatch、或 Design/Plan/acceptance/scope revision 分流时必须清为 `null`。

Merge 成功后才可 dispatch fresh bounded repair implementer/fixer。该 worker 必须收到新的 `task-brief.md` path 与当前 brief hash、new attempt tuple `(attempt=<previous+1>,fix_cycle=0,review_cycle=0)`、新 report append 目标 `implementer.md`、上一 exhausted attempt 的 validation/review evidence paths + hashes + outcomes + authorization record id；旧 evidence 只作为 repair input/audit，不满足新 attempt 的 completion/freshness。新 attempt 的 first authoritative validation 必须在本 transition merge 成功且产品修改完成后，先按 Fix and review cycle updates 的 fresh path 将 `review_cycle=1` 持久化，再生成绑定 `(attempt=<new>,fix_cycle=0,review_cycle=1)` 的 final validation并 dispatch fresh reviewer；后续产品 failure/finding 再按同一 attempt 的 `fix_cycle=1..2` 预算执行。不得复用旧 attempt 的 validation/review/fingerprint 完成 Task，也不得把 authorization record 当作 PASS evidence。

#### Pending manual-escalation authorization reconciliation before recovery/dispatch

每次 resume/re-entry、以及 manual escalation active state 下任何 recovery 或 dispatch 前，Controller 必须扫描当前 Task 的 `evidence/tasks/<task-id>/implementer.md` 并按以下互斥顺序处理；该 reconciliation 不引入新 helper/runtime/journal，只把固定 Task evidence 与 `state.json` 重新对齐，并保证不会重复 attempt 或重复 authorization record：

1. **已应用身份优先**：若 `tasks.<task-id>.manual_repair_authorization=<authorization_record_id>` 为 non-null，必须找到 matching authorization record 并重算 canonical payload；若当前正在判断“authorization 已 append 后的 previous merge 是否已经成功”，state 还必须是 exact new attempt shape：`tasks.<id>.attempts=record.new_attempt`、`fix_cycle=0`、`review_cycle=0`、`current_task={id,attempt:record.new_attempt,status:in_progress}`、`phase=implement,status=in_progress`。只有同时满足 applied ID + exact new attempt shape，才能判定 previous merge 已成功，并继续/恢复该 new attempt 的 fresh worker/validation/review；不得再次 apply authorization、不得再次递增 attempt。若 applied ID 存在但 record 缺失、payload mismatch、或用于判定 interrupted merge 的 state shape/freshness 不匹配，fail closed，STOP。若 new attempt 已在该 applied ID 下产生后续 persisted cycles/evidence（例如 `review_cycle>0` 或 `fix_cycle>0`），不再把旧 authorization record 当作 merge-success signal；Controller 只保留并核验 applied ID 为 audit，随后按普通 new-attempt freshness 读取同 attempt 的最新 validation/review，且仍不得再次应用该 authorization。
2. **previous escalation 可重试**：若 state 仍是 previous manual escalation active state（Task/current pointer 为 previous attempt、`fix_cycle=2`、`phase=implement,status=blocked`、`manual_repair_authorization` 为 `null` 或 absent），并且 latest applicable authorization record 的 `previous_*` 精确匹配当前 manual escalation tuple、record identity 重算通过、validation/review evidence identity 与当前 latest authoritative validation/fresh review 仍完全匹配，则说明上轮可能已成功 append authorization 但 repair-attempt merge 失败；此时必须复用该 occurrence 与 `authorization_record_id` 重试上方 exact transition，不得重复 append authorization，也不得 dispatch。已存在 applied authorization ID 的 state 绝不进入本重试分支。
3. **已分流或普通路径不可误认**：若 state 已转 Design revision/Gate、Task blocked、普通 Task dispatch 的新 attempt（`manual_repair_authorization=null`）、其他 attempt、其他 current pointer，或 authorization record 与当前 latest validation/review evidence 的 freshness/identity mismatch，则该 record 仅保留审计，不授权自动恢复；不得用“attempt 已递增”或自由文本 reason 推断 merge 成功。若 mismatch 表明用户选择或事实需要 Design/Plan/acceptance/scope/context 修改，转 Design revision/Gate；否则 STOP，要求人工检查 append-only evidence。

### Task complete

只有同时满足以下条件，Task 才能写为 `completed`：

1. `task-brief.md`、`implementer.md`、`validation.md`、`review.md` 四个固定 evidence 文件均存在。
2. implementer status 为 `DONE` 或 `DONE_WITH_CONCERNS`。
3. Task 定义要求的 validation 已执行，真实结果 append 到 `validation.md`。只有**最新、完整、适用于当前 Task scope snapshot，且在对应 `attempt/fix_cycle/review_cycle` 已成功持久化后生成**的 authoritative final validation cycle 是完成 authority；该 cycle 必须绑定 Attempt/Fix/Review Cycle 编号、task-brief content hash、`task_scope_fingerprint` 及其 task-owned path/dependency/output components（HEAD 与当时 global snapshot 仅作辅助审计）。Task complete 前 Controller 必须重算并精确比较；Task 自有路径、brief、依赖或依赖 output 变化会使旧 cycle 失效，必须生成新的完整 validation/review cycle；后续无关 Task 的产品变化不使它失效。若定义含 commands，则该 cycle 的全部 required commands 必须成功；若 parser 合法输入是 `commands: []` + notes，或 notes-only verification，则统一走 no-command static branch，要求 static acceptance 与 reviewer 明确 `PASS`。历史失败、开发中间测试和 cycle 持久化前的输出必须保留为审计，但可由后续同 tuple 的完整成功 authoritative cycle supersede；不得挑选跨 cycle 的成功结果拼成 PASS。
4. reviewer 已同时检查 spec compliance 与 code quality。
5. 最新 reviewer verdict 无未解决的 Critical 或 Important finding。

满足后合并：

```text
tasks.<task-id>.status=completed
tasks.<task-id>.task_scope_fingerprint=<current canonical task-scope SHA-256>
current_task=null
implementation.completed_tasks=<append task-id once>
implementation.changed_files=<full reconciled project-relative paths from reports + Git>
implementation.head_sha=<current HEAD>
```

`DONE_WITH_CONCERNS` 的 concerns 必须保留在 evidence；它不豁免 reviewer 阻塞条件。

### Task blocked

出现 `NEEDS_CONTEXT`、`BLOCKED`、缺失 required evidence、validation/reviewer infrastructure 无法执行，或明确的权限、环境、外部依赖临时 blocker 时，必须先按 Task blocker evidence records 将 BLOCKED record 追加到与触发源匹配的固定 evidence 文件。普通产品 validation failure 的唯一路由是 Fix and review cycle updates：validation 命令可执行但 assertion/acceptance 失败时，若 `fix_cycle < 2` 必须进入下一轮 fixer、post-fix authoritative validation 与 fresh re-review；只有 `fix_cycle == 2` 后仍失败才走上方 change-level manual escalation，不创建 Task-local canonical blocker。validation/reviewer infrastructure 无法执行、权限/环境/外部依赖等无法获得 authoritative result 的故障才可使用 `resolved_evidence` Task blocker，且不消耗产品 `fix_cycle`。只有 append 成功且 kind 可确定，才可合并；分类表与 Pre-dispatch Task-local blocked 相同：Design/Plan/context mutation-required 写 `design_revision`，权限/环境/external dependency/validation-reviewer infrastructure 写 `resolved_evidence`，无法分类 STOP。Blocked state patch 必须写 canonical blocker object 与相同顶层 Task reason，并且 `blocker.evidence` 必须精确等于承载 BLOCKED record 的同一文件：

```text
tasks.<task-id>.status=blocked
tasks.<task-id>.blocker={kind:<design_revision|resolved_evidence>,code:<stable code>,evidence:<evidence/tasks/<task-id>/implementer.md|evidence/tasks/<task-id>/validation.md>,reason:<same reason>,blocker_occurrence:<positive integer>,blocker_record_id:<sha256:...>}
tasks.<task-id>.reason=<same reason>
current_task={id:<task-id>,attempt:<n>,status:blocked}
phase=implement
status=<in_progress when an independent eligible Task remains; blocked only when no Task can continue or a global blocker exists>
implementation.changed_files=<full reconciled project-relative paths from reports + Git>
implementation.head_sha=<current HEAD>
```

Blocked Task 只阻止其 transitive dependents；Controller 可继续 dispatch 与其无依赖关系且仍 eligible 的独立 Tasks。只要仍有独立 eligible Task，change-level `status` 必须保持 `in_progress`；只有 change-level invalid input、Gate、dirty/global blocker，或没有任何独立 eligible Task 时，才将全局 `status` 写为 `blocked` 并停止整个 orchestration。Evidence append 失败、BLOCKED record 与 state blocker/reason 不一致、或 `blocker.evidence` 不指向触发源映射的固定文件时，不得写 state。

Unblock 必须保留固定 Task evidence 中的旧 blocker/history，并在下一次 dispatch 才递增 attempt。`state.tasks.<id>.blocker.kind` 是唯一恢复策略 authority：

- `kind=design_revision`：Design、Plan 或 context 声明/内容变更导致的 blocker，必须重新经过 explicit Design Gate approval。Controller 先验证所有 blocked evidence identities、计算完整新 approved control-plane map，并比较 old/new normalized Task contract identity。若 identity 改变、发生 dynamic undeclared mutation 或需 invalidation completed Task，必须走 Design Revision Closure 的 contract revision mode：先完成 artifacts + `validate-change`，再用完整 new contract、exact affected closure、non-empty reason 与 complete approved control-plane 调用 `validate-design-revision` 只读 preflight；preflight 成功后请求用户明确 reapproval；用户批准后才用相同参数加 `--allow-approval` 调用一次 `approve-design-revision`。Preflight 失败 STOP、Gate pending；用户拒绝不调用 approve、不写 state。只有 identity 不变、纯 context/control-plane bytes 修正且不 invalidation completed Task 时，才可走 legacy `--unblock-tasks` context-only mode；legacy 分支保持 contract identity 不变，不调用或混用 contract preflight。两种 approval mode 都至多调用一次写入型 `approve-design-revision`，不得混参；helper 不读取 evidence 文件，Controller 仍须预先验证 matching BLOCKED/Design-choice records。Contract mode 按 helper 的 affected closure invalidation语义更新；legacy mode 的请求集合必须精确等于所有 design_revision blocked Tasks 加 pending Design-authorized Tasks，并保持 resolved-evidence/other Tasks不变。任一 mismatch、malformed state 或 helper failure 都保持 bytes unchanged并 STOP。不得用 `replace-object` + `merge-state`、多步 patch 或通用 JSON path mutation拼装 reapproval；普通 resume只 preserve/compare，绝不调用 reapproval action或刷新 hashes。
- `kind=resolved_evidence`：临时权限、环境、外部依赖或 validation/reviewer infrastructure blocker。只有 `state.tasks.<id>.blocker.evidence` 指向的同一固定 Task evidence 文件中追加了可审查且 latest applicable 的 RESOLVED record 后，才可走下方唯一 exact recovery transition；不要求也不得虚构 Design approval，不得调用 approval-only replacement、`replace-object` 或 `approve-design-revision`，并且不得因为 Design reapproval 被恢复。状态链为：`blocked(kind=resolved_evidence)` + matching `BLOCKED` record → 同文件 append latest applicable `RESOLVED` record → resolved-evidence exact recovery 写回 `pending` 并清 `blocker/reason/manual_repair_authorization/design_revision_authorization` → 重新计算 eligibility → 下一次普通 Task dispatch 才递增 attempt 并重置 cycles。

#### Resolved-evidence exact recovery

该 transition 只适用于当前 `state.tasks.<task-id>.status=blocked` 且 canonical `blocker.kind=resolved_evidence` 的 Task。写入前必须全部验证，任一失败即 STOP，不 dispatch、不调用 approval helper、不修改 state bytes：

1. `state.tasks` 是 object，目标 Task 存在且为 canonical Task shape；`status=blocked`；`blocker` object 的 `kind/code/reason/evidence/blocker_occurrence/blocker_record_id` 全部合法；`blocker_occurrence` 为 positive integer；`tasks.<id>.reason` 与 `blocker.reason` 完全相同。
2. `blocker.evidence` 是 safe project-relative path，且按触发源映射指向 `evidence/tasks/<task-id>/implementer.md` 或 `evidence/tasks/<task-id>/validation.md`；该文件存在、可读，且不是 raw log、review.md、session journal 或第五文件。
3. 当前 cycle identity 来自 `state.tasks.<id>.attempts/fix_cycle/review_cycle`；若 `current_task` 非 `null`，它必须是 exact `{id,attempt,status}` pointer、引用已知 Task、attempt 与 `tasks.<id>.attempts` 相等、status 与 `tasks.<id>.status` 相等。Pointer malformed、unknown、attempt/status mismatch 一律 STOP。
4. 在 `blocker.evidence` 文件中按 append 顺序应用 latest applicable 规则：找到最新一条 identity 精确等于 `{task_id:<id>,attempt:<attempts>,fix_cycle:<fix_cycle>,review_cycle:<review_cycle>,kind:resolved_evidence,code:<blocker.code>,evidence_path:<blocker.evidence>,blocker_occurrence:<blocker.blocker_occurrence>}` 且 `blocker_record_id=<blocker.blocker_record_id>` 的 BLOCKED record，并确认其 reason 与当前 blocker/reason 一致；只在这条 BLOCKED 之后选择最后一条精确引用同一 `blocker_record_id`、`blocker_occurrence` 与完整 identity 的 RESOLVED record。缺失、位于旧 BLOCKED 之后但非最新 applicable、旧 occurrence、旧 cycle、旧 code、旧 evidence path、旧 reason、其他 Task、或仅自由文本声明均为 stale/mismatch，拒绝恢复。
5. RESOLVED record 必须包含可审查 `resolution_facts`，足以说明临时权限、环境、外部依赖或 validation/reviewer infrastructure blocker 已解除；不能把 Design/Plan/context mutation-required 问题伪装为 resolved evidence。发现实际需要 Design/Plan/context 修改时 STOP，转 Design revision 路径。

验证通过后，只允许一次 preserve/merge 写入精确字段：

```text
tasks.<task-id>.status=pending
tasks.<task-id>.blocker=null
tasks.<task-id>.reason=null
tasks.<task-id>.manual_repair_authorization=null
tasks.<task-id>.design_revision_authorization=null
current_task=null   # only when current_task points to this same task; otherwise preserve existing valid pointer/null
```

该 merge 必须保留 `attempts`、`fix_cycle`、`review_cycle`、`task_scope_fingerprint`、metadata、evidence、artifacts、unrelated gates 与 unknown keys 作为审计，但必须与 Design reapproval 同步清空恢复 Task 上的 `manual_repair_authorization` 与 `design_revision_authorization`，避免 stale manual/Design identity 被 pending recovery 误认。不得递增 attempt，不得重置 cycles，不得更新 Design approval，不得从 blocked 直接跳为 `in_progress`。若 `current_task` 指向其他一致 Task 或本来为 `null`，patch 不包含 `current_task` 或保持原值；只有 pointer 命中当前恢复 Task 时才清为 `null`。Merge 失败即 STOP，RESOLVED record 保留为审计但不得 dispatch；下一次 dispatch 才按 Task dispatch 规则递增 attempt 并重置 `fix_cycle/review_cycle=0`。

两类都必须重新计算 eligibility；不得从 blocked 直接跳为 in-progress，也不得删除旧 attempt/blocker evidence。存在 legacy/malformed blocker 时，任何恢复写入都必须 fail closed，先回到 Design/显式 migration，不得静默分类或从自由文本推断。

### Implement complete

仅当 `plan.yaml` 中所有 Task 均在 `state.tasks` 中为 `completed`、`current_task` 已清空，且 Controller 按 Task and Implement Completion Freshness 验证每个 Task 的 current `task_scope_fingerprint` 时才合并：非 handoff path重算 current completion/live identities并与当前 bytes一致；handoff path重算历史 completion records自身identity、完整 incoming lineage、acceptance-preservation refs及final-owner current live identity，绝不使用最终 bytes重算历史 owner `own_mutations`。再核对当前 brief、同一 persisted tuple的authoritative validation与fresh reviewer PASS。后续无关或合法 downstream mutation不废弃早期历史 evidence；只有其cycle/contract、incoming lineage、acceptance preservation、dependency/output或final-owner live freshness drift才退回重验。完成逐 Task检查后再计算完整 `global_product_fingerprint`。缺少任一当前 evidence或global计算失败均不得完成：

```text
phase=implement
status=completed
current_task=null
implementation.changed_files=<full reconciled project-relative paths from reports + Git>
implementation.head_sha=<current HEAD>
implementation.product_fingerprint=<current global_product_fingerprint>
```

### Verify review ready

change-wide verification 与审查完成后，先完整写 `evidence/review.md`。Review artifact 可记录其依据的 `base_sha`、当前 HEAD、`global_product_fingerprint` 与 changed-files fingerprint，但**不得记录自身 hash**。写完最终 bytes 后计算普通 file SHA-256，再用同一个 ready merge 把 path、expected file hash 与全部 snapshot fields 存入外部 `state.json.evidence_snapshots.verify_review`。只有这次 merge 成功，review 才 ready；不能只记录路径：

```text
phase=verify
status=draft
gates.verify=pending
evidence.verify_review=evidence/review.md
evidence_snapshots.verify_review={path:evidence/review.md,sha256:<ordinary final-file SHA-256>,base_sha:<base>,head_sha:<HEAD>,global_product_fingerprint:<global>,changed_files_fingerprint:<changed-files>}
current_task=null
implementation.head_sha=<review-bound HEAD>
implementation.product_fingerprint=<review-bound global_product_fingerprint>
```

普通 Task dispatch/complete 不更新 `implementation.product_fingerprint`；Verify fix 或 product drift 不得以旧值批准，后续新的完整 Verify review ready 才更新。

此 transition 只表示 verdict 可供用户审查，不代表接受。

### Verify user decision

- **accept**：只有用户当前轮明确接受 Verify verdict，且 Controller 在 approval merge 前执行 **Verify accept freshness check**：从 `state.evidence_snapshots.verify_review` 读取 expected path/hash/snapshot fields，重算 review artifact 普通 file SHA-256、`base_sha`、HEAD、`global_product_fingerprint` 与 changed-files fingerprint并逐项精确比较，才以 approval-enabled merge 写 `gates.verify=approved`。Artifact 内不存在 expected self-hash authority。任一 product/review/artifact drift 都保持/退回 `gates.verify=pending,phase=verify,status=draft`；若存在当前 Fold proposal，不修改 proposal artifact，并在同一 preserve/merge patch 写 `evidence_snapshots.fold_proposal.status=superseded`。随后重新 Verify；不得批准旧 verdict、apply、close 或 archive。匹配时保持 `phase=verify,status=approved`，或同轮采用 Fold proposal ready transition。
- **fix**：保持 `gates.verify=pending`，写 `phase=implement,status=in_progress,current_task=null`。旧 `implementation.product_fingerprint` 仅为历史 reviewed snapshot，不得用于后续批准；只有新的完整 Verify review ready 更新它。Impact set 默认包含 direct affected Tasks 及所有已 completed 的 transitive dependents；将这些 Tasks 写为 pending，并从 `implementation.completed_tasks` 完整替换数组移除。只有 Verify evidence 中持久记录 explicit unaffected analysis（说明依赖输出为何未变且旧验收仍适用）时，才可保留某 dependent 为 completed。所有退回 Task 的旧 implementer/validation/review evidence 保留但对新 snapshot 失效；下一次 dispatch 才递增 attempt，并必须生成新 attempt、完整 validation cycle 与 fresh review。重新验证遵循最新 snapshot/cycle authority；修复完成后重新生成 change-wide review。
- **defer**：不批准、不回退、不伪造 blocker；保持 `phase=verify,status=draft,gates.verify=pending`。

只有 **explicit accept** 可以把 `gates.verify` 写为 `approved`。

### Fold proposal ready

Verify Gate 已 approved，且 Controller 在 **Fold proposal ready freshness check** 先从 `state.evidence_snapshots.verify_review` 读取 expected metadata，重算 review 普通 file SHA-256、`base_sha`、HEAD、`global_product_fingerprint` 与 changed-files fingerprint并逐项一致，才可生成 proposal。先完整写 `evidence/fold-proposal.md`；artifact 可记录 product snapshot fields 与所依据的 Verify review identity/hash，但**不得记录 proposal 自身 hash**。写完最终 bytes 后计算 proposal 普通 file SHA-256，再用同一个 ready merge 将 `status=ready`、expected proposal hash、Verify review hash 与 snapshot fields 存入外部 `state.evidence_snapshots.fold_proposal`。任一 product/review/artifact drift 必须将 Verify Gate 保持/退回 pending；若已有当前 proposal，则不得修改其 artifact，并以 exact patch 写 `evidence_snapshots.fold_proposal.status=superseded,phase=verify,status=draft,gates.verify=pending`。随后重新 Verify，不得基于旧 verdict 生成 proposal、apply、close 或 archive。Proposal 只可基于 focused stable brief/spec/design/plan artifacts、Verify evidence/verdict 与 scoped product diff summary；适用时提炼 architecture decisions/engineering constraints，并在 proposal 中标明目标长期文档与去重/reconciliation 依据。不得加载 raw/full history：

```text
phase=fold
status=draft
gates.fold=pending
evidence.fold_proposal=evidence/fold-proposal.md
evidence_snapshots.fold_proposal={status:ready,path:evidence/fold-proposal.md,sha256:<ordinary final-file SHA-256>,verify_review_sha256:<external expected review SHA-256>,base_sha:<base>,head_sha:<HEAD>,global_product_fingerprint:<global>,changed_files_fingerprint:<changed-files>}
current_task=null
```

Canonical proposal lifecycle：

- 新 proposal 或 edit 只有在 artifact 完整写入、外部 hashes/snapshot fields 计算完成，并由 ready transition 完整替换 metadata 后，才写 `evidence_snapshots.fold_proposal.status=ready`。
- 对尚未进入 blocked apply retry 的 ready proposal，任一 product/review/artifact drift 使用 exact preserve/merge patch：`evidence_snapshots.fold_proposal.status=superseded,gates.verify=pending,gates.fold=pending,phase=verify,status=draft`。不得修改 proposal artifact。
- 对 `fold_apply.status=blocked` 的 retry，任一 drift 使用 exact preserve/merge patch：`evidence_snapshots.fold_proposal.status=superseded,gates.verify=pending,gates.fold=pending,phase=verify,status=blocked,fold_apply.status=blocked` 并记录 drift evidence。不得修改 proposal artifact。
- 两个 supersede transition 都 fail closed：不得 apply/no-op/retry/close/archive。`superseded` 永久不可逆；只有完整写新/edited artifact 并创建一份新的 ready metadata 才产生新候选。

### Fold user decision

- **accept**：不得先 apply 后批准。只有 `state.evidence_snapshots.fold_proposal.status=ready` 才可执行 **Fold accept freshness check**：从该 metadata 与 `.verify_review` 读取 expected values，分别重算 proposal/review artifact 的普通 file SHA-256，并重算 `base_sha`、HEAD、`global_product_fingerprint` 与 changed-files fingerprint；全部逐项匹配后才使用外部 expected proposal hash 与每个 target before hash，用 approval-enabled merge 写 `gates.fold=approved,phase=fold,status=in_progress,fold_apply.proposal_hash=<hash>,fold_apply.status=pending,fold_apply.targets_before=<map>,fold_apply.targets_after={},fold_apply.error_evidence=null`；只有该 merge 成功才开始 apply。Apply 必须按 proposal 做 idempotent reconciliation：先检查目标是否已包含等价稳定知识，避免重试时重复插入。
  - apply 失败：保持 `gates.fold=approved,phase=fold`，写 `status=blocked,fold_apply.status=blocked,fold_apply.error_evidence=evidence/fold-apply.md` 与已观察 target hashes；不得 Close。修复临时问题后，对同一 external expected proposal hash 执行 **blocked apply retry freshness check**，再次从两份 `evidence_snapshots` 读取 expected metadata，重算两个 artifact hashes 与全部 snapshot fields，并做 before/current reconciliation；只有全部匹配才可重试。
  - apply 成功：写 `status=approved,fold_apply.status=applied,fold_apply.targets_after=<map>`；只有 proposal hash、targets 与 applied evidence 一致后才执行 Close。
  - accept drift 使用上方 ready proposal 的 `status=draft` supersede patch；blocked retry drift 使用 `status=blocked,fold_apply.status=blocked` supersede patch并记录 drift evidence。两者都不得修改 `evidence/fold-proposal.md` artifact。当前 Fold proposal自此永久不可 apply/no-op/retry；不得 apply/close/archive，必须重新完整 Verify。已批准但尚未成功 apply 的 Fold Gate 不得覆盖 stale Verify 判定。
- **edit**：完整写新 `evidence/fold-proposal.md` 后重算普通 file SHA-256，并通过 state merge 以 `status=ready` 完整替换 `evidence_snapshots.fold_proposal` metadata。保持 `phase=fold,status=draft,gates.fold=pending`，并清空/替换尚未批准的 fold_apply candidate fields；除非用户同轮还 explicit accept 新 external hash，否则不得应用或批准。Artifact 不记录自身 hash。旧 metadata/candidate 作为历史 evidence 保留时必须为 `superseded`，不能重新标回 ready。
- **reject**：不应用 proposal，保持 `phase=fold,status=draft,gates.fold=pending`；如用户意图是不写长期知识并关闭，必须另行明确选择 no-op。
- **no-op**：用户明确批准“没有稳定知识需要写回”；仅 `evidence_snapshots.fold_proposal.status=ready` 可执行与 Fold accept 相同的 **no-op accept freshness check**，从两份 state 外部 metadata 读取 expected hashes/snapshot fields，重算 proposal/review 普通 file SHA-256 与 product snapshot并逐项比较。匹配后才以 external expected proposal hash 进行 approval-enabled merge，写 `gates.fold=approved,phase=fold,status=approved,fold_apply.proposal_hash=<hash>,fold_apply.status=applied,fold_apply.targets_before={},fold_apply.targets_after={}`，再执行 Close。任一 drift 按统一规则退回 Verify pending、标记 proposal `superseded`，不得 close/archive。
- **defer**：不改 proposal、长期知识或 gate；保持 `phase=fold,status=draft,gates.fold=pending`。

Resume/re-entry 只把 `evidence_snapshots.fold_proposal.status=ready` 且重算 proposal/review ordinary file hashes、base SHA、HEAD、global product fingerprint、changed-files fingerprint 全部匹配的记录视为当前候选。发现任何 product/review/artifact drift 时，不修改 proposal artifact，执行上述 exact supersede patch。`status=superseded` 永不可 apply/no-op/retry，也不能在 resume 时恢复为当前候选；只能完整写新/edited proposal、计算新外部 hash 并以新 metadata `status=ready` 建立新候选。

### Close

仅在 `gates.fold=approved` 且 `fold_apply.status=applied`（成功 apply 或 explicit no-op）后，先以同样的 idempotent/reconciliation 规则更新 `.dev-docs/changes/index.md`，再合并最终状态：

```text
phase=archived
status=completed
current_task=null
active=false
gates.fold=approved
```

Close 不移动或重命名 `.dev-docs/changes/<change-id>/`。`.dev-docs/changes/index.md` 是 narrowly authorized mutable control-plane：只有 Fold Close 可修改当前 change 的 active/completed 条目；apply evidence 必须记录 index before/after hash 与 reconciliation 结果。它始终排除 product diff、`changed_files` 与 Verify product scope；其他条目或其他 stage 的修改一律 fail closed。

## Gate Readiness Rules

- `brief.md` + `spec.md` existence does not mean Brief Gate is approved。
- `design.md` + `plan.yaml` + context manifests existence does not mean Design Gate is approved。
- `evidence/review.md` existence does not mean Verify Gate is approved。
- `evidence/fold-proposal.md` existence does not mean Fold Gate is approved。
- Stage 只有在 `state.json.gates.<previous-stage>` 精确为 `approved`，或用户当前轮对该 Gate 给出 explicit approval 时才可继续；当前轮 approval 必须在 stage entry 持久化。
- Artifact 存在但 gate 为 missing、pending、draft 或 ambiguous 时，STOP 并请求 explicit Gate decision。
- Provisional continuation 只允许继续完善/审查当前 stage artifacts；它不等于 Gate approval，不得进入下一 stage，也不得写 approved。风险必须写入产物和报告。

## Plan Task Status Migration

`plan.yaml` 中 legacy Task `status` 只允许在首次初始化 `state.tasks` 时读取：

1. 若 `state.tasks.<id>` 已存在，忽略 Plan 中该 Task 的 legacy `status`。
2. 若缺失，安全默认始终初始化 `state.tasks.<id>.status=pending`、`attempts=0`。Legacy `completed`、`in_progress`、`blocked` 或其他合法值只复制到 audit metadata（例如 `state.tasks.<id>.legacy_status`），不得无当前 brief/product fingerprint evidence 直接迁移为 completed 或 active state。
3. 初始化完成后，所有 Task 状态只写 `state.json`；任何 legacy audit value 都不参与 eligibility/completion。
4. 不得把执行状态、attempt、completed 或 blocked 回写 `plan.yaml`。

## Dirty Worktree Protocol

Pre-flight 必须读取 Git repo、HEAD 与 dirty paths，并在首次 entry 和 resume 都把每条路径归入且仅归入四类：

1. **Immutable approved control-plane**：Design-approved brief/spec/design/plan/manifests 等。逐项记录 path + SHA-256 hash 到 `implementation.approved_control_plane`；每个 Task dispatch 与 Fold boundary 复核。缺失/hash drift 是 change-level STOP。重新 explicit Design approval 前，Controller 必须计算完整新 map 并比较 old/new normalized Task contract identity：contract字段变化、dynamic undeclared mutation或completed invalidation走 contract revision mode，并严格执行 artifacts + `validate-change` → `validate-design-revision` 只读 preflight → 用户明确 reapproval → 相同参数加 `--allow-approval` 的单次 `approve-design-revision`；只有 contract identity不变且纯 context/control-plane bytes修正时，legacy `--unblock-tasks` context-only mode 才可用且不得混用 preflight contract mode。写入型 helper action 同时完成相应 whole-map replacement、Design approval与恢复/invalidation；helper失败即 STOP。普通 resume/re-entry只 preserve/compare，绝不调用 reapproval action、replace或刷新。
2. **Workflow-owned mutable control-plane**：current-change `state.json`、固定 `evidence/tasks/<id>/` 四文件、`evidence/review.md`、`evidence/fold-proposal.md`、fold apply evidence，以及 narrowly authorized `.dev-docs/changes/index.md` current-change entry。它们只可按固定 path/shape、append-only evidence 与合法 transition 变化；不进入 product diff、`implementation.changed_files` 或 Verify product scope。Fold two-phase journal 和失败 evidence 属于此类。
3. **Workflow-owned product mutations**：由本 change 在 `base_sha` 后产生，且可由 Task brief hash、implementer/validation/review evidence 与 changed-files snapshot 归属的产品路径。首次 entry 可为空；resume 必须重建归属，不能误判为 preexisting dirt。
4. **Preexisting dirt**：在首次 entry 已存在且经用户当前轮 explicit authorization 保留的、与 scope 不相交的其他 dirty paths。逐项记录 path、Git status 和 content hash/deleted marker 到 `preexisting_fingerprints`；每个 Task/Verify/Fold mutation 边界复核，任一变化立即 STOP。产品 overlap 或无法归属的 dirty path 始终 STOP，授权不能覆盖。

Snapshot authority 在本 File Protocol 中唯一成立。Fingerprint 分为两层：

- `task_scope_fingerprint`：`task_id` + 当前 `attempt/fix_cycle/review_cycle` + task-brief hash + 按 approved path/edge 排序的 canonical per-path completion/dependency/live ref对象 + 直接 dependency/output fingerprints 的稳定排序 canonical SHA-256。`own_mutations`来自所引用snapshot record的单个`path_hash`，不另用当前最终bytes重算历史owner map。用于Task complete、Implement complete、Verify fix与resume；非handoff owner要求completion/live/current bytes一致，handoff历史owner要求append-only completion与完整incoming lineage，final owner承担current live freshness。旧cycle在其contract/cycle identity失效时只作审计，但合法downstream mutation本身不使历史cycle失效；无关后续Task也不参与。
- `global_product_fingerprint`：下方完整 reconciled workflow product scope 的最终 path→content/blob hash map canonical JSON SHA-256。用于 Implement complete 的初始 change-wide snapshot，以及 Verify/Fold 审查与所有用户 decision/retry freshness。

`global_product_fingerprint` 只有一个 canonical 算法：

1. 以首次 Implement `base_sha` 为 scope 基线，按下方 Git reconciliation 得到完整 workflow product scope。
2. 对 scope 中每个 project-relative path 读取**最终 reconciled bytes**，计算 final content/blob SHA-256；untracked path 进入同一 map，删除使用 canonical deleted marker。
3. 构造 `project-relative path -> final content/blob SHA-256` map，按 path lexicographic 排序，以 UTF-8 canonical JSON（固定 object key 顺序、无无意义空白）序列化。
4. 对 canonical JSON bytes 计算 SHA-256，得到 `global_product_fingerprint`。

该 fingerprint 基于 base scope，但只表示当前最终 bytes，不编码 committed/staged/unstaged/untracked 分区身份。相同最终 bytes 下，单纯 `git add`、`git reset` 或其他 staging 状态切换不得改变 fingerprint；HEAD、mtime、patch 分区 hash 或 changed path 集合均不能替代此算法。Changed-files content fingerprint 是同一 final-content map 中 `implementation.changed_files` 子集按相同 canonical JSON 算法所得 hash。Task scope 则仅取该 Task own mutations，并加入 brief 与 dependency/output fingerprints；不得错误绑定后续无关 Task 内容。

Git reconciliation 的规范公式是：

```text
workflow product scope =
  base-relative committed product paths
  ∪ staged product paths
  ∪ unstaged product paths
  ∪ untracked product paths
  - immutable approved control-plane paths
  - workflow-owned mutable control-plane paths
  - unchanged preexisting_paths
```

`implementation.changed_files` 与 Verify Git truth 都使用该去重后的完整集合。Reports 用于证明 ownership 与解释 scope，不可覆盖 Git；preexisting fingerprint 变化、证据不足的 overlap 或分类不唯一均 fail closed。不得用当前 HEAD 重置 `base_sha`，也不得 stash、reset、clean、触碰或提交 preexisting dirt。

## State Merge Rules

除 Design reapproval 必须通过单次写入型 `approve-design-revision --allow-approval` action 外，所有 `state.json` 更新必须使用 recursive preserve/merge。Contract revision 写入前必须已按 Design Revision Closure 完成只读 `validate-design-revision` preflight、取得用户明确 reapproval，并在 approve 时使用相同参数加 `--allow-approval` 重新 read/revalidate；context-only legacy reapproval 只在 contract identity不变时使用 `--unblock-tasks` mode。两者不得混用。`replace-object --allow-approval` 只保留为低层 allowlisted replacement helper，不得用于 Design reapproval transition，也不是普通 merge 的替代品：

- object 对 object 递归合并。
- scalar、array 或 `null` patch 替换对应值。
- 不在 patch 中的字段保持不变。
- Only update fields required by current transition. 只更新当前 transition 要求的字段，避免无关 fields 或 gates 回退。
- 不删除未知顶层键、nested metadata、evidence、current task details 或无关 gate。
- 数组更新必须由调用者提供完整期望数组；helper 不隐式 append。
- JSON 无效时 STOP，不覆盖原文件。
- Gate approval patch 必须来自当前轮 explicit Gate approval（不是 provisional continuation），并使用 helper 的 approval guard。

## Deterministic Helper Boundary

Task 1 helper CLI 是协议安全机制，不是 runtime：

- `state-helper.py inspect-state` 读取状态摘要。
- `state-helper.py check-gate` 只依据持久 gate 或调用者显式 `--authorized` 判断 readiness。
- `state-helper.py merge-state` 执行 recursive preserve/merge；任何 `gates.*="approved"` patch 必须显式 `--allow-approval`。
- `state-helper.py replace-object` 只 allowlist `implementation.approved_control_plane`，要求 `--allow-approval`；若 `state.implementation` 缺失可创建，若已存在但不是 object 必须 structured error 且不改 state bytes。它是低层 whole-object replacement helper，本身不批准 Gate，不得用于 Design reapproval transition。
- `state-helper.py validate-design-revision` 是 contract revision 的只读 preflight action，只接受 `--state`、完整 `--approved-control-plane`、`--task-contract`、`--affected-tasks` 与 `--revision-reason`，不得接受 `--allow-approval` 或 `--unblock-tasks`。它复用 approval 的 old/new canonical contract full validation、Task ID set guard、old/new reverse dependency union exact closure、affected in-progress guard、state/blocker/current-pointer/authorization/snapshot-ref/completed-tasks validation 与 candidate serialization；成功只输出 required/declared affected set、contract/control-plane identities 和 `updated=false` 摘要，不写 state、不批准 Gate、不证明 evidence freshness。失败 structured 且 bytes unchanged/Gate pending。该摘要只能用于向用户请求明确 reapproval，不能替代 approval。
- `state-helper.py approve-design-revision` 是 Design reapproval 的唯一写入型 helper action，要求 `--allow-approval`、完整 `--approved-control-plane`，并严格二选一：(a) contract mode 同时要求 `--task-contract`、`--affected-tasks`、`--revision-reason`，拒绝 `--unblock-tasks`，且必须在同一 Controller flow 中已用相同参数完成 `validate-design-revision` preflight 并取得用户当前轮明确 reapproval；(b) legacy context-only mode 要求 `--unblock-tasks`，且不得出现任一 contract参数，也不得混用 contract preflight。Contract mode 不信任 preflight缓存；approve重新读取state并重新执行与preflight相同的 full validation、exact closure 与候选构造，处理 TOCTOU。Contract mode 使 exact affected completed/blocked/pending Tasks回 pending/revalidation、移出 completed list、清 current fingerprint markers，同时保留 attempts/cycles/reports/snapshots历史。Legacy mode只恢复完整 Design-eligible集合，不替换 `approved_task_contract`，所以 Controller只有在 contract identity精确不变、无 dynamic undeclared mutation且无completed invalidation时才能调用。两种 approval mode都完整替换 approved control-plane、批准 Design Gate并在单次现有 write boundary写 state；所有 state/blocker/current-pointer/authorization validation在写前完成，失败 structured且bytes unchanged。Helper不读取 evidence或snapshot文件、不重算这些 record ids；Controller负责预验证。
- `task-helper.py validate-change` 验证 change、Plan 和 manifests 的声明形状。
- `task-helper.py extract-task` 生成单 Task brief，只选择 shared 或 matching manifest entries。

Helpers 不得读取 manifest `path` 指向的 target content，不得自动推进或批准 gate，不得读取聊天历史，也不得成为 CLI product、hook、daemon、MCP server 或 background automation。

## Change Index and Archival

Fold two-phase apply 已持久为 `fold_apply.status=applied`（成功 apply 或 no-op）后：

1. 将 `.dev-docs/changes/index.md` 对应 change 更新为 inactive/completed。
2. 再执行 Close transition，使 `state.json.active=false`。
3. 保留原 change 目录和所有 evidence 在原位；`archived` 是 lifecycle phase，不是文件移动操作。

## Hard Rules

- 不要把 chat history 当作 source of truth。
- 不要默认读取全部 `.dev-docs/` 或全部 source files。
- 不要把长篇 raw logs 写入 `.dev-docs/`。
- 不要把 raw/temporary runtime state 放入 Git-facing knowledge files。
- 不要把 artifact existence 当作 gate approval。
- 不要在无当前轮明确确认时将任何 gate 设置为 `approved`。
- 不要重写最小化 `state.json`；必须 recursive preserve/merge。
- 不要回写 `plan.yaml` Task status。
- 不要 stash、reset、clean 或触碰未授权 dirty paths。
- 不要在 Fold 前把 proposal 当成长期知识，也不要在 Close 时移动 change 目录。
