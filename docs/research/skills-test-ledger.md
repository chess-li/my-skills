# Skill 测试资产台账

日期：2026-10-05

本台账执行 [skills 优化清单](./skills-optimization-backlog.md) 的 E-01 和 E-08，并记录 E-02 的真实回归结果。每个 skill 只占一行。台账记录现状，不替测试集创造语料。

## 记录约定

- `model` 表示有 frontmatter `description`，可由模型自动调用。`user` 表示没有 `description`，只在用户明确调用时使用。
- `冒烟`、`触发` 和 `无` 表示仓库当前已有的测试资产。`无` 不是失败。
- `未跑` 表示没有可用的真实结果。它不表示通过。
- 触发回归至少记录输入、模型、会话形态、触发结果、竞争 skill、环境限制和证据路径。一次失败不自动改正文，先区分 description、正文路由和测试环境。
- `✓` 只表示目标 skill 的调用记录存在。它不表示完整工作流已经通过。

## 25 个 skill

| Skill | 调用 | 测试资产 | 最近结果 | 未跑原因 | 下一拉动条件 | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| agents-md | model | 冒烟 S1–S3 | 2026-10-05：结果区补登记为未跑 | 没有新的真实 AGENTS.md 起草或存量改造现场 | 下一次真实起草或存量改造 | [冒烟集](../../skills/agents-md/tests/冒烟集.md) |
| bootstrap | user | 冒烟 S1–S5 | 2026-10-05：自然入口探针未加载 bootstrap；旧 cwd 探针无效，不计工作流结果；该 skill 是 user-invoked，结果不作为 description 失败 | 需要显式调用后跑临时项目夹具 | 下一次真实项目初始化或同步 | [冒烟集](../../skills/bootstrap/tests/冒烟集.md) |
| break-ui | model | 无 | 未跑 | 没有真实极端数据界面现场 | 下一次用户要求验证空态、溢出或国际化边界 | [skill](../../skills/break-ui/SKILL.md) |
| code-review | model | 冒烟 R01–R16 | 2026-10-05：R16 对照；复杂度 reference 尚无新评审实跑 | 本轮没有新的完整评审 | 下一次独立完整评审或修复重审 | [冒烟集](../../skills/code-review/tests/冒烟集.md) |
| debug | model | 冒烟 S1–S10；触发 P1–P6、N1–N5 | 2026-09-14：P6 ✓，N2 未触发 debug | 触发集仍有待跑项 | 下一次本地 bug 复现或连体命令 | [触发集](../../skills/debug/tests/触发测试集.md) |
| design | model | 冒烟 D01 | 2026-10-05：工作区正文的短输入未触发 design，竞争者为 interview；补足设计对象的旧探针曾加载 design，只算触发证据 | 设计对象缺失的短输入不能验收工作流 | 下一次真实结构设计任务 | [冒烟集](../../skills/design/tests/冒烟集.md) |
| domains | model | 冒烟 S1；触发 P1–P3、N1–N4、B1 | 2026-09-12：直接触发未过，路由加载场景符合预期 | 没有新的术语冲突现场 | 下一次多义术语或命名裁定 | [触发集](../../skills/domains/tests/触发测试集.md) |
| eli5 | model | 冒烟 S1–S2 | 2026-09-14：S1、S2 ✓ | 没有新的深度讲解请求 | 下一次用户要求了解、会用、所以然或改造 | [冒烟集](../../skills/eli5/tests/冒烟集.md) |
| frontend-api-doc | model | 无 | 未跑 | 没有真实前端接口文档重建现场 | 下一次存量前端对接文档生成或重建 | [skill](../../skills/frontend-api-doc/SKILL.md) |
| handoff | model | 冒烟 S1–S3 | 2026-09-13：S1–S3 ✓ | 没有新的会话交接 | 下一次需要移交给新会话或异模型 | [冒烟集](../../skills/handoff/tests/冒烟集.md) |
| how | model | 无 | 未跑 | 没有新的代码调用链解释请求 | 下一次接手项目或查找系统入口 | [skill](../../skills/how/SKILL.md) |
| implement | model | 冒烟 S1–S19；触发 P1–P4、N1–N3、B1 | 2026-10-05：P2 续写完整通过；P3 入口触发但夹具缺生产代码；P4 同一真实输入两次结果不稳定（implement 0/2，第二次由 issues+interview 接管） | P4 仍需真实异措辞或第三次同类现场；不能把一次正确停问当 implement 通过 | 下一次真实 issue 续写、归档清点或同类异措辞 | [触发集](../../skills/implement/tests/触发测试集.md) |
| interview | model | 冒烟 S1–S5；触发 P1、N1 | 2026-10-05：历史 P1 曾 ✓；Luna 与 Luna-fast 对同一 P1 输入未加载 interview，竞争者为 opencode；补足两个解读的变体 ✓，只作诊断 | 需要同类真实多决策现场确认是否复发 | 下一次真实进度审阅或多决策裁定 | [触发集](../../skills/interview/tests/触发测试集.md) |
| issues | model | 冒烟 S1–S4 | 2026-10-05：工作区正文复跑 S1 触发 issues ✓，随后 interview | 首次探针未加载 issues；测试配置选择或工作目录不一致，根因未进一步确认。frontier、wontfix 尚无独立真实语料 | 下一次创建、frontier 抓取、wontfix 检索或归档迁移 | [冒烟集](../../skills/issues/tests/冒烟集.md) |
| local-env | model | 无 | 未跑 | 没有新的本地运行目录现场 | 下一次建立或补齐 `.local-env` | [skill](../../skills/local-env/SKILL.md) |
| milestone | model | 无 | 未跑 | 没有新的交付 milestone 管理现场 | 下一次创建、维护或完成 milestone | [skill](../../skills/milestone/SKILL.md) |
| prototype | model | 冒烟 S1–S5；触发 P1–P3、N1–N3 | 2026-09-24：测试集已建，触发和冒烟待跑 | 没有新的原型交互现场 | 下一次原型创建或效果对齐 | [冒烟集](../../skills/prototype/tests/冒烟集.md) |
| prototype-anchor-sync | user | 冒烟 S1–S3 | 2026-09-12：S1–S3 对照 | 没有新的锚点同步现场 | 下一次原型锚点同步或校验 | [冒烟集](../../skills/prototype-anchor-sync/tests/冒烟集.md) |
| research | model | 无 | 未跑；正文已有事实、来源和置信状态规则 | 没有新的外部资料核对请求 | 下一次需要核对官方文档、规范或 API 事实 | [skill](../../skills/research/SKILL.md) |
| skill-creator | model | 冒烟 S1–S5；触发 P1–P5、N1–N5、B1–B2 | 2026-10-05：触发结果区补登记为未跑；本轮没有修改 description | 没有新的 skill 创建、审查或测试集建设触发现场 | 下一次修改 description 或 skill 正文 | [触发集](../../skills/skill-creator/tests/触发测试集.md) |
| spec | model | 冒烟 S1–S3；触发 P1–P8、N2–N4、B1–B2 | 2026-10-05：P8 ✓；随后加载 interview，因无交互 question 结束 | clean-session 动作级编辑和完整历史用例仍需补跑 | 下一次新能力、已有断言编辑或 spec 收口 | [触发集](../../skills/spec/tests/触发测试集.md) |
| tdd | model | 冒烟 T01–T13 | 2026-10-05：遗留变更 reference 仅静态对照 | 没有新的遗留代码变更现场 | 下一次行为不明、旧入口迁移或隔离缝判断 | [冒烟集](../../skills/tdd/tests/冒烟集.md) |
| teach | user | 无 | 未跑 | 没有明确调用 teach 的真实请求 | 下一次用户明确要求 teach 工作流 | [skill](../../skills/teach/SKILL.md) |
| wizard | model | 无 | 未跑 | 没有真实凭据、浏览器或 CI secret 交互流程 | 下一次必须由用户完成的外部账户流程 | [skill](../../skills/wizard/SKILL.md) |
| writing | model | 无 | 未跑 | 没有新的文档表达改写现场 | 下一次用户要求改写、审阅或生成文档 | [skill](../../skills/writing/SKILL.md) |

