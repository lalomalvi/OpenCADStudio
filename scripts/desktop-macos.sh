#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
PYTHON="$(command -v python3 || true)"
if [ -z "$PYTHON" ]; then
    for candidate in /opt/homebrew/bin/python3 /usr/local/bin/python3 /Library/Frameworks/Python.framework/Versions/Current/bin/python3; do
        if [ -x "$candidate" ]; then PYTHON="$candidate"; break; fi
    done
fi
if [ -z "$PYTHON" ]; then
    echo 'Python 3.11+ helper missing; install Python explicitly or open the downloaded .app from Finder. See docs/install/macos.md.' >&2
    exit 2
fi
exec "$PYTHON" "$HERE/desktop.py" "$@"
