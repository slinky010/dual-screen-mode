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

run_toggle() {
    HOME="$test_home" \
    XDG_RUNTIME_DIR="$runtime_dir" \
    FAKE_STATE="$fake_state" \
    PATH="$fake_bin:$PATH" \
        bash "$root_dir/dual-screen-mode.sh"
}

run_toggle
[[ -f "$runtime_dir/dual-screen-mode/active" ]] || { echo 'FAIL host mode did not activate'; exit 1; }
grep -Fq 'stream_audio = disabled' "$test_home/.var/app/dev.lizardbyte.app.Sunshine/config/sunshine/sunshine.conf" || { echo 'FAIL host mode did not disable stream audio'; exit 1; }
grep -Fq -- '--password' "$fake_state/vmon-args" || { echo 'FAIL virtual monitor password was not supplied'; exit 1; }
vmon_password="$(awk 'previous == "--password" { print; exit } { previous = $0 }' "$fake_state/vmon-args")"
[[ "$vmon_password" =~ ^[[:alnum:]]{8}$ ]] || { echo 'FAIL virtual monitor password was not eight random alphanumeric characters'; exit 1; }
run_toggle
[[ ! -f "$runtime_dir/dual-screen-mode/active" ]] || { echo 'FAIL host mode did not deactivate'; exit 1; }
grep -Fq 'stream_audio = enabled' "$test_home/.var/app/dev.lizardbyte.app.Sunshine/config/sunshine/sunshine.conf" || { echo 'FAIL stream audio was not restored'; exit 1; }

printf '%s\n' 'resolution=1280x800' 'audio_mode=handheld' > "$test_home/.config/dual-screen-mode/settings.conf"
run_toggle
grep -Fxq 'yes' "$fake_state/mute" || { echo 'FAIL handheld mode did not mute host audio'; exit 1; }
run_toggle
grep -Fxq 'no' "$fake_state/mute" || { echo 'FAIL handheld mode did not restore host mute state'; exit 1; }

printf '%s\n' 'resolution=1280x800' 'audio_mode=both' > "$test_home/.config/dual-screen-mode/settings.conf"
run_toggle
grep -Fxq 'yes' "$fake_state/mute" || { echo 'FAIL both mode did not use handheld audio behavior'; exit 1; }
run_toggle
grep -Fxq 'no' "$fake_state/mute" || { echo 'FAIL both mode did not restore host mute state'; exit 1; }

echo 'PASS toggle activation, deactivation, and audio restoration'
