# agent-rules-books 融入评估

日期：2026-10-05

源仓库根目录：`/Users/chess/workspace/opensource/opensource-skills/agent-rules-books`。下文未带绝对前缀的源路径均相对于该目录。

全仓优化项见同目录的 [skills 仓库优化清单](./skills-optimization-backlog.md)。

## 结论

`agent-rules-books` 适合作为条件化参考库和规则候选来源，不适合作为本仓库的全局规则集合。

本仓库已有 `spec`、`design`、`domains`、`tdd`、`debug`、`code-review` 和 `implement` 的生命周期分工。源仓库的 14 组书籍规则与这些 skill 有大量重叠。直接复制 `mini` 文件，或把 14 组规则全部安装为自动触发 skill，会增加上下文负载和触发竞争。

原始评估按三层处理候选机制。截至 2026-10-05，P0–P2 已按下文“落地补记”完成条件性落点：

1. 保留本次结果为研究记录，继续把未满足证据门槛的候选留在 `skill-证据日志.md` 的观察名单。
2. 已有真实返工或测试失败证据的机制，翻译到已有 skill 的条件性参考文件或正文；本次已完成 P1/P2 指定落点。
3. 只有出现独立触发场景时，才考虑新增 skill。不要按书名新增 skill。

## 来源事实

| 事实 | 证据 |
| --- | --- |
| 本地检出包含 14 个书籍规则集，每组有 full、mini、nano 和 `SKILL.md` 入口 | 当前 `main`，`git describe` 为 `v0.6-3-g893a88a`；`/Users/chess/workspace/opensource/opensource-skills/agent-rules-books/README.md:34-38,78-93`；目录清单显示 14 个书籍目录 |
| `SKILL.md` 主要负责触发和指向 mini/full；实际规则在 mini/full | 例如 `release-it/SKILL.md:1-11` |
| 压缩目标是“决策等价”，不是句子等价；mini 保留会改变决策的规则，nano 只保留紧凑的常驻纠偏 | `_rule-workbench/PROCESS.md:3-9,62-90` |
| 每条 mini/nano 规则需要回溯到 full 的章节和行号，且要记录合并或有意丢弃 | `_rule-workbench/PROCESS.md:92-114`；各书的 `_rule-workbench/*/traceability.md` |
| 兼容性矩阵是定性判断，源仓库自己标注还没有任务实证 | `docs/COMPATIBILITY.md:50-62`；`docs/CRITICISM.md:15-17,75-77,105-107` |
| `docs/compatibility/` 有 91 个书籍对比文件，矩阵统计为 78 个互补、2 个冲突、11 个重叠 | `docs/COMPATIBILITY.md:3-10,50-62`；本次只读清点 |
| 源仓库说明规则是受书籍启发的原创实践指令，不是作者或出版社的官方材料，也不是书籍替代品 | `README.md:203-208` |
| 源仓库使用 MIT 许可证 | `README.md:27-30,241`；`LICENSE` |
| 书籍规则的早期实验是定性信号，不是基准；mini 与只提书名的分支在一次重构实验中得到不同评分 | `README.md:193-199` |
| 本次完整覆盖公开的 `SKILL.md`、mini、nano；traceability 和 full 按候选机制回查，未逐行验证所有 full 章节 | 本次 Luna 只读审查记录；未验证部分列在本文“未决项” |

## 规则机制和本仓库落点

### 1. 遗留代码先取得控制权

源仓库的 `Working Effectively with Legacy Code` 规则整理要求：没有可信测试的区域先当作遗留代码；编辑前写清行为变化和必须保留的行为；先做 characterization、找最小 seam，再改行为；行为改动、结构重构和清理分开（`working-effectively-with-legacy-code/working-effectively-with-legacy-code.mini.md:13-27`）。触发条件包括不确定行为、构造副作用、全局状态和框架回调（同文件 `:31-38`）。

本仓库的 `tdd` 已覆盖测试先行、真实生产路径、装配验证和重构测试断言迁回（`skills/tdd/SKILL.md:15-34`）。`debug` 已覆盖复现、根因解释和分层修复（`skills/debug/SKILL.md:10-15`）。因此不新建“遗留代码”总 skill。本次按遗留构造、装配和隔离缝返工证据，将 characterization、change point 和最小 seam 机制落到 `tdd` 的条件性 reference；`debug` 仍拥有复现与根因，生产代码修复继续回到 tdd。效果待后续真实任务验证。

### 2. 生产失败契约

源仓库的 `Release It!` 规则整理要求显式超时、受限且有退避的重试、容量和队列边界、隔离、降级、可观测性、可恢复的部署与迁移（`release-it/release-it.mini.md:13-27,31-37`）。

