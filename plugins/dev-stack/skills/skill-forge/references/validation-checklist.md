# Internal Validation Checklist

Used by Phase 5 to validate skill output before delegating to skill-forge Eval.

## Contents
- Dimension 1: Spec Conformance
- Dimension 2: Pattern Consistency
- Dimension 3: Flow Completeness
- Dimension 4: Structural Compliance
- Dimension 5: Token Efficiency
- Dimension 6: Behavioral Correctness

---

## Dimension 1: Spec Conformance

Compare implementation against the confirmed Spec from Phase 2.

| Check | Pass Criteria | How to Verify |
|-------|--------------|---------------|
| Contract coverage | Every input/output/side-effect in Spec Section 2 is implemented | Manual check (semantic): Read SKILL.md, match each contract item |
| Success criteria coverage | Every assertion in Spec Section 5 is achievable by the workflow | Manual check (semantic): Trace each criterion to a specific Step |
| Boundary respect | Nothing in Spec Section 4 "明确不做的事" is present | `grep -rn '<prohibited-behavior-keyword>' SKILL.md references/` |
| Gate coverage | Every Hard Gate in Spec Section 3 has a corresponding user confirmation point | `grep -c 'Hard Gate\|等待用户\|Gate' SKILL.md` 对照 Spec 计数 |

---

## Dimension 2: Pattern Consistency

Verify the implementation structurally matches the selected Google 8 Pattern.

| Check | Pass Criteria | How to Verify |
|-------|--------------|---------------|
| Primary pattern structure | Workflow skeleton matches the pattern's SKILL.md template from references/design-patterns.md | Manual check (semantic): compare structural elements |
| Secondary pattern integration | If Spec declares secondary patterns, they appear in the correct phases | Manual check (semantic) |
| No pattern drift | No steps that contradict the selected pattern (e.g., parallel spawn in a declared Sequential) | `grep -n 'spawn\|parallel' SKILL.md` 对照 Pattern 声明 |

**How to verify:** Read references/design-patterns.md for the selected pattern's template. Compare structural elements (step ordering, spawn points, loop boundaries, gate locations).

---

## Dimension 3: Flow Completeness

| Check | Pass Criteria | How to Verify |
|-------|--------------|---------------|
| Exit conditions | Every Step has an explicit, verifiable exit condition | Manual check (semantic) |
| Gate enforcement | Hard Gates use imperative language ("Wait for user confirmation before proceeding") | `grep -n 'Hard Gate\|等待用户\|Gate' SKILL.md` |
| Error/loop handling | Question loops have explicit safety valves; review/fix loops use one per-Task shared maximum=2 budget plus deterministic no-progress/budget HALT | `grep -n 'maximum=2\|HALTED_NO_PROGRESS\|HALTED_BUDGET_EXHAUSTED\|≤.*问\|安全阀' SKILL.md references/review-state-protocol.md` |
| Path coverage | Both CREATE and MODIFY paths are handled (if applicable) | `grep -n 'CREATE\|MODIFY\|AUDIT' SKILL.md` |

---

## Dimension 4: Structural Compliance (Anthropic Best Practices)

| Check | Pass Criteria | Command |
|-------|--------------|---------|
| description starts with "Use when" | First two words are "Use when" | Manual check |
| description ≤ 1024 chars | Character count ≤ 1024 | `echo -n "<desc>" \| wc -c` |
| description third person | No "I", "you", "we" in description | Manual check |
| Body < 500 lines | Line count < 500 (excluding frontmatter) | `awk '/^---$/{n++; next} n>=2' SKILL.md \| wc -l` |
| No nested references | Files in references/ do not link to other files in references/ | `python3 -c "import pathlib,re,sys; s='.'+'md'; rx=re.compile(r'\[[^\]]+\]\([^)]*'+re.escape(s)+r'[^)]*\)'); hits=[]; [hits.append((p,i,line)) for p in pathlib.Path('references').rglob('*'+s) for i,line in enumerate(p.read_text(encoding='utf-8').splitlines(),1) if rx.search(line)]; [print(f'{p}:{i}:{line}') for p,i,line in hits]; sys.exit(1 if hits else 0)"` |
| Large file TOC | Files > 100 lines have `## Contents` with valid anchors | Python heading/anchor check over changed Markdown |
| Bounded reviewer tools | Plugin-level reviewer/final reviewer frontmatter excludes Agent/Skill/Workflow/Edit/Write/Task/EnterWorktree | Parse frontmatter and assert forbidden-set intersection is empty |
| Controller wording | SKILL has no unbounded review phrase; Phase 5 has no implementer repair dispatch | `grep -n '直至通过\|重新 dispatch implementer' SKILL.md` returns no output |
| name format | ≤ 64 chars, letters/numbers/hyphens only | Manual check |

---

## Dimension 5: Token Efficiency

