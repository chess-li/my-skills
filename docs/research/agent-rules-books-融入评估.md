# agent-rules-books 融入评估

调查日：2026-10-05

目标版本：agent-rules-books `v0.6-3-g893a88a`（`893a88a6fce3a80c565bf39ac65021b43a8b2990`）；本仓库 `7d17167`

过期条件：上述提交中被引用文件的断言改版

支持的决策：不把该提交的 14 组规则安装为本仓库全局规则，也不按书名新增自动触发 skill。机制若被吸收，只进入已有 skill 的条件性参考；源规则整理不能单独充当 skill 正文证据。

不决定什么：不决定超时、重试次数或其他数值；不决定 skill 正文措辞；不把源规则当作书籍原文；不判断未读 mini 的单条机制以后是否值得吸收。

## 问题与范围

问题：`agent-rules-books` 在目标版本的规则集，能否作为本仓库的全局规则或自动触发 skill。

`agent-rules-books/` 指 `/Users/chess/workspace/opensource/opensource-skills/agent-rules-books` 的该提交。本仓库路径相对于本仓库根的 `7d17167`。

已读：`README.md`、`LICENSE`、`_rule-workbench/PROCESS.md`、`docs/COMPATIBILITY.md`、`docs/CRITICISM.md`、14 个规则目录的文件清单、`release-it/SKILL.md`，以及结论中引用的 mini 与兼容对比。本仓库对照了 `spec`、`design`、`tdd`、`debug`、`domains`、`skill-creator`、`code-review` 的对应断言。

不查：书籍原文；14 组 `full` 的逐行内容；其余 13 个 `SKILL.md` 正文；各书 `traceability.md` 是否逐条满足过程要求；远程在上次 fetch 之后的新提交。源仓库工作区里已修改、未提交的 `AGENTS.md` 未被引用。兼容矩阵的 78/2/11 采用文档自述，未重算单元格。

## 结论

1. 该提交有 14 个规则集，每组都有 full、mini、nano 和 `SKILL.md`。置信：事实。来源：`agent-rules-books/README.md:34-38,78-93`；调查日对该提交的目录清点。无冲突。

2. 抽查的 Release It! 入口要求先读 mini，full 只作更深参考。置信：事实。来源：`agent-rules-books/release-it/SKILL.md:7-11`。无冲突。

3. 压缩目标是决策等价，不是句子等价。mini 保留会改变决策的规则；nano 只保留紧上下文下的常驻纠偏。过程要求保留规则回溯到 full 的章节和行号，并记录合并或有意丢弃。置信：事实。来源：`agent-rules-books/_rule-workbench/PROCESS.md:3-9,62-90,92-114`。无冲突。

4. 这些规则是受书籍启发的原创实践指令，不是作者或出版社的官方材料，也不是书籍替代品。许可证是 MIT。置信：事实。来源：`agent-rules-books/README.md:28,203-208,241`；`agent-rules-books/LICENSE:1`。无冲突。

5. README 写明：一次重构实验把 mini 规则分支评为约 74/100，把只提书名的分支评为约 46/100；该结果是早期定性信号，不是基准。置信：事实。来源：`agent-rules-books/README.md:195-199`。无冲突。

6. 兼容矩阵的分数是定性估计，不是任务实证。文档自述互补 78、冲突 2、重叠 11。`agent-rules-books/docs/compatibility/` 下有 91 个 `.md`。置信：事实。来源：`agent-rules-books/docs/COMPATIBILITY.md:3-10,50-62`；`agent-rules-books/docs/CRITICISM.md:75-77`；调查日目录清点。无冲突。

7. 源仓库写明仍没有缺陷率、评审时间或任务结果数据。置信：事实。来源：`agent-rules-books/docs/CRITICISM.md:7,15-17,105-107`。无冲突。

8. 同时加载过多规则会增加 token，并挤占任务上下文。源仓库不能阻止使用者仍然一次挂上太多。置信：事实。来源：`agent-rules-books/docs/CRITICISM.md:19-27`。无冲突。

9. Clean Code 与 APoSD 被标为重叠。对比文件要求二选一作为主要设计或卫生规则集，因为二者在函数大小和注释上施压不同。置信：事实。来源：`agent-rules-books/docs/COMPATIBILITY.md:16-18`；`agent-rules-books/docs/compatibility/a-philosophy-of-software-design/clean-code.md:6,12-14`。无冲突。

