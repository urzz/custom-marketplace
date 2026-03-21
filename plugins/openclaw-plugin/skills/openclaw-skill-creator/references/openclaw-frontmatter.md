# OpenClaw frontmatter 设计参考

本文用于帮助判断 **OpenClaw skill 应该声明哪些 frontmatter 字段**，以及什么时候不该加字段。

## 1. 最小可行 frontmatter

最小版本只需要：

```yaml
---
name: changelog-writer
description: 帮用户根据代码变更和上下文起草发布说明。当用户想整理版本更新、归纳改动影响或撰写 release notes 时使用。
---
```

适用场景：
- 单一任务
- 不依赖外部运行环境
- 不需要显式命令入口
- 先验证技能价值，再决定是否扩展

这是默认推荐起点。

---

## 2. 字段决策表

### `name`
**何时使用：** 始终需要。

建议：
- 使用稳定、简短、可读的 kebab-case 名称
- 名称描述能力，不描述实现细节

好例子：
- `release-note-writer`
- `sql-migration-reviewer`
- `incident-timeline-builder`

避免：
- `my-skill`
- `best-openclaw-helper`
- `tool-v2-final`

### `description`
**何时使用：** 始终需要。

建议：
- 同时说明“做什么”和“什么时候用”
- 写用户意图，不只写内部实现
- 尽量覆盖典型触发语境

建议模板：

```text
帮助用户<完成什么任务>。当用户需要<典型场景1>、<典型场景2>、<典型场景3>时使用。
```

---

### `user-invocable`
**何时考虑：** 希望用户显式调用该 skill，而不是只依赖自动触发。

适合：
- 用户会把它当“命令型工具”来用
- 任务意图明确、边界清楚
- 希望降低误触发

不适合：
- 还在探索触发方式
- 普通自然语言即可很好触发
- 该 skill 更像一个通用工作流助手

---

### `disable-model-invocation`
**何时考虑：** 不希望模型自动调用，或你明确想把它限制为显式入口。

适合：
- 高成本操作
- 容易误触发
- 更适合由用户显式决定是否使用

不适合：
- 本来就希望在相关需求出现时自动参与
- skill 的价值主要来自被自然触发

---

### `command-tool`
**何时考虑：** skill 的核心是围绕某个命令行工具展开，且输入参数边界清晰。

适合：
- 任务本质上是“帮我正确调用某个工具”
- 工具是第一公民，而不是可选附属
- 参数可以稳定映射

先不要用它，如果：
- 现在只是分析、起草、评审类 skill
- 用户连最终会不会落到某个 CLI 都还没决定
- 工具接口变化快

---

### `command-dispatch`
**何时考虑：** skill 需要基于用户意图在多个命令/模式之间分发。

适合：
- 已经存在稳定的命令族
- 意图到命令的路由规则比较清晰
- 用户期望的是“命令入口”而不是“思考型助手”

先不要用它，如果：
- 现在只有单一流程
- 路由规则还在变化
- 还没有足够真实案例证明需要分发

---

### `command-arg-mode`
**何时考虑：** 已经启用了 `command-tool` 或 `command-dispatch`，并且参数传递方式需要显式约束。

建议：
- 仅在命令模式已确定时再声明
- 不要脱离命令场景单独讨论这个字段

---

## 3. `metadata.openclaw.*` 的常见用法

### `metadata.openclaw.requires`
用于声明 skill 成功运行依赖的外部能力。

常见内容：
- CLI 工具，如 `jq`、`kubectl`、`psql`
- 运行时，如 `python3`、`node`
- 项目内前置条件，如“仓库已初始化并包含某配置文件”

适合：
- 缺了这些依赖，skill 基本无法完成任务

不适合：
- 只是“有这些会更方便”
- 用户仍在早期探索，还不确定最终依赖

示例：

```yaml
metadata:
  openclaw:
    requires:
      - python3
      - psql
```

### `metadata.openclaw.install`
用于说明如何补齐依赖。

适合：
- skill 面向第一次搭环境的使用者
- 没有安装步骤，用户几乎无法成功运行

不适合：
- 团队环境默认已具备
- 安装动作高度因团队而异
- 当前版本只想先说明能力，不想绑定具体安装方式

示例：

```yaml
metadata:
  openclaw:
    install:
      - pip install -r requirements.txt
      - brew install jq
```

### `metadata.openclaw.os`
用于说明适用系统或明显受系统差异影响。

适合：
- 命令、路径或安装步骤强依赖系统
- 某些平台根本不支持

示例：

```yaml
metadata:
  openclaw:
    os:
      - linux
      - macos
```

### `metadata.openclaw.primaryEnv`
用于标记核心运行环境或主要技术栈。

适合：
- skill 强绑定某语言/运行时
- 需要帮助调用方快速理解主要执行上下文

示例：

```yaml
metadata:
  openclaw:
    primaryEnv: python
```

---

## 4. 推荐组合

### 组合 A：最小 skill

```yaml
---
name: changelog-writer
description: 帮用户根据代码变更和上下文起草发布说明。当用户要整理版本更新、总结改动影响或生成 release notes 时使用。
---
```

适合：
- 首次验证技能方向
- 无环境依赖
- 无命令型入口需求

### 组合 B：维护型 skill

```yaml
---
name: api-migration-guide
description: 帮用户规划 API 升级迁移步骤，并输出迁移草案、风险点和验证清单。当用户准备升级 SDK、修改接口调用或整理迁移影响时使用。
---
```

配套建议：
- 增加 `references/`
- 在参考文件里放版本差异、迁移清单和常见坑

### 组合 C：环境型 skill

```yaml
---
name: local-db-reset
description: 帮用户重建本地数据库环境，并给出依赖检查、执行顺序和验证步骤。当用户要重置开发数据库、补齐本地依赖或排查迁移状态时使用。
metadata:
  openclaw:
    primaryEnv: python
    os:
      - linux
      - macos
    requires:
      - python3
      - psql
    install:
      - pip install -r requirements.txt
---
```

适合：
- 外部环境决定成功率
- 需要显式说明前置条件

### 组合 D：工具协同型 skill（高级）

只在用户已经明确需要命令驱动时考虑：

```yaml
---
name: kubectl-safe-runner
description: 帮用户安全地组织常见 kubectl 操作，并在执行前确认上下文、命名空间和目标资源。当用户要查询、描述或谨慎执行集群运维命令时使用。
user-invocable: true
command-tool: kubectl
command-arg-mode: raw
metadata:
  openclaw:
    requires:
      - kubectl
    os:
      - linux
      - macos
---
```

如果用户还没有稳定命令边界，先不要进入这个组合。

---

## 5. 常见错误

- 还没确认需求，就把所有高级字段都加上
- 只有一个小 skill，却先拆出大量 references
- 把 `install` 写成与团队强耦合的私有步骤，却没有注明适用前提
- 明明只是思考型 skill，却过早引入 `command-tool`
- `description` 只写“做什么”，没写“什么时候用”

---

## 6. 简化判断法

拿不准时按这个顺序判断：

1. 只用 `name` + `description` 是否已经能表达清楚？
2. 如果不能，是缺结构、缺依赖声明，还是缺命令入口？
3. 只有确认缺口后，再补对应字段。

默认原则：**先让 skill 能清楚工作，再让它显得完整。**
