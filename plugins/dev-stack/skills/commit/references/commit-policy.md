# 提交策略与执行合同

本文定义 commit skill 的消息生成、选择性暂存、单次提交、失败处理和结果验证合同。调用方必须先完成逐路径分类与审批；本文不链接其他 reference，也不授权修改工作树内容。

## 消息合同

1. 必须生成恰好一个 Conventional Commit，不得生成多个 commit 方案作为默认执行结果。
2. subject 使用 `type(scope): summary`；没有可信 scope 时使用 `type: summary`。
3. type 必须从 `feat`、`fix`、`docs`、`refactor`、`test`、`build`、`ci`、`chore`、`perf`、`style`、`revert` 中按实际主要影响选择。
4. summary 必须简洁、使用祈使或描述式短语均可，但不得加句号，不得编造业务意图。
5. scope 只能来自可信路径、模块、插件、包名或用户明确说明；无法可信判断时省略。
6. body 只在需要解释多主题、破坏性影响、风险、迁移或用户要求时生成。
7. 多个独立主题仍只允许一个 commit：用影响最大的主题决定 subject，其余主题在 body 中用项目符号记录，并显式提示原子性较弱。
8. 没有变更、`include` 为空或无法形成可信意图时直接结束，不生成空提交。

## 审批合同

默认路径下，必须在任何 Git mutation 前展示完整提案并等待用户明确批准 exact include set 与 exact subject/body。用户批准后，若状态、diff、分类或消息任一项发生变化，批准失效，必须重新展示提案。明确直接执行偏好只在当前请求或当前会话有效，且不能绕过 mandatory-stop。

## Git 安全合同

- 禁止使用全量或不加边界的暂存命令，包括 `git add -A`、`git add .`、`git add --all`、`git add :/` 及等价模式。
- 只能对用户批准的 `include` 路径执行路径级暂存；每条命令必须显式列出批准路径或使用受控 pathspec 文件。
- 批准的删除必须通过路径级方式反映到 index，例如对已确认删除路径使用 `git add -- <path>` 或同等路径限定形式。
- 不得纳入 `exclude`、`uncertain`、ignored、未批准、疑似敏感或风险未确认路径。
- 不得修改工作树文件，不得格式化、生成、删除或修补内容来让提交成功。
- 不得执行 push、fetch、pull、merge、rebase、reset、revert、amend、squash、tag、switch、clean、Git config 修改或任何历史改写操作。
- 不得使用绕过 hooks 或签名要求的参数，例如 `--no-verify`；hooks 或签名失败时必须保留现场并报告。
- 不得创建空提交；不得因为用户要求“提交一下”就在无可信变更时提交。

## 选择性暂存流程

1. 在暂存前记录执行前 HEAD 与批准 include 集。
2. 对批准 include 集按路径执行暂存，确保 shell quoting 或 pathspec 处理不会扩大匹配范围。
3. 对 untracked include 路径，先确认仍存在且仍与批准摘要一致。
4. 对 delete include 路径，确认删除仍存在于 Git 状态，并用路径级暂存记录删除。
5. 暂存命令失败时立即停止；不尝试扩大暂存范围，不使用破坏性清理。

## Index 边界验证

暂存后必须重新读取 staged paths 与 staged diff，并验证：

- staged path 集合与批准 include 集完全一致；rename 应按 Git committed path 表示与批准记录对应。
- staged diff 只包含批准摘要所覆盖的内容，没有混入 exclude 或 uncertain。
- unstaged 中残留的 exclude/uncertain 不影响 index 边界，但必须在最终报告中列出。
- 若路径在审批后发生变化、消失或新增未批准内容，立即停止，不 commit。

任何边界漂移都不得自动修复为新的提交；必须回到分析与审批。

## 创建提交

通过边界验证后，只创建一个 commit。commit message 必须与用户批准的 subject/body 一致；若 body 为空，只使用 subject；若 body 存在，保持展示时的完整内容。commit 命令失败时报告 exit code、关键信息、当前 staged paths 与工作区遗留状态；不得规避性重试，不得绕过 hooks 或签名。

## 成功验证

提交命令成功后，必须从 Git truth 读取并验证：

1. 新 HEAD 与执行前 HEAD 不同。
2. 相对执行前 HEAD 恰好新增一个 commit。
3. 新 commit subject 与批准 subject 精确一致。
4. body 存在性与批准内容一致；若有 body，内容不得丢失关键项目符号。
5. 新 commit 中的路径集合与批准 include 集一致。
6. 工作区仍留存的 exclude 与 uncertain 变更被列出，且没有被提交。

只有所有验证满足时，才可报告提交成功。任一验证失败都必须说明不能宣称成功，并提供不一致证据。

## 结果输出

成功输出必须包含：

- commit hash。
- 完整 subject。
- body 是否存在。
- 实际 committed paths。
- 执行前 HEAD 与执行后 HEAD。
- 仍留在工作区的 exclude/uncertain 路径。
- “已从 Git truth 验证”的说明。

停止或失败输出必须包含停止阶段、触发条件、已执行与未执行的副作用、当前 staged paths、工作区遗留变更，以及用户下一步可选择的安全操作。
