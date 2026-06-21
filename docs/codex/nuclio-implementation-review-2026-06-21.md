# Nucl.io Implementation Review

Date: 2026-06-21

Design source: `.claude/plans/nuclio-design.md`

Implementation reviewed:

- `plugins/nuclio/skills/**`
- `plugins/nuclio/hooks/**`
- `plugins/nuclio/scripts/**`
- `plugins/nuclio/agents/**`
- `plugins/nuclio/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`

No Nucl.io implementation files were modified during this review.

## Executive Summary

Current implementation has a recognizable Nucl.io MVP skeleton: marketplace entry, plugin manifest, seven workflow skills, three agents, hook files, helper scripts, templates, and a passing static smoke test suite.

However, it is not fully aligned with the design yet. The biggest gaps are not missing files; they are contract mismatches between design, templates, validators, hooks, and marketplace execution:

1. Plugin-first execution is undermined by project-relative helper script paths.
2. Project Init state cannot pass the current state validator because `repository_stage` enums disagree.
3. Review/event result enums cannot represent `needs_patch` or `needs_redesign`.
4. Memory patch templates mix proposal and approval decisions, weakening the human gate boundary.
5. Context loading and `.dev-docs` index protocol are mostly prompt-level instructions, with weak deterministic validation.

## Verification Performed

Commands run:

```sh
node plugins/nuclio/scripts/nuclio-smoke-test.mjs
node plugins/nuclio/scripts/validate-state.mjs plugins/nuclio/skills/project-init/templates/init-state-template.json
node plugins/nuclio/scripts/validate-state.mjs plugins/nuclio/skills/spec/templates/state-template.json
node plugins/nuclio/scripts/validate-plan.mjs plugins/nuclio/skills/design/templates/plan-template.yaml --section tasks
node plugins/nuclio/scripts/validate-plan.mjs plugins/nuclio/skills/project-init/templates/scaffold-plan-template.yaml --section scaffold_tasks
node plugins/nuclio/scripts/validate-event.mjs '{"type":"task.reviewed","tool":null,"artifact":".nuclio/changes/c1/evidence/review.md","result":"needs_patch"}'
```

Results:

- Smoke test passed: 19/19 subtests.
- Spec state template passed validation.
- Design plan template passed validation.
- Scaffold plan template passed validation.
- Project Init state template failed validation.
- `task.reviewed` event with `needs_patch` failed validation.

## Findings

### F1. Plugin-first execution is broken by project-relative helper paths

Severity: High

Design expectation:

- Nucl.io workflow capabilities live in the plugin; project repositories should only need `.nuclio/` and `.dev-docs/` (`.claude/plans/nuclio-design.md:2768`, `:2772`, `:2900`).
- Plugin scripts live under plugin `scripts/`, not copied into every target project (`.claude/plans/nuclio-design.md:2782`, `:2786`).

Implementation evidence:

- Skills instruct the agent to run project-relative commands such as `node plugins/nuclio/scripts/bootstrap-check.mjs`:
  - `plugins/nuclio/skills/spec/SKILL.md:27`
  - `plugins/nuclio/skills/design/SKILL.md:30`
  - `plugins/nuclio/skills/build/SKILL.md:31`
  - `plugins/nuclio/skills/close/SKILL.md:28`
  - `plugins/nuclio/skills/project-init/SKILL.md:31`
  - `plugins/nuclio/skills/apply-memory/SKILL.md:24`
  - `plugins/nuclio/skills/resume/SKILL.md:28`
- `guard.mjs` only treats these helper paths as controlled helpers when the script path is exactly `plugins/nuclio/scripts/write-state.mjs` or `plugins/nuclio/scripts/append-event.mjs` (`plugins/nuclio/hooks/guard.mjs:614`, `:617`).

Why this matters:

In a real marketplace-installed plugin, an arbitrary user project should not contain `plugins/nuclio/scripts/*`. The skill commands will fail unless the user happens to be working inside this marketplace repository. If the skills are changed to use `${CLAUDE_PLUGIN_ROOT}`, the current guard helper recognizer will likely stop recognizing those absolute plugin paths and may block them as ambiguous Node commands during an active workflow.

Recommendation:

- Use plugin-root-aware script invocation in skills.
- Teach `guard.mjs` to recognize controlled helper scripts through `${CLAUDE_PLUGIN_ROOT}` or another canonical plugin-root path.
- Add a smoke test that runs Nucl.io helper commands from a temporary project that does not contain `plugins/nuclio`.

