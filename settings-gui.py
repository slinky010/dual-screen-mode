#!/usr/bin/env python3

import json
import os
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

os.umask(0o077)


APP_VERSION = "0.1.4-beta"
VIRTUAL_NAME = "DualScreen"
SUNSHINE_APP = "dev.lizardbyte.app.Sunshine"
SETTINGS_FILE = Path.home() / ".config" / "dual-screen-mode" / "settings.conf"
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "dual-screen-mode"
TOGGLE_PATH = Path.home() / ".local" / "bin" / "dual-screen-mode"
UNINSTALL_PATH = Path(__file__).resolve().parent / "uninstall.sh"
ICON_PATHS = (
    Path.home() / ".local" / "share" / "icons" / "dual-screen-mode-settings.png",
    Path.home() / ".local" / "share" / "icons" / "dual-screen-mode.png",
    Path(__file__).resolve().parent / "assets" / "dual-screen-mode.png",
)


class SettingsApp(tk.Tk):
    COLORS = {
        "ink": "#e7eef5",
        "soft": "#9aaaba",
        "navy": "#0b1118",
        "rail": "#182530",
        "paper": "#121b24",
        "card": "#1a2732",
        "card2": "#203241",
        "blue": "#4d91d5",
        "light": "#81bdf3",
        "cyan": "#09d0ed",
        "green": "#5bc7a4",
        "red": "#ed9999",
        "line": "#334554",
    }

    def __init__(self):
        super().__init__()
        self.title("Dual Screen Mode")
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        width = min(1400, max(1000, screen_width - 40))
        height = min(900, max(650, screen_height - 80))
        self.geometry(f"{width}x{height}")
        self.minsize(1000, 680)
        self.resizable(True, True)
        self.configure(bg=self.COLORS["navy"])
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self.settings = self.read_settings()
        self.audio_var = tk.StringVar(value=self.settings.get("audio_mode", "host"))
        self.resolution_var = tk.StringVar(value=self.settings.get("resolution", "1280x800"))
        self.note_var = tk.StringVar(value="Dual Screen Mode is currently off.")
        self.status_var = tk.StringVar(value="Virtual display off")
        self.status_detail_var = tk.StringVar(value="Double-click Dual Screen Mode on the desktop to start it.")
        self.status_badge_var = tk.StringVar(value="OFF")
        self.status_cards = {}
        self.views = {}
        self.nav_buttons = {}

        self.load_icon()
        self.build_shell()
        self.build_status()
        self.build_settings()
        self.build_updates()
        self.build_help()
        self.build_about()
        self.build_uninstall()
        self.show_view("status")
        self.refresh_status()

    def load_icon(self):
        self.icon_image = None
        for path in ICON_PATHS:
            if path.exists():
                try:
                    self.icon_image = tk.PhotoImage(file=str(path))
                    self.iconphoto(True, self.icon_image)
                    return
                except tk.TclError:
                    pass

    def read_settings(self):
        values = {"resolution": "1280x800", "audio_mode": "host"}
        if SETTINGS_FILE.exists():
            for line in SETTINGS_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    key, value = line.split("=", 1)
                    if key in values:
                        values[key] = value.strip()
        if values["audio_mode"] not in {"host", "handheld", "both"}:
            values["audio_mode"] = "host"
        if not self.valid_resolution(values["resolution"]):
            values["resolution"] = "1280x800"
        return values

    @staticmethod
    def valid_resolution(value):
        try:
            width, height = value.split("x", 1)
            return 300 <= int(width) <= 99999 and 300 <= int(height) <= 99999
        except (ValueError, AttributeError):
            return False

    def write_settings(self):
        if not self.valid_resolution(self.resolution_var.get()):
            self.note_var.set("Use a resolution such as 1280x800.")
            return
        directory = SETTINGS_FILE.parent
        directory.mkdir(parents=True, exist_ok=True)
        temporary = SETTINGS_FILE.with_suffix(".tmp")
        temporary.write_text(
            "# Managed by Dual Screen Mode\n"
            f"resolution={self.resolution_var.get()}\n"
            f"audio_mode={self.audio_var.get()}\n",
            encoding="utf-8",
        )
        os.replace(temporary, SETTINGS_FILE)
        self.settings = self.read_settings()
        self.refresh_status()
        self.note_var.set("Settings saved for the next session.")

    def build_shell(self):
        self.rail = tk.Frame(self, bg=self.COLORS["rail"], width=280)
        self.rail.pack(side="left", fill="y")
        self.rail.pack_propagate(False)

        brand = tk.Frame(self.rail, bg=self.COLORS["rail"])
        brand.pack(fill="x", padx=22, pady=(28, 48))
        if self.icon_image:
            small = self.icon_image.subsample(max(1, self.icon_image.width() // 48), max(1, self.icon_image.height() // 48))
            tk.Label(brand, image=small, bg=self.COLORS["paper"], padx=5, pady=5).pack(side="left")
            self.brand_small = small
        else:
            tk.Label(brand, text="▣", bg=self.COLORS["paper"], fg=self.COLORS["cyan"], padx=13, pady=9, font=("TkDefaultFont", 18)).pack(side="left")
        text = tk.Frame(brand, bg=self.COLORS["rail"])
        text.pack(side="left", padx=11)
        tk.Label(text, text="Dual Screen Mode", bg=self.COLORS["rail"], fg="#cce6fa", font=("TkDefaultFont", 12, "bold"), wraplength=145, justify="left").pack(anchor="w")
        tk.Label(text, text="Made by slinky", bg=self.COLORS["rail"], fg="#8799aa", font=("TkDefaultFont", 9)).pack(anchor="w")

        for key, icon, label in (
            ("status", "◉", "Status"),
            ("settings", "⚙", "Settings"),
            ("updates", "↻", "Updates"),
            ("help", "?", "Help"),
            ("about", "ⓘ", "About"),
            ("uninstall", "⌫", "Uninstall"),
        ):
            button = tk.Button(
                self.rail,
                text=f"{icon}    {label}",
                command=lambda view=key: self.show_view(view),
                bg=self.COLORS["rail"],
                fg=self.COLORS["soft"],
                activebackground="#24445d",
                activeforeground=self.COLORS["ink"],
                anchor="w",
                relief="flat",
                bd=0,
                padx=14,
                pady=11,
                font=("TkDefaultFont", 10, "bold"),
                cursor="hand2",
            )
            button.pack(fill="x", pady=3)
            self.nav_buttons[key] = button

        note = tk.Frame(self.rail, bg="#162a3a", highlightbackground="#406071", highlightthickness=1)
        note.pack(fill="x", padx=14, pady=(45, 0))
        tk.Label(note, text="Quick access", bg="#162a3a", fg=self.COLORS["light"], font=("TkDefaultFont", 9, "bold"), anchor="w").pack(fill="x", padx=12, pady=(11, 3))
        tk.Label(note, text="Double-click Dual Screen Mode on the desktop to turn the wireless virtual display on or off.", bg="#162a3a", fg=self.COLORS["soft"], font=("TkDefaultFont", 9), wraplength=205, justify="left", anchor="w").pack(fill="x", padx=12, pady=(0, 12))

        self.workspace = tk.Frame(self, bg=self.COLORS["paper"])
        self.workspace.pack(side="left", fill="both", expand=True)
        header = tk.Frame(self.workspace, bg=self.COLORS["paper"])
        header.pack(fill="x", padx=38, pady=(27, 0))
        tk.Label(header, text="Dual Screen Mode", bg=self.COLORS["paper"], fg=self.COLORS["soft"], font=("TkDefaultFont", 9)).pack(side="left")
        self.host_status = tk.Label(header, text="Host available", bg=self.COLORS["paper"], fg=self.COLORS["green"], font=("TkDefaultFont", 9, "bold"))
        self.host_status.pack(side="right")

        content_shell = tk.Frame(self.workspace, bg=self.COLORS["paper"])
        content_shell.pack(fill="both", expand=True, padx=58, pady=(35, 12))
        self.content_canvas = tk.Canvas(content_shell, bg=self.COLORS["paper"], highlightthickness=0, bd=0)
        self.content_scrollbar = ttk.Scrollbar(content_shell, orient="vertical", command=self.content_canvas.yview)
        self.content_canvas.configure(yscrollcommand=self.content_scrollbar.set)
        self.content_canvas.pack(side="left", fill="both", expand=True)
        self.content = tk.Frame(self.content_canvas, bg=self.COLORS["paper"])
        content_window = self.content_canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", lambda _event: self._update_scrollbar())
        self.content_canvas.bind("<Configure>", lambda event: (self.content_canvas.itemconfigure(content_window, width=event.width), self._update_scrollbar()))
        self.content_canvas.bind_all("<MouseWheel>", self._scroll_content)
        self.content_canvas.bind_all("<Button-4>", self._scroll_content)
        self.content_canvas.bind_all("<Button-5>", self._scroll_content)
        footer = tk.Frame(self.workspace, bg=self.COLORS["paper"], highlightbackground=self.COLORS["line"], highlightthickness=1)
        footer.pack(fill="x", side="bottom")
        tk.Label(footer, textvariable=self.note_var, bg=self.COLORS["paper"], fg=self.COLORS["soft"], font=("TkDefaultFont", 9), anchor="w").pack(side="left", padx=38, pady=17)
        self.footer_buttons = tk.Frame(footer, bg=self.COLORS["paper"])
        self.footer_buttons.pack(side="right", padx=30, pady=12)
        self.save_button = tk.Button(self.footer_buttons, text="Save settings", command=self.write_settings, bg=self.COLORS["blue"], fg="#fff", activebackground=self.COLORS["light"], relief="flat", bd=0, padx=16, pady=10, font=("TkDefaultFont", 10, "bold"), cursor="hand2")
        self.save_button.pack_forget()

    def _update_scrollbar(self):
        self.after_idle(self._set_scrollbar_visibility)

    def _set_scrollbar_visibility(self):
        bbox = self.content_canvas.bbox("all")
        if not bbox:
            return
        self.content_canvas.configure(scrollregion=bbox)
        content_height = bbox[3] - bbox[1]
        viewport_height = self.content_canvas.winfo_height()
        needs_scroll = content_height > viewport_height + 2
        is_visible = self.content_scrollbar.winfo_manager() == "pack"
        if needs_scroll and not is_visible:
            self.content_scrollbar.pack(side="right", fill="y")
        elif not needs_scroll and is_visible:
            self.content_scrollbar.pack_forget()

    def new_view(self, key):
        frame = tk.Frame(self.content, bg=self.COLORS["paper"])
        self.views[key] = frame
        return frame

    def _scroll_content(self, event):
        if not self.content_canvas.winfo_ismapped():
            return
        if getattr(event, "num", None) == 4:
            self.content_canvas.yview_scroll(-3, "units")
        elif getattr(event, "num", None) == 5:
            self.content_canvas.yview_scroll(3, "units")
        elif getattr(event, "delta", 0):
            self.content_canvas.yview_scroll(-int(event.delta / 120), "units")

    def heading(self, parent, title, detail):
        tk.Label(parent, text=title, bg=self.COLORS["paper"], fg=self.COLORS["ink"], font=("TkDefaultFont", 25, "bold"), anchor="w").pack(anchor="w")
        tk.Label(parent, text=detail, bg=self.COLORS["paper"], fg=self.COLORS["soft"], font=("TkDefaultFont", 11), wraplength=690, justify="left", anchor="w").pack(anchor="w", pady=(10, 25))

    def card(self, parent, title, detail, column=0, row=0, wide=False):
        frame = tk.Frame(parent, bg=self.COLORS["card"], highlightbackground=self.COLORS["line"], highlightthickness=1)
        frame.grid(column=column, row=row, columnspan=2 if wide else 1, sticky="nsew", padx=6, pady=6)
        tk.Label(frame, text=title, bg=self.COLORS["card"], fg=self.COLORS["light"], font=("TkDefaultFont", 11, "bold"), anchor="w").pack(fill="x", padx=18, pady=(16, 0))
        tk.Label(frame, text=detail, bg=self.COLORS["card"], fg=self.COLORS["soft"], font=("TkDefaultFont", 10), wraplength=310 if not wide else 650, justify="left", anchor="w").pack(fill="x", padx=18, pady=(6, 16))
        return frame

    def build_status(self):
        page = self.new_view("status")
        self.heading(page, "Status", "This shows the current state of Dual Screen Mode.")
        state = tk.Frame(page, bg="#163041", highlightbackground="#47728a", highlightthickness=1)
        state.pack(fill="x", pady=(0, 14))
        left = tk.Frame(state, bg="#163041")
        left.pack(side="left", fill="both", expand=True, padx=20, pady=17)
        tk.Label(left, textvariable=self.status_var, bg="#163041", fg=self.COLORS["light"], font=("TkDefaultFont", 12, "bold"), anchor="w").pack(anchor="w")
        tk.Label(left, textvariable=self.status_detail_var, bg="#163041", fg=self.COLORS["soft"], font=("TkDefaultFont", 9), anchor="w").pack(anchor="w", pady=(4, 0))
        tk.Label(state, textvariable=self.status_badge_var, bg="#536372", fg="#dce8f0", font=("TkDefaultFont", 8, "bold"), padx=11, pady=6).pack(side="right", padx=20)
        grid = tk.Frame(page, bg=self.COLORS["paper"])
        grid.pack(fill="x")
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)
        self.status_cards["display"] = self.card(grid, "Virtual display", "", 0, 0)
        self.status_cards["audio"] = self.card(grid, "Audio", "", 1, 0)
        self.status_cards["touch"] = self.card(grid, "Touch routing", "", 0, 1)
        self.status_cards["sunshine"] = self.card(grid, "Sunshine", "", 1, 1)
        self.status_refresh = tk.Button(page, text="Refresh status", command=self.refresh_status, bg=self.COLORS["card2"], fg=self.COLORS["ink"], activebackground="#24445d", relief="flat", bd=0, padx=13, pady=8, font=("TkDefaultFont", 8, "bold"), cursor="hand2")
        self.status_refresh.pack(anchor="e", pady=(18, 0))

    def set_card_detail(self, key, detail):
        frame = self.status_cards[key]
        labels = [widget for widget in frame.winfo_children() if isinstance(widget, tk.Label)]
        if len(labels) > 1:
            labels[1].configure(text=detail)

    def build_settings(self):
        page = self.new_view("settings")
        self.heading(page, "Settings", "Choose the display and audio options used the next time Dual Screen Mode starts.")
        grid = tk.Frame(page, bg=self.COLORS["paper"])
        grid.pack(fill="x")
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)
        display = tk.Frame(grid, bg=self.COLORS["card"], highlightbackground=self.COLORS["line"], highlightthickness=1)
        display.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        tk.Label(display, text="Display size", bg=self.COLORS["card"], fg=self.COLORS["light"], font=("TkDefaultFont", 11, "bold"), anchor="w").pack(fill="x", padx=18, pady=(16, 0))
        tk.Label(display, text="Choose the resolution that matches the handheld screen.", bg=self.COLORS["card"], fg=self.COLORS["soft"], font=("TkDefaultFont", 9), wraplength=280, justify="left", anchor="w").pack(fill="x", padx=18, pady=(6, 12))
        self.resolution_combo = ttk.Combobox(display, textvariable=self.resolution_var, values=("1280x800", "1280x720", "1920x1080", "1920x1200"), state="readonly", width=17)
        self.resolution_combo.pack(anchor="w", padx=18, pady=(0, 18))
        audio = tk.Frame(grid, bg=self.COLORS["card"], highlightbackground=self.COLORS["line"], highlightthickness=1)
        audio.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)
        tk.Label(audio, text="Audio", bg=self.COLORS["card"], fg=self.COLORS["light"], font=("TkDefaultFont", 11, "bold"), anchor="w").pack(fill="x", padx=18, pady=(16, 0))
        tk.Label(audio, text="Choose where audio plays during a session.", bg=self.COLORS["card"], fg=self.COLORS["soft"], font=("TkDefaultFont", 9), wraplength=280, justify="left", anchor="w").pack(fill="x", padx=18, pady=(6, 12))
        choices = tk.Frame(audio, bg=self.COLORS["card"])
        choices.pack(fill="x", padx=18, pady=(0, 18))
        self.audio_buttons = {}
        for key, label in (("host", "Host"), ("handheld", "Handheld"), ("both", "Both (work in progress)")):
            button = tk.Button(choices, text=label, command=lambda value=key: self.select_audio(value), bg=self.COLORS["card2"], fg=self.COLORS["soft"], activebackground="#24445d", activeforeground="#fff", relief="flat", bd=0, padx=9, pady=9, font=("TkDefaultFont", 9, "bold"), cursor="hand2")
            button.pack(side="left", fill="x", expand=True, padx=2)
            self.audio_buttons[key] = button
        details = tk.Frame(grid, bg=self.COLORS["card"], highlightbackground=self.COLORS["line"], highlightthickness=1)
        details.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=6, pady=6)
        self.audio_behavior_var = tk.StringVar()
        self.audio_restore_var = tk.StringVar(value="The saved Sunshine setting, volume, and mute state are restored when the mode turns off.")
        self.audio_not_changed_var = tk.StringVar(value="The default output is not changed. No audio driver, blank audio device, or virtual audio device is created. Other outputs are not altered.")
        self.audio_pipewire_var = tk.StringVar(value="On PipeWire, the toggle uses the existing PulseAudio compatibility interface. If the host output cannot be muted automatically, it is left unchanged and a warning is shown.")
        for title, variable in (("Selected option", self.audio_behavior_var), ("Saved and restored", self.audio_restore_var), ("Not changed", self.audio_not_changed_var), ("PipeWire and fallback", self.audio_pipewire_var)):
            row = tk.Frame(details, bg=self.COLORS["card"])
            row.pack(fill="x", padx=18, pady=(12, 0))
            tk.Label(row, text=title, bg=self.COLORS["card"], fg=self.COLORS["light"], font=("TkDefaultFont", 10, "bold"), anchor="nw", width=19).pack(side="left", anchor="nw")
            tk.Label(row, textvariable=variable, bg=self.COLORS["card"], fg=self.COLORS["soft"], font=("TkDefaultFont", 10), wraplength=650, justify="left", anchor="nw").pack(side="left", fill="x", expand=True)
        tk.Frame(details, bg=self.COLORS["card"], height=12).pack()
        self.select_audio(self.audio_var.get())

    def select_audio(self, value):
        self.audio_var.set(value)
        for key, button in self.audio_buttons.items():
            button.configure(bg="#24445d" if key == value else self.COLORS["card2"], fg="#fff" if key == value else self.COLORS["soft"])
        if hasattr(self, "audio_behavior_var"):
            self.audio_behavior_var.set({
                "host": "Sunshine audio streaming is disabled. Audio stays on the host.",
                "handheld": "Sunshine audio streaming is enabled. The host's current default output is muted for the session.",
                "both": "Both is work in progress. For now, it uses Handheld behavior: Sunshine audio streaming is enabled and the host's current default output is muted for the session.",
            }[value])

    def build_updates(self):
        page = self.new_view("updates")
        self.heading(page, "Updates", "Update support is still being built.")
        grid = tk.Frame(page, bg=self.COLORS["paper"])
        grid.pack(fill="x")
        grid.grid_columnconfigure(0, weight=1)
        self.card(grid, "Current version", f"Dual Screen Mode {APP_VERSION} is installed.", wide=True)
        self.card(grid, "Work in progress", "This page does not contact a server or check for updates yet. When a public release source is ready, it will show how to update here.", wide=True, row=1)

    def build_help(self):
        page = self.new_view("help")
        self.heading(page, "Help", "Useful checks when something does not look right.")
        grid = tk.Frame(page, bg=self.COLORS["paper"])
        grid.pack(fill="x")
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)
        self.card(grid, "Start or stop the mode", "Double-click Dual Screen Mode on the desktop. A Moonlight disconnect does not turn the mode off, so you can reconnect without recreating the display.", 0, 0)
        self.card(grid, "Check Moonlight", "The handheld connects to Sunshine over the same local network. Moonlight is installed separately on the handheld.", 1, 0)
        self.card(grid, "If the picture is tiny", "Match the saved display size to the handheld and check Moonlight's stream resolution and scaling settings.", 0, 1)
        self.card(grid, "If a game does not respond", "Moonlight sends the handheld's controls to the host. Game and emulator input setup is outside Dual Screen Mode.", 1, 1)
        self.card(grid, "If touch hits the wrong screen", "Turn Dual Screen Mode off and on again. The toggle maps Sunshine's virtual touchscreen to Virtual-DualScreen when it appears.", 0, 2)
        self.card(grid, "What the mode changes", "It creates a KDE virtual display, maps Sunshine's virtual touchscreen to that display when KWin exposes it, and changes Sunshine's capture and audio-stream settings. Handheld mode may mute the current default output for the session. It does not change the default output, install a driver, create a blank or virtual audio device, or alter other outputs. Saved audio values are restored when the mode turns off. Temporary startup logs are kept in the Dual Screen Mode runtime folder.", wide=True, row=3)
        actions = tk.Frame(page, bg=self.COLORS["paper"])
        actions.pack(fill="x", pady=(18, 0))
        tk.Button(actions, text="Open Sunshine log", command=self.open_sunshine_log, bg=self.COLORS["card2"], fg=self.COLORS["ink"], activebackground="#24445d", relief="flat", bd=0, padx=13, pady=8, font=("TkDefaultFont", 8, "bold"), cursor="hand2").pack(side="left", padx=(0, 8))
        tk.Button(actions, text="Copy diagnostic details", command=self.copy_diagnostics, bg=self.COLORS["card2"], fg=self.COLORS["ink"], activebackground="#24445d", relief="flat", bd=0, padx=13, pady=8, font=("TkDefaultFont", 8, "bold"), cursor="hand2").pack(side="left")

    @property
    def sunshine_log_path(self):
        return Path.home() / ".var" / "app" / SUNSHINE_APP / "config" / "sunshine" / "sunshine.log"

    def open_sunshine_log(self):
        path = self.sunshine_log_path
        if not path.exists():
            messagebox.showinfo("Sunshine log", f"The Sunshine log does not exist yet.\n\nExpected location:\n{path}")
            return
        try:
            subprocess.Popen(["xdg-open", str(path)])
            self.note_var.set("Opened the Sunshine log.")
        except (OSError, subprocess.SubprocessError) as exc:
            messagebox.showerror("Sunshine log", f"Could not open the log.\n\n{exc}\n\n{path}")

    def copy_diagnostics(self):
        marked_active = (RUNTIME_DIR / "active").exists()
        display_present = self.virtual_display_present()
        active = marked_active and (display_present is not False)
        details = "\n".join(
            (
                f"Dual Screen Mode {APP_VERSION}",
                f"Virtual display: {'active' if active else 'off'}",
                f"Saved resolution: {self.settings.get('resolution', '1280x800')}",
                f"Audio mode: {self.settings.get('audio_mode', 'host')}",
                f"Touch routing: {self.touch_status()}",
                f"Sunshine: {self.sunshine_status()}",
                f"Sunshine log: {self.sunshine_log_path}",
                f"Settings: {SETTINGS_FILE}",
            )
        )
        self.clipboard_clear()
        self.clipboard_append(details)
        self.update()
        self.note_var.set("Diagnostic details copied to the clipboard.")

    def build_about(self):
        page = self.new_view("about")
        self.heading(page, "About Dual Screen Mode", "A simple way to use a handheld as a wireless Wii U GamePad or DS style second screen.")
        grid = tk.Frame(page, bg=self.COLORS["paper"])
        grid.pack(fill="x")
        grid.grid_columnconfigure(0, weight=1)
        self.card(grid, "What this project does", "Dual Screen Mode brings together the pieces needed to create a virtual display, stream it over your local network, and use a handheld alongside the host computer.", wide=True)
        self.card(grid, "How it came together", "This project collects existing tools, guides, and configuration steps into one repeatable setup that is easier to install and share.", wide=True, row=1)
        self.card(grid, "Built with", "KDE Plasma and krfb virtual display\nKWin input routing for Sunshine's virtual touchscreen\nSunshine for host streaming\nMoonlight for the handheld connection", wide=True, row=2)
        self.card(grid, "Credits and license", "Made by slinky. Dual Screen Mode is released under the MIT License and credits the tools and community guides that make the setup possible.", wide=True, row=3)

    def build_uninstall(self):
        page = self.new_view("uninstall")
        self.heading(page, "Uninstall Dual Screen Mode", "Remove the shortcuts and settings created by Dual Screen Mode.")
        frame = tk.Frame(page, bg=self.COLORS["card"], highlightbackground="#8f5a65", highlightthickness=1)
        frame.pack(fill="x", pady=6)
        tk.Label(frame, text="Remove the setup", bg=self.COLORS["card"], fg=self.COLORS["red"], font=("TkDefaultFont", 10, "bold"), anchor="w").pack(fill="x", padx=18, pady=(16, 0))
        tk.Label(frame, text="Your existing streaming tools remain available.", bg=self.COLORS["card"], fg=self.COLORS["soft"], font=("TkDefaultFont", 9), anchor="w").pack(fill="x", padx=18, pady=(6, 14))
        tk.Button(frame, text="Uninstall Dual Screen Mode", command=self.request_uninstall, bg=self.COLORS["blue"], fg="#fff", activebackground=self.COLORS["light"], relief="flat", bd=0, padx=15, pady=9, font=("TkDefaultFont", 9, "bold"), cursor="hand2").pack(anchor="w", padx=18, pady=(0, 18))

    def show_view(self, key):
        for name, frame in self.views.items():
            frame.pack_forget()
            self.nav_buttons[name].configure(bg=self.COLORS["rail"], fg=self.COLORS["soft"])
        self.views[key].pack(fill="both", expand=True)
        self.content_canvas.yview_moveto(0)
        self.nav_buttons[key].configure(bg="#24445d", fg=self.COLORS["ink"])
        self.save_button.pack_forget()
        if key == "settings":
            self.save_button.pack(side="right")
            self.note_var.set("Changes are saved for the next session.")
        elif key == "status":
            self.note_var.set("Dual Screen Mode is currently off.")
        else:
            self.note_var.set("Dual Screen Mode management")
        if key == "status":
            self.refresh_status()

    def refresh_status(self):
        marked_active = (RUNTIME_DIR / "active").exists()
        display_present = self.virtual_display_present()
        active = marked_active and (display_present is not False)
        if active:
            self.status_var.set("Virtual display active")
            self.status_detail_var.set("Connect your handheld with Moonlight.")
            self.status_badge_var.set("ON")
            self.note_var.set("Dual Screen Mode is currently active.")
        elif marked_active and display_present is False:
            self.status_var.set("Virtual display needs recovery")
            self.status_detail_var.set("KDE no longer reports the virtual display. Double-click the toggle to reset the mode.")
            self.status_badge_var.set("CHECK")
            self.note_var.set("The mode marker is active, but the virtual display is missing.")
        else:
            self.status_var.set("Virtual display off")
            self.status_detail_var.set("Double-click Dual Screen Mode on the desktop to start it.")
            self.status_badge_var.set("OFF")
            self.note_var.set("Dual Screen Mode is currently off.")
        display = f"{'Active' if active else 'Off'}\nSize: {self.settings.get('resolution', '1280x800').replace('x', ' × ')}"
        audio_labels = {"host": "Host", "handheld": "Handheld", "both": "Both (work in progress)"}
        audio = f"Destination: {audio_labels.get(self.settings.get('audio_mode', 'host'), 'Host')}"
        sunshine = self.sunshine_status()
        self.set_card_detail("display", display)
        self.set_card_detail("audio", audio)
        self.set_card_detail("touch", self.touch_status())
        self.set_card_detail("sunshine", sunshine)

    @staticmethod
    def virtual_display_present():
        try:
            result = subprocess.run(["kscreen-doctor", "-j"], capture_output=True, text=True, timeout=3)
            if result.returncode != 0:
                return None
            return '"name": "Virtual-DualScreen"' in result.stdout
        except (OSError, subprocess.SubprocessError):
            return None

    @staticmethod
    def sunshine_status():
        try:
            result = subprocess.run(["flatpak", "ps", "--app", "--columns=application"], capture_output=True, text=True, timeout=3)
            if SUNSHINE_APP in result.stdout:
                return "Running"
        except (OSError, subprocess.SubprocessError):
            pass
        try:
            installed = subprocess.run(["flatpak", "info", SUNSHINE_APP], capture_output=True, timeout=3)
            if installed.returncode == 0:
                return "Installed"
        except (OSError, subprocess.SubprocessError):
            pass
        return "Not installed"

    @staticmethod
    def touch_status():
        if not (RUNTIME_DIR / "active").exists():
            return "Off until the mode starts"
        try:
            status = (RUNTIME_DIR / "touch-status").read_text(encoding="utf-8").strip()
        except OSError:
            status = ""
        return {
            "mapped": "Mapped to Virtual-DualScreen",
            "waiting": "Waiting for Sunshine's virtual touchscreen",
            "unavailable": "KWin D-Bus tool not found",
            "warning": "Could not map the virtual touchscreen",
        }.get(status, "Waiting for Sunshine's virtual touchscreen")

    def set_card_detail(self, key, detail):
        frame = self.status_cards.get(key)
        if not frame:
            return
        labels = [widget for widget in frame.winfo_children() if isinstance(widget, tk.Label)]
        if len(labels) > 1:
            labels[1].configure(text=detail)

    def request_uninstall(self):
        if not UNINSTALL_PATH.exists():
            messagebox.showerror("Dual Screen Mode", "The uninstall helper was not found.")
            return
        confirmed = messagebox.askyesno(
            "Uninstall Dual Screen Mode",
            "Remove Dual Screen Mode's shortcuts and settings?\n\nSunshine, Moonlight, krfb, and your backups will remain installed.",
        )
        if not confirmed:
            return
        result = subprocess.run(["bash", str(UNINSTALL_PATH), "--execute"], capture_output=True, text=True)
        if result.returncode == 0:
            messagebox.showinfo("Dual Screen Mode", "Dual Screen Mode was uninstalled.")
            self.destroy()
        else:
            messagebox.showerror("Dual Screen Mode", "The uninstall did not finish.\n\n" + (result.stderr.strip() or result.stdout.strip()))

    def show_toast(self, message):
        self.note_var.set(message)


if __name__ == "__main__":
    SettingsApp().mainloop()
