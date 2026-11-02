#!/usr/bin/env bash

set -u
umask 077

APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_SCRIPT="$APP_DIR/settings-gui.py"
LOG_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/dual-screen-mode"
LOG_FILE="$LOG_DIR/settings-gui.log"

show_error() {
    local message="$1"
    message="${message//\\n/$'\n'}"
    if command -v kdialog >/dev/null 2>&1; then
        kdialog --title "Dual Screen Mode Settings" --error "$message" 2>/dev/null || true
    elif command -v notify-send >/dev/null 2>&1; then
        notify-send "Dual Screen Mode Settings" "$message" 2>/dev/null || true
    else
        printf '%s\n' "$message" >&2
    fi
}

if ! command -v python3 >/dev/null 2>&1; then
    show_error "Python 3 was not found.\n\nThe settings app could not start."
    exit 1
fi

if ! python3 -c 'import tkinter' >/dev/null 2>&1; then
    show_error "Python Tk support was not found.\n\nThe settings app could not start."
    exit 1
fi

if [[ ! -f "$APP_SCRIPT" ]]; then
    show_error "The settings app file was not found:\n\n$APP_SCRIPT"
    exit 1
fi

mkdir -p "$LOG_DIR"
{
    printf 'Dual Screen Mode settings launch\n'
    printf 'Time: %s\n' "$(date --iso-8601=seconds 2>/dev/null || date)"
    printf 'Script: %s\n' "$APP_SCRIPT"
    printf 'Python: %s\n' "$(command -v python3)"
    printf 'Desktop: %s\n' "${XDG_CURRENT_DESKTOP:-unknown}"
    printf 'Session: %s\n\n' "${XDG_SESSION_TYPE:-unknown}"
} >"$LOG_FILE"
python3 -u "$APP_SCRIPT" >>"$LOG_FILE" 2>&1
status=$?
if (( status != 0 )); then
    details="$(tail -12 "$LOG_FILE" 2>/dev/null || true)"
    show_error "The settings app could not start.\n\nThe error was saved here:\n$LOG_FILE\n\nLast error:\n$details"
fi
exit "$status"
