# eos-fight-mon

Live view of the current EVE Online fight. Clients read their gamelogs, the server merges all clients.

- **Left**: the ships of all connected clients. **Right**: everyone else. Drone damage counts for the drone's owner; drones whose owner the log does not name are grouped on the right.
- Arrows for damage, remote reps (shield/armor/hull/cap), neut/nos and scram/point/jam (dashed), as per-second rates over the last 10 s.
- Cockpit on top: fight clock and the team's incoming/outgoing sums, per second and for the whole fight.
- The server works in 2 s ticks and alone decides what a fight is: it starts with the first event and ends after 60 s without one (`idle_end`, adjustable in *Settings*) (or when *Reset* is pressed on the server; clients have no reset). Clients fetch every stored fight of the last 7 days automatically; *Replays* (newest first) plays them with start/stop and a slider.
- Without a server connection a client shows only its own ship on the left and its enemies on the right; ships that only rep it are hidden (their reps still count in the cockpit). Nothing is stored then.
- Friendly fire is not shown: hostile effects between clients and ships that rep with them are dropped.
- Layout is made for teams of about 10.
- Runs at below-normal priority and only reads the gamelogs (no access to the game), about 5 ms of work every 2 s.

## Start

Put `eos-fight-mon.exe` in a folder and double-click it. `config.ini` is created next to it on first start.

| Start | Use |
|---|---|
| `eos-fight-mon.exe` | client: reads logs, sends them to the server, shows the merged fight |
| `eos-fight-mon.exe --server` | server with window (e.g. on one player's Windows PC) |
| `eos-fight-mon --headless` | server without window (e.g. Linux server) |

Every client instance belongs to exactly one character (dropdown top left, filled from the gamelogs of the last day). For several accounts start several instances, e.g. via shortcuts with `eos-fight-mon.exe --char "Name"`.

The *Connection* button turns the connection and its retry every 15 s on and off.

**Connecting:** the server shows a connection code `address:port/token` with a *Copy* button (the headless server prints it). Paste it into *Server address* in the client's *Settings* and save.

The address in the code is the server's public internet address, asked from api.ipify.org on start. If the server has a fixed name (e.g. DynDNS), put it in `public_address` in `config.ini`; then nothing is asked. For clients to reach the server from outside:

- the TCP port (default 47110) must be open in the server's firewall (Windows asks on first start, allow it),
- on a home connection the router must forward that port to the server PC,
- on a rented Linux server the provider's firewall must allow it.

The connection is not encrypted; the token keeps strangers out, but anyone who can read the traffic could read fight data and the token.

The tool only reads the gamelogs and only writes next to itself (`config.ini`, `history/`).

## config.ini

```ini
[general]
# client or server
mode = client
port = 47110
# created on first start; the server's token must be in every client
token = …
history_dir = history
# seconds without an event that end a fight (5-3600)
idle_end = 60
# server only: address clients use, e.g. a DynDNS name; empty = ask api.ipify.org
public_address =

[client]
# address of the server
host = localhost
log_dir = ~/Documents/EVE/logs/Gamelogs
auto_connect = yes
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

Build (Windows `.exe`; for Linux the same without `--windowed`, on a Linux machine):

```bash
python -m PyInstaller --onefile --windowed --name eos-fight-mon main.py
```
