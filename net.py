"""TCP, one JSON message per line. Clients send events every tick, the server answers with merged ticks."""
import asyncio
import hmac
import ipaddress
import json
import socket
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from fight import HISTORY_NAME, IDLE_END, TICK, Fight, list_history, load_history, save_history, to_event

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

    async def run(self):
        srv = await asyncio.start_server(self._handle, port=self.cfg.getint("general", "port"), limit=SERVER_LIMIT)
        self.out({"type": "status", "text": "server running"})
        async with srv:
            while True:
                await asyncio.sleep(TICK)
                now = time.time()
                self.fight.listeners = set().union(*self.clients.values())
                if tick := self.fight.tick(now):
                    self._broadcast({"type": "tick", **tick})
                if self.fight.ended(now, idle_end(self.cfg)):
                    await self.reset()

    async def reset(self):
        self.fight.end()
        self._broadcast({"type": "reset"})  # clients then sync the stored fight

    async def history(self):
        self.out({"type": "history", "sessions": list_history(self.fight.history_dir)})

    async def load(self, name):
        self.out({"type": "session", "ticks": load_history(self.fight.history_dir, name)})

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
            for tick in self.fight.ticks:  # late joiners get the running fight from its start
                writer.write(_line({"type": "tick", **tick}))
            self.clients[writer] = set()
            async for line in reader:
                msg = json.loads(line)
                kind = msg.get("type")
                if kind == "events":
                    self.clients[writer] = {n for n in msg["listeners"][:50] if isinstance(n, str)}
                    self.fight.add(e for e in map(to_event, msg["events"]) if e)
                elif kind == "history":  # no "reset" here: only the server ends a fight early
                    writer.write(_line({"type": "history", "sessions": list_history(self.fight.history_dir)}))
                elif kind == "load":
                    name = str(msg.get("name"))
                    writer.write(_line({"type": "session", "name": name,
                                        "ticks": load_history(self.fight.history_dir, name)}))
        except (OSError, ValueError, TypeError, KeyError, AttributeError, TimeoutError):
            pass  # broken or hostile client: just drop it
        finally:
            self.clients.pop(writer, None)
            writer.close()


class Client:
    def __init__(self, cfg, watcher, out, char):
        self.cfg, self.watcher, self.out, self.char = cfg, watcher, out, char
        self.history_dir = cfg["general"]["history_dir"]  # replays synced from the server
        self.fight = Fight(solo=True)  # live view while not connected; the server alone decides what a fight is
        self.enabled = cfg.getboolean("client", "auto_connect")
        self.writer = None
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
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port, limit=CLIENT_LIMIT), 10)
        except (OSError, TimeoutError, ValueError) as e:
            self.out({"type": "status", "text": f"disconnected ({e or 'timeout'}) – retry in 15 s"})
            return
        writer.write(_line({"type": "hello", "token": self.cfg["general"]["token"]}))
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
                if kind == "history":  # fetch the recent fights we do not have yet
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
            writer.close()
        self.out({"type": "reset"})
        self.out({"type": "status", "text": text})

    async def _pump(self):
        """Every tick: read new log lines, then send them or show them locally."""
        while True:
            await asyncio.sleep(TICK)
            char = self.char
            events = await asyncio.to_thread(self.watcher.poll, self.cfg["client"]["log_dir"], char)
            if self.writer:
                self.writer.write(_line({"type": "events", "listeners": [char] if char else [], "events": events}))
                continue
            now = time.time()
            self.fight.listeners = {char}
            self.fight.add(events)
            if tick := self.fight.tick(now):
                self.out({"type": "tick", **tick})
            if self.fight.ended(now, idle_end(self.cfg)):
                self.fight.end()
                self.out({"type": "reset"})

    async def history(self):
        self.out({"type": "history", "sessions": list_history(self.history_dir)})

    async def load(self, name):
        self.out({"type": "session", "ticks": load_history(self.history_dir, name)})

    async def set_enabled(self, on):
        self.enabled = on
        if not on and self.writer:
            self.writer.close()
        self.wake.set()

    async def set_char(self, char):
        self.char = char
        if not self.writer:
            self.fight.end()
            self.out({"type": "reset"})
