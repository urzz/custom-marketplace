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

修复登录后的回跳结果。

## Context

当前回调归一化会丢失回跳参数。

## Constraints

保持现有会话兼容。

## Non-goals

不重构认证框架。

## Acceptance Criteria

- AC-1: 登录后回到原始受保护页面。

## Decisions

仅记录用户确认的产品决定。
```

frontmatter 必须且只能包含 `schema_version`、`change_id`、`revision`；schema 为 `1`，revision 是正整数。H1、Goal、Context、Constraints、Non-goals、Acceptance Criteria 必须唯一且非空。Acceptance 使用唯一的 `AC-*` ID。`Decisions` 可选，但存在时非空。批准后的 Goal、Context、Constraints、Non-goals、Acceptance Criteria 与批准时存在的 Decisions 是冻结合同；语义改变时 revision 必须递增并重新 `approve`。

完成前在原合同后按顺序追加以下非空 section：`Outcome`、`Validation`、`Knowledge Updates`、`Residual Risks`。它们不属于批准合同。

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

CLI 仅有 `create`、`approve`、`status`、`record-check`、`verify`、`complete`、`archive` 七个命令，成功和失败均以 JSON 表达。`record-check` 只比较调用方给出的 argv、HEAD、exit code 与当前定义并记录结果，绝不执行 argv。

`approve` 要求完整合同、完整 delivery、附着 HEAD、空 index 和干净产品工作区；它只提交三件套，subject 为 `approve(<id>): confirm revision <n>`。提交成功但 State 回写中断时，重跑可恢复该提交。重新批准保留首次 `base_head`，替换 approval HEAD，并清空旧验证。

`verify` 要求批准合同未漂移、delivery 覆盖完整、产品工作区干净，且所有当前定义的项目与 change checks 都在当前 HEAD 通过。HEAD、合同或 check 的 `source`、`id`、`run`、`cwd`、`timeout_seconds`、`covers` 任一漂移都会使旧依据失效。`complete` 还要求每条 Acceptance 有当前依据、当前 HEAD 等于 `verified_head`、完成 section 已写入，以及明确且精确的知识结果。

知识结果为 `NO_OP|APPLIED|PARTIAL|REJECTED`。前两种无路径；`APPLIED|PARTIAL` 必须给出与当前 dirty knowledge 路径精确一致的 `.dev-docs/knowledge/**` 或 `.dev-docs/index.md` 路径。

`archive` 只处理已完成的显式 change，完整保留三件套，subject 为 `archive(<id>): retain complete change record`。它只暂存 active/archive 三件套和确认的知识路径，不吸收无关修改；移动或提交中断可重跑恢复，成功重跑幂等。Runtime 不 push、merge、stash、reset、clean、切换分支或改写历史。
