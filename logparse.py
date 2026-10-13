"""Turns EVE gamelog combat lines into events and tails the gamelog folder."""
import html
import os
import re
import time
from collections import namedtuple
from pathlib import Path

# kind: dmg | shield | armor | hull | cap | neut | nos | scram | point | jam
Event = namedtuple("Event", "kind src src_ship dst dst_ship amount weapon logger")
KINDS = {"dmg", "shield", "armor", "hull", "cap", "neut", "nos", "scram", "point", "jam"}

_LINE = re.compile(r"\[ [\d.: ]+ \] \(combat\) (.*)")
_TAG = re.compile(r"<[^>]*>")
_INCOMING = ("<color=0xffcc0000>", "<color=0xffe57f7f>")  # red: done to the listener, cyan: done by them
_PARTY = re.compile(r"(.+?)\s*\[[^\]]*\](?:<[^>]*>)?\s*\((.+?)\)(?:'.*')?")
_REMOTE_KIND = {"shield": "shield", "armor": "armor", "hull": "hull", "capacitor": "cap"}

_DMG = re.compile(r"(\d+) (to|from) (.+)")
_REMOTE = re.compile(r"(\d+) remote (shield|armor|hull|capacitor) \w+ (to|by) (.+)")
_NEUT = re.compile(r"(\d+) GJ energy neutralized (.+)")
_NOS = re.compile(r"[-+]?(\d+) GJ energy drained (from|to) (.+)")
_WARP = re.compile(r"Warp (scramble|disruption) attempt from (.+?) to (.+?)!?")
_JAM = re.compile(r"You're jammed by (.+)")
_LISTENER = re.compile(rb"Listener: (.+?)\r?\n")


def party(text, logger):
    """'Name [CORP]<ALLY> (Ship)'x'' or 'Name[CORP](Ship)' -> (name, ship). NPCs and drones come without ship."""
    if text == "you":
        return logger, None
    m = _PARTY.fullmatch(text)
    return (m[1], m[2]) if m else (text, None)


def parse(line, logger):
    """One gamelog line -> Event, or None for everything that is not a combat effect (misses included)."""
    m = _LINE.fullmatch(line)
    if not m:
        return None
    incoming = m[1].startswith(_INCOMING)
    text = " ".join(html.unescape(_TAG.sub("", m[1])).split())

    if m := _DMG.fullmatch(text):
        return _between("dmg", m[2] == "from", m[3], 3, int(m[1]), logger)
    if m := _REMOTE.fullmatch(text):
        return _between(_REMOTE_KIND[m[2]], m[3] == "by", m[4], 2, int(m[1]), logger)
    if m := _NEUT.fullmatch(text):
        return _between("neut", incoming, m[2], 2, int(m[1]), logger)
    if m := _NOS.fullmatch(text):
        return _between("nos", m[2] == "to", m[3], 2, int(m[1]), logger)
    if m := _JAM.fullmatch(text):
        return _between("jam", True, m[1], 2, 1, logger)
    if m := _WARP.fullmatch(text):
        src, src_ship = party(m[2], logger)
        dst, dst_ship = party(m[3], logger)
        return Event("scram" if m[1] == "scramble" else "point", src, src_ship, dst, dst_ship, 1, None, logger)
    return None


def _between(kind, incoming, rest, parts_with_weapon, amount, logger):
    # rest: "Other - Weapon - Hits" (damage) or "Other - Module"; NPC damage has no weapon part
    parts = rest.split(" - ")
    weapon = parts[1] if len(parts) >= parts_with_weapon else None
    name, ship = party(parts[0], logger)
    if incoming:
        return Event(kind, name, ship, logger, None, amount, weapon, logger)
    return Event(kind, logger, None, name, ship, amount, weapon, logger)


class LogWatcher:
    """Tails every recently written gamelog. Files already there on the first poll are read from their end."""

    def __init__(self, active_secs=600):
        self.active_secs = active_secs
        self.files = {}  # path -> [listener, offset, unfinished line]
        self.listeners = set()
        self._dir = None

    def poll(self, log_dir):
        first = log_dir != self._dir
        if first:  # new folder: forget offsets, skip its past
            self._dir, self.files = log_dir, {}
        now, events, listeners = time.time(), [], set()
        try:
            entries = list(os.scandir(Path(log_dir).expanduser()))
        except OSError:
            return events
        for de in entries:
            if not de.name.endswith(".txt"):
                continue
            try:
                st = de.stat()
            except OSError:
                continue
            f = self.files.setdefault(de.path, [None, st.st_size if first else 0, b""])
            if now - st.st_mtime > self.active_secs:
                continue
            if f[0] is not None and st.st_size <= f[1]:
                if f[0]:
                    listeners.add(f[0])
                continue
            try:
                with open(de.path, "rb") as fh:
                    if f[0] is None:
                        m = _LISTENER.search(fh.read(1024))
                        f[0] = m[1].decode("utf-8", "replace") if m else ""
                    fh.seek(f[1])
                    data = fh.read()
            except OSError:
                continue
            f[1] += len(data)
            *lines, f[2] = (f[2] + data).split(b"\n")
            if f[0]:
                listeners.add(f[0])
                for raw in lines:
                    if e := parse(raw.decode("utf-8", "replace").rstrip("\r"), f[0]):
                        events.append(e)
        self.listeners = listeners
        return events
