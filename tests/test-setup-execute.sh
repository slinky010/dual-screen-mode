#!/usr/bin/env bash

set -u

root_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
test_root="$(mktemp -d)"
fake_bin="$test_root/bin"
test_home="$test_root/home"
mkdir -p "$fake_bin" "$test_home"
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

chmod +x "$fake_bin"/*

HOME="$test_home" \
XDG_SESSION_TYPE=wayland \
XDG_CURRENT_DESKTOP=KDE \
PATH="$fake_bin:$PATH" \
    bash "$root_dir/setup-wizard.sh" --execute --resolution 1920x1080 --audio both --no-test > "$test_root/output.log"

grep -Fxq 'resolution=1920x1080' "$test_home/.config/dual-screen-mode/settings.conf"
! grep -q '^device=' "$test_home/.config/dual-screen-mode/settings.conf"
grep -Fxq 'audio_mode=both' "$test_home/.config/dual-screen-mode/settings.conf"
grep -Fxq 'capture = kwin' "$test_home/.var/app/dev.lizardbyte.app.Sunshine/config/sunshine/sunshine.conf"
grep -Fxq 'output_name = Virtual-DualScreen' "$test_home/.var/app/dev.lizardbyte.app.Sunshine/config/sunshine/sunshine.conf"
[[ -x "$test_home/.local/bin/dual-screen-mode" ]]
[[ -x "$test_home/Desktop/Dual Screen Mode.desktop" ]]
[[ -x "$test_home/Desktop/Uninstall Dual Screen Mode.desktop" ]]
[[ -x "$test_home/.local/share/dual-screen-mode/settings-gui.py" ]]
[[ -x "$test_home/.local/share/dual-screen-mode/settings-launcher.sh" ]]
[[ -f "$test_home/.local/share/icons/dual-screen-mode-settings.png" ]]
grep -Fq 'settings-gui.py' "$test_home/Desktop/Uninstall Dual Screen Mode.desktop"
grep -Fq 'settings-launcher.sh' "$test_home/Desktop/Uninstall Dual Screen Mode.desktop"
grep -Fq 'Icon=/home/' "$test_home/Desktop/Uninstall Dual Screen Mode.desktop"

echo 'PASS graphical backend execution path'
