"""TCP, one JSON message per line. Clients send events every tick, the server answers with merged ticks."""
import asyncio
import hmac
import json
import time

from fight import TICK, Fight, list_history, load_history, to_event

CLIENT_LIMIT = 64 * 2**20  # a whole fight comes back in one line for replay
SERVER_LIMIT = 2**20


def _line(msg):
    return json.dumps(msg, separators=(",", ":")).encode() + b"\n"


class Server:
    def __init__(self, cfg, out):
        self.cfg, self.out = cfg, out  # out(msg) feeds the local window
        self.fight = Fight(cfg["general"]["history_dir"])
        self.clients = {}  # writer -> characters of that client

    async def run(self):
        srv = await asyncio.start_server(self._handle, port=self.cfg.getint("general", "port"), limit=SERVER_LIMIT)
        self.out({"type": "status", "text": f"Server läuft auf Port {self.cfg['general']['port']}"})
        async with srv:
            while True:
                await asyncio.sleep(TICK)
                now = time.time()
                self.fight.listeners = set().union(*self.clients.values())
                if tick := self.fight.tick(now):
                    self._broadcast({"type": "tick", **tick})
                if self.fight.ended(now):
                    await self.reset()

    async def reset(self):
        self.fight.end()
        self._broadcast({"type": "reset"})

    async def history(self):
        self.out({"type": "history", "sessions": list_history(self.fight.history_dir)})

    async def load(self, name):
        self.out({"type": "session", "ticks": load_history(self.fight.history_dir, name)})

    async def set_enabled(self, on):
        pass

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
            self.clients[writer] = set()
            async for line in reader:
                msg = json.loads(line)
                kind = msg.get("type")
                if kind == "events":
                    self.clients[writer] = {n for n in msg["listeners"][:50] if isinstance(n, str)}
                    self.fight.add(e for e in map(to_event, msg["events"]) if e)
                elif kind == "reset":
                    await self.reset()
                elif kind == "history":
                    writer.write(_line({"type": "history", "sessions": list_history(self.fight.history_dir)}))
                elif kind == "load":
                    ticks = load_history(self.fight.history_dir, str(msg.get("name")))
                    writer.write(_line({"type": "session", "ticks": ticks}))
        except (OSError, ValueError, TypeError, KeyError, AttributeError, TimeoutError):
            pass  # broken or hostile client: just drop it
        finally:
            self.clients.pop(writer, None)
            writer.close()


class Client:
    def __init__(self, cfg, watcher, out):
        self.cfg, self.watcher, self.out = cfg, watcher, out
        self.fight = Fight(cfg["general"]["history_dir"])  # used while not connected
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
                self.out({"type": "status", "text": "Verbindung aus – nur eigene Charaktere"})
                await self.wake.wait()
                continue
            try:
                await asyncio.wait_for(self.wake.wait(), 15)
            except TimeoutError:
                pass

    async def _connect(self):
        host, port = self.cfg["client"]["host"], self.cfg.getint("general", "port")
        self.out({"type": "status", "text": f"verbinde mit {host}:{port} …"})
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port, limit=CLIENT_LIMIT), 10)
        except (OSError, TimeoutError, ValueError) as e:
            self.out({"type": "status", "text": f"getrennt ({e or 'Zeitüberschreitung'}) – neuer Versuch in 15 s"})
            return
        writer.write(_line({"type": "hello", "token": self.cfg["general"]["token"]}))
        self.fight.end()
        self.writer = writer
        self.out({"type": "reset"})
        self.out({"type": "status", "text": f"verbunden mit {host}:{port}"})
        text = "getrennt – neuer Versuch in 15 s"
        try:
            async for line in reader:
                msg = json.loads(line)
                if msg.get("type") == "denied":
                    text = "Token abgelehnt – Token in den Einstellungen prüfen"
                    break
                self.out(msg)
        except (OSError, ValueError):
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
            events = await asyncio.to_thread(self.watcher.poll, self.cfg["client"]["log_dir"])
            if self.writer:
                self.writer.write(_line({"type": "events", "listeners": sorted(self.watcher.listeners),
                                         "events": events}))
                continue
            now = time.time()
            self.fight.listeners = self.watcher.listeners
            self.fight.add(events)
            if tick := self.fight.tick(now):
                self.out({"type": "tick", **tick})
            if self.fight.ended(now):
                await self.reset()

    async def reset(self):
        if self.writer:
            self.writer.write(_line({"type": "reset"}))
        else:
            self.fight.end()
            self.out({"type": "reset"})

    async def history(self):
        if self.writer:
            self.writer.write(_line({"type": "history"}))
        else:
            self.out({"type": "history", "sessions": list_history(self.fight.history_dir)})

    async def load(self, name):
        if self.writer:
            self.writer.write(_line({"type": "load", "name": name}))
        else:
            self.out({"type": "session", "ticks": load_history(self.fight.history_dir, name)})

    async def set_enabled(self, on):
        self.enabled = on
        if not on and self.writer:
            self.writer.close()
        self.wake.set()
