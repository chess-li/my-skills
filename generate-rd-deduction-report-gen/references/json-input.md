# JSON 输入协议

输入是事实底稿 JSON。`scripts/data_model.py` 只做归一化（顶层字段、嵌套对象、字段别名、默认值）和派生投影；形式校验（必填、技术主线数量与六项齐全、时间顺序、Hxx 格式/唯一/连续、页码格式、图片路径存在、固定要素/核对项枚举）由 `scripts/rule_engine.py` 按 `templates/rules.json` 在归一化前后执行，该文件是唯一可执行规则来源，不同业务可替换。DOCX/XLSX 模板负责固定章节、固定段落、表格列、样式和工作表布局；`templates/report.json` 渲染清单负责声明产物与模板的对应关系；`scripts/generate_rd_docs.py` 只按固定流程执行：加载清单和规则、把模型投射为渲染上下文、调用 docxtpl/openpyxl 渲染、执行跨文件一致性核验（Hxx 集合与首次出现顺序，模式取自 rules.json）。

## 渲染清单与模板约定

`templates/report.json` 是唯一产物清单，包含两部分：

- `documents`：每项声明 `template`（DOCX 模板文件）、`output`（产物文件名）和 `date_field`（该文档使用的日期字段，必须是数据模型字段）。DOCX 模板的变量契约由模板自身推导——模板声明的每个 `{{ 变量 }}` 都必须在渲染上下文中存在，否则渲染失败并报出缺失变量。
- `workbooks`：每项声明 `template`（XLSX 模板文件）、`output` 和 `sheets`（工作表名 → 数据键的映射）。数据键对应数据模型 `to_dict()` 输出的列表字段，如 `supplements`、`word_supplements`、`facts`、`source_manifest`、`unified_element_rows`、`consistency_rows`。

XLSX 模板中，每个数据表有一行 `{{ key }}` 标记单元格，声明该表的数据注入点和列映射；标记行之外的单元格可内联使用 `{{ 字段名 }}` 标量占位（如 04 清单标题中的 `{{ project_name }}`）。渲染器复制标记行样式逐条写入数据行，标量占位的变量名无效时渲染失败。两个 XLSX 模板由 `scripts/create_xlsx_templates.py` 生成；修改工作簿版式（表头、列宽、统计公式、下拉选项、条件格式）应改模板文件本身，而不是生成脚本。

模板语法由 docxtpl 提供：普通字段使用 `{{ item.field }}`，表格行循环使用 `{%tr for item in items %}` / `{%tr endfor %}`，段落循环使用 `{%p for item in items %}` / `{%p endfor %}`，图片字段使用 `InlineImage`。DOCX 模板变量缺失时使用 `StrictUndefined` 使渲染失败。

## 必填字段

- `project_name`、`company_name`、`period`、`leader`、`decision_maker`、`decision_date`、`plan_date`、`outcome_date`
- `background`、`objective`、`difficulties`、`uncertainties`、`company_advantages`、`personnel_advantages`
- `purpose`、`technical_indicators`、`actual_results`、`innovation_points`、`social_benefits`、`economic_benefits`、`application_results`
- `schedule`、`personnel`、`budget_items`、`intellectual_property`
- `topics`：恰好三条技术主线，每条至少提供 `title`、`existing_problem`、`research_objective`、`research_content`、`variables`、`verification`、`expected_effect`。
- `supplements`：可省略，省略时按空列表处理；默认 `channel` 为 `word`，使用唯一 `H01`、`H02`……编号并填写最终 Word 页码；`channel: "list"` 使用唯一 `L01`、`L02`……编号，不填 Word 页码、不进正文。word 项写入工作底稿与 04 补充信息清单；list 项只写入 04 补充信息清单。DOCX 和 Hxx 一致性核验只读取 word 通道。

## 批量对应表

batch 场景下，模型先输出对应表数据 JSON：`materials` 是原始材料到拟归属项目、最终文档的映射行；`questions` 是需要用户裁定的事项行。脚本只负责将结构化数据排版为两个工作表，不判断材料归属。用户审核并更新工作簿后，才将 `corr_status` 设为 `audited`。

```bash
python3 scripts/generate_correspondence_workbook.py \
  --input <correspondence-data.json> \
  --output output/研发加计/对应表与待确认事项清单.xlsx
```

输入示例：

