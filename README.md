# eos-fight-mon

Live-Anzeige des laufenden EVE-Online-Kampfes. Clients lesen ihre Gamelogs, der Server führt alle Clients zusammen.

- **Links** die Schiffe aller verbundenen Clients, **rechts** alle anderen, Drohnen je Seite gesammelt.
- Pfeile für Schaden, Remote-Reps (Schild/Panzer/Hülle/Cap), Neut/Nos sowie Scram/Punkt/Jam (gestrichelt), Werte pro Sekunde über die letzten 10 s.
- Der Server rechnet in 2-Sekunden-Takten. Nach 60 s ohne Ereignis (oder per *Reset*) wird der Kampf im Verlauf gespeichert und kann wieder abgespielt werden.
- Läuft mit niedriger Prozesspriorität, liest nur die Logdateien (kein Zugriff aufs Spiel), etwa 5 ms Arbeit alle 2 s.

## Start

Nur `eos-fight-mon.exe` in einen Ordner legen und doppelklicken. Beim ersten Start entsteht daneben `config.ini`.

| Start | Wofür |
|---|---|
| `eos-fight-mon.exe` | Client: liest Logs, sendet an den Server, zeigt die gemeinsame Lage |
| `eos-fight-mon.exe --server` | Server mit Fenster (bei einem Spieler unter Windows) |
| `eos-fight-mon --headless` | Server ohne Fenster (z. B. Linux-Server) |

Ohne Serververbindung zeigt der Client nur die eigenen Charaktere. Der Knopf *Verbindung* schaltet die Verbindung bzw. den Neuversuch alle 15 s an und aus.

## config.ini

```ini
[general]
# client oder server
mode = client
port = 47110
# wird beim ersten Start erzeugt; der Token des Servers muss in jeden Client
token = …
history_dir = history

[client]
# Adresse des Servers
host = localhost
log_dir = ~/Documents/EVE/logs/Gamelogs
auto_connect = yes
```

Alles lässt sich auch im Fenster unter *Einstellungen* ändern. Der Server muss auf dem Port per TCP erreichbar sein.

## Was das Log nicht hergibt

Webs, Dämpfer, Painter, Tracking Disruptors und Flottenboosts stehen nicht im Kampf-Log und werden daher nicht angezeigt.

## Entwicklung

Nur Python-Standardbibliothek (3.11+).

```bash
python main.py
```

```bash
python -m unittest discover -s tests
```

Build (Windows `.exe`; für Linux dasselbe ohne `--windowed` auf einem Linux-Rechner):

```bash
python -m PyInstaller --onefile --windowed --name eos-fight-mon main.py
```
