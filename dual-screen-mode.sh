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
LOCK_FILE="$RUNTIME_DIR/toggle.lock"
LOCK_DIR="$RUNTIME_DIR/lock"
STATE_FILE="$RUNTIME_DIR/active"
STARTING_FILE="$RUNTIME_DIR/starting"
START_CANCEL_FILE="$RUNTIME_DIR/start-cancel"
STOPPING_FILE="$RUNTIME_DIR/stopping"
DISABLED_AT_FILE="$RUNTIME_DIR/disabled-at"
TOGGLE_COOLDOWN_MS=1200
VMON_PID_FILE="$RUNTIME_DIR/vmonitor.pid"
SUNSHINE_PID_FILE="$RUNTIME_DIR/sunshine.pid"
SUNSHINE_START_FILE="$RUNTIME_DIR/sunshine.start"
SUNSHINE_INSTANCE_FILE="$RUNTIME_DIR/sunshine.instance"
SUNSHINE_OWNED_FILE="$RUNTIME_DIR/sunshine.owned"
SUNSHINE_PREEXISTING_FILE="$RUNTIME_DIR/sunshine.preexisting"
SUNSHINE_SESSION_CONFIG_FILE="$RUNTIME_DIR/sunshine-config"
AUDIO_STATE_FILE="$RUNTIME_DIR/audio.state"
TOUCH_MAPPING_FILE="$RUNTIME_DIR/touch-mappings"
TOUCH_STATUS_FILE="$RUNTIME_DIR/touch-status"
TOUCH_WATCHER_PID_FILE="$RUNTIME_DIR/touch-watcher.pid"
DISCOVERY_PID_FILE="$RUNTIME_DIR/motion-discovery.pid"
MOTION_MONITOR_PATH="$HOME/.local/share/dual-screen-mode/motion_monitor.py"
MOTION_DISCOVERY_PATH="$HOME/.local/share/dual-screen-mode/motion_discovery.py"
DISPLAY_LAYOUT_HELPER="$HOME/.local/share/dual-screen-mode/display_layout.py"
CEMU_PROFILE_HELPER="$HOME/.local/share/dual-screen-mode/cemu_profile.py"
MOTION_STATUS_FILE="$RUNTIME_DIR/motion-status"
MOTION_PID_FILE="$RUNTIME_DIR/motion-monitor.pid"
STATE_DIR="$HOME/.local/state/dual-screen-mode"
OWNED_SUNSHINE_CONFIG_MARKER="$STATE_DIR/owned-sunshine-config"

# Keep the toggle single-instance.  flock is preferred because the kernel
# releases it after a crash; the directory fallback keeps the launcher usable
# on minimal systems that do not ship util-linux's flock helper.
TOGGLE_LOCK_MODE="none"

notify_user() {
    if command -v notify-send >/dev/null 2>&1; then
        notify-send "Dual Screen Mode" "$1" 2>/dev/null || true
    fi
}

run_bounded() {
    local seconds="$1"
    shift
    if command -v timeout >/dev/null 2>&1; then
        timeout --kill-after=1s "${seconds}s" "$@"
    else
        "$@"
    fi
}

now_ms() {
    local value
    value="$(date '+%s%3N' 2>/dev/null || true)"
    if [[ "$value" =~ ^[0-9]+$ ]]; then
        printf '%s\n' "$value"
    else
        printf '%s000\n' "$(date '+%s')"
    fi
}

mark_disabled() {
    local temporary="${DISABLED_AT_FILE}.tmp.$$"
    printf '%s\n' "$(now_ms)" > "$temporary" && mv -f "$temporary" "$DISABLED_AT_FILE"
}

disabled_cooldown_active() {
    [[ -f "$DISABLED_AT_FILE" ]] || return 1

    local disabled_at now
    disabled_at="$(cat "$DISABLED_AT_FILE" 2>/dev/null || true)"
    now="$(now_ms)"
    if [[ "$disabled_at" =~ ^[0-9]+$ && "$now" =~ ^[0-9]+$ ]] &&
        (( now >= disabled_at && now - disabled_at < TOGGLE_COOLDOWN_MS )); then
        return 0
    fi
    rm -f "$DISABLED_AT_FILE"
    return 1
}

acquire_toggle_lock() {
    if command -v flock >/dev/null 2>&1; then
        exec 9>"$LOCK_FILE" || return 1
        if ! flock -n 9 2>/dev/null; then
            exec 9>&-
            return 1
        fi
        TOGGLE_LOCK_MODE="flock"
        return 0
    fi

    if ! mkdir "$LOCK_DIR" 2>/dev/null; then
        return 1
    fi
    TOGGLE_LOCK_MODE="directory"
    return 0
}

