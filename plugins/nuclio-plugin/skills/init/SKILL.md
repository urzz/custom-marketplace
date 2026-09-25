---
name: init
description: "仅在用户显式要求为项目首次建立或安全修复 Nuclio v3 .dev-docs 知识骨架时使用。"
disable-model-invocation: true
---
# Nuclio Init

`/nuclio:init`（DSH 为 `/nuclio-init`，Codex 为 `$nuclio:init`）只能由用户显式调用。它只直接创建或安全修复 Nuclio v3 项目知识骨架，成功后立即停止；不调用 Runtime，也不处理任何 change 生命周期。

## Plan Mode 边界

从显式调用开始直到停止，始终在当前模式执行，不得调用 Claude Code 的 `EnterPlanMode` 或 `ExitPlanMode`。若调用开始时已处于 Claude Code Plan Mode 或 Codex Plan mode，立即 fail closed：不创建或恢复 change，也不写入知识骨架、不自行调用 `ExitPlanMode`；报告阻塞，并要求用户先退出 Plan Mode 后重新显式调用当前宿主入口（Claude `/nuclio:init`、Codex `$nuclio:init`、DSH `/nuclio-init`）。

## 宿主与路径

通过上述模式边界后，先读取 [宿主适配](../../references/host-runtime.md)，固定本次 `NUCLIO_SKILL_DIR` 与 `NUCLIO_PROJECT_DIR` 的绝对路径并选择当前宿主的确认/委派方式；DSH 通过 bundle provider 的 `resourceBase.path` 定位 `NUCLIO_SKILL_DIR`，不会把 bundle 安装目录当作项目根目录；后续命令中的变量是路径记号，必须在每次调用中落实。

## Read first

按需读取一层 reference：[workflow](../../references/workflow.md)、[change format](../../references/change-format.md)、[context hygiene](../../references/context-hygiene.md)。

## Scope

在 `${NUCLIO_PROJECT_DIR}` 中检查 `.dev-docs` 后，只可：

- 创建缺失的 `.dev-docs/index.md`、`.dev-docs/knowledge/project.md`、`.dev-docs/knowledge/architecture.md`、`.dev-docs/knowledge/engineering.md` 与 `.dev-docs/changes/archive/`；
- 为缺失的入口写入简短导航或空知识标题；索引只列出路径、摘要和何时读取，知识正文留在对应文件；
- 安全修复缺失的目录或明显损坏且没有用户正文的根索引。

已有知识正文、active change、archive、非空未知文件、符号链接或混合的旧流程痕迹必须保留。无法确认安全性时停止并报告精确路径。发现 v2 active change（特别是 `plan.yaml`）时停止；v3 不迁移或解析它。

## Boundaries

- 不创建 `changes/<id>/` 下的 `change.md`、`delivery.yaml` 或 `state.yaml`。
- 不调用 `change.py`；七命令 Runtime 不增加初始化命令。
- 不确认合同，不实现产品，不运行产品检查，不恢复、Verify、Finish、complete 或 archive。
- 不依赖插件源码仓库路径，也不向 `${NUCLIO_SKILL_DIR}` 或 Marketplace cache 写入；所有允许写入只在 `${NUCLIO_PROJECT_DIR}/.dev-docs/`。

用户请求功能、缺陷、文档变更、恢复、验证或归档时，停止并请其显式使用当前宿主的 work 入口（Claude `/nuclio:work`、Codex `$nuclio:work`、DSH `/nuclio-work`）。成功后只报告创建或修复的路径，并说明日常 change 使用该入口。
