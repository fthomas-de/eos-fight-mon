"""Tk windows: client ships left, everyone else right, effects as arrows in between; small cockpit and graph windows."""
import asyncio
import configparser
import ctypes
import json
import math
import queue
import re
import sys
import threading
import tkinter as tk
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import logparse
import snap
import update
from fight import EWAR, REPS, TICK, WINDOW

THEMES = {
    "client": {"bg": "#0e1621", "panel": "#172333", "fg": "#d8e4f0", "dim": "#71859a", "accent": "#3fa9f5"},
    "server": {"bg": "#1a120c", "panel": "#2a1d13", "fg": "#f0e4d8", "dim": "#9a8571", "accent": "#f5a33f"},
}
COLORS = {"dmg": "#e5484d", "shield": "#30a46c", "armor": "#30a46c", "hull": "#30a46c", "cap": "#e2b93b",
          "neut": "#9d5bd2", "nos": "#9d5bd2", "scram": "#f76b15", "point": "#f76b15", "jam": "#f76b15"}
OFFSET = {"dmg": -9, "shield": 0, "armor": 0, "hull": 0, "cap": 5, "neut": 9, "nos": 9, "scram": 14, "point": 14, "jam": 14}
LANE = {k: sorted(set(OFFSET.values())).index(v) for k, v in OFFSET.items()}  # 0 = damage … 4 = scram
LEGEND = [("Damage", "dmg"), ("Reps", "shield"), ("Cap", "cap"), ("Neut/Nos", "neut"), ("Scram/Point/Jam", "scram")]
GROUPS = [("Damage", "dmg", {"dmg"}), ("Reps", "shield", REPS - {"cap"}), ("Cap", "cap", {"cap"}),
          ("Neut/Nos", "neut", {"neut", "nos"})]
NAMES = {"dmg": "Damage", "shield": "Shield reps", "armor": "Armor reps", "hull": "Hull reps", "cap": "Cap transfer",
         "neut": "Neut", "nos": "Nos", "scram": "Scram", "point": "Point", "jam": "Jam"}
BOX_W = 290
FONT = "Segoe UI"


def fmt(v):
    return f"{v / 1e6:.1f}M" if v >= 1e6 else f"{v / 1000:.1f}k" if v >= 1000 else f"{v:.0f}"


# window and taskbar icon, 32 px PNG (the exe itself gets icon.ico from the build)
APP_ICON = ("iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAB6klEQVR42tWX7W3CMBCGHyIGSDfICGwAnaBZoRM03YBOQDsBMAF0"
            "AmCCsAHZIJnA9EfO9OQ6jiNBSy1Fkc6+T9+9d4b/sgxkBgoDOwO1gbPz1bJXGMiuqXgigs8Dv42BSZ/8UY/yBVA45AY4AgeHPqVVmDr0"
            "9wReh3qdGigdj3YG8gje3BOx0vw0LFp5HaO4w5B6sBGO8njL45wp+xgW11IeMGIRynYd9jQgcOmEtxZaiEefn/gObdSBfEByRiWb5MSl"
            "RH0gc8n2QDjnEfU/D/Dr6sgAEtnTHn8ErnQace2hM1p27rOs7kmoTQwC9siodaRtBGxSHCM8bIBnYKVoK6E1EfxHrdMaYBPn0MN8AKqk"
            "VbhWCtdCqyJlXHSOB5Z1hZSrikZDe4V2vQ0RmAw0wG2ze/lCZ4JrHIlmmXi6kv+TZLGuni3wCWwFC9KkjViUgjqEAQLRpUWwjvlgpxC1"
            "7IJct+JGlgjMgCaBB5+BKlErCXvqqY6ZuoI+WfsEHi2xCMGwaQVbOF0aOKkeYKN3kr1c8wTguNBJuFXnXjpCNxPLU+Vlxfc9Z3bfp9wj"
            "exvC6bwjR86+wdMZWM8+VA02o752LE0oaj5QHXM+qB3/+UByFyPZXQylvz2W3+fDxFMdm1s9ze7/cXrr9QX3jDlxpIDpYwAAAABJRU5E"
            "rkJggg==")

_ICON_FILE = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "ship_icons.json"  # packed into the exe
_icons, _images = None, {}


def ship_icon(ship):
    """32 px image of a ship type; None for NPCs, wrecks, or a build without ship_icons.json."""
    global _icons
    if _icons is None:
        try:
            _icons = json.loads(_ICON_FILE.read_text(encoding="utf-8"))["icons"]
        except (OSError, ValueError, KeyError):
            _icons = {}
    if ship not in _images:  # Tk needs the image objects kept alive
        _images[ship] = tk.PhotoImage(data=_icons[ship]) if ship in _icons else None
    return _images[ship]


def _rates(window):
    """Per-second rates of the given ticks plus the ewar seen in them."""
    secs = TICK * len(window)
    rates, ewar = defaultdict(float), set()
    for t in window:
        for k, s, d, a in t["flows"]:
            if k in EWAR:
                ewar.add((k, s, d))
            else:
                rates[(k, s, d)] += a / secs
    return rates, ewar


