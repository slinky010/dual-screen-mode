#!/usr/bin/env bash

set -u
umask 077

VIRTUAL_NAME="${DUAL_SCREEN_VIRTUAL_NAME:-DualScreen}"
if [[ ! "$VIRTUAL_NAME" =~ ^[[:alnum:]_-]{1,32}$ ]]; then
    VIRTUAL_NAME="DualScreen"
fi
SUNSHINE_APP="dev.lizardbyte.app.Sunshine"
SUNSHINE_CONF="$HOME/.var/app/$SUNSHINE_APP/config/sunshine/sunshine.conf"
SETTINGS_FILE="$HOME/.config/dual-screen-mode/settings.conf"
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp}/dual-screen-mode"
LOCK_DIR="$RUNTIME_DIR/lock"
STATE_FILE="$RUNTIME_DIR/active"
VMON_PID_FILE="$RUNTIME_DIR/vmonitor.pid"
SUNSHINE_PID_FILE="$RUNTIME_DIR/sunshine.pid"
AUDIO_STATE_FILE="$RUNTIME_DIR/audio.state"
TOUCH_MAPPING_FILE="$RUNTIME_DIR/touch-mappings"
TOUCH_STATUS_FILE="$RUNTIME_DIR/touch-status"
TOUCH_WATCHER_PID_FILE="$RUNTIME_DIR/touch-watcher.pid"

# Prevent rapid double-clicks from starting duplicate processes.
notify_user() {
    if command -v notify-send >/dev/null 2>&1; then
        notify-send "Dual Screen Mode" "$1" 2>/dev/null || true
    fi
}

if ! mkdir -p "$RUNTIME_DIR" || ! chmod 700 "$RUNTIME_DIR" || [[ ! -O "$RUNTIME_DIR" ]]; then
    notify_user "Dual Screen Mode could not create a private runtime folder. Nothing was started."
    exit 1
fi
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

read_setting() {
    local key="$1"
    if [[ -f "$SETTINGS_FILE" ]]; then
        awk -F= -v wanted="$key" '$1 == wanted { print substr($0, index($0, "=") + 1); exit }' "$SETTINGS_FILE"
    fi
}

VIRTUAL_RESOLUTION="$(read_setting resolution)"
if [[ ! "$VIRTUAL_RESOLUTION" =~ ^[0-9]{3,5}x[0-9]{3,5}$ ]]; then
    VIRTUAL_RESOLUTION="1280x800"
fi

AUDIO_MODE="$(read_setting audio_mode)"
case "$AUDIO_MODE" in
    host|handheld|both) ;;
    *) AUDIO_MODE="host" ;;
esac

virtual_display_exists() {
    kscreen-doctor -j 2>/dev/null |
        grep -Fq "\"name\": \"Virtual-${VIRTUAL_NAME}\""
}

sunshine_running() {
    if flatpak ps --app --columns=application 2>/dev/null |
        grep -Fq "$SUNSHINE_APP"; then
        return 0
    fi

    # Some Flatpak versions do not report a system-installed app through the
    # columns query even while it is running. Sunshine's HTTPS UI is a better
    # readiness signal in that case.
    if command -v ss >/dev/null 2>&1 &&
        ss -ltn 2>/dev/null | grep -Eq ':47990[[:space:]]'; then
        return 0
    fi
    return 1
}

wait_for_sunshine() {
    for _ in {1..40}; do
        if sunshine_running; then
            return 0
        fi
        sleep 0.5
    done
    return 1
}

kwin_dbus() {
    local dbus_tool
    if command -v qdbus6 >/dev/null 2>&1; then
        dbus_tool="qdbus6"
    elif command -v qdbus >/dev/null 2>&1; then
        dbus_tool="qdbus"
    else
        return 127
    fi
    "$dbus_tool" "$@"
}

kwin_get_input_property() {
    local device="$1"
    local property="$2"
    kwin_dbus \
        org.kde.KWin \
        "/org/kde/KWin/InputDevice/$device" \
        org.freedesktop.DBus.Properties.Get \
        org.kde.KWin.InputDevice \
        "$property" 2>/dev/null || true
}

kwin_set_input_property() {
    local device="$1"
    local property="$2"
    local value="$3"
    kwin_dbus \
        org.kde.KWin \
        "/org/kde/KWin/InputDevice/$device" \
        org.freedesktop.DBus.Properties.Set \
        org.kde.KWin.InputDevice \
        "$property" \
        "$value" >/dev/null 2>&1
}

