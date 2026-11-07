#!/usr/bin/env bash

set -u
umask 077

APP_ID="dev.lizardbyte.app.Sunshine"
SUNSHINE_CONF="$HOME/.var/app/$APP_ID/config/sunshine/sunshine.conf"
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
MOTION_MONITOR_DEST="$UNINSTALL_APP_DIR/motion_monitor.py"
MOTION_DISCOVERY_DEST="$UNINSTALL_APP_DIR/motion_discovery.py"
DISPLAY_LAYOUT_DEST="$UNINSTALL_APP_DIR/display_layout.py"
CEMU_PROFILE_DEST="$UNINSTALL_APP_DIR/cemu_profile.py"
UPDATE_SUPPORT_DEST="$UNINSTALL_APP_DIR/update_support.py"
MOTION_PROBE_DIR_DEST="$UNINSTALL_APP_DIR/motion_probe"
ICON_DEST="$HOME/.local/share/icons/dual-screen-mode.png"
SETTINGS_ICON_DEST="$HOME/.local/share/icons/dual-screen-mode-settings.png"
ENV_FILE="$HOME/.config/environment.d/dual-screen-mode.conf"
SETTINGS_FILE="$HOME/.config/dual-screen-mode/settings.conf"
SETTINGS_DIR="$HOME/.config/dual-screen-mode"
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp}/dual-screen-mode"
STARTING_FILE="$RUNTIME_DIR/starting"
START_CANCEL_FILE="$RUNTIME_DIR/start-cancel"
SUNSHINE_PID_FILE="$RUNTIME_DIR/sunshine.pid"
SUNSHINE_START_FILE="$RUNTIME_DIR/sunshine.start"
SUNSHINE_INSTANCE_FILE="$RUNTIME_DIR/sunshine.instance"
SUNSHINE_OWNED_FILE="$RUNTIME_DIR/sunshine.owned"
SUNSHINE_PREEXISTING_FILE="$RUNTIME_DIR/sunshine.preexisting"
SUNSHINE_SESSION_CONFIG_FILE="$RUNTIME_DIR/sunshine-config"
TOUCH_MAPPING_FILE="$RUNTIME_DIR/touch-mappings"
TOUCH_WATCHER_PID_FILE="$RUNTIME_DIR/touch-watcher.pid"
DISCOVERY_PID_FILE="$RUNTIME_DIR/motion-discovery.pid"
MOTION_PID_FILE="$RUNTIME_DIR/motion-monitor.pid"
STATE_DIR="$HOME/.local/state/dual-screen-mode"
VIRTUAL_NAME="DualScreen"
OWNED_ENV_MARKER="$STATE_DIR/owned-environment-setting"
OWNED_OVERRIDE_MARKER="$STATE_DIR/owned-sunshine-override"
OWNED_SUNSHINE_CONFIG_MARKER="$STATE_DIR/owned-sunshine-config"
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

run_bounded() {
    local seconds="$1"
    shift
    if have timeout; then
        timeout --kill-after=1s "${seconds}s" "$@"
    else
        "$@"
    fi
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
        terminate_process_tree "$pid"
        for _ in {1..10}; do
            [[ ! -d "/proc/$pid" ]] && break
            sleep 0.1
        done
    fi
}

motion_monitor_pid_is_ours() {
    local pid="$1"
    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    [[ -r "/proc/$pid/cmdline" && -O "/proc/$pid" ]] || return 1
    tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null |
        grep -Fq "$MOTION_MONITOR_DEST"
}

sunshine_pid_is_ours() {
    local pid="$1"
    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    [[ -r "/proc/$pid/cmdline" && -O "/proc/$pid" ]] || return 1

    if [[ -f "$SUNSHINE_START_FILE" ]]; then
        local expected_start actual_start
        expected_start="$(cat "$SUNSHINE_START_FILE" 2>/dev/null || true)"
        actual_start="$(awk '{ print $22 }' "/proc/$pid/stat" 2>/dev/null || true)"
        if [[ "$expected_start" =~ ^[0-9]+$ && "$actual_start" =~ ^[0-9]+$ &&
            "$expected_start" == "$actual_start" ]]; then
            return 0
        fi
    fi

    tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null |
        grep -Fq "$APP_ID" && return 0
    grep -Fq "$APP_ID" "/proc/$pid/cgroup" 2>/dev/null
}

motion_discovery_pid_is_ours() {
    local pid="$1"
    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    [[ -r "/proc/$pid/cmdline" && -O "/proc/$pid" ]] || return 1
    tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null |
        grep -Fq "dual-screen-mode"
}

