"""Folds the events of all clients into 2 s ticks and stores finished fights as history."""
import gzip
import json
import os
import re
import time
from pathlib import Path

from drones import DRONE_TYPES
from logparse import KINDS, Event

TICK = 2  # seconds
WINDOW = 5  # ticks averaged into per-second rates (10 s)
IDLE_END = 60  # default seconds without an event that end the fight
EWAR = {"scram", "point", "jam"}
REPS = {"shield", "armor", "hull", "cap"}
BURST_SECS = 120  # a command burst's bonus lasts this long after its last "applied bonuses" (cycle 60 s)
DRONES = "Drones (owner unknown)"
# fight start in UTC, so names sort by date and time; a client's own fight without server adds ".solo-<character>"
HISTORY_NAME = re.compile(r"\d{8}_\d{6}(?:\.solo-[\w~-]{1,200})?\.jsonl\.gz")


def is_drone(name):
    return name in DRONE_TYPES


class Fight:
    def __init__(self, history_dir=None, solo=False):
        self.history_dir = history_dir and Path(history_dir)  # None: show only, never store (server decides)
        self.solo = solo  # one client without server: hide friends, keep only own ship and enemies
        self.listeners = set()  # characters of all connected clients
        self.friendly_fire = False  # show hostile effects between clients and their rep partners
        self.pending = []
        self.bursts = {}  # client -> burst module -> (fleet members reached, time); outlives fights
        self._reset()

    def _reset(self):
        self.ticks, self.left, self.ships, self.last_event = [], set(), {}, 0.0
        self.friends = set()
        self.drone_users = {}  # drone type -> clients that hit something with it in this fight

    def add(self, events):
        self.pending.extend(events)

    def tick(self, now):
        """Fold the pending events into one tick. None while no fight is running."""
        events, self.pending = self.pending, []
        linked = False  # a burst starts and prolongs a fight like any event, but draws no arrow
        for e in events:
            if e.kind == "burst":
                self.bursts.setdefault(e.src, {})[e.weapon] = (e.amount, now)
                linked = True
        events, bursts = [e for e in events if e.kind != "burst"], self.active_bursts(now)
        for e in events:  # a client's own drone hits are logged with the drone type as weapon
            if e.src == e.logger and e.src in self.listeners and e.weapon and is_drone(e.weapon):
                self.drone_users.setdefault(e.weapon, set()).add(e.src)
        for e in events:  # whoever reps with a client is on our side; known before judging this tick's shots
            if e.kind in REPS:
                self.friends |= {e.src, e.dst} - self.listeners
        ours = self.listeners | self.friends
        flows, single = {}, []
        for e in events:
            if e.dst == e.logger and e.src != e.logger and e.src in self.listeners:
                continue  # the source client logged the same thing
            if self.solo and e.logger not in (e.src, e.dst):
                continue  # e.g. a rat pointing a fleet mate: neither own ship nor enemy of it
            if not self.friendly_fire and e.kind not in REPS and e.src in ours and e.dst in ours:
                continue  # friendly fire is not shown unless asked for
            key = (e.kind, self._name(e.src, e.src_ship), self._name(e.dst, e.dst_ship))
            flows[key] = 1 if e.kind in EWAR else flows.get(key, 0) + e.amount
            single.append([e.kind, self._detail(e.src, e.src_ship), self._detail(e.dst, e.dst_ship), e.amount,
                           e.weapon, e.quality])
        if flows or linked:
            self.last_event = now
        elif not self.ticks:
            return None
        self.left |= {n for _, s, d in flows for n in (s, d) if n in self.listeners} | set(bursts)
        start = self.ticks[0]["t"] if self.ticks else int(now)
        tick = {"t": int(now), "start": start, "flows": [[k, s, d, a] for (k, s, d), a in flows.items()],
                "ships": dict(self.ships), "left": sorted(self.left)}
        if single:  # each log event on its own, for the graph's hover box
            tick["events"] = single
        if bursts:  # per client [[module, fleet members reached], …], shown in its box on the left
            tick["bursts"] = bursts
        if self.solo:  # friends: counted in the sums, not drawn
            tick["hidden"] = sorted(self.friends)
        self.ticks.append(tick)
        return tick

    def active_bursts(self, now):
        """{client: [[module, fleet members reached, seconds since applied], …]} of the bursts running now; outside
        a fight (after the idle end, between two burst cycles) the backends send them on their own."""
        bursts = {c: sorted([m, n, int(now - t)] for m, (n, t) in mods.items() if now - t < BURST_SECS)
                  for c, mods in self.bursts.items()}
        return {c: mods for c, mods in bursts.items() if mods}

    def _name(self, name, ship):
        # drone damage is logged with the owner as source, so it counts for the owner already;
        # only drones acting or targeted on their own have no known owner
        if ship in (None, name) and is_drone(name):
            return DRONES
        if ship:
            self.ships[name] = ship
        return name

    def _detail(self, name, ship):
        """Name for the hover: a drone without owner as its type, with the one client that uses that type
        (a guess: the log never names the owner, and others may fly the same drones)."""
        if ship in (None, name) and is_drone(name):
            users = self.drone_users.get(name, ())
            return f"{name} (drone, {next(iter(users))}?)" if len(users) == 1 else f"{name} (drone)"
        return name

    def ended(self, now, idle_end=IDLE_END):
        return bool(self.ticks) and now - self.last_event >= idle_end

    def end(self):
        """Store the running fight (without its idle tail) and wait for the next one."""
        ticks = self.ticks
        while ticks and not ticks[-1]["flows"]:
            ticks.pop()
        if ticks and self.history_dir:
            name = time.strftime("%Y%m%d_%H%M%S", time.gmtime(ticks[0]["t"]))
            if self.solo:  # two tabs may see the same fight start in the same second
                name += ".solo-" + (solo_tag("".join(sorted(self.listeners))) or "x")
            save_history(self.history_dir, name + ".jsonl.gz", ticks)
        self._reset()


