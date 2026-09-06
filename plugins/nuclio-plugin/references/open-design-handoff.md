# Open Design MCP Handoff

仅当用户显式通过 `/nuclio:work` 要求同步、实现或审查 Open Design 交付，且当前请求或已加载的项目上下文提供稳定 `project-id` 时读取本文件。Open Design MCP 只是 Shape/Build 的只读输入通道；Nuclio Runtime 不托管 MCP，也不把外部状态当作可恢复事实。

## Binding and intake

按以下优先级确定项目：用户本轮明确给出的 `project-id`，其次是已加载项目上下文中的绑定。项目上下文缺失绑定、出现冲突或只有项目名时，在 Shape 报告 blocker。不得从 `.dev-docs/knowledge/` 推断工具绑定，不得调用 `get_active_context`，不要按最近活动、项目名或列表顺序猜测项目。

只使用用户已经配置的 Open Design MCP，并只调用读取工具：

1. 用 `get_project` 验证绑定 ID、项目名称和元数据；
2. 用 `get_artifact` 且 `include="all"` 拉取完整文本交付；
3. 仅在诊断截断或缺失文件时使用 `list_files`、`get_file` 或 `search_files`。

不得调用 `collect_brief`、`confirm_brief`、`create_artifact`、`write_file`、`delete_file`、`delete_project`、`start_run` 或其他写入/生成工具。不得修改 Open Design 项目。

交付至少包含 `design-handoff.md`、`DESIGN.md` 和一个页面原型。响应为 `truncated` 时继续读取缺失的文本文件；存在 MCP 无法返回内容的二进制依赖时，要求用户提供显式导出目录。MCP 不可用、绑定无效、workspace 授权失败或交付不完整时，在 Shape 报告 blocker；不得退回 active context、自动扫描 `.od` 或猜测文件。用户明确提供的导出目录可作为只读 fallback。

## Authority

按以下顺序解决冲突：

1. 当前代码、测试、真实 API、安全约束和 `.dev-docs/knowledge/` 中的项目事实；
2. `design-handoff.md` 的页面职责、交互和状态覆盖；
3. `DESIGN.md` 与 `brand-spec.md` 的视觉规范；
4. HTML/CSS/JavaScript 原型的表现细节。

原型数据、计数、时间、模拟请求和原生 JavaScript 状态不是生产事实。不得为了贴合原型而绕过现有 API、复制 mock 业务逻辑或引入未批准的框架迁移。

## Lifecycle

### Shape

读取绑定、MCP 交付和相关仓库事实，确认页面范围、交互、响应式、无障碍与数据边界。合同只描述可观察结果，不写 MCP 调用、复制路径或组件拆分等实现步骤。合同批准前不得把设计文件写入产品仓库。

### Build

批准后在首个相关 milestone 中把接受的交付固化到固定目录 `.dev-docs/artifacts/open-design/`。每个代码仓库只维护一个由项目上下文绑定的 Open Design 交付，不再按 UUID 或其他内部 ID 分层。只写 `design-handoff.md` 声明的用户交付文件及其必要依赖，跳过 `*.artifact.json`，不删除目标目录中来源不明的文件。不得把完整 HTML/CSS 交付写入 `.dev-docs/knowledge/`，也不得默认写入项目的 `docs/`。

固化后以仓库快照作为当前 change 的恢复输入，不在 Build 中静默重新拉取 Open Design。需要刷新设计时重新调用 MCP；若变化影响合同语义、兼容性或 Acceptance，回到 Shape 提升 revision。

按共享框架和页面拆分 delivery milestone，最后保留覆盖全部 Acceptance 的 integration milestone。实现复用当前技术栈和 API；设计快照是规范，不是可直接搬运的生产业务模型。

### Verify and Finish

用 delivery 中的 exact argv 验证构建、lint 和测试。视觉、交互、响应式与无障碍观察通过 `verify --manual` 绑定到当前 HEAD；记录视口、步骤和结果，不把截图或完整日志写入 State。

每条 manual JSON 必须显式包含 `status: PASS|FAIL` 以及 `acceptance`、`steps`、`result`、`executor`。观察失败提交 `FAIL` 并回到 Build；不能因为已记录观察就视为验收通过。旧记录缺少状态时重新观察，不猜测自由文本结果。

Finish 时把版本化设计快照视为当前 change 的可恢复输入，而不是项目事实。Open Design 绑定继续归属 `CLAUDE.md` 或 `AGENTS.md`；只有从设计中提炼出的跨 change 稳定规则新建、变化或失效时，才按知识流程提出候选，不要把完整交付或本次同步记录复制进长期知识。
