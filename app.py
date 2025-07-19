import os
import json
import re # Import re for regex operations
from flask import Flask, request, jsonify
from flask_cors import CORS # Import Flask-Cors
import requests # For making HTTP requests to USDA
from airtable import Airtable # For interacting with Airtable
from datetime import datetime
from pprint import pprint # For debugging, can be removed later
import traceback # For printing full tracebacks

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
ADDITIVES_LOOKUP = {} # Maps normalized alias to normalized canonical FDA substance name
COMMON_INGREDIENTS_LOOKUP = {} # Maps normalized common ingredient to its preferred original casing
COMMON_FDA_SUBSTANCES_SET = set() # Stores normalized canonical FDA substance names that are also common ingredients

def load_data_lookups():
    """
    Loads the additive data and common ingredients data from JSON files
    and builds the optimized lookup dictionaries/sets.
    This function should be called once at application startup.
    """
    global ADDITIVES_LOOKUP, COMMON_INGREDIENTS_LOOKUP, COMMON_FDA_SUBSTANCES_SET

    # Load additive data
    print(f"[Backend Init] Attempting to load additives data from: {ADDITIVES_DATA_FILE}")
    try:
        with open(ADDITIVES_DATA_FILE, 'r', encoding='utf-8') as f:
            additives_raw = json.load(f)

        for entry in additives_raw:
            canonical_name = entry.get("Substance Name (Heading)")
            if not canonical_name:
                continue

            normalized_canonical_name_for_key = re.sub(r'[^a-z0-9\s\&\.\-#]', '', canonical_name.lower()).strip()
            normalized_canonical_name_for_key = re.sub(r'\s+', ' ', normalized_canonical_name_for_key)
            normalized_canonical_name_for_key = normalized_canonical_name_for_key.replace('no.', 'no ')

            names_to_add = set()
            if entry.get("Substance"):
                names_to_add.add(entry.get("Substance"))
            names_to_add.add(canonical_name)
            names_to_add.add(normalized_canonical_name_for_key)
            names_to_add.update(entry.get("Other Names", []))

            # --- Explicitly add common aliases for problematic cases ---
            # These aliases map to their respective canonical names
            if "fd&c red no 40" in normalized_canonical_name_for_key:
                names_to_add.add("red 40")
                names_to_add.add("red #40")
            if "fd&c yellow no 5" in normalized_canonical_name_for_key:
                names_to_add.add("yellow 5")
                names_to_add.add("yellow #5")
            if "fd&c blue no 1" in normalized_canonical_name_for_key:
                names_to_add.add("blue 1")
                names_to_add.add("blue #1")
            
            if "caramel" in normalized_canonical_name_for_key:
                names_to_add.add("caramel color")
            if "phosphoric acid" in normalized_canonical_name_for_key:
                names_to_add.add("phosphoric acid")
            if "sodium bicarbonate" in normalized_canonical_name_for_key:
                names_to_add.add("baking soda")
            if "sucrose" in normalized_canonical_name_for_key:
                names_to_add.add("sugar")
                names_to_add.add("cane sugar")
                names_to_add.add("pure cane sugar")
            if "sodium chloride" in normalized_canonical_name_for_key:
                names_to_add.add("salt")
            if "mono- and diglycerides" in normalized_canonical_name_for_key:
                names_to_add.add("mono and diglycerides")
            if "cellulose gum" in normalized_canonical_name_for_key:
                names_to_add.add("cellulose gum")
                names_to_add.add("carboxymethylcellulose")
                names_to_add.add("cmc")
            if "annatto" in normalized_canonical_name_for_key:
                names_to_add.add("annatto (color)")
            if "garlic" in normalized_canonical_name_for_key: # Explicitly add garlic related terms
                names_to_add.add("garlic")
                names_to_add.add("dehydrated garlic")
                names_to_add.add("garlic powder")


            for name in names_to_add:
                if name:
                    normalized_alias = re.sub(r'[^a-z0-9\s\&\.\-#\(\)]', '', name.lower()).strip()
                    normalized_alias = re.sub(r'\s+', ' ', normalized_alias)
                    normalized_alias = normalized_alias.replace('no.', 'no ')

                    if normalized_alias:
                        ADDITIVES_LOOKUP[normalized_alias] = normalized_canonical_name_for_key

        print(f"[Backend Init] ✅ Successfully loaded {len(additives_raw)} additives and built lookup with {len(ADDITIVES_LOOKUP)} aliases.")
        print(f"[Backend Init] DEBUG: 'garlic' in ADDITIVES_LOOKUP: {'garlic' in ADDITIVES_LOOKUP}")
        print(f"[Backend Init] DEBUG: Value for 'garlic': {ADDITIVES_LOOKUP.get('garlic')}")
        print(f"[Backend Init] DEBUG: 'sucrose' in ADDITIVES_LOOKUP: {'sucrose' in ADDITIVES_LOOKUP}")
        print(f"[Backend Init] DEBUG: Value for 'sucrose': {ADDITIVES_LOOKUP.get('sucrose')}")
        print(f"[Backend Init] DEBUG: 'sodium chloride' in ADDITIVES_LOOKUP: {'sodium chloride' in ADDITIVES_LOOKUP}")
        print(f"[Backend Init] DEBUG: Value for 'sodium chloride': {ADDITIVES_LOOKUP.get('sodium chloride')}")

    except FileNotFoundError:
        print(f"[Backend Init] ❌ Error: Additives data file not found at '{ADDITIVES_DATA_FILE}'. Additive lookup will not work.")
    except json.JSONDecodeError as e:
        print(f"[Backend Init] ❌ Error decoding JSON from '{ADDITIVES_DATA_FILE}': {e}")
    except Exception as e:
        print(f"[Backend Init] ❌ An unexpected error occurred while loading additive data: {e}")

    # Load common ingredients data
    print(f"[Backend Init] Attempting to load common ingredients data from: {COMMON_INGREDIENTS_DATA_FILE}")
    temp_common_ingredients_set = set() # Use a temporary set for initial loading
    try:
        with open(COMMON_INGREDIENTS_DATA_FILE, 'r', encoding='utf-8') as f:
            common_ingredients_raw = json.load(f)
        
        for ingredient in common_ingredients_raw:
            normalized_ingredient = re.sub(r'[^a-z0-9\s\&\.\-#\(\)]', '', ingredient.lower()).strip()
            normalized_ingredient = re.sub(r'\s+', ' ', normalized_ingredient)
            COMMON_INGREDIENTS_LOOKUP[normalized_ingredient] = ingredient # Keep mapping to original casing
            temp_common_ingredients_set.add(normalized_ingredient) # Add to temp set for intersection

        print(f"[Backend Init] ✅ Successfully loaded {len(common_ingredients_raw)} common ingredients into lookup.")
        print(f"[Backend Init] DEBUG: 'cottonseed' in COMMON_INGREDIENTS_LOOKUP: {'cottonseed' in COMMON_INGREDIENTS_LOOKUP}")
        print(f"[Backend Init] DEBUG: Value for 'cottonseed': {COMMON_INGREDIENTS_LOOKUP.get('cottonseed')}")
        print(f"[Backend Init] DEBUG: 'sunflower' in COMMON_INGREDIENTS_LOOKUP: {'sunflower' in COMMON_INGREDIENTS_LOOKUP}")
        print(f"[Backend Init] DEBUG: Value for 'sunflower': {COMMON_INGREDIENTS_LOOKUP.get('sunflower')}")
    except FileNotFoundError:
        print(f"[Backend Init] ❌ Error: Common ingredients data file not found at '{COMMON_INGREDIENTS_DATA_FILE}'. Common ingredient lookup will not work.")
    except json.JSONDecodeError as e:
        print(f"[Backend Init] ❌ Error decoding JSON from '{COMMON_INGREDIENTS_DATA_FILE}': {e}")
    except Exception as e:
        print(f"[Backend Init] ❌ An unexpected error occurred while loading common ingredient data: {e}")

    # Populate COMMON_FDA_SUBSTANCES_SET
    # Iterate through the canonical names (values) in ADDITIVES_LOOKUP
    # If a canonical name is also present in the normalized common ingredients set, add it
    for canonical_fda_name in set(ADDITIVES_LOOKUP.values()):
        if canonical_fda_name in temp_common_ingredients_set:
            COMMON_FDA_SUBSTANCES_SET.add(canonical_fda_name)
    print(f"[Backend Init] Populated COMMON_FDA_SUBSTANCES_SET with {len(COMMON_FDA_SUBSTANCES_SET)} entries.")
    print(f"[Backend Init] DEBUG: 'garlic' in COMMON_FDA_SUBSTANCES_SET: {'garlic' in COMMON_FDA_SUBSTANCES_SET}")
    print(f"[Backend Init] DEBUG: 'sucrose' in COMMON_FDA_SUBSTANCES_SET: {'sucrose' in COMMON_FDA_SUBSTANCES_SET}")
    print(f"[Backend Init] DEBUG: 'sodium chloride' in COMMON_FDA_SUBSTANCES_SET: {'sodium chloride' in COMMON_FDA_SUBSTANCES_SET}")
    print(f"[Backend Init] DEBUG: 'red 40' in COMMON_FDA_SUBSTANCES_SET: {'red 40' in COMMON_FDA_SUBSTANCES_SET}")


