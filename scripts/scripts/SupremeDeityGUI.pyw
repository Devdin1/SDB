"""Small standard-library launcher. Importing this file never starts farming."""
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText

ROOT = Path(__file__).resolve().parent


def resize_game():
    """Reuse AutoFarmers' utility with the successful SD run's client size."""
    import ctypes
    # Match the live worker's pyautogui DPI setup before using window coordinates.
    ctypes.windll.user32.SetProcessDPIAware()
    from utilities.capture_window import capture_window, resize_7ds_window
    if resize_7ds_window(width=518, height=922):
        screenshot, _ = capture_window(client_area=True)
        height, width = screenshot.shape[:2]
        if abs(width-518) <= 1 and abs(height-922) <= 1:
            print(f"[Launcher] Game area verified: {width} × {height} pixels.", flush=True)
            return 0
        print(f"[Launcher] Resize did not reach the target: got {width} × {height}, expected 518 × 922.", flush=True)
        return 1
    print("[Launcher] Resize failed. Open 7DS; if it runs as administrator, restart this launcher as administrator.", flush=True)
    return 1


def python_console():
    configured = ROOT.parent / "supreme-deity-python.txt"
    if configured.is_file():
        path = Path(configured.read_text(encoding="utf-8-sig").strip())
        if not path.is_absolute() or not path.is_file():
            raise OSError(f"Configured Python was not found: {path}\nUpdate {configured}")
        return str(path)
    current = Path(sys.executable)
    return str(current.with_name("python.exe") if current.name.lower() == "pythonw.exe" else current)


