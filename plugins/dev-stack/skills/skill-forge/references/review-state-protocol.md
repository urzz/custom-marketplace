# Review State Protocol

Phase 4/5 的单层权威协议。本文固定 Controller、bounded agents 与
`review-state-helper.py` 之间的文件和状态合同；语义审查仍由 fresh reviewer 完成。

## Contents

- [Failure Baseline](#failure-baseline)
- [Authority](#authority)
- [Artifacts](#artifacts)
- [Immutable Identities](#immutable-identities)
- [State Schema](#state-schema)
- [Task Lifecycle](#task-lifecycle)
- [Finding Schema](#finding-schema)
- [Baseline Classification](#baseline-classification)
- [Review Observation](#review-observation)
- [Fix Authorization](#fix-authorization)
- [No-Progress Rules](#no-progress-rules)
- [Cross-Gate Ownership](#cross-gate-ownership)
- [Recovery](#recovery)
- [Review Package](#review-package)
- [Completion and Squash](#completion-and-squash)
- [Error Codes](#error-codes)
- [Controller Pseudocode](#controller-pseudocode)
- [Red Flags](#red-flags)

## Failure Baseline

Session `312b5737-1f48-41f2-9fee-6c2e05d0e1ef` 已观察以下 RED failure
predicates；它们是本行为变更的复用基线，不重复运行同一昂贵 baseline：

- baseline debt blocked unrelated rename
- same checker finding survived multiple fixes
- fix report did not run its new command
- fresh reviewer introduced a contract-external future case
- final reviewer delegated recursively

## Authority

- 主 Session 是唯一 Controller，也是 state、Gate、rubric 与用户决策 authority。
- `scripts/review-state-helper.py` 是 `review-state.json` 的唯一 writer；任何 agent、
  Controller 文本总结或任务列表都不能直接编辑 state。
- Helper 只校验机械事实并执行转换，不做语义 review、不调用模型、不修改产品文件、
  不 commit，也不替用户批准 Gate。
- Implementer/fixer 生成有界变更；task reviewer/final reviewer 生成结构化 observation。
  Sequential + Generator-Critic 的职责分离不因状态机而改变。
- Agent report、commit message、自然语言 verdict 都只是 claim。只有 helper 成功记录
  implementation/fix 或成功 import observation 后，claim 才影响 state。
- Controller 只服从 `next-action` 的一个返回动作，不从 agent summary、会话记忆、
  todo 状态或“看起来已通过”推导转换。
- Reviewer、fixer、implementer、eval 均不得 delegation，不得调用其他 skill，不得
  创建 worktree，不得修改 state/Gate/rubric。

## Artifacts

一个 run 使用 `.skill-forge/<skill-name>-<change-topic>/`，所有文件平铺；目录的
`.gitignore` 内容为 `*`。所有 dispatch 传绝对路径，不能依赖 agent CWD。

| Artifact | Contract |
|---|---|
| `spec.md` | 已确认 Spec；init 后 hash 冻结 |
| `plan.yaml` | 已确认 Plan；init 后 hash 冻结 |
| `rubric-snapshot.md` | `init` 从已存在且只读的 `--rubric-source` 复制的 rubric bytes；run 内 `--rubric-snapshot` 目标在调用前必须不存在；仅 helper 创建且不得刷新 |
| `review-state.json` | schema v1，helper 唯一写入 |
| `task<N>-brief.md` / `.json` | `plan-task-query.py` 生成的稳定 brief |
| `task<N>-report.md` | implementer 原始报告 claim |
| `task<N>-review-attempt<M>.json` | task reviewer 原始 observation |
| `task<N>-fix-attempt<M>-report.json` | fixer 原始 JSON report |
| `final-review-attempt<M>.json` | final reviewer 原始 observation |
| `validation-<gate>-attempt<M>.json` | structural/behavioral observation |
| `review-<base7>..<head7>-attempt<M>.diff` | helper 生成、不可覆盖的 review package |
| `eval-prompts.md` | mandatory final review 前生成、Phase 5 使用的行为验证输入 |

Attempt artifact 一经交给 helper 即不可覆盖。只有 helper 推进后的新 review/fix attempt 才增加
`<M>`；无合法 handoff 的 API/transport retry 保留相同 schema `attempt` 和 `<M>`，仅将
原始 artifact 另存为带 `-retry<N>` 的新文件且不得覆盖旧文件，state/helper attempt 不递增。
Agent 输出先原样落盘，再调用 helper；非法 JSON 也保留作审计证据。若 Controller 需要处理
`cannot_verify`，保留原始文件，
另建同目录、带 `-controller` 后缀的派生 import 文件，仅加入 Controller resolution
或经重新审查得到的 finding，不伪装成原始 agent 输出。

每个 task-bound dispatch envelope 必须显式包含：绝对 state、brief、report、
review-package、observation 路径，以及 `scope`、`ticket`、`task_id`、`model`。
不适用的路径仍作为该 attempt 的预定路径传递。`model` 必须逐字取该 Task 的
`meta.model`；不得由 agent 推断。Whole-change final/eval dispatch 使用明确的
`task_id: null`，并携带 Plan task acceptance index；final reviewer 的 model 取最后一个
Task 的 `meta.model`，eval case 取其合同 owner Task 的 `meta.model`。它们不得伪装成
某个 owner Task。

## Immutable Identities

`init` 一次冻结：

- `initial_base`（40 位 commit SHA）
- `spec_path` + `spec_sha256`
- `plan_path` + `plan_sha256`
- `rubric_snapshot_path` + `rubric_sha256`
- `scope` 与 `ticket`（无 ticket 时 JSON 为 `null`，CLI 传 `--ticket none`）
- Plan task 顺序与每个 Task 的 exact `files.create/modify/delete` ownership

`start-task` 再冻结该 Task 的 `task_base`；后续 fix 只累计更新 `task_head`。
`current_head` 随合法 implementation/fix/squash 更新，不是 immutable identity。
Task review 始终使用 `task_base..task_head`，final review 和 Phase 5 始终使用
`initial_base..current_head`。

每个 mutating command 都重新验证 Spec、Plan、rubric snapshot hash。任一 hash drift
返回 `ARTIFACT_HASH_DRIFT`，不得刷新 hash、替换 snapshot 或继续旧 run。Plan 经用户
修订后必须返回 Phase 3、重新确认，并在新 run 中重新 init。

## State Schema

顶层必须恰好是：

```json
{
  "schema_version": 1,
  "workflow": {},
  "artifacts": {},
  "tasks": {},
  "findings": {},
  "history": []
}
```

`workflow` 必含：

- `scope`, `ticket`, `repo_root`
- `initial_base`, `current_head`
- `spec_path`, `spec_sha256`, `plan_path`, `plan_sha256`
- `rubric_snapshot_path`, `rubric_sha256`
- `status`, `current_gate`, `current_task_id`

`artifacts` 必含：

- `task_order`: Plan 中有序 Task ID 字符串数组
- `gate_attempts`: `FINAL_REVIEW`、`STRUCTURAL_VALIDATION`、
  `BEHAVIORAL_VALIDATION` 三个 Gate 的 attempt（不含 `TASK_REVIEW`）
- `controller_resolutions`: 仅 append 的 resolution 数组

`tasks` 以字符串 Task ID 为 key。每项恰含：

- `status`, `task_base`, `task_head`, `ownership`
- `fix_budget`: `{ "maximum": 2, "used": 0, "remaining": 2 }`
- `review_attempt`, `fix_attempt`
- `open_blocking_findings`, `resolved_findings`, `baseline_findings`
- `authorized_finding_ids`, `previous_open_blocker_fingerprints`
- `cannot_verify`

`findings` 是 canonical finding ID 到完整 finding ledger entry 的映射。`history` 仅
append；每个 event 含 `event/from/to/task_id/gate/attempt/base_sha/head_sha/finding_ids`。

合法 next-action enum 只有：

```text
DISPATCH_IMPLEMENTER
DISPATCH_REVIEWER
DISPATCH_FIXER
RUN_FINAL_REVIEW
RUN_STRUCTURAL_VALIDATION
RUN_BEHAVIORAL_VALIDATION
REQUEST_SQUASH_APPROVAL
COMPLETE
HALT
```

CLI command names 和参数固定为：

```text
init --state --repo-root --spec --plan --rubric-source --rubric-snapshot --scope --ticket --initial-base
start-task --state --task-id --expected-head
record-implementation --state --task-id --base-head --new-head --report
record-fix --state --task-id --base-head --new-head --report
import-review --state --observation
needs-fix --state --task-id
authorize-fix --state --task-id --finding-ids-json
advance-gate --state --gate SQUASH_APPROVAL --result SQUASHED|UNSQUASHED --head
next-action --state
status --state
review-package --repo-root --base --head --output
```

成功只向 stdout 写一个 `{"ok": true, ...}` JSON。预期协议错误只向 stderr 写一个
`{"ok": false, "code": "STABLE_UPPER_SNAKE_CASE", ...}` JSON 并 exit 2。

## Task Lifecycle

1. Controller 记录 `INITIAL_BASE=$(git rev-parse HEAD)`。
2. Phase 3→4 只做一次 bounded Pre-Flight Contract Review，只扫描：Task 互相矛盾、
   Global Constraints 与将冻结 rubric 冲突、Task ownership 无法覆盖 acceptance。
   一次性提交全部冲突；无冲突不打断，也不扩张为全仓 audit。
3. 用户修订 Plan 时返回 Phase 3 保存并重新确认；确认后的候选 Plan 再完成其一次
   Pre-Flight。无冲突时，Controller 解析已存在且只读的 `--rubric-source` 绝对路径，确认
   run 内 `--rubric-snapshot` 目标必须不存在，然后调用 helper `init`；只有 helper `init`
   创建 snapshot 与 state，Controller 不得预创建二者。
4. `READY` 的 `DISPATCH_IMPLEMENTER` 动作先调用 `start-task`，固定 `task_base`，再
   dispatch 一个 fresh implementer。`IMPLEMENTING` 恢复时复用相同 Task/attempt 合同。
5. Implementer 恰好产生一个 `feat(<scope>): [Task N] <name>` commit 与报告。
   Controller 用 `record-implementation` 校验实际 HEAD、ancestry、report 存在及完整
   diff ownership；成功后状态成为 `REVIEWING`。
6. `DISPATCH_REVIEWER` 前生成累计 `task_base..task_head` package，dispatch 一个 fresh、
   independent reviewer。保存原始 JSON，再 `import-review`。
7. Task 仅在 helper 成功 import `PASS` 并把 Task 置为 `PASSED` 后完成。Agent 自报
   PASS、报告存在或测试通过都不能单独完成 Task。
8. 最后一个 Task PASS 后，helper 进入 `FINAL_REVIEW`。Controller 先生成基于冻结 Spec 的
   `eval-prompts.md`，再执行 whole-change final review；不能用 per-task PASS 替代。
9. Final review PASS 后自动进入 Phase 5 的 structural gate；Phase 4 与 Phase 5 之间没有用户 Gate。

Implementation/fix commit 之外的 out-of-band HEAD 变化由 base/head/ancestry 校验拒绝。
Controller 不重写 agent commit，也不直接补改产品文件。

## Finding Schema

Finding、Review Observation、Fix Report 与 Controller Resolution 的具体 JSON 示例在
`templates.md`；这是同级文件名提示，不是 reference 链接，agents 由 Controller 直接接收
其绝对路径，禁止从本文递归加载 reference。

每个 finding 必含以下字段，且不得以自由 `additional` 字段代替合同字段：

| Field | Contract |
|---|---|
| `id` | 非空 observation ID；helper 可能按 fingerprint 合并到 canonical ID |
| `owner_task_id` | task review 必填；final/validation 原始值为 `null`，由 helper 映射 |
| `source_gate` | 四个 review gate 之一，等于 observation `gate` |
| `attempt` | 整数，等于 observation attempt |
| `rule_id` | 稳定规则 ID |
| `contract_ref` 或 `rubric_ref` | 恰好一个非空 |
| `failure_key` | 同一失败语义的稳定 key |
| `severity` | `CRITICAL` / `IMPORTANT` / `MINOR` |
| `blocking` | boolean |
| `origin` | `NEW` / `REGRESSION` / `BASELINE` / `OUT_OF_CONTRACT` |
| `status` | `OPEN` / `RESOLVED` / `BASELINE` |
| `summary`, `path` | 非空具体描述与主路径 |
| `required_fix_paths` | exact repo-relative paths；actionable finding 非空且不重复 |
| `base_evidence`, `head_evidence` | `{command, exit_code, output}` |
| `closure_test.expected` | `{command, exit_code, output}` |
| `closure_test.actual` | 未关闭时 `null`；RESOLVED 时为实际命令结果 |
| `observations` | 每项含非空 `risk` 与 `check` |
| `resolution` | `null` 或结构化 resolution claim |

Actionable 的充要条件是：`status=OPEN`、`origin` 为 `NEW|REGRESSION`、
`blocking=true`、`severity` 为 `CRITICAL|IMPORTANT`。其余 finding 不能授权 fixer。

Helper 忽略 agent 自报 fingerprint，并重算：

```text
sha256(owner_task_id + "\0" + rule_id + "\0" + normalized_path + "\0" +
       contract_or_rubric_ref + "\0" + failure_key)
```

相同 fingerprint 合并 observation history；同一 ID 指向不同 fingerprint 返回
`FINDING_ID_COLLISION`。RESOLVED fingerprint 再出现时 origin 变为 `REGRESSION`。

## Baseline Classification

Reviewer/validator 必须比较相同适用检查在 review base 与 head 的结果：

| Base | Head | Origin |
|---|---|---|
| PASS | FAIL | `NEW` |
| FAIL（同一 failure） | FAIL（未由本 change 引入） | `BASELINE` |
| 已在 ledger RESOLVED | 再次 FAIL | helper 归一为 `REGRESSION` |
| 要求超出冻结 Spec/Plan/rubric | 任意 | `OUT_OF_CONTRACT` |

Structural validation 必须对 `INITIAL_BASE` 与 `CURRENT_HEAD` 运行相同适用命令，
分别写入 `base_evidence`、`head_evidence` 后再分类；不能因为 head 检查失败就假设 NEW。
Task review 使用 Task base/head，final/behavioral 使用 initial/current 范围。

`BASELINE` 由 helper 强制 `blocking=false,status=BASELINE`，不授权 fix、不消费预算。
`MINOR` 或 suggestion（`blocking=false`）同样不授权 fix。`OUT_OF_CONTRACT` 进入
`HALTED_CONTRACT_DISPUTE` 交用户，不自动修复；若争议指向 Plan/rubric 合同，回 Phase 3
由用户裁定并在新 run 重新冻结 identities。

## Review Observation

一个 observation 必须是单个 JSON object：

```text
schema_version, gate, verdict, task_id, base_sha, head_sha,
rubric_sha256, attempt, findings, cannot_verify, controller_resolutions
```

- `schema_version` 精确为整数 `1`；`verdict` 只允许 `PASS|FAIL`。
- `gate` 只允许 `TASK_REVIEW|FINAL_REVIEW|STRUCTURAL_VALIDATION|BEHAVIORAL_VALIDATION`。
- Task review 的 `task_id` 为当前 Task；其他 gate 为 `null`。
- Base/head、attempt、rubric hash 必须与 state 当前期待值精确一致。
- `findings`、`cannot_verify`、`controller_resolutions` 都必须是数组。
- 合法 FAIL 必须产生可处理 finding 或确定性 HALT；没有 OPEN blocker 时 verdict 必须 PASS。

复审必须逐个返回全部 `authorized_finding_ids`，每个保持同 ID，状态只可为 OPEN 或
RESOLVED。RESOLVED 必须提供实际 `closure_test.actual`；fixer 报告中的通过 claim 不会
代替 reviewer 的 closure evidence。

Reviewer 把不能从规定范围核验的项写入 `cannot_verify`，不扩大搜索。Controller 在
首次 import 前只能三选一：独立验证后添加 `{id,action,reason}` resolution；让 reviewer
把它转换为完整 finding；或保留未解决项并接受 helper 的 `HALTED_NEEDS_DECISION`。
Agent 不得替 Controller 填 resolution。已有 resolution ID 不得重复。

## Fix Authorization

所有四个 gate 共享 owner Task 的唯一 budget：`maximum=2`。预算只在
`authorize-fix` 成功时消费；以下情况均不消费：

- reviewer/eval/API failure，尚无合法 observation
- 非法 JSON、schema/base/head/attempt/rubric 错误
- Spec/Plan/rubric hash drift
- BASELINE、MINOR、suggestion、OUT_OF_CONTRACT
- ownership 不明、scope blocked、跨 owner observation
- 仅调用 `needs-fix`、`status` 或 `next-action`

`import-review` 产生单一 owner 的 `FIX_REQUIRED` 后，Controller 先调用 `needs-fix`，
确认完整 OPEN ID 集与 remaining；再以完全相同 ID 集调用 `authorize-fix`。同 Gate、
同 owner 的全部 actionable findings 合并为一次授权和一次 fixer dispatch，不能挑选子集。
`import-review` 仅在 finding schema 合法并完成 owner mapping 后写 ledger；若同一 observation
包含多个 owner，它在任何 `authorize-fix` 之前直接 HALT，因此 owner budget 全部保持原值。

只有 `authorize-fix` 成功并返回 attempt 后才能 dispatch
`dev-stack:skill-file-fixer`。Fixer 接收该 attempt、base head、完整 authorized IDs、
ownership、closure tests 与绝对 artifact paths，只做最小有界修复，恰好一个
`fix(<scope>): [Task N] <finding-summary>` commit。

Controller 用 `record-fix` 校验 FIXED report 的 attempt、base/new head、完整 finding
集合、changed paths 与每项实际 closure command/exit/output。BLOCKED、NO_PROGRESS、
NEEDS_CONTEXT report 进入对应 HALTED state，不产生伪造 HEAD。预算耗尽后的下一次
`authorize-fix` 持久化 `HALTED_BUDGET_EXHAUSTED`；`used` 保持 2。

## No-Progress Rules

Fix 后必须由 fresh reviewer 对同一累计范围复审，不能由 fixer 自批 RESOLVED。

- 上轮 targeted IDs 任一缺失：拒绝 observation，`MISSING_TARGETED_FINDING`。
- 上轮 OPEN fingerprint 集完全未减少：`HALTED_NO_PROGRESS`。
- 旧 blocker 未减少且同时出现新 blocker：`HALTED_REGRESSION`。
- RESOLVED finding 再现：记为 `REGRESSION`，仍受同一剩余 budget 约束。
- Closure command 未实际执行或缺 command/exit/output：拒绝 fix report 或 RESOLVED finding。

HALT 后 Controller 报告 ledger evidence、剩余 budget、base/head 与合法下一步，不以新
prompt 或新 agent 隐式继续循环。

## Cross-Gate Ownership

Task review finding 的 `owner_task_id` 必须等于当前 Task，且所有
`required_fix_paths` 都在其 ownership；否则 `HALTED_SCOPE_BLOCKED`。

Final review 和两个 validation gate 的 actionable finding 由 helper 用完整
`required_fix_paths` 对 Plan ownership 求唯一 owner：

- 单条 finding 恰有一个 owner：保留 helper 映射后的唯一 `owner_task_id` 和证据。
- 单条 finding 没有 owner 或同时落入多个 owner：`HALTED_NEEDS_DECISION`；无法形成唯一映射的 finding 原始 evidence 仍进入 ledger，budget 不消费。
- 同一 observation 的每条 finding 都能唯一映射，但合计出现多个 owner：helper 保留
  每条 finding 的唯一 owner 映射、原始 evidence 与 ledger history，然后确定性进入
  `HALTED_NEEDS_DECISION`；所有 owner 的 budget 都不消费。
- 同一 Gate、同一 owner 才能合并为一个 fixer dispatch。

当前 state 不自动选择 owner group、不拆分 observation、不排序逐 owner修复，也没有
从这个 HALT 恢复的 command。主 Session 必须向用户报告 owner→finding/path/evidence
映射。用户裁定后返回 Phase 3 修订并重新确认 Plan，在新的 run directory 重新 init；
不得编辑 halted state、复用其 budget 或在原 run 追加恢复命令。

## Recovery

任何 compaction、agent timeout、API failure 或主 Session 重启后：

1. 从已知绝对路径调用 `status --state ...`。
2. 调用 `next-action --state ...`。
3. 只恢复返回的一个动作，并复用 state 中的 Task、attempt、base/head、authorized IDs。
4. 动作产生文件后，先原样保存，再调用对应 `record-*` 或 `import-review`。
5. 再次调用 `next-action`；不依据旧对话追加 fix 或跳 Gate。

API/agent failure 若没有合法 observation/report 和 commit，不调用 import/record，state、
attempt、budget 不变。若 state 已是 `FIXING`，恢复的是同一已授权 attempt，不再次调用
`authorize-fix`。若 report 存在但 helper 未记录，先核对实际 HEAD 与 state 再调用原
record command；不要重新 commit。

`next-action=HALT` 没有通用自动恢复。Hash drift、合同争议、ownership 决策、scope
blocked、no-progress、regression 与 budget exhausted 都必须把确定性 evidence 提交主
Session/用户；需要改变合同的处理一律回 Phase 3 并初始化新 run。

## Review Package

只使用 helper 创建 package，禁止 agent 自行重建 diff 或用 `HEAD~1` 缩小范围：

```text
review-package --repo-root <ABS_REPO> --base <FULL_SHA> --head <FULL_SHA> --output <ABS_OUTPUT>
```

- Task review：`base=task_base`，`head=task_head`。
- Final/structural/behavioral：`base=initial_base`，`head=current_head`。
- Package 含完整 `Commits`、`Files changed`、`Diff`，使用累计多 commit range。
- Output 已存在时返回 `OUTPUT_EXISTS`；每个 attempt 使用新的平铺文件名。
- Reviewer 以 package 为主要视图，仅在可命名的具体风险需要时读取最小源链。

## Completion and Squash

只有 final、structural、behavioral 三个 gate 都经 helper import PASS 后，`next-action`
才会返回 `REQUEST_SQUASH_APPROVAL`。此时主 Session 才询问用户当前确认；agents、旧确认
或 Plan 文字不能批准 squash。

询问前记录：`INITIAL_BASE`、当前 HEAD/tree、`INITIAL_BASE..HEAD` commits，以及拟用
`feat(<scope>): <summary>`。用户同意后，只有主 Session 可执行跨平台非交互 squash：

```bash
PRE_SQUASH_TREE=$(git rev-parse 'HEAD^{tree}')
git log --reverse --format='%H %s' "${INITIAL_BASE}..HEAD"
git reset --soft "$INITIAL_BASE"
git commit -m "feat(<scope>): <summary>"
SQUASHED_HEAD=$(git rev-parse HEAD)
test "$(git rev-parse 'HEAD^{tree}')" = "$PRE_SQUASH_TREE"
test "$(git rev-list --count "${INITIAL_BASE}..HEAD")" -eq 1
test "$(git log -1 --format=%s)" = "feat(<scope>): <summary>"
```

验证通过后调用 `advance-gate ... --result SQUASHED --head "$SQUASHED_HEAD"`，得到
`COMPLETE`。这些改写分支的命令永不放进 agent prompt，也不得在本轮用户确认前执行。

用户拒绝时不改 commit，调用 `advance-gate ... --result UNSQUASHED --head <CURRENT_HEAD>`，
得到合法终态 `COMPLETE_UNSQUASHED`。两者的 `next-action` 都是 `COMPLETE`。

## Error Codes

预期错误不会授权 fixer；除 `FIX_BUDGET_EXHAUSTED` 按合同持久化 HALT 外，失败转换不应
替换旧可读 state。

| Group | Stable codes |
|---|---|
| JSON/state | `INVALID_JSON`, `INVALID_JSON_OBJECT`, `INVALID_STATE_SCHEMA`, `REPO_ROOT_MISMATCH`, `ARTIFACT_HASH_DRIFT` |
| Init/Plan | `STATE_EXISTS`, `FILE_NOT_FOUND`, `RUBRIC_SNAPSHOT_EXISTS`, `INVALID_PLAN`, `INVALID_PLAN_TASKS`, `INVALID_PLAN_TASK`, `DUPLICATE_TASK_ID`, `INVALID_OWNERSHIP_PATH`, `DUPLICATE_OWNERSHIP_PATH` |
| Git/range | `INVALID_REPO`, `GIT_ERROR`, `INVALID_SHA`, `HEAD_MISMATCH`, `HEAD_NOT_CHANGED`, `NOT_ANCESTOR`, `BASE_MISMATCH`, `OWNERSHIP_VIOLATION` |
| Lifecycle | `UNKNOWN_TASK`, `INVALID_TRANSITION`, `REPORT_NOT_FOUND`, `INVALID_GATE`, `UNKNOWN_COMMAND`（非法 `advance-gate --result` 由当前 helper 以 `INVALID_RESULT` 报告） |
| Review/fix | `INVALID_OBSERVATION_SCHEMA`, `INVALID_FINDING_SCHEMA`, `INVALID_CLOSURE_EVIDENCE`, `RUBRIC_MISMATCH`, `ATTEMPT_MISMATCH`, `FINDING_ID_COLLISION`, `MISSING_TARGETED_FINDING`, `VERDICT_FINDING_MISMATCH`, `INVALID_CONTROLLER_RESOLUTION`, `INVALID_FIX_REPORT`, `INVALID_FINDING_IDS`, `FINDING_SET_MISMATCH`, `FIX_BUDGET_EXHAUSTED` |
| Artifact output | `OUTPUT_EXISTS` |

Workflow HALT statuses 包括：`HALTED_CONTRACT_DISPUTE`、`HALTED_NEEDS_DECISION`、
`HALTED_SCOPE_BLOCKED`、`HALTED_NO_PROGRESS`、`HALTED_REGRESSION`、
`HALTED_BUDGET_EXHAUSTED`。它们的 next-action 一律为 `HALT`。

## Controller Pseudocode

```text
record INITIAL_BASE
run bounded Pre-Flight once for the confirmed Plan
if conflicts: present all to user; return Phase 3; do not init
resolve an existing read-only rubric source; require absent snapshot/state targets
helper init creates state and rubric snapshot; Controller creates neither

loop:
  result = helper next-action(state)
  action = result.action

  if action == DISPATCH_IMPLEMENTER:
    if state says READY: helper start-task(expected current_head)
    dispatch/resume fresh implementer with absolute artifact paths and task.meta.model
    save raw report; helper record-implementation

  elif action == DISPATCH_REVIEWER:
    helper review-package(task_base, task_head, new attempt path)
    dispatch fresh task reviewer
    save raw JSON; helper import-review

  elif action == DISPATCH_FIXER:
    if state says FIX_REQUIRED:
      helper needs-fix
      helper authorize-fix(exact complete finding ID set)
    dispatch/resume fixer for the state-authorized attempt
    save raw JSON report; helper record-fix

  elif action == RUN_FINAL_REVIEW:
    if eval-prompts does not exist: generate it from the frozen Spec
    helper review-package(initial_base, current_head, new attempt path)
    dispatch fresh final reviewer with the last Task task.meta.model
    save raw JSON; helper import-review

  elif action == RUN_STRUCTURAL_VALIDATION:
    run same applicable commands at initial_base and current_head
    save schema-v1 observation; helper import-review

  elif action == RUN_BEHAVIORAL_VALIDATION:
    for each eval case: dispatch with its owner Task task.meta.model and explicit flags
    save schema-v1 observation; helper import-review

  elif action == REQUEST_SQUASH_APPROVAL:
    ask user now; execute only the chosen completion branch; helper advance-gate

  elif action == COMPLETE:
    report persisted terminal status and evidence; stop

  elif action == HALT:
    report persisted status, ledger evidence, budget and decision needed; stop

  else:
    stop as protocol error

  helper next-action(state)
```

顺序不可调换：调用 `next-action` → 只执行返回动作 → 保存 agent 原始 JSON/report →
helper `import-review`/`record-*` → 再调用 `next-action`。Controller 不以自然语言 summary
跳转。Structural/behavioral 的 observation 也进入同一 ledger/shared budget。

Behavioral flags 由 Delta Spec 机械决定：只有 Routing/Gate 改动时
`run_consistency=true`，且只追加一次重跑；只有 Changed 包含 Pattern/Architecture 时
`run_baseline=true`。任一 flag 为 false 时对应维度必须输出 `SKIP`，不得 spawn 或追加运行。
Eval 必须像其他 agent 一样接收绝对 state/brief/report/review-package/observation 路径、
`scope`、`ticket`、`task_id: null`、显式 flags，以及 Plan acceptance index。每个
trajectory/adversarial case 归属产生该合同的 Task，并逐字使用其 `meta.model`；无法唯一
归属的 case 在 Phase 3 Pre-Flight 交用户裁定，不进入初始化后的 run。

## Red Flags

- “Agent 说 PASS，所以直接标 Task complete。”
- “这次 API timeout，凭记忆再给一个 fix attempt。”
- “Validation 有自己的两轮额度。”
- “Final finding 跨两个 owner，先选比较像的那个修。”
- “把 baseline debt 顺手算作本次 blocker。”
- “更新 rubric snapshot/hash 以消除 drift。”
- “Fixer 的报告足以把 finding 设为 RESOLVED。”
- “Package 太大，改看最后一个 commit。”
- “Final reviewer 可以再 delegate 一层。”
- “全部检查看起来通过，不等 helper 就 squash。”
