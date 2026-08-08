# Nuclio v3 Change Format

本文件定义 Nuclio v3 active change 的唯一 Runtime 合同。生命周期由 Claude Code 主会话控制；Runtime 只校验和写入可恢复事实。

## Active artifacts

```text
.dev-docs/
├── nuclio.yaml                  # 可选、项目级稳定检查
└── changes/
    ├── <change-id>/
    │   ├── change.md            # 用户确认的结果合同
    │   ├── delivery.yaml        # Agent 维护的交付地图
    │   └── state.yaml           # Runtime 唯一写入的当前事实
    └── archive/
        └── <change-id>/
            ├── change.md
            ├── delivery.yaml
            └── state.yaml
```

`change-id` 仅可使用小写字母、数字和单个连字符分隔的段；不得为 `archive`，不得含路径分隔符、`..`、glob 或控制字符。Runtime 的所有路径均解析在显式 project root 的 `.dev-docs/**` 下。

发现 active 目录中的 v2 `plan.yaml` 或旧 State 时，Runtime 返回 `V2_ACTIVE_UNSUPPORTED` 并停止；不迁移、不读取旧协议。archive 仅按用户明确的 change ID 操作；不扫描、解析、修改或删除旧 archive。

## `change.md`

```markdown
---
schema_version: 1
change_id: auth-redirect
revision: 1
---

# 修复登录回跳

## Goal

登录成功后安全地返回用户最初访问的受保护页面，同时保持无回跳参数时的现有行为。

## Context

登录拦截器会保存包含 query string 的目标页面；当前回调归一化会丢失该参数，导致密码登录和 SSO 登录都回到首页。

## Constraints

- 只允许站内绝对路径作为回跳目标，非法或外站地址回退首页。
- 保持现有会话以及无回跳参数时的登录行为兼容。

## Non-goals

- 不重构认证框架或更换会话机制。
- 不增加跨域登录跳转能力。

## Acceptance Criteria

- AC-1: 密码登录后回到原始受保护页面，并保留 query string。
- AC-2: SSO 登录后回到原始受保护页面，并保留 query string。
- AC-3: 非法或外站回跳地址不会离开本站，而是回到首页。
- AC-4: 无回跳参数时继续使用现有默认落点。

## Decisions

非法或外站回跳地址统一回退首页，不显示额外错误。
```

frontmatter 必须且只能包含 `schema_version`、`change_id`、`revision`；schema 为 `1`，revision 是正整数。H1、Goal、Context、Constraints、Non-goals、Acceptance Criteria 必须唯一且非空。Acceptance 使用唯一的 `AC-*` ID。`Decisions` 可选，但存在时非空。批准后的 Goal、Context、Constraints、Non-goals、Acceptance Criteria 与批准时存在的 Decisions 是冻结合同；语义改变时 revision 必须递增并重新 `approve`。

合同必须在不读取旧聊天、`delivery.yaml` 或 archive 的情况下说明做什么、为什么、边界和可观察完成条件。精简不等于单句：Goal 可以是一句明确结果；Context 保留理解需求所需的当前事实与影响；每项独立 Constraint 和 Non-goal 分开记录，存在多项时使用列表；每条 Acceptance 只表达一个可观察结果，并覆盖与合同有关的关键正常路径和边界，不写实现步骤或臆测信息。

完成前在原合同后按顺序追加以下非空 section，它们不属于批准合同：

- `Outcome`：实际交付结果、覆盖的 Acceptance 和必要的变更范围摘要；
- `Validation`：验证所绑定的 HEAD、执行的准确检查及 exit code/关键结果，并包含实际使用的手工观察或 review；
- `Knowledge Updates`：知识结果及实际更新路径，未更新时明确记录结果；
- `Residual Risks`：已知风险、影响条件和必要处置；没有时明确记录无已知残余风险。

这些完成 section 必须脱离聊天仍可用于追溯，但不复制完整日志、diff、transcript 或 Agent 消息。

## `delivery.yaml`

```yaml
schema_version: 1
change_id: auth-redirect
milestones:
  - id: M1
    kind: delivery
    outcome: 修复回跳并补定向测试
    covers: [AC-1]
    status: in_progress
    handoff:
      summary: 已定位 callback 归一化阶段。
      remaining: 完成实现和检查。
  - id: M2
    kind: integration
    outcome: 验证认证流程没有回归
    covers: [AC-1]
    status: pending
    handoff: null
verification:
  checks:
    - id: auth-tests
      run: [python3, -m, unittest, tests.auth]
      cwd: .
      timeout_seconds: 300
      covers: [AC-1]
```

至少一个 milestone；每条 Acceptance 必须被 milestone 覆盖。多个 milestone 时最后一个必须为 `integration` 并覆盖全部 Acceptance。milestone 的 `status` 为 `pending|in_progress|done`，只表示 Agent 工作进度；handoff 为 `null` 或含非空 `summary`、`remaining` 的当前简短记录。

