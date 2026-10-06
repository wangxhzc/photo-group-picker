import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from photo_group_picker.cli import quality, select, similarity
from photo_group_picker.report import write_report
from photo_group_picker.review import apply_review, composite_plans, regroup


def photo(path, sharpness=500, person="p1", eyes="unknown"):
    return {"path": path, "timestamp": None, "width": 200, "height": 100,
            "analyzed_size": [100, 50], "sharpness": 500, "exposure": 0.8,
            "faces": [{"box": [20, 10, 20, 20], "sharpness": sharpness,
                       "person": person, "eyes": eyes, "expression": "unknown"}]}


class ReviewTests(unittest.TestCase):
    def apply(self, photos, entries):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.json"
            path.write_text(json.dumps({"version": 1, "photos": entries}), encoding="utf-8")
            apply_review(photos, path)

    def test_merge_split_and_manual_selection(self):
        a, b, c = photo("a"), photo("b"), photo("c")
        self.apply([a, b, c], [{"path": "a", "group": "merge", "selected": False},
                              {"path": "b", "group": "split", "selected": True},
                              {"path": "c", "group": "merge"}])
        groups = dict(regroup([[a, b], [c]]))
        self.assertEqual([p["path"] for p in groups["merge"]], ["a", "c"])
        self.assertEqual(select(groups["merge"], 1), {"c"})
        self.assertEqual(select(groups["split"], 1), {"b"})

    def test_bad_eye_assessment_changes_ranking(self):
        closed = photo("closed", eyes="closed")
        open_eyes = photo("open", eyes="open")
        self.assertGreater(quality(open_eyes), quality(closed))
        self.assertEqual(select([closed, open_eyes], 1), {"open"})
        closed["sharpness"] = 10000
        closed["faces"][0]["sharpness"] = 10000
        self.assertEqual(select([closed, open_eyes], 1), {"open"})

    def test_invalid_review_is_atomic(self):
        a = photo("a")
        with self.assertRaises(ValueError):
            self.apply([a], [{"path": "a", "group": "new"}, {"path": "missing"}])
        self.assertNotIn("group_override", a)
        with self.assertRaises(ValueError):
            self.apply([a], [{"path": "a", "faces": [{"index": 9}]}])

    def test_replacement_requires_same_person_and_improvement(self):
        base = photo("base", eyes="closed")
        other = photo("other", person="p2", eyes="open")
        self.assertEqual(composite_plans([("g", [base, other])], {"g": {"base"}}), [])
        source = photo("source", eyes="open")
        plans = composite_plans([("g", [base, source])], {"g": {"base"}})
        self.assertEqual(plans[0]["replacements"][0]["source"], "source")
        self.assertEqual(plans[0]["status"], "needs_confirmation")

    def test_embedding_similarity(self):
        self.assertAlmostEqual(similarity({"embedding": np.array([1., 0.])},
                                          {"embedding": np.array([1., 0.])}), 1)
        self.assertAlmostEqual(similarity({"embedding": np.array([1., 0.])},
                                          {"embedding": np.array([0., 1.])}), 0)

    def test_full_resolution_face_crop_and_script_escaping(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "face.png"
            Image.new("RGB", (200, 100), "red").save(path)
            p = photo(str(path))
            p["group_override"] = "</script><script>alert(1)</script>"
            p["embedding"] = np.array([1., 0.])
            output = Path(directory) / "output"
            write_report([[p]], [], output, 1)
            with Image.open(output / "faces/00001-0.jpg") as crop:
                self.assertEqual(crop.size, (56, 56))
            report = (output / "index.html").read_text(encoding="utf-8")
            self.assertNotIn(p["group_override"], report)
            review = json.loads((output / "review-template.json").read_text(encoding="utf-8"))
            self.assertEqual(review["photos"][0]["faces"][0]["index"], 0)
