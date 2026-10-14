"""eos-fight-mon: live EVE fight display. Clients read their gamelogs, the server merges all clients."""
import argparse
import asyncio
import configparser
import os
import queue
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path

import logparse
import net
import update

BASE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
DEFAULTS = {
    "general": {"port": "47110", "token": "", "history_dir": "history", "public_address": "", "idle_end": "60",
                "always_on_top": "no", "graph_on_top": "no", "friendly_fire": "no"},
    "client": {"host": "localhost", "log_dir": "~/Documents/EVE/logs/Gamelogs", "auto_connect": "yes"},
    "update": {"check": "yes"},
}


def load_config(path):
    """Read the config, fill in missing keys and write it back so it is always complete."""
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read_dict(DEFAULTS)
    cfg.read(path, encoding="utf-8-sig")  # tolerate the BOM some Windows editors write
    cfg.remove_option("general", "mode")  # old configs: the mode is per start (--server), not shared
    if not cfg["general"]["token"]:
        cfg["general"]["token"] = secrets.token_urlsafe(16)  # copy the server's token to every client
    with open(path, "w", encoding="utf-8") as fh:
        cfg.write(fh)
    return cfg


def restart(cfg_path, char, geometry, mode):
    """Start a fresh copy in the given mode."""
    cmd = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, str(Path(__file__).resolve())]
    cmd += ["--config", str(cfg_path), "--geometry", geometry] + (["--char", char] if char else [])
    cmd += ["--server"] if mode == "server" else []
    # a one-file build must unpack itself anew instead of reusing this instance's folder, which goes away
    subprocess.Popen(cmd, env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"})


def printer():
    """Headless server output: connections, and start and end of each fight."""
    fight = {}  # start and last active tick of the running fight (the idle tail before its end is not stored)

    def out(msg):
        kind, clock = msg.get("type"), time.strftime("%H:%M:%S")
        if kind == "clients":
            names = [f"{', '.join(chars) or 'no character'} ({addr})" for addr, chars in msg["list"]]
            print(f"{clock} {len(names)} connected: {'; '.join(names) or '-'}", flush=True)
        elif kind == "tick":
            if not fight:
                print(f"{clock} fight started", flush=True)
                fight.update(start=msg["start"], t=msg["t"])
            if msg["flows"]:
                fight["t"] = msg["t"]
        elif kind == "reset" and fight:  # idle end, or --reset
            secs = int(fight["t"] - fight["start"]) + 2
            print(f"{clock} fight ended after {secs // 60}:{secs % 60:02d} min, stored", flush=True)
            fight.clear()
    return out


def lower_priority():
    """The game always wins the CPU."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        k = ctypes.windll.kernel32
        k.SetPriorityClass.argtypes = (wintypes.HANDLE, wintypes.DWORD)  # untyped, the 64-bit handle gets mangled
        k.SetPriorityClass(wintypes.HANDLE(-1), 0x4000)  # own process, BELOW_NORMAL_PRIORITY_CLASS
    else:
        os.nice(5)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--server", action="store_true", help="run as server")
    ap.add_argument("--headless", action="store_true", help="server without window (e.g. Linux)")
    ap.add_argument("--reset", action="store_true", help="end the running fight of the server on this machine")
    ap.add_argument("--geometry", help="window size and place, WxH+X+Y or \"zoomed WxH+X+Y\" (kept on restart)")
    ap.add_argument("--char", help="character of this instance (default: most recently active)")
    ap.add_argument("--version", action="version", version=f"eos-fight-mon {update.VERSION}")
    ap.add_argument("--config", default=str(BASE / "config.ini"), help="path to config.ini")
    args = ap.parse_args()
    cfg_path = Path(args.config).resolve()
    os.chdir(BASE)  # relative paths in the config (history) live next to the program
    update.cleanup()
    cfg = load_config(cfg_path)
    if args.reset:
        print(asyncio.run(net.send_reset(cfg)), flush=True)
        return
    mode = "server" if args.server or args.headless else "client"  # a plain start is always a client
    lower_priority()

    # only the server asks for its public address
    code = mode == "server" and f"{net.public_address(cfg)}:{cfg['general']['port']}/{cfg['general']['token']}"

    if args.headless:
        print(f"eos-fight-mon server running. Connection code for clients: {code}", flush=True)
        if cfg.getboolean("update", "check"):
            try:
                if found := update.latest():
                    print(f"{found[0]} is available: https://github.com/{update.REPO}/releases/latest", flush=True)
            except (OSError, ValueError, KeyError):
                pass
        asyncio.run(net.Server(cfg, printer()).run())
        return

    q = queue.Queue()
    if mode == "server":
        backend = net.Server(cfg, q.put)
    else:
        import snap
        chars = logparse.characters(cfg["client"]["log_dir"])
        free = [c for c in chars if not snap.char_open(c)]  # one instance per character: skip those already open
        backend = net.Client(cfg, logparse.LogWatcher(), q.put, args.char or next(iter(free + chars), None))
    loop = asyncio.new_event_loop()

    def run():
        try:
            loop.run_until_complete(backend.run())
        except Exception as e:  # e.g. port already in use: show it instead of dying silently
            q.put({"type": "status", "text": f"error: {e}"})
    threading.Thread(target=run, daemon=True).start()

    from ui import App  # only here, so a headless Linux server needs no Tk
    App(mode, backend, loop, q, cfg, cfg_path, code, lambda char, geo, mode: restart(cfg_path, char, geo, mode),
        args.geometry).root.mainloop()


if __name__ == "__main__":
    main()
