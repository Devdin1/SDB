"""Native, resizable silver frames and ornaments for the launcher."""
import math
import tkinter as tk

BG = "#081321"
PANEL = "#0c1b2e"
EDGE = "#788cae"


def rounded(canvas, x1, y1, x2, y2, radius=12, **options):
    return canvas.create_polygon(
        x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
        smooth=True, splinesteps=24, **options)


def diamond(canvas, x, y, size=4, color=EDGE):
    canvas.create_polygon(x, y-size, x+size, y, x, y+size, x-size, y,
                          fill=PANEL, outline=color, width=1)


def divider(parent, background=PANEL):
    c = tk.Canvas(parent, height=12, bg=background, highlightthickness=0)
    def paint(event):
        c.delete("all")
        middle = event.width / 2
        c.create_line(0, 6, middle-15, 6, fill="#354d6e")
        c.create_line(middle+15, 6, event.width, 6, fill="#354d6e")
        diamond(c, middle, 6, 4)
        diamond(c, middle-10, 6, 2, "#506787")
        diamond(c, middle+10, 6, 2, "#506787")
    c.bind("<Configure>", paint)
    return c


def sigil(canvas, x, y, radius=50):
    for r in (radius, radius*.79, radius*.45):
        canvas.create_oval(x-r, y-r, x+r, y+r, outline="#243d5a")
    for i in range(12):
        angle = i*math.pi/6
        canvas.create_line(x+math.cos(angle)*radius*.85, y+math.sin(angle)*radius*.85,
                           x+math.cos(angle)*radius*1.13, y+math.sin(angle)*radius*1.13,
                           fill="#345372")
    for i in range(4):
        angle = i*math.pi/2
        canvas.create_polygon(x+math.cos(angle)*radius, y+math.sin(angle)*radius,
                              x+math.cos(angle+.3)*radius*.17, y+math.sin(angle+.3)*radius*.17,
                              x, y, x+math.cos(angle-.3)*radius*.17, y+math.sin(angle-.3)*radius*.17,
                              outline="#3c5778", fill="")


class SilverPanel(tk.Frame):
    def __init__(self, parent, *, padx=16, pady=12, ornaments=True, fill=PANEL):
        super().__init__(parent, bg=parent.cget("bg"), borderwidth=0)
        self.fill = fill
        self.ornaments = ornaments
        self.canvas = tk.Canvas(self, bg=self.cget("bg"), highlightthickness=0)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.content = tk.Frame(self, bg=fill)
        self.content.pack(fill="both", expand=True, padx=padx, pady=pady)
        self.canvas.bind("<Configure>", self.paint)

    def paint(self, event):
        c = self.canvas
        c.delete("all")
        w, h = event.width-1, event.height-1
        rounded(c, 1, 1, w-1, h-1, 14, fill=self.fill, outline=EDGE, width=1)
        if not self.ornaments:
            return
        for right, bottom in ((False, False), (True, False), (False, True), (True, True)):
            def coords(points):
                return [v for x, y in points for v in (w-x if right else x, h-y if bottom else y)]
            c.create_line(*coords([(3, 31), (5, 15), (9, 6), (30, 3)]),
                          fill="#b1bfd7", width=1, smooth=True)
            c.create_line(*coords([(7, 19), (6, 10), (14, 5), (23, 10), (18, 19), (10, 20), (7, 12), (15, 9), (20, 15)]),
                          fill="#8f9fbd", width=1, smooth=True)
            c.create_line(*coords([(6, 31), (12, 21), (24, 13), (31, 6)]),
                          fill="#647c9e", width=1, smooth=True)


class DarkScrollbar(tk.Canvas):
    def __init__(self, parent, command):
        super().__init__(parent, width=9, bg=PANEL, highlightthickness=0)
        self.command = command
        self.first, self.last = 0., 1.
        self.offset = 0
        self.bind("<Configure>", lambda _: self.paint())
        self.bind("<Button-1>", self.press)
        self.bind("<B1-Motion>", self.drag)
        self.bind("<MouseWheel>", lambda e: command("scroll", -int(e.delta / 120), "units"))

    def set(self, first, last):
        self.first, self.last = float(first), float(last)
        self.paint()

    def paint(self):
        self.delete("all")
        height = max(1, self.winfo_height())
        top, bottom = self.first * height, max(self.first * height + 24, self.last * height)
        rounded(self, 1, top, 8, min(height, bottom), 4,
                fill="#2a3d59" if self.last-self.first >= .999 else "#536582", outline="")

    def press(self, event):
        top, bottom = self.first*self.winfo_height(), self.last*self.winfo_height()
        self.offset = event.y-top if top <= event.y <= bottom else 0
        if not top <= event.y <= bottom:
            self.drag(event)

    def drag(self, event):
        fraction = (event.y-self.offset) / max(1, self.winfo_height())
        self.command("moveto", max(0, min(1-(self.last-self.first), fraction)))
