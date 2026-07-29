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

Some plugins may also include shared references and helper scripts. The Nuclio v2 plugin uses plugin-level `references/` and `scripts/`. The dev-stack `skill-forge` skill uses skill-local `references/` and `scripts/`, plus plugin-level bounded agents.

当前 marketplace 注册三个插件：

- `openclaw-plugin`：提供 `/openclaw-skill-creator`。
- `dev-stack`：提供显式调用的 `/skill-forge` 和 `/commit`；`/skill-forge` 通过 Focused/Grill 澄清、第一性原理综合、已确认 Spec、精简 Plan、顺序实施和 deterministic-first 验证创建、修改或只读审查 Claude Code skill。
- `nuclio`：提供 `/nuclio:init` 和 `/nuclio:work`；`/nuclio:init` 只负责 v2 `.dev-docs` skeleton setup/repair/`legacy/v1` 整体移动，`/nuclio:work` 负责 active 三层 `change.md`（人类可读 Spec 角色）、`plan.yaml` 批准合同、`state.yaml` 当前恢复状态的人本 change 工作流，并在知识优先 finish 后将 archive 收敛为只保留精简 `change.md`；4.0.5 保持 `state.git_branch` 分支锁定（branch drift/detached HEAD fail closed，禁止 Coordinator/subagent 创建、切换、重命名分支或 worktree，禁止 `task4-member-auth-dto-vo` 这类临时 Task 分支）、archive checkpoint commit/recovery、successor `change.md` backlink predecessor、active predecessor relation 写入 `state.superseded_by`、predecessor archive `related_changes` 与 State 校验一致，且不 pre-link frozen predecessor、不新增 link-related/hash refresh/手改 State；同时采用场景化增量审查，普通开发可 final-only，少数风险 Task 可选择性 task review，高风险仍保持 task-and-final；bounded subagent 不得调用 TaskStop/Stop Task、不得停止/接管 Controller/task-tracking 任务，阻塞时只返回 Coordinator。

## Key Files

- `.claude-plugin/marketplace.json`: Determines which plugins Claude Code can discover.
- `plugins/<plugin-name>/.claude-plugin/plugin.json`: Defines the plugin's name, description, version, and author metadata.
- `plugins/<plugin-name>/skills/<skill-name>/SKILL.md`: Defines skill metadata and the actual prompt.
- `plugins/<plugin-name>/skills/<skill-name>/references/`: Optional skill-local references. Dev-stack uses this for the skill-forge clarification protocol, templates, and validation checklist.
- `plugins/<plugin-name>/skills/<skill-name>/agents/`: Optional skill-local agents. Skill-forge does not currently use this directory.
- `plugins/<plugin-name>/skills/<skill-name>/scripts/`: Optional skill-local deterministic helper scripts and tests. Dev-stack uses this for `plan_contract.py` and `test_plan_contract.py`.
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
- `init-state` freezes the current attached `state.git_branch`; State-driven commands and archive recovery fail closed on `BRANCH_DRIFT` or `DETACHED_HEAD`. The Coordinator and bounded subagents must not create, switch, or rename branches, must not create worktrees, and must not move execution to temporary task branches such as `task4-member-auth-dto-vo`.
- Each implementation Task and each approved in-scope repair creates exactly one selective-stage local checkpoint commit. Helper validation checks parent, subject, changed paths, clean index, branch identity, PASS validation, and allowed-path boundaries; Nuclio never auto-squashes, resets, rebases, stashes, switches branches, or rewrites history.
- `state.yaml` stays light: it stores current phase, current Task, review, validation, repair, blocker, `next_action`, checkpoint identities, and hashes needed for recovery. It must not store complete transition history, full diffs, transcript, long test logs, agent messages, file-content snapshots, or duplicate Git history.
- Finish is knowledge-first after verified product results: always analyze long-term knowledge candidates, record `NO_OP` when none qualify, request user confirmation only for qualified candidates, then `complete`, distill `change.md` into a concise historical record, and archive that lightweight record.
- When an approved scope expansion needs a successor because a frozen predecessor cannot safely continue, successor creation/revision must make successor `change.md.related_changes` name the predecessor; do not pre-link frozen predecessor, add link-related, run hash refresh/rebaseline, or hand-edit State. After the successor successfully archives, the Coordinator must run `supersede` so active predecessor relation is recorded in `state.superseded_by`, then distill the predecessor as a superseded historical record whose archive `related_changes` matches that State relation, and archive it. Nuclio must not infer successor takeover from `-v2` naming, recency, transcript, or predecessor one-way links; superseded records must not pretend old acceptance succeeded, and failures must report remaining active predecessor paths.
- Successful future archives keep only `.dev-docs/changes/archive/<change-id>/change.md`; active `plan.yaml` and `state.yaml` are pruned and are not retained as long-term archive artifacts. Helper creates exactly one verified archive checkpoint commit with subject `archive(<change-id>): retain distilled change record`; changed paths must include active `change.md`, active `plan.yaml`, active `state.yaml`, and archive `change.md`. Pending-state write failure restores the active three artifacts, while moved/pruned pre-commit or commit interruption is recovered by rerunning the same archive command on the frozen branch. Existing archives are not migrated.
- Scenario-based incremental review is used: ordinary development can stay final-only with mandatory final review, selected risky Tasks may receive task review when failure impact, coupling, or validation strength warrants it, and high-risk changes remain task-and-final. Review policy is decided by scenario and risk, not by programming language.
- Small, well-bounded single-Task changes may be handled by the main session directly. Larger changes default to bounded generic subagent units when useful for context control, with sequential product writes and compact returns. Bounded subagents must not call TaskStop/Stop Task, create/update/stop/take over Controller/task-tracking tasks, or try to stop themselves, parent tasks, sibling tasks, or background tasks; when complete, blocked, timed out, or needing a decision, they return only a compact result to the Coordinator. Only read-only exploration/review without write conflicts may run concurrently.
- Review/validation failures may use `repair_policy: in-scope` only when paths remain inside `allowed_paths` and the approved Goal/Constraints/Acceptance/risk/contract do not change. Scope expansion, dependency/API/migration changes, irreversible/outward actions, or risk increases require a Plan revision and renewed file-first approval.
- Work follows a sequential lifecycle: locate/create/resume change, clarify intent, write Spec and Plan, validate Plan, obtain user approval, initialize State, execute ordered Tasks with checkpoint commits, apply risk-based review and validation, decide in-scope repair when needed, report product results, always analyze long-term knowledge candidates, request user confirmation only for qualified candidates, record write/partial/modified/rejected/`NO_OP` outcome, complete, distill `change.md`, and archive only that concise record.
- User-visible prose defaults to the user's current primary language; code, commands, paths, field names, and raw output remain literal.
- The v2 maintenance boundary forbids runtime hooks, daemon behavior, MCP integration, network service, project-local `.claude/` installation, `.nuclio/` runtime state, external Superpowers dependency, persistent process JSON, `changes/index.md`, archive manifest, hidden archive backup, a v1 compatibility converter, a v1/v2 dual stack, content snapshots, full State history, automatic fixer, owner budget, owner routing, DAG scheduler, parallel product write engine, restoring the old three-artifact archive-retention promise, or migrating existing archives.