10. 矩阵把 DDD–PoEAA 与 IDDD–PoEAA 标为冲突。DDD–PoEAA 对比文件要求不要把二者作为同一任务的平等有效指导。置信：事实。来源：`agent-rules-books/docs/COMPATIBILITY.md:21-24`；`agent-rules-books/docs/compatibility/domain-driven-design/patterns-of-enterprise-application-architecture.md:6,12-14`。无冲突。

11. Release It! 与 DDIA 被标为互补。对比文件写明二者保护不同失败面：DDIA 管数据所有权、一致性、耐久、重放和派生数据；Release It! 管超时、重试、隔离、过载和诊断。置信：事实。来源：`agent-rules-books/docs/compatibility/designing-data-intensive-applications/release-it.md:6,12-14`。无冲突。

12. Working Effectively with Legacy Code 的 mini 要求：没有可信测试的区域先当遗留代码；编辑前写清要改变的行为和必须保留的行为；先做 characterization，再用最小 seam；行为改动、结构重构和清理分开。置信：事实。来源：`agent-rules-books/working-effectively-with-legacy-code/working-effectively-with-legacy-code.mini.md:13-20,31-38`。无冲突。

13. Release It! 的 mini 要求显式时限，只对安全操作做有界重试，并定义容量、隔离、降级和诊断。置信：事实。来源：`agent-rules-books/release-it/release-it.mini.md:16-19,24,31-32`。无冲突。

14. DDIA 的 mini 要求显式写出 source of truth、一致性、耐久与可见时点、重复与重放、派生数据修复，以及超时或未知成功后的行为。置信：事实。来源：`agent-rules-books/designing-data-intensive-applications/designing-data-intensive-applications.mini.md:13-14,18-20,34-37`。无冲突。

15. APoSD 的 mini 用认知负担和变更扩散衡量复杂度，拒绝只增加名字的薄封装，并要求没有证据不加泛化或框架。Refactoring 的 mini 要求小步、行为与结构分离，并在阻塞 smell 消失后停止。Refactoring.Guru 的 mini 要求先命名 smell，再用最小治疗，验证后停止。置信：事实。来源：`agent-rules-books/a-philosophy-of-software-design/a-philosophy-of-software-design.mini.md:13-15,25,29-30`；`agent-rules-books/refactoring/refactoring.mini.md:13-17,26`；`agent-rules-books/refactoring-guru/refactoring-guru.mini.md:13-18,53`。无冲突。

16. DDD 的 mini 要求一个限界上下文一套统一语言，业务规则留在领域模型，聚合只承载需要立即一致的边界。IDDD 的 mini 还要求跨上下文先标明关系和翻译责任，跨聚合默认用身份引用。置信：事实。来源：`agent-rules-books/domain-driven-design/domain-driven-design.mini.md:14-17,21`；`agent-rules-books/implementing-domain-driven-design/implementing-domain-driven-design.mini.md:13-19`。无冲突。

17. PoEAA 的 mini 要求先写明责任归属，再选分层、事务、仓储或映射；只转发的层不合格。置信：事实。来源：`agent-rules-books/patterns-of-enterprise-application-architecture/patterns-of-enterprise-application-architecture.mini.md:13-15,34-35`。无冲突。

18. The Pragmatic Programmer 的 mini 要求每个系统知识有一个权威表示，并保持职责不重叠、契约可见。置信：事实。来源：`agent-rules-books/the-pragmatic-programmer/the-pragmatic-programmer.mini.md:16-17,25`。无冲突。

19. 本仓库当前断言是：`spec` 先枚举失败入口，并在相关边界读取失败契约；`design` 只记录悄悄变化会受损的决策，模式决策先读责任参考，失败边界另读失败契约；`tdd` 先写失败测试，遗留条件另读安全回路；`debug` 没有复现不诊断；`domains` 维护一套统一语言，无真实歧义不扩张术语表；`code-review` 要求复杂度有认知负担或变更扩散证据，按已命名 smell 做最小治疗并在验证后停止，不以行数判定；`skill-creator` 规定没有真实返工或测试失败不改 skill 正文。置信：事实。来源：`skills/workflow/spec/SKILL.md:59-60`；`skills/workflow/design/SKILL.md:17,42-43`；`skills/coding/tdd/SKILL.md:15-17,28`；`skills/coding/debug/SKILL.md:13`；`skills/workflow/domains/SKILL.md:10,16`；`skills/coding/code-review/references/review-dimensions.md:16-17`；`skills/skill/skill-creator/SKILL.md:99`。无冲突。

