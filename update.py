"""Self-update from the GitHub releases; installs only after the user agreed."""
import hashlib
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

VERSION = "0.6.0"
REPO = "fthomas-de/eos-fight-mon"
SUFFIX = "-windows-x64.exe" if sys.platform == "win32" else "-linux-x86_64"  # release asset of this platform


def can_install():
    """Only a built exe can swap itself; from source there is nothing to replace."""
    return getattr(sys, "frozen", False)


def _get(url, timeout=10):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": f"eos-fight-mon/{VERSION}"}),
                                  timeout=timeout)


def _key(tag):
    return tuple(int(n) for n in re.findall(r"\d+", tag))


def latest():
    """(tag, {asset name: url}) of the newest release if it is newer than this program, else None."""
    with _get(f"https://api.github.com/repos/{REPO}/releases/latest") as r:
        rel = json.load(r)
    tag = rel["tag_name"]
    if _key(tag) <= _key(VERSION):
        return None
    return tag, {a["name"]: a["browser_download_url"] for a in rel["assets"]}


def install(assets, exe=None):
    """Download this platform's binary, check it against SHA256SUMS.txt and put it in place of the running exe."""
    exe = Path(exe or sys.executable)
    name = next((n for n in assets if n.endswith(SUFFIX)), None)
    if not name or "SHA256SUMS.txt" not in assets:
        raise ValueError("release has no binary for this system")
    with _get(assets["SHA256SUMS.txt"]) as r:
        sums = {n.lstrip("*"): h.lower() for h, n in (line.split(maxsplit=1) for line in r.read().decode().splitlines()
                                                    if line.strip())}
    new, digest = exe.with_name(exe.name + ".new"), hashlib.sha256()
    try:
        with _get(assets[name], timeout=60) as r, open(new, "wb") as fh:
            while chunk := r.read(1 << 16):
                digest.update(chunk)
                fh.write(chunk)
        if digest.hexdigest() != sums.get(name):
            raise ValueError("checksum does not match SHA256SUMS.txt")
        if sys.platform == "win32":
            # a running exe cannot be overwritten but can be renamed; the next start deletes it
            old = exe.with_name(f"{exe.name}.{VERSION}.old")
            os.replace(exe, old)
            try:
                os.replace(new, exe)
            except OSError:
                os.replace(old, exe)
                raise
        else:
            new.chmod(0o755)
            os.replace(new, exe)
    finally:
        new.unlink(missing_ok=True)


def cleanup():
    """Delete exes replaced by an update; one still running in another window stays until next time."""
    if can_install():
        exe = Path(sys.executable)
        for old in exe.parent.glob(exe.name + ".*.old"):
            try:
                old.unlink()
            except OSError:
                pass
