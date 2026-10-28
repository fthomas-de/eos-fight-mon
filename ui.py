"""Tk windows: one tab per client character and the server; client ships left, everyone else right, effects as
arrows in between; small cockpit and graph windows per tab."""
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
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import logparse
import net
import snap
import update
from fight import BURST_SECS, DRONES, EWAR, IDLE_END, REPS, TICK, WINDOW, solo_char

THEMES = {
    "client": {"bg": "#0e1621", "panel": "#172333", "fg": "#d8e4f0", "dim": "#71859a", "accent": "#3fa9f5"},
    "server": {"bg": "#1a120c", "panel": "#2a1d13", "fg": "#f0e4d8", "dim": "#9a8571", "accent": "#f5a33f"},
}
COLORS = {"dmg": "#e5484d", "shield": "#30a46c", "armor": "#30a46c", "hull": "#30a46c", "cap": "#e2b93b",
          "neut": "#9d5bd2", "nos": "#9d5bd2", "scram": "#f76b15", "point": "#f76b15", "jam": "#05c3dd"}
OFFSET = {"dmg": -11, "shield": -4, "armor": -4, "hull": -4, "cap": 2, "neut": 7, "nos": 7, "scram": 11, "point": 11,
          "jam": 15}  # within the smallest box (32 px)
LANE = {k: sorted(set(OFFSET.values())).index(v) for k, v in OFFSET.items()}  # 0 = damage … 5 = jam
LEGEND = [("Damage", "dmg"), ("Reps", "shield"), ("Cap", "cap"), ("Neut/Nos", "neut"), ("Scram/Point", "scram"),
          ("Jam", "jam")]
LEGEND_OF = {"dmg": "dmg", "shield": "shield", "armor": "shield", "hull": "shield", "cap": "cap",
             "neut": "neut", "nos": "neut", "scram": "scram", "point": "scram", "jam": "jam"}  # arrow kind → entry
GROUPS = [("Damage", "dmg", {"dmg"}), ("Reps", "shield", REPS - {"cap"}), ("Cap", "cap", {"cap"}),
          ("Neut/Nos", "neut", {"neut", "nos"})]
EWAR_ROWS = [("Scram/Point", "scram", {"scram", "point"}), ("Jam", "jam", {"jam"})]  # graph: active effects (_ewar)
JAM_ROW = ("Jams", "jam", {"jam"})  # cockpit
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
    """Per-second rates of the given ticks; ewar has no amount (see _ewar)."""
    secs = TICK * len(window)
    rates = defaultdict(float)
    for t in window:
        for k, s, d, a in t["flows"]:
            if k not in EWAR:
                rates[(k, s, d)] += a / secs
    return rates


JAM_TICKS = 20 // TICK  # a jam is logged once and holds for the ECM cycle of 20 s


def _ewar(ticks, end=None):
    """Ewar active at ticks[end - 1]: scram/point seen in the last 10 s, a jam in the last 20 s."""
    end = len(ticks) if end is None else end
    return {(k, s, d) for back, t in enumerate(reversed(ticks[max(0, end - max(WINDOW, JAM_TICKS)):end]))
            for k, s, d, _ in t["flows"] if k in EWAR and back < (JAM_TICKS if k == "jam" else WINDOW)}


def _who(ticks, k, s, d):
    """Names for an arrow's hover: "Drones (owner unknown)" becomes the drone types the single events of the last
    ticks name (with the probable owner where the fight shows one)."""
    if DRONES not in (s, d):
        return s, d
    side, other = (1, d) if s == DRONES else (2, s)  # where the drone stands in an event, and who is on the other end
    names = ", ".join(sorted({e[side] for t in ticks[-max(WINDOW, JAM_TICKS):] for e in t.get("events", ())
                              if e[0] == k and e[3 - side] == other and e[side] != other})) or DRONES
    return (names, d) if side == 1 else (s, names)


