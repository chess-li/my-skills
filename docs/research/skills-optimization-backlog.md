# skills 仓库优化清单

日期：2026-10-05

本文把当前仓库的优化项整理为可执行的优先级。它与 [agent-rules-books 融入评估](./agent-rules-books-融入评估.md) 配套使用。证据以 [`skill-证据日志.md`](../../skill-证据日志.md) 为单一入口。

## 使用规则

- **已有证据**：已有真实返工、测试失败或用户反馈。可以进入下一次实现排期，但改 skill 正文前仍须按 `skill-creator` 做新旧对比、回归和减法审查。
- **回归项**：正文已有修法。当前动作是补跑或检查，不再重复设计同一修法。
- **观察项**：只有候选机制或一次性信号。没有达到拉动条件时不改正文，不建新 skill。
- **明确不做**：会制造第二事实源、触发竞争或缺少独立场景。除非出现新的反证，不重新打开。

这份清单不把书名、模式名或书籍原文直接变成规则。`agent-rules-books` 是二手规则整理，且其兼容性判断没有任务实证。候选机制只有在本仓库出现对应返工后才可移植。

## 当前盘点

- 本仓库有 25 个 skill。
- 其中 15 个有 `tests/` 目录，10 个没有：`break-ui`、`design`、`frontend-api-doc`、`how`、`local-env`、`milestone`、`research`、`teach`、`wizard`、`writing`。
- 没有测试目录不等于缺陷。用户触发型 skill 可以等真实语料到场后建集；关键是要记录“为何尚未建集”和下一次拉动条件。
- 书籍源仓库有 14 组规则。它们与本仓库的 `spec`、`design`、`domains`、`tdd`、`debug`、`code-review`、`implement` 已有大量交集。

### 14 组书籍规则的处置

| 规则集 | 处置 | 原因或落点 |
| --- | --- | --- |
| A Philosophy of Software Design | 合并到 B-03 | 认知负担、深模块和薄 wrapper 已落入 `code-review` 条件性评审维度；不写成数字门槛 |
| Clean Architecture | 暂不移植 | 依赖方向和可替换边界只有在具体架构决策中有用；不能要求 CRUD 也套 ports/adapters |
| Clean Code | 合并到 B-03 | 与 APoSD、Refactoring 重叠；已合并到同一复杂度证据和停止条件，不把小函数或参数数量写成数字门槛 |
| Code Complete | 暂不新增条款 | 构造质量、输入校验、可读性和验证已分散在 `spec`、`tdd`、`code-review`；缺少独立触发面 |
| Designing Data-Intensive Applications | 合并到 B-01 候选 | source of truth、可见性、持久化、重放和派生数据修复属于失败契约 |
| Domain-Driven Design | 合并到 B-04 候选 | 与 `domains` 的统一语言和上下文边界相邻；只在真实模型冲突时移植 |
| Domain-Driven Design Distilled | 合并到 B-04 候选 | 提供“复杂领域才使用 DDD”的成本护栏，不能预建术语 |
| Implementing Domain-Driven Design | 合并到 B-04 候选 | 聚合立即一致边界、身份引用和跨上下文翻译；不得创建书名 skill |
| Patterns of Enterprise Application Architecture | 合并到 B-05 候选 | 先责任和事务边界，再选模式；防止模式先行和分层转发 |
| Refactoring | 合并到 B-03 候选 | 行为保持、小步验证、准备性重构和停止条件 |
| Refactoring.Guru | 合并到 B-03 候选 | smell 到最小治疗的操作化版本；与 Refactoring 去重，不建立第二套清单 |
| Release It! | 合并到 B-01 候选 | 超时、受限重试、隔离、容量、降级和诊断 |
| The Pragmatic Programmer | 维持分散现状 | 单一事实源、正交、反馈和可逆性已经是仓库治理原则；新增通用 skill 会制造第二解释 |
| Working Effectively with Legacy Code | 合并到 B-02 | characterization、最小 seam 和行为/清理分离已落入 `tdd` 条件性 reference；效果待真实任务验证 |

## 第一优先级：清理已有证据债

这些项已有返工或测试证据。它们比新增书籍规则更值得先做。