# Call load_data_lookups() immediately after app creation to ensure data is loaded when Gunicorn runs the app
load_data_lookups()

# --- Ingredient Analysis Function (Revised for Data Score and Phrase Matching) ---
def analyze_ingredients(ingredients_string):
    """
    Analyzes an ingredient string to identify FDA-regulated substances and common ingredients.
    Calculates a Data Score based on the completeness of identification.
    Returns categorized lists of ingredients for the four categories.
    """
    identified_fda_non_common = set() # New category 1
    identified_fda_common = set()      # New category 2
    identified_common_ingredients_only = set() # New category 3 (previously identified_common_ingredients)
    truly_unidentified_ingredients = set() # Category 4 (previously truly_unidentified_ingredients)

    if not ingredients_string:
        return [], [], [], [], 100.0, "High" # Adjusted return for new categories

    # Step 1: Initial cleanup and pre-processing
    cleaned_string = re.sub(r'^(?:ingredients|contains|ingredient list|ingredients list):?\s*', '', ingredients_string, flags=re.IGNORECASE).strip()
    cleaned_string = re.sub(r'\s+and/or\s+', ', ', cleaned_string, flags=re.IGNORECASE)
    cleaned_string = re.sub(r'\s*\((?:color|flavour|flavor|emulsifier|stabilizer|thickener|preservative|antioxidant|acidifier|sweetener|gelling agent|firming agent|nutrient|vitamin [a-z0-9]+)\)\s*', '', cleaned_string, flags=re.IGNORECASE)
    cleaned_string = re.sub(r'\s*\[vitamin b\d\]\s*', '', cleaned_string, flags=re.IGNORECASE)


    # Step 2: Extract content within parentheses and process separately
    parenthetical_matches = re.findall(r'\(([^()]*?(?:\([^()]*?\)[^()]*?)*?)\)', cleaned_string)
    main_components_string = re.sub(r'\([^()]*?(?:\([^()]*?\)[^()]*?)*?\)', '', cleaned_string).strip()

    # Step 3: Split main string into components by commas and semicolons
    components = [comp.strip() for comp in re.split(r',\s*|;\s*', main_components_string) if comp.strip()]
    
    for p_content in parenthetical_matches:
        sub_components = [s.strip() for s in re.split(r',\s*| and\s*', p_content) if s.strip()]
        components.extend(sub_components)

    components = [comp for comp in components if comp]

    total_analyzed_items = len(components)
    categorized_items_count = 0

    for original_component in components:
        normalized_component = original_component.lower().strip()
        normalized_component = re.sub(r'\s+', ' ', normalized_component)
        normalized_component = normalized_component.replace('no.', 'no ')
        normalized_component = normalized_component.rstrip('.,\'"').strip()

        print(f"[Analyze] DEBUG: Original: '{original_component}', Normalized: '{normalized_component}'")

        if not normalized_component:
            continue

        component_categorized = False
        
        # Pass 1: Try to match against FDA Additives (longest match first for phrases)
        words = normalized_component.split()
        matched_additive_canonical = None
        for i in range(len(words)):
            for j in range(len(words), i, -1):
                phrase = " ".join(words[i:j])
                if phrase in ADDITIVES_LOOKUP:
                    matched_additive_canonical = ADDITIVES_LOOKUP[phrase]
                    break
            if matched_additive_canonical:
                break
        
        if matched_additive_canonical:
            # Determine if this FDA substance is also considered a "common food substance"
            if matched_additive_canonical in COMMON_FDA_SUBSTANCES_SET:
                identified_fda_common.add(COMMON_INGREDIENTS_LOOKUP.get(matched_additive_canonical, original_component)) # Use original casing if available
            else:
                identified_fda_non_common.add(matched_additive_canonical)
            component_categorized = True
        else:
            # Pass 2: If not an FDA Additive, try to match against Common Ingredients (longest match first)
            matched_common_ingredient_original_casing = None
            for i in range(len(words)):
                for j in range(len(words), i, -1):
                    phrase = " ".join(words[i:j])
                    if phrase in COMMON_INGREDIENTS_LOOKUP:
                        # Ensure it's not an FDA substance that we already caught in Pass 1
                        # This check is important to prevent double-counting or miscategorization
                        if phrase not in ADDITIVES_LOOKUP or ADDITIVES_LOOKUP[phrase] not in COMMON_FDA_SUBSTANCES_SET:
                            matched_common_ingredient_original_casing = COMMON_INGREDIENTS_LOOKUP[phrase]
                            break
                if matched_common_ingredient_original_casing:
                    break

            if matched_common_ingredient_original_casing:
                identified_common_ingredients_only.add(matched_common_ingredient_original_casing)
                component_categorized = True
            else:
                # If still not categorized, it's truly unidentified
                truly_unidentified_ingredients.add(original_component)
        
        if component_categorized:
            categorized_items_count += 1

    # Calculate Data Score
    if total_analyzed_items == 0:
        data_score_percentage = 100.0
    else:
        data_score_percentage = (categorized_items_count / total_analyzed_items) * 100.0
        data_score_percentage = max(0.0, min(100.0, data_score_percentage))

    # Convert score to High/Medium/Low
    if data_score_percentage >= 90:
        data_completeness_level = "High"
    elif data_score_percentage >= 70:
        data_completeness_level = "Medium"
    else:
        data_completeness_level = "Low"

    # Return all four categorized lists, plus score and level
    return (list(identified_fda_non_common), list(identified_fda_common), 
            list(identified_common_ingredients_only), list(truly_unidentified_ingredients), 
            data_score_percentage, data_completeness_level)

