# Handover

State on 2026-10-14 (afternoon). Read this, `README.md` and `PLAN.md` before continuing.

## Where things stand

- Latest release: **v0.6.3** (https://github.com/fthomas-de/eos-fight-mon/releases/tag/v0.6.3, 2026-10-14), Windows exe + Linux binary + SHA256SUMS, checksums verified after re-download; README step 6 (raw `upgrade_linux.sh` on a v0.6.2 binary → 0.6.3) verified end to end. `main` is pushed; nothing of substance uncommitted (`tests/test_fight.py` may show as modified from line endings only, `git diff` is empty).
- **The v0.6.3 release commit `1de9b42` carries the wrong subject "Handover: v0.6.2 released"** (a stale `.git/CLAUDE_COMMIT_MSG` was used; the Write of the new message failed and the commit ran in parallel). Content and tag are right; left as is because fixing needs a force push. Lesson: write the message file, check it, then commit — never in the same parallel batch.
- v0.6.3 brought: legend click hides/shows an arrow kind (`draw(..., off)`, `LEGEND_OF`, `App._off`, `_legend_at` by position because each hover redraw replaces the canvas items; hidden entry grey + struck out; per window, not stored; numbers in the boxes unaffected; since after v0.6.3 the cockpit rows and graph rows of a hidden entry are left out too (`off` passed to `draw_cockpit`/`draw_graph`)), headless server prints fight start/end with clock (`main.printer`, duration without the idle tail), `tools/upgrade_linux.sh` (latest release, SHA256 check, `--reset`, `pkill -f "eos-fight-mon --headless"`, `mv`, restart with nohup only if it ran; assumes a nohup start, not systemd), README *Quick start* (Windows client/server, Linux client/server, headless; download one-liners via the GitHub API) and the note that the Linux binary includes Tk (runs with window under WSLg; tested live by the user).
- Damage "not syncing" on the user's Linux server (212.227.135.47) was friendly fire: both test chars are clients, so their damage on each other is dropped (`friendly_fire = no`, the server's setting counts). Server itself works.
- v0.6.2 brought: window places per character (`_restore_layout`, `_layout_key`, closed panels stored as `off WxH+X+Y`), docking (`snap.py`, Windows only, DWM frames, 15 px), one instance per character (`snap.char_open`), *Reset size* / ⟲, *Graph always on top* (`graph_on_top`), mode per start (plain = client, `--server` = server, never stored), *Paste code* in the client bar, connection footer, app icon (`APP_ICON` in `ui.py`, `icon.ico` for the exe), readable same-side arrows (cubic `smooth="raw"` bow, depth per kind `LANE` + 15 px for upward arrows, bigger arrowheads) and arrow hover (`_arrow_hover` → `draw(..., hover)`, box "Damage  A → B  1.5k/s").
- Things learned in v0.6.2 worth keeping:
  - Character-switch places: the small windows were moved and then put back within 1 s by a focus/raise race while the combobox closes. Fix: `update_idletasks()` after `geometry()` plus the same geometry again after 300 ms. Invisible (alpha-0) test windows never get focus, so only a debug log in a test build on the user's PC showed it.
  - The connection code holds the server's public address; the user's router refuses it from inside (no hairpin NAT). `Client._connect` falls back to 127.0.0.1 (token guards against a different local server). User confirmed it works. A server on another PC in the same LAN still needs its LAN IP in *Settings*; whether the router forwards 47110 for internet clients is unknown.
  - EVE never writes the own ship into the own gamelog, so a client's ship (icon/type on the left) is only known when another client's log names it in the same fight. **User decided: show only confirmed info, do not remember ships across fights.**
