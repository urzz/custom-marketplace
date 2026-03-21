# OpenClaw skill 验证清单

本文用于在交付 OpenClaw skill 草案前，做一次最小但有效的手工验收。

## 一、结构检查

### 1. 最小规范是否满足
至少确认：
- 存在 `SKILL.md`
- frontmatter 中有 `name`
- frontmatter 中有 `description`

如果这 3 项都不满足，就还不算一个合格的最小 skill。

### 2. 目录层级是否必要
检查当前结构是否过度设计：
- 只有一个简单流程，却拆了很多 reference 文件
- reference 文件内容很短，且只在一个地方被顺手引用
- 还没确定需求，就先加了复杂目录

若出现这些情况，应回退到更小结构。

### 3. 脚本是否放在 skill 自己的 `scripts/` 下
如果目标 OpenClaw skill 需要 Python、Shell 或其他辅助脚本，默认应检查：
- 脚本是否位于 `<skill>/scripts/`
- 脚本是否属于该 skill 本体能力，而不是散放在 skill 外部
- 只有在多个 skill 明确共享同一套脚本时，才考虑更高层级的共享目录

如果脚本只是偶发实验产物、一次性草稿，或还没有稳定复用价值，先不要纳入正式 skill 结构。

---

## 二、字段检查

### 4. 每个字段是否都有明确理由
逐项追问：
- 为什么需要 `user-invocable`？
- 为什么需要 `disable-model-invocation`？
- 为什么需要 `requires`？
- 为什么需要 `install`？
- 为什么需要 `command-tool` 或 `command-dispatch`？

如果某个字段回答不出理由，应优先删除。

### 5. 是否过早引入命令模式
如果当前 skill 主要还是：
- 分析需求
- 给出方案
- 起草文档
- 组织步骤

那通常还不该引入：
- `command-tool`
- `command-dispatch`
- `command-arg-mode`

---

## 三、正文检查

### 6. `description` 是否同时描述了“做什么”和“什么时候用”
坏例子：
- `帮助用户写 SQL`

更好的写法：
- `帮助用户起草和检查 SQL 迁移脚本。当用户需要修改表结构、补数据迁移步骤或评审迁移风险时使用。`

### 7. 主 `SKILL.md` 是否保留了主流程
确认主文件没有被细节淹没。主文件最好只承担：
- skill 的目标
- 决策顺序
- 输出要求
- 需要时如何读取 `references/`

### 8. 是否混入了不属于 OpenClaw 的宿主特性
检查有没有把其他系统专属内容直接塞进目标 skill，例如：
- 只适用于 Claude 的命令或工作流
- 与 OpenClaw 无关的触发优化术语
- 当前宿主环境独有的工具调用说明

如果有，应改成 OpenClaw 语义，或移出目标产物。

---

## 四、测试 prompt 检查

### 9. 是否至少有 2-5 个真实 prompt
测试 prompt 不要只写：
- `帮我做一个 skill`
- `生成配置`

应尽量接近真实用户说法，例如：
- `我想做一个 OpenClaw skill，用来把 git diff 整理成中文发布说明，默认输出给产品经理看得懂的版本。先帮我判断需要不要 references。`
- `我要做一个只在 Linux 和 macOS 下工作的 OpenClaw skill，负责检查本地数据库迁移状态。请帮我设计 frontmatter，看看需不需要 requires 和 install。`

### 10. 测试样例是否覆盖复杂度边界
至少覆盖：
- 最小场景
- 一个带依赖或环境约束的场景
- 一个“可能诱导你过度设计”的场景

---

## 五、最终 smoke test

如果用户有 OpenClaw 运行环境，可建议执行：

1. 把 skill 放入实际技能目录
2. 让系统成功装载
3. 用 2-5 个真实 prompt 做显式调用或常规调用测试
4. 观察结果是否存在以下问题：
   - 不先澄清需求就直接输出模板
   - 无差别推荐所有高级字段
   - 总是建议上 `command-tool` / `command-dispatch`
   - 没有交付可复制的 frontmatter 和 `SKILL.md` 草案
   - 测试 prompt 太抽象，无法真正验证 skill

---

## 六、常见返工原因

- 结构先行过度，导致维护成本高
- 字段堆砌，实际没人知道为什么加
- 主文件太长，没有 progressive disclosure
- 输出看起来完整，但用户无法直接复制使用
- 测试样例不真实，导致误判 skill 已经可用

---

## 七、通过标准

一个首版 OpenClaw creator 输出，至少应做到：
- 结构推荐清楚
- frontmatter 有理由
- `SKILL.md` 草案可继续修改
- 测试 prompt 真实可执行
- 手工验证步骤足够让用户自行继续迭代
