# Context Manifest Protocol

## Contents
- [Purpose](#purpose)
- [Files and JSONL Shape](#files-and-jsonl-shape)
- [Implement Manifest](#implement-manifest)
- [Validation and Extraction](#validation-and-extraction)
- [Worker Loading Contract](#worker-loading-contract)
- [Verify Manifest](#verify-manifest)
- [Context Budget](#context-budget)
- [Forbidden Inputs](#forbidden-inputs)

## Purpose

Context manifest 声明某个 stage 可以加载哪些 stable context。它防止 implementation 和 verification 继承完整 conversation history、全量项目文档或与当前 Task 无关的源文件。

Manifest 是只读 stable project/change context 的声明，不是内容缓存，也不授予任何写权限。读取某路径不等于允许修改该路径；实际 mutation scope 由 Task acceptance 与 reviewer scope verdict 约束。Task-local source discovery 使用后文单一规则，不要求把每个源文件预先列入 manifest。Snapshot、fingerprint、state lifecycle、Design reapproval replacement 与 Verify/Fold freshness 的唯一 authority 是 `protocol.md`；本文件只定义 context 声明和加载边界。

## Files and JSONL Shape

```text
.dev-docs/changes/<change-id>/context/
  implement.jsonl
  verify.jsonl
```

每个非空行必须是一个 JSON object。Required fields 精确为：

```text
path
kind
mode
reason
```

示例：

```json
{"path":".dev-docs/project/brief.md","kind":"project","mode":"required","reason":"理解项目目标和边界","tasks":["*"]}
```

字段合同：

- `path`：仓库相对的单个文件路径，只声明目标，不内联内容。
- `kind`：context 类别，必须是 strip 后非空字符串；helper fail closed 校验 shape，但保持开放字符串，不设 allowlist。
- `mode`：只允许 `required` 或 `jit`。
- `reason`：为什么 acceptance 需要该 context，必须是 strip 后非空字符串；helper fail closed 校验 shape，但保持开放字符串，不设 allowlist。
- `tasks`：Implement entry 的 Task scope；值为非空字符串数组，成员只允许 `"*"` 或 `plan.yaml` 中存在的 Task id。

## Implement Manifest

`implement.jsonl` 可以包含：

- 当前 Task 需要的 project brief 或 principles。
- 当前 Task 需要的 architecture constraints。
- engineering testing guidance。
- 当前 change 的 focused spec/design/plan context。
- focused research notes。
- 作为只读 navigation hints 的关键 contract/schema/interface files；它们不构成 mutation allowlist。

### Task-Level Scope

所有 **new implement entries** 必须显式写 `tasks`：

```json
{"path":".dev-docs/changes/2026-07-09-example/spec.md","kind":"change","mode":"required","tasks":["*"],"reason":"所有 Tasks 都需要 acceptance criteria"}
{"path":"src/contracts/example.ts","kind":"source","mode":"jit","tasks":["T2"],"reason":"T2 acceptance 需要核对接口"}
```

规则：

- `tasks: ["*"]` 表示 shared entry，适用于所有 Tasks。
- `tasks: ["T1", "T2"]` 只适用于列出的 Task ids。
- 缺失 `tasks` 只用于 backward compatibility；validator 将其规范化并视为 `tasks: ["*"]`。
- Validator 无法辨别缺失 `tasks` 是 legacy artifact 还是新产物遗漏，这是已知兼容限制；Design 生成的新 implement entries 必须显式写 `tasks`。
- 不得以 backward compatibility 为理由创建新的无 `tasks` entry。
- Worker 不得加载仅属于 unrelated Tasks 的 entry。

## Validation and Extraction

在任何 Task dispatch 前运行 `task-helper.py validate-change --change <change-dir>`。它校验：

- `state.json`、`plan.yaml`、`context/implement.jsonl`、`context/verify.jsonl` 的固定输入存在且可解析。
- Plan Task shape、Task ids、依赖引用与依赖环。
- Manifest JSONL object shape、required fields 与 `mode`。
- `path` 的安全形状。
- `tasks` 中的 Task ids 是否存在于 Plan。

`task-helper.py extract-task --change <change-dir> --task <task-id> --output <task-brief-path>`：

- 只选择 `tasks` 包含 `"*"` 或 matching Task id 的 Implement entries。
- 保持 manifest 声明顺序并将规范化 entry 写入 Task brief。
- 只写调用者指定的 task brief，不创建其他 evidence，不修改 state。

Helper **只验证声明**。它不打开、读取或验证 `path` 指向的 target content；真正加载由 worker 按本协议执行。

在每个 Task dispatch 前，Controller 必须对 extract 后 matching `mode=required` targets 逐一检查存在性与可读性；此检查属于 Controller，不改变 helper 的声明验证边界：

- 仅匹配当前 Task 的 required target 缺失/不可读：在 dispatch 和 attempt 递增之前追加 blocker evidence，执行精确 pre-dispatch Task-local blocked transition。`tasks.<id>.status=blocked`；`current_task` 可记录 `{id,attempt:<当前已持久 attempts，首次未 dispatch 时为 0>,status:blocked}`；不得递增 attempt。随后跳过其 transitive dependents并继续独立 eligible Tasks。
- `tasks:["*"]` shared/change-wide required target 缺失/不可读、manifest invalid，或 immutable approved control-plane hash drift：change-level STOP，不得把它伪装成单 Task blocker。

Task-local target 经 Design/Plan/context 修正后必须重新 explicit Design approval，再按 File Protocol 的 Design reapproval transition 完整替换 immutable control-plane map 并回 pending；本文件不复制 replacement/state patch。临时读取权限问题若 target 声明/内容均未变，可在 resolved evidence 后按 File Protocol 的临时 blocker unblock。

## Worker Loading Contract

每个 fresh implementer/fixer 必须遵循：

1. 先读取 task brief。
2. 载入所有 matching `mode=required` entries。
3. `mode=jit` 只在具体 acceptance、verification 或 blocker 需要时加载；不得预加载全部 jit entries。
4. Task-local source discovery 只允许从 acceptance、`files_hint`、已知 symbol/import 或 direct caller chain 出发，读取满足 Task 所需的最小源码集合；禁止 repository root、module-wide 或 broad sibling scan。读取的每条源码路径必须在 `Loaded Context` 标明来源（acceptance/files_hint/symbol/import/direct caller）与理由。
5. 需要未声明的 stable Design/project knowledge、跨 Task/architecture boundary 源码，或必须 broad discovery 才能继续时，worker 返回 `NEEDS_CONTEXT`，由 Design 收紧 manifest/Task；不得自行扩大。
6. 不得读取 unrelated manifest entries。
7. 在 `evidence/tasks/<task-id>/implementer.md` 写 `Loaded Context`：
   - 所有 manifest 与 task-local discovery 实际载入文件的 project-relative path、来源与理由。
   - 每个 matching 但未载入的 jit entry 及 skip reason。
   - 对缺失或无法读取的 required path，记录 blocker，不得静默跳过。
8. Fixer 必须基于 reviewer package 与仍匹配的最小 context 工作，不继承完整先前 transcript。

`Loaded Context` 记录路径和原因，不复制文件全文。

## Verify Manifest

`verify.jsonl` 通常包含：

- testing guidance。
- 当前 change spec acceptance criteria。
- plan Task acceptance criteria。
- verification 必须检查的 explicit architecture constraints。

Verification 还必须检查当前 diff 与持久 evidence。

Verify manifest 应小于 Implement manifest。优先用更少、更聚焦的 entries 表达这个约束；若两者不能仅凭 entry count 比较（例如少量 Verify entry 指向更大的文件），controller 必须在 `evidence/review.md` 中记录 `bloated-context` 风险、原因与影响，不得声称已证明 Verify context 更小。

## Context Budget

推荐 context budget：

| Stage | Recommended upper bound |
|---|---:|
| SessionStart breadcrumb | < 1k |
| Brief | 20k-40k |
| Design | 40k-80k |
| Implement single task | 30k-60k |
| Verify | 20k-40k |
| Fold | 20k-40k |

MVP 不自动 token count，不产出 token reporting；budget 仍是 controller 与 worker 必须主动遵守的行为约束。Manifest 过宽时应拆分或摘要，而不是引入 runtime/RAG 自动加载。

## Forbidden Inputs

Manifest `path` 禁止：

- absolute paths，包括 POSIX、Windows drive 与 UNC 形式。
- `..` traversal。
- glob 字符或 patterns。
- 目录式路径、尾随 `/`。
- broad roots，例如 `.`、`.dev-docs` 或等价形式。

Manifest 内容与 worker context 禁止：

- 完整聊天记录或 full conversation history。
- all-doc / all `.dev-docs` 加载。
- all-source / 全仓 source 加载。
- raw logs 或长篇 test output dumps。
- proposal/comment/reviewer history 与完整 review/session history。
- session journals、daemon task history 或 runtime traces。
- 仅属于 unrelated Tasks 的 entries。

需要更广信息时，STOP 并回到 Design 收紧 Task brief/manifest；不得由 worker 自行扩大 scope。
