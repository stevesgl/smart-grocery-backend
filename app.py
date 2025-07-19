import os
import json
import re
from flask import Flask, request, jsonify
from flask_cors import CORS # Import Flask-Cors
import requests # For making HTTP requests to USDA
from airtable import Airtable # For interacting with Airtable
from pprint import pprint # Import pprint for pretty printing dictionaries

# --- Configuration ---
# Load environment variables for sensitive API keys and IDs
# In a production environment, these would be set as environment variables
# For local testing, you might load them from a .env file (e.g., using python-dotenv)
# For Render deployment, you'll set these in Render's environment variables.
AIRTABLE_API_KEY = os.environ.get('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = os.environ.get('AIRTABLE_BASE_ID')
AIRTABLE_TABLE_NAME = os.environ.get('AIRTABLE_TABLE_NAME', 'GTIN Cache') # Default table name
USDA_API_KEY = os.environ.get('USDA_API_KEY')

# Path to your full additives JSON file
# Assumes 'all_fda_substances_full.json' is in a 'data' subdirectory
ADDITIVES_DATA_FILE = os.path.join(os.path.dirname(__file__), 'data', 'all_fda_substances_full.json')

# --- Flask App Initialization ---
app = Flask(__name__)
# Enable CORS for all routes. This is the preferred way to handle CORS with Flask-Cors.
# In production, you might restrict this to your frontend's domain: CORS(app, resources={r"/api/*": {"origins": "https://your-frontend-domain.vercel.app"}})
CORS(app) 

# --- Global Additives Lookup Dictionary ---
# This dictionary will store our pre-processed additive data for fast lookups.
# It will be populated once when the Flask app starts.
ADDITIVES_LOOKUP = {}

# --- Data Loading Function for Additives ---
def load_additives_data():
    """
    Loads the additive data from the JSON file and builds the optimized lookup dictionary.
    This function should be called once at application startup.
    """
    global ADDITIVES_LOOKUP
    print(f"Attempting to load additives data from: {ADDITIVES_DATA_FILE}")
    try:
        with open(ADDITIVES_DATA_FILE, 'r', encoding='utf-8') as f:
            additives_raw = json.load(f)

        for entry in additives_raw:
            canonical_name = entry.get("Substance Name (Heading)")
            if not canonical_name:
                continue # Skip entries without a canonical name

            # Normalize the canonical name once
            normalized_canonical_name = re.sub(r'[^a-z0-9\s]', '', canonical_name.lower()).strip()
            normalized_canonical_name = re.sub(r'\s+', ' ', normalized_canonical_name)

            # Collect all names/aliases for this substance
            names_to_add = set()
            # Add Substance itself
            if entry.get("Substance"):
                names_to_add.add(entry.get("Substance"))
            # Add Substance Name (Heading)
            names_to_add.add(canonical_name)
            # Add Other Names
            names_to_add.update(entry.get("Other Names", []))

            for name in names_to_add:
                if name:
                    # Normalize each name/alias
                    normalized_alias = re.sub(r'[^a-z0-9\s]', '', name.lower()).strip()
                    normalized_alias = re.sub(r'\s+', ' ', normalized_alias) # Replace multiple spaces with single

                    if normalized_alias:
                        # Map the normalized alias to the normalized canonical name
                        ADDITIVES_LOOKUP[normalized_alias] = normalized_canonical_name

        print(f"✅ Successfully loaded {len(additives_raw)} additives and built lookup with {len(ADDITIVES_LOOKUP)} aliases.")
    except FileNotFoundError:
        print(f"❌ Error: Additives data file not found at '{ADDITIVES_DATA_FILE}'. Additive lookup will not work.")
    except json.JSONDecodeError as e:
        print(f"❌ Error decoding JSON from '{ADDITIVES_DATA_FILE}': {e}")
    except Exception as e:
        print(f"❌ An unexpected error occurred while loading additive data: {e}")

# Call the data loading function when the app starts
with app.app_context(): # Ensure app context for potential future Flask extensions
    load_additives_data()

# --- Ingredient Analysis Function ---
def analyze_ingredients(ingredients_string):
    """
    Analyzes an ingredient string to identify additives and calculate a trust score.
    """
    identified_substances = set() # Use a set to avoid duplicates
    unidentified_ingredients_tokens = set() # Use set for unique unidentified parts

    if not ingredients_string:
        return [], [], "High", 100.0 # No ingredients, assume 100% confidence

    # Normalize the entire input string for initial splitting
    # Keep commas and semicolons for splitting, but normalize spaces and lower case
    normalized_ingredients_string = ingredients_string.lower()
    # Replace common separators with a consistent delimiter for splitting
    normalized_ingredients_string = re.sub(r'[,;()]|\s*(?:and|or|contains)\s*', '|', normalized_ingredients_string)
    normalized_ingredients_string = re.sub(r'\s+', ' ', normalized_ingredients_string).strip()

    # Split into components based on the consistent delimiter
    components = [comp.strip() for comp in normalized_ingredients_string.split('|') if comp.strip()]

    total_analyzed_tokens = 0
    
    for component in components:
        # Normalize the component itself (remove non-alphanumeric except spaces)
        clean_component = re.sub(r'[^a-z0-9\s]', '', component).strip()
        clean_component = re.sub(r'\s+', ' ', clean_component) # Ensure single spaces

        if not clean_component:
            continue # Skip empty components

        total_analyzed_tokens += 1 # Count each non-empty component as a token for score calculation
        matched_in_component = False

        # Try matching multi-word phrases first, then single words from the component
        words = clean_component.split()
        
        # Iterate from longest possible phrase down to single words
        for i in range(len(words)):
            for j in range(len(words), i, -1): # j goes from len(words) down to i+1
                phrase = " ".join(words[i:j])
                if phrase in ADDITIVES_LOOKUP:
                    identified_substances.add(ADDITIVES_LOOKUP[phrase])
                    matched_in_component = True
                    break # Found a match, move to next component
            if matched_in_component:
                break
        
        if not matched_in_component:
            unidentified_ingredients_tokens.add(component) # Add the original (less cleaned) component if no part matched

    # Calculate Trust Score
    if total_analyzed_tokens == 0:
        trust_score_percentage = 100.0 # No identifiable components, but no additives found either
    else:
        identified_count = total_analyzed_tokens - len(unidentified_ingredients_tokens)
        # Ensure score is not negative or over 100
        trust_score_percentage = max(0.0, min(100.0, (identified_count / total_analyzed_tokens) * 100.0))

    # Convert score to High/Medium/Low (example thresholds, can be adjusted)
    if trust_score_percentage >= 90:
        confidence_level = "High"
    elif trust_score_percentage >= 70:
        confidence_level = "Medium"
    else:
        confidence_level = "Low"

    return list(identified_substances), list(unidentified_ingredients_tokens), confidence_level, trust_score_percentage

# --- Airtable Setup ---
# Initialize Airtable client
airtable = Airtable(AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME, api_key=AIRTABLE_API_KEY)

# --- Routes ---
@app.route('/')
def home():
    return "Backend is running. Use /api/gtin-lookup for GTIN lookups."

@app.route('/api/gtin-lookup', methods=['POST']) # Removed 'OPTIONS' as Flask-Cors handles it
def gtin_lookup():
    try:
        data = request.get_json()
        gtin = data.get('gtin')

        if not gtin:
            return jsonify({"error": "GTIN is required"}), 400

        # 1. Check Airtable Cache
        print(f"Checking cache for GTIN: {gtin}")
        try:
            # Airtable's formula for exact match on 'GTIN' field
            cached_record = airtable.search('GTIN', gtin)
            if cached_record:
                # Assuming 'cached_record' is a list and we take the first match
                product_data = cached_record[0]['fields']
                print(f"GTIN {gtin} found in cache.")
                print("DEBUG: Cached product_data from Airtable:")
                pprint(product_data) # DEBUG: Print the raw data from Airtable

                # Construct the response explicitly to ensure top-level fields
                response_data = {
                    "gtin": gtin,
                    "description": product_data.get('Description'),
                    "ingredients": product_data.get('Ingredients'),
                    "trust_report_markdown": product_data.get('Trust Report Markdown'),
                    "status": "found_in_cache"
                }
                print("DEBUG: Response data being sent for cached item:")
                pprint(response_data) # DEBUG: Print the final response data
                return jsonify(response_data)
        except Exception as e:
            print(f"Error checking Airtable cache: {e}")
            # Continue to USDA if cache check fails

        # 2. If not in cache, lookup from USDA FoodData Central
        print(f"GTIN {gtin} not in cache. Looking up from USDA...")
        usda_url = f"https://api.nal.usda.gov/fdc/v1/foods/search?api_key={USDA_API_KEY}&query={gtin}"
        
        response = requests.get(usda_url)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        usda_data = response.json()

        product_description = "N/A"
        product_ingredients = "N/A"
        
        # Parse USDA response to find product details
        if usda_data and usda_data.get('foods'):
            # Iterate through foods to find a match, prioritizing exact GTIN if possible
            for food in usda_data['foods']:
                if food.get('gtinUpc') == gtin:
                    product_description = food.get('description', 'N/A')
                    # Ingredients can be in different fields, common ones are 'ingredients' or 'householdServingFullText'
                    product_ingredients = food.get('ingredients', food.get('householdServingFullText', 'N/A'))
                    break # Found the product, exit loop

        if product_description == "N/A" and product_ingredients == "N/A":
            print(f"GTIN {gtin} not found in USDA.")
            return jsonify({"gtin": gtin, "status": "not_found", "message": "Product not found in USDA FoodData Central."})

        # --- New: Analyze Ingredients and Generate Trust Report ---
        identified_substances, unidentified_ingredients, confidence_level, trust_score_percentage = analyze_ingredients(product_ingredients)

        # Build the Trust Report in Markdown format
        trust_report_markdown = f"## GTIN: {gtin}  **Product:** {product_description}\n\n"
        trust_report_markdown += "### Identified Substances:\n"
        if identified_substances:
            for sub in identified_substances:
                trust_report_markdown += f"- {sub.title()}\n" # Capitalize for display
        else:
            trust_report_markdown += "- None identified from known additive list.\n"

        trust_report_markdown += "\n### Unidentified Ingredients:\n"
        if unidentified_ingredients:
            for unident in unidentified_ingredients:
                trust_report_markdown += f"- {unident.title()}\n" # Capitalize for display
        else:
            trust_report_markdown += "- All components matched known substances or were processed.\n"
        
        trust_report_markdown += f"\n### Trust Score:\n"
        trust_report_markdown += f"- **Confidence Level:** {confidence_level} ({trust_score_percentage:.1f}%)\n"
        trust_report_markdown += "_Explanation: This score reflects our certainty that all relevant ingredients were identified. A lower score indicates more unidentifiable words/phrases in the ingredient list, suggesting potential formatting issues or unknown substances._\n"

        # Placeholder for other sections (as per AI Coach's example)
        # You'll need to define how to get this data (e.g., from USDA response, or simple hardcoded for MVP)
        trust_report_markdown += "\n### Processing Level:\n"
        trust_report_markdown += "- Ultra-Processed (Nova 4)\n" # Placeholder, needs actual logic
        trust_report_markdown += "_Source: NOVA Classification System (Placeholder)_"

        trust_report_markdown += "\n### Ownership:\n"
        trust_report_markdown += "- PepsiCo\n" # Placeholder, needs actual logic
        trust_report_markdown += "_Source: AI-generated summary (Placeholder)_"

        trust_report_markdown += "\n### Origin:\n"
        trust_report_markdown += "- Likely U.S.-based manufacturing\n" # Placeholder, needs actual logic
        trust_report_markdown += "_Source: AI-generated (Placeholder)_"


        # 3. Write to Airtable Cache
        print(f"Caching GTIN {gtin} to Airtable...")
        try:
            airtable.insert({
                'GTIN': gtin,
                'Description': product_description,
                'Ingredients': product_ingredients,
                'Trust Report Markdown': trust_report_markdown # Store the full markdown report
            })
            print(f"GTIN {gtin} successfully cached.")
            # Construct the response explicitly to ensure top-level fields
            response_data = {
                "gtin": gtin,
                "description": product_description,
                "ingredients": product_ingredients,
                "trust_report_markdown": trust_report_markdown,
                "status": "pulled_from_usda_and_cached"
            }
            print("DEBUG: Response data being sent for new USDA item:")
            pprint(response_data) # DEBUG: Print the final response data
            return jsonify(response_data)
        except Exception as e:
            print(f"Error writing to Airtable cache for GTIN {gtin}: {e}")
            # Even if caching fails, return the product data to the user
            # Construct the response explicitly to ensure top-level fields
            response_data = {
                "gtin": gtin,
                "description": product_description,
                "ingredients": product_ingredients,
                "trust_report_markdown": trust_report_markdown,
                "status": "pulled_from_usda_no_cache"
            }
            print("DEBUG: Response data being sent when cache fails:")
            pprint(response_data) # DEBUG: Print the final response data
            return jsonify(response_data)

    except requests.exceptions.RequestException as e:
        print(f"Network or USDA API error: {e}")
        return jsonify({"error": "Failed to connect to USDA FoodData Central or network issue.", "details": str(e)}), 500
    except Exception as e:
        print(f"An unexpected error occurred in gtin_lookup: {e}")
        return jsonify({"error": "An internal server error occurred.", "details": str(e)}), 500

if __name__ == '__main__':
    # This block is for local development only. Render will run the app via Gunicorn or similar.
    # Ensure environment variables are set if running locally.
    if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, USDA_API_KEY]):
        print("WARNING: Missing one or more environment variables (AIRTABLE_API_KEY, AIRTABLE_BASE_ID, USDA_API_KEY).")
        print("Please set them for local testing or ensure they are configured on Render.")
    app.run(debug=True, host='0.0.0.0', port=os.environ.get('PORT', 5000))