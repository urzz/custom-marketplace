# 提交策略与执行合同

本文定义 commit skill 的消息生成、授权、选择性暂存、单次提交、失败处理和结果验证合同。调用方必须先完成逐路径分类、消息生成与授权判定；本文不链接其他 reference，也不授权修改工作树内容。

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

1. 必须生成恰好一个 Conventional Commit，不得生成多个 commit 方案作为默认执行结果。
2. subject 使用 `type(scope): summary`；没有可信 scope 时使用 `type: summary`。
3. type 必须从 `feat`、`fix`、`docs`、`refactor`、`test`、`build`、`ci`、`chore`、`perf`、`style`、`revert` 中按实际主要影响选择。
4. summary 必须简洁、使用祈使或描述式短语均可，但不得加句号，不得编造业务意图。
5. scope 只能来自可信路径、模块、插件、包名或用户明确说明；无法可信判断时省略。
6. body 只在需要解释多主题、破坏性影响、风险、迁移或用户要求时生成。
7. 多个独立主题仍只允许一个 commit：用影响最大的主题决定 subject，其余主题在 body 中用项目符号记录，并显式提示原子性较弱。
8. 没有变更、`include` 为空或无法形成可信意图时直接结束，不生成空提交。

## 授权合同

授权判定必须在分类与消息生成后、任何 Git mutation 前完成。authorized include set/message 同时覆盖两种来源：通过全部 auto-execution eligibility 的本轮 `default-auto` 自动授权，或用户在显式 preview/approval-only 路径给出的明确批准。

- `default-auto`：仅当 eligibility 全部满足、mandatory-stop 为空、include 非空、uncertain 为空、状态/diff/分类证据新鲜且 exact subject/body 可信时，才授权 exact include set 与 exact subject/body；自动模式不是风险接受。
- 显式 `preview/approval-only`：必须等待用户批准 exact include set 与 exact subject/body 后才能授权；模糊同意、只批准消息或只批准路径均不足以执行。
- 显式 `analysis-only`：禁止 staging、commit 或任何 Git mutation；只能输出分析、消息建议、eligibility 与安全下一步。
- 授权失效：状态、diff、分类、消息、eligibility 或用户风险裁定发生变化时，现有授权立即失效，必须回到分析、消息生成与授权判定。
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

1. 在暂存前记录执行前 HEAD、execution mode、authorized include set 与 authorized message。
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

任何边界漂移都不得自动修复为新的提交；必须回到分析与授权。

## 创建提交

通过边界验证后，只创建一个 commit。commit message 必须与 authorized message 的 subject/body 一致；若 body 为空，只使用 subject；若 body 存在，保持授权时的完整内容。commit 命令失败时报告 exit code、关键信息、当前 staged paths 与工作区遗留状态；不得规避性重试，不得绕过 hooks 或签名。

## 成功验证

提交命令成功后，必须从 Git truth 读取并验证：

1. 新 HEAD 与执行前 HEAD 不同。
2. 相对执行前 HEAD 恰好新增一个 commit。
3. 新 commit subject 与 authorized subject 精确一致。
4. body 存在性与 authorized body 一致；若有 body，内容不得丢失关键项目符号。
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
