"""Download Scryfall's daily oracle-cards bulk file, trim it, tag it, write data/cards.json.
Free: bulk files don't count against API rate limits. Run once per day at most."""
import json, sys, os, urllib.request
from tags import tag
from game_changers import FALLBACK

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

def find_download_uri(kind="oracle_cards"):
    """Scryfall lists bulk files at /bulk-data as {"data": [{"type": ..., "download_uri": ...}]}."""
    meta = json.loads(get("https://api.scryfall.com/bulk-data"))
    for item in meta.get("data", []):
        if item.get("type") == kind and item.get("download_uri"):
            return item["download_uri"]
    sys.exit(f"Could not find a '{kind}' bulk file. Scryfall returned:\n{json.dumps(meta)[:800]}")

def main(out="data/cards.json"):
    uri = find_download_uri("oracle_cards")
    print("downloading", uri, flush=True)
    raw = json.loads(get(uri))
    if not isinstance(raw, list):
        sys.exit(f"Unexpected bulk file format: {str(raw)[:500]}")
    keep = [trim(c) for c in raw
            if c.get("legalities", {}).get("commander") == "legal"
            and c.get("layout") not in ("token", "art_series", "emblem", "double_faced_token")]
    flagged = sum(c["game_changer"] for c in keep)
    if flagged < 30:   # expected ~53; the flag is probably missing from the bulk data
        fb = {n.lower() for n in FALLBACK}
        for c in keep:
            c["game_changer"] = c["name"].lower() in fb
        print(f"WARNING: Scryfall flagged only {flagged} Game Changers; using built-in fallback list "
              f"({sum(c['game_changer'] for c in keep)} matched). Check it is current.", flush=True)
    else:
        print(f"Game Changers flagged by Scryfall: {flagged}")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(keep, f, separators=(",", ":"))
    print(f"wrote {len(keep)} commander-legal cards to {out}")

if __name__ == "__main__":
    main(*sys.argv[1:])