```json
{
  "materials": [
    {
      "source_file": "研发记录.docx",
      "source_location": "第 2 页",
      "project_name": "项目甲",
      "report_document": "02-项目计划书.docx",
      "match_basis": "文件主题与项目目标一致",
      "status": "待确认",
      "note": ""
    }
  ],
  "questions": [
    {
      "topic": "项目归属",
      "question": "该记录属于哪个项目？",
      "proposal": "项目甲",
      "decision": "",
      "status": "待确认",
      "evidence": "文件标题含项目甲关键词"
    }
  ]
}
```

## 常用字段

`period`、`decision_date`、`actual_start_date`、`plan_date`、`actual_end_date`、`outcome_date`、`leader`、`decision_maker`、`funding_source`、`background`、`objective`、`objectives`、`difficulties`、`uncertainties`、`company_advantages`、`personnel_advantages`、`schedule`、`personnel`、`budget_items`、`technical_indicators`、`actual_results`、`innovation_points`、`economic_benefits`、`social_benefits`、`application_results`、`intellectual_property`、`source_manifest`、`unified_elements`、`facts`、`projection_matrix` 和 `consistency_checks`。`objective` 始终作为项目计划书的主要目标段落；未提供 `objectives` 时，列表标记另外使用 `objective` 作为一项；如提供 `objectives`，必须是列表，显式空列表表示不增加额外列表项；若提供实际研发起止日期，脚本会按决议日 ≤ 实际开始日 ≤ 计划书编制日 ≤ 实际结束日 ≤ 成果说明日校验。

以下可选字段由数据模型直接支持：`research_content`（项目级研究内容摘要）、`budget_summary` 或 `budget`（预算摘要）、`expected_results`（预期成果摘要）、`result_ownership`（成果归属）、`result_images`（图片对象列表，每项至少含 `path`，可含 `caption`）。模板渲染会将这些字段投射到对应文档；图片路径必须存在。

列表字段的对象结构由 `scripts/data_model.py` 定义并在入口处归一化；例如 `problem` 归一化为 `existing_problem`，`goal` 归一化为 `research_objective`，`approach` 归一化为 `research_content`，`parameters` 归一化为 `variables`，`validation` 归一化为 `verification`，`effect` 归一化为 `expected_effect`。不确定或冲突的事实必须在值中保留 `【待补充：Hxx】` 或 `【待核对：Hxx】`，不得让脚本猜测事实。

## 归一化与形式校验

两个流程节点都可从 skill 根目录独立运行。归一化脚本读取原始 facts JSON，写出规范化投影；形式规则脚本同时读取原始 JSON 与投影，按 `templates/rules.json` 分别执行 input 与 model 阶段的规则。失败时命令以非零状态退出，并向标准错误输出 JSON 错误对象。

```bash
python3 scripts/data_model.py \
  --input <facts.json> \
  --rules templates/rules.json \
  --output work/normalized.json

python3 scripts/rule_engine.py \
  --input <facts.json> \
  --projection work/normalized.json \
  --rules templates/rules.json
```

## 执行

```bash
python3 scripts/generate_rd_docs.py \
  --input <facts.json> \
  --template-dir templates \
  --output-dir <output-dir>
```

脚本会拒绝少于或多于三条技术主线、重复 `Hxx`、缺失模板和 DOCX/XLSX 占位符集合不一致的输入。

安装 LibreOffice 后可追加 `--render-dir <render-dir>`，脚本会把五个最终文件转为 PDF，供逐页检查分页、目录、表格、图片和公式显示。

## 渲染核验与跨项目汇总

渲染完成后，调用独立核验脚本。它读取 facts JSON、模板清单和已渲染文件；成功时输出 `verify_passed: true`，失败时输出 `verify_passed: false` 并以非零状态退出。

```bash
python3 scripts/verify_rd_docs.py \
  --input <facts.json> \
  --template-dir templates \
  --output-dir <rendered-output-dir>
```

核验通过后调用汇总脚本。单项目不传 `--batch`，脚本返回 skipped 且不创建文件；batch 场景中，所有项目 facts JSON 就绪后传入 `--batch` 和所有项目 facts JSON。脚本从每个 JSON 的 `supplements` 读取待办，生成明细表和分部门统计表。

```bash
python3 scripts/generate_supplement_summary.py \
  --batch \
  --input <project-1-facts.json> <project-2-facts.json> \
  --output output/补充信息汇总清单.xlsx
```
