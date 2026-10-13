"""Folds the events of all clients into 2 s ticks and stores finished fights as history."""
import gzip
import json
import os
import re
import time
from pathlib import Path

from logparse import KINDS, Event

TICK = 2  # seconds
WINDOW = 5  # ticks averaged into per-second rates (10 s)
IDLE_END = 60  # default seconds without an event that end the fight
EWAR = {"scram", "point", "jam"}
REPS = {"shield", "armor", "hull", "cap"}
DRONES = "Drones (owner unknown)"
HISTORY_NAME = re.compile(r"\d{8}_\d{6}\.jsonl\.gz")  # fight start in UTC, so names sort by date and time
# shortcut: drones are recognised by one word of their type name; add a word when a drone shows up as a ship
_DRONE_WORDS = {
    "Acolyte", "Infiltrator", "Praetor", "Curator", "Hobgoblin", "Hammerhead", "Ogre", "Garde",
    "Warrior", "Valkyrie", "Berserker", "Bouncer", "Hornet", "Vespa", "Wasp", "Warden", "Gecko",
    "Bot", "Dragonfly", "Firbolg", "Einherji", "Templar", "Cyclops", "Malleus", "Tyrfing", "Mantis",
    "Gram", "Locust", "Satyr", "Siren", "Dromi", "Equite", "Termite", "Ametat", "Antero",
}


def is_drone(name):
    return bool(name) and not _DRONE_WORDS.isdisjoint(name.split())


class Fight:
    def __init__(self, history_dir=None, solo=False):
        self.history_dir = history_dir and Path(history_dir)  # None: show only, never store (server decides)
        self.solo = solo  # one client without server: hide friends, keep only own ship and enemies
        self.listeners = set()  # characters of all connected clients
        self.pending = []
        self._reset()

    def _reset(self):
        self.ticks, self.left, self.ships, self.last_event = [], set(), {}, 0.0
        self.friends = set()

    def add(self, events):
        self.pending.extend(events)

    def tick(self, now):
        """Fold the pending events into one tick. None while no fight is running."""
        events, self.pending = self.pending, []
        for e in events:  # whoever reps with a client is on our side; known before judging this tick's shots
            if e.kind in REPS:
                self.friends |= {e.src, e.dst} - self.listeners
        ours = self.listeners | self.friends
        flows = {}
        for e in events:
            if e.dst == e.logger and e.src != e.logger and e.src in self.listeners:
                continue  # the source client logged the same thing
            if self.solo and e.logger not in (e.src, e.dst):
                continue  # e.g. a rat pointing a fleet mate: neither own ship nor enemy of it
            if e.kind not in REPS and e.src in ours and e.dst in ours:
                continue  # friendly fire is not shown
            key = (e.kind, self._name(e.src, e.src_ship), self._name(e.dst, e.dst_ship))
            flows[key] = 1 if e.kind in EWAR else flows.get(key, 0) + e.amount
        if flows:
            self.last_event = now
        elif not self.ticks:
            return None
        self.left |= {n for _, s, d in flows for n in (s, d) if n in self.listeners}
        start = self.ticks[0]["t"] if self.ticks else int(now)
        tick = {"t": int(now), "start": start, "flows": [[k, s, d, a] for (k, s, d), a in flows.items()],
                "ships": dict(self.ships), "left": sorted(self.left)}
        if self.solo:  # friends: counted in the sums, not drawn
            tick["hidden"] = sorted(self.friends)
        self.ticks.append(tick)
        return tick

    def _name(self, name, ship):
        # drone damage is logged with the owner as source, so it counts for the owner already;
        # only drones acting or targeted on their own have no known owner
        if ship in (None, name) and is_drone(name):
            return DRONES
        if ship:
            self.ships[name] = ship
        return name

    def ended(self, now, idle_end=IDLE_END):
        return bool(self.ticks) and now - self.last_event >= idle_end

    def end(self):
        """Store the running fight (without its idle tail) and wait for the next one."""
        ticks = self.ticks
        while ticks and not ticks[-1]["flows"]:
            ticks.pop()
        if ticks and self.history_dir:
            save_history(self.history_dir, time.strftime("%Y%m%d_%H%M%S", time.gmtime(ticks[0]["t"])) + ".jsonl.gz",
                         ticks)
        self._reset()


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


def to_event(x):
    """An event a client sent, checked field by field; None if malformed."""
    try:
        e = Event(*x)
    except TypeError:
        return None
    names = (e.src, e.dst, e.logger)
    optional = (e.src_ship, e.dst_ship, e.weapon)
    ok = (e.kind in KINDS
          and all(isinstance(v, str) and len(v) <= 100 for v in names)
          and all(v is None or isinstance(v, str) and len(v) <= 100 for v in optional)
          and type(e.amount) is int and 0 <= e.amount < 10**9)
    return e if ok else None
