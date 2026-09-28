"""Observe/start one unified CI run; download its verified runner without rebuilding."""
import argparse
import datetime as dt
import io
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
import zipfile
from urllib.parse import quote
from fork_sync import fingerprint, git, validate_remotes
from ci_scope import valid_receipt

REPO = 'lalomalvi/OpenCADStudio'


def gh(*args, binary=False):
    result = subprocess.run(['gh', *args], capture_output=True, timeout=180)
    if result.returncode:
        raise RuntimeError('GitHub request failed; inspect existing run before retrying a dispatch')
    return result.stdout if binary else json.loads(result.stdout or 'null')


def runs(sha):
    payload = gh('api', f'repos/{REPO}/actions/workflows/ci.yml/runs?head_sha={sha}&per_page=100')
    return [r for r in payload['workflow_runs'] if r['head_sha'] == sha]


def receipt_for_run(run_id, sha):
    run_id = str(int(run_id))
    run = gh('api', f'repos/{REPO}/actions/runs/{run_id}')
    if run['head_sha'] != sha or run['status'] != 'completed' or run['conclusion'] != 'success':
        raise ValueError('run is not a successful check of the expected commit')
    artifacts = gh('api', f'repos/{REPO}/actions/runs/{run_id}/artifacts')['artifacts']
    matches = [a for a in artifacts if a['name'] == 'sync-evidence' and not a['expired']]
    if len(matches) != 1 or matches[0]['size_in_bytes'] > 131072:
        raise ValueError('verification artifact missing or invalid')
    data = gh('api', f"repos/{REPO}/actions/artifacts/{matches[0]['id']}/zip", binary=True)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if archive.namelist() != ['verification.json'] or archive.getinfo('verification.json').file_size > 131072:
            raise ValueError('invalid receipt archive')
        receipt = json.loads(archive.read('verification.json'))
    if str(receipt.get('run_id')) != run_id or not valid_receipt(receipt, sha, []):
        raise ValueError('receipt binding mismatch')
    return receipt


def successful_receipt(sha, required, exclude=None):
    for run in runs(sha):
        if str(run['id']) == str(exclude) or run['status'] != 'completed' or run['conclusion'] != 'success':
            continue
        try:
            receipt = receipt_for_run(run['id'], sha)
            if valid_receipt(receipt, sha, required) and not receipt.get('reused_run'):
                return receipt
        except ValueError:
            continue
    return None


def observe(sha, required):
    existing = runs(sha)
    for run in existing:
        if run['status'] != 'completed':
            return {'state': 'running', 'run_id': run['id'], 'url': run['html_url']}
    receipt = successful_receipt(sha, required)
    if receipt:
        return {'state': 'verified', 'run_id': receipt['run_id'], 'validated': receipt['validated']}
    if existing:
        return {'state': 'failed_or_insufficient', 'run_ids': [r['id'] for r in existing]}
    return {'state': 'absent'}


def claim_dispatch(root, sha, ref, base, scope):
    out = Path(root) / 'target/fork-sync-ci'
    out.mkdir(parents=True, exist_ok=True)
    claim = out / (sha + '.dispatch.json')
    try:
        fd = os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return {'state': 'dispatch_already_claimed', 'claim': str(claim)}
    record = {'head': sha, 'ref': ref, 'base': base, 'scope': scope,
              'started_at': dt.datetime.now(dt.timezone.utc).isoformat(),
              'state': 'dispatch_pending_or_uncertain'}
    with os.fdopen(fd, 'w') as stream:
        json.dump(record, stream, indent=2)
    # A failed/expired observation must never automatically repeat this mutation.
    subprocess.run(['gh', 'workflow', 'run', 'ci.yml', '--repo', REPO, '--ref', ref,
                    '-f', 'base_ref=' + base, '-f', 'scope=' + scope],
                   check=True, capture_output=True, timeout=60)
    record['state'] = 'dispatched'
    claim.write_text(json.dumps(record, indent=2) + '\n')
    return record



def start_when_absent(root, sha, ref, base, scope):
    # PR events can take several seconds to become visible in Actions. An open
    # PR at this exact revision already requests Tests; never race that trigger.
    pulls = gh('api', f'repos/{REPO}/pulls?state=open&head={quote("lalomalvi:" + ref, safe="")}&per_page=100')
    for pull in pulls:
        head = pull.get('head', {})
        if pull.get('state') == 'open' and head.get('sha') == sha and (head.get('repo') or {}).get('full_name') == REPO:
            return {'state': 'awaiting_pull_request_run', 'pull_request': pull['number'],
                    'url': pull['html_url'], 'reason': 'automatic Tests trigger not visible yet; observe again without dispatch'}
    return claim_dispatch(root, sha, ref, base, scope)


def download_runtime(root, sha, run_id):
    from ci_runtime import verify
    receipt = receipt_for_run(run_id, sha)
    if 'host' not in receipt['validated']:
        raise ValueError('host was not validated; no runner can be reused')
    # Reused runs point to the actual producer, which must itself be successful.
    producer = receipt['reused_run'] or receipt['run_id']
    producer_receipt = receipt_for_run(producer, sha)
    if 'host' not in producer_receipt['validated'] or producer_receipt['reused_run']:
        raise ValueError('runtime producer must be a direct host-validation run')
    out = Path(root) / 'target/fork-sync-ci' / ('runtime-' + sha[:12] + '-' + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    subprocess.run(['gh', 'run', 'download', str(producer), '--repo', REPO,
                    '--name', 'runner-windows', '--dir', str(out)],
                   check=True, capture_output=True, timeout=180)
    manifest = verify(out, sha, fingerprint(root, sha))
    return {'directory': str(out), 'source_sha': sha,
            'binary_sha256': manifest['files']['OpenCADStudio.exe']['sha256'],
            'producer_run': producer}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default='.')
    parser.add_argument('--start', action='store_true')
    parser.add_argument('--base')
    parser.add_argument('--full', action='store_true')
    parser.add_argument('--artifact', action='store_true')
    parser.add_argument('--reuse-ref')
    args = parser.parse_args()
    root = Path(git(args.repo, 'rev-parse', '--show-toplevel'))
    validate_remotes(root)
    head = git(root, 'rev-parse', 'HEAD')
    sha = git(root, 'rev-parse', '--verify', args.reuse_ref + '^{commit}') if args.reuse_ref else head
    if fingerprint(root, head) != fingerprint(root, sha):
        raise ValueError('sources differ from reuse reference')
    from ci_scope import select
    selection = select(root, args.base or 'origin/main', args.full)
    required = sorted(set(selection['required'] + (['host'] if args.artifact else [])))
    state = observe(sha, required)
    if args.start and state['state'] == 'absent':
        if args.reuse_ref or git(root, 'status', '--porcelain'):
            raise ValueError('dispatch requires a clean current candidate')
        ref = git(root, 'branch', '--show-current')
        remote = git(root, 'ls-remote', 'https://github.com/' + REPO + '.git', 'refs/heads/' + ref)
        if not ref or not remote or remote.split()[0] != head:
            raise ValueError('publish candidate branch before dispatch')
        state = start_when_absent(root, head, ref, selection['base'] or '',
                               'full' if args.full else 'auto')
    if args.artifact:
        if state['state'] != 'verified':
            raise ValueError('runner unavailable until verification is successful')
        state['runtime'] = download_runtime(root, sha, state['run_id'])
    print(json.dumps({'head': head, 'tested_head': sha,
                      'required': required, **state}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print('CI coordination failed:', type(exc).__name__, str(exc))
        raise SystemExit(1)