### F2. Project Init state template is incompatible with the validator

Severity: High

Design expectation:

- `repository_stage` values are `empty_repo`, `skeleton_repo`, `existing_app_without_foundation`, and `existing_app_with_foundation` (`.claude/plans/nuclio-design.md:952`).

Implementation evidence:

- Project Init template uses `existing_app_without_foundation` (`plugins/nuclio/skills/project-init/templates/init-state-template.json:13`), which matches the design.
- `validate-state.mjs` accepts `new`, `existing`, `unknown`, `greenfield`, and `brownfield` instead (`plugins/nuclio/scripts/validate-state.mjs:23`).
- `guard.mjs` has the same non-design enum (`plugins/nuclio/hooks/guard.mjs:42`).
- Running validation fails:

```text
Invalid repository_stage: existing_app_without_foundation. Expected one of: new, existing, unknown, greenfield, brownfield, null
```

Why this matters:

`project-init` explicitly says to use the template and write state through `write-state.mjs`/`validate-state.mjs` (`plugins/nuclio/skills/project-init/SKILL.md:224`, `:228`). The canonical template cannot be written through the canonical writer, so Project Init is blocked or forced to drift away from the design.

Recommendation:

- Align `validate-state.mjs`, `guard.mjs`, and templates to the design enum.
- Add a regression test that validates every state template directly.

### F3. Review result events cannot represent design-required outcomes

Severity: High

Design expectation:

- Review result must be one of `pass | needs_patch | needs_redesign | blocked` (`.claude/plans/nuclio-design.md:1516`).
- Event examples include `{"type":"task.reviewed","result":"needs_patch"}` (`.claude/plans/nuclio-design.md:1862`).

Implementation evidence:

- `review-template.md` correctly lists `pass | needs_patch | needs_redesign | blocked` (`plugins/nuclio/skills/build/templates/review-template.md:17`).
- `agents/reviewer.md` also requires `needs_patch` and `needs_redesign` (`plugins/nuclio/agents/reviewer.md:45`).
- `validate-event.mjs` only accepts `pass`, `fail`, `blocked`, and `unknown` for `event.result` (`plugins/nuclio/scripts/validate-event.mjs:5`, `:66`).
- Running validation for a design-valid review event fails:

```text
event.result must be one of: pass, fail, blocked, unknown, null
```

Why this matters:

Build is supposed to append typed `task.reviewed` events as the patch loop progresses (`plugins/nuclio/skills/build/SKILL.md:128`). The canonical event helper rejects the review outcomes needed to drive `patch` vs `redesign` behavior.

Recommendation:

- Extend event result validation to include `needs_patch` and `needs_redesign`, or introduce a separate `review_result` field with the design enum.
- Add tests for `task.reviewed` events with all review template outcomes.

### F4. Memory patch templates collapse proposal and approval into one artifact

Severity: High

Design expectation:

- `initial-dev-docs.patch.md` and `memory.patch.md` are candidate patches generated before approval (`.claude/plans/nuclio-design.md:836`, `:898`, `:2456`).
- Approval decisions happen at the human gate; each proposed update can later be `accept`, `reject`, `edit`, or `defer` (`.claude/plans/nuclio-design.md:2534`).
- Proposed updates should contain target, operation, confidence/reason, and diff/content details (`.claude/plans/nuclio-design.md:2472`).

Implementation evidence:

- `memory-patch-template.md` requires a `decision` column inside `## Proposed Updates`, with sample rows already marked `accept`, `edit`, `reject`, and `defer` (`plugins/nuclio/skills/close/templates/memory-patch-template.md:14`, `:16`).
- `initial-dev-docs-patch-template.md` does the same for `## Proposed Files` (`plugins/nuclio/skills/project-init/templates/initial-dev-docs-patch-template.md:37`, `:39`).
- `validate-memory-patch.mjs` requires every parsed row to already contain a decision (`plugins/nuclio/scripts/validate-memory-patch.mjs:111`, `:118`).
- Close asks to validate `memory.patch.md` before asking for Memory Approval (`plugins/nuclio/skills/close/SKILL.md:180`).

Why this matters:

