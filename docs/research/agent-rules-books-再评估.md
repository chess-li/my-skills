# agent-rules-books 再评估

调查日：2026-10-05

目标版本：agent-rules-books `v0.6-3-g893a88a`（`893a88a6fce3a80c565bf39ac65021b43a8b2990`）；本仓库 `7d17167` 的已提交 skill 文本。工作区里未提交的研究文件改写不改变这些 skill 断言。

过期条件：上述提交中被引用文件的断言改版，或 agent-rules-books 的 mini 决策规则改版。

支持的决策：不再把 14 组规则安装为全局规则或书名 skill。已落地的四条条件性机制继续保留。现在不新增第五条 skill 正文、reference 或模式/可靠性清单。

不决定什么：不改 skill 措辞；不规定超时、重试或重复次数；不把源规则当作书籍原文；不回滚已落地参考。

## 问题与范围

问题：在 [融入评估](agent-rules-books-融入评估.md) 已抽出并落地的机制之上，该提交的 14 组规则还有哪些值得引入本仓库。

`agent-rules-books/` 指 `/Users/chess/workspace/opensource/opensource-skills/agent-rules-books` 的该提交。本仓库路径相对于本仓库根。

已读：14 个 `SKILL.md` 的 mini 入口句；14 个 mini 的决策规则（主会话抽读结论所引段落，其余 mini 由只读调查按条摘录后由主会话剔除同义项和相反压力）；`docs/COMPATIBILITY.md` 的冲突/重叠裁决；APoSD–Clean Code、Clean Architecture–PoEAA、DDD–PoEAA 三份对比的 Loading Decision；`_rule-workbench/PROCESS.md` 的追溯要求；traceability 中 intentionally lost 的抽查。本仓库对照了已落地的失败契约、遗留变更安全回路、责任先于模式、评审维度，以及 `domains`、`tdd`、`skill-creator` 的对应断言。

不查：书籍原文；14 组 `full` 逐行；远程在上次 fetch 之后的新提交。兼容矩阵 78/2/11 仍采用文档自述，未重算。

## 结论

1. 14 个 `SKILL.md` 都要求先读 mini，full 只在 mini 不够时作更深参考。置信：事实。来源：各书 `SKILL.md:11`。无冲突。

2. 压缩过程要求每条保留规则回溯到 full，并记录合并或有意丢弃。抽查的 intentionally lost 是目录名、示例、政策措辞或 nano 压缩，并写明操作效果留在 mini。置信：事实（抽查）。来源：`agent-rules-books/_rule-workbench/PROCESS.md:92-114`；`agent-rules-books/_rule-workbench/refactoring/traceability.md:88,104-105`；`agent-rules-books/_rule-workbench/domain-driven-design/traceability.md:13,94-95`；`agent-rules-books/_rule-workbench/a-philosophy-of-software-design/traceability.md:131-133`。未逐节重走 14 份 Section coverage review。无冲突。

3. 值得引入本仓库的机制仍是已落地的四条，不是新的书或新的 skill。它们改变的是当时 skill 留空的决策，并有本地返工；源规则整理不是单独证据。置信：推断。来源：`skills/workflow/spec/references/failure-contract.md:9-25,45`；`skills/coding/tdd/references/legacy-change-safety.md:9-28,39`；`skills/coding/code-review/references/review-dimensions.md:15-18`；`skills/workflow/design/references/responsibility-before-pattern.md:9-17,29`；`skills/skill/skill-creator/SKILL.md:99`；`agent-rules-books/docs/CRITICISM.md:15-17`。无冲突。

4. 失败契约保留的是边界、权威状态、成功阶段、可见性、超时、重试资格、重复/重放、容量与隔离、恢复、诊断和演进。Release It! 的命名稳定性模式，以及生产演练、game day、chaos，不改变这些字段已经要求回答的问题；演练还超出本仓库 skill 的规格与实现职责。置信：推断。来源：`agent-rules-books/release-it/release-it.mini.md:16-20,27`；`skills/workflow/spec/references/failure-contract.md:15-24,38`。无冲突。

5. DDIA 剩余的复制拓扑、分区、隔离异常名词、批流重算清单和共识算法名，是失败契约字段的下一层目录，不是新的决策类型。失败契约已经要求写出一致性、冲突处置、重放和恢复，并禁止规定一致性等级。把这些名词写进共享参考，会让每次失败边界都携带第二份可靠性清单。置信：推断。来源：`agent-rules-books/designing-data-intensive-applications/designing-data-intensive-applications.mini.md:24-30`；`skills/workflow/spec/references/failure-contract.md:16-23,38-40`。无冲突。

