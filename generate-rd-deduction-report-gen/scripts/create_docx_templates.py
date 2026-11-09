#!/usr/bin/env python3
"""Create editable DOCX templates using standard Jinja2/docxtpl syntax."""

from __future__ import annotations

import argparse
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Mm, Pt, RGBColor


BLUE = RGBColor(31, 78, 121)


def configure(document: Document) -> None:
    section = document.sections[0]
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.3)
    section.right_margin = Cm(2.3)
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    styles = document.styles
    normal = styles["Normal"]
    normal.font.name = "宋体"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    normal.font.size = Pt(10.5)
    for name, size in [("Title", 20), ("Heading 1", 16), ("Heading 2", 13), ("Heading 3", 11.5)]:
        style = styles[name]
        style.font.name = "黑体"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "黑体")
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = BLUE
    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.CENTER
    header.add_run("研发项目资料").font.name = "宋体"
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run("第 ")
    add_field(footer, "PAGE")
    footer.add_run(" 页")


def add_field(paragraph, instruction: str) -> None:
    run = paragraph.add_run()
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), instruction)
    run._r.append(field)


def enable_field_updates(document: Document) -> None:
    settings = document.settings.element
    update = settings.find(qn("w:updateFields"))
    if update is None:
        update = OxmlElement("w:updateFields")
        settings.append(update)
    update.set(qn("w:val"), "true")


def add_cover(document: Document, title: str) -> None:
    cover = document.add_paragraph()
    cover.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cover.paragraph_format.space_before = Pt(120)
    run = cover.add_run(title)
    run.font.name = "黑体"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "黑体")
    run.font.size = Pt(20)
    run.font.bold = True
    run.font.color.rgb = BLUE
    for text in ["项目名称：{{ project_name }}", "承担单位：{{ company_name }}", "研发周期：{{ period }}", "编制日期：{{ document_date }}"]:
        paragraph = document.add_paragraph(text)
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_before = Pt(12)
    document.add_page_break()
    document.add_heading("目录", level=1)
    toc = document.add_paragraph()
    add_field(toc, 'TOC \\o "1-3" \\h \\z \\u')
    document.add_page_break()


def add_heading(document, text: str, level: int = 1) -> None:
    document.add_heading(text, level=level)


def add_text(document, text: str) -> None:
    document.add_paragraph(text)


def add_bullet_loop(document, collection: str) -> None:
    document.add_paragraph(f"{{%p for item in {collection} %}}")
    document.add_paragraph("{{ item }}", style="List Bullet")
    document.add_paragraph("{%p endfor %}")


def add_table(document, headers, rows) -> None:
    table = document.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    for index, value in enumerate(headers):
        table.rows[0].cells[index].text = value
    for row in rows:
        cells = table.add_row().cells
        for index, value in enumerate(row):
            cells[index].text = value
    table.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
    document.add_paragraph()


def add_row_loop_table(document, headers, collection: str, fields: list[str], variable: str = "item") -> None:
    table = document.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    for index, value in enumerate(headers):
        table.rows[0].cells[index].text = value
    start = table.add_row().cells
    start[0].text = f"{{%tr for {variable} in {collection} %}}"
    data_row = table.add_row().cells
    for index, field in enumerate(fields):
        data_row[index].text = f"{{{{ {variable}.{field} }}}}"
    end = table.add_row().cells
    end[0].text = "{%tr endfor %}"
    table.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
    document.add_paragraph()


