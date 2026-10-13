"""Tk window: cockpit on top, client ships left, everyone else right, effects as arrows in between."""
import asyncio
import math
import queue
import re
import tkinter as tk
from collections import defaultdict
from datetime import datetime, timezone
from tkinter import filedialog, messagebox, ttk

import logparse
from fight import EWAR, REPS, TICK, WINDOW

THEMES = {
    "client": {"bg": "#0e1621", "panel": "#172333", "fg": "#d8e4f0", "dim": "#71859a", "accent": "#3fa9f5"},
    "server": {"bg": "#1a120c", "panel": "#2a1d13", "fg": "#f0e4d8", "dim": "#9a8571", "accent": "#f5a33f"},
}
COLORS = {"dmg": "#e5484d", "shield": "#30a46c", "armor": "#30a46c", "hull": "#30a46c", "cap": "#e2b93b",
          "neut": "#9d5bd2", "nos": "#9d5bd2", "scram": "#f76b15", "point": "#f76b15", "jam": "#f76b15"}
OFFSET = {"dmg": -6, "shield": 0, "armor": 0, "hull": 0, "cap": 3, "neut": 6, "nos": 6, "scram": 9, "point": 9, "jam": 9}
LEGEND = [("Damage", "dmg"), ("Reps", "shield"), ("Cap", "cap"), ("Neut/Nos", "neut"), ("Scram/Point/Jam", "scram")]
GROUPS = [("Damage", "dmg", {"dmg"}), ("Reps", "shield", REPS - {"cap"}), ("Cap", "cap", {"cap"}),
          ("Neut/Nos", "neut", {"neut", "nos"})]
BOX_W, COCKPIT_H = 260, 70
FONT = "Segoe UI"


def fmt(v):
    return f"{v / 1e6:.1f}M" if v >= 1e6 else f"{v / 1000:.1f}k" if v >= 1000 else f"{v:.0f}"


