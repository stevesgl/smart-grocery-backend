# FILE: backend/ingredient_parser_service.py

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
        load_common_fda_additives, # New import
        categorize_parsed_ingredients,
        calculate_data_completeness,
        calculate_nova_score,
        get_nova_description,
        load_ingredient_aliases
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

        # 1. Fetch data from USDA
        fdc_id_from_map = gtin_to_fdc.get(gtin)
        if not fdc_id_from_map:
            return jsonify({"error": "GTIN not found in local map."}), 404

        usda_data = fetch_product_from_usda(fdc_id_from_map)

        if not usda_data:
            return jsonify({"error": f"Product not found for FDC ID {fdc_id_from_map} or USDA API error."}), 404

        # Extract all relevant data from usda_data, with 'N/A' fallbacks for robustness
        fdc_id = usda_data.get('fdcId')
        brand_name = usda_data.get('brandName', 'N/A') # Use 'brandName' for the specific product brand
        brand_owner = usda_data.get('brandOwner', 'N/A')
        description = usda_data.get('description', 'N/A')
        ingredients_raw = usda_data.get('ingredients', 'N/A')

        if not ingredients_raw or ingredients_raw == 'N/A':
            return jsonify({"error": "No ingredients found for this product."}), 404

        # DEBUG: Print raw ingredients from USDA
        print(f"DEBUG_SERVICE: Raw Ingredients: {ingredients_raw}")

        # 2. Parse ingredients using the globally loaded data
        parsed_ingredients = parse_ingredient_string(
            ingredients_raw,
            patterns_data,
            ingredient_aliases_map
        )
        print(f"DEBUG_SERVICE: Parsed Ingredients (from service): {parsed_ingredients}")

        # 3. Categorize parsed ingredients using all loaded data
        parsed_fda_common, parsed_fda_non_common, parsed_common_only, truly_unidentified, all_fda_parsed_for_report = \
            categorize_parsed_ingredients(
                parsed_ingredients=parsed_ingredients,
                fda_substances_map=fda_substances_map,
                common_ingredients_set=common_ingredients_set,
                common_fda_additives_set=common_fda_additives_set
            )

        # 4. Calculate data completeness
        data_score, completeness = calculate_data_completeness(parsed_ingredients, truly_unidentified)

        # 5. Calculate NOVA score
        nova_score = calculate_nova_score(parsed_ingredients)
        nova_description = get_nova_description(nova_score)

        # 6. Generate Trust Report HTML
        # All parameters are now consistently derived from earlier in the function
        trust_report_html = generate_trust_report_html(
            product_name=description,
            brand_name=brand_name, # Correctly uses 'brandName' from USDA data
            ingredients_raw=ingredients_raw,
            parsed_ingredients=parsed_ingredients,
            parsed_fda_common=parsed_fda_common,
            parsed_fda_non_common=parsed_fda_non_common,
            parsed_common_only=parsed_common_only,
            truly_unidentified=truly_unidentified,
            data_completeness_score=data_score, # Corrected variable name
            data_completeness_level=completeness, # Corrected variable name
            nova_score=nova_score, # Corrected variable name
            nova_description=nova_description, # Corrected variable name
            all_fda_parsed_for_report=all_fda_parsed_for_report
        )
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
        print(f"❌ Error in /gtin-lookup for GTIN {gtin}: {str(e)}")
        import traceback
        traceback.print_exc() # Print full traceback for debugging
        return jsonify({"error": str(e)}), 500

# This block ensures the app runs when executed directly
if __name__ == '__main__':
    print("Running Flask app locally...")
    app.run(debug=True, host='0.0.0.0', port=os.environ.get('PORT', 5000)) # Use PORT env var or default 5000