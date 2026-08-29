# Nuclio v3 Eval Prompts

以下 fresh-session 场景验证 Claude Code 2.1.212 的真实入口行为。Runtime 合同以 `change-format.md` 和 `change.py` 为准。

## Should Trigger

### 1. 普通 change

- **User Prompt**：`/nuclio:work 修复登录回跳并补测试`
- **Expected**：在当前模式直接进入 Shape，索引优先读取相关知识；把 `create` 的单行种子补全为无需旧聊天也能理解、精简但信息完整的 `change.md`，再用一次 `AskUserQuestion` 确认结果合同；随后主会话自主 Build/Verify。
- **Assertions**：不调用 `EnterPlanMode` 或 `ExitPlanMode`；不直接批准只有单句概括的草稿；多个独立边界分别记录、Acceptance 原子且可观察；不要求批准 milestone、路径、Agent 或普通失败修复；检查由 Claude Code 直接执行，再以 `record-check` 记录。

### 2. 无 active change 的 Shape

- **Setup**：`.dev-docs/changes/` 不存在 active change 目录，或只存在 `archive/`。
- **User Prompt**：`/nuclio:work 修复登录回跳并补测试`
- **Expected**：通过 Plan Mode 边界后，仅发现 active change 候选；不调用 `status`，直接进入 Shape 调查并在需要时 `create`。
- **Assertions**：不发起无 `--id` 的 `status --json`；不扫描或读取 archive；不依赖旧聊天或全量知识。

### 3. 恢复与失败修复

- **Setup**：`.dev-docs/changes/` 恰有一个 active change 目录。
- **User Prompt**：`/nuclio:work 恢复当前 change，检查失败则修好后完成`
- **Expected**：以唯一目录名作为 change ID，先运行 `status --id <change-id> --json`，读取当前合同、milestone/handoff 和索引路由的相关知识；失败回到 Build。
- **Assertions**：不依赖旧聊天或全量知识；合同不变的修复不再询问用户；合同语义变化才重新 AskUserQuestion。

### 4. 多个 active change

- **Setup**：`.dev-docs/changes/` 存在多个非 `archive/` 的 active change 目录。
- **User Prompt**：`/nuclio:work 继续交付`
- **Expected**：报告候选目录并 fail closed。
- **Assertions**：不猜测 change ID、不调用 Runtime、不读取或修改 archive；要求用户先解决歧义。

### 5. Open Design 绑定交付

- **Setup**：已加载的项目上下文保存一致且有效的 Open Design `project-id`，用户已配置对应 MCP。
- **User Prompt**：`/nuclio:work 按项目绑定的 Open Design 最终设计实现前端`
- **Expected**：Shape 条件读取 `open-design-handoff.md`，使用显式 ID 调用只读 `get_project` 与 `get_artifact(include="all")`，结合仓库事实形成结果合同；批准后才把交付固化到固定目录 `.dev-docs/artifacts/open-design/` 并实施。
- **Assertions**：不从 `.dev-docs/knowledge/`、active context 或项目名猜测绑定；不调用 Open Design 写入/生成工具；artifact 路径不含 UUID；完整交付不进入 knowledge；原型数据不成为生产事实；固化后恢复只读取仓库快照；视觉观察作为当前 HEAD 的 manual evidence。

### 6. 首次初始化

- **User Prompt**：`/nuclio:init 为这个项目建立 Nuclio 文档骨架`
- **Expected**：在当前模式仅在 `${CLAUDE_PROJECT_DIR}/.dev-docs/` 创建或安全修复索引、三个知识入口和 `changes/archive`。
- **Assertions**：不调用 `EnterPlanMode` 或 `ExitPlanMode`；不调用 Runtime，不创建 change 三件套，不实现功能；完成后停止并建议显式使用 `/nuclio:work`。

### 7. 多文件阅读与测试诊断的 Build 派发

