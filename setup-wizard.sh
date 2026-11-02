#!/usr/bin/env bash

set -u
umask 077

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_ID="dev.lizardbyte.app.Sunshine"
VIRTUAL_NAME="DualScreen"
SUNSHINE_CONF="$HOME/.var/app/$APP_ID/config/sunshine/sunshine.conf"
ENV_DIR="$HOME/.config/environment.d"
ENV_FILE="$ENV_DIR/dual-screen-mode.conf"
TOGGLE_DEST="$HOME/.local/bin/dual-screen-mode"
DESKTOP_DEST="$HOME/Desktop/Dual Screen Mode.desktop"
UNINSTALL_DESKTOP_DEST="$HOME/Desktop/Uninstall Dual Screen Mode.desktop"
UNINSTALL_APP_DIR="$HOME/.local/share/dual-screen-mode"
UNINSTALL_SCRIPT_DEST="$UNINSTALL_APP_DIR/uninstall.sh"
MANAGEMENT_SCRIPT_DEST="$UNINSTALL_APP_DIR/settings-gui.py"
MANAGEMENT_LAUNCHER_DEST="$UNINSTALL_APP_DIR/settings-launcher.sh"
ICON_DEST="$HOME/.local/share/icons/dual-screen-mode.png"
SETTINGS_ICON_DEST="$HOME/.local/share/icons/dual-screen-mode-settings.png"
BUNDLED_ICON="$PROJECT_DIR/assets/dual-screen-mode.png"
BUNDLED_SETTINGS_ICON="$PROJECT_DIR/assets/dual-screen-mode-settings.png"
SETTINGS_DIR="$HOME/.config/dual-screen-mode"
SETTINGS_FILE="$SETTINGS_DIR/settings.conf"
STATE_DIR="$HOME/.local/state/dual-screen-mode"
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp}/dual-screen-mode"
BACKUP_DIR="$STATE_DIR/backups/$(date +%Y%m%d-%H%M%S)"
OWNED_ENV_MARKER="$STATE_DIR/owned-environment-setting"
OWNED_OVERRIDE_MARKER="$STATE_DIR/owned-sunshine-override"
OWNED_SETTINGS_ICON_MARKER="$STATE_DIR/owned-settings-icon"

DRY_RUN=0
AUDIT=0
CHECK_ONLY=0
GUI_EXECUTE=0
AUTO_CONFIRM=0
NO_PROGRESS_UI=0
NO_TEST=0
ICON_SOURCE=""
READONLY_DISABLED=0
PERMISSIONS_APPROVED=0
PROGRESS_REF=""
QDBUS_CMD=""
RESOLUTION="1280x800"
AUDIO_MODE="host"

usage() {
    cat <<'EOF'
Dual Screen Mode setup wizard

Usage:
  ./setup-wizard.sh [--dry-run] [--audit] [--icon PATH]

Options:
  --dry-run     inspect the system and show planned changes without modifying it
  --audit       print actions, sources, and trust boundaries without checking the host
  --check       check the host without changing it
  --execute     run the reviewed setup choices without opening extra dialogs
  --resolution WxH virtual display size used by the graphical wizard
  --audio MODE  host, handheld, or both (work in progress; uses handheld behavior)
  --no-test     finish without opening the optional connection test
  --icon PATH   install a custom PNG launcher icon
  --help        show this help
EOF
}

