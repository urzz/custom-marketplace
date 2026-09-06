# Claude Code 与 Codex 兼容性

本仓库提供两端原生 Marketplace 入口，共用 2 个插件、5 个技能和确定性脚本。支持范围是本地/Git Marketplace 分发；OpenAI 公共目录上架属于单独的发布工作。

## 格式与行为映射

| 项目 | Claude Code | Codex |
|---|---|---|
| Marketplace | `.claude-plugin/marketplace.json` | `.agents/plugins/marketplace.json` |
| 本地 source | `"./plugins/…"` | `{"source":"local","path":"./plugins/…"}`，相对仓库根目录 |
| 插件清单 | `.claude-plugin/plugin.json` | `.codex-plugin/plugin.json` |
| 技能入口 | `/plugin:skill` | `$plugin:skill`；可从 `/skills` 选择 |
| 显式调用控制 | `disable-model-invocation: true` | `agents/openai.yaml` 的 `allow_implicit_invocation: false` |
| 技能目录 | `CLAUDE_SKILL_DIR` | 实际加载的 `SKILL.md` 目录 |
| 项目目录 | 用户指定目录或 `CLAUDE_PROJECT_DIR` | 用户指定目录或宿主会话项目目录 |
| 用户确认 | 原生 `AskUserQuestion` | 对话中等待明确回复，或宿主明确允许的确认工具 |
| 子代理 | 原生 Agent / 插件 `agents/*.md` | 当前宿主的原生子代理，共用角色合同 |
| 项目维护规则 | `CLAUDE.md` 引用 `AGENTS.md` | `AGENTS.md` |

技能内的任务路径变量只是已解析路径的记号，不是 Codex 自动注入的环境变量。每次执行需使用实际绝对路径或在同一次 shell 调用内赋值。Nuclio 不因进入 Git 子目录而静默改变项目边界；从子目录启动且要管理顶层项目时，应明确提供顶层项目路径。

Nuclio 也支持以仓库子目录本身作为目标项目：Runtime 负责 Git 路径转换，共享 index 和项目外改动仍参与 clean gate。中文文件名通过 NUL 分隔的 Git 文件列表处理；`.dev-docs` 下的符号链接重定向会被拒绝。两个宿主都支持显式 ID 的归档中断恢复和 `recover-approval` 路由，详见 Nuclio workflow。

## 权限与模式

Nuclio 在任一宿主的 Plan mode 中都停止，不自动进入或退出模式。Skill Forge 与 commit 系列在只读/Plan mode 中仅分析。确认合同不等于扩大 sandbox 或工具权限。

Claude agent frontmatter 的工具限制不自动适用于 Codex。Claude 的 Nuclio reviewer 仅有 Read/Grep/Glob，Skill Forge reviewer 保留既有 Bash 以执行只读检查，其文本合同不等于文件系统只读 sandbox。Codex 只读 reviewer 必须有当前宿主可验证的有效只读限制；内置 `explorer` 的名称或自然语言约束不能证明隔离。父会话可能覆盖子代理默认配置，需以有效权限为准。缺少只读能力时报告 `CANNOT_VERIFY`；主会话继续自检，但不宣称完成独立审查。独立审查是用户/项目要求时，保留未满足验证，不能据此结束 Nuclio 归档。

实现代理不可用时可以由主会话顺序实施。插件不安装 Codex 原生代理配置，也不通过调用另一个客户端补齐代理能力。角色合同在 `plugins/dev-stack/references/agent-roles.md` 与 `plugins/nuclio-plugin/references/readonly-review.md`。

## 校验范围

| 检查 | 能证明什么 | 不能证明什么 |
|---|---|---|
| `validate_marketplace.py` | 本仓库双平台元数据、调用策略及包内链接一致 | 模型遵循技能、任意第三方插件 schema |
| `claude plugin validate --strict` | Claude 客户端接受 Marketplace 与插件结构 | 真实会话的决策结果 |
| `smoke_codex.py` | Codex 实际读取临时本地 Marketplace、5 个带命名空间技能及界面元数据 | 安装/更新流程、隐式触发的模型行为、端到端 change 交付 |
| 现有单元测试与 relocation 测试 | 共享 Runtime、Plan validator 以及显式项目路径的可执行行为 | 所有自然语言流程分支 |
| 独立行为用例 | 该输入与环境下观察到的行为 | 未执行用例或其他客户端版本 |

加载验证基线为 Claude Code `2.1.201` 与 Codex CLI `0.153.4`。这是已用版本，不是最低版本承诺。Codex IDE 的独立技能加载与桌面端 UI、账号分发和其他操作系统需各自验证，不能从 CLI 的加载结果推断已通过。

### 本地插件与公共目录 ingestion

双平台技能保留 Claude 的 `disable-model-invocation: true`，并独立声明 Codex 的 `allow_implicit_invocation: false`。本地 Codex CLI 能读取这份共享技能。当前内置 plugin-creator 的 `validate_plugin.py` 面向 ingestion，拒绝 `disable-model-invocation: true`；skill-creator 的 `quick_validate.py` 也不接受这个 Claude 扩展字段。

因此这两个外部校验器对 3 个显式调用技能的拒绝不能被写成 PASS，也不能通过删除 Claude 字段来规避。当前使用本仓库合同校验和两端原生加载证明本地兼容性。若今后要求公共目录上架，需要另行确认发布渠道的调用策略，并生成符合该渠道要求的发布包；本次不声称公共目录校验通过。

## 行为用例

Nuclio 的完整场景位于 `plugins/nuclio-plugin/references/eval-prompts.md`，在两个宿主各执行一次；Codex 将 `/nuclio:*` 换成 `$nuclio:*`。

重点验证：

1. 显式 init 只在给定项目建立知识骨架；已有正文保持完整，插件缓存只读。
2. 无 active change 且起点 dirty 的 work 停止；存在唯一 active change 时按 ID 读取恢复，不因 dirty 提前阻断 discovery。
3. Plan mode 中显式调用 init/work 不写骨架、不查询 Runtime、不创建分支，并要求退出后重新调用。
4. 普通功能请求不隐式运行 3 个仅显式调用技能；明确 commit-only 请求不执行 push。
5. Skill Forge 在 Codex 中维护 Claude Code 目标、在 Claude Code 中创建 Codex 目标，保留目标平台和调用策略。
6. 无可用代理时顺序实施；无有效只读代理权限时，不以普通子代理冒充独立 reviewer。
7. 分别从插件源码、含空格的缓存路径及不同工作目录调用共享 Python helper，产物只落在显式项目中。

未执行的行为场景记录为 SKIP 或未验证；静态断言不能替代这些结果。

## 规范来源

- [OpenAI：Build plugins](https://learn.chatgpt.com/docs/build-plugins) 定义 `.codex-plugin/plugin.json` 和技能插件布局。
- [OpenAI：Build skills](https://learn.chatgpt.com/docs/build-skills) 定义技能入口、`agents/openai.yaml` 与显式调用策略。
- [OpenAI：Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) 说明原生代理配置与有效权限继承。
- [Claude Code：Plugins reference](https://code.claude.com/docs/en/plugins-reference) 定义插件清单、组件和原生校验。

配置格式应同时核对实际客户端；外部文档或目录校验器更新不自动改变本仓库已确认的行为边界。
