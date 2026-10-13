# Handover

State on 2026-10-13. Read this, `README.md` and `PLAN.md` before continuing.

## Where things stand

- Latest release: **v0.5.0** (https://github.com/fthomas-de/eos-fight-mon/releases/tag/v0.5.0), Windows exe + Linux binary + SHA256SUMS. `main` is pushed.
- unit tests green: `python -m unittest discover -s tests`
- Python 3.13, standard library only. Build-time tools: PyInstaller (Windows), WSL Ubuntu + `uv` (Linux).

## Files

| File | Job |
|---|---|
| `logparse.py` | gamelog line → `Event`; `LogWatcher` tails one character's logs; `characters()` lists characters from log headers; spots logs in another language |
| `fight.py` | 2 s ticks, dedupe between clients, friendly fire filter, solo view (`hidden`), drones, idle end, replay files (`history/*.jsonl.gz`) |
| `net.py` | TCP, one JSON per line, token check, server/client, replay sync (last 7 days), `--reset` (localhost only), public address via api.ipify.org |
| `ui.py` | tkinter canvas, separate cockpit window, always on top, update dialog, themes, replay bar, settings (restart on mode/port/host/token), window geometry per character in `[windows]` of config.ini, ship icons |
| `main.py` | CLI (`--server`, `--headless`, `--reset`, `--char`, `--geometry`, `--config`, `--version`), config defaults, restart |
| `update.py` | `VERSION`, GitHub release check, download + SHA256 check + exe swap, cleanup of `*.old` |
| `tools/build_icons.py` | SDE → `ship_icons.json` (424 ships, 32 px icons, base64) |
| `tools/build_linux.sh` | Linux build with portable Python (glibc 2.17+) plus smoke test |

## Build and release

```bash
python tools/build_icons.py
```
(only when new ships came out; downloads ~100 MB SDE)

```bash
python -m PyInstaller --onefile --windowed --name eos-fight-mon --add-data "ship_icons.json;." main.py
```

```bash
wsl.exe -d Ubuntu -- bash /mnt/c/Users/floth/Documents/eos-fight-mon/tools/build_linux.sh
```

Before building: bump `VERSION` in `update.py`. The self-update finds the asset by its suffix `-windows-x64.exe` / `-linux-x86_64` and needs `SHA256SUMS.txt` (format `hash *name`) in the release, so keep those names.

Release: copy both binaries renamed `eos-fight-mon-vX.Y.Z-windows-x64.exe` / `-linux-x86_64` into a folder, write `SHA256SUMS.txt` and `RELEASE_NOTES.md` (previous notes: `gh release view v0.5.0`), tag, push, then
`"C:\Program Files\GitHub CLI\gh.exe" release create vX.Y.Z --repo fthomas-de/eos-fight-mon --title ... --notes-file ... <files>`
and re-download to compare checksums. `gh` is logged in as `fthomas-de` but not on PATH in older terminals.

## Decisions taken with the user (do not reopen)

- One exe, modes client / server / headless; one instance = one character.
- Server alone decides fights (idle end, default 60 s, adjustable); only the server can reset (button or `--reset` from localhost).
- Left = clients, right = enemies; drone damage counts for the owner; friendly fire hidden; without server: own ship + enemies only, friends hidden, nothing stored.
- English UI and docs. Reply to the user in German.
- **TLS: rejected as overkill.** Connection stays plain TCP with token.
- Connection code `address:port/token` instead of a browser link (no registry changes). Tool touches only gamelogs and its own files.
- Ship icons packed into the exe, 32 px.

## Open

- **Other EVE client languages**: only English logs are parsed; the client warns otherwise. Needs real sample gamelogs per language (damage both ways, remote reps given/received, neut/nos, scram/point/jam). The SDE has ship names in all languages (`name.de`, `name.ru`, …), useful for icons/ship names then.
- Never tested: the cockpit window and always on top over a running EVE, a real self-update v0.5.0 → next version, a client connecting over the internet, a real 10-man fight, the v0.4.0 Windows exe started by hand (icons only checked on an invisible canvas and in the archive), clicking through the settings dialog, the Linux binary on an old distribution.
- No systemd unit for the headless server (user did not ask).
- Possible: show the drone-name list gaps (`fight._DRONE_WORDS`) when new drones appear.

- Self-update (since v0.5.0): v0.4.0 and older have no updater, users must take v0.5.0 by hand once. Windows renames the running exe to `<exe>.<old version>.old` and deletes it on a later start. `[update] installed` tells sibling windows to only restart, `[update] skip` stops the start-up question for one version.

## Gotchas

- **Do not open visible windows for tests** while the user plays: they pop up in front of EVE, get closed from outside and screenshots come out black. Test UI on a withdrawn root with a Canvas subclass that fakes `winfo_width/height`.
- `dist\eos-fight-mon.exe` may be running (user's instance): rename it before rebuilding, never kill it.
- Git Bash heredocs mangle `\r`/`\n` escapes in inline Python; use the Edit tool or write scripts to files.
- Downloads of the release exes from Windows here sometimes get reset (WinError 10054, also `gh release download`); WSL `curl` works. On 2026-10-13 it cleared after a few minutes. The updater then shows "update failed" and *Check for updates* retries; a retry loop in `update.install` would be the fix if users hit it.
- `curl` fails TLS to CCP servers here; Python works but CCP drops ~half of the handshakes (build_icons retries 8×).
- PowerShell 5.1 `Set-Content -Encoding utf8` writes a BOM; config is read with `utf-8-sig`.
- Older gamelogs write names as `Name [CORP]<ALLY>'1'(Ship)` (label before ship); both orders are parsed.
- Logs without `Listener:` are empty character-select logs, not other languages.
