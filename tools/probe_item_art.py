"""Check All Skins pictures and music kit songs against this PC's CS2 files.

Run from the repo folder:  python tools\\probe_item_art.py  [--all]
Prints how many items of each type got a real picture, and whether music
kit songs could be cut out. Writes a few sample files to probe-item-art\\.
Reads the game files only; changes nothing in CS2.
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cs2cfg import econ, skins_catalog, steam  # noqa: E402

install = steam.find_cs2_install(steam.find_steam_root())
vpk = install / "game" / "csgo" / "pak01_dir.vpk"
out = Path("probe-item-art")
out.mkdir(exist_ok=True)
items = skins_catalog.build(vpk)
seen, found = Counter(), Counter()
for it in items:
    if seen[it["kind"]] >= (100000 if "--all" in sys.argv else 40):
        continue
    seen[it["kind"]] += 1
    pic = econ.picture(vpk, out / "cache", it["art"], skins_catalog.pictures_for(vpk, it["art"]))
    found[it["kind"]] += pic is not None
for kind in seen:
    print(f"{kind:9} pictures found {found[kind]}/{seen[kind]}  (total items {sum(i['kind'] == kind for i in items)})")
kits = [it for it in items if it["kind"] == "music"]
ok = 0
for it in kits[:10]:
    parts = econ.song_parts(vpk, it["paintkit"])
    song = econ.song(vpk, it["paintkit"], parts[0]["part"]) if parts else None
    print(f"music  {it['skin_name'][:30]:30} parts={len(parts)} first={'ok ' + song[1] if song else 'NOT READ'}")
    if song:
        ok += 1
        (out / f"{it['paintkit']}{'.mp3' if song[1] == 'audio/mpeg' else '.wav'}").write_bytes(song[0])
print(f"music kits with a playable song: {ok}/{min(10, len(kits))}")
