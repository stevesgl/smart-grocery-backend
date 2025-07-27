from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
import sys

app = Flask(__name__)

from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
import sys
from airtable import Airtable

# Airtable helpers
def check_airtable_cache(gtin):
    airtable = Airtable(
        os.getenv("AIRTABLE_BASE_ID"),
        os.getenv("AIRTABLE_TABLE_NAME"),
        api_key=os.getenv("AIRTABLE_API_KEY")
    )
    records = airtable.search('gtin_upc', gtin)
    if records:
        fields = records[0].get('fields', {})
        cached = fields.get("data_report")
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                return cached  # fallback if it's already parsed
    return None

def update_airtable_cache(gtin, data_report):
    airtable = Airtable(
        os.getenv("AIRTABLE_BASE_ID"),
        os.getenv("AIRTABLE_TABLE_NAME"),
        api_key=os.getenv("AIRTABLE_API_KEY")
    )
    records = airtable.search('gtin_upc', gtin)
    json_report = json.dumps(data_report)
    if records:
        record_id = records[0]['id']
        airtable.update(record_id, {"gtin_upc": gtin, "data_report": json_report})
    else:
        airtable.insert({"gtin_upc": gtin, "data_report": json_report})

# Flask config
app = Flask(__name__)
CORS(app, resources={r"/*": {
    "origins": ["https://barcode-vercel-ten.vercel.app"],
    "methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type"]
}})

# Parser imports
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

# Load parsing data once
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

        # ✅ Check Airtable cache first
        cached_data = check_airtable_cache(gtin)
        if cached_data:
            return jsonify(cached_data)

        # 🔧 Fallback to stubbed parse until USDA product lookup is re-enabled
        ingredient_string = "sugar, water, natural flavor, red 40"

        parsed = parse_ingredient_string(
            ingredient_string, patterns_data, common_ingredients_set, fda_substances_set
        )

        response_data = {
            "gtin": gtin,
            "ingredientsRaw": ingredient_string,
            "parsedIngredients": parsed
        }

        # ✅ Save to Airtable
        update_airtable_cache(gtin, response_data)

        return jsonify(response_data)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
