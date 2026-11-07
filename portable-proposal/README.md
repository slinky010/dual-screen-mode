# Dual Screen Mode

Dual Screen Mode creates a wireless second screen for your Linux gaming PC and connects it to a Steam Deck or other handheld through Moonlight and Sunshine. Use it as a Wii U-style GamePad screen, a DS or 3DS second screen, or simply as another monitor.

It handles the host-side setup, creates simple desktop shortcuts, and keeps the temporary display, audio, touch, and Sunshine changes organized for you.

## What's new

- Settings now refreshes the display, Sunshine, touch, and motion status automatically, while Deck discovery can use the saved address or search the local network when needed.
- The virtual display opens centered below the main monitor, touch routing is monitored after Moonlight connects, and duplicate clicks are safely ignored during startup and shutdown.
- The new **DSU Motion Probe** is a standalone diagnostic tool for checking the Deck-to-host motion path before troubleshooting an emulator. It shows whether the DSU service responds, identifies the connected controller and gyro capability, reports packet health and rate, and displays live accelerometer and gyroscope data with a temporary visual calibration view.
- Cemu setup is now a simple one-choice step: start DSM with Cemu closed, wait for the Deck Gyro profile-ready notification, then open Cemu and select **Dual Screen Mode Deck Gyro**. DSM prepares the complete profile, updates its DSU connection to the discovered Deck IP on port **26760**, and preserves the existing controls.

## Changelog

### 0.1.6-beta

- Added a working Updates tab that checks GitHub releases, verifies the downloaded checksum, and applies updates in place without installing a second DSM instance.
- The updater safely stops an active DSM session, replaces only DSM-owned files, preserves user settings and backups, leaves Sunshine/Moonlight/krfb/emulator files alone, and relaunches Settings when finished.
- Added updater failure logging and clearer progress/confirmation messages so an interrupted update can be diagnosed without losing the current installation.

### 0.1.5-beta

- Added live status updates for the display, Sunshine, touch routing, and DSU motion.
- Added automatic Deck discovery, touch monitoring, centered display placement, and safer desktop toggling.
- Added the standalone **DSU Motion Probe**, with live DSU connection details, controller and gyro detection, packet-health statistics, accelerometer and gyroscope readings, and temporary visual calibration.
- Added a Sunshine refresh at mode startup so an already-running session loads the virtual display target, plus stronger cleanup when the mode is disabled.
- Simplified Cemu setup: DSM prepares the Deck Gyro profile and DSU address automatically, so users only need to select **Dual Screen Mode Deck Gyro** in Cemu.

### Coming next

- Explore SteamOS Game Mode support so Dual Screen Mode can be used without switching to Desktop Mode.
- Explore a Windows edition for Windows hosts.
- Finish the **Both** audio mode so host and handheld audio behavior can be selected intentionally.
- Continue broader handheld, hardware, and network compatibility testing.

Emulator installation and broad emulator-specific configuration are intentionally outside the current project. Cemu receives the focused profile preparation described above; Azahar, melonDS, and other emulators keep their own profiles and settings.

This is beta release **0.1.6-beta** for SteamOS and KDE Plasma on Wayland.

## What you need

- A host PC running SteamOS or another Arch-based Linux installation
- KDE Plasma on Wayland
- A working Flatpak installation
- A Steam Deck, PC handheld, tablet, or phone that supports Moonlight
- Both devices on the same local network

Dual Screen Mode can install Sunshine on the host if it is missing. Moonlight is installed and paired separately on the handheld.

## Install

1. Extract this folder somewhere easy to find, such as the Desktop.
2. Double-click **Install Dual Screen Mode.desktop**.
3. Choose **Launch** if KDE asks what to do. Do not choose **Open with Kate**.
4. Click **Begin setup** and follow the wizard.
5. If KDE's virtual-display package is missing, the wizard opens Konsole. Enter your normal administrator password there, wait for the installation to finish, close Konsole, and click **Check again**.
6. Let the wizard finish and create the two desktop shortcuts.

Your password is entered in Konsole, not into Dual Screen Mode. The application does not collect or store it.

## Normal use

