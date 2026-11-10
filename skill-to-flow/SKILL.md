---
name: skill-to-flow
description: 将已有 Agent Skill 转换为可在外部流程引擎执行的流程：按流程A规范（Mermaid 拓扑 + YAML 契约块）编排或校验 skill，经决策环（批量语义、模型/人工/返工落地策略）编译为 EY TIMP ETL 的 BPMN JSON（elBpmn）与状态表 DDL，并驱动两种绑定的无损验证。适用于已流程化 skill 的 ETL 化（参考案例：generate-rd-deduction-report-gen）。不用于创作或评审 skill 内容本身，那是 skill-creator 的事；不直接修改 ETL 平台代码。
---

# skill → 流程 → ETL 流程

把 Agent Skill 变成流程引擎可执行的东西，全程一条纪律：**语义只在声明层，转换器不做推断**——分支判断在 `fields:`，人工语义在 `states:`，批量与落地策略是显式决策，编译器遇到未声明的构造就失败，绝不静默降级。

## 必备前置

被转换的 skill 必须已按流程A规范编排（嵌 Mermaid 流程图 + YAML 契约块）。没有流程A 的 skill 先转交 `skill-creator` 补编排，不在本 skill 里现场发明格式。规范全文与参考案例（相对 **skills 仓库根**）：`skills/business/generate-rd-deduction-report-gen/SKILL.md`（首个验证案例，含四台状态机与 binding_line 声明）。编译与绑定也在该仓库根执行；目标运行时是 EY TIMP ETL（独立的 ey-timp-etl 工程）。

## 流程A 契约块必备区段

`fields:`（路由字段：type、闭合枚举、emitted_by）、`channels:`（状态通道，cond 不得引用）、`states:`（状态机：producer/consumer/blocking + `binding_line:` 行封套）、`acceptance:`（交付门槛）、`policies:`、`artifacts:`、`outputs:`。六条铁律（图管拓扑块管契约、分支只读路由字段、classDef 即执行者、待办双通道、acceptance 是门槛、人工语义只在 states: 声明）的完整表述见参考案例，转换时逐条机器校验。

## 平台硬约束（EY TIMP ETL，已实证——含执行级验证）

1. **无环**：返工回边必须给落地策略，平台 EL 不表达环。
2. **无人工节点**：human/gate 落地为 `OUTPUT_DB` 状态落库（`--human-as=db_state`）或失败边通知点（`--human-as=fail_edge`）；阻断/非阻断只来自 `states:` 的 `blocking:`。
3. **禁止多分支合并到同一节点**：switch 直接分支与嵌套分支汇入同一节点时 EL 生成失败；编译器完全树化（每个汇合点克隆下游），保证全图零汇合。
4. **分支 tag 机制脆弱**：`branchConfig.tableData.nextNode` 必须是下游节点的 **tag**（text.value）不是 id；克隆子树时内部 switch 的 tableData 必须同步改写为克隆 tag；**switch 不得作为 switch 的直接分支子项**（tag 组成不可靠），编译器融合直连 switch→switch（条件 AND 合取）。
5. **节点 tag 全链唯一**：克隆必须换新 tag。
6. **条件表达式协议**：cond 边编译为 **`${field}` 占位符表达式**（如 `${batch} == true`、`${file_type} == 'xls'`），由 `SpelExpressionUtils` 先字面替换再求 SpEL；**字段缺失时整行替换为恒假**（连取反行也失效），所以布尔输入字段必须显式给默认值；值侧字符串用单引号字面量。
7. **formData 平台契约**：`nodeConfig.text`、`ceScriptConfig.ceScriptCode`、`iteratorConfig.loopType`、`branchConfig.tableData` 缺一不可。
8. **请求数据协议**：节点请求数据 = 对象上下文（主）∪ 迭代上下文 ∪ slot 链请求数据（putIfAbsent）∪ 默认配置；初始触发参数需由首输入节点 emit 进上下文（冒烟测试直接注入 `EtlTransmittableContext.setRequestData`）。

## 执行验证（FlowAExecuteSmokeTest，5 场景；策略 `--human-as=db_state --rework-as=fail_edge`）

冒烟单测在 ey-timp-etl-web（`liteflow/test/FlowAExecuteSmokeTest`），吃的是本仓库编译进 etl 测试资源的 BPMN，不是在 etl 仓内再编译。

- 主路径（generic）：batchq→…→done 按序执行，无 audit/rework 状态节点误触发；
- 损坏分路（generic）：docq → `docdmg_state`（OUTPUT_DB）→ 原路继续到交付；
- 冲突分路（generic，无用户裁定）：dateq → `hxxdate_state` → conflict → `hxx_state` → ruleq → **`ruleq_rework_state` 后链路终止**（`--rework-as=fail_edge` 把 ruleq(false) 回边落地为返工状态落库+失败终止；**不会**走到 ruling/compliance/done）。人工裁定或确认 Hxx 后需**重触发**才正向收敛；
- 核验失败分路（generic）：verify(false) → **`verify_rework_state` 后终止**，不进 summary/done；
- 批量循环（loop 产物）：`PROCESS_ITERATOR` foreach，单项目链每轮独立路由（render/vcheck/done 各 2 轮；干净项目走 frext→fread、损坏项目走状态落库；轮间互不污染）。
- 路径断言用 `LiteflowResponse.getExecuteStepQueue()` 的 `refNode.getTag()`（步骤类型是 SINGLE 不是 START；`getExecuteStepStrWithoutTime()` 只给组件类名）。

