#!/usr/bin/env bash
# One-time setup for the drawthings skill: a private virtualenv with drawthings-py.
# Location: $XDG_CACHE_HOME/drawthings-skill/venv (default ~/.cache/drawthings-skill/venv).
# Override the interpreter later with DRAWTHINGS_PYTHON=/path/to/python.
set -euo pipefail
VENV="${XDG_CACHE_HOME:-$HOME/.cache}/drawthings-skill/venv"
# drawthings-py depends on a betterproto beta, so betterproto is listed explicitly to allow the pre-release.
PKGS=('drawthings-py>=0.4,<0.5' 'betterproto>=2.0.0b6,<3')
if command -v uv >/dev/null 2>&1; then
  uv venv --python '>=3.11' "$VENV" --quiet
  uv pip install --python "$VENV/bin/python" --quiet "${PKGS[@]}"
else
  python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
    || { echo "drawthings-py needs Python 3.11+ (or install uv, which fetches one)"; exit 1; }
  python3 -m venv "$VENV"
  "$VENV/bin/python" -m pip install --quiet --upgrade pip
  "$VENV/bin/python" -m pip install --quiet "${PKGS[@]}"
fi
"$VENV/bin/python" - <<'PY'
import importlib.metadata as m, sys
print(f"drawthings-py {m.version('drawthings-py')} on Python {sys.version.split()[0]} at {sys.executable}")
PY
