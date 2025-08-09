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

# data fetchers
from off_product_lookup_v3 import fetch_product_from_off, OFFProductNotFound
from usda_product_lookup_v3 import fetch_product_from_usda, USDAProductNotFound

# parsing + classification
from ingredient_classifier_v3 import (
    parse_ingredient_string,         # tokenizer
    classify_ingredients,            # 3-bucket classifier
    load_fda_additive_dict,
    load_classified_ingredient_dict,
    load_alias_dict,
    load_unified_alias_map
)

# renderer
from report_renderer_v3 import generate_trust_report_html




app = Flask(__name__)
CORS(app, resources={r"/*": {
    
    "origins": [
        "http://localhost",
        "http://127.0.0.1",
        "http://localhost:5173",
        "capacitor://localhost",
        "https://smart-grocery-backend-jxku.onrender.com"  # optional: allow self/or future previews
    ],    
    "methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type"]
}})

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

    # Expect MVP fields from fetchers:
    ingredients_text = product.get("ingredients_text") or ""

    # --- Tokenize (OFF list-first, else text fallback) ---
    ingredients_list = product.get("ingredients_list") or []
    if source == "OFF" and isinstance(ingredients_list, list) and any(
        isinstance(i, dict) and i.get("text") for i in ingredients_list
    ):
        tokenized_ingredients = [i["text"] for i in ingredients_list if i.get("text")]
    else:
        if not ingredients_text.strip():
            return jsonify({"error": "No ingredients found for this product."}), 404
        tokenized_ingredients = parse_ingredient_string(ingredients_text)

    # --- Classify into 3 buckets (runs for both paths) ---
    parsed_ingredients = classify_ingredients(
        ingredients_tokens=tokenized_ingredients,
        fda_additive_dict=fda_additive_dict,
        classified_ingredient_dict=classified_ingredient_dict,
        alias_dict=alias_dict,
        unified_alias_map=unified_alias_map
    )

    fda_additive_items = [p for p in parsed_ingredients if p.get("classification") == "fda_additive"]
    classified_items    = [p for p in parsed_ingredients if p.get("classification") == "classified_ingredient"]
    unclassified_items  = [p for p in parsed_ingredients if p.get("classification") == "unclassified"]

    # --- Build product meta for renderer ---
    product_meta = {
        "gtin": gtin,
        "product_name": product.get("product_name") or product.get("description"),
        "brand_name": product.get("brand_name"),
        "brand_owner": product.get("brand_owner"),
        "source": source,
        "nova_score": product.get("nova_score"),
    }

    # --- Render Trust Report HTML (3 sections + placeholder) ---
    trust_report_html = generate_trust_report_html(
        parsed_fda_additives=fda_additive_items,
        parsed_classified_ingredients=classified_items,
        unclassified=unclassified_items,
        product_meta=product_meta
    )

    return jsonify({
        "gtin": gtin,
        "source": source,
        "product_name": product_meta["product_name"],
        "brand_name": product_meta["brand_name"],
        "brand_owner": product_meta["brand_owner"],
        "nova_score": product_meta["nova_score"],
        "ingredients_text": ingredients_text,
        "parsed_ingredients": parsed_ingredients,
        "trust_report_html": trust_report_html
    }), 200


@app.get("/health")
def health():
    return {"ok": True}, 200

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=True)

