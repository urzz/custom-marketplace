# Output Language Policy

## Contents

- [Purpose](#purpose)
- [Authority Priority](#authority-priority)
- [Language Tag](#language-tag)
- [Applicable Artifacts](#applicable-artifacts)
- [Machine-Stable English](#machine-stable-english)
- [Human-Readable Prose](#human-readable-prose)
- [Raw Passthrough](#raw-passthrough)
- [Knowledge Target Language](#knowledge-target-language)
- [Gate Tokens and Document Language](#gate-tokens-and-document-language)
- [Historical Archives](#historical-archives)
- [Bounded Agent Contracts](#bounded-agent-contracts)

## Purpose

Nuclio separates machine-stable protocol tokens from human-readable maintainer prose.
The selected `output_language` controls prose produced for maintainers, while stable
protocol fields remain canonical English so helpers, schemas, hashes, Gate records,
packets, and review imports stay deterministic.

This policy is canonical for Nuclio output language behavior. It is consumed by
Coordinator prompts, packet dispatch, bounded agents, Finish application, and future
Task 5 synchronization work. It does not authorize any state transition, Gate approval,
knowledge application, archive rewrite, or ownership expansion.

## Authority Priority

When choosing a document language, follow this authority order and fail closed on
missing required values:

1. Contract-bound `output_language` recorded in the current approved Contract and
   propagated into task, review, fix, and completion packets.
2. Packet-bound `output_language` in the current dispatch envelope, when it matches
   the current Contract identity and packet identity.
3. Finish target language metadata for Finish-only artifacts, when the Finish packet
   explicitly binds it to the same change identity.
4. Existing knowledge target language when applying to an existing long-term target.
5. New knowledge target language metadata when creating a new target.

Agents must not infer language from chat history, branch names, repository locale,
previous agent prose, filenames, user profile memory, or adjacent task reports. If the
required packet or envelope language is absent or contradictory, the bounded agent must
return its existing fail-closed status instead of guessing.

## Language Tag

`output_language` is a stable language tag string supplied by Nuclio authority. A tag
identifies the intended language for human-readable prose. Common values may include
`zh-CN` or `en`, but this policy does not restrict the schema beyond the authoritative
contract and packet validation rules.

The tag is data, not a Gate token. It must be copied exactly where machine records need
identity preservation. Do not translate, normalize, localize, or paraphrase the tag in
schemas, helper inputs, packet identity, report identity sections, or evidence records.

## Applicable Artifacts

The `output_language` prose rule applies to maintainer-facing prose in:

- implementation attempt reports from `nuclio-implementer`;
- task review reports from `nuclio-task-reviewer`;
- fixer attempt reports from `nuclio-fixer`;
- whole-change completion critiques from `nuclio-completion-critic`;
- `completion.md` body prose;
- `decision.md` body prose;
- Finish apply summaries and archive summaries;
- knowledge proposal rationale, target notes, and maintainer explanation prose;
- blocker explanations, concern descriptions, finding summaries, failure scenarios,
  required fixes, closure explanations, coverage explanations, remaining-risk prose,
  and nonblocking notes.

The policy does not require translating machine-stable protocol material embedded inside
those artifacts.

## Machine-Stable English

Keep the following tokens in canonical English or their original machine form:

- JSON, YAML, schema, and packet keys;
- status enums, verdict enums, severity enums, helper actions, and state values;
- fixed Markdown headings required by a packet, report schema, helper import, review
  package, hash input, or downstream parser;
- table column names in fixed report schemas;
- identity keys such as `scope`, `ticket`, `task_id`, `model`, `packet_path`,
  `state_path`, `contract_sha256`, `context_fingerprint`, `state_version`,
  `base_head`, `new_head`, `packet_id`, and `change_id`;
- paths, filenames, branch names, commit SHAs, hashes, command names, CLI flags, class
  names, function names, schema names, constants, and environment variable names;
- exact Gate tokens and aliases as defined by helper boundaries;
- literal protocol lines such as `Completion Verdict: PASS|FAIL`;
- raw command output, raw error output, stack traces, diffs, log excerpts, and quoted
  source text.

Do not translate machine-stable English even when the surrounding prose uses another
language. This protects state import, reviewer comparison, packet validation, and hash
chain stability.

## Human-Readable Prose

Write human-readable prose in `output_language` when the text is not a fixed protocol
token. This includes:

- implementation summaries and validation explanations;
- blockers, concerns, design-revision reasons, and maintainer-facing rationale;
- finding summaries, failure scenarios, required fixes, cannot-verify explanations, and
  review notes;
- fix actions, closure explanations, blocker explanations, and concerns;
- completion coverage explanations, remaining risks, findings, notes, and critique prose;
- Finish decision body prose, Finish apply prose, archive prose, and knowledge proposal
  prose.

If a prose sentence includes a stable key, enum, path, command, or quoted raw output,
keep that stable segment unchanged and write only the surrounding explanation in
`output_language`.

## Raw Passthrough

Raw command output and raw error output must be preserved exactly enough to support
review and debugging. Agents may shorten long output only when the existing report schema
allows relevant excerpts, but they must not translate or rewrite the excerpt.

Examples of raw passthrough include:

- shell stdout and stderr;
- failing test output;
- exception text and stack traces;
- compiler, linter, schema, helper, Git, or CLI errors;
- generated diffs or quoted source snippets;
- tool transport error text when it is quoted as evidence.

A prose explanation around raw output may use `output_language`; the raw output itself
keeps its original text.

## Knowledge Target Language

Knowledge target language follows target authority rather than chat inference:

- Existing target: preserve the existing target language and style unless Finish target
  metadata explicitly authorizes a different language for new prose. Do not translate the
  existing file merely because `output_language` differs.
- New target: require explicit Finish target language metadata before packet derivation
  and before apply. The target must declare `before_sha256: null`, `target_language`
  equal to packet `output_language`, and `language_source: contract_output_language`.
- Unknown target or missing, unknown, or contradictory target metadata: STOP before
  packet derivation or apply; do not draft or write irreversible knowledge changes.

Machine-stable identifiers inside knowledge targets remain unchanged. Historical facts,
quoted commands, hashes, paths, and schema tokens remain in their original form.

## Gate Tokens and Document Language

Gate decisions and document language are orthogonal. Exact Gate tokens, accepted aliases,
canonical helper values, state transition names, and stored approval records remain
machine-stable. A localized prose document does not localize Gate tokens, and a localized
Gate explanation does not authorize semantic weakening of the Gate.

Do not interpret a vague localized phrase as a final `accept`. Gate freshness, exact
normalization, authority, state import, hash checks, and helper-only transitions remain
unchanged.

## Historical Archives

Historical archives, prior reports, accepted evidence, hash-chain inputs, snapshots,
fingerprints, archived `completion.md`, archived `decision.md`, and long-term knowledge
records are not rewritten solely to match a new language policy. Preserve prior artifacts
as historical evidence.

New archive summaries or new Finish prose may use the current target language, but quoted
historical material and machine-stable records stay unchanged.

## Bounded Agent Contracts

All bounded Nuclio agents must consume `output_language` from the packet or dispatch
envelope authority. They must not read the full conversation to infer language.

`nuclio-implementer` keeps fixed Markdown headings, status enums, identity keys, paths,
commands, and raw output in machine-stable English or original form. Implementation
summary, validation explanation, blockers, and concerns use `output_language`.

`nuclio-task-reviewer` keeps fixed headings, table columns, verdict enums, severity
enums, identity keys, paths, commands, and raw output in machine-stable English or
original form. Finding summary, failure scenario, required fix, cannot-verify prose, and
notes use `output_language`.

`nuclio-fixer` consumes the same `output_language` as the original worker packet or
helper authorization envelope. Status, budget fields, finding IDs, paths, commands, and
raw output stay machine-stable or original. Fix actions, closure explanations, blockers,
and concerns use `output_language`.

`nuclio-completion-critic` consumes `output_language` from the completion packet. The
literal `Completion Verdict: PASS|FAIL`, fixed report headings, identity keys, table
columns, severity enums, paths, commands, and raw output stay machine-stable or original.
Coverage explanations, remaining risks, findings, notes, and critique prose use
`output_language`.
