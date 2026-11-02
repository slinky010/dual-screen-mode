# Reddit post draft

## Suggested title

I made a little setup wizard for using a Steam Deck as a wireless Wii U GamePad on Linux

## Post

I've been messing around with my Steam Machine and Steam Deck and wanted to
use the Deck as a second screen and controller for Cemu and Azahar. Basically,
I wanted the Wii U GamePad experience, or something like the bottom screen of a
DS or 3DS, but using the stuff I already had.

The funny thing is that the setup itself already existed. KDE can create the
virtual display, Sunshine can stream it, and Moonlight can connect to it. The
problem was that getting all of those pieces working together involved a bunch
of different guides and terminal commands.

Once I finally got it working, I realized I just hated having to open Konsole
every time I wanted to use it. I wanted to play a game, not run a command, wait
for a display to appear, check whether Sunshine was looking at the right one,
and then figure out how to clean it all up afterward.

So I made Dual Screen Mode. It is basically a small setup wizard and desktop
toggle that packages the existing setup into something easier to repeat. It
creates the KDE virtual display, configures Sunshine to capture it, remembers
the display size and audio choice, and gives you a shortcut to turn it on and
off.

It is literally a wireless second monitor. A little while ago I was watching a
YouTube video and dragged the window over to the Steam Deck just to see if it
would work. It did. That was pretty cool, because it stopped feeling like a
weird emulator experiment and started feeling like I had actually added another
monitor to my setup.

The important thing is that I am not claiming to have invented the underlying
technology. Sunshine, Moonlight, KDE, and the virtual-display tools are doing
the real work. I just collected the parts that were scattered across different
guides and made the setup repeatable, with a simple click-on and click-off flow.

Moonlight still needs to be installed separately on the Steam Deck or other
handheld, and pairing Moonlight with Sunshine is still done manually through
their normal pairing process. Dual Screen Mode handles the Linux host setup. It
does not configure the network or automatically pair anything.

I have tested it with my Steam Machine and Steam Deck. It is still an early
beta, and the current target is SteamOS or another Arch-based Linux setup using
KDE Plasma on Wayland. Cemu and Azahar controller profiles still need to be set
up separately. Gyro and microphone support are not included right now.

The project is here:

GitHub: https://github.com/slinky010/dual-screen-mode

I mostly made this because I was tired of doing the manual setup myself, but I
figured other people might want the same kind of thing. If anyone tries it on a
different KDE Wayland setup, I would be interested to hear how it goes.