1. Double-click **Dual Screen Mode** on the host.
2. Wait for the virtual display to become ready.
3. Open Moonlight on the handheld and connect to the paired host.
4. Start the stream.
5. Enable Moonlight's gamepad mode when you want the handheld controls sent to the host.
6. Double-click **Dual Screen Mode** again when you are finished.

The toggle accepts one action at a time. Rapid duplicate clicks are ignored while it is starting or disabling, and a very fast second click after disabling cannot immediately re-enable the mode.

When the mode starts, DSM refreshes the Flatpak Sunshine session so Sunshine loads the virtual display target instead of keeping a previously loaded physical-display target. If Sunshine was already streaming, that stream may end; reconnect Moonlight after DSM reports that it is ready.

When the mode is disabled, DSM stops the session it started, restores the Sunshine display settings it temporarily changed, and returns a Sunshine session that was already running before startup.

When the virtual display appears, Dual Screen Mode places it centered along the bottom edge of the main physical display. You can still adjust the arrangement later in KDE's Display Configuration if you prefer a different layout.

The virtual display remains active if Moonlight disconnects, so the handheld can reconnect without rebuilding the display. The mode is independent of the Moonlight stream: Moonlight status does not determine whether DSU motion data is arriving.

The host must remain in KDE Desktop Mode while the virtual display is active.

## Motion and gyro health

Motion monitoring is enabled by default after setup. It checks the Deck's local DSU motion connection while Dual Screen Mode is active and reconnects automatically if the Deck briefly disappears.

The Deck address is optional. When it is blank, both **Dual Screen Mode** and **Dual Screen Mode Settings** automatically search the local network for the Deck's motion service and save a discovered address. **Find Deck** and manual entry remain available as fallbacks. Discovery never uses the internet.

When a saved address is present, DSM gives it a full settling window of about five seconds before falling back to the local-network scan, so a Deck that is waking up is not rejected too quickly.

Settings shows clear live states:

- **Motion: Enabled · Connected**
- **Motion: Enabled · Looking for your Steam Deck…**
- **Motion: Enabled · Connecting…**
- **Motion: Enabled · Unable to connect**
- **Motion: Disabled**

The Settings window refreshes motion, touch routing, Sunshine, and virtual-display status together about once per second. Settings can perform its own temporary motion check while the main mode is disabled; that check ends when Settings closes.

### DSU Motion Probe

The DSU Motion Probe is a separate, optional diagnostic window for checking the Deck's motion connection before opening Cemu or another emulator. It helps answer the basic question: **is motion data actually reaching the host?**

The probe shows:

- Whether the Deck's DSU service responds
- Which controller is connected and whether full gyro data is available
- Live packet rate, valid packets, invalid packets, and detected sequence gaps
- Live accelerometer and gyroscope readings
- A visual gravity view that responds as the Deck moves

Its **Calibrate** button only recenters the probe's temporary visual gravity view. It does not change raw DSU data, emulator settings, or anything on the Deck. A connected probe confirms that DSM is receiving motion packets; it does not claim that Cemu or another emulator is using them.

When Dual Screen Mode finds a Cemu configuration, it prepares a **Dual Screen Mode Deck Gyro** profile on the next mode start. Start DSM with Cemu closed and wait for the Deck Gyro profile-ready notification before opening Cemu. The profile preserves the existing controller mappings, adds the Deck's DSU motion connection as **DSMController**, updates Cemu's DSU host to the discovered Deck IP on port **26760**, and backs up the previous profile and settings. Once DSM reports that the profile is ready, open Cemu's Input settings and select **Dual Screen Mode Deck Gyro**. No manual IP entry or **Add input API** step is needed. DSM does not install Cemu or any other emulator, and Azahar, melonDS, and other emulator profiles remain separate.

For Azahar and other emulators, DSM's responsibility is to keep the local DSU path and handheld touchscreen available. Use the emulator's own controller and motion settings when an emulator needs a one-time selection.

## Touch routing

When Sunshine exposes its virtual touchscreen, Dual Screen Mode maps it to the virtual second screen through KWin and watches for devices that appear after Moonlight connects. The previous touch mapping is restored when the mode turns off.

The Settings status updates automatically and uses plain-language states such as **Mapped to the second screen**, **Waiting for the handheld touchscreen**, and **Unable to check touch routing**. Touch behavior inside an emulator still depends on that emulator's own input settings.

