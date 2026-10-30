"""Supreme Deity desktop launcher. Importing this file never starts farming."""
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
        from utilities.supreme_deity_gui_view import BattleView
        self.view = BattleView(self, ROOT / "images" / "supreme_deity" / "gui")
        root.protocol("WM_DELETE_WINDOW", self.close)
        if self.display_session.saved:
            self.append("[Launcher] Saved display settings found. Use Restore display to recover them.\n")
        root.after(100, self.poll)

    def append(self, text):
        self.view.consume(text)
        match = re.fullmatch(r"\[CLEAR\] Supreme Deity (?:Hell|Hard): (\d+)\s*", text.strip())
        if match:
            self.wins.set(match.group(1))
        follow_output = self.log.yview()[1] >= .995
        self.log.configure(state="normal")
        start_line = int(self.log.index("end-1c").split(".")[0])
        if text.strip() and not text.startswith("\n"):
            self.log.insert("end", time.strftime("[%H:%M:%S]  "), "timestamp")
        from utilities.supreme_deity_output import log_parts
        for segment, tag in log_parts(text):
            self.log.insert("end", segment, tag)
        end_line = int(self.log.index("end-1c").split(".")[0])
        for line in range(start_line, end_line):
            if line % 2 == 0:
                self.log.tag_add("row_even", f"{line}.0", f"{line}.end+1c")
        if int(self.log.index("end-1c").split(".")[0]) > 1500:
            self.log.delete("1.0", "300.0")
        if follow_output:
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
            arguments = subprocess.list2cmdline([str(ROOT / "SupremeDeityGUI.pyw"),
                                                "--difficulty", self.difficulty.get().lower()])
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
        command = [interpreter, "-u", str(ROOT / "SupremeDeityFarmer.py"),
                   "--difficulty", self.difficulty.get().lower()]
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
        self.view.difficulty_combo.configure(state="disabled")
        self.paused_at = None
        self.pause_button.configure(text="Pause", state="normal" if live else "disabled")
        if live:
            self.run_started = time.monotonic()
            self.elapsed_seconds = 0
            self.elapsed.set("00:00:00")
            self.wins.set("0")
            self.view.reset_count = 0
            self.view.resets.set("0")
            self.view.reset()
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
                self.view.difficulty_combo.configure(state="readonly")
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
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--difficulty", choices=("hell", "hard"), default="hell")
    parser.add_argument("--resize", action="store_true")
    args = parser.parse_args()
    if args.resize:
        # Desktop helper imports can leave background threads running. This
        # dedicated worker has no run state to save once resize has completed.
        code = 1
        try:
            code = resize_game()
        finally:
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(code)
    if os.name == "nt":
        import ctypes
        ctypes.windll.user32.SetProcessDPIAware()
    app = tk.Tk()
    launcher = Launcher(app)
    launcher.difficulty.set(args.difficulty.title())
    app.mainloop()
