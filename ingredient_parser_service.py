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

# Conditional import for cache_manager, disabled for MVP
# from cache_manager import get_from_cache, write_to_cache, update_lookup_count

# Mock cache_manager functions for MVP (no-op)
# These mock functions will prevent errors if the calls are accidentally not commented out,
# and clearly signal that caching is disabled.
def get_from_cache(gtin):
    print(f"[Cache Manager - MOCKED] Attempted to read from cache for GTIN {gtin}. Caching is disabled for MVP.")
    return None

def write_to_cache(*args, **kwargs):
    print("[Cache Manager - MOCKED] Attempted to write to cache. Caching is disabled for MVP.")
    pass

def update_lookup_count(gtin):
    print(f"[Cache Manager - MOCKED] Attempted to update lookup count for GTIN {gtin}. Caching is disabled for MVP.")
    pass

# Import product lookup service and ingredient parser
from product_lookup_service import get_product_data_from_usda
from ingredient_parser import parse_ingredient_string, load_patterns, load_fda_substances, load_common_ingredients

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

# ✅ Load ingredient data on startup
# These are loaded once when the app starts
print("[Startup] Loading ingredient data...")
ingredient_patterns = load_patterns(os.path.join(DATA_DIR, "ingredient_naming_patterns.json"))
fda_substances_map = load_fda_substances(os.path.join(DATA_DIR, "all_fda_substances_full_live.json"))
common_ingredients_set = load_common_ingredients(os.path.join(DATA_DIR, "structured_common_ingredients_live.json"))
print("[Startup] Ingredient data loaded.")


@app.route('/')
def home():
    return "Smart Grocery Lens Backend is running!"