def solo_tag(char):
    """A character name fit for a file name and back: "E 'o" <-> "E~20~~27~o"."""
    return "".join(c if c.isalnum() or c in "_-" else f"~{ord(c):x}~" for c in char)


def solo_char(tag):
    return re.sub(r"~([0-9a-f]+)~", lambda m: chr(int(m[1], 16)), tag)


def save_history(history_dir, name, ticks):
    """Write via a temp file, so parallel instances sharing the folder never read half a fight."""
    history_dir = Path(history_dir)
    history_dir.mkdir(parents=True, exist_ok=True)
    tmp = history_dir / f".{name}.{os.getpid()}.tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        fh.writelines(json.dumps(t) + "\n" for t in ticks)
    os.replace(tmp, history_dir / name)


def list_history(history_dir):
    """Stored fights, newest start first."""
    return sorted((p.name for p in Path(history_dir).glob("*.jsonl.gz") if HISTORY_NAME.fullmatch(p.name)),
                  reverse=True)


def load_history(history_dir, name):
    if name not in list_history(history_dir):  # names come from the network: only ever open listed files
        return []
    with gzip.open(Path(history_dir) / name, "rt", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


_secs = {}  # (name, mtime) -> fight seconds, so the replay list reads each file once


def history_secs(history_dir, names):
    """Fight length per stored fight, the same as the fight clock shows at its end."""
    out = {}
    for name in names:
        path = Path(history_dir) / name
        try:
            key = (name, path.stat().st_mtime_ns)
            if key not in _secs:
                ticks = load_history(history_dir, name)
                _secs[key] = ticks[-1]["t"] - ticks[0]["t"] + TICK if ticks else 0
        except (OSError, ValueError, KeyError, EOFError):
            continue
        out[name] = _secs[key]
    return out


def to_event(x):
    """An event a client sent, checked field by field; None if malformed."""
    try:
        e = Event(*x)
    except TypeError:
        return None
    names = (e.src, e.dst, e.logger)
    optional = (e.src_ship, e.dst_ship, e.weapon, e.quality)
    ok = (e.kind in KINDS
          and all(isinstance(v, str) and len(v) <= 100 for v in names)
          and all(v is None or isinstance(v, str) and len(v) <= 100 for v in optional)
          and type(e.amount) is int and 0 <= e.amount < 10**9)
    return e if ok else None
