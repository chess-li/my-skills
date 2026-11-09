import io
import tempfile
import unittest
from pathlib import Path

from docx import Document
from PIL import Image
from openpyxl import Workbook

from scripts.extract_images import (
    extract_doc_images,
    extract_docx_images,
    extract_standalone_image,
    extract_xlsx_images,
)


def tiny_png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buffer, "PNG")
    return buffer.getvalue()


def tiny_jpeg() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "gray").save(buffer, "JPEG")
    return buffer.getvalue()


class ExtractImagesTest(unittest.TestCase):
    def test_docx_image_carries_surrounding_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "sample.docx"
            document = Document()
            document.add_heading("第2章 试验记录", level=1)
            document.add_paragraph("段落一：空白对照组")
            document.add_paragraph("如图 1 所示")
            run = document.add_paragraph("图片段落").add_run()
            run.add_picture(io.BytesIO(tiny_png()))
            document.add_paragraph("图 1 样品状态")

            document.save(source)
            entries = extract_docx_images(source, root / "out")

            self.assertEqual(len(entries), 1)
            context = entries[0]["context"]
            self.assertEqual(context["heading"], "第2章 试验记录")
            self.assertEqual(context["paragraph"], "图片段落")
            self.assertEqual(context["previous"], "如图 1 所示")
            self.assertEqual(context["following"], "图 1 样品状态")
            self.assertTrue((root / "out" / entries[0]["image"]).exists())

    def test_xlsx_image_carries_sheet_and_nearby_cell(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "sample.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "试验"
            sheet["A1"] = "2024-03-21 解冻测试"
            sheet["B3"] = "温度记录"
            sheet.add_image(__import__("openpyxl.drawing.image", fromlist=["Image"]).Image(io.BytesIO(tiny_png())), "C3")
            workbook.save(source)

            entries = extract_xlsx_images(source, root / "out")

            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["context"]["sheet"], "试验")
            self.assertEqual(entries[0]["context"]["nearby"], "温度记录")

    def test_doc_carves_jpeg_in_page_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "sample.doc"
            source.write_bytes(b"\x00" * 16 + tiny_jpeg() + b"\xff" * 32 + tiny_jpeg() + b"\x00" * 8)

            entries = extract_doc_images(source, root / "out")

            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0]["context"]["page_order"], 1)
            self.assertEqual(entries[1]["context"]["page_order"], 2)
            for entry in entries:
                self.assertTrue((root / "out" / entry["image"]).read_bytes().startswith(b"\xff\xd8"))

    def test_standalone_attachment_image_is_extracted_with_filename_context(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "TS-NX-93-N001-01调味蚬子500g标签.jpg"
            source.write_bytes(tiny_jpeg())

            entries = extract_standalone_image(source, root / "out")

            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["kind"], "image")
            self.assertEqual(entries[0]["context"]["filename"], source.name)
            self.assertTrue((root / "out" / entries[0]["image"]).exists())


if __name__ == "__main__":
    unittest.main()
