import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT))

import thumbnail


class ThumbnailOutputTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_later_grid_exists_does_not_publish_earlier_grid(self):
        slides = []
        for index in range(13):
            image = self.root / f"slide-{index}.png"
            Image.new("RGB", (8, 8), "blue").save(image)
            slides.append((image, f"slide{index}.xml"))
        later = self.root / "thumbnails-2.jpg"
        later.write_bytes(b"pre-existing-grid")
        before = later.read_bytes()

        with self.assertRaises(FileExistsError):
            thumbnail.create_grids(slides, 3, 80, self.root / "thumbnails.jpg")

        self.assertFalse((self.root / "thumbnails-1.jpg").exists())
        self.assertEqual(later.read_bytes(), before)

    def test_existing_single_grid_is_not_overwritten(self):
        image = self.root / "slide.png"
        Image.new("RGB", (8, 8), "blue").save(image)
        output = self.root / "thumbnails.jpg"
        output.write_bytes(b"pre-existing-thumbnail")
        before = output.read_bytes()

        with self.assertRaises(FileExistsError):
            thumbnail.create_grids([(image, "slide1.xml")], 3, 80, output)

        self.assertEqual(output.read_bytes(), before)
