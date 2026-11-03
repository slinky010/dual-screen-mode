# Moonlight setup

Dual Screen Mode prepares the Linux host. Moonlight is installed and paired on
the handheld separately.

## Pair Moonlight with the host

1. Make sure Sunshine is installed and running on the host.
2. Open Moonlight on the handheld.
3. Select the host when it appears.
4. Follow Moonlight and Sunshine's normal pairing prompt and enter the PIN.
5. Start a stream once pairing is complete.

Pairing only needs to be completed once. Dual Screen Mode does not configure the
network, firewall, or pairing. If the host does not appear, confirm that
Sunshine is running and that both devices are on the same local network.

## Use the virtual display

1. Double-click **Dual Screen Mode** on the host.
2. Wait for the virtual display to be ready.
3. Connect with Moonlight and start the stream.
4. Use Moonlight's gamepad mode when you want handheld controls sent to the
   host.

Physical controls are available only when the client device has them. Tablets
and phones can still be used as wireless displays.

When the mode is active, Dual Screen Mode also maps Sunshine's virtual
touchscreen to the virtual display through KWin when Sunshine exposes it. If
touch lands on the host monitor, turn the mode off and on again, then reconnect
Moonlight.

The host must remain in KDE Desktop Mode while the virtual display is active.

Double-click **Dual Screen Mode** again when finished. The virtual display is
removed and temporary audio state is restored. A Moonlight disconnect does not
turn the mode off, so the handheld can reconnect without rebuilding the
display.