if [[ "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --audit)
            AUDIT=1
            shift
            ;;
        --check)
            CHECK_ONLY=1
            shift
            ;;
        --execute)
            GUI_EXECUTE=1
            AUTO_CONFIRM=1
            NO_PROGRESS_UI=1
            shift
            ;;
        --device)
            if [[ $# -lt 2 ]]; then
                echo "--device requires a name" >&2
                exit 2
            fi
            # Kept as a no-op for compatibility with older launcher scripts.
            shift 2
            ;;
        --resolution)
            if [[ $# -lt 2 ]]; then
                echo "--resolution requires a value" >&2
                exit 2
            fi
            RESOLUTION="$2"
            shift 2
            ;;
        --audio)
            if [[ $# -lt 2 ]]; then
                echo "--audio requires host, handheld, or both" >&2
                exit 2
            fi
            AUDIO_MODE="$2"
            shift 2
            ;;
        --no-test)
            NO_TEST=1
            shift
            ;;
        --icon)
            if [[ $# -lt 2 ]]; then
                echo "--icon requires a path" >&2
                exit 2
            fi
            ICON_SOURCE="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

have() {
    command -v "$1" >/dev/null 2>&1
}

run_as_root() {
    # The graphical wizard handles missing krfb before it starts this script.
    # This helper is for direct terminal use and systems with polkit.
    if have pkexec; then
        pkexec "$@"
        return $?
    fi
    if have sudo && [[ -t 0 && -t 1 ]]; then
        sudo "$@"
        return $?
    fi
    printf '%s\n' 'Run this installer from a terminal or install krfb from the setup wizard.' >&2
    return 127
}

ui_message() {
    local message="$1"
    if (( GUI_EXECUTE )); then
        note "$message"
        return 0
    fi
    if have kdialog; then
        kdialog --title "Dual Screen Mode" --msgbox "$message"
    else
        printf '\n%b\n\n' "$message"
    fi
}

ui_question() {
    local message="$1"
    if (( DRY_RUN || AUTO_CONFIRM )); then
        return 0
    fi
    if have kdialog; then
        kdialog --title "Dual Screen Mode" --yesno "$message"
        return $?
    fi
    printf '%b [y/N] ' "$message" >&2
    read -r answer
    [[ "$answer" =~ ^[Yy]([Ee][Ss])?$ ]]
}

ui_choose() {
    local message="$1"
    shift
    local result

    if (( DRY_RUN )); then
        printf '%s\n' "$1"
        return 0
    fi

    if have kdialog; then
        result="$(kdialog --title "Dual Screen Mode" --combobox "$message" "$@" 2>/dev/null)" || return 1
        [[ -n "$result" ]] || return 1
        printf '%s\n' "$result"
        return 0
    fi

    printf '%b\n' "$message" >&2
    local index=1
    local option
    for option in "$@"; do
        printf '  %d) %s\n' "$index" "$option" >&2
        index=$((index + 1))
    done
    printf 'Choose [1]: ' >&2
    read -r result
    result="${result:-1}"
    if [[ "$result" =~ ^[0-9]+$ ]] && (( result >= 1 && result < index )); then
        shift $((result - 1))
        printf '%s\n' "$1"
        return 0
    fi
    return 1
}

ui_input() {
    local message="$1"
    local initial="${2:-}"
    local result

    if (( DRY_RUN )); then
        printf '%s\n' "$initial"
        return 0
    fi

    if have kdialog; then
        result="$(kdialog --title "Dual Screen Mode" --inputbox "$message" "$initial" 2>/dev/null)" || return 1
        [[ -n "$result" ]] || return 1
        printf '%s\n' "$result"
        return 0
    fi

    printf '%b [%s]: ' "$message" "$initial" >&2
    read -r result
    printf '%s\n' "${result:-$initial}"
}

find_qdbus() {
    local candidate
    for candidate in qdbus6 qdbus qdbus-qt5; do
        if have "$candidate"; then
            QDBUS_CMD="$candidate"
            return 0
        fi
    done
    return 1
}

progress_open() {
    PROGRESS_REF=""
    if (( NO_PROGRESS_UI )) || ! have kdialog || ! find_qdbus; then
        return 0
    fi
    PROGRESS_REF="$(kdialog --title "Dual Screen Mode" --progressbar "Setting up Dual Screen Mode" 8 2>/dev/null || true)"
}

progress_step() {
    local value="$1"
    local label="$2"
    note "$label"
    if [[ -n "$PROGRESS_REF" ]]; then
        "$QDBUS_CMD" "$PROGRESS_REF" Set "" value "$value" >/dev/null 2>&1 || true
        "$QDBUS_CMD" "$PROGRESS_REF" setLabelText "$label" >/dev/null 2>&1 || true
    fi
}

progress_close() {
    if [[ -n "$PROGRESS_REF" ]]; then
        "$QDBUS_CMD" "$PROGRESS_REF" close >/dev/null 2>&1 || true
        PROGRESS_REF=""
    fi
}

note() {
    printf '[Dual Screen Mode] %s\n' "$1"
}

welcome() {
    if (( DRY_RUN || AUDIT || CHECK_ONLY || GUI_EXECUTE )); then
        return 0
    fi

    ui_question \
        "Welcome to Dual Screen Mode.\n\nUse a Steam Deck or other PC handheld as a Wii U-style GamePad or DS/3DS bottom screen with your SteamOS or KDE Plasma gaming PC.\n\nThe wizard checks the host, explains anything missing, and creates the Dual Screen Mode and Dual Screen Mode Settings shortcuts.\n\nContinue with setup?" ||
        exit 0
}

print_audit() {
    cat <<'EOF'
Dual Screen Mode trust/audit summary

Changes it may make:
  - Install krfb through the host's pacman repositories, only after confirmation.
  - Install Sunshine from the official Flathub app ID: dev.lizardbyte.app.Sunshine.
  - Add a user-level KWin screencast permission setting.
  - Update Sunshine's local capture/output settings.
  - Save a selected display size and audio preference in a user config file.
  - Audio is explicit: Host sets Sunshine audio streaming off and leaves host outputs alone. Handheld sets it on and mutes the current default output. Both is work in progress and currently uses the Handheld behavior. Before this, Dual Screen Mode saves Sunshine's current audio-stream setting and, when available, the current default output's volume and mute state. Those saved values are restored when the mode turns off.
  - Create a user-local on/off launcher and management app plus matching launcher icons.

What it does not do:
  - No telemetry, analytics, ads, bundled software, or background daemon.
  - No curl|bash, remote shell script, or arbitrary third-party download.
  - No automatic removal of Sunshine, Moonlight, or krfb.
  - No access to personal files beyond the selected icon and known config paths.
  - No audio driver, blank audio device, or virtual audio device is installed. The default output is not changed and other outputs are not altered. If the host uses PipeWire, audio controls use its existing PulseAudio compatibility interface. If the host output cannot be muted automatically, it is left unchanged and a warning is shown.

Safety controls:
  - --dry-run previews the host-specific work without modifying it.
  - Existing files are backed up before replacement.
  - System changes require explicit confirmation.
  - If krfb is missing, the graphical wizard opens a visible Konsole package step and waits for the user to check again.
  - The KWin permission tradeoff is shown before it is enabled.
  - Uninstall removes only files and settings owned by Dual Screen Mode.
EOF
}

fail() {
    ui_message "$1"
    exit 1
}

restore_readonly() {
    if (( READONLY_DISABLED )); then
        run_as_root steamos-readonly enable >/dev/null 2>&1 || true
        READONLY_DISABLED=0
    fi
}
trap 'progress_close; restore_readonly' EXIT

backup_file() {
    local source="$1"
    if [[ ! -e "$source" ]]; then
        return 0
    fi
    if (( DRY_RUN )); then
        note "Would back up $source"
        return 0
    fi
    mkdir -p "$BACKUP_DIR"
    cp -a "$source" "$BACKUP_DIR/"
}

set_config_key() {
    local file="$1"
    local key="$2"
    local value="$3"

    if (( DRY_RUN )); then
        note "Would set $key = $value in $file"
        return 0
    fi

    if grep -Eq "^[[:space:]]*${key}[[:space:]]*=" "$file" 2>/dev/null; then
        sed -i -E "s|^[[:space:]]*${key}[[:space:]]*=.*$|${key} = ${value}|" "$file"
    else
        printf '%s = %s\n' "$key" "$value" >> "$file"
    fi
}

valid_resolution() {
    [[ "$1" =~ ^[0-9]{3,5}x[0-9]{3,5}$ ]]
}

check_host() {
    local session="${XDG_SESSION_TYPE:-unknown}"
    local desktop="${XDG_CURRENT_DESKTOP:-unknown}"

    note "Desktop session: $desktop / $session"

    if [[ "$session" != "wayland" ]]; then
        fail "Dual Screen Mode needs a KDE Wayland session. Current session: $session"
    fi

    if [[ "$desktop" != *KDE* && "$desktop" != *Plasma* ]]; then
        fail "Dual Screen Mode currently targets KDE Plasma. Current desktop: $desktop"
    fi

    if ! have kscreen-doctor; then
        fail "kscreen-doctor was not found. This does not look like a complete KDE Plasma session."
    fi
}

system_check() {
    check_host
    if have krfb-virtualmonitor; then
        note "krfb-virtualmonitor is ready."
    else
        note "krfb-virtualmonitor is missing. The setup will offer to install krfb."
    fi
    if have flatpak && flatpak info "$APP_ID" >/dev/null 2>&1; then
        note "Sunshine is ready."
    else
        note "Sunshine is missing or unavailable. The setup will offer the official Flatpak."
    fi
}

permissions_step() {
    if (( DRY_RUN )); then
        note "Would ask for approval to install missing pieces and add the KWin screencast setting."
        PERMISSIONS_APPROVED=1
        return 0
    fi

    ui_question \
        "Setup and permissions\n\nDual Screen Mode may install KDE's krfb virtual-display component and Sunshine if they are missing. It also adds a user-level KWin setting so Sunshine can capture the virtual display.\n\nThere is no background service or telemetry. Sunshine, Moonlight, krfb, and your backups stay under your control.\n\nContinue?" ||
        exit 0
    PERMISSIONS_APPROVED=1
}

install_krfb() {
    if have krfb-virtualmonitor; then
        note "krfb-virtualmonitor is already installed."
        return 0
    fi

    if ! ui_question "krfb-virtualmonitor is missing. Install KDE's krfb package?"; then
        fail "krfb is required to create the virtual second screen."
    fi

    if (( DRY_RUN )); then
        note "Would install krfb and its dependencies."
        return 0
    fi

    if ! have pacman; then
        fail "This setup expects pacman for the SteamOS or Arch host."
    fi

    if ! have pkexec && ! have kdesu && ! have sudo; then
        fail "A system administrator authorization tool is required to install krfb."
    fi

    if have steamos-readonly; then
        if ! run_as_root bash -c '
            set -e
            steamos-readonly disable
            trap "steamos-readonly enable" EXIT
            pacman-key --init
            pacman-key --populate archlinux holo
            pacman -S --needed krfb
        '; then
            fail "The system could not authorize or complete the temporary SteamOS package installation."
        fi
    elif ! run_as_root pacman -S --needed krfb; then
        fail "The krfb installation failed. No Dual Screen Mode files were installed."
    fi

    have krfb-virtualmonitor || fail "krfb installed without krfb-virtualmonitor being available."
}

install_sunshine() {
    if ! have flatpak; then
        fail "Flatpak is required for the Sunshine host in v1."
    fi

    if flatpak info "$APP_ID" >/dev/null 2>&1; then
        note "Sunshine is already installed."
    else
        if ! ui_question "Sunshine is missing. Install the LizardByte Sunshine Flatpak from Flathub?"; then
            fail "Sunshine is required to stream the virtual display."
        fi

        if (( DRY_RUN )); then
            note "Would install $APP_ID from Flathub."
        else
            if ! flatpak remotes --columns=name 2>/dev/null | grep -Fxq flathub; then
                flatpak remote-add --if-not-exists --user flathub \
                    https://flathub.org/repo/flathub.flatpakrepo
            fi
            if ! flatpak install --user flathub "$APP_ID"; then
                fail "The Sunshine installation failed."
            fi
        fi
    fi

    if flatpak override --user --show "$APP_ID" 2>/dev/null |
        grep -Fq 'KWIN_WAYLAND_NO_PERMISSION_CHECKS=1'; then
        note "Sunshine's KWin permission override is already present."
    elif (( DRY_RUN )); then
        note "Would enable Sunshine's KWin permission override."
    else
        if (( ! PERMISSIONS_APPROVED )) && ! ui_question \
            "Sunshine needs a user-level KWin screencast override for this capture method. Continue?"; then
            fail "Sunshine's KWin permission override was not enabled."
        fi
        if ! flatpak override --user \
            --env=KWIN_WAYLAND_NO_PERMISSION_CHECKS=1 \
            "$APP_ID"; then
            fail "Could not configure Sunshine's KWin permission override."
        fi
        mkdir -p "$STATE_DIR"
        touch "$OWNED_OVERRIDE_MARKER"
    fi
}

configure_environment() {
    if grep -Fxq 'KWIN_WAYLAND_NO_PERMISSION_CHECKS=1' "$ENV_FILE" 2>/dev/null; then
        note "KWin screencast environment setting is already present."
        return 0
    fi

    if (( ! PERMISSIONS_APPROVED )) && ! ui_question \
        "Add the KWin screencast environment setting? It is needed for the virtual display capture method."; then
        fail "The KWin screencast environment setting was not added."
    fi

    backup_file "$ENV_FILE"
    if (( DRY_RUN )); then
        note "Would add KWIN_WAYLAND_NO_PERMISSION_CHECKS=1 to $ENV_FILE"
        return 0
    fi

    mkdir -p "$ENV_DIR" "$STATE_DIR"
    if [[ -e "$ENV_FILE" ]]; then
        printf '%s\n' 'KWIN_WAYLAND_NO_PERMISSION_CHECKS=1' >> "$ENV_FILE"
    else
        printf '%s\n' \
            '# Managed by Dual Screen Mode' \
            'KWIN_WAYLAND_NO_PERMISSION_CHECKS=1' > "$ENV_FILE"
    fi
    touch "$OWNED_ENV_MARKER"
}

configure_sunshine() {
    if grep -Eq "^[[:space:]]*capture[[:space:]]*=[[:space:]]*kwin[[:space:]]*$" "$SUNSHINE_CONF" 2>/dev/null &&
        grep -Eq "^[[:space:]]*output_name[[:space:]]*=[[:space:]]*Virtual-${VIRTUAL_NAME}[[:space:]]*$" "$SUNSHINE_CONF" 2>/dev/null; then
        note "Sunshine is already configured for Virtual-${VIRTUAL_NAME}."
        return 0
    fi

    backup_file "$SUNSHINE_CONF"
    if (( DRY_RUN )); then
        note "Would configure Sunshine for KWin capture and Virtual-${VIRTUAL_NAME}."
        return 0
    fi

    mkdir -p "$(dirname "$SUNSHINE_CONF")" ||
        fail "Could not create Sunshine's configuration directory."
    touch "$SUNSHINE_CONF" ||
        fail "Could not create Sunshine's configuration file."
    set_config_key "$SUNSHINE_CONF" capture kwin
    set_config_key "$SUNSHINE_CONF" output_name "Virtual-${VIRTUAL_NAME}"
}

choose_resolution() {
    if (( DRY_RUN )); then
        RESOLUTION="1280x800"
        note "Display size: $RESOLUTION"
        return 0
    fi

    local selected
    selected="$(ui_choose "Choose the virtual display size" "1280x800" "1280x720" "1920x1080" "1920x1200" "Custom")" || exit 0
    if [[ "$selected" == "Custom" ]]; then
        RESOLUTION="$(ui_input "Enter the resolution as widthxheight" "1280x800")" || exit 0
        if ! valid_resolution "$RESOLUTION"; then
            ui_message "That resolution was not recognized. Use a format such as 1280x800."
            exit 1
        fi
    else
        RESOLUTION="$selected"
    fi
}

choose_audio() {
    if (( DRY_RUN )); then
        AUDIO_MODE="host"
        note "Audio choice: Host"
        return 0
    fi

    local selected
    selected="$(ui_choose "Where should audio play?" "Host" "Handheld" "Both (work in progress)")" || exit 0
    case "$selected" in
        "Handheld") AUDIO_MODE="handheld" ;;
        "Both (work in progress)") AUDIO_MODE="both" ;;
        *) AUDIO_MODE="host" ;;
    esac
}

review_choices() {
    if (( DRY_RUN )); then
        note "Would ask for final confirmation: $RESOLUTION, audio $AUDIO_MODE."
        return 0
    fi

    local audio_label="Host"
    case "$AUDIO_MODE" in
        handheld) audio_label="Handheld" ;;
        both) audio_label="Both (work in progress; uses Handheld for now)" ;;
    esac

    ui_question \
        "Review\n\nVirtual display: $RESOLUTION at 60 Hz\nAudio: $audio_label\n\nThe next step installs Dual Screen Mode, creates the Dual Screen Mode shortcut, and adds the Dual Screen Mode Settings app. Install Dual Screen Mode now?" ||
        exit 0
}

