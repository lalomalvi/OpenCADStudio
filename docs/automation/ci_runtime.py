"""Package and verify the Windows runner already built by host CI."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from fork_sync import fingerprint, git

FILES = {'OpenCADStudio.exe', 'plugin/opencad_python.dll', 'plugin/plugin.toml'}
BUILD = ['cargo', 'build', '--locked', '--bin', 'OpenCADStudio', '--features', 'rust-embed/debug-embed']


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def verify(directory, expected_sha, expected_fingerprint):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / 'runtime.json').read_text())
    if (manifest.get('schema') != 'fork-ci-runtime-1' or
            manifest.get('source_sha') != expected_sha or
            manifest.get('source_fingerprint') != expected_fingerprint or
            manifest.get('platform') != 'windows' or
            manifest.get('build_command') != BUILD or
            manifest.get('features') != 'rust-embed/debug-embed' or
            manifest.get('startup_without_source_locales') != 'passed' or
            'x86_64-pc-windows-msvc' not in manifest.get('rustc', '') or
            set(manifest.get('files', {})) != FILES):
        raise ValueError('runtime metadata mismatch')
    version = manifest.get('version', '')
    if expected_sha[:12] not in version or 'dirty' in version:
        raise ValueError('runner revision is missing, dirty, or mismatched')
    for name, expected in manifest['files'].items():
        path = directory / name
        if not path.is_file() or path.is_symlink() or directory not in path.resolve().parents:
            raise ValueError('invalid artifact path')
        if path.stat().st_size != expected['bytes'] or digest(path) != expected['sha256']:
            raise ValueError('runtime content mismatch: ' + name)
    return manifest


def check_portability(root, binary):
    # This relocation test is CI-only. Never hide the user's source resources.
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise ValueError('source-relocation check is restricted to the CI checkout')
    root, binary = Path(root).resolve(), Path(binary).resolve()
    locales = root / 'locales'
    if not locales.is_dir() or locales.is_symlink() or root not in locales.resolve().parents:
        raise ValueError('invalid checkout locale path')
    (root / 'target').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root / 'target', prefix='ci-portability-') as directory:
        isolated = Path(directory)
        (isolated / 'profile').mkdir()
        (isolated / 'temp').mkdir()
        env = os.environ.copy()
        env.update(APPDATA=str(isolated / 'profile'), LOCALAPPDATA=str(isolated / 'profile'),
                   TEMP=str(isolated / 'temp'), TMP=str(isolated / 'temp'))
        held = isolated / 'held-locales'
        locales.rename(held)
        try:
            from mcp_client import META
            request = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'server/discover',
                                  'params': {'_meta': META}}) + '\n'
            result = subprocess.run([str(binary), '--mcp'], cwd=root, env=env,
                                    input=request, capture_output=True, text=True, timeout=20)
            replies = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
            if result.returncode or not any(r.get('id') == 1 and 'result' in r for r in replies):
                raise ValueError('runner failed without source locales: ' + result.stderr[:1000])
        finally:
            held.rename(locales)
    return 'passed'


def package(root, out):
    root, out = Path(root).resolve(), Path(out).resolve()
    if root not in out.parents:
        raise ValueError('package must be inside the repository')
    if git(root, 'status', '--porcelain', '--untracked-files=no'):
        raise ValueError('source tree is dirty')
    out.mkdir(parents=True, exist_ok=False)
    (out / 'plugin').mkdir()
    sources = {'OpenCADStudio.exe': root / 'target/debug/OpenCADStudio.exe',
               'plugin/opencad_python.dll': root / 'work/plugin/opencad_python.dll',
               'plugin/plugin.toml': root / 'work/plugin/plugin.toml'}
    for name, source in sources.items():
        shutil.copyfile(source, out / name)
    sha = git(root, 'rev-parse', 'HEAD')
    portability = check_portability(root, out / 'OpenCADStudio.exe')
    manifest = {'schema': 'fork-ci-runtime-1', 'source_sha': sha,
                'source_fingerprint': fingerprint(root, sha), 'platform': 'windows',
                'build_command': BUILD, 'features': 'rust-embed/debug-embed',
                'startup_without_source_locales': portability,
                'rustc': subprocess.check_output(['rustc', '-Vv'], text=True),
                'version': subprocess.check_output([str(out / 'OpenCADStudio.exe'), '--version'], text=True),
                'files': {name: {'sha256': digest(out / name), 'bytes': (out / name).stat().st_size}
                          for name in sorted(FILES)}}
    (out / 'runtime.json').write_text(json.dumps(manifest, indent=2) + '\n')
    verify(out, sha, manifest['source_fingerprint'])
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    package('.', args.out)
