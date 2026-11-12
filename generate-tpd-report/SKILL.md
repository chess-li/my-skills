---
name: generate-tpd-report
description: 根据转让定价工作底稿 Excel 与上期 Word 报告，依据外置业务规则 Skill 包生成本期 TPD 报告模板与区域差异报告。纯声明式驱动，解析全部由内部 Python 脚本承载，支持流程A编译与 ETL 承载。
---

# 转让定价（TPD）报告模板生成（流程A规范版）

将企业上期 Word 报告与本期转让定价工作底稿（Workingpaper Excel）在业务规则 Skill（如 `customer-report-rules`）指导下自动匹配、映射并渲染为本期报告模板，同时输出精准的区域级差异比对。

本 Skill 完全遵循**流程A规范**：
1. **解析完全由内部 Python 脚本承载**：使用 `extract_tpd_materials.py` 对 Word 与 Excel 执行物理结构抽取与格式解码，不依赖 Java/POI 硬编码；
2. **业务规则外置解耦**：表与 Sheet 的来源匹配（SRC-01）和列映射格式规则（MAP-01）由独立的业务规则包声明；
3. **流程即拓扑**：可无损编译为 LiteFlow BPMN 与状态表 DDL，输入 `ey-timp-etl` 平台执行。

## 流程A（编排唯一信源）

```mermaid
flowchart TD
    start(["输入：Word上期报告 + Excel底稿 + customer-report-rules规则包"]):::io

    extract["材料解析：extract_tpd_materials.py（抽取Word与Excel原始结构）"]:::script
    match["规则匹配：evaluate_rules.py --mode match（执行 SRC-01 来源绑定）"]:::script
    match_gate{"match_status 匹配结果?"}:::cond
    match_audit[["人工介入：来源冲突或底稿缺失确认"]]:::human

    derive["规则推导：evaluate_rules.py --mode derive（执行 MAP-01 映射生成）"]:::script
    derive_gate{"derive_status 映射结果?"}:::cond
    derive_audit[["人工介入：字段口径或精度确认"]]:::human

    render["模板填充：render_tpd_report.py（纯声明式表格回填与书签对齐）"]:::script
    diff["区域比对：diff_regions.py（生成区域差异对比报告）"]:::script
    vcheck["交付核验：verify_report.py（表格完整性与数据对账）"]:::script
    verify_gate{"verify_passed == true?"}:::cond
    rework["返工登记：记录未达标项并阻断"]:::gate
    save_audit[("审计台账入库：记录区域差异与核验明细")]:::data

    done(["交付：本期报告模板 DOCX + 区域差异报告 + 审计状态"]):::io

    start --> extract --> match --> match_gate
    match_gate -->|"matched"| derive
    match_gate -->|"needs_review"| match_audit --> derive
    derive --> derive_gate
    derive_gate -->|"derived"| render
    derive_gate -->|"needs_review"| derive_audit --> render
    render --> diff --> vcheck --> verify_gate
    verify_gate -->|"true"| save_audit --> done
    verify_gate -->|"false"| rework

    classDef model fill:#f96,stroke:#333,color:#000;
    classDef script fill:#9cf,stroke:#333,color:#000;
    classDef human fill:#c9f,stroke:#333,color:#000;
    classDef gate fill:#fd3,stroke:#333,stroke-dasharray:5,color:#000;
    classDef cond fill:#fff,stroke:#333,color:#000;
    classDef data fill:#dfd,stroke:#333,color:#000;
    classDef io fill:#eee,stroke:#999,color:#000;
```

```yaml
flow: generate-tpd-report
version: 1
scope: 单报告粒度；以 Word 上期报告与 Excel 底稿为单位生成本期报告模板
inputs: [上期Word报告路径, 工作底稿Excel路径, 业务Skill规则包路径]
artifacts:
  scripts:
    extract: scripts/extract_tpd_materials.py
    match: scripts/evaluate_rules.py
    derive: scripts/evaluate_rules.py
    render: scripts/render_tpd_report.py
    diff: scripts/diff_regions.py
    vcheck: scripts/verify_report.py
outputs:
  - output/<报告名称>_本期模板.docx
  - output/<报告名称>_区域差异报告.json
  - output/<报告名称>_审计日志.json
fields:
  match_status: {type: enum, values: [matched, needs_review], emitted_by: match}
  derive_status: {type: enum, values: [derived, needs_review], emitted_by: derive}
  verify_passed: {type: bool, emitted_by: vcheck}
channels:
  regions.channel: {type: enum, values: [table, paragraph], emitted_by: extract, note: 区域类型通道，cond不得引用}
states:
  binding_line:
    envelope: [state, entity, flow_instance, chain_code, source_node, blocking, status_value, ts]
    note: 轻量绑定（state.jsonl）与平台 DB 状态表同源，行逐字可逆。
  match_audit:
    field: match_status
    entity: 来源匹配审核
    names: {matched: 匹配通过, needs_review: 待人工确认}
    producer: match_audit
    consumer: match_gate
    changed_by: 人工（在审阅台确认来源工作表）
    blocking: true
  derive_audit:
    field: derive_status
    entity: 映射规则审核
    names: {derived: 推导通过, needs_review: 待人工确认}
    producer: derive_audit
    consumer: derive_gate
    changed_by: 人工（在审阅台确认字段映射口径）
    blocking: true
  rework_audit:
    field: verify_passed
    entity: 渲染核验返工
    names: {false: 校验不通过待返工}
    producer: rework
    consumer: verify_gate
    changed_by: 人工（排查格式或底稿后重跑）
    blocking: true
acceptance:
  - 所有待填充表格均有来源 Sheet 对应或显式标记 needs_review
  - 字段映射符合业务 Skill 声明，金额列保留两位小数，零值显示为 -
  - Base 稿与 Template 稿具备完全对齐的书签锚点（TPL_TR_xxxxxx）
  - 区域差异对比报告覆盖全部标注区域，无结构丢失
  - 产出符合 DOCX 规范，可在各类 Web 编辑器（Collabora / OnlyOffice）中无损打开
policies:
  - 格式解析直接使用 Skill 中的 Python 脚本执行，严禁在 Java/ETL 引擎中编写特定格式或业务抽取逻辑
  - 业务规则完全由外部业务 Skill（customer-report-rules 等）提供，主流程保持通用无业务硬编码
  - 匹配或映射不确定时必须给出 needs_review，阻断至人工门禁，杜绝伪造乘数（禁止使用 1.085 等假数据）
```
