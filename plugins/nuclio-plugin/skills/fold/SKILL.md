---
name: fold
description: Use when the user wants to fold a verified Nucl.io change by writing stable conclusions back into long-term `.dev-docs` knowledge, without archiving full chat history or raw logs, and stop with a Fold completion report.
---

# Nucl.io Fold

## Critical Constraints

- Fold 只处理 verify 后的 completed change；verify 未通过或 evidence 缺失时，必须 STOP 并要求先运行 `/nuclio:verify` 或补充证据。
- 只读取当前 completed change 的 stable artifacts：`brief.md`、`spec.md`、`design.md`、`plan.yaml`、`evidence/review.md`、必要 diff summary。
- 不读取或归档完整历史对话；不归档完整聊天记录、raw long logs、session journals、comments/reviewer history 或 daemon task history。
- 不默认读取整个 `.dev-docs/`，不默认读取全部 source files。
- 只更新相关长期知识文档，例如 `.dev-docs/architecture/decisions.md`、`.dev-docs/architecture/constraints.md`、`.dev-docs/engineering/testing.md`、`.dev-docs/domain/model.md`、`.dev-docs/product/glossary.md`、`.dev-docs/index.md` 或对应二级 index。
- 不大范围重写全部 `.dev-docs`。
- 不重复已有知识；若稳定结论已存在，只引用或跳过。
- `.dev-docs/` 是 source-of-truth；`.nuclio/` 仍是 runtime/cache/temp state only，本轮不实现 runtime 或 hooks。
- 不实现 `/nuclio:status`、`/nuclio:resume`、hooks、runtime state automation、optional scripts、CLI、daemon、MCP、multi-agent platform、cross-project RAG、automatic context budget reporting 或 verify-loop enhancements。
- 不依赖 `grill-me`，不 fork Trellis，不复制 Chorus 式全量上下文注入。

## Contents

- [Critical Constraints](#critical-constraints)
- [Workflow](#workflow)
- [Phase 1: Determine Fold Scope](#phase-1-determine-fold-scope)
- [Phase 2: Load Stable Inputs](#phase-2-load-stable-inputs)
- [Phase 3: Extract Stable Conclusions](#phase-3-extract-stable-conclusions)
- [Phase 4: Update Relevant Long-Term Docs](#phase-4-update-relevant-long-term-docs)
- [Phase 5: Update Change State / Archive Marker](#phase-5-update-change-state--archive-marker)
- [Phase 6: Fold Gate / Completion Report](#phase-6-fold-gate--completion-report)
- [Behavior Verification](#behavior-verification)

## Workflow

Fold 用于在 verify 之后关闭当前 Nucl.io change 的生命周期，把已经验证通过的稳定结论沉淀回长期 `.dev-docs` knowledge，而不是继续停留在一次性会话上下文中。

整体模式采用 Generator-Critic + Sequential HITL：先生成候选 stable conclusions，再以 critic 方式筛除临时、重复、原始或越界内容，最后把通过筛选的结论按顺序写回相关长期文档，并停在可审查的 completion report。

执行时先从 current change 的 completed artifacts 生成候选 stable conclusions，只围绕 brief、spec、design、plan、review evidence 和必要 diff summary 工作，不从完整聊天记录或长日志补全上下文。

随后使用 critic 方式过滤所有 temporary、duplicated、raw、speculative 或 out-of-scope 内容，只保留适合长期复用的 decisions、constraints、domain terms、testing guidance、known pitfalls 和 validation summaries。

通过筛选后，只把相关结论写入对应的长期 `.dev-docs` 文档，并保持现有结构稳定；如果没有值得沉淀的稳定知识，应明确 no-op，而不是为了折叠而重写文档。

Sequential HITL 体现在每个 gate 都要求先确认 target、verify evidence 和文档边界，避免模型把 fold 扩展成 status、resume、runtime、hooks 或全量归档任务。

在执行顺序上，先确认 scope，再加载稳定输入，再抽取结论、更新文档、更新 state，最后输出 completion report；不要跳步，也不要把未验证的过程信息提前写入长期知识。

如果用户要求同时做归档、状态查看、恢复会话或 runtime 设计，必须把这些需求拆开处理，并明确说明本次 fold 只负责 verified knowledge write-back。

Fold 完成后只输出 completion report 并停止，不继续进入 status、resume、runtime、hooks 或其他后续能力讨论。

## Phase 1: Determine Fold Scope

- Locate current change from explicit user path or `.dev-docs/changes/index.md` / `state.json` evidence.
- If target is ambiguous, STOP and ask for the change path.
- Confirm verify evidence exists and indicates pass/accept; otherwise STOP and require `/nuclio:verify` or evidence.
- Do not use `.nuclio/` runtime state as source-of-truth.

## Phase 2: Load Stable Inputs

- Load only `brief.md`, `spec.md`, `design.md`, `plan.yaml`, `evidence/review.md`, necessary diff summary, and relevant long-term doc indexes.
- Do not load full chat history, raw logs, session journals, all `.dev-docs`, all source files, comments or reviewer history.
- If necessary artifacts are missing, report confidence impact or STOP when fold would become speculative.

## Phase 3: Extract Stable Conclusions

- Generate candidate conclusions grouped by Project, Product, Architecture, Engineering, Domain, and Change summary.
- Critic-filter candidates: keep only decisions, constraints, domain terms, testing guidance, known pitfalls, reusable validation summaries.
- Drop temporary guesses, one-off process notes, raw command output, implementation minutiae, duplicate knowledge, and any runtime/hook/status/resume scope.

## Phase 4: Update Relevant Long-Term Docs

- Update only docs relevant to accepted candidates.
- Suggested targets: `.dev-docs/architecture/decisions.md`, `.dev-docs/architecture/constraints.md`, `.dev-docs/engineering/testing.md`, `.dev-docs/domain/model.md`, `.dev-docs/product/glossary.md`, `.dev-docs/project/principles.md`, `.dev-docs/index.md`, and corresponding second-level indexes.
- Preserve existing content and structure; append or minimally edit.
- If no stable conclusion exists, perform no-op and report why.

## Phase 5: Update Change State / Archive Marker

- If fold succeeds, update current change `state.json` by preserving/merging existing fields.
- Recommended update: `phase: fold` and `status: completed`, or mark archived only when project convention already supports archive.
- Do not move directories unless user explicitly asks and project convention is clear.
- Do not store raw runtime state in Git-tracked knowledge files.

## Phase 6: Fold Gate / Completion Report

- Output changed files, stable conclusions folded, skipped candidates with reasons, validation evidence, and suggested next step.
- End with exact STOP text:

```text
STOP. Fold Complete：stable conclusions 已写回相关 `.dev-docs` knowledge。请 review 变更；如需 status/resume/runtime/hooks，请单独开启后续设计。
```

## Behavior Verification

- RED: baseline may archive full chat history, paste raw logs, rewrite all `.dev-docs`, or implement status/resume/hooks during fold.
- GREEN: fold reads only stable artifacts, updates only relevant docs, filters temporary/raw/duplicated/out-of-scope content, and stops with Fold Complete.
- REFACTOR: no full chat transcript, no raw logs, no reviewer history, no session journal, no all-doc rewrite, no runtime/hook/status/resume implementation.
- Wording micro-test strategy: manually run at least 5 repetitions each for prompts asking to archive all chat, save full logs, rewrite `.dev-docs`, and implement status/runtime/hooks; flag any output that violates boundaries.
