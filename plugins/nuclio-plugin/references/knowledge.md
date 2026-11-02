# Nuclio v3 知识闭环

长期知识只保存跨 change 稳定、可复用、非显然、已验证且有唯一归属的事实，不是日志、State 镜像或每次 change 的必然产物。

## 主题路由与 Knowledge Context

`.dev-docs/index.md` 是入口；条目至少说明主题、何时读、authority 路径/heading、适用边界。易漂移事实可附验证来源与最近核对标记。可直接链接已有文件的 heading，不要求批量迁移或拆分所有项目知识。Shape、Build、恢复、Verify、Finish 按当前问题路由，不按文件名推定整个文件已读，不把截断内容当完整覆盖，不递归加载全部知识或默认搜索 archive。

默认 authority：`knowledge/project.md` 保存产品目标、术语和跨领域规则；`knowledge/architecture.md` 保存系统边界、稳定关系和重要决策；`knowledge/engineering.md` 保存构建、测试、发布与协作实践。有稳定主题、唯一 authority 和读取触发时才新增 `knowledge/<topic>.md`。一个结论只有一个 authority；入口、主题边界、读取时机变化时同步索引。

每个 change 的必需 `Knowledge Context` 简短记录：

- 相关主题、已读 authority/heading 及读取理由/适用边界；
- 受影响但尚未核对的主题及待核对原因；
- 冲突、过期、缺失项与处理决定/证据定位。

该 section 可随调查与实施更新，不属于冻结合同，不复制全部知识正文。读取范围/核对记录更新无需重批；但新发现的知识冲突若推翻已批准方案假设，必须同步修改 Design/Scope/Constraints、提升 revision 并重批，不能借可变 Knowledge Context 绕开 Gate。记录只能证明覆盖声明，不证明理解正确。关键约束尚未核对时明确风险，不把“索引可找到”当“已读”。恢复时从这里和当前 index 补齐相关主题。

代码/配置表示当前行为，不自动废止历史产品约束；区分实现偏差、文档过期和需用户裁决的约束变化。不要简单以“代码总是赢”掩盖 bug；若关键设计或影响范围要变，回 Shape 重批。

## Finish 分析与一次决定

以最终 diff、批准决定和 Knowledge Context 共同核对新候选及存量失效。候选可 `MERGE`、`REFINE`、`REPLACE`、`DEPRECATE`；强证据且明确确认后才 `DELETE`。无法确认则标记 `review-needed` 或停止该项写入；已接受 ADR 用新 ADR 或 `SUPERSEDE_ADR` 表达替代关系。

先报告产品结果。没有新增或失效候选才记录 `NO_OP`，不增加交互；说明核对过的相关主题/authority、为何现有知识仍适用且无需新增。已发现失效却跳过不得记作 NO_OP。

有候选时展示结论、唯一目标、操作、冲突、影响、证据及拟应用内容摘要，一次询问：

> 如何处理以上知识候选并完成本次 change？

选项为“写入并归档（推荐）”和“跳过并归档”。决定同时授权知识处理、完成 section、complete、archive，不再问归档。用户调整候选时重新展示调整后内容，不沿用对旧内容的批准。知识整理不无限阻塞产品交付，但用户跳过的失效必须在 `Knowledge Context`、`Knowledge Updates`、`Residual Risks` 留下受影响主题、失效结论、风险和定位；可在本次知识选择中明确授权最小 index/主题入口的 `review-needed` 提示，让未来按主题读取可发现。若用户连提示写入也拒绝，则不暗写 index，明确报告“风险仅保留在本次记录，主题入口仍不可发现”的限制，不能宣称知识闭环完成。

结果 `NO_OP|APPLIED|PARTIAL|REJECTED`：全部写入为 APPLIED，部分落实/保留失效风险为 PARTIAL，完全跳过为 REJECTED。APPLIED/PARTIAL 只列实际改变且精确匹配的 `.dev-docs/knowledge/**` 与必要 `.dev-docs/index.md` 路径；NO_OP/REJECTED 不带路径。若只写风险提示而跳过正文修复，使用 PARTIAL。应用后检查索引链接、唯一 authority 和已列候选是否全部落地。

## Runtime 绑定与限制

`complete --knowledge-assessment '<已核对主题、结论、理由及剩余风险>'` 必须非空；NO_OP 也一样。State 保存 `knowledge.assessment` 和 `knowledge.digests`（路径到 SHA256，删除为 null），不保存知识正文。assessment 是主会话声明，Runtime 不判断语义充分性，也不凭字符串证明用户批准了候选。

complete 到 archive 及未提交归档恢复须维持登记路径与实际 dirty 集合、内容摘要一致；同路径正文漂移不能复用旧结果。恢复已确认内容或重新处理知识决定与完成记录，不改 State 绕过保护。摘要是 complete 时实际工作区 raw SHA256，只在移动前及未提交归档恢复复核；已提交恢复不拿 Git blob 与 raw 摘要比较（autocrlf/clean filter 可转换字节），而依赖既有三件套匹配归档 commit、transition 路径与证据链。后续正常知识更新不使旧归档失效。中文路径受支持；`.dev-docs` 内父目录与知识文件不得通过符号链接重定向。
