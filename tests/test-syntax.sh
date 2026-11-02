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
    "$root_dir/tests/test-toggle.sh" \
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

if ! grep -Eq '#[0-9A-Fa-f]{8}' "$root_dir/wizard-gui.py" "$root_dir/settings-gui.py"; then
    printf 'PASS Tk color formats\n'
else
    printf 'FAIL Tk color formats\n'
    status=1
fi

for file in \
    "$root_dir/Install Dual Screen Mode.desktop" \
    "$root_dir/START HERE.txt" \
    "$root_dir/settings-gui.py" \
    "$root_dir/assets/dual-screen-mode.png" \
    "$root_dir/assets/dual-screen-mode-settings.png" \
    "$root_dir/wizard-preview.html"; do
    if [[ -e "$file" ]]; then
        printf 'PASS %s\n' "${file#$root_dir/}"
    else
        printf 'FAIL %s\n' "${file#$root_dir/}"
        status=1
    fi
done

if grep -Fq 'Install Dual Screen Mode' "$root_dir/wizard-preview.html" &&
    grep -Fq 'Run connection test' "$root_dir/wizard-preview.html" &&
    grep -Fq 'Install Dual Screen Mode.desktop' "$root_dir/START HERE.txt"; then
    printf 'PASS preview content\n'
else
    printf 'FAIL preview content\n'
    status=1
fi

exit "$status"
