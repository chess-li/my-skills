import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import xlrd

from scripts.extract_office_layers import extract_office_layers


class FakeSheet:
    name = "费用"
    nrows = 2
    ncols = 2

    _values = [["日期", "金额"], [45292.0, 1200.0]]
    _types = [
        [xlrd.XL_CELL_TEXT, xlrd.XL_CELL_TEXT],
        [xlrd.XL_CELL_DATE, xlrd.XL_CELL_NUMBER],
    ]

    def cell_value(self, row, column):
        return self._values[row][column]

    def cell_type(self, row, column):
        return self._types[row][column]


class FakeBook:
    datemode = 0

    def __init__(self):
        self.sheet = FakeSheet()
        self.released = False

    def sheet_names(self):
        return [self.sheet.name]

    def sheet_by_name(self, name):
        if name != self.sheet.name:
            raise KeyError(name)
        return self.sheet

    def release_resources(self):
        self.released = True


class ExtractOfficeLayersTest(unittest.TestCase):
    def test_xls_writes_text_and_sheet_tables(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "sample.xls"
            source.write_bytes(b"xls fixture handled by xlrd mock")
            output_dir = root / "out"
            book = FakeBook()

            with patch("xlrd.open_workbook", return_value=book) as open_workbook:
                result = extract_office_layers(source, output_dir)

            expected_text = "[费用]\t日期\t金额\n[费用]\t2024-01-01 00:00:00\t1200"
            expected_tables = {"费用": [["日期", "金额"], ["2024-01-01 00:00:00", "1200"]]}
            self.assertEqual(
                result,
                {
                    "source": "sample.xls",
                    "kind": "xls",
                    "text_path": "text.txt",
                    "text_chars": len(expected_text),
                    "tables_path": "tables.json",
                    "sheet_names": ["费用"],
                    "errors": [],
                },
            )
            self.assertEqual((output_dir / "sample" / "text.txt").read_text(encoding="utf-8"), expected_text)
            self.assertEqual(
                json.loads((output_dir / "sample" / "tables.json").read_text(encoding="utf-8")),
                expected_tables,
            )
            open_workbook.assert_called_once_with(str(source), on_demand=True)
            self.assertTrue(book.released)


if __name__ == "__main__":
    unittest.main()
