"""Tk window: client ships left, everyone else right, effects as arrows in between."""
import asyncio
import math
import queue
import tkinter as tk
from collections import defaultdict, deque
from tkinter import filedialog, messagebox, ttk

from fight import DRONES_L, EWAR, REPS, TICK, WINDOW

THEMES = {
    "client": {"bg": "#0e1621", "panel": "#172333", "fg": "#d8e4f0", "dim": "#71859a", "accent": "#3fa9f5"},
    "server": {"bg": "#1a120c", "panel": "#2a1d13", "fg": "#f0e4d8", "dim": "#9a8571", "accent": "#f5a33f"},
}
COLORS = {"dmg": "#e5484d", "shield": "#30a46c", "armor": "#30a46c", "hull": "#30a46c", "cap": "#e2b93b",
          "neut": "#9d5bd2", "nos": "#9d5bd2", "scram": "#f76b15", "point": "#f76b15", "jam": "#f76b15"}
OFFSET = {"dmg": -6, "shield": 0, "armor": 0, "hull": 0, "cap": 3, "neut": 6, "nos": 6, "scram": 9, "point": 9, "jam": 9}
LEGEND = [("Schaden", "dmg"), ("Reps", "shield"), ("Cap", "cap"), ("Neut/Nos", "neut"), ("Scram/Punkt/Jam", "scram")]
BOX_W, ROW = 260, 46
FONT = "Segoe UI"


def fmt(rate):
    return f"{rate / 1000:.1f}k" if rate >= 1000 else f"{rate:.0f}"


