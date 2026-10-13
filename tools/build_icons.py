"""Build ship_icons.json: every published ship of the EVE SDE with its 32 px icon, to be packed into the exe.

Run before a release build when new ships came out:  python tools/build_icons.py
"""
import base64
import io
import json
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SDE = "https://developers.eveonline.com/static-data/tranquility/"
ICON = "https://images.evetech.net/types/{}/icon?size=32"
SHIP_CATEGORY = 6
OUT = Path(__file__).resolve().parent.parent / "ship_icons.json"


def get(url, tries=8):
    for attempt in range(tries):  # CCP's servers drop the odd handshake
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "eos-fight-mon build"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except OSError:
            if attempt == tries - 1:
                raise
            time.sleep(0.5 * (attempt + 1))


def main():
    build = json.loads(get(SDE + "latest.jsonl").splitlines()[0])["buildNumber"]
    print(f"SDE build {build}: downloading …")
    sde = zipfile.ZipFile(io.BytesIO(get(f"{SDE}eve-online-static-data-{build}-jsonl.zip")))

    def rows(name):
        with sde.open(name) as fh:
            return [json.loads(line) for line in fh]

    groups = {g["_key"] for g in rows("groups.jsonl") if g["categoryID"] == SHIP_CATEGORY}
    ships = {t["name"]["en"]: t["_key"] for t in rows("types.jsonl")
             if t.get("published") and t["groupID"] in groups}
    print(f"{len(ships)} ships, fetching icons …")

    with ThreadPoolExecutor(4) as pool:  # polite to CCP's image server
        pngs = dict(zip(ships, pool.map(lambda type_id: get(ICON.format(type_id)), ships.values())))
    bad = [name for name, png in pngs.items() if not png.startswith(b"\x89PNG")]
    assert not bad, f"not a PNG: {bad[:5]}"

    icons = {name: base64.b64encode(png).decode() for name, png in sorted(pngs.items())}
    OUT.write_text(json.dumps({"sde_build": build, "icons": icons}, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT.name}: {len(icons)} icons, {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
