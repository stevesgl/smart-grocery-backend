import os
import json
import re # Import re for regex operations
from flask import Flask, request, jsonify
from flask_cors import CORS # Import Flask-Cors
import requests # For making HTTP requests to USDA
from airtable import Airtable # For interacting with Airtable
from datetime import datetime
from pprint import pprint # For debugging, can be removed later

# --- Configuration ---
# Load environment variables for sensitive API keys and IDs
AIRTABLE_API_KEY = os.environ.get('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = os.environ.get('AIRTABLE_BASE_ID')
AIRTABLE_TABLE_NAME = os.environ.get('AIRTABLE_TABLE_NAME', 'GTIN Cache') # Default table name
USDA_API_KEY = os.environ.get('USDA_API_KEY')

# Path to your full additives JSON file
# Assumes 'all_fda_substances_full.json' is in a 'data' subdirectory relative to app.py
ADDITIVES_DATA_FILE = os.path.join(os.path.dirname(__file__), 'data', 'all_fda_substances_full.json')
# Path to your common ingredients JSON file
COMMON_INGREDIENTS_DATA_FILE = os.path.join(os.path.dirname(__file__), 'data', 'common_ingredients.json')

# Airtable max rows for the free tier (for eviction logic)
AIRTABLE_MAX_ROWS = 1000

# --- Flask App Initialization ---
app = Flask(__name__)
# Enable CORS for all routes. In production, you might restrict this to your frontend's domain.
CORS(app)

# Initialize Airtable client globally
airtable = None
if AIRTABLE_BASE_ID and AIRTABLE_TABLE_NAME and AIRTABLE_API_KEY:
    try:
        airtable = Airtable(AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME, AIRTABLE_API_KEY)
        print("Airtable client initialized successfully.")
    except Exception as e:
        print(f"Error initializing Airtable client: {e}")

# USDA API search URL
USDA_SEARCH_URL = 'https://api.nal.usda.gov/fdc/v1/foods/search'

# --- Global Lookups (will be populated once on app startup) ---
ADDITIVES_LOOKUP = {}
COMMON_INGREDIENTS_LOOKUP = {} # Changed to a dictionary for phrase matching and storing original casing

def load_data_lookups(): # Renamed from load_additives_data
    """
    Loads the additive data and common ingredients data from JSON files
    and builds the optimized lookup dictionaries/sets.
    This function should be called once at application startup.
    """
    global ADDITIVES_LOOKUP, COMMON_INGREDIENTS_LOOKUP

    # Load additive data
    print(f"Attempting to load additives data from: {ADDITIVES_DATA_FILE}")
    try:
        with open(ADDITIVES_DATA_FILE, 'r', encoding='utf-8') as f:
            additives_raw = json.load(f)

        for entry in additives_raw:
            canonical_name = entry.get("Substance Name (Heading)")
            if not canonical_name:
                continue # Skip entries without a canonical name

            # Normalize the canonical name once for lookup keys
            normalized_canonical_name = re.sub(r'[^a-z0-9\s\&\.\-#]', '', canonical_name.lower()).strip()
            normalized_canonical_name = re.sub(r'\s+', ' ', normalized_canonical_name)
            normalized_canonical_name = normalized_canonical_name.replace('no.', 'no ')

            names_to_add = set()
            if entry.get("Substance"):
                names_to_add.add(entry.get("Substance"))
            names_to_add.add(canonical_name)
            names_to_add.update(entry.get("Other Names", []))

            # --- Explicitly add common aliases for problematic cases ---
            if "fd&c red no 40" in normalized_canonical_name:
                names_to_add.add("red 40")
                names_to_add.add("red #40")
            if "fd&c yellow no 5" in normalized_canonical_name:
                names_to_add.add("yellow 5")
                names_to_add.add("yellow #5")
            if "fd&c blue no 1" in normalized_canonical_name:
                names_to_add.add("blue 1")
                names_to_add.add("blue #1")
            
            if "caramel" in normalized_canonical_name:
                names_to_add.add("caramel color")
            if "phosphoric acid" in normalized_canonical_name:
                names_to_add.add("phosphoric acid")
            if "sodium bicarbonate" in normalized_canonical_name:
                names_to_add.add("baking soda")
            if "sucrose" in normalized_canonical_name:
                names_to_add.add("sugar")
                names_to_add.add("cane sugar")
                names_to_add.add("pure cane sugar")
            if "sodium chloride" in normalized_canonical_name:
                names_to_add.add("salt")
            if "mono- and diglycerides" in normalized_canonical_name:
                names_to_add.add("mono and diglycerides")
            if "cellulose gum" in normalized_canonical_name:
                names_to_add.add("cellulose gum")
                names_to_add.add("carboxymethylcellulose")
                names_to_add.add("cmc")
            if "annatto" in normalized_canonical_name:
                names_to_add.add("annatto (color)")

            for name in names_to_add:
                if name:
                    normalized_alias = re.sub(r'[^a-z0-9\s\&\.\-#\(\)]', '', name.lower()).strip()
                    normalized_alias = re.sub(r'\s+', ' ', normalized_alias)
                    normalized_alias = normalized_alias.replace('no.', 'no ')

                    if normalized_alias:
                        ADDITIVES_LOOKUP[normalized_alias] = normalized_canonical_name

        print(f"✅ Successfully loaded {len(additives_raw)} additives and built lookup with {len(ADDITIVES_LOOKUP)} aliases.")
    except FileNotFoundError:
        print(f"❌ Error: Additives data file not found at '{ADDITIVES_DATA_FILE}'. Additive lookup will not work.")
    except json.JSONDecodeError as e:
        print(f"❌ Error decoding JSON from '{ADDITIVES_DATA_FILE}': {e}")
    except Exception as e:
        print(f"❌ An unexpected error occurred while loading additive data: {e}")

    # Load common ingredients data
    print(f"Attempting to load common ingredients data from: {COMMON_INGREDIENTS_DATA_FILE}")
    try:
        with open(COMMON_INGREDIENTS_DATA_FILE, 'r', encoding='utf-8') as f:
            common_ingredients_raw = json.load(f)
        
        for ingredient in common_ingredients_raw:
            normalized_ingredient = re.sub(r'[^a-z0-9\s\&\.\-#\(\)]', '', ingredient.lower()).strip()
            normalized_ingredient = re.sub(r'\s+', ' ', normalized_ingredient)
            COMMON_INGREDIENTS_LOOKUP[normalized_ingredient] = ingredient # Store original casing
        print(f"✅ Successfully loaded {len(common_ingredients_raw)} common ingredients into lookup.")
    except FileNotFoundError:
        print(f"❌ Error: Common ingredients data file not found at '{COMMON_INGREDIENTS_DATA_FILE}'. Common ingredient lookup will not work.")
    except json.JSONDecodeError as e:
        print(f"❌ Error decoding JSON from '{COMMON_INGREDIENTS_DATA_FILE}': {e}")
    except Exception as e:
        print(f"❌ An unexpected error occurred while loading common ingredient data: {e}")

# Call load_data_lookups() immediately after app creation to ensure data is loaded when Gunicorn runs the app
load_data_lookups() # Changed function name

# --- Ingredient Analysis Function (Revised for Data Score and Phrase Matching) ---
def analyze_ingredients(ingredients_string):
    """
    Analyzes an ingredient string to identify FDA-regulated substances and common ingredients.
    Calculates a Data Score based on the completeness of identification.
    Returns categorized lists of ingredients.
    """
    identified_fda_substances = set()
    identified_common_ingredients = set()
    truly_unidentified_ingredients = set()

    if not ingredients_string:
        return [], [], [], 100.0, "High" # No ingredients, assume 100% data completeness

    # Step 1: Initial cleanup and pre-processing
    cleaned_string = re.sub(r'^(?:ingredients|contains|ingredient list|ingredients list):?\s*', '', ingredients_string, flags=re.IGNORECASE).strip()
    cleaned_string = re.sub(r'\s+and/or\s+', ', ', cleaned_string, flags=re.IGNORECASE)

    # Remove common parenthetical descriptors that are not part of the substance name
    cleaned_string = re.sub(r'\s*\((?:color|flavour|flavor|emulsifier|stabilizer|thickener|preservative|antioxidant|acidifier|sweetener|gelling agent|firming agent|nutrient|vitamin [a-z0-9]+)\)\s*', '', cleaned_string, flags=re.IGNORECASE)
    cleaned_string = re.sub(r'\s*\[vitamin b\d\]\s*', '', cleaned_string, flags=re.IGNORECASE) # Remove [VITAMIN B#]


    # Step 2: Extract content within parentheses and process separately
    parenthetical_matches = re.findall(r'\(([^()]*?(?:\([^()]*?\)[^()]*?)*?)\)', cleaned_string)
    main_components_string = re.sub(r'\([^()]*?(?:\([^()]*?\)[^()]*?)*?\)', '', cleaned_string).strip()

    # Step 3: Split main string into components by commas and semicolons
    components = [comp.strip() for comp in re.split(r',\s*|;\s*', main_components_string) if comp.strip()]
    
    for p_content in parenthetical_matches:
        sub_components = [s.strip() 