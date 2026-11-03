# Dual Screen Mode

<p align="center">
  <img src="assets/dual-screen-mode.png" alt="Monitor and handheld connected as a second screen" width="300">
</p>

<p align="center"><strong>Use a Steam Deck or other PC handheld as a wireless second screen for a Linux gaming PC.</strong></p>

Dual Screen Mode is a small KDE Plasma utility that lets you use a handheld like a Wii U GamePad, a DS or 3DS second screen, or a regular wireless monitor.

It creates a virtual display on the host PC, prepares Sunshine to stream that display, and gives you simple desktop shortcuts to turn the setup on and off.

It can be used for emulation, but it is not limited to emulation. You can also use the handheld as an extra wireless display for regular desktop or gaming use.

This is an early beta made for SteamOS and KDE Plasma on Wayland.

## Before you start

Dual Screen Mode uses two devices:

- **Host:** The main Linux PC that runs your games and creates the virtual display.
- **Handheld/client:** The Steam Deck or other device that connects to the host.

The setup uses two existing streaming tools:

- **Sunshine:** The streaming server running on the host.
- **Moonlight:** The app on the handheld that connects to Sunshine.

The currently validated host setup is:

- SteamOS or another Arch-based Linux installation
- KDE Plasma on Wayland
- Sunshine installed through Flatpak
- KDE's `krfb-virtualmonitor` component
- The host and handheld connected to the same local network

The handheld can be a Steam Deck, another PC handheld, tablet, or phone that supports Moonlight.

Moonlight is installed and paired separately. Dual Screen Mode can install Sunshine on the host if it is missing, but it does not install Moonlight or pair the devices for you.

## What setup is like

Once you download and extract Dual Screen Mode, the actual setup is only a few steps:

1. Double-click the installer.
2. Click **Begin setup**.
3. Follow the wizard's instructions.
4. Connect Moonlight on your handheld.

You do not need to copy terminal commands, edit configuration files, manually configure Sunshine, or search through KDE settings.

If the KDE virtual-display package is missing, the wizard opens Konsole and guides you through installing it. Enter your normal administrator password in Konsole, wait for the installation to finish, close the terminal, and click **Check again**.

Your password is entered in Konsole, not into Dual Screen Mode. The application does not collect or store it.

After the one-time setup, normal use is even simpler:

1. Double-click **Dual Screen Mode**.
2. Connect with Moonlight.
3. Use the handheld as your second screen.

## Install

1. Download the latest release from GitHub and extract it somewhere easy to find.
2. Open the extracted folder.
3. Double-click **Install Dual Screen Mode.desktop**.
4. Choose **Launch** if KDE asks what to do with the file. Do not choose **Open with Kate**.
5. Click **Begin setup** and follow the wizard.
6. When setup finishes, use the shortcuts created on your Desktop.

The wizard checks the host before making changes. It explains anything that is missing and asks for confirmation before installing packages or changing settings.

## Visual setup guide

<details>
<summary>Open the step-by-step guide</summary>

You do not need to know how to use GitHub or the Linux terminal to follow this guide. The screenshots show what to click and explain what should happen next.

#### 1. Open the latest release

On the Dual Screen Mode GitHub page, click **Releases** on the right side.

![Open the Releases section](docs/guide/1.jpg)

#### 2. Download the package

Open the newest release and expand **Assets**.

Download the `.tar.gz` package. It is a compressed package, similar to a `.zip` file. Do not choose the individual source files or the **Source code** downloads.

![Open the latest release assets](docs/guide/2.jpg)

#### 3. Extract the package

Open the downloaded `.tar.gz` file with Ark, KDE's archive utility, and click **Extract**.

Choose an easy-to-find location, such as your Desktop. You do not need to extract the files one at a time.

![Extract the package](docs/guide/3.jpg)

#### 4. Open the installer

Open the extracted Dual Screen Mode folder and double-click **Install Dual Screen Mode.desktop**.

![Open the installer file](docs/guide/4.jpg)

When KDE asks what you want to do with the file, choose **Launch**. Do not choose **Open with Kate**. Kate is a text editor, so that would only show the file contents instead of starting the installer.

![Choose Launch](docs/guide/5.jpg)

#### 5. Start the setup wizard

The welcome screen explains what Dual Screen Mode will set up. When you are ready, click **Begin setup**.

![Start the setup wizard](docs/guide/6.jpg)

The wizard checks the host computer for the pieces it needs and handles the setup for you. It will explain anything that is missing before continuing.

#### 6. Install the KDE virtual-display package if needed

If the KDE virtual-display package is missing, the wizard will tell you what to do. Click **Open installation terminal**.

![System check](docs/guide/7.jpg)

Konsole will open and ask for your normal system password. The password is entered in Konsole, not into Dual Screen Mode.

![Enter your password in Konsole](docs/guide/8.jpg)

Approve the package installation and wait for it to finish.

![Approve the package installation](docs/guide/9.jpg)

When the installation is complete, close Konsole and return to the wizard. Click **Check again**.

![Return to the wizard and check again](docs/guide/10.jpg)