| 编号 | 优化项 | 主要落点 | 已知缺口 | 下一步 | 完成信号 |
| --- | --- | --- | --- | --- | --- |
| E-01 | 建立测试资产台账 | `skills/*/tests/`、`skill-证据日志.md` | 测试目录、冒烟集、触发集、结果区和欠账分散；部分 skill 尚无真实语料 | 为 25 个 skill 记录触发类型、测试类型、最近结果、未跑原因、下一拉动条件；不为填表造语料 | 每个 skill 都有明确状态；已有测试的结果区不再空置；编号不重复 |
| E-02 | 清偿已有触发回归欠账 | `spec`、`design`、`implement`、`issues`、`bootstrap` | spec/design 的干净会话补跑、implement 续写与异措辞、issues frontier/wontfix、bootstrap 结果仍有尾项 | 先跑已有真实用例，再把失败归因到 description、正文路由或测试环境 | 每个失败用例有“触发/未触发/竞争者/修法”记录；不把干净会话结果冒充真实使用 |
| E-03 | 补入口动作锚点 | `implement`、`interview` | “审阅进度后安排任务”没有稳定触发 implement；多决策现场一次发出三问；阻塞项没有优先处理 | 用下一次真实进度审阅或多决策会话验证；复发后只补最小动作锚点和阻塞优先步骤 | 进度审阅先列阻塞与未决；多决策按一次一问；任务安排不会静默跳过 implement |
| E-04 | 收紧 issue 归档与镜像闭环 | `issues`、`implement` | archive 内容物、拆分边界、`blockedBy` 清空、guide 汇总回写和归档后清点没有共同入口 | 把归档执行、依赖消解、汇总回写分别锚到现有步骤；不新增汇总视图 | 真实归档后只剩允许的 issue/历史文件；frontmatter、guide 和 frontier 一致；过期待办同步消失 |
| E-05 | 统一完成语义 | `DOMAINS.md`、`implement`、`code-review` | “无未处理发现”既可读成零发现，也可读成无 P4 及以上；P5 是否阻断没有统一表述 | 在下一次出现 P5 分歧前保留观察；若争议复发，再由一个文档定义完成门槛并让其他文档引用 | 归档者、评审者和执行者对同一状态给出相同结论 |
| E-06 | 保留代码事实核验出口 | `spec`、`design`、`issues` | 写者自查可能漏掉代码现状；一次文档漏覆盖已由 issues 两级评审补救，但 spec/design 盲区仍在 | 真实设计或 spec 因错误行号、字段或装配事实返工时，增加独立核验，而不是复制全文评审 | 关键断言有 `file:line` 或可运行查询；代码差距有 issue 覆盖；无法核验的值明确标注 |
| E-07 | 清偿研究结论的验证标记 | `docs/research/`、`design` | subagent 或社区调研转述的具体值可能没有来源，却被写成已确认事实 | 以后落盘时区分“已核对”“约定初值”“未复核”；复发前不新增统一模板 | 读者可区分外部事实、项目约定和待核查建议 |
| E-08 | 补齐缺测试 skill 的冷启动记录 | `design`、`how`、`research`、`milestone`、`frontend-api-doc`、`local-env`、`break-ui`、`teach`、`wizard`、`writing` | 无测试目录的原因和拉动条件不在同一处，容易被误判为漏项 | 在 E-01 台账中登记；真实语料到场后按 skill 类型建最小冒烟或触发集 | 不再用拟真案例填空；每个缺测试 skill 都有下一次可操作的拉动条件 |

## 第二优先级：把已出现的结构风险变成小修法

这些项已有信号，但部分修法需要再次确认触发面。它们应按真实事件逐项处理，不做一次性大重写。