save_settings() {
    if (( DRY_RUN )); then
        note "Would save display size $RESOLUTION and audio mode $AUDIO_MODE to $SETTINGS_FILE"
        return 0
    fi
    if [[ -e "$SETTINGS_FILE" && ! -f "$STATE_DIR/owned-settings" ]]; then
        if ! ui_question "An existing Dual Screen Mode settings file was found. Back it up and replace it with these choices?"; then
            fail "The existing settings file was left unchanged."
        fi
        backup_file "$SETTINGS_FILE"
    fi
    mkdir -p "$SETTINGS_DIR" "$STATE_DIR"
    printf '%s\n' \
        '# Managed by Dual Screen Mode' \
        "resolution=$RESOLUTION" \
        "audio_mode=$AUDIO_MODE" > "$SETTINGS_FILE"
    touch "$STATE_DIR/owned-settings"
}

install_toggle() {
    if [[ -e "$TOGGLE_DEST" && ! -f "$STATE_DIR/owned-toggle" ]]; then
        if ! ui_question "An existing toggle is at $TOGGLE_DEST. Back it up and replace it with Dual Screen Mode?"; then
            fail "The existing toggle was left unchanged."
        fi
    fi

    backup_file "$TOGGLE_DEST"
    if (( DRY_RUN )); then
        note "Would install the Dual Screen Mode toggle at $TOGGLE_DEST"
        return 0
    fi

    mkdir -p "$(dirname "$TOGGLE_DEST")"
    install -m 755 "$PROJECT_DIR/dual-screen-mode.sh" "$TOGGLE_DEST" ||
        fail "Could not install the Dual Screen Mode toggle."
    mkdir -p "$STATE_DIR"
    touch "$STATE_DIR/owned-toggle"
}

