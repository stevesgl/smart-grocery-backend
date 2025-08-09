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


# ======================
#  Helper Functions
# ======================

def normalize_token(s: str) -> str:
    return (s or "").strip().lower()

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
    unified_alias_map: dict
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
        resolved = resolve_unified_alias(t1, unified_alias_map)

        # coerce for display + matching (handles list/tuple returns)
        resolved_display, resolved_key = _coerce_to_display_and_key(resolved)

        # exact-match membership checks
        if resolved_key in fda_additive_dict:
            cls = "fda_additive"
        elif resolved_key in classified_ingredient_dict:
            cls = "classified_ingredient"
        else:
            cls = "unclassified"

        results.append({
            "token": original,
            "resolved": resolved_display,   # safe, single string for UI
            "classification": cls
        })

    return results
