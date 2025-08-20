# `trust_report_service.py` – **Main Orchestrator**
# FILE: backend/trust_report_service.py
# **Purpose:** Acts as the central entry point for the backend. Handles incoming GTIN requests from the frontend, coordinates with data source lookups (OFF first, USDA as fallback), ingredient classification, and report rendering.
# **Key Functions:**
# - Receives `/gtin-lookup` POST requests containing a GTIN (barcode number).
# - Attempts product retrieval from **Open Food Facts** via `off_product_lookup.py`.
# - If not found, falls back to **USDA** via `usda_product_lookup.py`.
# - Passes raw ingredient data to `ingredient_classifier.py` for parsing and classification.
# - Calls `report_renderer.py` to generate the HTML Trust Report.
# **Workflow Role:** **Conductor** – decides the flow, ensures data is fetched, parsed, classified, and formatted for the frontend.
#
#
# ## 🔄 End-to-End Workflow (From GTIN to Trust Report)
# 1. **Frontend:** User enters/scans a barcode → sends POST request to `/gtin-lookup`.
# 2. **`trust_report_service.py`:**
#    - Tries `off_product_lookup.py` first.
#    - If product not found, uses `usda_product_lookup.py`.
# 3. **Ingredient Parsing:** Passes raw ingredient text to `ingredient_classifier.py`.
# 4. **Classification:** Ingredients are matched against dictionaries and categorized.
# 5. **Report Rendering:** `report_renderer.py` builds HTML Trust Report.
# 6. **Frontend Display:** Trust Report is sent back to the frontend for the user to view.
# 
# 
# **Summary:**  
# - `trust_report_service.py` = **Conductor**  
# - `off_product_lookup.py` = **Primary Fetcher**  
# - `usda_product_lookup.py` = **Fallback Fetcher**  
# - `ingredient_classifier.py` = **Data Interpreter**  
# - `report_renderer.py` = **Presentation Layer** 



from flask import Flask, request, jsonify
from flask_cors import CORS
import os, re
import requests
from flask import make_response

# data fetchers
from off_product_lookup_v3 import fetch_product_from_off, OFFProductNotFound, off_flat_list_and_anomalies
from usda_product_lookup_v3 import fetch_product_from_usda, USDAProductNotFound

# parsing + classification
from ingredient_classifier_v3 import (
    parse_ingredient_string,         # tokenizer
    classify_ingredients,            # 3-bucket classifier
    build_classification_payload,
    load_fda_additive_dict,
    load_classified_ingredient_dict,
    load_alias_dict,
    load_unified_alias_map
)

# renderer
from report_renderer_v3 import generate_trust_report_html

def _cache_off_ingredients(gtin: str, raw: dict):
    """Fire-and-forget upsert of OFF ingredients cache to Supabase."""
    try:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            return  # silently skip if not configured

        endpoint = f"{url.rstrip('/')}/rest/v1/off_ingredients_cache?on_conflict=gtin,source"
        body = {
            "gtin": gtin,
            "source": "OFF",
            "off_ingredients_list": raw.get("off_ingredients_list") or [],
            "ingredients_text": raw.get("ingredients_text") or "",
            # analytics-only fields (trust-first: not used for rendering)
            "ingredients_flat": raw.get("ingredients_flat") or [],
            "anomalies": raw.get("anomalies") or [],
        }
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal,resolution=merge-duplicates",
        }
        requests.post(endpoint, json=body, headers=headers, timeout=2.0)  # non-blocking
    except Exception:
        # fail quietly; caching must never break the main flow
        pass


# --- NEW: extract NOVA (OFF usually provides group 1..4) ---
def _extract_off_nova(off_product: dict):
    candidates = [
        off_product.get("nova_group"),
        off_product.get("nova_groups"),
        (off_product.get("nova_group_tags") or [None])[0]
            if isinstance(off_product.get("nova_group_tags"), list) else None,
    ]
    for c in candidates:
        if c is None:
            continue
        s = str(c)
        digits = "".join(ch for ch in s if ch.isdigit())
        if digits:
            val = int(digits)
            if 1 <= val <= 4:
                return val
    return None

