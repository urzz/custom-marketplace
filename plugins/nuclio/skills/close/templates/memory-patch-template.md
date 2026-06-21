# Memory Patch: <change-id>

## Source
- Spec: `.nuclio/changes/<change-id>/spec.md`
- Design: `.nuclio/changes/<change-id>/design.md`
- Plan: `.nuclio/changes/<change-id>/plan.yaml`
- Verify: `.nuclio/changes/<change-id>/evidence/verify.md`
- Review: `.nuclio/changes/<change-id>/evidence/review.md`
- Close: `.nuclio/changes/<change-id>/close.md`
- Events: `.nuclio/changes/<change-id>/events.jsonl`

## Summary

## Proposed Updates

Candidate rows are proposals only. Do not fill human decisions here.

| id | target | operation | reason | confidence |
| --- | --- | --- | --- | --- |
| U1 | .dev-docs/architecture/index.md | update | Add routing note from completed change | high |
| U2 | .dev-docs/changes/<change-id>.md | create | Capture stable implementation knowledge from this change | medium |

### Update U1

- id: U1
- target: .dev-docs/architecture/index.md
- operation: update
- reason: Add routing note from completed change
- confidence: high

```diff
--- before
+++ after
@@
- Existing architecture index entry.
+ Existing architecture index entry with the stable routing note from <change-id>.
```

### Update U2

- id: U2
- target: .dev-docs/changes/<change-id>.md
- operation: create
- reason: Capture stable implementation knowledge from this change
- confidence: medium

```markdown
# <change-id> Knowledge

Stable, reusable project knowledge from this completed change.
```

## Human Approval Decisions

Fill only after explicit Memory Approval.

| id | decision | approved_content_ref | note |
| --- | --- | --- | --- |

## Rejected Candidates

## Stale Checks
