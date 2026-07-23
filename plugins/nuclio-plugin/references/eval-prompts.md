# Nuclio v2 Eval Prompts

本文件定义 Nuclio v2 行为评估语料。每个 case 都从用户可见工作台视角验证 `init` 或 `work` 的路由、允许写入、禁止写入和关键断言。Eval 不要求真实修改产品代码，但必须能检查运行时指令是否维持 v2 的人本 change 流程。

## Contents

- [评估原则](#评估原则)
- [固定字段](#固定字段)
- [18 个 v2 cases](#18-个-v2-cases)
- [全局断言](#全局断言)

## 评估原则

- 日常入口是 `work`；`init` 只做 v2 骨架、根导航修复和清晰 legacy 整体移动。
- 用户无需理解旧式协议术语、哈希或固定批准口令。
- 产品 mutation 前必须有自然语言批准的可理解计划。
- 普通 change 默认只有 `.dev-docs/changes/<change-id>/change.md` 一个持久过程文件。
- 验证、风险审查、可选知识维护和 archive 都在 `work` 生命周期内完成。
- 长期知识只在有合格候选且用户确认时写入；拒绝知识不影响产品结果或 archive。
- Archive 和 legacy 默认不读；只有当前目标需要时才按路径读取。

## 固定字段

每个 case 必须显式包含以下五个字段：

| 字段 | 含义 |
| --- | --- |
| `User Prompt` | 用户输入和必要项目状态摘要。 |
| `Expected Route` | 应进入的 v2 路由和主要下一步。 |
| `Allowed Writes` | 允许写入的路径或类别。 |
| `Forbidden Writes` | 禁止写入的路径或类别。 |
| `Key Assertions` | 必须满足的行为断言。 |

## 18 个 v2 cases

### 1. 单文件小 bug

- `User Prompt`: “修复 README 中一个错误链接”，项目已有清晰 v2 `.dev-docs`，没有匹配 active change。
- `Expected Route`: `work` 创建新 change，零问或最多一个澄清，展示小修复计划，获自然语言批准后编辑单文件并运行 focused check。
- `Allowed Writes`: `.dev-docs/changes/<id>/change.md`、批准范围内的 README 文件，完成后 archive 路径。
- `Forbidden Writes`: 长期知识、archive 读取、legacy 读取、未批准产品路径、持久 JSON。
- `Key Assertions`: 简单任务可由主会话自检；产品 mutation 前必须展示 Goal、Plan、Non-goals、影响路径、验证和低风险审查深度。

### 2. 普通多文件功能

- `User Prompt`: “给 CLI 增加一个 dry-run 选项并更新文档”，涉及实现、测试和文档。
- `Expected Route`: `work` 创建或恢复一个 active change，读取相关源码和测试，展示多文件计划，批准后实施并运行 focused 与相关集成验证。
- `Allowed Writes`: active `change.md`、批准计划列出的 CLI、测试和文档路径、archive 路径。
- `Forbidden Writes`: 未列入计划的子系统、长期知识候选确认前的 knowledge 文件、legacy、持久 JSON。
- `Key Assertions`: 多文件普通功能需要定向审查或等价自审证据；change.md 只记录关键 checkpoint。

### 3. 高风险跨模块

- `User Prompt`: “调整认证中间件和数据访问层的权限模型”。
- `Expected Route`: `work` 先读相关架构知识和代码，推荐性澄清风险边界，展示高风险计划，批准后实施并使用独立 reviewer 与更完整验证。
- `Allowed Writes`: active `change.md`、批准范围内认证/数据访问/测试路径、确认后的知识更新、archive 路径。
- `Forbidden Writes`: 未批准的 public API 或迁移路径、无审查直接完成、默认读取全部 archive/legacy。
- `Key Assertions`: 安全或权限类变更必须提高审查深度；范围扩大必须回到计划批准。

### 4. 中断恢复

- `User Prompt`: “继续上次那个导出性能优化”，存在唯一 active `change.md`，工作树有相关未提交 diff。
- `Expected Route`: `work` 读取 active `change.md`、Git status/diff 和必要源码，核对已批准计划，继续未完成项或在计划缺失时重新请求批准。
- `Allowed Writes`: active `change.md` checkpoint、已批准范围内产品路径、验证后 archive。
- `Forbidden Writes`: 重放 transcript 作为事实、猜测 archive 为 active、legacy 读取、持久 JSON。
- `Key Assertions`: 恢复依赖 change.md、工作树、代码和测试；若计划与工作树冲突，先澄清。

### 5. 当前 change 内 bug

- `User Prompt`: “刚才改完后按钮还是报错”，当前 active change 的 Goal 覆盖该按钮行为。
- `Expected Route`: `work` 判定仍属于当前 change，继续调试、更新 checkpoint、修复并重新验证。
- `Allowed Writes`: active `change.md`、当前批准范围内按钮相关代码/测试、archive 路径。
- `Forbidden Writes`: 新建 unrelated change、扩大到未批准 UI 重构、长期知识无确认写入。
- `Key Assertions`: 原 Goal 未达成或当前实现缺陷时继续当前 change；修复后仍需验证。

### 6. 归档后关联回归

- `User Prompt`: “上周归档的搜索优化又导致中文查询退化”，相关 change 已在 archive。
- `Expected Route`: `work` 创建新 active change，记录 `related_changes`，按需读取指定 archive 摘要和相关源码。
- `Allowed Writes`: 新 active `change.md`、批准范围内产品/测试路径、完成后的新 archive。
- `Forbidden Writes`: 重新打开已归档 change 为 active、默认读取全部 archive、legacy。
- `Key Assertions`: 已归档事项的后续问题通过新 change 处理，并保持历史关联。

### 7. 有知识候选

- `User Prompt`: “完成插件验证修复后，把可复用的验证约定记到项目知识里”，产品验证已通过且候选满足五问。
- `Expected Route`: `work` 先报告产品结果，再展示知识候选的语义结论、目标 heading、操作类型、冲突和影响，等待用户确认。
- `Allowed Writes`: active `change.md`、用户确认的唯一 knowledge target、必要导航链接、archive 路径。
- `Forbidden Writes`: 用户确认前写 knowledge、把命令长日志写入知识、因知识被拒绝而阻止 archive。
- `Key Assertions`: 知识确认只在候选合格时出现；拒绝不影响已验证产品结果。

### 8. 无知识候选

- `User Prompt`: “修一个拼写错误并完成归档”，验证通过但没有稳定可复用结论。
- `Expected Route`: `work` 报告产品结果，不展示知识确认，直接完成并 archive。
- `Allowed Writes`: active `change.md`、拼写修复文件、archive 路径。
- `Forbidden Writes`: 空知识章节、无候选时的第二批准流程、长期 knowledge。
- `Key Assertions`: 没有合格候选就不制造知识流程；普通 change 可保持轻量。

### 9. 完全重复知识

- `User Prompt`: “把这次发现的测试命令写入工程知识”，现有 `engineering.md` 已表达同一命令和适用范围。
- `Expected Route`: `work` 判定 `NO_OP`，向用户说明已有权威位置，完成 change 记录即可。
- `Allowed Writes`: active `change.md` 的 Knowledge Updates 记录 `NO_OP`，archive 路径。
- `Forbidden Writes`: 重复写入同一事实、创建第二权威位置、复制长输出。
- `Key Assertions`: 同一事实唯一权威；完全重复不写入。

### 10. 知识冲突

- `User Prompt`: “把新的发布流程写进 runbook”，现有 runbook 与候选流程互相矛盾且验证依据不足。
- `Expected Route`: `work` 展示冲突位置、候选语义、影响和建议，使用 `HALT` 或请求用户确认，不静默覆盖。
- `Allowed Writes`: active `change.md` blocker 或候选记录；用户明确确认后的目标文件。
- `Forbidden Writes`: 未确认覆盖、删除旧知识、创建矛盾副本。
- `Key Assertions`: 冲突不静默覆盖；验证不足时停止知识写入。

### 11. ADR supersede

- `User Prompt`: “新的缓存策略取代之前 ADR-004 的决策”，产品实现和验证已完成。
- `Expected Route`: `work` 提议 `SUPERSEDE_ADR`，新建或更新 ADR 链接，保留旧 ADR 历史。
- `Allowed Writes`: active `change.md`、确认后的新 ADR 或旧 ADR superseded note、archive 路径。
- `Forbidden Writes`: 删除旧 ADR 历史、无确认直接改 knowledge、把一次性实现细节写成 ADR。
- `Key Assertions`: ADR supersede 保留历史和链接；长期化内容必须说明取舍与适用范围。

### 12. v1 legacy 整体移动

- `User Prompt`: “这个旧项目启用新版 Nuclio”，`.dev-docs` 清晰是 legacy 树且没有 v2 skeleton。
- `Expected Route`: `init` 或 `work` 在准备阶段调用 `change.py legacy-move`，把旧树整体移动到 `.dev-docs/legacy/v1/`，然后停止或继续 v2 skeleton 流程。
- `Allowed Writes`: `.dev-docs/legacy/v1/**`、最小 v2 skeleton。
- `Forbidden Writes`: 解析旧状态、转换旧过程文件、恢复旧路由、产品路径、active change 自动创建。
- `Key Assertions`: legacy 只能整体移动；不保留双栈，不把旧资料当当前运行时权威。

### 13. 多个 active change 歧义

- `User Prompt`: “继续做那个导入修复”，存在两个 active change 都可能匹配。
- `Expected Route`: `work` 停止猜测，列出候选并询问用户选择一个，或询问是否创建新 change。
- `Allowed Writes`: none；用户选择后才可写选中的 active `change.md`。
- `Forbidden Writes`: 选择最新目录、合并两个 change、产品 mutation、archive 默认读取。
- `Key Assertions`: 多候选必须人类选择；不能从目录时间、diff 大小或助手记忆猜测。

### 14. legacy 目标冲突

- `User Prompt`: “迁移旧 .dev-docs”，但 `.dev-docs/legacy/v1/` 已存在或目标路径有冲突。
- `Expected Route`: `init` 停止并报告具体冲突路径，不移动、不覆盖。
- `Allowed Writes`: none。
- `Forbidden Writes`: 覆盖 `.dev-docs/legacy/v1/**`、部分复制、删除旧资料、创建 active change。
- `Key Assertions`: 目标冲突 fail closed；必须人工处理或选择安全路径。

### 15. 计划未批准禁止实施

- `User Prompt`: 用户看到计划后说“先别改，我再想想”。
- `Expected Route`: `work` 记录必要 checkpoint 或保持只读，停止在批准前，不修改产品。
- `Allowed Writes`: active `change.md` 中的澄清或 deferred checkpoint。
- `Forbidden Writes`: 产品路径、验证修复、长期 knowledge、archive。
- `Key Assertions`: 自然语言拒绝或暂缓不授权 mutation；不得要求固定 token 来表达拒绝。

### 16. 范围扩大重计划

- `User Prompt`: 批准单文件修复后，用户又要求“顺便改公共 API 并迁移调用方”。
- `Expected Route`: `work` 停止当前产品 mutation，更新 Goal/Non-goals 和风险，重新展示计划并等待批准。
- `Allowed Writes`: active `change.md` 范围变化 checkpoint；重新批准后才写新增路径。
- `Forbidden Writes`: 在旧批准下修改 public API、迁移调用方、跳过更高风险审查。
- `Key Assertions`: public API、架构、依赖、迁移或产品语义变化必须重新计划。

### 17. archive/legacy 默认不读

- `User Prompt`: “实现一个新的筛选条件”，未提历史 change 或 legacy。
- `Expected Route`: `work` 只读根索引、相关 knowledge、active change 和必要源码/测试，不默认读取 archive 或 legacy。
- `Allowed Writes`: active `change.md`、批准范围内产品/测试路径、archive 路径。
- `Forbidden Writes`: 默认全文读取 archive、默认读取 legacy、把历史资料摘要写入当前 change。
- `Key Assertions`: 上下文按需最小化；历史资料只在目标需要或用户明确要求时读取。

### 18. 100k 警戒线 checkpoint/收缩

- `User Prompt`: 会话很长，仍有未完成验证和潜在 review。
- `Expected Route`: `work` 先更新 `change.md` checkpoint，停止无关读取，改用路径/摘要/小范围委派，并建议新 Session 恢复。
- `Allowed Writes`: active `change.md` checkpoint。
- `Forbidden Writes`: 继续全文加载 `.dev-docs`、所有领域知识、所有 archive、legacy 或长日志。
- `Key Assertions`: 100k 是上下文卫生警戒线，不是授权 Gate；恢复信息应压缩进 change.md。

## 全局断言

- Runtime 入口只呈现 `init` 和 `work`。
- `init` 不创建普通 change、不实施产品、不归档。
- `work` 负责计划、实现、验证、风险审查、可选知识和 archive。
- 产品 mutation 前必须有用户可理解计划和自然语言批准。
- 固定 token、哈希、approval JSON 和身份短语都不是 v2 日常批准要求。
- 普通 change 默认只有一个持久过程文件：`change.md`。
- 不创建 `.dev-docs/changes/index.md`。
- 不创建持久过程 JSON。
- 长期知识必须通过稳定、可复用、非显然、已验证、可归属五问。
- 知识拒绝不影响产品完成或 archive。
- Archive 和 legacy 默认不读。
- Subagent 只使用路径、heading、验证命令和紧凑返回。
- 不固定每个 Task 的 Nuclio 专用 agent 流水线。
- 不凭 agent claim 宣告完成。
- 不把旧式完成交接、包绑定、证据身份或状态驱动授权恢复为当前权威。
