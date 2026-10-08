"""Download Scryfall's daily oracle-cards bulk file, trim it, tag it, write data/cards.json.
Free: bulk files don't count against API rate limits. Run once per day at most."""
import json, sys, os, urllib.request
from tags import tag

UA = {"User-Agent": "DeckAutomation/0.1 (personal hobby project)", "Accept": "application/json"}

def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300).read()

def trim(c):
    faces = c.get("card_faces") or []
    text = c.get("oracle_text") or "\n".join(f.get("oracle_text", "") for f in faces)
    type_line = c.get("type_line") or " // ".join(f.get("type_line", "") for f in faces)
    mana_cost = c.get("mana_cost") or (faces[0].get("mana_cost", "") if faces else "")
    d = {
        "name": c["name"], "cmc": c.get("cmc", 0), "mana_cost": mana_cost,
        "type_line": type_line, "text": text,
        "identity": c.get("color_identity", []), "produces": c.get("produces", []),
        "game_changer": bool(c.get("game_changer", False)),
        "rank": c.get("edhrec_rank"), "usd": (c.get("prices") or {}).get("usd"),
        "can_be_commander": ("Legendary" in type_line and "Creature" in type_line)
                            or "can be your commander" in text,
    }
    d["tags"] = tag(d)
    return d

def main(out="data/cards.json"):
    meta = json.loads(get("https://api.scryfall.com/bulk-data/oracle-cards"))
    raw = json.loads(get(meta["download_uri"]))
    keep = [trim(c) for c in raw
            if c.get("legalities", {}).get("commander") == "legal"
            and c.get("layout") not in ("token", "art_series", "emblem", "double_faced_token")]
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(keep, f, separators=(",", ":"))
    print(f"wrote {len(keep)} commander-legal cards to {out}")

if __name__ == "__main__":
    main(*sys.argv[1:])
