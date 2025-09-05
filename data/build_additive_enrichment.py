#!/usr/bin/env python3
# build_additive_enrichment.py
# Generates fda_additive_enriched.json from existing JSON assets.

import json, re, unicodedata, sys
from collections import defaultdict, Counter
from pathlib import Path
from tqdm import tqdm   # make sure to `pip install tqdm` if you don’t already have it

HERE = Path(__file__).resolve().parent

# ---------- Helpers ----------

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def normalize_for_compare(s: str) -> str:
    # Lowercase, strip accents, remove punctuation & extra spaces
    if not isinstance(s, str):
        return ""
    s = s.strip()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s)       # remove punctuation
    s = re.sub(r"\s+", " ", s).strip()
    return s

def make_slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = s.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s

def clean_used_for(raw: str):
    if not isinstance(raw, str):
        return []
    # replace <br /> with commas, split on commas/semicolons
    txt = raw.replace("<BR />", ",").replace("<br />", ",").replace("<br/>", ",")
    parts = [p.strip(" \t\r\n.:;,-") for p in re.split(r"[;,]", txt) if p.strip()]
    # standardize common FDA phrases (keep short, human readable)
    MAP = {
        "flavoring agent or adjuvant": "Flavoring agent/adjuvant",
        "flavor enhancer": "Flavor enhancer",
        "nutrient supplement": "Nutrient supplement",
        "antimicrobial agent": "Antimicrobial agent",
        "solvent or vehicle": "Solvent/vehicle",
        "washing or surface removal agent": "Washing/surface removal agent",
        "surface-finishing agent": "Surface-finishing agent",
        "boiler water additive": "Boiler water additive",
        "enzyme": "Enzyme",
        "ph control agent": "pH control agent",
        "color additive": "Color additive",
        "preservative": "Preservative",
        "curing agent": "Curing agent",
    }
    out = []
    seen = set()
    for p in parts:
        key = normalize_for_compare(p)
        if not key:
            continue
        label = MAP.get(key, None)
        # Fallback: nice-case generic phrases; avoid mangling chemistry (rare in this field)
        if label is None:
            # title-case words ≤3 tokens; otherwise just capitalize first letter
            tokens = p.split()
            label = p.title() if 1 <= len(tokens) <= 4 else (p[:1].upper() + p[1:])
        nkey = normalize_for_compare(label)
        if nkey not in seen:
            seen.add(nkey)
            out.append(label)
    return out

def add_alias(target_set, alias):
    if not alias or not isinstance(alias, str):
        return
    n = normalize_for_compare(alias)
    if n and n not in target_set["_norm"]:
        target_set["_norm"].add(n)
        target_set["display"].append(alias.strip())

# ---------- Load inputs ----------

try:
    fda_additive_dict = load_json(HERE / "fda_additive_dict.json")  # {canonical: {aliases: [...]}}
except FileNotFoundError:
    print("ERROR: fda_additive_dict.json not found next to this script.", file=sys.stderr)
    sys.exit(1)

# Optional/augmenting inputs (best-effort)
ingredient_aliases = {}
additive_alias_map = {}
additive_cas_map = {}
additive_dict = []  # list of additive objects with name/aliases/technical_effect
substances = []

if (HERE / "ingredient_aliases.json").exists():
    ingredient_aliases = load_json(HERE / "ingredient_aliases.json")  # alias -> canonical
if (HERE / "additive_alias_map.json").exists():
    additive_alias_map = load_json(HERE / "additive_alias_map.json")  # alias -> canonical
if (HERE / "additive_cas_map.json").exists():
    additive_cas_map = load_json(HERE / "additive_cas_map.json")      # CAS -> canonical
if (HERE / "additive_dict.json").exists():
    additive_dict = load_json(HERE / "additive_dict.json")            # [{name, aliases, technical_effect, ...}, ...]
if (HERE / "all_fda_substances_full_live.json").exists():
    substances = load_json(HERE / "all_fda_substances_full_live.json")  # [{...}, ...]

# ---------- Build canonical sets & reverse maps ----------

canonicals = set()
# from fda_additive_dict keys
canonicals.update(list(fda_additive_dict.keys()))
# from additive_dict 'name' field
for obj in additive_dict or []:
    name = obj.get("name")
    if isinstance(name, str) and name.strip():
        canonicals.add(name.strip())

# Reverse alias maps: alias(lower/normalized) -> canonical
rev_alias = {}

def add_rev_alias(alias, canonical):
    if not alias or not canonical:
        return
    rev_alias[normalize_for_compare(alias)] = canonical

# from fda_additive_dict aliases
for canonical, meta in (fda_additive_dict or {}).items():
    for a in (meta or {}).get("aliases", []) or []:
        add_rev_alias(a, canonical)
# from additive_dict aliases
for obj in additive_dict or []:
    cname = obj.get("name")
    for a in obj.get("aliases", []) or []:
        add_rev_alias(a, cname)
# from ingredient_aliases.json (alias -> canonical)
for a, cname in (ingredient_aliases or {}).items():
    if cname in canonicals:
        add_rev_alias(a, cname)
# from additive_alias_map.json (alias -> canonical)
for a, cname in (additive_alias_map or {}).items():
    if cname in canonicals:
        add_rev_alias(a, cname)
