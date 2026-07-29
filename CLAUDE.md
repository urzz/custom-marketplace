# 仓库维护指南

## 仓库定位

本仓库是 Claude Code 插件 Marketplace，不是应用项目。核心层级为：

```text
.claude-plugin/marketplace.json
plugins/<plugin-name>/.claude-plugin/plugin.json
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
- `plugins/<plugin-name>/.claude-plugin/plugin.json`；
- `.claude-plugin/marketplace.json`；
- `README.md` 与本文件中的用户可见能力和维护约束。

插件名称、Marketplace `source`、description 和 version 必须一致。新增 skill 使用 `plugins/<plugin-name>/skills/<skill-name>/SKILL.md`，并保留合法 frontmatter。

确定性检查优先于 LLM review。JSON/YAML、schema、静态检查、单元测试或 plugin validation 失败时，不得用人工或模型判断替代。

## dev-stack 约束

### skill-forge

- `/skill-forge` 仅显式调用，用于 CREATE、MODIFY、AUDIT Claude Code skill。
- CREATE/MODIFY 先完成 Focused 或 Grill 澄清并确认 `spec.md`，再生成和校验精简 `plan.yaml`；只有删除、依赖、权限、外部副作用或用户选择变化时追加 Plan 确认。
- `plan_contract.py` 是唯一 Plan validator，负责重复 YAML key、Spec hash、repo-relative path、Task ownership、文件前置条件、placeholder、字段类型和空 checks。
- 主 Session 是唯一 Controller，产品写入按 Task 顺序执行。bounded implementer 只修改一个 Task 的精确路径；bounded reviewer 只读；两者都不写 report、不递归委派、不 commit。
- AUDIT 始终只读且不创建 run。默认 run 只保留忽略的 `.skill-forge/<run>/spec.md` 与 `plan.yaml`；仅跨会话多 Task 恢复时可增加轻量 `state.json`。
- 不恢复风险分类、review-state、Gate、ledger、fix budget、checkpoint commit、自动 squash 或 Git 历史改写；不增加 DAG、并行产品写入、外部 orchestration、MCP、daemon、runtime hook 或 worktree 依赖。

修改 `/skill-forge` 时同步其 `SKILL.md`、一层 `references/`、`plan_contract.py`、测试、插件 metadata、Marketplace、README 和本文件。

### commit

- `/commit` 是自包含 Conventional Commit 流程，不调用 `/verify`、其他 skill、agent、workflow、MCP、网络或外部服务。
- commit type、scope、summary 与 body 的唯一语义来源是选择性暂存后重新读取的最终 staged diff；未暂存内容不得影响最终消息。
- 不绑定 skill-forge 的 agent/script，不引入 runtime hook、daemon 或本地状态机制。

修改 `/commit` 时同步 `plugins/dev-stack/skills/commit/SKILL.md`、其一层 `references/`、插件 metadata、Marketplace、README 和本文件。

## Nuclio v2 4.1.0 约束

Nuclio 当前权威文件：

```text
plugins/nuclio-plugin/skills/{init,work}/SKILL.md
plugins/nuclio-plugin/references/{workflow,change-format,knowledge,context-hygiene,eval-prompts}.md
plugins/nuclio-plugin/scripts/{change.py,test_change.py,test_static_plugin.py}
```

`docs/research/` 仅是历史设计输入，不是运行时权威。维护时遵守以下边界：

- `/nuclio:init` 只负责 v2 `.dev-docs` skeleton、导航修复和旧目录整体移动到 `.dev-docs/legacy/v1/`；日常 change 只通过 `/nuclio:work`。
- active change 使用 `change.md` Spec、canonical `plan.yaml` 批准合同和轻量 `state.yaml` 恢复状态。`change.py` 是唯一 runtime helper 和 State writer，运行时只依赖 PyYAML。
- 产品 mutation 前必须通过 file-first Spec/Plan 验证和自然语言批准；`init-state` 创建 approval checkpoint 并冻结 `state.git_branch`。
- 每个 implementation Task 与获批 in-scope repair 只有一个 selective-stage checkpoint。Task、review 和 whole-change validation evidence 必须绑定 helper 推导的 Git identity；repair 后过期 evidence 必须失效。
- Plan 只使用 change-level `allowed_paths`，不增加 per-Task ownership、owner routing、automatic fixer 或第二状态协议。
- State 不保存完整 diff、日志、transcript、agent message、文件 snapshot 或完整 transition history。
- finish 先报告产品结果，再分析长期知识；`complete` 必须记录 `knowledge.result` 与精确 paths。完成文档保留批准 Spec，并追加非空 `Outcome`、`Validation`、`Knowledge Updates`、`Residual Risks`。
- 4.1.0 archive 完整移动并保留 `change.md`、`plan.yaml`、terminal `state.yaml`，创建一个 helper 验证的 archive commit；中断可恢复，成功重跑幂等，无关 dirty 文件不得进入 commit。
- `supersede` 只接受已成功归档、tracked/clean、completed 且 backlink predecessor 的 successor。旧 4.0.x 单文件 archive 仅作为只读兼容输入，不迁移。
- branch drift 或 detached HEAD 必须 fail closed。Coordinator 与 subagent 不创建、切换或重命名分支，不创建 worktree，不自动 reset/rebase/stash 或改写历史。
- 不增加 `workflow.py`、第二 State writer、DAG scheduler、并行产品写入、runtime hook、daemon、MCP、network service、项目级 `.claude/`、`.nuclio/` 状态、persistent process JSON、`changes/index.md`、archive manifest、隐藏备份、v1 converter 或双栈 runtime。

修改 Nuclio 时同步上述 skill/reference/script/test、插件 metadata、Marketplace、README 和本文件。详细 schema 与状态迁移以 Nuclio runtime reference 和 helper 测试为准，不在仓库级文档复制完整合同。

## 验证命令

基础检查：

```bash
git status --short
git diff --check
python3 -m json.tool .claude-plugin/marketplace.json >/dev/null
python3 -m json.tool plugins/openclaw-plugin/.claude-plugin/plugin.json >/dev/null
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