- **Open bug:** the settings dialog opens on the wrong monitor (released with it). It is placed at the main window's corner + 50 px (user wants that, not centred). User's setup: DISPLAY1 primary 2560×1440 at 0,0; DISPLAY2 1920×1080 at -1920,608; main window usually on DISPLAY2 (e.g. `+-1399+817`), possibly `zoomed`. Suspects: `root.geometry()` of a zoomed window, Tk/Windows ignoring the position of a transient Toplevel before it is mapped (set it after `update_idletasks()` or with `after_idle` after mapping), or the reuse path (`_settings_top` exists → only `deiconify`). Invisible tests put it right on both monitors; a test build with a small debug log on the user's PC is the way to find it.
- Offered, not done: Ctrl+C / SIGTERM on the headless server should store the running fight and exit without a traceback (today the fight is lost; README says `--reset` first). The Linux client's Proton log path in the README (`compatdata/8500/...`) is unverified.
- Not yet confirmed live by the user: the legend toggle, fight start/end lines on a real server, the new arrows and hover, docking feel, connection footer, char-switch places (debug log said fixed).
- The user's `dist\config.ini` may still hold leftover identical places from the old bug; placing the windows once per character fixes them.
- `dist\` holds `eos-fight-mon.exe` (v0.6.3), `eos-fight-mon-linux`, `release-0.6.3\`, `config.ini`, `history\` (cleaned up). WSL test copy of the Linux binary with its own config: `~/efm-test/`. For test builds use `--name eos-fight-mon-<version>-testN`, never overwrite an exe that runs (`tasklist | grep eos-fight`), delete `build\` and the `.spec` afterwards.
- Releases: the repo's own `/release` skill (`.claude/skills/release/SKILL.md`, committed since 2026-10-14; it guards the commit subject and cleans up `dist\` after a verified release). Not `/commit` or `/push` (those are for Alliance Auth apps). Do not ask about releasing, never run `/release` unasked. From Git Bash, `wsl.exe ... /mnt/c/...` gets its path mangled: run the Linux build from PowerShell.
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

- Main-window legend (after v0.6.3): *Scram/Point* (orange) and *Jam* (cyan `#05c3dd`, own arrow lane `OFFSET` 15) are separate entries; hiding one hides its graph row / cockpit row too.
- Replay list (after v0.6.3) shows each fight's length (`fight.history_secs`, cached per file and mtime; sent as `secs` in the local `history` message only, the server→client sync message stays names-only).
- Graph (after v0.6.3): rows *Scram/Point (active)* and *Jam (active)* (`EWAR_ROWS`) = number of active ewar effects (`_ewar`: scram/point seen in the last 10 s, a jam for 20 s because it is logged once per ECM cycle; gaps between jams in the logs are 20 s; main-window arrows use the same), out/in by team side (`EWAR_ROW`, `series`); default graph size 460x460, min 320x310. Cockpit has a *Jams* row (`JAM_ROW`): active now in the /s columns, Σ = number of jams in the fight; default cockpit size 340x144, min 280x140. Cockpit/Graph buttons are filled with the accent colour while their window is open (`_mark_panels`); Replays is one window per instance, placed like Settings (`_dialog`).
- **Client languages** (since after v0.6.3): all eight (en de fr es ru ja ko zh) are parsed by markup, not words: colour = kind and direction (dmg `0xff00ffff` out / `0xffcc0000` in, neut/nos `0xff7fffff` out / `0xffe57f7f` in, reps `0xffccff66` both ways, warp/jam white or dim), `<b>` = amount and names, `<localized hint="English">shown*` gives English ship/module names (so icons, drones and rep kind need no translations). Words are left only for rep direction (`_RECEIVED`), scram vs point (`_SCRAM`/`_POINT`) and "you" (`_YOU`). Checked against 650k English lines (same result as the old regex parser except own jams, `-0` cap, wrecks) and against both sides of the test fights in every language (`tests/languages.tsv`). Jam: incoming has the word and the jammer in separate bold parts, an own jam one bold part with target and word (es/ru put the word in front, `_jam`); Chinese turns the sentence around, so colour says nothing there. Switching the language in a running client keeps the old header and writes no hints (seen with Chinese in an English file): those rep lines are lost until the client restarts. The Japanese client sometimes writes unfilled templates (`{defender}`), skipped.
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
- Logs without a character (start time on header line 3) are empty character-select logs. The listener is header line 3 in every language (`Listener:`, `Auditeur:`, `Empfänger:`, `收听者:` …).