# CAS map (CAS -> canonical)
cas_to_canonical = {}
for cas, cname in (additive_cas_map or {}).items():
    if cname in canonicals:
        cas_to_canonical[normalize_for_compare(cas)] = cname

# ---------- Mine “Other Names” + “Used for” from substances ----------

sub_enrichment = defaultdict(lambda: {"other_names": [], "used_for": []})
sub_hits = 0

for row in tqdm(substances or [], desc="Processing substances"):
    heading = (row.get("Substance Name (Heading)") or row.get("Substance") or "").strip()
    other_names = row.get("Other Names") or []
    used_for_raw = row.get("Used for (Technical Effect)") or ""
    cas_raw = row.get("CAS Reg No (or other ID)") or ""

    # Determine canonical via CAS, heading, or alias in "Other Names"
    canonical = None

    if cas_raw:
        cas_key = normalize_for_compare(cas_raw)
        canonical = cas_to_canonical.get(cas_key)

    if not canonical and heading:
        # direct match or alias match
        h_norm = normalize_for_compare(heading)
        # exact canonical by normalization
        for c in canonicals:
            if normalize_for_compare(c) == h_norm:
                canonical = c
                break
        if not canonical:
            canonical = rev_alias.get(h_norm)

    if not canonical:
        # try any of the "Other Names" as alias
        for a in other_names:
            canonical = rev_alias.get(normalize_for_compare(a))
            if canonical:
                break

    if not canonical:
        continue  # not one of our additives

    sub_hits += 1

    # Collect other names (keep display text; dedupe later)
    sub_enrichment[canonical].setdefault("other_names", [])
    for a in other_names:
        if isinstance(a, str) and a.strip():
            sub_enrichment[canonical]["other_names"].append(a.strip())

    # Collect used_for tokens (dedup later)
    uf = clean_used_for(used_for_raw)
    if uf:
        sub_enrichment[canonical].setdefault("used_for", [])
        sub_enrichment[canonical]["used_for"].extend(uf)

# ---------- Assemble final enrichment per canonical ----------

out = {}
alias_count_stats = []
used_for_presence = 0

for canonical in sorted(canonicals, key=lambda x: x.lower()):
    display_aliases = {"display": [], "_norm": set()}

    # 1) Canonical first
    add_alias(display_aliases, canonical)

    # 2) Known aliases from fda_additive_dict
    for a in (fda_additive_dict.get(canonical, {}) or {}).get("aliases", []) or []:
        add_alias(display_aliases, a)

    # 3) Aliases from additive_dict
    for obj in additive_dict or []:
        if normalize_for_compare(obj.get("name", "")) == normalize_for_compare(canonical):
            for a in obj.get("aliases", []) or []:
                add_alias(display_aliases, a)
            # Also mine technical_effect here
            tech = obj.get("technical_effect")
            for t in clean_used_for(tech or ""):
                sub_enrichment[canonical].setdefault("used_for", []).append(t)
            break

    # 4) Aliases from ingredient_aliases/additive_alias_map that point to this canonical
    for alias_norm, cname in list(rev_alias.items()):
        if cname == canonical:
            # We don't have original-casing here; try to recover from keys in the original maps
            # Use the best-available display: the alias_norm with spaces (approximate)
            approx = alias_norm.replace(" ", " ")
            add_alias(display_aliases, approx)

    # 5) Aliases from substances
    for a in sub_enrichment.get(canonical, {}).get("other_names", []):
        add_alias(display_aliases, a)

    # Drop helper
    other_names = display_aliases["display"]

    # Ensure canonical is index 0
    if other_names and other_names[0] != canonical:
        # move canonical to front if it exists somewhere else
        if canonical in other_names:
            other_names.remove(canonical)
        other_names = [canonical] + other_names

    # Sort remaining aliases (after index 0) by length then alpha for readability
    if len(other_names) > 1:
        head, rest = other_names[0], other_names[1:]
        rest = sorted(rest, key=lambda s: (len(s), s.lower()))
        other_names = [head] + rest

    used_for = []
    seen_uf = set()
    for t in sub_enrichment.get(canonical, {}).get("used_for", []):
        key = normalize_for_compare(t)
        if key and key not in seen_uf:
            seen_uf.add(key)
            used_for.append(t)

    if used_for:
        used_for_presence += 1

    out[canonical] = {
        "slug": make_slug(canonical),
        "canonical_name": canonical,
        "other_names": other_names,
        "used_for": used_for,
    }

    alias_count_stats.append(len(other_names))

# ---------- Write output & print stats ----------

out_path = HERE / "fda_additive_enriched.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)

total = len(canonicals)
with_alias_gt1 = sum(1 for c in out.values() if len(c["other_names"]) > 1)
max_aliases = max(alias_count_stats) if alias_count_stats else 0

print(f"Wrote: {out_path}")
print(f"Canonicals: {total}")
print(f"Aliases >1: {with_alias_gt1} ({with_alias_gt1/total*100:.1f}%)")
print(f"Used-for present: {used_for_presence} ({used_for_presence/total*100:.1f}%)")
print(f"Max alias count: {max_aliases}")
