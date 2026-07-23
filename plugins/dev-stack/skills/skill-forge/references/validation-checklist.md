# Internal Validation Checklist

Deterministic-first validation checklist for Skill Forge changes. Run only dimensions relevant to the risk and change, but L2/L3 must preserve whole-change evidence across final/structural/behavioral gates. The canonical L2/L3 ledger, owner mapping, budget, HALT, and transition contract is review-state-protocol.md; this file defines what to check.

## Contents

- [Validation Order](#validation-order)
- [Scriptable Checks](#scriptable-checks)
- [Semantic Checks](#semantic-checks)
- [Dimension 1: Spec Conformance](#dimension-1-spec-conformance)
- [Dimension 2: Pattern Consistency](#dimension-2-pattern-consistency)
- [Dimension 3: Flow Completeness](#dimension-3-flow-completeness)
- [Dimension 4: Structural Compliance](#dimension-4-structural-compliance)
- [Dimension 5: Token Efficiency](#dimension-5-token-efficiency)
- [Dimension 6: Behavioral Correctness](#dimension-6-behavioral-correctness)
- [Observation and Report Shape](#observation-and-report-shape)

---

## Validation Order

1. Determine risk and changed contract surface.
2. Run scriptable checks first: schema, exact paths, line counts, Contents/anchors, tool boundaries, JSON/YAML validity, command/test checks, and commit/ownership checks.
3. If any scriptable check FAILs, do not dispatch LLM reviewer first. Fix within scope or report through the L2/L3 protocol.
4. Run semantic checks only after applicable deterministic checks pass or are explicitly not applicable.
5. L2/L3 structural and behavioral observations use the same finding schema and shared owner budget described in review-state-protocol.md.

---

## Scriptable Checks

| Area | Example command/check | Applies when |
|---|---|---|
| Plugin metadata JSON | `python3 -m json.tool <plugin.json> >/dev/null` | metadata touched or full audit |
| Plugin strict validation | `claude plugin validate plugins/dev-stack --strict` | dev-stack skill/plugin changes |
| Plan schema | `python3 plugins/dev-stack/skills/skill-forge/scripts/plan-task-query.py <plan> <task-id> --output <new-brief>` in a disposable run path, or shared Plan validator through helper commands | L2/L3 Plan changes |
| Ownership path contract | Ensure create/modify/delete entries are exact repo-relative paths, unique, no globs/spaces/absolute/`..` | Plan/template changes |
| Body line count | Count SKILL.md body after frontmatter; pass if < 500 | SKILL.md touched |
| Large Markdown Contents | Every Markdown file > 100 lines has `## Contents` and matching anchors | Markdown touched |
| Reference depth | references are one level deep and references files do not Markdown-link other references files | reference changes |
| Stale wording | Search for removed legacy phase anchors, non-stable brief defaults, and forced all-task reviewer wording | protocol/template changes |
| Tool authority | Parse bounded agent frontmatter for forbidden write/delegation tools | agent contract or full audit |
| Commit contract | Check exactly expected implementation/fix subject and ownership-only diff | L2/L3 helper flow |
| Tests | Run focused script unit tests or static probes for changed scripts/docs | script or contract changes |

---

## Semantic Checks

LLM or human semantic review covers items that cannot be reduced to a stable local command:

- Spec/Plan acceptance coverage and non-goal preservation.
- Pattern fit and whether Risk-Adaptive Composite components are combined correctly.
- Cross-Task consistency, owner boundaries, and user-facing behavior intent.
- Whether deterministic evidence is sufficient for a `final-only` L2 Task.
- Whether an audit scope truly covers affected contracts beyond git diff.
- Whether behavioral eval prompts represent the changed user behavior.

Semantic review must cite the contract source and changed path. It must not override a failing deterministic check.

---

## Dimension 1: Spec Conformance

| Check | Type | Pass Criteria |
|---|---|---|
| Contract coverage | Semantic | Every input/output/side effect in Spec is implemented or explicitly non-goal |
| Success criteria coverage | Semantic | Every success criterion maps to workflow steps and validation evidence |
| Boundary respect | Scriptable + semantic | Prohibited behaviors are absent by search and by contract reading |
| Joint approval | Semantic | L2/L3 Spec and Plan receive one implementation approval Gate; L0/L1 do not repeat clearly granted reversible authorization |
| Upgrade triggers | Semantic | Scope expansion, irreversible/outward-facing action, ownership ambiguity, or unobservable validation stop and upgrade |

---

## Dimension 2: Pattern Consistency

| Check | Type | Pass Criteria |
|---|---|---|
| Risk-Adaptive Composite | Semantic | Router, Sequential Controller, HITL, Generator-Critic, and Validation Gate are combined according to L0-L3 |
| No premature Pattern Selection | Semantic | Pattern Selection runs only for CREATE, Pattern/Architecture changes, or real design choices |
| Sequential writes | Scriptable + semantic | No instruction introduces parallel product writes in the current version |
| Dispatch counts | Semantic | L0=0 agents; L1≤1 implementation unit plus one whole-diff review; L2=T+R+1+E with R≤T and E∈{0,1}; L3 strict task-and-final |

---

## Dimension 3: Flow Completeness

| Check | Type | Pass Criteria |
|---|---|---|
| Routing coverage | Scriptable + semantic | CREATE, MODIFY, CHANGE_AUDIT, FULL_AUDIT, ambiguity, and no-match are covered |
| AUDIT read-only | Semantic | Audit path cannot Edit/Write/commit and FULL_AUDIT reads complete related surfaces, not only git diff |
| Deterministic-first | Semantic | Reviewers are blocked behind applicable schema/static/test checks |
| Helper authority | Scriptable + semantic | L2/L3 state transitions use review-state-helper.py next-action only |
| Recovery/HALT | Semantic | API failures, hash drift, no-progress, budget exhaustion, owner ambiguity, and contract disputes produce deterministic HALT or recovery evidence |

---

## Dimension 4: Structural Compliance

| Check | Type | Pass Criteria |
|---|---|---|
| description format | Scriptable/manual | Starts with `Use when`, third person, ≤1024 chars |
| name format | Scriptable/manual | ≤64 chars, letters/numbers/hyphens only |
| SKILL.md body | Scriptable | <500 lines excluding frontmatter |
| Large Markdown Contents | Scriptable | Files >100 lines include Contents with anchor links |
| References one level | Scriptable | No nested reference directories and no Markdown links from one references file to another references file |
| Stable logic | Semantic | Deterministic logic lives in scripts rather than copied prose when it must be executable |
| Marketplace sync | Scriptable + semantic | Metadata, README, and CLAUDE guidance are checked when touched or full-audited |

---

## Dimension 5: Token Efficiency

| Check | Type | Pass Criteria |
|---|---|---|
| No conflicting duplicates | Scriptable + semantic | Detailed L2/L3 lifecycle/schema/budget appears only in review-state-protocol.md |
| Summaries only elsewhere | Semantic | SKILL.md, templates.md, and this checklist keep only role-specific summaries |
| Inline length | Scriptable | Long examples and templates live in references, not SKILL.md body |
| Anchor clarity | Scriptable + semantic | Contents anchors are stable and headings are specific |

---

## Dimension 6: Behavioral Correctness

Run behavioral validation only when user behavior, Routing, Gate, Pattern, or Architecture changed. Otherwise produce SKIP evidence.

| Check | Type | Pass Criteria |
|---|---|---|
| Routing behavior | Behavioral/semantic | CREATE/MODIFY/CHANGE_AUDIT/FULL_AUDIT prompts route as expected |
| Gate behavior | Behavioral/semantic | Required confirmations pause; already authorized L0/L1 reversible work is not re-asked |
| Risk escalation | Behavioral/semantic | Ambiguity raises risk; runtime scope/ownership/validation problems stop and upgrade |
| Consistency rerun | Behavioral | Only Routing/Gate changes set `run_consistency=true`, with at most one extra run per selected prompt |
| Baseline comparison | Behavioral | Only Pattern/Architecture changes set `run_baseline=true`; otherwise SKIP |
| Eval ownership | Semantic | Every eval case maps to the Task that owns the contract; ambiguity is resolved before L2/L3 init |

---

## Observation and Report Shape

For L2/L3 validation failures:

1. Save a schema v1 observation with command, exit code, output, base/head evidence, contract/rubric reference, origin, severity, and exact required_fix_paths.
2. Import through helper; do not directly edit product files after final review or validation failure.
3. Helper performs owner mapping and budget handling. Same Gate/same owner findings are one fixer dispatch; multi-owner or no-owner findings HALT for user decision.
4. BASELINE, MINOR, suggestion, OUT_OF_CONTRACT, invalid observation, and API/transport failure do not consume budget.

Report validation by listing command/check, exit code or PASS/FAIL/SKIP, output summary, evidence path when applicable, and any residual risk. Do not state that reviewer Gate passed unless helper state says so.
