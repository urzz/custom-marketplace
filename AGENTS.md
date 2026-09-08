# 仓库维护指南

## 仓库定位

本仓库是同时支持 Claude Code 与 Codex 的插件 Marketplace，不是应用项目。核心层级为：

```text
.claude-plugin/marketplace.json
.agents/plugins/marketplace.json
plugins/<plugin-dir>/.claude-plugin/plugin.json
plugins/<plugin-dir>/.codex-plugin/plugin.json
plugins/<plugin-name>/skills/<skill-name>/SKILL.md
```

插件可按需提供 skill 级或插件级 `references/`、`scripts/`、测试和 agent 定义。不要假设存在 `package.json`、npm、pnpm、bun 或统一构建流程。

## 语言规则

- 面向用户的回复和新生成的 README、设计文档、计划、操作说明默认使用简体中文。
- `SKILL.md`、reference 和维护文档的说明文字默认使用简体中文；代码、命令、路径、配置键、协议字段、API 名称和原始输出保留原文。
- 用户明确指定其他语言、项目已有更具体约定或所属生态必须使用英文时，遵循更具体要求。
- 修改现有文档时保持术语一致，避免无必要的中英文混排。

## 通用同步规则

修改插件时检查并按需同步：

- `plugins/<plugin-name>/` 内的实现、skill、reference、script 和测试；
- 两端 `plugins/<plugin-name>/{.claude-plugin,.codex-plugin}/plugin.json`；
- 两端 `.claude-plugin/marketplace.json` 与 `.agents/plugins/marketplace.json`；
- `README.md`、`CLAUDE.md` 与本文件中的用户可见能力和维护约束。

插件名称、Marketplace `source`、description 和 version 必须一致。新增 skill 使用 `plugins/<plugin-name>/skills/<skill-name>/SKILL.md`，并保留合法 frontmatter。

确定性检查优先于 LLM review。JSON/YAML、schema、静态检查、单元测试或 plugin validation 失败时，不得用人工或模型判断替代。

## dev-stack 约束

### skill-forge

- `/skill-forge` 仅显式调用，用于 CREATE、MODIFY、AUDIT Claude Code、Codex 或双平台 skill。
- CREATE/MODIFY 先完成 Focused 或 Grill 澄清并确认 `spec.md`，再生成和校验精简 `plan.yaml`；只有删除、依赖、权限、外部副作用或用户选择变化时追加 Plan 确认。
- `plan_contract.py` 是唯一 Plan validator，负责重复 YAML key、Spec hash、repo-relative path、Task ownership、文件前置条件、placeholder、字段类型和空 checks。
- 主 Session 是唯一 Controller，产品写入按 Task 顺序执行。bounded implementer 只修改一个 Task 的精确路径；bounded reviewer 只读；两者都不写 report、不递归委派、不 commit。Claude Code 保留原生 agents；Codex 按 `platforms.md` 传递共享角色合同，代理不可用时顺序实施，无法满足有效只读权限时明确报告独立审查未完成。
- AUDIT 始终只读且不创建 run。默认 run 只保留忽略的 `.skill-forge/<run>/spec.md` 与 `plan.yaml`；仅跨会话多 Task 恢复时可增加轻量 `state.json`。
- 不恢复风险分类、review-state、Gate、ledger、fix budget、checkpoint commit、自动 squash 或 Git 历史改写；不增加 DAG、并行产品写入、外部 orchestration、MCP、daemon、runtime hook 或 worktree 依赖。

修改 `/skill-forge` 时同步其 `SKILL.md`、一层 `references/`、`plan_contract.py`、测试、插件 metadata、Marketplace、README 和本文件。

### commit 与 commit-and-push

