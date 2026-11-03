#!/usr/bin/env bash
# One-shot start: set up/activate ./.venv, install Python deps if missing, bring up the
# hotspot and run delaycam fullscreen. Hotspot is taken down again on exit.
# Usage: ./quickstart.sh [extra delaycam.py args]    Env: DELAY (default 8), plus hotspot.sh's SSID/PASS/IFACE
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

for cmd in ffmpeg nmcli python3; do
  command -v "$cmd" >/dev/null || { echo "missing '$cmd' - install it with your package manager" >&2; exit 1; }
done

if [[ ! -d .venv ]]; then
  echo "creating virtualenv in .venv"
  python3 -m venv .venv
fi
source .venv/bin/activate

if ! python -c "import cv2, numpy" 2>/dev/null; then
  echo "installing Python dependencies"
  pip install --upgrade pip
  pip install -r requirements.txt
fi

trap './hotspot.sh down >/dev/null 2>&1 || true' EXIT
python delaycam.py --hotspot --delay "${DELAY:-8}" --fullscreen "$@"
