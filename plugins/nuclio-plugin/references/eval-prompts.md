# Nuclio v3 Eval Prompts

以下 fresh-session 场景验证 Claude Code 2.1.212 的真实入口行为。Runtime 合同以 `change-format.md` 和 `change.py` 为准。

## Should Trigger

### 1. 普通 change

- **User Prompt**：`/nuclio:work 修复登录回跳并补测试`
- **Expected**：进入 Shape，索引优先读取相关知识；把 `create` 的单行种子补全为无需旧聊天也能理解、精简但信息完整的 `change.md`，再用一次 `AskUserQuestion` 确认结果合同；随后主会话自主 Build/Verify。
- **Assertions**：不直接批准只有单句概括的草稿；多个独立边界分别记录、Acceptance 原子且可观察；不要求批准 milestone、路径、Agent 或普通失败修复；检查由 Claude Code 直接执行，再以 `record-check` 记录。

### 2. 恢复与失败修复

- **User Prompt**：`/nuclio:work 恢复当前 change，检查失败则修好后完成`
- **Expected**：先运行 `status --json`，读取当前合同、milestone/handoff 和索引路由的相关知识；失败回到 Build。
- **Assertions**：不依赖旧聊天或全量知识；合同不变的修复不再询问用户；合同语义变化才重新 AskUserQuestion。

### 3. 首次初始化

- **User Prompt**：`/nuclio:init 为这个项目建立 Nuclio 文档骨架`
- **Expected**：仅在 `${CLAUDE_PROJECT_DIR}/.dev-docs/` 创建或安全修复索引、三个知识入口和 `changes/archive`。
- **Assertions**：不调用 Runtime，不创建 change 三件套，不实现功能；完成后停止并建议显式使用 `/nuclio:work`。

## Should Not Trigger

### 4. 仅咨询

- **User Prompt**：`Nuclio v3 的提案和用法是什么？`
- **Expected**：回答咨询，不触发 init 或 work。
- **Assertions**：不创建 `.dev-docs`，不调用 Runtime。

### 5. Skill/plugin 工作

- **User Prompt**：`帮我修改一个 Claude Code skill`
- **Expected**：不触发 Nuclio，路由至 Skill Forge。
- **Assertions**：不创建或恢复 Nuclio change。

### 6. init 越界请求

- **User Prompt**：`/nuclio:init 实现登录修复并归档当前 change`
- **Expected**：init 只处理安全骨架，拒绝产品实施、恢复、验证和归档。
- **Assertions**：提示用户显式使用 `/nuclio:work`。

## Boundary checks

### 7. Relocated plugin cache

- **Setup**：从临时 Marketplace cache 风格插件目录调用 Skill，当前目录不是插件源码仓库。
- **Assertions**：每个 Runtime 调用使用 `python3 "${CLAUDE_SKILL_DIR}/../../scripts/change.py" --project-root "${CLAUDE_PROJECT_DIR}" ...`；运行时写入只在项目 `.dev-docs/**`，cache 不写入。

### 8. Reviewer permissions

- **User Prompt**：要求 `nuclio:readonly-reviewer` 实现、写文件、运行 shell、调用 Skill 或委派其他 agent。
- **Expected**：reviewer 只用 Read、Grep、Glob 审查相关材料并返回 findings，或在无法审查时 `CANNOT_VERIFY`。
- **Assertions**：frontmatter 工具精确为 `Read, Grep, Glob`；没有 Bash、写入、Skill、Agent 或继续委派能力。
