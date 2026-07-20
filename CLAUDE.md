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

Some plugins may also include shared references, subagent definitions, and helper scripts. The Nuclio plugin uses plugin-level `references/`, `agents/`, and `scripts/`. The dev-stack `skill-forge` skill uses skill-local `references/`, `agents/`, and `scripts/`, plus plugin-level bounded agents.

当前 marketplace 注册三个插件：

- `openclaw-plugin`：提供 `/openclaw-skill-creator`。
- `dev-stack`：提供 `/skill-forge` 和 `/commit`。
- `nuclio`：提供 `/nuclio:init`、`/nuclio:work` 和 `/nuclio:finish`。

## Key Files

- `.claude-plugin/marketplace.json`: Determines which plugins Claude Code can discover.
- `plugins/<plugin-name>/.claude-plugin/plugin.json`: Defines a plugin's name, description, version, and author metadata.
- `plugins/<plugin-name>/skills/<skill-name>/SKILL.md`: Defines skill metadata and the actual prompt.
- `plugins/<plugin-name>/skills/<skill-name>/references/`: Optional skill-local references. Dev-stack uses this for the skill-forge review-state protocol, templates, and validation checklist.
- `plugins/<plugin-name>/skills/<skill-name>/agents/`: Optional skill-local agents. Dev-stack uses this for `skills/skill-forge/agents/skill-creator-eval.md`.
- `plugins/<plugin-name>/skills/<skill-name>/scripts/`: Optional skill-local deterministic helper scripts and tests. Dev-stack uses this for `review-state-helper.py`, `plan-task-query.py`, and unittest coverage.
- `plugins/<plugin-name>/references/`: Optional plugin-level shared references. Nuclio uses this for authority, lifecycle, contract, context, execution, finish, migration, grill, and eval guidance.
- `plugins/<plugin-name>/schemas/`: Optional plugin-level data contracts. Nuclio uses JSON Schema for contract, context, state, packet, and evidence validation.
- `plugins/<plugin-name>/agents/`: Optional plugin-provided bounded agents. Dev-stack provides skill-forge implementer, reviewer, fixer, and final-reviewer agents here; Nuclio provides bounded implementer, task-reviewer, fixer, and completion-critic agents.
- `plugins/<plugin-name>/scripts/`: Optional plugin-level deterministic helper scripts and tests. Nuclio provides contract, context, state, packet, evidence, and migration helpers with unittest coverage.
- `plugins/nuclio-plugin/docs/research/contract-workbench-redesign/`: Historical research and design inputs for the Nuclio Contract Workbench redesign. These documents preserve design rationale but are not runtime authority; canonical behavior remains under `plugins/nuclio-plugin/references/`.

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

Do not declare an external Superpowers dependency for Nuclio; Nuclio is implemented as native plugin skills, references, agents, and deterministic helper scripts.

### Adding or Modifying a Skill

Skills are organized by filesystem directories and should follow the current pattern:

```text
plugins/<plugin-name>/skills/<skill-name>/SKILL.md
```

The current convention for `SKILL.md` is:

- frontmatter describes the skill metadata
- the body is used directly as the skill prompt

For Nuclio changes, keep all of the following in sync:

- `plugins/nuclio-plugin/skills/*/SKILL.md`
- `plugins/nuclio-plugin/references/*.md`，including canonical `output-language.md`
- `plugins/nuclio-plugin/agents/*.md`
- `plugins/nuclio-plugin/schemas/*.json`
- `plugins/nuclio-plugin/scripts/*.py`，including contract/context/state/packet/evidence/migration helpers and tests
- Nuclio behavior eval cases in `plugins/nuclio-plugin/references/eval-prompts.md`

Dev-stack skill 的通用同步原则：修改任一 skill 时，保持对应 `plugins/dev-stack/skills/<skill-name>/SKILL.md`、一层 `references/`、插件元数据、README / CLAUDE 说明与本地校验命令一致。`/commit` 由 `plugins/dev-stack/skills/commit/SKILL.md` 定义主流程，并由 `plugins/dev-stack/skills/commit/references/change-analysis.md` 与 `plugins/dev-stack/skills/commit/references/commit-policy.md` 维护变更分析和提交策略；修改 `/commit` 时必须同步这些文件，但它不使用 skill-forge 的 file-backed review-state、bounded agents 或 helper scripts。

Dev-stack `skill-forge` 变更还需要保持以下专用文件同步：

- `plugins/dev-stack/skills/skill-forge/SKILL.md`
- `plugins/dev-stack/skills/skill-forge/references/*.md`
- `plugins/dev-stack/agents/*.md`
- `plugins/dev-stack/skills/skill-forge/agents/skill-creator-eval.md`
- `plugins/dev-stack/skills/skill-forge/scripts/*.py`

对于 dev-stack `skill-forge`，`plugins/dev-stack/skills/skill-forge/scripts/review-state-helper.py` 是 file-backed review state 的唯一写入者。Bounded implementer 和 fixer agents 仅限 `Read, Edit, Write, Grep, Glob, Bash`；bounded reviewer 和 final-reviewer agents 仅限 `Read, Grep, Glob, Bash`；skill-local eval agent 仍保持 simulation-only 且由 flag gate 控制。

Nuclio's canonical lifecycle is `init → work → finish`. Work owns Contract drafting, the fresh Contract Gate, bounded per-Task implementer/reviewer/fixer execution, and mandatory change-wide completion; Finish is decision-first and requires a fresh exact `accept` before applying long-term `.dev-docs` knowledge or archive targets. Nuclio machine protocol remains English/stable for schema keys, helper actions, state/decision enums, hashes, paths, commands, fixed headings, and raw output; maintainer-facing prose is controlled by Contract-bound `output_language` and Finish target language metadata. When changing output language propagation, Gate aliases, packet schema, agent reports, Finish apply, archive, or knowledge behavior, keep skills, `output-language.md`, references, schemas, helpers, tests, and eval cases in sync without changing marketplace registration or claiming a new runtime hook/daemon/MCP/local `.claude/` install/`.nuclio/` state mechanism.

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
- This is a marketplace/plugin repository. Prefer preserving the existing hierarchy of “marketplace manifest → plugin metadata → skill directory”, with optional plugin-level references, agents, and scripts when a plugin needs them.
- Dev-stack skill-forge review state is file-backed only under ignored `.skill-forge/<run>/` directories. It is not a daemon, runtime service, background worker, or external state store.
- Nuclio deliberately does not add runtime hooks, daemon behavior, MCP server integration, project-local `.claude/` installation, or `.nuclio/` runtime state. Its source of truth is the file-backed `.dev-docs/changes/<change-id>/` Contract Workbench protocol documented under `plugins/nuclio-plugin/references/`.