def draw(cv, ticks, th, hover=None, off=(), countdown=None, can_end=False):
    """Draw a fight up to its last tick: ships with per-second rates of the last 10 s; hover (x, y) shows the arrows there.
    off: legend entries whose arrows are hidden (clicking an entry toggles it).
    countdown: seconds until the live fight ends; shown in place of the enemies while nobody acts.
    can_end: this window may end the fight (server, or a client without server): the countdown is clickable."""
    cv.delete("all")
    w, h = cv.winfo_width(), cv.winfo_height()
    if not ticks:
        cv.create_text(w / 2, h / 2, text="Waiting for a fight …", fill=th["dim"], font=(FONT, 16))
        return
    last = ticks[-1]
    ships, left_names = last["ships"], set(last["left"])
    rates, ewar = _rates(ticks[-WINDOW:]), _ewar(ticks)

    out_dmg, in_dmg, in_rep = defaultdict(float), defaultdict(float), defaultdict(float)
    for (k, s, d), r in rates.items():
        if k == "dmg":
            out_dmg[s] += r
            in_dmg[d] += r
        elif k in REPS:
            in_rep[d] += r
    bursts = last.get("bursts", {})  # a booster that only bursts still stands on the left
    names = ({n for _, s, d in [*rates, *ewar] for n in (s, d)} | set(bursts)) - set(last.get("hidden", ()))
    left = sorted(n for n in names if n in left_names)
    right = sorted(names - set(left), key=lambda n: -(out_dmg[n] + in_dmg[n] + in_rep[n]))

    top, usable = 10, h - 50
    row = max(38, min(56, usable / max(1, len(left), len(right))))  # a 10 man team always fits
    rows = max(2, int(usable // row))
    if len(right) > rows:
        right = right[:rows - 1] + [f"+{len(right) - rows + 1} more"]
    pos, tips = {}, {}
    if countdown is not None and not names:
        x, tags = w - 20 - BOX_W, ("end",) if can_end else ()  # tag "end": a click ends the fight now
        cv.create_rectangle(x, top, x + BOX_W, top + (80 if can_end else 64), fill=th["panel"], tags=tags,
                            outline=th["accent"] if can_end else th["dim"])
        cv.create_text(x + 10, top + 6, anchor="nw", text="No fight activity", fill=th["dim"], font=(FONT, 10),
                       tags=tags)
        cv.create_text(x + 10, top + 26, anchor="nw", text=f"Fight ends in {_mmss(countdown)}", fill=th["accent"],
                       font=(FONT, 16, "bold"), tags=tags)
        if can_end:
            cv.create_text(x + 10, top + 58, anchor="nw", text="click to end it now", fill=th["dim"],
                           font=(FONT, 9), tags=tags)
    for col, column in enumerate((left[:rows], right)):
        x = 20 if col == 0 else w - 20 - BOX_W
        for i, n in enumerate(column):
            y = top + i * row
            pos[n] = (x + BOX_W if col == 0 else x, y + (row - 6) / 2, col, x, y)

    for (k, s, d), r in rates.items():
        if LEGEND_OF[k] not in off and (item := _arrow(cv, pos, k, s, d, 1 + min(6, math.log10(1 + r)))):
            tips[item] = "{}  {} → {}  {}/s".format(NAMES[k], *_who(ticks, k, s, d), fmt(r))
    for k, s, d in ewar:
        if LEGEND_OF[k] not in off and (item := _arrow(cv, pos, k, s, d, 2, dash=(4, 3))):
            tips[item] = "{}  {} → {}".format(NAMES[k], *_who(ticks, k, s, d))
    for n, (_, _, col, x, y) in pos.items():
        cv.create_rectangle(x, y, x + BOX_W, y + row - 6, fill=th["panel"],
                            outline=th["accent"] if col == 0 else th["dim"])
        tx = x + 8
        if icon := ship_icon(ships.get(n, n)):  # NPCs and bare ship names are their own type
            cv.create_image(x + 3, y + (row - 6) / 2, anchor="w", image=icon)
            tx += 34
        name = cv.create_text(tx, y + 3, anchor="nw", text=n, fill=th["fg"], font=(FONT, 10, "bold"))
        if n in bursts:  # "Armor 6  Info 5": running command bursts and the fleet members each reached
            text = cv.create_text(x + BOX_W - 6, y + 4, anchor="ne", fill=th["accent"], font=(FONT, 8), text="  ".join(
                f"{m.split()[0].replace('Information', 'Info')} {k}" for m, k, *_ in bursts[n]))
            if cv.bbox(text)[0] < cv.bbox(name)[2] + 8:  # a long name: "A6 I5"
                cv.itemconfigure(text, text=" ".join(f"{m[0]}{k}" for m, k, *_ in bursts[n]))
        info = f"{ships.get(n, '')}   out {fmt(out_dmg[n])}  in {fmt(in_dmg[n])}  rep {fmt(in_rep[n])}"
        cv.create_text(tx, y + 19, anchor="nw", text=info, fill=th["dim"], font=(FONT, 9))

    x = 20
    for label, kind in LEGEND:  # tagged "legend:<kind>" for the click toggle; a hidden entry is grey and struck out
        tags = ("legend", f"legend:{kind}")
        hidden = kind in off
        x2 = cv.bbox(cv.create_text(x + 26, h - 14, anchor="w", text=label, fill=th["dim"], tags=tags,
                                    font=(FONT, 9, "overstrike") if hidden else (FONT, 9)))[2]
        cv.tag_lower(cv.create_rectangle(x - 4, h - 24, x2 + 6, h - 4, fill=th["bg"], outline="", tags=tags))  # click area
        cv.create_line(x, h - 14, x + 20, h - 14, fill=th["dim"] if hidden else COLORS[kind], width=3, tags=tags)
        x = x2 + 18

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
        return 0, {label: (0, 0, 0, 0) for label, _, _ in [*GROUPS, JAM_ROW]}
    left_names = set(ticks[-1]["left"])

    def by_side(items):
        out = defaultdict(float)
        for (k, s, d), v in items:
            out[(k, s in left_names, d in left_names)] += v
        return out
    now = by_side(_rates(ticks[-WINDOW:]).items())
    total = by_side(((k, s, d), a) for t in ticks for k, s, d, a in t["flows"])

    def side(values, kinds, outgoing):
        return sum(v for (k, s_left, d_left), v in values.items() if k in kinds and (s_left if outgoing else d_left))
    secs = ticks[-1]["t"] - ticks[-1].get("start", ticks[0]["t"]) + TICK
    groups = {label: (side(now, kinds, True), side(now, kinds, False), side(total, kinds, True),
                      side(total, kinds, False)) for label, _, kinds in GROUPS}
    # jams: active now instead of /s; each jam is logged once, so Σ counts the jams of the fight
    active = by_side(((k, s, d), 1) for k, s, d in _ewar(ticks) if k == "jam")
    groups[JAM_ROW[0]] = (side(active, {"jam"}, True), side(active, {"jam"}, False),
                          side(total, {"jam"}, True), side(total, {"jam"}, False))
    return secs, groups


def draw_cockpit(cv, ticks, th, off=()):
    """The small cockpit window: fight clock, then one row per group with the team's sums (jams: active, Σ count).
    off: legend entries hidden in the main window are left out here too."""
    cv.delete("all")
    w = cv.winfo_width()
    secs, groups = summary(ticks)
    cv.create_text(10, 6, anchor="nw", text=_mmss(secs), fill=th["accent"], font=(FONT, 16, "bold"))
    col = (w - 100) / 4
    xs = [w - 10 - (3 - i) * col for i in range(4)]
    for x, head in zip(xs, ("out/s", "in/s", "Σ out", "Σ in")):
        cv.create_text(x, 30, anchor="se", text=head, fill=th["dim"], font=(FONT, 9))
    rows = [r for r in [*GROUPS, JAM_ROW] if LEGEND_OF[r[1]] not in off]
    for row, (label, color_kind, _) in enumerate(rows):
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
        for k, s, d in _ewar(ticks, i + 1):  # ewar has no amount: count the active effects, like the arrows
            label = next(label for label, _, kinds in EWAR_ROWS if k in kinds)
            rates[(label, True)] += s in left
            rates[(label, False)] += d in left
        out.append(rates)
    return out


def draw_graph(cv, ticks, th, hover=None, off=(), span=None):
    """One small chart per group, out solid and in dashed, over the fight or its last span seconds;
    hover (canvas x) picks the shown tick and lists its log events."""
    cv.delete("all")
    w, h = cv.winfo_width(), cv.winfo_height()
    first = max(0, len(ticks) - span // TICK) if span else 0  # only the display is cut, the fight stays whole
    margin = max(0, first - max(WINDOW, JAM_TICKS))  # earlier ticks the rates of the first shown one need
    data = series(ticks[margin:])[first - margin:]
    if len(data) < 2:
        cv.create_text(w / 2, h / 2, text="Waiting for a fight …", fill=th["dim"], font=(FONT, 11))
        return
    links = any(t.get("bursts") for t in ticks[first:])
    pad_l, pad_r, top, bottom = 50, 12, 30 if links else 20, 18  # links: room for their bars
    rows = [r for r in [*GROUPS, *EWAR_ROWS] if LEGEND_OF[r[1]] not in off]  # as hidden in the main window
    if not rows:
        cv.create_text(w / 2, h / 2, text="All hidden in the main window", fill=th["dim"], font=(FONT, 11))
        return
    pw, ph, n = w - pad_l - pad_r, (h - top - bottom) / len(rows), len(data)
    i = n - 1 if hover is None else max(0, min(n - 1, round((hover - pad_l) / pw * (n - 1))))
    # legend: the line style tells out from in, not colour alone
    cv.create_line(pad_l, 10, pad_l + 22, 10, fill=th["fg"], width=2)
    cv.create_text(pad_l + 28, 10, anchor="w", text="out", fill=th["dim"], font=(FONT, 8))
    cv.create_line(pad_l + 60, 10, pad_l + 82, 10, fill=th["fg"], width=2, dash=(4, 3))
    legend = cv.create_text(pad_l + 88, 10, anchor="w", text="in   (per second, last 10 s)", fill=th["dim"],
                            font=(FONT, 8))
    if links:
        _links_info(cv, ticks[first + (n - 1 if hover is None else i)], th, w - 30, legend)  # left of the ⟲ button
    for g, (label, color_kind, _) in enumerate(rows):
        y0 = top + g * ph
        base, height = y0 + ph - 4, ph - 20
        vmax = max([d[(label, o)] for d in data for o in (True, False)] + [1])
        cv.create_line(pad_l, base, w - pad_r, base, fill=th["panel"])
        cv.create_line(pad_l, base - height, w - pad_r, base - height, fill=th["panel"], dash=(1, 3))
        cv.create_text(pad_l - 6, base, anchor="e", text="0", fill=th["dim"], font=(FONT, 8))
        cv.create_text(pad_l - 6, base - height, anchor="e", text=fmt(vmax), fill=th["dim"], font=(FONT, 8))
        cv.create_rectangle(pad_l, y0 + 3, pad_l + 8, y0 + 11, fill=COLORS[color_kind], outline="")
        cv.create_text(pad_l + 13, y0 + 7, anchor="w", text=label + (" (active)" if color_kind in ("scram", "jam") else ""),
                       fill=th["fg"], font=(FONT, 9, "bold"))
        cv.create_text(w - pad_r, y0 + 7, anchor="e", fill=th["fg"], font=(FONT, 9),
                       text=f"out {fmt(data[i][(label, True)])}   in {fmt(data[i][(label, False)])}")
        for outgoing, dash in ((True, None), (False, (4, 3))):
            pts = [v for j, d in enumerate(data)
                   for v in (pad_l + pw * j / (n - 1), base - height * d[(label, outgoing)] / vmax)]
            cv.create_line(*pts, fill=COLORS[color_kind], width=2, dash=dash)
    t0 = ticks[0]["t"]
    cv.create_text(pad_l, h - 4, anchor="sw", text=_mmss(ticks[first]["t"] - t0), fill=th["dim"], font=(FONT, 8))
    cv.create_text(w - pad_r, h - 4, anchor="se", text=_mmss(ticks[-1]["t"] - t0 + TICK), fill=th["dim"],
                   font=(FONT, 8))
    if hover is not None:
        x = pad_l + pw * i / (n - 1)
        cv.create_line(x, top, x, h - bottom, fill=th["dim"])
        tick = ticks[first + i]
        cv.create_text(x, h - 4, anchor="s", text=_mmss(tick["t"] - t0 + TICK), fill=th["fg"],
                       font=(FONT, 8, "bold"))
        _events_box(cv, tick, th, x, top, h - bottom, w, off, tick["t"] - t0)


LINKS = (("Information", "Info"), ("Armor", "Armor"), ("Shield", "Shield"), ("Skirmish", "Skirmish"))


def _links_info(cv, tick, th, right, legend):
    """"Links  Info 6  Armor 5  Shield –  Skirmish 6": fleet members each link type reaches in this tick
    (the most of all boosters), under each a bar of the bonus time left (the freshest burst of that type);
    when it does not fit, the legend loses its note, then the links shorten ("In6 Ar5 Sh– Sk6")."""
    reached, left = {}, defaultdict(float)
    for mods in tick.get("bursts", {}).values():
        for m, k, *age in mods:  # ticks of older test builds hold no age: no bar
            kind = m.split()[0]
            reached[kind] = max(reached.get(kind, 0), k)
            if age:
                left[kind] = max(left[kind], 1 - age[0] / BURST_SECS)
    for step in range(3):  # full; full with the legend shortened; short
        if step == 1:
            cv.itemconfigure(legend, text="in")
        cv.delete("links")
        x = right
        for kind, short in reversed(LINKS):
            on = kind in reached
            item = cv.create_text(x, 10, anchor="e", fill=th["accent"] if on else th["dim"], font=(FONT, 8),
                                  tags="links", text=f"{short[:2]}{reached[kind] if on else '–'}" if step == 2
                                  else f"{short} {reached[kind] if on else '–'}")
            x1, _, x2, _ = cv.bbox(item)
            if on:
                cv.create_rectangle(x1, 18, x2, 21, fill=th["panel"], outline="", tags="links")
                cv.create_rectangle(x1, 18, x1 + (x2 - x1) * left[kind], 21, fill=th["accent"], outline="",
                                    tags="links")
            x = x1 - (5 if step == 2 else 10)
        if step < 2:
            x = cv.bbox(cv.create_text(x, 10, anchor="e", text="Links", fill=th["dim"], font=(FONT, 8),
                                       tags="links"))[0]
        if x >= cv.bbox(legend)[2] + 10:
            break


def _event_lines(tick, off):
    """One tick's log events, by kind as in the legend, biggest first: each hit with amount and hit quality,
    equal ones counted ("2× Scram …"). Ticks from before v0.6.8 hold only the sum per pair."""
    order = [k for _, entry in LEGEND for k in NAMES if LEGEND_OF[k] == entry]
    single = tick.get("events") or [[*f, None, None] for f in tick["flows"]]
    counts = Counter(tuple(e) for e in single if LEGEND_OF[e[0]] not in off)
    lines = []
    for (k, s, d, a, weapon, quality), n in sorted(counts.items(), key=lambda c: (order.index(c[0][0]), -c[0][3])):
        what = " ".join(filter(None, (NAMES[k], None if k in EWAR else fmt(a), quality)))
        lines.append(f"{f'{n}× ' if n > 1 else ''}{what}  {s} → {d}" + (f"  · {weapon}" if weapon else ""))
    return lines or ["no events"]


def _events_box(cv, tick, th, x, top, bottom, w, off, secs):
    """The log events of one tick beside the hover line; long lines wrap, what does not fit is counted."""
    lines, head = _event_lines(tick, off), f"Log events {_mmss(secs)} – {_mmss(secs + TICK)}"
    shown = len(lines)
    while True:
        rest = [f"+{len(lines) - shown} more"] if shown < len(lines) else []
        text = cv.create_text(x + 10, top + 6, anchor="nw", fill=th["fg"], font=(FONT, 8), width=w - 30,
                              text="\n".join([head, *lines[:shown], *rest]))
        x1, y1, x2, y2 = cv.bbox(text)
        if y2 <= bottom or shown == 0:
            break
        cv.delete(text)
        shown -= 1
    if x2 > w - 6:  # no room right of the line: put the box on its left, but never past the left edge
        cv.move(text, max(6 - x1, x - 10 - x2), 0)
        x1, y1, x2, y2 = cv.bbox(text)
    cv.tag_lower(cv.create_rectangle(x1 - 6, y1 - 4, x2 + 6, y2 + 4, fill=th["panel"], outline=th["accent"]), text)


MAIN_SIZE = "1150x720"
ICONS = {"cockpit": "⏱", "graph": "∿"}  # on the Cockpit/Graph buttons (Segoe UI Symbol; Tk falls back to it)
PANELS = {  # small extra windows: title, default size, min (width, height, height per shown row), painter
    "cockpit": ("Cockpit", "340x144", (280, 40, 20), draw_cockpit),
    "graph": ("Graph", "460x460", (320, 40, 45), draw_graph),
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
    """'20261013_191334.jsonl.gz' (UTC) -> '2026-10-13  21:13:34' (local time); a fight without server gets
    'solo <character>'."""
    start = datetime.strptime(name[:15], "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
    solo = re.search(r"\.solo-(.+?)\.jsonl", name)
    return start.astimezone().strftime("%Y-%m-%d  %H:%M:%S") + (f"   solo {solo_char(solo[1])}" if solo else "")


SERVER = ":server"  # the server tab in [windows] tabs; a colon is never part of a character name


def _saved_windows(cfg_path):
    saved = configparser.ConfigParser(interpolation=None)
    saved.read(cfg_path, encoding="utf-8-sig")  # fresh: other instances write the file too
    return saved["windows"] if saved.has_section("windows") else {}


def start_tabs(cfg, cfg_path, char=None, server=False):
    """[(mode, character)] to open: --char alone, else the tabs open at the last close; never one another
    running instance shows. --server adds the server tab."""
    taken = snap.open_tabs()
    names = [char] if char else [n for n in _saved_windows(cfg_path).get("tabs", "").split("|") if n]
    tabs = []
    for n in names:
        tab = ("server", None) if n == SERVER else ("client", n)
        if tab not in tabs and (n != SERVER or "Server" not in taken) and n not in taken:
            tabs.append(tab)
    if server and ("server", None) not in tabs:
        tabs.insert(0, ("server", None))
    if not tabs:
        chars = logparse.characters(cfg["client"]["log_dir"])
        tabs.append(("client", next(iter([c for c in chars if c not in taken] + chars), None)))
    return tabs


def _button(parent, text, cmd, th):
    return tk.Button(parent, text=text, command=cmd, bg=th["bg"], fg=th["fg"], relief="flat",
                     activebackground=th["accent"], activeforeground=th["bg"], padx=8)


async def _run(backend, out):
    try:
        await backend.run()
    except asyncio.CancelledError:
        raise
    except Exception as e:  # e.g. port already in use: show it instead of dying silently
        out({"type": "status", "text": f"error: {e}"})


class Tab:
    """One character's client or the server: its own bar, fight view, replays, cockpit and graph windows."""

    def __init__(self, app, tid, mode, char=None):
        self.app, self.tid, self.mode = app, tid, mode
        self.th = th = THEMES[mode]
        cfg = app.cfg
        self.live = []  # ticks of the running fight
        self.bursts = {}  # links running while no fight is
        self.replay, self.pos, self.playing, self._timer = None, 0, False, None
        self.panels, self.panel_canvas, self._panel_geo, self._hover = {}, {}, {}, None
        self._main_hover, self._replays_top = None, None
        self._off = set()  # legend entries whose arrows are hidden
        out = self.out = lambda msg: app.q.put((tid, msg))
        self.backend = app.make(mode, char, out)
        self.future = asyncio.run_coroutine_threadsafe(_run(self.backend, out), app.loop)

        self.frame = tk.Frame(app.root, bg=th["bg"])
        self.bar = tk.Frame(self.frame, bg=th["panel"])
        self.bar.pack(fill="x")
        if mode == "client":
            self.char = tk.StringVar(value=char or "")
            box = ttk.Combobox(self.bar, textvariable=self.char, state="readonly", width=24,
                               postcommand=lambda: box.configure(values=logparse.characters(cfg["client"]["log_dir"])))
            box.bind("<<ComboboxSelected>>", lambda e: self._set_char())
            box.pack(side="left", padx=(10, 4), pady=4)
            _button(self.bar, "⤓ Paste code", app._paste_code, th).pack(side="left", padx=4)
        else:
            tk.Label(self.bar, text="Connection code:", bg=th["panel"], fg=th["dim"]).pack(side="left", padx=(10, 4))
            self.code = tk.Entry(self.bar, width=46, bg=th["bg"], fg=th["fg"], relief="flat", readonlybackground=th["bg"])
            self._set_code("…")
            self.code.pack(side="left", pady=4)
            _button(self.bar, "⧉ Copy", self._copy, th).pack(side="left", padx=4)
            # the public address may take a few seconds to look up
            threading.Thread(target=lambda: out({"type": "code", "text": f"{net.public_address(cfg)}:"
                             f"{cfg['general']['port']}/{cfg['general']['token']}"}), daemon=True).start()
        foot = tk.Frame(self.frame, bg=th["panel"])  # connection messages, below everything else
        foot.pack(side="bottom", fill="x")
        line = tk.Frame(foot, bg=th["panel"])
        line.pack(fill="x")
        self.status = tk.StringVar()
        tk.Label(line, textvariable=self.status, bg=th["panel"], fg=th["fg"], font=(FONT, 10)).pack(
            side="left", padx=10, pady=2)
        self.warning = tk.StringVar()
        tk.Label(line, textvariable=self.warning, bg=th["panel"], fg=COLORS["dmg"],
                 font=(FONT, 10, "bold")).pack(side="left", padx=10)
        self.panel_btn = {name: _button(self.bar, f"{ICONS[name]} {PANELS[name][0]}",
                                        lambda n=name: self._toggle_panel(n), th) for name in ("graph", "cockpit")}
        for btn in self.panel_btn.values():
            btn.pack(side="right", padx=4)
        _button(self.bar, "⏪ Replays", lambda: self.call(self.backend.history), th).pack(side="right", padx=4)
        if mode == "server":  # only the server may end a fight early
            _button(self.bar, "⏹ Reset", lambda: self.call(self.backend.reset), th).pack(side="right", padx=4)
            self.clients = tk.StringVar(value="no client connected")  # with the character each client picked
            info = tk.Label(foot, textvariable=self.clients, bg=th["panel"], fg=th["dim"], font=(FONT, 9),
                            anchor="w", justify="left")
            info.pack(fill="x", padx=10, pady=(0, 2))
            info.bind("<Configure>", lambda e: info.configure(wraplength=e.width - 10))
        else:
            self.enabled = cfg.getboolean("client", "auto_connect")
            self.conn = _button(self.bar, "", self._toggle, th)
            self.conn.pack(side="right", padx=4)
            self._conn_text()

        self.replay_bar = tk.Frame(self.frame, bg=th["panel"])
        self.play_btn = _button(self.replay_bar, "⏸ Stop", self._play_pause, th)
        self.play_btn.pack(side="left", padx=4, pady=4)
        self.scale = tk.Scale(self.replay_bar, orient="horizontal", showvalue=False, command=self._seek,
                              bg=th["panel"], fg=th["fg"], troughcolor=th["bg"], highlightthickness=0)
        self.scale.pack(side="left", fill="x", expand=True, padx=4)
        self.replay_label = tk.Label(self.replay_bar, bg=th["panel"], fg=th["fg"])
        self.replay_label.pack(side="left", padx=4)
        _button(self.replay_bar, "● Back to live", self._stop_replay, th).pack(side="left", padx=4)

        self.canvas = tk.Canvas(self.frame, bg=th["bg"], highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.redraw())
        self.canvas.bind("<Motion>", lambda e: self._arrow_hover((e.x, e.y)))
        self.canvas.bind("<Leave>", lambda e: self._arrow_hover(None))
        self.canvas.bind("<Button-1>", lambda e: self._click(e.x, e.y))
        self._restore_layout(first=True)

    def name(self):
        """Shown on the tab and in the main window title (snap.open_tabs reads it there)."""
        return "Server" if self.mode == "server" else self.char.get() or "no character"

    def _char(self):
        return self.char.get() if self.mode == "client" else None

    def _window_key(self):
        return "server" if self.mode == "server" else self._char() or "client"

    def title(self):
        for name, top in self.panels.items():
            top.title(f"{PANELS[name][0]} – {self.name()}")

    def call(self, fn, *args):
        asyncio.run_coroutine_threadsafe(fn(*args), self.app.loop)

    def close(self):
        """Store the window places, close the small windows and stop the backend (a server stores its fight)."""
        if self._timer:
            self.app.root.after_cancel(self._timer)
        for top in self.panels.values():
            top.destroy()
        for top in (self._replays_top,):
            if top and top.winfo_exists():
                top.destroy()
        self.frame.destroy()
        stop = asyncio.run_coroutine_threadsafe(self.backend.stop(), self.app.loop)
        stop.add_done_callback(lambda _: self.future.cancel())

    def _set_code(self, text):
        self.code.configure(state="normal")
        self.code.delete(0, "end")
        self.code.insert(0, text)
        self.code.configure(state="readonly")

    def _copy(self):
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append(self.code.get())
        self.status.set("connection code copied")

    # --- cockpit and graph windows ---

    def _restore_layout(self, first=False):
        """Put this tab's small windows where they were last time (also after picking another character).
        A closed cockpit or graph is stored as "off WxH+X+Y" and reopens at that place."""
        windows = _saved_windows(self.app.cfg_path)
        key = self._layout_key = self._window_key()
        # legend entries this character had hidden: before the windows open, they set the graph's min size
        self._off = set(windows.get(f"{key}.hidden", "").split(",")) & {kind for _, kind in LEGEND}
        for name in self.panels:
            self._minsize(name)
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
                    self.app.root.after(300, lambda top=top, geo=geo: top.winfo_exists() and top.geometry(geo))
            else:
                self._open_panel(name)
        self._mark_panels()

    def windows(self):
        """config [windows] entries of the small windows, under the character they belong to."""
        key = self._layout_key  # also right after picking another character
        return {f"{key}.hidden": ",".join(sorted(self._off)), **{
            f"{key}.{name}": self.panels[name].geometry() if name in self.panels
            else f"off {self._panel_geo.get(name, '')}".strip() for name in PANELS}}

    def _mark_panels(self):
        """Cockpit/Graph button filled with the accent colour while its window is open."""
        th = self.th
        for name, btn in self.panel_btn.items():
            on = name in self.panels
            btn.configure(bg=th["accent"] if on else th["bg"], fg=th["bg"] if on else th["fg"])

    def _open_panel(self, name):
        size, th = PANELS[name][1], self.th
        top = self.panels[name] = tk.Toplevel(self.app.root, bg=th["bg"])  # not transient: stays when the main one is minimized
        self._minsize(name)
        top.geometry(size)
        if _valid_place(geometry := self._panel_geo.get(name, "")):
            top.geometry(geometry)
        if sys.platform == "win32":
            top.attributes("-toolwindow", True)  # thin title bar
        top.protocol("WM_DELETE_WINDOW", lambda: self._toggle_panel(name))
        top.bind("<Configure>", self.app._on_move)
        cv = self.panel_canvas[name] = tk.Canvas(top, bg=th["bg"], highlightthickness=0)
        cv.pack(fill="both", expand=True)
        cv.bind("<Configure>", lambda e: self.redraw())
        tk.Button(top, text="⟲", command=lambda: top.geometry(PANELS[name][1]), bg=th["bg"], fg=th["dim"],
                  relief="flat", bd=0, padx=3, pady=0, font=(FONT, 8), activebackground=th["accent"],
                  cursor="hand2").place(relx=1, x=-2, y=1, anchor="ne")
        if name == "graph":
            cv.bind("<Motion>", lambda e: self._hover_at(e.x))
            cv.bind("<Leave>", lambda e: self._hover_at(None))
        self.title()
        self.apply_topmost()

    def _minsize(self, name):
        """The small windows may shrink to the rows the legend still shows (e.g. the graph with only Jam)."""
        width, height, per_row = PANELS[name][2]
        rows = [*GROUPS, *EWAR_ROWS] if name == "graph" else [*GROUPS, JAM_ROW]
        self.panels[name].minsize(width, height + per_row * max(1, sum(LEGEND_OF[r[1]] not in self._off for r in rows)))

    def _toggle_panel(self, name):
        if top := self.panels.pop(name, None):
            self._panel_geo[name] = top.geometry()
            del self.panel_canvas[name]
            top.destroy()
        else:
            self._open_panel(name)
        self._mark_panels()

    def apply_topmost(self):
        """Keep cockpit and graph above the game (works with EVE in window or fixed window mode, not in fullscreen)."""
        for name, key in (("cockpit", "always_on_top"), ("graph", "graph_on_top")):
            if top := self.panels.get(name):
                top.attributes("-topmost", self.app.cfg.getboolean("general", key))

    # --- drawing ---

    def _arrow_hover(self, xy):
        self._main_hover = xy
        draw(self.canvas, self._main_ticks(), self.th, xy, self._off, self._countdown(), self._can_end())
        self.canvas.configure(cursor="hand2" if xy and (self._legend_at(*xy) or self._end_at(*xy)) else "")

    def _legend_at(self, x, y):
        """Legend entry under (x, y) or None. By position, not "current": every hover redraw replaces the items."""
        for item in self.canvas.find_overlapping(x, y, x, y):
            for tag in self.canvas.gettags(item):
                if tag.startswith("legend:"):
                    return tag[7:]

    def _end_at(self, x, y):
        return any("end" in self.canvas.gettags(i) for i in self.canvas.find_overlapping(x, y, x, y))

    def _can_end(self):
        """Only the server, or a client without server, decides when a fight ends."""
        return self.mode == "server" or self.backend.writer is None

    def _click(self, x, y):
        if self._end_at(x, y) and self._can_end():
            self.call(self.backend.reset)  # the server stores the fight, as with its Reset button
        else:
            self._toggle_legend(x, y)

    def _toggle_legend(self, x, y):
        """Show or hide the arrows of the clicked legend entry (this tab only, stored per character)."""
        if kind := self._legend_at(x, y):
            self._off ^= {kind}
            for name in self.panels:
                self._minsize(name)
            self.redraw()  # cockpit and graph hide it too
            self._arrow_hover(self._main_hover)

    def _hover_at(self, x):
        self._hover = x
        if "graph" in self.panels:
            draw_graph(self.panel_canvas["graph"], self._ticks(), self.th, x, self._off, self._span())

    def _span(self):
        """Seconds the graph shows: the last few minutes, longer for replays; the fight itself is stored whole."""
        live = self.replay is None
        try:
            minutes = self.app.cfg.getint("general", "graph_live_minutes" if live else "graph_replay_minutes")
        except ValueError:  # hand-edited garbage in config.ini
            minutes = 5 if live else 10
        return max(1, minutes) * 60

    def _countdown(self):
        """Seconds until the running fight ends for lack of events (the server's idle_end when connected); None in replays."""
        if self.replay is not None or not self.live:
            return None
        last = next((t["t"] for t in reversed(self.live) if t["flows"]), self.live[0]["t"])
        try:
            idle = int(self.live[-1].get("idle_end") or self.app.cfg.getint("general", "idle_end"))
        except ValueError:
            idle = IDLE_END
        return max(0, idle - (self.live[-1]["t"] - last))

    def _ticks(self):
        return self.replay[:self.pos + 1] if self.replay is not None else self.live

    def _main_ticks(self):
        """The main window outside a fight still shows the pilots whose links run."""
        if self._ticks() or not self.bursts or self.replay is not None:
            return self._ticks()
        return [{"t": 0, "flows": [], "ships": {}, "left": sorted(self.bursts), "bursts": self.bursts}]

    def redraw(self):
        ticks = self._ticks()
        if self.app.active is self:  # hidden tabs keep only their small windows up to date
            draw(self.canvas, self._main_ticks(), self.th, self._main_hover, self._off, self._countdown(),
                 self._can_end())
        for name, cv in self.panel_canvas.items():
            if name == "graph":
                draw_graph(cv, ticks, self.th, self._hover, self._off, self._span())
            else:
                PANELS[name][3](cv, ticks, self.th, self._off)

    def handle(self, msg):
        """A message of this tab's backend."""
        kind = msg.get("type")
        if kind == "tick":
            self.live.append(msg)
        elif kind == "reset":
            self.live = []
        elif kind == "bursts":
            if msg["bursts"] == self.bursts:
                return  # nothing changed: no redraw every 2 s
            self.bursts = msg["bursts"]
        elif kind == "status":
            self.status.set(msg["text"])
        elif kind == "warning":
            self.warning.set(msg["text"])
        elif kind == "code":
            self._set_code(msg["text"])
        elif kind == "history":
            self._history(msg["sessions"], msg.get("secs", {}))
        elif kind == "session":
            self._start_replay(msg["ticks"])
        elif kind == "clients":
            names = [f"{', '.join(chars) or 'no character yet'} ({', '.join(filter(None, (addr, ver)))})"
                     for addr, chars, ver in msg["list"]]
            self.clients.set(f"{len(names)} connected:   " + "   ·   ".join(names) if names
                             else "no client connected")
        if kind in ("tick", "reset", "bursts") and self.replay is None:
            self.redraw()

    def _set_char(self):
        app, char = self.app, self.char.get()
        if char in {t.name() for t in app.tabs.values() if t is not self} | app.taken():
            # one tab per character: a second one would sit on the first one's places and overwrite them
            self.char.set(self.backend.char or "")
            self.status.set(f"{char} is already open in another tab or window")
            return
        app._save_window()  # keep the places of the character we leave
        self.call(self.backend.set_char, char)
        self.title()
        app._title()
        self._restore_layout()
        self.redraw()  # with the legend entries the new character had hidden

    def _toggle(self):
        self.enabled = not self.enabled
        self.call(self.backend.set_enabled, self.enabled)
        self._conn_text()

    def _conn_text(self):
        self.conn.configure(text=f"⇄ Connection: {'on' if self.enabled else 'off'}")

    # --- replays ---

    def _history(self, sessions, secs):
        th = self.th
        if (top := self._replays_top) and top.winfo_exists():  # one replay list per tab
            for w in top.winfo_children():  # fill it again with the fresh list
                w.destroy()
            self.app._place_dialog(top)  # the main window may have moved since
            top.deiconify()
            top.lift()
            top.focus_force()
        else:
            top = self._replays_top = self.app._dialog(f"Replays – {self.name()}")
        if not sessions:
            tk.Label(top, text="No fights stored yet.", bg=th["bg"], fg=th["fg"]).pack(padx=20, pady=20)
            return
        lb = tk.Listbox(top, width=56, height=15, bg=th["panel"], fg=th["fg"], relief="flat", font=(FONT, 10))
        lb.insert("end", *(f"{fight_label(n)}   {_mmss(secs[n]) if n in secs else ''}" for n in sessions))
        lb.pack(padx=10, pady=10)

        def play(_=None):
            if sel := lb.curselection():
                self.call(self.backend.load, sessions[sel[0]])
                top.destroy()
        lb.bind("<Double-1>", play)
        _button(top, "▶ Play", play, th).pack(pady=(0, 10))

    def _start_replay(self, ticks):
        if not ticks:
            return
        self.replay, self.pos, self.playing = ticks, 0, True
        self.scale.configure(to=len(ticks) - 1)
        self.scale.set(0)
        self.play_btn.configure(text="⏸ Stop")
        self.replay_bar.pack(fill="x", after=self.bar)
        self.app.select(self.tid)  # the replay plays in this tab
        self._schedule()
        self._seek(0)

    def _schedule(self):
        if self._timer:
            self.app.root.after_cancel(self._timer)
        self._timer = self.app.root.after(TICK * 1000, self._step)

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
        self.play_btn.configure(text="⏸ Stop" if self.playing else "▶ Start")

    def _stop_replay(self):
        if self._timer:
            self.app.root.after_cancel(self._timer)
            self._timer = None
        self.replay = None
        self.replay_bar.pack_forget()
        self.redraw()


class App:
    """The main window: one tab per character's client, plus the server tab if this instance runs it."""

    def __init__(self, tabs, make, loop, q, cfg, cfg_path, restart=None, geometry=None):
        self.make, self.loop, self.q = make, loop, q  # make(mode, char, out) builds a tab's backend
        self._restart = restart
        self.cfg, self.cfg_path = cfg, cfg_path
        self.th = th = THEMES["client"]
        self.tabs, self.active, self._next = {}, None, 0

        root = self.root = tk.Tk()
        root.minsize(900, 560)
        root.geometry(MAIN_SIZE)
        root.iconphoto(True, tk.PhotoImage(data=APP_ICON))  # True: cockpit, graph and dialogs get it too
        self._normal_geo = None  # last place while neither maximized nor minimized
        windows = _saved_windows(cfg_path)
        if place := geometry or windows.get("main") or windows.get("server" if tabs[0][0] == "server" else
                                                                    tabs[0][1] or "client"):
            self._place(place)  # a restart passes the place it had; before tabs it was stored per character
        root.bind("<Configure>", self._track_place, add="+")
        self._sizes, self._snap_jobs = {}, {}
        root.bind("<Configure>", self._on_move, add="+")
        root.protocol("WM_DELETE_WINDOW", self._close)
        # any widget getting focus (a click often focuses a child, not the window) raises the whole group
        root.bind_all("<FocusIn>", self._on_focus, add="+")
        root.configure(bg=th["bg"])
        self.tabbar = tk.Frame(root, bg=th["panel"])
        self.tabbar.pack(fill="x")
        for mode, char in tabs:
            self.add_tab(mode, char)
        try:
            self.select(list(self.tabs)[int(windows.get("tab", 0))])
        except (ValueError, IndexError):
            pass
        root.after(100, self._drain)
        if cfg.getboolean("update", "check"):
            root.after(5000, self._check_online)  # after the first connection messages

    # --- tabs ---

    def add_tab(self, mode, char=None):
        tid, self._next = self._next, self._next + 1
        self.tabs[tid] = Tab(self, tid, mode, char)
        self.select(tid)
        self._title()

    def select(self, tid):
        tab = self.tabs[tid]
        if self.active and self.active is not tab:
            self.active.frame.pack_forget()
        self.active = tab
        tab.frame.pack(fill="both", expand=True)
        self._tabbar()
        tab.redraw()

    def close_tab(self, tid):
        if len(self.tabs) < 2:  # the window always keeps one tab
            return
        tab = self.tabs.pop(tid)
        self._store(tab.windows())
        tab.close()
        if self.active is tab:
            self.active = None
            self.select(next(iter(self.tabs)))
        self._title()
        self._tabbar()

    def taken(self):
        """Tab names other running instances show."""
        return snap.open_tabs(int(self.root.wm_frame(), 16))

    def _new_client(self):
        """A tab for the first character from the logs that no tab and no other window shows yet."""
        taken = {t.name() for t in self.tabs.values()} | self.taken()
        chars = logparse.characters(self.cfg["client"]["log_dir"])
        self.add_tab("client", next((c for c in chars if c not in taken), None))

    def _new_server(self):
        if server := next((tid for tid, t in self.tabs.items() if t.mode == "server"), None):
            self.select(server)
        elif "Server" in self.taken():
            messagebox.showinfo("Server", "Another eos-fight-mon window already runs the server.", parent=self.root)
        else:
            self.add_tab("server")

    def _tabbar(self):
        """One button per tab (the shown one filled), × closes it; adding tabs and the window-wide buttons right."""
        for w in self.tabbar.winfo_children():
            w.destroy()
        th = self.th
        for tid, tab in self.tabs.items():
            on, tth = tab is self.active, tab.th
            b = tk.Button(self.tabbar, text=tab.name(), command=lambda tid=tid: self.select(tid), relief="flat",
                          bg=tth["accent"] if on else th["bg"], fg=th["bg"] if on else tth["accent"],
                          activebackground=tth["accent"], activeforeground=th["bg"], padx=10,
                          font=(FONT, 9, "bold"))
            b.pack(side="left", padx=(6, 0), pady=4)
            b.bind("<Button-2>", lambda e, tid=tid: self.close_tab(tid))  # middle click closes, as in browsers
            if len(self.tabs) > 1:
                tk.Button(self.tabbar, text="×", command=lambda tid=tid: self.close_tab(tid), relief="flat",
                          bg=th["bg"], fg=th["dim"], activebackground=COLORS["dmg"], activeforeground=th["fg"],
                          padx=4).pack(side="left", pady=4)
        _button(self.tabbar, "+ Client", self._new_client, th).pack(side="left", padx=(12, 4))
        if not any(t.mode == "server" for t in self.tabs.values()):
            _button(self.tabbar, "+ Server", self._new_server, THEMES["server"]).pack(side="left", padx=4)
        _button(self.tabbar, "⚙ Settings", self._settings, th).pack(side="right", padx=(4, 10), pady=4)
        _button(self.tabbar, "⟲ Reset size", self._reset_size, th).pack(side="right", padx=4)

    def _title(self):
        self.root.title("eos-fight-mon – " + " · ".join(t.name() for t in self.tabs.values()))
        if self.tabs:
            self._tabbar()

    def _panels(self):
        return [top for tab in self.tabs.values() for top in tab.panels.values()]

    # --- window places ---

    def _place(self, geometry):
        # "zoomed WxH+X+Y": the normal place picks the monitor the window maximizes on
        if _valid_place(normal := geometry.removeprefix("zoomed").strip()):
            self._normal_geo = normal
            if self.root.state() == "zoomed":
                self.root.state("normal")
            self.root.geometry(normal)
        if geometry.startswith("zoomed"):
            self.root.state("zoomed")

    def _reset_size(self):
        """Back to the size the window had at the very first start; the place stays."""
        self.root.state("normal")
        self.root.geometry(MAIN_SIZE)

    def _on_focus(self, e):
        try:
            top = e.widget.winfo_toplevel()
        except (AttributeError, tk.TclError):  # e.g. a combobox popdown tkinter does not know
            return
        if top is self.root or top in self._panels():
            self._raise_group(top)

    def _raise_group(self, clicked):
        """Clicking one window brings the main window and all cockpit and graph windows of this instance up."""
        for w in [self.root, *self._panels(), clicked]:  # the clicked one last, so it stays in front
            if w.winfo_exists() and w.state() != "iconic":
                w.lift()

    def _on_move(self, e):
        """A window let go near another one docks to it (moves only, resizing never snaps)."""
        top = e.widget
        if top is not self.root and top not in self._panels():
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

    def _store(self, windows):
        try:
            update_config(self.cfg_path, {"windows": windows})
        except OSError:
            pass  # a read-only folder must not keep the window from closing

    def _save_window(self):
        """Main window place, the small windows of every tab, and which tabs are open (reopened at the next start)."""
        state = self.root.state()
        normal = self.root.geometry() if state == "normal" else self._normal_geo or ""
        geometry = f"zoomed {normal}".strip() if state == "zoomed" else normal
        tabs = list(self.tabs.values())
        names = [SERVER if t.mode == "server" else t._char() for t in tabs]
        windows = {"main": geometry, "tabs": "|".join(filter(None, names)),
                   "tab": str(tabs.index(self.active) if self.active in tabs else 0)}
        for tab in tabs:
            windows.update(tab.windows())
        self._store(windows)
        return geometry

    def restart(self):
        """Reopen the window as a fresh program with the same tabs, e.g. after changing the port."""
        geometry = self._save_window()  # same size and place
        self._stop_all()  # frees the server port before the new copy wants it
        self._restart(geometry)
        self.root.destroy()

    def _close(self):
        self._save_window()
        self._stop_all()
        self.root.destroy()

    def _stop_all(self):
        """Store the running fights (the server's, and the own fight of a client without server) before leaving."""
        for tab in self.tabs.values():
            try:
                asyncio.run_coroutine_threadsafe(tab.backend.stop(), self.loop).result(3)
            except Exception:  # a stuck backend must not keep the window open
                pass
            tab.future.cancel()

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
        self.restart()

    def _status(self, text):
        for tab in self.tabs.values():
            tab.status.set(text)

    def _drain(self):
        """Handle what the network thread queued: (tab id, message), tab id None for the whole window."""
        try:
            while True:
                tid, msg = self.q.get_nowait()
                if tid is not None:
                    if tab := self.tabs.get(tid):  # a closed tab's last messages are dropped
                        tab.handle(msg)
                    continue
                kind = msg.get("type")
                if kind == "status":
                    self._status(msg["text"])
                elif kind == "update":
                    self._offer_update(msg)
                elif kind == "updated":
                    update_config(self.cfg_path, {"update": {"installed": msg["tag"]}})  # tells the other windows
                    self.restart()
                    return
        except queue.Empty:
            pass
        self.root.after(100, self._drain)

    def _put(self, msg):
        self.q.put((None, msg))

    # --- update ---

    def _check_online(self):
        """Once after start: newest release (offered for install) and SDE, as one line in the status bar."""
        def run():
            parts = []
            try:
                found = update.latest()
                parts.append(f"{found[0]} available" if found else f"v{update.VERSION} is the newest")
                if found and update.can_install():
                    self._put({"type": "update", "tag": found[0], "assets": found[1], "manual": False})
            except (OSError, ValueError, KeyError):
                pass  # GitHub or CCP unreachable: leave that part out
            try:
                parts.append(update.sde_status())
            except (OSError, ValueError, KeyError):
                pass
            if parts:
                self._put({"type": "status", "text": "  ·  ".join(parts)})
        threading.Thread(target=run, daemon=True).start()

    def _check_update(self, manual):
        """Ask GitHub in the background; the answer comes back through the queue."""
        if not update.can_install():
            self._status("running from source: no self-update")
            return

        def run():
            try:
                found = update.latest()
            except (OSError, ValueError, KeyError) as e:
                if manual:
                    self._put({"type": "status", "text": f"update check failed: {e}"})
                return
            if found:
                self._put({"type": "update", "tag": found[0], "assets": found[1], "manual": manual})
            elif manual:
                self._put({"type": "status", "text": f"v{update.VERSION} is the newest version"})
        threading.Thread(target=run, daemon=True).start()

    def _offer_update(self, msg):
        tag = msg["tag"]
        state = configparser.ConfigParser(interpolation=None)
        state.read(self.cfg_path, encoding="utf-8-sig")  # fresh: another window may have installed it already
        state = state["update"] if state.has_section("update") else {}
        if state.get("installed") == tag:
            if messagebox.askyesno("Update", f"{tag} was installed by another eos-fight-mon window.\n\n"
                                   "Restart this window with it now?", parent=self.root):
                self.restart()
            return
        if not msg["manual"] and state.get("skip") == tag:
            return
        if not messagebox.askyesno("Update", f"eos-fight-mon {tag} is available (this is v{update.VERSION}).\n\n"
                                   "Download and install it now? The window restarts afterwards.\n\n"
                                   "No: not asked again for this version (Settings › Check for updates still does).",
                                   parent=self.root):
            update_config(self.cfg_path, {"update": {"skip": tag}})
            return
        self._status(f"downloading {tag} …")

        def run():
            try:
                update.install(msg["assets"])
                self._put({"type": "updated", "tag": tag})
            except (OSError, ValueError, KeyError) as e:
                self._put({"type": "status", "text": f"update failed: {e}"})
        threading.Thread(target=run, daemon=True).start()

    # --- settings ---

    def _dialog(self, title):
        top = tk.Toplevel(self.root, bg=self.th["bg"])
        top.title(title)
        top.transient(self.root)
        self._place_dialog(top)
        return top

    def _place_dialog(self, top):
        # top left corner 50 px into the main window; root.geometry() holds the normal place even when
        # the window is maximized (maybe on another monitor), winfo_root* is where it really is
        top.geometry(f"+{self.root.winfo_rootx() + 50}+{self.root.winfo_rooty() + 50}")

    def _settings(self):
        if (top := getattr(self, "_settings_top", None)) and top.winfo_exists():  # one settings dialog per window
            self._place_dialog(top)  # the main window may have moved since
            top.deiconify()
            top.lift()
            top.focus_force()
            return
        th = self.th
        top = self._settings_top = self._dialog("Settings")
        fields = [("Server address or connection code", "client", "host"),
                  ("Port", "general", "port"), ("Token", "general", "token"), ("Fight ends after idle seconds", "general", "idle_end"),
                  ("Cockpit always on top (over EVE in window mode)", "general", "always_on_top"),
                  ("Graph always on top (over EVE in window mode)", "general", "graph_on_top"),
                  ("Graph shows the last minutes (live)", "general", "graph_live_minutes"),
                  ("Graph shows the last minutes (replays)", "general", "graph_replay_minutes"),
                  ("Show friendly fire (when connected, the server's setting counts)", "general", "friendly_fire"),
                  ("Check for updates at start", "update", "check"),
                  ("Log folder", "client", "log_dir")]  # log folder last: the browse button sits in its row
        values = {}
        for row, (label, sec, key) in enumerate(fields):
            tk.Label(top, text=label, bg=th["bg"], fg=th["fg"]).grid(row=row, column=0, sticky="w", padx=10, pady=4)
            var = values[(sec, key)] = tk.StringVar(value=self.cfg[sec][key])
            if key in ("always_on_top", "graph_on_top", "friendly_fire", "check"):
                var.set("yes" if self.cfg.getboolean(sec, key) else "no")
                # native ttk box (white with a dark tick): tk.Checkbutton draws the tick in system colours
                ttk.Style(top).configure("Dark.TCheckbutton", background=th["bg"])
                ttk.Checkbutton(top, variable=var, onvalue="yes", offvalue="no", style="Dark.TCheckbutton").grid(
                    row=row, column=1, sticky="w", padx=6)
            else:
                tk.Entry(top, textvariable=var, width=50).grid(row=row, column=1, padx=10)
        log_dir = values[("client", "log_dir")]
        _button(top, "…", lambda: log_dir.set(filedialog.askdirectory(parent=top) or log_dir.get()), th).grid(
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
            for key in ("graph_live_minutes", "graph_replay_minutes"):
                minutes = values[("general", key)].get().strip()
                if not minutes.isdigit() or not 1 <= int(minutes) <= 600:
                    messagebox.showerror("Settings", "Graph minutes must be a number from 1 to 600.", parent=top)
                    return
            changed = {k for k, var in values.items() if self.cfg[k[0]][k[1]] != var.get().strip()}
            new = {}
            for sec, key in changed:
                self.cfg[sec][key] = new.setdefault(sec, {})[key] = values[(sec, key)].get().strip()
            update_config(self.cfg_path, new)
            top.destroy()
            # the rest is read live; a server keeps its running fight unless the port changes
            if changed & {("general", "port"), ("client", "host"), ("general", "token")}:
                self.restart()
                return
            for tab in self.tabs.values():
                tab.apply_topmost()
                tab.redraw()
            self._status("settings saved")
        _button(top, "⟳ Check for updates", lambda: self._check_update(manual=True), th).grid(
            row=len(fields), column=0, sticky="w", padx=10, pady=10)
        _button(top, "✔ Save", save, th).grid(row=len(fields), column=1, sticky="e", padx=10, pady=10)


def _mmss(secs):
    return f"{int(secs) // 60:02d}:{int(secs) % 60:02d}"
