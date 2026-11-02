#!/usr/bin/env bash

set -u

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ $# -eq 0 ]] && command -v python3 >/dev/null 2>&1 &&
    python3 -c 'import tkinter' >/dev/null 2>&1; then
    exec python3 "$PROJECT_DIR/wizard-gui.py"
fi

exec bash "$PROJECT_DIR/setup-wizard.sh" "$@"
