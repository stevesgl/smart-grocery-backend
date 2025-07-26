# ingredient_parser_service.py

from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
import sys

# Initialize Flask app
app = Flask(__name__)

# ✅ Enable CORS for your Vercel frontend with support for preflight
CORS(app, resources={r"/*": {
    "origins": ["https://barcode-vercel-ten.vercel.app"],
    "methods": ["GET", "POST", "OPTIONS"]
}}, supports_credentials=True)

# ✅ Add current directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# ✅ Import parser logic
try:
    from ingredient_parser import (
        load_patterns,
        load_fda_substances,
        load_common_ingredients,
        parse_ingredient_string,
        normalize_string
    )
except Exception as e:
    print("Error importing ingredient_parser:", str(e))
    raise

# ✅ Load data once at startup
patterns_data = load_patterns()
fda_substances_set = load_fda_substances()
common_ingredients_set = load_common_ingredients()

# ✅ Health check
@app.route('/')
def home():
    return "Ingredient Parser Service is running."

# ✅ Handle GTIN product lookup POSTs
@app.route('/gtin-lookup', methods=['POST', 'OPTIONS'])
def gtin_lookup():
    if request.method == 'OPTIONS':
        # Preflight handled by flask-cors, but return early just in case
        return '', 204

    try:
        data = request.get_json()
        gtin = data.get("gtin")

        if not gtin:
            return jsonify({"error": "GTIN is required"}), 400

        # For now, simulate output
        ingredient_string = "sugar, water, natural flavor, red 40"
        parsed = parse_ingredient_string(
            ingredient_string, patterns_data, common_ingredients_set, fda_substances_set)

        return jsonify({
            "gtin": gtin,
            "ingredientsRaw": ingredient_string,
            "parsedIngredients": parsed
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ✅ Run only for local testing (not in production)
if __name__ == '__main__':
    app.run(debug=True)
