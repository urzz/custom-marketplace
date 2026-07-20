# 提交策略与执行合同

本文定义 commit skill 的 provisional message/intent、最终消息生成、授权、选择性暂存、单次提交、失败处理和结果验证合同。调用方必须先完成逐路径分类、provisional message/intent 与授权判定；本文不链接其他 reference，也不授权修改工作树内容。最终 Conventional Commit 的 type、scope、summary 与 body 的唯一语义来源是完成选择性暂存并重新验证 index 边界后读取的最终 staged diff。

## Contents

- [消息合同](#消息合同)
- [授权合同](#授权合同)
- [Git 安全合同](#git-安全合同)
- [选择性暂存流程](#选择性暂存流程)
- [Index 边界验证](#index-边界验证)
- [创建提交](#创建提交)
- [成功验证](#成功验证)
- [结果输出](#结果输出)

## 消息合同

1. 必须创建恰好一个 Conventional Commit，不得生成多个 commit 方案作为默认执行结果。
2. 暂存前只能形成 provisional message/intent，用于分类复核、preview 展示和授权语义边界；它不是最终 authorized message。
3. 选择性暂存后必须重新读取最终 staged diff；final message 的 type、scope、summary 与 body 中每一项语义都必须由该最终 staged diff 支撑，且该 diff 是唯一语义来源。
4. 禁止读取 git log 或历史 commit message 来推断消息风格或语义；Conventional Commits 只提供固定格式、type 枚举和 subject/body 结构。
5. 禁止使用 ticket、用户陈述、当前会话内容、仓库文档、历史提交、暂存前 staged/unstaged diff、untracked 安全摘要或 provisional message/intent 补充最终消息语义。
6. subject 使用 `type(scope): summary`；没有由最终 staged diff 可信支撑的 scope 时使用 `type: summary`。
7. type 必须从 `feat`、`fix`、`docs`、`refactor`、`test`、`build`、`ci`、`chore`、`perf`、`style`、`revert` 中按最终 staged diff 呈现的实际主要影响选择。
8. summary 必须简洁、使用祈使或描述式短语均可，但不得加句号，不得编造业务意图。
9. scope 只能来自最终 staged diff 中可信呈现的路径、模块、插件或包名；无法可信判断时省略。
10. body 只在最终 staged diff 支撑多主题、破坏性影响、风险或迁移说明时生成；用户要求本身不能成为 body 语义。
11. 多个独立主题仍只允许一个 commit：用最终 staged diff 中影响最大的主题决定 subject，其余由最终 staged diff 支撑的主题在 body 中用项目符号记录，并显式提示原子性较弱。
12. 没有变更、`include` 为空、最终 staged diff 为空或最终 staged diff 无法形成可信消息时直接结束，不生成空提交，也不得从其他来源补全。

## 授权合同

授权判定必须在分类与 provisional message/intent 形成后、任何 Git mutation 前完成。此时只授权 exact include set 与语义边界，不授权最终 commit message；最终 authorized message 必须在 index 固定后仅由最终 staged diff 生成。

- `default-auto`：仅当 eligibility 全部满足、mandatory-stop 为空、include 非空、uncertain 为空、状态/diff/分类证据新鲜且 provisional message/intent 可信时，才授权 exact include set 与 provisional 语义边界；自动模式不是风险接受。
- 显式 `preview/approval-only`：必须在 Git mutation 前等待用户批准 exact include set 与 provisional message/intent 的语义边界；模糊同意、只批准消息或只批准路径均不足以执行。
- 显式 `analysis-only`：禁止 staging、commit 或任何 Git mutation；只能输出分析、provisional message/intent、eligibility 与安全下一步。
- 授权失效：状态、diff、分类、provisional message/intent、eligibility 或用户风险裁定发生变化时，现有授权立即失效，必须回到分析、provisional message/intent 形成与授权判定。
- 最终消息漂移：final message 若与已批准语义边界不一致，必须停止并重新进入所需的人类裁定；不得静默扩大语义或把用户描述补入最终消息。
- 资格失败或 mandatory-stop：必须停止在 Human-in-the-Loop，报告失败证据和最小裁定问题；不得部分自动执行或扩大授权范围。

## Git 安全合同

- 禁止使用全量或不加边界的暂存命令，包括 `git add -A`、`git add .`、`git add --all`、`git add :/` 及等价模式。
- 只能对 authorized include set 中的路径执行路径级暂存；每条命令必须显式列出 authorized 路径或使用受控 pathspec 文件。
- 授权删除必须通过路径级方式反映到 index，例如对已确认删除路径使用 `git add -- <path>` 或同等路径限定形式。
- 不得纳入 `exclude`、`uncertain`、ignored、未授权、疑似敏感或风险未确认路径。
- 不得修改工作树文件，不得格式化、生成、删除或修补内容来让提交成功。
- 不得执行 push、fetch、pull、merge、rebase、reset、revert、amend、squash、tag、switch、clean、Git config 修改或任何历史改写操作。
- 不得使用绕过 hooks 或签名要求的参数，例如 `--no-verify`；hooks 或签名失败时必须保留现场并报告。
- 不得使用签名绕过或关闭验证的方式创建提交；不得创建空提交。
- 不得因为用户要求“提交一下”就在无可信变更时提交。
- 边界漂移必须回到分析与授权，不能扩大暂存、自动修复或用破坏性命令清理现场。

## 选择性暂存流程

1. 在暂存前记录执行前 HEAD、execution mode、authorized include set 与已批准语义边界；不得把 provisional message/intent 记录为最终 authorized message。
2. 对 authorized include set 按路径执行暂存，确保 shell quoting 或 pathspec 处理不会扩大匹配范围。
3. 对 untracked include 路径，先确认仍存在且仍与授权摘要一致。
4. 对 delete include 路径，确认删除仍存在于 Git 状态，并用路径级暂存记录删除。
5. 暂存命令失败时立即停止；不尝试扩大暂存范围，不使用破坏性清理。

## Index 边界验证

暂存后必须重新读取 staged paths 与 staged diff，并验证：

- staged path 集合与 authorized include set 完全一致；rename 应按 Git committed path 表示与授权记录对应。
- staged diff 只包含授权摘要所覆盖的内容，没有混入 exclude、uncertain 或未授权路径。
- unstaged 中残留的 exclude/uncertain 不影响 index 边界，但必须在最终报告中列出。
- 若路径在授权后发生变化、消失或新增未授权内容，立即停止，不 commit。
- 边界通过后，才可从最终 staged diff 生成 authorized final Conventional Commit message；该 diff 是 type、scope、summary 与 body 的唯一语义来源。
- 若最终 staged diff 无法支撑可信消息，或 final message 与已批准语义边界不一致，立即停止并回到所需的人类裁定。

任何边界漂移都不得自动修复为新的提交；必须回到分析与授权。

## 创建提交

通过边界验证并从最终 staged diff 生成 authorized final message 后，只创建一个 commit。commit message 必须与 authorized final message 的 subject/body 一致；若 body 为空，只使用 subject；若 body 存在，保持 final message 的完整内容。commit 命令失败时报告 exit code、关键信息、当前 staged paths 与工作区遗留状态；不得规避性重试，不得绕过 hooks 或签名。

## 成功验证

提交命令成功后，必须从 Git truth 读取并验证：

1. 新 HEAD 与执行前 HEAD 不同。
2. 相对执行前 HEAD 恰好新增一个 commit。
3. 新 commit subject 与 authorized final subject 精确一致。
4. body 存在性与 authorized final body 一致；若有 body，内容不得丢失关键项目符号。
5. 新 commit 中的路径集合与 authorized include set 一致。
6. 工作区仍留存的 exclude 与 uncertain 变更被列出，且没有被提交。
7. 无论 `default-auto` 还是 preview/approval-only，整个工作流只创建一个 Conventional Commit。

只有所有验证满足时，才可报告提交成功。任一验证失败都必须说明不能宣称成功，并提供不一致证据。

## 结果输出

成功输出必须包含：

- execution mode。
- commit hash。
- 完整 subject。
- body 是否存在。
- 实际 committed paths。
- 执行前 HEAD 与执行后 HEAD。
- 仍留在工作区的 exclude/uncertain 路径。
- Git truth 验证结论，包括 exact commit count、exact subject/body、exact committed path set，以及 excluded/uncertain 未被提交。

停止或失败输出必须包含：

- 停止阶段。
- 资格失败或 mandatory-stop 证据，包括受影响路径或状态摘要但不泄漏敏感值。
- 已执行与未执行的副作用。
- 当前 staged paths。
- 工作区遗留变更。
- 用户下一步可选择的最小安全操作。
