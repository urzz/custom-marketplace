# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Contents

- [Repository Purpose](#repository-purpose)
- [Key Files](#key-files)
- [What Must Stay in Sync When Editing](#what-must-stay-in-sync-when-editing)
  - [Adding or Modifying a Plugin](#adding-or-modifying-a-plugin)
  - [Adding or Modifying a Skill](#adding-or-modifying-a-skill)
- [Common Commands](#common-commands)
- [Current Known Constraints](#current-known-constraints)

## Repository Purpose

This repository is a Claude Code plugin marketplace repository, not a traditional application repository. The main responsibility of the current codebase is to declare which plugins can be discovered and which skills each plugin exposes.

The core hierarchy is:

1. `/.claude-plugin/marketplace.json`: The marketplace entry point, which registers the list of plugins.
2. `/plugins/<plugin-name>/.claude-plugin/plugin.json`: The metadata entry point for an individual plugin.
3. `/plugins/<plugin-name>/skills/<skill-name>/SKILL.md`: The skill definition, using frontmatter plus the prompt body.

Some plugins may also include shared references and helper scripts. The Nuclio v2 plugin uses plugin-level `references/` and `scripts/`. The dev-stack `skill-forge` skill uses skill-local `references/`, `agents/`, and `scripts/`, plus plugin-level bounded agents.

当前 marketplace 注册三个插件：

- `openclaw-plugin`：提供 `/openclaw-skill-creator`。
- `dev-stack`：提供 `/skill-forge` 和 `/commit`；`/skill-forge` 是 risk-adaptive skill 创建、修改、审查与验证入口，覆盖 L0-L3、deterministic-first、单 Controller 顺序执行、L2/L3 file-backed 状态、conditional review/eval 和 L3 strict 路径。
- `nuclio`：提供 `/nuclio:init` 和 `/nuclio:work`；`/nuclio:init` 负责 v2 `.dev-docs` setup/repair/`legacy/v1` 整体移动，`/nuclio:work` 负责基于 `change.md` 的人本 change 工作流。

## Key Files

- `.claude-plugin/marketplace.json`: Determines which plugins Claude Code can discover.
- `plugins/<plugin-name>/.claude-plugin/plugin.json`: Defines a plugin's name, description, version, and author metadata.
- `plugins/<plugin-name>/skills/<skill-name>/SKILL.md`: Defines skill metadata and the actual prompt.
- `plugins/<plugin-name>/skills/<skill-name>/references/`: Optional skill-local references. Dev-stack uses this for the skill-forge review-state protocol, templates, and validation checklist.
- `plugins/<plugin-name>/skills/<skill-name>/agents/`: Optional skill-local agents. Dev-stack uses this for `skills/skill-forge/agents/skill-creator-eval.md`.
- `plugins/<plugin-name>/skills/<skill-name>/scripts/`: Optional skill-local deterministic helper scripts and tests. Dev-stack uses this for `review-state-helper.py`, `plan_contract.py`, `plan-task-query.py`, and unittest coverage.
- `plugins/<plugin-name>/references/`: Optional plugin-level shared references. Nuclio v2 uses `workflow.md`, `change-format.md`, `knowledge.md`, `context-hygiene.md`, and `eval-prompts.md` as current runtime authority.
- `plugins/<plugin-name>/scripts/`: Optional plugin-level deterministic helper scripts and tests. Nuclio v2 uses `change.py`, `test_change.py`, and `test_static_plugin.py`.
- `plugins/nuclio-plugin/docs/research/contract-workbench-redesign/`: Historical research and design inputs for the earlier Nuclio redesign. These documents preserve design rationale but are not runtime authority.
- `plugins/nuclio-plugin/docs/research/human-centered-workflow-redesign/`: Historical research and design inputs for the Nuclio v2 human-centered workflow. The proposal is preserved as design context only; canonical behavior remains in Nuclio skills, references, and scripts.

## What Must Stay in Sync When Editing

### Adding or Modifying a Plugin

If the plugin directory or plugin metadata changes, you usually need to check both of these places:

- `plugins/<plugin-name>/...`
- `.claude-plugin/marketplace.json`

In other words, the plugin implementation and the marketplace registration must stay consistent, especially for:

- plugin `name`
- marketplace `source`
- marketplace `description`
- plugin directory name
- plugin version and author metadata when publishing updates
- repository `README.md` and `CLAUDE.md` when current guidance changes

Do not declare an external Superpowers dependency for Nuclio; Nuclio is implemented as native plugin skills, references, and deterministic helper scripts.

### Adding or Modifying a Skill

Skills are organized by filesystem directories and should follow the current pattern:

```text
plugins/<plugin-name>/skills/<skill-name>/SKILL.md
```

The current convention for `SKILL.md` is:

- frontmatter describes the skill metadata
- the body is used directly as the skill prompt

For Nuclio v2 changes, keep all of the following in sync:

- `plugins/nuclio-plugin/skills/init/SKILL.md`
- `plugins/nuclio-plugin/skills/work/SKILL.md`
- `plugins/nuclio-plugin/references/workflow.md`
- `plugins/nuclio-plugin/references/change-format.md`
- `plugins/nuclio-plugin/references/knowledge.md`
- `plugins/nuclio-plugin/references/context-hygiene.md`
- `plugins/nuclio-plugin/references/eval-prompts.md`
- `plugins/nuclio-plugin/scripts/change.py`
- `plugins/nuclio-plugin/scripts/test_change.py`
- `plugins/nuclio-plugin/scripts/test_static_plugin.py`
- `plugins/nuclio-plugin/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `README.md` and this `CLAUDE.md`

Nuclio v2 current behavior:

- Daily use goes through `/nuclio:work`; `/nuclio:init` is limited to v2 skeleton setup, navigation repair, and whole-directory movement of old `.dev-docs` content into `.dev-docs/legacy/v1/`.
- A normal change keeps one persistent process file at `.dev-docs/changes/<change-id>/change.md`; Git working tree, code, configuration, tests, and CI are execution facts.
- Work follows a sequential lifecycle: locate/create change, clarify intent, draft a human-readable plan, obtain user approval, implement, validate, apply risk-based review, optionally distill long-term knowledge after user confirmation, and archive.
- Human-in-the-Loop approval is mandatory before implementation plans are executed. Knowledge confirmation is conditional: only qualified candidates are proposed, and refusal does not affect validated product results or archive.
- The main session acts as coordinator/orchestrator. It may handle small low-risk work directly or use generic subagents based on complexity; extra critic/review is conditional on risk or explicit user request, not a fixed protocol-agent pipeline.
- User-visible prose defaults to the user's current primary language; code, commands, paths, field names, and raw output remain literal.
- The v2 maintenance boundary forbids runtime hooks, daemon behavior, MCP integration, project-local `.claude/` installation, `.nuclio/` runtime state, external Superpowers dependency, a v1 compatibility converter, a v1/v2 dual stack, or `changes/index.md`.

Dev-stack skill 的通用同步原则：修改任一 skill 时，保持对应 `plugins/dev-stack/skills/<skill-name>/SKILL.md`、一层 `references/`、插件元数据、README / CLAUDE 说明与本地校验命令一致。`/commit` 由 `plugins/dev-stack/skills/commit/SKILL.md` 定义主流程，并由 `plugins/dev-stack/skills/commit/references/change-analysis.md` 与 `plugins/dev-stack/skills/commit/references/commit-policy.md` 维护变更分析和提交策略；修改 `/commit` 时必须同步这些文件、`plugins/dev-stack/.claude-plugin/plugin.json` 的版本、README / CLAUDE 说明与本地校验命令。`/commit` 必须维持自包含执行边界：不调用 `/verify`、其他 skill、agent、workflow、MCP、网络或外部服务，不使用 skill-forge 的 file-backed review-state、bounded agents、scripts 或 review-state helper，也不新增 runtime hook、daemon 或本地状态机制。最终 Conventional Commit 的 type、scope、summary 与 body 的唯一语义来源是选择性暂存后重新读取的最终 staged diff；未进入最终 staged diff 的内容不得影响最终消息。内部行为变更不得误写成 marketplace source、plugin name 或外部依赖变化。

Dev-stack `skill-forge` 变更还需要保持以下专用文件同步：

- `plugins/dev-stack/skills/skill-forge/SKILL.md`
- `plugins/dev-stack/skills/skill-forge/references/*.md`
- `plugins/dev-stack/agents/*.md`
- `plugins/dev-stack/skills/skill-forge/agents/skill-creator-eval.md`
- `plugins/dev-stack/skills/skill-forge/scripts/*.py`
- `plugins/dev-stack/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `README.md`
- `CLAUDE.md`

维护 dev-stack `skill-forge` 时保持以下不变量：

- L0/L1/L2/L3 语义必须与 `plugins/dev-stack/skills/skill-forge/SKILL.md` 和 `references/review-state-protocol.md` 一致：L0 机械直改、L1 常规有界、L2 structural file-backed、L3 high-risk strict。
- `plan_contract.py` 是 L2/L3 Plan meta 的确定性合同校验入口；`risk_level` 仅接受 `L2`/`L3`，`review_policy` 仅接受 `final-only`/`task-and-final`，L3 必须 `task-and-final`，含任一 L3 Task 的 run 中每个 Task 都必须 `task-and-final`。
- deterministic-first 是强制维护原则：JSON/YAML/schema/static/test/plugin validation 等可本地运行的检查必须先于 LLM reviewer/eval；LLM review 不能替代失败的确定性校验。
- 主 Session 是唯一 Controller；bounded agents 不得修改 state、Gate、rubric、review-state.json、helper ledgers 或 Controller resolutions。
- L2/L3 中 `plugins/dev-stack/skills/skill-forge/scripts/review-state-helper.py` 是 file-backed `review-state.json` 的唯一写入者，`next-action` 是状态跳转唯一权威；`plan-task-query.py` 负责生成 stable task brief。
- Bounded implementer 和 fixer agents 仅限 `Read, Edit, Write, Grep, Glob, Bash`；bounded reviewer 和 final-reviewer agents 仅限 `Read, Grep, Glob, Bash`；skill-local eval agent 保持 simulation-only 且由 flag gate 控制。
- L2/L3 保留 checkpoint commits、cumulative review package、恢复语义、helper ledger、共享 owner-level fix budget、final review、structural validation 和适用 behavioral validation。
- conditional review/eval 必须按风险和 `risk/review policy` 触发：L2 可 `final-only` 或 `task-and-final`，E 为 0 或 1；L3 strict 保证每个 Task 都有 task-and-final review、mandatory final review、structural validation 和适用 behavioral validation。
- L2/L3 Spec 与 Plan 使用一次联合实施批准；用户修改、scope 扩张、ownership 不清、验证不可观察、不可逆或外向动作出现时必须停止并升级或回到 Phase 3 重新确认。
- 第一版不并行执行产品写入，不新增 DAG scheduler、外部 orchestration、MCP、network service、daemon、runtime hook、worktree 强依赖或新的项目外状态体系。
- Squash/reset/rebase/history rewrite 不得进入 bounded agent prompt；只有验证完成后由主 Session 在当前用户明确同意下执行，用户拒绝 squash 仍可合法完成为 unsquashed。

## Common Commands

This repository currently has no `package.json`, and there is no standalone build / lint / test workflow. Day-to-day development mainly consists of editing manifests and skill/reference files, then doing minimal static validation.

```bash
git status --short
```

```bash
git ls-tree -r --name-only HEAD
```

```bash
python3 -m json.tool .claude-plugin/marketplace.json >/dev/null
python3 -m json.tool plugins/openclaw-plugin/.claude-plugin/plugin.json >/dev/null
python3 -m json.tool plugins/dev-stack/.claude-plugin/plugin.json >/dev/null
python3 -m json.tool plugins/nuclio-plugin/.claude-plugin/plugin.json >/dev/null
```

```bash
python3 -m unittest discover -s plugins/dev-stack/skills/skill-forge/scripts -p 'test_*.py'
```

```bash
python3 plugins/dev-stack/skills/skill-forge/scripts/plan_contract.py --help >/dev/null
```

```bash
claude plugin validate plugins/dev-stack --strict
```

```bash
python3 -m unittest discover -s plugins/nuclio-plugin/scripts -p 'test_*.py'
```

```bash
claude plugin validate plugins/nuclio-plugin --strict
```

```bash
claude --version
```

## Current Known Constraints

- The repository currently has no application code, test code, package manager manifest, or build scripts; do not assume any npm / pnpm / bun workflow exists.
- This is a marketplace/plugin repository. Preserve the hierarchy “marketplace manifest → plugin metadata → skill directory,” with optional references and scripts when a plugin needs them.
- Dev-stack skill-forge review state is file-backed only under ignored `.skill-forge/<run>/` directories. It is not a daemon, runtime service, background worker, external orchestration layer, MCP integration, runtime hook, DAG scheduler, parallel write engine, or external state store.
- Dev-stack skill-forge first-version product writes are sequential; do not add parallel implementation dispatch or cross-owner auto-selection without a new confirmed contract.
- Dev-stack skill-forge L2/L3 state, ledger, budget, hash drift, recovery, completion, risk/review policy, and transition behavior are maintained by `review-state-helper.py`, `plan_contract.py`, `plan-task-query.py`, and the canonical review-state protocol.
- Nuclio v2 source of truth is the native plugin runtime under `plugins/nuclio-plugin/skills/{init,work}/`, `plugins/nuclio-plugin/references/{workflow,change-format,knowledge,context-hygiene,eval-prompts}.md`, and `plugins/nuclio-plugin/scripts/{change.py,test_change.py,test_static_plugin.py}`.
- Nuclio v2 deliberately does not add runtime hooks, daemon behavior, MCP server integration, project-local `.claude/` installation, `.nuclio/` runtime state, external Superpowers dependency, v1 compatibility converter, or a v1/v2 dual-stack runtime.
- Nuclio v2 recovery is centered on `.dev-docs/changes/<change-id>/change.md`; old `.dev-docs` content may only be moved as a whole into `.dev-docs/legacy/v1/`.