@app.route('/gtin-lookup', methods=['POST', 'OPTIONS'])
def gtin_lookup():
    if request.method == 'OPTIONS':
        # Pre-flight request. Reply successfully:
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', 'https://barcode-vercel-ten.vercel.app')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        return response

    data = request.json
    gtin = data.get('gtin')

    if not gtin:
        return jsonify({"error": "GTIN is required"}), 400

    print(f"Received GTIN: {gtin}")

    try:
        # Step 1: Check local GTIN map
        fdc_id = gtin_to_fdc.get(gtin)
        if not fdc_id:
            print(f"GTIN {gtin} not found in local map.")
            return jsonify({"error": "GTIN not found in local database. Please try a different product."}), 404

        # Step 2: Try to get from cache (DISABLED FOR MVP)
        # cached_data = get_from_cache(gtin)
        # if cached_data:
        #     print(f"Serving GTIN {gtin} from cache.")
        #     # Ensure fields that were stringified are parsed back
        #     if isinstance(cached_data.get('parsed_fda_non_common'), str):
        #         cached_data['parsed_fda_non_common'] = json.loads(cached_data['parsed_fda_non_common'])
        #     if isinstance(cached_data.get('parsed_fda_common'), str):
        #         cached_data['parsed_fda_common'] = json.loads(cached_data['parsed_fda_common'])
        #     if isinstance(cached_data.get('parsed_common_only'), str):
        #         cached_data['parsed_common_only'] = json.loads(cached_data['parsed_common_only'])
        #     if isinstance(cached_data.get('truly_unidentified_ingredients'), str):
        #         cached_data['truly_unidentified_ingredients'] = json.loads(cached_data['truly_unidentified_ingredients'])
        #     if isinstance(cached_data.get('parsed'), str):
        #         cached_data['parsed'] = json.loads(cached_data['parsed'])
        #
        #     # Regenerate HTML, as only raw data is cached
        #     fda_additives_for_report = [
        #         fda_substances_map.get(item.lower()) for item in cached_data['parsed_fda_common'] + cached_data['parsed_fda_non_common']
        #         if fda_substances_map.get(item.lower()) is not None
        #     ]
        #     trust_report_html = generate_trust_report_html(fda_additives_for_report)
        #     cached_data['trust_report_html'] = trust_report_html
        #
        #     # Update lookup count (DISABLED FOR MVP)
        #     # update_lookup_count(gtin)
        #     return jsonify(cached_data), 200

        # Step 3: Fetch from USDA if not in cache (or cache is disabled)
        print(f"Fetching data for FDC ID {fdc_id} from USDA...")
        product_data = get_product_data_from_usda(fdc_id)

        if not product_data:
            print(f"No data found for FDC ID {fdc_id} from USDA.")
            return jsonify({"error": f"Product data not found for FDC ID {fdc_id}."}), 404

        # Extract relevant fields
        brand_name = product_data.get('brand_name')
        brand_owner = product_data.get('brand_owner')
        description = product_data.get('description')
        ingredients_raw = product_data.get('ingredients')

        if not ingredients_raw:
            return jsonify({"error": "No ingredient list found for this product."}), 404

        # Parse ingredients
        parsed_result = parse_ingredient_string(
            ingredients_raw,
            ingredient_patterns,
            fda_substances_map,
            common_ingredients_set
        )

        parsed_ingredients = parsed_result['parsed']
        parsed_fda_non_common = parsed_result['parsed_fda_non_common']
        parsed_fda_common = parsed_result['parsed_fda_common']
        parsed_common_only = parsed_result['parsed_common_only']
        truly_unidentified = parsed_result['truly_unidentified']

        # Calculate data completeness score
        total_components = len(parsed_ingredients)
        identified_components = len(parsed_fda_non_common) + len(parsed_fda_common) + len(parsed_common_only)
        data_score = (identified_components / total_components) * 100 if total_components > 0 else 0

        if data_score >= 90:
            completeness = "High"
        elif data_score >= 70:
            completeness = "Medium"
        else:
            completeness = "Low"

        # Determine NOVA score and description (simplified for MVP)
        nova_score = 4 # Default to Ultra-Processed for MVP unless specific conditions dictate otherwise
        nova_description = "Ultra-Processed Food" # Default description

        # Example simple NOVA adjustment (can be expanded)
        # If no FDA additives and mostly common ingredients, could be minimally processed
        if not parsed_fda_non_common and not parsed_fda_common and len(parsed_common_only) > 0 and not truly_unidentified:
             nova_score = 1
             nova_description = "Unprocessed or minimally processed food"
        elif len(parsed_fda_common) > 0 or len(parsed_fda_non_common) > 0 : # presence of additives implies some processing
            # Further refinement needed for NOVA 2, 3 classifications
            pass


        # Generate Trust Report HTML
        # Prepare list of FDA additives that were actually found,
        # mapping them back to their full objects from fda_substances_map
        # This ensures we have 'used_for', 'other_names', etc. for HTML generation.
        found_fda_additives_for_report = []
        for ing_name in parsed_fda_common + parsed_fda_non_common:
            # Need to find the original full object from fda_substances_map using the lowercase name
            # The fda_substances_map now maps lowercase name/alias to the full object
            full_additive_obj = fda_substances_map.get(ing_name.lower())
            if full_additive_obj:
                found_fda_additives_for_report.append(full_additive_obj)

        trust_report_html = generate_trust_report_html(found_fda_additives_for_report)

        # Step 4: Write to cache (DISABLED FOR MVP)
        # write_to_cache(
        #     gtin=gtin,
        #     fdc_id=fdc_id,
        #     brand_name=brand_name,
        #     brand_owner=brand_owner,
        #     description=description,
        #     ingredients_raw=ingredients_raw,
        #     parsed_fda_non_common=json.dumps(parsed_fda_non_common), # Store as string
        #     parsed_fda_common=json.dumps(parsed_fda_common), # Store as string
        #     parsed_common_only=json.dumps(parsed_common_only), # Store as string
        #     truly_unidentified=json.dumps(truly_unidentified), # Store as string
        #     data_score=data_score,
        #     completeness=completeness,
        #     nova_score=nova_score,
        #     nova_description=nova_description,
        #     parsed=json.dumps(parsed_ingredients) # Store raw parsed list as string
        # )

        # Step 5: Update lookup count (DISABLED FOR MVP)
        update_lookup_count(gtin)


        # Return the comprehensive JSON response
        return jsonify({
            "gtin": gtin,
            "fdc_id": fdc_id,
            "brand_name": brand_name,
            "brand_owner": brand_owner,
            "description": description,
            "ingredients_raw": ingredients_raw,
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
    # This route is for testing cache writing if it were enabled.
    # It remains commented out as per MVP strategy.
    try:
        test_gtin = "999999999999"
        # The following lines are commented out because Airtable caching is deferred for MVP
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
        return jsonify({"message": "Cache write attempted (DISABLED FOR MVP). Check logs."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001) # Changed port to 5001 for consistency