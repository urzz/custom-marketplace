# OpenClaw skill archetypes

本文给出几种常见的 OpenClaw skill 形态，用来帮助用户快速选择合适的起点。

## 1. 最小 skill

### 适用场景
- 单一任务
- 说明不长
- 无外部依赖
- 先验证价值，不急着做厚重结构

### 目录结构

```text
my-skill/
└── SKILL.md
```

### 推荐理由
这是默认起点。只要 `SKILL.md` 能把目标、触发语境、步骤和输出说清楚，就先不要增加层级。

---

## 2. references 增强型 skill

### 适用场景
- 主流程明确，但细节较多
- 有多个变体或决策分支
- 需要字段说明、验收清单、模板示例

### 目录结构

```text
my-skill/
├── SKILL.md
└── references/
    ├── frontmatter.md
    ├── examples.md
    └── validation.md
```

### 推荐理由
把高频主流程留在 `SKILL.md`，把低频细节放到 `references/`。这能保持主文件清晰，也方便后续维护。

### 判断信号
出现以下情况时，通常应从最小 skill 升级到这种形态：
- `SKILL.md` 越写越像说明书而不是工作流
- 你开始写很多“只有在某些情况下才读”的内容
- 你想给多个模板或多类字段解释

---

## 3. 带脚本的 skill

### 适用场景
- skill 内有可重复执行的确定性步骤
- 需要把辅助逻辑与 skill 一起分发
- 不希望每次调用都重新手写相同脚本

### 目录结构

```text
my-skill/
├── SKILL.md
├── references/
│   └── validation.md
└── scripts/
    ├── validate.py
    └── build_output.py
```

### 推荐理由
`scripts/` 适合承载真正可复用的执行资产，例如校验、骨架生成、固定转换和结构提取。对被创建的 OpenClaw skill 来说，如果脚本属于 skill 本体能力，默认应放在该 skill 自己的 `scripts/` 目录下。

### 注意
- 不要为了“将来可能会用”就预先放很多脚本
- 只有当脚本已经稳定、重复出现、值得复用时再加
- 默认不要把脚本散放到 skill 外部

---

## 4. 环境型 skill

### 适用场景
- 成功执行依赖 CLI、运行时或系统环境
- 需要明确声明 `requires` / `install` / `os` / `primaryEnv`
- 用户很可能因为环境不齐而失败

### 目录结构

```text
my-skill/
├── SKILL.md
└── references/
    ├── environment.md
    └── validation.md
```

### 推荐理由
环境型 skill 的难点通常不在主流程本身，而在“前置条件是否满足”。把环境说明单独拆开，能减少主文件噪音。

### 注意
即使是环境型 skill，也不代表一定要上命令模式。很多时候声明依赖并给出人工验证步骤就够了。

---

## 5. 工具协同型 skill（高级）

### 适用场景
- 技能核心围绕稳定工具展开
- 用户希望通过显式入口触发
- 参数传递模式比较清楚

### 目录结构

```text
my-skill/
├── SKILL.md
└── references/
    ├── command-modes.md
    └── safety-checks.md
```

### 常见 frontmatter 信号
- `user-invocable: true`
- `command-tool`
- `command-dispatch`
- `command-arg-mode`

### 何时不该选它
- 用户主要是想让 skill 帮忙分析或起草
- 还没有稳定的命令边界
- 只是“将来可能会接工具”

默认应把这种形态视为第二阶段，而不是首版起点。

---

## 6. 插件携带型 skill

### 适用场景
- 需要和其他相关 skill 一起分发
- 有共享资源、共享命名空间或统一插件元数据需求
- 组织上希望以插件为单位交付

### 目录结构

```text
my-plugin/
├── .claude-plugin/
│   └── plugin.json
└── skills/
    └── my-skill/
        ├── SKILL.md
        └── references/
            └── validation.md
```

### 推荐理由
这更像“打包方式”的选择，不是 skill 本身复杂度的体现。若用户只是要做一个独立 OpenClaw skill，通常没必要一开始就做成插件携带型。

---

## 7. 选择建议

拿不准时按这个顺序选：

1. **最小 skill**
2. **references 增强型**
3. **带脚本的 skill**
4. **环境型**
5. **工具协同型**
6. **插件携带型**

也就是说：
- 先问“是否需要更多层级”
- 再问“是否需要把可复用脚本放入 `scripts/`”
- 再问“是否需要环境声明”
- 最后才问“是否需要命令驱动或插件分发”

默认原则：**优先从最小、最稳、最容易验证的 archetype 开始。**
