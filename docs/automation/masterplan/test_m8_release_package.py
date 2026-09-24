import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from m8_release_package import (BINARY_MEMBER, SOURCE_FILES, ZIP_NAME,
                                ReleasePackageError, _check_import_closure,
                                _zip_info, sha256, sha256_bytes, verify)


class ReleasePackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()
        payload = {}
        for member in set(SOURCE_FILES) | {BINARY_MEMBER}:
            data = b"MZ synthetic" if member == BINARY_MEMBER else member.encode()
            path = self.bundle / member
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            payload[member] = data
        manifest = {"schema_version": "m8-local-release-bundle-1",
                    "status": "candidate_partial_m7_gates_open",
                    "source_git_sha": "a" * 40,
                    "files": {name: {"sha256": sha256_bytes(data), "bytes": len(data)}
                              for name, data in payload.items()},
                    "cargo_lock_sha256": sha256_bytes(payload["Cargo.lock"])}
        self.manifest_bytes = (json.dumps(manifest) + "\n").encode()
        (self.bundle / "manifest.json").write_bytes(self.manifest_bytes)
        self.archive = self.root / ZIP_NAME
        with zipfile.ZipFile(self.archive, "x") as handle:
            for name, data in payload.items():
                handle.writestr(_zip_info(name), data)
            handle.writestr(_zip_info("manifest.json"), self.manifest_bytes)
        (self.root / "archive.sha256").write_text(sha256(self.archive) + "\n")

    def test_bundle_verifies_and_rejects_changed_extracted_file(self):
        self.assertEqual(verify(self.root)["status"], "passed_bundle_integrity")
        (self.bundle / "Cargo.lock").write_bytes(b"changed")
        with self.assertRaisesRegex(ReleasePackageError, "Bundle file changed"):
            verify(self.root)

    def test_rejects_extra_archive_member_even_with_rehashed_archive(self):
        with zipfile.ZipFile(self.archive, "a") as handle:
            handle.writestr(_zip_info("private.dwg"), b"private")
        (self.root / "archive.sha256").write_text(sha256(self.archive) + "\n")
        with self.assertRaisesRegex(ReleasePackageError, "Archive member allowlist"):
            verify(self.root)

    def test_bundle_source_import_closure_is_explicit(self):
        repo = Path(__file__).resolve().parents[3]
        _check_import_closure(repo)


if __name__ == "__main__":
    unittest.main()
