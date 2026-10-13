# eos-fight-mon

Live-Anzeige des laufenden EVE-Online-Kampfes. Clients lesen ihre Gamelogs, der Server führt alle Clients zusammen.

- **Links** die Schiffe aller verbundenen Clients, **rechts** alle anderen, Drohnen je Seite gesammelt.
- Pfeile für Schaden, Remote-Reps (Schild/Panzer/Hülle/Cap), Neut/Nos sowie Scram/Punkt/Jam (gestrichelt), Werte pro Sekunde über die letzten 10 s.
- Cockpit oben: Dauer des Kampfes und die Summen des Teams, ein- und ausgehend, pro Sekunde und über den ganzen Kampf.
- Der Server rechnet in 2-Sekunden-Takten. Nach 60 s ohne Ereignis (oder per *Reset*) wird der Kampf gespeichert. Die Clients holen sich jeden gespeicherten Kampf automatisch; unter *Replays* (sortiert nach Startzeit) lässt er sich mit Start/Stop und Schieberegler abspielen.
- Eigene Drohnen landen links, fremde rechts. Das Layout ist auf Teams um 10 Schiffe ausgelegt.
- Läuft mit niedriger Prozesspriorität, liest nur die Logdateien (kein Zugriff aufs Spiel), etwa 5 ms Arbeit alle 2 s.

## Start

Nur `eos-fight-mon.exe` in einen Ordner legen und doppelklicken. Beim ersten Start entsteht daneben `config.ini`.

| Start | Wofür |
|---|---|
| `eos-fight-mon.exe` | Client: liest Logs, sendet an den Server, zeigt die gemeinsame Lage |
| `eos-fight-mon.exe --server` | Server mit Fenster (bei einem Spieler unter Windows) |
| `eos-fight-mon --headless` | Server ohne Fenster (z. B. Linux-Server) |

Jede Client-Instanz gehört zu genau einem Charakter (Dropdown oben links, gefüllt aus den Gamelogs des letzten Tages). Für mehrere Accounts einfach mehrere Instanzen starten, z. B. per Verknüpfung mit `eos-fight-mon.exe --char "Name"`.

Ohne Serververbindung zeigt der Client nur den eigenen Charakter. Der Knopf *Verbindung* schaltet die Verbindung bzw. den Neuversuch alle 15 s an und aus.

**Verbinden:** Der Server zeigt oben einen Verbindungscode `IP:Port/Token` mit *Kopieren*-Knopf (bzw. gibt ihn ohne Fenster auf der Konsole aus). Im Client unter *Einstellungen* in das Feld *Server-Adresse* einfügen und speichern. Die angezeigte IP ist die im lokalen Netz; über das Internet braucht es die öffentliche IP und eine Portweiterleitung am Router.

Das Tool liest nur die Gamelogs und schreibt nur neben sich selbst (`config.ini`, `history/`).

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