def add_topic_loop_table(document) -> None:
    table = document.add_table(rows=1, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    table.rows[0].cells[0].text = "方案要素"
    table.rows[0].cells[1].text = "内容"
    start = table.add_row().cells
    start[0].text = "{%tr for topic in topics %}"
    rows = [
        ("课题名称", "{{ topic.title }}"),
        ("现有问题", "{{ topic.existing_problem }}"),
        ("研究目标", "{{ topic.research_objective }}"),
        ("研究内容/试验思路", "{{ topic.research_content }}"),
        ("变量或参数", "{{ topic.variables }}"),
        ("验证方式", "{{ topic.verification }}"),
        ("预期效果", "{{ topic.expected_effect }}"),
    ]
    for label, value in rows:
        cells = table.add_row().cells
        cells[0].text = label
        cells[1].text = value
    conditional_start = table.add_row().cells
    conditional_start[0].text = "{%tr if topic.image %}"
    image_row = table.add_row().cells
    image_row[0].text = "图片"
    image_row[1].text = "{{ topic.image }}"
    caption_row = table.add_row().cells
    caption_row[0].text = "图注"
    caption_row[1].text = "{{ topic.caption }}"
    conditional_end = table.add_row().cells
    conditional_end[0].text = "{%tr endif %}"
    end = table.add_row().cells
    end[0].text = "{%tr endfor %}"
    table.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
    document.add_paragraph()


def create_decision(path: Path) -> None:
    document = Document()
    configure(document)
    add_cover(document, "关于{{ project_name }}的立项决议")
    add_heading(document, "一、审议事项")
    add_text(document, "审议本项目立项申请。")
    add_heading(document, "二、立项决议")
    add_text(document, "经审议，同意本项目立项并按计划组织研发。")
    add_table(document, ["项目要素", "内容"], [
        ["项目目标", "{{ objective }}"],
        ["主要研究内容", "{{ research_content_summary }}"],
        ["项目负责人及团队", "{{ leader }}"],
        ["研发周期", "{{ period }}"],
        ["预算及费用构成", "{{ budget_summary }}"],
        ["经费来源", "{{ funding_source }}"],
        ["预期成果", "{{ expected_results }}"],
    ])
    add_heading(document, "三、组织实施授权")
    add_text(document, "授权项目负责人组织研发团队实施项目，并按企业内部管理制度推进。")
    add_heading(document, "四、落款")
    add_table(document, ["承担单位", "决策机构或授权人", "日期"], [["{{ company_name }}", "{{ decision_maker }}", "{{ decision_date }}"]])
    path.parent.mkdir(parents=True, exist_ok=True)
    enable_field_updates(document)
    document.save(path)


def create_plan(path: Path) -> None:
    document = Document()
    configure(document)
    add_cover(document, "{{ project_name }}项目计划书")
    add_table(document, ["项目名称", "承担单位", "项目负责人", "研发周期"], [["{{ project_name }}", "{{ company_name }}", "{{ leader }}", "{{ period }}"]])
    add_heading(document, "第1章 立项依据")
    add_heading(document, "1.1 立项背景", 2)
    add_text(document, "{{ background }}")
    add_heading(document, "第2章 项目目标与方案")
    add_heading(document, "2.1 研发目标", 2)
    add_text(document, "{{ objective }}")
    add_bullet_loop(document, "objectives")
    add_heading(document, "2.2 方案设计", 2)
    add_topic_loop_table(document)
    add_heading(document, "第3章 项目难点与技术不确定性")
    add_heading(document, "3.1 项目难点", 2)
    add_bullet_loop(document, "difficulties")
    add_heading(document, "3.2 项目技术不确定性", 2)
    add_bullet_loop(document, "uncertainties")
    add_heading(document, "第4章 现有研发条件和工作基础")
    add_heading(document, "4.1 公司优势", 2)
    add_bullet_loop(document, "company_advantages")
    add_heading(document, "4.2 人员优势", 2)
    add_bullet_loop(document, "personnel_advantages")
    add_heading(document, "第5章 计划进度")
    add_row_loop_table(document, ["计划时间", "阶段", "主要研发内容", "阶段成果或输出物"], "schedule", ["time", "stage", "content", "output"])
    add_heading(document, "第6章 项目编制及研发人员名单")
    add_row_loop_table(document, ["姓名", "部门/岗位", "项目职责", "工作内容"], "personnel", ["name", "department", "responsibility", "work_content"])
    add_heading(document, "第7章 经费预算")
    add_row_loop_table(document, ["费用分类", "预算金额", "主要用途"], "budget_items", ["category", "amount", "purpose"])
    path.parent.mkdir(parents=True, exist_ok=True)
    enable_field_updates(document)
    document.save(path)


def create_outcome(path: Path) -> None:
    document = Document()
    configure(document)
    add_cover(document, "{{ project_name }}成果效用说明")
    add_table(document, ["项目名称", "承担单位", "项目负责人", "研发周期"], [["{{ project_name }}", "{{ company_name }}", "{{ leader }}", "{{ period }}"]])
    add_heading(document, "第1章 项目研发的整体概述")
    add_heading(document, "1.1 项目研发目的及意义", 2)
    add_text(document, "{{ purpose }}")
    add_heading(document, "1.2 项目研发的技术创新点", 2)
    add_bullet_loop(document, "innovation_points")
    add_heading(document, "第2章 项目研发成果综述")
    add_heading(document, "2.1 实现的技术指标与关键参数", 2)
    add_row_loop_table(document, ["指标/参数", "目标或计划", "实际结果", "验证依据"], "technical_indicators", ["name", "target", "actual", "evidence"])
    add_heading(document, "2.2 研发具体成果展示", 2)
    add_heading(document, "2.2.1 研发成果归属", 3)
    add_text(document, "{{ result_ownership }}")
    add_heading(document, "2.2.2 研发成果展示", 3)
    add_bullet_loop(document, "actual_results")
    add_text(document, "{%p if result_image %}")
    add_text(document, "{{ result_image }}")
    add_text(document, "{{ result_caption }}")
    add_text(document, "{%p endif %}")
    add_row_loop_table(document, ["成果/知识产权", "编号", "日期", "归属或状态"], "intellectual_property", ["name", "number", "date", "status"])
    add_heading(document, "第3章 研发项目经济及社会效应")
    add_heading(document, "3.1 社会效益", 2)
    add_text(document, "{{ social_benefits }}")
    add_heading(document, "3.2 经济效益", 2)
    add_text(document, "{{ economic_benefits }}")
    add_heading(document, "3.3 应用成果", 2)
    add_bullet_loop(document, "application_results")
    path.parent.mkdir(parents=True, exist_ok=True)
    enable_field_updates(document)
    document.save(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    create_decision(args.output_dir / "01-立项决议-template.docx")
    create_plan(args.output_dir / "02-项目计划书-template.docx")
    create_outcome(args.output_dir / "03-成果效用说明-template.docx")


if __name__ == "__main__":
    main()
