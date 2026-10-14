# Handover

State on 2026-10-14 (afternoon). Read this, `README.md` and `PLAN.md` before continuing.

## Where things stand

- Latest release: **v0.6.2** (https://github.com/fthomas-de/eos-fight-mon/releases/tag/v0.6.2, 2026-10-14), Windows exe + Linux binary + SHA256SUMS, checksums verified after re-download. `main` is pushed up to v0.6.2; nothing of substance uncommitted (`tests/test_fight.py` may show as modified from line endings only, `git diff` is empty).
- v0.6.2 brought: window places per character (`_restore_layout`, `_layout_key`, closed panels stored as `off WxH+X+Y`), docking (`snap.py`, Windows only, DWM frames, 15 px), one instance per character (`snap.char_open`), *Reset size* / ⟲, *Graph always on top* (`graph_on_top`), mode per start (plain = client, `--server` = server, never stored), *Paste code* in the client bar, connection footer, app icon (`APP_ICON` in `ui.py`, `icon.ico` for the exe), readable same-side arrows (cubic `smooth="raw"` bow, depth per kind `LANE` + 15 px for upward arrows, bigger arrowheads) and arrow hover (`_arrow_hover` → `draw(..., hover)`, box "Damage  A → B  1.5k/s").
- Things learned in v0.6.2 worth keeping:
  - Character-switch places: the small windows were moved and then put back within 1 s by a focus/raise race while the combobox closes. Fix: `update_idletasks()` after `geometry()` plus the same geometry again after 300 ms. Invisible (alpha-0) test windows never get focus, so only a debug log in a test build on the user's PC showed it.
  - The connection code holds the server's public address; the user's router refuses it from inside (no hairpin NAT). `Client._connect` falls back to 127.0.0.1 (token guards against a different local server). User confirmed it works. A server on another PC in the same LAN still needs its LAN IP in *Settings*; whether the router forwards 47110 for internet clients is unknown.
  - EVE never writes the own ship into the own gamelog, so a client's ship (icon/type on the left) is only known when another client's log names it in the same fight. **User decided: show only confirmed info, do not remember ships across fights.**
- **Open bug:** the settings dialog opens on the wrong monitor (released with it). It is placed at the main window's corner + 50 px (user wants that, not centred). User's setup: DISPLAY1 primary 2560×1440 at 0,0; DISPLAY2 1920×1080 at -1920,608; main window usually on DISPLAY2 (e.g. `+-1399+817`), possibly `zoomed`. Suspects: `root.geometry()` of a zoomed window, Tk/Windows ignoring the position of a transient Toplevel before it is mapped (set it after `update_idletasks()` or with `after_idle` after mapping), or the reuse path (`_settings_top` exists → only `deiconify`). Invisible tests put it right on both monitors; a test build with a small debug log on the user's PC is the way to find it.
- After v0.6.2 (uncommitted): clicking a legend entry (colour or name) hides/shows those arrows (`draw(..., off)`, `LEGEND_OF`, `App._off`, `_legend_at` by position because each hover redraw replaces the items; hidden entry grey + struck out; per window, not stored). README: Linux binary includes Tk; *Quick start* with five copy-paste setups (download one-liners via the GitHub API tested). Headless server prints fight start/end with clock (`main.printer`, duration without the idle tail). `tools/upgrade_linux.sh` for the headless server (latest release, SHA256 check, `--reset`, pkill, `mv`, restart only if it ran), tested in WSL incl. the restart path; the README fetches it from raw.githubusercontent `main`, so it works only once pushed.
- Not yet confirmed live by the user: the legend toggle, the new arrows and hover, docking feel, connection footer, char-switch places (debug log said fixed).
- The user's `dist\config.ini` may still hold leftover identical places from the old bug; placing the windows once per character fixes them.
- `dist\` holds `eos-fight-mon.exe` (v0.6.2), `eos-fight-mon-0.6.2-prev.exe` (same code, renamed by the release), `eos-fight-mon-linux`, `release-0.6.2\`, `config.ini`, `history\`. For test builds use `--name eos-fight-mon-<version>-testN`, never overwrite an exe that runs (`tasklist | grep eos-fight`), delete `build\` and the `.spec` afterwards.
- Releases: the repo's own `/release` skill (`.claude/skills/release`, untracked on purpose). Not `/commit` or `/push` (those are for Alliance Auth apps). Do not ask about releasing, never run `/release` unasked. From Git Bash, `wsl.exe ... /mnt/c/...` gets its path mangled: run the Linux build from PowerShell.
- unit tests green: `python -m unittest discover -s tests`
- Python 3.13, standard library only. Build-time tools: PyInstaller (Windows), WSL Ubuntu + `uv` (Linux).

## Files

| File | Job |
|---|---|
| `logparse.py` | gamelog line → `Event`; `LogWatcher` tails one character's logs; `characters()` lists characters from log headers; spots logs in another language |
| `fight.py` | 2 s ticks, dedupe between clients, friendly fire filter, solo view (`hidden`), drones, idle end, replay files (`history/*.jsonl.gz`) |
| `net.py` | TCP, one JSON per line, token check, server/client, replay sync (last 7 days), `--reset` (localhost only), public address via api.ipify.org |
| `ui.py` | tkinter canvas, small windows (`PANELS`: cockpit, graph), cockpit/graph always on top (`always_on_top`, `graph_on_top`), server connection list, update dialog, themes, replay bar, settings (restart on mode/port/host/token; mode is per start, never stored: plain start = client, `--server` = server), window geometry per character in `[windows]` of config.ini (`_restore_layout`, `_save_window`, closed panels `off WxH+X+Y`), *Reset size* / ⟲, client *Paste code*, docking hook (`_on_move` → `_snap`), arrow hover (`_arrow_hover`), ship icons |
| `main.py` | CLI (`--server`, `--headless`, `--reset`, `--char`, `--geometry`, `--config`, `--version`), config defaults, restart |
| `snap.py` | Windows docking: other instances' window rectangles via ctypes, `snap_offset` |
| `update.py` | `VERSION`, GitHub release check, download + SHA256 check + exe swap, cleanup of `*.old` |
| `tools/build_icons.py` | SDE → `ship_icons.json` (424 ships, 32 px icons, base64) |
| `tools/build_linux.sh` | Linux build with portable Python (glibc 2.17+) plus smoke test |

## Build and release

```bash
python tools/build_icons.py
```
(only when new ships came out; downloads ~100 MB SDE)

```bash
python -m PyInstaller --onefile --windowed --name eos-fight-mon --icon icon.ico --add-data "ship_icons.json;." main.py
```

```bash
wsl.exe -d Ubuntu -- bash /mnt/c/Users/floth/Documents/eos-fight-mon/tools/build_linux.sh
```

Before building: bump `VERSION` in `update.py`. The self-update finds the asset by its suffix `-windows-x64.exe` / `-linux-x86_64` and needs `SHA256SUMS.txt` (format `hash *name`) in the release, so keep those names.

Release: copy both binaries renamed `eos-fight-mon-vX.Y.Z-windows-x64.exe` / `-linux-x86_64` into a folder, write `SHA256SUMS.txt` and `RELEASE_NOTES.md` (previous notes: `gh release view v0.6.1`), tag, push, then
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
- Never tested live: docking (feel, other instances, multi-monitor), ⟲ button looks in the small cockpit (may touch the column header), char-switch places, windows of one instance raising together on click (v0.6.1, `_raise_group`), the cockpit and graph windows (looks, hover) and always on top over a running EVE, a maximized window reopening on a second monitor, a real self-update v0.5.0 → next version, a client connecting over the internet, a real 10-man fight, the v0.4.0 Windows exe started by hand (icons only checked on an invisible canvas and in the archive), clicking through the settings dialog, the Linux binary on an old distribution.
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
