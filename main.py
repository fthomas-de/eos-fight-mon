"""eos-fight-mon: live EVE fight display. Clients read their gamelogs, the server merges all clients."""
import argparse
import asyncio
import configparser
import hashlib
import os
import queue
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import logparse
import net
import snap
import update

BASE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
DEFAULTS = {
    "general": {"port": "47110", "token": "", "history_dir": "history", "public_address": "", "idle_end": "60",
                "always_on_top": "no", "graph_on_top": "no", "friendly_fire": "no",
                "graph_live_minutes": "5", "graph_replay_minutes": "10"},
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


def restart(cfg_path, geometry):
    """Start a fresh copy; it opens the tabs this one stored on closing."""
    cmd = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, str(Path(__file__).resolve())]
    cmd += ["--config", str(cfg_path), "--geometry", geometry, "--restart"]
    # a one-file build must unpack itself anew instead of reusing this instance's folder, which goes away
    subprocess.Popen(cmd, env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"})


_lock = []  # the open lock file; the OS frees the lock when the process ends, also after a crash


def single_instance(cfg_path, wait):
    """Lock this config file for the life of the process. None if we got it, else the holder's process id
    (0 if unknown). Waits up to `wait` seconds, so a restart can let its old copy go first."""
    key = str(cfg_path).lower() if sys.platform == "win32" else str(cfg_path)
    fh = open(Path(tempfile.gettempdir()) / f"eos-fight-mon-{hashlib.sha1(key.encode()).hexdigest()[:12]}.lock", "a+")
    end = time.time() + wait
    while True:
        try:
            if sys.platform == "win32":
                import msvcrt
                fh.seek(1000)  # lock a byte past the process id, so others can still read it
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            if time.time() >= end:
                os.lseek(fh.fileno(), 0, 0)
                pid = os.read(fh.fileno(), 20).decode(errors="ignore").strip()  # unbuffered: never touch byte 1000
                fh.close()
                return int(pid) if pid.isdigit() else 0
            time.sleep(0.2)
    fh.seek(0)
    fh.truncate()
    fh.write(str(os.getpid()))
    fh.flush()
    _lock.append(fh)
    return None


def printer():
    """Headless server output: connections, and start and end of each fight."""
    fight = {}  # start and last active tick of the running fight (the idle tail before its end is not stored)

    def out(msg):
        kind, clock = msg.get("type"), time.strftime("%H:%M:%S")
        if kind == "clients":
            names = [f"{', '.join(chars) or 'no character'} ({', '.join(filter(None, (addr, ver)))})"
                     for addr, chars, ver in msg["list"]]
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
    ap.add_argument("--server", action="store_true", help="open the server tab too")
    ap.add_argument("--headless", action="store_true", help="server without window (e.g. Linux)")
    ap.add_argument("--reset", action="store_true", help="end the running fight of the server on this machine")
    ap.add_argument("--geometry", help="window size and place, WxH+X+Y or \"zoomed WxH+X+Y\" (kept on restart)")
    ap.add_argument("--char", help="open only this character's tab (default: the tabs open at the last close)")
    ap.add_argument("--version", action="version", version=f"eos-fight-mon {update.VERSION}")
    ap.add_argument("--config", default=str(BASE / "config.ini"), help="path to config.ini")
    ap.add_argument("--restart", action="store_true", help=argparse.SUPPRESS)  # wait for the old copy to end
    args = ap.parse_args()
    cfg_path = Path(args.config).resolve()
    os.chdir(BASE)  # relative paths in the config (history) live next to the program
    if not args.headless and not args.reset:  # one window per config: a second start shows the running one
        if (other := single_instance(cfg_path, 15 if args.restart else 2)) is not None:
            snap.focus(other)
            print(f"eos-fight-mon already runs with {cfg_path}", flush=True)
            return
    update.cleanup()
    cfg = load_config(cfg_path)
    if args.reset:
        print(asyncio.run(net.send_reset(cfg)), flush=True)
        return
    lower_priority()

    if args.headless:
        code = f"{net.public_address(cfg)}:{cfg['general']['port']}/{cfg['general']['token']}"
        print(f"eos-fight-mon v{update.VERSION} server running. Connection code for clients: {code}", flush=True)
        if cfg.getboolean("update", "check"):
            def check():  # CCP may need several handshakes: do not hold up the server start
                try:
                    found = update.latest()
                    print(f"{time.strftime('%H:%M:%S')} " + (
                        f"{found[0]} is available: https://github.com/{update.REPO}/releases/latest" if found
                        else f"v{update.VERSION} is the newest version"), flush=True)
                except (OSError, ValueError, KeyError):
                    pass
                try:
                    print(f"{time.strftime('%H:%M:%S')} {update.sde_status()}", flush=True)
                except (OSError, ValueError, KeyError):
                    pass
            threading.Thread(target=check, daemon=True).start()
        server = net.Server(cfg, printer())

        def stop(*_):  # Ctrl+C or kill: store the running fight, then exit without waiting for the clients
            server.fight.end()
            server.out({"type": "reset"})
            print(f"{time.strftime('%H:%M:%S')} server stopped", flush=True)
            os._exit(0)
        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
        asyncio.run(server.run())
        return

    loop = asyncio.new_event_loop()  # one loop runs the server and the clients of all tabs
    threading.Thread(target=loop.run_forever, daemon=True).start()

    def make(mode, char, out):
        return net.Server(cfg, out) if mode == "server" else net.Client(cfg, logparse.LogWatcher(), out, char)

    from ui import App, start_tabs  # only here, so a headless Linux server needs no Tk
    App(start_tabs(cfg, cfg_path, args.char, args.server), make, loop, queue.Queue(), cfg, cfg_path,
        lambda geo: restart(cfg_path, geo), args.geometry).root.mainloop()


if __name__ == "__main__":
    main()
