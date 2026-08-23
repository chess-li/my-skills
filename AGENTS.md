# AGENTS.md

本工作区是 skill 创作项目。

## 统一语言

领域术语见 `DOMAINS.md`：讨论与命名前先查已有词条；会话中出现歧义信号时即时沉淀，不要等会话结束。

## 治理 skill

创建、修改、审查任何 skill（含本仓库 `skills/` 对外产物）→ 加载 `skill-creator`（`skills/skill-creator/`）。

纪律：
- 动笔前必须先加载 skill-creator，不凭直觉写 SKILL.md
- 改动必须附带证据（一次真实返工或一条测试失败）；无证据的想法记入 `skill-证据日志.md` 观察名单，不落地
- 共用设计原理在 `skills/skill-creator/references/design-principles.md`

## 对外产物

`skills/` 下的 skill 是对外分发的产物；`skill-creator` 本身亦在此目录，本项目与外部消费者同一份。
