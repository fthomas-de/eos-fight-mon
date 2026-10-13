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
from pathlib import Path

import logparse
import net

BASE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
DEFAULTS = {
    "general": {"mode": "client", "port": "47110", "token": "", "history_dir": "history",
                "public_address": "", "idle_end": "60"},
    "client": {"host": "localhost", "log_dir": "~/Documents/EVE/logs/Gamelogs", "auto_connect": "yes"},
}


def load_config(path):
    """Read the config, fill in missing keys and write it back so it is always complete."""
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read_dict(DEFAULTS)
    cfg.read(path, encoding="utf-8-sig")  # tolerate the BOM some Windows editors write
    if not cfg["general"]["token"]:
        cfg["general"]["token"] = secrets.token_urlsafe(16)  # copy the server's token to every client
    with open(path, "w", encoding="utf-8") as fh:
        cfg.write(fh)
    return cfg


def restart(cfg_path, char, geometry):
    """Start a fresh copy; the config's mode decides now, so --server is not passed on."""
    cmd = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, str(Path(__file__).resolve())]
    cmd += ["--config", str(cfg_path), "--geometry", geometry] + (["--char", char] if char else [])
    # a one-file build must unpack itself anew instead of reusing this instance's folder, which goes away
    subprocess.Popen(cmd, env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"})


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
    ap.add_argument("--geometry", help="window size and place, WxH+X+Y or zoomed (kept on restart)")
    ap.add_argument("--char", help="character of this instance (default: most recently active)")
    ap.add_argument("--config", default=str(BASE / "config.ini"), help="path to config.ini")
    args = ap.parse_args()
    cfg_path = Path(args.config).resolve()
    os.chdir(BASE)  # relative paths in the config (history) live next to the program
    cfg = load_config(cfg_path)
    if args.reset:
        print(asyncio.run(net.send_reset(cfg)), flush=True)
        return
    mode = "server" if args.server or args.headless or cfg["general"]["mode"] == "server" else "client"
    lower_priority()

    # only the server asks for its public address
    code = mode == "server" and f"{net.public_address(cfg)}:{cfg['general']['port']}/{cfg['general']['token']}"

    if args.headless:
        print(f"eos-fight-mon server running. Connection code for clients: {code}", flush=True)
        asyncio.run(net.Server(cfg, lambda msg: None).run())
        return

    q = queue.Queue()
    if mode == "server":
        backend = net.Server(cfg, q.put)
    else:
        chars = logparse.characters(cfg["client"]["log_dir"])
        backend = net.Client(cfg, logparse.LogWatcher(), q.put, args.char or (chars[0] if chars else None))
    loop = asyncio.new_event_loop()

    def run():
        try:
            loop.run_until_complete(backend.run())
        except Exception as e:  # e.g. port already in use: show it instead of dying silently
            q.put({"type": "status", "text": f"error: {e}"})
    threading.Thread(target=run, daemon=True).start()

    from ui import App  # only here, so a headless Linux server needs no Tk
    App(mode, backend, loop, q, cfg, cfg_path, code, lambda char, geo: restart(cfg_path, char, geo),
        args.geometry).root.mainloop()


if __name__ == "__main__":
    main()