def draw(cv, ticks, th):
    """Draw a fight up to its last tick: cockpit with team sums, ships with per-second rates of the last 10 s."""
    cv.delete("all")
    w, h = cv.winfo_width(), cv.winfo_height()
    if not ticks:
        cv.create_text(w / 2, h / 2, text="Waiting for a fight …", fill=th["dim"], font=(FONT, 16))
        return
    last = ticks[-1]
    ships, left_names = last["ships"], set(last["left"])
    window = ticks[-WINDOW:]
    secs = TICK * len(window)
    rates, ewar = defaultdict(float), set()
    for t in window:
        for k, s, d, a in t["flows"]:
            if k in EWAR:
                ewar.add((k, s, d))
            else:
                rates[(k, s, d)] += a / secs
    _cockpit(cv, w, th, ticks, rates, left_names)

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

    top, usable = COCKPIT_H + 10, h - COCKPIT_H - 40
    row = max(38, min(56, usable / max(1, len(left), len(right))))  # a 10 man team always fits
    rows = max(2, int(usable // row))
    if len(right) > rows:
        right = right[:rows - 1] + [f"+{len(right) - rows + 1} more"]
    pos = {}
    for col, column in enumerate((left[:rows], right)):
        x = 20 if col == 0 else w - 20 - BOX_W
        for i, n in enumerate(column):
            y = top + i * row
            pos[n] = (x + BOX_W if col == 0 else x, y + (row - 6) / 2, col, x, y)

    for (k, s, d), r in rates.items():
        _arrow(cv, pos, k, s, d, 1 + min(6, math.log10(1 + r)))
    for k, s, d in ewar:
        _arrow(cv, pos, k, s, d, 2, dash=(4, 3))
    for n, (_, _, col, x, y) in pos.items():
        cv.create_rectangle(x, y, x + BOX_W, y + row - 6, fill=th["panel"],
                            outline=th["accent"] if col == 0 else th["dim"])
        cv.create_text(x + 8, y + 3, anchor="nw", text=n, fill=th["fg"], font=(FONT, 10, "bold"))
        info = f"{ships.get(n, '')}   out {fmt(out_dmg[n])}  in {fmt(in_dmg[n])}  rep {fmt(in_rep[n])}"
        cv.create_text(x + 8, y + 19, anchor="nw", text=info, fill=th["dim"], font=(FONT, 9))

    x = 20
    for label, kind in LEGEND:
        cv.create_line(x, h - 14, x + 20, h - 14, fill=COLORS[kind], width=3)
        x = cv.bbox(cv.create_text(x + 26, h - 14, anchor="w", text=label, fill=th["dim"], font=(FONT, 9)))[2] + 18


def _cockpit(cv, w, th, ticks, rates, left_names):
    """Fight clock plus the team's outgoing/incoming sums: per second now and over the whole fight."""
    total = defaultdict(float)
    for t in ticks:
        for k, s, d, a in t["flows"]:
            total[(k, s in left_names, d in left_names)] += a
    now = defaultdict(float)
    for (k, s, d), r in rates.items():
        now[(k, s in left_names, d in left_names)] += r

    def side(values, kinds, outgoing):
        return sum(v for (k, s_left, d_left), v in values.items() if k in kinds and (s_left if outgoing else d_left))

    secs = ticks[-1]["t"] - ticks[-1].get("start", ticks[0]["t"]) + TICK
    col_w = 175
    x = max(20, (w - 120 - col_w * len(GROUPS)) / 2)
    cv.create_rectangle(x - 10, 6, x + 120 + col_w * len(GROUPS), COCKPIT_H - 4, fill=th["panel"], outline=th["dim"])
    cv.create_text(x + 50, COCKPIT_H / 2, text=_mmss(secs), fill=th["accent"],
                   font=(FONT, 20, "bold"))
    x += 120
    for label, color_kind, kinds in GROUPS:
        cv.create_text(x, 12, anchor="nw", text=label, fill=COLORS[color_kind], font=(FONT, 10, "bold"))
        for i, (word, outgoing) in enumerate((("out", True), ("in", False))):
            text = f"{word} {fmt(side(now, kinds, outgoing))}/s   Σ {fmt(side(total, kinds, outgoing))}"
            cv.create_text(x, 32 + i * 16, anchor="nw", text=text, fill=th["fg"], font=(FONT, 9))
        x += col_w


def _arrow(cv, pos, kind, s, d, width, dash=None):
    if s not in pos or d not in pos:
        return
    (x1, y1, c1, *_), (x2, y2, c2, *_) = pos[s], pos[d]
    y1, y2 = y1 + OFFSET[kind], y2 + OFFSET[kind]
    opts = {"fill": COLORS[kind], "width": width, "dash": dash, "arrow": "last"}
    if c1 == c2:  # same side: bow towards the middle
        mx = x1 + (140 if c1 == 0 else -140)
        cv.create_line(x1, y1, mx, (y1 + y2) / 2, x2, y2, smooth=True, **opts)
    else:
        cv.create_line(x1, y1, x2, y2, **opts)


def fight_label(name):
    """'20261013_191334.jsonl.gz' (UTC) -> '2026-10-13  21:13:34' (local time)."""
    start = datetime.strptime(name[:15], "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
    return start.astimezone().strftime("%Y-%m-%d  %H:%M:%S")


class App:
    def __init__(self, mode, backend, loop, q, cfg, cfg_path, connect_code=None):
        self.mode, self.backend, self.loop, self.q = mode, backend, loop, q
        self.cfg, self.cfg_path = cfg, cfg_path
        self.th = th = THEMES[mode]
        self.live = []  # ticks of the running fight
        self.replay, self.pos, self.playing, self._timer = None, 0, False, None

        root = self.root = tk.Tk()
        root.geometry("1150x720")
        root.minsize(900, 560)
        root.configure(bg=th["bg"])

        self.bar = tk.Frame(root, bg=th["panel"])
        self.bar.pack(fill="x")
        if mode == "client":
            self.char = tk.StringVar(value=backend.char or "")
            box = ttk.Combobox(self.bar, textvariable=self.char, state="readonly", width=24,
                               postcommand=lambda: box.configure(values=logparse.characters(cfg["client"]["log_dir"])))
            box.bind("<<ComboboxSelected>>", lambda e: self._set_char())
            box.pack(side="left", padx=(10, 4), pady=4)
        else:
            tk.Label(self.bar, text="Connection code:", bg=th["panel"], fg=th["dim"]).pack(side="left", padx=(10, 4))
            code = tk.Entry(self.bar, width=len(connect_code) + 2, bg=th["bg"], fg=th["fg"], relief="flat",
                            readonlybackground=th["bg"])
            code.insert(0, connect_code)
            code.configure(state="readonly")
            code.pack(side="left", pady=4)
            self._button(self.bar, "Copy", lambda: self._copy(connect_code)).pack(side="left", padx=4)
        self.status = tk.StringVar()
        tk.Label(self.bar, textvariable=self.status, bg=th["panel"], fg=th["fg"], font=(FONT, 10)).pack(
            side="left", padx=10)
        self._button(self.bar, "Settings", self._settings).pack(side="right", padx=4, pady=4)
        self._button(self.bar, "Replays", lambda: self.call(backend.history)).pack(side="right", padx=4)
        self._button(self.bar, "Reset", lambda: self.call(backend.reset)).pack(side="right", padx=4)
        if mode == "client":
            self.enabled = cfg.getboolean("client", "auto_connect")
            self.conn = self._button(self.bar, "", self._toggle)
            self.conn.pack(side="right", padx=4)
            self._conn_text()
        self._title()

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
        root.after(100, self._drain)

    def _button(self, parent, text, cmd):
        th = self.th
        return tk.Button(parent, text=text, command=cmd, bg=th["bg"], fg=th["fg"], relief="flat",
                         activebackground=th["accent"], activeforeground=th["bg"], padx=8)

    def _title(self):
        who = f"Client – {self.char.get() or 'no character'}" if self.mode == "client" else "Server"
        self.root.title(f"eos-fight-mon – {who}")

    def _copy(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status.set("connection code copied")

    def call(self, fn, *args):
        asyncio.run_coroutine_threadsafe(fn(*args), self.loop)

    def redraw(self):
        draw(self.canvas, self.replay[:self.pos + 1] if self.replay is not None else self.live, self.th)

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
                elif kind == "history":
                    self._history(msg["sessions"])
                elif kind == "session":
                    self._start_replay(msg["ticks"])
                if kind in ("tick", "reset") and self.replay is None:
                    self.redraw()
        except queue.Empty:
            pass
        self.root.after(100, self._drain)

    def _set_char(self):
        self.call(self.backend.set_char, self.char.get())
        self._title()

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

    # --- settings ---

    def _dialog(self, title):
        top = tk.Toplevel(self.root, bg=self.th["bg"])
        top.title(title)
        top.transient(self.root)
        return top

    def _settings(self):
        top = self._dialog("Settings")
        fields = [("Mode", "general", "mode"), ("Server address or connection code", "client", "host"),
                  ("Port", "general", "port"), ("Token", "general", "token"), ("Log folder", "client", "log_dir")]
        values = {}
        for row, (label, sec, key) in enumerate(fields):
            tk.Label(top, text=label, bg=self.th["bg"], fg=self.th["fg"]).grid(row=row, column=0, sticky="w",
                                                                              padx=10, pady=4)
            var = values[(sec, key)] = tk.StringVar(value=self.cfg[sec][key])
            if key == "mode":
                ttk.Combobox(top, textvariable=var, values=["client", "server"], state="readonly", width=12).grid(
                    row=row, column=1, sticky="w", padx=10)
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
            for (sec, key), var in values.items():
                self.cfg[sec][key] = var.get().strip()
            with open(self.cfg_path, "w", encoding="utf-8") as fh:
                self.cfg.write(fh)
            messagebox.showinfo("Settings", "Saved. Client settings apply from the next connection, "
                                "mode and server port after a restart.", parent=top)
            top.destroy()
        self._button(top, "Save", save).grid(row=len(fields), column=1, sticky="e", padx=10, pady=10)


def _mmss(secs):
    return f"{int(secs) // 60:02d}:{int(secs) % 60:02d}"
