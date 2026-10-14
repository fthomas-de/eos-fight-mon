#!/bin/sh
# Upgrade the headless Linux server to the latest release. Put it next to the binary `eos-fight-mon` and run
# `sh upgrade_linux.sh`: downloads, checks SHA256SUMS.txt, stores a running fight, swaps the binary, restarts
# the server if it was running. config.ini and history/ stay, so clients reconnect with the same code.
set -eu
cd "$(dirname "$0")"

json=$(curl -fsS https://api.github.com/repos/fthomas-de/eos-fight-mon/releases/latest)
url=$(printf '%s' "$json" | grep -o 'https://[^"]*-linux-x86_64' | head -1)
sums=$(printf '%s' "$json" | grep -o 'https://[^"]*SHA256SUMS.txt' | head -1)
name=${url##*/}
new=$(printf '%s' "$name" | sed 's/.*-v\(.*\)-linux-x86_64/\1/')
old=$( (./eos-fight-mon --version 2>/dev/null || echo "- none") | cut -d' ' -f2)
if [ "$new" = "$old" ]; then
    echo "already on $old"
    exit 0
fi

curl -fsSLo eos-fight-mon.new "$url"
hash=$(curl -fsSL "$sums" | grep " \*$name\$" | cut -d' ' -f1)
echo "$hash  eos-fight-mon.new" | sha256sum -c -
chmod +x eos-fight-mon.new

running=no
if pgrep -f "eos-fight-mon --headless" >/dev/null; then
    running=yes
    ./eos-fight-mon --reset || true  # store the running fight
    pkill -f "eos-fight-mon --headless"
    sleep 2
fi
mv eos-fight-mon.new eos-fight-mon
if [ $running = yes ]; then
    nohup ./eos-fight-mon --headless >> server.log 2>&1 &
    echo "server restarted, log: server.log"
fi
echo "upgraded $old -> $new"
