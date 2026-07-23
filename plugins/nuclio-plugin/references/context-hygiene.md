# Nuclio v2 Context Hygiene

Nuclio v2 用路径、heading 和紧凑摘要保持上下文可控。默认只读完成当前 change 所需的材料，不把 `.dev-docs` 当成必须全文加载的数据库。

## Contents

- [读取顺序](#读取顺序)
- [默认禁止全文读取](#默认禁止全文读取)
- [按需读取](#按需读取)
- [Subagent 上下文](#subagent-上下文)
- [体验预算](#体验预算)
- [100k 警戒线](#100k-警戒线)
- [恢复策略](#恢复策略)
- [非 Gate 声明](#非-gate-声明)

## 读取顺序

推荐读取顺序：

1. `.dev-docs/index.md` 根索引。
2. 匹配领域的知识文件或 heading。
3. 相关全局知识章节：`project.md`、`architecture.md`、`engineering.md`。
4. 必要 ADR。
5. 当前 active `change.md`。
6. 相关源码、配置、测试和 CI 文件。
7. 仅在历史必要时读取 archive。
8. 仅在用户明确要求时读取 legacy。

顺序不是强制命令脚本；它用于避免先吞入大量历史资料。

## 默认禁止全文读取

默认不要全文读取：

- 整个 `.dev-docs`。
- 所有 `knowledge/domains/**`。
- 所有 ADR。
- 所有 runbook。
- `.dev-docs/changes/archive/**`。
- `.dev-docs/legacy/**`。
- 全仓库源码。
- 所有测试输出或 CI 日志。

需要历史时，先定位具体路径或 heading，再读取必要片段。

## 按需读取

读取前先说明要回答的问题：目标、约束、接口、验证方法、风险或知识归属。读完后把结果压缩为可用于计划或实施的结论。

若文件很大，优先读取目录、frontmatter、Contents、相关 heading、符号定义或测试名。避免复制整份长文档到对话中。

## Subagent 上下文

委派 subagent 时提供：

- 目标和非目标。
- 允许读取/修改路径。
- 必要 knowledge 路径或 heading。
- 相关源码/测试路径。
- 验证命令。
- 紧凑返回格式：结论、路径、证据、风险、下一步。

不要传大型 packet、完整知识全文、完整 transcript、全量 archive 或 legacy。subagent 返回也应是摘要和证据，而不是长日志。

## 体验预算

软预算：

- 开始定位与恢复：约 2k tokens。
- 计划前上下文：约 8k tokens。
- 单次 subagent prompt：约 4k tokens。
- 单次 subagent 返回：约 2k tokens。
- 完成前主会话目标：低于 50k tokens。

这些是体验预算，不是 schema、hash 或批准 Gate。

## 100k 警戒线

当会话达到约 100k tokens，必须先收缩：

1. 更新当前 `change.md` checkpoint，记录 Goal、批准计划、已完成项、未完成项、验证结果、阻塞和下一步。
2. 停止无关读取。
3. 改用路径、heading 和摘要。
4. 必要时委派小范围 subagent。
5. 建议用户在新 Session 用 `work` 恢复。

不要继续全文读取 archive、legacy、所有领域知识或所有源码来“保险”。

## 恢复策略

恢复依赖 active `change.md`、Git status/diff、代码、配置、测试和用户当前请求。不要重放 transcript。若 `change.md` 与工作树冲突，先报告冲突并询问或检查事实；不要猜测最新聊天就是权威。

Archive 默认不参与恢复。只有用户提到历史 change、回归、类似问题或 `related_changes` 时才读取相关 archive。Legacy 仅在用户明确要求历史材料或 init 需要整体移动时读取。

## 非 Gate 声明

上下文预算不是身份、hash、状态版本或授权机制。计划批准是用户可理解的自然语言确认；知识确认只在候选存在时出现。不要把上下文指纹、包绑定、证据身份或旧式状态路由作为当前 v2 运行时权威。