release_toggle_lock() {
    case "$TOGGLE_LOCK_MODE" in
        flock)
            flock -u 9 2>/dev/null || true
            exec 9>&-
            ;;
        directory)
            rmdir "$LOCK_DIR" 2>/dev/null || true
            ;;
    esac
    TOGGLE_LOCK_MODE="none"
}

close_toggle_lock_for_child() {
    if [[ "$TOGGLE_LOCK_MODE" == "flock" ]]; then
        exec 9>&-
    fi
}

terminate_process_tree() {
    local pid="$1"
    [[ "$pid" =~ ^[0-9]+$ ]] || return 0

    local child
    if command -v pgrep >/dev/null 2>&1; then
        while IFS= read -r child; do
            [[ -n "$child" ]] || continue
            terminate_process_tree "$child"
        done < <(pgrep -P "$pid" 2>/dev/null || true)
    fi
    kill "$pid" 2>/dev/null || true
}

if ! mkdir -p "$RUNTIME_DIR" || ! chmod 700 "$RUNTIME_DIR" || [[ ! -O "$RUNTIME_DIR" ]]; then
    notify_user "Dual Screen Mode could not create a private runtime folder. Nothing was started."
    exit 1
fi
startup_timing() {
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S.%3N')" "$1" >> "$RUNTIME_DIR/startup.log"
}
startup_timing "toggle-start"
if ! acquire_toggle_lock; then
    # A second click during startup is a cancellation request, not a silent
    # no-op. The startup owner will see this marker and unwind everything it
    # created before the active state is published.
    if [[ -f "$STARTING_FILE" ]]; then
        touch "$START_CANCEL_FILE"
    fi
    exit 0
fi
trap release_toggle_lock EXIT

# A normal double-click sends two launcher invocations.  The lock handles
# overlap; this short cooldown also covers a fast shutdown that finishes
# before the second desktop click is delivered, so that click cannot restart
# the mode immediately after disabling it.
if [[ ! -f "$STATE_FILE" ]] && disabled_cooldown_active; then
    exit 0
fi

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

position_virtual_display() {
    # KDE places a newly-created output wherever its current layout happens
    # to put it. Give the virtual screen a predictable starting position:
    # centered below the main physical display.
    command -v python3 >/dev/null 2>&1 || return 0

    local layout placement output_id target_x target_y
    layout="$(kscreen-doctor -j 2>/dev/null || true)"
    [[ -n "$layout" ]] || return 0

    placement="$(printf '%s' "$layout" | python3 "$DISPLAY_LAYOUT_HELPER" "$VIRTUAL_NAME" "$VIRTUAL_RESOLUTION" 2>/dev/null || true)"

    read -r output_id target_x target_y <<< "$placement"
    [[ "$output_id" =~ ^[[:alnum:]_-]+$ ]] || return 0
    [[ "$target_x" =~ ^-?[0-9]+$ && "$target_y" =~ ^-?[0-9]+$ ]] || return 0

    kscreen-doctor "output.${output_id}.position.${target_x},${target_y}" >/dev/null 2>&1 || true
}

sunshine_flatpak_running() {
    if run_bounded 3 flatpak ps --app --columns=application 2>/dev/null |
        grep -Fq "$SUNSHINE_APP"; then
        return 0
    fi

    return 1
}

sunshine_flatpak_instance() {
    run_bounded 3 flatpak ps --app --columns=instance,application,pid 2>/dev/null |
        awk -v app="$SUNSHINE_APP" '$2 == app && $1 != "" { print $1; exit }'
}

sunshine_flatpak_pid() {
    local pid
    pid="$(run_bounded 3 flatpak ps --app --columns=instance,application,pid 2>/dev/null |
        awk -v app="$SUNSHINE_APP" '$2 == app && $3 ~ /^[0-9]+$/ { print $3; exit }')"
    if [[ "$pid" =~ ^[0-9]+$ ]]; then
        printf '%s\n' "$pid"
        return 0
    fi

    # Older Flatpak versions may not expose the instance column. Keep the
    # simpler query as a compatibility fallback.
    run_bounded 3 flatpak ps --app --columns=application,pid 2>/dev/null |
        awk -v app="$SUNSHINE_APP" '$1 == app && $2 ~ /^[0-9]+$/ { print $2; exit }'
}

sunshine_running() {
    if sunshine_flatpak_running; then
        return 0
    fi

    # Some Flatpak versions do not report a system-installed app through the
    # columns query even while it is running. Sunshine's HTTPS UI is a better
    # readiness signal in that case.
    if command -v ss >/dev/null 2>&1 &&
        run_bounded 3 ss -ltn 2>/dev/null | grep -Eq ':47990[[:space:]]'; then
        return 0
    fi
    return 1
}

