# cc-marketplace

一个用于组织和分发 Claude Code 插件的轻量级 marketplace 仓库。

当前仓库包含：

- `openclaw-plugin`：提供 `/openclaw-skill-creator` 技能，用于帮助用户起草 OpenClaw skill。
- `dev-stack`：提供 `/skill-forge` 与 `/commit` 技能；`/skill-forge` 用于创建、设计和改进 Claude Code skill，`/commit` 用于自包含分析当前 Git 变更、生成单个 Conventional Commit，并在安全门禁下选择性暂存和提交。`/commit` 不调用 `/verify`、其他 skill、agent、workflow、MCP、网络或外部服务；最终 commit message 的 type、scope、summary 与 body 的唯一语义来源是选择性暂存后重新读取的最终 staged diff。
- `nuclio`：提供 Nucl.io 文件驱动 Contract Workbench：`/nuclio:init`、`/nuclio:work`、`/nuclio:finish`。

## 仓库结构

- `.claude-plugin/marketplace.json`：市场清单，声明当前 marketplace 暴露的插件。
- `plugins/<plugin-name>/.claude-plugin/plugin.json`：插件元数据。
- `plugins/<plugin-name>/skills/<skill-name>/SKILL.md`：技能定义。
- `plugins/<plugin-name>/skills/<skill-name>/references/`：skill 级协议、设计约束或参考资料（如 dev-stack/skill-forge 的 review-state 协议与模板；`plugins/dev-stack/skills/commit/references/` 存放 `/commit` 的变更分析和提交策略）。
- `plugins/<plugin-name>/skills/<skill-name>/scripts/`：skill 级确定性辅助脚本与测试（如 dev-stack/skill-forge 的 `review-state-helper.py`、`plan-task-query.py` 与 unittest；`/commit` 自包含执行，不使用 skill-forge agents、scripts 或 review-state helper，也不新增 runtime hook、daemon、MCP 或本地状态机制）。
- `plugins/<plugin-name>/references/`：插件级共享协议、设计约束或参考资料（如 Nuclio）。
- `plugins/<plugin-name>/agents/`：插件级有界子代理定义（如 dev-stack/skill-forge 的 bounded implementer/reviewer/fixer/final reviewer，以及 Nuclio agents）。
- `plugins/<plugin-name>/scripts/`：插件级确定性辅助脚本与测试（如 Nuclio contract/context/state/packet/evidence/migration helpers）。
- `plugins/nuclio-plugin/docs/research/contract-workbench-redesign/`：Nuclio Contract Workbench 重构的历史研究与设计材料；它们用于追溯设计依据，不是运行时行为权威，运行协议仍以 `plugins/nuclio-plugin/references/` 为准。

## 维护方式

新增或修改插件时，通常需要同时更新：

1. `plugins/` 下对应插件目录
2. 根目录 `.claude-plugin/marketplace.json`
3. 相关 README / CLAUDE 说明与本地校验命令

新增或修改 skill 时，保持当前目录约定：

```text
plugins/<plugin-name>/skills/<skill-name>/SKILL.md
```

Dev-stack 的 `/commit` 由 `plugins/dev-stack/skills/commit/SKILL.md` 定义主流程，并由 `plugins/dev-stack/skills/commit/references/change-analysis.md` 与 `plugins/dev-stack/skills/commit/references/commit-policy.md` 维护变更分析和提交策略；修改 `/commit` 时需同步这些文件、`plugins/dev-stack/.claude-plugin/plugin.json` 的版本、README / CLAUDE 说明与本地校验命令。`/commit` 必须维持自包含执行边界：不调用 `/verify`、其他 skill、agent、workflow、MCP、网络或外部服务，不绑定 skill-forge 的 agents、scripts 或 review-state helper，也不新增 runtime hook、daemon 或本地状态机制。最终 commit message 的 type、scope、summary 与 body 的唯一语义来源是选择性暂存后重新读取的最终 staged diff；未进入最终 staged diff 的内容不得影响最终消息。内部协议更新不应误写成 marketplace source、plugin name 或外部依赖变化。