6. Working Effectively with Legacy Code 的决策层已经在遗留变更安全回路：保留行为、目标行为、characterization、change point、最小 seam、行为与清理分离。没有未覆盖且会改变测试或调试决策的 mini 规则。置信：推断。来源：`agent-rules-books/working-effectively-with-legacy-code/working-effectively-with-legacy-code.mini.md:13-20`；`skills/coding/tdd/references/legacy-change-safety.md:9-28`；`skills/coding/tdd/SKILL.md:26-28`。无冲突。

7. 复杂度判断继续用认知负担或变更扩散，按已命名 smell 做最小治疗，验证后停止，不以行数判定。Refactoring 与 Refactoring.Guru 的 smell 分类、治疗顺序和 Rule of Three 是目录或数值，不引入。置信：推断。来源：`skills/coding/code-review/references/review-dimensions.md:16-17`；`agent-rules-books/refactoring-guru/refactoring-guru.mini.md:19-26`。无冲突。

8. Clean Code 不引入。它与 APoSD 被标为重叠，并在函数大小和注释上施压不同；同等加载会把代码拆到 APoSD 认为变浅的程度。本仓库已采纳认知负担一侧。置信：推断。来源：`agent-rules-books/docs/compatibility/a-philosophy-of-software-design/clean-code.md:6,12-14,42-45`；`agent-rules-books/clean-code/clean-code.mini.md:16,23`；`agent-rules-books/a-philosophy-of-software-design/a-philosophy-of-software-design.mini.md:15,20`；`skills/coding/code-review/references/review-dimensions.md:16-17`。无冲突。

9. APoSD 的「拒绝只增加名字的薄封装」已经由「只转发、只增加名称、没有当前消费者不得作为默认方案」覆盖。深模块口号、注释契约和「先测量再优化」不再单独立条。置信：推断。来源：`agent-rules-books/a-philosophy-of-software-design/a-philosophy-of-software-design.mini.md:15,22,25`；`skills/workflow/design/references/responsibility-before-pattern.md:17`；`skills/coding/code-review/references/review-dimensions.md:15-16`。无冲突。

10. Clean Architecture 的一律向内依赖、一律端口和纯请求模型不引入。对比文件要求它与 PoEAA 二选一，因为同等加载会多加层和模式机制。本仓库已要求最轻形状，并拒绝没有当前消费者或只转发的层。置信：推断。来源：`agent-rules-books/clean-architecture/clean-architecture.mini.md:13-18`；`agent-rules-books/docs/compatibility/clean-architecture/patterns-of-enterprise-application-architecture.md:6,12-14`；`skills/workflow/design/references/responsibility-before-pattern.md:15,17`。无冲突。

11. PoEAA 的模式菜单不引入。责任、不变量、边界和当前消费者已经必须先于模式名；远程调用隐藏在长事务中已不得作为默认方案。把 Transaction Script、Unit of Work、Identity Map 等写成默认步骤，会撤销「模式名是结果」。置信：推断。来源：`agent-rules-books/patterns-of-enterprise-application-architecture/patterns-of-enterprise-application-architecture.mini.md:13-15,22,27-28`；`skills/workflow/design/references/responsibility-before-pattern.md:15-17,22`。无冲突。

12. DDD、DDD Distilled 和 Implementing DDD 的战术目录、上下文关系名和 Core Domain 预分类不引入。DDD 与 PoEAA 被标为冲突，不得作为同一任务的平等指导。无真实歧义时不扩张术语表；跨上下文不共享外部模型已经写在设计参考里，不必再写入 `domains`。置信：推断。来源：`agent-rules-books/docs/compatibility/domain-driven-design/patterns-of-enterprise-application-architecture.md:6,12-14`；`agent-rules-books/domain-driven-design-distilled/domain-driven-design-distilled.mini.md:13-15`；`skills/workflow/domains/SKILL.md:16`；`skills/workflow/design/references/responsibility-before-pattern.md:13,23`。无冲突。

13. Code Complete 的施工微规则（控制流、变量作用域、伪代码、防御性检查）与现有评审的命名、复杂度和真实路径重叠，不构成新的 skill 决策。不引入。置信：推断。来源：`agent-rules-books/code-complete/code-complete.mini.md:15-23`；`skills/coding/code-review/references/review-dimensions.md:13-17`；`skills/coding/tdd/SKILL.md:26`。无冲突。

14. The Pragmatic Programmer 不引入为通用 skill。单一权威表示、显式契约和正交责任已经由 spec、domains 和 design 的分工承担。broken windows 要求碰到衰败就修，与「最小治疗，验证后停止，无关清理另列」相反。置信：推断。来源：`agent-rules-books/the-pragmatic-programmer/the-pragmatic-programmer.mini.md:16-17,35`；`skills/workflow/domains/SKILL.md:10,16`；`skills/coding/code-review/references/review-dimensions.md:17`。无冲突。

15. 源规则整理仍然不能单独充当 skill 正文证据。上述未落地项都没有本仓库的新返工或测试失败。置信：推断。来源：`skills/skill/skill-creator/SKILL.md:99`；`agent-rules-books/docs/CRITICISM.md:15-17`。无冲突。