install_launcher() {
    if [[ -e "$DESKTOP_DEST" && ! -f "$STATE_DIR/owned-launcher" ]]; then
        if ! ui_question "An existing desktop launcher is at $DESKTOP_DEST. Back it up and replace it?"; then
            fail "The existing desktop launcher was left unchanged."
        fi
    fi

    if [[ -n "$ICON_SOURCE" && ! -f "$ICON_SOURCE" ]]; then
        fail "Icon file was not found: $ICON_SOURCE"
    fi

    if [[ -z "$ICON_SOURCE" && ! -f "$BUNDLED_ICON" && ! -f "$ICON_DEST" ]]; then
        note "No custom icon found; the desktop icon will use KDE's built-in display icon."
    fi

    backup_file "$DESKTOP_DEST"
    if (( DRY_RUN )); then
        note "Would create $DESKTOP_DEST"
        if [[ -n "$ICON_SOURCE" ]]; then
            note "Would install custom icon from $ICON_SOURCE"
        elif [[ -f "$BUNDLED_ICON" ]]; then
            note "Would install the bundled Dual Screen Mode icon"
        fi
        return 0
    fi

    mkdir -p "$(dirname "$DESKTOP_DEST")"

    local icon_value="video-display"
    if [[ -n "$ICON_SOURCE" ]]; then
        mkdir -p "$(dirname "$ICON_DEST")"
        install -m 644 "$ICON_SOURCE" "$ICON_DEST" ||
            fail "Could not install the custom icon."
        icon_value="$ICON_DEST"
        mkdir -p "$STATE_DIR"
        touch "$STATE_DIR/owned-icon"
    elif [[ -f "$BUNDLED_ICON" ]]; then
        mkdir -p "$(dirname "$ICON_DEST")"
        install -m 644 "$BUNDLED_ICON" "$ICON_DEST" ||
            fail "Could not install the bundled icon."
        icon_value="$ICON_DEST"
        mkdir -p "$STATE_DIR"
        touch "$STATE_DIR/owned-icon"
    elif [[ -f "$ICON_DEST" ]]; then
        icon_value="$ICON_DEST"
    fi

    printf '%s\n' \
        '[Desktop Entry]' \
        'Type=Application' \
        'Name=Dual Screen Mode' \
        'Comment=Toggle the virtual second screen' \
        "Exec=$TOGGLE_DEST" \
        "Icon=$icon_value" \
        'Terminal=false' \
        'Categories=Utility;System;' \
        'StartupNotify=true' > "$DESKTOP_DEST"
    chmod +x "$DESKTOP_DEST" || fail "Could not make the desktop launcher executable."
    mkdir -p "$STATE_DIR"
    touch "$STATE_DIR/owned-launcher"
}

