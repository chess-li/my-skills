---
status: open
category: enhancement
blockedBy: []
---

# Gemini 安装在 agy 缺失时记为 skipped

## 目标

把 Gemini 安装在 `agy` 不存在时的结果从失败改为 skipped，满足 `docs/contexts/插件分发/插件分发-spec.md` 中该条验收标准。安装命令失败的语义不变。

## 验收清单

- [ ] 当 `agy` 不存在时，Gemini 安装应标记为 skipped，不记为失败，且不改写 `.gemini`。skipped 不使安装流程失败。其他平台继续。
- [ ] 当 `agy` 存在但 `agy plugin install` 返回失败时，应报告 Gemini 失败和原因，且不自动重试。其他已成功的平台结果仍可使用。安装流程不得改写 `.gemini` 来代替该 CLI。

## 显式出界

- 不改 Gemini 卸载。`agy` 不存在且副本或导入记录仍在时，卸载仍失败并保留源目录。
- 不实现 WorkBuddy 方言。那是 `03_workbuddy插件安装与卸载_issue.md`。
- 不改 `agy` 存在时安装成功的副本与导入记录语义。

## 变更历史

- 2026-10-06 创建。用户裁定 CLI 不存在时标记为 skipped，并要求 Antigravity 安装使用同一策略。
