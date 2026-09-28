"""Package and verify the Windows runner already built by host CI."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from fork_sync import fingerprint, git

FILES = {'OpenCADStudio.exe', 'plugin/opencad_python.dll', 'plugin/plugin.toml'}


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
            manifest.get('build_command') != ['cargo', 'build', '--locked', '--bin', 'OpenCADStudio'] or
            manifest.get('features') != 'default' or
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
    manifest = {'schema': 'fork-ci-runtime-1', 'source_sha': sha,
                'source_fingerprint': fingerprint(root, sha), 'platform': 'windows',
                'build_command': ['cargo', 'build', '--locked', '--bin', 'OpenCADStudio'],
                'features': 'default',
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