sunshine_pid_is_ours() {
    local pid="$1"
    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    [[ -r "/proc/$pid/cmdline" && -O "/proc/$pid" ]] || return 1

    # Flatpak may exec Sunshine in place, so the final process command line
    # does not always retain the app ID that was used to launch it. When DSM
    # recorded the process start time, that identity is the authoritative
    # ownership check and survives that exec.
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
        grep -Fq "$SUNSHINE_APP" && return 0

    # Keep compatibility with an older DSM runtime file after Flatpak has
    # replaced the command line. The app ID normally remains in its cgroup.
    grep -Fq "$SUNSHINE_APP" "/proc/$pid/cgroup" 2>/dev/null
}

record_sunshine_identity() {
    local launcher_pid="$1"
    local pid="$launcher_pid"
    local detected_pid
    local instance
    detected_pid="$(sunshine_flatpak_pid || true)"
    if [[ "$detected_pid" =~ ^[0-9]+$ ]]; then
        pid="$detected_pid"
    fi
    printf '%s\n' "$pid" > "$SUNSHINE_PID_FILE"
    chmod 600 "$SUNSHINE_PID_FILE"

    instance="$(sunshine_flatpak_instance || true)"
    if [[ -n "$instance" ]]; then
        printf '%s\n' "$instance" > "$SUNSHINE_INSTANCE_FILE"
        chmod 600 "$SUNSHINE_INSTANCE_FILE"
    else
        rm -f "$SUNSHINE_INSTANCE_FILE"
    fi

    local start_time
    start_time="$(awk '{ print $22 }' "/proc/$pid/stat" 2>/dev/null || true)"
    if [[ "$start_time" =~ ^[0-9]+$ ]]; then
        printf '%s\n' "$start_time" > "$SUNSHINE_START_FILE"
        chmod 600 "$SUNSHINE_START_FILE"
    else
        rm -f "$SUNSHINE_START_FILE"
    fi
    touch "$SUNSHINE_OWNED_FILE"
}

wait_for_process_exit() {
    local pid="$1"
    [[ "$pid" =~ ^[0-9]+$ ]] || return 0
    for _ in {1..20}; do
        [[ ! -d "/proc/$pid" ]] && return 0
        sleep 0.1
    done
    return 1
}

stop_owned_sunshine() {
    local should_stop=0
    local sunshine_target="$SUNSHINE_APP"
    local owned_pid=""
    if [[ -f "$SUNSHINE_PID_FILE" ]]; then
        local sunshine_pid
        sunshine_pid="$(cat "$SUNSHINE_PID_FILE" 2>/dev/null || true)"
        if sunshine_pid_is_ours "$sunshine_pid"; then
            should_stop=1
            owned_pid="$sunshine_pid"
        fi
    fi
    if [[ -f "$SUNSHINE_INSTANCE_FILE" ]]; then
        local sunshine_instance
        sunshine_instance="$(cat "$SUNSHINE_INSTANCE_FILE" 2>/dev/null || true)"
        if [[ -n "$sunshine_instance" ]]; then
            sunshine_target="$sunshine_instance"
            should_stop=1
        fi
    fi
    [[ -f "$SUNSHINE_OWNED_FILE" ]] && should_stop=1

    local result=0
    if (( should_stop )); then
        run_bounded 5 flatpak kill "$sunshine_target" 2>/dev/null || result=1
        wait_for_process_exit "$owned_pid" || result=1
        for _ in {1..20}; do
            if ! sunshine_flatpak_running; then
                break
            fi
            sleep 0.25
        done
        sunshine_flatpak_running && result=1
    fi
    rm -f "$SUNSHINE_PID_FILE" "$SUNSHINE_START_FILE" "$SUNSHINE_INSTANCE_FILE" "$SUNSHINE_OWNED_FILE"
    return "$result"
}

wait_for_sunshine() {
    for _ in {1..40}; do
        if sunshine_running; then
            return 0
        fi
        if declare -F startup_cancel_requested >/dev/null 2>&1 && startup_cancel_requested; then
            return 2
        fi
        sleep 0.5
    done
    return 1
}

