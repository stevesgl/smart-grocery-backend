# app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
import sys

# Add the directory containing ingredient_parser.py to the Python path
# This assumes app.py and ingredient_parser.py are in the same directory.
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

try:
    # Import the parsing functions from your ingredient_parser.py
    from ingredient_parser import (
        load_patterns,
        load_fda_substances,
        load_common_ingredients, # Assuming this function exists and loads structured_common_ingredients_live.json
        parse_ingredient_string,
        normalize_string # Assuming this is also in your parser
    )
    print("Successfully imported ingredient_parser functions.")
except ImportError as e:
    print(f"Error importing ingredient_parser: {e}")
    print("Please ensure 'ingredient_parser.py' is in the same directory as 'app.py'.")
    sys.exit(1) # Exit if essential module cannot be imported

app = Flask(__name__)
CORS(app) # Enable CORS for all routes, allowing frontend to access

# --- Global Data Loading ---
# Load all necessary data once when the Flask app starts
print("Loading ingredient data (patterns, FDA substances, common ingredients)...")

# Define file paths relative to the 'data' subdirectory
DATA_DIR = os.path.join(current_dir, "data") # Path to the data directory

PATTERNS_FILE_PATH = os.path.join(DATA_DIR, "ingredient_naming_patterns.json")
FDA_SUBSTANCES_FILE_PATH = os.path.join(DATA_DIR, "all_fda_substances_full_live.json")
COMMON_INGREDIENTS_FILE_PATH = os.path.join(DATA_DIR, "structured_common_ingredients_live.json")


patterns_data = {}
fda_substances_set = set()
common_ingredients_set = set()

try:
    patterns_data = load_patterns(PATTERNS_FILE_PATH)
    print(f"Loaded patterns from: {PATTERNS_FILE_PATH}")
except Exception as e:
    print(f"Failed to load patterns from {PATTERNS_FILE_PATH}: {e}")

try:
    fda_substances_set = load_fda_substances(FDA_SUBSTANCES_FILE_PATH)
    print(f"Loaded FDA substances from: {FDA_SUBSTANCES_FILE_PATH}")
except Exception as e:
    print(f"Failed to load FDA substances from {FDA_SUBSTANCES_FILE_PATH}: {e}")

try:
    # Assuming load_common_ingredients returns a set of normalized ingredients
    # If your load_common_ingredients expects a different file, adjust here.
    common_ingredients_set = load_common_ingredients(COMMON_INGREDIENTS_FILE_PATH)
    print(f"Loaded common ingredients from: {COMMON_INGREDIENTS_FILE_PATH}")
except Exception as e:
    print(f"Failed to load common ingredients from {COMMON_INGREDIENTS_FILE_PATH}: {e}")

if not (patterns_data and fda_substances_set and common_ingredients_set):
    print("WARNING: One or more essential data files failed to load. Parsing might not work correctly.")

# --- API Endpoint ---
@app.route('/parse_ingredient', methods=['GET'])
def explain_usage():
    return jsonify({
        "message": "POST a JSON payload with 'ingredient_string' to this endpoint to receive parsed output."
    }), 200

@app.route('/parse_ingredient', methods=['POST'])
def parse_ingredient():
    """
    API endpoint to parse an ingredient string.
    Expects a JSON payload with a 'ingredient_string' key.
    Returns a JSON object with the parsed ingredient details.
    """
    data = request.get_json()
    if not data or 'ingredient_string' not in data:
        return jsonify({"error": "Missing 'ingredient_string' in request body"}), 400

    ingredient_str = data['ingredient_string']
    print(f"Received request to parse: '{ingredient_str}'")

    try:
        # Call the parsing function from your ingredient_parser.py
        # Ensure your parse_ingredient_string function accepts these arguments
        parsed_result = parse_ingredient_string(
            ingredient_str,
            patterns_data,
            common_ingredients_set,
            fda_substances_set
        )
        return jsonify(parsed_result)
    except Exception as e:
        print(f"Error parsing ingredient '{ingredient_str}': {e}")
        return jsonify({"error": f"Internal server error during parsing: {str(e)}"}), 500

@app.route('/')
def index():
    """
    Basic route to confirm the server is running.
    """
    return "Ingredient Parser Backend is running!"

if __name__ == '__main__':
    # Run the Flask app
    # In a production environment, you would use a WSGI server like Gunicorn or uWSGI
    print("Flask app starting... Go to http://127.0.0.1:5000/")
    app.run(debug=True, port=5000) # debug=True enables auto-reloading and better error messages
