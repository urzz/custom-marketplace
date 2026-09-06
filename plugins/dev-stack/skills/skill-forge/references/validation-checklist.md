# Skill Forge 验证清单

按变更实际影响选择检查，但必须保持“确定性检查优先”。任何未运行项都以 SKIP 和原因报告，不得伪装为 PASS。

## Contents

- [顺序](#顺序)
- [结构与触发](#结构与触发)
- [Scripts](#scripts)
- [Agents 与权限](#agents-与权限)
- [发布同步](#发布同步)
- [行为评测](#行为评测)
- [最终 Diff](#最终-diff)

## 顺序

1. 校验 Spec hash 与 Plan schema。
2. 运行每个 Task 的 `checks`。
3. 运行目标 Skill、script 和 plugin 的适用确定性检查。
4. 运行条件行为评测。
5. 完成一次最终完整 diff review。
6. 只在高影响条件命中时增加独立 reviewer。

## 结构与触发

- `name` 与目录命名符合已确认目标平台的 Skill 规则。
- `description` 说明 Skill 做什么以及适用场景。
- 按 `platforms.md` 保持目标技能既有调用策略；仅显式调用目标分别检查 Claude frontmatter 与 Codex `agents/openai.yaml`，不把 Skill Forge 自身的显式策略强加给生成内容。
- 详细步骤与安全边界位于正文，不把核心程序藏在 metadata。
- `SKILL.md` 保持精简；大段 schema、示例和澄清细节放入一层 `references/`。
- 每个 supporting file 都从 `SKILL.md` 直接可发现，并说明何时读取或执行。
- 不存在无引用资源、placeholder、过期路径或同一合同的冲突副本。
- 用户可见 prose 默认跟随用户当前主要语言。

## Scripts

当 `script_changed=true`：

- 使用结构化 parser/API 处理 YAML、JSON 等结构数据。
- 拒绝不安全路径、重复 key、无效类型和超出限制的输入。
- 缺少依赖时给出稳定、可操作的错误。
- 实际运行单元测试、`--help` 和至少一个成功或失败 CLI 示例。
- Skill 内调用从实际加载目录定位 bundled script，显式传入目标项目路径，不依赖后来变化的 shell CWD 或跨调用环境变量。
- 脚本不静默 commit、改写 Git 历史、访问网络或执行外部副作用。

## Agents 与权限

当 `agent_permissions_changed=true`：

- Claude plugin agent 位于插件根级 `agents/`；Codex 按宿主可用能力派发，不把技能 `agents/openai.yaml` 当作子代理定义。
- implementer 只有 Task 所需写工具；reviewer 需满足平台适配规定的有效只读限制，不以角色名称或自然语言声明替代权限边界。
- agent 不嵌套 delegation、不调用其他 Skill、不创建 worktree、不 commit。
- dispatch 明确 repo root、Spec、Plan Task、允许路径、checks 和返回格式。
- Subagent 返回简短结果，不创建 report、observation 或 diff package。
- 运行一次独立只读审查，确认 tools 边界与正文一致。

## 发布同步

- Claude Code 目标运行 `claude plugin validate <plugin> --strict`；Codex 目标进行清单与技能元数据检查和实际客户端加载；双平台分别执行。
- 校验两端 plugin metadata、marketplace JSON 以及名称、source、版本和调用策略的一致性。
- plugin description、marketplace description、README、AGENTS 和 CLAUDE 与实际行为一致。
- 不保留 L0-L3、review-state、Gate、ledger、fix budget、checkpoint commit 或 squash 的旧描述。
- 只宣称已验证的宿主和能力；本地插件加载、公共目录 ingestion、模型行为与独立审查分别报告。

## 行为评测

当 `trigger_or_behavior_changed=true`：

1. 从 Spec 选择 3-5 个代表性请求。
2. description 变化至少包含 Should Trigger 和 Should Not Trigger。
3. Routing/确认点变化验证进入正确路径并在正确位置停止。
4. 模糊请求验证进入 Focused/Grill 澄清，而不是提前实施。
5. 每个 case 在 fresh session 中运行，记录是否触发及触发后的关键行为。
6. 只在用户要求 benchmark 或触发调优时运行 baseline/A-B。
7. 可复用 case 写入目标 Skill 的 `evals/evals.json`；临时日志和结果不进入长期产物。

若当前环境没有 fresh-session harness，报告 `SKIP: no isolated harness`，再做静态合同检查作为补充，但不要称其为行为 PASS。

## 最终 Diff

使用实现前 base 与当前 working tree 形成一次完整审查范围，检查：

- Spec 的目标、非目标和每条验收是否被覆盖；
- Plan 声明路径与实际 diff 是否一致；
- 未覆盖的用户已有改动是否被误改；
- supporting files、脚本调用、agent tools、字段名和发布说明是否同步；
- trigger、权限和外部副作用是否存在回归；
- 测试是否足以覆盖真实行为变化。

发现问题后只在原 Plan 范围修复并重跑受影响检查。新增路径、依赖、权限、副作用或合同变化必须回到 Spec。
