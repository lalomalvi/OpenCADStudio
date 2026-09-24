"""M7 freezer uses six generated images; no reserved user material."""

from pathlib import Path
import tempfile
import unittest

from PIL import Image

from reserved_cohort import CohortError, freeze, verify_sources


class ReservedCohortTests(unittest.TestCase):
    def make_inputs(self, directory):
        root = Path(directory) / "images"
        root.mkdir()
        entries = []
        for index, role in enumerate(("simple", "simple", "medium", "medium",
                                      "adversarial", "adversarial")):
            path = root / f"synthetic-{index}.png"
            Image.new("RGB", (64, 64), (index * 30, 10, 20)).save(path)
            entries.append({"id": f"case-{index}", "role": role, "path": path.resolve()})
        return root.resolve(), entries

    def test_freeze_and_verify_six_cases_without_paths_in_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root, entries = self.make_inputs(directory)
            output = (Path(directory) / "cohort.json").resolve()
            manifest = freeze(entries, input_root=root, forbidden_hashes=set(),
                              output=output, cohort_id="synthetic-six")
            self.assertEqual((manifest["case_count"], manifest["repetition_count"]), (6, 18))
            self.assertEqual(manifest["cases"][0]["repetitions"],
                             ["case-0-r1", "case-0-r2", "case-0-r3"])
            self.assertNotIn(str(root), output.read_text())
            verify_sources(manifest, {item["id"]: item["path"] for item in entries},
                           input_root=root)
            with self.assertRaisesRegex(CohortError, "already exists"):
                freeze(entries, input_root=root, forbidden_hashes=set(),
                       output=output, cohort_id="synthetic-six")

    def test_duplicate_development_and_changed_image_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root, entries = self.make_inputs(directory)
            output = (Path(directory) / "cohort.json").resolve()
            entries[1]["path"] = entries[0]["path"]
            with self.assertRaisesRegex(CohortError, "duplicated"):
                freeze(entries, input_root=root, forbidden_hashes=set(),
                       output=output, cohort_id="synthetic-six")
            entries[1]["path"] = (root / "synthetic-1.png").resolve()
            digest = __import__("hashlib").sha256(entries[0]["path"].read_bytes()).hexdigest()
            with self.assertRaisesRegex(CohortError, "used previously"):
                freeze(entries, input_root=root, forbidden_hashes={digest},
                       output=output, cohort_id="synthetic-six")
            manifest = freeze(entries, input_root=root, forbidden_hashes=set(),
                              output=output, cohort_id="synthetic-six")
            Image.new("RGB", (64, 64), (255, 0, 0)).save(entries[0]["path"])
            with self.assertRaisesRegex(CohortError, "changed"):
                verify_sources(manifest, {item["id"]: item["path"] for item in entries},
                               input_root=root)

    def test_wrong_split_and_source_escape_fail_before_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root, entries = self.make_inputs(directory)
            output = (Path(directory) / "cohort.json").resolve()
            entries[0]["role"] = "medium"
            with self.assertRaisesRegex(CohortError, "requires two"):
                freeze(entries, input_root=root, forbidden_hashes=set(),
                       output=output, cohort_id="synthetic-six")
            entries[0]["role"] = "simple"
            outside = (Path(directory) / "outside.png").resolve()
            Image.new("RGB", (64, 64), (1, 2, 3)).save(outside)
            entries[0]["path"] = outside
            with self.assertRaisesRegex(CohortError, "escapes"):
                freeze(entries, input_root=root, forbidden_hashes=set(),
                       output=output, cohort_id="synthetic-six")
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