| Check | Pass Criteria | How to Verify |
|-------|--------------|---------------|
| No redundant explanations | No explaining concepts Claude already knows | Manual check (semantic) |
| No duplicate content | Same instruction not repeated in multiple places | `grep -rn '<repeated-phrase>' SKILL.md references/` |
| Inline code blocks < 50 lines | No single code block exceeds 50 lines | `awk '/^~~~|```/{n++; if(n%2==1) start=NR; if(n%2==0) print NR-start}' SKILL.md` |
| Heavy content separated | Content > 100 lines lives in references/, not inline | `wc -l references/*.md` + `grep -c '^## ' SKILL.md` |

---

## Dimension 6: Behavioral Correctness

**验证时机：** Phase 5.2（前提: Dimension 1-5 全部通过）

**验证方法：** 使用 Phase 4 Step 4.3 生成的 Eval Prompts，spawn eval agent 执行模拟验证。

### 6.1 路径正确性

| 检查项 | 通过标准 |
|--------|----------|
| CREATE prompt → CREATE path | 100% 路径匹配预期 |
| MODIFY prompt → MODIFY path | 100% 路径匹配预期 |
| Routing 规则与 SKILL.md Routing section 一致 | 无矛盾 |

### 6.2 Gate 完整性

| 检查项 | 通过标准 |
|--------|----------|
| 每个 Hard Gate 处暂停等待用户确认 | 所有 Gate 均触发暂停 |
| Gate 通过前不执行后续 Phase | 无跳过行为 |
| Gate 通过后立即执行 Persist（如有） | Persist 产物存在 |

### 6.3 边界处理

| 检查项 | 通过标准 |
|--------|----------|
| 模糊输入（无法判断 CREATE/MODIFY） | 主动向用户澄清 |
| 跨领域输入（与 skill 创建无关） | 不触发，或正确拒绝 |
| 部分信息输入（缺少关键上下文） | 提问补充，不假设 |

### 6.4 输出格式

| 检查项 | 通过标准 |
|--------|----------|
| description format | starts with "Use when", third person, ≤ 1024 chars |
| Body line count | < 500 lines |
| Progressive disclosure | content > 100 lines in references/ |
| TOC presence | files > 100 lines have `## Contents` |

### 6.5 一致性

| 检查项 | 通过标准 |
|--------|----------|
| 同一 prompt 执行 1 次 | 路径选择一致；仅 Routing/Gate 逻辑改动时追加 1 次重跑，路径选择一致 |
| 输出结构一致 | 产出 section 顺序和层级不变 |

### 6.6 质量基线（LLM-as-Judge）— 条件触发

**条件触发：** 仅当 Delta Spec 的 Changed 部分包含 Pattern/Architecture 级改动时才执行 with-skill vs baseline 双跑；纯内容/文案微调（无结构变化）跳过该维度，标记为 SKIP。

| 检查项 | 通过标准 |
|--------|----------|
| with-skill vs baseline 双跑 | 输出质量不低于 baseline（纯内容微调 SKIP） |

### 失败处理

1. 任一子维度失败都生成与 reviewer 相同 schema 的 observation，包含具体 prompt、
   expected/actual、base/head evidence、contract/rubric ref 与 exact `required_fix_paths`。
2. Controller 保存原始 JSON 后调用 helper `import-review`；不得直接改文件或调用 implementer。
3. Helper 对每条 finding 做唯一 owner mapping。同 Gate/同 owner findings 合并；同一
   observation 出现多个 owner 时保留逐 finding owner/evidence，所有 owner budget 不消费，
   确定性 `HALTED_NEEDS_DECISION`。用户裁定后回 Phase 3 修订 Plan，在新 run 重新 init。
4. 只有 helper `authorize-fix` 后才 dispatch bounded fixer。Task review、final review、
   structural validation、behavioral validation 共用 owner Task 的 maximum=2 budget；
   unchanged blocker set、regression 或预算耗尽分别确定性 HALT。
5. BASELINE、MINOR、suggestion、OUT_OF_CONTRACT、非法 observation 与 API failure 不消费 budget。

---

## Validation Flow

1. Helper 返回 `RUN_STRUCTURAL_VALIDATION` → 对 initial/base 与 current/head 跑相同适用检查。
2. 保存 STRUCTURAL_VALIDATION observation → helper import；PASS 才进入 behavioral。
3. Helper 返回 `RUN_BEHAVIORAL_VALIDATION` → 按显式 flags 执行 eval；false 维度 `SKIP`。
4. 保存 BEHAVIORAL_VALIDATION observation → helper import；FAIL 走 owner mapping/shared budget。
5. 两个 Gate 均 PASS 后，仅 helper `REQUEST_SQUASH_APPROVAL` 可触发用户完成 Gate。

## Report Format

| Dimension | Status | Evidence |
|-----------|--------|----------|
| Spec Conformance | ✓ PASS / ✗ FAIL | [specific finding] |
| Pattern Consistency | ✓ PASS / ✗ FAIL | [specific finding] |
| Flow Completeness | ✓ PASS / ✗ FAIL | [specific finding] |
| Structural Compliance | ✓ PASS / ✗ FAIL | [specific finding] |
| Token Efficiency | ✓ PASS / ✗ FAIL | [specific finding] |
| Behavioral Correctness | ✓ PASS / ✗ FAIL | [specific finding] |
