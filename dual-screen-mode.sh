#!/usr/bin/env bash

set -u
umask 077

VIRTUAL_NAME="${DUAL_SCREEN_VIRTUAL_NAME:-DualScreen}"
SUNSHINE_APP="dev.lizardbyte.app.Sunshine"
SUNSHINE_CONF="$HOME/.var/app/$SUNSHINE_APP/config/sunshine/sunshine.conf"
SETTINGS_FILE="$HOME/.config/dual-screen-mode/settings.conf"
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp}/dual-screen-mode"
LOCK_DIR="$RUNTIME_DIR/lock"
STATE_FILE="$RUNTIME_DIR/active"
VMON_PID_FILE="$RUNTIME_DIR/vmonitor.pid"
SUNSHINE_PID_FILE="$RUNTIME_DIR/sunshine.pid"
AUDIO_STATE_FILE="$RUNTIME_DIR/audio.state"

mkdir -p "$RUNTIME_DIR"
chmod 700 "$RUNTIME_DIR" 2>/dev/null || true

# Prevent rapid double-clicks from starting duplicate processes.
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

notify_user() {
    if command -v notify-send >/dev/null 2>&1; then
        notify-send "Dual Screen Mode" "$1" 2>/dev/null || true
    fi
}

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

vmonitor_pid_is_ours() {
    local pid="$1"
    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    [[ -r "/proc/$pid/cmdline" ]] || return 1
    tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null |
        grep -Fq "krfb-virtualmonitor" || return 1
    tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null |
        grep -Fq -- "--name $VIRTUAL_NAME"
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
        pkill -CONT -f "krfb-virtualmonitor.*${VIRTUAL_NAME}" 2>/dev/null || true
        pkill -f "krfb-virtualmonitor.*${VIRTUAL_NAME}" 2>/dev/null || true
    fi
}

turn_off() {
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
    nohup krfb-virtualmonitor \
        --name "$VIRTUAL_NAME" \
        --resolution "$VIRTUAL_RESOLUTION" \
        --password dualscreen \
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

touch "$STATE_FILE"
startup_cleanup_needed=0
trap - INT TERM
notify_user "Dual Screen Mode ready. Connect your handheld."