The artifact that should propose candidate knowledge already contains approval decisions. This makes it ambiguous whether `accept/edit/reject/defer` is the AI's suggestion or the user's decision. It also makes guard approval rely on content inside a pre-approval proposal once `approved.memory === true` is set.

Recommendation:

- Split proposal fields from human decision fields.
- Candidate patch should include `id`, `target`, `operation`, `reason`, `confidence`, and proposed content/diff.
- Approval decisions should either live in a separate approval record or be added only after explicit user approval.
- Validators should support pre-approval candidate validation separately from post-approval decision validation.

### F5. Memory patch templates do not provide enough content to apply updates

Severity: Medium

Design expectation:

- Memory patches include concrete proposed update blocks and diff/content snippets (`.claude/plans/nuclio-design.md:2472`, `:2481`).
- Initial Dev Docs patches include proposed file content blocks (`.claude/plans/nuclio-design.md:855`, `:861`, `:869`, `:875`).

Implementation evidence:

- `memory-patch-template.md` only contains a table of `id`, `target`, and `decision` (`plugins/nuclio/skills/close/templates/memory-patch-template.md:16`).
- `initial-dev-docs-patch-template.md` only contains a table of `id`, `target`, and `decision` (`plugins/nuclio/skills/project-init/templates/initial-dev-docs-patch-template.md:39`).
- `validate-memory-patch.mjs` validates only `id`, `.dev-docs` target, and decision (`plugins/nuclio/scripts/validate-memory-patch.mjs:115`).

Why this matters:

`/nuclio:apply-memory` is supposed to apply approved updates. With only target paths and decisions, there is no deterministic update operation or content to apply.

Recommendation:

- Expand both templates to require operation and proposed content.
- Validate that accepted/edited rows include applicable content or a structured patch.

### F6. `change_kind` enum differs from the design

Severity: Medium

Design expectation:

- `change_kind` values are `feature | bugfix | refactor | tech_debt | docs | maintenance` (`.claude/plans/nuclio-design.md:1649`).

Implementation evidence:

- `validate-state.mjs` accepts `feature`, `bugfix`, `refactor`, `docs`, `test`, `chore`, and `spike` (`plugins/nuclio/scripts/validate-state.mjs:22`).
- `guard.mjs` uses the same implementation enum (`plugins/nuclio/hooks/guard.mjs:41`).

Why this matters:

Design-valid changes with `tech_debt` or `maintenance` will fail validation, while non-design kinds such as `chore` and `spike` are accepted.

Recommendation:

- Align the enum to the design, or update the design if the implementation enum is intentional.

### F7. Bootstrap Check does not satisfy the action contract

Severity: Medium

Design expectation:

- `BootstrapCheck` should report `repository_stage`, `has_nuclio_dir`, `has_dev_docs`, `project_init_state`, `active_changes`, and `recommendation` (`.claude/plans/nuclio-design.md:3738`).
- It should judge whether the current requested skill is suitable to continue (`.claude/plans/nuclio-design.md:1698`).

Implementation evidence:

- `bootstrap-check.mjs` does not accept `requested_skill`.
- It reports `foundation`, `foundation_details`, `project_state`, `active_changes`, `next_action`, and `errors` (`plugins/nuclio/scripts/bootstrap-check.mjs:78`).
- It determines foundation readiness only from `.nuclio` and `.dev-docs/index.md` existence (`plugins/nuclio/scripts/bootstrap-check.mjs:51`).

Why this matters:

Project Init needs repository stage to branch safely, and phase skills need skill-specific recommendations. The current bootstrap check is useful, but it is closer to a state linter than the full design contract.

Recommendation:

- Add `requested_skill` input.
- Return design-named fields or clearly revise the design/skill contract.
- Implement repository-stage detection aligned to the design enum.

### F8. Plan validation is weaker than the Build/Design contract

Severity: Medium

Design expectation:

- `plan.yaml` is a task graph, with dependencies, task types, risks, path boundaries, acceptance, verification, and review focus (`.claude/plans/nuclio-design.md:1306`, `:1345`).
- Design skill says tasks must include `type`, `risk`, `allowed_paths`, `forbidden_paths`, `acceptance`, `verify`, and `review_focus` (`plugins/nuclio/skills/design/SKILL.md:31`).

Implementation evidence:

