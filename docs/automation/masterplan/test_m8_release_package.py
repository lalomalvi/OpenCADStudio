import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from m8_release_package import (BINARY_MEMBER, SOURCE_FILES, ZIP_NAME,
                                ReleasePackageError, _check_import_closure,
                                _zip_info, binary_source_revision, sha256,
                                sha256_bytes, verify)


class ReleasePackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()
        payload = {}
        for member in set(SOURCE_FILES) | {BINARY_MEMBER}:
            if member == BINARY_MEMBER:
                header = bytearray(128)
                header[:2] = b"MZ"
                header[0x3C:0x40] = struct.pack("<I", 0x40)
                header[0x40:0x44] = b"PE\0\0"
                header[0x44:0x46] = struct.pack("<H", 0x8664)
                data = bytes(header)
            else:
                data = member.encode()
            path = self.bundle / member
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            payload[member] = data
        manifest = {"schema_version": "m8-local-release-bundle-1",
                    "status": "candidate_partial_m7_gates_open",
                    "platform": "windows-x86_64", "pe_machine": "AMD64-0x8664",
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

    def test_stage_revision_must_match_source_commit(self):
        binary = Path("synthetic-release.exe")
        source_sha = "a" * 40
        response = subprocess.CompletedProcess([], 0,
            stdout="OpenCADStudio 2026.38\nrevision: aaaaaaaaaaaa\nprofile: release\n")
        with patch("m8_release_package.subprocess.run", return_value=response):
            self.assertEqual(binary_source_revision(binary, source_sha), "a" * 12)
        response.stdout = "OpenCADStudio 2026.38\nrevision: bbbbbbbbbbbb\n"
        with patch("m8_release_package.subprocess.run", return_value=response):
            with self.assertRaisesRegex(ReleasePackageError, "differs from source"):
                binary_source_revision(binary, source_sha)

    def test_bundle_rejects_claimed_binary_revision_mismatch(self):
        manifest = json.loads(self.manifest_bytes)
        manifest["binary_source_revision"] = "b" * 12
        (self.bundle / "manifest.json").write_text(json.dumps(manifest) + "\n")
        with self.assertRaisesRegex(ReleasePackageError, "binary revision differs"):
            verify(self.root)


if __name__ == "__main__":
    unittest.main()
