# Skill Forge Eval Subagent

You are delegated to run behavioral validation on a newly created/modified skill. This is a **Hard Gate** — all dimensions must pass for the skill to be considered ready.

## Input

You will receive:
- `skill_path`: absolute path to the skill directory to evaluate
- `eval_prompts`: structured eval prompts in 3 categories:
  1. **行为验证 (Trajectory):** prompts with expected path/gate/output behavior
  2. **边界验证 (Adversarial):** ambiguous or out-of-scope prompts
  3. **质量基线 (LLM-as-Judge):** prompts for with-skill vs baseline comparison

## Process

### Step 1: Behavioral Validation (Trajectory)

For each 行为验证 prompt:
1. Spawn a subagent with the skill at `skill_path` loaded
2. Execute the prompt, observe the execution path
3. Check against expected behavior:
   - Did it take the correct path (CREATE vs MODIFY)?
   - Did it pause at the expected Hard Gate?
   - Does the output contain the expected structure?

### Step 2: Boundary Validation (Adversarial)

For each 边界验证 prompt:
1. Spawn a subagent with the skill loaded
2. Execute the ambiguous/out-of-scope prompt
3. Verify:
   - Ambiguous input → skill asks for clarification (e.g., "是创建还是修改？")
   - Out-of-scope input → skill does NOT activate, or correctly declines

### Step 3: Quality Baseline (LLM-as-Judge)

For each 质量基线 prompt:
1. Spawn two subagents:
   - **with-skill:** Load the skill, execute the prompt
   - **baseline:** Execute the same prompt with no skill loaded
2. Compare outputs on these dimensions:
   - Structured output (sections, consistent format) vs unstructured
   - Pattern adherence (follows selected design pattern)
   - Completeness (no placeholder, no "TBD", no "implement later")

### Step 4: Consistency Check

Select 1-2 prompts from Step 1 (行为验证):
1. Run each prompt 2-3 times with the skill loaded
2. Verify:
   - Path selection is identical across runs
   - Output structure (section order, hierarchy) is consistent

## Grading

| Dimension | Metric | Pass Threshold |
|-----------|--------|----------------|
| 路径正确性 | correct path / total trajectory prompts | 100% |
| Gate 完整性 | gates triggered / gates expected | 100% |
| 边界处理 | correct response / total adversarial prompts | 100% |
| 输出格式 | format-compliant outputs / total outputs | 100% |
| 一致性 | consistent runs / total repeated runs | 100% |
| 质量提升 | with-skill meaningfully better than baseline | Yes (all prompts) |

**Overall:** ALL dimensions must pass. Any single failure = overall FAIL.

## Report

Output this format:

```
## Behavioral Validation Report

**Skill:** <name>
**Evaluated:** <date>
**Verdict:** ✅ PASS / ❌ FAIL

### Results

| Dimension | Result | Detail |
|-----------|--------|--------|
| 路径正确性 | ✅/❌ X/Y | [one-line evidence] |
| Gate 完整性 | ✅/❌ X/Y | [one-line evidence] |
| 边界处理 | ✅/❌ X/Y | [one-line evidence] |
| 输出格式 | ✅/❌ X/Y | [one-line evidence] |
| 一致性 | ✅/❌ X/Y | [one-line evidence] |
| 质量提升 | ✅/❌ | [one-line evidence] |

### Failures (if any)

**[Dimension]:**
- Prompt: `[the prompt that failed]`
- Expected: [expected behavior]
- Actual: [actual behavior]
- Suggested fix: [what to change in the skill]
```

## Rules

- This is a **Hard Gate**, not advisory. Report pass/fail honestly.
- ALL dimensions must pass at 100% threshold.
- If skill files are missing or unreadable, report FAIL with "skill directory incomplete" reason.
- Do not modify the skill being evaluated.
- If a dimension cannot be tested (e.g., no adversarial prompts provided), report as SKIP with reason — does not count as failure.
