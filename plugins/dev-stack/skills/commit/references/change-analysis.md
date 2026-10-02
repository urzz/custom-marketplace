# 变更分析协议

本文定义 commit skill 的完整盘点、逐路径分类与 auto-execution eligibility 协议。调用方必须先获得完整 Git 状态，再按本文对每个 changed path 生成可审查证据；本文不链接其他 reference，也不定义提交执行策略。`default-auto` 的目标是让安全候选继续执行：路径级风险应被隔离并报告，不应因为一个风险路径阻塞其他可安全提交的路径。本文产出的用户请求、当前会话说明、路径状态、各状态面 diff 与 untracked 安全摘要只可用于主意图推断、逐路径分类、风险和暂存边界，不得直接成为最终 commit message 语义；最终消息只能由选择性暂存后重新读取的最终 staged diff 决定。

## Contents

- [状态盘点](#状态盘点)
- [每路径证据](#每路径证据)
- [主意图推断](#主意图推断)
- [分类规则](#分类规则)
- [特殊状态规则](#特殊状态规则)
- [自动执行资格](#自动执行资格)
- [强制停止确认](#强制停止确认)
- [输出清单](#输出清单)

## 状态盘点

1. 读取仓库根目录与执行前 HEAD，记录当前分支名仅用于报告，不据此扩大范围。
2. 使用 Git 状态区分 staged、unstaged、untracked、rename、delete、conflict；ignored 文件默认不进入候选集合。
3. 对同一路径同时存在 staged 与 unstaged 的情况，必须记录为同一 changed path 的两个状态面，不能只看 index。
4. rename 必须记录旧路径、新路径、相似度或 Git 提供的 rename 标记；delete 必须记录被删除路径与所在状态面。
5. conflict 状态必须进入 mandatory-stop；不得尝试自动解决，也不得从冲突内容中抽取敏感片段。
6. 若状态命令失败或输出无法解析，停止并报告命令结果。

## 每路径证据

每个 changed path 必须收集以下字段：

- 路径：相对仓库根目录的路径；rename 同时记录旧路径与新路径。
- 状态：staged、unstaged、untracked、rename、delete、conflict 的组合。
- 变更摘要：已跟踪文件使用 diff 摘要；untracked 文件使用安全摘要；这些摘要只作为分类、风险和暂存边界证据。
- 内容安全判断：是否疑似密钥、凭据、环境文件、私钥、证书、异常二进制、大文件、生成物或无法安全读取。
- 意图关联证据：说明该路径如何支持、偏离或无法判断是否支持主意图。
- 分类：恰好一个 `include`、`exclude` 或 `uncertain`。
- 理由：一句到三句，必须引用路径、状态、摘要和主意图关系。

不得凭文件名臆造内容；无法读取时只能记录无法读取事实与风险，不得假装已确认安全。

## 主意图推断

主意图可来自以下证据，按可信度从高到低使用：

1. 用户在当前请求中明确说明的修改目的、范围或 ticket。
2. 当前会话中与提交请求直接相关的最近说明。
3. changed paths、diff 摘要与文件命名共同呈现的一个或多个主题。
4. 已 staged 内容与 unstaged/untracked 内容之间稳定一致的语义关系。

这些证据只用于判断本次提交的候选边界、风险和 provisional intent/message，不得直接写入最终 commit message，也不得在最终 staged diff 无法支撑时补充 type、scope、summary 或 body 语义。没有单一主题不再自动触发确认；当请求没有指定范围时，可把多个安全主题作为一个提交候选，并在最终消息中按最终 staged diff 说明多主题和原子性风险。只有无法从安全变更中形成任何可信候选，或候选边界会造成风险内容被纳入时，才暂停等待用户补充。不得为了生成 commit message 而编造业务目的。

## 分类规则

- `include`：路径与请求范围或当前安全变更直接相关，摘要显示它可以作为本次提交的一部分，且不存在未解决风险。
- `exclude`：路径明显无关、属于临时文件、ignored 候选、用户明确排除的范围，或不应进入本次 commit。
- `uncertain`：路径可能相关但证据不足、摘要无法安全确认、同时包含相关和无关片段、意图关联不清，或存在需要单独裁定的风险。

每个 changed path 必须恰好归入一个分类；不得重复列入多个分类，也不得遗漏。`default-auto` 下，`uncertain` 路径应先隔离并留在工作区；只要仍有至少一个安全的 `include` 候选，就继续提交安全子集并在结果中列出 deferred 路径。只有所有候选都为 `uncertain`，或者隔离它需要修改已有 index，才进入 Human-in-the-Loop。若一个路径的 staged 部分安全且相关而 unstaged 部分无关，且 path-level staging 会把两者合并，则该路径按已有 staged 内容归入 `include`，保留现有 index 并延期该路径的 unstaged 内容，不为此要求确认。

## 特殊状态规则

- staged：读取 staged diff，确认 index 中已存在的内容是否安全且属于请求范围；对未指定范围的普通 commit 请求，安全 staged 内容默认作为 include 候选。
- unstaged：读取 unstaged diff，判断是否属于请求范围；安全且未明确排除的路径可以在 `default-auto` 中直接暂存。
- untracked：只读取安全摘要，例如文件类型、大小、路径、首层结构或无敏感值的片段；不得展示疑似 secret 内容。安全的 untracked 文件可以直接纳入，风险文件隔离。
- rename：若 rename 与内容改动共同支持请求范围，可 include；普通清晰 rename 不要求确认；旧路径与新路径关系不清、可能覆盖无关内容或无法安全表达时隔离并停止该路径。
- delete：若删除是请求范围或 diff 明确支持的结果，可 include；普通清晰删除不要求确认；疑似误删、破坏性删除或意图不足时隔离并停止该路径。
- conflict：始终为 workflow-level mandatory-stop，分类为 uncertain，等待用户解决或明确指示后重新盘点。

## 自动执行资格

`auto-execution eligibility` 是独立于分类的布尔结论，必须逐项给出证据。它表示本轮分析能否授权安全的 exact include set 与 provisional message/intent 语义边界进入选择性暂存；它不授权风险路径，也不把失败项静默纳入提交。

只有以下条件全部满足时，eligibility 才为 true：

1. Git 状态、staged/unstaged diff 与 untracked 安全摘要完整可读，且命令结果可解析。
2. 没有 conflict、无法解释的整体状态或分析期间的状态/diff 漂移。单个风险路径可以被隔离，不应拖住无关安全路径。
3. 能从用户范围、路径和 diff 中形成至少一个可信安全候选；可以是一个主题，也可以是多个主题。最终消息仍必须等待最终 staged diff 生成。
4. 每个 changed path 都有唯一的 `include`、`exclude` 或 `uncertain` 分类，并明确记录被隔离的路径。
5. `include` 非空；`uncertain` 可以存在，但只能留在工作区，不能要求通过确认才能继续安全子集。
6. `include` 中不存在疑似 secret、token、password、credential、`.env`、私钥、证书或认证配置。此类路径按路径隔离；若风险内容已经在 index 中且无法不修改 index 地排除，则整个流程停止。
7. `include` 中不存在无法安全处理的异常 binary、large、generated、压缩包、数据库、模型权重或 unreadable 项。可隔离的风险路径不阻塞其他安全路径。
8. destructive delete/rename 歧义不进入 include；普通、清晰且可由 diff 支持的删除或重命名可以自动执行。
9. staged/unstaged 同路径若无法用 path-level staging 表达边界，则保留已有 index、延期该路径的 unstaged 部分；只有已有 index 本身包含风险内容时才停止整个流程。
10. 证据仍新鲜：授权前重新读取的必要状态与分类依据一致。

任一整体条件失败时，eligibility 为 false，才进入 Human-in-the-Loop 或 analysis-only 结果；路径级风险应先被隔离并报告，不得扩大 include、忽略风险或把自动模式解释为用户接受风险。

## 强制停止确认

强制停止分为路径级和 workflow-level 两类。路径级风险只隔离对应路径；存在其他安全 include 时，`default-auto` 继续执行并在结果中报告，不为隔离路径额外询问。以下情况属于路径级 mandatory-stop：

- 疑似 secret、token、password、credential、`.env` 类环境文件、私钥、证书或含认证信息的配置。
- 异常二进制、大文件、生成物、压缩包、数据库、模型权重或无法安全读取的文件。
- destructive delete/rename 歧义，或 delete/rename 等可能破坏性变化且意图证据不足。
- 路径被分类为 `uncertain`，但仍有其他可信安全 include。
- staged/unstaged 同路径边界歧义，且只能通过改变已有 index 才能排除风险的 unstaged 内容。

以下情况属于 workflow-level mandatory-stop，必须在任何 staging/commit 前暂停：

- merge conflict 或无法解释的整体状态。
- 没有任何可信安全 include（全部路径都被隔离、exclude 或 uncertain）。
- 风险内容已经在 index 中，无法在不重置或扩大副作用的情况下排除。
- 主意图和路径边界都无法形成可信 Conventional Commit。
- 状态或 diff 在分析期间发生变化，导致整体证据过期。

停止时只展示风险摘要与路径，不展示敏感值本身；路径级隔离无需等待用户，workflow-level 停止才提出最小裁定问题，例如“是否排除该路径”“是否确认删除属于本次提交”“是否改为只分析”。

## 输出清单

分析输出必须包含：

- 主意图与置信度。
- `include` 清单：路径、状态、证据、理由。
- `exclude` 清单：路径、状态、证据、理由。
- `uncertain` 清单：路径、状态、风险、隔离结果；只有 workflow-level 停止时才附需要用户回答的问题。
- 多主题判断：是否存在多个独立主题，以及原子性风险。
- mandatory-stop 列表：区分路径级隔离和 workflow-level 停止，记录触发原因、路径与后续动作。
- deferred 清单：因同路径 staged/unstaged 边界或风险而保留在工作区的路径。
- auto-execution eligibility：布尔结论、每项资格的 pass/fail 证据、失败项对应路径或状态摘要。

若没有 changed path，输出“无可提交变更”并结束；若所有路径都是 exclude、uncertain 或 deferred，不得生成可执行 commit 提案。路径级 mandatory-stop 或存在可继续的安全候选时，继续执行而不等待确认；只有 workflow-level 停止才展示必要风险摘要、路径和最小裁定问题，不泄漏敏感值。任何分析输出中的主意图、路径理由或 provisional message/intent 都不能作为最终消息语义来源；最终 Conventional Commit 的 type、scope、summary 和 body 必须在选择性暂存与 index 边界验证后，仅由最终 staged diff 支撑。
