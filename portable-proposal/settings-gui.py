#!/usr/bin/env python3

import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from motion_discovery import discover_motion_hosts
from motion_probe.dsu_motion_probe import DsuClient
import update_support

os.umask(0o077)


APP_VERSION = "0.1.5-beta"
VIRTUAL_NAME = "DualScreen"
SUNSHINE_APP = "dev.lizardbyte.app.Sunshine"
SETTINGS_FILE = Path.home() / ".config" / "dual-screen-mode" / "settings.conf"
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "dual-screen-mode"
TOGGLE_PATH = Path.home() / ".local" / "bin" / "dual-screen-mode"
UNINSTALL_PATH = Path(__file__).resolve().parent / "uninstall.sh"
MOTION_MONITOR_PATH = Path(__file__).resolve().parent / "motion_monitor.py"
MOTION_PROBE_PATH = Path(__file__).resolve().parent / "motion_probe" / "dsu_motion_probe.py"
MOTION_STATUS_FILE = RUNTIME_DIR / "motion-status"
MOTION_PID_FILE = RUNTIME_DIR / "motion-monitor.pid"
MOTION_CHOICE_MARKER = Path.home() / ".local" / "state" / "dual-screen-mode" / "motion-choice"
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
        self.protocol("WM_DELETE_WINDOW", self.close_app)

        self.settings = self.read_settings()
        self.audio_var = tk.StringVar(value=self.settings.get("audio_mode", "host"))
        self.resolution_var = tk.StringVar(value=self.settings.get("resolution", "1280x800"))
        self.motion_enabled_var = tk.BooleanVar(value=self.settings.get("motion_enabled", "1") == "1")
        self.motion_host_var = tk.StringVar(value=self.settings.get("motion_host", ""))
        self.motion_port_var = tk.StringVar(value=self.settings.get("motion_port", "26760"))
        self.motion_slot_var = tk.StringVar(value=self.settings.get("motion_slot", "0"))
        self.motion_status_var = tk.StringVar(value="Motion is enabled by default. Settings will look for your Steam Deck automatically while it is open.")
        self.motion_discovery_var = tk.StringVar(value="")
        self.motion_discovery_running = False
        self.settings_motion_client = None
        self.settings_motion_events = None
        self.settings_motion_target = None
        self.settings_motion_started = 0.0
        self.settings_motion_last_motion = None
        self.settings_motion_last_error = ""
        self.update_release = None
        self.update_check_running = False
        self.update_download_running = False
        self.note_var = tk.StringVar(value="Dual Screen Mode is currently disabled.")
        self.status_var = tk.StringVar(value="Virtual display disabled")
        self.status_detail_var = tk.StringVar(value="Double-click Dual Screen Mode on the desktop to enable it.")
        self.status_badge_var = tk.StringVar(value="DISABLED")
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
        # If the mode was already active before Settings opened, make sure the
        # automatic monitor is reconciled with the saved endpoint now.
        self.sync_motion_monitor()
        self.refresh_status()
        # Keep all live status cards on the same refresh cycle. The background
        # touch watcher and motion monitor both write their state independently,
        # so Settings needs to reread them together instead of refreshing only
        # the motion card.
        self.after(1000, self.poll_status)
        self.after(500, self.auto_discover_motion_host)

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
        values = {
            "resolution": "1280x800",
            "audio_mode": "host",
            "motion_enabled": "1",
            "motion_host": "",
            "motion_port": "26760",
            "motion_slot": "0",
        }
        try:
            settings_text = SETTINGS_FILE.read_text(encoding="utf-8", errors="replace")
        except OSError:
            settings_text = ""
        for line in settings_text.splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                if key in values:
                    values[key] = value.strip()
        if values["audio_mode"] not in {"host", "handheld", "both"}:
            values["audio_mode"] = "host"
        if not self.valid_resolution(values["resolution"]):
            values["resolution"] = "1280x800"
        if values["motion_enabled"] not in {"0", "1"}:
            values["motion_enabled"] = "1"
        values["motion_host"] = values["motion_host"].strip()
        if values["motion_host"] and not self.valid_motion_host(values["motion_host"]):
            values["motion_host"] = ""
        if not self.valid_motion_port(values["motion_port"]):
            values["motion_port"] = "26760"
        if not self.valid_motion_slot(values["motion_slot"]):
            values["motion_slot"] = "0"
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
        previous_motion_target = self.motion_target(self.settings)
        motion_host = self.motion_host_var.get().strip()
        motion_port = self.motion_port_var.get().strip()
        motion_slot = self.motion_slot_var.get().strip()
        if motion_host and not self.valid_motion_host(motion_host):
            self.note_var.set("Use the Deck's IP address or a hostname without spaces.")
            return
        if not self.valid_motion_port(motion_port):
            self.note_var.set("Use a motion port from 1 to 65535. The default is 26760.")
            return
        if not self.valid_motion_slot(motion_slot):
            self.note_var.set("Use a controller slot from 0 to 3.")
            return
        directory = SETTINGS_FILE.parent
        directory.mkdir(parents=True, exist_ok=True)
        temporary = SETTINGS_FILE.with_suffix(".tmp")
        temporary.write_text(
            "# Managed by Dual Screen Mode\n"
            f"resolution={self.resolution_var.get()}\n"
            f"audio_mode={self.audio_var.get()}\n"
            f"motion_enabled={1 if self.motion_enabled_var.get() else 0}\n"
            f"motion_host={motion_host}\n"
            f"motion_port={motion_port}\n"
            f"motion_slot={motion_slot}\n",
            encoding="utf-8",
        )
        os.replace(temporary, SETTINGS_FILE)
        MOTION_CHOICE_MARKER.parent.mkdir(parents=True, exist_ok=True)
        MOTION_CHOICE_MARKER.write_text("user-configured\n", encoding="utf-8")
        self.settings = self.read_settings()
        current_motion_target = self.motion_target(self.settings)
        if current_motion_target != previous_motion_target:
            # Replace any checker or monitor that still has the old endpoint.
            # Otherwise the window can keep reporting the previous target
            # until Settings is closed and opened again.
            self.stop_settings_motion_check()
            self.stop_motion_monitor()
            try:
                MOTION_STATUS_FILE.unlink()
            except OSError:
                pass
        self.sync_motion_monitor()
        self.refresh_live_status()
        if self.motion_enabled_var.get() and not motion_host:
            self.note_var.set("Settings saved. Dual Screen Mode will look for your Steam Deck automatically.")
            self.discover_motion_host(auto=True)
        else:
            self.note_var.set("Settings saved. Motion changes apply to the current session when the mode is active.")

    @staticmethod
    def valid_motion_host(value):
        value = str(value).strip()
        return bool(value) and len(value) <= 253 and not any(character.isspace() for character in value)

    @staticmethod
    def valid_motion_port(value):
        try:
            return 1 <= int(str(value).strip()) <= 65535
        except (TypeError, ValueError):
            return False

    @staticmethod
    def valid_motion_slot(value):
        try:
            return int(str(value).strip()) in range(4)
        except (TypeError, ValueError):
            return False

    @staticmethod
    def motion_target(settings):
        return (
            settings.get("motion_enabled", "1"),
            settings.get("motion_host", ""),
            settings.get("motion_port", "26760"),
            settings.get("motion_slot", "0"),
        )

    def motion_form_matches(self, settings):
        return (
            self.motion_enabled_var.get() == (settings.get("motion_enabled", "0") == "1")
            and self.motion_host_var.get().strip() == settings.get("motion_host", "")
            and self.motion_port_var.get().strip() == settings.get("motion_port", "26760")
            and self.motion_slot_var.get().strip() == settings.get("motion_slot", "0")
        )

    def sync_saved_settings(self):
        saved = self.read_settings()
        if saved == self.settings:
            return
        previous = self.settings
        form_matches_previous = self.motion_form_matches(previous)
        motion_target_changed = self.motion_target(saved) != self.motion_target(previous)
        self.settings = saved
        if form_matches_previous:
            self.resolution_var.set(saved.get("resolution", "1280x800"))
            self.audio_var.set(saved.get("audio_mode", "host"))
            self.motion_enabled_var.set(saved.get("motion_enabled", "1") == "1")
            self.motion_host_var.set(saved.get("motion_host", ""))
            self.motion_port_var.set(saved.get("motion_port", "26760"))
            self.motion_slot_var.set(saved.get("motion_slot", "0"))
            self.select_audio(self.audio_var.get())
        if motion_target_changed:
            self.stop_settings_motion_check()
            self.stop_motion_monitor()
            try:
                MOTION_STATUS_FILE.unlink()
            except OSError:
                pass
            self.sync_motion_monitor()

    def build_shell(self):
        self.rail = tk.Frame(self, bg=self.COLORS["rail"], width=320)
        self.rail.pack(side="left", fill="y")
        self.rail.pack_propagate(False)

        brand = tk.Frame(self.rail, bg=self.COLORS["rail"])
        brand.pack(fill="x", padx=22, pady=(28, 48))
        if self.icon_image:
            small = self.icon_image.subsample(max(1, self.icon_image.width() // 100), max(1, self.icon_image.height() // 100))
            tk.Label(brand, image=small, bg=self.COLORS["rail"], borderwidth=0, highlightthickness=0, padx=0, pady=0).pack(side="left")
            self.brand_small = small
        else:
            tk.Label(brand, text="D", bg=self.COLORS["rail"], fg=self.COLORS["cyan"], padx=13, pady=9, font=("TkDefaultFont", 18, "bold")).pack(side="left")
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
        tk.Label(note, text="Double-click Dual Screen Mode on the desktop to enable or disable the wireless virtual display.", bg="#162a3a", fg=self.COLORS["soft"], font=("TkDefaultFont", 9), wraplength=205, justify="left", anchor="w").pack(fill="x", padx=12, pady=(0, 12))

        self.workspace = tk.Frame(self, bg=self.COLORS["paper"])
        self.workspace.pack(side="left", fill="both", expand=True)
        header = tk.Frame(self.workspace, bg=self.COLORS["paper"])
        header.pack(fill="x", padx=38, pady=(27, 0))
        tk.Label(header, text="Dual Screen Mode", bg=self.COLORS["paper"], fg=self.COLORS["soft"], font=("TkDefaultFont", 9)).pack(side="left")
        self.host_status = tk.Label(header, text="Mode disabled", bg=self.COLORS["paper"], fg=self.COLORS["soft"], font=("TkDefaultFont", 9, "bold"))
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
        self.status_cards["motion"] = self.card(grid, "Motion / gyro", "", 0, 2, wide=True)
        self.status_refresh = tk.Button(page, text="Refresh status", command=self.refresh_live_status, bg=self.COLORS["card2"], fg=self.COLORS["ink"], activebackground="#24445d", relief="flat", bd=0, padx=13, pady=8, font=("TkDefaultFont", 8, "bold"), cursor="hand2")
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
        motion = tk.Frame(grid, bg=self.COLORS["card"], highlightbackground=self.COLORS["line"], highlightthickness=1)
        motion.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=6, pady=6)
        tk.Label(motion, text="Motion / gyro", bg=self.COLORS["card"], fg=self.COLORS["light"], font=("TkDefaultFont", 11, "bold"), anchor="w").pack(fill="x", padx=18, pady=(16, 0))
        tk.Label(motion, text="Motion is enabled by default. Settings checks the Deck connection while this app is open, and Dual Screen Mode keeps its own connection active during a session. When a Cemu configuration is found, keep Cemu closed while the next mode start prepares the complete Deck Gyro profile, updates Cemu's saved DSU address, and preserves the existing controls. Wait for DSM's profile-ready notification before opening Cemu, then select Dual Screen Mode Deck Gyro in Cemu Input settings. No manual IP or Add input API step is needed. The separate diagnostics window can test the same path and temporarily calibrate its visual gravity view.", bg=self.COLORS["card"], fg=self.COLORS["soft"], font=("TkDefaultFont", 9), wraplength=650, justify="left", anchor="w").pack(fill="x", padx=18, pady=(6, 10))
        tk.Checkbutton(motion, text="Enable motion connection", variable=self.motion_enabled_var, command=self.preview_motion_setting, bg=self.COLORS["card"], fg=self.COLORS["ink"], activebackground=self.COLORS["card"], activeforeground=self.COLORS["ink"], selectcolor=self.COLORS["card2"], highlightthickness=0, anchor="w").pack(fill="x", padx=15, pady=(0, 10))
        endpoint = tk.Frame(motion, bg=self.COLORS["card"])
        endpoint.pack(fill="x", padx=18, pady=(0, 8))
        tk.Label(endpoint, text="Steam Deck address (optional)", bg=self.COLORS["card"], fg=self.COLORS["soft"], font=("TkDefaultFont", 9)).pack(side="left")
        self.motion_host_entry = tk.Entry(endpoint, textvariable=self.motion_host_var, width=22, bg="#edf3f7", fg="#111820", relief="flat")
        self.motion_host_entry.pack(side="left", padx=(8, 16))
        tk.Label(endpoint, text="Port", bg=self.COLORS["card"], fg=self.COLORS["soft"], font=("TkDefaultFont", 9)).pack(side="left")
        tk.Entry(endpoint, textvariable=self.motion_port_var, width=7, bg="#edf3f7", fg="#111820", relief="flat").pack(side="left", padx=(8, 16))
        tk.Label(endpoint, text="Slot", bg=self.COLORS["card"], fg=self.COLORS["soft"], font=("TkDefaultFont", 9)).pack(side="left")
        tk.Entry(endpoint, textvariable=self.motion_slot_var, width=4, bg="#edf3f7", fg="#111820", relief="flat").pack(side="left", padx=(8, 16))
        self.motion_find_button = tk.Button(endpoint, text="Find Deck", command=self.discover_motion_host, bg=self.COLORS["card2"], fg=self.COLORS["ink"], activebackground="#24445d", relief="flat", bd=0, padx=11, pady=7, font=("TkDefaultFont", 8, "bold"), cursor="hand2")
        self.motion_find_button.pack(side="left", padx=(0, 8))
        tk.Button(endpoint, text="Open separate diagnostics", command=self.open_motion_probe, bg=self.COLORS["card2"], fg=self.COLORS["ink"], activebackground="#24445d", relief="flat", bd=0, padx=11, pady=7, font=("TkDefaultFont", 8, "bold"), cursor="hand2").pack(side="left")
        tk.Label(motion, textvariable=self.motion_status_var, bg=self.COLORS["card"], fg=self.COLORS["soft"], font=("TkDefaultFont", 9), anchor="w", justify="left").pack(fill="x", padx=18, pady=(0, 15))
        tk.Label(motion, textvariable=self.motion_discovery_var, bg=self.COLORS["card"], fg=self.COLORS["soft"], font=("TkDefaultFont", 8), anchor="w", justify="left").pack(fill="x", padx=18, pady=(0, 12))

        details = tk.Frame(grid, bg=self.COLORS["card"], highlightbackground=self.COLORS["line"], highlightthickness=1)
        details.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=6, pady=6)
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
        self.preview_motion_setting()

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

    def preview_motion_setting(self):
        if self.motion_enabled_var.get():
            if self.valid_motion_host(self.motion_host_var.get()):
                if (RUNTIME_DIR / "active").exists():
                    self.motion_status_var.set("Motion will start for the active session after you save settings.")
                else:
                    self.motion_status_var.set("Motion will start with the next Dual Screen Mode session after you save settings.")
            else:
                self.motion_status_var.set("Motion will look for your Steam Deck automatically. You can also use Find Deck or enter its address manually.")
        else:
            self.motion_status_var.set("Motion connection is disabled. Dual Screen Mode will leave the Deck DSU service alone.")

    @staticmethod
    def motion_monitor_is_ours(pid):
        if not str(pid).isdigit():
            return False
        proc = Path("/proc") / str(pid)
        try:
            if proc.stat().st_uid != os.getuid():
                return False
            command = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            return False
        return str(MOTION_MONITOR_PATH) in command

    def stop_motion_monitor(self):
        try:
            pid = MOTION_PID_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            return
        if self.motion_monitor_is_ours(pid):
            try:
                os.kill(int(pid), signal.SIGTERM)
            except (OSError, ValueError):
                pass
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline and (Path("/proc") / pid).exists():
                time.sleep(0.05)
        try:
            if MOTION_PID_FILE.read_text(encoding="utf-8").strip() == pid:
                MOTION_PID_FILE.unlink()
        except OSError:
            pass

    def start_motion_monitor(self):
        if not MOTION_MONITOR_PATH.exists():
            self.note_var.set("Motion monitor is not installed with this copy of Dual Screen Mode.")
            return
        try:
            current_pid = MOTION_PID_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            current_pid = ""
        if self.motion_monitor_is_ours(current_pid):
            return
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        log_path = RUNTIME_DIR / "motion-monitor.log"
        try:
            log = log_path.open("a", encoding="utf-8")
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(MOTION_MONITOR_PATH),
                    "--host", self.settings["motion_host"],
                    "--port", self.settings["motion_port"],
                    "--slot", self.settings["motion_slot"],
                    "--status-file", str(MOTION_STATUS_FILE),
                    "--pid-file", str(MOTION_PID_FILE),
                ],
                cwd=str(MOTION_MONITOR_PATH.parent),
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            MOTION_PID_FILE.write_text(str(process.pid) + "\n", encoding="utf-8")
            os.chmod(MOTION_PID_FILE, 0o600)
            log.close()
        except (OSError, subprocess.SubprocessError) as exc:
            self.note_var.set(f"Could not start motion monitoring: {exc}")

    def sync_motion_monitor(self):
        mode_active = (RUNTIME_DIR / "active").exists()
        if self.settings.get("motion_enabled") != "1":
            self.stop_motion_monitor()
            self.stop_settings_motion_check()
            return
        if mode_active and self.valid_motion_host(self.settings.get("motion_host", "")):
            self.stop_settings_motion_check()
            self.start_motion_monitor()
        elif mode_active:
            self.stop_settings_motion_check()
            self.stop_motion_monitor()
        else:
            self.stop_motion_monitor()
            self.start_settings_motion_check()

    def start_settings_motion_check(self):
        host = self.settings.get("motion_host", "").strip()
        port = self.settings.get("motion_port", "26760")
        slot = self.settings.get("motion_slot", "0")
        if not self.valid_motion_host(host):
            self.stop_settings_motion_check()
            return
        target = (host, port, slot)
        if self.settings_motion_client is not None:
            if self.settings_motion_client.is_alive() and self.settings_motion_target == target:
                return
            self.stop_settings_motion_check()
        try:
            numeric_port = int(port)
            numeric_slot = int(slot)
        except (TypeError, ValueError):
            return
        self.settings_motion_events = queue.Queue()
        self.settings_motion_client = DsuClient(host, numeric_port, numeric_slot, self.settings_motion_events)
        self.settings_motion_target = target
        self.settings_motion_started = time.monotonic()
        self.settings_motion_last_motion = None
        self.settings_motion_last_error = ""
        self.settings_motion_client.start()

    def stop_settings_motion_check(self):
        client = self.settings_motion_client
        self.settings_motion_client = None
        self.settings_motion_events = None
        self.settings_motion_target = None
        if client is not None:
            client.stop()
            client.join(timeout=0.5)

    def sync_settings_motion_check(self):
        if (RUNTIME_DIR / "active").exists() or self.settings.get("motion_enabled") != "1":
            self.stop_settings_motion_check()
        else:
            self.start_settings_motion_check()

    def poll_settings_motion_events(self):
        events = self.settings_motion_events
        client = self.settings_motion_client
        if events is None or client is None:
            return
        while True:
            try:
                event = events.get_nowait()
            except queue.Empty:
                break
            if event.kind == "motion":
                self.settings_motion_last_motion = time.monotonic()
                self.settings_motion_last_error = ""
            elif event.kind == "error":
                self.settings_motion_last_error = str(event.value)

    def settings_motion_status_detail(self, endpoint):
        client = self.settings_motion_client
        if client is None:
            return f"Enabled · Looking for your Steam Deck…\nChecking the local network · {endpoint}"
        self.poll_settings_motion_events()
        now = time.monotonic()
        if self.settings_motion_last_motion is not None and now - self.settings_motion_last_motion <= 3.0:
            stats = client.stats(now)
            return f"Enabled · Connected\nDeck motion data is arriving · {float(stats.get('rate', 0.0)):.0f} packets/s · {stats.get('dropped', 0)} dropped · {endpoint}"
        if now - self.settings_motion_started <= 3.0:
            return f"Enabled · Connecting…\nWaiting for your Steam Deck · {endpoint}"
        if self.settings_motion_last_error:
            return f"Enabled · Unable to connect\n{self.settings_motion_last_error} · {endpoint}"
        return f"Enabled · Unable to connect\nCheck that the motion service is running on your Steam Deck · {endpoint}"

    def close_app(self):
        self.stop_settings_motion_check()
        self.destroy()

    def auto_discover_motion_host(self):
        if self.motion_enabled_var.get() and not self.motion_host_var.get().strip():
            self.discover_motion_host(auto=True)

    def discover_motion_host(self, auto=False):
        if self.motion_discovery_running:
            return
        try:
            port = int(self.motion_port_var.get() or "26760")
        except (TypeError, ValueError):
            port = 26760
        preferred_host = self.motion_host_var.get().strip()
        self.motion_discovery_running = True
        self.motion_find_button.configure(state="disabled", text="Finding…")
        self.motion_discovery_var.set("Looking for a Deck DSU service on the local network…")
        threading.Thread(
            target=self._discover_motion_host_worker,
            args=(auto, port, preferred_host),
            daemon=True,
        ).start()

    def _discover_motion_host_worker(self, auto, port, preferred_host):
        try:
            unique = discover_motion_hosts(
                port=port,
                preferred_host=preferred_host,
            )
        except (TypeError, ValueError):
            unique = []
        self.after(0, lambda: self._finish_motion_discovery(unique, auto))

    def _finish_motion_discovery(self, found, auto):
        self.motion_discovery_running = False
        self.motion_find_button.configure(state="normal", text="Find Deck")
        if found:
            self.motion_host_var.set(found[0])
            extra = f" ({len(found)} found)" if len(found) > 1 else ""
            if auto:
                self.write_settings()
                self.motion_discovery_var.set(f"Found and saved DSU service at {found[0]}{extra}.")
            else:
                self.motion_discovery_var.set(f"Found DSU service at {found[0]}{extra}. Save settings to keep this address.")
            self.preview_motion_setting()
        elif auto:
            self.motion_discovery_var.set("Deck not found automatically. You can enter its current IP or use Find Deck again.")
        else:
            self.motion_discovery_var.set("No DSU service found on the local network. Check that the Deck service is running.")

    def open_motion_probe(self):
        host = self.motion_host_var.get().strip()
        port = self.motion_port_var.get().strip()
        slot = self.motion_slot_var.get().strip()
        if not self.valid_motion_host(host):
            self.note_var.set("Enter the Deck's IP address before opening diagnostics.")
            return
        if not self.valid_motion_port(port) or not self.valid_motion_slot(slot):
            self.note_var.set("Check the motion port and controller slot.")
            return
        if not MOTION_PROBE_PATH.exists():
            messagebox.showerror("Motion diagnostics", "The motion probe is not installed with this copy of Dual Screen Mode.")
            return
        try:
            subprocess.Popen(
                [sys.executable, str(MOTION_PROBE_PATH), "--host", host, "--port", port, "--slot", slot],
                cwd=str(MOTION_PROBE_PATH.parent.parent),
                start_new_session=True,
            )
            self.note_var.set("Opened the separate DSU Motion Probe. It does not control the automatic monitor.")
        except (OSError, subprocess.SubprocessError) as exc:
            messagebox.showerror("Motion diagnostics", f"Could not open the motion probe.\n\n{exc}")

    def motion_status_detail(self):
        if self.settings.get("motion_enabled", "1") != "1":
            return "Disabled\nTurn on motion / gyro in Settings if you want automatic motion monitoring."
        if self.motion_discovery_running and not self.settings.get("motion_host", ""):
            return "Enabled · Looking for your Steam Deck…\nLooking on the local network."
        host = self.settings.get("motion_host", "")
        port = self.settings.get("motion_port", "26760")
        slot = self.settings.get("motion_slot", "0")
        endpoint = f"{host or 'Deck address not set'}:{port} · slot {slot}"
        if not host:
            return f"Enabled · Unable to connect\nYour Steam Deck was not found automatically. Use Find Deck or enter its address · {endpoint}"
        if not (RUNTIME_DIR / "active").exists():
            return self.settings_motion_status_detail(endpoint)
        if not MOTION_PID_FILE.exists():
            log_path = RUNTIME_DIR / "motion-monitor.log"
            try:
                log_text = log_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                log_text = ""
            if "Traceback" in log_text or "ModuleNotFoundError" in log_text:
                return "Enabled · Unable to connect\nThe automatic motion monitor needs attention. Try toggling Dual Screen Mode off and on."
            return f"Enabled · Connecting…\nStarting the automatic motion connection · {endpoint}"
        try:
            monitor_pid = MOTION_PID_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            monitor_pid = ""
        if not self.motion_monitor_is_ours(monitor_pid):
            return "Enabled · Unable to connect\nThe automatic motion connection is not running. Try toggling Dual Screen Mode off and on."
        try:
            status = json.loads(MOTION_STATUS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return f"Enabled · Connecting…\nWaiting for the automatic motion connection · {endpoint}"
        status_target = (
            str(status.get("host", "")),
            str(status.get("port", "")),
            str(status.get("slot", "")),
        )
        if status_target != (host, str(port), str(slot)):
            return f"Enabled · Connecting…\nUpdating the automatic motion connection · {endpoint}"
        updated = status.get("updated")
        if isinstance(updated, (int, float)) and time.time() - updated > 3.0:
            return f"Enabled · Unable to connect\nThe automatic motion connection has stopped responding · {endpoint}"
        state = status.get("state", "unknown")
        if state == "connected":
            return f"Enabled · Connected\nDeck motion data is arriving · {float(status.get('rate', 0.0)):.0f} packets/s · {status.get('dropped', 0)} dropped · {endpoint}"
        if state == "connecting":
            return f"Enabled · Connecting…\nWaiting for your Steam Deck at {endpoint}"
        if state == "reconnecting":
            return f"Enabled · Connecting…\nTrying your Steam Deck again · {endpoint}"
        if state == "no_motion":
            return f"Enabled · Unable to connect\nCheck that the motion service is running on your Steam Deck · {endpoint}"
        if state == "unreachable":
            error = status.get("last_error") or "No response from the Deck"
            return f"Enabled · Unable to connect\n{error} · {endpoint}"
        if state == "invalid_config":
            return f"Enabled · Unable to connect\n{status.get('last_error', 'Check the Steam Deck address and port')}"
        if state == "stopped":
            return f"Enabled · Unable to connect\nThe automatic motion connection is stopped · {endpoint}"
        return f"Enabled · Unable to connect\nThe automatic motion connection reported: {state} · {endpoint}"

    def refresh_live_status(self, update_note=False):
        self.sync_saved_settings()
        self.sync_settings_motion_check()
        self.poll_settings_motion_events()
        self.refresh_status(update_note=update_note)
        if hasattr(self, "status_cards") and "motion" in self.status_cards:
            self.set_card_detail("motion", self.motion_status_detail())
        form_matches_saved = self.motion_form_matches(self.settings)
        if hasattr(self, "motion_status_var") and form_matches_saved:
            self.motion_status_var.set(self.motion_status_detail().replace("\n", " · "))

    def poll_status(self):
        # Refresh every live status card together so touch routing does not
        # remain stale while motion continues updating.
        self.refresh_live_status()
        self.after(1000, self.poll_status)

    def build_updates(self):
        page = self.new_view("updates")
        self.heading(page, "Updates", "Check for a newer Dual Screen Mode release and open its verified installer.")
        grid = tk.Frame(page, bg=self.COLORS["paper"])
        grid.pack(fill="x")
        grid.grid_columnconfigure(0, weight=1)
        self.card(grid, "Current version", f"Dual Screen Mode {APP_VERSION} is installed.", wide=True)
        update = tk.Frame(grid, bg=self.COLORS["card"], highlightbackground=self.COLORS["line"], highlightthickness=1)
        update.grid(column=0, row=1, columnspan=2, sticky="nsew", padx=6, pady=6)
        tk.Label(update, text="Update status", bg=self.COLORS["card"], fg=self.COLORS["light"], font=("TkDefaultFont", 11, "bold"), anchor="w").pack(fill="x", padx=18, pady=(16, 0))
        self.update_status_var = tk.StringVar(value="No update check has been run yet.")
        tk.Label(update, textvariable=self.update_status_var, bg=self.COLORS["card"], fg=self.COLORS["soft"], font=("TkDefaultFont", 10), wraplength=650, justify="left", anchor="w").pack(fill="x", padx=18, pady=(6, 0))
        self.update_notes_var = tk.StringVar(value="")
        tk.Label(update, textvariable=self.update_notes_var, bg=self.COLORS["card"], fg=self.COLORS["soft"], font=("TkDefaultFont", 9), wraplength=650, justify="left", anchor="w").pack(fill="x", padx=18, pady=(6, 0))
        actions = tk.Frame(update, bg=self.COLORS["card"])
        actions.pack(fill="x", padx=18, pady=(12, 16))
        self.update_check_button = tk.Button(actions, text="Check for updates", command=self.check_for_updates, bg=self.COLORS["blue"], fg="#fff", activebackground=self.COLORS["light"], relief="flat", bd=0, padx=13, pady=8, font=("TkDefaultFont", 9, "bold"), cursor="hand2")
        self.update_check_button.pack(side="left", padx=(0, 8))
        self.update_download_button = tk.Button(actions, text="Download update", command=self.download_update, state="disabled", bg=self.COLORS["card2"], fg=self.COLORS["soft"], activebackground="#24445d", relief="flat", bd=0, padx=13, pady=8, font=("TkDefaultFont", 9, "bold"), cursor="hand2")
        self.update_download_button.pack(side="left")
        self.card(grid, "How updating works", "DSM checks the public GitHub release list, downloads the Linux package and its checksum, verifies the download, and opens the normal setup wizard. Your existing settings and backups are preserved. You still review and start the installation yourself.", wide=True, row=2)

    def check_for_updates(self):
        if self.update_check_running or self.update_download_running:
            return
        self.update_check_running = True
        self.update_release = None
        self.update_check_button.configure(state="disabled")
        self.update_download_button.configure(state="disabled")
        self.update_status_var.set("Checking GitHub for a newer release…")
        self.update_notes_var.set("")

        def worker():
            try:
                releases = update_support.fetch_releases()
                release = update_support.find_update(releases, APP_VERSION)
                self.after(0, lambda: self.finish_update_check(release, None))
            except update_support.UpdateError as exc:
                self.after(0, lambda: self.finish_update_check(None, str(exc)))
            except Exception as exc:
                self.after(0, lambda: self.finish_update_check(None, f"Update check failed: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def finish_update_check(self, release, error):
        self.update_check_running = False
        self.update_check_button.configure(state="normal")
        if error:
            self.update_status_var.set(error)
            self.update_notes_var.set("You can try again later or use the GitHub release page manually.")
            return
        if release is None:
            self.update_status_var.set(f"You are up to date. Dual Screen Mode {APP_VERSION} is the newest available release.")
            self.update_notes_var.set("")
            return
        tag = release.get("tag_name", "new release")
        self.update_release = release
        self.update_status_var.set(f"Update available: {tag}")
        body = str(release.get("body") or "").strip()
        self.update_notes_var.set(body[:700] + ("…" if len(body) > 700 else ""))
        self.update_download_button.configure(state="normal")

    def download_update(self):
        if self.update_release is None or self.update_check_running or self.update_download_running:
            return
        if (RUNTIME_DIR / "active").exists() or (RUNTIME_DIR / "starting").exists() or (RUNTIME_DIR / "stopping").exists():
            messagebox.showwarning("Turn off Dual Screen Mode first", "Please turn off Dual Screen Mode and wait for shutdown to finish before updating.")
            return
        tag = self.update_release.get("tag_name", "the update")
        if not messagebox.askyesno("Download update", f"Download and verify {tag}?\n\nThe normal setup wizard will open after the download. You will still review and start the installation yourself."):
            return
        self.update_download_running = True
        self.update_check_button.configure(state="disabled")
        self.update_download_button.configure(state="disabled")
        self.update_status_var.set("Downloading and verifying the update…")

        def worker():
            try:
                extracted = update_support.download_and_extract(self.update_release)
                self.after(0, lambda: self.finish_update_download(extracted, None))
            except update_support.UpdateError as exc:
                self.after(0, lambda: self.finish_update_download(None, str(exc)))
            except Exception as exc:
                self.after(0, lambda: self.finish_update_download(None, f"Update download failed: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def finish_update_download(self, extracted, error):
        self.update_download_running = False
        self.update_check_button.configure(state="normal")
        if error:
            self.update_status_var.set(error)
            self.update_notes_var.set("The current installation was not changed.")
            return
        self.update_status_var.set("Update downloaded and verified.")
        self.update_notes_var.set("DSM is ready to safely close, replace its owned files, and reopen the updated Settings app.")
        if messagebox.askyesno(
            "Apply update",
            "DSM will safely turn off its active session if needed, close Settings, replace its owned files, and reopen the updated Settings app.\n\nYour settings, backups, Sunshine, Moonlight, krfb, and emulator files will remain in place. Continue?",
        ):
            self.apply_update(extracted)

    def apply_update(self, extracted):
        self.update_download_running = True
        self.update_check_button.configure(state="disabled")
        self.update_download_button.configure(state="disabled")
        self.update_status_var.set("Preparing the in-place update…")

        resolution = self.settings.get("resolution", self.resolution_var.get())
        audio = self.settings.get("audio_mode", self.audio_var.get())
        parent_pid = os.getpid()

        def worker():
            try:
                mode_files = (RUNTIME_DIR / "active", RUNTIME_DIR / "starting", RUNTIME_DIR / "stopping")
                if any(path.exists() for path in mode_files):
                    if not TOGGLE_PATH.exists():
                        raise RuntimeError("The Dual Screen Mode toggle could not be found.")
                    subprocess.run([str(TOGGLE_PATH)], capture_output=True, text=True, timeout=35, check=False)
                    deadline = time.monotonic() + 35.0
                    while time.monotonic() < deadline and any(path.exists() for path in mode_files):
                        time.sleep(0.2)
                    if any(path.exists() for path in mode_files):
                        raise RuntimeError("DSM could not finish shutting down safely. The update was not started.")
                runner = extracted / "update_runner.py"
                if not runner.is_file():
                    raise RuntimeError("The update package is missing its updater.")
                subprocess.Popen(
                    [
                        sys.executable,
                        str(runner),
                        "--package",
                        str(extracted),
                        "--parent-pid",
                        str(parent_pid),
                        "--resolution",
                        resolution,
                        "--audio",
                        audio if audio in ("host", "handheld", "both") else "host",
                    ],
                    cwd=str(extracted),
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self.after(100, self.destroy)
            except Exception as exc:
                self.after(0, lambda: self.finish_update_apply_error(str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def finish_update_apply_error(self, error):
        self.update_download_running = False
        self.update_check_button.configure(state="normal")
        self.update_status_var.set(f"Update stopped safely: {error}")
        self.update_notes_var.set("The current installation was not replaced.")

    def build_help(self):
        page = self.new_view("help")
        self.heading(page, "Help", "Useful checks when something does not look right.")
        grid = tk.Frame(page, bg=self.COLORS["paper"])
        grid.pack(fill="x")
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)
        self.card(grid, "Enable or disable the mode", "Double-click Dual Screen Mode on the desktop. DSM refreshes Sunshine at startup so it loads the virtual display target. Rapid duplicate clicks are ignored while a transition is finishing. A Moonlight disconnect does not disable the mode, so you can reconnect without recreating the display.", 0, 0)
        self.card(grid, "Check Moonlight", "The handheld connects to Sunshine over the same local network. Moonlight is installed separately on the handheld.", 1, 0)
        self.card(grid, "If the picture is tiny", "Match the saved display size to the handheld, check Moonlight's stream resolution, and adjust the PC's display scaling settings if needed.", 0, 1)
        self.card(grid, "If a game does not respond", "Moonlight sends the handheld's controls to the host. For Cemu, select the prepared Dual Screen Mode Deck Gyro profile. Other emulator and game-specific input setup remains outside Dual Screen Mode.", 1, 1)
        self.card(grid, "If touch hits the wrong screen", "Disable and re-enable Dual Screen Mode. The touch status updates automatically and will show whether the handheld touchscreen is mapped, waiting, or unavailable.", 0, 2)
        self.card(grid, "What the mode changes", "It creates a KDE virtual display, maps the handheld touchscreen to that display when it appears, refreshes the Flatpak Sunshine session so its virtual-display target is loaded, and changes Sunshine's capture and audio-stream settings. When enabled, the motion monitor runs only while the mode is active, reconnects when the Deck briefly disappears, and updates its status automatically. Settings can check motion while it is open. Handheld mode may mute the current default output for the session. It does not change the default output, install a driver, create a blank or virtual audio device, or alter other outputs. Saved audio and temporary Sunshine display values are restored when the mode turns off, and a Sunshine session that was already running is returned. Temporary startup logs are kept in the Dual Screen Mode runtime folder.", wide=True, row=3)
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
                f"Virtual display: {'active' if active else 'disabled'}",
                f"Saved resolution: {self.settings.get('resolution', '1280x800')}",
                f"Audio mode: {self.settings.get('audio_mode', 'host')}",
                f"Touch routing: {self.touch_status()}",
                f"Motion: {self.motion_status_detail().replace(chr(10), ' / ')}",
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
        # Keep the Status page compact so shorter displays do not get a
        # needless scrollbar from expandable geometry.
        if key == "status":
            self.views[key].pack(fill="x", expand=False)
        else:
            self.views[key].pack(fill="both", expand=True)
        self.content_canvas.yview_moveto(0)
        self.nav_buttons[key].configure(bg="#24445d", fg=self.COLORS["ink"])
        self.save_button.pack_forget()
        if key == "settings":
            self.save_button.pack(side="right")
            self.note_var.set("Save settings to keep them. Motion changes apply to the active session; display and audio choices apply when the mode starts.")
        elif key == "status":
            self.note_var.set("Dual Screen Mode is currently disabled.")
        else:
            self.note_var.set("Dual Screen Mode management")
        if key == "status":
            self.refresh_status()

    def refresh_status(self, update_note=True):
        marked_active = (RUNTIME_DIR / "active").exists()
        starting = (RUNTIME_DIR / "starting").exists()
        stopping = (RUNTIME_DIR / "stopping").exists()
        display_present = self.virtual_display_present()
        active = marked_active and (display_present is not False)
        connection = self.sunshine_connection_status()
        if stopping:
            self.status_var.set("Virtual display stopping")
            self.status_detail_var.set("Finishing shutdown and restoring your previous Sunshine and audio settings.")
            self.status_badge_var.set("STOPPING")
            self.host_status.configure(text="Stopping", fg=self.COLORS["light"])
            if update_note:
                self.note_var.set("Dual Screen Mode is finishing its shutdown. Please wait a moment before starting it again.")
        elif starting:
            self.status_var.set("Virtual display starting")
            self.status_detail_var.set("Preparing the virtual display and Sunshine connection.")
            self.status_badge_var.set("STARTING")
            self.host_status.configure(text="Starting", fg=self.COLORS["light"])
            if update_note:
                self.note_var.set("Dual Screen Mode is starting. The desktop shortcut will be ready when setup finishes.")
        elif active:
            self.status_var.set("Virtual display active")
            if connection == "connected":
                self.status_detail_var.set("Handheld connected through Sunshine.")
            elif connection == "waiting":
                self.status_detail_var.set("Connect your handheld with Moonlight.")
            else:
                self.status_detail_var.set("Sunshine is ready. Connect your handheld with Moonlight.")
            self.status_badge_var.set("ON")
            if connection == "connected":
                self.host_status.configure(text="Handheld connected", fg=self.COLORS["green"])
            else:
                self.host_status.configure(text="Mode active", fg=self.COLORS["light"])
            if update_note:
                if connection == "connected":
                    self.note_var.set("Dual Screen Mode is active and the handheld is connected.")
                else:
                    self.note_var.set("Dual Screen Mode is currently active.")
        elif marked_active and display_present is False:
            self.status_var.set("Virtual display needs recovery")
            self.status_detail_var.set("KDE no longer reports the virtual display. Double-click the toggle to reset the mode.")
            self.status_badge_var.set("CHECK")
            self.host_status.configure(text="Needs attention", fg=self.COLORS["red"])
            if update_note:
                self.note_var.set("The mode marker is active, but the virtual display is missing.")
        else:
            self.status_var.set("Virtual display disabled")
            sunshine_available = self.sunshine_status() == "Running"
            if sunshine_available:
                self.status_detail_var.set("Dual Screen Mode is disabled. Sunshine is available for normal streaming.")
            else:
                self.status_detail_var.set("Double-click Dual Screen Mode on the desktop to enable it.")
            self.status_badge_var.set("DISABLED")
            self.host_status.configure(
                text="Host available" if sunshine_available else "Mode disabled",
                fg=self.COLORS["light"] if sunshine_available else self.COLORS["soft"],
            )
            if update_note:
                self.note_var.set(
                    "Dual Screen Mode is disabled, but Sunshine is available for normal streaming."
                    if sunshine_available
                    else "Dual Screen Mode is currently disabled."
                )
        if stopping:
            display_state = "Stopping"
        elif starting:
            display_state = "Starting"
        else:
            display_state = "Active" if active else "Disabled"
        if not starting and not stopping and active and connection == "connected":
            display_state += "\nHandheld connected"
        elif not starting and not stopping and active and connection == "waiting":
            display_state += "\nWaiting for handheld"
        display = f"{display_state}\nSize: {self.settings.get('resolution', '1280x800').replace('x', ' × ')}"
        audio_labels = {"host": "Host", "handheld": "Handheld", "both": "Both (work in progress)"}
        audio = f"Destination: {audio_labels.get(self.settings.get('audio_mode', 'host'), 'Host')}"
        sunshine = self.sunshine_status()
        self.set_card_detail("display", display)
        self.set_card_detail("audio", audio)
        self.set_card_detail("touch", self.touch_status())
        self.set_card_detail("sunshine", sunshine)
        self.set_card_detail("motion", self.motion_status_detail())

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

    def sunshine_connection_status(self):
        """Return the latest known Moonlight/Sunshine streaming state.

        Sunshine records a clear CLIENT CONNECTED/DISCONNECTED event in its
        log. The display can remain active between streams, so this is kept
        separate from sunshine_status(), which only answers whether Sunshine
        itself is running or installed.
        """
        path = self.sunshine_log_path
        if not path.exists():
            return "unknown"
        try:
            with path.open("rb") as handle:
                handle.seek(0, os.SEEK_END)
                size = handle.tell()
                handle.seek(max(0, size - 131072), os.SEEK_SET)
                text = handle.read().decode("utf-8", errors="replace")
        except OSError:
            return "unknown"

        sessions = 0
        saw_session_event = False
        session_start_seen = False
        for line in text.splitlines():
            marker = "[active sessions:"
            if "New streaming session started" in line and marker in line:
                try:
                    sessions = max(0, int(line.split(marker, 1)[1].split("]", 1)[0].strip()))
                    saw_session_event = True
                except (ValueError, IndexError):
                    sessions = max(1, sessions)
                    saw_session_event = True
                session_start_seen = True
            elif "CLIENT CONNECTED" in line:
                # Recent Sunshine versions log the active-session count when
                # the stream starts, followed by CLIENT CONNECTED for the
                # same session. Do not count that connection twice.
                if not session_start_seen:
                    sessions += 1
                saw_session_event = True
                session_start_seen = False
            elif "CLIENT DISCONNECTED" in line:
                sessions = max(0, sessions - 1)
                saw_session_event = True
                session_start_seen = False

        if not saw_session_event:
            return "unknown"
        return "connected" if sessions > 0 else "waiting"

    @staticmethod
    def touch_status():
        if (RUNTIME_DIR / "stopping").exists():
            return "Restoring previous touch routing"
        if (RUNTIME_DIR / "starting").exists() and not (RUNTIME_DIR / "active").exists():
            return "Starting with Dual Screen Mode"
        if not (RUNTIME_DIR / "active").exists():
            return "Disabled until Dual Screen Mode starts"
        try:
            status = (RUNTIME_DIR / "touch-status").read_text(encoding="utf-8").strip()
        except OSError:
            status = ""
        return {
            "mapped": "Mapped to the second screen",
            "waiting": "Waiting for the handheld touchscreen",
            "unavailable": "Unable to check touch routing",
            "warning": "Unable to route touch to the second screen",
        }.get(status, "Waiting for the handheld touchscreen")

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