install_uninstaller() {
    if [[ -e "$UNINSTALL_DESKTOP_DEST" && ! -f "$STATE_DIR/owned-uninstall-launcher" ]]; then
        if ! ui_question "An existing uninstall launcher is at $UNINSTALL_DESKTOP_DEST. Back it up and replace it?"; then
            fail "The existing uninstall launcher was left unchanged."
        fi
    fi

    backup_file "$UNINSTALL_DESKTOP_DEST"
    backup_file "$UNINSTALL_SCRIPT_DEST"
    if (( DRY_RUN )); then
        note "Would create the graphical uninstall launcher at $UNINSTALL_DESKTOP_DEST"
        return 0
    fi

    mkdir -p "$UNINSTALL_APP_DIR"
    install -m 755 "$PROJECT_DIR/uninstall.sh" "$UNINSTALL_SCRIPT_DEST" ||
        fail "Could not install the graphical uninstall helper."
    install -m 755 "$PROJECT_DIR/settings-gui.py" "$MANAGEMENT_SCRIPT_DEST" ||
        fail "Could not install the Dual Screen Mode settings app."
    install -m 755 "$PROJECT_DIR/settings-launcher.sh" "$MANAGEMENT_LAUNCHER_DEST" ||
        fail "Could not install the Dual Screen Mode settings launcher."

    local settings_icon_value="video-display"
    if [[ -f "$BUNDLED_SETTINGS_ICON" ]]; then
        mkdir -p "$(dirname "$SETTINGS_ICON_DEST")"
        install -m 644 "$BUNDLED_SETTINGS_ICON" "$SETTINGS_ICON_DEST" ||
            fail "Could not install the Dual Screen Mode settings icon."
        settings_icon_value="$SETTINGS_ICON_DEST"
        touch "$OWNED_SETTINGS_ICON_MARKER"
    elif [[ -f "$SETTINGS_ICON_DEST" ]]; then
        settings_icon_value="$SETTINGS_ICON_DEST"
    fi
    printf '%s\n' \
        '[Desktop Entry]' \
        'Type=Application' \
        'Name=Dual Screen Mode Settings' \
        'Comment=View status, change settings, update, or uninstall Dual Screen Mode' \
        "Exec=$MANAGEMENT_LAUNCHER_DEST" \
        "TryExec=python3" \
        "Icon=$settings_icon_value" \
        'Terminal=false' \
        'Categories=Utility;System;' \
        'StartupNotify=true' > "$UNINSTALL_DESKTOP_DEST"
    chmod +x "$UNINSTALL_DESKTOP_DEST" || fail "Could not make the uninstall launcher executable."
    mkdir -p "$STATE_DIR"
    touch "$STATE_DIR/owned-uninstaller" "$STATE_DIR/owned-management-app" "$STATE_DIR/owned-management-launcher" "$STATE_DIR/owned-uninstall-launcher"
}

