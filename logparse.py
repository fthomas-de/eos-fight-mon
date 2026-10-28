"""Turns EVE gamelog combat lines into events and tails the gamelog folder."""
import html
import os
import re
import time
from collections import namedtuple
from pathlib import Path

# kind: dmg | shield | armor | hull | cap | neut | nos | scram | point | jam | burst
# burst: the listener's command burst (weapon) reached amount fleet members; src = dst = listener
# quality: how well a shot hit ("Wrecks", "Smashes", … in the client's language), None for everything else
Event = namedtuple("Event", "kind src src_ship dst dst_ship amount weapon logger quality", defaults=(None,))
KINDS = {"dmg", "shield", "armor", "hull", "cap", "neut", "nos", "scram", "point", "jam", "burst"}

_LINE = re.compile(r"\[ [\d.: ]+ \] \(combat\) (.*)")
# English only: no client in another language has logged a burst here yet
_BURST = re.compile(r"\[ [\d.: ]+ \] \(notify\) Your <b>([^<]*Burst[^<]*)</b> has applied bonuses to <b>(\d+)</b> fleet "
                    r"members\.")
# Every client language writes the same markup, only the words differ. So a line is read by its structure:
# the colour gives kind and direction, <b> holds amount and names, and non-English clients add the English
# name of ships and modules as <localized hint="...">; the shown name after it ends with "*".
_HINT = re.compile(r'<localized hint="([^"]*)">[^<*]*\*?')
_TOKEN = re.compile(r"<(/?)b>|<[^>]*>|([^<]+)")
_COLOR = re.compile(r"<color=(0x\w+)>")
_DMG = {"0xff00ffff": False, "0xffcc0000": True}  # colour -> done to the listener
_ENERGY = {"0xff7fffff": False, "0xffe57f7f": True}  # neut and nos
_REMOTE = "0xffccff66"  # reps given and received look alike, only one word differs
_RECEIVED = re.compile(r"\b(?:by|von|par|por)\b|получено|受け|받음|由")  # en de fr es ru ja ko zh
_REMOTE_KIND = (("Capacitor", "cap"), ("Shield", "shield"), ("Armor", "armor"), ("Hull", "hull"))
_SCRAM = re.compile(r"scramble|inhibition|Unterbrechung|スクランブル|스크램블|глушени|distorsión|扰频")
_POINT = re.compile(r"disruption|perturbation|Stör|妨害|디스럽트|подавлени|disrupción|扰断")
_YOU = {"you", "vous", "sie", "ihnen", "あなた", "당신", "вы", "ti", "tu parte", "你"}
# the 'label' stands after the ship in newer logs, before it in older ones
_PARTY = re.compile(r"(.+?)\s*\[[^\]]*\](?:<[^>]*>)?\s*(?:'[^']*')?\s*\((.+?)\)(?:'.*')?")
_DOUBLED = re.compile(r"(.+) \1")
# header line 3 is "Listener: name" in the client's language; a log without character has the start time there
_LISTENER = re.compile(rb"\A-+\r?\n[^\n]*\n[^\n:]*: (.+?)\r?\n")
_STARTED = re.compile(rb"\d{4}\.\d\d\.\d\d \d\d:\d\d:\d\d")


def party(text, logger):
    """'Name [CORP]<ALLY> (Ship)'x'' or 'Name[CORP](Ship)' -> (name, ship). NPCs and drones come without ship."""
    text = text.replace("\x01", "").replace("\x02", "").strip(" ,.!！")
    if text.lower() in _YOU:
        return logger, None
    if m := _PARTY.fullmatch(text):
        return m[1], m[2]
    d = _DOUBLED.fullmatch(text)  # a drone in space: its name, then its type, both the same
    return (d[1] if d else text), None


def _pieces(body):
    """Markup -> [text, bold, closed] per run of plain or bold text; hints become \x01English\x02."""
    pieces, depth = [], 0
    for m in _TOKEN.finditer(_HINT.sub(lambda h: f"\x01{h[1]}\x02", body)):
        if m[2]:
            if not pieces or pieces[-1][1] != (depth > 0):
                pieces.append(["", depth > 0, False])
            pieces[-1][0] += html.unescape(m[2])
        elif m[0] == "<b>":
            if not depth:
                pieces.append(["", True, False])
            depth += 1
        elif m[0] == "</b>" and depth:
            depth -= 1
            pieces[-1][2] = not depth
    return [[" ".join(t.split()), b, c] for t, b, c in pieces]