# --- Data Report Generation ---
def generate_data_report_markdown(identified_fda_non_common, identified_fda_common, identified_common_ingredients_only, truly_unidentified_ingredients, data_score, data_completeness_level):
    """
    Generates a markdown-formatted data report for the product,
    now with four distinct categories.
    """
    report = "## Ingredient Data Report\n\n"
    report += f"**Data Score:** {data_score:.1f}% ({data_completeness_level})\n\n"
    report += "The Data Score indicates the percentage of ingredients our system could categorize.\n\n"

    # Category 1: FDA Substance Detected (Non-Common)
    report += "### FDA Substance Detected (Non-Common):\n"
    if identified_fda_non_common:
        for sub in sorted(identified_fda_non_common):
            report += f"* {sub.title()}\n"
    else:
        report += "* No specific FDA-regulated substances (additives) identified that are not also common food ingredients.\n"

    # Category 2: Common Food Substance Regulated by FDA
    report += "\n### Common Food Substance Regulated by FDA:\n"
    if identified_fda_common:
        for common_fda_sub in sorted(identified_fda_common):
            report += f"* {common_fda_sub.title()}\n"
    else:
        report += "* No common food ingredients identified that are explicitly regulated by the FDA as substances.\n"

    # Category 3: Common Food Ingredients (Not Explicitly FDA-Regulated as Additives)
    report += "\n### Common Food Ingredients (Not Explicitly FDA-Regulated as Additives):\n"
    if identified_common_ingredients_only:
        for common_ing in sorted(identified_common_ingredients_only):
            report += f"* {common_ing.title()}\n"
    else:
        report += "* No common food ingredients identified that are not also FDA-regulated substances.\n"

    # Category 4: Truly Unidentified Ingredients/Phrases
    report += "\n### Truly Unidentified Ingredients/Phrases:\n"
    if truly_unidentified_ingredients:
        report += "The following components were not matched against our database of FDA-regulated substances or common ingredients. This means our system couldn't fully categorize them. These could be:\n"
        report += "* **Complex phrasing** not yet fully parsed.\n"
        report += "* **Obscure ingredients** not yet in our database.\n"
        report += "* **Potential misspellings** from the label.\n\n"
        report += "We'll keep improving. The more you use, the better we get!!\n"
        for unident in sorted(truly_unidentified_ingredients):
            report += f"* {unident.title()}\n"
    else:
        report += "* All ingredient components were successfully categorized!\n"
    
    report += "\n---\n"
    report += "*Data Score reflects the percentage of parsed ingredient components that matched known FDA-regulated substances or common food ingredients.*"
    return report