checks 使用 argv 数组；`cwd` 是位于项目根目录内的 repo-relative 路径，`timeout_seconds` 是正整数。每个 change check 覆盖至少一个 Acceptance。可选 `.dev-docs/nuclio.yaml` 使用 `schema_version: 1` 和 `checks` 列表，项目 check 不声明 `covers`。合并后的 check ID 全局唯一。

## `state.yaml`

State 只由 `change.py` 原子写入。初始 State 保存 `revision: null`、`phase: shape`、`base_head: null`、`approval_head: null`、`verified_head: null`。批准后保存批准 revision、首次批准前的 `base_head`、approval commit SHA，以及当前 verification：每条记录的完整规范化定义、HEAD、exit code 和有界 summary；同时保存每条 Acceptance 的 `missing|passed`、可选手工观察/review 与知识结果。

State 不保存合同正文、content hash、完整命令输出、diff、Agent/transcript、attempt、Task、path ownership 或验证历史。

## Runtime commands and gates

CLI 仅有 `create`、`approve`、`status`、`record-check`、`verify`、`complete`、`archive` 七个命令；成功、参数错误和 schema 错误均以 JSON 表达。`record-check` 只比较调用方给出的 argv、HEAD、exit code 与当前定义并记录结果，绝不执行 argv。

`approve` 要求完整合同、完整 delivery、附着 HEAD、空 index 和干净产品工作区；它只提交三件套，subject 为 `approve(<id>): confirm revision <n>`。提交成功但 State 回写中断时，重跑可恢复该提交。重新批准保留首次 `base_head`，替换 approval HEAD，并清空旧验证。

正常 `verify` 要求批准合同未漂移、delivery 覆盖完整、产品工作区干净，且所有当前定义的项目与 change checks 都在当前 HEAD 通过；stale complete 恢复时仅允许 State 已精确登记的 `APPLIED|PARTIAL` knowledge 路径保持 dirty，其他 dirty 路径仍被拒绝。HEAD、合同或 check 的 `source`、`id`、`run`、`cwd`、`timeout_seconds`、`covers` 任一漂移（包括新增或删除 check ID）都会使旧依据失效；重跑 `verify` 会移除已不在当前定义中的旧记录。当前 HEAD 上显式 reviewer `FAIL` 会阻断 `verify` 和 `complete`；同一 HEAD 的 `PASS` 可解除该阻断。未提供 `--manual` 时保留同一 HEAD 的已有手工依据；提供 `--manual` 时以该次完整批次替换，旧 HEAD 依据自然失效。`complete` 还要求每条 Acceptance 有当前依据、当前 HEAD 等于 `verified_head`、完成 section 已写入，以及明确且精确的知识结果；terminal evidence 仍为当前时 `verify` 不会降级 complete State，stale complete 恢复时可按验证结果转为 `verified|build`。

`status.next_action` 按当前事实恢复，并在工作包中返回 index 与 dirty-product clean gate：`shape` 为 `confirm-contract`；当前 reviewer `FAIL` 优先为 `build`；检查缺失、失败或过期为 `run-required-checks`；verified evidence 因 HEAD 漂移失效为 `build`；其余尚未绑定的证据为 `verify`；当前 `verified` 仅在 index 为空且除 Finish 可确认的 knowledge 候选外无产品 dirty 时为 `finish`。`complete` 仅在 terminal evidence、完成章节与 clean gate 均当前时为 `archive`；clean gate 只允许 State 已登记的 `APPLIED|PARTIAL` knowledge 路径保持 dirty。完成章节缺失为 `finish`，证据或 clean gate 漂移按相同规则回到 Build/检查并允许 `record-check`、`verify` 重建依据，不重新确认未变化的合同。工作包同时返回 `verified_head`、缺失 Acceptance 和当前 reviewer blocker。

知识结果为 `NO_OP|APPLIED|PARTIAL|REJECTED`。`NO_OP|REJECTED` 不带路径；`APPLIED|PARTIAL` 必须给出与当前 dirty knowledge 路径精确一致的 `.dev-docs/knowledge/**` 或 `.dev-docs/index.md` 路径。

`archive` 只处理已完成的显式 change，完整保留三件套，subject 为 `archive(<id>): retain complete change record`。正常归档及移动/提交中断恢复都重新验证批准合同、完整 delivery、当前 check 定义和 terminal evidence；它只暂存 active/archive 三件套和确认的知识路径，不吸收无关修改。成功重跑幂等。terminal evidence 仍为当前的完成态拒绝新的 `record-check`，避免 State 被无条件降级；证据漂移后的完成态可按恢复路由重建依据。Runtime 不 push、merge、stash、reset、clean、切换分支或改写历史。
