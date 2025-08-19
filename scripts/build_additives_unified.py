import csv, json, re, sys
from pathlib import Path

# ---------- CONFIG ----------
BASE = Path(r"C:\Users\steve\OneDrive\Documents\MyGroceryScanner\backend")
DATA = BASE / "data"

# The *conditionally_additives_and_colors* CSV export
ADDITIVES_CSV = DATA / "conditionally_additives_and_colors.csv"

# Your substances JSON (~4k) with clean aliases & tech effect
SUBSTANCES_JSON = DATA / "substances_raw.json"

OUT_ADD_DICT  = DATA / "additive_dict.json"          # unified output
OUT_ALIAS_MAP = DATA / "additive_alias_map.json"
OUT_CAS_MAP   = DATA / "additive_cas_map.json"
# ----------------------------

def norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def clean_cas(s: str) -> str:
    s = norm_space(s)
    return s.replace(" ", "")

def upper_or_blank(s: str) -> str:
    s = norm_space(s)
    return s.upper() if s else ""

# --- Load Substances JSON (authoritative for aliases & tech effect) ---
def load_substances():
    """
    Returns:
      - by_cas: { CAS -> {canonical, aliases:[pretty], technical_effect:str}}
      - alias_sub: { alias_lower -> canonical_heading }
      - canon_to_aliases: { canonical_heading -> [pretty aliases] }
      (Heading is preferred canonical if present; falls back to Substance)
    """
    if not SUBSTANCES_JSON.exists():
        return {}, {}, {}

    raw = json.loads(SUBSTANCES_JSON.read_text(encoding="utf-8"))
    by_cas, alias_sub, canon_to_aliases = {}, {}, {}

    for row in raw:
        heading = norm_space(row.get("Substance Name (Heading)", ""))
        subst   = norm_space(row.get("Substance", ""))
        canonical = heading or subst
        if not canonical:
            continue

        cas  = clean_cas(row.get("CAS Reg No (or other ID)", ""))
        tech = upper_or_blank(row.get("Used for (Technical Effect)", ""))

        names = set()
        if heading: names.add(heading)
        if subst:   names.add(subst)
        other = row.get("Other Names") or []
        if isinstance(other, str):
            other = [n for n in re.split(r";|,", other) if n.strip()]
        for n in other:
            n = norm_space(str(n))
            if n:
                names.add(n)

        canon_to_aliases.setdefault(canonical, set()).update(names)
        for n in names | {canonical}:
            alias_sub[n.lower()] = canonical

        if cas:
            if cas not in by_cas:
                by_cas[cas] = {"canonical": canonical, "aliases": set(names), "technical_effect": tech}
            else:
                by_cas[cas]["aliases"].update(names)
                if not by_cas[cas]["technical_effect"] and tech:
                    by_cas[cas]["technical_effect"] = tech

    for cas, obj in by_cas.items():
        obj["aliases"] = sorted(obj["aliases"])
    for canon, s in canon_to_aliases.items():
        canon_to_aliases[canon] = sorted(s)

    return by_cas, alias_sub, canon_to_aliases

# --- CSV header helpers ---
REG_ADD_COLS = [f"Reg add{str(i).zfill(2)}" for i in range(1, 21)]
REG_COL_COLS = [f"Reg col{str(i).zfill(2)}" for i in range(1, 7)]

def parse_cfr_tokens(cell_val: str):
    """Extract CFR numeric tokens from a messy cell like '172.814 , 173.370'."""
    if not cell_val:
        return []
    txt = str(cell_val)
    # capture 2–3 digit part numbers optionally followed by .x/.xx/.xxx
    return re.findall(r"\b(\d{2,3}(?:\.\d{1,3})?)\b", txt)

def classify_sections(tokens):
    """
    Split tokens into food/color/other by part prefix.
      food_additive: parts 172, 173
      color_additive: parts 73, 74
      other_cfr: everything else (e.g., 184, 133.* etc.)
    """
    food, color, other = set(), set(), set()
    for t in tokens:
        part = t.split(".")[0]
        if part in {"172", "173"}:
            food.add(t)
        elif part in {"73", "74"}:
            color.add(t)
        else:
            other.add(t)
    return sorted(food), sorted(color), sorted(other)

def read_csv_rows(csv_path: Path):
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader), reader.fieldnames