def parse(line, logger):
    """One gamelog line -> Event, or None for everything that is not a combat effect (misses included)."""
    if b := _BURST.fullmatch(line):
        return Event("burst", logger, None, logger, None, int(b[2]), b[1], logger)
    m = _LINE.fullmatch(line)
    if not m or not (c := _COLOR.match(m[1])):
        return None
    color, pieces = c[1], _pieces(m[1])
    bold = [p for p in pieces if p[1] and p[0]]
    if color not in _DMG and color not in _ENERGY and color != _REMOTE:
        # jams name the ECM module (English drone jams only end in " - Hornet EC-300"), warp attempts do not
        ecm = re.search("\x01([^\x02]*ECM[^\x02]*)\x02", " ".join(p[0] for p in pieces))
        tail = pieces[-1][0].rstrip(".")
        if ecm or not pieces[-1][1] and tail[:1] in "-—":
            return _jam(bold, ecm[1] if ecm else re.sub(r"^.*[-—] ", "", tail), logger)
        return _warp(bold, logger)
    if len(bold) < 2 or not (n := re.search(r"\d+", bold[0][0])):
        return None
    amount, other = int(n[0]), bold[1]
    # after the other party: " - Weapon - Hits" (NPCs without weapon) or " - Module", Spanish with " — "
    rest = " " + " ".join(p[0] for p in pieces[pieces.index(other) + 1:]).replace(" — ", " - ").rstrip(".")
    hint = re.search("\x01(.*?)\x02", rest)
    parts = rest.split(" - ")
    if color in _DMG:
        weapon = (hint[1] if hint else parts[1]) if len(parts) >= 3 else None
        quality = re.sub("\x01.*?\x02", "", parts[-1]).strip() if len(parts) >= 2 else None
        return _between("dmg", _DMG[color], other[0], amount, weapon, logger, quality or None)
    module = hint[1] if hint else parts[-1] if len(parts) >= 2 else None
    verb = " ".join(re.sub("\x01.*?\x02", "", p[0]) for p in pieces if not p[1])
    if color in _ENERGY:  # NPCs name themselves instead of the module
        nos = "Nosferatu" in (module or "") or " drained " in verb
        return _between("nos" if nos else "neut", _ENERGY[color], other[0], amount, module, logger)
    kind = next((k for word, k in _REMOTE_KIND if word in (module or "")), None)
    return kind and _between(kind, bool(_RECEIVED.search(verb)), other[0], amount, module, logger)


def _between(kind, incoming, other, amount, weapon, logger, quality=None):
    name, ship = party(other, logger)
    if incoming:
        return Event(kind, name, ship, logger, None, amount, weapon, logger, quality)
    return Event(kind, logger, None, name, ship, amount, weapon, logger, quality)


def _jam(bold, module, logger):
    # "You're <b>jammed</b> by <b>X</b>" has the word and the jammer in bold parts of their own (any order);
    # the listener's own jam is one bold part with word and target together: "<b>X jammed</b>"
    if len(bold) >= 2:
        jammer = next((p for p in bold if _PARTY.search(p[0])), bold[-1])
        name, ship = party(jammer[0], logger)
        return Event("jam", name, ship, logger, None, 1, module, logger)
    if not bold:
        return None
    text = bold[0][0].replace("\x01", "").replace("\x02", "")
    text = re.sub(r"^(Neutralizado:|Сопровождение целей) ", "", text)  # es, ru put the word in front
    m = _PARTY.match(text)
    name, ship = (m[1], m[2]) if m else (text.rsplit(" ", 1)[0], None)
    return Event("jam", logger, None, name, ship, 1, module, logger)


def _warp(bold, logger):
    # "<b>Warp scramble attempt</b> from <b>A</b> to <b>B": B's bold is never closed. The order of the
    # parts differs between languages, so A is the closed part that is not the attempt itself.
    word = next((p for p in bold if _SCRAM.search(p[0]) or _POINT.search(p[0])), None)
    target = next((p for p in bold if not p[2]), None)
    source = next((p for p in bold if p[2] and p is not word), None)
    if not (word and target and source) or "{" in target[0]:  # the Japanese client sometimes forgets to fill in names
        return None
    src, src_ship = party(source[0], logger)
    dst, dst_ship = party(target[0], logger)
    return Event("scram" if _SCRAM.search(word[0]) else "point", src, src_ship, dst, dst_ship, 1, None, logger)


_headers = {}  # path -> listener; a gamelog never changes its header


def listener(path):
    if path not in _headers:
        try:
            with open(path, "rb") as fh:
                m = _LISTENER.search(fh.read(1024))
        except OSError:
            return ""
        if not m:
            return ""  # header not written yet: ask again later
        _headers[path] = "" if _STARTED.fullmatch(m[1]) else m[1].decode("utf-8", "replace")
    return _headers[path]


def characters(log_dir, max_age=86400):
    """Characters with a gamelog written in the last day, most recently active first."""
    now = time.time()
    try:
        entries = sorted(((de.stat().st_mtime, de.path) for de in os.scandir(Path(log_dir).expanduser())
                          if de.name.endswith(".txt")), reverse=True)
    except OSError:
        return []
    names = {}
    for mtime, path in entries:
        if now - mtime > max_age:
            break
        if name := listener(path):
            names.setdefault(name)
    return list(names)


class LogWatcher:
    """Tails the gamelogs of one character. Files already there when watching starts are read from their end."""

    def __init__(self, active_secs=600):
        self.active_secs = active_secs
        self.files = {}  # path -> [offset, unfinished line]
        self._key = None
        self.combat = self.parsed = 0  # combat lines seen / understood, to spot a log in another language

    @property
    def foreign(self):
        """Plenty of combat lines and not one understood: the EVE client writes another language."""
        return self.combat >= 10 and not self.parsed

    def poll(self, log_dir, char):
        first = (log_dir, char) != self._key
        if first:  # other folder or character: forget offsets, skip the past
            self._key, self.files = (log_dir, char), {}
            self.combat = self.parsed = 0
        now, events = time.time(), []
        if not char:
            return events
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
            f = self.files.setdefault(de.path, [st.st_size if first else 0, b""])
            if now - st.st_mtime > self.active_secs or st.st_size <= f[0] or listener(de.path) != char:
                continue
            try:
                with open(de.path, "rb") as fh:
                    fh.seek(f[0])
                    data = fh.read()
            except OSError:
                continue
            f[0] += len(data)
            *lines, f[1] = (f[1] + data).split(b"\n")
            for raw in lines:
                line = raw.decode("utf-8", "replace").rstrip("\r")
                if e := parse(line, char):
                    events.append(e)
                    self.parsed += 1
                if "(combat) <color=" in line:  # misses start without colour and are not parsed on purpose
                    self.combat += 1
        return events
