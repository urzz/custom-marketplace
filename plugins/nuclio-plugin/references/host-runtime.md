# Nuclio 宿主适配

`init` 与 `work` 共用同一份技能、reference 和 `change.py`。先执行技能中的 Plan Mode 边界，再按本文件解析路径；不要根据残留环境变量猜测当前宿主。

## 入口与确认

| 行为 | Claude Code | Codex |
|---|---|---|
| 初始化 | `/nuclio:init` | `$nuclio:init` |
| 交付 | `/nuclio:work` | `$nuclio:work` |
| 显式调用策略 | frontmatter `disable-model-invocation: true` | `agents/openai.yaml` 中 `policy.allow_implicit_invocation: false` |
| 结果合同与知识决定 | `AskUserQuestion` | 在对话中展示合同或知识候选，等待用户明确回复；也可使用宿主明确允许用于确认的交互工具 |

文档中的 `/nuclio:init`、`/nuclio:work` 表示对应工作流，在 Codex 使用表中的 `$` 入口。默认选项、等待超时、工具返回空答案均不是确认。需要确认时停止依赖该决定的动作，明确回复到达后才继续。`request_user_input` 若仅在 Plan Mode 可用，不为提问而切换模式。

Claude Code Plan Mode 与 Codex Plan mode 均执行技能的停止规则。不要自行进入或退出模式；Codex 的 `update_plan` 或交付 milestone 不等于进入 Plan mode。权限由当前宿主控制，不能因为工作流获批而扩大 sandbox 或工具权限。

## 两个绝对路径

技能正文中的 `NUCLIO_SKILL_DIR`、`NUCLIO_PROJECT_DIR` 是本次调用解析得到的路径记号，**不是宿主自动提供的环境变量**。

1. `NUCLIO_SKILL_DIR`：当前实际加载的 `SKILL.md` 所在目录。Claude Code 从 `${CLAUDE_SKILL_DIR}` 取得；Codex 从技能目录清单或显式加载位置取得。支持插件缓存、路径含空格及符号链接；必须确认相邻 `../../scripts/change.py` 属于当前插件。
2. `NUCLIO_PROJECT_DIR`：用户明确指定的项目根目录优先，否则使用宿主本次会话的项目目录（Claude Code 为 `${CLAUDE_PROJECT_DIR}`，Codex 为会话提供的工作目录）。不从插件目录或后来执行命令的 CWD 推断，不因为它在某个 Git 仓库内就静默改成另一层目录。项目边界不明确时先澄清。
3. 在开始流程前固定两个绝对路径。每次 shell 调用都把记号替换成已核实且正确引用的绝对路径，或在**同一次 shell 调用**内设置这两个任务变量；不要依赖前一次 shell 的赋值。不会 shell 转义时使用结构化 argv。
4. Git 始终显式传入 `-C`，Runtime 始终显式传入 `--project-root`。无法定位任一路径时停止并报告，不能退回插件源码仓库、猜测安装路径或借用 Claude 的残留变量。

项目可以是 Git 仓库中的子目录；Runtime 负责转换项目相对路径与 Git 根目录相对路径，Git 的共享 index 和项目外 dirty 路径仍参与 clean gate。项目根路径可以解析符号链接；其下 `.dev-docs` 的目录、artifact、配置和知识路径不能再通过符号链接重定向。分支 ref 列举命令中的 `--format="%(refname)"` 必须保留 shell 引号。

两个宿主都按 work 的显式归档恢复例外处理用户当前给出的恢复/归档 ID：没有 active 候选时，只定点检查该 archive 目录并调用 `archive --id`，不扫描 archive、不进入新建分支规则。`status` 返回 `recover-approval` 时重跑 `approve --id`，不重复确认已经提交的合同。

例如，本次加载技能位于 `/opt/plugin cache/nuclio/skills/work/SKILL.md`，目标项目为 `/work/my project`，实际命令是：

```bash
python3 "/opt/plugin cache/nuclio/scripts/change.py" --project-root "/work/my project" status --id example-change --json
```

安装目录与 Marketplace cache 始终只读。Runtime 的状态和知识产物只在目标项目的 `.dev-docs/**`；其既有 approval/archive Git 元数据提交也只作用于显式目标项目。切换宿主恢复 change 时读取同一份三件套，不迁移 schema，也不增加宿主状态。

## 有界委派

- Claude Code 使用原生 `Agent`；Codex 使用当前会话实际提供的原生子代理工具。此技能在工作流规定的有界条件下请求委派，主会话保留全部控制决定。
- 派发时传入明确项目目录、当前合同、milestone/handoff、必要范围及检查；禁止继续委派和写 Runtime State。代理不可用时由主会话顺序完成工作，不调用另一套 CLI 或新增代理服务。
- Claude Code 的 `nuclio:readonly-reviewer` 有 `Read`、`Grep`、`Glob` 三个工具，不运行 shell。Codex 不自动加载插件根级 `agents/*.md`。
- Codex 需要独立审查时，只能选择当前环境**已提供有效只读限制**的原生子代理，并将 [只读审查合同](readonly-review.md) 传入。只读限制必须由宿主工具限制或有效 sandbox 提供；`explorer` 名称、自然语言约束以及可能被父会话覆盖的配置都不能证明权限隔离。只允许读取材料；若只能通过 shell 读取，可用只读命令，但不执行测试、构建、Git mutation、网络或写文件。
- 无法满足只读边界时不派发该审查，报告 `CANNOT_VERIFY: isolated read-only reviewer unavailable`。主会话仍自检；可选审查可明确跳过，用户或项目要求独立审查时必须保留未满足项，不能声称审查通过或据此完成归档。