| 编号 | 优化项 | 主要落点 | 触发条件 | 候选修法 | 验收信号 |
| --- | --- | --- | --- | --- | --- |
| R-01 | 能力方向先裁定 | `spec`、`interview`、`debug` | 第二次出现“spec 已落盘的能力方向后来被用户删除或改成另一种产品面” | 在落 spec 断言前识别互斥产品方向；必要时转 interview，不能由 debug 静默扩展 | 用户在实现前选定方向；错误方向不再积累到验证期 |
| R-02 | 归档清点责任人 | `issues`、`implement` | archive 再次因过期 issue 误导创建前检索而腐化 | 指定归档步骤发起同上下文 archive 清点，并写结果 | 清点有执行记录；没有重复修复已关闭事项 |
| R-03 | 汇总待办回写 | `implement` | 第二次因过期汇总待办造成错误决策 | 归档步骤读取本任务涉及的汇总，消化或回写待办 | 归档后的汇总与代码、issue 状态一致 |
| R-04 | 基线分支准入保护 | Git hook 或 CI | 正文已有基线准入要求，但再次发生直接在基线分支提交实现 | 先验证复发；复发后再讨论 hook 或 CI，不提前增加不可逆门禁 | 违规提交在提交前被明确拒绝，文档提交仍可通过 |
| R-05 | 安装副本漂移回归 | `install.sh`、发布流程 | 仓库外再次出现孤儿 skill 或安装副本与仓库不一致 | 先保持仓库为唯一信源；第二次孤儿再讨论 prune/白名单或同步校验 | 安装结果可由仓库重建；孤儿被发现并有处理记录 |
| R-06 | 观察名单生命周期 | `skill-证据日志.md`、`skill-creator` | 名单膨胀到无法检索，或同一观察项长期没有拉动条件 | 定义进入、复查、升格、合并和移出的最小状态，不把理论候选直接改正文 | 每项都有状态和下次检查点；已证伪项可追溯移出 |
| R-07 | 触发回归覆盖长会话和模型变化 | `skill-creator` 测试指南、harness | 干净短会话全绿，但真实长会话出现上下文竞争或模型变化退化 | 先记录事件；复发后增加长会话样本和模型版本标记，不假设差值恒定 | 触发结果包含会话长度、竞争 skill、模型和证据路径 |
| R-08 | 统一测试环境保真约定 | `skill-creator/references/testing-guide.md` | 第二个 skill 需要项目 `AGENTS.md` 竞争模板、改前源码桩或历史版本才能复现触发 | 把 spec 已验证的环境要求提炼成共享参考；只抽共性，不复制项目细节 | 新 skill 测试能复现真实竞争；没有因改后源码桩制造假失败 |
| R-09 | 统一“单一写者/单一事实源” | `DOMAINS.md`、`design-principles.md` | 再出现同一资产由两个写者或两个文件同时定义 | 先确认第四起同类事故，再提炼为跨文档原则；已有个案规则继续单独保留 | 术语、spec、原型、安装副本和汇总视图各有唯一写者 |

## 第三优先级：书籍机制落地状态

这些是本次 Luna 探索得到的最佳候选。P0–P2 已按用户指令落成条件性 reference；后续仍要用真实任务验证效果，不把 reference 误读为无条件规则。

| 编号 | 候选机制 | 来源规则集 | 建议消费者 | 最小可移植内容 | 拉动条件 |
| --- | --- | --- | --- | --- | --- |
| B-01 | 失败契约 | DDIA、Release It! | `spec`、`design`、必要时 `code-review` | 已落 `skills/spec/references/failure-contract.md`；边界、source of truth、可见性、超时、重试资格、重复/重放、容量、恢复、诊断 | 真实任务因未知成功、重复副作用、无界等待/重试或派生数据无法修复返工；当前待验证效果 |
| B-02 | 遗留变更安全回路 | Working Effectively with Legacy Code | `tdd` | 已落 `skills/tdd/references/legacy-change-safety.md`；先声明保留行为，做 characterization，找最小 seam，再改行为；结构清理与行为改动分开 | 行为不明或无可信测试时直接修改再次造成返工，或“不可测”未评估 seam；当前待验证触发竞争 |
| B-03 | 复杂度与停止条件 | A Philosophy of Software Design、Refactoring、Refactoring.Guru | `code-review` reference | 已落 `skills/code-review/references/review-dimensions.md`；命名 smell/认知负担，采用最小治疗，验证后停止；不使用固定行数 | 评审再次漏掉薄 wrapper、投机泛化、清理越界，或误用数字规则；当前待验证误报/漏报 |
| B-04 | 上下文翻译与聚合边界 | DDD、DDD Distilled、IDDD | `domains`、`design` | 跨 context 同词先翻译；只把必须立即一致的不变量放入边界；跨边界保留身份引用 | 共享模型、Aggregate 边界或跨上下文事务造成真实设计返工 |
| B-05 | 责任先于模式 | PoEAA | `design` reference | 已落 `skills/design/references/responsibility-before-pattern.md`；先写责任、不变量和边界，再选分层、事务、仓储或映射模式；简单流程不套仪式 | 真实设计因先选模式、后补责任而返工；当前待验证设计效果 |
| B-06 | 事实唯一拥有者 | The Pragmatic Programmer | 已分散在 `DOMAINS.md`、`spec`、`design`、`debug`、`skill-creator` | 不新增通用 skill；只在 R-09 复发后统一术语或索引 | 再出现双写者事故并且现有分散规则无法定位责任 |