touch_watcher_pid_is_ours() {
    local pid="$1"
    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    [[ -r "/proc/$pid/cmdline" && -O "/proc/$pid" ]] || return 1
    tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null |
        grep -Fq "dual-screen-mode"
}

terminate_process_tree() {
    local pid="$1"
    [[ "$pid" =~ ^[0-9]+$ ]] || return 0

    local child
    if have pgrep; then
        while IFS= read -r child; do
            [[ -n "$child" ]] || continue
            terminate_process_tree "$child"
        done < <(pgrep -P "$pid" 2>/dev/null || true)
    fi
    kill "$pid" 2>/dev/null || true
}

stop_runtime_process() {
    local pid_file="$1"
    local ownership_check="$2"
    [[ -f "$pid_file" ]] || return 0
    local pid
    pid="$(cat "$pid_file" 2>/dev/null || true)"
    local owned=0
    case "$ownership_check" in
        motion) motion_discovery_pid_is_ours "$pid" && owned=1 ;;
        touch) touch_watcher_pid_is_ours "$pid" && owned=1 ;;
        monitor) motion_monitor_pid_is_ours "$pid" && owned=1 ;;
    esac
    if (( owned )); then
        terminate_process_tree "$pid"
    fi
    rm -f "$pid_file"
}

stop_motion_monitor() {
    stop_runtime_process "$MOTION_PID_FILE" monitor
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
            run_bounded 3 "$dbus_tool" \
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

set_sunshine_config_key() {
    local key="$1"
    local value="$2"
    mkdir -p "$(dirname "$SUNSHINE_CONF")"
    touch "$SUNSHINE_CONF"
    if grep -Eq "^[[:space:]]*${key}[[:space:]]*=" "$SUNSHINE_CONF" 2>/dev/null; then
        sed -i -E "s|^[[:space:]]*${key}[[:space:]]*=.*$|${key} = ${value}|" "$SUNSHINE_CONF"
    else
        printf '%s = %s\n' "$key" "$value" >> "$SUNSHINE_CONF"
    fi
}

restore_audio_state() {
    [[ -f "$RUNTIME_DIR/audio.state" ]] || return 0

    local stream_value sink volume mute
    stream_value="$(awk -F= '$1 == "stream_audio" { print substr($0, index($0, "=") + 1); exit }' "$RUNTIME_DIR/audio.state")"
    sink="$(awk -F= '$1 == "sink" { print substr($0, index($0, "=") + 1); exit }' "$RUNTIME_DIR/audio.state")"
    volume="$(awk -F= '$1 == "volume" { print substr($0, index($0, "=") + 1); exit }' "$RUNTIME_DIR/audio.state")"
    mute="$(awk -F= '$1 == "mute" { print substr($0, index($0, "=") + 1); exit }' "$RUNTIME_DIR/audio.state")"

    if [[ "$stream_value" == "__MISSING__" ]]; then
        sed -i '/^[[:space:]]*stream_audio[[:space:]]*=/d' "$SUNSHINE_CONF" 2>/dev/null || true
    elif [[ -n "$stream_value" ]]; then
        set_sunshine_config_key stream_audio "$stream_value"
    fi
    if [[ -n "$sink" ]] && have pactl; then
        [[ -n "$volume" ]] && pactl set-sink-volume "$sink" "$volume" 2>/dev/null || true
        [[ "$mute" == "yes" || "$mute" == "no" ]] && pactl set-sink-mute "$sink" "$mute" 2>/dev/null || true
    fi
    rm -f "$RUNTIME_DIR/audio.state"
}

restore_sunshine_key() {
    local key="$1"
    local original="$2"
    [[ -f "$SUNSHINE_CONF" ]] || {
        [[ "$original" == "__MISSING__" ]] && return 0
        mkdir -p "$(dirname "$SUNSHINE_CONF")"
        : > "$SUNSHINE_CONF"
    }
    sed -i -E "/^[[:space:]]*${key}[[:space:]]*=/d" "$SUNSHINE_CONF"
    if [[ "$original" != "__MISSING__" && -n "$original" ]]; then
        printf '%s\n' "$original" >> "$SUNSHINE_CONF"
    fi
}

restore_sunshine_config() {
    [[ -f "$OWNED_SUNSHINE_CONFIG_MARKER" ]] || return 0
    local capture_line output_line
    capture_line="$(awk -F= '$1 == "capture_line" { print substr($0, index($0, "=") + 1); exit }' "$OWNED_SUNSHINE_CONFIG_MARKER")"
    output_line="$(awk -F= '$1 == "output_name_line" { print substr($0, index($0, "=") + 1); exit }' "$OWNED_SUNSHINE_CONFIG_MARKER")"
    [[ -n "$capture_line" ]] || capture_line="__MISSING__"
    [[ -n "$output_line" ]] || output_line="__MISSING__"
    restore_sunshine_key capture "$capture_line" || return 1
    restore_sunshine_key output_name "$output_line" || return 1
    rm -f "$OWNED_SUNSHINE_CONFIG_MARKER"
}

stop_mode() {
    if [[ -f "$STARTING_FILE" && -x "$TOGGLE_DEST" ]]; then
        touch "$START_CANCEL_FILE"
        for _ in {1..60}; do
            [[ ! -f "$STARTING_FILE" ]] && break
            sleep 0.1
        done
    fi
    if [[ -f "$RUNTIME_DIR/active" && -x "$TOGGLE_DEST" ]]; then
        "$TOGGLE_DEST" >/dev/null 2>&1 || true
    fi

    stop_runtime_process "$DISCOVERY_PID_FILE" motion
    stop_runtime_process "$TOUCH_WATCHER_PID_FILE" touch
    restore_touch_mappings
    stop_motion_monitor
    if [[ -f "$SUNSHINE_INSTANCE_FILE" ]]; then
        local sunshine_instance
        sunshine_instance="$(cat "$SUNSHINE_INSTANCE_FILE" 2>/dev/null || true)"
        if [[ -n "$sunshine_instance" ]]; then
            run_bounded 5 flatpak kill "$sunshine_instance" 2>/dev/null || true
        fi
    elif [[ -f "$SUNSHINE_PID_FILE" || -f "$SUNSHINE_OWNED_FILE" ]]; then
        local sunshine_pid
        sunshine_pid="$(cat "$SUNSHINE_PID_FILE" 2>/dev/null || true)"
        if [[ -f "$SUNSHINE_OWNED_FILE" ]] || sunshine_pid_is_ours "$sunshine_pid"; then
            run_bounded 5 flatpak kill "$APP_ID" 2>/dev/null || true
        fi
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
    restore_audio_state
    restore_sunshine_config
    rm -f "$RUNTIME_DIR/active" "$RUNTIME_DIR/stopping" "$STARTING_FILE" "$START_CANCEL_FILE" "$RUNTIME_DIR/vmonitor.pid" "$RUNTIME_DIR/sunshine.pid" "$SUNSHINE_START_FILE" "$SUNSHINE_INSTANCE_FILE" "$SUNSHINE_OWNED_FILE" "$SUNSHINE_PREEXISTING_FILE" "$SUNSHINE_SESSION_CONFIG_FILE" "$RUNTIME_DIR/motion-status" "$RUNTIME_DIR/motion-monitor.log" "$MOTION_PID_FILE" "$DISCOVERY_PID_FILE" "$TOUCH_WATCHER_PID_FILE"
}

if (( DRY_RUN )); then
    printf '%s\n' \
        "Would turn Dual Screen Mode off first, restoring saved audio state" \
        "Would remove the owned toggle: $TOGGLE_DEST" \
        "Would remove the owned launcher: $DESKTOP_DEST" \
        "Would remove the owned uninstall launcher: $UNINSTALL_DESKTOP_DEST" \
        "Would remove the settings app: $MANAGEMENT_SCRIPT_DEST" \
        "Would remove the motion monitor and diagnostics tool" \
        "Would remove the owned icon: $ICON_DEST" \
        "Would remove the owned settings icon: $SETTINGS_ICON_DEST" \
        "Would remove the owned display and audio choices: $SETTINGS_FILE" \
        "Would remove the owned KWin environment setting" \
        "Would remove the owned Sunshine Flatpak override" \
        "Would restore the owned Sunshine capture settings" \
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
    rm -f "$MANAGEMENT_SCRIPT_DEST" "$MOTION_MONITOR_DEST" "$MOTION_DISCOVERY_DEST" "$DISPLAY_LAYOUT_DEST" "$CEMU_PROFILE_DEST" "$UPDATE_SUPPORT_DEST" "$MOTION_PROBE_DIR_DEST/dsu_motion_probe.py" "$MOTION_PROBE_DIR_DEST/__init__.py"
    rmdir "$MOTION_PROBE_DIR_DEST" 2>/dev/null || true
    rm -f "$STATE_DIR/owned-management-app"
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

