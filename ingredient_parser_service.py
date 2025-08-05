# FILE: backend/ingredient_parser_service.py

from flask import Flask, request, jsonify
from flask_cors import CORS
from report_generator import generate_trust_report_html
import json
import os
import sys
import datetime
from off_lookup import fetch_product_from_off, OFFProductNotFound

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
        load_common_fda_additives, # New import
        categorize_parsed_ingredients,
        calculate_data_completeness,
        calculate_nova_score,
        get_nova_description,
        load_ingredient_aliases,
        load_fda_additive_dict,
        load_fda_substance_dict,
        load_common_ingredient_dict,
        load_alias_dict
    )
    print("✅ Successfully imported ingredient_parser functions.")
except ImportError as e:
    print(f"❌ Error importing ingredient_parser: {e}")
    sys.exit(1)

# Import fetch_product_from_usda from usda.py (assuming usda.py exists and has this function)
try:
    from usda import fetch_product_from_usda
    print("✅ Successfully imported fetch_product_from_usda from usda.py.")
except ImportError as e:
    print(f"❌ Error importing usda.py: {e}")
    sys.exit(1)


# ✅ Load gtin_map.json with error fallback (Your existing logic for GTIN map)
DATA_DIR = os.path.join(current_dir, "data")
GTIN_MAP_PATH = os.path.join(DATA_DIR, "gtin_map.json")

try:
    with open(GTIN_MAP_PATH, "r") as f:
        gtin_to_fdc = json.load(f)
    print("✅ gtin_map.json loaded successfully.")
except FileNotFoundError:
    print(f"[Startup Error] gtin_map.json not found at: {GTIN_MAP_PATH}. Initializing empty map.")
    gtin_to_fdc = {}
except json.JSONDecodeError as e:
    print(f"[Startup Error] Failed to decode gtin_map.json: {e}. Initializing empty map.")
    gtin_to_fdc = {}
print(f"🔍 Loaded GTIN map keys: {list(gtin_to_fdc.keys())[:5]}")

# --- Global data loading for ingredient_parser functions ---
# These variables must be defined here, outside the route functions,
# so they are loaded once when the app starts.
try:
    # Call the load functions WITHOUT manually constructing absolute paths
    # as they handle relative paths internally to ingredient_parser.py
    patterns_data = load_patterns() # This uses default 'data/ingredient_naming_patterns.json' defined in ingredient_parser.py
    fda_substances_map = load_fda_substances() # This uses default 'data/all_fda_substances_full_live.json'
    common_ingredients_set = load_common_ingredients() # This uses default 'data/common_ingredients_live.json'
    common_fda_additives_set = load_common_fda_additives() # This uses default 'data/common_fda_additives.json'
    ingredient_aliases_map = load_ingredient_aliases()

    if not patterns_data or not fda_substances_map or not common_ingredients_set or not common_fda_additives_set or not ingredient_aliases_map:
        print("❌ Critical: Some essential parsing data failed to load. App may not function correctly.")
        sys.exit(1) # Exit if critical data isn't loaded
    else:
        print("✅ All ingredient parser data loaded successfully.")
except Exception as e:
    print(f"❌ Error loading ingredient parser data: {e}")
    sys.exit(1)

# ✅ Load dictionaries required for classify_ingredients()
fda_additive_dict = load_fda_additive_dict()
fda_substance_dict = load_fda_substance_dict()
common_ingredient_dict = load_common_ingredient_dict()
alias_dict = load_alias_dict()


@app.route('/')
def home():
    """Basic home route to confirm service is running."""
    return "Smart Grocery Backend Service is running!"

@app.route('/test-cache', methods=['GET'])
def test_cache():
    """
    A temporary endpoint to simulate writing to cache and confirm data structure.
    As per 'onboarding_sgl_gtin_cache_072720251656.md', caching is deferred to MVP+1.
    This function is a no-op in MVP, so it just prints a message and returns None.
    """
    test_gtin = "1234567890123" # Example GTIN
    print(f"Attempted to write test GTIN {test_gtin} to cache (no-op in MVP).")
    return jsonify({"message": f"Attempted to write test GTIN {test_gtin} to cache (no-op in MVP)."}), 200

