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

The marketplace currently registers three plugins:

- `openclaw-plugin`: provides `/openclaw-skill-creator`.
- `dev-stack`: provides `/skill-forge`.
- `nuclio`: provides `/nuclio:project-init`, `/nuclio:brief`, `/nuclio:design`, `/nuclio:implement`, `/nuclio:verify`, and `/nuclio:fold`.

## Key Files

- `.claude-plugin/marketplace.json`: Determines which plugins Claude Code can discover.
- `plugins/<plugin-name>/.claude-plugin/plugin.json`: Defines a plugin's name, description, version, and author metadata.
- `plugins/<plugin-name>/skills/<skill-name>/SKILL.md`: Defines skill metadata and the actual prompt.
- `plugins/<plugin-name>/skills/<skill-name>/references/`: Optional skill-local references. Dev-stack uses this for the skill-forge review-state protocol, templates, and validation checklist.
- `plugins/<plugin-name>/skills/<skill-name>/agents/`: Optional skill-local agents. Dev-stack uses this for `skills/skill-forge/agents/skill-creator-eval.md`.
- `plugins/<plugin-name>/skills/<skill-name>/scripts/`: Optional skill-local deterministic helper scripts and tests. Dev-stack uses this for `review-state-helper.py`, `plan-task-query.py`, and unittest coverage.
- `plugins/<plugin-name>/references/`: Optional plugin-level shared references. Nuclio uses this for lifecycle, file protocol, context manifest, lightweight SDD, grill protocol, and roadmap guidance.
- `plugins/<plugin-name>/agents/`: Optional plugin-provided bounded agents. Dev-stack provides skill-forge implementer, reviewer, fixer, and final-reviewer agents here; Nuclio also provides bounded workflow agents.
- `plugins/<plugin-name>/scripts/`: Optional plugin-level deterministic helper scripts and tests. Nuclio provides `state-helper.py`, `task-helper.py`, and unittest coverage.

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
- `plugins/nuclio-plugin/references/*.md`
- `plugins/nuclio-plugin/agents/*.md`
- `plugins/nuclio-plugin/scripts/*.py`
- Nuclio eval prompts under `.superpowers/sdd/nuclio-*.md`

For dev-stack skill-forge changes, keep all of the following in sync:

- `plugins/dev-stack/skills/skill-forge/SKILL.md`
- `plugins/dev-stack/skills/skill-forge/references/*.md`
- `plugins/dev-stack/agents/*.md`
- `plugins/dev-stack/skills/skill-forge/agents/skill-creator-eval.md`
- `plugins/dev-stack/skills/skill-forge/scripts/*.py`

For dev-stack skill-forge, `plugins/dev-stack/skills/skill-forge/scripts/review-state-helper.py` is the only writer of file-backed review state. Bounded implementer and fixer agents are limited to `Read, Edit, Write, Grep, Glob, Bash`; bounded reviewer and final-reviewer agents are limited to `Read, Grep, Glob, Bash`; the skill-local eval agent remains simulation-only and flag-gated.

Nuclio's current lifecycle is `project-init → brief → design → implement → verify → fold`. Implement is a native lightweight SDD controller that dispatches one fresh worker per Task and a fresh reviewer; Verify is change-wide and approval-gated; Fold is proposal-first and approval-first before writing long-term `.dev-docs` knowledge.

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
- Nuclio MVP deliberately does not add runtime hooks, daemon behavior, MCP server integration, project-local `.claude/` installation, or `.nuclio/` runtime state. Its current source of truth is the file-backed `.dev-docs` protocol documented under `plugins/nuclio-plugin/references/`.
