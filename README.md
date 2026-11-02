# Dual Screen Mode

<p align="center">
  <img src="assets/dual-screen-mode.png" alt="Monitor and handheld connected as a second screen" width="180">
</p>

<p align="center"><strong>Use a Steam Deck or PC handheld as a wireless Wii U GamePad-style second screen for a Linux gaming PC.</strong></p>

Made by slinky.

Dual Screen Mode packages an existing KDE, Sunshine, and Moonlight setup into
one repeatable install. The goal is simple: make a handheld work like a Wii U
GamePad, a DS or 3DS bottom screen, or another useful two-screen display
without asking people to piece together scattered guides and terminal commands.

This is an early beta. The first target is SteamOS with KDE Plasma on Wayland.

## Important: what this project handles

Dual Screen Mode prepares the Linux PC that acts as the host. It creates and
removes the virtual display, configures Sunshine for KDE's capture method, and
gives you a simple on/off shortcut.

The handheld side is still manual:

- Install Moonlight separately on the Steam Deck, handheld, tablet, or phone.
- Pair Moonlight with Sunshine using Sunshine and Moonlight's normal pairing
  flow.
- Choose the host in Moonlight and enter the pairing PIN when prompted.

The project does not configure the network, firewall rules, or automatic
pairing. A short client setup guide is in
[`docs/MOONLIGHT_SETUP.md`](docs/MOONLIGHT_SETUP.md).

Sunshine can be installed by the wizard if it is missing. The wizard does not
install Moonlight on the handheld.

## What you need

### Host PC

This is the computer that runs the games and sends the virtual display to the
handheld. It needs:

- SteamOS or another Arch-based Linux installation
- KDE Plasma running on Wayland
- A working Flatpak installation
- A graphics device supported by Sunshine's encoder
- The host and handheld connected to the same local network

The wizard checks the host before it changes anything. It can guide you through
installing KDE's `krfb` package through `pacman`, and it can install Sunshine
from the official Flathub app ID `dev.lizardbyte.app.Sunshine` if Sunshine is
not already present.

If `krfb` is missing, the wizard pauses and opens a visible Konsole window for
the package installation. Enter the normal administrator password in Konsole,
wait for the package operation to finish, close that terminal, and click
**Check again** in the wizard. The wizard continues only after it confirms that
`krfb-virtualmonitor` is available. Dual Screen Mode does not handle, collect,
or store the administrator password.

If setup needs to be stopped, closing the wizard asks for confirmation and
stops the installer process; it does not remove anything that was already
installed.

### Handheld or client

- Moonlight installed separately
- A screen resolution that matches one of the available virtual display sizes
- Gamepad support enabled in Moonlight when you want the handheld controls sent
  to the host

The client can be a Steam Deck, another PC handheld, a tablet, or a phone.

## Install

1. Download and extract the project archive.
2. Double-click `Install Dual Screen Mode.desktop`.
3. Press **Begin setup** in the wizard.
4. Review the host checks, display size, and audio choice.
5. Let the wizard finish.

When setup finishes, the wizard creates two desktop shortcuts:

- **Dual Screen Mode** turns the virtual display on or off.
- **Dual Screen Mode Settings** opens the management app for status, settings,
  updates, help, about, and uninstall.

The installer does not pair Moonlight. Install Moonlight on the handheld and
complete the normal Sunshine pairing separately. See
[`docs/MOONLIGHT_SETUP.md`](docs/MOONLIGHT_SETUP.md).

## Normal use

1. Double-click **Dual Screen Mode** on the host.
2. Wait for the virtual display to be ready.
3. Open Moonlight on the handheld and connect to the already-paired host.
4. Start a Sunshine stream and use Moonlight's gamepad mode when you want the
   handheld controls sent to the host.
5. Double-click **Dual Screen Mode** again when you are finished.

The virtual display remains active if Moonlight disconnects. That allows the
handheld to reconnect without rebuilding the display.

## Wii U and DS-style use

For Cemu, open `Options` and `Input settings`, choose `Wii U GamePad`, select
`SDLController`, choose the Moonlight controller, and save the profile. Cemu's
GamePad touch input is normally controlled by a left mouse click, so Moonlight
mouse mode can be useful when a game needs touchscreen input.

