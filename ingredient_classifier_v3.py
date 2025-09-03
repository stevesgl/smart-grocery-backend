# FILE: backend/ingredient_classifier_v3.py
# ## 4. `ingredient_classifier_v3.py` – **Ingredient Parsing & Classification**
# - **Purpose:** Parses raw ingredient strings into structured tokens, matches them against FDA additive lists, aliases, and classified ingredient dictionaries.
# - **Key Functions:**
#   - Tokenizes ingredient lists.
#   - Matches tokens against multiple dictionaries:
#       • FDA Additives
#       • FDA Substances (Coming Soon MVP+1)
#       • Classified Ingredients
#       • Aliases
#   - Assigns classification categories:
#       • fda_additive
#       • classified_ingredient
#       • unclassified
# - **Workflow Role:** **Data Interpreter** – transforms unstructured ingredient text into structured, categorized data.

"""
Ingredient Classifier v3
------------------------
This module converts a raw ingredients string into structured, 
categorized tokens. It uses multiple dictionaries and alias maps 
to ensure exact-match classification and trust-first data handling.
"""

import json
import os
import re
from html import escape as _html_escape

SENTINEL_GENERIC_COLOR = "__generic_color__"
DISPLAY_GENERIC_COLOR = "Artificial color (unspecified)"


# ======================
#  Data Loader Functions
# ======================

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

def _load_json(filename: str):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# --- Helper to lowercase all dict keys recursively ---
def _lower_keys(obj):
    """Recursively lowercases all string keys in dictionaries (values unchanged)."""
    if isinstance(obj, dict):
        return {(k.lower() if isinstance(k, str) else k): _lower_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_lower_keys(x) for x in obj]
    return obj

def load_fda_additive_dict():
    # 21 CFR additives (exact-match keys, lowercase)
    return _lower_keys(_load_json("fda_additive_dict.json"))

def load_classified_ingredient_dict():
    # replaces common_ingredients_live.json
    return _lower_keys(_load_json("classified_ingredient_dict.json"))

def load_alias_dict():
    # additive/processed aliases
    return _lower_keys(_load_json("ingredient_aliases.json"))

def load_unified_alias_map():
    # whole/common ingredient aliases
    return _lower_keys(_load_json("unified_ingredient_alias_map.json"))

# --- ADD near top-level helpers ---
def _flatten_off_ingredients(nodes):
    """
    Deterministically flatten OFF `ingredients` tree.
    Returns a list of ingredient texts (original casing), de-duplicated
    case-insensitively while preserving first-seen casing.
    """
    if not nodes:
        return []

    out = []
    seen = set()  # store lowercase keys for de-dupe

    def dfs(node_list):
        for n in node_list or []:
            # OFF nodes can be dicts with .text and possibly .ingredients
            if isinstance(n, dict):
                txt = (n.get("text") or "").strip()
                if txt:
                    key = txt.lower()
                    if key not in seen:
                        seen.add(key)
                        out.append(txt)
                # recurse into children
                if isinstance(n.get("ingredients"), list):
                    dfs(n["ingredients"])
            # Some feeds may contain stray strings; include them safely
            elif isinstance(n, str):
                t = n.strip()
                if t:
                    key = t.lower()
                    if key not in seen:
                        seen.add(key)
                        out.append(t)

    dfs(nodes)
    return out



# ======================
#  Helper Functions
# ======================

def normalize_token(s: str) -> str:
    # basic normalization: lowercase, collapse spaces, strip leading conjunctions
    t = (s or "").replace("\u00A0", " ").strip().lower()   # NBSP → space
    t = re.sub(r"\s+", " ", t)
    # remove a leading "and " or "& " that commonly precedes last-listed colors
    t = re.sub(r"^(and|&)\s+", "", t)
    # normalize fd&c vs fdc
    t = re.sub(r"\bfdc\b", "fd&c", t)
    t = t.replace("fd & c", "fd&c").replace("fd &c", "fd&c").replace("fd& c", "fd&c")
    return t

def resolve_alias(token: str, alias_dict: dict) -> str:
    key = normalize_token(token)
    return alias_dict.get(key, key)

def resolve_unified_alias(token: str, unified_alias_map: dict) -> str:
    key = normalize_token(token)
    return unified_alias_map.get(key, key)


def _coerce_to_display_and_key(val):
    """
    Ensure alias/unified resolution yields a single display string and a lowercase key for lookups.
    - If list/tuple: pick the first non-empty string.
    - If other types: str() them.
    Returns (display_str, lookup_key_lower).
    """
    if isinstance(val, str):
        s = val
    elif isinstance(val, (list, tuple)):
        s = next((x for x in val if isinstance(x, str) and x.strip()), "")
    elif val is None:
        s = ""
    else:
        s = str(val)
    return s, (s.strip().lower() if s else "")


def _compute_counts(fda_additives, classified_ingredients, unclassified):
    return {
        "fda_additive": len(fda_additives),
        "classified_ingredient": len(classified_ingredients),
        "unclassified": len(unclassified),
    }

def _compute_data_score(fda_additives, classified_ingredients, unclassified):
    matched = len(fda_additives) + len(classified_ingredients)
    total = matched + len(unclassified)
    percent = round(100 * matched / max(total, 1))
    return {"matched": matched, "total": total, "percent": percent}

def _build_segments_from_list(ingredients_list, fda_set, classified_set):
    """
    Preferred path when OFF provides a list of ingredients in order.
    Exact-match only; preserve original casing.
    """
    segs = []
    for idx, item in enumerate(ingredients_list or []):
        norm_key = normalize_token(item)
        cls = "unclassified"
        if norm_key in fda_set:
            cls = "fda_additive"
        elif norm_key in classified_set:
            cls = "classified_ingredient"
        segs.append({"text": item, "class": cls})
        if idx < len(ingredients_list) - 1:
            segs.append({"text": ", ", "class": "none"})
    return segs

