import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT))

import render_docx


class RenderDirectoryTest(unittest.TestCase):
    def test_replace_directory_preserves_sibling_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staged = root / "staged"
            staged.mkdir()
            (staged / "new.pdf").write_bytes(b"new fixture output")
            output = root / "render"
            output.mkdir()
            (output / "old.pdf").write_bytes(b"old fixture output")
            history = root / ".render.previous" / "historical-evidence.json"
            history.parent.mkdir()
            history.write_bytes(b'{"owned_by":"another-run"}\n')
            before = history.read_bytes()

            render_docx._replace_directory(staged, output)

            self.assertEqual(history.read_bytes(), before)
            self.assertEqual((output / "new.pdf").read_bytes(), b"new fixture output")
            self.assertEqual(list(root.glob(".render.previous-*")), [])
