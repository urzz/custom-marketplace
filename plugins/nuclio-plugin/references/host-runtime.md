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

## 原生代理能力映射

共享 workflow 只规定能力语义：有界原生代理、完成通知或原生阻塞等待、可选 resume，以及由宿主强制的只读 reviewer。独立线程、输入上下文传播、回传、共享工作区和权限限制是不同边界，不能因其中一项存在而推定其他项成立。模型或宿主可能不会自动达到 workflow 期望的委派频率；技能已显式授权条件性积极委派，由模型按工作独立性、上下文隔离收益与协调成本自主拆分。不得把模型名、具体代理工具名、固定代理数量或某种自动委派模式写入共享决策合同。

| 能力语义 | Claude Code 映射 | Codex 映射 | 缺失时降级 |
|---|---|---|---|
| 有界原生代理 | 使用原生 `Agent` 派发 | 使用 native subagent `spawn` 派发；`/agent` 只查看或切换已有线程 | 主会话按同一工作包顺序直做；不启动另一宿主 CLI、不安装代理配置或新增服务 |
| 完成通知/等待 | 需要结果后再继续时以前台运行阻塞等待；后台运行的完成结果由宿主在后续 turn 通过 completion notification 送达 | 使用 native subagent `wait` 阻塞等待已派发代理的结果；`/agent` 不是等待或轮询机制 | 无异步通知时使用当前宿主原生阻塞等待；不得用 shell `sleep`、Git 状态、反复消息或其他轮询模拟 |
| resume | 对返回可寻址 agent ID/name 的普通代理，可用原生 `SendMessage` 继续原线程；内置 Explore/Plan 或用户手动停止的代理不可 resume | 按当前会话实际提供的工具及原代理状态继续原线程，具体映射见下文 | 仅在无可用继续能力、宿主明确拒绝恢复或工作包不再适合时，才缩小/重切工作包或重新派发；仍不合适时按 workflow 留理由后由主会话接管 |
| 强制只读 reviewer | `nuclio:readonly-reviewer` 的工具限制 | 当前环境提供有效只读工具限制或 sandbox 的原生子代理 | 报告 `CANNOT_VERIFY: isolated read-only reviewer unavailable`；不得用自然语言声明模拟权限 |

派发实现或调查时，映射到当前宿主真实机制，并传入明确项目目录、当前合同、milestone/handoff、相关 Acceptance 与 Constraints/Non-goals、必要路径边界、集成接缝、预期 changed paths 和 exact checks；禁止继续委派、调用 Skill 和写 Runtime State。调查与实施代理（含返修）的活动范围、最多 15 行结构化回传、失败恢复与有理由接管均遵循 workflow。主会话保持唯一 Controller，产品写入顺序执行。

这里的 resume 表示保留原线程与上下文继续工作，不要求工具名包含 `resume`。Codex 以当前会话暴露的工具定义和返回状态为准，不能因文档未列出某项能力或固定版本假设而直接判为不可恢复：

- 提供 `followup_task` 时，向原 agent ID/name 发送后续任务；该工具会为已完成且处于 idle 的代理触发新 turn，仍在运行的代理则按工具定义接收后续任务。`send_message` 仅递送消息、不触发新 turn，不能单独用于唤起 idle 代理。
- 提供 `send_input` 时，可向仍可接收输入的原 agent ID 发送后续任务；原代理已关闭且当前宿主提供 `resume_agent` 时，先用原 ID 恢复，确认成功后再发送后续任务。不要把重新 spawn 当作保留原线程的恢复。
- 仅提供针对运行中代理的 `steer` 时，不据此推定能唤起已完成代理；`stop`、`close` 本身也不等于恢复。只有实际工具无法继续原线程、明确拒绝恢复或工作包不再适合时，才按表中规则降级，不调用未提供的工具。

独立 reviewer 派发前，先预检审查问题、当前合同、当前 HEAD、changed paths、[只读审查合同](readonly-review.md) 和必要材料完整。Claude Code 的 `nuclio:readonly-reviewer` 只有 `Read`、`Grep`、`Glob`，不运行 shell。Codex 不自动加载插件根级 `agents/*.md`；需要审查时只能选择当前环境**已提供有效只读限制**的原生子代理。只读限制必须由宿主工具限制或有效 sandbox 提供；角色名称、自然语言约束以及可能被父会话覆盖的配置都不能证明权限隔离。只允许读取材料；若只能通过 shell 读取，可用只读命令，但不执行测试、构建、Git mutation、网络或写文件。

独立 reviewer 回传按只读审查合同验收，使用 `verdict`、`summary`、`findings`、`remaining_risk`；调查与实施代理的五字段、`DELIVERED|BLOCKED` 状态和 15 行限制不适用于 reviewer，不因其遵循审查格式而触发恢复或重派。

无法满足只读边界时不派发该审查并报告上述 `CANNOT_VERIFY`。主会话仍自检；可选审查可明确跳过，用户或项目要求独立审查时必须保留未满足项，不能声称审查通过或据此完成归档。任何能力降级都不得调用另一宿主 CLI、扩大权限、假装能力存在或新增代理服务。
