# Handover

State on 2026-10-14 (afternoon). Read this, `README.md` and `PLAN.md` before continuing.

## Where things stand

- Latest release: **v0.6.1** (https://github.com/fthomas-de/eos-fight-mon/releases/tag/v0.6.1), Windows exe + Linux binary + SHA256SUMS. `main` is pushed up to v0.6.1.
- **v0.6.2 is done but NOT committed** (working tree; `VERSION` already 0.6.2, Windows exe built in `dist\eos-fight-mon.exe` from the current tree, no Linux build yet). Contents:
  - Windows of one instance raise together: `bind_all("<FocusIn>")` → `_on_focus` (a click often focuses a child like the combobox, so the old `e.widget is root` filter missed it).
  - Settings checkboxes are `ttk.Checkbutton` (style `Dark.TCheckbutton`, native vista box) — `tk.Checkbutton` drew the tick unreadable.
  - Mode is per start, never stored: plain start = client, `--server` = server, *Settings › Mode* restarts this window with/without `--server`; `load_config` drops an old `mode` key. Servers that relied on `mode = server` now need `--server` (mention in release notes).
  - New option *Graph always on top* (`[general] graph_on_top`), separate from the cockpit's `always_on_top`.
  - Cockpit/graph places fixed: they were loaded under the start character (`chars[0]`), so a client switched to another character got the wrong places; picking a character now moves main, cockpit and graph to that character's saved places (`_restore_layout`, reads config.ini fresh). Before switching, the places are saved under the character being left (`_layout_key`); without that, all characters ended up with the places of whichever character was active at close. A closed panel is stored as `off WxH+X+Y` and reopens there (before: plain `off`, place lost).
  - *Reset size* in the main bar, ⟲ (placed top right) in cockpit and graph: back to `MAIN_SIZE` / the `PANELS` size, place kept.
  - Docking on release (`snap.py`, Windows only): after a move (not a resize) and 250 ms quiet with the left mouse button up, `snap.offset` lists all visible `TkTopLevel` windows titled `eos-fight-mon – `/`Cockpit – `/`Graph – ` (any instance), takes their DWM visible frames (no invisible 7 px border) plus the monitor work area, and moves the window if an edge is < 15 px away (`snap_offset`, unit tested). Checked with alpha-0 windows. Not handled: DPI scaling other than 100 % (DWM bounds are physical pixels), moving a docked group together (user did not ask).
  - Client bar has *Paste code*: reads `host:port/token` from the clipboard, writes host/port/token, restarts (`_paste_code`). Before, the code could only go into *Settings › Server address*.
  - Character switch places (long story, user reported it broken 5×): `_set_char` saves under the character being left (`_layout_key`), then `_restore_layout` moves main, cockpit and graph. Real Windows bug found via a debug log: the small windows were moved and then put back within 1 s (focus/raise race while the combobox closes; invisible test windows never get focus, so tests never showed it). Fix: `update_idletasks()` after `geometry()` plus the same geometry once more after 300 ms. **The test9 log confirms it** (1 s later the panels stay put); the user has not said it explicitly.
  - One instance per character: picking a character another instance already shows is refused with a status message (`snap.char_open` → `snap.title_taken`, finds a `TkTopLevel` titled `eos-fight-mon – Client – <char>`, minimized too; Linux always allows), and a new start takes the first character not open elsewhere (`main.py`). Reason: two instances of one character stacked their panels and overwrote each other's places.
  - The temporary layout debug log (`App._dbg`) is removed again, with `import os` in `ui.py`.
  - Same-side arrows (e.g. a client hitting/repping another client) were an unreadable knot: now a cubic bow (`smooth="raw"`, leaves and enters level), depth per kind (`LANE`) plus 15 px more for upward arrows, wider `OFFSET` spread, bigger arrowheads (`arrowshape` scales with width). Hovering an arrow in the main window (`_arrow_hover` → `draw(..., hover)`) thickens it and shows a box "Damage  A → B  1.5k/s" (all arrows within 4 px, ewar without a rate). User has not confirmed the arrows/hover live yet.
  - Paste code did not connect when server and client run on the same PC: the code holds the public address (77.21.88.121) and the user's router refuses connections to it from inside (no hairpin NAT; tested: refused, 127.0.0.1 works). `Client._connect` now falls back to 127.0.0.1 when the code's host fails (token check guards against a different local server). A server on another PC in the same LAN is still not reachable via the public address (would need the LAN IP typed in Settings). Also unknown whether the router forwards 47110 for internet clients at all. **User confirmed: connection works now.**
  - Own ship sometimes missing on the left (no icon/type): EVE never writes the own ship into the own gamelog (checked the user's logs, not even in notify lines), so a client's ship is only known when another client's log names it in this fight. **User decided: show only confirmed info, do not remember ships across fights** (tried and reverted). Left as is.
  - Connection messages (status, warning, server's client list) moved from the top bar into a footer at the very bottom of the main window (user confirmed nothing yet).
  - Settings dialog opens with its top left corner 50 px right/down from the main window's corner (`root.geometry()` corner + 50; user wanted that, not centred). **OPEN BUG: the user reports it opens on the wrong monitor.** Their setup: DISPLAY1 primary 2560×1440 at 0,0; DISPLAY2 1920×1080 at -1920,608; the main window usually sits on DISPLAY2 (e.g. `+-1399+817`), possibly maximized (`zoomed`). Not investigated yet. Suspects: `root.geometry()` of a zoomed window, Tk/Windows ignoring the position of a transient Toplevel before it is mapped (try setting it after `update_idletasks()`, or after mapping with `after_idle`), or the reuse path (`_settings_top` exists → only `deiconify`, no new place). Invisible tests (alpha-0) put it right on both monitors, so check with the user's real case.
  - The user's `dist\config.ini` still has some leftover identical places from the old bug; they fix them by placing the windows once per character.
  - App icon (red skull, from the user, confirmed live): `APP_ICON` in `ui.py` (32 px PNG as base64, `root.iconphoto(True, …)` for all windows and the taskbar) and `icon.ico` (16–48 px) for the exe via `--icon icon.ico` (build commands in README, here and the release skill updated). Linux binary has no file icon, only the window icon.
  - New files `snap.py`, `tests/test_snap.py` and `icon.ico` are untracked and belong to v0.6.2 (the release skill asks about unknown untracked files: these go in). `.claude/` holds the release skill itself.
- **Next step:** fix the settings dialog monitor bug, then the user releases v0.6.2 with the repo's own `/release` skill (`.claude/skills/release`: tests, commit, tag, push, both builds, GitHub release, handover). Not `/commit` or `/push` (those are for Alliance Auth apps). Do not ask about releasing, never run `/release` unasked.
- `dist\` was cleaned up on 2026-10-14 (user asked): only `eos-fight-mon.exe` (current tree), `config.ini` and `history\` are left; old prev/test exes, old release folders (all on GitHub), debug logs, `build\` and the spec file are gone. For new test builds use `--name eos-fight-mon-0.6.2-testN` (copies, numbering can restart at 1), never overwrite an exe that runs (`tasklist | grep eos-fight`), delete `build\` and the `.spec` afterwards.
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
