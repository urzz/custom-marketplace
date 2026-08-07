# Nuclio v3 Knowledge

长期知识只保存跨 change 稳定、可复用、非显然、已验证且有唯一归属的事实；它不是执行日志、State 镜像或每次 change 的必然产物。

## Index-first reading

`.dev-docs/index.md` 是入口，只列出知识路径、简短摘要和何时读取。Shape、Build、恢复、Verify 与 Finish 都先从索引选择有明确相关性的文件或 heading；不递归加载整个 `.dev-docs/knowledge/**`，不默认搜索 archive。代码、测试和 Git 表示当前事实，合同表示本次结果，知识表示不能仅从当前代码可靠推导的稳定约束。

默认 authority 为：

- `knowledge/project.md`：产品目标、术语和跨领域规则；
- `knowledge/architecture.md`：系统边界、稳定关系和重要决策；
- `knowledge/engineering.md`：构建、测试、发布和协作实践；
- `knowledge/<topic>.md`：有稳定主题、唯一 authority 与明确读取时机时才创建。

一个语义结论只保留一个 authority。新建、删除、重命名入口或读取时机实质变化时更新索引；普通正文修改不要求改索引。

## Finish analysis

产品验证通过后，主会话同时检查：

1. 本次结果是否产生合格的新知识候选；
2. 本次 diff、API、数据、架构边界、权限、发布方式或用户决定是否使相关存量知识失效。

相关现有知识可 `MERGE`、`REFINE`、`REPLACE`、`DEPRECATE`，或在强证据和明确用户确认下 `DELETE`。无法确认时标记 `review-needed` 或停止该项写入；不要因 change 更近或测试更多而静默覆盖。已接受 ADR 用新 ADR 或 `SUPERSEDE_ADR` 表达替代关系。

## One decision

先报告产品结果，再完成候选分析。没有候选时记录 `NO_OP`，不增加交互。有候选（新增或存量失效均计入）时展示精简 proposal：结论、唯一目标、操作、冲突状态、影响和证据摘要，并只用一次 `AskUserQuestion`：

> 如何处理以上知识候选并完成本次 change？

选项为“写入并归档（推荐）”与“跳过并归档”。用户也可说明调整；调整后重新展示同一组选择。一次写入或跳过同时授权知识处理、完成 section、`complete` 与 `archive`，不得再次请求归档确认或要求固定口令。

结果为 `NO_OP`、`APPLIED`、`PARTIAL` 或 `REJECTED`。`APPLIED`/`PARTIAL` 仅声明实际改变且精确匹配的 `.dev-docs/knowledge/**` 路径和必要的 `.dev-docs/index.md`；其余结果不带路径。知识正文和 proposal 不写入 State，短摘要写入 `change.md` 的 `Knowledge Updates`。