20. 该规则集不适合作为本仓库全局规则，也不应按书名安装为 14 个自动触发 skill。全部常驻或按书名自动触发，会与 spec、design、tdd、debug、domains、code-review 的现有触发面重叠，并增加上下文负载。置信：推断。来源：`agent-rules-books/docs/CRITICISM.md:19-27`；`agent-rules-books/docs/COMPATIBILITY.md:16-24`；`skills/workflow/spec/SKILL.md:59-60`；`skills/workflow/design/SKILL.md:17,42-43`；`skills/coding/tdd/SKILL.md:15-17,28`；`skills/coding/debug/SKILL.md:13`；`skills/workflow/domains/SKILL.md:10,16`；`skills/coding/code-review/references/review-dimensions.md:16-17`。无冲突。

21. 源规则整理不能单独充当本仓库 skill 正文的证据。源仓库没有任务结果数据；本仓库改 skill 正文需要一次真实返工或一条测试失败。置信：推断。来源：`agent-rules-books/docs/CRITICISM.md:15-17`；`skills/skill/skill-creator/SKILL.md:99`。无冲突。

22. 可从 Release It! 与 DDIA 抽出的失败契约字段是边界、source of truth、可见性、超时、重试资格、重复/重放、容量、恢复和诊断。二者不能压成同一份可靠性清单。置信：推断。来源：`agent-rules-books/release-it/release-it.mini.md:16-19,24,31-32`；`agent-rules-books/designing-data-intensive-applications/designing-data-intensive-applications.mini.md:13-14,18-20,34-37`；`agent-rules-books/docs/compatibility/designing-data-intensive-applications/release-it.md:12-14`。无冲突。指针：`skills/workflow/spec/references/failure-contract.md`

23. 遗留变更可移植的是 characterization、change point、最小 seam，以及行为改动与清理分离。这不构成新 skill：`tdd` 已拥有测试先行，`debug` 已拥有复现。置信：推断。来源：`agent-rules-books/working-effectively-with-legacy-code/working-effectively-with-legacy-code.mini.md:13-20`；`skills/coding/tdd/SKILL.md:15-17,28`；`skills/coding/debug/SKILL.md:13`。无冲突。指针：`skills/coding/tdd/references/legacy-change-safety.md`

24. 复杂度判断使用认知负担或变更扩散证据，按已命名 smell 做最小治疗，验证后停止，不用固定行数。不能把 Clean Code 与 APoSD 合成“函数越小越好”。置信：推断。来源：`agent-rules-books/a-philosophy-of-software-design/a-philosophy-of-software-design.mini.md:13-15,25`；`agent-rules-books/refactoring/refactoring.mini.md:17,26`；`agent-rules-books/refactoring-guru/refactoring-guru.mini.md:14-18,53`；`agent-rules-books/docs/compatibility/a-philosophy-of-software-design/clean-code.md:12-14`；`skills/coding/code-review/references/review-dimensions.md:16-17`。无冲突。指针：`skills/coding/code-review/references/review-dimensions.md`

25. 模式选择先写责任、不变量和边界，再选分层、事务、仓储或映射。置信：推断。来源：`agent-rules-books/patterns-of-enterprise-application-architecture/patterns-of-enterprise-application-architecture.mini.md:13-15`；`skills/workflow/design/SKILL.md:42`。无冲突。指针：`skills/workflow/design/references/responsibility-before-pattern.md`

26. 跨上下文的同一个词应先翻译；聚合只放必须立即一致的不变量。没有真实歧义时，不把 Aggregate、Value Object 等词预先写入术语表。置信：推断。来源：`agent-rules-books/domain-driven-design/domain-driven-design.mini.md:14-17,21`；`agent-rules-books/implementing-domain-driven-design/implementing-domain-driven-design.mini.md:16-19`；`skills/workflow/domains/SKILL.md:16`。无冲突。