The wizard will confirm that the required pieces are ready. Once the check passes, **Continue** becomes available.

#### 7. Finish the setup

Click **Continue** and let the wizard finish setting everything up.

When setup is complete, two shortcuts will be created on your Desktop:

- **Dual Screen Mode** turns the virtual display on or off.
- **Dual Screen Mode Settings** opens the management app for status, settings, updates, help, about, and uninstall.

![The two desktop shortcuts](docs/guide/11.jpg)

#### 8. Turn on Dual Screen Mode

Double-click **Dual Screen Mode** on your Desktop.

This turns on the virtual display and prepares Sunshine for the connection. You do not need to open Sunshine manually.

![Dual Screen Mode is ready](docs/guide/12.jpg)

Open Moonlight on your handheld and connect to the host. Moonlight must already be installed and paired separately.

#### 9. Uninstall if you change your mind

Open **Dual Screen Mode Settings** from the Desktop and choose **Uninstall**. The settings app removes Dual Screen Mode and its own changes without removing Sunshine, Moonlight, or `krfb`.

</details>



## Normal use

After setup:

1. Double-click **Dual Screen Mode** on the host.
2. Wait for the virtual display to become ready.
3. Open Moonlight on the handheld.
4. Connect to the paired host.
5. Start the stream.
6. Enable Moonlight's gamepad mode when you want the handheld controls sent to the host.
7. Double-click **Dual Screen Mode** again when you are finished.

The virtual display remains active if Moonlight disconnects, so the handheld can reconnect without rebuilding the display.

Choose a virtual display size that matches the handheld's screen. Some setups may also need adjustments in the host's KDE Display Configuration settings, such as scaling or display arrangement.

Emulator controller profiles and touch settings are configured separately inside each emulator.

## Settings and session behavior

**Dual Screen Mode Settings** lets you:

- View the current status
- Change the display size
- Change the audio behavior
- View help and diagnostic information
- Check update information
- Uninstall Dual Screen Mode

### Audio

The wizard lets you choose how audio behaves during the session:

- **Host:** Audio stays on the host. Sunshine audio streaming is disabled.
- **Handheld:** Audio streams to the handheld. The current default host output is muted temporarily.
- **Both:** Work in progress. It currently behaves like **Handheld** mode.

Before changing audio, Dual Screen Mode saves the existing Sunshine audio setting and, when available, the current default output's volume and mute state. Those values are restored when the mode turns off.

The project does not install an audio driver, create a virtual audio device, change the system's default output, or alter other outputs.

### Touch

When Sunshine exposes its virtual touchscreen, Dual Screen Mode maps it to `Virtual-DualScreen` through KWin.

This keeps touch input associated with the handheld display instead of the host's main monitor. Touch behavior inside Cemu, Azahar, or another application still depends on that application's own input settings.

## Uninstall

Open **Dual Screen Mode Settings** and choose **Uninstall**.

The uninstaller removes Dual Screen Mode's shortcuts, settings, scripts, and owned configuration changes.

It does not remove:

- Sunshine
- Moonlight
- `krfb`
- User backups
- Games or emulator files

## Troubleshooting

### Moonlight cannot find or pair with the host

Make sure Sunshine is running, Moonlight has been paired with it, and both devices are on the same local network.

Pairing is handled through Sunshine and Moonlight, not Dual Screen Mode.

### The handheld shows the host's main monitor

Turn Dual Screen Mode off and on again, then reconnect Moonlight.

The host should show a virtual output named `Virtual-DualScreen`.

### Touch lands on the wrong monitor

Turn the mode off and on again, then reconnect Moonlight.

The Settings app will show whether touch routing is mapped or waiting for Sunshine's virtual touchscreen.

### The stream is difficult to read

Choose a display size that matches the handheld. Then check Moonlight's stream resolution and scaling settings and the host's KDE Display Configuration settings.

### The Settings app does not open

Rerun the installer from the current package so the Settings app and launcher are replaced together.

If it still fails, inspect:

```
~/.local/state/dual-screen-mode/settings-gui.log
```

The Settings app's Help page can also open the Sunshine log and copy a small diagnostic summary.

## Known limitations

This is a one-person beta tested primarily with a Steam Machine and Steam Deck.

- The **Both** audio option is still a work in progress.
- Touch routing depends on Sunshine exposing a virtual touchscreen and KWin exposing the required input mapping.
- Emulator-specific touch behavior is outside this project.
- Gyro and microphone forwarding are not included.
- Other KDE, graphics, and handheld combinations may have issues that have not been tested yet.
- Ubuntu, Fedora, GNOME, X11, and other non-Arch or non-KDE setups are not currently supported by the installer.

If something behaves strangely, open a GitHub issue and include the host, handheld, desktop session, display setup, and what happened.

## Source, tests, and credits

The source is plain shell and Python and can be inspected directly. The tests in `tests/` are for development and are not needed for a normal installation.

Dual Screen Mode packages together existing tools and community knowledge. It does not replace or claim ownership of Sunshine, Moonlight, KDE, `krfb`, or the guides that informed the setup.

See [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md) and [LICENSE](LICENSE).


