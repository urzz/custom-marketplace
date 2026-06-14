# Nucl.io Plugin

Nucl.io 是一个面向 Claude Code marketplace 的 workflow plugin，用来把项目初始化和变更流程收成一套可发现、可停住的工作流骨架。

当前仓库已具备首版静态闭环：plugin 已注册，workflow skills、只读辅助 agents 与 guard / event hooks 已落位，可用于静态 smoke checklist 验收。

## 首版范围

首版只做两条闭环：Project Init 和 Change Workflow。先把流程入口、gate 停住、artifact 输出，以及受 guard 约束的写入路径打通。

## 首版 skills

下面 7 个 skills 构成当前 Nucl.io 首版静态闭环：

- `/nuclio:project-init`：项目初始化入口
- `/nuclio:spec`：需求收敛与规格整理
- `/nuclio:design`：设计与执行前准备
- `/nuclio:build`：实现推进与结果校验
- `/nuclio:close`：收尾与状态整理
- `/nuclio:resume`：状态读取与下一步建议
- `/nuclio:apply-memory`：已批准 memory / `.dev-docs/` 变更应用

## 首版重点

首版优先保证这些约束成立：

- plugin 可发现
- artifact 可产出
- gate 会停住
- build 有 verify / review
- `.dev-docs/` 写入受 guard 约束

## 目录职责

- `skills/`：放 workflow skills，负责流程编排、输入输出和 gate 约束。
- `agents/`：放辅助代理，负责审查、调试和验证等补充视角。
- `hooks/`：放 enforcement 逻辑，负责 guard、事件记录落盘和输出过滤。
- `scripts/`：放可复用的底层状态与事件读写脚本。

## 验收方式

首版以静态 smoke checklist 为准，目标是在没有应用构建系统的仓库里，确认 Nucl.io 的最小闭环已经成形。

1. 确认 marketplace 能发现 `nuclio`：`.claude-plugin/marketplace.json` 中存在 `name: "nuclio"`，且 `source` 指向 `./plugins/nuclio`，并与 `plugins/nuclio/.claude-plugin/plugin.json` 保持一致。
2. 确认 `project-init` 闭环 artifact 与 gate 齐全：`project-brief.md`、`architecture-baseline.md`、`scaffold-plan.yaml`、`initial-dev-docs.patch.md`、`init-state.json`、`events.jsonl` 都在 skill 输出中声明，同时存在 Foundation Approval、Architecture Approval、Scaffold Approval、Initial Dev Docs Approval，并明确在批准前不得写入 `.dev-docs/`。
3. 确认 `spec → design → build → close` 闭环 artifact 与 gate 齐全：`spec` 停在 Spec Approval，`design` 停在 Design Approval，`build` 以 `plan.yaml` 为唯一执行来源并产出 `evidence/verify.md` 与 `evidence/review.md`，`close` 生成 `close.md` 与 `memory.patch.md` 并停在 Memory Approval。
4. 确认 `build` 明确包含 verify / review / patch：既要记录验证证据，也要从独立只读视角产出 review 证据；若 verify 或 review 失败，必须进入最小 patch loop 或停下来请求人工决策。
5. 确认 `.dev-docs/` 写入与危险 Bash 受 guard 约束：`hooks/guard.mjs` 必须阻断未批准的 `.dev-docs/` 写入，以及 `git push`、`kubectl`、`terraform apply`、`rm -rf` 等危险 Bash；`apply-memory` 只能在明确 approval 后落盘，不能绕过审批边界。
6. 通过一次全量静态检查和一次复跑检查，确认上述约束没有新的明显缺口，再进入后续人工试运行或真实项目接入。
