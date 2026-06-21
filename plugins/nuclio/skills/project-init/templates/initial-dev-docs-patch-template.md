# Initial Dev Docs Patch: <project name>

## Source
- `.nuclio/project/project-brief.md`
- `.nuclio/project/architecture-baseline.md`
- `.nuclio/project/scaffold-plan.yaml`

## Summary

## Proposed Files

Candidate rows are proposals only. Do not fill human decisions here.

| id | target | operation | reason | confidence |
| --- | --- | --- | --- | --- |
| D1 | .dev-docs/index.md | create | Initialize project memory navigation | high |
| D2 | .dev-docs/product/index.md | create | Initialize product knowledge index | high |
| D3 | .dev-docs/architecture/index.md | create | Initialize architecture knowledge index | high |

### Update D1

- id: D1
- target: .dev-docs/index.md
- operation: create
- reason: Initialize project memory navigation
- confidence: high

```markdown
# Dev Docs

| Path | Load Mode | Visible In | Load When |
|------|-----------|------------|-----------|
| product/index.md | index | spec, design | Product behavior is relevant |
| architecture/index.md | index | design, build | Architecture constraints are relevant |
```

### Update D2

- id: D2
- target: .dev-docs/product/index.md
- operation: create
- reason: Initialize product knowledge index
- confidence: high

```markdown
# Product Index

| Path | Load Mode | Visible In | Load When |
|------|-----------|------------|-----------|
| overview.md | leaf | spec, design | Product behavior is relevant |
```

### Update D3

- id: D3
- target: .dev-docs/architecture/index.md
- operation: create
- reason: Initialize architecture knowledge index
- confidence: high

```markdown
# Architecture Index

| Path | Load Mode | Visible In | Load When |
|------|-----------|------------|-----------|
| overview.md | leaf | design, build | Architecture constraints are relevant |
```

## Human Approval Decisions

Fill only after explicit Memory Approval.

| id | decision | approved_content_ref | note |
| --- | --- | --- | --- |

## Deferred Docs

## Approval Checklist
- [ ] Files are useful now, not empty placeholders.
- [ ] Document structure is minimal and navigation is clear.
- [ ] Architecture decisions match approved baseline.
- [ ] No secrets or local-only accidental data.
