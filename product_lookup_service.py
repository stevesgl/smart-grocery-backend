# product_lookup_service.py

from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
import sys

# Add the current directory to sys.path so we can import local modules
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

try:
    from ingredient_parser import (
        load_patterns,
        load_fda_substances,
        load_common_ingredients,
        parse_ingredient_string,
        normalize_string
    )
    print("✅ Successfully imported ingredient_parser functions.")
except ImportError as e:
    print(f"❌ Error importing ingredient_parser: {e}")
    sys.exit(1)

app = Flask(__name__)
CORS(app)  # Allow CORS for all routes

# --- Data Initialization ---

DATA_DIR = os.path.join(current_dir, "data")

PATTERNS_FILE_PATH = os.path.join(DATA_DIR, "ingredient_naming_patterns.json")
FDA_SUBSTANCES_FILE_PATH = os.path.join(DATA_DIR, "all_fda_substances_full_live.json")
COMMON_INGREDIENTS_FILE_PATH = os.path.join(DATA_DIR, "structured_common_ingredients_live.json")
GTIN_MAP_PATH = os.path.join(DATA_DIR, "gtin_map.json")

patterns_data = {}
fda_substances_set = set()
common_ingredients_set = set()
gtin_to_fdc = {}

try:
    patterns_data = load_patterns(PATTERNS_FILE_PATH)
    print(f"✅ Loaded patterns from {PATTERNS_FILE_PATH}")
except Exception as e:
    print(f"❌ Failed to load patterns: {e}")

try:
    fda_substances_set = load_fda_substances(FDA_SUBSTANCES_FILE_PATH)
    print(f"✅ Loaded FDA substances from {FDA_SUBSTANCES_FILE_PATH}")
except Exception as e:
    print(f"❌ Failed to load FDA substances: {e}")

try:
    common_ingredients_set = load_common_ingredients(COMMON_INGREDIENTS_FILE_PATH)
    print(f"✅ Loaded common ingredients from {COMMON_INGREDIENTS_FILE_PATH}")
except Exception as e:
    print(f"❌ Failed to load common ingredients: {e}")

try:
    with open(GTIN_MAP_PATH, "r") as f:
        gtin_to_fdc = json.load(f)
    print(f"✅ Loaded GTIN map from {GTIN_MAP_PATH}")
except Exception as e:
    print(f"❌ Failed to load GTIN map: {e}")

# --- API Routes ---

@app.route("/")
def index():
    return "✅ Ingredient Parser Backend is running!"

@app.route("/parse_ingredient", methods=["GET"])
def usage():
    return jsonify({
        "message": "POST a JSON payload with 'ingredient_string' to /parse_ingredient"
    }), 200

@app.route("/parse_ingredient", methods=["POST"])
def parse_ingredient():
    data = request.get_json()
    if not data or "ingredient_string" not in data:
        return jsonify({"error": "Missing 'ingredient_string' in request"}), 400

    ingredient_str = data["ingredient_string"]
    print(f"📥 Received ingredient string: {ingredient_str}")

    try:
        result = parse_ingredient_string(
            ingredient_str,
            patterns_data,
            common_ingredients_set,
            fda_substances_set
        )
        return jsonify(result)
    except Exception as e:
        print(f"❌ Error parsing ingredient: {e}")
        return jsonify({"error": "Parsing error"}), 500

@app.route("/gtin_lookup", methods=["POST"])
def lookup_gtin():
    data = request.get_json()
    if not data or "gtin" not in data:
        return jsonify({"error": "Missing 'gtin' in request"}), 400

    gtin = str(data["gtin"])
    fdc_id = gtin_to_fdc.get(gtin)

    if fdc_id:
        return jsonify({"fdc_id": fdc_id})
    else:
        return jsonify({"error": "GTIN not found in local map"}), 404

if __name__ == "__main__":
    app.run(debug=True, port=5000)
