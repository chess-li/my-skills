---
name: bootstrap
---

# 项目初始化

## 意图锚点（每次使用前必读）

本 skill 守护一条主线：**让项目（含全部子孙项目）的 AGENTS.md、DOMAINS.md、ARCHITECTURE.md 与 codegraph 索引从项目事实派生、与事实同步、可增量更新。** 基座只铺底与同步，不承担日常维护：词条与歧义演进归 domains skill，架构决策演进归 design skill。

改动护栏：
- 只写从项目事实（manifest、代码、已有文档）可确认的内容；推断不出的留白，不虚构
- 已有文件的手写内容是用户资产：AGENTS.md 标记区外一字不动；DOMAINS.md/ARCHITECTURE.md 的改动先出清单经确认再落盘
- codegraph 只装不更新，任何安装动作先征得同意
- 文档语言跟随项目已有文档；无文档则跟随用户输入语言

## 核心工作流

### 1. 勘察项目树

子项目判据：目录含独立项目 manifest（package.json、go.mod、Cargo.toml、pyproject.toml、pom.xml、build.gradle(.kts) 等）；排除 node_modules、vendor、dist、build 等产物与依赖目录。产物：项目清单（根 + 各子项目路径、一句话定位）。

### 2. AGENTS.md（每个项目一份）

生成内容置于标记区 `<!-- bootstrap:begin -->` 与 `<!-- bootstrap:end -->` 之间；更新只重算标记区，区外保留。

按文件现状分路：
- **不存在** → 新建，全文置于标记区内
- **存在、无标记区** → 扫描与待生成内容重复的段落：重复段落收编进标记区，删除原段落前向用户出示清单确认；用户拒绝 → 保留原文，标记区只补不重复的增量
- **存在、有标记区** → 重算标记区，区外不动；发现多个标记区 → 以第一个为准，其余报告用户

标记区内容（只列事实，不写建议与规范）：

```markdown
## 项目概览
<一句话定位>。技术栈：<…>。常用命令：构建 <…>、测试 <…>、lint <…>。

## 子项目（仅根项目）
- <相对路径> — <一句话定位>，详见 `<相对路径>/AGENTS.md`

## 文档入口（仅根项目）
- 统一语言：`DOMAINS.md`
- 架构事实：`ARCHITECTURE.md`
```

子项目的 AGENTS.md 含概览与其下子项目索引（若有），并以相对路径引用根级 `DOMAINS.md` / `ARCHITECTURE.md`。

### 3. DOMAINS.md（根级单文件）

- 新建：从项目事实提取核心领域概念（模块名、核心实体、业务术语），最小集 3–10 条；词条格式：术语 + 定义 + 所属限界上下文 + 反例。只有一个上下文时不拆子文件；提取不足 3 条 → 不建文件，报告用户
- 已存在 → 与事实比对，产出增删改清单（修订失实词条、补缺失核心概念），用户确认后落盘；手写词条不删，与事实冲突的在清单中标注交由用户裁定
- 追加一行变更历史（YYYY-MM-DD 同步了什么）

### 4. ARCHITECTURE.md（根级单文件）

- 新建：只写可确认的架构事实——技术栈、项目/子项目结构与依赖关系、部署形态、跨模块契约
- 已存在 → 只更新事实性描述；决策性内容（选型、取舍理由）属 design skill 管辖，不动，失实的仅报告。同样先出清单、确认后落盘
- 追加一行变更历史

### 5. codegraph 索引

```bash
# invocation optional
command -v codegraph                    # 无 CLI → 询问用户是否安装，拒绝则跳过本步
npm install -g @colbymchenry/codegraph  # 仅用户同意安装后执行
codegraph init <目录>                   # 仅对清单中用户同意的目录执行；已有 .codegraph/ 跳过
```

- 列出尚无 `.codegraph/` 的目录清单，一次性征求同意
- 已有 `.codegraph/` 的一律跳过：不重建、不同步；不升级 CLI 版本

### 6. 收尾

- 核对：每个项目 AGENTS.md 存在且标记区最新；根级 DOMAINS.md、ARCHITECTURE.md 存在且与事实一致；codegraph 状态与用户选择一致
- 向用户报告生成/更新/跳过三类清单，并交代后续维护归属：词条与歧义 → domains skill，架构决策 → design skill

## 授权分档

- 直接执行：勘察、读取、分析、起草
- 执行后告知：新建不存在的文件、重算 AGENTS.md 标记区
- 必须先确认：删除已有 AGENTS.md 原段落、改动已有 DOMAINS.md/ARCHITECTURE.md、安装 codegraph CLI、执行 codegraph init
