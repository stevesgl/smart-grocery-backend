# Temporary comment 2025-07-27
from flask import Flask, request, jsonify
from flask_cors import CORS
from report_generator import generate_trust_report_html
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

# Import necessary functions from ingredient_parser
try:
    from ingredient_parser import (
        parse_ingredient_string,
        load_patterns,
        load_fda_substances,
        load_common_ingredients,
        categorize_parsed_ingredients,
        calculate_data_completeness,
        calculate_nova_score,
        get_nova_description
    )
    print("✅ Successfully imported ingredient_parser functions.")
except ImportError as e:
    print(f"❌ Error importing ingredient_parser: {e}")
    sys.exit(1)

# Import fetch_product_from_usda from usda.py
try:
    from usda import fetch_product_from_usda
    print("✅ Successfully imported fetch_product_from_usda from usda.py.")
except ImportError as e:
    print(f"❌ Error importing fetch_product_from_usda from usda.py: {e}")
    sys.exit(1)


# ✅ Load gtin_map.json with error fallback
DATA_DIR = os.path.join(current_dir, "data")
GTIN_MAP_PATH = os.path.join(DATA_DIR, "gtin_map.json")

try:
    with open(GTIN_MAP_PATH, "r") as f:
        gtin_to_fdc = json.load(f)
    print(f"✅ Loaded GTIN map from {GTIN_MAP_PATH}")
except FileNotFoundError:
    print(f"[Startup Error] gtin_map.json not found at: {GTIN_MAP_PATH}")
    gtin_to_fdc = {}
except json.JSONDecodeError as e:
    print(f"[Startup Error] Failed to decode gtin_map.json: {e}")
    gtin_to_fdc = {}

# Load parsing data
patterns_data = load_patterns(os.path.join(DATA_DIR, "ingredient_naming_patterns.json"))
fda_substances_data = load_fda_substances(os.path.join(DATA_DIR, "all_fda_substances_full_live.json"))
common_ingredients_set = load_common_ingredients(os.path.join(DATA_DIR, "structured_common_ingredients_live.json"))

# Mock cache manager for MVP (no-op functions)
# The cache_manager.py functions are no-ops for MVP to defer caching to MVP+1
from cache_manager import read_from_cache, write_to_cache

