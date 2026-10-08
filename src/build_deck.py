"""Constraint-based Commander deck builder. No AI calls, $0 to run.
Hard rules (legality, color identity, singleton, budget, Game Changer cap) are enforced in code.
Judgment is approximated by: tribe match + keyword overlap with the commander + EDHREC popularity rank."""
import argparse, math, os, re, sys
from collections import Counter
from common import load_cards, pips

BASICS = {"W": "Plains", "U": "Island", "B": "Swamp", "R": "Mountain", "G": "Forest"}
QUOTAS = {"ramp": 10, "draw": 8, "removal": 6, "counter": 3, "sweeper": 2, "recursion": 2}
VOCAB = ["mill", "graveyard", "+1/+1 counter", "token", "sacrifice", "flying", "untap", "treasure",
         "artifact", "enchantment", "exile", "draw", "whenever", "attacks", "enters"]

def price(c):
    try:
        return float(c["usd"]) if c.get("usd") else 0.5
    except ValueError:
        return 0.5

def score(c, tribe, cmd_kw):
    s = 0.0
    t, x = c["type_line"].lower(), (c.get("text") or "").lower()
    if tribe:
        tl = tribe.lower()
        if "creature" in t and (tl in t or "changeling" in x):
            s += 100
        elif tl in x:
            s += 40
    s += 15 * sum(1 for k in cmd_kw if k in x)
    if c.get("rank"):
        s += max(0.0, 30 - 6 * math.log10(c["rank"] + 1))
    if c["cmc"] >= 7:
        s -= 10
    return s

def build(a):
    cards = load_cards(a.cards)
    cmd = cards.get(a.commander.lower())
    if not cmd:
        sys.exit(f"Commander not found (or not Commander-legal): {a.commander}")
    ident = set(cmd["identity"])
    tribe = a.tribe or (cmd["type_line"].split("—")[-1].split()[0] if "—" in cmd["type_line"] else "")
    cmd_text = (cmd.get("text") or "").lower()
    cmd_kw = [k for k in VOCAB if k in cmd_text]

    pool = [c for c in {id(v): v for v in cards.values()}.values()
            if set(c["identity"]) <= ident and c["name"] != cmd["name"]
            and not c["name"].lower() in {n.lower() for n in a.exclude}
            and "mass_land_denial" not in c["tags"]
            and not (a.no_extra_turns and "extra_turn" in c["tags"])]
    nonland = [c for c in pool if "land" not in c["tags"]]
    for c in nonland:
        c["_s"] = score(c, tribe, cmd_kw)
    nonland.sort(key=lambda c: -c["_s"])

    n_nonland = 99 - a.lands
    picked, names, spent, gc = [], set(), 0.0, 0
    per_card_cap = max(5.0, a.budget * 0.10)

    def try_add(c, force=False):
        nonlocal spent, gc
        if c["name"] in names or len(picked) >= n_nonland:
            return False
        p = price(c)
        if not force and (p > per_card_cap or spent + p > a.budget):
            return False
        if c["game_changer"] and gc >= a.max_gc:
            return False
        picked.append(c); names.add(c["name"]); spent += p
        gc += c["game_changer"]
        return True

    for n in a.must:                      # user-required cards first
        c = cards.get(n.lower())
        if c and set(c["identity"]) <= ident:
            try_add(c, force=True)
        else:
            print(f"warning: --must card unavailable or off-color: {n}", file=sys.stderr)

    gcs = [c for c in nonland if c["game_changer"] and ("draw" in c["tags"] or "counter" in c["tags"]
                                                         or "removal" in c["tags"] or "ramp" in c["tags"])]
    for c in sorted(gcs, key=lambda c: c.get("rank") or 10**9):   # most popular Game Changers
        if gc >= a.max_gc:
            break
        try_add(c)

    tribe_creatures = [c for c in nonland if tribe and "creature" in c["tags"] and score(c, tribe, []) >= 100]
    for c in tribe_creatures:
        if sum(1 for p in picked if tribe.lower() in p["type_line"].lower()) >= a.tribe_count:
            break
        try_add(c)

    for role, need in QUOTAS.items():
        if role == "counter" and "U" not in ident:
            continue
        for c in (x for x in nonland if role in x["tags"]):
            if sum(role in p["tags"] for p in picked) >= need:
                break
            try_add(c)

    for c in nonland:                     # fill the rest by score
        if len(picked) >= n_nonland:
            break
        try_add(c)

    # --- lands
    land_pool = [c for c in pool if "land" in c["tags"] and "Basic" not in c["type_line"]
                 and len(set(c["produces"]) & ident) >= (2 if len(ident) > 1 else 1)
                 and "creature" not in c["tags"]]
    land_pool.sort(key=lambda c: c.get("rank") or 10**9)
    nonbasic = []
    for c in land_pool:
        if len(nonbasic) >= min(a.max_nonbasic, a.lands - 10):
            break
        if price(c) <= max(5.0, a.budget * 0.03) and not (c["game_changer"] and gc >= a.max_gc):
            nonbasic.append(c); gc += c["game_changer"]; spent += price(c)
    colors = [x for x in "WUBRG" if x in ident]
    pc = Counter()
    for c in picked + [cmd]:
        for k, v in pips(c["mana_cost"]).items():
            if k in ident:
                pc[k] += v
    basics_n = a.lands - len(nonbasic)
    basics = Counter()
    if colors:
        total = sum(pc.values()) or len(colors)
        for k in colors:
            basics[BASICS[k]] = max(1, round(basics_n * (pc[k] or 1) / total))
        while sum(basics.values()) > basics_n:
            basics[max(basics, key=basics.get)] -= 1
        while sum(basics.values()) < basics_n:
            basics[max(basics, key=basics.get)] += 1
    else:
        basics["Wastes"] = basics_n

    lines = [f"1 {cmd['name']}"] + [f"1 {c['name']}" for c in sorted(picked, key=lambda c: (c["cmc"], c["name"]))] \
            + [f"1 {c['name']}" for c in nonbasic] + [f"{n} {b}" for b, n in basics.items()]
    total = 1 + len(picked) + len(nonbasic) + sum(basics.values())
    return lines, total, spent, gc, tribe

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--commander", required=True)
    ap.add_argument("--tribe", default="", help="creature type to emphasize (default: commander's first subtype)")
    ap.add_argument("--budget", type=float, default=400, help="approx USD cap for nonland+nonbasic cards")
    ap.add_argument("--max-gc", type=int, default=3, help="Game Changer cap (Bracket 3 = 3, Bracket 2 = 0)")
    ap.add_argument("--lands", type=int, default=37)
    ap.add_argument("--max-nonbasic", type=int, default=14)
    ap.add_argument("--tribe-count", type=int, default=24)
    ap.add_argument("--must", nargs="*", default=[], help="cards to force in")
    ap.add_argument("--exclude", nargs="*", default=[])
    ap.add_argument("--no-extra-turns", action="store_true")
    ap.add_argument("--cards", default="data/cards.json")
    ap.add_argument("--out", default="out/deck.txt")
    a = ap.parse_args()
    lines, total, spent, gc, tribe = build(a)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    open(a.out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"commander={a.commander} tribe={tribe or '-'} cards={total} est_cost=${spent:.0f} game_changers={gc}")
    if total != 100:
        print("WARNING: deck is not 100 cards (pool too small or filters too strict)", file=sys.stderr)

if __name__ == "__main__":
    main()