- `validate-plan.mjs` requires only non-empty `allowed_paths` and `forbidden_paths` for every task (`plugins/nuclio/scripts/validate-plan.mjs:144`).
- For change tasks it checks `acceptance`, `verify`, and `review_focus`, but not `type`, `risk`, or dependency validity (`plugins/nuclio/scripts/validate-plan.mjs:148`).
- It does not validate graph ordering, missing dependency IDs, cycles, task type enum, risk enum, source links, or `global_acceptance`.

Why this matters:

Build depends on the plan as its source of truth. A malformed or under-specified task graph can pass validation and later leave Build or guard without enough information to enforce the workflow.

Recommendation:

- Validate `type`, `risk`, `depends_on`, dependency graph, source fields, and `global_acceptance`.
- Consider a real YAML parser for this script.

### F9. SelectContext and `.dev-docs` index protocol are not deterministically checked

Severity: Medium

Design expectation:

- Runtime context loading must follow root index -> second-level index -> leaf docs, without scanning all leaf frontmatter (`.claude/plans/nuclio-design.md:2231`, `:2251`).
- Index rows should support `Path`, `Load Mode`, `Visible In`, and `Load When` (`.claude/plans/nuclio-design.md:2196`).
- MVP includes `.dev-docs/index.md + multi-level index.md` and `SelectContext` loading protocol (`.claude/plans/nuclio-design.md:4052`).

Implementation evidence:

- Spec skill instructs context-report or typed context events (`plugins/nuclio/skills/spec/SKILL.md:28`).
- `context-report-template.md` records loaded/skipped/missing context, but does not enforce index table semantics (`plugins/nuclio/skills/spec/templates/context-report-template.md:7`).
- `validate-context-report.mjs` only checks for broad words like `.dev-docs/index.md`, `Loaded`, `Skipped`, `reason`, and missing/stale/not applicable (`plugins/nuclio/scripts/validate-context-report.mjs:151`).
- No `validate-dev-docs-index.mjs` exists, even though the design's plugin script list includes it (`.claude/plans/nuclio-design.md:2856`).

Why this matters:

The design's core context-engineering value depends on index-routed loading. Current implementation records intent, but does not reliably validate that an artifact followed the routing protocol.

Recommendation:

- Add deterministic validation for `.dev-docs/index.md` and second-level index tables.
- Validate context reports against actual selected index/doc paths when files exist.
- Keep SelectContext as a behavior contract, but strengthen audit artifacts.

### F10. Guard does not protect approved `.nuclio` artifacts from phase-inappropriate edits

Severity: Medium

Design expectation:

- Spec, Design, Build, and Close are separated by human gates.
- Build must not modify Spec or Design without returning to the proper phase (`.claude/plans/nuclio-design.md:3208`, `:3213`).

Implementation evidence:

- `guard.mjs` classifies `.nuclio` paths separately from application paths and `.dev-docs` paths (`plugins/nuclio/hooks/guard.mjs:337`, `:342`).
- Application path checks and `.dev-docs` approval checks do not apply to `.nuclio` artifact writes (`plugins/nuclio/hooks/guard.mjs:1215`, `:1225`).
- Build skill relies on prompt rules to avoid editing `spec.md` or `design.md` (`plugins/nuclio/skills/build/SKILL.md:121`, `:131`).

Why this matters:

Approved workflow artifacts can be modified during the wrong phase unless the model follows the skill prompt. This weakens the design goal that hooks enforce deterministic constraints.

Recommendation:

- Add guard rules for phase-owned `.nuclio` artifacts, especially approved `spec.md`, `design.md`, `plan.yaml`, close artifacts, and state transitions.
- Allow state/events writes only through controlled helpers or scoped phase rules.

### F11. Event log stores raw tool input/output snippets

Severity: Medium

Design expectation:

- Event logs should record file write events, Bash command/result summaries, blocked operations, and context-loading audit (`.claude/plans/nuclio-design.md:3464`).

Implementation evidence:

- `event-log.mjs` writes a `debug` object containing the first 500 characters of raw tool input and raw tool output (`plugins/nuclio/hooks/event-log.mjs:201`).

Why this matters:

Tool input/output may include secrets, tokens, file content, local paths, or verbose logs. This is broader than a result summary and may create durable sensitive data in `.nuclio/**/events.jsonl`.

Recommendation:

- Remove raw debug logging by default.
- Log structured command/result summaries and target paths only.
- If debug logging is retained, make it opt-in and redact common secret patterns.