- **Setup**：fresh-session 中恰有一个 active change；`status` 表明当前 milestone 的支付回调修复与现有检查边界明确，已确认结果合同保持不变。
- **User Prompt**：`/nuclio:work 恢复当前 change，修复支付回调集成测试失败`
- **Expected**：主会话先只保留或读取 `status` 工作包、当前合同、milestone/handoff 和索引路由的相关知识，并先判断派发；保留合同、`delivery.yaml`、Runtime 和 Verify 控制。当前 milestone 需要阅读多个回调、服务、配置和测试文件，预计反复运行诊断检查并产生较多原始输出；支付子系统范围清晰且可验证，因此优先派发一个有界 Claude Code Agent。主会话不预读委派范围的局部材料；agent 在支付子系统必要范围内吸收局部探索、测试诊断和原始输出，只短回传改动、检查和未完成项。
- **Assertions**：不以 token 或 ctx 数值硬阈值决定派发；主会话不预读委派范围的局部材料，包括局部代码、测试、配置或测试诊断；dispatch 仅含当前 milestone、相关 Acceptance、Constraints/Non-goals、handoff、相关知识路径及读取理由、必要范围和预期检查，不复制知识正文；agent 不调用 Skill、不继续委派、不接管 Runtime；主会话只处理短回传、milestone/handoff、Runtime 和 Verify，并执行最终验证和决定后续。

## Should Not Trigger

### 8. 单文件确定性 Build 不机械派发

- **Setup**：fresh-session 中恰有一个 active change；当前 milestone 只要求将单个已知超时常量从 `30` 改为 `60` 并运行既有检查，合同不变。
- **User Prompt**：`/nuclio:work 恢复当前 change，完成当前 milestone`
- **Expected**：主会话先基于紧凑控制信息判断该工作无需派发；范围限于一个文件且实现路径确定、无需探索或诊断时，主会话直接完成改动和检查，不为形式派发 Agent。
- **Assertions**：不因进入 Build 或存在 Agent 能力而机械委派；直接实施时主会话才读取相关代码、测试和配置；产品语义、兼容性或跨 milestone 架构取舍同样保留在主会话，必要时回到 Shape 或询问用户。

### 9. 仅咨询

- **User Prompt**：`Nuclio v3 的提案和用法是什么？`
- **Expected**：回答咨询，不触发 init 或 work。
- **Assertions**：不创建 `.dev-docs`，不调用 Runtime。

### 10. Skill/plugin 工作

- **User Prompt**：`帮我修改一个 Claude Code skill`
- **Expected**：不触发 Nuclio，路由至 Skill Forge。
- **Assertions**：不创建或恢复 Nuclio change。

### 11. init 越界请求

- **User Prompt**：`/nuclio:init 实现登录修复并归档当前 change`
- **Expected**：init 只处理安全骨架，拒绝产品实施、恢复、验证和归档。
- **Assertions**：提示用户显式使用 `/nuclio:work`。

### 12. 已处于 Plan Mode

- **Setup**：Claude Code 已处于 Plan Mode。
- **User Prompt**：`/nuclio:work 修复登录回跳并补测试`，或 `/nuclio:init 为这个项目建立 Nuclio 文档骨架`。
- **Expected**：立即 fail closed，要求用户先退出 Plan Mode 后重新显式调用对应 Nuclio Skill。
- **Assertions**：不调用 `EnterPlanMode` 或 `ExitPlanMode`；work 不创建或恢复 change、不调用 Runtime；init 不写入知识骨架。

## Boundary checks

### 13. Relocated plugin cache

- **Setup**：从临时 Marketplace cache 风格插件目录调用 Skill，当前目录不是插件源码仓库。
- **Assertions**：每个 Runtime 调用使用 `python3 "${CLAUDE_SKILL_DIR}/../../scripts/change.py" --project-root "${CLAUDE_PROJECT_DIR}" ...`；运行时写入只在项目 `.dev-docs/**`，cache 不写入。

### 14. Reviewer permissions

- **User Prompt**：要求 `nuclio:readonly-reviewer` 实现、写文件、运行 shell、调用 Skill 或委派其他 agent。
- **Expected**：reviewer 只用 Read、Grep、Glob 审查相关材料并返回 findings，或在无法审查时 `CANNOT_VERIFY`。
- **Assertions**：frontmatter 工具精确为 `Read, Grep, Glob`；没有 Bash、写入、Skill、Agent 或继续委派能力。

### 15. Open Design 输入不可用

- **Setup**：项目上下文绑定缺失或冲突、MCP 未配置、workspace 授权失败、返回截断且无法补齐，或二进制依赖没有内容。
- **User Prompt**：`/nuclio:work 实现已绑定的 Open Design 设计`
- **Expected**：Shape 报告 blocker，并要求修复 MCP 或提供显式导出目录。
- **Assertions**：不扫描 `.od`，不退回 active context，不创建产品快照，不开始实现，也不调用任何 Open Design 写入工具。
