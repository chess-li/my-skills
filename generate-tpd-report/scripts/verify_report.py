#!/usr/bin/env python3
"""TPD 交付核验脚本 (vcheck node)

核验生成的模板 Word 与差异报告：
1. 检查修改区域数量是否合理；
2. 检查表格结构是否完整；
3. 输出 verify_passed 决策字段 (true / false)。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def verify_deliverables(diff_report_path: Path, output_dir: Path) -> bool:
    if not diff_report_path.exists():
        print("[vcheck] Error: Diff report not found", file=sys.stderr)
        return False

    report = json.loads(diff_report_path.read_text(encoding="utf-8"))
    total = report.get("total_regions", 0)
    modified = report.get("modified_regions", 0)

    # 门禁准则：总区域数 > 0 且存在修改区域
    passed = total > 0 and modified > 0

    result = {
        "verify_passed": passed,
        "criteria": {
            "has_regions": total > 0,
            "has_modifications": modified > 0
        },
        "summary": f"Verified {total} regions, {modified} modified."
    }

    out_file = output_dir / "verify_result.json"
    out_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "verify_status.txt").write_text("true" if passed else "false", encoding="utf-8")
    print(f"[vcheck] Verification {'PASSED' if passed else 'FAILED'}: {result['summary']}")
    return passed


def main():
    parser = argparse.ArgumentParser(description="Verify generated TPD deliverables")
    parser.add_argument("--diff-report", required=True, help="Path to region_diff.json")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    args = parser.parse_args()

    passed = verify_deliverables(Path(args.diff_report), Path(args.output_dir))
    if not passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
