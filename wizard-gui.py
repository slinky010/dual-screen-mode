#!/usr/bin/env python3

import os
import queue
import re
import shlex
import shutil
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk


BASE_DIR = Path(__file__).resolve().parent
SETUP_SCRIPT = BASE_DIR / "setup-wizard.sh"
ICON_PATH = BASE_DIR / "assets" / "dual-screen-mode.png"
TOGGLE_PATH = Path.home() / ".local" / "bin" / "dual-screen-mode"


class DualScreenWizard(tk.Tk):
    COLORS = {
        "ink": "#e6edf4",
        "soft": "#9baaba",
        "navy": "#0d141d",
        "rail": "#182530",
        "paper": "#121b24",
        "paper2": "#1a2732",
        "blue": "#4d91d5",
        "blue_bright": "#81bdf3",
        "cyan": "#0bd0ed",
        "good": "#59c6a2",
        "warning": "#f1c56d",
        "line": "#334252",
    }

    def __init__(self):
        super().__init__()
        self.title("Install Dual Screen Mode")
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        window_width = min(1600, max(1120, screen_width - 40))
        window_height = min(1000, max(720, screen_height - 60))
        self.geometry(f"{window_width}x{window_height}")
        self.minsize(1100, 720)
        self.resizable(True, True)
        self.configure(bg=self.COLORS["navy"])
        self.protocol("WM_DELETE_WINDOW", self.close_window)

        self.page_index = 0
        self.install_started = False
        self.install_failed = False
        self.install_process = None
        self.krfb_missing = False
        self.check_started = False
        self.events = queue.Queue()
        self.output_lines = []

        self.resolution_var = tk.StringVar(value="1280x800")
        self.audio_var = tk.StringVar(value="host")
        self.check_status_var = tk.StringVar(value="Checking this computer when you reach this step.")
        self.progress_detail_var = tk.StringVar(value="Waiting to begin.")
        self.test_result_var = tk.StringVar(value="")

        self.setup_styles()
        self.load_artwork()
        if self.logo_small:
            self.iconphoto(True, self.logo_small)
        self.build_shell()
        self.build_pages()
        self.show_page(0)

    def setup_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Dark.TCombobox",
            fieldbackground=self.COLORS["paper2"],
            background=self.COLORS["paper2"],
            foreground=self.COLORS["ink"],
            bordercolor=self.COLORS["line"],
            arrowcolor=self.COLORS["blue_bright"],
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", self.COLORS["paper2"])],
            foreground=[("readonly", self.COLORS["ink"])],
        )

    def load_artwork(self):
        self.logo_large = None
        self.logo_small = None
        if not ICON_PATH.exists():
            return
        try:
            original = tk.PhotoImage(file=str(ICON_PATH))
            factor = max(1, original.width() // 320)
            self.logo_large = original.subsample(factor, factor)
            self.logo_small = original.subsample(max(1, original.width() // 52), max(1, original.height() // 52))
        except tk.TclError:
            self.logo_large = None
            self.logo_small = None

    def build_shell(self):
        self.rail = tk.Frame(self, bg=self.COLORS["rail"], width=310)
        self.rail.pack(side="left", fill="y")
        self.rail.pack_propagate(False)

        brand = tk.Frame(self.rail, bg=self.COLORS["rail"])
        brand.pack(fill="x", padx=24, pady=(26, 52))
        brand.grid_columnconfigure(1, weight=1, minsize=0)
        if self.logo_small:
            tk.Label(brand, image=self.logo_small, bg=self.COLORS["paper"], padx=5, pady=5).grid(row=0, column=0, sticky="nw")
        brand_text = tk.Frame(brand, bg=self.COLORS["rail"])
        brand_text.grid(row=0, column=1, sticky="new", padx=(11, 0))
        brand_text.grid_columnconfigure(0, weight=1)
        brand_title = tk.Label(brand_text, text="Dual Screen Mode", bg=self.COLORS["rail"], fg="#c7e1f8", font=("TkDefaultFont", 13, "bold"), anchor="w", justify="left", wraplength=170)
        brand_title.grid(row=0, column=0, sticky="ew")
        brand_credit = tk.Label(brand_text, text="Made by slinky", bg=self.COLORS["rail"], fg="#8d9dad", font=("TkDefaultFont", 9), anchor="w", justify="left", wraplength=170)
        brand_credit.grid(row=1, column=0, sticky="ew")
        brand_text.bind("<Configure>", lambda event: [label.configure(wraplength=max(1, event.width - 4)) for label in (brand_title, brand_credit)])

        self.step_widgets = []
        steps = [
            ("Welcome", "The idea", None),
            ("System check", "Check the host", 1),
            ("Setup & permissions", "What may change", 2),
            ("Display size", "Choose the resolution", 3),
            ("Audio", "Choose where it plays", 4),
            ("Review", "Check the choices", 5),
            ("Setting things up", "Watch the progress", 6),
            ("Complete", "Connect and play", 7),
        ]
        for index, (title, caption, number) in enumerate(steps):
            row = tk.Frame(self.rail, bg=self.COLORS["rail"])
            row.pack(fill="x", padx=24, pady=5)
            dot = tk.Label(row, text="" if number is None else str(number), width=2, height=1, bg=self.COLORS["rail"], fg="#8493a4", font=("TkDefaultFont", 9, "bold"), padx=5, pady=5)
            dot.pack(side="left", anchor="n")
            text_frame = tk.Frame(row, bg=self.COLORS["rail"])
            text_frame.pack(side="left", padx=10)
            label = tk.Label(text_frame, text=title, bg=self.COLORS["rail"], fg="#8493a4", font=("TkDefaultFont", 11, "bold"), anchor="w", wraplength=205, justify="left")
            label.pack(anchor="w")
            small = tk.Label(text_frame, text=caption, bg=self.COLORS["rail"], fg="#718091", font=("TkDefaultFont", 9), anchor="w", wraplength=205, justify="left")
            small.pack(anchor="w")
            self.step_widgets.append((dot, label, small))

        self.workspace = tk.Frame(self, bg=self.COLORS["paper"])
        self.workspace.pack(side="left", fill="both", expand=True)

        header = tk.Frame(self.workspace, bg=self.COLORS["paper"])
        header.pack(fill="x", padx=38, pady=(26, 0))
        tk.Label(header, text="Install Dual Screen Mode", bg=self.COLORS["paper"], fg=self.COLORS["soft"], font=("TkDefaultFont", 9)).pack(side="left")
        self.status_label = tk.Label(header, text="Ready to set up", bg=self.COLORS["paper"], fg=self.COLORS["good"], font=("TkDefaultFont", 9, "bold"))
        self.status_label.pack(side="right")

        content_shell = tk.Frame(self.workspace, bg=self.COLORS["paper"])
        content_shell.pack(fill="both", expand=True, padx=54, pady=(22, 12))
        self.content_canvas = tk.Canvas(content_shell, bg=self.COLORS["paper"], highlightthickness=0, bd=0)
        self.content_scrollbar = ttk.Scrollbar(content_shell, orient="vertical", command=self.content_canvas.yview)
        self.content_canvas.configure(yscrollcommand=self.content_scrollbar.set)
        self.content_canvas.pack(side="left", fill="both", expand=True)
        self.content = tk.Frame(self.content_canvas, bg=self.COLORS["paper"])
        content_window = self.content_canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", lambda _event: self._update_scrollbar())
        self.content_canvas.bind("<Configure>", lambda event: (self.content_canvas.itemconfigure(content_window, width=event.width), self._update_scrollbar()))

        footer = tk.Frame(self.workspace, bg=self.COLORS["paper"], highlightbackground=self.COLORS["line"], highlightthickness=1)
        footer.pack(fill="x", side="bottom")
        self.footer_note = tk.Label(footer, text="No changes are made until the review step.", bg=self.COLORS["paper"], fg=self.COLORS["soft"], font=("TkDefaultFont", 9), anchor="w")
        self.footer_note.pack(side="left", padx=38, pady=17)
        buttons = tk.Frame(footer, bg=self.COLORS["paper"])
        buttons.pack(side="right", padx=30, pady=12)
        self.back_button = self.make_button(buttons, "Back", self.previous_page, primary=False)
        self.back_button.pack(side="left", padx=5)
        self.test_button = self.make_button(buttons, "Run connection test", self.run_connection_test, primary=False)
        self.next_button = self.make_button(buttons, "Begin setup", self.next_page, primary=True)
        self.next_button.pack(side="left", padx=5)

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

    def build_pages(self):
        self.pages = []
        self.build_welcome()
        self.build_system_check()
        self.build_permissions()
        self.build_device()
        self.build_audio()
        self.build_review()
        self.build_progress()
        self.build_complete()

    def new_page(self):
        frame = tk.Frame(self.content, bg=self.COLORS["paper"])
        self.pages.append(frame)
        return frame

    def make_label(self, parent, text, size=11, color=None, bold=False, wrap=650):
        return tk.Label(parent, text=text, bg=self.COLORS["paper"], fg=color or self.COLORS["ink"], font=("TkDefaultFont", size, "bold" if bold else "normal"), justify="left", anchor="nw", wraplength=wrap)

    def make_button(self, parent, text, command, primary=True):
        bg = self.COLORS["blue"] if primary else self.COLORS["paper"]
        fg = "#ffffff" if primary else self.COLORS["ink"]
        return tk.Button(parent, text=text, command=command, bg=bg, fg=fg, activebackground=self.COLORS["blue_bright"], activeforeground="#ffffff", relief="flat", bd=0, padx=16, pady=10, font=("TkDefaultFont", 10, "bold"), cursor="hand2")

    def card(self, parent, title, detail, symbol="✓", column=0, row=0):
        frame = tk.Frame(parent, bg=self.COLORS["paper2"], highlightbackground=self.COLORS["line"], highlightthickness=1)
        frame.grid(column=column, row=row, sticky="nsew", padx=6, pady=6)
        tk.Label(frame, text=symbol, bg=self.COLORS["paper2"], fg=self.COLORS["good"], font=("TkDefaultFont", 14, "bold")).pack(side="left", padx=(14, 8), pady=14)
        text = tk.Frame(frame, bg=self.COLORS["paper2"])
        text.pack(side="left", fill="both", expand=True, padx=(0, 10), pady=12)
        tk.Label(text, text=title, bg=self.COLORS["paper2"], fg=self.COLORS["ink"], font=("TkDefaultFont", 10, "bold"), anchor="w").pack(anchor="w")
        tk.Label(text, text=detail, bg=self.COLORS["paper2"], fg=self.COLORS["soft"], font=("TkDefaultFont", 9), anchor="w", wraplength=230, justify="left").pack(anchor="w", pady=(3, 0))
        return frame

    def heading(self, page, eyebrow, title, lede):
        tk.Label(page, text=eyebrow.upper(), bg=self.COLORS["paper"], fg=self.COLORS["blue_bright"], font=("TkDefaultFont", 8, "bold"), anchor="w").pack(anchor="w", pady=(8, 6))
        self.make_label(page, title, size=25, bold=True, wrap=720).pack(anchor="w")
        self.make_label(page, lede, size=11, color=self.COLORS["soft"], wrap=700).pack(anchor="w", pady=(12, 0))

    def build_welcome(self):
        page = self.new_page()
        body = tk.Frame(page, bg=self.COLORS["paper"])
        body.pack(fill="both", expand=True)
        left = tk.Frame(body, bg=self.COLORS["paper"])
        left.pack(side="left", fill="both", expand=True, padx=(0, 20))
        tk.Label(left, text="A WIRELESS WII U GAMEPAD FOR YOUR LINUX PC", bg=self.COLORS["paper"], fg=self.COLORS["blue_bright"], font=("TkDefaultFont", 8, "bold"), anchor="w").pack(anchor="w", pady=(65, 8))
        self.make_label(left, "Use your handheld like a Wii U GamePad.", size=27, bold=True, wrap=450).pack(anchor="w")
        self.make_label(left, "Set up a Steam Deck or PC handheld as a wireless second screen for Wii U and 3DS games, emulation, and other two-screen setups.", size=11, color=self.COLORS["soft"], wrap=470).pack(anchor="w", pady=(16, 0))
        callout = tk.Frame(left, bg="#1b3044", highlightbackground="#315d80", highlightthickness=1)
        callout.pack(fill="x", pady=(25, 0))
        tk.Label(callout, text="✦", bg="#1b3044", fg=self.COLORS["cyan"], font=("TkDefaultFont", 14, "bold")).pack(side="left", padx=14, pady=14)
        tk.Label(callout, text="Moonlight is installed separately.\nPair it with Sunshine manually after setup.", bg="#1b3044", fg="#c0cfdd", font=("TkDefaultFont", 9), justify="left", anchor="w").pack(side="left", pady=14)
        art = tk.Frame(body, bg=self.COLORS["paper"])
        art.pack(side="right", fill="both", expand=True)
        if self.logo_large:
            tk.Label(art, image=self.logo_large, bg=self.COLORS["paper"]).pack(expand=True)

    def build_system_check(self):
        page = self.new_page()
        self.heading(page, "Step 1 · System check", "Check the host.", "Dual Screen Mode checks the pieces it needs and explains anything missing before installation.")
        grid = tk.Frame(page, bg=self.COLORS["paper"])
        grid.pack(fill="x", pady=(22, 8))
        for col in range(2):
            grid.grid_columnconfigure(col, weight=1)
        self.card(grid, "KDE Plasma on Wayland", "Required host environment", column=0, row=0)
        self.card(grid, "Sunshine", "Offers the host stream", column=1, row=0)
        self.card(grid, "krfb virtual display", "Creates the second screen", symbol="＋", column=0, row=1)
        self.card(grid, "Supported graphics", "Used by the host encoder", symbol="▣", column=1, row=1)
        status = tk.Frame(page, bg="#1b3044", highlightbackground="#315d80", highlightthickness=1)
        status.pack(fill="x", pady=(20, 0))
        tk.Label(status, text="ⓘ", bg="#1b3044", fg=self.COLORS["cyan"], font=("TkDefaultFont", 13, "bold")).pack(side="left", padx=14, pady=14)
        tk.Label(status, textvariable=self.check_status_var, bg="#1b3044", fg="#c0cfdd", font=("TkDefaultFont", 9), justify="left", anchor="w").pack(side="left", pady=14)

        self.krfb_action = tk.Frame(page, bg=self.COLORS["paper2"], highlightbackground=self.COLORS["line"], highlightthickness=1)
        self.krfb_action_text = tk.StringVar(value="")
        tk.Label(self.krfb_action, text="KDE's virtual-display package is missing", bg=self.COLORS["paper2"], fg=self.COLORS["warning"], font=("TkDefaultFont", 10, "bold"), anchor="w").pack(anchor="w", padx=16, pady=(14, 3))
        tk.Label(self.krfb_action, text="1. Click Open installation terminal.\n2. Enter your normal system password and let the package finish.\n3. Close Konsole, then click Check again.", bg=self.COLORS["paper2"], fg=self.COLORS["ink"], font=("TkDefaultFont", 10), justify="left", anchor="w", wraplength=680).pack(anchor="w", padx=16, pady=(0, 8))
        tk.Label(self.krfb_action, textvariable=self.krfb_action_text, bg=self.COLORS["paper2"], fg=self.COLORS["soft"], font=("TkDefaultFont", 9), justify="left", anchor="w", wraplength=680).pack(anchor="w", padx=16)
        krfb_buttons = tk.Frame(self.krfb_action, bg=self.COLORS["paper2"])
        krfb_buttons.pack(anchor="w", padx=16, pady=(12, 14))
        self.krfb_install_button = self.make_button(krfb_buttons, "Open installation terminal", self.open_krfb_terminal, primary=True)
        self.krfb_install_button.pack(side="left", padx=(0, 8))
        self.krfb_check_button = self.make_button(krfb_buttons, "Check again", self.check_krfb, primary=False)
        self.krfb_check_button.pack(side="left")

    def build_permissions(self):
        page = self.new_page()
        self.heading(page, "Step 2 · Setup and permissions", "What will change?", "The setup adds the virtual display support, configures Sunshine for KDE capture, and routes Sunshine's virtual touchscreen to that display when it appears.")
        grid = tk.Frame(page, bg=self.COLORS["paper"])
        grid.pack(fill="x", pady=(22, 8))
        for col in range(2):
            grid.grid_columnconfigure(col, weight=1)
        self.card(grid, "Virtual second screen", "Add the KDE component if needed", symbol="＋", column=0, row=0)
        self.card(grid, "Sunshine capture", "Use KDE’s virtual output and touch routing", symbol="↗", column=1, row=0)
        self.card(grid, "One user-level permission", "Allows KWin capture for Sunshine", symbol="⌁", column=0, row=1)
        self.card(grid, "Settings app", "Manage settings, updates, and uninstall", column=1, row=1)
        self.make_label(page, "The setup keeps things simple. Your existing streaming tools remain available for regular use, and Dual Screen Mode has its own settings app for changes or removal.", size=10, color=self.COLORS["soft"], wrap=680).pack(anchor="w", pady=(25, 0))

    def build_device(self):
        page = self.new_page()
        self.heading(page, "Step 3 · Display size", "Choose the resolution.", "Pick the size your handheld or other Moonlight client will use. 1280 × 800 is a good starting point for a Steam Deck.")
        field = tk.Frame(page, bg=self.COLORS["paper"])
        field.pack(anchor="w", pady=(28, 0))
        tk.Label(field, text="Starting resolution", bg=self.COLORS["paper"], fg=self.COLORS["soft"], font=("TkDefaultFont", 9)).pack(side="left", padx=(0, 12))
        self.resolution_combo = ttk.Combobox(field, textvariable=self.resolution_var, values=("1280x800", "1280x720", "1920x1080", "1920x1200", "Custom"), state="readonly", width=16, style="Dark.TCombobox")
        self.resolution_combo.pack(side="left")
        self.resolution_combo.bind("<<ComboboxSelected>>", self.resolution_changed)
        self.custom_resolution = tk.Entry(field, bg=self.COLORS["paper2"], fg=self.COLORS["ink"], insertbackground=self.COLORS["ink"], relief="flat", width=16)
        self.custom_resolution.insert(0, "1280x800")
        self.resolution_changed()

    def build_audio(self):
        page = self.new_page()
        self.heading(page, "Step 4 · Audio", "Choose where audio plays.", "Host is the default. Dual Screen Mode does not install an audio device or change your system's default output.")
        choices = tk.Frame(page, bg=self.COLORS["paper"])
        choices.pack(fill="x", pady=(22, 12))
        self.audio_buttons = {}
        for key, title, sub in [("host", "Host", "Keep it on the host"), ("handheld", "Handheld", "Stream it and mute host"), ("both", "Both (work in progress)", "Uses Handheld for now")]:
            button = tk.Button(choices, text=f"▣\n{title}\n{sub}", command=lambda value=key: self.select_audio(value), bg=self.COLORS["paper2"], fg=self.COLORS["ink"], activebackground="#24435e", activeforeground="#ffffff", relief="flat", bd=0, padx=18, pady=16, font=("TkDefaultFont", 11, "bold"), justify="left", anchor="w")
            button.pack(side="left", fill="both", expand=True, padx=5)
            self.audio_buttons[key] = button
        details = tk.Frame(page, bg=self.COLORS["paper2"], highlightbackground=self.COLORS["line"], highlightthickness=1)
        details.pack(fill="x", pady=(24, 0))
        self.audio_behavior_var = tk.StringVar()
        self.audio_restore_var = tk.StringVar(value="The saved Sunshine setting, volume, and mute state are restored when the mode turns off.")
        self.audio_not_changed_var = tk.StringVar(value="The default output is not changed. No audio driver, blank audio device, or virtual audio device is created. Other outputs are not altered.")
        self.audio_pipewire_var = tk.StringVar(value="On PipeWire, the toggle uses the existing PulseAudio compatibility interface. If the host output cannot be muted automatically, it is left unchanged and a warning is shown.")
        details.grid_columnconfigure(0, weight=1)
        details.grid_columnconfigure(1, weight=1)
        for index, (title, variable) in enumerate((("Selected option", self.audio_behavior_var), ("Saved and restored", self.audio_restore_var), ("Not changed", self.audio_not_changed_var), ("PipeWire and fallback", self.audio_pipewire_var))):
            row = tk.Frame(details, bg=self.COLORS["paper2"])
            row.grid(row=index // 2, column=index % 2, sticky="nsew", padx=12, pady=12)
            tk.Label(row, text=title, bg=self.COLORS["paper2"], fg=self.COLORS["blue_bright"], font=("TkDefaultFont", 10, "bold"), anchor="nw", justify="left").pack(anchor="w")
            tk.Label(row, textvariable=variable, bg=self.COLORS["paper2"], fg=self.COLORS["soft"], font=("TkDefaultFont", 10), wraplength=285, justify="left", anchor="nw").pack(fill="x", pady=(4, 0))
        self.select_audio("host")

    def build_review(self):
        page = self.new_page()
        self.heading(page, "Step 5 · Review", "Review your choices.", "Installation begins when you press the button below. Nothing has changed yet.")
        card = tk.Frame(page, bg=self.COLORS["paper2"], highlightbackground=self.COLORS["line"], highlightthickness=1)
        card.pack(fill="x", pady=(26, 8))
        self.review_vars = {}
        for key, label in [("resolution", "Virtual display"), ("audio", "Audio")]:
            row = tk.Frame(card, bg=self.COLORS["paper2"])
            row.pack(fill="x", padx=20, pady=13)
            tk.Label(row, text=label, bg=self.COLORS["paper2"], fg=self.COLORS["soft"], font=("TkDefaultFont", 9)).pack(side="left")
            variable = tk.StringVar()
            self.review_vars[key] = variable
            tk.Label(row, textvariable=variable, bg=self.COLORS["paper2"], fg=self.COLORS["ink"], font=("TkDefaultFont", 9, "bold")).pack(side="right")
        self.update_review()
        self.make_label(page, "Install creates the Dual Screen Mode shortcut and the Dual Screen Mode Settings app. Sunshine, Moonlight, krfb, and backups remain available after uninstall.", size=10, color=self.COLORS["soft"], wrap=680).pack(anchor="w", pady=(23, 0))

    def build_progress(self):
        page = self.new_page()
        self.heading(page, "Step 6 · Setting things up", "Installing Dual Screen Mode.", "The setup will show each task as it finishes.")
        self.progress_detail = tk.Label(page, textvariable=self.progress_detail_var, bg=self.COLORS["paper"], fg=self.COLORS["soft"], font=("TkDefaultFont", 10), anchor="w")
        self.progress_detail.pack(anchor="w", pady=(18, 8))
        self.progress_rows = []
        items = [("Check the host environment", "KDE Plasma and Wayland"), ("Prepare the virtual display", "krfb-virtualmonitor"), ("Prepare Sunshine", "Capture, touch routing, and audio"), ("Apply KDE capture permission", "User-level setting"), ("Create the shortcuts", "Dual Screen Mode and Dual Screen Mode Settings")]
        for index, (title, sub) in enumerate(items):
            row = tk.Frame(page, bg=self.COLORS["paper2"], highlightbackground=self.COLORS["line"], highlightthickness=1)
            row.pack(fill="x", pady=5)
            dot = tk.Label(row, text=str(index + 1), width=2, bg=self.COLORS["paper2"], fg=self.COLORS["soft"], font=("TkDefaultFont", 10, "bold"))
            dot.pack(side="left", padx=12, pady=12)
            text = tk.Frame(row, bg=self.COLORS["paper2"])
            text.pack(side="left", fill="x", expand=True, pady=10)
            tk.Label(text, text=title, bg=self.COLORS["paper2"], fg=self.COLORS["ink"], font=("TkDefaultFont", 10, "bold"), anchor="w").pack(anchor="w")
            tk.Label(text, text=sub, bg=self.COLORS["paper2"], fg=self.COLORS["soft"], font=("TkDefaultFont", 9), anchor="w").pack(anchor="w")
            status = tk.Label(row, text="Waiting", bg=self.COLORS["paper2"], fg=self.COLORS["soft"], font=("TkDefaultFont", 9))
            status.pack(side="right", padx=14)
            self.progress_rows.append((row, dot, status))

    def build_complete(self):
        page = self.new_page()
        self.heading(page, "Step 7 · Complete", "Setup complete. Give it a try!", "Double-click Dual Screen Mode to create the wireless virtual display. Moonlight is installed separately on the handheld and pairs with Sunshine manually.")
        card = tk.Frame(page, bg=self.COLORS["paper2"], highlightbackground=self.COLORS["line"], highlightthickness=1)
        card.pack(fill="x", pady=(26, 8))
        tk.Label(card, text="✓", bg=self.COLORS["paper2"], fg=self.COLORS["good"], font=("TkDefaultFont", 32, "bold")).pack(side="right", padx=28, pady=27)
        text = tk.Frame(card, bg=self.COLORS["paper2"])
        text.pack(side="left", fill="both", expand=True, padx=20, pady=20)
        tk.Label(text, text="Your Dual Screen Mode shortcuts are ready.", bg=self.COLORS["paper2"], fg=self.COLORS["blue_bright"], font=("TkDefaultFont", 10, "bold"), anchor="w").pack(anchor="w")
        tk.Label(text, text="Dual Screen Mode turns the virtual display on or off. Dual Screen Mode Settings lets you change options or remove the project.", bg=self.COLORS["paper2"], fg=self.COLORS["soft"], font=("TkDefaultFont", 9), wraplength=510, justify="left", anchor="w").pack(anchor="w", pady=(7, 0))
        tk.Label(page, textvariable=self.test_result_var, bg=self.COLORS["paper"], fg=self.COLORS["good"], font=("TkDefaultFont", 9), justify="left", anchor="w", wraplength=680).pack(anchor="w", pady=(22, 0))
        self.make_label(page, "Open Moonlight on the handheld, choose the already-paired host, and follow its normal Sunshine pairing flow if needed. If KDE needs a refresh for the new capture permission, log out and back in or restart the host computer.", size=10, color=self.COLORS["soft"], wrap=680).pack(anchor="w", pady=(22, 0))

    def resolution_changed(self, _event=None):
        if self.resolution_var.get() == "Custom":
            self.custom_resolution.pack(side="left", padx=10)
        else:
            self.custom_resolution.pack_forget()
        self.update_review()

    def select_audio(self, value):
        self.audio_var.set(value)
        for key, button in self.audio_buttons.items():
            button.configure(bg="#24435e" if key == value else self.COLORS["paper2"])
        if hasattr(self, "audio_behavior_var"):
            self.audio_behavior_var.set({
                "host": "Sunshine audio streaming is disabled. Audio stays on the host.",
                "handheld": "Sunshine audio streaming is enabled. The host's current default output is muted for the session.",
                "both": "Both is work in progress. For now, it uses Handheld behavior: Sunshine audio streaming is enabled and the host's current default output is muted for the session.",
            }[value])
        self.update_review()

    def selected_resolution(self):
        value = self.resolution_var.get()
        if value == "Custom":
            value = self.custom_resolution.get().strip() or "1280x800"
        return value

    def update_review(self):
        if not hasattr(self, "review_vars"):
            return
        audio = {"host": "Host", "handheld": "Handheld", "both": "Both (work in progress; uses Handheld for now)"}[self.audio_var.get()]
        resolution = self.selected_resolution().replace("x", " × ") + " at 60 Hz"
        self.review_vars["resolution"].set(resolution)
        self.review_vars["audio"].set(audio)

    def show_page(self, index):
        self.page_index = index
        for page in self.pages:
            page.pack_forget()
        self.pages[index].pack(fill="both", expand=True)
        self.content_canvas.yview_moveto(0)
        for i, (dot, label, small) in enumerate(self.step_widgets):
            if i == index:
                dot.configure(bg=self.COLORS["cyan"], fg=self.COLORS["navy"])
                label.configure(fg="#d5ebff")
            elif i < index:
                dot.configure(bg=self.COLORS["rail"], fg=self.COLORS["blue_bright"])
                label.configure(fg=self.COLORS["blue_bright"])
            else:
                dot.configure(bg=self.COLORS["rail"], fg="#8493a4")
                label.configure(fg="#8493a4")
            small.configure(fg="#8493a4" if i <= index else "#718091")

        self.back_button.pack_forget()
        self.test_button.pack_forget()
        self.next_button.pack_forget()
        if index not in (0, 6):
            self.back_button.pack(side="left", padx=5)
        if index == 7:
            self.test_button.pack(side="left", padx=5)
        if index != 6:
            self.next_button.pack(side="left", padx=5)

        if index == 0:
            self.next_button.configure(text="Begin setup", state="normal")
            self.footer_note.configure(text="No changes are made until the review step.")
            self.status_label.configure(text="Ready to set up", fg=self.COLORS["good"])
        elif index == 5:
            self.next_button.configure(text="Install Dual Screen Mode", state="normal")
            self.footer_note.configure(text="Nothing has changed yet.")
            self.status_label.configure(text="Ready to install", fg=self.COLORS["good"])
        elif index == 6:
            self.status_label.configure(text="Setting things up", fg=self.COLORS["warning"])
            self.footer_note.configure(text="Please keep this window open while setup runs.")
        elif index == 7:
            self.next_button.configure(text="Done", state="normal")
            self.footer_note.configure(text="Easy to uninstall later.")
            self.status_label.configure(text="Ready to connect", fg=self.COLORS["good"])
        else:
            self.next_button.configure(text="Continue", state="normal")
            self.footer_note.configure(text="Moonlight is installed separately on the handheld.")
            self.status_label.configure(text="Ready to set up", fg=self.COLORS["good"])

        if index == 1 and not self.check_started:
            self.check_started = True
            self.run_host_check()

    def next_page(self):
        if self.page_index == 1 and self.krfb_missing:
            self.check_status_var.set("krfb is still missing. Install it in Konsole, then click Check again.")
            return
        if self.page_index == 5:
            self.start_install()
        elif self.page_index == 7:
            self.destroy()
        elif self.page_index < 7:
            self.show_page(self.page_index + 1)

    def previous_page(self):
        if self.page_index > 0 and self.page_index not in (6, 7):
            self.show_page(self.page_index - 1)

    def run_host_check(self):
        def worker():
            try:
                result = subprocess.run(["bash", str(SETUP_SCRIPT), "--check"], capture_output=True, text=True, env=os.environ.copy(), timeout=30)
                self.events.put(("check", result.returncode, result.stdout + result.stderr))
            except Exception as exc:
                self.events.put(("check", 1, str(exc)))
        threading.Thread(target=worker, daemon=True).start()
        self.after(100, self.poll_events)

    def check_krfb(self):
        self.check_started = False
        self.check_status_var.set("Checking for krfb-virtualmonitor...")
        self.run_host_check()

    def open_krfb_terminal(self):
        if not shutil.which("konsole"):
            messagebox.showerror(
                "Konsole not found",
                "Konsole is needed to install krfb. Open a terminal manually and install the KDE krfb package, then return and click Check again.",
                parent=self,
            )
            return

        root_script = """set -u
if command -v steamos-readonly >/dev/null 2>&1; then
    steamos-readonly disable || exit 1
    trap 'steamos-readonly enable' EXIT
    pacman-key --init || exit 1
    pacman-key --populate archlinux holo || exit 1
fi
pacman -S --needed krfb
status=$?
if (( status == 0 )); then
    printf '\\nkrfb installation finished. Close this terminal, then click Check again in the wizard.\\n'
else
    printf '\\nkrfb installation failed. Review the message above, then close this terminal.\\n'
fi
read -r -p 'Press Enter to close this terminal... '
exit "$status"
"""
        terminal_script = "sudo bash -c " + shlex.quote(root_script)
        try:
            subprocess.Popen(
                ["konsole", "--separate", "-e", "bash", "-lc", terminal_script],
                start_new_session=True,
            )
            self.krfb_action_text.set("Konsole is open. Finish the package installation there, close it, then click Check again.")
        except OSError as exc:
            messagebox.showerror("Could not open Konsole", str(exc), parent=self)

    def start_install(self):
        if self.install_started:
            return
        resolution = self.selected_resolution()
        if not re.fullmatch(r"[0-9]{3,5}x[0-9]{3,5}", resolution):
            self.footer_note.configure(text="Enter a resolution such as 1280x800 before installing.")
            return
        self.install_started = True
        self.show_page(6)
        for row, dot, status in self.progress_rows:
            row.configure(bg=self.COLORS["paper2"])
            dot.configure(text="", fg=self.COLORS["soft"])
            status.configure(text="Waiting", fg=self.COLORS["soft"])
        self.output_lines = []
        command = ["bash", str(SETUP_SCRIPT), "--execute", "--resolution", resolution, "--audio", self.audio_var.get(), "--no-test"]
        environment = os.environ.copy()
        environment["DUAL_SCREEN_GUI"] = "1"

        def worker():
            try:
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=environment)
                self.install_process = process
                for line in process.stdout:
                    self.events.put(("line", line.rstrip()))
                code = process.wait()
                self.install_process = None
                self.events.put(("done", code))
            except Exception as exc:
                self.install_process = None
                self.events.put(("done", 1))
                self.events.put(("line", str(exc)))
        threading.Thread(target=worker, daemon=True).start()
        self.after(100, self.poll_events)

    def update_progress(self, index, line):
        for i, (row, dot, status) in enumerate(self.progress_rows):
            if i < index:
                row.configure(bg="#1d302f")
                dot.configure(text="✓", fg=self.COLORS["good"])
                status.configure(text="Done", fg=self.COLORS["good"])
            elif i == index:
                row.configure(bg="#1b3044")
                dot.configure(text=str(i + 1), fg=self.COLORS["cyan"])
                status.configure(text="Working", fg=self.COLORS["cyan"])
            else:
                row.configure(bg=self.COLORS["paper2"])
                dot.configure(text=str(i + 1), fg=self.COLORS["soft"])
                status.configure(text="Waiting", fg=self.COLORS["soft"])
        self.progress_detail_var.set(line)

    def handle_output(self, line):
        if not line:
            return
        self.output_lines.append(line)
        lower = line.lower()
        if "checking the host" in lower or "desktop session" in lower:
            self.update_progress(0, line)
        elif "virtual-display" in lower or "krfb" in lower:
            self.update_progress(1, line)
        elif "sunshine" in lower:
            self.update_progress(2, line)
        elif "permission" in lower or "kwin" in lower:
            self.update_progress(3, line)
        elif "shortcut" in lower or "saving display" in lower or "settings" in lower:
            self.update_progress(4, line)

    def poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "check":
                    output = event[2]
                    self.krfb_missing = "krfb-virtualmonitor is missing" in output
                    if self.krfb_missing:
                        self.check_status_var.set("The virtual-display package is missing. Follow the instructions below before continuing.")
                        self.krfb_action_text.set("Your password is entered in Konsole, not in Dual Screen Mode.")
                        self.krfb_action.pack(fill="x", pady=(16, 0))
                        if self.page_index == 1:
                            self.next_button.configure(state="disabled")
                    elif event[1] == 0:
                        self.check_status_var.set("This host is ready for the setup.")
                        self.krfb_action.pack_forget()
                        if self.page_index == 1:
                            self.next_button.configure(state="normal")
                    else:
                        self.check_status_var.set("The host check needs attention before installation.\n" + output.strip()[-240:])
                elif event[0] == "line":
                    self.handle_output(event[1])
                elif event[0] == "done":
                    self.finish_install(event[1])
        except queue.Empty:
            pass
        if self.install_started and self.page_index == 6 and not self.install_failed:
            self.after(120, self.poll_events)

    def finish_install(self, code):
        if code == 0:
            for row, dot, status in self.progress_rows:
                row.configure(bg="#1d302f")
                dot.configure(text="✓", fg=self.COLORS["good"])
                status.configure(text="Done", fg=self.COLORS["good"])
            self.progress_detail_var.set("Setup complete. Moving to the completion screen.")
            self.after(500, lambda: self.show_page(7))
        else:
            self.install_failed = True
            self.progress_detail_var.set("Setup stopped before it finished. Nothing else will run automatically.")
            self.next_button.pack(side="left", padx=5)
            self.next_button.configure(text="Close", command=self.destroy)
            self.footer_note.configure(text="Check the last message in the setup output.")

    def run_connection_test(self):
        if not TOGGLE_PATH.exists():
            self.test_result_var.set("The setup shortcut was not found. Run the installer again after checking the error.")
            return
        runtime = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "dual-screen-mode" / "active"
        if runtime.exists():
            self.test_result_var.set("Dual Screen Mode is already active, so the test left it alone.")
            return
        self.test_button.configure(state="disabled")
        self.test_result_var.set("Running the safe connection test...")

        def worker():
            try:
                first = subprocess.run([str(TOGGLE_PATH)], capture_output=True, text=True, timeout=30)
                if first.returncode != 0:
                    self.events.put(("test", "The virtual display could not be started. The setup is still installed."))
                    return
                time.sleep(4)
                if runtime.exists():
                    subprocess.run([str(TOGGLE_PATH)], capture_output=True, text=True, timeout=30)
                    self.events.put(("test", "Connection test finished. The virtual display was turned back off."))
                else:
                    self.events.put(("test", "The virtual display did not stay active long enough to test."))
            except Exception as exc:
                self.events.put(("test", "Connection test stopped: " + str(exc)))
        threading.Thread(target=worker, daemon=True).start()
        self.after(100, self.poll_test_events)

    def poll_test_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "test":
                    self.test_result_var.set(event[1])
                    self.test_button.configure(state="normal")
        except queue.Empty:
            self.after(100, self.poll_test_events)

    def close_window(self):
        if self.install_started and not self.install_failed and self.page_index == 6:
            if not messagebox.askyesno(
                "Stop setup?",
                "Setup is still running. Stop it now?\n\nPartial changes may remain, but you can safely run the installer again.",
                parent=self,
            ):
                return
            process = self.install_process
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
            self.install_failed = True
            self.destroy()
            return
        self.destroy()


if __name__ == "__main__":
    DualScreenWizard().mainloop()