def _build_segments_from_text(ingredients_text, fda_set, classified_set, splitter=","):
    if not ingredients_text:
        return []
    parts = parse_ingredient_string(ingredients_text)  # robust tokenizer
    return _build_segments_from_list(parts, fda_set, classified_set)

# ======================
#  Tokenizer
# ======================

def parse_ingredient_string(ingredients_text: str) -> list[str]:
    """
    Conservative split on commas not inside parentheses.
    Returns a list of ingredient tokens (strings).
    """
    text = ingredients_text or ""
    parts = []
    depth = 0
    buff = []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            tok = "".join(buff).strip()
            if tok:
                parts.append(tok)
            buff = []
        else:
            buff.append(ch)
    last = "".join(buff).strip()
    if last:
        parts.append(last)
    return parts

# ======================
#  Main Classification
# ======================

def classify_ingredients(
    ingredients_tokens: list[str],
    fda_additive_dict: dict,
    classified_ingredient_dict: dict,
    alias_dict: dict,
    unified_alias_map: dict,
    default_off_non_additives_to_classified: bool = False
) -> list[dict]:
    """
    Classify a list of ingredient tokens into:
      - fda_additive
      - classified_ingredient
      - unclassified

    Returns a list of dicts:
    {
      "token": "<original token>",
      "resolved": "<after alias/unified resolution>",
      "classification": "fda_additive" | "classified_ingredient" | "unclassified"
    }
    """
    results = []
    if not ingredients_tokens:
        return results

    for raw in ingredients_tokens:
        original = (raw or "").strip()
        if not original:
            continue

        # normalize + alias passes
        t0 = normalize_token(original)
        t1 = resolve_alias(t0, alias_dict)
        # If alias already yielded an FDA canonical or the sentinel, DO NOT unify back
        if (isinstance(t1, str) 
            and (t1.strip().lower() in fda_additive_dict or t1 == SENTINEL_GENERIC_COLOR)):
            resolved = t1
        else:
            resolved = resolve_unified_alias(t1, unified_alias_map)

        # coerce for display + matching (handles list/tuple returns)
        resolved_display, resolved_key = _coerce_to_display_and_key(resolved)

        # exact-match membership checks with sentinel handling
        if resolved_key == SENTINEL_GENERIC_COLOR:
            # Treat as FDA Additive (unspecified) without dict lookup
            cls = "fda_additive"
            resolved_display = DISPLAY_GENERIC_COLOR
            match_key = t0  # highlight using what appeared on label
            # TODO (non-blocking): log anomaly "unspecified_color_additive" with raw string
        elif resolved_key in fda_additive_dict:
            cls = "fda_additive"
            # Highlight by label token, not canonical
            match_key = t0  # highlight by label token
            # prefer canonical display string from dictionary if present
            canon_display = fda_additive_dict.get(resolved_key, {}).get("display")
            if isinstance(canon_display, str) and canon_display.strip():
                resolved_display = canon_display
        elif resolved_key in classified_ingredient_dict:
            cls = "classified_ingredient"
            match_key = resolved_key
        else:
            if default_off_non_additives_to_classified:
                cls = "classified_ingredient"
                match_key = t0
            else:
                cls = "unclassified"
                match_key = t0

        results.append({
            "token": original,
            "resolved": resolved_display,   # safe, single string for UI
            "classification": cls,
            "match_key": match_key
        })

    return results

# --- NEW: Build renderer-ready classification payload ---
def build_classification_payload(
    results: list[dict],
    raw: dict
) -> dict:
    """
    Turn per-token classification results into the renderer payload.
    Expects each item in `results` to have: token (original), resolved (display), classification.
    `raw` should contain:
      - "off_ingredients_list": list[str] or None
      - "ingredients_text": str or None
      - optional "nova_group": int 1..4
    """
    # Split buckets keeping original display casing
    fda_additives = []
    classified_ingredients = []
    unclassified = []

    for r in results or []:
        cls = r.get("classification")
        display = r.get("resolved") or r.get("token") or ""
        # Use match_key to align highlights with label text (esp. for sentinel)
        token_lc = (r.get("match_key") or r.get("resolved") or r.get("token") or "").strip().lower()
        item = {"token": token_lc, "display": display}

        if cls == "fda_additive":
            fda_additives.append(item)
        elif cls == "classified_ingredient":
            classified_ingredients.append(item)
        else:
            unclassified.append(item)

    # Counts + Data Score
    counts = _compute_counts(fda_additives, classified_ingredients, unclassified)
    data_score = _compute_data_score(fda_additives, classified_ingredients, unclassified)

    # Exact-match sets for highlighting
    fda_set = {i["token"] for i in fda_additives}
    classified_set = {i["token"] for i in classified_ingredients}

    off_ingredients_list = raw.get("off_ingredients_list")
    ingredients_text = raw.get("ingredients_text")

    if off_ingredients_list:
        segments = _build_segments_from_list(off_ingredients_list, fda_set, classified_set)
        source = "list"
    else:
        segments = _build_segments_from_text(ingredients_text or "", fda_set, classified_set)
        source = "text"

    classification = {
        "fda_additives": fda_additives,
        "classified_ingredients": classified_ingredients,
        "unclassified": unclassified,
        "counts": counts,
        "data_score": data_score,
        # NOVA only when present
        **({"nova_group": raw.get("nova_group")} if raw.get("nova_group") is not None else {}),
        "original_ingredients": {
            "source": source,
            "segments": segments,
        },
    }
    return classification
# --- /NEW ---
