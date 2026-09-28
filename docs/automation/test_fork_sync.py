"""Regression coverage for sync scope and source-evidence reuse."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import fork_sync as sync


class SyncPolicyTests(unittest.TestCase):
    def test_scopes(self):
        for paths, kind in [([], 'no_change'), (['docs/a.md'], 'prose'),
                            (['AGENTS.md', 'README.md'], 'prose'),
                            (['docs/automation/test_a.py', 'docs/a.md'], 'python'),
                            (['docs/automation/fixture.json'], 'native_or_infrastructure'),
                            (['src/io/mod.rs'], 'native_or_infrastructure'),
                            (['Cargo.lock'], 'native_or_infrastructure'),
                            (['.github/workflows/ci.yml'], 'native_or_infrastructure'),
                            (['new.unknown'], 'native_or_infrastructure')]:
            with self.subTest(paths=paths):
                self.assertEqual(sync.classify(paths), kind)

    def test_old_code_path_prevents_rename_downgrade(self):
        self.assertEqual(sync.classify(['src/io.rs', 'docs/io.md']),
                         'native_or_infrastructure')

    def test_repo_snapshot_and_equivalence(self):
        # Unique synthetic git repo; no global config or user's repository writes.
        test_root = Path(__file__).resolve().parents[2] / 'target/fork-sync-tests'
        test_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as directory:
            root = Path(directory)
            sync.git(root, 'init', '-q')
            sync.git(root, 'config', 'user.name', 'Fixture')
            sync.git(root, 'config', 'user.email', 'fixture@example.invalid')
            sync.git(root, 'remote', 'add', 'origin', sync.FORK)
            sync.git(root, 'remote', 'add', 'upstream', sync.UPSTREAM)
            (root / 'src').mkdir()
            (root / 'src/main.rs').write_text('fn main() {}\n')
            sync.git(root, 'add', '.')
            sync.git(root, '-c', 'commit.gpgsign=false', 'commit', '-qm', 'base')
            base = sync.git(root, 'rev-parse', 'HEAD')
            for remote in ('origin', 'upstream'):
                sync.git(root, 'update-ref', 'refs/remotes/' + remote + '/main', base)
            plan = sync.make_plan(root, tested_ref=base)
            self.assertEqual(plan['classification'], 'no_change')
            self.assertFalse(plan['required_review'])
            self.assertFalse(plan['fresh_remote_refs'])
            (root / 'README.md').write_text('description\n')
            sync.git(root, 'add', '.')
            sync.git(root, '-c', 'commit.gpgsign=false', 'commit', '-qm', 'docs')
            plan = sync.make_plan(root, tested_ref=base)
            self.assertEqual(plan['classification'], 'prose')
            self.assertTrue(plan['source_equivalence']['same_nonprose_tree'])
            frozen_upstream = plan['upstream_snapshot']
            (root / 'src/main.rs').write_text('fn main() { println!("changed"); }\n')
            self.assertIn('account_for_working_changes_before_merge', sync.make_plan(root)['blockers'])
            sync.git(root, 'add', '.')
            sync.git(root, '-c', 'commit.gpgsign=false', 'commit', '-qm', 'code')
            plan = sync.make_plan(root, tested_ref=base)
            self.assertFalse(plan['source_equivalence']['same_nonprose_tree'])
            self.assertEqual(plan['classification'], 'native_or_infrastructure')
            self.assertEqual(plan['upstream_snapshot'], frozen_upstream)
            incoming = sync.git(root, 'rev-parse', 'HEAD')
            sync.git(root, 'update-ref', 'refs/remotes/upstream/main', incoming)
            sync.git(root, 'checkout', '--detach', '-q', base)
            snapshot = sync.make_plan(root)
            self.assertEqual(snapshot['incoming_commits'], 2)
            self.assertEqual(snapshot['classification'], 'native_or_infrastructure')
            sync.git(root, 'update-ref', 'refs/remotes/upstream/main', base)
            self.assertEqual(snapshot['merge_ref'], incoming)
            self.assertEqual(sync.make_plan(root)['incoming_commits'], 0)
            (root / 'private.dwg').write_bytes(b'synthetic placeholder, not a drawing')
            plan = sync.make_plan(root)
            self.assertEqual(plan['untracked_count'], 1)
            self.assertIn('account_for_working_changes_before_merge', plan['blockers'])
            self.assertNotIn('private.dwg', str(plan))
            sync.git(root, 'config', 'remote.origin.pushurl', sync.UPSTREAM)
            with self.assertRaises(ValueError):
                sync.make_plan(root)

    def test_fetch_uses_only_validated_remotes(self):
        with patch.object(sync, 'validate_remotes', side_effect=ValueError('wrong remote')):
            with patch.object(sync, 'git', return_value='.') as git:
                with self.assertRaises(ValueError):
                    sync.make_plan('.', fetch=True)
                self.assertFalse(any('fetch' in call.args for call in git.call_args_list))


if __name__ == '__main__':
    unittest.main()