# --- helper to normalize OFF ingredients into a flat list of strings ---
def _off_list_to_strings(prod: dict):
    """
    Flatten OFF ingredient structures (normalized `ingredients_list` or raw `ingredients`)
    into a simple list[str] of ingredient names, deduped case-insensitively while
    preserving first-seen casing and order.

    Order of preference:
      1) normalized `ingredients_list` (list[dict|string], possibly nested)
      2) raw OFF `ingredients` tree (list[dict], nested)
      3) `ingredients_tags` / `ingredients_tags_en` (lossy fallback)

    Returns: list[str] or None
    """
    def _dfs_collect(nodes):
        out = []
        seen = set()

        def _add(name):
            if not isinstance(name, str):
                return
            n = name.replace("en:", "").strip()
            if not n:
                return
            key = n.lower()
            if key not in seen:
                seen.add(key)
                out.append(n)

        def _dfs(lst):
            for node in lst or []:
                if isinstance(node, dict):
                    # prefer `.text`, then `.id`, then `.ingredient`
                    name = node.get("text") or node.get("id") or node.get("ingredient") or ""
                    _add(name)
                    # traverse children if present
                    if isinstance(node.get("ingredients"), list):
                        _dfs(node["ingredients"])
                else:
                    # strings or other simple values
                    _add(str(node))

        _dfs(nodes)
        return out

    # 1) Normalized shape from fetcher: `ingredients_list`
    lst = prod.get("ingredients_list")
    if isinstance(lst, list) and lst:
        flattened = _dfs_collect(lst)
        if flattened:
            return flattened

    # 2) Raw OFF shape: `ingredients` list of dicts
    ingr = prod.get("ingredients")
    if isinstance(ingr, list) and ingr:
        flattened = _dfs_collect(ingr)
        if flattened:
            return flattened

    # 3) Tags fallback (lossy)
    tags = prod.get("ingredients_tags") or prod.get("ingredients_tags_en")
    if isinstance(tags, list) and tags:
        out = []
        seen = set()
        for t in tags:
            n = str(t).replace("en:", "").strip()
            if n:
                key = n.lower()
                if key not in seen:
                    seen.add(key)
                    out.append(n)
        if out:
            return out

    return None

app = Flask(__name__)

ALLOWED_ORIGINS = {
    "http://localhost:5173",
    "capacitor://localhost",
    "http://localhost",
    "http://127.0.0.1",
    "https://sgl-frontend-gamma.vercel.app",
    "https://sgl-frontend-2h7a3tpr4-steves-projects-96024ab9.vercel.app",
}

# Scope CORS to just the API route
CORS(app, resources={r"/gtin-lookup": {"origins": list(ALLOWED_ORIGINS)}})

@app.route("/gtin-lookup", methods=["OPTIONS"])
def gtin_lookup_preflight():
    origin = request.headers.get("Origin", "")
    resp = make_response(("", 204))
    if origin in ALLOWED_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Accept, X-Requested-With, Authorization, Origin"
        resp.headers["Access-Control-Max-Age"] = "86400"
    return resp

# Add headers for both preflight and actual responses
@app.after_request
def apply_cors_headers(resp):
    origin = request.headers.get("Origin")
    if origin in ALLOWED_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, Accept, X-Requested-With, Authorization, Origin"
        )
        resp.headers["Access-Control-Max-Age"] = "86400"
    return resp


# ✅ Load dictionaries once at startup
fda_additive_dict = load_fda_additive_dict()                 # data/fda_additive_dict.json
classified_ingredient_dict = load_classified_ingredient_dict()  # data/classified_ingredient_dict.json
alias_dict = load_alias_dict()                               # data/ingredient_aliases.json
unified_alias_map = load_unified_alias_map()                 # data/unified_ingredient_alias_map.json


