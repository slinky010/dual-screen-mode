#!/usr/bin/env bash

set -u

root_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
test_root="$(mktemp -d)"
fake_bin="$test_root/bin"
fake_state="$test_root/state"
test_home="$test_root/home"
runtime_dir="$test_root/runtime"
toggle_pid=""
mkdir -p "$fake_bin" "$fake_state" "$test_home" "$runtime_dir"

cleanup() {
    if [[ -n "$toggle_pid" ]]; then
        kill "$toggle_pid" 2>/dev/null || true
    fi
    rm -rf "$test_root"
}
trap cleanup EXIT

cat > "$fake_bin/kscreen-doctor" <<'EOF'
#!/usr/bin/env bash
if [[ -f "$FAKE_STATE/vmon" ]]; then
    printf '%s\n' '{"outputs": [{"name": "Virtual-DualScreen"}]}'
else
    printf '%s\n' '{"outputs":[]}'
fi
EOF

cat > "$fake_bin/krfb-virtualmonitor" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$FAKE_STATE/vmon-args"
touch "$FAKE_STATE/vmon"
trap 'rm -f "$FAKE_STATE/vmon"; exit 0' TERM INT EXIT
while :; do sleep 1; done
EOF

cat > "$fake_bin/qdbus6" <<'EOF'
#!/usr/bin/env bash
case "${3:-}" in
    org.kde.KWin.InputDeviceManager.ListTouch)
        [[ -f "$FAKE_STATE/touch-device" ]] && printf '%s\n' event28
        ;;
    org.freedesktop.DBus.Properties.Get)
        case "${5:-}" in
            name) printf '%s\n' 'libvirtualhid Touchscreen' ;;
            outputName) cat "$FAKE_STATE/touch-output" 2>/dev/null || true ;;
        esac
        ;;
    org.freedesktop.DBus.Properties.Set)
        if [[ "${5:-}" == outputName ]]; then
            printf '%s\n' "${6:-}" > "$FAKE_STATE/touch-output"
        fi
        ;;
esac
EOF

cat > "$fake_bin/flatpak" <<'EOF'
#!/usr/bin/env bash
case "${1:-}" in
    ps)
        [[ -f "$FAKE_STATE/sunshine" ]] && printf '%s\n' 'dev.lizardbyte.app.Sunshine'
        ;;
    run)
        touch "$FAKE_STATE/sunshine"
        printf '%s\n' "$BASHPID" > "$FAKE_STATE/sunshine.pid"
        trap 'rm -f "$FAKE_STATE/sunshine" "$FAKE_STATE/sunshine.pid"; exit 0' TERM INT EXIT
        while :; do sleep 1; done
        ;;
    kill)
        rm -f "$FAKE_STATE/sunshine" "$FAKE_STATE/sunshine.pid"
        ;;
esac
EOF

cat > "$fake_bin/pactl" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_STATE/pactl.log"
case "${1:-}" in
    get-default-sink) printf '%s\n' 'test-sink' ;;
    get-sink-volume) printf '%s\n' 'Volume: front-left: 65536 / 100% / 0.00 dB, front-right: 65536 / 100% / 0.00 dB' ;;
    get-sink-mute) printf 'Mute: %s\n' "$(cat "$FAKE_STATE/mute" 2>/dev/null || printf no)" ;;
    set-sink-mute) [[ "$3" == 1 ]] && printf '%s\n' yes > "$FAKE_STATE/mute" || printf '%s\n' no > "$FAKE_STATE/mute" ;;
    set-sink-volume) printf '%s\n' "$3" > "$FAKE_STATE/volume" ;;
esac
EOF

chmod +x "$fake_bin"/*
mkdir -p "$test_home/.config/dual-screen-mode" "$test_home/.var/app/dev.lizardbyte.app.Sunshine/config/sunshine"
printf '%s\n' 'resolution=1280x800' 'audio_mode=host' > "$test_home/.config/dual-screen-mode/settings.conf"
printf '%s\n' 'stream_audio = enabled' > "$test_home/.var/app/dev.lizardbyte.app.Sunshine/config/sunshine/sunshine.conf"
printf '%s\n' 'DP-1' > "$fake_state/touch-output"

run_toggle() {
    HOME="$test_home" \
    XDG_RUNTIME_DIR="$runtime_dir" \
    FAKE_STATE="$fake_state" \
    PATH="$fake_bin:$PATH" \
        bash "$root_dir/dual-screen-mode.sh"
}

assert_mute_state() {
    local expected="$1"
    local message="$2"
    for _ in {1..20}; do
        if grep -Fxq "$expected" "$fake_state/mute" 2>/dev/null; then
            return 0
        fi
        sleep 0.05
    done
    echo "FAIL $message" >&2
    echo "Expected mute state: $expected" >&2
    echo "Actual mute state: $(cat "$fake_state/mute" 2>/dev/null || echo '<missing>')" >&2
    echo "pactl calls:" >&2
    cat "$fake_state/pactl.log" 2>/dev/null >&2 || true
    exit 1
}

run_toggle
[[ -f "$runtime_dir/dual-screen-mode/active" ]] || { echo 'FAIL host mode did not activate'; exit 1; }
grep -Fq 'stream_audio = disabled' "$test_home/.var/app/dev.lizardbyte.app.Sunshine/config/sunshine/sunshine.conf" || { echo 'FAIL host mode did not disable stream audio'; exit 1; }
grep -Fq -- '--password' "$fake_state/vmon-args" || { echo 'FAIL virtual monitor password was not supplied'; exit 1; }
vmon_password="$(awk 'previous == "--password" { print; exit } { previous = $0 }' "$fake_state/vmon-args")"
[[ "$vmon_password" =~ ^[[:alnum:]]{8}$ ]] || { echo 'FAIL virtual monitor password was not eight random alphanumeric characters'; exit 1; }
touch "$fake_state/touch-device"
for _ in {1..30}; do
    grep -Fxq 'Virtual-DualScreen' "$fake_state/touch-output" && break
    sleep 0.1
done
grep -Fxq 'Virtual-DualScreen' "$fake_state/touch-output" || { echo 'FAIL Sunshine virtual touchscreen was not mapped to the virtual display'; exit 1; }
run_toggle
[[ ! -f "$runtime_dir/dual-screen-mode/active" ]] || { echo 'FAIL host mode did not deactivate'; exit 1; }
grep -Fq 'stream_audio = enabled' "$test_home/.var/app/dev.lizardbyte.app.Sunshine/config/sunshine/sunshine.conf" || { echo 'FAIL stream audio was not restored'; exit 1; }
grep -Fxq 'DP-1' "$fake_state/touch-output" || { echo 'FAIL touch output mapping was not restored'; exit 1; }

printf '%s\n' 'resolution=1280x800' 'audio_mode=handheld' > "$test_home/.config/dual-screen-mode/settings.conf"
run_toggle
assert_mute_state yes 'handheld mode did not mute host audio'
run_toggle
assert_mute_state no 'handheld mode did not restore host mute state'

printf '%s\n' 'resolution=1280x800' 'audio_mode=both' > "$test_home/.config/dual-screen-mode/settings.conf"
run_toggle
assert_mute_state yes 'both mode did not use handheld audio behavior'
run_toggle
assert_mute_state no 'both mode did not restore host mute state'

echo 'PASS toggle activation, deactivation, and audio restoration'
