"""Synthetic M7 oracle freeze tests; no reserved user image is loaded."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

from reserved_cohort import freeze as freeze_cohort
from reserved_oracle import OracleError, freeze, verify_ready


class ReservedOracleTests(unittest.TestCase):
    def make_inputs(self, directory):
        root = (Path(directory) / "images").resolve()
        oracle_root = (Path(directory) / "oracles").resolve()
        root.mkdir()
        oracle_root.mkdir()
        entries = []
        for index, role in enumerate(("simple", "simple", "medium", "medium",
                                      "adversarial", "adversarial")):
            path = root / f"synthetic-{index}.png"
            Image.new("RGB", (64, 64), (index * 30, 10, 20)).save(path)
            entries.append({"id": f"case-{index}", "role": role, "path": path})
        cohort_path = (Path(directory) / "cohort.json").resolve()
        cohort = freeze_cohort(entries, input_root=root, forbidden_hashes=set(),
                               output=cohort_path, cohort_id="synthetic-six")
        oracle_paths = {}
        for case in cohort["cases"]:
            name = case["id"]
            path = oracle_root / f"{name}.json"
            oracle = {"schema_version": "m7-case-oracle-1", "case_id": name,
                      "source_sha256": case["source"]["sha256"],
                      "verification": {"kind": "human_verified",
                                       "reference": "synthetic-review"},
                      "checks": {category: [{"id": f"{category}-1",
                                            "criterion": f"Synthetic {category} criterion"}]
                                 for category in ("metric", "topology", "semantic", "visual")}}
            path.write_text(json.dumps(oracle) + "\n", encoding="utf-8")
            oracle_paths[name] = path
        image_paths = {entry["id"]: entry["path"] for entry in entries}
        return root, cohort_path, image_paths, oracle_root, oracle_paths

    def test_freeze_and_preflight_are_path_free_and_bound_to_all_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root, cohort, images, oracle_root, oracles = self.make_inputs(directory)
            manifest_path = (Path(directory) / "oracle-freeze.json").resolve()
            manifest = freeze(cohort, images, input_root=root, oracle_paths=oracles,
                              oracle_root=oracle_root, output=manifest_path)
            self.assertEqual((manifest["case_count"], manifest["repetition_count"]), (6, 18))
            self.assertEqual(sum(case["check_count"] for case in manifest["cases"]), 24)
            self.assertNotIn(str(root), manifest_path.read_text(encoding="utf-8"))
            self.assertNotIn(str(oracle_root), manifest_path.read_text(encoding="utf-8"))
            self.assertNotIn("Synthetic metric criterion", manifest_path.read_text(encoding="utf-8"))
            ready = verify_ready(cohort, images, input_root=root,
                                 oracle_manifest_path=manifest_path, oracle_paths=oracles,
                                 oracle_root=oracle_root)
            self.assertEqual(ready["status"], "ready_for_L3")
            with self.assertRaisesRegex(OracleError, "New oracle manifest"):
                freeze(cohort, images, input_root=root, oracle_paths=oracles,
                       oracle_root=oracle_root, output=manifest_path)

    def test_changed_oracle_or_image_blocks_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            root, cohort, images, oracle_root, oracles = self.make_inputs(directory)
            manifest_path = (Path(directory) / "oracle-freeze.json").resolve()
            freeze(cohort, images, input_root=root, oracle_paths=oracles,
                   oracle_root=oracle_root, output=manifest_path)
            oracle = json.loads(oracles["case-0"].read_text(encoding="utf-8"))
            oracle["checks"]["metric"][0]["criterion"] = "Changed after freeze"
            oracles["case-0"].write_text(json.dumps(oracle), encoding="utf-8")
            with self.assertRaisesRegex(OracleError, "changed after freeze"):
                verify_ready(cohort, images, input_root=root,
                             oracle_manifest_path=manifest_path, oracle_paths=oracles,
                             oracle_root=oracle_root)
            Image.new("RGB", (64, 64), (255, 255, 255)).save(images["case-1"])
            with self.assertRaisesRegex(OracleError, "images changed"):
                verify_ready(cohort, images, input_root=root,
                             oracle_manifest_path=manifest_path, oracle_paths=oracles,
                             oracle_root=oracle_root)

    def test_missing_category_and_wrong_source_fail_before_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root, cohort, images, oracle_root, oracles = self.make_inputs(directory)
            manifest_path = (Path(directory) / "oracle-freeze.json").resolve()
            oracle = json.loads(oracles["case-0"].read_text(encoding="utf-8"))
            del oracle["checks"]["visual"]
            oracles["case-0"].write_text(json.dumps(oracle), encoding="utf-8")
            with self.assertRaisesRegex(OracleError, "four fidelity"):
                freeze(cohort, images, input_root=root, oracle_paths=oracles,
                       oracle_root=oracle_root, output=manifest_path)
            self.assertFalse(manifest_path.exists())
            oracle["checks"]["visual"] = [{"id": "visual-1", "criterion": "Visible"}]
            oracle["source_sha256"] = "0" * 64
            oracles["case-0"].write_text(json.dumps(oracle), encoding="utf-8")
            with self.assertRaisesRegex(OracleError, "identity or source"):
                freeze(cohort, images, input_root=root, oracle_paths=oracles,
                       oracle_root=oracle_root, output=manifest_path)
            self.assertFalse(manifest_path.exists())

    def test_cli_freeze_then_verify_omits_private_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root, cohort, images, oracle_root, oracles = self.make_inputs(directory)
            image_map = (Path(directory) / "image-map.json").resolve()
            oracle_map = (Path(directory) / "oracle-map.json").resolve()
            image_map.write_text(json.dumps({key: str(path) for key, path in images.items()}),
                                 encoding="utf-8")
            oracle_map.write_text(json.dumps({key: str(path) for key, path in oracles.items()}),
                                  encoding="utf-8")
            manifest = (Path(directory) / "oracle-freeze.json").resolve()
            base = [sys.executable, str(Path(__file__).with_name("reserved_oracle.py")),
                    "--cohort", str(cohort), "--image-root", str(root),
                    "--image-map", str(image_map), "--oracle-root", str(oracle_root),
                    "--oracle-map", str(oracle_map), "--manifest", str(manifest)]
            frozen = subprocess.run(base[:2] + ["freeze"] + base[2:], check=True,
                                    capture_output=True, text=True)
            ready = subprocess.run(base[:2] + ["verify"] + base[2:], check=True,
                                   capture_output=True, text=True)
            self.assertEqual(json.loads(frozen.stdout)["status"], "frozen")
            self.assertEqual(json.loads(ready.stdout)["status"], "ready_for_L3")
            self.assertNotIn(str(root), frozen.stdout + ready.stdout)
            self.assertNotIn(str(oracle_root), frozen.stdout + ready.stdout)

    def test_changed_cohort_bytes_and_unverified_oracle_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root, cohort, images, oracle_root, oracles = self.make_inputs(directory)
            manifest = (Path(directory) / "oracle-freeze.json").resolve()
            freeze(cohort, images, input_root=root, oracle_paths=oracles,
                   oracle_root=oracle_root, output=manifest)
            cohort.write_bytes(cohort.read_bytes() + b"\n")
            with self.assertRaisesRegex(OracleError, "no longer matches frozen cohort"):
                verify_ready(cohort, images, input_root=root,
                             oracle_manifest_path=manifest, oracle_paths=oracles,
                             oracle_root=oracle_root)
        with tempfile.TemporaryDirectory() as directory:
            root, cohort, images, oracle_root, oracles = self.make_inputs(directory)
            manifest = (Path(directory) / "oracle-freeze.json").resolve()
            oracle = json.loads(oracles["case-0"].read_text(encoding="utf-8"))
            oracle["verification"]["reference"] = ""
            oracles["case-0"].write_text(json.dumps(oracle), encoding="utf-8")
            with self.assertRaisesRegex(OracleError, "provenance"):
                freeze(cohort, images, input_root=root, oracle_paths=oracles,
                       oracle_root=oracle_root, output=manifest)
            self.assertFalse(manifest.exists())


if __name__ == "__main__":
    unittest.main()
