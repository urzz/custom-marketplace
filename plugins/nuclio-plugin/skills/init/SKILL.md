---
name: init
description: "仅在用户显式要求为项目首次建立或安全修复 Nuclio v3 .dev-docs 知识骨架时使用。"
disable-model-invocation: true
---
# Nuclio Init

`/nuclio:init` 只能由用户显式调用。它只直接创建或安全修复 Nuclio v3 项目知识骨架，成功后立即停止；不调用 Runtime，也不处理任何 change 生命周期。

## Read first

按需读取一层 reference：[workflow](../../references/workflow.md)、[change format](../../references/change-format.md)、[context hygiene](../../references/context-hygiene.md)。

## Scope

在 `${CLAUDE_PROJECT_DIR}` 中检查 `.dev-docs` 后，只可：

- 创建缺失的 `.dev-docs/index.md`、`.dev-docs/knowledge/project.md`、`.dev-docs/knowledge/architecture.md`、`.dev-docs/knowledge/engineering.md` 与 `.dev-docs/changes/archive/`；
- 为缺失的入口写入简短导航或空知识标题；索引只列出路径、摘要和何时读取，知识正文留在对应文件；
- 安全修复缺失的目录或明显损坏且没有用户正文的根索引。

已有知识正文、active change、archive、非空未知文件、符号链接或混合的旧流程痕迹必须保留。无法确认安全性时停止并报告精确路径。发现 v2 active change（特别是 `plan.yaml`）时停止；v3 不迁移或解析它。

## Boundaries

- 不创建 `changes/<id>/` 下的 `change.md`、`delivery.yaml` 或 `state.yaml`。
- 不调用 `change.py`；七命令 Runtime 不增加初始化命令。
- 不确认合同，不实现产品，不运行产品检查，不恢复、Verify、Finish、complete 或 archive。
- 不依赖插件源码仓库路径，也不向 `${CLAUDE_SKILL_DIR}` 或 Marketplace cache 写入；所有允许写入只在 `${CLAUDE_PROJECT_DIR}/.dev-docs/`。

用户请求功能、缺陷、文档变更、恢复、验证或归档时，停止并请其显式使用 `/nuclio:work`。成功后只报告创建或修复的路径，并说明日常 change 使用 `/nuclio:work`。