run_connection_test() {
    if [[ -f "$RUNTIME_DIR/active" ]]; then
        ui_message "Dual Screen Mode is already active, so the test left it alone.\n\nConnect your handheld with Moonlight when you are ready."
        return 0
    fi

    ui_message "The connection test will turn the virtual display on for a few seconds, then turn it back off. It will not launch a game or emulator."
    if ! "$TOGGLE_DEST" >/dev/null 2>&1; then
        ui_message "The connection test could not start the virtual display. The setup itself is still installed."
        return 0
    fi
    sleep 4
    if [[ -f "$RUNTIME_DIR/active" ]]; then
        "$TOGGLE_DEST" >/dev/null 2>&1 || true
        ui_message "Connection test finished. The virtual display was turned back off."
    else
        ui_message "The virtual display did not stay active long enough to test. The setup itself is still installed."
    fi
}

main() {
    if (( AUDIT )); then
        print_audit
        exit 0
    fi

    if (( CHECK_ONLY )); then
        system_check
        exit 0
    fi

    if (( GUI_EXECUTE )); then
        if ! valid_resolution "$RESOLUTION"; then
            fail "The selected resolution is not valid: $RESOLUTION"
        fi
        case "$AUDIO_MODE" in
            host|handheld|both) ;;
            *) fail "The selected audio mode is not valid: $AUDIO_MODE" ;;
        esac
        PERMISSIONS_APPROVED=1
    fi

    if (( DRY_RUN )); then
        note "Dry run: no files, packages, or settings will be changed."
    fi

    if (( ! GUI_EXECUTE )); then
        system_check
        permissions_step
        choose_resolution
        choose_audio
        review_choices
    fi

    progress_open
    progress_step 1 "Checking the host environment"
    check_host
    progress_step 2 "Checking the virtual-display component"
    install_krfb
    progress_step 3 "Checking Sunshine"
    install_sunshine
    progress_step 4 "Applying the KDE capture permission"
    configure_environment
    progress_step 5 "Configuring Sunshine for the virtual display"
    configure_sunshine
    progress_step 6 "Saving display and audio choices"
    save_settings
    progress_step 7 "Creating Dual Screen Mode and Settings shortcuts"
    install_toggle
    install_launcher
    install_uninstaller
    progress_step 8 "Setup complete"
    progress_close

    if (( DRY_RUN )); then
        ui_message "Dry run complete. No changes were made."
    elif (( GUI_EXECUTE )); then
        ui_message "Setup complete."
    else
        ui_message "Setup complete. Give it a try!\n\nDouble-click Dual Screen Mode to create the virtual display. Moonlight is installed separately on the handheld, and Sunshine pairing is completed manually through the normal Moonlight and Sunshine flow. If KDE does not see the new capture permission right away, log out and back in or restart the host computer.\n\nOpen Dual Screen Mode Settings whenever you want to change options or remove the project.\n\nMade by slinky."
        if ui_question "Run a safe connection test now? It will turn the virtual display on, wait briefly, and turn it back off."; then
            run_connection_test
        fi
    fi
}

welcome
main
