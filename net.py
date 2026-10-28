"""TCP, one JSON message per line. Clients send events every tick, the server answers with merged ticks."""
import asyncio
import hmac
import ipaddress
import json
import socket
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from fight import (HISTORY_NAME, IDLE_END, TICK, Fight, history_secs, list_history, load_history, save_history,
                   to_event)
from update import VERSION, _key

CLIENT_LIMIT = 64 * 2**20  # a whole fight comes in one line when replays sync
SERVER_LIMIT = 2**20
SYNC_DAYS = 7  # replays older than this are not fetched


def _line(msg):
    return json.dumps(msg, separators=(",", ":")).encode() + b"\n"


def idle_end(cfg):
    """Seconds without an event that end a fight; read every tick so a change in the settings applies at once."""
    try:
        return max(5, cfg.getint("general", "idle_end"))
    except ValueError:  # hand-edited garbage in config.ini
        return IDLE_END


def friendly_fire(cfg):
    try:
        return cfg.getboolean("general", "friendly_fire")
    except ValueError:
        return False


def _is_local(writer):
    ip = ipaddress.ip_address(writer.get_extra_info("peername")[0])
    return (getattr(ip, "ipv4_mapped", None) or ip).is_loopback


async def send_reset(cfg):
    """End the running fight of the server on this machine (for the headless server). Returns a message."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", cfg.getint("general", "port"), limit=CLIENT_LIMIT), 5)
    except (OSError, TimeoutError) as e:
        return f"no server running on this machine ({e or 'timeout'})"
    writer.write(_line({"type": "hello", "token": cfg["general"]["token"]}) + _line({"type": "reset"}))
    try:
        while line := await asyncio.wait_for(reader.readline(), 5):
            kind = json.loads(line).get("type")
            if kind in ("reset", "denied"):
                return "reset done (a running fight is stored)" if kind == "reset" else "token rejected"
        return "server closed the connection"
    except (OSError, ValueError, TimeoutError):
        return "no answer from the server"
    finally:
        writer.close()


def _warning(char, watcher):
    if not char:
        return "no character found in the gamelogs – check the log folder"
    if watcher.foreign:
        return f"cannot read the log of {char} – unknown log format"
    return ""


def local_ip():
    """The address other machines in the LAN reach this one by. No packet is sent."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def public_address(cfg):
    """The address clients on the internet use: from the config (e.g. a DynDNS name), else asked from ipify."""
    if addr := cfg["general"]["public_address"].strip():
        return addr
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=3) as r:
            return str(ipaddress.ip_address(r.read(64).decode().strip()))
    except (OSError, ValueError):
        return local_ip()  # offline: at least the LAN address


