import tempfile
import unittest
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from photo_group_picker.cli import analyze, group_photos, select, write_report


class PickerTests(unittest.TestCase):
    def photo(self, path, timestamp=None, faces=None):
        return {"path": path, "timestamp": timestamp, "hash": np.zeros(63, dtype=bool),
                "histogram": np.ones((16, 8), dtype=np.float32), "sharpness": 100,
                "exposure": 0.8, "faces": faces or [], "width": 100, "height": 100}

    def test_time_gap_splits_similar_scenes(self):
        photos = [self.photo("a", 0), self.photo("b", 10), self.photo("c", 500)]
        self.assertEqual([len(g) for g in group_photos(photos, 0.72, 180)], [2, 1])

    def test_distinct_visuals_split_without_time(self):
        a, b = self.photo("a"), self.photo("b")
        b["hash"] = np.ones(63, dtype=bool)
        self.assertEqual(len(group_photos([a, b], 0.72, 180)), 2)

    def test_recommend_both_categories_and_full_group(self):
        landscape = self.photo("landscape")
        solo = self.photo("solo", faces=[{"sharpness": 1000}])
        group = self.photo("group", faces=[{"sharpness": 100}, {"sharpness": 50}])
        self.assertEqual(select([landscape, solo, group], 1), {"landscape", "group"})

    def test_analyze_and_report_original_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test & image.png"
            Image.new("RGB", (120, 80), "green").save(path)
            before = path.read_bytes()
            detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
            photo = analyze(path, detector)
            output = Path(directory) / "report"
            write_report([[photo]], [], output, 2)
            self.assertEqual(path.read_bytes(), before)
            self.assertTrue((output / "results.json").exists())
            self.assertIn(r"test \u0026 image.png", (output / "index.html").read_text(encoding="utf-8"))
            self.assertTrue((output / "thumbnails/00001.jpg").exists())
            self.assertTrue((output / "sheets/0001.jpg").exists())
            self.assertTrue((output / "ai-tasks.json").exists())

    def test_cli_unicode_paths_and_repeated_run(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "旅行 照片"
            source.mkdir()
            Image.new("RGB", (100, 100), "green").save(source / "照片 01.jpg")
            (source / "损坏.jpg").write_bytes(b"invalid image")
            output = source / "report"
            command = [sys.executable, "-m", "photo_group_picker.cli", str(source),
                       "--output", str(output)]
            for _ in range(2):
                result = subprocess.run(command, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
                records = json.loads((output / "results.json").read_text(encoding="utf-8"))
                self.assertEqual(len(records["photos"]), 1)
                self.assertEqual(len(records["errors"]), 1)


if __name__ == "__main__":
    unittest.main()
