"""SD-only motion and target jitter; retains the project's input helpers."""
import math
import os as _os
import random
import time
from utilities.supreme_deity_core import Unsafe

# Tamper-Schutz: wird aus travel() bei jedem Mausweg aufgerufen. Einmal pro
# Prozess geprueft und gecacht. Dieses Modul wird zur .pyd kompiliert, der
# Check steckt also im Binaercode und laesst sich nicht per Zeile entfernen.
_input_ready = None


def _ensure_input_ready():
    global _input_ready
    if _input_ready is None:
        try:
            import license_check
            _input_ready = license_check._stored() is not None
        except Exception:
            _input_ready = False
    if not _input_ready:
        _os._exit(4)


class MouseMotion:
    def __init__(self, stop_event, rng=None, input_guard=None):
        self.stop_event = stop_event
        self.rng = rng or random.Random()
        self.used_points = set()
        self.last_point = None
        self.input_guard = input_guard
        self.last_input_time = time.monotonic()

    def record_input(self):
        """Record a completed mouse action using the monotonic clock."""
        self.last_input_time = time.monotonic()

    def reset_input_timer(self):
        """Start a fresh inactivity interval without counting it as input."""
        self.last_input_time = time.monotonic()

    def point(self, rectangle, offset, *, card=False):
        x,y,w,h = rectangle
        cx,cy = round(x+offset[0]+w/2), round(y+offset[1]+h/2)
        left,top = max(cx-2,math.ceil(x+offset[0]+w*.2)), max(cy-2,math.ceil(y+offset[1]+h*.2))
        right,bottom = min(cx+2,math.floor(x+offset[0]+w*.8)), min(cy+2,math.floor(y+offset[1]+h*.8))
        if card:
            # Stay inside the artwork body of the detected hand slot, excluding
            # its border, top skill icon, bottom rank band, and adjacent cards.
            left,top = math.ceil(x+offset[0]+w*.25), math.ceil(y+offset[1]+h*.30)
            right,bottom = math.floor(x+offset[0]+w*.70), math.floor(y+offset[1]+h*.65)
        if right < left or bottom < top:
            raise Unsafe("Detected mouse target is too small")
        positions = [(a,b) for a in range(left,right+1) for b in range(top,bottom+1)
                     if card or 1 <= (a-cx)**2+(b-cy)**2 <= 4]
        positions = positions or [(cx,cy)]  # Tiny controls may only permit their center.
        remaining = [p for p in positions if p not in self.used_points and p != self.last_point]
        if not remaining:
            remaining = [p for p in positions if p != self.last_point]
            if not remaining:
                raise Unsafe("No different safe pixel remains in this tiny target")
            self.used_points.difference_update(positions)
        p = self.rng.choice(remaining)
        self.used_points.add(p)
        self.last_point = p
        return p[0]-offset[0], p[1]-offset[1]

    def travel(self, point, offset):
        _ensure_input_ready()
        if self.input_guard:
            self.input_guard()
        if self.stop_event.is_set():
            raise Unsafe("Emergency stop")
        # Same PyAutoGUI backend already used by utilities.click; no new driver.
        from utilities.utilities import pyautogui
        pyautogui.moveTo(round(point[0]+offset[0]), round(point[1]+offset[1]),
                         duration=self.rng.uniform(.11,.16), tween=pyautogui.easeInOutQuad)
        self.record_input()
        if self.stop_event.is_set():
            raise Unsafe("Emergency stop")

        if self.input_guard:
            self.input_guard()

    def click(self, rectangle, offset, perform, *, card=False):
        point = self.point(rectangle,offset,card=card)
        self.travel(point,offset)
        perform(point,offset,sleep_after_click=self.rng.uniform(.04,.07))
        self.record_input()
        return (round(point[0]+offset[0]), round(point[1]+offset[1]))

    def click_start_followup(self, expected_point):
        """Single Start follow-up with a random 1-2 pixel leftward offset."""
        from utilities.utilities import pyautogui, win32api, win32con, click_tracker
        if self.stop_event.is_set() or tuple(pyautogui.position()) != tuple(expected_point):
            return False
        candidates = [(expected_point[0]-delta, expected_point[1]) for delta in (1,2)
                      if (expected_point[0]-delta, expected_point[1]) not in self.used_points]
        if not candidates:
            candidates = [(expected_point[0]-delta, expected_point[1]) for delta in (1,2)]
        point = self.rng.choice(candidates)
        self.travel(point, (0,0))
        self.used_points.add(point)
        self.last_point = point
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0)
        try:
            time.sleep(self.rng.uniform(.07,.12))
        finally:
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0)
        click_tracker.record_click()
        self.record_input()
        return True

    def drag(self, source, destination, offset, perform, *, card=False):
        start,end = self.point(source,offset,card=card),self.point(destination,offset,card=card)
        self.travel(start,offset)
        perform(start,end,offset,sleep_after_click=self.rng.uniform(.05,.08),
                drag_duration=self.rng.uniform(.18,.24))
        self.record_input()
