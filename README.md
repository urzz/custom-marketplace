# cc-marketplace

用于组织和分发 **Claude Code 与 Codex** 插件的轻量级 Marketplace 仓库。两端使用各自原生入口，共用技能正文、参考资料和 Python 实现。

## 插件与调用

| 插件 / 版本 | Claude Code | Codex | 用途 |
|---|---|---|---|
| `dev-stack` / `0.5.0` | `/dev-stack:skill-forge` | `$dev-stack:skill-forge` | 为 Claude Code、Codex 或双平台创建、修改、审查 skill |
| `dev-stack` / `0.5.0` | `/dev-stack:commit` | `$dev-stack:commit` | 分析改动并安全创建单个 Conventional Commit |
| `dev-stack` / `0.5.0` | `/dev-stack:commit-and-push` | `$dev-stack:commit-and-push` | 创建并验证单个提交后普通推送当前分支 |
| `nuclio` / `5.3.3` | `/nuclio:init` | `$nuclio:init` | 创建或安全修复 `.dev-docs` 知识骨架 |
| `nuclio` / `5.3.3` | `/nuclio:work` | `$nuclio:work` | 创建、恢复、验证和归档一个 change |

`skill-forge` 与 Nuclio 的两个技能仅显式调用。commit 系列保留自动发现，实际暂存、提交和推送仍遵守各自的用户请求与授权合同。

## 安装

需要 Git、Python 3.10+ 和 PyYAML；安装对应客户端后，在本仓库根目录执行以下命令。Marketplace 注册与插件安装会写入该客户端的个人配置。

Claude Code：

```bash
claude plugin marketplace add .
claude plugin install dev-stack@jade-tools-marketplace
claude plugin install nuclio@jade-tools-marketplace
```

Codex CLI：

```bash
codex plugin marketplace add .
codex plugin add dev-stack@jade-tools-marketplace
codex plugin add nuclio@jade-tools-marketplace
```

按需选择插件安装，之后开启新会话。Codex 也可用 `/plugins` 打开插件浏览器。Git 托管分发时，将 `marketplace add` 的 `.` 换成该仓库的 Git 地址。

本地开发可直接以 `claude --plugin-dir ./plugins/dev-stack` 加载 Claude 插件。Codex 的目录加载检查见下文；修改已安装插件后需通过客户端更新/重新安装并在新会话验证，安装缓存中的内容不应手工编辑。

当前验证基线为 Claude Code `2.1.201` 与 Codex CLI `0.153.4`，不是声明的最低版本。客户端能力和未覆盖项见 [兼容性说明](docs/compatibility.md)。

## 工作流

**Skill Forge** 先确定目标平台与需求，确认 Spec，再生成并校验 Plan，按 Task 顺序实施。宿主与目标可以不同，例如在 Codex 中维护 Claude Code skill。两端共用 Plan validator 和代理角色合同；工具与权限按实际宿主适配。

**Nuclio v3 5.3.3** 共用七命令 Runtime，active change 和新 archive 都保留 `change.md`、`delivery.yaml`、`state.yaml`。在另一宿主恢复时继续读取同一份文件，无需转换状态。

Nuclio 在 Claude Code Plan Mode 或 Codex Plan mode 中均停止并要求退出后重新显式调用。普通模式下，work 在 discovery 前只读捕获调用起点 snapshot；snapshot unavailable 或起点 dirty 不阻塞已有 active change 的 discovery 与恢复。唯一 active change 按 ID 恢复，多个候选报告歧义；仅无 active change 且需要新建时才要求起点 attached 且 clean，并在只读 Shape 后完成分支/HEAD/工作区及全部已配置 remote 的缓存 remote-tracking refs 检查，创建受控新分支，再进行 post-switch 复核与 Runtime create。

用户确认结果合同后，主会话管理交付与检查。每个 Shape 调查和 Build/返修工作包开始前，主会话按独立性、上下文隔离收益与协调成本决定直接执行或条件性积极委派，由模型自主选择拆分；多文件调查、大输出诊断和可独立验收轨道在有收益时积极委派，单文件小改、紧密依赖或共享资源争用时直接处理，不机械要求 agent-first。实际委派形成可独立验收的工作包；活动期间产品路径和诊断主题对主会话排他，调查与实施代理（含返修）仅作最多 15 行的五字段结构化回传，独立 reviewer 使用专用审查格式，不套用该字段或行数限制。依赖结果时使用宿主原生完成通知或等待，失败则优先按实际能力继续原线程（resume），无法继续或工作包不再适合时才缩小/重切或重新委派。