27. 把 The Pragmatic Programmer 复制成新的通用 skill，会与本仓库已有分工形成第二解释。置信：推断。来源：`agent-rules-books/the-pragmatic-programmer/the-pragmatic-programmer.mini.md:16-17,25`；`skills/workflow/domains/SKILL.md:10`；`skills/workflow/design/SKILL.md:17`；`skills/coding/debug/SKILL.md:13`。无冲突。

## 冲突

无。

## 未决

- 这些 mini 规则在本仓库真实任务中是否减少缺陷、返工或评审时间：未知。
- 未在本文结论中引用的 mini 是否还有值得引入的决策规则：已由 [再评估](agent-rules-books-再评估.md) 关闭。结论是没有第五条现在值得写入 skill 的机制。
- 14 个 `SKILL.md` 是否都只指向 mini：已关闭。再评估核对各书 `SKILL.md:11`，全部先读 mini。
- 各书 `traceability.md` 是否都满足 `PROCESS.md:92-114`：未在本文重走；再评估只抽查了 intentionally lost，未逐节核对。
- `full` 是否含有 traceability 未记载的决策规则：未知。再评估不把它当作引入理由。
- 上次 fetch 之后 `origin/main` 是否有新提交：未知。本地 `main` 与已记录的 `origin/main` 无 ahead/behind；本次未 fetch。

## 来源

`agent-rules-books/` = `/Users/chess/workspace/opensource/opensource-skills/agent-rules-books` @ `893a88a6fce3a80c565bf39ac65021b43a8b2990`。其余路径相对于本仓库根 @ `7d17167`。

- `agent-rules-books/README.md:28,34-38,78-93,195-199,203-208,241`
- `agent-rules-books/LICENSE:1`
- `agent-rules-books/_rule-workbench/PROCESS.md:3-9,62-90,92-114`
- `agent-rules-books/docs/COMPATIBILITY.md:3-10,16-24,50-62`
- `agent-rules-books/docs/CRITICISM.md:7,15-17,19-27,75-77,105-107`
- `agent-rules-books/docs/compatibility/a-philosophy-of-software-design/clean-code.md:6,12-14`
- `agent-rules-books/docs/compatibility/domain-driven-design/patterns-of-enterprise-application-architecture.md:6,12-14`
- `agent-rules-books/docs/compatibility/designing-data-intensive-applications/release-it.md:6,12-14`
- `agent-rules-books/release-it/SKILL.md:7-11`
- `agent-rules-books/release-it/release-it.mini.md:16-19,24,31-32`
- `agent-rules-books/designing-data-intensive-applications/designing-data-intensive-applications.mini.md:13-14,18-20,34-37`
- `agent-rules-books/`（调查日目录清点）
- `agent-rules-books/docs/compatibility/`（调查日目录清点）
- `agent-rules-books/working-effectively-with-legacy-code/working-effectively-with-legacy-code.mini.md:13-20,31-38`
- `agent-rules-books/a-philosophy-of-software-design/a-philosophy-of-software-design.mini.md:13-15,25,29-30`
- `agent-rules-books/refactoring/refactoring.mini.md:13-17,26`
- `agent-rules-books/refactoring-guru/refactoring-guru.mini.md:13-18,53`
- `agent-rules-books/domain-driven-design/domain-driven-design.mini.md:14-17,21`
- `agent-rules-books/implementing-domain-driven-design/implementing-domain-driven-design.mini.md:13-19`
- `agent-rules-books/patterns-of-enterprise-application-architecture/patterns-of-enterprise-application-architecture.mini.md:13-15,34-35`
- `agent-rules-books/the-pragmatic-programmer/the-pragmatic-programmer.mini.md:16-17,25`
- `skills/workflow/spec/SKILL.md:59-60`
- `skills/workflow/design/SKILL.md:17,42-43`
- `skills/coding/tdd/SKILL.md:15-17,28`
- `skills/coding/debug/SKILL.md:13`
- `skills/workflow/domains/SKILL.md:10,16`
- `skills/skill/skill-creator/SKILL.md:99`
- `skills/coding/code-review/references/review-dimensions.md:16-17`
