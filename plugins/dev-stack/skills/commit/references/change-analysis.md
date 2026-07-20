# 变更分析协议

本文定义 commit skill 的完整盘点、逐路径分类与 auto-execution eligibility 协议。调用方必须先获得完整 Git 状态，再按本文对每个 changed path 生成可审查证据；本文不链接其他 reference，也不定义提交执行策略。本文产出的用户请求、当前会话说明、路径状态、各状态面 diff 与 untracked 安全摘要只可用于主意图推断、逐路径分类、风险和暂存边界，不得直接成为最终 commit message 语义；最终消息只能由选择性暂存后重新读取的最终 staged diff 决定。

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
3. changed paths、diff 摘要与文件命名共同呈现的单一主题。
4. 已 staged 内容与 unstaged/untracked 内容之间稳定一致的语义关系。

这些证据只用于判断本次提交的候选边界、风险和 provisional intent/message，不得直接写入最终 commit message，也不得在最终 staged diff 无法支撑时补充 type、scope、summary 或 body 语义。若这些证据无法形成高置信度主题，必须标记低置信度意图并停止等待用户补充；不得为了生成 commit message 而编造业务目的。

## 分类规则

- `include`：路径与主意图直接相关，摘要显示它是该提交必要组成部分，且不存在未解决风险。
- `exclude`：路径明显无关、属于临时文件、另一个主题、用户未批准范围、ignored 候选，或不应进入本次 commit。
- `uncertain`：路径可能相关但证据不足、摘要无法安全确认、同时包含相关和无关片段、意图关联不清，或需要用户判断。

每个 changed path 必须恰好归入一个分类；不得重复列入多个分类，也不得遗漏。若一个路径的 staged 部分相关而 unstaged 部分无关，必须把边界风险讲清楚；当 path-level staging 无法表达行级边界时，auto-execution eligibility 失败，必须进入 Human-in-the-Loop。

## 特殊状态规则

- staged：读取 staged diff，确认 index 中已存在的内容是否属于主意图；staged 不自动等于 include。
- unstaged：读取 unstaged diff，判断是否也属于主意图；不得因为未暂存就排除。
- untracked：只读取安全摘要，例如文件类型、大小、路径、首层结构或无敏感值的片段；不得展示疑似 secret 内容。
- rename：若 rename 与内容改动共同支持主意图，可 include；若仅移动与主意图不明，标为 uncertain；破坏性或意图不足的 rename 触发 mandatory-stop。
- delete：若删除是主意图的必要结果，可 include；若可能是误删或破坏性变化，mandatory-stop。
- conflict：始终 mandatory-stop，分类为 uncertain，等待用户解决或明确指示后重新盘点。

## 自动执行资格

`auto-execution eligibility` 是独立于分类的布尔结论，必须逐项给出证据。它只表示本轮分析能否授权 exact include set 与 provisional message/intent 语义边界进入选择性暂存；自动资格不是风险接受，也不得把失败项部分自动执行。

只有以下条件全部满足时，eligibility 才为 true：

1. Git 状态、staged/unstaged diff 与 untracked 安全摘要完整可读，且命令结果可解析。
2. 不存在 conflict、无法解释的状态、无法安全读取的路径或分析期间状态/diff 漂移。
3. 主意图高置信，且 provisional message/intent 可信、不编造业务目的；最终消息仍必须等待最终 staged diff 生成。
4. 每个 changed path 都有高置信、唯一的 `include`、`exclude` 或 `uncertain` 分类。
5. `include` 非空，`uncertain` 为空。
6. 不存在疑似 secret、token、password、credential、`.env`、私钥、证书或认证配置。
7. 不存在异常 binary、large、generated、压缩包、数据库、模型权重或 unreadable 项。
8. 不存在 destructive delete/rename 歧义；删除或重命名必须由主意图明确支持。
9. 不存在 staged/unstaged 同路径且 path-level staging 无法表达的行级边界问题。
10. 证据仍新鲜：授权前重新读取的必要状态与分类依据一致。

任一条件失败时，eligibility 为 false，必须阻止自动执行并进入 Human-in-the-Loop 或 analysis-only 结果；不得扩大 include、忽略风险或把自动模式解释为用户接受风险。

## 强制停止确认

出现以下任一情况，必须设置 mandatory-stop，并在任何 staging/commit 前阻止自动执行：

- 疑似 secret、token、password、credential、`.env` 类环境文件、私钥、证书或含认证信息的配置。
- 异常二进制、大文件、生成物、压缩包、数据库、模型权重或无法安全读取的文件。
- merge conflict。
- destructive delete/rename 歧义，或 delete/rename 等可能破坏性变化且意图证据不足。
- 任一路径被分类为 `uncertain`。
- 主意图低置信度，无法形成可信 Conventional Commit。
- 状态或 diff 在分析期间发生变化，导致证据可能过期。
- staged/unstaged 同路径边界歧义，且路径级暂存无法安全表达授权边界。

强制停止时只展示风险摘要与路径，不展示敏感值本身，不把风险路径静默纳入 include；输出必须提出用户需要回答的最小问题，例如“是否排除该路径”“是否确认删除属于本次提交”“是否改为只分析”。

## 输出清单

分析输出必须包含：

- 主意图与置信度。
- `include` 清单：路径、状态、证据、理由。
- `exclude` 清单：路径、状态、证据、理由。
- `uncertain` 清单：路径、状态、风险、需要用户回答的问题。
- 多主题判断：是否存在多个独立主题，以及原子性风险。
- mandatory-stop 列表：触发原因、路径与后续需要的最小用户确认。
- auto-execution eligibility：布尔结论、每项资格的 pass/fail 证据、失败项对应路径或状态摘要。

若没有 changed path，输出“无可提交变更”并结束；若所有路径都是 exclude 或 uncertain，不得生成可执行 commit 提案。若 mandatory-stop 或 eligibility=false，只展示必要风险摘要、路径和最小裁定问题，不泄漏敏感值。任何分析输出中的主意图、路径理由或 provisional message/intent 都不能作为最终消息语义来源；最终 Conventional Commit 的 type、scope、summary 和 body 必须在选择性暂存与 index 边界验证后，仅由最终 staged diff 支撑。
