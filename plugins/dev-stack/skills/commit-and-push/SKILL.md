---
name: commit-and-push
description: Use only when the user explicitly asks to create one Conventional Commit from current staged, unstaged, or untracked changes and then push the current branch; do not use for commit-only, push-only, force-push, history-rewrite, pull/rebase, multi-commit, tag, or release requests.
---

# Commit and Push

本技能在 Claude Code 与 Codex 中共用同一提交合同。插件入口分别为 `/dev-stack:commit-and-push` 与 `$dev-stack:commit-and-push`；相对 references 路径以实际加载的技能目录为基准。按调用起点的用户项目定位 Git 仓库，确认根目录后所有 Git 命令显式使用 `git -C <repo-root>`，不从插件缓存目录推断目标。需要人工判断时使用宿主允许的提问方式并等待明确回复；空答案或超时不是批准。在只读/Plan mode 下仅提供分析，不 stage、commit 或 push。

此 skill 将一次明确的“提交并推送”请求处理为两个严格顺序阶段：先安全创建并验证恰好一个 Conventional Commit，再把当前分支普通推送到其 upstream。用户显式调用本 skill 即授权第二阶段的普通 push，但不代表接受提交边界风险、敏感内容或其他强制停止项。

## 边界

- 当前调用必须自包含：不得使用 Skill 工具、agent/subagent、workflow、MCP、外部服务或网络操作；唯一允许的网络副作用是最终 Git push。
- 不处理 commit-only、push-only、force push、多个 commit、pull、fetch、merge、rebase、amend、squash、reset、revert、tag、switch、clean、release 或 Git config 修改。
- 不修改工作树内容，不绕过 hooks 或签名，不自动解决分叉，不使用任何 force 参数或等价 refspec。
- push 失败不得撤销、amend、reset 或隐藏已成功创建的本地 commit，也不得换策略重试。

## 必读合同

严格按顺序读取并执行：

1. `../commit/references/change-analysis.md`
2. `../commit/references/commit-policy.md`
3. `../commit/SKILL.md`

提交阶段完整继承这些文件的状态盘点、逐路径分类、auto-execution eligibility、Human-in-the-Loop、选择性暂存、最终消息来源、单次提交和 Git truth 验证合同。仅作以下窄范围覆盖：

- 合并的 commit-and-push 请求在本 skill 内属于适用请求；
- `commit-policy.md` 和 commit skill 对 push 的禁止只约束提交阶段，提交成功验证后允许进入本文定义的 push 阶段；
- 最终输出还必须包含 push 结果。

除此之外不得弱化、跳过或重新解释 commit 合同。尤其是最终 commit 的 type、scope、summary 与 body 仍只能来自选择性暂存后重新读取的最终 staged diff。

## 严格顺序流程

### 1. Push 预检

在任何 staging 或 commit mutation 前：

1. 读取仓库根目录、执行前 HEAD 和当前分支名。detached HEAD、无法读取分支名或不是 Git 仓库时停止。
2. 判断当前分支是否已有 upstream。
   - 已有 upstream：读取对应的 branch remote 与 merge ref；remote 必须存在，merge ref 必须是单个 `refs/heads/<branch>`，对应远端跟踪引用必须可解析。若该引用不是当前 HEAD 的祖先，说明已知会产生 non-fast-forward，停止且不 commit。
   - 没有 upstream：确认名为 `origin` 的 remote 存在且具有 push URL；以 `origin/<当前分支>` 作为可选比较基线，并计划在成功提交后执行 `git push -u origin <当前分支>`。若该远端跟踪引用存在但不是当前 HEAD 的祖先，停止且不 commit；引用不存在时按首次发布分支处理。
3. 记录精确 push target，但不连接远端、不 fetch，也不修改 Git config。
4. 以已有 upstream 或存在的 `origin/<当前分支>` 远端跟踪引用为基线。若当前 HEAD 包含相对该基线尚未推送的既有 commits，push 会连同新 commit 一并发布；把这些 commit 的 hash 与 subject 作为 mandatory-stop，在任何 mutation 前请求用户确认。用户确认后重新读取状态和同一基线并继续。

任何预检失败都不得进入提交阶段。

### 2. 创建并验证一个 Commit

按“必读合同”执行完整 commit 管道，包括 `default-auto`、显式 `preview/approval-only` 和显式 `analysis-only`：

- `analysis-only` 输出提交分析和 push target 后结束，不 staging、不 commit、不 push。
- `preview/approval-only` 必须在任何 Git mutation 前同时展示 exact include set、provisional message/intent、push target 和已确认的既有 outgoing commits，并等待批准。
- 提交阶段任一停止、失败或 Git truth 验证不通过时，立即结束且不得 push。
- 只有确认相对执行前 HEAD 恰好新增一个 commit、消息和 committed paths 精确一致、exclude/uncertain 未混入后，才记录该新 commit hash 并进入 push 阶段。

### 3. 普通 Push

push 前重新验证：

- `HEAD` 仍是刚创建并验证的新 commit；
- 当前分支名、upstream 状态和精确 push target 与预检一致；
- 工作区变化不影响已提交内容，但任何分支、HEAD 或 push target 漂移都必须停止，不 push。

随后只执行一次普通 push：

- 已有 upstream：推送当前 `HEAD` 到预检锁定的 remote 与 merge ref；禁止额外 refspec、tag 和 force 选项。
- 没有 upstream：执行 `git push -u origin <当前分支>`，只为当前分支建立 upstream。

命令失败时停止，不自动 fetch、pull、rebase、force、重试或改写本地 commit。

### 4. Push 后验证

从 Git truth 验证：

1. 当前 `HEAD` 仍等于新 commit hash。
2. 当前分支的 upstream 存在且与预检目标一致。
3. upstream 对应的远端跟踪引用解析为新 commit hash。
4. push 命令成功，且没有推送额外 refspec 或 tag。

只有全部满足才可报告 commit-and-push 成功。任一项不一致都必须说明无法确认 push 成功，不得用命令的乐观文本替代验证。

## 输出

成功时报告：execution mode、commit hash、完整 subject、body 是否存在、committed paths、执行前后 HEAD、push target、upstream、已发布的既有 outgoing commits（如有）、工作区遗留 exclude/uncertain，以及 commit 与 push 的 Git truth 验证结论。

停止或失败时报告：停止阶段、已执行和未执行的副作用、当前 HEAD、是否已创建本地 commit、push 是否执行、push target、当前 staged paths、工作区遗留变更和最小安全下一步。若 commit 已成功但 push 失败，必须明确标记“本地提交成功，推送未确认”，并给出原样重试该普通 push 的命令；不得声称整体成功。
