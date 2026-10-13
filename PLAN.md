# Plan

## Ziel

Live-Visualisierung des aktuellen EVE-Kampfes, ohne die Spielperformance zu beeinflussen. Eine ausführbare Datei plus `config.ini`.

## Aufbau

| Datei | Aufgabe |
|---|---|
| `logparse.py` | Gamelog-Zeile → Event; `LogWatcher` liest neue Zeilen aller aktiven Logs |
| `fight.py` | 2-s-Takte, Dedupe zwischen Clients, Drohnen-Sammlung, Kampfende, Verlauf |
| `net.py` | TCP, eine JSON-Nachricht pro Zeile, Token, Reconnect alle 15 s |
| `ui.py` | tkinter-Canvas, Client- und Server-Theme, Wiedergabe, Einstellungen |
| `main.py` | Kommandozeile, Config, Start |

## Entscheidungen

- **Eine Datei, drei Modi**: Client, Server mit Fenster, Server ohne Fenster (`--headless`).
- **Client** sendet alle 2 s die geparsten Events; ohne Verbindung rechnet er selbst und zeigt nur die eigenen Charaktere.
- **Server** fasst pro Takt zusammen und schickt allen Clients dieselbe Lage. Ereignisse zwischen zwei Clients zählen nur aus dem Log der Quelle.
- **Seiten**: links die Charaktere der Clients (`Listener:` im Log-Kopf), rechts alle anderen. Drohnen erkannt über den Typnamen.
- **Kampfende**: 60 s ohne Event oder *Reset* → Speichern als `history/<start>.jsonl.gz`, Anzeige leeren.
- **Richtung** bei Neuts aus der Farbe: rot = eingehend, cyan = ausgehend (an echten Logs geprüft).
- **Takte nach Eingang**, nicht nach Log-Zeitstempel (Uhren der Clients müssen nicht stimmen).
- **Sicherheit**: gemeinsames Token, Prüfung jedes Events vom Netz, Verlauf nur über gelistete Dateinamen.

## Nicht im Log, daher nicht umsetzbar

Webs, Dämpfer, Painter, Tracking Disruptors, Boosts.

## Offen / später

- Drohnen fremder Besitzer landen immer rechts.
- Negative Cap-Übertragungen (2 von ~80.000 Zeilen) werden ignoriert.
- Linux-Build muss auf Linux gebaut werden.