start_or_refresh_sunshine() {
    # Sunshine reads output_name when it starts. Refresh an already-running
    # Flatpak instance so a previously loaded physical-display target cannot
    # survive into this mode. Do not touch an unrelated native/system
    # Sunshine process that merely owns the streaming port.
    if sunshine_running; then
        if ! sunshine_flatpak_running; then
            startup_fail "Sunshine is already running outside the supported Flatpak setup. Close that Sunshine instance, then try Dual Screen Mode again."
        fi
        printf '%s\n' 1 > "$SUNSHINE_PREEXISTING_FILE"
        local previous_instance previous_pid
        previous_instance="$(sunshine_flatpak_instance || true)"
        previous_pid="$(sunshine_flatpak_pid || true)"
        startup_timing "sunshine-restart"
        if [[ -n "$previous_instance" ]]; then
            run_bounded 5 flatpak kill "$previous_instance" 2>/dev/null ||
                startup_fail "Sunshine could not be refreshed for the virtual display. Nothing was left running."
        else
            run_bounded 5 flatpak kill "$SUNSHINE_APP" 2>/dev/null ||
            startup_fail "Sunshine could not be refreshed for the virtual display. Nothing was left running."
        fi
        for _ in {1..20}; do
            if startup_cancel_requested; then
                startup_fail "Dual Screen Mode startup was cancelled. Your previous Sunshine session will be restored."
            fi
            if ! sunshine_running; then
                break
            fi
            sleep 0.25
        done
        wait_for_process_exit "$previous_pid" || true
        if sunshine_running; then
            startup_fail "Sunshine did not finish restarting. Nothing was left running."
        fi
    else
        printf '%s\n' 0 > "$SUNSHINE_PREEXISTING_FILE"
    fi

    startup_timing "sunshine-start"
    nohup flatpak run "$SUNSHINE_APP" \
        >"$RUNTIME_DIR/sunshine.log" 2>&1 9>&- &

    local launcher_pid="$!"
    printf '%s\n' "$launcher_pid" > "$SUNSHINE_PID_FILE"
    chmod 600 "$SUNSHINE_PID_FILE"
    touch "$SUNSHINE_OWNED_FILE"
    if ! wait_for_sunshine; then
        if startup_cancel_requested; then
            startup_fail "Dual Screen Mode startup was cancelled. Your previous Sunshine session will be restored."
        fi
        startup_fail "Sunshine did not become ready. Nothing was left running."
    fi
    record_sunshine_identity "$launcher_pid"
}

restart_preexisting_sunshine() {
    [[ "$(cat "$SUNSHINE_PREEXISTING_FILE" 2>/dev/null || true)" == "1" ]] || {
        rm -f "$SUNSHINE_PREEXISTING_FILE"
        return 0
    }

    if ! sunshine_running; then
        nohup flatpak run "$SUNSHINE_APP" \
            >"$RUNTIME_DIR/sunshine.log" 2>&1 9>&- &
        local restored=0
        for _ in {1..40}; do
            if sunshine_running; then
                restored=1
                break
            fi
            sleep 0.5
        done
        if (( ! restored )); then
            return 1
        fi
    fi

    rm -f "$SUNSHINE_PREEXISTING_FILE" "$SUNSHINE_PID_FILE" "$SUNSHINE_START_FILE" "$SUNSHINE_INSTANCE_FILE" "$SUNSHINE_OWNED_FILE"
    return 0
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
    run_bounded 3 "$dbus_tool" "$@"
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
        close_toggle_lock_for_child
        while [[ -f "$STATE_FILE" && ! -f "$STOPPING_FILE" ]]; do
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
            terminate_process_tree "$pid"
            for _ in {1..10}; do
                [[ ! -d "/proc/$pid" ]] && break
                sleep 0.1
            done
            if [[ -d "/proc/$pid" ]]; then
                kill -INT "$pid" 2>/dev/null || true
                for _ in {1..10}; do
                    [[ ! -d "/proc/$pid" ]] && break
                    sleep 0.1
                done
            fi
        fi
        rm -f "$TOUCH_WATCHER_PID_FILE"
    fi
}

motion_monitor_pid_is_ours() {
    local pid="$1"
    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    [[ -r "/proc/$pid/cmdline" && -O "/proc/$pid" ]] || return 1
    tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null |
        grep -Fq "$MOTION_MONITOR_PATH"
}

motion_enabled() {
    [[ "$(read_setting motion_enabled)" == "1" ]]
}

