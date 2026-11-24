---
name: worktree
description: 实质性代码变更的作业隔离纪律。用于：无 issue 流程的临时变更（新能力、行为变更、多文件或跨模块改动）在首次编辑前建立独立 worktree；主 checkout 有未提交改动时的变更任务；接管或清理既有 worktree。不用于：issue 驱动实现流程的 worktree 约定（implement 的事）；诊断纪律与测试先行（debug、tdd 的事，本 skill 只裁决作业位置，与它们叠加）；单文件琐碎修复与纯只读任务（直接作业）。
---

# Worktree 作业隔离

## 意图锚点（每次使用前必读）

本 skill 守护一条主线：**实质性变更的第一处编辑发生在 worktree 内，不落在主 checkout。** 隔离以编辑路径为准，不以会话 cwd 为准——cwd 在 worktree 而编辑写主树绝对路径，等于没有隔离。

纪律：

- 开工闸：首次 edit/write 前判定规模。实质变更先隔离再动手；琐碎修复与纯只读直接作业；非 git 项目无 worktree 可建，直接作业。拿不准是否实质 → 隔离，事后迁移的成本远高于隔离
- 主 checkout 有未提交改动时，非琐碎变更必须隔离。在混有他人改动的脏树里直接改，事后只能按 hunk 剥离并恢复主树（2026-11-24 两起返工：52 分钟与 3 小时作业后被迫迁移）
- issue 驱动流程按 implement 正文的 worktree 约定执行，本 skill 不重复管辖
- 诊断、测试先行等任务自身纪律照常叠加（debug、tdd），本 skill 只裁决作业位置

## 工作流

1. **快照主树**：`git status --short` 记录主 checkout 既有改动。不碰、不恢复、不提交他人改动；快照供收尾对账与撞车预判
2. **建 worktree**：默认用宿主 harness 机制（OpenCode：`worktree_create`，名称 = 任务短名 kebab-case）；无 harness 机制时用 `git worktree add <项目根>/.worktrees/<任务名> -b worktrees/<任务名>`（分支命名与 implement 一致），首次把 `/.worktrees/` 写入 `.gitignore`（该行不夹带进任务提交）。创建前 `git worktree list` 核对路径与分支占用；基线取当前 HEAD，不擅自更换基线分支
3. **迁入会话**：会话开在主 checkout 时，建后迁移会话（OpenCode：`session.move`）。此后第一个编辑动作前核对目标路径在 worktree 内
4. 按任务自身纪律作业
5. **收尾三选一，问用户**：合回基线 / 保留 worktree / 丢弃。合回 = 在 worktree 提交后回主 checkout 合入；丢弃 = 确认后删除
6. **清理**：合回或丢弃后删除 worktree（harness 机制或 `git worktree remove`）；保留的在交付说明中写明路径与分支

## 接管与迁移

- 接管既有 worktree（含他人或前会话所建）：先核对 `git worktree list` 的登记路径、实际分支、未提交内容，与任务记录（issue、交接文档）一致再动手；不符先查明，不覆盖、不重置
- 发现主 checkout 混有本任务改动（历史纠偏残留）时按迁移处理：纯本任务文件复制进 worktree；混合文件按 hunk 剥离；主树恢复他人改动原状。迁移属高危操作，动手前把双方改动清单列给用户确认

## 授权

- 直接执行：快照、建 worktree、迁会话、worktree 内作业
- 执行后告知：worktree 内提交
- 必须先确认：合回基线、丢弃变更、删除 worktree、改动主树既有内容