@app.route("/gtin-lookup", methods=["POST"])
def gtin_lookup():
    """Main GTIN lookup endpoint."""
    payload = request.get_json(force=True) or {}
    gtin = (payload.get("gtin") or payload.get("barcode") or "").strip()

    # Robust boolean parsing for force_usda (accepts true/false or "true"/"false")
    val = payload.get("force_usda")
    force_usda = (val is True) or (isinstance(val, str) and val.strip().lower() == "true")
    print(f"[SGL] force_usda={force_usda} gtin={gtin}")

    if not gtin:
        return jsonify({"error": "GTIN is required"}), 400

    product = None
    source = None

    if force_usda:
        # ---- USDA forced path (skip OFF entirely) ----
        try:
            print("[SGL] LOOKUP: USDA (forced)")
            product = fetch_product_from_usda(gtin)
            source = "USDA"
        except USDAProductNotFound:
            return jsonify({"error": "Product not found in USDA for this GTIN (forced)."}), 404
    else:
        # ---- OFF-first, USDA fallback ----
        try:
            print("[SGL] LOOKUP: OFF-first")
            product = fetch_product_from_off(gtin)
            source = "OFF"
        except OFFProductNotFound:
            try:
                print("[SGL] LOOKUP: USDA (fallback)")
                product = fetch_product_from_usda(gtin)
                source = "USDA"
            except USDAProductNotFound:
                return jsonify({"error": "Product not found in OFF or USDA for this GTIN."}), 404

    # Raw fields used by the classifier payload/builders
    raw = {
        "off_ingredients_list": None,
        "ingredients_text": None,
        # "nova_group" will be set for OFF only
    }

    if source == "OFF":
        # --- OFF: set raw fields from product ---
        raw["off_ingredients_list"] = _off_list_to_strings(product)
        raw["ingredients_text"] = (
            product.get("ingredients_text_en")
            or product.get("ingredients_text")
            or ""
        )
        raw["nova_group"] = _extract_off_nova(product)

        # Fallback: if extractor missed but normalized nova_score exists, set it
        if raw.get("nova_group") is None:
            try:
                ns = int(str(product.get("nova_score")))
                if 1 <= ns <= 4:
                    raw["nova_group"] = ns
            except (TypeError, ValueError):
                pass

        # (optional lightweight analytics from structured list; logging only)
        try:
            flat_items, off_anomalies = off_flat_list_and_anomalies(
                product.get("ingredients_list") or []
            )
            raw["ingredients_flat"] = flat_items or []
            raw["anomalies"] = off_anomalies or []
        except Exception:
            raw["ingredients_flat"] = []
            raw["anomalies"] = []

        # ✅ fire-and-forget cache write (does not affect rendering)
        _cache_off_ingredients(gtin, raw)

    else:
        # USDA fallback: we typically only have a flat text string
        raw["ingredients_text"] = product.get("ingredients_text") or ""

    # If we truly have no ingredients, fail fast
    if not raw["off_ingredients_list"] and not (raw["ingredients_text"] or "").strip():
        return jsonify({"error": "No ingredients found for this product."}), 404

    # Tokenize for per-token classification
    if source == "OFF":
        # Prefer the structured OFF list; fall back to parsing the text
        tokenized_ingredients = list(raw["off_ingredients_list"] or [])
        if not tokenized_ingredients:
            tokenized_ingredients = parse_ingredient_string(raw["ingredients_text"])
    else:
        tokenized_ingredients = parse_ingredient_string(raw["ingredients_text"])

    # --- Classify into 3 buckets ---
    if source == "OFF":
        # Trust-OFF MVP:
        parsed_ingredients = []
        fda_keys = set(fda_additive_dict.keys())
        for tok in tokenized_ingredients:
            key = (tok or "").strip().lower()
            parsed_ingredients.append({
                "token": tok,
                "resolved": tok,
                "classification": "fda_additive" if key in fda_keys else "classified_ingredient",
            })
    else:
        # USDA (or any other source): use your dictionary-driven classifier
        parsed_ingredients = classify_ingredients(
            ingredients_tokens=tokenized_ingredients,
            fda_additive_dict=fda_additive_dict,
            classified_ingredient_dict=classified_ingredient_dict,
            alias_dict=alias_dict,
            unified_alias_map=unified_alias_map
        )

    # --- Build renderer-ready payload (counts, data_score, segments, nova) ---
    # Trust-first MVP: do NOT filter anomalies here. They’re logged only.
    classification = build_classification_payload(parsed_ingredients, raw)

    # --- Build product meta for header (unchanged fields you already return) ---
    product_meta = {
        "gtin": gtin,
        "product_name": product.get("product_name") or product.get("description"),
        "brand_name": product.get("brand_name"),
        "brand_owner": product.get("brand_owner"),
        "source": source,
        # Keep nova_score if you already expose it; NOVA group is in `classification`
        "nova_score": product.get("nova_score"),
    }

    # --- Render Trust Report HTML (now driven by `classification`) ---
    trust_report_html = generate_trust_report_html(
        product_name=product_meta["product_name"],
        classification=classification,
        brand=(product_meta.get("brand_name") or product_meta.get("brand_owner")),
        gtin=gtin
    )

    # --- Response: keep your existing fields + include classification for testing ---
    return jsonify({
        "gtin": gtin,
        "source": source,
        "product_name": product_meta["product_name"],
        "brand_name": product_meta["brand_name"],
        "brand_owner": product_meta["brand_owner"],
        "nova_score": product_meta["nova_score"],   # OFF NOVA group is in classification.nova_group
        "ingredients_text": raw["ingredients_text"],
        "parsed_ingredients": parsed_ingredients,   # per-token list (unchanged)
        "classification": classification,           # NEW: counts/score/segments/nova_group
        "trust_report_html": trust_report_html,
        # NEW: compact product metadata for frontend toast (non-breaking)
        "product": {
            "name": product_meta["product_name"] or None,
            "brand": (product_meta["brand_name"] or product_meta["brand_owner"]) or None
        }    
    }), 200

@app.get("/health")
def health():
    return {"ok": True}, 200

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=True)

