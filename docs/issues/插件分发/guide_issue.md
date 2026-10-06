---
status: open
category: enhancement
blockedBy: []
---

# 插件分发

## 排查结论

插件分发已有 portable 包和 OpenCode、Codex、Kimi Work、Gemini 四种方言。WorkBuddy 应用内的 `codebuddy plugin` 能安装用户级插件，但安装器尚未接入。`agy` 不存在时 Gemini 安装仍按旧断言记为失败；spec 已改为 skipped。

## 覆盖对账

| spec 断言 | 归属 |
| --- | --- |
| 构建 portable 包、名称与版本、Codex/OpenCode/Kimi 安装、重复安装、单平台失败、卸载与重复卸载、默认插件名 | `01_安装插件而非散装skill_issue.md`，清单已勾 |
| Gemini 安装成功、重复安装、命令失败、主目录隔离、卸载与同名目录保护、无单独时限 | `02_gemini插件安装与卸载_issue.md`，清单已勾。其中「`agy` 不存在记为失败」已被 2026-10-06 spec 取代，当前语义归 04 |
| WorkBuddy 安装、重复安装、CLI 缺失、命令失败、市场名冲突、卸载、无单独时限 | `03_workbuddy插件安装与卸载_issue.md` |
| `agy` 不存在时 Gemini 安装 skipped；`agy` 存在但安装失败仍失败 | `04_gemini安装在agy缺失时记为skipped_issue.md` |

## 拆分理由

WorkBuddy 方言与 Gemini 安装的 skipped 策略可以分别验收，不互相阻塞。

## 子 issue 状态

| issue | status | frontier |
| --- | --- | --- |
| `01_安装插件而非散装skill_issue.md` | doing | 否 |
| `02_gemini插件安装与卸载_issue.md` | doing | 否 |
| `03_workbuddy插件安装与卸载_issue.md` | open | 是 |
| `04_gemini安装在agy缺失时记为skipped_issue.md` | open | 是 |

## 验收清单

- [ ] 本目录子 issue 全部归档

## 变更历史

- 2026-10-06 创建。上下文已有 01、02 在执行；本次拆出 WorkBuddy 方言与 Gemini 安装 skipped。