Claude Code 与 Codex 共用模型和工具无关的能力合同，并按当前宿主真实提供的原生 Agent、等待、resume 与强制只读能力适配。Codex 依据当前工具定义及代理状态判断能否继续原线程，不按固定版本或文档遗漏推定恢复能力缺失。能力不足时按语义降级：无原生 Agent 则主会话顺序直做，无 resume 则重切或重新委派，无异步通知则使用宿主原生阻塞等待，无法强制只读则 reviewer 报告 `CANNOT_VERIFY`；不跨宿主调用 CLI 或模拟缺失能力。Runtime 记录当前检查依据、判断完成条件，并支持知识决定与可恢复归档。可选 Open Design 只使用用户已配置的 MCP 和明确绑定的 `project-id`，批准后的设计交付固定保存到 `.dev-docs/artifacts/open-design/`。

手工验收必须明确 `PASS` 或 `FAIL`；旧 v3 无状态手工记录不再作为通过依据，需要重新观察。批准提交回写中断通过 status 的 `recover-approval` 恢复；归档移动中断后，可明确请求“恢复并归档 `<change-id>`”，直接恢复指定 ID。Runtime 支持 Git 子目录项目、中文路径，并在归档移动前检查知识改动和忽略规则；已完成归档可在后续提交后幂等确认，归档内容漂移会被拒绝。

详细规则见 [Nuclio workflow](plugins/nuclio-plugin/references/workflow.md)、[宿主适配](plugins/nuclio-plugin/references/host-runtime.md) 和 [Skill Forge 平台适配](plugins/dev-stack/skills/skill-forge/references/platforms.md)。

## 仓库结构

```text
AGENTS.md                              # 两端共用维护规则
CLAUDE.md                              # 引用 AGENTS.md
.claude-plugin/marketplace.json         # Claude marketplace
.agents/plugins/marketplace.json        # Codex marketplace
plugins/
└── <plugin-dir>/
    ├── .claude-plugin/plugin.json
    ├── .codex-plugin/plugin.json
    ├── agents/*.md                    # 可选：Claude 原生代理入口
    ├── skills/<skill-name>/
    │   ├── SKILL.md                   # 共享技能
    │   └── agents/openai.yaml          # Codex 界面与调用策略
    ├── references/                    # 可选：共享资料与宿主适配
    └── scripts/                       # 可选：共享 helper 与测试
scripts/                               # 仓库级兼容性检查
```

插件标识 `nuclio` 的目录仍为 `plugins/nuclio-plugin/`，由两端 source 显式映射。Nuclio 当前权威位于 `skills/`、`references/` 和 `scripts/`；`plugins/nuclio-plugin/docs/research/` 是历史设计背景。

维护规则见 [AGENTS.md](AGENTS.md)。这是插件仓库，没有独立应用构建流程。

## 验证

从仓库根目录执行：

```bash
python3 scripts/validate_marketplace.py
python3 -m unittest discover -s scripts -p 'test_*.py'
python3 -m unittest discover -s plugins/dev-stack/skills/skill-forge/scripts -p 'test_*.py'
python3 -m unittest discover -s plugins/nuclio-plugin/scripts -p 'test_*.py'
python3 plugins/dev-stack/skills/skill-forge/scripts/plan_contract.py --help
python3 plugins/nuclio-plugin/scripts/change.py --help
```

两端原生检查：

```bash
claude plugin validate . --strict
claude plugin validate plugins/dev-stack --strict
claude plugin validate plugins/nuclio-plugin --strict
python3 scripts/smoke_codex.py
```

[静态校验](scripts/validate_marketplace.py) 检查两端名称、source、版本、调用策略和包内资源链接。[Codex 加载检查](scripts/smoke_codex.py) 通过临时副本与本地 app-server RPC 验证实际插件及技能元数据加载，同时覆盖含空格的缓存路径、不同 CWD 和插件目录只读；不安装到个人配置，也不启动模型会话。

配置校验、模型行为评测、有效只读代理权限、公共目录上架是不同检查，不能相互替代。当前边界与可复用行为场景见 [兼容性说明](docs/compatibility.md)。
