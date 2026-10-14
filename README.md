# eos-fight-mon

Live view of the current EVE Online fight. Clients read their gamelogs, the server merges all clients.

- **Left**: the ships of all connected clients. **Right**: everyone else. Drone damage counts for the drone's owner; drones whose owner the log does not name are grouped on the right.
- Arrows for damage, remote reps (shield/armor/hull/cap), neut/nos and scram/point/jam (dashed), as per-second rates over the last 10 s.
- Cockpit: a small separate window with the fight clock and the team's incoming/outgoing sums, per second and for the whole fight. The *Cockpit* button opens and closes it; it stays when the main window is minimized and remembers its place per character, also while closed and when the character is picked after start.
- Graph: a third small window with one chart per group (damage, reps, cap, neut/nos), the team's out (solid) and in (dashed) per second over the fight; move the mouse over it to read the values at that moment. The *Graph* button opens and closes it.
- *Cockpit always on top* and *Graph always on top* in *Settings* keep those windows above the game. That works with EVE in window or fixed window mode, not in exclusive fullscreen.
- Windows reopen on the monitor and at the place they were closed, also when closed maximized or minimized. *Reset size* (main window) and the small ⟲ in the cockpit and graph windows bring a window back to its original size.
- Docking (Windows): a window let go within 15 px of another eos-fight-mon window (also of other characters) or a screen edge lines up with it.
- The server window lists every connected client with the character it picked and its address (the headless server prints the list when it changes).
- Updates: on start the exe asks GitHub for a newer release and offers to install it. *Yes* downloads it, checks it against `SHA256SUMS.txt`, replaces the exe and restarts; *No* skips that version (*Settings › Check for updates* asks anyway). Other open windows then offer a restart only. Can be turned off (`[update] check`).
- The server works in 2 s ticks and alone decides what a fight is: it starts with the first event and ends after 60 s without one (`idle_end`, adjustable in *Settings*) (or on *Reset* in the server window / `--reset` on the server machine; clients cannot reset). Clients fetch every stored fight of the last 7 days automatically; *Replays* (newest first) plays them with start/stop and a slider.
- Without a server connection a client shows only its own ship on the left and its enemies on the right; ships that only rep it are hidden (their reps still count in the cockpit). Nothing is stored then.
- Friendly fire (hostile effects between clients and ships that rep with them) is dropped unless *Show friendly fire* is on. With a server the server's setting counts for everyone.
- Ship icons (32 px) for every ship type, packed into the exe.
- Layout is made for teams of about 10.
- Runs at below-normal priority and only reads the gamelogs (no access to the game), about 5 ms of work every 2 s.

## Start

Put `eos-fight-mon.exe` in a folder and double-click it. `config.ini` is created next to it on first start.

| Start | Use |
|---|---|
| `eos-fight-mon.exe` | client (a plain start is always a client; *Settings › Mode* switches this window to server): reads logs, sends them to the server, shows the merged fight |
| `eos-fight-mon.exe --server` | server with window (e.g. on one player's Windows PC) |
| `eos-fight-mon --headless` | server without window (e.g. Linux server) |
| `eos-fight-mon --reset` | on the server machine: end the running fight (the headless server's reset button; only accepted from the same machine) |

Every client instance belongs to exactly one character (dropdown top left, filled from the gamelogs of the last day). For several accounts start several instances, e.g. via shortcuts with `eos-fight-mon.exe --char "Name"`.

The *Connection* button turns the connection and its retry every 15 s on and off.

**Connecting:** the server shows a connection code `address:port/token` with a *Copy* button (the headless server prints it). In the client, copy it and press *Paste code* (top bar): the client saves it and reconnects. Pasting it into *Server address* in the client's *Settings* works too.

The address in the code is the server's public internet address, asked from api.ipify.org on start. If the server has a fixed name (e.g. DynDNS), put it in `public_address` in `config.ini`; then nothing is asked. For clients to reach the server from outside:

- the TCP port (default 47110) must be open in the server's firewall (Windows asks on first start, allow it),
- on a home connection the router must forward that port to the server PC,
- on a rented Linux server the provider's firewall must allow it.

The connection is not encrypted; the token keeps strangers out, but anyone who can read the traffic could read fight data and the token.

The tool only reads the gamelogs and only writes next to itself (`config.ini`, `history/`, the exe on update). Network: the server connection, api.ipify.org (server, for its address) and api.github.com/github.com (update check).

## config.ini

```ini
[general]
port = 47110
# created on first start; the server's token must be in every client
token = …
history_dir = history
# seconds without an event that end a fight (5-3600)
idle_end = 60
# server only: address clients use, e.g. a DynDNS name; empty = ask api.ipify.org
public_address =
# keep the cockpit window above the game
always_on_top = no
# the same for the graph window
graph_on_top = no
# show damage/ewar between our own ships; on a client it only counts without a server
friendly_fire = no

[client]
# address of the server
host = localhost
log_dir = ~/Documents/EVE/logs/Gamelogs
auto_connect = yes

[update]
# ask GitHub for a newer version on start (the headless server only prints it)
check = yes
```

Everything can also be changed in the window under *Settings*. The server must be reachable on the port via TCP.

## Not in the log

Webs, damps, painters, tracking disruptors and fleet boosts are not written to the combat log and therefore not shown.

## Development

Python standard library only (3.11+).

```bash
python main.py
```

```bash
python -m unittest discover -s tests
```

Ship icons: `ship_icons.json` holds every published ship of the EVE SDE with its 32 px icon from CCP's image server. Rebuild it when new ships come out (downloads the SDE, about 100 MB):

```bash
python tools/build_icons.py
```

Windows build:

```bash
python -m PyInstaller --onefile --windowed --name eos-fight-mon --icon icon.ico --add-data "ship_icons.json;." main.py
```

Linux build (headless server only, no Tk). Built on Linux or WSL with a portable Python from `uv`, so the binary runs on any distribution with glibc 2.17 or newer; a distribution's own Python would tie it to that distribution's glibc:

```bash
bash tools/build_linux.sh
```

(sets up the portable Python in `~/efm-build` on first run, builds `dist/eos-fight-mon-linux` and smoke-tests it)

On the server: copy the binary, `chmod +x eos-fight-mon`, start `./eos-fight-mon --headless`; `./eos-fight-mon --reset` ends the running fight.

## Legal

EVE Online and all related ship images are the property of CCP hf. This tool is not affiliated with or endorsed by CCP.
