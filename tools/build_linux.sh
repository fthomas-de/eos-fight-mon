#!/bin/bash
# Linux build (client with window and headless server) with a portable Python, so the binary runs on glibc 2.17+.
# Run from WSL or Linux:  bash tools/build_linux.sh   -> dist/eos-fight-mon-linux
# Then smoke-tests it: start headless, send one event, --reset must store the fight.
set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
WORK=~/efm-build
mkdir -p "$WORK" && cd "$WORK"
if [ ! -x venv313/bin/python ]; then
    python3 -m venv venv && ./venv/bin/pip install -q uv
    ./venv/bin/uv python install 3.13
    ./venv/bin/uv venv -q --python 3.13 venv313
    ./venv/bin/uv pip install -q --python venv313/bin/python pyinstaller
fi
cp "$REPO"/*.py "$REPO"/ship_icons.json .
rm -rf dist build
venv313/bin/python -m PyInstaller --onefile --name eos-fight-mon --noconfirm --log-level ERROR --add-data "ship_icons.json:." main.py 2>&1 | grep -v INFO || true
venv313/bin/pyi-archive_viewer -l dist/eos-fight-mon | grep -q ship_icons.json || { echo "ship_icons.json missing in the build"; exit 1; }

T=$(mktemp -d)
cp dist/eos-fight-mon "$T/"
cd "$T"
./eos-fight-mon --headless > out.txt 2>&1 &
PID=$!
sleep 4
cat out.txt
python3 - <<'EOF'
import json, socket, configparser, time
c = configparser.ConfigParser(interpolation=None); c.read('config.ini')
s = socket.create_connection(('127.0.0.1', int(c['general']['port'])))
s.sendall((json.dumps({'type': 'hello', 'token': c['general']['token']}) + '\n' +
           json.dumps({'type': 'events', 'listeners': ['A'],
                       'events': [['dmg', 'Foe', None, 'A', None, 5, None, 'A']]}) + '\n').encode())
time.sleep(2.5); s.settimeout(1)
print('tick from linux server:', s.recv(4096)[:80])
EOF
./eos-fight-mon --reset
ls history
kill $PID
mkdir -p "$REPO/dist"
cp "$WORK/dist/eos-fight-mon" "$REPO/dist/eos-fight-mon-linux"
echo "built $REPO/dist/eos-fight-mon-linux"