set_touch_status() {
    local value="$1"
    local temporary="$TOUCH_STATUS_FILE.tmp"
    printf '%s\n' "$value" > "$temporary" && mv -f "$temporary" "$TOUCH_STATUS_FILE"
}

touch_device_matches_sunshine() {
    local name="${1,,}"
    [[ "$name" == *libvirtualhid* && "$name" == *touch* ]] && return 0
    [[ "$name" == *touch\ passthrough* ]] && return 0
    [[ "$name" == *sunshine* && "$name" == *touch* ]] && return 0
    return 1
}

touch_mapping_saved_for() {
    local device="$1"
    [[ -f "$TOUCH_MAPPING_FILE" ]] || return 1
    awk -F '\t' -v wanted="$device" '$1 == wanted { found = 1 } END { exit !found }' \
        "$TOUCH_MAPPING_FILE"
}

map_sunshine_touch_devices() {
    local target="Virtual-${VIRTUAL_NAME}"
    local devices
    devices="$(kwin_dbus \
        org.kde.KWin \
        /org/kde/KWin/InputDevice \
        org.kde.KWin.InputDeviceManager.ListTouch 2>/dev/null)" || {
        set_touch_status unavailable
        return 2
    }

    local found=0
    local failed=0
    local device name old_output
    while IFS= read -r device; do
        [[ -n "$device" ]] || continue
        name="$(kwin_get_input_property "$device" name)"
        if ! touch_device_matches_sunshine "$name"; then
            continue
        fi

        found=1
        old_output="$(kwin_get_input_property "$device" outputName)"
        if [[ "$old_output" == "$target" ]]; then
            continue
        fi

        if ! touch_mapping_saved_for "$device"; then
            printf '%s\t%s\n' "$device" "$old_output" >> "$TOUCH_MAPPING_FILE"
        fi
        if ! kwin_set_input_property "$device" outputName "$target"; then
            failed=1
            continue
        fi
    done <<< "$devices"

    if (( failed )); then
        set_touch_status warning
        return 3
    fi
    if (( found )); then
        set_touch_status mapped
        return 0
    fi

    set_touch_status waiting
    return 1
}

touch_watcher_pid_is_ours() {
    local pid="$1"
    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    [[ -r "/proc/$pid/cmdline" && -O "/proc/$pid" ]] || return 1
    tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null |
        grep -Fq "dual-screen-mode"
}

start_touch_watcher() {
    command -v qdbus6 >/dev/null 2>&1 ||
        command -v qdbus >/dev/null 2>&1 || {
        set_touch_status unavailable
        return 0
    }

    (
        while [[ -f "$STATE_FILE" ]]; do
            map_sunshine_touch_devices >/dev/null 2>&1 || true
            sleep 1
        done
    ) >"$RUNTIME_DIR/touch-watcher.log" 2>&1 &
    echo "$!" > "$TOUCH_WATCHER_PID_FILE"
}

stop_touch_watcher() {
    if [[ -f "$TOUCH_WATCHER_PID_FILE" ]]; then
        local pid
        pid="$(cat "$TOUCH_WATCHER_PID_FILE" 2>/dev/null || true)"
        if touch_watcher_pid_is_ours "$pid"; then
            kill "$pid" 2>/dev/null || true
        fi
        rm -f "$TOUCH_WATCHER_PID_FILE"
    fi
}

restore_touch_mappings() {
    [[ -f "$TOUCH_MAPPING_FILE" ]] || {
        rm -f "$TOUCH_STATUS_FILE"
        return 0
    }

    local device old_output
    while IFS=$'\t' read -r device old_output; do
        [[ -n "$device" ]] || continue
        kwin_set_input_property "$device" outputName "$old_output" || true
    done < "$TOUCH_MAPPING_FILE"
    rm -f "$TOUCH_MAPPING_FILE" "$TOUCH_STATUS_FILE"
}

vmonitor_pid_is_ours() {
    local pid="$1"
    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    [[ -r "/proc/$pid/cmdline" ]] || return 1
    [[ -O "/proc/$pid" ]] || return 1
    tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null |
        grep -Fq "krfb-virtualmonitor" || return 1
    tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null |
        grep -Eq -- "(^|[[:space:]])--name[[:space:]]+$VIRTUAL_NAME([[:space:]]|$)"
}

