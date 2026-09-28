#!/usr/bin/env python3
"""Prepare weekly releases and share package versions across build targets."""

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def run(*args):
    return subprocess.check_output(args, text=True, encoding="utf-8").rstrip("\n")


def gh(*args):
    return json.loads(run("gh", *args))


def versions(tag):
    version = tag.removeprefix("v")
    weekly = re.fullmatch(r"(20\d{2})\.(\d{2})", version)
    if weekly:
        year, week = map(int, weekly.groups())
        date.fromisocalendar(year, week, 1)
        cargo = f"{year}.{week}.0"
        msi = f"{year - 2000}.{week}.0"
    elif re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", version):
        cargo = msi = version
        major, minor, patch = map(int, version.split("."))
        if major > 255 or minor > 255 or patch > 65535:
            raise ValueError(f"Unsupported MSI version: {version}")
    else:
        raise ValueError(f"Invalid release version: {tag}")
    return {"version": version, "cargo": cargo, "msi": msi, "tag": f"v{version}"}


def cargo_version():
    return re.search(r'^version = "([^"]+)"', Path("Cargo.toml").read_text(encoding="utf-8"), re.M)[1]


def display_version(cargo):
    year, week, patch = cargo.split(".")
    if len(year) == 4 and year.startswith("20") and patch == "0":
        return versions(f"{year}.{int(week):02}")["version"]
    return cargo


def output(values):
    lines = "".join(f"{key}={value}\n" for key, value in values.items())
    print(lines, end="")
    if path := os.environ.get("GITHUB_OUTPUT"):
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(lines)


def release_notes(previous, tag, repo, head="HEAD"):
    sections = {
        "Modeling, drawing and annotation": [],
        "Rendering, plotting and file fidelity": [],
        "Interface, web and plugins": [],
        "Maintenance": [],
    }
    entries = run("git", "log", "--first-parent", "--format=%s%x1f%b%x1e", f"{previous}..{head}")
    for entry in entries.split("\x1e"):
        if "\x1f" not in entry:
            continue
        subject, body = entry.strip("\n").split("\x1f", 1)
        if subject.startswith("Merge pull request"):
            subject = next((line for line in body.splitlines() if line.strip()), subject)
        if subject.startswith(("Merge ", "Release v")):
            continue
        subject = re.sub(r"^(?:feat|fix|perf|chore|docs)(?:\([^)]*\))?:\s*", "", subject)
        text = subject.lower()
        if re.search(r"render|plot|print|gpu|buffer|save|file|serializ|vram", text):
            section = "Rendering, plotting and file fidelity"
        elif re.search(r"ui|web|plugin|ribbon|theme|translat|dropdown|mcp|control|cli", text):
            section = "Interface, web and plugins"
        elif re.search(r"kernel|curve|solid|surface|extrud|loft|sweep|revol|presspull|snap|hatch|grip|trim|offset|draw|dimension", text):
            section = "Modeling, drawing and annotation"
        else:
            section = "Maintenance"
        if subject not in sections[section]:
            sections[section].append(subject)
    summary = (f"- {tag.removeprefix('v')} desktop distribution of the lalomalvi fork, including its native MCP."
               if repo == "lalomalvi/OpenCADStudio" else
               f"- Weekly {tag.removeprefix('v')} release for web and desktop from the same source revision.")
    lines = ["## Highlights", "", summary, ""]
    for title, subjects in sections.items():
        if subjects:
            lines += [f"## {title}", ""]
            # ponytail: six recent entries per section; full history is linked below.
            lines += [f"- {subject}" for subject in subjects[:6]]
            lines += [""]
    lines += [f"**Full Changelog:** https://github.com/{repo}/compare/{previous}...{tag}", ""]
    return "\n".join(lines)