Dev-stack skill 的通用同步原则：修改任一 skill 时，保持对应 `plugins/dev-stack/skills/<skill-name>/SKILL.md`、一层 `references/`、插件元数据、README / CLAUDE 说明与本地校验命令一致。`/commit` 由 `plugins/dev-stack/skills/commit/SKILL.md` 定义主流程，并由 `plugins/dev-stack/skills/commit/references/change-analysis.md` 与 `plugins/dev-stack/skills/commit/references/commit-policy.md` 维护变更分析和提交策略；修改 `/commit` 时必须同步这些文件、`plugins/dev-stack/.claude-plugin/plugin.json` 的版本、README / CLAUDE 说明与本地校验命令。`/commit` 必须维持自包含执行边界：不调用 `/verify`、其他 skill、agent、workflow、MCP、网络或外部服务，不使用 skill-forge 的 bounded agents 或 scripts，也不新增 runtime hook、daemon 或本地状态机制。最终 Conventional Commit 的 type、scope、summary 与 body 的唯一语义来源是选择性暂存后重新读取的最终 staged diff；未进入最终 staged diff 的内容不得影响最终消息。内部行为变更不得误写成 marketplace source、plugin name 或外部依赖变化。

Dev-stack `skill-forge` 变更还需要保持以下专用文件同步：