get_config_line() {
    local key="$1"
    grep -m1 -E "^[[:space:]]*${key}[[:space:]]*=" "$SUNSHINE_CONF" 2>/dev/null || true
}

set_config_key() {
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

save_audio_state() {
    [[ -f "$AUDIO_STATE_FILE" ]] && return 0

    local stream_line="$(get_config_line stream_audio)"
    local stream_value="__MISSING__"
    if [[ -n "$stream_line" ]]; then
        stream_value="${stream_line#*=}"
        stream_value="${stream_value# }"
    fi

    printf 'stream_audio=%s\n' "$stream_value" > "$AUDIO_STATE_FILE"

    if command -v pactl >/dev/null 2>&1; then
        local sink=""
        local volume=""
        local mute=""
        sink="$(pactl get-default-sink 2>/dev/null || true)"
        if [[ -n "$sink" ]]; then
            volume="$(pactl get-sink-volume "$sink" 2>/dev/null |
                sed -n 's/.*: \([0-9][0-9]*\) \/.*/\1/p' | head -n 1)"
            mute="$(pactl get-sink-mute "$sink" 2>/dev/null | awk '{print $2}')"
        fi
        printf 'sink=%s\nvolume=%s\nmute=%s\n' "$sink" "$volume" "$mute" >> "$AUDIO_STATE_FILE"
    fi
}

apply_audio_mode() {
    save_audio_state

    case "$AUDIO_MODE" in
        host)
            # Host audio stays local. The stream is disabled for a clean default.
            set_config_key stream_audio disabled
            ;;
        handheld|both)
            set_config_key stream_audio enabled
            local sink
            sink="$(awk -F= '$1 == "sink" { print substr($0, index($0, "=") + 1); exit }' "$AUDIO_STATE_FILE" 2>/dev/null || true)"
            if [[ -n "$sink" ]] && command -v pactl >/dev/null 2>&1; then
                pactl set-sink-mute "$sink" 1 2>/dev/null ||
                    notify_user "Handheld audio is selected, but the host output could not be muted automatically."
            else
                notify_user "Handheld audio is selected. The host output could not be muted automatically."
            fi
            ;;
    esac
}

restore_audio_state() {
    [[ -f "$AUDIO_STATE_FILE" ]] || return 0

    local stream_value
    local sink
    local volume
    local mute
    stream_value="$(awk -F= '$1 == "stream_audio" { print substr($0, index($0, "=") + 1); exit }' "$AUDIO_STATE_FILE")"
    sink="$(awk -F= '$1 == "sink" { print substr($0, index($0, "=") + 1); exit }' "$AUDIO_STATE_FILE")"
    volume="$(awk -F= '$1 == "volume" { print substr($0, index($0, "=") + 1); exit }' "$AUDIO_STATE_FILE")"
    mute="$(awk -F= '$1 == "mute" { print substr($0, index($0, "=") + 1); exit }' "$AUDIO_STATE_FILE")"

    if [[ "$stream_value" == "__MISSING__" ]]; then
        sed -i '/^[[:space:]]*stream_audio[[:space:]]*=/d' "$SUNSHINE_CONF" 2>/dev/null || true
    elif [[ -n "$stream_value" ]]; then
        set_config_key stream_audio "$stream_value"
    fi

    if [[ -n "$sink" ]] && command -v pactl >/dev/null 2>&1; then
        [[ -n "$volume" ]] && pactl set-sink-volume "$sink" "$volume" 2>/dev/null || true
        [[ "$mute" == "yes" || "$mute" == "no" ]] && pactl set-sink-mute "$sink" "$mute" 2>/dev/null || true
    fi
    rm -f "$AUDIO_STATE_FILE"
}

stop_virtual_monitor() {
    if [[ -f "$VMON_PID_FILE" ]]; then
        local pid
        pid="$(cat "$VMON_PID_FILE" 2>/dev/null || true)"
        if vmonitor_pid_is_ours "$pid"; then
            kill -CONT "$pid" 2>/dev/null || true
            kill "$pid" 2>/dev/null || true
        fi
        rm -f "$VMON_PID_FILE"
    else
        # Fallback handles a monitor started manually before the toggle was installed.
        while IFS= read -r pid; do
            if vmonitor_pid_is_ours "$pid"; then
                kill -CONT "$pid" 2>/dev/null || true
                kill "$pid" 2>/dev/null || true
            fi
        done < <(pgrep -u "$(id -u)" -f '(^|/)krfb-virtualmonitor([[:space:]]|$)' 2>/dev/null || true)
    fi
}

