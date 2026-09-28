"""Shared CI scope policy and explicit verification receipt (stdlib only)."""
import argparse
import json
import os
from pathlib import Path
import sys
from fork_sync import changed, classify, fingerprint, git

POLICY = 'fork-ci-2'
POLICY_FILES = {'docs/automation/ci_scope.py', 'docs/automation/ci_runtime.py'}


def requirements(paths, full=False):
    kind = classify(paths)
    if full or POLICY_FILES.intersection(paths):
        kind = 'native_or_infrastructure'
    return kind, {
        'no_change': [], 'prose': [], 'python': ['python'],
        'native_or_infrastructure': ['rust_workspace', 'python', 'host'],
    }[kind]


def select(root, base=None, full=False):
    head = git(root, 'rev-parse', 'HEAD')
    # Missing/new-branch bases must never silently downgrade native verification.
    try:
        base = git(root, 'rev-parse', '--verify', str(base) + '^{commit}')
        paths = changed(root, base, head)
    except RuntimeError:
        base, paths, full = None, [], True
    kind, required = requirements(paths, full)
    if base:
        git(root, 'diff', '--check', base, head)
    return {'policy': POLICY, 'head': head, 'base': base, 'classification': kind,
            'paths': paths, 'required': required,
            'source_fingerprint': fingerprint(root, head)}


def finalize(selection, results, reused=None):
    if results.get('changes') != 'success':
        raise ValueError('scope selection did not succeed')
    required = selection['required']
    if reused:
        if not valid_receipt(reused, selection['head'], required):
            raise ValueError('reused receipt does not cover this selection')
        validated = reused['validated']
    else:
        jobs = {'rust_workspace': 'test', 'python': 'masterplan-python', 'host': 'host'}
        for scope in required:
            if results.get(jobs[scope]) != 'success':
                raise ValueError('required job not successful: ' + scope)
        validated = required
    return {**selection, 'schema': 'fork-ci-receipt-1', 'validated': validated,
            'job_results': results, 'status': 'verified',
            'reused_run': reused.get('run_id') if reused else None,
            'run_id': os.environ.get('GITHUB_RUN_ID')}


def valid_receipt(receipt, sha, required):
    return (receipt.get('schema') == 'fork-ci-receipt-1' and
            receipt.get('policy') == POLICY and receipt.get('status') == 'verified' and
            receipt.get('head') == sha and isinstance(receipt.get('validated'), list) and
            set(required).issubset(receipt['validated']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['select', 'finalize'])
    parser.add_argument('--base')
    parser.add_argument('--full', action='store_true')
    parser.add_argument('--from-event', action='store_true')
    args = parser.parse_args()
    root = Path(git('.', 'rev-parse', '--show-toplevel'))
    out = root / 'target/ci-scope'
    out.mkdir(parents=True, exist_ok=True)
    if args.operation == 'select':
        base, full = args.base, args.full
        if args.from_event:
            event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
            full = full or os.environ.get('SCOPE') == 'full'
            if not base:
                if 'pull_request' in event:
                    base = event['pull_request']['base']['sha']
                elif event.get('before') and event['before'] != '0' * 40:
                    base = event['before']
                else:
                    base = 'origin/' + event['repository']['default_branch']
        selection = select(root, base, full)
        reuse = None
        if os.environ.get('GITHUB_REPOSITORY') == 'lalomalvi/OpenCADStudio':
            from fork_sync_ci import successful_receipt
            # Observation errors are not proof of reuse; run the required checks.
            try:
                reuse = successful_receipt(selection['head'], selection['required'],
                                           exclude=os.environ.get('GITHUB_RUN_ID'))
            except (RuntimeError, ValueError):
                pass
        selection['reuse_run'] = reuse['run_id'] if reuse else ''
        (out / 'selection.json').write_text(json.dumps(selection, indent=2) + '\n')
        values = {scope: str(scope in selection['required'] and not reuse).lower()
                  for scope in ('rust_workspace', 'python', 'host')}
        values['reuse_run'] = selection['reuse_run']
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
                for key, value in values.items():
                    output.write(f'{key}={value}\n')
        print(json.dumps(selection, indent=2))
    else:
        selection = json.loads((out / 'selection.json').read_text())
        results = {key: value['result'] for key, value in json.loads(os.environ['NEEDS_JSON']).items()}
        reuse = None
        if selection['reuse_run']:
            from fork_sync_ci import receipt_for_run
            reuse = receipt_for_run(selection['reuse_run'], selection['head'])
        receipt = finalize(selection, results, reuse)
        (out / 'verification.json').write_text(json.dumps(receipt, indent=2) + '\n')
        summary = '\n'.join([
            '### Fork sync verification', f"Commit: `{receipt['head']}`",
            f"Scope: `{receipt['classification']}`",
            f"Required: {', '.join(receipt['required']) or 'none (prose/no change)'}",
            f"Validated: {', '.join(receipt['validated']) or 'none; no tests claimed'}",
            f"Reused run: {receipt['reused_run'] or 'none'}",
            'Jobs outside the required scope are not test passes.', ''])
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
                stream.write(summary)
        print(summary)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, KeyError) as exc:
        print('Verification failed:', exc, file=sys.stderr)
        raise SystemExit(1)