## Audio

- **Host:** Audio stays on the host and Sunshine audio streaming is disabled.
- **Handheld:** Audio streams to the handheld and the current default host output is muted temporarily.
- **Both:** Work in progress. It currently behaves like **Handheld**.

Before changing audio, Dual Screen Mode saves the existing Sunshine audio setting and, when available, the current default output's volume and mute state. Those values are restored when the mode turns off. The project does not install an audio driver, create a virtual audio device, change the system's default output, or alter other outputs.

## Settings

**Dual Screen Mode Settings** provides:

- Live status for the virtual display, touch routing, Sunshine, and motion
- Display-size and audio choices
- Motion enable/disable control
- Automatic Deck discovery, **Find Deck**, and optional manual address, port, and slot fields
- Separate motion diagnostics and temporary calibration
- Help, logs, diagnostic copying, update checks, verified downloads, and uninstall

The Updates tab checks GitHub for a newer beta release, shows its release notes,
downloads the Linux package and matching checksum, verifies the download, and
offers to apply it in place. DSM safely closes its own Settings process, replaces
its owned files, preserves your settings and backups, and reopens the updated
Settings app. Sunshine, Moonlight, krfb, and emulator files are left alone.

The GUI uses the original Dual Screen Mode artwork for both launchers and its in-app branding.

## Uninstall

Open **Dual Screen Mode Settings** and choose **Uninstall**. It disables the mode, stops DSM-owned helpers, restores temporary audio and touch changes, restores DSM-owned Sunshine capture settings, and removes only Dual Screen Mode's files, shortcuts, settings, and owned configuration changes.

It does not remove:

- Sunshine
- Moonlight
- `krfb`
- User backups
- Games or emulator files

## Troubleshooting

### Motion says Unable to connect

Make sure the Deck's DSU motion service is running and both devices are on the same local network. Open Settings and use **Find Deck**. Manual entry is available if local discovery cannot find the service.

### Touch is waiting

Connect the handheld with Moonlight and wait for its touchscreen device to appear. If touch still reaches the wrong display, turn Dual Screen Mode off and on again, then reconnect Moonlight.

### Moonlight cannot find or pair with the host

Make sure Sunshine is running, Moonlight has been paired with it, and both devices are on the same local network. Pairing is handled through Sunshine and Moonlight, not Dual Screen Mode.

### The handheld shows the host's main monitor

Turn Dual Screen Mode off and on again, then reconnect Moonlight. DSM refreshes Sunshine during startup so it can load the virtual output named `Virtual-DualScreen`.

### The Settings app does not open

Rerun the installer from the same package so the Settings app and launcher are replaced together. The Settings Help page can also open the Sunshine log and copy a diagnostic summary.

### Cemu needs a manual DSU address

Close Cemu before starting Dual Screen Mode. Do not open Cemu until DSM shows the Deck Gyro profile-ready notification. Then open Cemu's Input settings and select **Dual Screen Mode Deck Gyro**. DSM prepares the DSU address for that profile; you should not need to add a DSU controller or type the IP manually.

### I clicked the shortcut twice

The toggle accepts one action at a time. Duplicate clicks are ignored while the mode is starting or disabling, and a very fast second click after disabling cannot immediately enable the mode again. Wait a moment before intentionally starting it again.

## Current limitations

- The **Both** audio option is still a work in progress.
- The Deck's DSU motion service must already be running; Dual Screen Mode does not install or manage it.
- Emulator-facing motion selection is not automated for Azahar, melonDS, or other emulators. Cemu receives the focused DSMController profile described above, and the user selects it in Cemu.
- Emulator-specific touch behavior is outside this project.
- Microphone forwarding is not included.
- Broader Game Mode and hardware compatibility testing is still needed.
- Ubuntu, Fedora, GNOME, X11, and other non-Arch or non-KDE setups are not currently supported by the installer.

## Development checks

The `tests/` directory contains shell, Python, setup, and touch-routing checks. They are for development and are not needed for normal installation.

Nothing in Dual Screen Mode uses telemetry or an always-on background daemon. The motion monitor runs only while Dual Screen Mode is active, and the Settings check ends when Settings closes.