discover_motion_host() {
    motion_enabled || return 1
    local host port discovered temporary
    host="$(read_setting motion_host)"
    port="$(read_setting motion_port)"
    [[ "$port" =~ ^[0-9]+$ && "$port" -ge 1 && "$port" -le 65535 ]] || port=26760
    command -v python3 >/dev/null 2>&1 || return 1
    [[ -f "$MOTION_DISCOVERY_PATH" ]] || return 1
    if [[ -n "$host" ]]; then
        discovered="$(python3 "$MOTION_DISCOVERY_PATH" --port "$port" --preferred-host "$host" 2>/dev/null | head -n 1)"
    else
        discovered="$(python3 "$MOTION_DISCOVERY_PATH" --port "$port" 2>/dev/null | head -n 1)"
    fi
    [[ "$discovered" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || return 1
    [[ -f "$SETTINGS_FILE" ]] || return 1
    # A matching address means the saved endpoint answered the DSU probe. It
    # is safe to use it for Cemu even though the settings file needs no write.
    [[ "$discovered" == "$host" ]] && return 0
    temporary="${SETTINGS_FILE}.tmp.$$"
    awk -v discovered="$discovered" '
        BEGIN { updated = 0 }
        /^motion_host=/ { print "motion_host=" discovered; updated = 1; next }
        { print }
        END { if (!updated) print "motion_host=" discovered }
    ' "$SETTINGS_FILE" > "$temporary" || { rm -f "$temporary"; return 1; }
    chmod 600 "$temporary"
    mv -f "$temporary" "$SETTINGS_FILE" || return 1
    if [[ -n "$host" ]]; then
        notify_user "Deck address updated to $discovered. Motion monitoring will use the new address."
    else
        notify_user "Deck found automatically at $discovered. Motion monitoring will start with Dual Screen Mode."
    fi
    return 0
}

motion_discovery_pid_is_ours() {
    local pid="$1"
    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    [[ -r "/proc/$pid/cmdline" && -O "/proc/$pid" ]] || return 1
    tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null |
        grep -Fq "dual-screen-mode"
}

stop_motion_discovery() {
    if [[ -f "$DISCOVERY_PID_FILE" ]]; then
        local pid
        pid="$(cat "$DISCOVERY_PID_FILE" 2>/dev/null || true)"
        if motion_discovery_pid_is_ours "$pid"; then
            terminate_process_tree "$pid"
            for _ in {1..10}; do
                [[ -d "/proc/$pid" ]] || break
                sleep 0.1
            done
        fi
        rm -f "$DISCOVERY_PID_FILE"
    fi
}

sync_cemu_profile() {
    motion_enabled || return 0
    command -v python3 >/dev/null 2>&1 || return 0
    [[ -f "$CEMU_PROFILE_HELPER" ]] || return 0

    local host port slot result backup_dir
    host="$(read_setting motion_host)"
    port="$(read_setting motion_port)"
    slot="$(read_setting motion_slot)"
    [[ "$host" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || return 0
    [[ "$port" =~ ^[0-9]+$ && "$port" -ge 1 && "$port" -le 65535 ]] || port=26760
    [[ "$slot" =~ ^[0-3]$ ]] || slot=0

    backup_dir="$HOME/.local/state/dual-screen-mode/backups/$(date +%Y%m%d-%H%M%S)/cemu"
    result="$(python3 "$CEMU_PROFILE_HELPER" \
        --host "$host" \
        --port "$port" \
        --slot "$slot" \
        --backup-dir "$backup_dir" 2>/dev/null || true)"
    case "$result" in
        UPDATED*|UNCHANGED*)
            notify_user "Cemu's Deck Gyro profile is ready. Open Cemu Input settings and select Dual Screen Mode Deck Gyro."
            ;;
        ERROR*)
            notify_user "Cemu's gyro profile could not be updated. Your existing Cemu settings were left unchanged."
            ;;
    esac
}

start_motion_discovery() {
    motion_enabled || return 0
    command -v python3 >/dev/null 2>&1 || return 0
    [[ -f "$MOTION_DISCOVERY_PATH" ]] || return 0

    if [[ -f "$DISCOVERY_PID_FILE" ]]; then
        local existing_pid
        existing_pid="$(cat "$DISCOVERY_PID_FILE" 2>/dev/null || true)"
        if motion_discovery_pid_is_ours "$existing_pid"; then
            return 0
        fi
        rm -f "$DISCOVERY_PID_FILE"
    fi

    startup_timing "motion-discovery-start"
    (
        close_toggle_lock_for_child
        # Do not rewrite Cemu from a merely syntactically valid saved address.
        # The discovery helper must first receive a real DSU response.
        if discover_motion_host; then
            sync_cemu_profile
        fi
        startup_timing "motion-discovery-finished"
        if [[ -f "$START_CANCEL_FILE" ]]; then
            rm -f "$DISCOVERY_PID_FILE"
            exit 0
        fi
        if [[ -f "$STATE_FILE" && ! -f "$STOPPING_FILE" ]]; then
            # A stale saved address may have been used to start the first
            # monitor. Restart it after discovery so a changed Deck address
            # takes effect immediately.
            stop_motion_monitor
            start_motion_monitor
        fi
        rm -f "$DISCOVERY_PID_FILE"
        if [[ -f "$STATE_FILE" && ! -f "$START_CANCEL_FILE" && ! -f "$STOPPING_FILE" &&
            -z "$(read_setting motion_host)" ]]; then
            notify_user "Motion is enabled, but the Deck was not found automatically. Open Dual Screen Mode Settings to use Find Deck or enter its address."
        fi
    ) >"$RUNTIME_DIR/motion-discovery.log" 2>&1 &
    echo "$!" > "$DISCOVERY_PID_FILE"
}

stop_motion_monitor() {
    if [[ -f "$MOTION_PID_FILE" ]]; then
        local pid
        pid="$(cat "$MOTION_PID_FILE" 2>/dev/null || true)"
        if motion_monitor_pid_is_ours "$pid"; then
            kill "$pid" 2>/dev/null || true
            for _ in {1..10}; do
                [[ -d "/proc/$pid" ]] || break
                sleep 0.1
            done
        fi
        rm -f "$MOTION_PID_FILE"
    fi
}

start_motion_monitor() {
    if ! motion_enabled; then
        rm -f "$MOTION_PID_FILE"
        return 0
    fi

    local host port slot
    host="$(read_setting motion_host)"
    port="$(read_setting motion_port)"
    slot="$(read_setting motion_slot)"
    if [[ -z "$host" || ! "$port" =~ ^[0-9]+$ || "$port" -lt 1 || "$port" -gt 65535 || ! "$slot" =~ ^[0-3]$ ]]; then
        if [[ ! -f "$DISCOVERY_PID_FILE" ]]; then
            notify_user "Motion is enabled, but the Deck was not found automatically. Open Dual Screen Mode Settings to use Find Deck or enter its address."
        fi
        return 0
    fi
    if [[ -f "$MOTION_PID_FILE" ]]; then
        local existing_pid
        existing_pid="$(cat "$MOTION_PID_FILE" 2>/dev/null || true)"
        if motion_monitor_pid_is_ours "$existing_pid"; then
            return 0
        fi
        rm -f "$MOTION_PID_FILE"
    fi
    if ! command -v python3 >/dev/null 2>&1 || [[ ! -f "$MOTION_MONITOR_PATH" ]]; then
        notify_user "Motion is enabled, but its health monitor is not installed. Re-run setup to add it."
        return 0
    fi

    nohup python3 "$MOTION_MONITOR_PATH" \
        --host "$host" \
        --port "$port" \
        --slot "$slot" \
        --status-file "$MOTION_STATUS_FILE" \
        --pid-file "$MOTION_PID_FILE" \
        >"$RUNTIME_DIR/motion-monitor.log" 2>&1 9>&- &
    printf '%s\n' "$!" > "$MOTION_PID_FILE"
    chmod 600 "$MOTION_PID_FILE"
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

save_sunshine_session_config() {
    [[ -f "$SUNSHINE_SESSION_CONFIG_FILE" ]] && return 0

    local original_capture original_output
    original_capture="$(get_config_line capture)"
    original_output="$(get_config_line output_name)"
    mkdir -p "$RUNTIME_DIR" || return 1
    printf '%s\n' \
        "capture_line=${original_capture:-__MISSING__}" \
        "output_name_line=${original_output:-__MISSING__}" > "$SUNSHINE_SESSION_CONFIG_FILE" || return 1
    chmod 600 "$SUNSHINE_SESSION_CONFIG_FILE"
}

restore_sunshine_key() {
    local key="$1"
    local original="$2"
    [[ -f "$SUNSHINE_CONF" ]] || {
        [[ "$original" == "__MISSING__" ]] && return 0
        mkdir -p "$(dirname "$SUNSHINE_CONF")" || return 1
        : > "$SUNSHINE_CONF" || return 1
    }
    sed -i -E "/^[[:space:]]*${key}[[:space:]]*=/d" "$SUNSHINE_CONF" || return 1
    if [[ "$original" != "__MISSING__" && -n "$original" ]]; then
        printf '%s\n' "$original" >> "$SUNSHINE_CONF" || return 1
    fi
}

restore_sunshine_session_config() {
    local config_marker="$SUNSHINE_SESSION_CONFIG_FILE"
    if [[ ! -f "$config_marker" && -f "$OWNED_SUNSHINE_CONFIG_MARKER" ]]; then
        # The installer may already have recorded the user's pre-DSM values.
        # Reuse that marker for a clean toggle-off even when the runtime did
        # not need to rewrite the same target values at startup.
        config_marker="$OWNED_SUNSHINE_CONFIG_MARKER"
    fi
    [[ -f "$config_marker" ]] || return 0

    local capture_line output_line
    capture_line="$(awk -F= '$1 == "capture_line" { print substr($0, index($0, "=") + 1); exit }' "$config_marker")"
    output_line="$(awk -F= '$1 == "output_name_line" { print substr($0, index($0, "=") + 1); exit }' "$config_marker")"
    [[ -n "$capture_line" ]] || capture_line="__MISSING__"
    [[ -n "$output_line" ]] || output_line="__MISSING__"
    restore_sunshine_key capture "$capture_line" || return 1
    restore_sunshine_key output_name "$output_line" || return 1
    rm -f "$SUNSHINE_SESSION_CONFIG_FILE"
}

ensure_sunshine_capture_config() {
    if grep -Eq "^[[:space:]]*capture[[:space:]]*=[[:space:]]*kwin[[:space:]]*$" "$SUNSHINE_CONF" 2>/dev/null &&
        grep -Eq "^[[:space:]]*output_name[[:space:]]*=[[:space:]]*Virtual-${VIRTUAL_NAME}[[:space:]]*$" "$SUNSHINE_CONF" 2>/dev/null; then
        return 0
    fi

    # Older installs and updates may not have the current setup marker. Save
    # the user's original values before repairing the runtime target so the
    # uninstaller can still restore them later.
    save_sunshine_session_config || return 1
    if [[ ! -f "$OWNED_SUNSHINE_CONFIG_MARKER" ]]; then
        local original_capture original_output
        original_capture="$(get_config_line capture)"
        original_output="$(get_config_line output_name)"
        mkdir -p "$STATE_DIR" || return 1
        printf '%s\n' \
            "capture_line=${original_capture:-__MISSING__}" \
            "output_name_line=${original_output:-__MISSING__}" > "$OWNED_SUNSHINE_CONFIG_MARKER" || return 1
    fi

    set_config_key capture kwin
    set_config_key output_name "Virtual-${VIRTUAL_NAME}"
    grep -Eq "^[[:space:]]*capture[[:space:]]*=[[:space:]]*kwin[[:space:]]*$" "$SUNSHINE_CONF" 2>/dev/null &&
        grep -Eq "^[[:space:]]*output_name[[:space:]]*=[[:space:]]*Virtual-${VIRTUAL_NAME}[[:space:]]*$" "$SUNSHINE_CONF" 2>/dev/null
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
            terminate_process_tree "$pid"
            for _ in {1..10}; do
                [[ ! -d "/proc/$pid" ]] && break
                sleep 0.1
            done
            if [[ -d "/proc/$pid" ]]; then
                kill -INT "$pid" 2>/dev/null || true
                for _ in {1..10}; do
                    [[ ! -d "/proc/$pid" ]] && break
                    sleep 0.1
                done
            fi
        fi
        rm -f "$VMON_PID_FILE"
    fi

    # Fallback handles a monitor started by an older DSM copy before the PID
    # file was written, and also catches a launcher process that replaced the
    # recorded PID during exec.
    while IFS= read -r pid; do
        if vmonitor_pid_is_ours "$pid"; then
            kill -CONT "$pid" 2>/dev/null || true
            terminate_process_tree "$pid"
            for _ in {1..10}; do
                [[ ! -d "/proc/$pid" ]] && break
                sleep 0.1
            done
        fi
    done < <(pgrep -u "$(id -u)" -f '(^|/)krfb-virtualmonitor([[:space:]]|$)' 2>/dev/null || true)
}

turn_off() {
    local cleanup_warning=0
    touch "$STOPPING_FILE"
    # Restore KWin's input mapping before Sunshine exits and removes its
    # virtual touchscreen device.
    stop_motion_discovery
    stop_touch_watcher
    stop_motion_monitor
    restore_touch_mappings

    stop_owned_sunshine || cleanup_warning=1

    stop_virtual_monitor
    restore_audio_state
    if ! restore_sunshine_session_config; then
        cleanup_warning=1
    elif ! restart_preexisting_sunshine; then
        cleanup_warning=1
    fi
    rm -f "$STATE_FILE"
    mark_disabled
    rm -f "$STOPPING_FILE"
    if (( cleanup_warning )); then
        notify_user "Dual Screen Mode disabled, but Sunshine needed attention while it was being restored. Check the Sunshine status before reconnecting."
    else
        notify_user "Dual Screen Mode disabled. Your previous audio and Sunshine settings were restored."
    fi
}

turn_off_interrupted() {
    # If the user interrupts a shutdown, leave a clean state marker so the
    # next toggle can run the stale-resource cleanup path instead of getting
    # trapped behind an active session forever.
    trap - INT TERM
    rm -f "$STATE_FILE" "$STOPPING_FILE"
    mark_disabled
    exit 130
}

# Turn the mode off when our state marker says it is active.
if [[ -f "$STATE_FILE" ]]; then
    trap turn_off_interrupted INT TERM
    turn_off
    exit 0
fi

# Clear stale bookkeeping but do not touch unrelated processes.
rm -f "$STOPPING_FILE"
stop_motion_discovery
stop_touch_watcher
stop_motion_monitor
restore_touch_mappings
stop_owned_sunshine
if [[ -f "$VMON_PID_FILE" ]]; then
    stop_virtual_monitor
fi
restore_audio_state
if restore_sunshine_session_config; then
    restart_preexisting_sunshine || true
fi
rm -f "$VMON_PID_FILE"

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
virtual_display_created=0
touch "$STARTING_FILE"
rm -f "$START_CANCEL_FILE"
startup_cancel_requested() {
    [[ -f "$START_CANCEL_FILE" ]]
}
cleanup_startup_resources() {
    if (( startup_cleanup_needed )); then
        stop_motion_discovery
        stop_touch_watcher
        stop_motion_monitor
        restore_touch_mappings
        stop_owned_sunshine || true
        if (( virtual_display_created )); then
            stop_virtual_monitor
        fi
        restore_audio_state
        if restore_sunshine_session_config; then
            restart_preexisting_sunshine || true
        fi
        rm -f "$STATE_FILE" "$STARTING_FILE" "$START_CANCEL_FILE" "$STOPPING_FILE"
    fi
}
startup_fail() {
    local message="$1"
    cleanup_startup_resources
    startup_cleanup_needed=0
    notify_user "$message"
    exit 1
}
startup_exit_cleanup() {
    local status="$1"
    trap - EXIT
    cleanup_startup_resources
    startup_cleanup_needed=0
    release_toggle_lock
    exit "$status"
}
startup_cleanup() {
    cleanup_startup_resources
    startup_cleanup_needed=0
    exit 130
}
trap 'startup_exit_cleanup "$?"' EXIT
trap startup_cleanup INT TERM

# Discover the Deck and prepare emulator profiles in parallel with display
# startup. The full retry and local-network scan still runs, but it no longer
# blocks the first virtual-screen launch.
start_motion_discovery
if startup_cancel_requested; then
    startup_fail "Dual Screen Mode startup was cancelled. Nothing was left running."
fi

apply_audio_mode
if startup_cancel_requested; then
    startup_fail "Dual Screen Mode startup was cancelled. Nothing was left running."
fi
startup_timing "display-start"

# Start the virtual display if it is not already present.
if ! virtual_display_exists; then
    if ! command -v base64 >/dev/null 2>&1; then
        startup_fail "A secure temporary display password could not be generated. Nothing was started."
    fi
    VMON_PASSWORD="$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 8)"
    if [[ ! "$VMON_PASSWORD" =~ ^[[:alnum:]]{8}$ ]]; then
        startup_fail "A secure temporary display password could not be generated. Nothing was started."
    fi
    nohup krfb-virtualmonitor \
        --name "$VIRTUAL_NAME" \
        --resolution "$VIRTUAL_RESOLUTION" \
        --password "$VMON_PASSWORD" \
        --port 5900 \
        >"$RUNTIME_DIR/vmonitor.log" 2>&1 9>&- &

    echo "$!" > "$VMON_PID_FILE"
    virtual_display_created=1

    for _ in {1..30}; do
        if virtual_display_exists; then
            break
        fi
        sleep 0.25
    done
fi
startup_timing "display-ready"

if startup_cancel_requested; then
    startup_fail "Dual Screen Mode startup was cancelled. Nothing was left running."
fi

if ! virtual_display_exists; then
    startup_fail "Could not create the virtual display. Nothing was left running."
fi

if (( virtual_display_created )); then
    position_virtual_display
fi

if ! ensure_sunshine_capture_config; then
    startup_fail "Sunshine could not be configured for the virtual display. Nothing was left running."
fi
start_or_refresh_sunshine
startup_timing "sunshine-ready"

if startup_cancel_requested; then
    startup_fail "Dual Screen Mode startup was cancelled. Nothing was left running."
fi

# The first KScreen layout update can land just after krfb reports the output.
# Re-read the logical geometry once Sunshine is ready so a fractional-scale
# host cannot leave a visible gap between the physical and virtual displays.
if (( virtual_display_created )); then
    sleep 0.2
    position_virtual_display
fi

map_sunshine_touch_devices >/dev/null 2>&1 || true
touch "$STATE_FILE"
start_touch_watcher
start_motion_monitor
startup_timing "mode-ready"
startup_cleanup_needed=0
rm -f "$STARTING_FILE" "$START_CANCEL_FILE"
trap - INT TERM
if [[ "$(cat "$TOUCH_STATUS_FILE" 2>/dev/null || true)" == "unavailable" ]]; then
    notify_user "Dual Screen Mode is ready, but touch routing could not be checked. The virtual display is still available."
else
    notify_user "Dual Screen Mode is ready. Connect your handheld. Touch will follow the second screen when the handheld touchscreen appears."
fi

