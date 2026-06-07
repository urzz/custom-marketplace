# Internal Validation Checklist

Used by Phase 5 to validate skill output before delegating to skill-creator Eval.

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
| Contract coverage | Every input/output/side-effect in Spec Section 2 is implemented | Read SKILL.md, match each contract item |
| Success criteria coverage | Every assertion in Spec Section 5 is achievable by the workflow | Trace each criterion to a specific Step |
| Boundary respect | Nothing in Spec Section 4 "明确不做的事" is present | Search for prohibited behaviors |
| Gate coverage | Every Hard Gate in Spec Section 3 has a corresponding user confirmation point | Count gates in Spec vs implementation |

---

## Dimension 2: Pattern Consistency

Verify the implementation structurally matches the selected Google 8 Pattern.

| Check | Pass Criteria |
|-------|--------------|
| Primary pattern structure | Workflow skeleton matches the pattern's SKILL.md template from references/design-patterns.md |
| Secondary pattern integration | If Spec declares secondary patterns, they appear in the correct phases |
| No pattern drift | No steps that contradict the selected pattern (e.g., parallel spawn in a declared Sequential) |

**How to verify:** Read references/design-patterns.md for the selected pattern's template. Compare structural elements (step ordering, spawn points, loop boundaries, gate locations).

---

## Dimension 3: Flow Completeness

| Check | Pass Criteria |
|-------|--------------|
| Exit conditions | Every Step has an explicit, verifiable exit condition |
| Gate enforcement | Hard Gates use imperative language ("Wait for user confirmation before proceeding") |
| Error/loop handling | Any loop has a maximum iteration count |
| Path coverage | Both CREATE and MODIFY paths are handled (if applicable) |

---

## Dimension 4: Structural Compliance (Anthropic Best Practices)

| Check | Pass Criteria | Command |
|-------|--------------|---------|
| description starts with "Use when" | First two words are "Use when" | Manual check |
| description ≤ 1024 chars | Character count ≤ 1024 | `echo -n "<desc>" \| wc -c` |
| description third person | No "I", "you", "we" in description | Manual check |
| Body < 500 lines | Line count < 500 (excluding frontmatter) | `awk '/^---$/{n++; next} n>=2' SKILL.md \| wc -l` |
| No nested references | Files in references/ do not link to other files in references/ | `grep -rn '\[.*\](.*\.md)' references/` |
| Large file TOC | Files > 100 lines have `## Contents` section | Manual check |
| name format | ≤ 64 chars, letters/numbers/hyphens only | Manual check |

---

## Dimension 5: Token Efficiency

| Check | Pass Criteria |
|-------|--------------|
| No redundant explanations | No explaining concepts Claude already knows |
| No duplicate content | Same instruction not repeated in multiple places |
| Inline code blocks < 50 lines | No single code block exceeds 50 lines |
| Heavy content separated | Content > 100 lines lives in references/, not inline |

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
| 同一 prompt 执行 2-3 次 | 路径选择一致 |
| 输出结构一致 | 产出 section 顺序和层级不变 |

### 失败处理

- 任一子维度失败 → 列出失败项 + 具体 prompt + 实际行为 vs 预期行为
- 回 Phase 4 修复（通过 superpowers:subagent-driven-development 重新执行相关 Task）
- Maximum 2 fix cycles；2 次后仍失败 → 停止，报告用户，等待指令

---

## Validation Flow

1. Run Dimensions 1-5
2. If ALL pass → run Dimension 6 (Behavioral Correctness)
3. If ALL 6 pass → proceed to Layer 2 (skill-creator Eval)
4. If ANY fail → list failures with specific evidence and fix suggestions → return to Phase 4
5. Maximum 2 fix-and-retry cycles before stopping

## Report Format

| Dimension | Status | Evidence |
|-----------|--------|----------|
| Spec Conformance | ✓ PASS / ✗ FAIL | [specific finding] |
| Pattern Consistency | ✓ PASS / ✗ FAIL | [specific finding] |
| Flow Completeness | ✓ PASS / ✗ FAIL | [specific finding] |
| Structural Compliance | ✓ PASS / ✗ FAIL | [specific finding] |
| Token Efficiency | ✓ PASS / ✗ FAIL | [specific finding] |
| Behavioral Correctness | ✓ PASS / ✗ FAIL | [specific finding] |
