# FILE: backend/ingredient_parser_service.py

# Temporary comment 2025-07-27 (You can remove this if it's not serving a purpose)
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
        load_fda_substances, # This will now load a map/dict
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
    print(f"❌ Error importing usda.py: {e}")
    sys.exit(1)


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


# --- Global data loading for ingredient_parser functions ---
# These variables must be defined here, outside the route functions,
# so they are loaded once when the app starts.
try:
    # Ensure these file paths are correct relative to DATA_DIR
    patterns_data = load_patterns(os.path.join(DATA_DIR, "ingredient_naming_patterns.json"))
    # Renamed from _set to _map for clarity, as it will now hold a dict/map
    fda_substances_map = load_fda_substances(os.path.join(DATA_DIR, "all_fda_substances_full_live.json"))
    # Ensure this points to common_ingredients_live.json (list of strings)
    common_ingredients_set = load_common_ingredients(os.path.join(DATA_DIR, "common_ingredients_live.json"))

    print("✅ All ingredient parser data loaded successfully.")
except Exception as e:
    print(f"❌ Error loading ingredient parser data: {e}")
    sys.exit(1)


@app.route('/gtin-lookup', methods=['POST'])
def gtin_lookup():
    try:
        data = request.get_json()
        gtin = data.get('gtin')

        if not gtin:
            return jsonify({"error": "GTIN is required"}), 400

        # 1. Fetch data from USDA
        fdc_id_from_map = gtin_to_fdc.get(gtin)
        if not fdc_id_from_map:
            return jsonify({"error": "GTIN not found in local map."}), 404

        usda_data = fetch_product_from_usda(fdc_id_from_map)

        if not usda_data:
            return jsonify({"error": f"Product not found for FDC ID {fdc_id_from_map} or USDA API error."}), 404

        fdc_id = usda_data.get('fdcId')
        brand_name = usda_data.get('brandName')
        brand_owner = usda_data.get('brandOwner')
        description = usda_data.get('description')
        ingredients_raw = usda_data.get('ingredients')

        if not ingredients_raw:
            return jsonify({"error": "No ingredients found for this product."}), 404

        # 2. Parse ingredients using the globally loaded data
        parsed_ingredients = parse_ingredient_string(
            ingredients_raw,
            patterns_data,
            common_ingredients_set,
            fda_substances_map # Pass the map here, not the set
        )
        print(f"DEBUG_SERVICE: Raw Ingredients: {ingredients_raw}")
        print(f"DEBUG_SERVICE: Parsed Ingredients (from service): {parsed_ingredients}") # ADD THIS LINE
        
        # 3. Categorize parsed ingredients
        parsed_fda_common, parsed_fda_non_common, parsed_common_only, truly_unidentified, all_fda_parsed_for_report = \
            categorize_parsed_ingredients(parsed_ingredients, fda_substances_map) # Pass the map here

        # 4. Calculate data completeness
        data_score, completeness = calculate_data_completeness(parsed_ingredients, truly_unidentified)

        # 5. Calculate NOVA score
        nova_score = calculate_nova_score(parsed_ingredients)
        nova_description = get_nova_description(nova_score)

        # 6. Generate Trust Report HTML
        trust_report_html = generate_trust_report_html(all_fda_parsed_for_report)

        # 7. Return response
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

# THIS BLOCK NEEDS TO BE DE-INDENTED TO THE SAME LEVEL AS 'app = Flask(__name__)'
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=os.getenv("PORT", 5001))