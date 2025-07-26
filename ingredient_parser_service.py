from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
import sys

app = Flask(__name__)

# ✅ Allow your Vercel frontend origin and all required methods
CORS(app, resources={r"/*": {
    "origins": ["https://barcode-vercel-ten.vercel.app"],
    "methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type"]
}})

# ✅ Import parser
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
except Exception as e:
    print("Import error:", str(e))
    raise

# ✅ Load once
patterns_data = load_patterns()
fda_substances_set = load_fda_substances()
common_ingredients_set = load_common_ingredients()

@app.route('/')
def home():
    return "Ingredient Parser Service is live."

@app.route('/gtin-lookup', methods=['POST', 'OPTIONS'])
def gtin_lookup():
    # ✅ Handle preflight
    if request.method == 'OPTIONS':
        return ('', 204)

    try:
        data = request.get_json()
        gtin = data.get("gtin")
        if not gtin:
            return jsonify({"error": "GTIN is required"}), 400

        # Stubbed ingredient string
        ingredient_string = "sugar, water, natural flavor, red 40"

        parsed = parse_ingredient_string(
            ingredient_string, patterns_data, common_ingredients_set, fda_substances_set
        )

        return jsonify({
            "gtin": gtin,
            "ingredientsRaw": ingredient_string,
            "parsedIngredients": parsed
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
