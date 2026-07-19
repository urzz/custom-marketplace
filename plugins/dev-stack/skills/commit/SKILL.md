---
name: commit
description: Use when the user asks to analyze staged, unstaged, or untracked Git changes, generate a commit message, or safely create exactly one Conventional Commit; it defaults to automatic execution when all safety conditions are satisfied and pauses for human judgment when required.
---

# Commit

此 skill 用于把当前仓库的 staged、unstaged 与 untracked 变更整理为一个语义清晰、边界受控的 Conventional Commit，并在本轮新鲜分析证明安全资格满足时默认自动创建恰好一个 commit。它不适用于历史查看、push、fetch、pull、merge、rebase、amend、squash、reset、revert、tag、switch、clean、配置修改或任何需要改写历史的请求；遇到这些请求时必须说明不处理并停止。

## Composite 工作流

本 skill 采用 Composite 架构：`SKILL.md` 只负责顺序控制、门禁和 reference 读取时机；逐路径分类与 auto-execution eligibility 细则来自 `references/change-analysis.md`；消息、授权、暂存、提交和验证细则来自 `references/commit-policy.md`。Sequential Pipeline 是唯一主干，不得跳步、并行执行副作用或用已有 staged diff 直接生成提交。

## 严格顺序管道

1. **确认 Git 仓库与执行模式**
   - 输入：用户请求、当前请求中明确表达的限制、当前目录。
   - 输出：仓库根目录、执行前 HEAD、执行模式：`default-auto`、显式 `preview/approval-only`、显式 `analysis-only`。
   - 规则：无相反指令时使用 `default-auto`；用户在当前请求中明确要求先看方案、提交前批准或只分析时覆盖默认，但不持久化到后续独立请求。
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
   - 失败行为：不得展示敏感值本身；把相关路径标为 mandatory-stop 并进入 Human-in-the-Loop。
4. **读取 `references/change-analysis.md` 并逐路径分类**
   - 输入：用户意图、路径状态、diff/安全摘要。
   - 输出：每个 changed path 恰好进入 `include`、`exclude` 或 `uncertain`，并带简短理由、证据、mandatory-stop 列表与 auto-execution eligibility 布尔结论及逐项证据。
   - 停止条件：无法推断可信主意图、任一路径为 `uncertain`、存在强制确认风险，或 eligibility 任一条件失败。
   - 失败行为：请求用户补充意图或批准边界；不得静默纳入存疑路径。
5. **读取 `references/commit-policy.md` 并生成一个消息**
   - 输入：`include` 集、主意图、分类理由、多主题判断。
   - 输出：恰好一个 Conventional Commit subject，以及必要 body。
   - 停止条件：`include` 为空、无法形成可信消息、用户要求多个 commit。
   - 失败行为：不生成空提交，不拆分多个 commit；请求补充信息或说明只能生成单个提交提案。
6. **授权判定**
   - 输入：执行模式、分类结果、mandatory-stop、auto-execution eligibility、完整 subject/body。
   - 输出：authorized include set/message、Human-in-the-Loop 问题，或 analysis-only 结果。
   - `default-auto` 且 eligibility 全部满足时，不等待批准，授权 exact include set 与 exact subject/body 并直接进入暂存。
   - 显式 `preview/approval-only` 时，在任何 Git mutation 前展示 exact include/exclude/uncertain、逐路径理由、风险、mandatory-stop、exact subject/body，并暂停等待用户批准。
   - 显式 `analysis-only` 时输出分析、消息建议与 eligibility 后结束，禁止 Git mutation。
   - eligibility 不满足时展示资格失败或 mandatory-stop 证据、受影响路径和最小裁定问题后暂停。
7. **选择性暂存**
   - 输入：authorized include set/message。
   - 输出：仅包含 authorized include set 的 index。
   - 停止条件：授权集合为空、路径不存在且不是授权删除、路径级暂存失败。
   - 失败行为：保留现场，报告失败命令和路径，不做提交。
8. **验证 index 边界**
   - 输入：authorized include set、重新读取的 staged paths 与 staged diff。
   - 输出：边界一致结论。
   - 停止条件：staged paths 与 authorized include set 不完全一致，或 staged diff 出现未授权内容。
   - 失败行为：立即停止，不 commit，不尝试用破坏性命令修复。
9. **创建一个 commit**
   - 输入：已验证 index、authorized message、执行前 HEAD。
   - 输出：Git 创建的一个新 commit 或失败结果。
   - 停止条件：commit 命令失败、hooks/签名失败、消息被拒绝。
   - 失败行为：不绕过 hooks 或签名，不规避性重试；报告失败并保留现场。
10. **从 Git truth 验证并报告**
    - 输入：执行模式、执行前 HEAD、执行后 HEAD、authorized message 与 authorized include set。
    - 输出：execution mode、commit hash、完整 subject、body 是否存在、实际 committed paths、仍留在工作区的 exclude/uncertain、Git truth 结论。
    - 停止条件：没有恰好新增一个 commit、subject/body 不一致、committed paths 与 authorized include set 不一致，或 excluded/uncertain 被提交。
    - 失败行为：不得宣称成功；报告不一致证据和需要人工处理的状态。

## 授权状态机

- **Auto-first 默认值**：当前请求未明确要求 preview、approval-only 或 analysis-only 时，默认尝试 `default-auto`；默认自动授权必须来自本轮新鲜分析，不是持久偏好。
- **显式覆盖**：当前请求明确要求先看方案、提交前批准或只分析时优先；preview/approval-only 必须等待 exact include set 与 exact subject/body 批准，analysis-only 不执行任何 Git mutation。
- **自动资格**：仅当 include 非空、uncertain 为空、主意图和消息可信、每个路径边界明确、mandatory-stop 为空、状态/diff 证据新鲜且 `change-analysis.md` 的 auto-execution eligibility 全部通过时，才可自动授权。
- **Human-in-the-Loop 兜底**：任一资格失败、敏感或异常风险、冲突、低置信意图、不可读内容、边界歧义或状态漂移都阻止自动执行；只展示风险摘要与路径，并提出最小裁定问题。
- **授权失效**：用户改变边界、消息或风险裁定，或状态、diff、分类、消息、资格发生变化后，必须重新读取必要状态、重新分类、重新生成消息并重新授权。
- **授权语义**：authorized include set/message 同时表示通过全部 eligibility 的本轮自动授权，或用户在 preview 路径给出的明确批准；自动模式不是风险接受。

## 输出格式

成功时报告：execution mode、新 commit hash、完整 subject、body 是否存在、实际 committed paths、执行前后 HEAD、仍留在工作区的 exclude/uncertain 变更，以及验证结论来自 Git truth。停止或失败时报告：停止阶段、资格失败或 mandatory-stop 证据、已执行/未执行的副作用、当前 staged paths、遗留变更和最小安全下一步；若任一验证失败，明确说明不能宣称提交成功。