## foreach 迭代协议（实证）

- 集合来源：上游节点数据集（`context.getLatestData`），即输入节点产出的行列表；每行 Map 成为该轮 `currLoopObj`，由 `EtlRequestDataConvent` 合入子链请求数据（putIfAbsent，优先级低于对象上下文）；
- 因此批量场景的外层上下文**不得携带路由字段**，否则按项目的路由值会被遮蔽；测试替身在上游数据集为空时回退请求参数 `loopList`（测试注入专用，生产无此前端键）。

## 转换工作流

1. **可转换判定**：读目标 skill 的 SKILL.md，确认流程A 齐全（mermaid + 契约块必备区段，见上节列举）；缺失即回 skill-creator，不现场补格式。
2. **批量语义决策环**（必问用户）：`--batch-mode=loop`（单项目链入 PROCESS_ITERATOR.childChain）还是 `generic`（只声明粒度）；默认不替用户选。
3. **落地策略决策环**（必问用户，缺省即编译失败）：`--model-as`（现仅 ce_script：模型步骤包装 CE 脚本调 LLM，脚本内容人工补全）、`--human-as`（db_state 推荐 / fail_edge）、`--rework-as`（**fail_edge：图上返工回边编译为返工状态落库后链路终止，人工修正后重触发** / iterator 未实现）。独立 Agent 跑流程A 仍可在语义层“回 paper 再跑”；ETL 编译产物在 `fail_edge` 下不保留环。
4. **编译**（在 **skills 仓库根**执行，不是 ey-timp-etl）：`python3 scripts/flowa_compile.py <SKILL.md> [策略参数] --out <产物>.bpmn.json`；脚本路径即本仓 `scripts/flowa_compile.py`。产出 elBpmn JSON + 状态表 DDL（`<产物>.ddl.sql`，states 声明驱动）。铁律 violation 与策略缺失都以编译错误呈现，修声明或补策略，不改编译器迁就。
5. **绑定验证**（有独立运行样本时，同样在 skills 仓根）：`python3 scripts/flowa_state_bind.py <state.jsonl> <SKILL.md>` 验证轻量绑定与 DB 绑定无声明之外的信息差（列纯投影、行逐字可逆、键不越界）。新样本与验证记录放 `<主工作区>/.agent-artifacts/<任务>/<唯一运行标识>/`；Git 用登记的主 checkout，非 Git 用项目目录。首次创建前在该工作区 `.gitignore` 加入 `/.agent-artifacts/` 并用 `git check-ignore` 核验，非 Git 跳过。BPMN/DDL 默认先写该运行目录，正式交付再按第 6 步显式复制；保留样本不随编译或 worktree 清理删除，既有 `flow-a-validate/` 不自动迁移或清理。
6. **平台验证**（在 **ey-timp-etl** 消费产物，不在那边跑编译器）：把 BPMN/DDL 拷入或对齐 `ey-timp-etl-web/src/test/resources/flowa/`，走 `LiteFlowParser.convertElData` + `LiteFlowChainELBuilder.validateWithEx`（`FlowACompileBpmnValidateTest` / `FlowAExecuteSmokeTest`）；或在 ETL 管理界面导入。
7. **交付清单**：BPMN JSON、DDL、EL 表达式、策略决策记录、未决项显式列出（FLOWA_* 占位 CE 脚本绑定、_ctx 变量对齐、建表与数据源绑定、分页工具链）。

## 已知边界

- `--rework-as=iterator`（回边转 ITERATOR 循环）未实现；当前实证与冒烟均按 `--rework-as=fail_edge`（回边→返工状态节点→终止）。
- model→CE_SCRIPT 只生成占位 `ceScriptCode=FLOWA_<node>`，LLM 调用协议需人工补全。
- 树化后 EL 冗长（公共后缀按分支复制；本参考案例 generic 约 **350** 节点/349 边，loop 为 1 个 `PROCESS_ITERATOR` 外包同构 childChain）——机器生成产物，语义正确，不宜人工阅读。历史产物若仍见约 264/322 节点，以当前编译器输出为准并同步 etl 测试资源。
- 批量循环 foreach 数据源是上游节点数据集；编译产物在循环容器前没有输入节点时，需要在容器前补一个产出项目清单的输入节点（或按平台惯例由 API 输入节点承担）；冒烟测试在数据集为空时用请求参数 `loopList` 注入（仅测试）。
- **仓职责拆分**：编译器/绑定器在 **skills 仓库**（`scripts/flowa_compile.py`、`scripts/flowa_state_bind.py`，案例 `skills/business/...`）；验证材料位置按第 5 步。**ey-timp-etl 不含这些脚本**，只消费 BPMN/DDL 并跑平台单测。skill 单独分发时不含 scripts，需随 skills 仓获取或改运行时定位。
- 平台单测依赖 ey-timp-etl 工作树与本地构件（如 ey-timp-etl-process 2.5.0.9）；全量 `mvn test` 重编译若遇 Lombok/JDK（`JCImport.qualid`）不匹配，属 etl 工具链问题而非本 skill 流程缺陷——可先用已编译 class 跑 `mvn surefire:test -pl ey-timp-etl-web -Dtest=FlowACompileBpmnValidateTest,FlowAExecuteSmokeTest`，或在 etl 侧固定可用的 JDK/Lombok 后再重建。
