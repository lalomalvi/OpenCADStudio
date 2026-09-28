"""Boundary tests plus optional real distributed-binary integration tests."""
import os
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import desktop


class DesktopBoundaries(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="OCS path with spaces ")
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_tools_diagnose_without_writes(self):
        with patch.dict(os.environ, {"CARGO_HOME": str(self.root / "absent")}), patch("desktop.shutil.which", return_value=None):
            info = desktop.diagnose()
        self.assertEqual(info["tools"]["cargo"]["status"], "missing")
        self.assertTrue(any("cargo missing" in b for b in info["blockers"]))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_installed_tool_outside_path_is_not_missing(self):
        exe = self.root / "cargo.exe"
        exe.touch()
        with patch("desktop.shutil.which", return_value=None):
            info = desktop.tool("cargo", [exe])
        self.assertEqual(info["status"], "installed_outside_PATH")
        self.assertEqual(info["path"], str(exe.resolve()))

    def test_absent_installation_has_concrete_recovery(self):
        with self.assertRaisesRegex(desktop.Blocked, "run build then install"):
            desktop.resolve(self.root)

    def test_download_hash_failure_precedes_extraction(self):
        archive = self.root / "wrong.zip"
        archive.write_bytes(b"wrong")
        with self.assertRaisesRegex(desktop.Blocked, "SHA-256 mismatch"):
            desktop.install(archive, self.root / "app", self.root, "0" * 64)
        self.assertFalse((self.root / "app").exists())

    def test_archive_traversal_is_rejected(self):
        for name in ("../escape.exe", "C:/escape.exe", "safe/../../escape", "safe\\..\\escape"):
            with self.subTest(name=name):
                archive = self.root / "bad.zip"
                with zipfile.ZipFile(archive, "w") as z:
                    z.writestr(name, "bad")
                with self.assertRaises(desktop.Blocked):
                    desktop.unpack(archive, self.root / "output")
        self.assertFalse((self.root / "output").exists())

    def test_arguments_with_spaces_are_not_shell_code(self):
        script = self.root / "argument check.py"
        script.write_text("import sys; print(sys.argv[1])")
        self.assertEqual(desktop.run([sys.executable, script, "space ; $value ' literal"], cwd=self.root), "space ; $value ' literal")

    @unittest.skipUnless(os.name == "nt", "Native PowerShell entrypoint requires Windows")
    def test_powershell_from_external_directory_resolves_python_and_missing_install(self):
        shell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        result = subprocess.run([str(shell), "-NoProfile", "-File", str(desktop.ROOT / "scripts/desktop.ps1"),
                                 "path", "--install-dir", str(self.root / "missing installation")],
                                cwd=self.root.resolve(), capture_output=True, encoding="utf-8", errors="replace")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("No managed installation", result.stderr)

    def test_mcp_timeout_kills_owned_process(self):
        script = self.root / "stall.py"
        script.write_text("import time; time.sleep(30)")
        real_popen = subprocess.Popen
        with patch.object(desktop.smoke.subprocess, "Popen", side_effect=lambda *a, **kw: real_popen([sys.executable, str(script)], **kw)), patch.object(desktop.smoke, "TIMEOUT", 0.1):
            process = desktop.smoke.start(script)
            with self.assertRaises(Exception):
                desktop.smoke.request(process, {"jsonrpc": "2.0", "id": 1, "method": "ping"})
        self.assertIsNotNone(process.poll())


class DistributedIntegration(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("OCS_TEST_PACKAGE"), "Set OCS_TEST_PACKAGE to a real built ZIP")
    def test_real_package_outside_checkout_repeat_install_and_corruption(self):
        with tempfile.TemporaryDirectory(prefix="OCS installed path with spaces ") as temporary:
            root = Path(temporary)
            package = Path(os.environ["OCS_TEST_PACKAGE"]).resolve()
            first_log, second_log = root / "first logs", root / "second logs"
            first_log.mkdir()
            second_log.mkdir()
            state = desktop.install(package, root / "user application", first_log)
            repeated = desktop.install(package, root / "user application", second_log)
            self.assertEqual(state["executable"], repeated["executable"])
            self.assertTrue(Path(state["executable"]).is_file())
            self.assertEqual(len([p for p in (root / "user application").iterdir() if p.is_dir()]), 1)
            self.assertEqual(desktop.resolve(root / "user application")["executable"], state["executable"])
            if os.name == "nt":
                command = ["powershell.exe", "-NoProfile", "-File", str(desktop.ROOT / "scripts/desktop.ps1")]
            else:
                command = ["bash", str(desktop.ROOT / "scripts/desktop-macos.sh")]
            fragment = json.loads(desktop.run(command + ["config", "--install-dir", str(root / "user application")], cwd=root.resolve()))
            self.assertEqual(fragment["command"], state["executable"])
            self.assertEqual(fragment["args"], ["--mcp"])
            client = desktop.smoke.start(Path(state["executable"]), cwd=root.resolve(),
                                        env={**os.environ, "OCS_CONFIG_DIR": str(root / "wrapper private config")},
                                        command=command + ["mcp", "--install-dir", str(root / "user application")])
            reply = desktop.smoke.request(client, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                                  "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                                                             "clientInfo": {"name": "wrapper-test", "version": "1"}}})
            self.assertEqual(reply["result"]["protocolVersion"], "2025-11-25")
            tools = desktop.smoke.request(client, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            self.assertEqual({t["name"] for t in tools["result"]["tools"]}, desktop.smoke.TOOLS)
            desktop.smoke.close(client)
            executable = Path(state["executable"])
            removed = executable.with_suffix(".removed")
            executable.rename(removed)
            with self.assertRaises((desktop.Blocked, FileNotFoundError)):
                desktop.resolve(root / "user application")
            removed.rename(executable)
            payload = Path(state["payload"])
            manifest = json.loads((payload / "distribution.json").read_text(encoding="utf-8"))
            resources = [name for name in manifest["files"] if name.endswith(".dll") or "/Resources/" in name]
            self.assertTrue(resources, "Real package should have its audited native runtime or bundle resources")
            with (payload / resources[0]).open("ab") as resource:
                resource.write(b"\0")
            with self.assertRaisesRegex(desktop.Blocked, "hash mismatch"):
                desktop.resolve(root / "user application")


if __name__ == "__main__":
    unittest.main()
