---
name: word
description: "处理本地 Word 文档和模板：读取、提取、分析、创建、编辑、转换与验证 DOC/DOCX/DOTX。需要保留段落、表格、样式、图片、页眉页脚、页码、目录、脚注、公式、批注、修订或复杂模板时使用。不用于 XLS/XLSX/XLSM、PPT/PPTX、TXT、CSV/TSV、在线文档资源、完整 PDF 编辑或纯文字润色；分别交给 excel、powerpoint、txt、spreadsheet、对应连接器、PDF 或 writing skill。"
---

# Word 文档与模板

本 skill 只处理本地 Word 文件的结构和交付，脚本按通用 Linux、macOS 和 Windows 设计。writing 负责文字表达；本 skill 负责 DOCX 包、样式、对象、修订和验证。不存在云文档、网盘、登录或固定厂商应用依赖。

## 工作流

1. **分类**：确定 DOC/DOCX/DOTX 输入、输出扩展名、是否原位编辑，以及是否要保留布局、图片、批注、修订、脚注和嵌入对象。旧版 DOC 默认转换为 DOCX 后处理；未指定输出时，旧版输入默认交付 DOCX。
2. **快照**：检查文件类型和包结构，复制输入或建立工作副本，记录段落、表格、节和关系。默认写到不存在的新路径；输入输出相同或输出已存在时停止并报告。
3. **读取**：提取正文、标题层级、表格、页眉页脚、脚注/尾注、超链接、图片、节、批注、修订、域、书签和文本框；需要审计时同时读原始 XML。
4. **选择路线**：新建使用 `docx` npm 包或 `python-docx`；已有富文档优先修改 OOXML/ZIP 包中的目标部件，或使用能保留未建模部件的本地引擎。高层库会丢失内容时先换保真路线。Markdown 需要引用时使用 `scripts/md2docx_citeproc.py`，引用键采用 Pandoc 标准语法并从本地 bibliography 文件读取。
5. **写出**：执行创建、替换、表格/样式/图片编辑、Markdown/TXT 转换、批注或修订操作。使用本次独占的临时文件和原子替换；用户明确授权原位编辑后先留可恢复副本。
6. **验证**：重新打开并检查包关系、内容类型、XML、文本和对象；布局变化后运行 `scripts/render_docx.py`，由 LibreOffice 转 PDF、再由 Poppler 逐页输出 PNG，检查分页、表格越界、空白页、字体回退、目录和页码，再交付绝对路径与限制。视觉输出使用独立新目录；`--force` 只替换指定输出目录，不删除同名兄弟目录或历史备份。

## 读取与文本替换

- 文字搜索按段落、表格和 XML run 处理。可见短语经常拆到多个 run；先跨 run 匹配，再按最小范围替换。
- 普通提取不等于已读取批注、修订、域、书签、文本框或嵌入对象。报告没有读取的对象。
- 需要按文档顺序提取时，保留段落与表格的顺序；表格包含嵌套表格时递归读取。

## 创建与编辑

- 正式文档使用标题级别、段落样式、列表、表格、页眉页脚、页码和目录；数学使用原生公式结构，不用截图代替公式。
- 使用生成库时先固定页面尺寸和方向；表格同时设置表格与单元格宽度；列表使用编号定义；图片声明真实类型；分页符放在段落中；换行使用新段落；目录使用内置标题级别；点引线使用定位制表符。
- 从 TXT 或 Markdown 生成 DOCX 时明确段落、标题、列表、表格和脚注映射；引用标记保留来源关系。
- 编辑已有文件时保留原始包，只重写目标 XML 部件。复杂模板、嵌入对象或未建模 XML 不用会整包重序列化的库保存。
- 批注、回复、解决和删除批注要维护关系与标识；修订使用插入/删除标记。接受或拒绝修订后重新验证，不用普通替换冒充修订。

## 模板与格式验证

- DOTX 沿用模板样式、页眉页脚、目录和关系；填充后检查占位符、书签、图片、目录和扩展名。
- 验证内容类型、关系目标、XML schema、页眉页脚、书签、批注、修订和图片关系没有断链。
- 生成或改变布局后转为 PDF 或逐页图片检查；结构检查通过不能替代视觉检查。
- 交付前确认没有占位符、错误空项目符号、删除段落残留或丢失脚注/批注。无法渲染时明确标为未验证。

## 随附资产

- `scripts/docx_tool.py`：基础创建、检查、提取和文本替换。
- `scripts/docx.py`：把本地 docx-js 构建、验证、lint、Markdown 转换和视觉 QA 串成统一 CLI。
- `scripts/accept_changes.py`、`scripts/comment.py`、`scripts/merge_runs.py`：修订接受、批注和 run 合并。
- `scripts/render_docx.py`：LibreOffice → PDF → Poppler PNG 的本地布局渲染链；只使用输入和输出路径，不依赖预览服务。
- `scripts/md2docx_citeproc.py`：Pandoc + citeproc 的 Markdown → DOCX 转换；接受 BibTeX/BibLaTeX、CSL JSON/YAML 和 RIS bibliography 文件。
- `scripts/office/validate.py`、`scripts/office/soffice.py`：包验证与跨平台本地转换；`scripts/verify/`：准备、读取、批注、修订、追踪和 OOXML 验证。
- `scripts/lint_docx_js.py`、`assets/example.js`、`assets/reference.docx`、`references/authoring/`：创建、公式和编辑参考；`references/local-alternatives.md` 记录本地工具和分发边界；`vendor/docx/` 是离线 docx-js 依赖。
- 调用随附 Python 资产时使用 `python3 <skill_path>/scripts/<name>`；引用数据、CSL 样式、字体和本地 LibreOffice/Poppler/Pandoc 安装由调用方通过文件路径提供。

## 工具、授权与边界

- 可用工具：`python3`、`python-docx`、`docx` npm 包、`pandoc`、`lxml`、标准 ZIP/XML 工具、LibreOffice 和 Poppler。缺少依赖时报告影响，不反复自动安装；需要安装 Python 包时使用 `pip3`。
- 默认直接执行读取、分析、创建草稿和写新输出；编辑已有文件但保留原件后告知。输出已存在时默认停止并报告；用户明确授权覆盖或原位编辑后，先留可恢复副本再继续。丢弃批注/修订/嵌入对象、删除唯一原件或外部发送必须先确认。
- 输入损坏、依赖缺失或验证失败时停止交付，保留错误证据和最后一个可验证产物。
