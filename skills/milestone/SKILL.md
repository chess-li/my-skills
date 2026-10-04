---
name: milestone
description: 管理交付 milestone 的范围与执行入口。用于创建或维护 docs/milestones/ 文档、查看 milestone 进度，以及完成指定 milestone 时定位跨限界上下文的 issue 子集。不用于定义能力目标与验收标准（spec 的事）；不用于 issue 格式与生命周期（issues 的事）；不用于单个 issue 的实现与验收（implement 的事）；不用于技术决策（design 的事）。
---

# Milestone 管理

## 意图锚点

**milestone 组合一次交付的范围；spec 保存稳定的能力断言；issue 保存执行状态。** 一个 milestone 可包含 N 个限界上下文中的 issue 子集。`guide_issue.md` 管理单个上下文的全部子 issue；milestone 完成不要求该上下文的 guide 归档。

## 核心工作流

### 1. 定位 milestone 与范围

读取 `DOMAINS.md` 和已有 `docs/milestones/` 文档。涉及新概念或命名时先走 <use-skill>domains</use-skill>。

- 维护或执行：以文件名中的完整 ID 定位，如 `M1-plugin-kernel`。用户只给序号或名称时，唯一匹配即可继续；多个候选才交用户选择。
- 创建：沿用项目命名规则；无规则时用 `M<下一序号>-<kebab-case 名称>`。ID 发布后保持稳定。
- 读取纳入的 spec 能力与验收条款。目标未被覆盖或需要改变断言时，先走 <use-skill>spec</use-skill>；目标与交付范围尚未决定时，走 <use-skill>interview</use-skill> 收敛后再落盘。

完成物：唯一 milestone ID，以及每个纳入上下文的 spec 引用和交付范围。查看与执行已有 milestone 时直接进入第 3 步。

### 2. 写 milestone 文档

落 `docs/milestones/<milestone-id>.md`，使用下方模板。规范依据和完成出口引用 spec 的能力标题与验收编号；spec 没有编号时用验收条款所在标题定位，必要时先由 spec 补足可定位的范围。milestone 不另写能力断言。

本次纳入按上下文列交付范围；明确出界列本次不交付的部分。新增、移出范围或调整完成出口时同步引用，并在变更历史记依据。不要在 spec 中保存 milestone 归属。

```markdown
# <milestone-id>：<名称>

## 目标
<本次交付的用户价值>

## 规范依据
- [<上下文／能力>](../contexts/<上下文>/<上下文>-spec.md#<标题锚点>)：<纳入的验收条款>

## 本次纳入
- <上下文>：<本次交付范围>

## 明确出界
- <不在本次交付范围内的能力或验收条款>

## 依赖
- <前置能力、环境或其他 milestone；issue 依赖仍写 blockedBy>

## 完成出口
- <引用的验收条款全部通过，以及需要验证的交付结果>

## 变更历史
- YYYY-MM-DD：<范围变更及依据>
```

完成物：spec 引用可解析、纳入与出界无重叠的 milestone 文档。文档不存 issue 状态、验证记录或提交区间。

### 3. 找出 issue 子集并核对覆盖

加载 <use-skill>issues</use-skill>，递归读取 `docs/issues/` 中子 issue 的 frontmatter，包含归档；精确匹配 `milestone: <milestone-id>`。排除所有 `guide_issue.md`，正文提及 ID 不算归属。字段格式和 guide 规则以 issues 为准。

按 issue 存放的上下文分组；读取对应 guide 的覆盖对账作为线索，状态以子 issue frontmatter 为准。一个跨上下文 issue 只列一次，但把它目标中引用的全部 spec 映射到覆盖上下文；不能因其他上下文目录没有 issue 就重复建单。

将每条纳入的验收条款对照子 issue 的验收清单：

- 已被当前 milestone 的 issue 覆盖：沿用。
- 当前行为已经满足：只有带当前 milestone 标签的 issue 验证记录可以作为本 milestone 的完成证据；已有独立 issue 或其他 milestone 的记录不能直接改变归属。没有当前 milestone 的承载 issue 时，建立一个验证型子 issue，再记录验证结果。
- 尚未覆盖：先按概念检索其他 milestone 或独立 issue。已有当前 milestone issue 时复用；独立 issue 只有在用户明确授权改绑后才能转入当前 milestone，否则建立当前 milestone 的验证型子 issue；属于其他 milestone 的共用前置用 `blockedBy` 引用，不改绑。确无承载者时按引用的 spec 创建子 issue，写入当前 milestone 字段，并更新本上下文已有 guide。

某个纳入上下文的验收条款没有被匹配子 issue 覆盖时，使用 <use-skill>issues</use-skill> 按该条款创建 issue；跨上下文 issue 已覆盖该条款时不重复创建。需要拆分时只在该上下文建立 guide，再使用 <use-skill>implement</use-skill> 抓取。

标签指向不存在的 milestone，或 issue 的目标／验收范围超出本 milestone 时，列出不一致项；依据已授权的范围修正，否则交用户裁定。修正前不执行该 issue，也不宣称 milestone 完成。

完成物：按上下文分组的成员集合、逐条验收覆盖及未解决的不一致项。查询结果留在会话中；归属只写子 issue 字段，不另建成员索引或进度文件。

### 4. 按成员集合推进

查看进度时，只报告第 3 步查询得到的状态、覆盖缺口和阻塞。创建或维护 milestone 不自动开始实现；用户要求完成 milestone 时，再进入执行。

按 issues 的 frontier 规则选择成员，`blockedBy` 可以跨上下文或指向其他 milestone 的 issue。读取已在执行的成员及对应 worktree 后按 <use-skill>implement</use-skill> 接管；新成员也由 implement 核验验证条件后抓取。guide 只供对账，不作为待实现成员。完成一份后重新读取成员状态，继续其余成员；尚未满足的依赖和未决决策按 implement 的入口规则处理，不因部分 issue 归档而结束整个 milestone。

完成物：成员 issue 中实时保存的执行与验证记录。

### 5. 核对完成出口

重新读取 milestone、spec 与匹配的子 issue，逐条核对：纳入的验收条款和完成出口都有可复核验证记录；当前 milestone 成员全部 `archived`；没有未解决的标签／范围不一致或前置依赖。`wontfix` 表示拒绝，不等于完成；范围调整先更新 milestone，能力断言变化先回 spec。

通过后报告完成并引用证据；缺项时报告未完成项并回到相应的 issue 或范围决策。guide 可继续管理该上下文的其他 milestone 与独立 issue，其状态不计入本 milestone 的完成条件。milestone 文档不维护独立状态或进度副本。

## 授权与默认值

- 默认直接执行：读取、检索、范围对账和进度报告。
- 执行后告知：在已确定的范围内创建或更新 milestone、关联子 issue、补验证证据和变更历史；git 仓库落盘即提交。
- 尚未授权的范围变更、已有 issue 的改绑、milestone 删除或已发布 ID 改名先交用户裁定；用户已明确指定这些动作时直接执行，不重复确认。
