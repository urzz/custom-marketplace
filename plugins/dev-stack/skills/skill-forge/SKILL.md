---
name: skill-forge
description: Use when explicitly creating, modifying, optimizing, or auditing Claude Code, Codex, or DeepSeek Harness skills, including SKILL.md, supporting references/scripts/assets, plugin agents, trigger behavior, and skill validation.
disable-model-invocation: true
---

# Skill Forge

为 Claude Code、Codex、DeepSeek Harness 或多宿主共用的目标创建、修改和审查 Skill。先通过需求澄清理解真实问题，再用 Spec、Plan、确定性验证和按需行为评测完成工作；不要把普通 Skill 维护扩张为通用软件交付状态机。

## Contents

- [核心规则](#核心规则)
- [路由](#路由)
- [CREATE 和 MODIFY](#create-和-modify)
- [AUDIT](#audit)
- [验证与完成](#验证与完成)

## 宿主与目标平台

先读取 [平台适配](references/platforms.md)，区分当前执行宿主与目标技能的平台，落实本次技能目录和项目根目录、调用策略、用户确认及代理权限。

## 核心规则

1. 先路由，再执行任何写入或验证。只接受 CREATE、MODIFY、CHANGE_AUDIT 或 FULL_AUDIT。
2. AUDIT 始终只读，不创建 `.skill-forge` 产物；用户要求修复后重新进入 MODIFY。
3. CREATE 和 MODIFY 必须先完成需求澄清，写入 `spec.md` 并获得用户确认，再生成 `plan.yaml` 或修改目标 Skill。
4. 使用 Focused 或 Grill 澄清深度；不要重复询问仓库、review 文档或上下文已经回答的问题。
5. 先运行确定性检查，再做语义审查或行为评测。LLM 判断不能替代失败的 schema、静态检查、脚本或测试。
6. 主 Session 是唯一 Controller。产品写入保持顺序；Subagent 只接收一个 Plan Task 的精确文件边界。
7. 不自动 commit、squash、reset、rebase、checkout、stash，不创建或切换分支、worktree。完成后保留已验证 working tree。
8. 不调用其他 Skill、workflow、MCP、网络服务、hook 或 daemon。仅在本流程明确需要且宿主支持时，按平台适配使用原生 bounded agents。
9. 保留用户已有未提交改动。若目标路径存在非本次修改，先理解并协同编辑；无法安全合并时停止并说明冲突。
10. 用户可见 prose 和生成文档默认使用用户当前主要语言；代码、命令、路径、配置键和协议字段保持原文。

## 路由

| 用户信号 | 路由 |
|---|---|
| 描述一个新 Skill，未引用已有 Skill | CREATE |
| 指向已有 Skill，并要求修改、优化、修复或重构 | MODIFY |
| 要求审查指定 diff、commit 或变更集 | CHANGE_AUDIT |
| 要求完整 Skill/plugin 审计、发布准备或跨文件一致性检查 | FULL_AUDIT |
| 只涉及普通业务代码或通用代码 review | HALT，说明不属于 Skill Forge |
| 无法确定 | 询问用户要创建、修改、审查当前变更，还是完整审计 |

CHANGE_AUDIT 以用户指定范围为入口，并读取直接受影响的稳定合同。FULL_AUDIT 读取完整 Skill、本层 references/scripts/assets、相关插件级 agents、插件 metadata、README、AGENTS 与 CLAUDE 同步点。

## CREATE 和 MODIFY

### 1. Discovery 与需求澄清

1. 读取适用的仓库规则和目标 Skill 结构。
2. CREATE 明确目标平台（Claude Code、Codex、DeepSeek Harness 或多平台）、用户问题、目标用户、最小能力、输入、输出、触发边界、副作用和验证方式。
3. MODIFY 读取目标 `SKILL.md`、直接引用的 supporting files、相关 scripts/tests、插件级 agents、metadata 和同步文档；区分根因与表面症状，明确必须保持的行为。
4. 把 review 或设计文档当作输入，用当前源码和可执行检查验证；不要把旧结论直接当成当前事实。
5. 读取 [需求澄清协议](references/clarification.md)。默认使用 Focused；用户说 `grill me`、要求苏格拉底式追问，或存在会改变架构、权限、副作用或验收的重大不确定性时使用 Grill。
6. 一次只问一个会改变 Spec 的关键问题，并在证据充分时给出推荐答案和理由。
7. 达到澄清停止条件后，在对话中输出简洁 First Principles Synthesis。它不是独立 artifact，也不需要单独确认。

### 2. Spec

在 `.skill-forge/<skill-name>-<change-topic>/spec.md` 写入用户可读合同。首次使用时确保 `.skill-forge/.gitignore` 包含 `*`。使用 [模板](references/templates.md) 中的 Spec 结构，至少包含：

- 目标；
- 第一性原理：根本问题、最小必要能力、不可变约束、关键假设；
- 当前问题与预期行为；
- Should Trigger 与 Should Not Trigger；
- 非目标；
- 验收标准与验证场景；
- 仅在适用时记录权限、副作用、依赖或发布要求。

展示 Spec 路径和简短摘要，请用户确认。确认前不得生成 Plan 或修改目标 Skill。需求变化时先更新 Spec 并重新确认。

### 3. Plan

根据已确认 Spec 在同一 run 目录写入 `plan.yaml`，使用 [模板](references/templates.md) 中的精简 schema：

- `spec` 与 `spec_sha256` 锁定已确认 Spec；
- `impacts` 使用四个布尔标记，不使用 L0-L3、风险关键词或 review policy；
- 每个 Task 只包含 `id`、`name`、精确 `files`、`steps`、`acceptance` 和 `checks`；
- 不写 model、file type、通用 rubric、Task report、commit 或 Gate 合同。

使用 bundled validator 计算 Spec hash 并校验 Plan：

```bash
python3 "${SKILL_FORGE_DIR}/scripts/plan_contract.py" hash-spec "${SKILL_FORGE_REPO_ROOT}/.skill-forge/<run>/spec.md"
python3 "${SKILL_FORGE_DIR}/scripts/plan_contract.py" validate "${SKILL_FORGE_REPO_ROOT}/.skill-forge/<run>/plan.yaml" --repo-root "${SKILL_FORGE_REPO_ROOT}"
```

校验失败时修正 Plan，不能绕过。展示 Plan 路径、Task 数、create/modify/delete 摘要、影响标记和 checks。

若 Plan 完全落在已确认 Spec 内且没有新增删除、依赖、权限、外部副作用或用户选择，直接继续实施。否则先请求一次 Plan 确认；用户修改后重新生成并校验。

### 4. 顺序实施

1. 记录实现前 Git 状态和 diff base，但不要求干净工作区。
2. 按 Plan 顺序执行 Task；同一时间只允许一个产品写入单元。
3. 小型单 Task 由主 Session 直接实施。多 Task、上下文较重或文件边界清晰时，按平台适配使用 bounded implementer；Claude Code 为 `dev-stack:skill-file-implementer`，Codex 使用可用原生子代理。代理不可用时主 Session 依相同 Task 顺序实施。
4. Subagent 只读取已确认 Spec、Plan 中自己的 Task 和必要接口文件；只能修改 Task 路径，直接返回不超过 15 行的结果，不写 brief/report/observation，不 commit，也不修改 Spec、Plan 或 State。
5. 每个 Task 后运行其全部 `checks`。失败时只在原 Task 范围内修复并重跑。
6. 需要新路径、依赖、权限、副作用，改变触发边界或原验收不可观察时停止实施，更新 Spec 并重新确认。
7. 只有跨会话且多 Task 的工作确实需要恢复时，才可创建 [模板](references/templates.md) 中的轻量 `state.json`；不得记录 diff、finding、日志、agent 对话或 transition history。

## AUDIT

1. 明确 CHANGE_AUDIT 或 FULL_AUDIT 的范围和基线。
2. 保持只读；允许运行不写产品文件的确定性检查。
3. 先报告可复现 bug、行为风险、触发误差、结构问题和缺失测试，按严重度排序并引用文件与行号。
4. 区分本次变更新增问题与既有问题。没有发现时明确说明，并列出未执行检查或剩余风险。
5. 不创建 Spec、Plan、State、review package 或 eval 输出。用户要求修复时，从 findings 重新进入 MODIFY。

## 验证与完成

读取 [验证清单](references/validation-checklist.md)，按以下顺序完成：

1. 汇总并运行所有 Task `checks`，再运行适用的 Skill、script 和 plugin 确定性检查。
2. `impacts.script_changed=true` 时运行相关单元测试、`--help` 和至少一个真实 CLI 示例。
3. `impacts.trigger_or_behavior_changed=true` 时，从 Spec 选择 3-5 个 fresh-session cases；description 变化同时覆盖 Should Trigger 和 Should Not Trigger。
4. 没有隔离 harness 时报告 `SKIP: no isolated harness`，可以补充静态合同检查，但不能声称行为 PASS。
5. 只有用户明确要求 benchmark 或专门调优 description 时，才运行 with-skill/without-skill 或版本 A/B。可复用用例写入目标 Skill 的 `evals/evals.json`，临时输出不长期保留。
6. 对实现前 base 到当前 working tree 做一次最终完整 diff review，检查 Spec/Plan 覆盖、越界修改、触发边界、跨文件一致性和已确认目标平台的结构。
7. agent 权限、外部副作用、带副作用 script 或高影响核心控制流程变化时，按平台适配选择 reviewer 做独立只读审查；Claude Code 为 `dev-stack:skill-file-reviewer`，Codex 传入相同角色合同。若 Codex 无法满足有效只读限制，记录 CANNOT_VERIFY 和未完成验证，不声称整体 PASS；普通 Markdown 变化由主 Session 完成最终审查。
8. 发现问题时在原 Plan 范围内修复并重跑受影响检查；范围变化则回到 Spec。同一失败重复且无进展时停止并报告。
9. 报告修改内容、确定性检查、行为评测、独立审查和剩余风险。不要自动提交或改写 Git 历史。

默认长期保留的 Skill Forge run 产物只有 `spec.md` 和 `plan.yaml`；跨会话恢复时可额外保留轻量 `state.json`。
