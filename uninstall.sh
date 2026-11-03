#!/usr/bin/env bash

set -u
umask 077

APP_ID="dev.lizardbyte.app.Sunshine"
TOGGLE_DEST="$HOME/.local/bin/dual-screen-mode"
desktop_dir() {
    local candidate=""
    if command -v xdg-user-dir >/dev/null 2>&1; then
        candidate="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
    fi
    if [[ -z "$candidate" ]]; then
        local user_dirs_file="${XDG_CONFIG_HOME:-$HOME/.config}/user-dirs.dirs"
        if [[ -r "$user_dirs_file" ]]; then
            candidate="$(sed -n 's/^XDG_DESKTOP_DIR="\([^"]*\)".*/\1/p' "$user_dirs_file" | head -n 1)"
            candidate="${candidate//\$HOME/$HOME}"
        fi
    fi
    if [[ -z "$candidate" || "$candidate" != /* ]]; then
        candidate="$HOME/Desktop"
    fi
    printf '%s\n' "$candidate"
}
DESKTOP_DIR="$(desktop_dir)"
DESKTOP_DEST="$DESKTOP_DIR/Dual Screen Mode.desktop"
UNINSTALL_DESKTOP_DEST="$DESKTOP_DIR/Uninstall Dual Screen Mode.desktop"
LEGACY_DESKTOP_DEST="$HOME/Desktop/Dual Screen Mode.desktop"
LEGACY_UNINSTALL_DESKTOP_DEST="$HOME/Desktop/Uninstall Dual Screen Mode.desktop"
UNINSTALL_APP_DIR="$HOME/.local/share/dual-screen-mode"
UNINSTALL_SCRIPT_DEST="$UNINSTALL_APP_DIR/uninstall.sh"
MANAGEMENT_SCRIPT_DEST="$UNINSTALL_APP_DIR/settings-gui.py"
MANAGEMENT_LAUNCHER_DEST="$UNINSTALL_APP_DIR/settings-launcher.sh"
ICON_DEST="$HOME/.local/share/icons/dual-screen-mode.png"
SETTINGS_ICON_DEST="$HOME/.local/share/icons/dual-screen-mode-settings.png"
ENV_FILE="$HOME/.config/environment.d/dual-screen-mode.conf"
SETTINGS_FILE="$HOME/.config/dual-screen-mode/settings.conf"
SETTINGS_DIR="$HOME/.config/dual-screen-mode"
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp}/dual-screen-mode"
TOUCH_MAPPING_FILE="$RUNTIME_DIR/touch-mappings"
STATE_DIR="$HOME/.local/state/dual-screen-mode"
VIRTUAL_NAME="DualScreen"
OWNED_ENV_MARKER="$STATE_DIR/owned-environment-setting"
OWNED_OVERRIDE_MARKER="$STATE_DIR/owned-sunshine-override"
OWNED_SETTINGS_ICON_MARKER="$STATE_DIR/owned-settings-icon"

DRY_RUN=0
AUTO_CONFIRM=0
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=1
fi
if [[ "${1:-}" == "--execute" ]]; then
    AUTO_CONFIRM=1
fi

have() {
    command -v "$1" >/dev/null 2>&1
}

ui_message() {
    local message="$1"
    if have kdialog; then
        kdialog --title "Dual Screen Mode" --msgbox "$message"
    else
        printf '\n%b\n\n' "$message"
    fi
}

ui_question() {
    local message="$1"
    if have kdialog; then
        kdialog --title "Dual Screen Mode" --yesno "$message"
        return $?
    fi
    printf '%b [y/N] ' "$message" >&2
    read -r answer
    [[ "$answer" =~ ^[Yy]([Ee][Ss])?$ ]]
}

vmonitor_pid_is_ours() {
    local pid="$1"
    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    [[ -r "/proc/$pid/cmdline" && -O "/proc/$pid" ]] || return 1
    tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null |
        grep -Fq "krfb-virtualmonitor" || return 1
    tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null |
        grep -Eq -- "(^|[[:space:]])--name[[:space:]]+$VIRTUAL_NAME([[:space:]]|$)"
}

stop_vmonitor_pid() {
    local pid="$1"
    if vmonitor_pid_is_ours "$pid"; then
        kill -CONT "$pid" 2>/dev/null || true
        kill "$pid" 2>/dev/null || true
    fi
}

restore_touch_mappings() {
    [[ -f "$TOUCH_MAPPING_FILE" ]] || return 0

    local dbus_tool=""
    if have qdbus6; then
        dbus_tool="qdbus6"
    elif have qdbus; then
        dbus_tool="qdbus"
    fi
    if [[ -n "$dbus_tool" ]]; then
        local device old_output
        while IFS=$'\t' read -r device old_output; do
            [[ -n "$device" ]] || continue
            "$dbus_tool" \
                org.kde.KWin \
                "/org/kde/KWin/InputDevice/$device" \
                org.freedesktop.DBus.Properties.Set \
                org.kde.KWin.InputDevice \
                outputName \
                "$old_output" >/dev/null 2>&1 || true
        done < "$TOUCH_MAPPING_FILE"
    fi
    rm -f "$TOUCH_MAPPING_FILE" "$RUNTIME_DIR/touch-status" "$RUNTIME_DIR/touch-watcher.pid"
}

stop_mode() {
    if [[ -f "$RUNTIME_DIR/active" && -x "$TOGGLE_DEST" ]]; then
        "$TOGGLE_DEST" >/dev/null 2>&1 || true
        return 0
    fi

    restore_touch_mappings
    if [[ -f "$RUNTIME_DIR/sunshine.pid" ]]; then
        flatpak kill "$APP_ID" 2>/dev/null || true
    fi
    if [[ -f "$RUNTIME_DIR/vmonitor.pid" ]]; then
        local pid
        pid="$(cat "$RUNTIME_DIR/vmonitor.pid" 2>/dev/null || true)"
        stop_vmonitor_pid "$pid"
    else
        while IFS= read -r pid; do
            stop_vmonitor_pid "$pid"
        done < <(pgrep -u "$(id -u)" -f '(^|/)krfb-virtualmonitor([[:space:]]|$)' 2>/dev/null || true)
    fi
    rm -f "$RUNTIME_DIR/active" "$RUNTIME_DIR/vmonitor.pid" "$RUNTIME_DIR/sunshine.pid" "$RUNTIME_DIR/audio.state"
}

if (( DRY_RUN )); then
    printf '%s\n' \
        "Would turn Dual Screen Mode off first, restoring saved audio state" \
        "Would remove the owned toggle: $TOGGLE_DEST" \
        "Would remove the owned launcher: $DESKTOP_DEST" \
        "Would remove the owned uninstall launcher: $UNINSTALL_DESKTOP_DEST" \
        "Would remove the settings app: $MANAGEMENT_SCRIPT_DEST" \
        "Would remove the owned icon: $ICON_DEST" \
        "Would remove the owned settings icon: $SETTINGS_ICON_DEST" \
        "Would remove the owned display and audio choices: $SETTINGS_FILE" \
        "Would remove the owned KWin environment setting" \
        "Would remove the owned Sunshine Flatpak override" \
        "Sunshine, Moonlight, krfb, and user backups would remain installed"
    exit 0
fi

if (( ! AUTO_CONFIRM )); then
    ui_question \
        "Remove Dual Screen Mode?\n\nThis turns the mode off, restores the saved audio state, and removes only Dual Screen Mode's files and settings. Sunshine, Moonlight, krfb, and your backups stay installed." ||
        exit 0
fi

stop_mode

if [[ -f "$STATE_DIR/owned-toggle" ]]; then
    rm -f "$TOGGLE_DEST" "$STATE_DIR/owned-toggle"
fi
if [[ -f "$STATE_DIR/owned-launcher" ]]; then
    rm -f "$DESKTOP_DEST" "$LEGACY_DESKTOP_DEST" "$STATE_DIR/owned-launcher"
fi
if [[ -f "$STATE_DIR/owned-icon" ]]; then
    rm -f "$ICON_DEST" "$STATE_DIR/owned-icon"
fi
if [[ -f "$OWNED_SETTINGS_ICON_MARKER" ]]; then
    rm -f "$SETTINGS_ICON_DEST" "$OWNED_SETTINGS_ICON_MARKER"
fi
if [[ -f "$STATE_DIR/owned-settings" ]]; then
    rm -f "$SETTINGS_FILE" "$STATE_DIR/owned-settings"
    rmdir "$SETTINGS_DIR" 2>/dev/null || true
fi

if [[ -f "$OWNED_ENV_MARKER" && -f "$ENV_FILE" ]]; then
    sed -i '/^KWIN_WAYLAND_NO_PERMISSION_CHECKS=1$/d' "$ENV_FILE"
    sed -i '/^# Managed by Dual Screen Mode$/d' "$ENV_FILE"
    [[ -s "$ENV_FILE" ]] || rm -f "$ENV_FILE"
    rm -f "$OWNED_ENV_MARKER"
fi

if [[ -f "$OWNED_OVERRIDE_MARKER" ]]; then
    flatpak override --user --unset-env=KWIN_WAYLAND_NO_PERMISSION_CHECKS "$APP_ID" \
        2>/dev/null || true
    rm -f "$OWNED_OVERRIDE_MARKER"
fi

if [[ -f "$STATE_DIR/owned-uninstall-launcher" ]]; then
    rm -f "$UNINSTALL_DESKTOP_DEST" "$LEGACY_UNINSTALL_DESKTOP_DEST" "$STATE_DIR/owned-uninstall-launcher"
fi
if [[ -f "$STATE_DIR/owned-uninstaller" ]]; then
    rm -f "$UNINSTALL_SCRIPT_DEST" "$STATE_DIR/owned-uninstaller"
    rmdir "$UNINSTALL_APP_DIR" 2>/dev/null || true
fi
if [[ -f "$STATE_DIR/owned-management-app" ]]; then
    rm -f "$MANAGEMENT_SCRIPT_DEST" "$STATE_DIR/owned-management-app"
    rmdir "$UNINSTALL_APP_DIR" 2>/dev/null || true
fi
if [[ -f "$STATE_DIR/owned-management-launcher" ]]; then
    rm -f "$MANAGEMENT_LAUNCHER_DEST" "$STATE_DIR/owned-management-launcher"
    rmdir "$UNINSTALL_APP_DIR" 2>/dev/null || true
fi

if have notify-send; then
    notify-send "Dual Screen Mode" "Uninstalled. Sunshine, Moonlight, krfb, and backups remain." 2>/dev/null || true
fi
if (( ! AUTO_CONFIRM )); then
    ui_message "Dual Screen Mode was uninstalled.\n\nIts shortcuts and settings are gone. Sunshine, Moonlight, krfb, and your backups were left installed."
fi

