#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "$(uname -s)" != Linux ]; then
    echo 'Run this test package on your Linux desktop.' >&2
    exit 1
fi
PYTHON=${CALLPERCH_TEST_PYTHON:-python3}
if [ ! -x .venv/bin/python ]; then
    "$PYTHON" - <<'PY'
import sys
if not ((3,10) <= sys.version_info[:2] <= (3,13)):
    raise SystemExit('Use Python 3.10–3.13 for the pinned Qt runtime. Set CALLPERCH_TEST_PYTHON to a supported interpreter, such as python3.12.')
PY
    "$PYTHON" -m venv .venv
fi
if ! .venv/bin/python -c 'import PySide6; assert PySide6.__version__ == "6.8.3"' >/dev/null 2>&1; then
    echo 'Installing the pinned desktop dependency into this test folder…'
    .venv/bin/python -m pip install -r linux/requirements.txt
fi
printf 'Starting CallPerch test. Close other CallPerch instances first.\n'
printf 'This uses your existing CallPerch settings and FCC database.\n'
exec .venv/bin/python linux/callperch.py "$@"