源仓库的 `Designing Data-Intensive Applications` 规则整理要求显式记录 source of truth、一致性、持久化与可见性时点、重复和重放语义、派生数据修复、schema 演进和未知成功状态（`designing-data-intensive-applications/designing-data-intensive-applications.mini.md:13-30,34-42`）。

本仓库的 `spec` 已要求枚举外部调用、异步、超时和中断的失败入口（`skills/spec/SKILL.md:56-60`），`design` 已要求记录技术决策及取舍（`skills/design/SKILL.md:37-54`）。本次没有把两个书籍 mini 全文并入这些 skill，而是建立条件性“失败契约”参考表，供 `spec` 写用户可观察验收标准、`design` 写 how 决策、`code-review` 按边界核对实现。

候选表的最小字段应是：边界、超时、重试资格、重复/重放、容量、可见性、恢复或修复、诊断信号。它不能替代 spec 的行为断言，也不能在没有系统证据时规定具体数值。

### 3. 复杂度和抽象边界

源仓库的 `A Philosophy of Software Design` 规则整理提供的可移植机制是：以认知负担和变更扩散作为复杂度信号；优先深模块和语义接口；拒绝只增加名字的薄 wrapper；让拥有细节的模块吸收复杂度；没有证据不加入泛化、框架或优化（`a-philosophy-of-software-design/a-philosophy-of-software-design.mini.md:13-25,29-38`）。

`Refactoring` 和 `Refactoring.Guru` 将其落成小步、可验证、按 smell 选择最小处理、行为改动与结构改动分离、到达停止条件后停止（`refactoring/refactoring.mini.md:13-26,30-39`；`refactoring-guru/refactoring-guru.mini.md:13-18,30-36,53-64`）。

本仓库已有 `tdd` 的“最小实现不得添加无消费者抽象”（`skills/tdd/SKILL.md:17-20`）、`design` 的“只记录悄悄变化会造成损失的决策”（`skills/design/SKILL.md:12-19,49-54`），以及 `skill-creator` 的删减和证据门禁（`skills/skill-creator/SKILL.md:95-123,149-154`）。这些机制已经覆盖大部分内容。本次根据过度设计、薄封装和清理范围返工证据，在 `code-review` 维度增加了复杂度证据、最小治疗和停止条件；效果待后续真实评审验证。

### 4. 领域模型和上下文边界

源仓库的 DDD 规则整理强调一个限界上下文内使用一套统一语言，业务规则留在领域模型，跨上下文交互必须有关系和翻译责任，聚合只承载需要立即一致的边界（`domain-driven-design/domain-driven-design.mini.md:13-27,31-39`；`implementing-domain-driven-design/implementing-domain-driven-design.mini.md:13-31,35-44`）。

本仓库的 `domains` 已直接覆盖查术语、边界场景和代码事实交叉核对（`skills/domains/SKILL.md:20-47`），并规定没有真实歧义信号不扩张术语表（同文件 `:12-16,49-65`）。DDD 规则在本仓库的最佳融入方式是作为现有 domains 的来源对照，不新增 DDD skill，也不把 Aggregate、Value Object 等词预先加入 `DOMAINS.md`。没有项目真实概念和消费者时，新增术语会违反 domains 的消费者闭环。

### 5. 模式选择，而不是模式清单

源仓库的 `Patterns of Enterprise Application Architecture` 规则整理要求先明确责任归属，再选择分层、事务、仓储、映射和集成模式；每层必须减少耦合或澄清责任，拒绝只转发的分层（`patterns-of-enterprise-application-architecture/patterns-of-enterprise-application-architecture.mini.md:13-30,34-43`）。

这与 `design` 的决策归属和取舍记录相容，但不适合加入模式名清单。本次根据设计选项经调研后重写的证据，已在 `design` 增加“先写责任和约束，再选模式”的条件性参考；效果待后续真实设计任务验证。

### 6. 一致性和可维护性的一般原则

源仓库的 `The Pragmatic Programmer` 规则整理强调每个事实只有一个权威拥有者、保持正交、让假设和契约可见、自动化重复工作、从复现事实调试（`the-pragmatic-programmer/the-pragmatic-programmer.mini.md:13-24`）。这些原则在本仓库已经分散落在 `DOMAINS.md`、spec/design/issue 单一信源、`debug` 和 `skill-creator`。复制为新的通用 skill 会制造第二套解释，不建议移植。

## 冲突和风险

