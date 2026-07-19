# Context

`context.jsonl` 是 bounded read authority。每行是一个 JSON object，描述谁可以为了什么原因读取哪个稳定或 JIT context。写授权只来自 Contract 中的 `mutation_targets`，context 条目永远不授权写入。

## 每行字段

每行必须包含：

- `id`：稳定条目 id，供 Contract、packet 和 evidence 引用。
- `audience`：允许消费该 context 的角色，只能是 `contract`、`worker`、`reviewer`、`completion`、`finish`。
- `mode`：`stable` 或 `jit`。
- `path`：项目相对路径，不能是绝对路径，不能路径穿越，不能 glob。
- `reason`：为什么需要该 context，必须具体说明与当前 change 的关系。

## stable context

`mode: stable` 表示 context 内容已固定到 fingerprint。stable 条目必须携带：

- `sha256`：内容 SHA-256，使用 64 位小写 hex。
- 可选 `line_range`：读取范围，包含正整数 `start` 与 `end`。

Stable context 适合 Contract、worker packet、review packet 或 completion proposal 使用；如果内容 hash 改变，依赖它的 approval 或 packet 不再 fresh。

## jit context

`mode: jit` 表示只在触发条件满足时读取。jit 条目必须携带：

- `retrieval_trigger`：明确触发条件，例如 “reviewer needs declared interface for path X”。
- `budget`：正整数预算；helper 解释预算单位并 fail closed。

JIT context 必须保持 bounded；它不能成为读取整个仓库或历史对话的授权。

## 禁止内容

Context 条目不得包含或授权：

- full conversation、chat history 或 raw transcript。
- all docs、all source、整个仓库、宽泛目录根或未限定递归读取。
- raw logs、terminal scrollback 或不可复现 agent summary。
- unrelated tasks、其它 change 的私有 packet/evidence，除非 Contract 明确将其列为 handoff。
- 绝对路径、路径穿越、glob pattern、home directory shortcut 或 repository 外路径。

## Helper 责任

Schema 约束字段 shape、枚举、必填与条件字段。Helper 必须 fail closed 校验 path 语义、budget 语义、line range、hash match、audience 使用、context fingerprint 与 Contract/packet/evidence identity 是否一致。
