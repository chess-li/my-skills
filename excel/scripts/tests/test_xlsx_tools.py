import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT))

import xlsx_tools


class ExcelStagingTest(unittest.TestCase):
    def test_calc_mode_staging_preserves_fixed_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "book.xlsx"
            book = Workbook()
            book.active["A1"] = "=1+1"
            book.save(source)
            unrelated = root / "book.xlsx.calcmode-part"
            unrelated.write_bytes(b"pre-existing staging data from another operation\n")
            before = unrelated.read_bytes()

            self.assertTrue(xlsx_tools._set_calc_mode_auto(str(source)))

            self.assertEqual(unrelated.read_bytes(), before)
            self.assertEqual(list(root.glob("book.xlsx.calcmode-part-*")), [])
