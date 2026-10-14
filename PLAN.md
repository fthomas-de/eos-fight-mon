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
| `update.py` | version, update check and install |

## Decisions

- **One file, three modes**: client, server with window, server without window (`--headless`).
- **One instance = one character** (dropdown / `--char`), so several accounts run side by side.
- **Client** sends the parsed events every 2 s. Without a server it shows its own ship and enemies only and stores nothing.
- **Server** decides what a fight is (start with the first event, end after 60 s idle or *Reset* on the server only), merges per tick and sends the same picture to all clients. Events between two clients count only from the source's log.
- **Sides**: left the clients' characters (`Listener:` in the log header), right everyone else.
- **Drones**: damage is logged with the owner as source, so it counts for the owner. Drones acting on their own (e.g. EC drones) or being targeted have no known owner and form one entry on the right.
- **Replays**: stored on the server as `history/<start UTC>.jsonl.gz`; clients fetch the last 7 days on connect and after each fight. Late clients get the running fight from its start.
- **Cockpit**: clock plus team sums in/out, per second and total, in its own small window.
- **Always on top** optional, separately for cockpit and graph.
- **Graph** window: per group out/in per second over the fight, small multiples, no second axis.
- **Server** lists its connections with the picked character.
- **Self-update** from GitHub releases, only after asking; checked against SHA256SUMS; the running exe is renamed, not overwritten.
- **Connection code** `IP:port/token` to copy, instead of a browser link (that would need a registry entry).
- **Friendly fire** (hostile effects between clients and their rep partners) is dropped unless `friendly_fire` is on; the server's setting decides for connected clients.
- **Internet**: server listens on all interfaces; connection code uses the public address (`public_address` or api.ipify.org). No TLS.
- **Neut direction** from the colour: red = incoming, cyan = outgoing (checked against real logs).
- **Ticks by arrival**, not by log timestamp (client clocks need not agree).
- **Security**: shared token, every event from the network is checked, replays only by listed file names.

## Not in the log, so not possible

Webs, damps, painters, tracking disruptors, boosts.

## Open / later

- Negative cap transfers (2 of ~80,000 lines) are ignored.
- The Linux build has to be made on Linux.