# --- Airtable Cache Management Functions ---
def check_airtable_cache(gtin):
    """
    Checks if a GTIN exists in the Airtable cache.
    If found, it updates the lookup_count and last_access fields for that record.
    """
    if not airtable:
        print("[Render Backend] Airtable client not initialized. Skipping cache check.")
        return None
    
    print(f"[Render Backend] Checking Airtable cache for GTIN: {gtin}...")
    try:
        results = airtable.search('gtin_upc', gtin)
        
        if results:
            record = results[0]
            record_id = record['id']
            current_fields = record['fields']
            
            new_lookup_count = current_fields.get('lookup_count', 0) + 1
            new_last_access = datetime.now().isoformat()
            
            update_data = {
                'lookup_count': new_lookup_count,
                'last_access': new_last_access
            }
            
            airtable.update(record_id, update_data)
            print(f"[Render Backend] ✅ Found in Airtable cache. Updated lookup_count to {new_lookup_count}.")
            return current_fields
    except Exception as e:
        print(f"[Render Backend] ⚠️ Error in check_airtable_cache for GTIN {gtin}: {e}")
    return None

def fetch_from_usda_api(gtin):
    """
    Queries the USDA FoodData Central API using the GTIN.
    Returns the first matching food item's data if found, otherwise None.
    """
    if not USDA_API_KEY:
        print("[Render Backend] USDA API Key not set. Skipping USDA API fetch.")
        return None

    print(f"[Render Backend] Querying USDA API for GTIN: {gtin}...")
    params = {
        'query': gtin,
        'api_key': USDA_API_KEY,
        'dataType': ['Branded'],
        'pageSize': 1
    }
    
    try:
        response = requests.get(USDA_SEARCH_URL, params=params)
        response.raise_for_status()
        data = response.json()
        
        if data.get('foods'):
            print("[Render Backend] 📥 Pulled from USDA API.")
            return data['foods'][0]
    except requests.exceptions.RequestException as e:
        print(f"[Render Backend] ❌ Error fetching from USDA API for GTIN {gtin}: {e}")
    except json.JSONDecodeError:
        print(f"[Render Backend] ❌ JSON Decode Error from USDA API for GTIN {gtin}. Response: {response.text.strip()}")
    except Exception as e:
        print(f"[Render Backend] ❌ Unexpected Error fetching from USDA: {e}")
            
    return None

def store_to_airtable(gtin, usda_data, data_report_markdown):
    """
    Stores product data pulled from USDA API into the Airtable ca