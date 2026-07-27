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
- `nuclio`：提供 `/nuclio:init` 和 `/nuclio:work`；`/nuclio:init` 只负责 v2 `.dev-docs` skeleton setup/repair/`legacy/v1` 整体移动，`/nuclio:work` 负责 active 三层 `change.md`（人类可读 Spec 角色）、`plan.yaml` 批准合同、`state.yaml` 当前恢复状态的人本 change 工作流，并在知识优先 finish 后将 archive 收敛为只保留精简 `change.md`；4.0.3 明确 successor `change.md` backlink predecessor、active predecessor relation 写入 `state.superseded_by`、predecessor archive `related_changes` 与 State 校验一致，且不 pre-link frozen predecessor、不新增 link-related/hash refresh/手改 State；bounded subagent 不得调用 TaskStop/Stop Task、不得停止/接管 Controller/task-tracking 任务，阻塞时只返回 Coordinator。

## Key Files

- `.claude-plugin/marketplace.json`: Determines which plugins Claude Code can discover.
- `plugins/<plugin-name>/.claude-plugin/plugin.json`: Defines the plugin's name, description, version, and author metadata.
- `plugins/<plugin-name>/skills/<skill-name>/SKILL.md`: Defines skill metadata and the actual prompt.
- `plugins/<plugin-name>/skills/<skill-name>/references/`: Optional skill-local references. Dev-stack uses this for the skill-forge review-state protocol, templates, and validation checklist.
- `plugins/<plugin-name>/skills/<skill-name>/agents/`: Optional skill-local agents. Dev-stack uses this for `skills/skill-forge/agents/skill-creator-eval.md`.
- `plugins/<plugin-name>/skills/<skill-name>/scripts/`: Optional skill-local deterministic helper scripts and tests. Dev-stack uses this for `review-state-helper.py`, `plan_contract.py`, `plan-task-query.py`, and unittest coverage.
- `plugins/<plugin-name>/references/`: Optional plugin-level shared references. Nuclio v2 uses `workflow.md`, `change-format.md`, `knowledge.md`, `context-hygiene.md`, and `eval-prompts.md` as current runtime authority.
- `plugins/<plugin-name>/scripts/`: Optional plugin-level deterministic helper scripts and tests. Nuclio v2 has exactly one runtime helper, `change.py`, plus `test_change.py` and `test_static_plugin.py`.
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

- Daily use goes through `/nuclio:work`; `/nuclio:init` is limited to v2 skeleton setup, navigation repair, and whole-directory movement of old `.dev-docs` content into `.dev-docs/legacy/v1/`. `init` never creates ordinary change artifacts, never approves a Plan, never initializes State, and never implements product work.
- Ordinary active changes use exactly three file-backed runtime artifacts under `.dev-docs/changes/<change-id>/`: `change.md` is the human-readable Spec role and authority, `plan.yaml` is the approved execution contract, and `state.yaml` is the only dynamic recovery-state artifact. Spec is not a separate file.
- `plugins/nuclio-plugin/scripts/change.py` is the only runtime helper and the only writer for `state.yaml`; it also owns explicit `supersede` transitions for predecessor changes taken over by a verified successor. No `workflow.py`, second helper, subprocess state protocol, or hidden runtime state store exists.
- Nuclio runtime depends on PyYAML. `plan.yaml` and `state.yaml` use native YAML with duplicate-key rejection, safe loading/dumping, input-size limits, explicit schema/type checks, and a stable dependency error when PyYAML is missing.
- Product mutation is gated by file-first approval: complete `change.md` Spec role and `plan.yaml` Plan are written to files and `validate-plan` passes; the terminal default shows only artifact paths, a 1-3 line summary, risk/review/repair policy, Task count, `allowed_paths` summary, key exit code, and a natural-language approval prompt.
- Plan uses change-level `allowed_paths` for write boundaries. Nuclio runtime does not use per-Task files ownership, owner mapping, finding owner routing, or behavioral-eval owner fields.
- Each implementation Task and each approved in-scope repair creates exactly one selective-stage local checkpoint commit. Helper validation checks parent, subject, changed paths, clean index, PASS validation, and allowed-path boundaries; Nuclio never auto-squashes, resets, rebases, stashes, or rewrites history.
- `state.yaml` stays light: it stores current phase, current Task, review, validation, repair, blocker, `next_action`, checkpoint identities, and hashes needed for recovery. It must not store complete transition history, full diffs, transcript, long test logs, agent messages, file-content snapshots, or duplicate Git history.
- Finish is knowledge-first after verified product results: always analyze long-term knowledge candidates, record `NO_OP` when none qualify, request user confirmation only for qualified candidates, then `complete`, distill `change.md` into a concise historical record, and archive that lightweight record.
- When an approved scope expansion needs a successor because a frozen predecessor cannot safely continue, successor creation/revision must make successor `change.md.related_changes` name the predecessor; do not pre-link frozen predecessor, add link-related, run hash refresh/rebaseline, or hand-edit State. After the successor successfully archives, the Coordinator must run `supersede` so active predecessor relation is recorded in `state.superseded_by`, then distill the predecessor as a superseded historical record whose archive `related_changes` matches that State relation, and archive it. Nuclio must not infer successor takeover from `-v2` naming, recency, transcript, or predecessor one-way links; superseded records must not pretend old acceptance succeeded, and failures must report remaining active predecessor paths.
- Successful future archives keep only `.dev-docs/changes/archive/<change-id>/change.md`; active `plan.yaml` and `state.yaml` are pruned and are not retained as long-term archive artifacts. Existing archives are not migrated.
- Small, well-bounded single-Task changes may be handled by the main session directly. Larger changes default to bounded generic subagent units when useful for context control, with sequential product writes and compact returns. Bounded subagents must not call TaskStop/Stop Task, create/update/stop/take over Controller/task-tracking tasks, or try to stop themselves, parent tasks, sibling tasks, or background tasks; when complete, blocked, timed out, or needing a decision, they return only a compact result to the Coordinator. Only read-only exploration/review without write conflicts may run concurrently.
- Review/validation failures may use `repair_policy: in-scope` only when paths remain inside `allowed_paths` and the approved Goal/Constraints/Acceptance/risk/contract do not change. Scope expansion, dependency/API/migration changes, irreversible/outward actions, or risk increases require a Plan revision and renewed file-first approval.
- Work follows a sequential lifecycle: locate/create/resume change, clarify intent, write Spec and Plan, validate Plan, obtain user approval, initialize State, execute ordered Tasks with checkpoint commits, apply risk-based review and validation, decide in-scope repair when needed, report product results, always analyze long-term knowledge candidates, request user confirmation only for qualified candidates, record write/partial/modified/rejected/`NO_OP` outcome, complete, distill `change.md`, and archive only that concise record.
- User-visible prose defaults to the user's current primary language; code, commands, paths, field names, and raw output remain literal.
- The v2 maintenance boundary forbids runtime hooks, daemon behavior, MCP integration, network service, project-local `.claude/` installation, `.nuclio/` runtime state, external Superpowers dependency, persistent process JSON, `changes/index.md`, archive manifest, hidden archive backup, a v1 compatibility converter, a v1/v2 dual stack, content snapshots, full State history, automatic fixer, owner budget, owner routing, DAG scheduler, parallel product write engine, restoring the old three-artifact archive-retention promise, or migrating existing archives.

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
python3 -c 'import yaml; print(yaml.__version__)'
```

```bash
python3 plugins/nuclio-plugin/scripts/change.py --help >/dev/null
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