1. `Clean Code` 的小函数压力与 APoSD 的深模块压力可能在同一方法上竞争。源仓库把该对标为 overlap，而不是无条件同时加载（`docs/COMPATIBILITY.md:16-19`）。本仓库不应把二者合成“函数越小越好”。
2. DDD/IDDD 与 PoEAA 对模型、事务脚本和数据访问模式的优先级不同。源仓库将 DDD–PoEAA、IDDD–PoEAA 标为 conflicting（`docs/COMPATIBILITY.md:21-24`）。模式参考只能在具体上下文和约束下读取。
3. Release It! 与 DDIA 虽互补，但一个偏运行时失败和容量，一个偏数据语义、一致性和演进。把两者压成“可靠性清单”会丢失 source of truth、unknown success 和重放语义。
4. 源仓库自己承认还缺少事故和任务结果驱动的验证（`docs/CRITICISM.md:7,15-17`）。书籍规则可作为候选机制来源，不能作为本仓库 skill 正文的证据。

## 建议的落地顺序

| 优先级 | 动作 | 进入条件 | 目标落点 |
| --- | --- | --- | --- |
| P0 | 保留本评估和来源路径；候选只进观察名单 | 已完成；仍不把候选升级为全局规则 | 本文件、`skill-证据日志.md` |
| P1 | 建立“失败契约”条件性 reference | 已有真实失败边界证据，且本次按条件性 reference 落地；效果待后续任务验证 | `skills/spec/references/failure-contract.md`；由 `spec`、`design`、`code-review` 分工读取 |
| P1 | 补“遗留变更安全回路”条件性 reference | 已有遗留构造、装配和隔离缝返工证据；本次落在 `tdd`，效果待后续任务验证 | `skills/tdd/references/legacy-change-safety.md`；不新建总 skill |
| P2 | 补“复杂度/抽象停止条件”评审维度 | 已有过度设计、薄封装和清理范围返工证据；已加入评审维度，效果待后续评审验证 | `skills/code-review/references/review-dimensions.md` |
| P2 | 补“责任先于模式”设计检查 | 已有模式选项经调研后重写的设计证据；已落条件性 reference，效果待后续设计任务验证 | `skills/design/references/responsibility-before-pattern.md` |
| 不做 | 复制 14 组 mini/full/nano；创建按书名的 14 个 skill；把书籍规则放入根 AGENTS.md；导入源仓库兼容矩阵作为运行时策略 | 无独立触发场景或会形成第二事实源 | 保持不动 |

每次 P1/P2 改动都必须先写目标 skill 的具体缺口，引用 `skill-证据日志.md` 的返工或测试失败，再按 skill-creator 的移植纪律翻译机制、补新旧对比和触发回归。没有证据时，只保留观察项。

## P0–P2 落地补记（2026-10-05）

用户要求将本评估中的 P0–P2 全部落地。本次按已有返工证据和用户明确授权完成以下落点：

- P0：研究报告、源仓库路径、14 组规则处置表和候选观察项已保留；新增内容仍以条件性 reference 为主，不把书籍规则放入根 AGENTS.md，也不创建书名 skill。
- P1 失败契约：以 skills/spec/references/failure-contract.md 为单一参考。spec、design 和 code-review 分别读取同一文件，分别拥有行为、技术边界和实现核验。触发条件是外部调用、异步、超时、重试、复制/派生数据、迁移、容量或未知成功。
- P1 遗留变更安全回路：以 skills/tdd/references/legacy-change-safety.md 为单一消费者。它补 characterization、change point、最小 seam、隔离缝评估和行为/清理分离，不新建遗留代码 skill，也不替换 debug 或 TDD 主流程。
- P2 复杂度和停止条件：skills/code-review/references/review-dimensions.md 现在要求复杂度有认知负担或变更扩散证据，按已命名 smell 采用最小治疗并在验证后停止，不使用固定行数。
- P2 责任先于模式：以 skills/design/references/responsibility-before-pattern.md 为条件性参考。design 和 code-review 在模式决策时先核对责任、不变量、边界、耦合变化和当前消费者，再选择最轻方案。

本次同步补充 spec S3、tdd T10、code-review R16 和 design D01 真实语料用例。description 未改，因此没有重复运行触发测试；有效性仍待下一次真实任务按条件读取并产出可核查证据。

## 未决项

- 尚未在本仓库的真实任务中验证 source `mini` 规则能否减少缺陷、返工或评审时间。
- “失败契约”的消费者已定为 spec（行为）、design（技术边界）和 code-review（实现核验），但尚未验证条件性读取是否减少返工。
- 遗留变更 reference 已落在 tdd，debug 仍通过修复阶段路由到 tdd；尚未验证它是否与现有 tdd/debug 触发面竞争。
- 复杂度/停止条件与责任先于模式已落到 code-review/design；尚未在新的真实评审和设计任务中验证误报、漏报和读取成本。
- 本评估只使用源仓库本地检出内容，未核对上游最新提交，也未把书籍原文当作证据。
