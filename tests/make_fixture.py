"""DEV ONLY: build a Scryfall-shaped data/cards.json from Forge's card scripts so the pipeline
can be tested offline. Uses no popularity ranks or prices (the real Scryfall data has both)."""
import json, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from tags import tag
GC = """Ad Nauseam|Ancient Tomb|Aura Shards|Biorhythm|Bolas's Citadel|Braids, Cabal Minion|Chrome Mox|Coalition Victory|
Consecrated Sphinx|Crop Rotation|Cyclonic Rift|Demonic Tutor|Drannith Magistrate|Enlightened Tutor|Farewell|Field of the Dead|
Fierce Guardianship|Force of Will|Gaea's Cradle|Gamble|Gifts Ungiven|Glacial Chasm|Grand Arbiter Augustin IV|Grim Monolith|Humility|
Imperial Seal|Intuition|Jeska's Will|Lion's Eye Diamond|Mana Vault|Mishra's Workshop|Mox Diamond|Mystical Tutor|Narset, Parter of Veils|
Natural Order|Necropotence|Notion Thief|Opposition Agent|Orcish Bowmasters|Panoptic Mirror|Rhystic Study|Seedborn Muse|Serra's Sanctum|
Smothering Tithe|Survival of the Fittest|Teferi's Protection|Tergrid, God of Fright|Thassa's Oracle|The One Ring|
The Tabernacle at Pendrell Vale|Underworld Breach|Vampiric Tutor|Worldly Tutor""".replace("\n", "").split("|")
GC = {g.strip().lower() for g in GC}
root = sys.argv[1]; out = []
for r, _, fs in os.walk(root):
    for f in fs:
        if not f.endswith(".txt"): continue
        txt = open(os.path.join(r, f), encoding="utf-8", errors="ignore").read().split("\nALTERNATE")[0]
        g = lambda k: (re.search(r"^%s:(.*)$" % k, txt, re.M) or [None, ""])[1].strip()
        name, mc, types, oracle = g("Name"), g("ManaCost"), g("Types"), g("Oracle").replace("\\n", "\n")
        if not name or name.startswith("A-"): continue
        cost = "" if mc in ("no cost", "") else "".join("{%s}" % p for p in mc.split())
        words = types.split()
        main_t = [w for w in words if w in ("Artifact","Creature","Enchantment","Instant","Land","Planeswalker","Sorcery","Battle")]
        subs = [w for w in words if w not in main_t and w not in ("Legendary","Basic","Snow","Tribal")]
        tl = " ".join(w for w in words if w in ("Legendary","Basic","Snow") ) + " " + " ".join(main_t) + (" — " + " ".join(subs) if subs else "")
        ident = sorted({c for c in "WUBRG" if ("{%s" % c in cost or "/%s" % c in cost or c + "}" in cost or "{%s}" % c in oracle)})
        cmc = 0
        for p in mc.split():
            cmc += int(p) if p.isdigit() else (0 if p == "X" else 1)
        prod = sorted({c for c in "WUBRGC" if re.search(r"Add .{0,25}\{%s\}" % c, oracle)}) if "Land" in tl else \
               sorted({c for c in "WUBRGC" if re.search(r"[Aa]dd .{0,25}\{%s\}" % c, oracle)})
        c = {"name": name, "cmc": cmc, "mana_cost": cost, "type_line": tl.strip(), "text": oracle, "identity": ident,
             "produces": prod, "game_changer": name.lower() in GC, "rank": None, "usd": None,
             "can_be_commander": "Legendary" in tl and "Creature" in tl}
        c["tags"] = tag(c); out.append(c)
os.makedirs("data", exist_ok=True)
json.dump(out, open("data/cards.json", "w"), separators=(",", ":"))
print(len(out), "fixture cards")