### F12. `output-filter.mjs` hook placement does not match the design and likely does not filter the original output

Severity: Low

Design expectation:

- `output-filter.mjs` is described as `PreToolUse: Bash` (`.claude/plans/nuclio-design.md:3474`).

Implementation evidence:

- `hooks.json` registers `output-filter.mjs` under `PostToolUse` for `Bash` (`plugins/nuclio/hooks/hooks.json:19`, `:29`).
- The script prints filtered lines from `CLAUDE_TOOL_OUTPUT` (`plugins/nuclio/hooks/output-filter.mjs:1`).

Why this matters:

The current hook may add filtered output as an extra hook result, but it is not proven to replace or reduce the original tool output in the model context. If the goal is token reduction, this needs runtime verification.

Recommendation:

- Confirm Claude Code hook semantics for output replacement.
- Update either the design or implementation to match the intended trigger and effect.

### F13. Browser verification dependency is declared but not packaged or checked

Severity: Low

Design expectation:

- Browser verification uses the external `dev-browser` skill (`.claude/plans/nuclio-design.md:3577`, `:3598`, `:3629`).

Implementation evidence:

- `browser-verifier.md` declares `skills: - dev-browser` (`plugins/nuclio/agents/browser-verifier.md:8`).
- No `dev-browser` skill exists in this repository based on `rg`.

Why this matters:

This may be acceptable if `dev-browser` is expected to be installed separately, but the current plugin does not declare or check that dependency. UI verification can fail late.

Recommendation:

- Document the external dependency clearly.
- Add a bootstrap warning when UI verification is requested but `dev-browser` is unavailable.

### F14. Plugin manifest is more minimal than the design example

Severity: Low

Design expectation:

- Manifest example includes metadata such as `author`, `homepage`, `repository`, `license`, and `strict` (`.claude/plans/nuclio-design.md:2869`).

Implementation evidence:

- `plugins/nuclio/.claude-plugin/plugin.json` contains only `name`, `description`, and `version` (`plugins/nuclio/.claude-plugin/plugin.json:1`).

Why this matters:

This probably does not block local discovery, and marketplace root registration exists (`.claude-plugin/marketplace.json:19`). It may still be incomplete for marketplace readiness if the design metadata is expected.

Recommendation:

- Decide whether the design example is mandatory. If yes, complete metadata and add `strict`.

## Areas That Match the Design Well

- Plugin root structure is present and matches the expected high-level shape: `skills/`, `agents/`, `hooks/`, `scripts/`, and plugin manifest.
- The seven core skills exist: `project-init`, `spec`, `design`, `build`, `close`, `resume`, and `apply-memory`.
- Skills mostly express the intended gates: Foundation, Architecture, Scaffold, Initial Dev Docs, Spec, Design, and Memory Approval.
- The Build skill includes task order, path boundaries, verify/review evidence, independent reviewer, and patch-loop guidance.
- Reviewer/debugger/browser-verifier agents are read-only by default.
- `guard.mjs` is substantial and enforces several important constraints:
  - `.dev-docs` writes require canonical approval state.
  - Build writes require `phase === build`, `approved.design === true`, and `state.current_task`.
  - Task `allowed_paths` and `forbidden_paths` are enforced for application writes.
  - Dangerous Bash patterns such as `git push`, `kubectl`, `terraform apply`, and `rm -rf` are blocked unless scoped risk approval exists.
  - Invalid Nucl.io state fails closed for application and `.dev-docs` writes.
- Static smoke tests cover meaningful guard and helper behavior and currently pass.

## Recommended Fix Order

1. Fix plugin-first helper execution paths and guard helper recognition.
2. Align `repository_stage`, `change_kind`, and event result enums across design, templates, validators, and hooks.
3. Split candidate patch validation from approval-decision validation for memory and initial dev docs.
4. Expand memory patch templates to include operation/content/diff details.
5. Strengthen BootstrapCheck and SelectContext/index validation.
6. Add guard rules for phase-owned `.nuclio` artifacts.
7. Reduce event-log raw debug persistence.
8. Clarify output-filter and dev-browser dependency behavior.

## Overall Assessment

Nucl.io currently looks like a solid static MVP skeleton with a meaningful guard implementation, but it is not yet ready as a design-compliant marketplace workflow. The most important next step is to make the file protocol internally consistent: states, events, approvals, helper paths, and validators need to agree with the design before real project onboarding.