## 冲突

无。调查摘录曾把大量 mini 句子标为「未覆盖」。主会话核对后，这些句子或与已有断言同义，或是目录和数值，或与已采纳压力相反，不构成第五条引入。

## 未决

- 已落地的四条是否减少后续真实任务的缺陷、返工或评审时间：未知。参考文件自己也写明有效性待观察。
- 两条理论缺口现在不落地。拉动条件到场前不改 skill：
  - 复杂度下拉到拥有者，或用接口消掉非用户可见的无效状态。来源：`agent-rules-books/a-philosophy-of-software-design/a-philosophy-of-software-design.mini.md:18,21`。边界：不能用来删除 spec 已要求枚举的用户可观察失败。拉动：真实评审把调用方重复防御当成合格，或把缩小了调用方负担的实现仅因实现变复杂而判为过度设计。
  - 线性一致或共识只在必须达成一致且延迟或可用性成本可接受时使用；一个需要立即一致的业务概念不拆到多个服务的热路径。来源：`agent-rules-books/designing-data-intensive-applications/designing-data-intensive-applications.mini.md:28,30`。拉动：真实设计因默认上强一致，或因拆分紧密一致概念造成返工。
- 事务脚本与领域模型按 force 选择仍是既有观察项，拉动条件未到场。到场时也只写 force 问题，不引入模式菜单。来源：`skill-证据日志.md` 2026-10-05 观察名单；`agent-rules-books/patterns-of-enterprise-application-architecture/patterns-of-enterprise-application-architecture.mini.md:15`。
- 14 份 traceability 是否每一节都满足 `PROCESS.md:92-114`：未逐节重走。抽查未发现被有意丢弃、且会改变决策的规则。
- `full` 是否含有 traceability 未记载的决策规则：未知。这不构成引入理由。
- 上次 fetch 之后 `origin/main` 是否有新提交：未知。本次未 fetch。

## 来源

`agent-rules-books/` = `/Users/chess/workspace/opensource/opensource-skills/agent-rules-books` @ `893a88a6fce3a80c565bf39ac65021b43a8b2990`。本仓库路径相对于根 @ `7d17167`。

- `agent-rules-books/*/SKILL.md:11`
- `agent-rules-books/_rule-workbench/PROCESS.md:92-114`
- `agent-rules-books/_rule-workbench/refactoring/traceability.md:88,104-105`
- `agent-rules-books/_rule-workbench/domain-driven-design/traceability.md:13,94-95`
- `agent-rules-books/_rule-workbench/a-philosophy-of-software-design/traceability.md:131-133`
- `agent-rules-books/docs/COMPATIBILITY.md:16-24`
- `agent-rules-books/docs/CRITICISM.md:15-17`
- `agent-rules-books/docs/compatibility/a-philosophy-of-software-design/clean-code.md:6,12-14,42-45`
- `agent-rules-books/docs/compatibility/clean-architecture/patterns-of-enterprise-application-architecture.md:6,12-14`
- `agent-rules-books/docs/compatibility/domain-driven-design/patterns-of-enterprise-application-architecture.md:6,12-14`
- `agent-rules-books/release-it/release-it.mini.md:16-20,27`
- `agent-rules-books/designing-data-intensive-applications/designing-data-intensive-applications.mini.md:24-30`
- `agent-rules-books/working-effectively-with-legacy-code/working-effectively-with-legacy-code.mini.md:13-20`
- `agent-rules-books/a-philosophy-of-software-design/a-philosophy-of-software-design.mini.md:15,18,20-22,25`
- `agent-rules-books/clean-code/clean-code.mini.md:16,23`
- `agent-rules-books/clean-architecture/clean-architecture.mini.md:13-18`
- `agent-rules-books/patterns-of-enterprise-application-architecture/patterns-of-enterprise-application-architecture.mini.md:13-15,22,27-28`
- `agent-rules-books/domain-driven-design-distilled/domain-driven-design-distilled.mini.md:13-15`
- `agent-rules-books/code-complete/code-complete.mini.md:15-23`
- `agent-rules-books/the-pragmatic-programmer/the-pragmatic-programmer.mini.md:16-17,35`
- `agent-rules-books/refactoring-guru/refactoring-guru.mini.md:19-26`
- `skills/workflow/spec/references/failure-contract.md:15-25,38-40,45`
- `skills/coding/tdd/references/legacy-change-safety.md:9-28,39`
- `skills/coding/tdd/SKILL.md:26-28`
- `skills/workflow/design/references/responsibility-before-pattern.md:13-17,22-23,29`
- `skills/coding/code-review/references/review-dimensions.md:13-18`
- `skills/workflow/domains/SKILL.md:10,16`
- `skills/skill/skill-creator/SKILL.md:99`
- `docs/research/agent-rules-books-融入评估.md`
