"""Run with python3 scripts/test_release.py; uses only local temporary repositories."""

from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest
from unittest.mock import patch

import release


class ReleaseTests(unittest.TestCase):
    def test_empty_fork_can_prepare_first_release_without_publishing(self):
        with tempfile.TemporaryDirectory() as temp:
            previous = Path.cwd()
            try:
                os.chdir(temp)
                subprocess.run(["git", "init", "-b", "main"], check=True, capture_output=True)
                subprocess.run(["git", "config", "user.name", "Fixture"], check=True)
                subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], check=True)
                Path("Cargo.toml").write_text('[package]\nname = "fixture"\nversion = "0.9.8"\n')
                subprocess.run(["git", "add", "Cargo.toml"], check=True)
                subprocess.run(["git", "commit", "-m", "Initial source"], check=True, capture_output=True)
                def empty_releases(*args):
                    if args[:2] == ("release", "view"):
                        raise subprocess.CalledProcessError(1, ["gh", *args])
                    self.assertEqual(args[:2], ("release", "list"))
                    return []
                output = io.StringIO()
                with patch.dict(os.environ, {"GITHUB_REPOSITORY": "lalomalvi/OpenCADStudio"}), patch.object(release, "gh", side_effect=empty_releases), redirect_stdout(output):
                    release.prepare(False)
                self.assertIn("ready=false", output.getvalue())
                self.assertEqual(release.run("git", "tag", "--list"), "")
                self.assertEqual(release.run("git", "status", "--porcelain"), "")
            finally:
                os.chdir(previous)

    def test_web_source_selection(self):
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/pages.yml").read_text()
        source = workflow.split("      - name: Resolve release source\n", 1)[1]
        script = textwrap.dedent(source.split("        run: |\n", 1)[1].split("\n      - uses:", 1)[0])
        mock_gh = 'gh() { if [ "$1" = release ]; then echo v2026.37; else echo release-sha; fi; }\n'
        cases = (
            ({}, "release-sha", None),
            ({"RELEASE_TAG": "v2026.37", "RELEASE_COMMIT": "release-sha"}, "release-sha", None),
            ({"RELEASE_COMMIT": "wrong-sha"}, None, "Release tag and commit do not match"),
            ({"BUILD_MAIN": "true"}, "main-sha", None),
            ({"BUILD_MAIN": "true", "GITHUB_REF": "refs/heads/other"}, None, "Web hotfixes must run on main"),
        )
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "output"
            for overrides, commit, error in cases:
                with self.subTest(overrides=overrides):
                    output.write_text("")
                    result = subprocess.run(["bash", "-e", "-c", mock_gh + script], text=True, capture_output=True, env={
                        **os.environ, "GITHUB_REPOSITORY": "owner/repo", "GITHUB_REF": "refs/heads/main",
                        "GITHUB_SHA": "main-sha", "GITHUB_OUTPUT": str(output),
                        "RELEASE_TAG": "", "RELEASE_COMMIT": "", "BUILD_MAIN": "false", **overrides,
                    })
                    if error:
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn(error, result.stdout)
                        self.assertEqual(output.read_text(), "")
                    else:
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(output.read_text(), f"tag=v2026.37\ncommit={commit}\n")

    @unittest.skipIf(os.name == "nt", "Standalone rustc lacks Cargo winresource linkage; Windows native Cargo build covers metadata")
    def test_build_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            binary = str(Path(temp) / "build-script")
            subprocess.run(["rustc", str(Path(__file__).resolve().parents[1] / "build.rs"), "-o", binary], check=True)
            for cargo in ("0.9.8", "2026.9.0", "2026.35.0", "2026.53.0", "2027.1.0", "2026.40.1", "2026.9.1"):
                result = subprocess.check_output([binary], text=True, env={**os.environ, "CARGO_PKG_VERSION": cargo})
                self.assertIn(f"cargo:rustc-env=OCS_APP_VERSION={release.display_version(cargo)}\n", result)

    def test_calendar_versions(self):
        self.assertEqual(release.versions("v2026.35"), {
            "version": "2026.35", "cargo": "2026.35.0", "msi": "26.35.0", "tag": "v2026.35",
        })
        self.assertEqual(release.versions("2026.09")["cargo"], "2026.9.0")
        self.assertEqual(release.display_version("2026.9.0"), "2026.09")
        self.assertEqual(release.display_version("0.9.8"), "0.9.8")
        self.assertEqual(datetime(2027, 1, 3, tzinfo=timezone.utc).strftime("v%G.%V"), "v2026.53")
        for value in ("2026.00", "2026.54", "2027.53", "2026.9", "2026.35.0", "bad", "0.09.8"):
            with self.assertRaises(ValueError, msg=value):
                release.versions(value)

    def test_calendar_patch_versions(self):
        self.assertEqual(release.versions("v2026.40.1"), {
            "version": "2026.40.1", "cargo": "2026.40.1", "msi": "26.40.1", "tag": "v2026.40.1",
        })
        self.assertEqual(release.display_version("2026.40.1"), "2026.40.1")
        self.assertEqual(release.display_version("2026.9.1"), "2026.09.1")
        self.assertEqual(release.versions("2026.09.1")["cargo"], "2026.9.1")
        self.assertEqual(release.versions("2026.40.65535")["msi"], "26.40.65535")
        for value in ("2026.40.0", "2026.40.01", "2026.40.65536", "2027.53.1", "2026.00.1"):
            with self.assertRaises(ValueError, msg=value):
                release.versions(value)

    def test_release_commit_push_and_retry(self):
        self._exercise_release_commit_push_and_retry(fork=False)

    def test_fork_release_stays_draft_through_prepare_and_retry(self):
        self._exercise_release_commit_push_and_retry(fork=True)

    def test_prepared_fork_version_tags_reviewed_commit(self):
        self._exercise_release_commit_push_and_retry(fork=True, pre_bumped=True)

    def test_verification_requires_explicit_repository_context(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(release, "gh") as requests:
            with self.assertRaisesRegex(ValueError, "GITHUB_REPOSITORY"):
                release.verify_native("v2026.40")
            requests.assert_not_called()

    def test_fork_refuses_inherited_tag_without_distribution(self):
        def run(*args):
            if args[1:3] == ("status", "--porcelain"):
                return ""
            if args[1:3] == ("tag", "--list"):
                return "v2026.40"
            if args[1:2] == ("rev-parse",):
                return "upstream-only-sha"
            if args[1:3] == ("cat-file", "-e"):
                raise subprocess.CalledProcessError(1, args)
            self.fail(f"Unexpected operation: {args}")
        with patch.object(release, "run", run), patch.object(release, "gh", return_value={"tagName": "v2026.39"}), patch.dict(os.environ, {"GITHUB_REPOSITORY": "lalomalvi/OpenCADStudio", "GITHUB_REF": "refs/heads/main"}), patch.object(release, "datetime") as clock:
            clock.now.return_value = datetime(2026, 9, 28, tzinfo=timezone.utc)
            with self.assertRaisesRegex(ValueError, "lacks the fork distribution"):
                release.prepare(True)

    def _exercise_release_commit_push_and_retry(self, fork, pre_bumped=False):
        original_run = release.run
        releases = {"v0.9.8": {"name": "v0.9.8", "body": "Previous notes", "isDraft": False}}
        latest = "v0.9.8"
        fail_create = False

        def run(*args):
            nonlocal latest, fail_create
            if args[0] != "gh":
                return original_run(*args)
            expected_repo = "lalomalvi/OpenCADStudio" if fork else "owner/repo"
            chosen_repo = args[args.index("--repo") + 1] if "--repo" in args else os.environ.get("GH_REPO")
            self.assertEqual(chosen_repo, expected_repo, "Release operation escaped its repository")
            if args[1:3] == ("release", "list"):
                return json.dumps([{"tagName": tag, "isDraft": False} for tag in releases])
            if args[1:3] == ("release", "create"):
                if fail_create:
                    fail_create = False
                    raise RuntimeError("Temporary release API failure")
                latest = args[3]
                releases[latest] = {
                    "name": args[args.index("--title") + 1],
                    "body": Path(args[args.index("--notes-file") + 1]).read_text(encoding="utf-8"),
                    "isDraft": "--draft" in args,
                }
                self.assertEqual(releases[latest]["isDraft"], fork)
                if fork:
                    self.assertNotIn("--latest", args)
                return ""
            self.assertEqual(args[1:3], ("release", "view"))
            if args[3] == "--json":
                return json.dumps({"tagName": latest})
            return json.dumps(releases[args[3]])

        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            root = temp / "checkout"
            root.mkdir()
            previous_directory = Path.cwd()
            os.chdir(root)
            try:
                original_run("git", "init", "-b", "main")
                original_run("git", "config", "user.name", "Release test")
                original_run("git", "config", "user.email", "test@example.invalid")
                original_run("git", "init", "--bare", "-b", "main", str(temp / "origin.git"))
                original_run("git", "remote", "add", "origin", str(temp / "origin.git"))
                Path("Cargo.toml").write_text('[package]\nname = "OpenCADStudio"\nversion = "0.9.8"\n')
                Path("Cargo.lock").write_text('version = 4\n[[package]]\nname = "OpenCADStudio"\nversion = "0.9.8"\n')
                if fork:
                    Path("scripts").mkdir()
                    Path("scripts/desktop.py").write_text("# fork distribution entrypoint\n")
                original_run("git", "add", ".")
                original_run("git", "commit", "-m", "Initial release")
                original_run("git", "tag", "v0.9.8")
                original_run("git", "push", "origin", "main", "--tags")

                with patch.object(release, "run", run), patch.object(release, "datetime") as clock, patch.dict(os.environ, {
                    "GITHUB_REPOSITORY": "lalomalvi/OpenCADStudio" if fork else "owner/repo", "GITHUB_REF": "refs/heads/main", "GITHUB_OUTPUT": str(temp / "output"),
                    "GH_REPO": "HakanSeven12/OpenCADStudio",
                }):
                    clock.now.return_value = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)

                    def prepare(publish):
                        result = io.StringIO()
                        with redirect_stdout(result):
                            release.prepare(publish)
                        return result.getvalue()

                    self.assertIn("ready=false", prepare(True))
                    Path("feature").write_text("web release source")
                    original_run("git", "add", "feature")
                    original_run("git", "commit", "-m", "Add web release synchronization")
                    reviewed_sha = None
                    if pre_bumped:
                        for version_file in (Path("Cargo.toml"), Path("Cargo.lock")):
                            version_file.write_text(version_file.read_text().replace('version = "0.9.8"', 'version = "2026.35.0"'))
                        original_run("git", "add", "Cargo.toml", "Cargo.lock")
                        original_run("git", "commit", "-m", "Reviewed fork release source")
                        reviewed_sha = original_run("git", "rev-parse", "HEAD")
                    preview = prepare(False)
                    self.assertIn("Add web release synchronization", preview)
                    self.assertEqual(release.cargo_version(), "2026.35.0" if pre_bumped else "0.9.8")
                    self.assertEqual(original_run("git", "tag", "--list", "v2026.35"), "")

                    self.assertIn("ready=true", prepare(True))
                    sha = original_run("git", "rev-parse", "HEAD")
                    self.assertEqual(release.cargo_version(), "2026.35.0")
                    self.assertIn('version = "2026.35.0"', Path("Cargo.lock").read_text())
                    self.assertEqual(original_run("git", "log", "-1", "--format=%s"), "Reviewed fork release source" if pre_bumped else "Release v2026.35")
                    if reviewed_sha:
                        self.assertEqual(sha, reviewed_sha, "Publication must keep the reviewed source commit")
                    self.assertEqual(original_run("git", "rev-parse", "origin/main"), sha)
                    self.assertEqual(original_run("git", "rev-parse", "v2026.35^{commit}"), sha)
                    self.assertEqual(original_run("git", "status", "--porcelain"), "")
                    self.assertIn(f"commit={sha}", prepare(True))

                    clock.now.return_value = datetime(2026, 9, 6, 12, tzinfo=timezone.utc)
                    self.assertIn("ready=false", prepare(True))
                    Path("feature").write_text("next change")
                    original_run("git", "add", "feature")
                    original_run("git", "commit", "-m", "Fix release retry")
                    fail_create = True
                    with self.assertRaises(RuntimeError):
                        prepare(True)
                    sha = original_run("git", "rev-parse", "HEAD")
                    self.assertIn(f"commit={sha}", prepare(True))
                    self.assertEqual(original_run("git", "rev-parse", "HEAD"), sha)
                    self.assertEqual(releases["v2026.36"]["name"], "2026.36")
            finally:
                os.chdir(previous_directory)


if __name__ == "__main__":
    unittest.main()