@app.route('/gtin-lookup', methods=['POST'])
def gtin_lookup():
    data = request.get_json()
    gtin = data.get('gtin')

    if not gtin:
        return jsonify({"error": "GTIN is required"}), 400

    print(f"📥 Received GTIN: {gtin}")

    # 1. Check local GTIN map
    fdc_id = gtin_to_fdc.get(gtin)
    if not fdc_id:
        print(f"🔍 GTIN {gtin} not found in local map.")
        return jsonify({
            "error": "Product not found",
            "message": "GTIN not in our current mapping. Try another one."
        }), 404

    # 2. Fetch data from USDA (caching is no-op for MVP)
    print(f"Calling USDA API for FDC ID: {fdc_id}")
    # Use fetch_product_from_usda from usda.py
    product_data = fetch_product_from_usda(fdc_id)

    if not product_data:
        print(f"❌ Failed to fetch product data for FDC ID: {fdc_id}")
        return jsonify({"error": "Failed to fetch product data from USDA"}), 500

    brand_name = product_data.get('brandName', 'N/A')
    brand_owner = product_data.get('brandOwner', 'N/A')
    description = product_data.get('description', 'N/A')
    ingredients_raw = product_data.get('ingredients', '')

    if not ingredients_raw:
        print(f"⚠️ No ingredients found for FDC ID: {fdc_id}")
        return jsonify({
            "description": description,
            "brand_name": brand_name,
            "brand_owner": brand_owner,
            "ingredients_raw": "No ingredients listed.",
            "parsed_ingredients": [],
            "trust_report_html": "<p class='text-sm text-gray-500'>No ingredients found to generate a Trust Report.</p>",
            "data_score": 0,
            "data_completeness_level": "Low",
            "nova_score": None,
            "nova_description": "N/A",
            "parsed_fda_common": [],
            "parsed_fda_non_common": [],
            "parsed_common_only": [],
            "truly_unidentified_ingredients": []
        })

    # 3. Parse and categorize ingredients
    print(f"⚙️ Parsing ingredients: {ingredients_raw[:100]}...") # Log first 100 chars
    parsed_ingredients = parse_ingredient_string(
        ingredients_raw,
        patterns_data,
        common_ingredients_set,
        fda_substances_data # Pass the full data for detailed lookup
    )

    (parsed_fda_common, parsed_fda_non_common, parsed_common_only, truly_unidentified) = \
        categorize_parsed_ingredients(parsed_ingredients, fda_substances_data)

    # 4. Calculate scores
    data_score, completeness = calculate_data_completeness(
        len(ingredients_raw.split(',')), # Simple count of comma-separated items
        len(parsed_fda_common) + len(parsed_fda_non_common) + len(parsed_common_only)
    )
    nova_score = calculate_nova_score(parsed_fda_non_common, truly_unidentified)
    nova_description = get_nova_description(nova_score)

    # 5. Generate Trust Report HTML
    # Combine all FDA-related parsed ingredients for the report
    all_fda_parsed_for_report = []
    for ingredient in parsed_fda_non_common + parsed_fda_common:
        # For each FDA-related ingredient, find its full data from fda_substances_data
        # This allows us to retrieve 'used_for' and 'other_names'
        original_name = ingredient.get("base_ingredient", "").lower()
        fda_detail = fda_substances_data.get(original_name)
        if fda_detail:
            all_fda_parsed_for_report.append({
                "name": fda_detail.get("name"),
                "used_for": fda_detail.get("used_for", []),
                "other_names": fda_detail.get("other_names", [])
            })
        else:
            # Fallback if for some reason detail isn't found (shouldn't happen if categorized correctly)
            all_fda_parsed_for_report.append({
                "name": ingredient.get("base_ingredient", "Unknown Additive"),
                "used_for": [],
                "other_names": []
            })


    trust_report_html = generate_trust_report_html(all_fda_parsed_for_report)


    # 6. Return response
    print(f"✅ Successfully processed GTIN {gtin}. Returning response.")
    return jsonify({
        "gtin": gtin,
        "fdc_id": fdc_id,
        "brand_name": brand_name,
        "brand_owner": brand_owner,
        "description": description,
        "ingredients_raw": ingredients_raw,
        "parsed_ingredients": parsed_ingredients,
        "parsed_fda_common": parsed_fda_common,
        "parsed_fda_non_common": parsed_fda_non_common,
        "parsed_common_only": parsed_common_only,
        "truly_unidentified_ingredients": truly_unidentified,
        "data_score": data_score,
        "data_completeness_level": completeness,
        "nova_score": nova_score,
        "nova_description": nova_description,
        "trust_report_html": trust_report_html
    })

except Exception as e:
    print("Error in /gtin-lookup:", str(e))
    return jsonify({"error": str(e)}), 500

@app.route('/test-write', methods=['GET'])
def test_write():
    try:
        test_gtin = "999999999999"
        # The write_to_cache function is a no-op in MVP, so this will just
        # print a message and return None. It won't actually write to Airtable.
        # As per 'onboarding_sgl_gtin_cache_072720251656.md', caching is deferred to MVP+1.
        # write_to_cache(
        #     gtin=test_gtin,
        #     fdc_id="000000",
        #     brand_name="Test Brand",
        #     brand_owner="Test Owner",
        #     description="This is a test description",
        #     ingredients_raw="SUGAR, SALT, TEST INGREDIENT",
        #     parsed_fda_non_common=json.dumps([{"name": "sugar"}]),
        #     parsed_fda_common=json.dumps([{"name": "salt"}]),
        #     parsed_common_only=json.dumps([{"name": "test ingredient"}]),
        #     truly_unidentified=json.dumps([]),
        #     data_score=1.0,
        #     completeness="High",
        #     nova_score=1,
        #     nova_description="Unprocessed or minimally processed",
        #     parsed=[{"base_ingredient": "sugar", "attributes": {"trust_report_category": "fda_non_common"}}]
        # )
        return jsonify({"message": f"Attempted to write test GTIN {test_gtin} to cache (no-op in MVP)."}), 200
    except Exception as e:
        print("Error in /test-write:", str(e))
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=os.getenv("PORT", 5001))