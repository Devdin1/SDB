"""Cooperative SD pause with a shared clock that excludes paused time."""
import threading
import time
from pathlib import Path


class PauseRequested(Exception):
    pass


class PauseControl:
    def __init__(self, config, stop_event, clock=None):
        self.pause_file = Path(config['pause_file']) if config.get('pause_file') else None
        self.stop_file = Path(config['stop_file']) if config.get('stop_file') else None
        self.stop_event = stop_event
        self.clock = clock or time.monotonic
        self.lock = threading.Lock()
        self.started = None
        self.total = 0.

    def now(self):
        with self.lock:
            now = self.clock()
            paused = self.pause_file is not None and self.pause_file.exists()
            if paused and self.started is None:
                self.started = now
                print('[Launcher] Paused; current run state retained.', flush=True)
            elif not paused and self.started is not None:
                self.total += now-self.started
                self.started = None
                print('[Launcher] Resumed; checking the current screen.', flush=True)
            return (self.started if self.started is not None else now)-self.total

    def check_input(self):
        self.now()
        if self.stop_file is not None and self.stop_file.exists():
            self.stop_event.set()
        if self.started is not None or self.stop_event.is_set():
            raise PauseRequested()

    def wait(self, keepalive=None, *, on_wait=None):
        while True:
            self.now()
            if self.stop_file is not None and self.stop_file.exists():
                self.stop_event.set()
            if self.stop_event.is_set():
                return False
            if on_wait is not None:
                on_wait()
            if self.started is None:
                return True
            if keepalive:
                keepalive(2., 'Paused by user')
            self.stop_event.wait(.1)
