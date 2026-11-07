# Moonlight setup

Dual Screen Mode prepares the Linux host. Moonlight is installed and paired separately on the handheld.

## On the handheld

1. Install Moonlight from the normal app source for the device.
2. Make sure the handheld and host are on the same local network.
3. Open Moonlight and select the host running Sunshine.
4. If Moonlight shows a PIN, enter that PIN in Sunshine's normal pairing dialog on the host.
5. After pairing, return to Dual Screen Mode and double-click **Dual Screen Mode** on the host.
6. Start the paired host in Moonlight.

When Dual Screen Mode creates the virtual display, it starts centered below the host's main physical display. KDE's Display Configuration can still be used to move it later.

The toggle accepts one action at a time. Rapid duplicate clicks are ignored while it is starting or disabling.

When DSM starts, it refreshes the Flatpak Sunshine session so Sunshine loads
the virtual display target. If Sunshine was already streaming, reconnect
Moonlight after DSM reports that it is ready.

When DSM is disabled, it restores the Sunshine display settings it changed and
returns a Sunshine session that was already running before DSM started.

Dual Screen Mode does not install Moonlight, pair the devices, or change the normal Sunshine pairing process.

## Controls

Enable Moonlight's gamepad mode when you want the handheld's physical controls sent to the host. Start DSM with Cemu closed and wait for the Deck Gyro profile-ready notification before opening Cemu. DSM prepares the complete **Dual Screen Mode Deck Gyro** profile with a **DSMController** DSU entry, updates Cemu to use the discovered Deck IP on port **26760**, and preserves the existing mappings. Once DSM reports that the profile is ready, open Cemu's Input settings and select **Dual Screen Mode Deck Gyro**. No manual IP entry or **Add input API** step is needed. Azahar, melonDS, and other emulator profiles remain under their own control.

Touch routing is handled on the host when Sunshine exposes its virtual touchscreen. The Settings window shows whether the touchscreen is mapped to the virtual second screen or is still waiting to appear. The emulator still needs its own touch or controller configuration.

## Motion

Motion monitoring is a separate local Deck-to-host connection. It is enabled by default and automatically looks for the Deck's DSU service when Dual Screen Mode or Settings starts and no address has been saved. **Find Deck** and manual entry are available if discovery cannot find it.

If an address was saved previously, DSM waits about five seconds for that address to answer before starting the local-network fallback scan.

The DSU motion service on the Deck must already be running. The separate **DSU Motion Probe** can verify the path before you open an emulator. It shows the connected controller and gyro capability, packet health and rate, and live accelerometer and gyroscope readings without controlling the automatic monitor. Its **Calibrate** button only changes the temporary visual reference in that diagnostics window.

When Dual Screen Mode finds a Cemu configuration, starting the mode creates or updates a **Dual Screen Mode Deck Gyro** profile. It preserves Cemu's existing control mapping, adds the Deck's DSU motion entry, updates the DSU host and port, and backs up the previous profile and settings. Select the prepared profile in Cemu after DSM reports that it is ready.

## If the host is not listed

- Confirm Sunshine is installed and running.
- Confirm the handheld and host are on the same local network.
- Check that the host firewall is not blocking Sunshine.
- Complete pairing through Sunshine and Moonlight before troubleshooting Dual Screen Mode.

Dual Screen Mode's own **Motion** status is independent of whether Moonlight is currently streaming. **Connected** confirms that DSM is receiving DSU motion packets from the Deck; it does not confirm emulator input or game behavior.
