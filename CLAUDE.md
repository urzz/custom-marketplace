# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Purpose

This repository is a Claude Code plugin marketplace repository, not a traditional application repository. The main responsibility of the current codebase is to declare which plugins can be discovered and which skills each plugin exposes.

There are only three core layers:

1. `/.claude-plugin/marketplace.json`: The marketplace entry point, which registers the list of plugins.
2. `/plugins/<plugin-name>/.claude-plugin/plugin.json`: The metadata entry point for an individual plugin.
3. `/plugins/<plugin-name>/skills/<skill-name>/SKILL.md`: The skill definition, using frontmatter plus the prompt body.

The repository currently registers one plugin: `openclaw-plugin`, which provides the `/openclaw-skill-creator` skill.

## Key Files

- `.claude-plugin/marketplace.json`: Determines which plugins Claude Code can discover.
- `plugins/openclaw-plugin/.claude-plugin/plugin.json`: Defines the plugin name, description, and version.
- `plugins/openclaw-plugin/skills/<skill-name>/SKILL.md`: Defines the skill metadata and the actual prompt.

## What Must Stay in Sync When Editing

### Adding or Modifying a Plugin

If the plugin directory or plugin metadata changes, you usually need to check both of these places:

- `plugins/<plugin-name>/...`
- `.claude-plugin/marketplace.json`

In other words, the plugin implementation and the marketplace registration must stay consistent, especially for:

- plugin `name`
- `source` in the marketplace
- plugin directory name

### Adding or Modifying a Skill

Skills are organized by filesystem directories and should follow the current pattern:

```text
plugins/<plugin-name>/skills/<skill-name>/SKILL.md
```

The current convention for `SKILL.md` is:

- frontmatter describes the skill metadata
- the body is used directly as the skill prompt

## Common Commands

This repository currently has no `package.json`, and there is no standalone build / lint / test workflow. Day-to-day development mainly consists of editing manifests and skill files, then doing minimal static validation.

```bash
git status --short
```

```bash
git ls-tree -r --name-only HEAD
```

```bash
jq . .claude-plugin/marketplace.json >/dev/null && jq . plugins/openclaw-plugin/.claude-plugin/plugin.json >/dev/null
```

```bash
claude --version
```

## Current Known Constraints

- The repository currently has no application code, test code, or build scripts; do not assume any npm / pnpm / bun workflow exists.
- If more plugins are added later, prefer keeping the existing hierarchy of “marketplace manifest → plugin metadata → skill directory” unchanged.