- `/commit` 是自包含 Conventional Commit 流程，不调用 `/verify`、其他 skill、agent、workflow、MCP、网络或外部服务，也不执行 push。
- `/commit-and-push` 复用 `/commit` 的 references 与完整提交合同，仅在提交 Git truth 验证通过后普通推送当前分支；无 upstream 时只通过既有 `origin` 建立 upstream。
- 两者的 commit type、scope、summary 与 body 唯一语义来源都是选择性暂存后重新读取的最终 staged diff；未暂存内容不得影响最终消息。
- `/commit-and-push` 禁止 force push、自动处理分叉和历史改写；push 失败时保留本地 commit 并报告部分成功。
- 两者都不绑定 skill-forge 的 agent/script，不引入 runtime hook、daemon 或本地状态机制。

修改 `/commit` 或 `/commit-and-push` 时同步两者共享的提交合同、新 Skill、插件 metadata、Marketplace、README 和本文件。

## Nuclio v3 5.3.3 约束

Nuclio 当前权威文件：

```text
plugins/nuclio-plugin/skills/{init,work}/SKILL.md
plugins/nuclio-plugin/agents/readonly-reviewer.md
plugins/nuclio-plugin/references/{host-runtime,readonly-review,workflow,change-format,knowledge,context-hygiene,open-design-handoff,eval-prompts}.md
plugins/nuclio-plugin/scripts/{change.py,test_change.py,test_static_plugin.py}
```

`docs/research/` 仅是历史设计输入，不是 Runtime 权威。维护时遵守以下边界：

