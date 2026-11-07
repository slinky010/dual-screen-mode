#!/usr/bin/env bash

set -u

root_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
test_root="$(mktemp -d)"
fake_bin="$test_root/bin"
fake_state="$test_root/state"
test_home="$test_root/home"
runtime_dir="$test_root/runtime"
mkdir -p "$fake_bin" "$fake_state" "$test_home" "$runtime_dir"
mkdir -p "$test_home/.local/share/dual-screen-mode"
install -m 755 "$root_dir/display_layout.py" "$test_home/.local/share/dual-screen-mode/display_layout.py"
cat > "$test_home/.local/share/dual-screen-mode/motion_discovery.py" <<'EOF'
#!/usr/bin/env python3
raise SystemExit(1)
EOF
cat > "$test_home/.local/share/dual-screen-mode/cemu_profile.py" <<'EOF'
#!/usr/bin/env python3
import os
from pathlib import Path

Path(os.environ["FAKE_STATE"]).joinpath("cemu-sync").write_text("called\n", encoding="utf-8")
print("UPDATED fake")
EOF
chmod 755 "$test_home/.local/share/dual-screen-mode/motion_discovery.py" "$test_home/.local/share/dual-screen-mode/cemu_profile.py"

cleanup() {
    if [[ -f "$fake_state/sunshine.pid" ]]; then
        kill "$(cat "$fake_state/sunshine.pid")" 2>/dev/null || true
    fi
    rm -rf "$test_root"
}
trap cleanup EXIT

cat > "$fake_bin/kscreen-doctor" <<'EOF'
#!/usr/bin/env bash
for argument in "$@"; do
    if [[ "$argument" == output.*.position.* ]]; then
        printf '%s\n' "$argument" > "$FAKE_STATE/position"
    fi
done
if [[ "${1:-}" == "-j" ]]; then
    if [[ -f "$FAKE_STATE/vmon" ]]; then
        printf '%s\n' '{"outputs": [{"id": 17, "name": "DP-1", "priority": 1, "enabled": true, "pos": {"x": 0, "y": 0}, "size": {"width": 3840, "height": 2160}}, {"id": 42, "name": "Virtual-DualScreen", "enabled": true, "pos": {"x": 2649, "y": 0}, "size": {"width": 1280, "height": 800}}]}'
    else
        printf '%s\n' '{"outputs":[]}'
    fi
fi
EOF

cat > "$fake_bin/krfb-virtualmonitor" <<'EOF'
#!/usr/bin/env bash
if [[ -f "$FAKE_STATE/slow-start" ]]; then
    touch "$FAKE_STATE/start-entered"
    while [[ -f "$FAKE_STATE/slow-start" ]]; do
        sleep 0.05
    done
fi
touch "$FAKE_STATE/vmon"
trap 'rm -f "$FAKE_STATE/vmon"; exit 0' TERM INT EXIT
while :; do sleep 1; done
EOF

cat > "$fake_bin/qdbus6" <<'EOF'
#!/usr/bin/env bash
case "${3:-}" in
    org.kde.KWin.InputDeviceManager.ListTouch)
        if [[ -f "$FAKE_STATE/touch-device" ]]; then
            printf '%s\n' event28
        fi
        exit 0
        ;;
    org.freedesktop.DBus.Properties.Get)
        case "${5:-}" in
            name) printf '%s\n' 'libvirtualhid Touchscreen' ;;
            outputName) cat "$FAKE_STATE/touch-output" 2>/dev/null || true ;;
        esac
        ;;
    org.freedesktop.DBus.Properties.Set)
        if [[ -f "$FAKE_STATE/slow-kill" ]]; then
            touch "$FAKE_STATE/kill-started"
            sleep 0.4
        fi
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
        if [[ -f "$FAKE_STATE/sunshine" ]]; then
            if [[ -f "$FAKE_STATE/sunshine.pid" ]]; then
                printf '%s\t%s\t%s\n' fake-instance dev.lizardbyte.app.Sunshine "$(cat "$FAKE_STATE/sunshine.pid")"
            else
                printf '%s\n' 'dev.lizardbyte.app.Sunshine'
            fi
        fi
        ;;
    run)
        touch "$FAKE_STATE/sunshine"
        printf '%s\n' "$BASHPID" > "$FAKE_STATE/sunshine.pid"
        trap 'rm -f "$FAKE_STATE/sunshine" "$FAKE_STATE/sunshine.pid"; exit 0' TERM INT EXIT
        while :; do sleep 1; done
        ;;
    kill)
        touch "$FAKE_STATE/kill-called"
        if [[ -f "$FAKE_STATE/sunshine.pid" ]]; then
            kill "$(cat "$FAKE_STATE/sunshine.pid")" 2>/dev/null || true
        fi
        rm -f "$FAKE_STATE/sunshine" "$FAKE_STATE/sunshine.pid"
        ;;