class Server:
    def __init__(self, cfg, out):
        self.cfg, self.out = cfg, out  # out(msg) feeds the local window
        self.fight = Fight(cfg["general"]["history_dir"])
        self.clients = {}  # writer -> characters of that client
        self.versions = {}  # writer -> program version of that client
        self._shown = None  # client list last sent to the window
        self._srv = None

    async def run(self):
        for attempt in range(10):  # after a restart the old copy may hold the port for a moment
            try:
                srv = self._srv = await asyncio.start_server(self._handle, port=self.cfg.getint("general", "port"),
                                                 limit=SERVER_LIMIT)
                break
            except OSError:
                if attempt == 9:
                    raise
                await asyncio.sleep(0.5)
        self.out({"type": "status", "text": "server running"})
        async with srv:
            while True:
                await asyncio.sleep(TICK)
                now = time.time()
                self.fight.listeners = set().union(*self.clients.values())
                self.fight.friendly_fire = friendly_fire(self.cfg)
                self._report_clients()
                if tick := self.fight.tick(now):
                    self._broadcast({"type": "tick", **tick, "idle_end": idle_end(self.cfg)})  # clients show the end countdown
                else:  # links outside a fight (older clients ignore the message)
                    self._broadcast({"type": "bursts", "bursts": self.fight.active_bursts(now)})
                if self.fight.ended(now, idle_end(self.cfg)):
                    await self.reset()

    async def stop(self):
        """Its tab is closed: store the running fight, free the port and drop the clients."""
        self.fight.end()
        self.out({"type": "reset"})
        if self._srv:
            self._srv.close()
        for w in list(self.clients):
            w.close()

    async def reset(self):
        self.fight.end()
        self._broadcast({"type": "reset"})  # clients then sync the stored fight

    async def history(self):
        names = list_history(self.fight.history_dir)
        self.out({"type": "history", "sessions": names, "secs": history_secs(self.fight.history_dir, names)})

    async def load(self, name):
        self.out({"type": "session", "ticks": load_history(self.fight.history_dir, name)})

    def connections(self):
        """[address, characters, version note] of every connected client, sorted by character.
        The note names a client version that differs from the server's, else it is empty."""
        def note(w):
            v = self.versions.get(w)
            return "" if v == VERSION else f"v{v}" if v else "version before 0.6.5"
        return sorted(([w.get_extra_info("peername")[0].removeprefix("::ffff:"), sorted(chars), note(w)]
                       for w, chars in self.clients.items()), key=lambda c: (c[1] or ["~"], c[0]))

    def _report_clients(self):
        if (now := self.connections()) != self._shown:
            self._shown = now
            self.out({"type": "clients", "list": now})

    def _broadcast(self, msg):
        self.out(msg)
        data = _line(msg)
        for w in list(self.clients):
            if w.transport.get_write_buffer_size() > CLIENT_LIMIT:
                w.close()  # client stopped reading
            else:
                w.write(data)

    async def _handle(self, reader, writer):
        try:
            hello = json.loads(await asyncio.wait_for(reader.readline(), 10))
            token = self.cfg["general"]["token"].encode()
            if not hmac.compare_digest(str(hello.get("token", "")).encode(), token):
                writer.write(_line({"type": "denied"}))
                return
            self.versions[writer] = str(hello.get("version", ""))[:20]
            writer.write(_line({"type": "version", "version": VERSION}))  # older clients ignore it
            for tick in self.fight.ticks:  # late joiners get the running fight from its start
                writer.write(_line({"type": "tick", **tick, "idle_end": idle_end(self.cfg)}))
            self.clients[writer] = set()
            async for line in reader:
                msg = json.loads(line)
                kind = msg.get("type")
                if kind == "events":
                    self.clients[writer] = {n for n in msg["listeners"][:50] if isinstance(n, str)}
                    self.fight.add(e for e in map(to_event, msg["events"]) if e)
                elif kind == "reset" and _is_local(writer):  # `eos-fight-mon --reset` on the server machine
                    await self.reset()
                elif kind == "history":  # clients from outside cannot reset, even with the token
                    writer.write(_line({"type": "history", "sessions": list_history(self.fight.history_dir)}))
                elif kind == "load":
                    name = str(msg.get("name"))
                    writer.write(_line({"type": "session", "name": name,
                                        "ticks": load_history(self.fight.history_dir, name)}))
        except (OSError, ValueError, TypeError, KeyError, AttributeError, TimeoutError):
            pass  # broken or hostile client: just drop it
        finally:
            self.clients.pop(writer, None)
            self.versions.pop(writer, None)
            writer.close()