def main():
    # Preconditions
    if not ADDITIVES_CSV.exists():
        print(f"ERROR: CSV not found: {ADDITIVES_CSV}")
        sys.exit(1)

    by_cas_sub, alias_sub, canon_to_aliases = load_substances()

    rows, headers = read_csv_rows(ADDITIVES_CSV)
    # heuristic column names we expect to exist
    col_name = "Substance"
    col_cas  = "CAS Reg No (or other ID)"

    # Validate presence
    for needed in [col_name, col_cas]:
        if needed not in headers:
            print(f"ERROR: Column '{needed}' not found in CSV headers.")
            print("Headers:", headers)
            sys.exit(1)

    # Build unified additive dict
    records_by_key = {}   # key = CAS (preferred) or lower(name)
    alias_map = {}
    cas_map = {}

    for row in rows:
        name = norm_space(row.get(col_name, ""))
        if not name:
            continue
        cas = clean_cas(row.get(col_cas, ""))

        # Gather all CFR tokens from Reg addXX (food-use columns)
        add_tokens = []
        for c in REG_ADD_COLS:
            add_tokens += parse_cfr_tokens(row.get(c, ""))

        # Gather color-use tokens from Reg colXX
        color_tokens = []
        for c in REG_COL_COLS:
            color_tokens += parse_cfr_tokens(row.get(c, ""))

        # Classify separately, then merge with any stray tokens
        food_sections, _, other_from_add = classify_sections(add_tokens)
        _, color_sections, _ = classify_sections(color_tokens)

        # Consolidate "other_cfr" from any non-172/173 values in add columns PLUS
        # any stray in color columns that aren't 73/74 (rare, but safe)
        other_from_color = [t for t in color_tokens if t.split(".")[0] not in {"73", "74"}]
        other_sections = sorted(set(other_from_add) | set(other_from_color))

        # Base record (unified)
        rec = {
            "name": name,                         # canonical = CSV name
            "cas": cas,
            "conditional": True,                  # this tab denotes conditional use
            "is_food_additive": bool(food_sections),
            "is_color_additive": bool(color_sections),
            "cfr": {
                "food_sections": food_sections,   # e.g., ["172.814","173.370"]
                "color_sections": color_sections, # e.g., ["73.85"]
                "other_sections": other_sections  # e.g., ["184.1005","133.123"]
            },
            "aliases": [],                        # filled from substances JSON
            "technical_effect": ""                # filled from substances JSON
        }

        # Enrich from Substances JSON (authoritative for aliases/tech effect)
        if cas and cas in by_cas_sub:
            sub = by_cas_sub[cas]
            rec["technical_effect"] = sub.get("technical_effect", rec["technical_effect"])
            ali = set(sub.get("aliases", [])) | {name}
            rec["aliases"] = sorted(a for a in ali if a != name)
        else:
            # name/alias match
            canon = alias_sub.get(name.lower())
            if canon:
                ali = set(canon_to_aliases.get(canon, [])) | {name}
                rec["aliases"] = sorted(a for a in ali if a != name)
                # try to borrow a tech effect from any CAS group with this canonical
                for cas_key, sub in by_cas_sub.items():
                    if sub["canonical"] == canon and sub.get("technical_effect"):
                        rec["technical_effect"] = sub["technical_effect"]
                        break

        # Merge (dedupe) by CAS first, else by lower(name)
        key = cas or name.lower()
        if key in records_by_key:
            cur = records_by_key[key]
            # Merge sections
            cur["cfr"]["food_sections"]  = sorted(set(cur["cfr"]["food_sections"])  | set(rec["cfr"]["food_sections"]))
            cur["cfr"]["color_sections"] = sorted(set(cur["cfr"]["color_sections"]) | set(rec["cfr"]["color_sections"]))
            cur["cfr"]["other_sections"] = sorted(set(cur["cfr"]["other_sections"]) | set(rec["cfr"]["other_sections"]))
            cur["is_food_additive"]  = bool(cur["cfr"]["food_sections"])
            cur["is_color_additive"] = bool(cur["cfr"]["color_sections"])
            # Merge aliases & technical effect
            cur["aliases"] = sorted(set(cur["aliases"]) | set(rec["aliases"]))
            if not cur["technical_effect"] and rec["technical_effect"]:
                cur["technical_effect"] = rec["technical_effect"]
        else:
            records_by_key[key] = rec

    # Finalize & maps
    records = list(records_by_key.values())
    for rec in records:
        # alias → canonical (CSV name)
        for a in {rec["name"], *rec["aliases"]}:
            alias_map[a.lower()] = rec["name"]
        if rec["cas"]:
            cas_map[rec["cas"]] = rec["name"]

    # Write outputs
    OUT_ADD_DICT.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    OUT_ALIAS_MAP.write_text(json.dumps(alias_map, indent=2, ensure_ascii=False), encoding="utf-8")
    OUT_CAS_MAP.write_text(json.dumps(cas_map, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Rows read: {len(rows)}")
    print(f"Final unified additives: {len(records)}")
    print(f"Alias keys: {len(alias_map)}")
    print(f"CAS mappings: {len(cas_map)}")
    print(f"Wrote: {OUT_ADD_DICT.name}, {OUT_ALIAS_MAP.name}, {OUT_CAS_MAP.name}")

if __name__ == "__main__":
    main()