- `/nuclio:init` 与 `/nuclio:work` 都只能由用户显式调用；init 只在 `${NUCLIO_PROJECT_DIR}/.dev-docs/` 创建或安全修复知识骨架后停止，普通 change 只通过 work。
- 两个 Skill 始终在调用开始时的当前模式内运行，不调用 `EnterPlanMode` 或 `ExitPlanMode`；若调用时已处于 Claude Code Plan Mode 或 Codex Plan mode，则立即停止，不创建或恢复 change、不执行 Runtime，并要求用户退出后重新显式调用。`delivery.yaml` milestone 不等于宿主 Plan Mode。
- active change 与新 archive 都完整保留 `change.md`、`delivery.yaml`、`state.yaml`。主会话是唯一控制器；`change.py` 是唯一 State writer，只提供 `create`、`approve`、`status`、`record-check`、`verify`、`complete`、`archive` 七个命令。
- `/nuclio:work` 通过 Plan Mode 边界后、discovery 前只读捕获调用起点 snapshot；snapshot unavailable 或起点 dirty 不阻塞已有 active change 的 discovery 与恢复。恢复唯一 active change 不创建或切换分支，多个 active 仍 fail closed；仅无 active change 且需要新建时才要求调用起点为 attached 且无 staged、unstaged、untracked 改动。
- 无 active change 时，主会话只读完成 Shape 调查、确定合法 `<change-id>` 与 `feat|fix|refactor|docs|test|chore` 类型（无法明确时为 `feat`）后，复核 branch/HEAD 未漂移、当前仍 clean、本地 `refs/heads/...` 与全部本地配置 remote 的缓存 remote-tracking `refs/remotes/<remote>/...` 无精确冲突；只读本地 Git metadata，不 `fetch`、`ls-remote`、联网或刷新 refs。全部通过后执行 `git -C "${NUCLIO_PROJECT_DIR}" switch -c <type>/<change-id> <start-head>`；只有 post-switch 的 branch、HEAD、clean 和 remote-ref 二次校验成功才调用 `create`。
- 分支操作只由主会话执行，不加入 Runtime command、State 或 artifact；Runtime 不创建或切换分支，也不保存 branch state。前置检查或 switch 失败不调用 `create`，不写入本次 change 或产品文件；switch 后异常或 `create` 失败不自动回滚，保留分支并在部分成功或最终新建成功报告中包含分支名。不得自动 stash、commit、reset、clean、删除分支、切回原分支、push、merge、rebase 或创建 worktree。
- 用户只确认结果合同。每个 Shape 调查和 Build/返修工作包前，主会话按独立性、上下文隔离收益与协调成本决定直接执行或条件性积极委派，由模型自主拆分；多文件/大输出/可独立验收轨道在有收益时积极委派，单文件小改、紧密依赖、共享资源争用或需持续共享上下文时直接处理。主会话仍独占产品语义、兼容性、权限、外部副作用、不可逆结果、架构取舍、用户交互及 Runtime/Verify/Finish 决策，并自主维护 delivery milestone、实施、检查和合同不变的返修；只有结果合同发生实质变化才重新确认。
- 委派包必须可独立验收；活动期间其产品路径与诊断主题对主会话排他，调查与实施代理（含返修）只作最多 15 行的五字段结构化回传，依赖结果时使用宿主原生通知或等待，失败优先按实际能力继续原线程（resume），无法继续或工作包不再适合时才缩小/重切或重新委派。Claude Code 与 Codex 按真实原生 Agent、等待、resume 和只读能力适配；Codex 不按固定版本或文档遗漏推定恢复能力缺失。共享合同不依赖模型或具体工具，能力不足时按语义顺序直做、原生阻塞等待、重切/重派或报告 `CANNOT_VERIFY`，不得跨宿主调用 CLI。Agent 不调用 Skill、不继续委派、不接管 Runtime，产品写入保持顺序。
- bundled Runtime 通过 `${NUCLIO_SKILL_DIR}` 定位，并显式传入 `${NUCLIO_PROJECT_DIR}`；两个路径记号按 `references/host-runtime.md` 从实际加载位置和目标项目解析；插件源码和 Marketplace cache 始终只读，运行时写入只落在项目 `.dev-docs/**`。
- `record-check` 只校验并记录宿主主会话直接运行的 exact argv，不执行命令。合同、HEAD、检查定义或未登记的产品工作区漂移必须使旧验证失效；stale complete 恢复仅可保留 State 已精确登记的 `APPLIED|PARTIAL` knowledge dirty 路径，详细例外以 Runtime reference 为准。失败、缺失或过期依据回到 Build 修复。
- 手工观察必须显式提供 `status: PASS|FAIL`；当前 FAIL 阻断对应 Acceptance，旧 v3 无状态 manual 记录仅可读取、不贡献通过依据。`status.next_action=recover-approval` 时重跑 approve 恢复已提交批准，不重复确认。无 active 且用户当前明确给出恢复/归档 ID 时，只定点访问该 archive 并调用 archive，不进入新建的起点 clean 或分支流程；未指定 ID、目标冲突或多个 active 均不猜测目标。
- 主会话始终自检；独立审查仅按需要使用 `nuclio:readonly-reviewer`。Claude Code 下其工具精确限制为 `Read`、`Grep`、`Glob`，只返回 findings，不运行 shell、不写文件、不调用 Skill 或 Agent，也不接管 Runtime。Codex 按 `references/host-runtime.md` 使用具有有效只读限制的原生代理与共享审查合同；不能用自然语言声明替代权限，缺少能力时报告 CANNOT_VERIFY。独立 reviewer 使用 `verdict`、`summary`、`findings`、`remaining_risk`，不套用调查与实施代理的五字段、`DELIVERED|BLOCKED` 状态或 15 行限制；不得因合法审查格式而恢复或重派。
- `/nuclio:work` 通过 Plan Mode 边界并完成只读调用起点 snapshot 后，仅发现 `.dev-docs/changes/` 的非 archive 直接子目录：无候选时先处理用户明确 ID 的归档恢复，否则进入新建 Shape，唯一候选时才以目录名调用 `status --id <change-id> --json`，多个候选时 fail closed 并报告歧义；snapshot 不得提前阻塞已有 active change 的发现与恢复，不得无 ID 调用 `status`、猜测目标或扫描 archive。Shape、Build、恢复、Verify 与 Finish 均从 `.dev-docs/index.md` 路由相关知识；不默认读取全部知识或 archive。Finish 同时检查新增候选和既有知识失效，无候选记录 `NO_OP`，有候选只询问一次“写入并归档（推荐）/跳过并归档”。
- Open Design 能力只在显式 `/nuclio:work` 请求且当前请求或已加载项目上下文提供绑定 `project-id` 时启用。主会话仅使用用户已配置 MCP 的只读工具；Shape 不写产品文件，批准后将完整交付固化到固定目录 `.dev-docs/artifacts/open-design/`，knowledge 只接收提炼后的稳定项目事实，随后不静默刷新外部设计。
- v2 active 输入必须 fail closed；旧 archive 不扫描、解析、修改或删除。archive 只处理显式已完成 change，完整保留三件套且可恢复重跑，不吸收无关 dirty work。
- Runtime 支持 Git 子目录项目和中文文件名，统一转换 Git 与项目路径并使用 NUL 分隔的文件列表；`.dev-docs` 下目录和文件不得通过符号链接重定向。archive 在移动前及未提交恢复时复核精确 knowledge dirty 路径和目标 ignore 规则；暂存或提交失败只撤销本次 transition 已暂存路径。已提交归档在后续 HEAD 上仍可幂等确认，但三件套必须匹配该 ID 的归档提交，历史证据绑定原验证 HEAD；只查询显式 ID 的路径历史，不扫描其他 archive。
- Runtime 不执行项目检查，不复制宿主权限、sandbox、Agent 或 worktree 能力；不自动 push、merge、stash、reset、clean、切换分支或改写历史，不托管或新增 daemon、MCP、网络服务、第二 State writer、DAG 或双栈 Runtime。可选 Open Design MCP 只由主会话消费，不进入 Runtime。