class Client:
    def __init__(self, cfg, watcher, out, char):
        self.cfg, self.watcher, self.out, self.char = cfg, watcher, out, char
        self.history_dir = cfg["general"]["history_dir"]  # replays synced from the server
        # live view while not connected, stored as "<start>.solo-<character>"; connected, the server decides
        self.fight = Fight(self.history_dir, solo=True)
        self.enabled = cfg.getboolean("client", "auto_connect")
        self.writer = None
        self.mismatch = ""  # warning while connected to a server with another version
        self.quality = False  # the server takes events with hit quality (from v0.6.8; older ones drop them)
        self.wake = asyncio.Event()

    async def run(self):
        self._pump_task = asyncio.create_task(self._pump())
        while True:
            self.wake.clear()
            if self.enabled:
                await self._connect()
            if not self.enabled:
                self.out({"type": "status", "text": "connection off – own ship only"})
                await self.wake.wait()
                continue
            try:
                await asyncio.wait_for(self.wake.wait(), 15)
            except TimeoutError:
                pass

    async def _connect(self):
        host, port = self.cfg["client"]["host"], self.cfg.getint("general", "port")
        self.out({"type": "status", "text": f"connecting to {host}:{port} …"})
        # the code holds the server's public address, which the own router often refuses: a server on this PC
        # is then found on localhost (the token makes sure it is the right one)
        for h in dict.fromkeys([host, "127.0.0.1"]):
            try:
                reader, writer = await asyncio.wait_for(asyncio.open_connection(h, port, limit=CLIENT_LIMIT), 10)
                host = h
                break
            except (OSError, TimeoutError, ValueError) as e:
                err = e
        else:
            self.out({"type": "status", "text": f"disconnected ({err or 'timeout'}) – retry in 15 s"})
            return
        writer.write(_line({"type": "hello", "token": self.cfg["general"]["token"], "version": VERSION}))
        writer.write(_line({"type": "history"}))
        self.fight.end()
        self.writer = writer
        self.out({"type": "reset"})
        self.out({"type": "status", "text": f"connected to {host}:{port}"})
        text = "disconnected – retry in 15 s"
        try:
            async for line in reader:
                msg = json.loads(line)
                kind = msg.get("type")
                if kind == "denied":
                    text = "token rejected – check the connection code in the settings"
                    break
                if kind == "version":
                    self.quality = _key(str(msg["version"])) >= (0, 6, 8)
                    if msg["version"] != VERSION:
                        self.mismatch = f"server runs v{msg['version']}, this is v{VERSION}"
                elif kind == "history":  # fetch the recent fights we do not have yet
                    have = set(list_history(self.history_dir))
                    since = (datetime.now(timezone.utc) - timedelta(days=SYNC_DAYS)).strftime("%Y%m%d_%H%M%S")
                    for name in msg["sessions"]:
                        if HISTORY_NAME.fullmatch(str(name)) and name not in have and name >= since:
                            writer.write(_line({"type": "load", "name": name}))
                elif kind == "session":
                    if HISTORY_NAME.fullmatch(str(msg.get("name"))) and msg["ticks"]:
                        save_history(self.history_dir, msg["name"], msg["ticks"])
                else:
                    if kind == "reset":  # the server just stored a fight
                        writer.write(_line({"type": "history"}))
                    self.out(msg)
        except (OSError, ValueError, TypeError, KeyError):
            pass
        finally:
            self.writer = None
            self.mismatch = ""
            self.quality = False
            writer.close()
        self.out({"type": "reset"})
        self.out({"type": "status", "text": text})

    async def _pump(self):
        """Every tick: read new log lines, then send them or show them locally."""
        while True:
            await asyncio.sleep(TICK)
            char = self.char
            events = await asyncio.to_thread(self.watcher.poll, self.cfg["client"]["log_dir"], char)
            self.out({"type": "warning", "text": _warning(char, self.watcher) or self.mismatch})
            if self.writer:
                sent = events if self.quality else [e[:8] for e in events]  # without hit quality for older servers
                self.writer.write(_line({"type": "events", "listeners": [char] if char else [], "events": sent}))
                continue
            now = time.time()
            self.fight.listeners = {char}
            self.fight.friendly_fire = friendly_fire(self.cfg)
            self.fight.add(events)
            if tick := self.fight.tick(now):
                self.out({"type": "tick", **tick, "idle_end": idle_end(self.cfg)})
            else:
                self.out({"type": "bursts", "bursts": self.fight.active_bursts(now)})
            if self.fight.ended(now, idle_end(self.cfg)):
                self.fight.end()
                self.out({"type": "reset"})

    async def history(self):
        names = list_history(self.history_dir)
        self.out({"type": "history", "sessions": names, "secs": history_secs(self.history_dir, names)})

    async def load(self, name):
        self.out({"type": "session", "ticks": load_history(self.history_dir, name)})

    async def set_enabled(self, on):
        self.enabled = on
        if not on and self.writer:
            self.writer.close()
        self.wake.set()

    async def stop(self):
        """Its tab or window is closed: store a fight of its own, stop reading the logs and leave the server."""
        if task := getattr(self, "_pump_task", None):
            task.cancel()
        if self.writer:
            self.writer.close()
        else:
            self.fight.end()

    async def reset(self):
        """End the local fight now (clicking the countdown); while connected only the server may do that."""
        if not self.writer:
            self.fight.end()
            self.out({"type": "reset"})

    async def set_char(self, char):
        self.char = char
        if not self.writer:
            self.fight.end()
            self.out({"type": "reset"})