- The repository currently has no application code, package manager manifest, or build scripts; do not assume any npm / pnpm / bun workflow exists.
- This is a marketplace/plugin repository. Preserve the hierarchy “marketplace manifest → plugin metadata → skill directory,” with optional references and scripts when a plugin needs them.
- Dev-stack skill-forge review state is file-backed only under ignored `.skill-forge/<run>/` directories. It is not a daemon, runtime service, background worker, external orchestration layer, MCP integration, runtime hook, DAG scheduler, parallel write engine, or external state store.
- Dev-stack skill-forge first-version product writes are sequential; do not add parallel implementation dispatch or cross-owner auto-selection without a new confirmed contract.
- Dev-stack skill-forge L2/L3 state, ledger, budget, hash drift, recovery, completion, risk/review policy, and transition behavior are maintained by `review-state-helper.py`, `plan_contract.py`, `plan-task-query.py`, and the canonical review-state protocol.
- Nuclio v2 source of truth is the native plugin runtime under `plugins/nuclio-plugin/skills/{init,work}/`, `plugins/nuclio-plugin/references/{workflow,change-format,knowledge,context-hygiene,eval-prompts}.md`, and `plugins/nuclio-plugin/scripts/{change.py,test_change.py,test_static_plugin.py}`.
- Nuclio v2 runtime helper is exactly `plugins/nuclio-plugin/scripts/change.py`; do not add `workflow.py`, a second State writer, subprocess status protocol, runtime schema service, daemon, hook, MCP server, network service, or hidden state directory.
- Nuclio v2 depends on PyYAML and no other third-party runtime dependency. Keep YAML safety checks, duplicate-key rejection, explicit schema/type validation, safe dump, and stable missing-dependency behavior intact.
- Nuclio v2 active changes use three artifacts: `change.md` for Spec, `plan.yaml` for approved contract, and `state.yaml` for current recovery State. Do not reintroduce a single mixed process file, dynamic status authority in `change.md`, or full transition history in State.
- Nuclio v2 finish is knowledge-first: product results are reported first, knowledge candidates are always analyzed, no qualified candidate records `NO_OP`, qualified candidates require user confirmation, and rejection does not block completion or archive.
- Nuclio v2 archive is a future-only concise one-file retention step: after normal `complete` or after `SUPERSEDED`/`ARCHIVE_SUPERSEDED` predecessor closure and distillation, successful archive retains only `change.md`; `plan.yaml` and `state.yaml` are active execution/recovery artifacts and are pruned from long-term archive. Existing archives are not migrated.
- Nuclio v2 Plan uses change-level `allowed_paths`; do not add runtime per-Task files ownership, path owner uniqueness, owner mapping, finding routing, behavioral eval owner fields, or automatic fixer routing.
- Nuclio v2 checkpoints use one selective-stage local commit per implementation Task or in-scope repair. Do not introduce content snapshots, automatic squash/reset/rebase/stash/history rewrite, or checkpoint-less completion.
- Nuclio v2 product writes remain sequential. Do not add DAG scheduling, parallel write execution, cross-owner task routing, or a fixed Nuclio-specific implementer/reviewer/fixer pipeline.
- Nuclio v2 recovery starts from `change.py status` and `change.py next-action`, then Git HEAD/status/diff, checkpoint commits, and deterministic evidence. Do not use chat transcript, agent claim, long logs in State, or archived v1 protocol files as current authority.
- Nuclio v2 deliberately does not add project-local `.claude/` installation, `.nuclio/` runtime state, persistent process JSON, `.dev-docs/changes/index.md`, archive manifest, hidden archive backup, external Superpowers dependency, v1 compatibility converter, or a v1/v2 dual-stack runtime.
- Nuclio v2 clear legacy content may only be moved as a whole into `.dev-docs/legacy/v1/`; it is not parsed, converted, migrated as archive history, or restored as current runtime authority.