- `plugins/dev-stack/skills/skill-forge/SKILL.md`
- `plugins/dev-stack/skills/skill-forge/references/*.md`
- `plugins/dev-stack/agents/*.md`
- `plugins/dev-stack/skills/skill-forge/scripts/*.py`
- `plugins/dev-stack/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `README.md`
- `CLAUDE.md`

维护 dev-stack `skill-forge` 时保持以下不变量：

- `/skill-forge` 使用 `disable-model-invocation: true`，只在用户显式调用时运行；只面向 Claude Code，不声明其他宿主兼容。
- CREATE 和 MODIFY 先通过 Focused 或 Grill 澄清真实问题；`grill me` 保留一次一问、建议优先的苏格拉底式追问，First Principles Synthesis 进入 `spec.md`。
- 用户确认 Spec 后才生成 Plan；只有 Plan 新增删除、依赖、权限、外部副作用或用户选择时才追加一次确认。
- `plan_contract.py` 是唯一 Plan validator，负责重复 YAML key、Spec hash、精确 repo-relative path、跨 Task ownership、文件前置条件、placeholder、字段类型和空 checks；不负责风险分类或状态推进。
- deterministic-first 是强制维护原则：JSON/YAML/schema/static/test/plugin validation 等可本地运行的检查必须先于 LLM reviewer/eval；LLM review 不能替代失败的确定性校验。
- 主 Session 是唯一 Controller，产品写入按 Task 顺序执行；bounded implementer 只能修改一个 Task 的精确 paths，bounded reviewer 必须保持只读，二者都不写 report、不 delegation、不 commit。
- AUDIT 始终只读且不创建 run；默认 run 只有 `spec.md` 和 `plan.yaml`，仅跨会话多 Task 恢复可增加轻量 `state.json`。
- 行为评测仅在 trigger/core behavior 变化时运行 3-5 个 fresh-session cases；独立 reviewer 仅用于权限、外部副作用、带副作用 script 或高影响核心控制流程。
- 不恢复风险等级、review-state、Gate、ledger、fix budget、checkpoint commit、自动 squash 或 Git 历史改写，也不新增 DAG scheduler、并行产品写入、外部 orchestration、MCP、network service、daemon、runtime hook 或 worktree 依赖。

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
- Dev-stack skill-forge default run artifacts are only ignored `.skill-forge/<run>/spec.md` and `plan.yaml`; optional `state.json` is a lightweight cross-session cursor, never a workflow state machine.
- Dev-stack skill-forge product writes are sequential; do not add parallel implementation dispatch or cross-owner auto-selection without a new confirmed Spec and Plan.
- Dev-stack skill-forge has exactly one runtime helper, `plan_contract.py`, plus its unit test. Do not reintroduce risk classifiers, review-state helpers, task-brief generators, Gate/ledger protocols, automatic commits, or fixer pipelines.
- Nuclio v2 source of truth is the native plugin runtime under `plugins/nuclio-plugin/skills/{init,work}/`, `plugins/nuclio-plugin/references/{workflow,change-format,knowledge,context-hygiene,eval-prompts}.md`, and `plugins/nuclio-plugin/scripts/{change.py,test_change.py,test_static_plugin.py}`.
- Nuclio v2 runtime helper is exactly `plugins/nuclio-plugin/scripts/change.py`; do not add `workflow.py`, a second State writer, subprocess status protocol, runtime schema service, daemon, hook, MCP server, network service, or hidden state directory.
- Nuclio v2 depends on PyYAML and no other third-party runtime dependency. Keep YAML safety checks, duplicate-key rejection, explicit schema/type validation, safe dump, and stable missing-dependency behavior intact.
- Nuclio v2 active changes use three artifacts: `change.md` for Spec, `plan.yaml` for approved contract, and `state.yaml` for current recovery State. Do not reintroduce a single mixed process file, dynamic status authority in `change.md`, or full transition history in State.
- Nuclio v2 finish is knowledge-first: product results are reported first, knowledge candidates are always analyzed, no qualified candidate records `NO_OP`, qualified candidates require user confirmation, and rejection does not block completion or archive.
- Nuclio v2 archive is a future-only concise one-file retention step: after normal `complete` or after `SUPERSEDED`/`ARCHIVE_SUPERSEDED` predecessor closure and distillation, successful archive retains only `change.md`; `plan.yaml` and `state.yaml` are active execution/recovery artifacts and are pruned from long-term archive. Existing archives are not migrated.
- Nuclio v2 Plan uses change-level `allowed_paths`; do not add runtime per-Task files ownership, path owner uniqueness, owner mapping, finding routing, behavioral eval owner fields, or automatic fixer routing.
- Nuclio v2 review is scenario-based and incremental: ordinary development can use final-only, selected risky Tasks can add task review, and high-risk work stays task-and-final. Do not imply a schema or dependency change for this review-policy clarification.
- Nuclio v2 checkpoints use one selective-stage local commit per implementation Task or in-scope repair, and archive uses one helper-verified checkpoint commit for the active-three-artifacts to one-file archive transition. Do not introduce content snapshots, automatic squash/reset/rebase/stash/history rewrite, branch switching, or checkpoint-less completion.
- Nuclio v2 product writes remain sequential. Do not add DAG scheduling, parallel write execution, cross-owner task routing, or a fixed Nuclio-specific implementer/reviewer/fixer pipeline.
- Nuclio v2 recovery starts from `change.py status` and `change.py next-action`, then frozen `state.git_branch`, Git HEAD/status/diff, checkpoint commits, and deterministic evidence. Branch drift or detached HEAD fails closed; do not create/switch/rename branches, create worktrees, move work to task-named temporary branches such as `task4-member-auth-dto-vo`, use chat transcript, agent claim, long logs in State, or archived v1 protocol files as current authority.
- Nuclio v2 deliberately does not add project-local `.claude/` installation, `.nuclio/` runtime state, persistent process JSON, `.dev-docs/changes/index.md`, archive manifest, hidden archive backup, external Superpowers dependency, v1 compatibility converter, or a v1/v2 dual-stack runtime.
- Nuclio v2 clear legacy content may only be moved as a whole into `.dev-docs/legacy/v1/`; it is not parsed, converted, migrated as archive history, or restored as current runtime authority.
