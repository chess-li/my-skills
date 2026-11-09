import io
import json
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from scripts.extract_doc_layers import _decode_word_stream, classify_doc_forensic, main


class ExtractDocLayersTest(unittest.TestCase):
    def test_utf16_word_stream_decodes_chinese_text(self):
        decoded = _decode_word_stream("研发目标：提高良品率".encode("utf-16le"))

        self.assertIn("研发目标：提高良品率", decoded)

    def test_chinese_ole_word_stream_is_classified_as_readable(self):
        class FakeOle:
            def exists(self, name):
                return name == "/WordDocument"

            def openstream(self, _name):
                return BytesIO("研发目标：提高良品率".encode("utf-16le"))

            def close(self):
                pass

        fake_olefile = types.ModuleType("olefile")
        fake_olefile.OleFileIO = lambda _data: FakeOle()
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "chinese.doc"
            source.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
            with patch.dict("sys.modules", {"olefile": fake_olefile}):
                result = classify_doc_forensic(source)

        self.assertEqual(result["doc_forensic_result"], "readable")
        self.assertGreater(result["text_chars"], 0)

    def test_non_ole_file_is_classified_as_damaged(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "broken.doc"
            source.write_bytes(b"not an OLE document")

            result = classify_doc_forensic(source)

            self.assertEqual(result["doc_forensic_result"], "damaged")
            self.assertIn("OLE", result["evidence"])

    def test_extractable_text_is_classified_as_readable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "readable.doc"
            source.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1Readable legacy document text.")

            result = classify_doc_forensic(source)

            self.assertEqual(result["doc_forensic_result"], "readable")
            self.assertGreater(result["text_chars"], 0)

    def test_no_text_with_carved_images_is_classified_as_image_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "scanned.doc"
            source.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
            with patch(
                "scripts.extract_doc_layers.extract_doc_images",
                return_value=[{"image": "img_001.jpg"}],
            ):
                result = classify_doc_forensic(source)

            self.assertEqual(result["doc_forensic_result"], "image_only")
            self.assertEqual(result["image_count"], 1)

    def test_classify_only_cli_emits_the_routing_field(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "readable.doc"
            source.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1Readable legacy document text.")
            stdout = io.StringIO()
            with patch(
                "sys.argv",
                ["extract_doc_layers.py", "--input", str(source), "--classify-only"],
            ), redirect_stdout(stdout):
                main()

            result = json.loads(stdout.getvalue())
            self.assertTrue(result["ok"])
            self.assertEqual(result["doc_forensic_result"], "readable")


if __name__ == "__main__":
    unittest.main()