def draw(cv, ticks, th, hover=None):
    """Draw a fight up to its last tick: ships with per-second rates of the last 10 s; hover (x, y) shows the arrows there."""
    cv.delete("all")
    w, h = cv.winfo_width(), cv.winfo_height()
    if not ticks:
        cv.create_text(w / 2, h / 2, text="Waiting for a fight …", fill=th["dim"], font=(FONT, 16))
        return
    last = ticks[-1]
    ships, left_names = last["ships"], set(last["left"])
    rates, ewar = _rates(ticks[-WINDOW:])

    out_dmg, in_dmg, in_rep = defaultdict(float), defaultdict(float), defaultdict(float)
    for (k, s, d), r in rates.items():
        if k == "dmg":
            out_dmg[s] += r
            in_dmg[d] += r
        elif k in REPS:
            in_rep[d] += r
    names = {n for _, s, d in [*rates, *ewar] for n in (s, d)} - set(last.get("hidden", ()))
    left = sorted(n for n in names if n in left_names)
    right = sorted(names - set(left), key=lambda n: -(out_dmg[n] + in_dmg[n] + in_rep[n]))

    top, usable = 10, h - 50
    row = max(38, min(56, usable / max(1, len(left), len(right))))  # a 10 man team always fits
    rows = max(2, int(usable // row))
    if len(right) > rows:
        right = right[:rows - 1] + [f"+{len(right) - rows + 1} more"]
    pos, tips = {}, {}
    for col, column in enumerate((left[:rows], right)):
        x = 20 if col == 0 else w - 20 - BOX_W
        for i, n in enumerate(column):
            y = top + i * row
            pos[n] = (x + BOX_W if col == 0 else x, y + (row - 6) / 2, col, x, y)

    for (k, s, d), r in rates.items():
        if item := _arrow(cv, pos, k, s, d, 1 + min(6, math.log10(1 + r))):
            tips[item] = f"{NAMES[k]}  {s} → {d}  {fmt(r)}/s"
    for k, s, d in ewar:
        if item := _arrow(cv, pos, k, s, d, 2, dash=(4, 3)):
            tips[item] = f"{NAMES[k]}  {s} → {d}"
    for n, (_, _, col, x, y) in pos.items():
        cv.create_rectangle(x, y, x + BOX_W, y + row - 6, fill=th["panel"],
                            outline=th["accent"] if col == 0 else th["dim"])
        tx = x + 8
        if icon := ship_icon(ships.get(n, n)):  # NPCs and bare ship names are their own type
            cv.create_image(x + 3, y + (row - 6) / 2, anchor="w", image=icon)
            tx += 34
        cv.create_text(tx, y + 3, anchor="nw", text=n, fill=th["fg"], font=(FONT, 10, "bold"))
        info = f"{ships.get(n, '')}   out {fmt(out_dmg[n])}  in {fmt(in_dmg[n])}  rep {fmt(in_rep[n])}"
        cv.create_text(tx, y + 19, anchor="nw", text=info, fill=th["dim"], font=(FONT, 9))

    x = 20
    for label, kind in LEGEND:
        cv.create_line(x, h - 14, x + 20, h - 14, fill=COLORS[kind], width=3)
        x = cv.bbox(cv.create_text(x + 26, h - 14, anchor="w", text=label, fill=th["dim"], font=(FONT, 9)))[2] + 18

    if hover and (hits := [i for i in cv.find_overlapping(hover[0] - 4, hover[1] - 4, hover[0] + 4, hover[1] + 4)
                           if i in tips]):
        for i in hits:
            cv.itemconfigure(i, width=float(cv.itemcget(i, "width")) + 2)
        text = cv.create_text(hover[0] + 14, hover[1] + 14, anchor="nw", text="\n".join(tips[i] for i in hits),
                              fill=th["fg"], font=(FONT, 9))
        x1, y1, x2, y2 = cv.bbox(text)
        dx, dy = min(0, w - 6 - x2), min(0, h - 6 - y2)  # keep the box inside the canvas
        cv.move(text, dx, dy)
        cv.tag_lower(cv.create_rectangle(x1 - 6 + dx, y1 - 4 + dy, x2 + 6 + dx, y2 + 4 + dy, fill=th["panel"],
                                         outline=th["accent"]), text)


def summary(ticks):
    """Fight seconds and per group the team's (out/s, in/s, Σ out, Σ in): /s over the last 10 s, Σ over the fight."""
    if not ticks:
        return 0, {label: (0, 0, 0, 0) for label, _, _ in GROUPS}
    left_names = set(ticks[-1]["left"])

    def by_side(items):
        out = defaultdict(float)
        for (k, s, d), v in items:
            out[(k, s in left_names, d in left_names)] += v
        return out
    now = by_side(_rates(ticks[-WINDOW:])[0].items())
    total = by_side(((k, s, d), a) for t in ticks for k, s, d, a in t["flows"])

    def side(values, kinds, outgoing):
        return sum(v for (k, s_left, d_left), v in values.items() if k in kinds and (s_left if outgoing else d_left))
    secs = ticks[-1]["t"] - ticks[-1].get("start", ticks[0]["t"]) + TICK
    return secs, {label: (side(now, kinds, True), side(now, kinds, False), side(total, kinds, True),
                          side(total, kinds, False)) for label, _, kinds in GROUPS}


def draw_cockpit(cv, ticks, th):
    """The small cockpit window: fight clock, then one row per group with the team's sums."""
    cv.delete("all")
    w = cv.winfo_width()
    secs, groups = summary(ticks)
    cv.create_text(10, 6, anchor="nw", text=_mmss(secs), fill=th["accent"], font=(FONT, 16, "bold"))
    col = (w - 100) / 4
    xs = [w - 10 - (3 - i) * col for i in range(4)]
    for x, head in zip(xs, ("out/s", "in/s", "Σ out", "Σ in")):
        cv.create_text(x, 30, anchor="se", text=head, fill=th["dim"], font=(FONT, 9))
    for row, (label, color_kind, _) in enumerate(GROUPS):
        y = 44 + row * 20
        cv.create_text(10, y, anchor="w", text=label, fill=COLORS[color_kind], font=(FONT, 10, "bold"))
        for x, v in zip(xs, groups[label]):
            cv.create_text(x, y, anchor="e", text=fmt(v), fill=th["fg"], font=(FONT, 10))


def series(ticks):
    """Per tick the team's {(group, outgoing): per second} over the 10 s up to it, the same numbers as the cockpit."""
    if not ticks:
        return []
    left = set(ticks[-1]["left"])
    group_of = {k: label for label, _, kinds in GROUPS for k in kinds}
    per_tick = []
    for t in ticks:
        sums = defaultdict(float)
        for k, s, d, a in t["flows"]:
            if label := group_of.get(k):
                if s in left:
                    sums[(label, True)] += a
                if d in left:
                    sums[(label, False)] += a
        per_tick.append(sums)
    out = []
    for i in range(len(per_tick)):
        window = per_tick[max(0, i - WINDOW + 1):i + 1]
        rates = defaultdict(float)
        for sums in window:
            for key, a in sums.items():
                rates[key] += a / (TICK * len(window))
        out.append(rates)
    return out


def draw_graph(cv, ticks, th, hover=None):
    """One small chart per group, out solid and in dashed, over the fight; hover (canvas x) picks the shown tick."""
    cv.delete("all")
    w, h = cv.winfo_width(), cv.winfo_height()
    data = series(ticks)
    if len(data) < 2:
        cv.create_text(w / 2, h / 2, text="Waiting for a fight …", fill=th["dim"], font=(FONT, 11))
        return
    pad_l, pad_r, top, bottom = 50, 12, 20, 18
    pw, ph, n = w - pad_l - pad_r, (h - top - bottom) / len(GROUPS), len(data)
    i = n - 1 if hover is None else max(0, min(n - 1, round((hover - pad_l) / pw * (n - 1))))
    # legend: the line style tells out from in, not colour alone
    cv.create_line(pad_l, 10, pad_l + 22, 10, fill=th["fg"], width=2)
    cv.create_text(pad_l + 28, 10, anchor="w", text="out", fill=th["dim"], font=(FONT, 8))
    cv.create_line(pad_l + 60, 10, pad_l + 82, 10, fill=th["fg"], width=2, dash=(4, 3))
    cv.create_text(pad_l + 88, 10, anchor="w", text="in   (per second, last 10 s)", fill=th["dim"], font=(FONT, 8))
    for g, (label, color_kind, _) in enumerate(GROUPS):
        y0 = top + g * ph
        base, height = y0 + ph - 4, ph - 20
        vmax = max([d[(label, o)] for d in data for o in (True, False)] + [1])
        cv.create_line(pad_l, base, w - pad_r, base, fill=th["panel"])
        cv.create_line(pad_l, base - height, w - pad_r, base - height, fill=th["panel"], dash=(1, 3))
        cv.create_text(pad_l - 6, base, anchor="e", text="0", fill=th["dim"], font=(FONT, 8))
        cv.create_text(pad_l - 6, base - height, anchor="e", text=fmt(vmax), fill=th["dim"], font=(FONT, 8))
        cv.create_rectangle(pad_l, y0 + 3, pad_l + 8, y0 + 11, fill=COLORS[color_kind], outline="")
        cv.create_text(pad_l + 13, y0 + 7, anchor="w", text=label, fill=th["fg"], font=(FONT, 9, "bold"))
        cv.create_text(w - pad_r, y0 + 7, anchor="e", fill=th["fg"], font=(FONT, 9),
                       text=f"out {fmt(data[i][(label, True)])}   in {fmt(data[i][(label, False)])}")
        for outgoing, dash in ((True, None), (False, (4, 3))):
            pts = [v for j, d in enumerate(data)
                   for v in (pad_l + pw * j / (n - 1), base - height * d[(label, outgoing)] / vmax)]
            cv.create_line(*pts, fill=COLORS[color_kind], width=2, dash=dash)
    t0 = ticks[0]["t"]
    cv.create_text(pad_l, h - 4, anchor="sw", text="00:00", fill=th["dim"], font=(FONT, 8))
    cv.create_text(w - pad_r, h - 4, anchor="se", text=_mmss(ticks[-1]["t"] - t0 + TICK), fill=th["dim"],
                   font=(FONT, 8))
    if hover is not None:
        x = pad_l + pw * i / (n - 1)
        cv.create_line(x, top, x, h - bottom, fill=th["dim"])
        cv.create_text(x, h - 4, anchor="s", text=_mmss(ticks[i]["t"] - t0 + TICK), fill=th["fg"],
                       font=(FONT, 8, "bold"))


MAIN_SIZE = "1150x720"
PANELS = {  # small extra windows: title, default size, min size, painter
    "cockpit": ("Cockpit", "340x124", (280, 120), draw_cockpit),
    "graph": ("Graph", "460x320", (320, 220), draw_graph),
}


def _arrow(cv, pos, kind, s, d, width, dash=None):
    if s not in pos or d not in pos:
        return
    (x1, y1, c1, *_), (x2, y2, c2, *_) = pos[s], pos[d]
    y1, y2 = y1 + OFFSET[kind], y2 + OFFSET[kind]
    opts = {"fill": COLORS[kind], "width": width, "dash": dash, "arrow": "last",
            "arrowshape": (10 + 2 * width, 12 + 2 * width, 5 + width)}
    if c1 == c2:  # same side: bow towards the middle, one lane per kind and direction so bows never overlap
        depth = 50 + 30 * LANE[kind] + (15 if y2 < y1 else 0)
        mx = x1 + (depth if c1 == 0 else -depth)
        return cv.create_line(x1, y1, mx, y1, mx, y2, x2, y2, smooth="raw", **opts)  # leaves and enters level
    return cv.create_line(x1, y1, x2, y2, **opts)


def update_config(path, values):
    """Change single keys in the file as it is now, so parallel instances never undo each other's changes."""
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(path, encoding="utf-8-sig")
    for sec, keys in values.items():
        if not cfg.has_section(sec):
            cfg.add_section(sec)
        cfg[sec].update(keys)
    with open(path, "w", encoding="utf-8") as fh:
        cfg.write(fh)


def _on_screen(x, y):
    """Is a window corner at x, y still on some monitor (e.g. after unplugging one)?"""
    if sys.platform != "win32":
        return True
    m = ctypes.windll.user32.GetSystemMetrics  # virtual screen = all monitors together
    left, top = m(76), m(77)
    return left <= x <= left + m(78) - 100 and top <= y <= top + m(79) - 100


def _valid_place(geometry):
    """A saved "WxH+X+Y" whose corner is still on a monitor."""
    m = re.fullmatch(r"\d+x\d+\+(-?\d+)\+(-?\d+)", geometry)
    return bool(m) and _on_screen(*map(int, m.groups()))


def fight_label(name):
    """'20261013_191334.jsonl.gz' (UTC) -> '2026-10-13  21:13:34' (local time)."""
    start = datetime.strptime(name[:15], "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
    return start.astimezone().strftime("%Y-%m-%d  %H:%M:%S")


class App:
    def __init__(self, mode, backend, loop, q, cfg, cfg_path, connect_code=None, restart=None, geometry=None):
        self.mode, self.backend, self.loop, self.q = mode, backend, loop, q
        self._restart = restart
        self.cfg, self.cfg_path = cfg, cfg_path
        self.th = th = THEMES[mode]
        self.live = []  # ticks of the running fight
        self.replay, self.pos, self.playing, self._timer = None, 0, False, None

        root = self.root = tk.Tk()
        root.minsize(900, 560)
        root.geometry(MAIN_SIZE)
        root.iconphoto(True, tk.PhotoImage(data=APP_ICON))  # True: cockpit, graph and dialogs get it too
        self._normal_geo = None  # last place while neither maximized nor minimized
        if geometry:  # a restart passes the place it had
            self._place(geometry)
        root.bind("<Configure>", self._track_place, add="+")
        self._sizes, self._snap_jobs = {}, {}
        root.bind("<Configure>", self._on_move, add="+")
        root.protocol("WM_DELETE_WINDOW", self._close)
        # any widget getting focus (a click often focuses a child, not the window) raises the whole group
        root.bind_all("<FocusIn>", self._on_focus, add="+")
        root.configure(bg=th["bg"])

        self.bar = tk.Frame(root, bg=th["panel"])
        self.bar.pack(fill="x")
        if mode == "client":
            self.char = tk.StringVar(value=backend.char or "")
            box = ttk.Combobox(self.bar, textvariable=self.char, state="readonly", width=24,
                               postcommand=lambda: box.configure(values=logparse.characters(cfg["client"]["log_dir"])))
            box.bind("<<ComboboxSelected>>", lambda e: self._set_char())
            box.pack(side="left", padx=(10, 4), pady=4)
            self._button(self.bar, "Paste code", self._paste_code).pack(side="left", padx=4)
        else:
            tk.Label(self.bar, text="Connection code:", bg=th["panel"], fg=th["dim"]).pack(side="left", padx=(10, 4))
            code = tk.Entry(self.bar, width=len(connect_code) + 2, bg=th["bg"], fg=th["fg"], relief="flat",
                            readonlybackground=th["bg"])
            code.insert(0, connect_code)
            code.configure(state="readonly")
            code.pack(side="left", pady=4)
            self._button(self.bar, "Copy", lambda: self._copy(connect_code)).pack(side="left", padx=4)
        foot = tk.Frame(root, bg=th["panel"])  # connection messages, below everything else
        foot.pack(side="bottom", fill="x")
        line = tk.Frame(foot, bg=th["panel"])
        line.pack(fill="x")
        self.status = tk.StringVar()
        tk.Label(line, textvariable=self.status, bg=th["panel"], fg=th["fg"], font=(FONT, 10)).pack(
            side="left", padx=10, pady=2)
        self.warning = tk.StringVar()
        tk.Label(line, textvariable=self.warning, bg=th["panel"], fg=COLORS["dmg"],
                 font=(FONT, 10, "bold")).pack(side="left", padx=10)
        self._button(self.bar, "Settings", self._settings).pack(side="right", padx=4, pady=4)
        self._button(self.bar, "Reset size", self._reset_size).pack(side="right", padx=4)
        self._button(self.bar, "Graph", lambda: self._toggle_panel("graph")).pack(side="right", padx=4)
        self._button(self.bar, "Cockpit", lambda: self._toggle_panel("cockpit")).pack(side="right", padx=4)
        self._button(self.bar, "Replays", lambda: self.call(backend.history)).pack(side="right", padx=4)
        if mode == "server":  # only the server may end a fight early
            self._button(self.bar, "Reset", lambda: self.call(backend.reset)).pack(side="right", padx=4)
        if mode == "client":
            self.enabled = cfg.getboolean("client", "auto_connect")
            self.conn = self._button(self.bar, "", self._toggle)
            self.conn.pack(side="right", padx=4)
            self._conn_text()
        self.panels, self.panel_canvas, self._panel_geo, self._hover = {}, {}, {}, None
        self._main_hover = None
        self._title()
        if mode == "server":  # who is connected, with the character each client picked
            self.clients = tk.StringVar(value="no client connected")
            info = tk.Label(foot, textvariable=self.clients, bg=th["panel"], fg=th["dim"], font=(FONT, 9),
                            anchor="w", justify="left")
            info.pack(fill="x", padx=10, pady=(0, 2))
            info.bind("<Configure>", lambda e: info.configure(wraplength=e.width - 10))

        self.replay_bar = tk.Frame(root, bg=th["panel"])
        self.play_btn = self._button(self.replay_bar, "Stop", self._play_pause)
        self.play_btn.pack(side="left", padx=4, pady=4)
        self.scale = tk.Scale(self.replay_bar, orient="horizontal", showvalue=False, command=self._seek,
                              bg=th["panel"], fg=th["fg"], troughcolor=th["bg"], highlightthickness=0)
        self.scale.pack(side="left", fill="x", expand=True, padx=4)
        self.replay_label = tk.Label(self.replay_bar, bg=th["panel"], fg=th["fg"])
        self.replay_label.pack(side="left", padx=4)
        self._button(self.replay_bar, "Back to live", self._stop_replay).pack(side="left", padx=4)

        self.canvas = tk.Canvas(root, bg=th["bg"], highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.redraw())
        self.canvas.bind("<Motion>", lambda e: self._arrow_hover((e.x, e.y)))
        self.canvas.bind("<Leave>", lambda e: self._arrow_hover(None))

        self._restore_layout(main=not geometry, first=True)
        root.after(100, self._drain)
        if update.can_install() and cfg.getboolean("update", "check"):
            root.after(3000, lambda: self._check_update(manual=False))

    def _button(self, parent, text, cmd):
        th = self.th
        return tk.Button(parent, text=text, command=cmd, bg=th["bg"], fg=th["fg"], relief="flat",
                         activebackground=th["accent"], activeforeground=th["bg"], padx=8)

    def _char(self):
        return self.char.get() if self.mode == "client" else None

    def _title(self):
        who = f"Client – {self.char.get() or 'no character'}" if self.mode == "client" else "Server"
        self.root.title(f"eos-fight-mon – {who}")
        for name, top in self.panels.items():
            top.title(f"{PANELS[name][0]} – {self._char() or 'Server'}")

    # --- cockpit and graph windows ---

    def _restore_layout(self, main=True, first=False):
        """Put this character's windows where they were last time (also after picking another character).
        A closed cockpit or graph is stored as "off WxH+X+Y" and reopens at that place."""
        saved = configparser.ConfigParser(interpolation=None)
        saved.read(self.cfg_path, encoding="utf-8-sig")  # fresh: other instances write the file too
        windows = saved["windows"] if saved.has_section("windows") else {}
        key = self._layout_key = self._window_key(self._char())
        if main and key in windows:
            self._place(windows[key])
        for name in PANELS:
            entry = windows.get(f"{key}.{name}")
            if entry is None:  # character never saved: both open at start, else leave them as they are
                if first:
                    self._open_panel(name)
                continue
            self._panel_geo[name] = geo = entry.removeprefix("off").strip()
            if entry.startswith("off"):
                if top := self.panels.pop(name, None):
                    del self.panel_canvas[name]
                    top.destroy()
            elif name in self.panels:
                if _valid_place(geo):
                    top = self.panels[name]
                    top.geometry(geo)
                    top.update_idletasks()
                    # Windows hands Tk the old place back while the character list closes: set it once more
                    self.root.after(300, lambda top=top, geo=geo: top.winfo_exists() and top.geometry(geo))
            else:
                self._open_panel(name)

    def _place(self, geometry):
        # "zoomed WxH+X+Y": the normal place picks the monitor the window maximizes on
        if _valid_place(normal := geometry.removeprefix("zoomed").strip()):
            self._normal_geo = normal
            if self.root.state() == "zoomed":
                self.root.state("normal")
            self.root.geometry(normal)
        if geometry.startswith("zoomed"):
            self.root.state("zoomed")

    def _open_panel(self, name):
        _, size, minsize, _ = PANELS[name]
        top = self.panels[name] = tk.Toplevel(self.root, bg=self.th["bg"])  # not transient: stays when the main one is minimized
        top.minsize(*minsize)
        top.geometry(size)
        if _valid_place(geometry := self._panel_geo.get(name, "")):
            top.geometry(geometry)
        if sys.platform == "win32":
            top.attributes("-toolwindow", True)  # thin title bar
        top.protocol("WM_DELETE_WINDOW", lambda: self._toggle_panel(name))
        top.bind("<Configure>", self._on_move)
        cv = self.panel_canvas[name] = tk.Canvas(top, bg=self.th["bg"], highlightthickness=0)
        cv.pack(fill="both", expand=True)
        cv.bind("<Configure>", lambda e: self.redraw())
        tk.Button(top, text="⟲", command=lambda: self._reset_size(name), bg=self.th["bg"], fg=self.th["dim"],
                  relief="flat", bd=0, padx=3, pady=0, font=(FONT, 8), activebackground=self.th["accent"],
                  cursor="hand2").place(relx=1, x=-2, y=1, anchor="ne")
        if name == "graph":
            cv.bind("<Motion>", lambda e: self._hover_at(e.x))
            cv.bind("<Leave>", lambda e: self._hover_at(None))
        self._title()
        self._apply_topmost()

    def _reset_size(self, name=None):
        """Back to the size the window had at the very first start; the place stays."""
        if name:
            self.panels[name].geometry(PANELS[name][1])
        else:
            self.root.state("normal")
            self.root.geometry(MAIN_SIZE)

    def _toggle_panel(self, name):
        if top := self.panels.pop(name, None):
            self._panel_geo[name] = top.geometry()
            del self.panel_canvas[name]
            top.destroy()
        else:
            self._open_panel(name)

    def _on_focus(self, e):
        try:
            top = e.widget.winfo_toplevel()
        except (AttributeError, tk.TclError):  # e.g. a combobox popdown tkinter does not know
            return
        if top is self.root or top in self.panels.values():
            self._raise_group(top)

    def _raise_group(self, clicked):
        """Clicking one window brings the main, cockpit and graph windows of this instance up together."""
        for w in [self.root, *self.panels.values(), clicked]:  # the clicked one last, so it stays in front
            if w.winfo_exists() and w.state() != "iconic":
                w.lift()

    def _arrow_hover(self, xy):
        self._main_hover = xy
        draw(self.canvas, self._ticks(), self.th, xy)

    def _hover_at(self, x):
        self._hover = x
        if "graph" in self.panels:
            draw_graph(self.panel_canvas["graph"], self._ticks(), self.th, x)

    def _apply_topmost(self):
        """Keep cockpit and graph above the game (works with EVE in window or fixed window mode, not in fullscreen)."""
        for name, key in (("cockpit", "always_on_top"), ("graph", "graph_on_top")):
            if top := self.panels.get(name):
                top.attributes("-topmost", self.cfg.getboolean("general", key))

    def restart(self, char, mode=None):
        """Reopen the window as a fresh program, e.g. after switching between client and server."""
        self._restart(char, self._save_window(), mode or self.mode)  # same size and place
        self.root.destroy()

    def _close(self):
        self._save_window()
        self.root.destroy()

    def _window_key(self, char):
        # one entry per character, since several client instances run side by side
        return "server" if self.mode == "server" else char or "client"

    def _on_move(self, e):
        """A window let go near another one docks to it (moves only, resizing never snaps)."""
        top = e.widget
        if top is not self.root and top not in self.panels.values():
            return
        if self._sizes.get(top) != (size := (e.width, e.height)):
            self._sizes[top] = size
            return
        if job := self._snap_jobs.pop(top, None):
            self.root.after_cancel(job)
        self._snap_jobs[top] = self.root.after(250, lambda: self._snap(top))

    def _snap(self, top):
        self._snap_jobs.pop(top, None)
        if not top.winfo_exists() or top.state() != "normal":
            return
        if (off := snap.offset(int(top.wm_frame(), 16))) is None:  # mouse still held: ask again shortly
            self._snap_jobs[top] = self.root.after(150, lambda: self._snap(top))
        elif off != (0, 0) and (m := re.search(r"\+(-?\d+)\+(-?\d+)$", top.geometry())):
            top.geometry(f"+{int(m.group(1)) + off[0]}+{int(m.group(2)) + off[1]}")

    def _track_place(self, event):
        if event.widget is self.root and self.root.state() == "normal":
            self._normal_geo = self.root.geometry()

    def _save_window(self):
        state = self.root.state()
        normal = self.root.geometry() if state == "normal" else self._normal_geo or ""
        geometry = f"zoomed {normal}".strip() if state == "zoomed" else normal
        key = self._layout_key  # the character the windows belong to, also right after picking another one
        try:
            update_config(self.cfg_path, {"windows": {key: geometry, **{
                f"{key}.{name}": self.panels[name].geometry() if name in self.panels
                else f"off {self._panel_geo.get(name, '')}".strip() for name in PANELS}}})
        except OSError:
            pass  # a read-only folder must not keep the window from closing
        return geometry

    def _paste_code(self):
        """Take the server's connection code "host:port/token" from the clipboard and reconnect with it."""
        try:
            text = self.root.clipboard_get().strip()
        except tk.TclError:
            text = ""
        m = re.fullmatch(r"(.+):(\d+)/(\S+)", text)
        if not m or not 0 < int(m.group(2)) < 65536:
            messagebox.showerror("Paste code", "The clipboard holds no connection code.\n"
                                 "Copy it on the server (address:port/token) first.", parent=self.root)
            return
        host, port, token = m.groups()
        update_config(self.cfg_path, {"client": {"host": host}, "general": {"port": port, "token": token}})
        self.restart(self.char.get())

    def _copy(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status.set("connection code copied")

    def call(self, fn, *args):
        asyncio.run_coroutine_threadsafe(fn(*args), self.loop)

    def _ticks(self):
        return self.replay[:self.pos + 1] if self.replay is not None else self.live

    def redraw(self):
        ticks = self._ticks()
        draw(self.canvas, ticks, self.th, self._main_hover)
        for name, cv in self.panel_canvas.items():
            if name == "graph":
                draw_graph(cv, ticks, self.th, self._hover)
            else:
                PANELS[name][3](cv, ticks, self.th)

    def _drain(self):
        """Handle what the network thread queued."""
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg.get("type")
                if kind == "tick":
                    self.live.append(msg)
                elif kind == "reset":
                    self.live = []
                elif kind == "status":
                    self.status.set(msg["text"])
                elif kind == "warning":
                    self.warning.set(msg["text"])
                elif kind == "history":
                    self._history(msg["sessions"])
                elif kind == "session":
                    self._start_replay(msg["ticks"])
                elif kind == "clients":
                    names = [f"{', '.join(chars) or 'no character yet'} ({addr})" for addr, chars in msg["list"]]
                    self.clients.set(f"{len(names)} connected:   " + "   ·   ".join(names) if names
                                     else "no client connected")
                elif kind == "update":
                    self._offer_update(msg)
                elif kind == "updated":
                    update_config(self.cfg_path, {"update": {"installed": msg["tag"]}})  # tells the other windows
                    self.restart(self._char())
                    return
                if kind in ("tick", "reset") and self.replay is None:
                    self.redraw()
        except queue.Empty:
            pass
        self.root.after(100, self._drain)

    def _set_char(self):
        char = self.char.get()
        if snap.char_open(char, int(self.root.wm_frame(), 16)):
            # one instance per character: a second one would sit on the first one's places and overwrite them
            self.char.set(self.backend.char or "")
            self.status.set(f"{char} is already open in another window")
            return
        self._save_window()  # keep the places of the character we leave
        self.call(self.backend.set_char, self.char.get())
        self._title()
        self._restore_layout()

    def _toggle(self):
        self.enabled = not self.enabled
        self.call(self.backend.set_enabled, self.enabled)
        self._conn_text()

    def _conn_text(self):
        self.conn.configure(text=f"Connection: {'on' if self.enabled else 'off'}")

    # --- replays ---

    def _history(self, sessions):
        top = self._dialog("Replays")
        if not sessions:
            tk.Label(top, text="No fights stored yet.", bg=self.th["bg"], fg=self.th["fg"]).pack(
                padx=20, pady=20)
            return
        lb = tk.Listbox(top, width=28, height=15, bg=self.th["panel"], fg=self.th["fg"], relief="flat",
                        font=(FONT, 10))
        lb.insert("end", *map(fight_label, sessions))
        lb.pack(padx=10, pady=10)

        def play(_=None):
            if sel := lb.curselection():
                self.call(self.backend.load, sessions[sel[0]])
                top.destroy()
        lb.bind("<Double-1>", play)
        self._button(top, "Play", play).pack(pady=(0, 10))

    def _start_replay(self, ticks):
        if not ticks:
            return
        self.replay, self.pos, self.playing = ticks, 0, True
        self.scale.configure(to=len(ticks) - 1)
        self.scale.set(0)
        self.play_btn.configure(text="Stop")
        self.replay_bar.pack(fill="x", after=self.bar)
        self._schedule()
        self._seek(0)

    def _schedule(self):
        if self._timer:
            self.root.after_cancel(self._timer)
        self._timer = self.root.after(TICK * 1000, self._step)

    def _step(self):
        self._timer = None
        if self.replay is None:
            return
        if self.playing and self.pos < len(self.replay) - 1:
            self.scale.set(self.pos + 1)
        self._schedule()

    def _seek(self, value):
        if self.replay is None:
            return
        self.pos = int(float(value))
        t0 = self.replay[0]["t"]
        self.replay_label.configure(
            text=f"{_mmss(self.replay[self.pos]['t'] - t0 + TICK)} / {_mmss(self.replay[-1]['t'] - t0 + TICK)}")
        self.redraw()

    def _play_pause(self):
        if not self.playing and self.pos >= len(self.replay) - 1:
            self.scale.set(0)  # Start at the end replays from the beginning
        self.playing = not self.playing
        self.play_btn.configure(text="Stop" if self.playing else "Start")

    def _stop_replay(self):
        if self._timer:
            self.root.after_cancel(self._timer)
            self._timer = None
        self.replay = None
        self.replay_bar.pack_forget()
        self.redraw()

    # --- update ---

    def _check_update(self, manual):
        """Ask GitHub in the background; the answer comes back through the queue."""
        if not update.can_install():
            self.status.set("running from source: no self-update")
            return

        def run():
            try:
                found = update.latest()
            except (OSError, ValueError, KeyError) as e:
                if manual:
                    self.q.put({"type": "status", "text": f"update check failed: {e}"})
                return
            if found:
                self.q.put({"type": "update", "tag": found[0], "assets": found[1], "manual": manual})
            elif manual:
                self.q.put({"type": "status", "text": f"v{update.VERSION} is the newest version"})
        threading.Thread(target=run, daemon=True).start()

    def _offer_update(self, msg):
        tag = msg["tag"]
        state = configparser.ConfigParser(interpolation=None)
        state.read(self.cfg_path, encoding="utf-8-sig")  # fresh: another window may have installed it already
        state = state["update"] if state.has_section("update") else {}
        if state.get("installed") == tag:
            if messagebox.askyesno("Update", f"{tag} was installed by another eos-fight-mon window.\n\n"
                                   "Restart this window with it now?", parent=self.root):
                self.restart(self._char())
            return
        if not msg["manual"] and state.get("skip") == tag:
            return
        if not messagebox.askyesno("Update", f"eos-fight-mon {tag} is available (this is v{update.VERSION}).\n\n"
                                   "Download and install it now? The window restarts afterwards.\n\n"
                                   "No: not asked again for this version (Settings › Check for updates still does).",
                                   parent=self.root):
            update_config(self.cfg_path, {"update": {"skip": tag}})
            return
        self.status.set(f"downloading {tag} …")

        def run():
            try:
                update.install(msg["assets"])
                self.q.put({"type": "updated", "tag": tag})
            except (OSError, ValueError, KeyError) as e:
                self.q.put({"type": "status", "text": f"update failed: {e}"})
        threading.Thread(target=run, daemon=True).start()

    # --- settings ---

    def _dialog(self, title):
        top = tk.Toplevel(self.root, bg=self.th["bg"])
        top.title(title)
        top.transient(self.root)
        return top

    def _settings(self):
        if (top := getattr(self, "_settings_top", None)) and top.winfo_exists():  # one settings dialog per window
            top.deiconify()
            top.lift()
            top.focus_force()
            return
        top = self._settings_top = self._dialog("Settings")
        fields = [("Mode", "general", "mode"), ("Server address or connection code", "client", "host"),
                  ("Port", "general", "port"), ("Token", "general", "token"), ("Fight ends after idle seconds", "general", "idle_end"),
                  ("Cockpit always on top (over EVE in window mode)", "general", "always_on_top"),
                  ("Graph always on top (over EVE in window mode)", "general", "graph_on_top"),
                  ("Show friendly fire (when connected, the server's setting counts)", "general", "friendly_fire"),
                  ("Check for updates at start", "update", "check"),
                  ("Log folder", "client", "log_dir")]  # log folder last: the browse button sits in its row
        values = {}
        for row, (label, sec, key) in enumerate(fields):
            tk.Label(top, text=label, bg=self.th["bg"], fg=self.th["fg"]).grid(row=row, column=0, sticky="w",
                                                                              padx=10, pady=4)
            # the mode belongs to this start, not to the shared config
            var = values[(sec, key)] = tk.StringVar(value=self.mode if key == "mode" else self.cfg[sec][key])
            if key == "mode":
                ttk.Combobox(top, textvariable=var, values=["client", "server"], state="readonly", width=12).grid(
                    row=row, column=1, sticky="w", padx=10)
            elif key in ("always_on_top", "graph_on_top", "friendly_fire", "check"):
                var.set("yes" if self.cfg.getboolean(sec, key) else "no")
                # native ttk box (white with a dark tick): tk.Checkbutton draws the tick in system colours
                ttk.Style(top).configure("Dark.TCheckbutton", background=self.th["bg"])
                ttk.Checkbutton(top, variable=var, onvalue="yes", offvalue="no", style="Dark.TCheckbutton").grid(
                    row=row, column=1, sticky="w", padx=6)
            else:
                tk.Entry(top, textvariable=var, width=50).grid(row=row, column=1, padx=10)
        log_dir = values[("client", "log_dir")]
        self._button(top, "…", lambda: log_dir.set(filedialog.askdirectory(parent=top) or log_dir.get())).grid(
            row=len(fields) - 1, column=2, padx=(0, 10))

        def save():
            # a pasted connection code "host:port/token" fills all three fields
            if m := re.fullmatch(r"(.+):(\d+)/(\S+)", values[("client", "host")].get().strip()):
                for key, value in zip((("client", "host"), ("general", "port"), ("general", "token")), m.groups()):
                    values[key].set(value)
            port = values[("general", "port")].get().strip()
            if not port.isdigit() or not 0 < int(port) < 65536:
                messagebox.showerror("Settings", "Port must be a number from 1 to 65535.", parent=top)
                return
            idle = values[("general", "idle_end")].get().strip()
            if not idle.isdigit() or not 5 <= int(idle) <= 3600:
                messagebox.showerror("Settings", "Idle seconds must be a number from 5 to 3600.", parent=top)
                return
            mode = values.pop(("general", "mode")).get()
            changed = {k for k, var in values.items() if self.cfg[k[0]][k[1]] != var.get().strip()}
            new = {}
            for sec, key in changed:
                self.cfg[sec][key] = new.setdefault(sec, {})[key] = values[(sec, key)].get().strip()
            update_config(self.cfg_path, new)
            top.destroy()
            self._apply_topmost()
            # the rest is read live; a server keeps its running fight unless mode or port change
            reload = {("general", "port")}
            if self.mode == "client":
                reload |= {("client", "host"), ("general", "token")}
            if changed & reload or mode != self.mode:
                self.restart(self.char.get() if self.mode == "client" else None, mode)
            else:
                self.status.set("settings saved")
        self._button(top, "Check for updates", lambda: self._check_update(manual=True)).grid(
            row=len(fields), column=0, sticky="w", padx=10, pady=10)
        self._button(top, "Save", save).grid(row=len(fields), column=1, sticky="e", padx=10, pady=10)
        x, y = map(int, re.search(r"\+(-?\d+)\+(-?\d+)$", self.root.geometry()).groups())
        top.geometry(f"+{x + 50}+{y + 50}")  # top left corner 50 px into the main window


def _mmss(secs):
    return f"{int(secs) // 60:02d}:{int(secs) % 60:02d}"