### 书籍机制的边界

- 不把 14 个书名变成 14 个 skill。
- 不把 `mini/full/nano` 复制到本仓库的根 `AGENTS.md` 或每个 skill 的常驻正文。
- 不把源仓库的兼容性矩阵当作本仓库的运行时决策表。源仓库标注了重叠和冲突，尤其是 Clean Code 与 APoSD、DDD/IDDD 与 PoEAA、Release It! 与 DDIA 的关注面。
- 不把“函数越小越好”、固定行数、固定模式或统一可靠性数字写成硬规则。
- 不把书籍整理当作原书证据。采用前需要重新核对来源、上下文和本仓库真实失败。

## 暂不执行的工具和新 skill 候选

以下候选有讨论价值，但现在没有足够证据。它们保留观察项，不进入正文。

| 候选 | 暂不执行原因 | 重新打开条件 |
| --- | --- | --- |
| 脚本化完成闸门 | 尚无验收方重跑仍无法拦截伪造完成证据的案例 | 首次伪造证据漏过人工/skill 闸门 |
| 基线分支 pre-commit hook | 当前只有一次违规证据，且 hook 会改变所有项目的提交行为 | 正文要求再次被绕过 |
| 会话启动注入或 bootstrap hook | 依赖 harness，且与现有用户级指针和 skill 路由重叠 | spec 与 tdd 同时未加载并造成写码翻车 |
| Ruling 裁决账本 | 与 interview 的“列候选并停下问人”方向相冲突，适用面只在无人值守长任务 | 等待确认导致停摆，或静默裁决造成返工 |
| YAML/CLI 工作流引擎 | 当前问题主要是语义路由和证据缺口，不是格式校验重复失败 | 同一格式错误多次阻断交付，且工具边界明确 |
| interview 澄清总数上限 | 现在只有社区候选，没有本仓库滥问反馈 | 用户报告追问过多，或访谈明显拖慢执行 |
| 独立 BDD、讨论、书籍 skill | 与现有 `spec`/`tdd`/`design` 触发面重叠，没有独立消费者 | 出现独立触发场景且现有 skill 无法承载 |
| OpenSpec 增量 spec | 与本仓库“全文维护、断言持续为真”冲突 | 并行任务反复因同一 spec 合并冲突返工 |

## 建议执行顺序

1. 先做 E-01，建立 25 个 skill 的状态台账。它只记录事实，不改正文。
2. 按 E-02 至 E-04 清偿已有触发、入口和归档闭环欠账。每次只处理一个具体缺口。
3. 下一批真实任务中观察 E-05 至 E-09 的拉动条件。出现第二次同类事件时再做最小修法。
4. B-01、B-02、B-03、B-05 已按用户指令翻译到已有消费者；后续按真实任务验证效果。B-04 和 B-06 仍只保留观察项，出现拉动条件后再决定是否吸收。
5. 完成一轮真实使用后再盘点冻结状态。没有稳定使用证据时，不用“已整理”代替“已验证”。

## 本轮结论

当前最值得做的是减少仓库自身的路由、测试记录、归档状态和事实核验缺口。书籍规则的最佳用法是提供候选机制和反例，等待本仓库真实任务证明缺口后再吸收。这样可以增加可验证的工程约束，同时避免新增 14 套重叠规则和常驻上下文负担。