esac
EOF

cat > "$fake_bin/pactl" <<'EOF'
#!/usr/bin/env bash
case "${1:-}" in
    get-default-sink) printf '%s\n' test-sink ;;
    get-sink-volume) printf '%s\n' 'Volume: front-left: 65536 / 100% / 0.00 dB' ;;
    get-sink-mute) printf '%s\n' 'Mute: no' ;;
esac
EOF

chmod +x "$fake_bin"/*
mkdir -p "$test_home/.config/dual-screen-mode" "$test_home/.var/app/dev.lizardbyte.app.Sunshine/config/sunshine"
printf '%s\n' 'resolution=1280x800' 'audio_mode=host' 'motion_enabled=1' 'motion_host=127.0.0.0' 'motion_port=26760' 'motion_slot=0' > "$test_home/.config/dual-screen-mode/settings.conf"
printf '%s\n' 'capture = nvenc' 'output_name = DP-1' 'stream_audio = enabled' > "$test_home/.var/app/dev.lizardbyte.app.Sunshine/config/sunshine/sunshine.conf"
printf '%s\n' DP-1 > "$fake_state/touch-output"
touch "$fake_state/sunshine"

run_toggle() {
    HOME="$test_home" \
    XDG_RUNTIME_DIR="$runtime_dir" \
    FAKE_STATE="$fake_state" \
    PATH="$fake_bin:$PATH" \
        bash "$root_dir/dual-screen-mode.sh"
}

run_toggle
[[ -f "$runtime_dir/dual-screen-mode/active" ]] || { echo 'FAIL mode did not activate'; exit 1; }
[[ -f "$fake_state/kill-called" ]] || { echo 'FAIL preexisting Sunshine was not refreshed'; exit 1; }
grep -Fxq 'capture = kwin' "$test_home/.var/app/dev.lizardbyte.app.Sunshine/config/sunshine/sunshine.conf" || { echo 'FAIL runtime did not enforce KWin capture'; exit 1; }
grep -Fxq 'output_name = Virtual-DualScreen' "$test_home/.var/app/dev.lizardbyte.app.Sunshine/config/sunshine/sunshine.conf" || { echo 'FAIL runtime did not enforce the virtual output'; exit 1; }
grep -Fxq 'stream_audio = disabled' "$test_home/.var/app/dev.lizardbyte.app.Sunshine/config/sunshine/sunshine.conf" || { echo 'FAIL host audio mode did not disable stream audio'; exit 1; }
grep -Fxq 'capture_line=capture = nvenc' "$test_home/.local/state/dual-screen-mode/owned-sunshine-config" || { echo 'FAIL runtime did not preserve the original capture setting'; exit 1; }
grep -Fxq 'output_name_line=output_name = DP-1' "$test_home/.local/state/dual-screen-mode/owned-sunshine-config" || { echo 'FAIL runtime did not preserve the original output setting'; exit 1; }
grep -Fxq 'output.Virtual-DualScreen.position.1280,2160' "$fake_state/position" || {
    echo 'FAIL virtual display was not centered below the main display';
    exit 1;
}

for _ in {1..20}; do
    [[ ! -f "$runtime_dir/dual-screen-mode/motion-discovery.pid" ]] && break
    sleep 0.05
done
[[ ! -e "$fake_state/cemu-sync" ]] || {
    echo 'FAIL stale DSU address was pushed into Cemu';
    exit 1;
}

for _ in {1..20}; do
    [[ "$(cat "$runtime_dir/dual-screen-mode/touch-status" 2>/dev/null || true)" == waiting ]] && break
    sleep 0.05
done
[[ "$(cat "$runtime_dir/dual-screen-mode/touch-status" 2>/dev/null || true)" == waiting ]] || {
    echo 'FAIL touch routing did not report waiting';
    exit 1;
}

touch "$fake_state/touch-device"
for _ in {1..30}; do
    [[ "$(cat "$runtime_dir/dual-screen-mode/touch-status" 2>/dev/null || true)" == mapped ]] && break
    sleep 0.1
done
[[ "$(cat "$runtime_dir/dual-screen-mode/touch-status" 2>/dev/null || true)" == mapped ]] || {
    echo 'FAIL touch routing did not report mapped';
    exit 1;
}
grep -Fxq Virtual-DualScreen "$fake_state/touch-output" || {
    echo 'FAIL touchscreen was not mapped to the virtual display';
    exit 1
}

touch "$fake_state/slow-kill"
run_toggle >"$test_root/first-disable.log" 2>&1 &
first_disable_pid=$!
for _ in {1..20}; do
    [[ -f "$fake_state/kill-started" ]] && break
    sleep 0.02
done
[[ -f "$fake_state/kill-started" ]] || {
    echo 'FAIL disable did not reach the shutdown path';
    exit 1;
}
run_toggle >"$test_root/second-disable.log" 2>&1 &
second_disable_pid=$!
wait "$first_disable_pid"
wait "$second_disable_pid"
rm -f "$fake_state/slow-kill"
[[ ! -f "$runtime_dir/dual-screen-mode/active" ]] || { echo 'FAIL mode did not deactivate'; exit 1; }
grep -Fxq 'capture = nvenc' "$test_home/.var/app/dev.lizardbyte.app.Sunshine/config/sunshine/sunshine.conf" || {
    echo 'FAIL previous Sunshine capture setting was not restored';
    exit 1;
}
grep -Fxq 'output_name = DP-1' "$test_home/.var/app/dev.lizardbyte.app.Sunshine/config/sunshine/sunshine.conf" || {
    echo 'FAIL previous Sunshine output target was not restored';
    exit 1;
}
grep -Fxq 'stream_audio = enabled' "$test_home/.var/app/dev.lizardbyte.app.Sunshine/config/sunshine/sunshine.conf" || {
    echo 'FAIL previous stream audio setting was not restored';
    exit 1;
}
[[ -f "$fake_state/sunshine" ]] || {
    echo 'FAIL pre-existing Sunshine session was not restored';
    exit 1;
}
grep -Fxq DP-1 "$fake_state/touch-output" || {
    echo 'FAIL previous touch output was not restored';
    exit 1
}
[[ ! -e "$runtime_dir/dual-screen-mode/touch-status" ]] || {
    echo 'FAIL touch status was not cleared';
    exit 1
}

# A second click that arrives just after shutdown must not turn the mode back
# on. Once the short double-click guard expires, a normal new start is allowed.
run_toggle
[[ ! -f "$runtime_dir/dual-screen-mode/active" ]] || {
    echo 'FAIL rapid post-disable click restarted the mode';
    exit 1;
}
sleep 1.6
run_toggle
[[ -f "$runtime_dir/dual-screen-mode/active" ]] || {
    echo 'FAIL mode did not start after the double-click guard expired';
    exit 1;
}
run_toggle
[[ ! -f "$runtime_dir/dual-screen-mode/active" ]] || {
    echo 'FAIL final disable did not complete';
    exit 1;
}

# The older lifecycle also supported starting Sunshine only when DSM needed
# it. Verify that a mode-owned Sunshine process is stopped rather than
# incorrectly treated as a pre-existing user session.
if [[ -f "$fake_state/sunshine.pid" ]]; then
    kill "$(cat "$fake_state/sunshine.pid")" 2>/dev/null || true
fi
rm -f "$fake_state/sunshine" "$fake_state/sunshine.pid"
sleep 1.6
run_toggle
[[ -f "$runtime_dir/dual-screen-mode/active" && -f "$fake_state/sunshine" ]] || {
    echo 'FAIL mode did not start Sunshine when no session existed';
    exit 1;
}
run_toggle
[[ ! -f "$runtime_dir/dual-screen-mode/active" && ! -f "$fake_state/sunshine" ]] || {
    echo 'FAIL mode-owned Sunshine session was not stopped';
    exit 1;
}

# A second click while startup is still running must cancel that startup and
# unwind its temporary display instead of being silently ignored.
sleep 1.6
rm -f "$fake_state/vmon" "$fake_state/start-entered"
touch "$fake_state/slow-start"
run_toggle >"$test_root/start-cancel.log" 2>&1 &
startup_pid=$!
for _ in {1..40}; do
    [[ -f "$fake_state/start-entered" ]] && break
    sleep 0.05
done
[[ -f "$fake_state/start-entered" ]] || { echo 'FAIL slow startup did not begin'; exit 1; }
run_toggle >"$test_root/cancel-click.log" 2>&1
[[ -f "$runtime_dir/dual-screen-mode/start-cancel" ]] || { echo 'FAIL second click did not request startup cancellation'; exit 1; }
rm -f "$fake_state/slow-start"
wait "$startup_pid"
[[ ! -f "$runtime_dir/dual-screen-mode/active" ]] || { echo 'FAIL cancelled startup became active'; exit 1; }
[[ ! -f "$runtime_dir/dual-screen-mode/starting" ]] || { echo 'FAIL startup marker was left behind'; exit 1; }
[[ ! -f "$runtime_dir/dual-screen-mode/start-cancel" ]] || { echo 'FAIL startup cancellation marker was left behind'; exit 1; }

echo 'PASS touch routing, safe duplicate clicks, and restore states'
