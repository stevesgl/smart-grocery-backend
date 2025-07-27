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

# ✅ Load data files once on startup
# Ensure fda_substances_map is correctly loaded as a dictionary
patterns_data = load_patterns(os.path.join(DATA_DIR, "ingredient_naming_patterns.json"))
fda_substances_map = load_fda_substances(os.path.join(DATA_DIR, "all_fda_substances_full_live.json"))
common_ingredients_set = load_common_ingredients(os.path.join(DATA_DIR, "structured_common_ingredients_live.json"))


@app.route('/gtin-lookup', methods=['POST'])
def gtin_lookup():
    try:
        data = request.get_json()
        gtin = data.get('gtin')

        if not gtin:
            return jsonify({"error": "GTIN is required"}), 400

        # Attempt to get from cache first (MVP+1 feature, currently bypassed)
        # For MVP, directly fetch from USDA
        # cached_product = get_cached_product(gtin)
        # if cached_product:
        #     # Ensure JSON strings from cache are parsed back to Python objects
        #     cached_product['parsed_fda_non_common'] = json.loads(cached_product['parsed_fda_non_common'])
        #     cached_product['parsed_fda_common'] = json.loads(cached_product['parsed_fda_common'])
        #     cached_product['parsed_common_only'] = json.loads(cached_product['parsed_common_only'])
        #     cached_product['truly_unidentified'] = json.loads(cached_product['truly_unidentified'])
        #     return jsonify(cached_product)

        # Fallback to USDA if not in cache or cache is bypassed for MVP
        fdc_id = gtin_to_fdc.get(gtin)
        if not fdc_id:
            return jsonify({"error": "GTIN not found in our current database."}), 404

        product_data = fetch_product_from_usda(fdc_id)

        if not product_data:
            return jsonify({"error": "Failed to fetch product data from USDA."}), 500

        ingredients_raw = product_data.get('ingredients_raw', '')
        brand_name = product_data.get('brand_name', 'Unknown Brand')
        brand_owner = product_data.get('brand_owner', 'Unknown Owner')
        description = product_data.get('description', 'No description available.')
        data_score = product_data.get('data_score', 0.0)
        completeness = product_data.get('data_completeness_level', 'Low')
        nova_score = product_data.get('nova_score', 4) # Default to 4 (ultra-processed)
        nova_description = product_data.get('nova_description', 'Ultra-Processed Food')


        # Parse ingredients
        parsed_ingredients_output = parse_ingredient_string(
            ingredients_raw,
            patterns_data,
            fda_substances_map, # Pass the correct map
            common_ingredients_set
        )

        parsed = parsed_ingredients_output['parsed']
        parsed_fda_non_common = parsed_ingredients_output['parsed_fda_non_common']
        parsed_fda_common = parsed_ingredients_output['parsed_fda_common']
        parsed_common_only = parsed_ingredients_output['parsed_common_only']
        truly_unidentified = parsed_ingredients_output['truly_unidentified']

        # Extract FDA additives for the report
        fda_additives_for_report = []
        for ing_name in parsed_fda_non_common + parsed_fda_common:
            # Ensure we're getting the full object from the map
            # It's important that parse_ingredient_string returns the actual substance name
            # that can be looked up in fda_substances_map
            fda_substance_obj = fda_substances_map.get(ing_name.lower())
            if fda_substance_obj:
                fda_additives_for_report.append({
                    "name": fda_substance_obj.get("name"),
                    "used_for": fda_substance_obj.get("used_for", []),
                    "other_names": fda_substance_obj.get("other_names", [])
                })


        # Generate Trust Report HTML
        trust_report_html = generate_trust_report_html(fda_additives_for_report)

        # Write to cache (MVP+1 feature, currently bypassed)
        # write_to_cache(
        #     gtin=gtin,
        #     fdc_id=fdc_id,
        #     brand_name=brand_name,
        #     brand_owner=brand_owner,
        #     description=description,
        #     ingredients_raw=ingredients_raw,
        #     # Store as JSON strings for caching
        #     parsed_fda_non_common=json.dumps(parsed_fda_non_common),
        #     parsed_fda_common=json.dumps(parsed_fda_common),
        #     parsed_common_only=json.dumps(parsed_common_only),
        #     truly_unidentified=json.dumps(truly_unidentified),
        #     data_score=data_score,
        #     completeness=completeness,
        #     nova_score=nova_score,
        #     nova_description=nova_description,
        #     parsed=json.dumps(parsed) # Store parsed list as JSON string
        # )

        # Update lookup count
        update_lookup_count(gtin)


        return jsonify({
            "gtin": gtin,
            "fdc_id": fdc_id,
            "brand_name": brand_name,
            "brand_owner": brand_owner,
            "description": description,
            "ingredients_raw": ingredients_raw,
            "parsed_ingredients": parsed, # This should be the list of parsed ingredient objects
            "parsed_fda_non_common": parsed_fda_non_common,
            "parsed_fda_common": parsed_fda_common,
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
        # Uncomment and modify to test caching if needed
        # write_to_cache(
        #     gtin=test_gtin,
        #     fdc_id="000000",
        #     brand_name="Test Brand",
        #     brand_owner="Test Owner",
        #     description="This is a test description",
        #     ingredients_raw="SUGAR, SALT, TEST INGREDIENT",
        #     parsed_fda_non_common=json.dumps(["sugar"]),
        #     parsed_fda_common=json.dumps(["salt"]),
        #     parsed_common_only=json.dumps(["test ingredient"]),
        #     truly_unidentified=json.dumps([]),
        #     data_score=1.0,
        #     completeness="High",
        #     nova_score=1,
        #     nova_description="Unprocessed or minimally processed",
        #     parsed=json.dumps([{"base_ingredient": "sugar", "attributes": {"trust_report_category": "fda_non_common"}}])
        # )
        return jsonify({"message": "Test write function (caching currently commented out)."}), 200
    except Exception as e:
        print("Error in /test-write:", str(e))
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=os.environ.get('PORT', 5001))