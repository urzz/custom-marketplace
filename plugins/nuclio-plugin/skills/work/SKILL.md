---
name: work
description: "仅在用户显式要求以 Nuclio v3 创建、恢复或交付一个 change 时使用。"
disable-model-invocation: true
---
# Nuclio Work

`/nuclio:work` 只能由用户显式调用。Claude Code 主会话是唯一控制器：只有主会话处理用户 Gate、调用 Runtime、维护 `delivery.yaml`，并决定是否使用 Claude Code `Agent`。被委派 agent 只完成有界工作、不得调用 Skill 或继续委派，也不接管 Runtime 状态。

## Read first

按当前阶段读取一层 reference：[workflow](../../references/workflow.md)、[change format](../../references/change-format.md)、[knowledge](../../references/knowledge.md)、[context hygiene](../../references/context-hygiene.md)。

所有 Runtime 调用使用 bundled script 与显式项目根目录，绝不依赖当前目录或插件源码路径：

```bash
python3 "${CLAUDE_SKILL_DIR}/../../scripts/change.py" --project-root "${CLAUDE_PROJECT_DIR}" <command> ...
```

插件安装目录和 Marketplace cache 始终只读；运行时写入只落在 `${CLAUDE_PROJECT_DIR}/.dev-docs/**`。

## Lifecycle

### 1. Shape

调查用户请求、仓库事实和通过 `.dev-docs/index.md` 路由的相关长期知识；不默认读取整个知识目录、archive 或旧聊天。定位唯一 active change；不存在时以 `create` 创建三件套草稿。补全 `change.md` 的 Goal、Context、Constraints、Non-goals、Acceptance Criteria，确保每条 Acceptance 可观察。

展示精简结果合同并使用一次 `AskUserQuestion` 获得明确确认。只确认结果、边界和 Acceptance；不得要求用户批准 milestone、路径、实现方式、Agent 选择、commit 或普通修复。合同语义、用户可见行为、兼容性、外部副作用或不可逆结果出现新决定时，回到 Shape、提升 revision 并重新确认。

确认后创建或调整 `delivery.yaml`，保证 milestone 和检查覆盖全部 Acceptance，然后执行：

```bash
python3 "${CLAUDE_SKILL_DIR}/../../scripts/change.py" --project-root "${CLAUDE_PROJECT_DIR}" approve --id <change-id>
```

### 2. Build

主会话自主维护 milestone、状态和短 handoff；合同不变时可重排、拆分或合并 milestone，并可直接实现或按需委派 Claude Code Agent。每次仅从索引读取与当前 milestone 有关的知识，再读取相关代码、测试和配置。agent dispatch 只提供当前 milestone、相关 Acceptance、Constraints/Non-goals、handoff、相关知识路径及读取理由、必要范围和预期检查；不得复制完整知识正文。

普通检查失败、实现缺陷或检查定义调整时，继续 Build 自主修复；不引入旧的修复审批、固定实现流水线、任务级提交或证据协议。只有真实产品语义变化、用户独有环境、无法形成新假设或环境阻塞才中断用户。

### 3. Verify

先执行 `status --json`，读取工作包、当前合同、milestone/handoff，并经索引读取相关知识。Claude Code 在当前 HEAD 直接执行 delivery 中的 exact argv；随后为每项检查调用 `record-check`，再调用 `verify`。Runtime 不执行检查。

```bash
python3 "${CLAUDE_SKILL_DIR}/../../scripts/change.py" --project-root "${CLAUDE_PROJECT_DIR}" status --id <change-id> --json
python3 "${CLAUDE_SKILL_DIR}/../../scripts/change.py" --project-root "${CLAUDE_PROJECT_DIR}" record-check --id <change-id> --check-id <id> --head <head> --exit-code <code> --summary <summary> -- <exact-argv>
python3 "${CLAUDE_SKILL_DIR}/../../scripts/change.py" --project-root "${CLAUDE_PROJECT_DIR}" verify --id <change-id>
```

恢复时按 `status --json` 基于当前 evidence 给出的 `next_action` 继续到合同确认、Build、Verify、Finish 或 archive；`review_blocker` 非空时先在 Build 处理 finding。complete 后若 HEAD、check 或 Acceptance evidence 漂移，按同一 Build/Verify 路径重建依据，不重新确认未变化的合同。Verify FAIL、缺失或过期依据时回到 Build 自主修复；向 Runtime 提交当前 reviewer `FAIL` 同样回到 Build。HEAD、合同或 check 定义变化会使旧依据失效。先进行主会话整体自检；用户或项目要求、较高后果或验证不足时，可选用 fresh `nuclio:readonly-reviewer`。reviewer 只返回 findings，主会话自行决定后续工作和 Runtime 输入。

### 4. Finish

验证通过后，先报告产品结果与最小证据。通过索引只读取受影响的知识，同时检查本次是否产生新候选以及现有知识是否失效。无候选时以 `NO_OP` 连续补全完成 section、`complete` 和 `archive`。有候选时只使用一次 `AskUserQuestion`：“如何处理以上知识候选并完成本次 change？”，选项为“写入并归档（推荐）”和“跳过并归档”。该选择同时授权知识处理、complete 和 archive；不得再次请求归档确认。

按 `change-format.md` 追加非空 `Outcome`、`Validation`、`Knowledge Updates`、`Residual Risks`，再调用 `complete` 与 `archive`。只报告最终 outcome、archive 路径/commit 与剩余风险。