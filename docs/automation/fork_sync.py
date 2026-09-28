"""Freeze a fork-sync snapshot and select work. Never merges, builds or pushes."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import time
import uuid

FORK = 'https://github.com/lalomalvi/OpenCADStudio.git'
UPSTREAM = 'https://github.com/HakanSeven12/OpenCADStudio.git'


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True,
                            timeout=120)
    if result.returncode:
        raise RuntimeError('git command failed: ' + ' '.join(args[:2]))
    return result.stdout.decode('utf-8', errors='strict').strip()


def prose(path):
    return path in {'README.md', 'AGENTS.md'} or (
        path.startswith('docs/') and path.endswith('.md'))


def classify(paths):
    paths = set(paths)
    if not paths:
        return 'no_change'
    if all(prose(p) for p in paths):
        return 'prose'
    if all(prose(p) or (p.startswith('docs/automation/') and
                       p.endswith('.py')) for p in paths):
        return 'python'
    # Unknown paths, manifests, workflows, assets and dependencies stay broad.
    return 'native_or_infrastructure'


def changed(root, base, head):
    # --no-renames includes old and new paths, preventing code -> docs escapes.
    value = git(root, 'diff', '--no-renames', '--name-only', '-z', base, head)
    return [p for p in value.split('\0') if p]


def fingerprint(root, ref):
    entries = git(root, 'ls-tree', '-rz', ref).split('\0')
    relevant = []
    for entry in entries:
        if entry:
            _, path = entry.split('\t', 1)
            if not prose(path):
                relevant.append(entry)
    return hashlib.sha256('\0'.join(sorted(relevant)).encode()).hexdigest()


def validate_remotes(root):
    # Restrict even fetch to the configured pair; do not print credential URLs.
    expected = [('origin', FORK), ('upstream', UPSTREAM)]
    for name, url in expected:
        if git(root, 'remote', 'get-url', '--all', name).splitlines() != [url]:
            raise ValueError('unexpected fetch URL for ' + name)
    if git(root, 'remote', 'get-url', '--push', '--all', 'origin').splitlines() != [FORK]:
        raise ValueError('unexpected push URL for origin')


def make_plan(root, fetch=False, tested_ref=None):
    started = time.monotonic()
    root = Path(git(root, 'rev-parse', '--show-toplevel'))
    validate_remotes(root)
    if fetch:
        for remote in ('origin', 'upstream'):
            git(root, 'fetch', '--no-tags', remote,
                'refs/heads/main:refs/remotes/' + remote + '/main')
    head = git(root, 'rev-parse', 'HEAD')
    upstream = git(root, 'rev-parse', 'upstream/main')
    fork = git(root, 'rev-parse', 'origin/main')
    common = git(root, 'merge-base', head, upstream)
    incoming = changed(root, common, upstream)
    outgoing = changed(root, fork, head)
    tracked_dirty = bool(git(root, 'status', '--porcelain', '--untracked-files=no'))
    untracked = git(root, 'ls-files', '--others', '--exclude-standard', '-z')
    untracked_count = len([p for p in untracked.split('\0') if p])
    kind = classify(incoming + outgoing)
    gates = {
        'no_change': [],
        'prose': ['diff_check', 'review_document_changes'],
        'python': ['diff_check', 'python_automation', 'python_masterplan'],
        'native_or_infrastructure': ['diff_check', 'rust_workspace',
                                     'python_automation', 'python_masterplan',
                                     'review_platform_and_persistence_impact'],
    }[kind]
    known = None
    if tested_ref:
        tested = git(root, 'rev-parse', '--verify', tested_ref + '^{commit}')
        known = {'tested_ref': tested,
                 'same_nonprose_tree': fingerprint(root, tested) == fingerprint(root, head),
                 'note': 'Source equivalence only; does not prove any test ran or passed.'}
    blockers = []
    if tracked_dirty or untracked_count:
        blockers.append('account_for_working_changes_before_merge')
    if git(root, 'merge-base', fork, head) != fork:
        blockers.append('fork_main_is_not_ancestor_of_head')
    return {
        'schema': 'fork-sync-plan-1',
        'created_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'workspace': str(root), 'head': head, 'upstream_snapshot': upstream,
        'fork_snapshot': fork, 'fresh_remote_refs': fetch,
        'incoming_commits': int(git(root, 'rev-list', '--count', head + '..' + upstream)),
        'incoming_paths': incoming, 'outgoing_paths': outgoing,
        'tracked_dirty': tracked_dirty, 'untracked_count': untracked_count,
        'classification': kind, 'required_review': gates, 'blockers': blockers,
        'source_equivalence': known, 'nonprose_fingerprint': fingerprint(root, head),
        'publish_destination': FORK, 'merge_ref': upstream,
        'note': 'Plan only. Freeze merge_ref for this cycle; new upstream commits wait for the next cycle. '
                'After merging, reassess the committed candidate before selecting final checks.',
        'duration_s': round(time.monotonic() - started, 3),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default='.')
    parser.add_argument('--fetch', action='store_true')
    parser.add_argument('--tested-ref')
    args = parser.parse_args()
    try:
        plan = make_plan(args.repo, args.fetch, args.tested_ref)
        out = Path(plan['workspace']) / 'target/fork-sync' / (
            dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
        out.mkdir(parents=True, exist_ok=False)
        (out / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({key: plan[key] for key in (
            'head', 'upstream_snapshot', 'fork_snapshot', 'fresh_remote_refs',
            'incoming_commits', 'classification', 'required_review', 'blockers',
            'source_equivalence', 'duration_s')}, indent=2))
        print('Evidence:', out / 'plan.json')
        return 2 if plan['blockers'] else 0
    except (ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print('Preflight failed:', type(exc).__name__, str(exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
