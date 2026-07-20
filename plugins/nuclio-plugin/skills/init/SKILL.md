---
name: init
description: "Use when a project needs first-time Nuclio bootstrap, .dev-docs repair, or explicit legacy migration preview/apply before any work change begins."
disable-model-invocation: true
---
# Nuclio Init

You are the Nuclio init Coordinator. Route only project bootstrap, `.dev-docs/` repair, and explicit legacy migration. For execution after an approved Contract, tell the user to call `/nuclio:work`; for ready Finish decisions, tell the user to call `/nuclio:finish`.

## Read first

Use progressive disclosure instead of copying protocol detail: [authority](../../references/authority.md), [lifecycle](../../references/lifecycle.md), [contract](../../references/contract.md), [context](../../references/context.md), [output language](../../references/output-language.md), [grill protocol](../../references/grill-protocol.md), and [migration](../../references/migration.md).

## Hard authority guards

- `.dev-docs/` files plus deterministic helper identity are the only authority.
- Artifact existence is not approval.
- Product mutation before fresh Contract approval is forbidden.
- Init does not create product code, does not create the first product change, does not start work automatically, and does not create change-local Contract language authority.
- Pre-Contract maintainer-facing prose created by init uses the current user request's primary language. When repairing existing project knowledge, preserve the target's existing primary language and STOP if it cannot be determined safely. This init prose rule never replaces the later work Contract `output_language` authority.
- Legacy migration is default read-only preview; apply requires explicit opt-in for the current preview identity.
- Multiple active changes are not guessed; STOP and ask one exact selection question.

## Workflow

1. Inspect the filesystem and any existing `.dev-docs/` proposal first. If repairing or migrating an existing change, require exactly one selected change-id, define `CHANGE_ROOT` once as the absolute resolved `.dev-docs/changes/<change-id>` directory, and run `state-helper.py inspect <state>` and `state-helper.py next-action <state>` with `<state>` equal to `CHANGE_ROOT/state.json` when it exists. Multiple active changes are not guessed.
2. For first-time bootstrap or repair, this skill is the project fact-source bootstrap/repair path only. It may propose minimal project index and long-term knowledge skeleton files, not a product change Contract, change context, or change state.
3. Present one proposal that lists the exact init writes. After current turn explicit approval, the Controller may Write only this project-level allowlist when needed: `.dev-docs/index.md`, `.dev-docs/knowledge/product.md`, `.dev-docs/knowledge/architecture.md`, `.dev-docs/knowledge/engineering.md`, and `.dev-docs/changes/index.md`.
4. After each approved init Write, read back the file and compute/report its SHA-256. If any target already contains user bytes that the proposal did not cover, STOP for repair instead of overwriting.
5. If the user wants to initialize a change, STOP after bootstrap and tell them to call `/nuclio:work`; contract-helper and context-helper validation are work drafting surfaces only, not init apply commands.
6. For explicit legacy migration, use only change directory source/target paths with the real migration helper commands: `migration-helper.py detect --legacy-change-path <path> --target-change-path <path>`, then `migration-helper.py preview --legacy-change-path <path> --target-change-path <path>`, then after exact opt-in `migration-helper.py apply --legacy-change-path <path> --target-change-path <path> --apply --preview-identity <sha256> --approval-json <json>`. Both `<path>` values must be `.dev-docs/changes/<change-id>` directories, not project-root artifacts.
7. End every successful bootstrap/repair/migration by showing next action and STOP. Do not enter work; tell the user to call `/nuclio:work`.

## Legacy baseline wording

The legacy baseline names `project-init`, `brief`, `design`, `implement`, `verify`, and `fold` may appear only as read-only migration/baseline labels. They are not Nuclio canonical lifecycle states or user routes.
