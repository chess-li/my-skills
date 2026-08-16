# AGENTS.md

本工作区是 skill 创作项目。

## 统一语言

领域术语见 `DOMAINS.md`：讨论与命名前先查已有词条；会话中出现歧义信号时即时沉淀，不要等会话结束。

## 治理 skill（.agents/skills/，项目私有，不对外分发）

- 从零创建新 skill → 加载 `skill-creator`
- 修改、优化、审查已有 skill → 加载 `skill-iteration-review`

纪律：
- 创建或迭代 skill 前必须先加载对应治理 skill，不凭直觉动笔
- 改动必须附带证据（一次真实返工或一条测试失败）；无证据的想法记入 `skill-证据日志.md` 观察名单，不落地
- 共用设计原理在 `.agents/skills/shared/design-principles.md`，创建与审查都以它为准

## 对外产物

`skills/` 下的 skill（如 `skills/domains/`）是对外分发的产物，其创建与改动同样走上述治理流程。