修改 Nuclio 时同步上述 skill/reference/script/test、插件 metadata、Marketplace、README 和本文件。详细 schema 与状态迁移以 Nuclio Runtime reference 和 helper 测试为准，不在仓库级文档复制完整合同。

## 双平台维护

- 本文件是两端共用的维护规则；`CLAUDE.md` 通过 `@AGENTS.md` 引用，不复制正文。
- 每个插件保持两份原生清单，共用 `skills/`、references 和 Runtime；Claude marketplace 的字符串 source 与 Codex marketplace 的 local source 对象必须解析到同一目录。既有 `nuclio` 标识对应 `plugins/nuclio-plugin/`。
- Skill 级 `agents/openai.yaml` 管理 Codex 展示和调用策略，与插件根级 Claude agent 定义不同。仅显式调用技能在两端分别声明；commit 系列保留自动发现及正文授权边界。
- 共享 workflow 不直接依赖 Claude 环境变量或专有提问工具；这些差异只出现在宿主适配文档中。
- 只修改当前权威文件；`docs/research/` 是历史背景，不批量改写成新的宿主能力声明。
- `change.py` 与 `plan_contract.py` 继续各有一份实现，不新增双栈 Runtime。

## 验证命令

基础检查（需要 Python 3.10+、PyYAML、Git；原生校验另需对应 CLI）：

```bash
python3 scripts/validate_marketplace.py
python3 -m unittest discover -s scripts -p 'test_*.py'
python3 scripts/smoke_codex.py
claude plugin validate . --strict
```

`smoke_codex.py` 只调用本地 app-server 的目录读取 RPC，在临时副本验证加载，不安装到个人配置，也不启动模型会话。公共目录上架校验与本地兼容性校验的差异见 `docs/compatibility.md`。

基础检查：

```bash
git status --short
git diff --check
python3 -m json.tool .claude-plugin/marketplace.json >/dev/null
python3 -m json.tool plugins/dev-stack/.claude-plugin/plugin.json >/dev/null
python3 -m json.tool plugins/nuclio-plugin/.claude-plugin/plugin.json >/dev/null
```

dev-stack：

```bash
python3 -m unittest discover -s plugins/dev-stack/skills/skill-forge/scripts -p 'test_*.py'
python3 plugins/dev-stack/skills/skill-forge/scripts/plan_contract.py --help >/dev/null
claude plugin validate plugins/dev-stack --strict
```

Nuclio：

```bash
python3 -c 'import yaml; print(yaml.__version__)'
python3 plugins/nuclio-plugin/scripts/change.py --help >/dev/null
python3 -m unittest discover -s plugins/nuclio-plugin/scripts -p 'test_*.py'
claude plugin validate plugins/nuclio-plugin --strict
```
