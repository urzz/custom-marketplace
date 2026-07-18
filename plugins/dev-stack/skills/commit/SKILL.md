---
name: commit
description: Use when the user asks to analyze staged, unstaged, or untracked Git changes, generate a commit message, safely create one commit, or explicitly requests direct execution of that commit workflow.
---

# Commit

此 skill 用于把当前仓库的 staged、unstaged 与 untracked 变更整理为一个语义清晰、边界受控的 Conventional Commit，并在满足授权条件时安全创建恰好一个 commit。它不适用于历史查看、push、fetch、pull、merge、rebase、amend、squash、reset、revert、tag、switch、clean、配置修改或任何需要改写历史的请求；遇到这些请求时必须说明不处理并停止。

## Composite 工作流

本 skill 采用 Composite 架构：`SKILL.md` 只负责顺序控制、门禁和 reference 读取时机；逐路径分类细则来自 `references/change-analysis.md`；消息、暂存、提交和验证细则来自 `references/commit-policy.md`。Sequential Pipeline 是唯一主干，不得跳步、并行执行副作用或用已有 staged diff 直接生成提交。

## 严格顺序管道

1. **确认 Git 仓库与执行模式**
   - 输入：用户请求、当前会话中明确表达的偏好、当前目录。
   - 输出：仓库根目录、执行前 HEAD、执行模式（默认审批或直接执行候选）。
   - 停止条件：不是 Git 仓库、无法读取 HEAD、请求属于不适用范围，或用户意图只是在询问历史/远端/改写历史。
   - 失败行为：报告原因，不读取不必要内容，不做 Git mutation。
2. **获取完整状态**
   - 输入：仓库根目录。
   - 输出：staged、unstaged、untracked、rename、delete、conflict 与 ignored 排除后的完整路径清单。
   - 停止条件：状态命令失败、存在无法解释的冲突状态，或没有任何 changed path。
   - 失败行为：无变更时直接结束；错误时报告命令结果并停止。
3. **读取 diff 与安全摘要**
   - 输入：完整路径清单。
   - 输出：staged/unstaged diff、untracked 文件的安全摘要、二进制/大文件/无法读取标记。
   - 停止条件：疑似密钥、凭据、环境文件、私钥、证书、异常二进制或大文件、无法安全读取，或冲突内容需要人工判断。
   - 失败行为：不得展示敏感值本身；把相关路径标为 mandatory-stop 并进入审批等待。
4. **读取 `references/change-analysis.md` 并逐路径分类**
   - 输入：用户意图、路径状态、diff/安全摘要。
   - 输出：每个 changed path 恰好进入 `include`、`exclude` 或 `uncertain`，并带简短理由与证据。
   - 停止条件：无法推断可信主意图、任一路径为 `uncertain`、存在强制确认风险。
   - 失败行为：请求用户补充意图或批准边界；不得静默纳入存疑路径。
5. **读取 `references/commit-policy.md` 并生成一个消息**
   - 输入：`include` 集、主意图、分类理由、多主题判断。
   - 输出：恰好一个 Conventional Commit subject，以及必要 body。
   - 停止条件：`include` 为空、无法形成可信消息、用户要求多个 commit。
   - 失败行为：不生成空提交，不拆分多个 commit；请求补充信息或说明只能生成单个提交提案。
6. **展示提案与审批**
   - 输入：分类结果、风险、完整 subject/body、执行模式候选。
   - 输出：用户明确批准、用户修改后的新需求，或停止。
   - 停止条件：默认模式下一律在此停止等待批准；直接执行候选遇到 mandatory-stop 也必须停止。
   - 失败行为：若用户修改 include/exclude/uncertain 或消息，必须回到分类与消息生成步骤，重新展示提案。
7. **选择性暂存**
   - 输入：已批准的 `include` 路径集合与消息。
   - 输出：仅包含批准路径的 index。
   - 停止条件：批准集合为空、路径不存在且不是批准删除、路径级暂存失败。
   - 失败行为：保留现场，报告失败命令和路径，不做提交。
8. **验证 index 边界**
   - 输入：批准的 `include` 集、重新读取的 staged paths 与 staged diff。
   - 输出：边界一致结论。
   - 停止条件：staged paths 与批准 include 集不完全一致，或 staged diff 出现未批准内容。
   - 失败行为：立即停止，不 commit，不尝试用破坏性命令修复。
9. **创建一个 commit**
   - 输入：已验证 index、批准 subject/body、执行前 HEAD。
   - 输出：Git 创建的一个新 commit 或失败结果。
   - 停止条件：commit 命令失败、hooks/签名失败、消息被拒绝。
   - 失败行为：不绕过 hooks 或签名，不规避性重试；报告失败并保留现场。
10. **从 Git truth 验证并报告**
    - 输入：执行前 HEAD、执行后 HEAD、批准消息与 include 集。
    - 输出：commit hash、完整 subject、body 是否存在、实际 committed paths、仍留在工作区的 exclude/uncertain。
    - 停止条件：没有恰好新增一个 commit、subject 不一致、committed paths 与 include 集不一致。
    - 失败行为：不得宣称成功；报告不一致证据和需要人工处理的状态。

## 审批状态机

- **默认审批模式**：只要用户没有在当前请求或当前会话中明确表达直接执行偏好，就必须在任何 staging/commit 副作用前展示提案并停止等待批准。
- **展示内容**：必须列出 `include`、`exclude`、`uncertain` 三个清单、逐路径理由、风险、mandatory-stop 项、多主题警告、完整 subject 与 body。
- **批准格式**：用户必须明确批准 exact include set 与 exact commit message；模糊同意、只说“继续看看”或只批准消息均不足以执行。
- **直接执行候选**：只有用户明确说要直接提交、自动提交或当前会话已有明确直接执行偏好，且不存在 mandatory-stop 条件时，才可跳过常规批准。
- **不可绕过暂停**：`uncertain` 路径、疑似敏感文件、异常 destructive/binary/large-file 变更、冲突、无法安全读取或低置信度意图始终强制等待确认。
- **用户修改**：用户调整文件边界、分类理由、风险接受范围或消息后，必须重新读取必要状态、重新分类、重新生成消息并再次展示提案。

## 输出格式

成功时报告：新 commit hash、完整 subject、body 是否存在、实际 committed paths、仍留在工作区的 exclude/uncertain 变更，以及验证结论来自 Git truth。失败或停止时报告：停止阶段、原因、已读取证据、未执行的副作用；若任一验证失败，明确说明不能宣称提交成功。
