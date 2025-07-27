from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
import sys
import datetime

# ✅ Setup Flask app and CORS
app = Flask(__name__)
CORS(app, resources={r"/*": {
    "origins": ["https://barcode-vercel-ten.vercel.app"],
    "methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type"]
}})

# ✅ Import parsers and utilities
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# ✅ Load gtin_map.json with error fallback
DATA_DIR = os.path.join(current_dir, "data")
GTIN_MAP_PATH = os.path.join(DATA_DIR, "gtin_map.json")

try:
    with open(GTIN_MAP_PATH, "r") as f:
        gtin_to_fdc = json.load(f)
except FileNotFoundError:
    print(f"[Startup Error] gtin_map.json not found at: {GTIN_MAP_PATH}")
    gtin_to_fdc = {}
except json.JSONDecodeError as e:
    print(f"[Startup Error] Failed to decode gtin_map.json: {e}")
    gtin_to_fdc = {}

try:
    from ingredient_parser import (
        load_patterns,
        load_fda_substances,
        load_common_ingredients,
        parse_ingredient_string
    )
    from cache_manager import get_cached_product, update_lookup_count, write_to_cache
    from usda import fetch_product_from_usda
except Exception as e:
    print("Import error:", str(e))
    raise

# ✅ Load reference data once
patterns_data = load_patterns()
fda_substances_set = load_fda_substances()
common_ingredients_set = load_common_ingredients()

@app.route('/')
def home():
    return "Ingredient Parser Service is live."

@app.route('/gtin-lookup', methods=['POST', 'OPTIONS'])
def gtin_lookup():
    if request.method == 'OPTIONS':
        return ('', 204)

    try:
        data = request.get_json()
        gtin = data.get("gtin")
        if not gtin:
            return jsonify({"error": "GTIN is required"}), 400

        # ✅ Step 1: Check Airtable cache
        cached = get_cached_product(gtin)
        if cached:
            update_lookup_count(cached["id"])
            return jsonify(cached["fields"])

        # ✅ Step 2: Get FDC ID from GTIN mapping
        fdc_id = gtin_to_fdc.get(gtin)
        if not fdc_id:
            return jsonify({"error": f"GTIN {gtin} not found in gtin_map."}), 404

        # ✅ Step 3: Get USDA product data
        usda_product = fetch_product_from_usda(fdc_id)
        if not usda_product:
            return jsonify({"error": f"FDC ID {fdc_id} not found in USDA API."}), 404

        # ✅ Step 4: Parse ingredient string
        ingredients_raw = usda_product.get("ingredients", "")
        parsed = parse_ingredient_string(
            ingredients_raw, patterns_data, common_ingredients_set, fda_substances_set
        )

        # ✅ Step 5: Categorize parsed output
        parsed_fda_non_common = [i["base_ingredient"] for i in parsed if i["attributes"]["trust_report_category"] == "fda_non_common"]
        parsed_fda_common = [i["base_ingredient"] for i in parsed if i["attributes"]["trust_report_category"] == "fda_common"]
        parsed_common_only = [i["base_ingredient"] for i in parsed if i["attributes"]["trust_report_category"] == "common_only"]
        truly_unidentified = [i["base_ingredient"] for i in parsed if i["attributes"]["trust_report_category"] == "unknown"]

        # ✅ Step 6: Compute scores
        total = len(parsed)
        identified = total - len(truly_unidentified)
        data_score = round(identified / total, 2) if total > 0 else 0.0
        if data_score >= 0.9:
            completeness = "High"
        elif data_score >= 0.5:
            completeness = "Medium"
        else:
            completeness = "Low"

        # ✅ Step 7: Estimate NOVA score
        nova_score = 4 if data_score < 0.3 else 3 if data_score < 0.7 else 2
        nova_description = {
            1: "Unprocessed or minimally processed",
            2: "Processed culinary ingredient",
            3: "Processed food",
            4: "Ultra-processed food"
        }.get(nova_score, "Unknown")

        # ✅ Step 8: Write to Airtable cache
write_to_cache(
    gtin=gtin,
    fdc_id=fdc_id,
    brand_name=usda_product.get("brandName", ""),
    brand_owner=usda_product.get("brandOwner", ""),
    description=usda_product.get("description", ""),
    ingredients_raw=ingredients_raw,
    parsed_fda_non_common=json.dumps(parsed_fda_non_common),
    parsed_fda_common=json.dumps(parsed_fda_common),
    parsed_common_only=json.dumps(parsed_common_only),
    truly_unidentified=json.dumps(truly_unidentified),
    data_score=data_score,
    completeness=completeness,
    nova_score=nova_score,
    nova_description=nova_description,
    parsed=parsed  # ✅ THIS MUST BE INCLUDED
)


        return jsonify({
            "gtin": gtin,
            "fdc_id": fdc_id,
            "brand_name": usda_product.get("brandName", ""),
            "brand_owner": usda_product.get("brandOwner", ""),
            "description": usda_product.get("description", ""),
            "ingredients": ingredients_raw,
            "lookup_count": 1,
            "last_access": datetime.datetime.utcnow().isoformat(),
            "source": "USDA API",
            "identified_fda_non_common": parsed_fda_non_common,
            "identified_fda_common": parsed_fda_common,
            "identified_common_ingredients_only": parsed_common_only,
            "truly_unidentified_ingredients": truly_unidentified,
            "data_score": data_score,
            "data_completeness_level": completeness,
            "nova_score": nova_score,
            "nova_description": nova_description
        })

    except Exception as e:
        print("Error in /gtin-lookup:", str(e))
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
