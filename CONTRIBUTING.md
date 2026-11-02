# Contributing to Dual Screen Mode

Dual Screen Mode is a small, inspectable packaging project. Contributions are
welcome when they make the setup clearer, safer, or more consistent on KDE
Plasma Wayland hosts.

## Before opening an issue

Please include:

- Linux distribution and version
- KDE Plasma version
- Wayland or X11 session type
- Whether the host is a Steam Machine, Steam Deck, or another PC
- The Moonlight client device
- The step or shortcut that failed
- The relevant log or terminal output, with personal paths and other private
  information removed when appropriate

Do not include passwords, pairing PINs, public IP addresses, or private network
details in an issue.

## Local checks

Run these from the project directory:

```bash
bash tests/test-syntax.sh
bash tests/test-toggle.sh
bash tests/test-setup-execute.sh
```

The tests use temporary directories and fake host commands. They do not install
packages, change the real Sunshine configuration, or alter real displays.

## Project rules

- Keep the installer readable in plain text.
- Do not add telemetry, advertising, bundled software, background services, or
  arbitrary remote scripts.
- Do not add a `curl | bash` install path.
- Keep uninstall limited to files and settings owned by Dual Screen Mode.
- Explain audio, display, permission, and network behavior in user-facing copy.
- Update `CHANGELOG.md` when behavior changes.
- Keep the Moonlight client setup manual and clearly documented.

## Pull requests

Keep changes focused. Include the reason for the change, the host environment
used for testing, and the commands that passed. A live SteamOS and KDE test is
especially useful for display, Sunshine, audio, and launcher changes.
