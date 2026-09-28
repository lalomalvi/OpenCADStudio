#!/usr/bin/env python3
"""Fork desktop lifecycle. Python 3.11+, standard library only; never installs tools.

Commands intentionally distinguish prepared, protocol-verified and GUI-verified.
No discovery by executable name, PATH or upstream package is allowed.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
import zipfile
import signal
import struct

if sys.version_info < (3, 11):
    print("Python 3.11+ is required by the desktop helper; the CAD binary itself does not need Python.", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "lalomalvi/OpenCADStudio"
TOOLCHAIN = "1.98.1"
TARGETS = {("Windows", "AMD64"): "x86_64-pc-windows-msvc",
           ("Windows", "x86_64"): "x86_64-pc-windows-msvc",
           ("Darwin", "arm64"): "aarch64-apple-darwin",
           ("Darwin", "x86_64"): "x86_64-apple-darwin"}
sys.path.insert(0, str(ROOT / "docs" / "automation"))
import mcp_smoke as smoke


class Blocked(RuntimeError):
    pass


def target():
    value = TARGETS.get((platform.system(), platform.machine()))
    if not value:
        raise Blocked(f"Unsupported native host: {platform.system()} {platform.machine()}; no compatible fork package declared.")
    return value


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def run(argv, *, cwd=ROOT, env=None, timeout=120, log=None):
    if log:
        with Path(log).open("a", encoding="utf-8") as stream:
            result = subprocess.run([str(x) for x in argv], cwd=cwd, env=env, timeout=timeout,
                                    stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode:
            raise Blocked(f"Command failed ({result.returncode}): {argv[0]}; inspect {log}")
        return ""
    result = subprocess.run([str(x) for x in argv], cwd=cwd, env=env, timeout=timeout,
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise Blocked(f"Command failed ({result.returncode}): {argv[0]}: {result.stderr.strip()[:1000]}")
    return result.stdout.strip()


def tool(name, candidates=()):
    found = shutil.which(name)
    if found and "WindowsApps" not in found:
        return {"path": os.path.abspath(found), "status": "on_PATH"}
    for candidate in candidates:
        if Path(candidate).is_file():
            return {"path": os.path.abspath(candidate), "status": "installed_outside_PATH"}
    return {"path": None, "status": "missing"}


def diagnose():
    home = Path.home()
    suffix = ".exe" if platform.system() == "Windows" else ""
    cargo_home = Path(os.environ.get("CARGO_HOME", home / ".cargo"))
    tools = {name: tool(name, [cargo_home / "bin" / (name + suffix)])
             for name in ("cargo", "rustc", "rustup")}
    tools["git"] = tool("git", [Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/cmd/git.exe", "/usr/bin/git"])
    result = {"platform": platform.system(), "architecture": platform.machine(), "python": sys.version.split()[0],
              "tested_rust": TOOLCHAIN, "tools": tools, "blockers": []}
    for name, info in tools.items():
        if not info["path"]:
            result["blockers"].append(f"{name} missing; see docs/install/{'windows' if platform.system() == 'Windows' else 'macos'}.md")
    if tools["rustup"]["path"]:
        installed = run([tools["rustup"]["path"], "toolchain", "list"])
        result["toolchains"] = installed
        # A named stable toolchain is acceptable only if it is the tested compiler.
        version = run([tools["rustc"]["path"], "--version"]) if tools["rustc"]["path"] else ""
        result["rustc"] = version
        if not version.startswith("rustc " + TOOLCHAIN + " "):
            result["blockers"].append(f"Use Rust {TOOLCHAIN}: rustup toolchain install {TOOLCHAIN} --profile minimal (explicit operator action).")
        if tools["rustc"]["path"]:
            verbose = run([tools["rustc"]["path"], "-vV"])
            result["rust_host"] = next((line[6:] for line in verbose.splitlines() if line.startswith("host: ")), None)
            if result["rust_host"] != TARGETS.get((platform.system(), platform.machine())):
                result["blockers"].append("Rust host must match the native MSVC/macOS architecture; select the platform toolchain with rustup override set.")
    if platform.system() == "Darwin":
        translated = subprocess.run(["sysctl", "-in", "sysctl.proc_translated"], capture_output=True, text=True)
        result["rosetta_process"] = translated.stdout.strip() == "1"
    if platform.system() == "Windows":
        vswhere = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Microsoft Visual Studio/Installer/vswhere.exe"
        instances = json.loads(run([vswhere, "-latest", "-products", "*", "-requires",
                                   "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-format", "json"])) if vswhere.is_file() else []
        links = sorted(Path(instances[0]["installationPath"]).glob("VC/Tools/MSVC/*/bin/Hostx64/x64/link.exe")) if instances else []
        compilers = sorted(Path(instances[0]["installationPath"]).glob("VC/Tools/MSVC/*/bin/Hostx64/x64/cl.exe")) if instances else []
        kits = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Windows Kits/10"
        sdks = [p.name for p in (kits / "Include").glob("*") if (p / "um/Windows.h").is_file()
                and (p / "ucrt/stdio.h").is_file() and (kits / "Lib" / p.name / "um/x64/kernel32.lib").is_file()]
        result.update(linker=str(links[-1]) if links else None, compiler=str(compilers[-1]) if compilers else None,
                      windows_sdks=sdks, visual_studio=instances[0]["displayName"] if instances else None)
        if not links or not compilers or not sdks:
            result["blockers"].append("Install Visual Studio Build Tools: Desktop development with C++, MSVC x64/x86 tools and Windows 10/11 SDK. Reopen terminal; never substitute an unrelated link.exe.")
    elif platform.system() == "Darwin":
        for name, argv in (("xcode_clt", ["xcode-select", "-p"]), ("macos_sdk", ["xcrun", "--sdk", "macosx", "--show-sdk-path"]), ("clang", ["xcrun", "--find", "clang"]), ("swift", ["xcrun", "--find", "swiftc"])):
            try:
                result[name] = run(argv)
            except (Blocked, FileNotFoundError):
                result["blockers"].append(f"{name} unavailable; run xcode-select --install explicitly, then retry.")
        result["rsvg_convert"] = tool("rsvg-convert", ["/opt/homebrew/bin/rsvg-convert", "/usr/local/bin/rsvg-convert", "/opt/local/bin/rsvg-convert"])
        if not result["rsvg_convert"]["path"]:
            result["blockers"].append("librsvg rsvg-convert missing for bundle icons; provide it via PATH (Homebrew is optional).")
    else:
        result["blockers"].append("This lifecycle supports native Windows x64 and macOS arm64/x64 only.")
    return result


def build(log_dir):
    doctor = diagnose()
    write_json(log_dir / "diagnosis.json", doctor)
    if doctor["blockers"]:
        raise Blocked("; ".join(doctor["blockers"]))
    env = os.environ.copy()
    env.setdefault("CARGO_BUILD_JOBS", "2")
    env["PATH"] = os.pathsep.join([str(Path(v["path"]).parent) for v in doctor["tools"].values() if v["path"]]) + os.pathsep + env.get("PATH", "")
    head = run([doctor["tools"]["git"]["path"], "rev-parse", "HEAD"], env=env)
    dirty = subprocess.run([doctor["tools"]["git"]["path"], "diff-index", "--quiet", "HEAD", "--"], cwd=ROOT, env=env).returncode
    if dirty not in (0, 1):
        raise Blocked("Cannot determine source state for build provenance")
    # Refresh metadata on clean/dirty transitions without recompiling an unchanged
    # application on every retry. Cargo still tracks all source/resource inputs.
    env.setdefault("OCS_DISTRIBUTION_BUILD", head + ("-dirty" if dirty else "-clean"))
    # Cargo and cc-rs discover MSVC/SDK via the installed VS instance, even off PATH.
    build_args = [doctor["tools"]["cargo"]["path"], "build", "--locked", "--release", "--bin", "OpenCADStudio", "-j", "2", "--message-format=json-render-diagnostics"]
    if platform.system() == "Darwin":
        build_args.extend(["--target", target()])
    build_log = log_dir / "build.log"
    run(build_args,
        env=env, timeout=3600, log=build_log)
    artifacts = []
    for line in build_log.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("reason") == "compiler-artifact" and record.get("target", {}).get("name") == "OpenCADStudio" and record.get("executable"):
            artifacts.append(Path(record["executable"]).resolve())
    if not artifacts or not artifacts[-1].is_file():
        raise Blocked(f"Cargo did not report an existing executable; inspect {build_log}")
    if platform.system() == "Darwin":
        env["PATH"] = str(Path(doctor["rsvg_convert"]["path"]).parent) + os.pathsep + env["PATH"]
        env["TARGET"] = target()
        metadata = json.loads(run([doctor["tools"]["cargo"]["path"], "metadata", "--locked", "--no-deps", "--format-version", "1"], env=env))
        env["CARGO_TARGET_DIR"] = metadata["target_directory"]
        env["DIST"] = str(log_dir / "macos-bundle")
        # Ad-hoc is explicit local development signing, never advertised as notarized.
        env.setdefault("DEVELOPER_ID", "-")
        run(["bash", ROOT / "packaging/build_macos_signed.sh"], env=env, timeout=3600, log=log_dir / "bundle.log")
        return log_dir / "macos-bundle/OpenCADStudio.app"
    return artifacts[-1]


def version_info(executable):
    output = run([executable, "--version"], cwd=Path(executable).parent, timeout=20)
    fields = dict(line.split(": ", 1) for line in output.splitlines()[1:] if ": " in line)
    if fields.get("source repository") not in (f"https://github.com/{REPOSITORY}.git", f"https://github.com/{REPOSITORY}", f"git@github.com:{REPOSITORY}.git", f"ssh://git@github.com/{REPOSITORY}.git"):
        raise Blocked("Binary has no verifiable fork source repository; rebuild this checkout with the documented script.")
    if not re.fullmatch(r"[0-9a-f]{40}", fields.get("source commit", "")):
        raise Blocked("Binary has no full verifiable source commit; rebuild from Git.")
    if fields.get("target") != target():
        raise Blocked(f"Binary target {fields.get('target')} differs from host {target()}")
    return {"version": output.splitlines()[0], **fields}


def executable_at(application):
    application = Path(application).resolve()
    return application / "Contents/MacOS/OpenCADStudio-App" if application.suffix == ".app" else application / "OpenCADStudio.exe"


def windows_signature(executable):
    """Inspect PE certificates without relying on PowerShell module autoloading."""
    with Path(executable).open("rb") as binary:
        if binary.read(2) != b"MZ":
            raise Blocked("Executable is not PE")
        binary.seek(0x3C)
        pe_offset = struct.unpack("<I", binary.read(4))[0]
        binary.seek(pe_offset)
        if binary.read(4) != b"PE\0\0":
            raise Blocked("Invalid PE header")
        coff = binary.read(20)
        machine, optional_size = struct.unpack_from("<H", coff)[0], struct.unpack_from("<H", coff, 16)[0]
        optional_offset = pe_offset + 24
        magic = struct.unpack("<H", binary.read(2))[0]
        if machine != 0x8664 or magic != 0x20B or optional_size < 152:
            raise Blocked("Fork Windows package requires a PE32+ AMD64 executable")
        binary.seek(optional_offset + 108)
        if struct.unpack("<I", binary.read(4))[0] < 5:
            raise Blocked("Missing PE data directory")
        binary.seek(optional_offset + 112 + 4 * 8)
        offset, size = struct.unpack("<II", binary.read(8))
    if offset == 0 and size == 0:
        return {"status": "NotSigned", "publisher": None, "evidence": "PE Authenticode certificate table is empty"}
    if not offset or size < 8 or offset + size > Path(executable).stat().st_size:
        raise Blocked("Malformed PE Authenticode certificate table")
    kits = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Windows Kits/10/bin"
    signers = sorted(kits.glob("*/x64/signtool.exe"))
    if not signers:
        raise Blocked("Certificate present: Windows SDK signtool is required to establish signature validity; no publisher signature is assumed.")
    details = run([signers[-1], "verify", "/pa", "/v", executable])
    return {"status": "Valid", "evidence": details}


def protocol(executable, log_dir, env=None):
    # Reuse the product smoke suite; run outside checkout and in private config.
    isolated = env or {**os.environ, "OCS_CONFIG_DIR": str(log_dir / "protocol-config")}
    run([sys.executable, ROOT / "docs/automation/mcp_smoke.py", executable], cwd=Path(executable).parent,
        env=isolated, timeout=180, log=log_dir / "mcp.log")
    return {"ok": True, "versions": ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25", smoke.MODERN],
            "tools": sorted(smoke.TOOLS), "stdio": "JSON-RPC only; clean EOF", "discovery_launch_if_none": False}


def package(source, output, log_dir):
    source = Path(source).resolve()
    exe = executable_at(source) if source.suffix == ".app" else source
    info = version_info(exe)
    if info.get("profile") != "release":
        raise Blocked("Only release builds are distributable; debug RustEmbed reads resources from the source tree.")
    protocol(exe, log_dir)
    dirty = "dirty" in info.get("revision", "")
    cargo_version = re.search(r'^version = "([^"]+)"', (ROOT / "Cargo.toml").read_text(), re.M)[1]
    platform_name = "windows-x86_64" if platform.system() == "Windows" else "macos-" + ("arm64" if platform.machine() == "arm64" else "x86_64")
    name = f"OpenCADStudio-fork-{cargo_version}-{info['source commit'][:12]}{'-dirty' if dirty else ''}-{platform_name}"
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ocs-package-") as tmp:
        payload = (Path(tmp) / name).resolve()
        payload.mkdir()
        app = payload / ("OpenCADStudio.app" if source.suffix == ".app" else "application")
        if source.suffix == ".app":
            run(["ditto", source, app])
            # Reject references to build machine libraries in *every* Mach-O.
            dynamic = {}
            for binary in app.rglob("*"):
                if binary.is_file() and "Mach-O" in run(["file", binary]):
                    listing = run(["otool", "-L", binary])
                    dynamic[str(binary.relative_to(app))] = listing
                    # A dylib reports its own install ID in otool -L. It is
                    # identity metadata, not an unbundled dependency.
                    identity = run(["otool", "-D", binary]).splitlines()[1:]
                    for line in listing.splitlines()[1:]:
                        library = line.strip().split(" (", 1)[0]
                        if library in identity:
                            continue
                        if not library.startswith(("/System/Library/", "/usr/lib/")):
                            raise Blocked(f"Non-system dynamic library requires explicit bundling: {library}")
            write_json(log_dir / "dynamic-libraries.json", dynamic)
            run(["codesign", "--verify", "--deep", "--strict", app])
            plist = plistlib.loads((app / "Contents/Info.plist").read_bytes())
            if plist["CFBundleExecutable"] != "OpenCADStudio":
                raise Blocked("Unexpected Finder launcher")
            if plist["CFBundleIdentifier"] != "io.github.lalomalvi.OpenCADStudioFork":
                raise Blocked("Bundle must have the fork LaunchServices identity")
            extension = plistlib.loads((app / "Contents/PlugIns/DWGThumbnail.appex/Contents/Info.plist").read_bytes())
            if extension["CFBundleIdentifier"] != plist["CFBundleIdentifier"] + ".DWGThumbnail":
                raise Blocked("Thumbnail extension identifier does not belong to the fork bundle")
            for plugin_resource in ("plugin.toml", "libopencad_python.dylib"):
                if not (app / "Contents/Resources/plugins/opencad.python" / plugin_resource).is_file():
                    raise Blocked(f"Missing bundled RustPython plugin resource: {plugin_resource}")
            for resource in ("AppIcon.icns", "DWG.icns", "DXF.icns"):
                if not (app / "Contents/Resources" / resource).is_file():
                    raise Blocked(f"Missing bundle resource: {resource}")
            signing = subprocess.run(["codesign", "-d", "--verbose=4", str(app)], capture_output=True, text=True)
            details = signing.stderr
            if signing.returncode:
                raise Blocked("Cannot inspect bundle signing identity")
            notarized = subprocess.run(["xcrun", "stapler", "validate", str(app)], capture_output=True, text=True).returncode == 0
            signature = {"status": "ad-hoc" if "Signature=adhoc" in details else "signed", "notarized_stapled": notarized,
                         "authority": re.findall(r"^Authority=(.*)$", details, re.M)}
        else:
            app.mkdir()
            shutil.copy2(source, app / "OpenCADStudio.exe")
            # App-local MSVC runtime avoids requiring an administrator/global redistributable.
            doctor = diagnose()
            if not doctor.get("linker"):
                raise Blocked("MSVC dumpbin required to audit Windows runtime dependencies")
            dumpbin = Path(doctor["linker"]).with_name("dumpbin.exe")
            vsroot = Path(doctor["linker"]).parents[7]
            listing = run([dumpbin, "/dependents", source])
            dependencies = re.findall(r"^\s+([A-Za-z0-9_.-]+\.dll)\s*$", listing, re.M | re.I)
            runtime = re.compile(r"^(vcruntime|msvcp|concrt|vcomp|msvcr).*\.dll$", re.I)
            for dll in dependencies:
                if runtime.match(dll):
                    locations = sorted((vsroot / "VC/Redist/MSVC").glob(f"*/x64/Microsoft.VC*.CRT/{dll}"))
                    if not locations:
                        raise Blocked(f"MSVC runtime {dll} absent from VS Redist; install C++ redistributable files component explicitly.")
                    shutil.copy2(locations[-1], app / dll)
                elif not dll.lower().startswith(("api-ms-", "ext-ms-")) and not (Path(os.environ["SystemRoot"]) / "System32" / dll).is_file():
                    raise Blocked(f"Unbundled non-system Windows DLL: {dll}")
            write_json(log_dir / "dynamic-libraries.json", {"dumpbin": listing, "bundled": [p.name for p in app.glob("*.dll")]})
            signature = windows_signature(source)
        shutil.copy2(ROOT / "LICENSE", payload / "LICENSE")
        files = {str(p.relative_to(payload)).replace(os.sep, "/"): digest(p) for p in payload.rglob("*") if p.is_file()}
        manifest = {"schema": 1, "repository": REPOSITORY, "target": target(), "build": info,
                    "application": app.relative_to(payload).as_posix(), "executable": executable_at(app).relative_to(payload).as_posix(),
                    "files": files, "mcp": {"versions": [smoke.MODERN, "2025-11-25"], "tools": sorted(smoke.TOOLS)},
                    "source_state": "dirty-development" if dirty else "clean", "signature": signature,
                    "cargo_lock_sha256": digest(ROOT / "Cargo.lock")}
        write_json(payload / "distribution.json", manifest)
        archive = output / (name + ".zip")
        if source.suffix == ".app":
            run(["ditto", "-c", "-k", "--keepParent", payload, archive])
        else:
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
                for path in payload.rglob("*"):
                    if path.is_file():
                        z.write(path, path.relative_to(payload.parent))
        checksum = digest(archive)
        # Never overwrite a prior development package with different bytes.
        final = archive.with_name(archive.stem + "-" + checksum[:12] + ".zip")
        if final.exists():
            if digest(final) != checksum:
                raise Blocked(f"Existing package differs: {final}")
            archive.unlink()
        else:
            archive.rename(final)
        final.with_suffix(".zip.sha256").write_text(f"{checksum}  {final.name}\n", encoding="utf-8")
        write_json(final.with_suffix(".zip.json"), {**manifest, "package_sha256": checksum, "package": final.name})
        return final


def unpack(archive, destination):
    # Check ZIP traversal, links and zip bombs before either unzip implementation.
    with zipfile.ZipFile(archive) as z:
        if sum(i.file_size for i in z.infolist()) > 2_000_000_000:
            raise Blocked("Package expands beyond the 2 GB limit")
        names = set()
        for info in z.infolist():
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or any(p in ("..", "") for p in name.rstrip("/").split("/")) or ":" in name:
                raise Blocked(f"Unsafe archive entry: {name}")
            if name.lower() in names or ((info.external_attr >> 16) & 0o170000) == 0o120000:
                raise Blocked(f"Duplicate entry or symbolic link: {name}")
            names.add(name.lower())
        if platform.system() == "Darwin":
            run(["ditto", "-x", "-k", archive, destination])
        else:
            z.extractall(destination)


def validate(payload):
    payload = Path(payload).resolve()
    manifest = json.loads((payload / "distribution.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != 1 or manifest.get("repository") != REPOSITORY or manifest.get("target") != target():
        raise Blocked("Package origin/schema/architecture mismatch")
    def within(name):
        path = (payload / name).resolve()
        if not path.is_relative_to(payload):
            raise Blocked("Manifest path escapes package")
        return path
    for name, checksum in manifest["files"].items():
        if digest(within(name)) != checksum:
            raise Blocked(f"Package hash mismatch: {name}")
    exe = within(manifest["executable"])
    if not exe.is_file() or manifest["executable"] not in manifest["files"]:
        raise Blocked("Executable missing from verified payload")
    info = version_info(exe)
    if info != manifest["build"]:
        raise Blocked("Binary version differs from package manifest")
    return manifest, within(manifest["application"]), exe


def default_install_dir():
    if platform.system() == "Windows":
        return Path(os.environ["LOCALAPPDATA"]) / "Programs/OpenCADStudio Fork"
    return Path.home() / "Applications/OpenCADStudio Fork"


def install(archive, directory, log_dir, expected=None):
    archive, directory = Path(archive).resolve(), Path(directory).resolve()
    checksum = digest(archive)
    sidecar = archive.with_suffix(".zip.sha256")
    expected = expected or (sidecar.read_text().split()[0] if sidecar.is_file() else None)
    if not expected or not re.fullmatch(r"[a-fA-F0-9]{64}", expected):
        raise Blocked("A SHA-256 from the fork release or local build is required (--sha256 or .zip.sha256).")
    if checksum.lower() != expected.lower():
        raise Blocked("Downloaded package SHA-256 mismatch; retain evidence and download again.")
    slot = directory / checksum[:16]
    directory.mkdir(parents=True, exist_ok=True)
    if not slot.exists():
        staging = directory / (".staging-" + uuid.uuid4().hex)
        staging.mkdir()
        try:
            unpack(archive, staging)
            candidates = list(staging.glob("*/distribution.json"))
            if len(candidates) != 1:
                raise Blocked("Expected exactly one distribution manifest")
            payload = candidates[0].parent
            validate(payload)
            payload.rename(slot)
        finally:
            # Only our freshly created staging directory can be removed.
            shutil.rmtree(staging)
    manifest, app, exe = validate(slot)
    verified = protocol(exe, log_dir)
    state = {"status": "prepared_protocol_verified", "package": str(archive), "package_sha256": checksum,
             "payload": str(slot), "application": str(app), "executable": str(exe), "build": manifest["build"],
             "platform": platform.system(), "architecture": platform.machine(), "provenance": REPOSITORY,
             "logs": str(log_dir), "protocol": verified, "gui": "not_yet_verified"}
    write_json(directory / "installation.json", state)
    return state


def resolve(directory):
    path = Path(directory).resolve() / "installation.json"
    if not path.is_file():
        raise Blocked(f"No managed installation: {path}; run build then install, or install a verified fork ZIP.")
    state = json.loads(path.read_text(encoding="utf-8"))
    manifest, app, exe = validate(state["payload"])
    if str(exe) != state["executable"] or str(app) != state["application"]:
        raise Blocked("Installation pointer differs from verified payload")
    return state


def windows_visible(pid):
    if platform.system() != "Windows":
        return None
    titles = []
    user32 = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
    def check(hwnd, _):
        process_id = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(process_id))
        if process_id.value == pid and user32.IsWindowVisible(ctypes.c_void_p(hwnd)):
            title = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(ctypes.c_void_p(hwnd), title, len(title))
            if title.value:
                titles.append(title.value)
        return True
    user32.EnumWindows(callback_type(check), 0)
    return titles


class OwnedMacLauncher:
    """Process returned by our exact LaunchServices launch, never a name search."""
    def __init__(self, pid):
        self.pid = pid

    def poll(self):
        try:
            os.kill(self.pid, 0)
            return None
        except ProcessLookupError:
            return 0

    def terminate(self):
        if self.poll() is None:
            os.kill(self.pid, signal.SIGTERM)

    def wait(self, timeout):
        deadline = time.monotonic() + timeout
        while self.poll() is None and time.monotonic() < deadline:
            time.sleep(0.1)
        if self.poll() is None:
            raise Blocked("Owned Finder launcher did not exit")
        return 0


def open_gui(state, log_dir, keep=True, cad=False, finder=False):
    # Private profile avoids restore/recent-file access and makes PID ownership exact.
    profile = log_dir / "gui-config"
    env = {**os.environ, "OCS_CONFIG_DIR": str(profile)}
    exe = Path(state["executable"])
    gui_pid = None
    if finder:
        if platform.system() != "Darwin":
            raise Blocked("--finder requires a native macOS host")
        launched = json.loads(run(["swift", ROOT / "scripts/finder-smoke.swift", state["application"], profile], cwd=log_dir, env=env))
        process = OwnedMacLauncher(launched["pid"])
    else:
        with (log_dir / "gui.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen([str(exe), "--new-instance", "--new"], cwd=exe.parent, env=env,
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=log)
    client = None
    try:
        client = smoke.start(exe, env=env, cwd=exe.parent)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            status = process.poll()
            if status is not None:
                raise Blocked(f"GUI exited with {status}; inspect {log_dir / 'gui.log'}")
            reply = smoke.request(client, {"jsonrpc": "2.0", "id": "sessions", "method": "tools/call",
                                          "params": {"name": "ocs_sessions", "arguments": {"launch_if_none": False}}})
            if reply.get("result", {}).get("isError"):
                raise Blocked("Session discovery failed")
            sessions = reply.get("result", {}).get("structuredContent", {}).get("result", [])
            descriptors = []
            for path in (profile / "automation").glob("*.json"):
                record = json.loads(path.read_text(encoding="utf-8"))
                owned = record.get("pid") == process.pid
                if finder and record.get("pid"):
                    parent = run(["ps", "-o", "ppid=", "-p", str(record["pid"])])
                    owned = parent.strip() == str(process.pid)
                if owned and Path(record.get("executable", "")).resolve() == exe.resolve():
                    descriptors.append(record["session_id"])  # never expose bridge token
                    gui_pid = record["pid"]
            ready = [s for s in sessions if s.get("session_id") in descriptors and s.get("mode") == "gui"]
            windows = windows_visible(process.pid)
            if ready and (windows is None or windows):
                sid = ready[0]["session_id"]
                if ready[0].get("modal"):
                    # Only our PID-correlated private session can be touched.
                    dismissed = smoke.request(client, {"jsonrpc": "2.0", "id": "startup-modal", "method": "tools/call",
                        "params": {"name": "ocs_execute", "arguments": {"ocs_session_id": sid,
                                   "request": {"op": "action", "name": "close_modal", "request_id": "startup-" + uuid.uuid4().hex}}}})
                    if dismissed.get("result", {}).get("isError"):
                        raise Blocked("Owned GUI startup modal could not be dismissed; inspect its capture manually.")
                    time.sleep(0.2)
                    continue
                # A rendered capture verifies the view is ready, even on a headless CI desktop.
                capture = smoke.request(client, {"jsonrpc": "2.0", "id": "capture", "method": "tools/call",
                    "params": {"name": "ocs_capture", "arguments": {"ocs_session_id": sid, "scope": "window"}}})
                images = [c for c in capture.get("result", {}).get("content", []) if c.get("type") == "image"]
                if not images or capture["result"].get("isError"):
                    time.sleep(0.5)
                    continue
                import base64
                screenshot = log_dir / "gui.png"
                screenshot.write_bytes(base64.b64decode(images[0]["data"], validate=True))
                if not screenshot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
                    raise Blocked("GUI capture is not PNG")
                outcome = {"ok": True, "pid": gui_pid, "launcher_pid": process.pid if finder else None, "session_id": sid, "executable": str(exe),
                           "visible_windows": windows, "render_capture": str(screenshot), "profile": str(profile),
                           "scope": "new empty document, isolated configuration", "finder_launch": "LaunchServices verified" if finder else "not tested by this command"}
                outcome["left_open"] = keep
                outcome["working_directory"] = str(exe.parent)
                write_json(log_dir / "gui-verification.json", outcome)
                if cad:
                    # Reuse the existing synthetic acceptance under this owned profile.
                    run([sys.executable, ROOT / "docs/automation/mcp_acceptance.py", exe, log_dir / "synthetic-cad"],
                        cwd=log_dir, env=env, timeout=240, log=log_dir / "cad-acceptance.log")
                    outcome["synthetic_cad"] = "verified saves and audits (not external CAD parity)"
                    write_json(log_dir / "gui-verification.json", outcome)
                return outcome
            time.sleep(0.5)
        raise Blocked(f"GUI readiness/window/capture timeout (60s); inspect {log_dir}")
    except Exception:
        # A failed verification cannot leave an owned, unverified GUI behind.
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        raise
    finally:
        if client and client.poll() is None:
            smoke.close(client)
        if (not keep or sys.exc_info()[0] is not None) and finder and gui_pid:
            # The GUI is the launcher's owned child; closing it also ends the relay.
            try:
                os.kill(gui_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        if not keep and process.poll() is None:
            process.terminate()
            process.wait(timeout=10)


def download(log_dir, downloads, tag=None):
    def get_json(url):
        request = urllib.request.Request(url, headers={"User-Agent": "OpenCADStudio-fork-installer"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    releases = get_json(f"https://api.github.com/repos/{REPOSITORY}/releases?per_page=100")
    write_json(log_dir / "releases.json", releases)
    candidates = [r for r in releases if not r["draft"] and (r["tag_name"] == tag if tag else not r["prerelease"])]
    suffix = "windows-x86_64" if platform.system() == "Windows" else "macos-" + ("arm64" if platform.machine() == "arm64" else "x86_64")
    for release in candidates:
        assets = {a["name"]: a for a in release["assets"]}
        packages = [a for n, a in assets.items() if n.startswith("OpenCADStudio-fork-") and suffix + "-" in n and n.endswith(".zip")]
        if len(packages) != 1 or packages[0]["name"] + ".sha256" not in assets:
            continue
        package = packages[0]
        downloads.mkdir(parents=True, exist_ok=True)
        for asset in (assets[package["name"] + ".sha256"], package):
            url = asset["browser_download_url"]
            if not url.startswith(f"https://github.com/{REPOSITORY}/releases/download/") or Path(asset["name"]).name != asset["name"]:
                raise Blocked("Release asset origin/name mismatch")
            destination = downloads / asset["name"]
            temporary = destination.with_suffix(destination.suffix + ".part")
            request = urllib.request.Request(url, headers={"User-Agent": "OpenCADStudio-fork-installer"})
            deadline = time.monotonic() + 180
            with urllib.request.urlopen(request, timeout=30) as response, temporary.open("wb") as stream:
                total = 0
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > 1_000_000_000 or time.monotonic() > deadline:
                        raise Blocked("Download exceeded 1 GB or 180s")
                    stream.write(chunk)
            os.replace(temporary, destination)
        return downloads / package["name"]
    raise Blocked(f"No compatible verified fork ZIP in {REPOSITORY} releases. Run build; a clone is not an installation.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["diagnose", "build", "package", "download", "install", "open", "path", "config", "mcp", "verify"])
    parser.add_argument("--source", type=Path, help="Release executable or .app for package")
    parser.add_argument("--package", type=Path)
    parser.add_argument("--sha256")
    parser.add_argument("--install-dir", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument("--logs", type=Path)
    parser.add_argument("--tag")
    parser.add_argument("--gui", action="store_true", help="verify also renders an isolated GUI, then closes it")
    parser.add_argument("--cad", action="store_true", help="run the existing synthetic CAD acceptance on the owned GUI")
    parser.add_argument("--finder", action="store_true", help="verify actual macOS LaunchServices bundle opening")
    args = parser.parse_args()
    if args.action == "diagnose":
        # Keep default diagnosis read-only. Explicit --logs preserves CI failures.
        diagnosis_logs = args.logs.resolve() if args.logs else None
        if diagnosis_logs:
            diagnosis_logs.mkdir(parents=True, exist_ok=False)
        try:
            result = diagnose()
        except (Blocked, OSError, ValueError, subprocess.TimeoutExpired) as error:
            result = {"blockers": [str(error)], "status": "blocked"}
        if diagnosis_logs:
            write_json(diagnosis_logs / "diagnosis.json", result)
        print(json.dumps(result, indent=2))
        return 2 if result["blockers"] else 0
    target()
    directory = (args.install_dir or default_install_dir()).resolve()
    if args.action in ("path", "config", "mcp"):
        state = resolve(directory)
        if args.action == "path":
            print(state["executable"])
            return 0
        client_env = os.environ.copy()
        fragment = {"command": state["executable"], "args": ["--mcp"]}
        gui = state.get("gui")
        if isinstance(gui, dict) and gui.get("left_open") and gui.get("profile"):
            # Connect to the exact private GUI opened by this helper, not a
            # global discovery directory containing older/upstream sessions.
            fragment["env"] = {"OCS_CONFIG_DIR": gui["profile"]}
            client_env.update(fragment["env"])
        if args.action == "config":
            print(json.dumps(fragment, indent=2))
            return 0
        # No banners/logs on stdout in MCP mode. Preserve the client's stdio.
        return subprocess.call([state["executable"], "--mcp"], cwd=Path(state["application"]).parent,
                               env=client_env, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr)
    log_dir = (args.logs or ROOT / "target/desktop-logs" / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])).resolve()
    log_dir.mkdir(parents=True, exist_ok=False)
    try:
        if args.action in ("build", "package"):
            source = build(log_dir) if args.action == "build" else args.source
            if not source:
                raise Blocked("package requires --source (release exe or .app)")
            archive = package(source, args.output, log_dir)
            state = {"status": "packaged_protocol_verified", "package": str(archive), "sha256": digest(archive), "logs": str(log_dir), "gui": "not_yet_verified"}
        elif args.action == "download":
            archive = download(log_dir, args.output.resolve(), args.tag)
            state = install(archive, directory, log_dir, args.sha256)
        elif args.action == "install":
            if not args.package:
                raise Blocked("install requires --package; use download or build first")
            state = install(args.package, directory, log_dir, args.sha256)
        else:
            state = resolve(directory)
            state["logs"] = str(log_dir)
            state["protocol"] = protocol(Path(state["executable"]), log_dir)
            if args.action == "open" or args.gui or args.cad or args.finder:
                state["gui"] = open_gui(state, log_dir, keep=args.action == "open", cad=args.cad, finder=args.finder)
                state["status"] = "installed_gui_protocol_verified"
                write_json(directory / "installation.json", state)
        write_json(log_dir / "summary.json", state)
        print(json.dumps(state, indent=2))
        return 0
    except Exception as error:
        report = {"status": "blocked", "error": str(error), "logs": str(log_dir), "next_step": "Follow the concrete error and the platform guide; no successful installation is claimed."}
        write_json(log_dir / "summary.json", report)
        print(json.dumps(report, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (Blocked, OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"Blocked: {error}", file=sys.stderr)
        sys.exit(2)
