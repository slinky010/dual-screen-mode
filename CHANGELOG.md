# Changelog

## 0.1.3 Beta

- Pause the graphical wizard when `krfb` is missing and use an explicit Konsole
  installation step with a Check again action instead of trying to track a
  privileged terminal in the background.
- Open the wizard and settings app at a larger default size and hide scrollbars
  unless the current page actually needs to scroll.
- Allow a stalled graphical setup to be stopped from the window close button
  with a clear warning about partial changes.
- Simplified the wizard and settings to choose a virtual display size instead of a device label that did not affect behavior.
- Added a Settings Help page with Moonlight, resolution, audio, and emulator guidance plus Sunshine log access.
- Added a dedicated settings launcher with visible startup errors and a matching gear icon.
- Increased the wizard's opening size and made long pages scroll inside a fixed footer so navigation stays visible.
- Made the settings window scroll-safe and recorded launch context plus the last startup error in its log.
- Replaced unsupported Tk alpha-color values so the Settings app starts correctly on standard SteamOS Python/Tk builds.
- Added a GitHub-ready README, Moonlight client setup guide, contribution notes, CI tests, and a Reddit post draft.
- Added conservative startup cleanup, private runtime files, and process ownership checks for safer recovery.
- Marked update checking as work in progress until a public release source exists.
- Documented the exact audio, PipeWire, logging, and reconnect behavior.
- Marked the Both audio choice as work in progress and made its current
  behavior match Handheld audio consistently.

## 0.1.2 Beta

- Softened the setup and permissions copy so it reads like a friendly explanation instead of a security checklist.

## 0.1.1 Beta

- Made the wireless handheld connection explicit in the welcome screen, launcher description, README, and completion instructions.

## 0.1 Beta

- Added a branded KDE setup wizard with a native Tk interface and KDE dialog fallback.
- Added host checks for KDE Plasma on Wayland, krfb, Sunshine, and graphics support.
- Added virtual display creation through `krfb-virtualmonitor`.
- Added Sunshine KWin capture configuration for `Virtual-DualScreen`.
- Added selectable display size and host, handheld, or both audio modes.
- Added audio state backup and restoration when Dual Screen Mode is turned off.
- Added graphical on/off and uninstall launchers.
- Added backups and ownership markers for safe replacement and uninstall.
- Added dry run, audit, host check, and sandbox tests for the setup paths.

## Current limits

- Moonlight pairing still happens manually on the handheld.
- Gyro setup through SteamDeckGyroDSU remains optional and separate.
- Microphone forwarding is not included.
- The host must remain in KDE Desktop Mode while the virtual display is active.
