# Skill Forge 平台适配

先区分**执行 Skill Forge 的宿主**与**所生成技能的目标平台**，两者可以不同。CREATE 的目标从用户要求或既有项目配置确定；没有明确信号时默认当前宿主并在 Spec 中写明。MODIFY/AUDIT 保留目标现有支持范围。双平台目标同时验证两端，不能通过更换宿主缩小已确认范围。

## 目标格式

| 项目 | Claude Code | Codex | DeepSeek Harness | 双平台/多平台 |
|---|---|---|---|---|
| 技能内容 | `skills/<name>/SKILL.md` | 同左 | provider 从 bundle 的 `plugins/*/skills/*/SKILL.md` 动态读取 | 共用正文和 supporting files |
| 插件入口 | `.claude-plugin/plugin.json` | `.codex-plugin/plugin.json` | provider 读取两者，优先 Codex 清单 | 两份原生清单加 DSH bundle |
| Marketplace | `.claude-plugin/marketplace.json` | `.agents/plugins/marketplace.json` | 根 `package.json` + `cordis.patch.yml` | 三个入口指向同一插件内容 |
| 显式调用 | `/plugin:skill` | `$plugin:skill`；独立技能为 `$skill` | `/<plugin>-<skill>`，例如 `/dev-stack-skill-forge` | 分别记录实际入口 |
| 仅显式调用 | `disable-model-invocation: true` | `agents/openai.yaml` 的 `policy.allow_implicit_invocation: false` | `disable-model-invocation: true` 映射为 `modelInvocable: false` | 分别声明并保留既有行为 |
| 原生代理配置 | 插件根级 `agents/*.md` | 宿主已配置的 `.codex/agents/*.toml` 或原生子代理工具 | 使用 DSH 原生 subagent 能力，bundle 不安装代理配置 | 共享角色要求，按宿主派发 |

目标技能的自动发现默认保持开启；只有用户明确要求或已有技能限定为显式调用时才关闭。Skill Forge 自身始终仅显式调用，不能把这个策略强加给它生成的所有技能。`agents/openai.yaml` 是技能元数据，不是子代理定义。

Claude Code 的专属 frontmatter 在双平台本地插件中可保留，Codex 的调用策略独立写入 `openai.yaml`。面向 OpenAI 公共目录的 ingestion validator 可能拒绝 `disable-model-invocation: true`；这是额外的发布目标，不能为通过它而解除 Claude 的显式调用限制。明确区分本地加载校验与公共目录上架校验。

## 运行路径与用户确认

本技能以 `/dev-stack:skill-forge`（Claude Code）、`$dev-stack:skill-forge`（Codex）或 `/dev-stack-skill-forge`（DSH bundle）显式调用。正文中的 `/skill-forge` 是简称。

`SKILL_FORGE_DIR` 表示本次实际加载的 `SKILL.md` 所在绝对目录：Claude Code 取 `${CLAUDE_SKILL_DIR}`；Codex 取技能目录清单中的实际路径；DSH 取 provider 返回的 `resourceBase.path`。它不是自动注入的环境变量。每次命令都使用核实并正确引用的绝对路径，或在同一次 shell 调用内设置任务变量，不依赖上一次 shell 的赋值。DSH bundle 的 provider 会保留相邻 `references/`、`scripts/` 等资源的相对解析位置。

`SKILL_FORGE_REPO_ROOT` 表示用户指定项目或宿主本次会话的目标仓库目录，不从插件路径或后来变化的 CWD 推断；它同样是每次调用需要落实的路径记号。`.skill-forge/<run>/` 始终位于目标仓库；validator 的 Spec/Plan 参数使用目标仓库内的绝对路径，`--repo-root` 显式传入目标仓库。插件缓存只读。DSH 当前会话的工作目录和用户明确指定的目标项目目录必须分别核实；不能把 bundle 安装目录当成项目根目录。

Claude Code 使用原生提问入口；Codex 展示问题并等待明确回复，或使用当前宿主明确允许用于该问题的交互工具；DSH 使用当前 profile 提供的确认能力。确认前停止依赖该答案的写入。空答案、默认选项、超时都不表示同意。不为使用仅限 Plan Mode 的提问工具而切换模式；在只读或 Plan mode 中只分析，不写 Spec、Plan 或目标文件。

## 顺序实施与独立审查

- Claude Code 使用 `dev-stack:skill-file-implementer` 或 `dev-stack:skill-file-reviewer`；向其传入本插件 [共享角色合同](../../../references/agent-roles.md) 的绝对路径和对应角色。
- Codex 使用当前会话可用的原生子代理，传入同一角色合同与当前 Task。此技能按核心流程规定的条件请求有界委派，不依赖插件 `agents/*.md` 自动加载。派发与产品写入保持顺序，不递归委派。
- DSH 使用当前 profile 实际提供的原生 subagent 能力；bundle 不写入 profile 代理配置，也不把 Claude/Codex agent 文件伪装成 DSH 原生代理。
- 代理不可用时，主会话按相同 Task 顺序实施。不要启动 Claude/Codex CLI 子进程、安装代理配置或扩大权限来补齐能力。
- Claude reviewer 保留既有 `Read`、`Grep`、`Glob`、`Bash` 工具；Bash 只执行角色合同允许的只读检查，这不是独立的文件系统只读 sandbox。不要把工具声明解读为允许写文件。
- Codex 的独立 reviewer 必须有宿主可验证的有效只读工具限制或 sandbox。自然语言的“只读”、`explorer` 名称、会被父会话覆盖的 sandbox 默认值均不构成权限隔离。无法满足时记录 `CANNOT_VERIFY: isolated read-only reviewer unavailable`，不派发不受限 reviewer；主会话自检也不能代替要求的独立审查。
- 流程要求独立审查而当前不可用时，交付已完成的改动和检查结果，同时把独立审查列为未完成验证；不能报告整体 PASS。

## 按目标选择验证

Claude Code 目标运行原生 `claude plugin validate <plugin> --strict`。Codex 目标验证清单、`SKILL.md`、`openai.yaml`，并用实际客户端加载；CLI 的本地目录 RPC 可验证名称、来源路径和技能元数据，不代表模型行为评测。DSH 目标先运行 `node dsh/test_provider.mjs` 和 `node --check dsh/index.mjs`，再在目标 profile 通过 bundle 安装完成一次真实 skill discovery smoke；本地 provider 测试不能代替 profile/UI/会话验证。多平台目标按各自入口分别执行。

本仓库的静态入口是 `python3 scripts/validate_marketplace.py`，Codex 加载检查是 `python3 scripts/smoke_codex.py`；这些是 Marketplace 仓库维护命令，不应复制成任意目标项目都存在的命令。用户明确要求发布时再执行相应发布渠道的 schema/ingestion 校验。没有隔离行为评测环境时报告 `SKIP: no isolated harness`。
