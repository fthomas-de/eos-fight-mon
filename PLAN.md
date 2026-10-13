# Plan

## Goal

Live view of the current EVE fight without affecting game performance. One executable plus `config.ini`.

## Layout

| File | Job |
|---|---|
| `logparse.py` | gamelog line → event; `LogWatcher` tails the logs of one character |
| `fight.py` | 2 s ticks, dedupe between clients, solo view, fight end, replays |
| `net.py` | TCP, one JSON message per line, token, reconnect every 15 s, replay sync |
| `ui.py` | tkinter canvas, cockpit, client and server theme, replay, settings |
| `main.py` | command line, config, start |

## Decisions

- **One file, three modes**: client, server with window, server without window (`--headless`).
- **One instance = one character** (dropdown / `--char`), so several accounts run side by side.
- **Client** sends the parsed events every 2 s. Without a server it shows its own ship and enemies only and stores nothing.
- **Server** decides what a fight is (start with the first event, end after 60 s idle or *Reset*), merges per tick and sends the same picture to all clients. Events between two clients count only from the source's log.
- **Sides**: left the clients' characters (`Listener:` in the log header), right everyone else.
- **Drones**: damage is logged with the owner as source, so it counts for the owner. Drones acting on their own (e.g. EC drones) or being targeted have no known owner and form one entry on the right.
- **Replays**: stored on the server as `history/<start UTC>.jsonl.gz`; clients fetch the last 7 days on connect and after each fight. Late clients get the running fight from its start.
- **Cockpit**: clock plus team sums in/out, per second and total.
- **Connection code** `IP:port/token` to copy, instead of a browser link (that would need a registry entry).
- **Neut direction** from the colour: red = incoming, cyan = outgoing (checked against real logs).
- **Ticks by arrival**, not by log timestamp (client clocks need not agree).
- **Security**: shared token, every event from the network is checked, replays only by listed file names.

## Not in the log, so not possible

Webs, damps, painters, tracking disruptors, boosts.

## Open / later

- Negative cap transfers (2 of ~80,000 lines) are ignored.
- The Linux build has to be made on Linux.