Nuclio 的 Contract Workbench 行为还需要与以下内容保持一致：

- `plugins/nuclio-plugin/skills/{init,work,finish}/SKILL.md`
- `plugins/nuclio-plugin/references/*.md`，特别是 `output-language.md` 与 authority/lifecycle/execution/finish/eval 协议
- `plugins/nuclio-plugin/agents/*.md`
- `plugins/nuclio-plugin/schemas/*.json`，包括 Contract、packet、state、evidence 中的语言与 identity 字段
- `plugins/nuclio-plugin/scripts/*.py`，包括 contract/context/state/packet/evidence/migration helpers 及对应 `test_*.py`
- `plugins/nuclio-plugin/references/eval-prompts.md` 中的行为 eval cases

Nuclio 的机器协议保持英文和稳定 token：schema keys、helper actions、state/decision enum、hash、路径、命令、固定 headings 与 raw output 不翻译；面向维护者的正文由 Contract-bound `output_language` 和 Finish target language metadata 控制。修改语言传播、Gate alias、packet schema、agent report、Finish apply 或 archive/knowledge 行为时，必须同步 references、schemas、helpers、tests 与 eval；不要修改 marketplace 注册来表达这类内部协议变化，也不要声称新增 runtime hook、daemon、MCP、项目本地 `.claude/` 安装或 `.nuclio/` state。

Nuclio worker packet 维护规则：worker SHA 不在 init/migration 预存；packet-helper 写入 worker packet artifact；state-helper 使用 canonical packet schema 与 current state identity 首次绑定并 start-task；atomic bind/start 成功后才 dispatch fresh implementer。artifact existence、裸 SHA 或 agent claim 都不是 dispatch authority。

Nuclio Finish resume 维护规则：`/nuclio:work` 在 completion PASS 后写五文件 canonical handoff：`CHANGE_ROOT/completion.md`、`CHANGE_ROOT/completion.json`、`CHANGE_ROOT/decision.md`、`CHANGE_ROOT/decision.json`、`CHANGE_ROOT/finish-plan.json`，并由 helper 验证 projected identity 后才进入 `decision_pending`。新 Session `/nuclio:finish` 必须先执行 fresh-process readiness；只有 `ready=true` 才展示绑定 `decision_sha256`、`finish_plan_sha256`、`decision_state_version` 的 decision，并要求 exact `accept`/`同意`。`finish-plan.json` 统一声明 `knowledge_targets`、`archive_targets`、`index_targets`；`.dev-docs/changes/index.md` 属于 `index_targets`，`.dev-docs/archive/**` 属于 project-level archive authority。所有 `--*-json` 参数只能传 `.json`，Markdown 仅作为维护者 prose 展示层。

## 本地校验

当前仓库没有独立的 package/build 工作流，但可以先做基础静态校验：

```bash
python3 -m json.tool .claude-plugin/marketplace.json >/dev/null
python3 -m json.tool plugins/openclaw-plugin/.claude-plugin/plugin.json >/dev/null
python3 -m json.tool plugins/dev-stack/.claude-plugin/plugin.json >/dev/null
python3 -m json.tool plugins/nuclio-plugin/.claude-plugin/plugin.json >/dev/null
```

Dev-stack / Nuclio helper 与插件严格校验：

```bash
python3 -m unittest discover -s plugins/dev-stack/skills/skill-forge/scripts -p 'test_*.py'
claude plugin validate plugins/dev-stack --strict
python3 -m unittest discover -s plugins/nuclio-plugin/scripts -p 'test_*.py'
claude plugin validate plugins/nuclio-plugin --strict
```

如需检查 skill 文件，可重点审阅：

```bash
find plugins -path '*/skills/*/SKILL.md' -type f | sort
```