turn_off() {
    # Restore KWin's input mapping before Sunshine exits and removes its
    # virtual touchscreen device.
    stop_touch_watcher
    restore_touch_mappings

    if [[ -f "$SUNSHINE_PID_FILE" ]]; then
        flatpak kill "$SUNSHINE_APP" 2>/dev/null || true
        rm -f "$SUNSHINE_PID_FILE"
    fi

    stop_virtual_monitor
    restore_audio_state
    rm -f "$STATE_FILE"
    notify_user "Dual Screen Mode disabled. Your previous audio settings were restored."
}

# Turn the mode off when our state marker says it is active.
if [[ -f "$STATE_FILE" ]]; then
    turn_off
    exit 0
fi

# Clear stale bookkeeping but do not touch unrelated processes.
restore_touch_mappings
rm -f "$VMON_PID_FILE" "$SUNSHINE_PID_FILE"

if ! command -v krfb-virtualmonitor >/dev/null 2>&1; then
    notify_user "krfb-virtualmonitor is not installed. Run Install Dual Screen Mode first."
    exit 1
fi
if ! command -v flatpak >/dev/null 2>&1; then
    notify_user "Flatpak is not installed. Run Install Dual Screen Mode first."
    exit 1
fi

# If setup is interrupted before the active marker is written, restore the
# host audio and stop only the processes started by this invocation.
startup_cleanup_needed=1
startup_cleanup() {
    if (( startup_cleanup_needed )); then
        stop_touch_watcher
        restore_touch_mappings
        restore_audio_state
        stop_virtual_monitor
        if [[ -f "$SUNSHINE_PID_FILE" ]]; then
            flatpak kill "$SUNSHINE_APP" 2>/dev/null || true
            rm -f "$SUNSHINE_PID_FILE"
        fi
    fi
    exit 130
}
trap startup_cleanup INT TERM

apply_audio_mode

# Start the virtual display if it is not already present.
if ! virtual_display_exists; then
    if ! command -v base64 >/dev/null 2>&1; then
        restore_audio_state
        notify_user "A secure temporary display password could not be generated. Nothing was started."
        exit 1
    fi
    VMON_PASSWORD="$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 8)"
    if [[ ! "$VMON_PASSWORD" =~ ^[[:alnum:]]{8}$ ]]; then
        restore_audio_state
        notify_user "A secure temporary display password could not be generated. Nothing was started."
        exit 1
    fi
    nohup krfb-virtualmonitor \
        --name "$VIRTUAL_NAME" \
        --resolution "$VIRTUAL_RESOLUTION" \
        --password "$VMON_PASSWORD" \
        --port 5900 \
        >"$RUNTIME_DIR/vmonitor.log" 2>&1 &

    echo "$!" > "$VMON_PID_FILE"

    for _ in {1..30}; do
        if virtual_display_exists; then
            break
        fi
        sleep 0.25
    done
fi

if ! virtual_display_exists; then
    restore_audio_state
    stop_virtual_monitor
    notify_user "Could not create the virtual display. Nothing was left running."
    exit 1
fi

# Start Sunshine only when it is not already running. If it was already
# running, leave ownership with the user and do not kill it on shutdown.
if ! sunshine_running; then
    nohup flatpak run "$SUNSHINE_APP" \
        >"$RUNTIME_DIR/sunshine.log" 2>&1 &

    echo "$!" > "$SUNSHINE_PID_FILE"
    if ! wait_for_sunshine; then
        restore_audio_state
        stop_virtual_monitor
        rm -f "$SUNSHINE_PID_FILE"
        notify_user "Sunshine did not become ready. Nothing was left running."
        exit 1
    fi
fi

map_sunshine_touch_devices >/dev/null 2>&1 || true
touch "$STATE_FILE"
start_touch_watcher
startup_cleanup_needed=0
trap - INT TERM
if [[ "$(cat "$TOUCH_STATUS_FILE" 2>/dev/null || true)" == "unavailable" ]]; then
    notify_user "Dual Screen Mode ready. KWin's touch-mapping tool was not found, so touch may need manual setup."
else
    notify_user "Dual Screen Mode ready. Connect your handheld. Touch routing will follow Sunshine's virtual touchscreen."
fi