class Launcher:
    def __init__(self, root):
        self.root = root
        self.process = None
        self.resize_process = None
        self.display_job = None
        self.update_job = None
        self.display_completion = None
        from utilities.supreme_deity_display import DisplaySession
        self.display_session = DisplaySession(ROOT / "config" / "supreme_deity" / "display-original.json")
        self.messages = queue.Queue()
        self.stop_path = None
        self.pause_path = None
        self.paused_at = None
        self.live_active = False
        self.admin_required = False
        self.stopping_at = None
        self.closing = False
        self.run_started = None
        self.elapsed_seconds = 0
        self.wins = tk.StringVar(value="0")
        self.elapsed = tk.StringVar(value="00:00:00")
        root.title("Supreme Deity • Hell V1")
        root.geometry("820x730")
        root.minsize(760, 670)
        root.configure(background="#101725")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(".", background="#101725", foreground="#e5eaf3", font=("Segoe UI", 10))
        style.configure("TFrame", background="#101725")
        style.configure("TLabel", background="#101725")
        style.configure("Muted.TLabel", foreground="#9aabc2")
        style.configure("Success.TLabel", foreground="#80d7ac")
        style.configure("Title.TLabel", foreground="#f2ce84", font=("Segoe UI", 23, "bold"))
        style.configure("Card.TFrame", background="#1c273a")
        style.configure("Card.TLabel", background="#1c273a", foreground="#c7d4e8")
        style.configure("Unit.TLabel", background="#1c273a", foreground="#f2ce84", font=("Segoe UI", 11, "bold"))
        style.configure("Stat.TLabel", background="#1c273a", foreground="#f2ce84", font=("Segoe UI", 21, "bold"))
        style.configure("TButton", background="#29384f", padding=(11, 9), borderwidth=0)
        style.map("TButton", background=[("active", "#3a506c"), ("disabled", "#1d2839")], foreground=[("disabled", "#6c7a90")])
        style.configure("Accent.TButton", background="#deb96e", foreground="#142035")
        style.map("Accent.TButton", background=[("active", "#f2ce84"), ("disabled", "#29384f")], foreground=[("disabled", "#6c7a90")])
        style.configure("Admin.TButton", background="#9b3546", foreground="#ffffff")
        style.map("Admin.TButton", background=[("active", "#bb4559")], foreground=[("active", "#ffffff")])
        style.configure("Error.TLabel", foreground="#ff7b86")
        style.configure("TSpinbox", fieldbackground="#1c273a", foreground="#e5eaf3", arrowcolor="#f2ce84", padding=5)
        panel = ttk.Frame(root, padding=24)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="SUPREME DEITY", style="Title.TLabel").pack(anchor="w")
        ttk.Label(panel, text="HELL  /  Odin · LR Freyr · green Hel · Gawain", padding=(0, 7), style="Muted.TLabel").pack(anchor="w")
        links = ttk.Frame(panel, style="Card.TFrame", padding=(14, 10))
        links.pack(fill="x", pady=(5, 8))
        ttk.Label(links, text="UNIT LINKS", style="Card.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))
        for column, (unit, link) in enumerate((("Odin", "Sabunak"), ("LR Freyr", "Red Tarmiel"),
                                               ("Hel", "Red Sariel"), ("Gawain", "Mael"))):
            links.columnconfigure(column, weight=1, uniform="links")
            ttk.Label(links, text=unit, style="Unit.TLabel").grid(row=1, column=column, sticky="w")
            ttk.Label(links, text=link, style="Card.TLabel").grid(row=2, column=column, sticky="w", pady=(3, 0))
        notes = ttk.Frame(panel, style="Card.TFrame", padding=(14, 10))
        notes.pack(fill="x", pady=(5, 12))
        for text in ("C8 ~ Everyone HP/DEF; Odin and Gawain can be ATK/CRIT",
                     "C7 ~ Gawain wants ATK/CRIT; others HP/DEF · ATK food", "Cardset No. 78"):
            ttk.Label(notes, text=text, style="Card.TLabel", padding=(0, 2)).pack(anchor="w")
        stats = ttk.Frame(panel, style="Card.TFrame", padding=(14, 10))
        stats.pack(fill="x")
        for column, (label, variable) in enumerate((("WINS THIS RUN", self.wins), ("ELAPSED TIME", self.elapsed))):
            stats.columnconfigure(column, weight=1)
            ttk.Label(stats, text=label, style="Card.TLabel").grid(row=0, column=column, sticky="w")
            ttk.Label(stats, textvariable=variable, style="Stat.TLabel").grid(row=1, column=column, sticky="w")
        options = ttk.Frame(panel, padding=(0, 12))
        options.pack(fill="x")
        self.clears = tk.StringVar(value="1")
        self.x3 = tk.BooleanVar(value=True)
        ttk.Label(options, text="Clears").pack(side="left")
        ttk.Spinbox(options, from_=1, to=999, width=5, textvariable=self.clears).pack(side="left", padx=(6, 18))
        self.x3_checkbox = ttk.Checkbutton(options, text="x3", variable=self.x3)
        self.x3_checkbox.pack(side="left", padx=(14, 0))
        self.admin_button = ttk.Button(options, text="Restart as administrator", command=self.restart_admin)
        self.admin_button.pack(side="right")
        buttons = ttk.Frame(panel)
        buttons.pack(fill="x")
        self.start_button = ttk.Button(buttons, text="Start", style="Accent.TButton", command=lambda: self.start(True))
        self.start_button.pack(side="left")
        self.check_button = ttk.Button(buttons, text="Check installation", command=lambda: self.start(False))
        self.check_button.pack(side="left", padx=8)
        self.stop_button = ttk.Button(buttons, text="Stop", command=self.stop, state="disabled")
        self.stop_button.pack(side="left")
        self.pause_button = ttk.Button(buttons, text="Pause", command=self.toggle_pause, state="disabled")
        self.pause_button.pack(side="left", padx=(8, 0))
        self.resize_button = ttk.Button(buttons, text="Resize game", command=lambda: self.start(False, resize=True))
        self.resize_button.pack(side="left", padx=8)
        ttk.Button(buttons, text="Open logs", command=self.open_logs).pack(side="right")
        display_controls = ttk.Frame(panel)
        display_controls.pack(fill="x", pady=(8, 0))
        self.display_button = ttk.Button(display_controls, text="Set 2560 × 1440 / 125%", command=self.set_display)
        self.display_button.pack(side="left")
        self.lower_display_button = ttk.Button(display_controls, text="Set 1920 × 1080 / 125%", command=lambda: self.set_display((1920,1080)))
        self.lower_display_button.pack(side="left", padx=8)
        self.restore_display_button = ttk.Button(display_controls, text="Restore display", command=self.restore_display)
        self.restore_display_button.pack(side="left", padx=8)
        update_controls = ttk.Frame(panel)
        update_controls.pack(fill="x", pady=(6, 0))
        self.update_button = ttk.Button(update_controls, text="Update from GitHub", command=self.request_update)
        self.update_button.pack(side="left")
        self.status = tk.StringVar(value="Ready • Keep the game visible. Stop / F8 stops input.")
        self.status_label = ttk.Label(panel, textvariable=self.status, padding=(0, 10))
        self.status_label.pack(anchor="w")
        self.log = ScrolledText(panel, height=12, wrap="word", state="disabled", font=("Consolas", 10),
                               background="#0b111d", foreground="#c7d4e8", insertbackground="#f2ce84",
                               relief="flat", borderwidth=0, padx=12, pady=10)
        self.log.tag_configure("success", foreground="#80d7ac")
        self.log.tag_configure("warning", foreground="#f2ce84")
        self.log.tag_configure("error", foreground="#ff7b86")
        self.log.tag_configure("phase", foreground="#81c7e8")
        self.log.tag_configure("turn", foreground="#c1a7ef")
        self.log.pack(fill="both", expand=True)
        root.protocol("WM_DELETE_WINDOW", self.close)
        if self.display_session.saved:
            self.append("[Launcher] Saved display settings found. Use Restore display to recover them.\n")
        root.after(100, self.poll)

    def append(self, text):
        match = re.fullmatch(r"\[CLEAR\] Supreme Deity Hell: (\d+)\s*", text.strip())
        if match:
            self.wins.set(match.group(1))
        self.log.configure(state="normal")
        from utilities.supreme_deity_output import log_parts
        for segment, tag in log_parts(text):
            self.log.insert("end", segment, tag)
        if int(self.log.index("end-1c").split(".")[0]) > 1500:
            self.log.delete("1.0", "300.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def restart_admin(self):
        if self.process is not None:
            messagebox.showinfo("Run active", "Stop the current run before restarting the launcher.")
            return
        import ctypes
        if ctypes.windll.shell32.IsUserAnAdmin():
            messagebox.showinfo("Administrator", "This launcher already has administrator privileges.")
            return
        try:
            executable = str(Path(python_console()).with_name("pythonw.exe"))
            arguments = subprocess.list2cmdline([str(ROOT / "SupremeDeityGUI.pyw")])
            result = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, arguments, str(ROOT), 1)
            if result <= 32:
                raise OSError("Windows did not approve the administrator relaunch. No run was started.")
            self.closing = True
        except OSError as exc:
            messagebox.showerror("Administrator relaunch", str(exc))

    def _has_admin(self):
        import ctypes
        return os.name != "nt" or bool(ctypes.windll.shell32.IsUserAnAdmin())

    def _show_admin_required(self):
        message = "Use 'Restart as administrator'"
        if not self.admin_required:
            self.append(message + "\n")
        self.admin_required = True
        self.status.set(message)
        self.status_label.configure(style="Error.TLabel")
        self.admin_button.configure(style="Admin.TButton", state="normal")
        for button in (self.start_button, self.resize_button, self.stop_button, self.pause_button):
            button.configure(state="disabled")

    def start(self, live, *, resize=False):
        if (live or resize) and not self._has_admin():
            self._show_admin_required()
            return
        if resize:
            self.request_resize()
            return
        if self.process is not None or self.display_job is not None or self.update_job is not None:
            return
        try:
            clears = 1 if resize else int(self.clears.get())
            if not (1 <= clears <= 999):
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid count", "Clears must be 1–999.")
            return
        # A private per-run directory avoids stale stop signals from earlier runs.
        self.stop_path = Path(tempfile.mkdtemp(prefix="sd-launcher-")) / "stop"
        self.pause_path = self.stop_path.with_name("pause")
        try:
            interpreter = python_console()
        except OSError as exc:
            self.cleanup_stop()
            messagebox.showerror("Python configuration", str(exc))
            return
        command = [interpreter, "-u", str(ROOT / "SupremeDeityFarmer.py")]
        command += (["--live", "--num-clears", str(clears),
                     "--stop-file", str(self.stop_path), "--pause-file", str(self.pause_path)] if live else ["--check"])
        if live:
            command += ["--registration-multiplier", "3" if self.x3.get() else "1"]
        if resize:
            command = [interpreter, "-u", str(ROOT / "SupremeDeityGUI.pyw"), "--resize"]
        try:
            self.process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True,
                encoding="utf-8", errors="replace", env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        except OSError as exc:
            self.cleanup_stop()
            messagebox.showerror("Cannot launch", str(exc))
            return
        self.stopping_at = None
        self.live_active = live
        self.paused_at = None
        self.pause_button.configure(text="Pause", state="normal" if live else "disabled")
        if live:
            self.run_started = time.monotonic()
            self.elapsed_seconds = 0
            self.elapsed.set("00:00:00")
            self.wins.set("0")
        self.start_button.configure(state="disabled")
        self.check_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status_label.configure(style="TLabel")
        self.status.set("Running live • F8 / Stop to stop" if live else "Checking installation…")
        self.append("\n--- Resize game ---\n" if resize else "\n--- Live run ---\n" if live else "\n--- Installation check ---\n")
        self.append(f"[Launcher] Python: {interpreter}\n")
        if resize:
            self.status.set("Resizing game…")
            self.append("[Launcher] Resizing game area to match the successful SD run: 518 × 922.\n")
        threading.Thread(target=self.read_output, args=(self.process,), daemon=True).start()

    def _display_work(self,restore,resolution):
        try:
            if restore:
                self.display_session.restore()
                self.messages.put("[SUCCESS] Original resolution and scale restored.\n")
            else:
                settings=self.display_session.set_display(resolution)
                self.messages.put(f"[SUCCESS] Display verified: {settings['mode']['PelsWidth']} × {settings['mode']['PelsHeight']} / {settings['scale']}%. Original settings saved.\n")
            self.display_completion=(True,restore)
        except Exception as exc:
            self.messages.put(f"[ERROR] {exc}\n")
            self.display_completion=(False,restore)

    def _request_display(self,restore,resolution=(2560,1440)):
        if self.process is not None or self.resize_process is not None or self.display_job is not None or self.update_job is not None:
            self.append("[Launcher] Stop the run and wait for other display operations to finish.\n")
            return False
        self.display_completion=None
        self.display_job=threading.Thread(target=self._display_work,args=(restore,resolution),daemon=False)
        self.display_job.start()
        self.append("[Launcher] Restoring original display…\n" if restore else f"[Launcher] Setting display to {resolution[0]} × {resolution[1]} / 125%…\n")
        return True

    def set_display(self,resolution=(2560,1440)):
        return self._request_display(False,resolution)

    def restore_display(self):
        return self._request_display(True)

    def request_resize(self):
        if self.update_job is not None:
            self.append("[Launcher] Wait for the update to finish.\n")
            return
        if not self._has_admin():
            self._show_admin_required()
            return
        if self.display_job is not None:
            self.append("[Launcher] Wait for the display change to finish before resizing.\n")
            return
        if self.resize_process is not None and self.resize_process.poll() is None:
            self.append("[Launcher] Resize is already in progress.\n")
            return
        if self.live_active and self.paused_at is None:
            self.toggle_pause()
            self.append("[Launcher] Run paused for resizing. Resume after resize completes.\n")
        try:
            self.resize_process = subprocess.Popen(
                [python_console(), "-u", str(ROOT / "SupremeDeityGUI.pyw"), "--resize"],
                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        except OSError as exc:
            messagebox.showerror("Cannot resize", str(exc))
            return
        self.append("[Launcher] Resizing game to 518 × 922.\n")
        threading.Thread(target=self.read_output, args=(self.resize_process,), daemon=True).start()

    def request_update(self):
        if (self.process is not None or self.resize_process is not None
                or self.display_job is not None or self.update_job is not None):
            self.append("[Launcher] Stop the bot and wait for other operations before updating.\n")
            return
        if self.display_session.saved:
            self.append("[Launcher] Use Restore display before updating.\n")
            return
        self.update_button.configure(state="disabled")
        self.update_job=threading.Thread(target=self._update_work,daemon=False)
        self.update_job.start()

    def _update_work(self):
        from utilities.supreme_deity_update import update_repository
        try:
            result=update_repository(ROOT.parent,self.messages.put)
            self.messages.put(f"[SUCCESS] {result}\n")
        except Exception as exc:
            self.messages.put(f"[ERROR] Update stopped: {exc}\n")

    def read_output(self, process):
        try:
            for line in process.stdout:
                self.messages.put(line)
        finally:
            process.stdout.close()

    def stop(self):
        if self.process is not None and self.stopping_at is None:
            self.stop_path.touch()
            self.stopping_at = time.monotonic()
            self.status.set("Stopping…")
            self.append("[Launcher] Stop requested.\n")
            self.pause_button.configure(state="disabled")

    def toggle_pause(self):
        if not self.live_active or self.process is None or self.stopping_at is not None:
            return
        if self.paused_at is None:
            self.pause_path.touch()
            self.paused_at = time.monotonic()
            self.pause_button.configure(text="Resume")
            self.status.set("Paused • Resume continues this run; Stop / F8 still works")
            self.append("[Launcher] Pause requested. Any in-progress input will finish safely.\n")
        else:
            self.pause_path.unlink(missing_ok=True)
            if self.run_started is not None:
                self.run_started += time.monotonic()-self.paused_at
            self.paused_at = None
            self.pause_button.configure(text="Pause")
            self.status.set("Running live • F8 / Stop to stop")
            self.append("[Launcher] Resume requested; continuing the current run.\n")

    def cleanup_stop(self):
        if self.pause_path:
            self.pause_path.unlink(missing_ok=True)
            self.pause_path = None
        if self.stop_path:
            self.stop_path.unlink(missing_ok=True)
            self.stop_path.parent.rmdir()
            self.stop_path = None

    def poll(self):
        if self.update_job is not None and not self.update_job.is_alive():
            self.update_job=None
            self.update_button.configure(state="normal")
        if self.display_job is not None and not self.display_job.is_alive():
            self.display_job=None
            success,restoring=self.display_completion
            if not success and self.closing:
                self.closing=False
                self.status.set("Display operation failed — review the log and retry Restore display")
        if self.resize_process is not None and self.resize_process.poll() is not None:
            self.append(f"[Launcher] Resize finished (code {self.resize_process.returncode}).\n")
            self.resize_process = None
        if self.run_started is not None:
            self.elapsed_seconds = int((self.paused_at if self.paused_at is not None else time.monotonic()) - self.run_started)
            hours, remainder = divmod(self.elapsed_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            self.elapsed.set(f"{hours:02}:{minutes:02}:{seconds:02}")
        for _ in range(200):
            try:
                self.append(self.messages.get_nowait())
            except queue.Empty:
                break
        if self.process:
            code = self.process.poll()
            if code is not None:
                check_ok = not self.live_active and code == 0 and self.stopping_at is None
                self.run_started = None
                self.paused_at = None
                self.live_active = False
                self.pause_button.configure(text="Pause", state="disabled")
                self.append(f"[Launcher] Process ended (code {code}). See the log above for the result.\n")
                self.status.set("Installation Successfull" if check_ok else
                                "Stopped" if self.stopping_at else "Finished — review log")
                self.status_label.configure(style="Success.TLabel" if check_ok else "TLabel")
                self.process = None
                self.cleanup_stop()
                self.start_button.configure(state="disabled" if self.admin_required else "normal")
                self.check_button.configure(state="normal")
                self.resize_button.configure(state="disabled" if self.admin_required else "normal")
                self.stop_button.configure(state="disabled")
            elif self.stopping_at and time.monotonic() - self.stopping_at > 5:
                self.process.terminate()
                self.append("[Launcher] Unresponsive worker terminated.\n")
        if self.admin_required and self.process is None:
            self.status.set("Use 'Restart as administrator'")
            self.status_label.configure(style="Error.TLabel")
        if (self.closing and self.process is None and self.resize_process is None
                and self.display_job is None and self.update_job is None):
            if self.display_session.saved:
                self.restore_display()
            else:
                self.root.destroy()
                return
        self.root.after(100, self.poll)

    def open_logs(self):
        logs = ROOT / "logs" / "supreme_deity"
        logs.mkdir(parents=True, exist_ok=True)
        os.startfile(str(logs))

    def close(self):
        self.closing = True
        self.stop()


if __name__ == "__main__":
    if "--resize" in sys.argv:
        # Desktop helper imports can leave background threads running. This
        # dedicated worker has no run state to save once resize has completed.
        code = 1
        try:
            code = resize_game()
        finally:
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(code)
    app = tk.Tk()
    Launcher(app)
    app.mainloop()