def draw(cv, window, th):
    """Draw the last ticks as per-second rates."""
    cv.delete("all")
    w, h = cv.winfo_width(), cv.winfo_height()
    if not window:
        cv.create_text(w / 2, h / 2, text="Warte auf Kampf …", fill=th["dim"], font=(FONT, 16))
        return
    secs = TICK * len(window)
    rates, ewar = defaultdict(float), set()
    for t in window:
        for k, s, d, a in t["flows"]:
            if k in EWAR:
                ewar.add((k, s, d))
            else:
                rates[(k, s, d)] += a / secs
    ships, left_names = window[-1]["ships"], set(window[-1]["left"]) | {DRONES_L}
    out_dmg, in_dmg, in_rep = defaultdict(float), defaultdict(float), defaultdict(float)
    for (k, s, d), r in rates.items():
        if k == "dmg":
            out_dmg[s] += r
            in_dmg[d] += r
        elif k in REPS:
            in_rep[d] += r

    names = {n for _, s, d in [*rates, *ewar] for n in (s, d)}
    left = sorted(n for n in names if n in left_names)
    right = sorted(names - set(left), key=lambda n: -(out_dmg[n] + in_dmg[n] + in_rep[n]))
    rows = max(2, (h - 60) // ROW)
    if len(right) > rows:
        right = right[:rows - 1] + [f"+{len(right) - rows + 1} weitere"]

    pos = {}
    for col, column in enumerate((left[:rows], right)):
        x = 20 if col == 0 else w - 20 - BOX_W
        for i, n in enumerate(column):
            pos[n] = (x + BOX_W if col == 0 else x, 20 + i * ROW + ROW / 2 - 3, col, x, 20 + i * ROW)

    for (k, s, d), r in rates.items():
        _arrow(cv, pos, k, s, d, 1 + min(6, math.log10(1 + r)))
    for k, s, d in ewar:
        _arrow(cv, pos, k, s, d, 2, dash=(4, 3))

    for n, (_, _, col, x, y) in pos.items():
        cv.create_rectangle(x, y, x + BOX_W, y + ROW - 6, fill=th["panel"],
                            outline=th["accent"] if col == 0 else th["dim"])
        cv.create_text(x + 8, y + 4, anchor="nw", text=n, fill=th["fg"], font=(FONT, 10, "bold"))
        info = f"{ships.get(n, '')}   aus {fmt(out_dmg[n])}  ein {fmt(in_dmg[n])}  rep {fmt(in_rep[n])}"
        cv.create_text(x + 8, y + 22, anchor="nw", text=info, fill=th["dim"], font=(FONT, 9))

    x = 20
    for label, kind in LEGEND:
        cv.create_line(x, h - 14, x + 20, h - 14, fill=COLORS[kind], width=3)
        x = cv.bbox(cv.create_text(x + 26, h - 14, anchor="w", text=label, fill=th["dim"], font=(FONT, 9)))[2] + 18


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


class App:
    def __init__(self, mode, backend, loop, q, cfg, cfg_path):
        self.mode, self.backend, self.loop, self.q = mode, backend, loop, q
        self.cfg, self.cfg_path = cfg, cfg_path
        self.th = th = THEMES[mode]
        self.live = deque(maxlen=WINDOW)
        self.replay, self.pos, self.playing, self._timer = None, 0, False, None

        root = self.root = tk.Tk()
        root.title(f"eos-fight-mon – {'Server' if mode == 'server' else 'Client'}")
        root.geometry("1150x720")
        root.configure(bg=th["bg"])

        self.bar = tk.Frame(root, bg=th["panel"])
        self.bar.pack(fill="x")
        self.status = tk.StringVar()
        tk.Label(self.bar, textvariable=self.status, bg=th["panel"], fg=th["fg"], font=(FONT, 10)).pack(
            side="left", padx=10)
        self._button(self.bar, "Einstellungen", self._settings).pack(side="right", padx=4, pady=4)
        self._button(self.bar, "Verlauf", lambda: self.call(backend.history)).pack(side="right", padx=4)
        self._button(self.bar, "Reset", lambda: self.call(backend.reset)).pack(side="right", padx=4)
        if mode == "client":
            self.enabled = cfg.getboolean("client", "auto_connect")
            self.conn = self._button(self.bar, "", self._toggle)
            self.conn.pack(side="right", padx=4)
            self._conn_text()

        self.replay_bar = tk.Frame(root, bg=th["panel"])
        self.play_btn = self._button(self.replay_bar, "Pause", self._play_pause)
        self.play_btn.pack(side="left", padx=4, pady=4)
        self.scale = tk.Scale(self.replay_bar, orient="horizontal", showvalue=False, command=self._seek,
                              bg=th["panel"], fg=th["fg"], troughcolor=th["bg"], highlightthickness=0)
        self.scale.pack(side="left", fill="x", expand=True, padx=4)
        self.replay_label = tk.Label(self.replay_bar, bg=th["panel"], fg=th["fg"])
        self.replay_label.pack(side="left", padx=4)
        self._button(self.replay_bar, "Zurück zu Live", self._stop_replay).pack(side="left", padx=4)

        self.canvas = tk.Canvas(root, bg=th["bg"], highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.redraw())
        root.after(100, self._drain)

    def _button(self, parent, text, cmd):
        th = self.th
        return tk.Button(parent, text=text, command=cmd, bg=th["bg"], fg=th["fg"], relief="flat",
                         activebackground=th["accent"], activeforeground=th["bg"], padx=8)

    def call(self, fn, *args):
        asyncio.run_coroutine_threadsafe(fn(*args), self.loop)

    def redraw(self):
        if self.replay is not None:
            draw(self.canvas, self.replay[max(0, self.pos - WINDOW + 1):self.pos + 1], self.th)
        else:
            draw(self.canvas, list(self.live), self.th)

    def _drain(self):
        """Handle what the network thread queued."""
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg.get("type")
                if kind == "tick":
                    self.live.append(msg)
                elif kind == "reset":
                    self.live.clear()
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

    def _toggle(self):
        self.enabled = not self.enabled
        self.call(self.backend.set_enabled, self.enabled)
        self._conn_text()

    def _conn_text(self):
        self.conn.configure(text=f"Verbindung: {'an' if self.enabled else 'aus'}")

    # --- history / replay ---

    def _history(self, sessions):
        top = self._dialog("Verlauf")
        if not sessions:
            tk.Label(top, text="Noch keine Kämpfe gespeichert.", bg=self.th["bg"], fg=self.th["fg"]).pack(padx=20, pady=20)
            return
        lb = tk.Listbox(top, width=32, height=15, bg=self.th["panel"], fg=self.th["fg"], relief="flat")
        lb.insert("end", *sessions)
        lb.pack(padx=10, pady=10)

        def play(_=None):
            if sel := lb.curselection():
                self.call(self.backend.load, sessions[sel[0]])
                top.destroy()
        lb.bind("<Double-1>", play)
        self._button(top, "Abspielen", play).pack(pady=(0, 10))

    def _start_replay(self, ticks):
        if not ticks:
            return
        self.replay, self.pos, self.playing = ticks, 0, True
        self.scale.configure(to=len(ticks) - 1)
        self.scale.set(0)
        self.play_btn.configure(text="Pause")
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
        self.replay_label.configure(text=f"{self.pos * TICK} s / {(len(self.replay) - 1) * TICK} s")
        self.redraw()

    def _play_pause(self):
        self.playing = not self.playing
        self.play_btn.configure(text="Pause" if self.playing else "Abspielen")

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
        top = self._dialog("Einstellungen")
        fields = [("Modus", "general", "mode"), ("Server-Adresse", "client", "host"), ("Port", "general", "port"),
                  ("Token", "general", "token"), ("Log-Ordner", "client", "log_dir")]
        values = {}
        for row, (label, sec, key) in enumerate(fields):
            tk.Label(top, text=label, bg=self.th["bg"], fg=self.th["fg"]).grid(row=row, column=0, sticky="w", padx=10, pady=4)
            var = values[(sec, key)] = tk.StringVar(value=self.cfg[sec][key])
            if key == "mode":
                ttk.Combobox(top, textvariable=var, values=["client", "server"], state="readonly", width=12).grid(
                    row=row, column=1, sticky="w", padx=10)
            else:
                tk.Entry(top, textvariable=var, width=50).grid(row=row, column=1, padx=10)
        browse = lambda: values[("client", "log_dir")].set(  # noqa: E731
            filedialog.askdirectory(parent=top) or values[("client", "log_dir")].get())
        self._button(top, "…", browse).grid(row=len(fields) - 1, column=2, padx=(0, 10))

        def save():
            port = values[("general", "port")].get().strip()
            if not port.isdigit() or not 0 < int(port) < 65536:
                messagebox.showerror("Einstellungen", "Port muss eine Zahl zwischen 1 und 65535 sein.", parent=top)
                return
            for (sec, key), var in values.items():
                self.cfg[sec][key] = var.get().strip()
            with open(self.cfg_path, "w", encoding="utf-8") as fh:
                self.cfg.write(fh)
            messagebox.showinfo("Einstellungen", "Gespeichert. Adresse, Token und Log-Ordner gelten sofort bzw. "
                                "ab der nächsten Verbindung, Modus und Server-Port nach einem Neustart.", parent=top)
            top.destroy()
        self._button(top, "Speichern", save).grid(row=len(fields), column=1, sticky="e", padx=10, pady=10)
