---
name: issues
description: 本地 markdown issue 的格式与生命周期单一信源：创建（含防重复检索）、队列与抓取（frontier = open 且无未归档阻塞）、归档与拒绝记忆，落 docs/issues/。用于：记录新需求或 bug 为 issue；查看待办与当前可抓取的 issue；spec 收口发布执行 issue；其他 skill 需创建或检索 issue 时。不用于按验收标准执行实现与更新执行状态（implement 的事）；不用于 bug 诊断与修复（debug 的事）；不用于澄清需求与验收标准（spec/interview 的事）；不用于会话间交接（handoff 的事）。
---

# Issue

## 意图锚点（每次使用前必读）

本 skill 守护一条主线：**一份 issue 承载一个需求或 bug 从创建到归档的完整生命周期，是人与 agent、会话与会话之间唯一的任务交接面。** 执行状态只写进 issue 文件，不另立平行产物（平行任务文件 = 双事实源，必污染）。

护栏：

- 创建前检索：`docs/issues/` 与 `docs/issues/archive/`（含 wontfix）按概念检索，不只按请求措辞；命中 open → 更新既有 issue，不重复立项；命中 wontfix → 告知用户曾被拒绝及理由，用户坚持才新建
- 书写三原则：耐久性优于精确性——issue 可能挂数周，创建期写行为契约与接口语义，不写会过期的文件路径与行号（模板标注「执行期」的小节允许精确，生命周期短）；行为式不过程式——写 what 不写 how，执行者自己重新探索；验收标准独立可验证，配「显式出界」清单
- 状态即事实：status 字段、所在目录、实际进展三者一致；流转即记变更历史，git 仓库改动即提交
- 本 skill 只管格式与生命周期：执行实现归 <use-skill>implement</use-skill>，bug 诊断修复归 <use-skill>debug</use-skill>

## 核心工作流

### 1. 创建

- 落 `docs/issues/<需求名>.md`（项目已有任务存放约定则跟随），模板见下
- spec 收口的需求：先对照 spec/design 排查代码现状差距，排查结论随创建消息呈现；验收标准逐条抄入验收清单，status: open 即入队列；验证手段留执行方预填
- 单 spec 拆出多份 issue → 建一份母 issue：承载排查结论、spec 节 × 子 issue 覆盖对账（每节有归属，或标注已满足/出界）与拆分理由；依赖只写各子 issue 的 blockedBy，母 issue 不复制依赖、不跟踪子 issue 执行状态；母 issue 验收清单 = 子 issue 全部归档
- bug：category: bug；已知根因或修法只当线索写入「当前位置」，不作结论
- 有依赖：blockedBy 列阻塞方 issue 相对 `docs/issues/` 的文件名（含 .md）。爆炸半径大的机械性改动（wide refactor）不塞进功能 issue——单独立 issue 走 expand–contract（先并存、分批迁移、最后删除），每批一份

### 2. 队列与抓取

- frontier = status: open 且 blockedBy 全部已归档（或路径不存在）；「还有什么可做」= 列 frontier，各附一句话目标
- 抓取 = status 改 doing + 变更历史记一笔；一个会话抓一份，抓完即开始：enhancement 走 <use-skill>implement</use-skill>，bug 走 <use-skill>debug</use-skill>
- 并行会话各抓 frontier 中的不同项；被阻塞项随阻塞方归档自动放行

### 3. 归档与拒绝

- 实现任务：由 <use-skill>implement</use-skill> 第 7 步归档（条件在那边：验收通过、声称未失真、最近一次完整评审无未处理发现）
- debug 修复闭环后：status 改 archived、移入 `docs/issues/archive/`、记变更历史，git 仓库并提交
- 拒绝：status 改 wontfix 归档，理由写入变更历史——归档即拒绝记忆，供创建前检索

**Issue 模板**（frontmatter 与未标注小节由创建者填；标注「执行期」的小节由执行方填与更新）：

```markdown
---
status: open          # open / doing / archived / wontfix
category: enhancement # enhancement / bug
blockedBy: []         # 阻塞方 issue 文件名（相对 docs/issues/）
---

# <需求名>

## 目标
<一句话>，满足 spec：docs/contexts/<限界上下文>/<限界上下文>-spec.md §<能力名>
基线分支：<建任务时检出的分支>（合并目标；非 git 项目省略本行；执行期）
提交区间：<起点 commit>..<终点 commit>（终点归档时补记；非 git 项目省略本行；执行期）

## 验收清单
- [ ] <验收标准（抄自 spec）> —— 验证手段：<命令 / 人工确认步骤>（验证手段为执行期预填）
- [x] <验收标准> —— 已验证：<命令>，结果：<关键输出摘录：测试计数/退出码/响应体>（YYYY-MM-DD）（执行期）

## 显式出界（创建时声明不做）
- <条目>

## 足迹（执行期）
- 仓库：<本任务触及的 git 仓库，含卫星仓库>
- 计划触碰：<文件/模块清单，供他方撞车预判求交>

## 当前位置（执行期，实时更新）
<下一步要做的事>

## 变更历史
- YYYY-MM-DD 创建 / <状态流转或变更>

## 范围外问题（顺手发现，本次不修；执行期）
- <问题 + 位置>

## 评审自检（派完整评审前填；执行期）
- 按 code-review 评审维度清单逐项「已查 + 结论 + 证据」（YYYY-MM-DD）
```

## 冷启动

项目没有 `docs/issues/` → 随第一份 issue 创建，`archive/` 首次归档时创建；不预建空目录、不建索引。现场存在 `docs/tasks/` 未归档任务文件（被取代的老布局）→ 列出并提议迁入 `docs/issues/`（补 frontmatter），用户同意后执行；任务已完成未归档 → 迁入即归档（status: archived、移 `archive/`、记变更历史）；已归档历史留原处，git 历史可查。

## 完整示例（spec 收口到另一会话抓取）

- **现场**：订单 spec 更新收口，用户说"先记下来，下午让另一个会话做"
- **创建**：检索无重复 → 写 `docs/issues/企业下单.md`（status: open，三条验收标准抄入验收清单，显式出界：退款对接）
- **下午新会话**：用户说"看看有什么能做的" → frontier 只有企业下单（open、无阻塞）
- **抓取**：status 改 doing、记变更历史，走 <use-skill>implement</use-skill> 预填验证手段、补足迹