For Azahar or another 3DS emulator, configure the emulator's second-screen
layout and controller profile separately. Dual Screen Mode only provides the
display and the streamed input connection.

Gyro and microphone forwarding are not included in this project. Optional
motion-control tools such as SteamDeckGyroDSU remain a separate setup.

## Audio behavior

The wizard makes the audio choice explicit:

- **Host:** Sunshine audio streaming is disabled. Host audio is left alone.
- **Handheld:** Sunshine audio streaming is enabled. The current default host
  output is muted for the session.
- **Both (work in progress):** This currently uses Handheld behavior. Sunshine
  audio streaming is enabled and the current default host output is muted for
  the session.

Before a temporary change, the toggle saves Sunshine's current audio-stream
setting and, when available, the current default output's volume and mute state.
Those values are restored when the mode turns off.

The project does not change the system's default output, install an audio
driver, create a blank or virtual audio device, or alter other outputs. On
PipeWire systems, it uses the existing PulseAudio compatibility interface. If
the host output cannot be muted automatically, it is left unchanged and a
warning is shown.

## What the installer changes

The setup can:

- Install `krfb` if the virtual display component is missing.
- Install Sunshine from Flathub if it is missing.
- Add a user-level KWin screencast setting required by this capture method.
- Configure Sunshine to use KWin capture and `Virtual-DualScreen`.
- Save the selected display size and audio preference.
- Create a user-local on/off toggle, management app, desktop shortcuts, and
  icons.

It does not add a background daemon, telemetry, advertisements, bundled
software, or an automatic network configuration. It does not remove Sunshine,
Moonlight, `krfb`, or user backups during uninstall.

## Uninstall

Open **Uninstall Dual Screen Mode** from the desktop, then choose **Uninstall**
inside the management app. It removes only files and settings owned by Dual
Screen Mode.

Sunshine, Moonlight, `krfb`, and user backups remain installed. The command-line
fallback is available for development:

```bash
bash uninstall.sh
```

## Supported setup

The currently validated setup is:

- SteamOS or Arch-based Linux
- KDE Plasma on Wayland
- Sunshine Flatpak
- Moonlight client
- KDE `krfb-virtualmonitor`
- Sunshine KWin capture

The host must remain in KDE Desktop Mode while the virtual display is active.
Switching a SteamOS host to Gaming Mode ends the desktop session that owns the
virtual display.

## Troubleshooting

### Moonlight cannot find or pair with the host

Confirm that Sunshine is running on the host and that both devices are on the
same local network. Moonlight and Sunshine pairing is handled through their
normal pairing flow, not by Dual Screen Mode.

### The handheld shows the main monitor instead of the second screen

Turn Dual Screen Mode off and on again, then reconnect Moonlight. The host
should show a virtual output named `Virtual-DualScreen`.

### The stream is too small or hard to read

Open the management app and choose a display size that matches the handheld.
Also check Moonlight's stream resolution and scaling settings.

### A controller does not appear in an emulator

Reconnect Moonlight, make sure gamepad mode is enabled, then revisit the
emulator's input settings. Emulator profiles are separate from Dual Screen
Mode.

### The Settings app does not open

Rerun the installer from the current package so the settings app and launcher
are replaced together. If it still fails, inspect:

```text
~/.local/state/dual-screen-mode/settings-gui.log
```

The Settings app's Help page can also open the Sunshine log and copy a small
diagnostic summary.

## Development

The source is intentionally plain and inspectable. There is no remote shell
script and no `curl | bash` install path.

Run the local tests from the project directory:

```bash
bash tests/test-syntax.sh
bash tests/test-toggle.sh
bash tests/test-setup-execute.sh
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for small changes and issue reports.

## Credits and license

Dual Screen Mode is a packaging and configuration layer around existing tools
and community knowledge. It does not replace or claim ownership of Sunshine,
Moonlight, KDE, `krfb`, or the guides that informed the setup.

See [`ACKNOWLEDGMENTS.md`](ACKNOWLEDGMENTS.md) and [`LICENSE`](LICENSE).
