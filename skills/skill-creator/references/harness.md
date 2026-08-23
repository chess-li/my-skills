# 观测基础设施：三层架构与 hook 迁移

观察-证明-优化是控制回路，skill 只是它的策略宿主。体系按**执行者**分三层，不按概念切 skill：

- **机制层（harness）**：hooks、定时任务、证据日志——负责捕获。skill 给不了确定性执行、持久状态、定时触发，捕获不该拜托模型"记得做"
- **策略层（skill-creator 迭代分路）**：证据判据、取证流程、升格闸、四步工作流——判断的载体
- **原理层（design-principles.md）**：创建与审查共用的设计原理

## hook 迁移边界：上交捕获，不上交判断

hook 写原始事件行（涉及的 skill 文件、改动、定时冒烟结果），语义归因由 skill 取证时完成；判断逻辑进 hook 配置 = 策略散落 + 平台锁定。返工感知留在对话层（hook 够不着），hook 守工件侧，人守结果侧。

hook 也会静默失效：定时任务每周写一条心跳，取证先查心跳，心跳缺席 = 观测系统已死。

## hook 落地顺序（基础设施同样过证据闸）

1. 改动日志 hook（最便宜的确定性收益）
2. 心跳（保活）
3. 冒烟集定时跑（等冒烟集真实存在后）
4. 改动拦截（最后——被无证据改动真实咬过之后再建，预防性拦截只能靠猜，猜出来的门禁最坏）

## 落地实例（2026-08-06，顺序①②）

- 捕获脚本 `scripts/skill-observe.py`；配置信源 `scripts/skill-observe.hooks.json`，安装到用户级 `~/.codex/hooks.json`（欠触发证据都发生在别的项目，项目级配置观测不到）；hook 定义变更后需在 CLI `/hooks` 重新信任（信任按定义哈希记录）
- 事件：`SessionStart` / `SessionEnd` / `UserPromptSubmit` / `PostToolUse`（matcher: Bash、apply_patch）→ `skill-事件日志.jsonl`（工作区根目录）；session.start 行带 model slug，model.change 取证靠它
- 心跳：周 automation「skill-观测心跳」追加 heartbeat 行并自查 7 天内有无 hook 事件行；取证先查心跳，缺席即观测系统已死
- ③冒烟集定时跑、④改动拦截仍未建：等各自的真实返工

## 拆分判据（防止把层次误拆成 skill）

新概念先问归属层，不问"要不要新 skill"。捕获不是 skill（没有模型触发场景）；创建与迭代由 skill-creator + 原理层值守；仅当某职责长出独立触发场景（如每周自动巡检证据日志的定时审计），才允许拆出独立 skill——且优先 user-invoked 或定时触发，不付常驻成本。

## 平台无关最小骨架

未接 hook 时，仍可先用一个追加式 `skill-证据日志.md`（观察名单 / 返工事件 / 升格移出 / 冻结状态）起步；hook 与定时任务等被真实返工咬过再建。事件日志只记机械事实，语义归因在取证时完成。
