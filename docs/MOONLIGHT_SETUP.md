# Moonlight and Sunshine setup

Dual Screen Mode prepares the host PC. Moonlight is installed and paired on
the handheld separately.

## On the handheld

Install Moonlight using the handheld's normal app store or package source.
On a Steam Deck, this usually means installing it in Desktop Mode through the
Discover app or another source you already trust.

Dual Screen Mode does not install Moonlight on the handheld.

## On the host

The Dual Screen Mode wizard checks for Sunshine. If Sunshine is missing, it can
offer to install the official LizardByte Flathub package. If Sunshine is
already installed, the wizard configures its KDE capture settings but leaves
the normal Sunshine controls under your control.

## Pair the devices

Pairing is a normal Sunshine and Moonlight step:

1. Make sure Sunshine is running on the host.
2. Open Moonlight on the handheld.
3. Use Moonlight's normal host discovery and select the host.
4. Follow the pairing prompt and enter the PIN where Sunshine asks for it.
5. Once paired, launch a Sunshine stream from Moonlight.

The project leaves network discovery and pairing to Moonlight and Sunshine. It
does not configure firewall rules, port forwarding, or automatic pairing. If
Moonlight cannot find the host, first confirm that Sunshine is running and that
both devices are on the same local network.

## Use the virtual display

After pairing:

1. Double-click **Dual Screen Mode** on the host.
2. Wait for the virtual display to be created.
3. Connect with Moonlight and start the Sunshine stream.
4. Use Moonlight's gamepad mode when you want handheld controls sent to the
   host.

The host should expose a virtual output named `Virtual-DualScreen`. A
Moonlight disconnect does not turn the virtual display off, so reconnecting
does not require rebuilding it.

Double-click **Dual Screen Mode** again when finished. The virtual display is
removed and any temporary audio state is restored.
