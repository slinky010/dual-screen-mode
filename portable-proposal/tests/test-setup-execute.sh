#!/usr/bin/env bash

set -u

root_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
test_root="$(mktemp -d)"
fake_bin="$test_root/bin"
test_home="$test_root/home"
desktop_dir="$test_home/Arbeitsfläche"
mkdir -p "$fake_bin" "$test_home" "$desktop_dir"
trap 'rm -rf "$test_root"' EXIT

cat > "$fake_bin/kscreen-doctor" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' '{"outputs": [{"name": "DP-1"}]}'
EOF

cat > "$fake_bin/krfb-virtualmonitor" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF

cat > "$fake_bin/flatpak" <<'EOF'
#!/usr/bin/env bash
case "${1:-}" in
    info) exit 0 ;;
    override)
        [[ "${2:-}" == "--show" ]] && exit 1
        exit 0
        ;;
    remotes) exit 0 ;;
esac
exit 0
EOF

cat > "$fake_bin/xdg-user-dir" <<'EOF'
#!/usr/bin/env bash
if [[ "${1:-}" == DESKTOP ]]; then
    printf '%s\n' "$FAKE_DESKTOP"
fi
EOF

chmod +x "$fake_bin"/*
mkdir -p "$test_home/.var/app/dev.lizardbyte.app.Sunshine/config/sunshine"
printf '%s\n' 'capture = nvenc' 'output_name = DP-1' 'custom_setting = preserve-me' > "$test_home/.var/app/dev.lizardbyte.app.Sunshine/config/sunshine/sunshine.conf"

HOME="$test_home" \
FAKE_DESKTOP="$desktop_dir" \
XDG_SESSION_TYPE=wayland \
XDG_CURRENT_DESKTOP=KDE \
PATH="$fake_bin:$PATH" \
    bash "$root_dir/setup-wizard.sh" --execute --resolution 1920x1080 --audio both --no-test > "$test_root/output.log"

grep -Fxq 'resolution=1920x1080' "$test_home/.config/dual-screen-mode/settings.conf"
! grep -q '^device=' "$test_home/.config/dual-screen-mode/settings.conf"
grep -Fxq 'audio_mode=both' "$test_home/.config/dual-screen-mode/settings.conf"
grep -Fxq 'motion_enabled=1' "$test_home/.config/dual-screen-mode/settings.conf"
grep -Fxq 'motion_port=26760' "$test_home/.config/dual-screen-mode/settings.conf"
grep -Fxq 'motion_slot=0' "$test_home/.config/dual-screen-mode/settings.conf"
grep -Fxq 'capture = kwin' "$test_home/.var/app/dev.lizardbyte.app.Sunshine/config/sunshine/sunshine.conf"
grep -Fxq 'output_name = Virtual-DualScreen' "$test_home/.var/app/dev.lizardbyte.app.Sunshine/config/sunshine/sunshine.conf"
[[ -x "$test_home/.local/bin/dual-screen-mode" ]]
[[ -x "$desktop_dir/Dual Screen Mode.desktop" ]]
[[ -x "$desktop_dir/Uninstall Dual Screen Mode.desktop" ]]
[[ ! -e "$test_home/Desktop/Dual Screen Mode.desktop" ]]
[[ -x "$test_home/.local/share/dual-screen-mode/settings-gui.py" ]]
[[ -x "$test_home/.local/share/dual-screen-mode/settings-launcher.sh" ]]
[[ -x "$test_home/.local/share/dual-screen-mode/motion_discovery.py" ]]
[[ -x "$test_home/.local/share/dual-screen-mode/display_layout.py" ]]
[[ -x "$test_home/.local/share/dual-screen-mode/cemu_profile.py" ]]
[[ -f "$test_home/.local/share/dual-screen-mode/update_support.py" ]]
[[ -f "$test_home/.local/share/icons/dual-screen-mode-settings.png" ]]
grep -Fq 'settings-gui.py' "$desktop_dir/Uninstall Dual Screen Mode.desktop"
grep -Fq 'settings-launcher.sh' "$desktop_dir/Uninstall Dual Screen Mode.desktop"
grep -Fq 'Icon=/home/' "$desktop_dir/Uninstall Dual Screen Mode.desktop"

dry_run_output="$test_root/uninstall-dry-run.log"
HOME="$test_home" \
FAKE_DESKTOP="$desktop_dir" \
PATH="$fake_bin:$PATH" \
    bash "$test_home/.local/share/dual-screen-mode/uninstall.sh" --dry-run > "$dry_run_output"
grep -Fq "$desktop_dir/Dual Screen Mode.desktop" "$dry_run_output"
grep -Fq "$desktop_dir/Uninstall Dual Screen Mode.desktop" "$dry_run_output"

mkdir -p "$test_home/Desktop"
touch "$test_home/Desktop/Dual Screen Mode.desktop"
touch "$test_home/Desktop/Uninstall Dual Screen Mode.desktop"
touch "$test_home/.local/state/dual-screen-mode/owned-launcher"
touch "$test_home/.local/state/dual-screen-mode/owned-uninstall-launcher"
HOME="$test_home" \
FAKE_DESKTOP="$desktop_dir" \
PATH="$fake_bin:$PATH" \
    bash "$test_home/.local/share/dual-screen-mode/uninstall.sh" --execute
[[ ! -e "$desktop_dir/Dual Screen Mode.desktop" ]]
[[ ! -e "$desktop_dir/Uninstall Dual Screen Mode.desktop" ]]
[[ ! -e "$test_home/Desktop/Dual Screen Mode.desktop" ]]
[[ ! -e "$test_home/Desktop/Uninstall Dual Screen Mode.desktop" ]]
grep -Fxq 'capture = nvenc' "$test_home/.var/app/dev.lizardbyte.app.Sunshine/config/sunshine/sunshine.conf"
grep -Fxq 'output_name = DP-1' "$test_home/.var/app/dev.lizardbyte.app.Sunshine/config/sunshine/sunshine.conf"
grep -Fxq 'custom_setting = preserve-me' "$test_home/.var/app/dev.lizardbyte.app.Sunshine/config/sunshine/sunshine.conf"

echo 'PASS graphical backend execution path'

