# Context Report: <change-id>

## Purpose

Record SelectContext decisions for this Nucl.io change so later phases can audit which project knowledge was loaded or skipped from `.dev-docs` routing indexes.

## SelectContext Decisions

| index | selected_path | load_mode | visible_in | load_when | decision | reason |
|---|---|---|---|---|---|---|
| .dev-docs/index.md | .dev-docs/index.md | index | spec, design, build, close | Root routing index for project knowledge | loaded | Always load the root routing index before selecting project context. |
| .dev-docs/index.md | .dev-docs/<topic>.md | conditional | spec | <condition from Load When column> | skipped | Not applicable to this change; replace with a concrete reason when used. |

## Notes

- Use `decision=loaded` only for context actually read into the workflow.
- Use `decision=skipped` for candidate context considered but intentionally not loaded.
- Keep `load_mode` aligned with `.dev-docs/index.md`: `index`, `leaf`, `always`, or `conditional`.
- Include `.dev-docs/index.md` in at least one row for every report.

## Event Log Notes

When possible, mirror these decisions into `.nuclio/changes/<change-id>/events.jsonl` using typed `context.root_loaded`, `context.index_loaded`, `context.doc_loaded`, and `context.doc_skipped` events.
