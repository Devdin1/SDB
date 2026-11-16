"""Presentation for the Supreme Deity launcher; never sends battle input."""
import re
import tkinter as tk
from tkinter import ttk
from utilities.supreme_deity_gui_theme import SilverPanel, DarkScrollbar, divider, sigil, diamond

BG = "#081321"
PANEL = "#0c1b2e"
EDGE = "#788cae"
TEXT = "#e4edf9"
MUTED = "#a2b6d5"
CYAN = "#50dcec"


class BattleView:
    def __init__(self, app, asset_dir):
        self.app = app
        self.phase = None
        self.turn = None
        self.reset_count = 0
        self.images = {}
        self.theme_images = {}
        self.target = tk.StringVar(value="Awaiting verification")
        self.phase_text = tk.StringVar(value="— / 6")
        self.turn_text = tk.StringVar(value="—")
        self.clears_text = tk.StringVar(value="0 / 1")
        self.resets = tk.StringVar(value="0")
        for name in ("odin", "freyr", "hel", "gawain", "crest"):
            path = asset_dir / (name + ".png")
            if path.is_file():
                self.images[name] = tk.PhotoImage(file=str(path))
        root = app.root
        root.title("Supreme Deity • Hell V1")
        # Floors match minsize below, so a small screen opens at a size that
        # actually fits instead of being forced wider than the display.
        width = min(1380, max(900, root.winfo_screenwidth() - 90))
        height = min(940, max(700, root.winfo_screenheight() - 100))
        root.geometry(f"{width}x{height}")
        root.minsize(900, 700)
        root.configure(background=BG)
        self._styles(root, asset_dir)
        outer = tk.Frame(root, bg=BG, padx=18, pady=10)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)
        self._header(outer)
        notebook = ttk.Notebook(outer, style="Hidden.TNotebook")
        notebook.grid(row=2, column=0, sticky="nsew")
        battle = tk.Frame(notebook, bg=BG, pady=8)
        display = tk.Frame(notebook, bg=BG, pady=8)
        notebook.add(battle, text="Battle")
        notebook.add(display, text="Display")
        self.notebook = notebook
        self._tabs(outer)
        self._battle(battle)
        self._display(display)
        app.status = tk.StringVar(value="Ready • Keep the game visible. Stop stops input.")
        app.status_label = ttk.Label(outer, textvariable=app.status, style="Muted.TLabel")
        app.status_label.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        app.clears.trace_add("write", lambda *_: self._clears())
        app.wins.trace_add("write", lambda *_: self._clears())

    def _styles(self, root, asset_dir):
        s = ttk.Style(root)
        s.theme_use("clam")
        for name in ("button", "button-hover", "button-disabled", "button-accent",
                     "button-accent-hover", "check-on", "check-off"):
            self.theme_images[name] = tk.PhotoImage(file=str(asset_dir / (name + ".png")))
        def button_element(name, normal, active):
            s.element_create(name, "image", self.theme_images[normal],
                             ("disabled", self.theme_images["button-disabled"]),
                             ("active", self.theme_images[active]), border=(16, 12, 16, 12), sticky="nsew")
            return [(name, {"sticky": "nsew", "children": [
                ("Button.padding", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})]})]
        s.layout("TButton", button_element("Silver.button", "button", "button-hover"))
        s.layout("Accent.TButton", button_element("Cyan.button", "button-accent", "button-accent-hover"))
        s.layout("Quiet.TButton", [("Button.padding", {"sticky": "nsew", "children": [("Button.label", {})]})])
        s.element_create("Cyan.check", "image", self.theme_images["check-off"],
                         ("selected", self.theme_images["check-on"]), sticky="w")
        s.layout("TCheckbutton", [("Checkbutton.padding", {"sticky": "nsew", "children": [
            ("Cyan.check", {"side": "left", "sticky": "w"}),
            ("Checkbutton.label", {"side": "left", "sticky": "w"})]})])
        s.configure(".", background=BG, foreground=TEXT, font=("Segoe UI", 9))
        s.configure("TFrame", background=BG)
        s.configure("TLabel", background=BG)
        s.configure("Muted.TLabel", foreground=MUTED)
        s.configure("Success.TLabel", foreground="#63e1b1")
        s.configure("Error.TLabel", foreground="#ff7b86")
        s.configure("TButton", background="#172b43", foreground=TEXT,
                    padding=(12, 2), borderwidth=0, bordercolor=EDGE, relief="flat")
        s.map("TButton", background=[("active", "#243e5c"), ("disabled", "#101f31")],
              foreground=[("disabled", "#667994")])
        s.configure("Accent.TButton", background="#087d96", foreground="#ffffff",
                    font=("Segoe UI", 11, "bold"), bordercolor=CYAN)
        s.map("Accent.TButton", background=[("active", "#119bb2"), ("disabled", "#173047")])
        s.configure("Quiet.TButton", background=BG, foreground=MUTED,
                    borderwidth=0, padding=(8, 4))
        s.map("Quiet.TButton", background=[("active", "#13273c")], foreground=[("active", TEXT)])
        s.configure("Admin.TButton", background="#492639", foreground="#ffb9c2")
        s.configure("TSpinbox", fieldbackground="#102137", foreground=TEXT,
                    arrowcolor=CYAN, bordercolor="#526580", lightcolor="#526580",
                    darkcolor="#526580", arrowsize=14, padding=4)
        s.configure("TCheckbutton", background=PANEL, foreground=TEXT)
        s.map("TCheckbutton", background=[("active", PANEL)])
        s.configure("TCombobox", foreground=TEXT, fieldbackground="#102137", background=PANEL,
                    arrowcolor=CYAN, bordercolor="#526580", padding=3)
        s.map("TCombobox", fieldbackground=[("readonly", "#102137")],
              foreground=[("readonly", TEXT)], selectbackground=[("readonly", "#102137")])
        root.option_add("*TCombobox*Listbox.background", "#102137")
        root.option_add("*TCombobox*Listbox.foreground", TEXT)
        s.configure("Vertical.TScrollbar", background="#344563", troughcolor=PANEL,
                    borderwidth=0, bordercolor=PANEL, lightcolor="#344563", darkcolor="#344563", width=8)
        s.layout("Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
            ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nsew"})]})])
        s.configure("TNotebook", background=BG, borderwidth=0, bordercolor=BG,
                    lightcolor=BG, darkcolor=BG, tabmargins=(0, 0, 0, 0))
        s.configure("TNotebook.Tab", background=BG, foreground=MUTED,
                    padding=(26, 8), borderwidth=0, bordercolor=BG, lightcolor=BG, darkcolor=BG)
        s.map("TNotebook.Tab", background=[("selected", "#122a40")],
              foreground=[("selected", CYAN)])
        s.layout("Hidden.TNotebook", [("Notebook.client", {"sticky": "nsew"})])
        s.layout("Hidden.TNotebook.Tab", [])

    def _tabs(self, parent):
        tabs = tk.Canvas(parent, height=34, bg=BG, highlightthickness=0)
        tabs.grid(row=1, column=0, sticky="ew")
        def paint(_=None):
            tabs.delete("all")
            tabs.create_line(0, 33, tabs.winfo_width(), 33, fill="#354a65")
            selected = self.notebook.index(self.notebook.select())
            for i, title in enumerate(("Battle", "Display")):
                x = 64 + 126*i
                tabs.create_text(x, 14, text=title, fill=CYAN if i == selected else MUTED,
                                 font=("Segoe UI", 10, "bold" if i == selected else "normal"), tags=f"tab{i}")
                tabs.create_rectangle(x-56, 0, x+56, 32, fill="", outline="", tags=f"tab{i}")
                tabs.tag_bind(f"tab{i}", "<Button-1>", lambda e, index=i: self.notebook.select(index))
                tabs.tag_bind(f"tab{i}", "<Enter>", lambda e: tabs.configure(cursor="hand2"))
                tabs.tag_bind(f"tab{i}", "<Leave>", lambda e: tabs.configure(cursor=""))
                if i == selected:
                    tabs.create_line(x-55, 32, x+55, 32, fill=CYAN, width=2)
        tabs.bind("<Configure>", paint)
        self.notebook.bind("<<NotebookTabChanged>>", paint)

    def label(self, parent, text=None, *, variable=None, size=9, color=TEXT, bold=False):
        return tk.Label(parent, text=text, textvariable=variable, bg=parent.cget("bg"),
                        fg=color, font=("Segoe UI", size, "bold" if bold else "normal"), anchor="w")

    def panel(self, parent, title=None, padx=14, pady=10):
        border = SilverPanel(parent, padx=padx, pady=pady)
        inner = border.content
        if title:
            self.label(inner, title, size=11, color="#b7cdf3", bold=True).pack(anchor="w", pady=(0, 4))
        return border, inner

    def _header(self, parent):
        head = tk.Canvas(parent, bg=BG, height=96, highlightthickness=0)
        head.grid(row=0, column=0, sticky="ew")
        self.app.admin_button = ttk.Button(head, text="♢  Restart as administrator",
                                           style="Quiet.TButton", command=self.app.restart_admin)
        def paint(event):
            head.delete("all")
            for y in range(96):
                f = 1-abs(y-40)/70
                color = "#%02x%02x%02x" % (8+int(3*f), 19+int(7*f), 33+int(13*f))
                head.create_line(0, y, event.width, y, fill=color)
            sigil(head, 238, 43, 60)
            head.create_line(24, 9, event.width-200, 9, fill="#2c4360")
            diamond(head, event.width*.58, 9, 5, "#91a4c2")
            head.create_line(16, 14, 16, 66, fill="#3e577a")
            diamond(head, 16, 32, 5, "#9bacc8")
            head.create_text(34, 39, anchor="w", text="S U P R E M E   D E I T Y",
                             fill=TEXT, font=("Georgia", 22))
            head.create_text(36, 77, anchor="w", text=f"{self.app.difficulty.get()} V1", fill=MUTED, font=("Consolas", 10))
            if "crest" in self.images:
                head.create_image(event.width-84, 48, image=self.images["crest"])
            head.create_window(event.width-187, 52, anchor="e", window=self.app.admin_button)
        head.bind("<Configure>", paint)
        self.header = head

    def _battle(self, parent):
        a = self.app
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        border, strip = self.panel(parent, "Current battle", pady=6)
        border.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        for title, value, width in (("Phase", self.phase_text, 5), ("Turn", self.turn_text, 3)):
            cell = tk.Frame(strip, bg=PANEL)
            cell.pack(side="left", padx=(0, 20))
            self.label(cell, title, color=MUTED).pack(anchor="w")
            tk.Label(cell, textvariable=value, bg=PANEL, fg=CYAN,
                     font=("Segoe UI", 19, "bold"), width=width, anchor="w").pack(anchor="w")
        cell = tk.Frame(strip, bg=PANEL)
        cell.pack(side="left")
        self.label(cell, "Target", color=MUTED).pack(anchor="w")
        target_row = tk.Frame(cell, bg=PANEL)
        target_row.pack(anchor="w", pady=(6, 7))
        self.target_icon = tk.Canvas(target_row, bg=PANEL, width=23, height=23, highlightthickness=0)
        self.target_icon.pack(side="left", padx=(0, 6))
        def paint_target(*_):
            icon = self.target_icon
            icon.delete("all")
            verified = self.target.get() == "Right target verified"
            color = CYAN if verified else "#778da9"
            icon.create_oval(2, 2, 21, 21, outline=color, width=2)
            if verified:
                icon.create_line(6, 11, 10, 15, 17, 7, fill=color, width=2)
            else:
                icon.create_oval(10, 10, 13, 13, fill=color, outline="")
        self.target.trace_add("write", paint_target)
        paint_target()
        self.target_label = self.label(target_row, variable=self.target, size=9, color=MUTED)
        self.target_label.pack(side="left")
        self.progress = tk.Canvas(strip, bg=PANEL, height=66, width=440, highlightthickness=0)
        self.progress.pack(side="right", fill="x", expand=True, padx=(20, 0))
        self.progress.bind("<Configure>", lambda _: self._progress())
        body = tk.Frame(parent, bg=BG)
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=3, uniform="body")
        body.columnconfigure(1, weight=2, minsize=340, uniform="body")
        body.rowconfigure(0, weight=1)
        log_border, log_panel = self.panel(body, padx=12)
        log_border.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        log_head = tk.Frame(log_panel, bg=PANEL)
        log_head.pack(fill="x", pady=(0, 9))
        self.label(log_head, "Activity log", size=12, color="#b7cdf3", bold=True).pack(side="left")
        self.label(log_head, "●", color="#54deb3", size=8).pack(side="right", padx=(7, 0))
        self.label(log_head, "Live output", color=MUTED).pack(side="right")
        divider(log_panel).pack(fill="x", pady=(0, 4))
        text_panel = tk.Frame(log_panel, bg=PANEL)
        text_panel.pack(fill="both", expand=True)
        a.log = tk.Text(text_panel, height=12, width=35, wrap="word", state="disabled",
                             font=("Consolas", 10), background="#0b192a", foreground=TEXT,
                             insertbackground=CYAN, relief="flat", borderwidth=0, highlightthickness=0,
                             selectbackground="#264565", padx=8, pady=8, spacing1=3, spacing3=3)
        scrollbar = DarkScrollbar(text_panel, command=a.log.yview)
        scrollbar.pack(side="right", fill="y", padx=(5, 0))
        a.log.configure(yscrollcommand=scrollbar.set)
        for tag, color in (("success", "#60e1b2"), ("warning", "#bdadf1"), ("error", "#ff7b86"),
                           ("phase", CYAN), ("turn", "#ab9bfa")):
            a.log.tag_configure(tag, foreground=color)
        a.log.pack(fill="both", expand=True)
        a.log.tag_configure("timestamp", foreground="#8b9fbf")
        a.log.tag_configure("row_even", background="#0e2035")
        right = tk.Frame(body, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        setup_border, setup = self.panel(right, "Run setup", pady=6)
        setup_border.grid(row=0, column=0, sticky="nsew")
        a.difficulty = tk.StringVar(value="Hell")
        self.difficulty_combo = ttk.Combobox(setup, textvariable=a.difficulty,
                                              values=("Hell", "Hard"), state="readonly", width=7)
        self.difficulty_combo.place(relx=1, y=-2, anchor="ne")
        def difficulty_changed(*_):
            a.root.title(f"Supreme Deity • {a.difficulty.get()} V1")
            self.header.event_generate("<Configure>", width=self.header.winfo_width(), height=self.header.winfo_height())
        a.difficulty.trace_add("write", difficulty_changed)
        options = tk.Frame(setup, bg=PANEL)
        options.pack(fill="x", pady=(0, 3))
        a.clears = tk.StringVar(value="1")
        a.x3 = tk.BooleanVar(value=True)
        self.label(options, "Clears to run").pack(side="left")
        ttk.Spinbox(options, from_=1, to=999, width=6, textvariable=a.clears).pack(side="left", padx=16)
        a.x3_checkbox = ttk.Checkbutton(options, text="x3", variable=a.x3)
        a.x3_checkbox.pack(side="left")
        divider(setup).pack(fill="x", pady=(1, 3))
        self.label(setup, "Team & links", size=10, color="#b7cdf3", bold=True).pack(anchor="w", pady=(0, 3))
        team = tk.Frame(setup, bg=PANEL)
        team.pack(fill="x")
        team_head = tk.Frame(team, bg=PANEL)
        team_head.pack(fill="x", pady=(0, 2))
        team_head.configure(height=19)
        self.label(team_head, "Unit", color=MUTED, size=8).place(x=100, y=0)
        self.label(team_head, "Link", color=MUTED, size=8).place(relx=.6, y=0)
        entries = (("odin", "Odin", "Sabunak"), ("freyr", "LR Freyr", "Red Tarmiel"),
                   ("hel", "Green Hel", "Red Sariel"), ("gawain", "Gawain", "Mael"))
        for index, (key, unit, link) in enumerate(entries, 1):
            row = SilverPanel(team, padx=7, pady=2)
            row.pack(fill="x", pady=1)
            inner = row.content
            inner.columnconfigure(2, weight=1, uniform="team")
            inner.columnconfigure(4, weight=1, uniform="team")
            tk.Label(inner, text=str(index), width=2, bg="#10243a", fg=TEXT,
                     font=("Segoe UI", 8), highlightthickness=1,
                     highlightbackground="#536b8c").grid(row=0, column=0, padx=(0, 7))
            if key in self.images:
                tk.Label(inner, image=self.images[key], bg=PANEL, bd=0).grid(row=0, column=1)
            self.label(inner, unit).grid(row=0, column=2, sticky="w", padx=8)
            tk.Frame(inner, bg="#344b69", width=1).grid(row=0, column=3, sticky="ns", padx=(4, 8))
            self.label(inner, link, color=TEXT).grid(row=0, column=4, sticky="w", padx=(2, 0))
        details = tk.Frame(setup, bg=PANEL)
        details.pack(fill="x", pady=(7, 0))
        details.columnconfigure(0, weight=3)
        details.columnconfigure(1, weight=1)
        gear_border = SilverPanel(details, padx=10, pady=6)
        gear_border.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        gear = gear_border.content
        self.label(gear, "Gear & food", color="#b7cdf3", bold=True).pack(anchor="w", pady=(0, 3))
        tk.Label(gear, text="C8: Everyone HP/DEF\nOdin / Gawain: ATK/CRIT optional\n"
                 "C7: Gawain / Odin ATK/CRIT\nOthers HP/DEF · ATK food", font=("Segoe UI", 8),
                 bg=PANEL, fg=MUTED, justify="left", anchor="w", padx=0, pady=0).pack(anchor="w")
        card_border = SilverPanel(details, padx=10, pady=6)
        card_border.grid(row=0, column=1, sticky="nsew")
        cards = card_border.content
        self.label(cards, "Card set", color="#b7cdf3", bold=True).pack(anchor="w", pady=(0, 7))
        card_body = tk.Frame(cards, bg=PANEL)
        card_body.pack(expand=True)
        icon = tk.Canvas(card_body, width=35, height=40, bg=PANEL, highlightthickness=0)
        for offset in (8, 4, 0):
            icon.create_polygon(5+offset, 8-offset*.4, 26+offset, 4+offset*.3,
                                28+offset, 33, 8+offset, 37, fill=PANEL, outline="#a7bddb", width=1)
        icon.create_text(18, 21, text="✧", fill="#b7cdef", font=("Georgia", 17))
        icon.pack(side="left", padx=(0, 4))
        self.label(card_body, "No. 78", color=TEXT, size=15, bold=True).pack(side="left")
        stat_border, stats = self.panel(right, pady=6)
        stat_border.grid(row=1, column=0, sticky="ew", pady=(7, 0))
        self.label(stats, "Run statistics", color="#b7cdf3", bold=True).pack(anchor="w", pady=(0, 3))
        stat_row = tk.Frame(stats, bg=PANEL)
        stat_row.pack(fill="x")
        for title, var in (("Clears", self.clears_text), ("Wins", a.wins), ("Resets", self.resets), ("Uptime", a.elapsed)):
            cell = tk.Frame(stat_row, bg=PANEL)
            cell.pack(side="left", fill="x", expand=True)
            self.label(cell, title, size=8, color=MUTED).pack(anchor="w")
            self.label(cell, variable=var, size=14, color=CYAN, bold=True).pack(anchor="w")
        footer = tk.Frame(parent, bg=BG)
        footer.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        for attr, text, command, style in (
                ("start_button", "▶  Start", lambda: a.start(True), "Accent.TButton"),
                ("pause_button", "Pause", a.toggle_pause, "TButton"),
                ("stop_button", "Stop", a.stop, "TButton")):
            button = ttk.Button(footer, text=text, command=command, style=style, width=12,
                                state="normal" if attr == "start_button" else "disabled")
            button.pack(side="left", padx=(0, 8))
            setattr(a, attr, button)
        ttk.Button(footer, text="Open logs", command=a.open_logs).pack(side="right")
        a.resize_button = ttk.Button(footer, text="Resize game", command=lambda: a.start(False, resize=True))
        a.resize_button.pack(side="right", padx=8)
        divider(footer, BG).pack(fill="x", expand=True, side="left", padx=22, pady=12)

    def _display(self, parent):
        a = self.app
        border, content = self.panel(parent, padx=30, pady=28)
        border.pack(fill="both", expand=True)
        divider(content).pack(fill="x", padx=100, pady=(0, 12))
        tk.Label(content, text="Display settings", font=("Georgia", 23), bg=PANEL,
                 fg=TEXT).pack(anchor="center", pady=(6, 8))
        self.label(content, "Choose a display preset for the game.", color=MUTED).pack(anchor="center")
        presets = tk.Frame(content, bg=PANEL)
        presets.pack(expand=True, pady=24)
        for index, (title, resolution, attr) in enumerate((
                ("2560 × 1440", (2560, 1440), "display_button"),
                ("1920 × 1080", (1920, 1080), "lower_display_button"))):
            card, inner = self.panel(presets, padx=38, pady=25)
            card.grid(row=0, column=index, padx=12)
            icon = tk.Canvas(inner, bg=PANEL, width=110, height=75, highlightthickness=0)
            icon.create_rectangle(12, 7, 98, 58, outline="#a2cff1", width=2)
            icon.create_line(55, 59, 55, 68, fill="#a2cff1", width=3)
            icon.create_line(35, 69, 75, 69, fill="#a2cff1", width=3)
            icon.pack(pady=(0, 14))
            tk.Label(inner, text=title, font=("Georgia", 19), bg=PANEL,
                     fg=TEXT).pack(anchor="center")
            self.label(inner, "125% scaling", color=MUTED).pack(anchor="center", pady=(6, 20))
            button = ttk.Button(inner, text="Apply preset", command=lambda r=resolution: a.set_display(r))
            button.pack(fill="x")
            setattr(a, attr, button)
        a.restore_display_button = ttk.Button(content, text="Restore display", width=23, command=a.restore_display)
        a.restore_display_button.pack(pady=(0, 8))
        self.label(content, "Return to your previous display settings.", color=MUTED).pack(anchor="center")
        tools = tk.Frame(content, bg=PANEL)
        tools.pack(fill="x", pady=(24, 0))
        a.check_button = ttk.Button(tools, text="Check installation", command=lambda: a.start(False))
        a.check_button.pack(side="left")
        a.update_button = ttk.Button(tools, text="Update from GitHub", command=a.request_update)
        a.update_button.pack(side="right")

    def _clears(self):
        self.clears_text.set(f"{self.app.wins.get()} / {self.app.clears.get()}")

    def _progress(self):
        c = self.progress
        c.delete("all")
        width = max(240, c.winfo_width())
        points = [34 + i * (width - 68) / 5 for i in range(6)]
        c.create_line(points[0], 23, points[-1], 23, fill="#354a66", width=2)
        if self.phase:
            c.create_line(points[0], 23, points[self.phase-1], 23, fill=CYAN, width=2)
        for i, x in enumerate(points, 1):
            active = self.phase == i
            color = CYAN if self.phase and i <= self.phase else "#8396b7"
            if active:
                c.create_oval(x-22, 1, x+22, 45, fill=PANEL, outline="#214b68", width=2)
                c.create_oval(x-19, 4, x+19, 42, outline="#38758c", width=1)
            c.create_oval(x-15, 8, x+15, 38, fill=CYAN if active else PANEL, outline=color, width=2)
            c.create_text(x, 23, text=str(i), fill="#0b2032" if active else TEXT, font=("Segoe UI", 9))
            c.create_text(x, 57, text=f"Phase {i}", fill=color, font=("Segoe UI", 9))

    def reset(self):
        self.phase = self.turn = None
        self.phase_text.set("— / 6")
        self.turn_text.set("—")
        self.target.set("Awaiting verification")
        self.target_label.configure(fg=MUTED)
        self._progress()

    def consume(self, text):
        """Display only worker-reported context, never invent battle state."""
        if "[ABORT]" in text:
            self.reset_count += 1
            self.resets.set(str(self.reset_count))
        if "Phase counter: 0/6" in text:
            self.reset()
            return
        match = re.search(r"Phase\s+(?:counter:\s*|\()?([1-6])(?:/6\))?", text)
        turn = re.search(r"\b[Tt]urn\s+(\d+)", text)
        if match:
            phase = int(match.group(1))
            new_turn = int(turn.group(1)) if turn else (None if phase != self.phase else self.turn)
            if phase != self.phase or new_turn != self.turn:
                self.target.set("Awaiting verification")
                self.target_label.configure(fg=MUTED)
            self.phase, self.turn = phase, new_turn
            self.phase_text.set(f"{phase} / 6")
            self.turn_text.set(str(new_turn) if new_turn else "—")
            self._progress()
        if "far-right selection visually verified" in text:
            self.target.set("Right target verified")
            self.target_label.configure(fg=CYAN)
        if "Can not verify current phase" in text or "[ABORT]" in text:
            self.reset()
