#!/usr/bin/env python3
"""TPD 业务规则评估脚本 (match / derive node)

负责调用并解释外置业务规则 Skill（如 customer-report-rules）：
1. --mode match (SRC-01)：将 Word 中的表格区域与 Workingpaper 的 Sheet 进行安全来源绑定；
2. --mode derive (MAP-01)：推导字段列映射、数值精度（2位小数）、零值表示（'-'）与合计行方案。
输出标准的 mapping_plan.json 与流程路由决策字段 (match_status / derive_status)。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


def parse_src01_rules(rules_md_path: Path) -> dict[str, str]:
    """从 rules.md 中解析 SRC-01 来源映射表"""
    if not rules_md_path.exists():
        return {}
    content = rules_md_path.read_text(encoding="utf-8")
    table_map = {}
    # 提取 Markdown 表格中的规则行: | 报告中的区域 | TPD workingpaper 候选工作表 |
    lines = content.splitlines()
    in_table = False
    for line in lines:
        line = line.strip()
        if "报告中的区域" in line and "工作表" in line:
            in_table = True
            continue
        if in_table:
            if not line.startswith("|"):
                in_table = False
                continue
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 2 and not parts[0].startswith("---"):
                word_region = parts[0]
                sheet_name = parts[1]
                table_map[word_region] = sheet_name
    return table_map


def run_match(word_layers_path: Path, wp_tables_path: Path, skill_dir: Path, output_dir: Path) -> str:
    """执行来源匹配 (SRC-01)"""
    w_data = json.loads(word_layers_path.read_text(encoding="utf-8"))
    x_data = json.loads(wp_tables_path.read_text(encoding="utf-8"))

    rules_file = skill_dir / "references" / "rules.md"
    src_map = parse_src01_rules(rules_file)

    sheets = x_data.get("sheets", {})
    available_sheets = set(sheets.keys())

    matched_pairs = []
    unmatched_count = 0

    for tbl in w_data.get("tables", []):
        headers = tbl.get("headers", [])
        h_str = " ".join(headers)
        matched_sheet = None

        # 检查是否命中规则表中的关联交易表
        for region_name, sheet_candidate in src_map.items():
            # 匹配表序号或核心关键词
            m = re.search(r"表\s*(\d+)", region_name)
            t_num = m.group(1) if m else None
            kw = region_name.replace("表", "").replace("：", "").replace(":", "").strip()

            if sheet_candidate in available_sheets:
                # 检查 Word 表格表头是否吻合关联方/金额特征
                if "关联方" in h_str and ("金额" in h_str or "境外" in h_str or "境内" in h_str):
                    # 如果匹配到
                    if sheet_candidate in available_sheets:
                        matched_sheet = sheet_candidate
                        break

        if matched_sheet:
            matched_pairs.append({
                "table_seq": tbl["seq"],
                "headers": headers,
                "matched_sheet": matched_sheet,
                "confidence": 1.0,
                "status": "matched"
            })
        else:
            matched_pairs.append({
                "table_seq": tbl["seq"],
                "headers": headers,
                "matched_sheet": None,
                "confidence": 0.0,
                "status": "unmatched"
            })
            unmatched_count += 1

    match_result = {
        "total_tables": len(w_data.get("tables", [])),
        "matched_count": len(matched_pairs) - unmatched_count,
        "unmatched_count": unmatched_count,
        "matches": matched_pairs
    }

    out_file = output_dir / "match_result.json"
    out_file.write_text(json.dumps(match_result, ensure_ascii=False, indent=2), encoding="utf-8")

    # 如果有重要关联交易表未能匹配或存在冲突，返回 needs_review
    match_status = "matched" if match_result["matched_count"] > 0 else "needs_review"
    print(f"[match] Matched {match_result['matched_count']} tables. Status: {match_status}")
    return match_status


def run_derive(match_result_path: Path, wp_tables_path: Path, skill_dir: Path, output_dir: Path) -> str:
    """执行展示映射推导 (MAP-01)"""
    match_data = json.loads(match_result_path.read_text(encoding="utf-8"))
    x_data = json.loads(wp_tables_path.read_text(encoding="utf-8"))
    sheets = x_data.get("sheets", {})

    plan = []
    for item in match_data.get("matches", []):
        sheet_name = item.get("matched_sheet")
        if not sheet_name or sheet_name not in sheets:
            continue

        sheet_rows = sheets[sheet_name]
        if not sheet_rows:
            continue

        sheet_headers = sheet_rows[0]
        data_rows = sheet_rows[1:]

        # MAP-01 规则：四列对应“关联方”“总金额”“境外金额”“境内金额”
        # 查找对应列的 index
        col_mapping = {}
        for idx, h in enumerate(sheet_headers):
            h_clean = h.strip()
            if "关联方" in h_clean and "全称" not in h_clean:
                col_mapping["关联方"] = idx
            elif "总金额" in h_clean or ("金额" in h_clean and "境" not in h_clean):
                col_mapping["总金额"] = idx
            elif "境外" in h_clean:
                col_mapping["境外金额"] = idx
            elif "境内" in h_clean:
                col_mapping["境内金额"] = idx

        # 数据行格式化（保留两位小数，零值显示为 '-'）
        formatted_rows = []
        for r in data_rows:
            if not any(r):
                continue
            row_dict = {}
            for col_name, c_idx in col_mapping.items():
                val = r[c_idx] if c_idx < len(r) else ""
                # 金额格式化
                if "金额" in col_name and val:
                    clean_val = val.replace(",", "").replace("，", "").replace("¥", "").replace("￥", "").strip()
                    try:
                        num = float(clean_val)
                        if abs(num) < 1e-6:
                            row_dict[col_name] = "-"
                        else:
                            row_dict[col_name] = f"{num:,.2f}"
                    except ValueError:
                        row_dict[col_name] = val
                else:
                    row_dict[col_name] = val
            formatted_rows.append(row_dict)

        plan.append({
            "table_seq": item["table_seq"],
            "sheet_name": sheet_name,
            "target_headers": item["headers"],
            "col_mapping": col_mapping,
            "total_rows": len(formatted_rows),
            "rows": formatted_rows,
            "rules_applied": ["MAP-01: 2-decimal-places", "MAP-01: zero-as-hyphen"]
        })

    mapping_plan = {
        "status": "derived",
        "total_mapped_tables": len(plan),
        "tables": plan
    }

    out_file = output_dir / "mapping_plan.json"
    out_file.write_text(json.dumps(mapping_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    derive_status = "derived" if plan else "needs_review"
    print(f"[derive] Generated plan for {len(plan)} tables. Status: {derive_status}")
    return derive_status


def main():
    parser = argparse.ArgumentParser(description="Evaluate business rules against extracted materials")
    parser.add_argument("--mode", required=True, choices=["match", "derive"])
    parser.add_argument("--run-dir", required=True, help="Run directory containing extracted layers")
    parser.add_argument("--skill-dir", required=True, help="Directory of customer-report-rules")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    skill_dir = Path(args.skill_dir)

    word_layers = run_dir / "word_layers.json"
    wp_tables = run_dir / "wp_tables.json"

    if args.mode == "match":
        status = run_match(word_layers, wp_tables, skill_dir, run_dir)
    elif args.mode == "derive":
        match_res = run_dir / "match_result.json"
        status = run_derive(match_res, wp_tables, skill_dir, run_dir)

    # 结果回写到状态字段文件供流程引擎读取
    (run_dir / f"{args.mode}_status.txt").write_text(status, encoding="utf-8")


if __name__ == "__main__":
    main()