@app.route('/gtin-lookup', methods=['POST'])
def gtin_lookup():
    try:
        data = request.get_json()
        gtin = data.get('gtin')

        if not gtin:
            return jsonify({"error": "GTIN is required"}), 400

        from off_lookup import fetch_product_from_off, OFFProductNotFound

        try:
            # 🌎 First try Open Food Facts
            off_data = fetch_product_from_off(gtin)
            description = off_data.get("description", "N/A")
            brand_name = off_data.get("brand_name", "N/A")
            brand_owner = "N/A"  # OFF doesn’t provide this consistently
            ingredients_raw = off_data.get("ingredients_string", "N/A")
            nova_score = off_data.get("nova_score", None)
            ingredients_parsed = off_data.get("ingredients_parsed", [])
            source = "OFF"
            fdc_id = None  # Not relevant for OFF
            print(f"✅ GTIN {gtin} found via Open Food Facts.")

        except OFFProductNotFound:
            print(f"ℹ️ GTIN {gtin} not found in OFF. Falling back to USDA...")

            fdc_id_from_map = gtin_to_fdc.get(gtin)
            if not fdc_id_from_map:
                return jsonify({"error": "GTIN not found in local map or OFF API."}), 404

            print(f"🔁 Fetching USDA product for FDC ID: {fdc_id_from_map}")

            usda_data = fetch_product_from_usda(fdc_id_from_map)
            if not usda_data:
                return jsonify({"error": f"Product not found for FDC ID {fdc_id_from_map} or USDA API error."}), 404

            description = usda_data.get('description', 'N/A')
            brand_name = usda_data.get('brandName', 'N/A')
            brand_owner = usda_data.get('brandOwner', 'N/A')
            ingredients_raw = usda_data.get('ingredients', 'N/A')
            nova_score = None  # USDA doesn't support NOVA
            ingredients_parsed = None  # No parsed output from USDA
            source = "USDA"
            fdc_id = usda_data.get('fdcId')

        # ✅ Continue with normal parsing pipeline
        if not ingredients_raw or ingredients_raw == 'N/A':
            return jsonify({"error": "No ingredients found for this product."}), 404

                # 🧪 Determine how to tokenize ingredients
        if source == "OFF" and ingredients_parsed:
            tokens_to_classify = [item["text"] for item in ingredients_parsed]
        else:
            tokens_to_classify = parse_ingredient_string(ingredients_raw, patterns_data)

        # 🧠 Classify each token
        classification_results = classify_ingredients(
            tokens_to_classify,
            fda_additive_dict,
            fda_substance_dict,
            common_ingredient_dict,
            alias_dict
        )

        # 📦 Group tokens by classification for Trust Report
        parsed_fda_additives = []
        parsed_common_ingredients = []
        parsed_unidentified = []

        for item in classification_results:
            classification = item.get("classification")
            if classification == "fda_additive":
                parsed_fda_additives.append(item)
            elif classification == "common_ingredient":
                parsed_common_ingredients.append(item)
            elif classification == "unidentified":
                parsed_unidentified.append(item)


        # 🧾 Generate final HTML Trust Report
        trust_report_html = generate_trust_report_html(
            product_name=description,
            brand_name=brand_name,
            brand_owner=brand_owner,
            ingredients_raw=ingredients_raw,
            parsed_ingredients=classification_results,  # actual results
            parsed_fda_common=parsed_fda_additives,      # additive section
            parsed_fda_non_common=[], 
            parsed_common_only=parsed_common_ingredients,
            truly_unidentified=parsed_unidentified,
            data_completeness_score=0.0,                 # Coming Soon
            data_completeness_level="Coming Soon",
            nova_score=nova_score or 0,
            nova_description=get_nova_description(nova_score or 0),
            all_fda_parsed_for_report=parsed_fda_additives  # For compatibility
        )


        # ✅ Return both HTML and classification JSON (for debugging if needed)
        return jsonify({
            "gtin": gtin,
            "fdc_id": fdc_id,
            "brand_name": brand_name,
            "brand_owner": brand_owner,
            "description": description,
            "ingredients_raw": ingredients_raw,
            "classification_results": classification_results,
            "nova_score": nova_score,
            "trust_report_html": trust_report_html
        }), 200

    except Exception as e:
        print(f"❌ Error in /gtin-lookup for GTIN {gtin}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

def classify_ingredients(tokens, fda_additive_dict, fda_substance_dict, common_ingredient_dict, alias_dict):
    results = []

    for token in tokens:
        if isinstance(token, dict) and "text" in token:
            original = token["text"].strip().lower()
        else:
            original = str(token).strip().lower()
            
        resolved = alias_dict.get(original, original)

        # Check all known dictionaries
        if resolved.upper() in fda_additive_dict:
            classification = "fda_additive"
        elif resolved.upper() in fda_substance_dict:
            classification = "fda_substance"
        elif resolved.lower() in common_ingredient_dict:
            classification = "common_ingredient"
        else:
            classification = "unidentified"

        results.append({
            "token": token,
            "resolved": resolved,
            "classification": classification
        })

    return results

# This block ensures the app runs when executed directly
if __name__ == '__main__':
    port = 5050
    print(f"🚀 Starting Flask app on http://127.0.0.1:{port}")
    app.run(debug=True, host='127.0.0.1', port=port)