def prepare(publish):
    if run("git", "status", "--porcelain"):
        raise ValueError("Release preparation requires a clean working tree")
    repo = os.environ["GITHUB_REPOSITORY"]
    fork = repo == "lalomalvi/OpenCADStudio"
    current = datetime.now(timezone.utc)
    tag = current.strftime("v%G.%V")
    version = versions(tag)
    try:
        latest = gh("release", "view", "--json", "tagName", "--repo", repo)["tagName"]
        first_release = False
    except subprocess.CalledProcessError:
        # An empty fork must be able to prepare its first release. Do not treat
        # an auth/network failure as empty: confirm the release list first.
        if gh("release", "list", "--limit", "1", "--json", "tagName", "--repo", repo):
            raise
        latest = run("git", "rev-list", "--max-parents=0", "HEAD").splitlines()[0]
        first_release = True
    if publish and os.environ.get("GITHUB_REF") != "refs/heads/main":
        raise ValueError("Weekly releases must run on main")
    existing = run("git", "tag", "--list", tag)
    if existing:
        # A retry always uses the original tag, even when main has advanced.
        sha = run("git", "rev-parse", f"{tag}^{{commit}}")
        if fork:
            try:
                run("git", "cat-file", "-e", f"{sha}:scripts/desktop.py")
            except subprocess.CalledProcessError as error:
                raise ValueError("Existing tag lacks the fork distribution entrypoint; choose a new reviewed fork version") from error
        releases = gh("release", "list", "--limit", "100", "--json", "tagName,isDraft", "--repo", repo)
        if any(release["tagName"] == tag for release in releases):
            published = gh("release", "view", tag, "--json", "name,isDraft,body", "--repo", repo)
            if (published["isDraft"] and not fork) or not published["body"].strip() or published["name"] != version["version"]:
                raise ValueError("Existing weekly release metadata is invalid")
            output({"ready": str(publish).lower(), "tag": tag, "commit": sha})
            return
    elif not first_release and run("git", "rev-list", "--count", f"{latest}..HEAD") == "0":
        output({"ready": "false"})
        return
    notes = release_notes(latest, tag, repo, tag if existing else "HEAD")
    print(notes)
    if not publish:
        output({"ready": "false", **version, "commit": run("git", "rev-parse", "HEAD")})
        return
    if not existing:
        old = cargo_version()
        updates = {}
        for path, prefix in ((Path("Cargo.toml"), ""), (Path("Cargo.lock"), 'name = "OpenCADStudio"\n')):
            content = path.read_text(encoding="utf-8")
            before = f'{prefix}version = "{old}"'
            if before not in content:
                raise ValueError(f"Cannot update version in {path}")
            updated = content.replace(before, f'{prefix}version = "{version["cargo"]}"', 1)
            if updated != content:
                updates[path] = updated
        for path, content in updates.items():
            path.write_text(content, encoding="utf-8")
        run("git", "config", "user.name", "github-actions[bot]")
        run("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
        # A reviewed candidate can already contain this week's version. Tag
        # that exact commit rather than failing on an empty metadata commit.
        if updates:
            run("git", "add", "Cargo.toml", "Cargo.lock")
            run("git", "commit", "-m", f"Release {tag}")
        run("git", "tag", "-a", tag, "-m", f"Release {tag}")
        run("git", "push", "--atomic", "origin", "HEAD:main", f"refs/tags/{tag}")
        sha = run("git", "rev-parse", "HEAD")
    # Close before gh reads: NamedTemporaryFile's open Windows handle denies
    # the second reader, which previously broke release preparation on Windows.
    with tempfile.TemporaryDirectory(prefix="ocs-release-notes-") as notes_dir:
        notes_file = Path(notes_dir) / "notes.md"
        notes_file.write_text(notes, encoding="utf-8")
        # Fork assets must pass native gates before becoming publicly visible.
        run("gh", "release", "create", tag, "--verify-tag", "--title", version["version"], "--notes-file", str(notes_file),
            *( ["--draft"] if fork else ["--latest"] ), "--repo", repo)
    published = gh("release", "view", tag, "--json", "name,body,isDraft", "--repo", repo)
    if published != {"name": version["version"], "body": notes, "isDraft": fork}:
        raise ValueError("Published release notes do not match the prepared release")
    output({"ready": "true", "tag": tag, "commit": sha})


def verify_native(tag, allow_draft=False):
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        raise ValueError("GITHUB_REPOSITORY must identify the release repository")
    if repo == "lalomalvi/OpenCADStudio":
        verify_fork_native(tag, allow_draft=allow_draft)
        return
    release = gh("release", "view", tag, "--json", "assets,body,isDraft", "--repo", repo)
    expected = {
        f"OpenCADStudio-{tag}-{suffix}"
        for suffix in ("linux-x86_64.AppImage", "linux-x86_64.snap",
                       "windows-x86_64-portable.exe", "windows-x86_64-installer.msi", "macos-arm64.dmg")
    }
    uploaded = {asset["name"] for asset in release["assets"] if asset["size"] > 0 and asset["state"] == "uploaded"}
    if release["isDraft"] or not release["body"].strip() or not expected <= uploaded:
        raise ValueError(f"Incomplete native release: {sorted(expected - uploaded)}")
    print(f"Verified native release {tag}")


def verify_fork_native(tag, allow_draft=False):
    """Read-only verification of actual fork packages, never upstream asset names."""
    import hashlib
    import zipfile
    repo = "lalomalvi/OpenCADStudio"
    published = gh("release", "view", tag, "--repo", repo, "--json", "assets,body,isDraft")
    if (published["isDraft"] and not allow_draft) or not published["body"].strip():
        raise ValueError("Fork release is draft or has no reviewable notes")
    names = {a["name"] for a in published["assets"] if a["size"] > 0 and a["state"] == "uploaded"}
    expected = {"x86_64-pc-windows-msvc", "aarch64-apple-darwin", "x86_64-apple-darwin"}
    source_commit = run("git", "rev-parse", f"{tag}^{{commit}}")
    with tempfile.TemporaryDirectory(prefix="ocs-release-verification-") as temp:
        run("gh", "release", "download", tag, "--repo", repo, "--dir", temp, "--pattern", "OpenCADStudio-fork-*.zip*")
        targets = set()
        for archive in Path(temp).glob("*.zip"):
            if "-dirty-" in archive.name:
                raise ValueError("A dirty development package cannot establish a published release")
            for suffix in (".sha256", ".json"):
                if archive.name + suffix not in names:
                    raise ValueError(f"Missing fork asset: {archive.name + suffix}")
            manifest = json.loads(archive.with_suffix(".zip.json").read_text())
            checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
            expected_checksum = archive.with_suffix(".zip.sha256").read_text().split()[0]
            if checksum != expected_checksum or checksum != manifest["package_sha256"]:
                raise ValueError(f"Fork package checksum mismatch: {archive.name}")
            if manifest["repository"] != repo or manifest["build"]["source commit"] != source_commit or manifest["source_state"] != "clean":
                raise ValueError(f"Fork source/tag mismatch: {archive.name}")
            if set(manifest["mcp"]["tools"]) != {"ocs_sessions", "ocs_read", "ocs_execute", "ocs_capture"}:
                raise ValueError("Required MCP surface missing from manifest")
            with zipfile.ZipFile(archive) as payload:
                roots = [n for n in payload.namelist() if n.endswith("/distribution.json") and n.count("/") == 1]
                if len(roots) != 1:
                    raise ValueError("Ambiguous distribution manifest")
                internal = json.loads(payload.read(roots[0]))
                if any(internal[k] != manifest[k] for k in internal):
                    raise ValueError("Sidecar differs from internal manifest")
                prefix = roots[0].removesuffix("distribution.json")
                for name, hash_value in internal["files"].items():
                    if hashlib.sha256(payload.read(prefix + name)).hexdigest() != hash_value:
                        raise ValueError(f"Fork payload hash mismatch: {name}")
            if manifest["target"] in targets:
                raise ValueError("Duplicate fork target")
            targets.add(manifest["target"])
        if targets != expected:
            raise ValueError(f"Incomplete fork targets: {expected - targets}")
    print(f"Verified fork assets, hashes and tag provenance for {tag}; native runtime evidence is in the distribution workflow.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--publish", action="store_true")
    version_parser = commands.add_parser("versions")
    version_parser.add_argument("--tag", default="")
    verify_parser = commands.add_parser("verify-native")
    verify_parser.add_argument("--tag", required=True)
    verify_parser.add_argument("--allow-draft", action="store_true", help="Check fork draft assets before promotion; does not publish")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.publish)
    elif args.command == "verify-native":
        verify_native(args.tag, allow_draft=args.allow_draft)
    else:
        version = versions(args.tag or display_version(cargo_version()))
        if args.tag and version["cargo"] != cargo_version():
            raise ValueError("Release tag and Cargo version do not match")
        output(version)


if __name__ == "__main__":
    main()