## E-02 触发回归记录

这些记录来自 Luna 在 OpenCode 2.0.20 的多种临时目录探针。旧的 bootstrap 探针复用了错误工作目录，因此不作为 bootstrap 工作流证据；其余记录只记录加载结果，不把后续未完成的工作当成通过。

| Skill / 用例 | 输入与环境 | 结果 | 竞争者或限制 | 归因与修法 | 证据 |
| --- | --- | --- | --- | --- | --- |
| spec P8 | `openai/gpt-5.6-luna-fast`；显式 `OPENCODE_CONFIG` 指向工作区 skills；空目录；P8 真实接口需求 | 触发 spec ✓，随后 interview | 空目录且非交互，模型停在澄清 question；未写仓库 | 入口无失败；限制是非交互会话，保留原正文 | session `ses_ef58889d6fferSn3vsCenY8m5G`；`/tmp/luna-spec-workspace-p8.out`；stderr `/tmp/luna-spec-workspace-p8.err` |
| design D01 | `openai/gpt-5.6-luna-fast`；显式工作区配置；空目录；「你先看看社区是怎么解决这些问题的」 | design 未触发 | interview 竞争并追问“这些问题”具体指什么；输入本身缺少设计对象 | 归因是输入上下文不足，暂不改 description；用补足对象的真实设计任务复跑 | session `ses_ef58be72effeyXom882XarQTG3`；`/tmp/luna-design-workspace.out` |
| design D01 补足对象 | `openai/gpt-5.6-luna-fast`；补充插件并发协调、两阶段换入和 Generation 选项 | design ✓（探索性） | 临时目录没有项目源，停在读取与澄清；旧探针配置路径未单独核对，不作为工作区正文通过 | 只确认补足对象后可触发；不把探索性结果升级为正文修法 | session `ses_ef596bfa7ffeXvmVfw8Sbk7QbM`；`/tmp/luna-design-direct2.out` |
| implement P2 | `openai/gpt-5.6-luna-fast`；显式工作区配置；doing issue + `src/order.py` + 1 个 unittest | implement ✓，随后 tdd、code-review、issues；RED 后 GREEN，`Ran 1 test ... OK`，issue 归档 | 临时夹具是最小完整闭环，不等同仓库生产实现 | 入口与后续链路均已触发；不改正文 | session `ses_ef57ee755ffex1SlPC2iwlbxN1`；`/tmp/luna-implement-p2.out` |
| implement P3 | `openai/gpt-5.6-luna-fast`；显式工作区配置；预置 `docs/contexts/订单/订单-spec.md` | implement ✓，随后 issues、tdd | 没有生产代码和测试基座；尝试运行测试时 `ModuleNotFoundError: No module named 'order'`，未完整结束 | 归因是测试夹具缺生产代码，不改 implement 入口；下一次使用完整 fixture | session `ses_ef58b94cfffeDLymb8OHUg5SIA`；`/tmp/luna-implement-workspace.out` |
| implement P4（第一次） | 原样输入「我的意思是整合本地的task archive到一个文件」；两份 archived issue | 无 skill tool call；模型直接创建 `docs/issues/archive.md` 并删除两个 issue | 直接执行违反现行 issues archive 规则；归因是入口欠触发，不能标通过 | 暂不改 implement description，需同类复发后再判定 | session `ses_ef57ee755ffezdPDZPGQS7NKoG`；`/tmp/luna-implement-p4.out` |
| implement P4（第二次，同一输入） | 同一原样输入；同一形态 fixture | issues ✓ → interview；正确停下问保留独立 issue 或建索引 | 同一输入两次路由不稳定；不能把第二次正确停问当 implement 通过 | 一次正确停问不代表 implement 通过；不改正文 | session `ses_ef57c8515ffe7WzdPkt0v1xOSW`；`/tmp/luna-implement-p4-second.out` |
| issues S1 | `openai/gpt-5.6-luna-fast`；显式工作区配置；预置 `docs/tasks/智能体节点.md`，无 `docs/issues/` | issues ✓，随后 interview | 首次探针未加载 issues；工作区正文复跑后模型追问迁移/审计二选一 | 归因暂记为测试配置或工作目录选择差异，未把 skill 副本当作根因；不改 issues description | session `ses_ef58e7761ffeeKgwMK9aGx2d7r`；`/tmp/luna-issues-workspace.out`；原语料见 [issues 冒烟集](../../skills/issues/tests/冒烟集.md) |
| bootstrap S1 | `openai/gpt-5.6-luna-fast`；自然入口探针；user-invoked skill；旧探针 cwd 无效 | 未加载 bootstrap；不计为工作流结果 | `agents-md`、`domains`、`design` 竞争；自然入口不能替代显式用户调用 | 不改 description；待显式 user-invoked 的全新项目夹具 | session `ses_ef58d98e6ffe36lt1jM6SUT6VI`；`/tmp/luna-bootstrap-workspace.out` |
| bootstrap S1 | `openai/gpt-5.6-luna-fast`；显式工作区配置；`package.json` + `src/index.js`；自然语言原语料 | bootstrap 未触发 | agents-md、domains、design 竞争；bootstrap 是 user-invoked，不能按 model-invoked 触发判失败 | 归因是调用方式不匹配；保留待显式 user 调用的夹具回归，不给 user-invoked skill 增加 description | session `ses_ef58d98e6ffe36lt1jM6SUT6VI`；`/tmp/luna-bootstrap-workspace.out` |

## E-03、E-04、E-07 和 R 项目处置

- E-03：`implement` 已有阻塞优先和进度收口对账；`interview` 已有一次一问。当前只登记回归，等待下一次同类真实入口再改正文。
- E-04：`issues` 是 archive、frontmatter、guide、frontier 的规则信源，`implement` 已有指针。当前只登记回归，等待真实归档闭环。
- E-07：`research` 正文已经要求来源、证据和置信状态；`design` reference 已区分已核对、项目约定和未复核。本轮不新建模板。
- E-05、E-06 以及 R-01–R-09 的拉动条件尚未满足，见 [优化清单](./skills-optimization-backlog.md) 的“下一步”与“触发条件”。
