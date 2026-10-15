# Handover

State on 2026-10-15 (evening). Read this, `README.md` and `PLAN.md` before continuing.

## Where things stand

- Latest release: **v0.6.7** (https://github.com/fthomas-de/eos-fight-mon/releases/tag/v0.6.7, 2026-10-15), Windows exe + Linux binary + SHA256SUMS, checksums verified after re-download (Linux asset via WSL curl, Windows download was reset again), Linux smoke test passed. `main` is pushed; nothing uncommitted.
- v0.6.7 brought:
  - Tabs: `ui.App` = main window, tab bar (`_tabbar`: tab buttons, ×/middle click, *+ Client*, *+ Server*, *Settings*, *Reset size*), window places, settings, update; `ui.Tab` = one backend with bar, canvas, footer, replays, cockpit/graph windows (`_layout_key` per character as before). Main window place under `[windows] main` (falls back to the old per-character key), open tabs under `tabs = :server|Name|…` and `tab` (index). `start_tabs`: `--char` alone, else the saved tabs, minus those `snap.open_tabs()` finds in other windows; `--server` adds the server tab. Restart (`main.restart(cfg_path, geometry)`) reopens the saved tabs; *Settings › Mode* is gone. One asyncio loop for all backends (`loop.run_forever`), queue items are `(tab id, msg)`, `None` = window-wide. Closing a tab: `backend.stop()` (server stores the fight, frees the port, drops clients; client stops the pump and its connection), then the task is cancelled; tested with real `Server`/`Client`.
  - Graph shows the last `graph_live_minutes` (5) / `graph_replay_minutes` (10) only; hover lists the log events (flows) of that tick (`_events_box`). Main window: *Fight ends in m:ss* in place of the enemies while nothing is active; the server sends `idle_end` with each tick (old servers: the client's own setting).
  - One window per config file (`main.single_instance`): lock file `%TEMP%\eos-fight-mon-<sha1 of config path>.lock` (msvcrt byte lock at offset 1000 / fcntl on Linux; holds the PID, read unbuffered), a second start waits 2 s, then `snap.focus(pid)` raises the running main window and exits. `--restart` (hidden, passed by `main.restart`) waits 15 s for the old copy. Not for `--headless`/`--reset`. Tested with processes on Windows and in WSL; the focus itself not seen live. Versions before 0.6.7 take no lock.
  - Button icons: BMP symbols from Segoe UI Symbol (checked with GetGlyphIndicesW), Tk falls back to that font.
  - Only tested on invisible windows; nothing of v0.6.7 seen live (tabs, icons, single window, countdown, graph hover).
- v0.6.6 brought: settings/replays dialog on the right monitor. Two causes, both reproduced with invisible windows: `root.geometry()` of a maximized window gives its *normal* place, which stays on the old monitor when the maximized window is moved (Win+Shift+Arrow or drag); and an open dialog was only `deiconify`'d at its old place when reopened. `_place_dialog` uses `winfo_rootx/rooty` (dialog 50 px into the client area, ~30 px lower than before) and runs on the reuse paths too. Both monitors are 96 DPI, DPI is not involved. User's setup: DISPLAY1 primary 2560×1440 at 0,0; DISPLAY2 1920×1080 at -1920,608. Not yet confirmed live.
- **Release clean-up accident (2026-10-14):** `rm -rf dist/release-0.6.4` deleted the user's *running* v0.6.4 (started from that folder; Windows let the PyInstaller exe be deleted) together with the `config.ini` and `history\` it kept there. Not recoverable from here (no admin for shadow copies). The release skill now checks process paths and never deletes folders with a running exe, `config.ini` or `history\`. The user was told to start `dist\eos-fight-mon.exe` (v0.6.5) next time; if that instance was the server, it has a new token and the clients need the new code.
- v0.6.5 brought:
  - Headless server: Ctrl+C / SIGTERM (`pkill`) store the running fight, print its end line and `server stopped`, exit 0 (`main.stop`, `os._exit` because Python 3.12's `Server.wait_closed` waits for connected clients and would hang). Tested under WSL with a connected client for both signals; Windows Ctrl+C not tried. README step 5 now uses `pkill` alone; `upgrade_linux.sh` keeps `--reset` for servers older than 0.6.5.
  - Drones come from the SDE: `tools/build_icons.py` also writes `drones.py` (`DRONE_TYPES`, categories 18 drones + 87 fighters, 248 names), `fight.is_drone` is an exact match; `_DRONE_WORDS` is gone. Drones in space are logged as `<b>Name</b> <font>Type</font>` (both the same), `logparse.party` now folds that `X X` to `X` (`_DOUBLED`). On all 2249 local gamelogs old and new detection agree (25 drone names).
  - Linux build packs `ship_icons.json` now (before, the Linux client with window had no ship icons); `build_linux.sh` stops if the file is missing in the archive (`pyi-archive_viewer -l`).
  - `python tools/build_icons.py --check`: SDE build of `ship_icons.json` vs. CCP's `latest.jsonl`, exit 1 if outdated; the release skill runs it instead of asking. On 2026-10-14 both were 3607705.
  - Start check (`[update] check`): `App._check_online` 5 s after start puts one status line "v0.6.x is the newest · SDE 3607705 is current" (or "vX available", "SDE … outdated (CCP: …)"); it also replaces the old automatic update check at 3 s and still offers a newer release when `can_install()`. `update.sde_status()` compares `drones.SDE_BUILD` with CCP's `latest.jsonl` (3 tries). Headless prints both lines from a thread, so the start does not wait. Unreachable GitHub/CCP: that part is left out.
  - Version handshake: the client sends `version` in its hello, the server answers `{"type": "version"}` (old clients ignore it, old servers ignore the field). Client: `Client.mismatch` is shown in the red warning while connected. Server: `connections()` has a third element, the client's version when it differs ("version before 0.6.5" for clients without the field), shown in the client list of the window and the headless log. Tested with a real `Server` and raw clients and a real `Client` against a fake server; windows not seen live.
- v0.6.4 brought:
  - Main-window legend: *Scram/Point* (orange) and *Jam* (cyan `#05c3dd`, own arrow lane `OFFSET` 15) are separate entries; hiding one hides its graph row / cockpit row too.
  - Replay list shows each fight's length (`fight.history_secs`, cached per file and mtime; sent as `secs` in the local `history` message only, the server→client sync message stays names-only).
  - Graph: rows *Scram/Point (active)* and *Jam (active)* (`EWAR_ROWS`) = number of active ewar effects (`_ewar`: scram/point seen in the last 10 s, a jam for 20 s because it is logged once per ECM cycle; gaps between jams in the logs are 20 s; main-window arrows use the same), out/in by team side (`series`); default graph size 460x460, min 320x310. Cockpit has a *Jams* row (`JAM_ROW`): active now in the /s columns, Σ = number of jams in the fight; default cockpit size 340x144, min 280x140. Cockpit/Graph buttons are filled with the accent colour while their window is open (`_mark_panels`); Replays is one window per instance, placed like Settings (`_dialog`).
  - **Client languages**: all eight (en de fr es ru ja ko zh) are parsed by markup, not words: colour = kind and direction (dmg `0xff00ffff` out / `0xffcc0000` in, neut/nos `0xff7fffff` out / `0xffe57f7f` in, reps `0xffccff66` both ways, warp/jam white or dim), `<b>` = amount and names, `<localized hint="English">shown*` gives English ship/module names (so icons, drones and rep kind need no translations). Words are left only for rep direction (`_RECEIVED`), scram vs point (`_SCRAM`/`_POINT`) and "you" (`_YOU`). Checked against 650k English lines (same result as the old regex parser except own jams, `-0` cap, wrecks) and against both sides of the test fights in every language (`tests/languages.tsv`). Jam: incoming has the word and the jammer in separate bold parts, an own jam one bold part with target and word (es/ru put the word in front, `_jam`); Chinese turns the sentence around, so colour says nothing there. Switching the language in a running client keeps the old header and writes no hints (seen with Chinese in an English file): those rep lines are lost until the client restarts. The Japanese client sometimes writes unfilled templates (`{defender}`), skipped.
- **The v0.6.3 release commit `1de9b42` carries the wrong subject "Handover: v0.6.2 released"** (a stale `.git/CLAUDE_COMMIT_MSG` was used; the Write of the new message failed and the commit ran in parallel). Content and tag are right; left as is because fixing needs a force push. Lesson: write the message file, check it, then commit — never in the same parallel batch.
- v0.6.3 brought: legend click hides/shows an arrow kind (`draw(..., off)`, `LEGEND_OF`, `App._off`, `_legend_at` by position because each hover redraw replaces the canvas items; hidden entry grey + struck out; per window, not stored; numbers in the boxes unaffected; since v0.6.4 the cockpit and graph rows of a hidden entry are left out too), headless server prints fight start/end with clock (`main.printer`, duration without the idle tail), `tools/upgrade_linux.sh` (latest release, SHA256 check, `--reset`, `pkill -f "eos-fight-mon --headless"`, `mv`, restart with nohup only if it ran; assumes a nohup start, not systemd), README *Quick start* (Windows client/server, Linux client/server, headless; download one-liners via the GitHub API) and the note that the Linux binary includes Tk (runs with window under WSLg; tested live by the user).
- Damage "not syncing" on the user's Linux server (212.227.135.47) was friendly fire: both test chars are clients, so their damage on each other is dropped (`friendly_fire = no`, the server's setting counts). Server itself works.
- v0.6.2 brought: window places per character (`_restore_layout`, `_layout_key`, closed panels stored as `off WxH+X+Y`), docking (`snap.py`, Windows only, DWM frames, 15 px), one instance per character (`snap.char_open`), *Reset size* / ⟲, *Graph always on top* (`graph_on_top`), mode per start (plain = client, `--server` = server, never stored), *Paste code* in the client bar, connection footer, app icon (`APP_ICON` in `ui.py`, `icon.ico` for the exe), readable same-side arrows (cubic `smooth="raw"` bow, depth per kind `LANE` + 15 px for upward arrows, bigger arrowheads) and arrow hover (`_arrow_hover` → `draw(..., hover)`, box "Damage  A → B  1.5k/s").
- Things learned in v0.6.2 worth keeping:
  - Character-switch places: the small windows were moved and then put back within 1 s by a focus/raise race while the combobox closes. Fix: `update_idletasks()` after `geometry()` plus the same geometry again after 300 ms. Invisible (alpha-0) test windows never get focus, so only a debug log in a test build on the user's PC showed it.
  - The connection code holds the server's public address; the user's router refuses it from inside (no hairpin NAT). `Client._connect` falls back to 127.0.0.1 (token guards against a different local server). User confirmed it works. A server on another PC in the same LAN still needs its LAN IP in *Settings*; whether the router forwards 47110 for internet clients is unknown.
  - EVE never writes the own ship into the own gamelog, so a client's ship (icon/type on the left) is only known when another client's log names it in the same fight. **User decided: show only confirmed info, do not remember ships across fights.**
- Offered, not done: The Linux client's Proton log path in the README (`compatdata/8500/...`) is unverified.
- Not yet confirmed live by the user: everything of v0.6.5 (version warning and client list note, start status line, headless stop with a real fight, Linux icons in a window), everything of v0.6.4 (other languages in a real fight, cyan jam arrows, graph/cockpit ewar rows, replay length), the legend toggle, fight start/end lines on a real server, the new arrows and hover, docking feel, connection footer, char-switch places (debug log said fixed).
- The user's `dist\config.ini` may still hold leftover identical places from the old bug; placing the windows once per character fixes them.
- `dist\` holds `eos-fight-mon.exe` and `eos-fight-mon-linux` (v0.6.7), `release-0.6.7\`, `config.ini`, `history\`, and `release-0.6.5\` (kept: the user ran v0.6.5 from there, it holds its own `config.ini` and `history\`; `release-0.6.4\` is gone). WSL test copy of the Linux binary with its own config: `~/efm-test/`. For test builds use `--name eos-fight-mon-<version>-testN`, never overwrite an exe that runs (`tasklist | grep eos-fight`), delete `build\` and the `.spec` afterwards.
- Releases: the repo's own `/release` skill (`.claude/skills/release/SKILL.md`, committed since 2026-10-14; it guards the commit subject and cleans up `dist\` after a verified release). Not `/commit` or `/push` (those are for Alliance Auth apps). Do not ask about releasing, never run `/release` unasked. From Git Bash, `wsl.exe ... /mnt/c/...` gets its path mangled: run the Linux build from PowerShell.
- unit tests green: `python -m unittest discover -s tests`
- Python 3.13, standard library only. Build-time tools: PyInstaller (Windows), WSL Ubuntu + `uv` (Linux).

## Files

| File | Job |
|---|---|
| `logparse.py` | gamelog line → `Event`; `LogWatcher` tails one character's logs; `characters()` lists characters from log headers (any language); reads all eight client languages by markup |
| `drones.py` | generated by `tools/build_icons.py`: every drone and fighter type name |
| `fight.py` | 2 s ticks, dedupe between clients, friendly fire filter, solo view (`hidden`), drones, idle end, replay files (`history/*.jsonl.gz`) |
| `net.py` | TCP, one JSON per line, token check, server/client, replay sync (last 7 days), `--reset` (localhost only), public address via api.ipify.org |
| `ui.py` | tkinter canvas, small windows (`PANELS`: cockpit, graph), cockpit/graph always on top (`always_on_top`, `graph_on_top`), server connection list, update dialog, themes, replay bar, settings (restart on mode/port/host/token; mode is per start, never stored: plain start = client, `--server` = server), window geometry per character in `[windows]` of config.ini (`_restore_layout`, `_save_window`, closed panels `off WxH+X+Y`), *Reset size* / ⟲, client *Paste code*, docking hook (`_on_move` → `_snap`), arrow hover (`_arrow_hover`), ship icons |
| `main.py` | CLI (`--server`, `--headless`, `--reset`, `--char`, `--geometry`, `--config`, `--version`), config defaults, restart |
| `snap.py` | Windows docking: other instances' window rectangles via ctypes, `snap_offset` |
| `update.py` | `VERSION`, GitHub release check, download + SHA256 check + exe swap, cleanup of `*.old` |
| `tools/build_icons.py` | SDE → `ship_icons.json` (424 ships, 32 px icons, base64) and `drones.py` |
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

- One exe, modes client / server / headless. **Since 2026-10-15 (user's wish): one window with tabs**, one tab per character plus an optional server tab; cockpit and graph stay separate windows *per tab* (user chose that over one pair following the active tab). One character / one server per process and across windows (`snap.open_tabs` reads the other main windows' titles).
- Server alone decides fights (idle end, default 60 s, adjustable); only the server can reset (button or `--reset` from localhost).
- Left = clients, right = enemies; drone damage counts for the owner; friendly fire hidden; without server: own ship + enemies only, friends hidden, nothing stored.
- English UI and docs. Reply to the user in German.
- **TLS: rejected as overkill.** Connection stays plain TCP with token.
- Connection code `address:port/token` instead of a browser link (no registry changes). Tool touches only gamelogs and its own files.
- Ship icons packed into the exe, 32 px.

## Open

- Never tested live: docking (feel, other instances, multi-monitor), ⟲ button looks in the small cockpit (may touch the column header), char-switch places, windows of one instance raising together on click (v0.6.1, `_raise_group`), the cockpit and graph windows (looks, hover) and always on top over a running EVE, a maximized window reopening on a second monitor, a real self-update v0.5.0 → next version, a client connecting over the internet, a real 10-man fight, the v0.4.0 Windows exe started by hand (icons only checked on an invisible canvas and in the archive), clicking through the settings dialog, the Linux binary on an old distribution.
- No systemd unit for the headless server (user did not ask).

- Self-update (since v0.5.0): v0.4.0 and older have no updater, users must take v0.5.0 by hand once. Windows renames the running exe to `<exe>.<old version>.old` and deletes it on a later start. `[update] installed` tells sibling windows to only restart, `[update] skip` stops the start-up question for one version.

## Gotchas

- **Do not open visible windows for tests** while the user plays: they pop up in front of EVE, get closed from outside and screenshots come out black. Test UI on a withdrawn root with a Canvas subclass that fakes `winfo_width/height`.
- `dist\eos-fight-mon.exe` may be running (user's instance): rename it before rebuilding, never kill it.
- Git Bash heredocs mangle `\r`/`\n` escapes in inline Python; use the Edit tool or write scripts to files.
- Downloads of the release exes from Windows here sometimes get reset (WinError 10054, also `gh release download`); WSL `curl` works. On 2026-10-13 it cleared after a few minutes. The updater then shows "update failed" and *Check for updates* retries; a retry loop in `update.install` would be the fix if users hit it.
- `curl` fails TLS to CCP servers here; Python works but CCP drops ~half of the handshakes (build_icons retries 8×).
- PowerShell 5.1 `Set-Content -Encoding utf8` writes a BOM; config is read with `utf-8-sig`.
- Older gamelogs write names as `Name [CORP]<ALLY>'1'(Ship)` (label before ship); both orders are parsed.
- Logs without a character (start time on header line 3) are empty character-select logs. The listener is header line 3 in every language (`Listener:`, `Auditeur:`, `Empfänger:`, `收听者:` …).
