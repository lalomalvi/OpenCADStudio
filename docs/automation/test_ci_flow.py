"""Policy, no-duplicate-dispatch, receipt coverage and runtime integrity tests."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import ci_scope as scope
import ci_runtime as runtime
import fork_sync_ci as coordinator


class FlowTests(unittest.TestCase):
    def test_scope_matrix_and_unknown_fallback(self):
        for paths, required in [([], []), (['docs/a.md'], []),
                                (['README.md', 'AGENTS.md'], []),
                                (['docs/automation/mcp_client.py'], ['python']),
                                (['docs/automation/ci_scope.py'], ['rust_workspace', 'python', 'host']),
                                (['src/io/mod.rs'], ['rust_workspace', 'python', 'host']),
                                (['Cargo.lock'], ['rust_workspace', 'python', 'host']),
                                (['.github/workflows/ci.yml'], ['rust_workspace', 'python', 'host']),
                                (['assets/icon.svg'], ['rust_workspace', 'python', 'host']),
                                (['docs/new.unknown'], ['rust_workspace', 'python', 'host']),
                                (['src/old.rs', 'docs/renamed.md'], ['rust_workspace', 'python', 'host'])]:
            with self.subTest(paths=paths):
                self.assertEqual(scope.requirements(paths)[1], required)
        self.assertIn('host', scope.requirements([], full=True)[1])

    def test_skips_failures_and_missing_jobs_are_not_passes(self):
        selection = {'head': 'a' * 40, 'policy': scope.POLICY,
                     'required': ['rust_workspace', 'python', 'host']}
        results = {'changes': 'success', 'test': 'success',
                   'masterplan-python': 'success', 'host': 'success'}
        self.assertEqual(scope.finalize(selection, results)['status'], 'verified')
        for status in ('failure', 'skipped', 'cancelled', None):
            with self.subTest(status=status):
                with self.assertRaises(ValueError):
                    scope.finalize(selection, {**results, 'host': status})
        with self.assertRaises(ValueError):
            scope.finalize(selection, {**results, 'changes': 'failure'})
        doc = {**selection, 'required': []}
        receipt = scope.finalize(doc, {'changes': 'success', 'test': 'skipped'})
        self.assertEqual(receipt['validated'], [])

    def test_receipt_cannot_cover_different_sha_policy_or_larger_scope(self):
        receipt = {'schema': 'fork-ci-receipt-1', 'policy': scope.POLICY,
                   'head': 'a' * 40, 'status': 'verified', 'validated': ['python'], 'run_id': '4'}
        self.assertTrue(scope.valid_receipt(receipt, 'a' * 40, ['python']))
        self.assertFalse(scope.valid_receipt(receipt, 'a' * 40, ['host']))
        self.assertFalse(scope.valid_receipt(receipt, 'b' * 40, ['python']))
        self.assertFalse(scope.valid_receipt({**receipt, 'policy': 'old'}, 'a' * 40, []))
        with self.assertRaises(ValueError):
            scope.finalize({'head': 'a' * 40, 'required': ['host']}, {'changes': 'success'}, receipt)

    def test_live_run_is_observed_without_dispatch(self):
        with patch.object(coordinator, 'runs', return_value=[
                {'id': 123, 'status': 'in_progress', 'html_url': 'https://example.invalid'}]):
            with patch.object(coordinator, 'gh') as gh:
                self.assertEqual(coordinator.observe('a' * 40, ['host'])['run_id'], 123)
                gh.assert_not_called()

    def fixture_dir(self):
        root = Path(__file__).resolve().parents[2] / 'target/ci-flow-tests'
        root.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=root)

    def test_dispatch_claim_survives_timeout_and_blocks_second_send(self):
        with self.fixture_dir() as directory:
            with patch.object(coordinator.subprocess, 'run', side_effect=coordinator.subprocess.TimeoutExpired('gh', 60)) as send:
                with self.assertRaises(coordinator.subprocess.TimeoutExpired):
                    coordinator.claim_dispatch(directory, 'a' * 40, 'codex/mcp-test', 'b' * 40, 'auto')
                state = coordinator.claim_dispatch(directory, 'a' * 40, 'codex/mcp-test', 'b' * 40, 'auto')
                self.assertEqual(state['state'], 'dispatch_already_claimed')
                self.assertEqual(send.call_count, 1)

    def test_runtime_binds_files_source_version_and_target(self):
        with self.fixture_dir() as directory:
            root = Path(directory)
            (root / 'plugin').mkdir()
            for name in runtime.FILES:
                (root / name).write_bytes(('synthetic artifact ' + name).encode())
            sha, key = 'a' * 40, 'key'
            manifest = {'schema': 'fork-ci-runtime-1', 'source_sha': sha,
                        'source_fingerprint': key, 'platform': 'windows',
                        'rustc': 'host: x86_64-pc-windows-msvc',
                        'build_command': runtime.BUILD,
                        'features': 'rust-embed/debug-embed',
                        'startup_without_source_locales': 'passed',
                        'version': 'revision: ' + sha[:12],
                        'files': {name: {'sha256': runtime.digest(root / name),
                                         'bytes': (root / name).stat().st_size} for name in runtime.FILES}}
            (root / 'runtime.json').write_text(json.dumps(manifest))
            runtime.verify(root, sha, key)
            for wrong_sha, wrong_key in [('b' * 40, key), (sha, 'other')]:
                with self.assertRaises(ValueError):
                    runtime.verify(root, wrong_sha, wrong_key)
            (root / 'plugin/plugin.toml').write_text('tampered')
            with self.assertRaises(ValueError):
                runtime.verify(root, sha, key)
            manifest['files']['plugin/plugin.toml'] = {'sha256': runtime.digest(root / 'plugin/plugin.toml'),
                                                     'bytes': (root / 'plugin/plugin.toml').stat().st_size}
            manifest['version'] += '-dirty'
            (root / 'runtime.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                runtime.verify(root, sha, key)
            manifest['version'] = 'revision: ' + sha[:12]
            manifest['rustc'] = 'host: x86_64-unknown-linux-gnu'
            (root / 'runtime.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                runtime.verify(root, sha, key)

    def test_locale_relocation_is_ci_only_and_restores_after_failure(self):
        with self.fixture_dir() as directory:
            root = Path(directory)
            (root / 'locales').mkdir()
            (root / 'locales/source.ftl').write_text('fixture source\n')
            with patch.dict(runtime.os.environ, {'GITHUB_ACTIONS': 'false'}):
                with self.assertRaises(ValueError):
                    runtime.check_portability(root, root / 'fake.exe')
            def failed_start(*args, **kwargs):
                self.assertFalse((root / 'locales').exists())
                return runtime.subprocess.CompletedProcess(args[0], 101, '', 'missing locales')
            with patch.dict(runtime.os.environ, {'GITHUB_ACTIONS': 'true'}):
                with patch.object(runtime.subprocess, 'run', side_effect=failed_start):
                    with self.assertRaises(ValueError):
                        runtime.check_portability(root, root / 'fake.exe')
            self.assertEqual((root / 'locales/source.ftl').read_text(), 'fixture source\n')


if __name__ == '__main__':
    unittest.main()
