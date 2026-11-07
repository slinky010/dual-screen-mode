#!/usr/bin/env bash

set -u

root_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
status=0

for file in \
    "$root_dir/dual-screen-mode.sh" \
    "$root_dir/setup-wizard.sh" \
    "$root_dir/uninstall.sh" \
    "$root_dir/launch-wizard.sh" \
    "$root_dir/settings-launcher.sh" \
    "$root_dir/tests/test-touch-routing.sh" \
    "$root_dir/tests/test-setup-execute.sh"; do
    if bash -n "$file"; then
        printf 'PASS %s\n' "${file#$root_dir/}"
    else
        printf 'FAIL %s\n' "${file#$root_dir/}"
        status=1
    fi
done

if python3 -c 'compile(open("'$root_dir'/wizard-gui.py", encoding="utf-8").read(), "wizard-gui.py", "exec")'; then
    printf 'PASS wizard-gui.py\n'
else
    printf 'FAIL wizard-gui.py\n'
    status=1
fi

if python3 -c 'compile(open("'$root_dir'/settings-gui.py", encoding="utf-8").read(), "settings-gui.py", "exec")'; then
    printf 'PASS settings-gui.py\n'
else
    printf 'FAIL settings-gui.py\n'
    status=1
fi

for file in \
    "$root_dir/motion_monitor.py" \
    "$root_dir/motion_discovery.py" \
    "$root_dir/display_layout.py" \
    "$root_dir/cemu_profile.py" \
    "$root_dir/update_support.py" \
    "$root_dir/update_runner.py" \
    "$root_dir/motion_probe/dsu_motion_probe.py"; do
    if python3 -c 'compile(open("'$file'", encoding="utf-8").read(), "'"${file#$root_dir/}"'", "exec")'; then
        printf 'PASS %s\n' "${file#$root_dir/}"
    else
        printf 'FAIL %s\n' "${file#$root_dir/}"
        status=1
    fi
done

if python3 -c 'compile(open("'"$root_dir"'/tests/test-motion-discovery.py", encoding="utf-8").read(), "tests/test-motion-discovery.py", "exec")'; then
    printf 'PASS tests/test-motion-discovery.py\n'
else
    printf 'FAIL tests/test-motion-discovery.py\n'
    status=1
fi

if python3 -c 'compile(open("'"$root_dir"'/tests/test-update-support.py", encoding="utf-8").read(), "tests/test-update-support.py", "exec")'; then
    printf 'PASS tests/test-update-support.py\n'
else
    printf 'FAIL tests/test-update-support.py\n'
    status=1
fi

if ! grep -Eq '#[0-9A-Fa-f]{8}' "$root_dir/wizard-gui.py" "$root_dir/settings-gui.py"; then
    printf 'PASS Tk color formats\n'
else
    printf 'FAIL Tk color formats\n'
    status=1
fi

for file in \
    "$root_dir/Install Dual Screen Mode.desktop" \
    "$root_dir/README.md" \
    "$root_dir/LICENSE" \
    "$root_dir/START HERE.txt" \
    "$root_dir/docs/MOONLIGHT_SETUP.md" \
    "$root_dir/settings-gui.py" \
    "$root_dir/motion_monitor.py" \
    "$root_dir/motion_probe/dsu_motion_probe.py" \
    "$root_dir/assets/dual-screen-mode.png" \
    "$root_dir/assets/dual-screen-mode-settings.png"; do
    if [[ -e "$file" ]]; then
        printf 'PASS %s\n' "${file#$root_dir/}"
    else
        printf 'FAIL %s\n' "${file#$root_dir/}"
        status=1
    fi
done

if grep -Fq 'Install Dual Screen Mode' "$root_dir/Install Dual Screen Mode.desktop" &&
    grep -Fq 'settings-gui.py' "$root_dir/settings-launcher.sh" &&
    grep -Fq 'Motion monitoring is enabled by default' "$root_dir/README.md" &&
    grep -Fq 'Calibrate' "$root_dir/docs/MOONLIGHT_SETUP.md" &&
    grep -Fq 'Rapid duplicate clicks' "$root_dir/README.md" &&
    grep -Fq 'DISABLED' "$root_dir/settings-gui.py"; then
    printf 'PASS preview content\n'
else
    printf 'FAIL preview content\n'
    status=1
fi

exit "$status"

