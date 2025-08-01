import os
import json
import re  # Import re for regex operations
from flask import Flask, request, jsonify
from flask_cors import CORS # Import Flask-Cors, already there but ensuring correct usage
import requests  # For making HTTP requests to USDA
from airtable import Airtable  # For interacting with Airtable
from datetime import datetime, timedelta # Import timedelta for date calculations
from pprint import pprint  # For debugging, can be removed later
import traceback  # For printing full tracebacks
import time

# --- Configuration ---
# Load environment variables for sensitive API keys and IDs
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME = os.environ.get(
    "AIRTABLE_TABLE_NAME", "GTIN Cache"
)  # Default table name
USDA_API_KEY = os.environ.get("USDA_API_KEY")

# Paths to your data files
# Assumes data files are in a 'data' subdirectory relative to app.py
ADDITIVES_DATA_FILE = os.path.join(
    os.path.dirname(__file__), "data", "all_fda_substances_full.json"
)
COMMON_INGREDIENTS_DATA_FILE = os.path.join(
    os.path.dirname(__file__), "data", "common_ingredients.json"
)
GTIN_FDCID_MAP_FILE = os.path.join(
    os.path.dirname(__file__), "data", "gtin_map.json"
) # Path to your new GTIN-FDCID map

# Airtable max rows for the free tier (for eviction logic)
AIRTABLE_MAX_ROWS = 1000
FRESHNESS_WINDOW_DAYS = 7 # Define freshness window in days
FRESHNESS_BONUS = 5 # Define the bonus for fresh items

app = Flask(__name__)
# Configure CORS for all origins, allowing POST requests and Content-Type header
CORS(app, resources={r"/api/*": {"origins": "*"}}) # Explicitly allow all origins for API routes

# Initialize Airtable client globally
airtable = None
if AIRTABLE_BASE_ID and AIRTABLE_TABLE_NAME and AIRTABLE_API_KEY:
    try:
        airtable = Airtable(AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME, AIRTABLE_API_KEY)
        print("[Backend Init] Airtable client initialized successfully.")
    except Exception as e:
        print(f"[Backend Init] Error initializing Airtable client: {e}")

# USDA API base URL for FDC ID lookup (used for the reliable FDC ID lookup)
USDA_GET_FOOD_BY_FDCID_URL = 'https://api.nal.usda.gov/fdc/v1/food/'

# --- Global Lookups (will be populated once on app startup) ---
ADDITIVES_LOOKUP = {}  # Maps normalized alias to normalized canonical FDA substance name
COMMON_INGREDIENTS_LOOKUP = {}  # Maps normalized common ingredient to its preferred original casing
COMMON_FDA_SUBSTANCES_SET = set()  # Stores normalized canonical FDA substance names that are also common ingredients
GTIN_TO_FDCID_MAP = {} # New: Maps GTIN to FDC ID
FDA_SUBSTANCE_DETAILS = {} # New: Stores full details for FDA substances (used_for, other_names, cas_no)

# --- NEW: Mapping for Technical Effect Categories and Colors (more structured) ---
# This dictionary maps keywords found in "Used for (Technical Effect)" to
# a user-friendly category name and a Tailwind CSS color class.
# The order of entries here can matter if a phrase contains multiple keywords,
# as the first match will be used for that specific phrase segment.
TECHNICAL_EFFECT_CATEGORIES = {
    # Flavor & Aroma
    "FLAVORING AGENT": {"category": "Flavor & Aroma", "color": "bg-teal-100 text-teal-800"},
    "FLAVOR ENHANCER": {"category": "Flavor & Aroma", "color": "bg-teal-100 text-teal-800"},
    "FLAVORING AGENT OR ADJUVANT": {"category": "Flavor & Aroma", "color": "bg-teal-100 text-teal-800"}, # Added for completeness

    # Texture & Structure
    "STABILIZER": {"category": "Texture & Structure", "color": "bg-purple-100 text-purple-800"},
    "THICKENER": {"category": "Texture & Structure", "color": "bg-purple-100 text-purple-800"},
    "EMULSIFIER": {"category": "Texture & Structure", "color": "bg-purple-100 text-purple-800"},
    "EMULSIFIER OR EMULSIFIER SALT": {"category": "Texture & Structure", "color": "bg-purple-100 text-purple-800"}, # Added for completeness
    "TEXTURIZER": {"category": "Texture & Structure", "color": "bg-purple-100 text-purple-800"},
    "FIRMING AGENT": {"category": "Texture & Structure", "color": "bg-purple-100 text-purple-800"},
    "DOUGH STRENGTHENER": {"category": "Texture & Structure", "color": "bg-purple-100 text-purple-800"},
    "MASTICATORY SUBSTANCE": {"category": "Texture & Structure", "color": "bg-purple-100 text-purple-800"},
    "GELLING AGENT": {"category": "Texture & Structure", "color": "bg-purple-100 text-purple-800"}, # Corrected typo from GELTING

    # Preservation & Shelf Life
    "ANTIMICROBIAL": {"category": "Preservation", "color": "bg-blue-100 text-blue-800"},
    "ANTIOXIDANT": {"category": "Preservation", "color": "bg-blue-100 text-blue-800"},
    "PRESERVATIVE": {"category": "Preservation", "color": "bg-blue-100 text-blue-800"},
    "CURING": {"category": "Preservation", "color": "bg-blue-100 text-blue-800"},
    "PICKLING": {"category": "Preservation", "color": "bg-blue-100 text-blue-800"},


    # Nutrient & Sweetener
    "NUTRIENT SUPPLEMENT": {"category": "Nutrient/Sweetener", "color": "bg-lime-100 text-lime-800"},
    "SWEETENER": {"category": "Nutrient/Sweetener", "color": "bg-lime-100 text-lime-800"},
    "CORN SYRUP": {"category": "Nutrient/Sweetener", "color": "bg-lime-100 text-lime-800"}, # Specific for corn syrup

    # Color
    "COLOR": {"category": "Color", "color": "bg-rose-100 text-rose-800"},
    "COLOR OR COLORING ADJUNCT": {"category": "Color", "color": "bg-rose-100 text-rose-800"}, # Added for completeness

    # Processing & Formulation Aids (Catch-all for less specific or numerous roles)
    "PROCESSING AID": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "FORMULATION AID": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "ANTICAKING": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "ANTICAKING AGENT OR FREE-FLOW AGENT": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"}, # Added for completeness
    "FREE-FLOW AGENT": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "SOLVENT": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "SOLVENT OR VEHICLE": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"}, # Added for completeness
    "VEHICLE": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "PH CONTROL": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "PH CONTROL AGENT": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"}, # Added for completeness
    "ENZYME": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "SURFACE-ACTIVE": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "SURFACE-FINISHING": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "LUBRICANT": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "RELEASE AGENT": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "DRYING AGENT": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "LEAVENING AGENT": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "SEQUESTRANT": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "MALTING": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "FERMENTING AID": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "FLOUR TREATING": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "BOILER WATER ADDITIVE": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "PROPELLANT": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "WASHING": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "OXIDIZING": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "REDUCING AGENT": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "FUMIGANT": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "SYNERGIST": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "FREEZING": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "COOLING AGENT": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "DIRECT CONTACT": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "TRACER": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "PROCESSING": {"category": "Processing Aid", "color": "bg-gray-100 text-gray-800"},
    "MALTODEXTRIN": {"category": "Thickener", "color": "bg-purple-100 text-purple-800"}, # Specific for maltodextrin, now using structured format
}


def get_technical_effect_categories(raw_effects_string):
    """
    Parses a raw 'Used for (Technical Effect)' string and maps it to
    a list of user-friendly categories and their colors.
    """
    categories_found = []
    colors_found = []
    individual_technical_effects = [] # For detailed display if needed

    if not raw_effects_string:
        return [], [], []

    # Split by common delimiters and clean up
    individual_effect_phrases = re.split(r',\s*|<br\s*/>', raw_effects_string, flags=re.IGNORECASE)
    
    # Use sets to store unique categories and colors to avoid duplicates
    unique_categories = set()
    unique_colors = set()

    for phrase_raw in individual_effect_phrases:
        cleaned_phrase = phrase_raw.strip().upper() # Convert to uppercase for consistent matching

        # Find the category and color for this specific phrase
        phrase_category = "Other"
        phrase_color = "bg-gray-100 text-gray-800"
        matched = False

        # Iterate through the defined TECHNICAL_EFFECT_CATEGORIES to find a match.
        # Sort by length in reverse to match longer keywords first (e.g., "flavoring agent or adjuvant" before "flavoring agent").
        for keyword, details in sorted(TECHNICAL_EFFECT_CATEGORIES.items(), key=lambda item: len(item[0]), reverse=True):
            if keyword in cleaned_phrase:
                phrase_category = details["category"]
                phrase_color = details["color"]
                matched = True
                break
        
        # Add to main categories and colors lists (for the overall ingredient summary)
        if phrase_category not in unique_categories:
            categories_found.append(phrase_category)
            colors_found.append(phrase_color)
            unique_categories.add(phrase_category)
            unique_colors.add(phrase_color) # Also track unique colors

        # Add the individual technical effect with its determined category and color
        if phrase_raw: # Only add if the original phrase was not empty
            individual_technical_effects.append({
                "phrase": phrase_raw.strip(), # Keep original casing for display of phrase
                "category": phrase_category,
                "color": phrase_color
            })

    return categories_found, colors_found, individual_technical_effects


def load_data_lookups():
    """
    Loads all necessary lookup data (additives, common ingredients, GTIN-FDCID map)
    from JSON files and builds the optimized lookup dictionaries/sets.
    This function should be called once at application startup.
    """
    global ADDITIVES_LOOKUP, COMMON_INGREDIENTS_LOOKUP, COMMON_FDA_SUBSTANCES_SET, GTIN_TO_FDCID_MAP, FDA_SUBSTANCE_DETAILS

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
            if "garlic" in normalized_canonical_name_for_key:
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
            
            # Populate FDA_SUBSTANCE_DETAILS for this canonical name
            raw_used_for = entry.get("Used for (Technical Effect)", "").strip()
            categories, colors, individual_effects = get_technical_effect_categories(raw_used_for)

            FDA_SUBSTANCE_DETAILS[normalized_canonical_name_for_key] = {
                "original_name": canonical_name,
                "used_for_raw": raw_used_for,
                "used_for_categories": categories,
                "used_for_colors": colors, # Store colors directly for frontend
                "individual_technical_effects": individual_effects, # Store individual effects
                "other_names": entry.get("Other Names", []),
                "cas_no": entry.get("CAS Reg No (or other ID)", "")
            }


        print(f"[Backend Init] ✅ Successfully loaded {len(additives_raw)} additives and built lookup with {len(ADDITIVES_LOOKUP)} aliases.")

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
    except FileNotFoundError:
        print(f"[Backend Init] ❌ Error: Common ingredients data file not found at '{COMMON_INGREDIENTS_DATA_FILE}'. Common ingredient lookup will not work.")
    except json.JSONDecodeError as e:
        print(f"[Backend Init] ❌ Error decoding JSON from '{COMMON_INGREDIENTS_DATA_FILE}': {e}")
    except Exception as e:
        print(f"[Backend Init] ❌ An unexpected error occurred while loading common ingredient data: {e}")

    # Populate COMMON_FDA_SUBSTANCES_SET
    for canonical_fda_name in set(ADDITIVES_LOOKUP.values()):
        if canonical_fda_name in temp_common_ingredients_set:
            COMMON_FDA_SUBSTANCES_SET.add(canonical_fda_name)
    print(f"[Backend Init] Populated COMMON_FDA_SUBSTANCES_SET with {len(COMMON_FDA_SUBSTANCES_SET)} entries.")

    # New: Load GTIN-to-FDC ID map
    print(f"[Backend Init] Attempting to load GTIN-to-FDC ID map from: {GTIN_FDCID_MAP_FILE}")
    try:
        with open(GTIN_FDCID_MAP_FILE, 'r', encoding='utf-8') as f:
            GTIN_TO_FDCID_MAP = json.load(f)
        print(f"[Backend Init] ✅ Loaded {len(GTIN_TO_FDCID_MAP)} GTIN-to-FDC ID mappings.")
    except FileNotFoundError:
        print(f"[Backend Init] ❌ Error: GTIN-FDC ID map file not found at '{GTIN_FDCID_MAP_FILE}'. GTIN lookup by FDC ID will not work.")
    except json.JSONDecodeError as e:
        print(f"[Backend Init] ❌ Error decoding JSON from '{GTIN_FDCID_MAP_FILE}': {e}")
    except Exception as e:
        print(f"[Backend Init] ❌ An unexpected error occurred while loading GTIN-FDC ID map: {e}")


# Call load_data_lookups() immediately when the script is imported/run
load_data_lookups()


# --- NOVA Score Calculation Function ---
def calculate_nova_score(identified_fda_non_common, identified_fda_common, identified_common_ingredients_only, truly_unidentified_ingredients):
    """
    Estimates the NOVA score based on the categorized ingredient lists.

    NOVA Groups:
    1: Unprocessed or Minimally Processed Foods (primarily identified_common_ingredients_only)
    2: Processed Culinary Ingredients (primarily identified_fda_common, e.g., salt, sugar, oil)
    3: Processed Foods (combination of Group 1 and Group 2 ingredients)
    4: Ultra-Processed Foods (presence of identified_fda_non_common, or a high number of additives/unidentified)
    """

    # Rule 1: If any "FDA Substance Detected (Non-Common)" is present, it's NOVA 4.
    if identified_fda_non_common:
        return 4, "Ultra-Processed Food"

    # Rule 2: If there are truly unidentified ingredients, it leans towards NOVA 4 due to complexity/obscurity
    if truly_unidentified_ingredients:
        if len(truly_unidentified_ingredients) > 2: # Heuristic: more than 2 unidentified ingredients
            return 4, "Ultra-Processed Food (Unidentified Ingredients)"

    # Rule 3: If no non-common FDA substances, and no significant unidentified,
    # check for combinations of common ingredients and common FDA-regulated substances.
    # This implies NOVA 3 (Processed Food).
    if (identified_common_ingredients_only and identified_fda_common) or \
       (len(identified_common_ingredients_only) > 0 and not identified_fda_common and not identified_fda_non_common and not truly_unidentified_ingredients):
        if identified_fda_common and identified_common_ingredients_only:
            return 3, "Processed Food"
        if len(identified_common_ingredients_only) > 1 and not identified_fda_common and not identified_fda_non_common and not truly_unidentified_ingredients:
             return 3, "Processed Food (Simple Combination)"

    # Rule 4: If only common FDA-regulated substances (like salt, sugar, oil) are present, it's NOVA 2.
    if identified_fda_common and not identified_common_ingredients_only and not truly_unidentified_ingredients:
        return 2, "Processed Culinary Ingredient"

    # Rule 5: If only common ingredients (like water, milk, fresh produce) are present, it's NOVA 1.
    if identified_common_ingredients_only and not identified_fda_common and not identified_fda_non_common and not truly_unidentified_ingredients:
        if len(identified_common_ingredients_only) == 1:
            return 1, "Unprocessed or Minimally Processed Food"
        return 1, "Unprocessed or Minimally Processed Food"

    # Fallback for empty ingredient list or very minimal products not fitting above rules
    if not identified_fda_non_common and not identified_fda_common and not identified_common_ingredients_only and not truly_unidentified_ingredients:
        return 1, "Unprocessed or Minimally Processed Food (No Ingredients Listed)"

    return 3, "Processed Food (Categorization Ambiguous)"


# --- Ingredient Analysis Function (Revised for Data Score and Phrase Matching) ---
def analyze_ingredients(ingredients_string):
    """
    Analyzes an ingredient string to identify FDA-regulated substances and common ingredients.
    Calculates a Data Score based on the completeness of identification.
    Returns categorized lists of ingredients for the four categories, plus estimated NOVA score.
    """
    print(f"[Analyze] Starting analysis for ingredients string: {ingredients_string[:100]}...")

    identified_fda_non_common = [] # Changed to list to store dictionaries
    identified_fda_common = []     # Changed to list to store dictionaries
    identified_common_ingredients_only = set()
    truly_unidentified_ingredients = set()

    if not ingredients_string:
        nova_score, nova_description = calculate_nova_score([], [], [], [])
        print(f"[Analyze] No ingredients string. Returning default. NOVA: {nova_score}")
        return [], [], [], [], 100.0, "High", nova_score, nova_description

    # Step 1: Initial cleanup and pre-processing
    cleaned_string = re.sub(r'^(?:ingredients|contains|ingredient list|ingredients list):?\s*', '', ingredients_string, flags=re.IGNORECASE).strip()
    cleaned_string = re.sub(r'\s+and/or\s+', ', ', cleaned_string, flags=re.IGNORECASE)
    cleaned_string = re.sub(r'\s*\((?:color|flavour|flavor|emulsifier|stabilizer|thickener|preservative|antioxidant|acidifier|sweetener|gelling agent|firming agent|nutrient|vitamin [a-z0-9]+)\)\s*', '', cleaned_string, flags=re.IGNORECASE)
    cleaned_string = re.sub(r'\s*\[vitamin b\d\]\s*', '', cleaned_string, flags=re.IGNORECASE)
    print(f"[Analyze] Cleaned string: {cleaned_string[:100]}...")


    # Step 2: Extract content within parentheses and process separately
    parenthetical_matches = re.findall(r'\(([^()]*?(?:\([^()]*?\)[^()]*?)*?)\)', cleaned_string)
    main_components_string = re.sub(r'\([^()]*?(?:\([^()]*?\)[^()]*?)*?\)', '', cleaned_string).strip()

    # Step 3: Split main string into components by commas and semicolons
    components = [comp.strip() for comp in re.split(r',\s*|;\s*', main_components_string) if comp.strip()]

    for p_content in parenthetical_matches:
        sub_components = [s.strip() for s in re.split(r',\s*| and\s*', p_content) if s.strip()]
        components.extend(sub_components)

    components = [comp for comp in components if comp]
    print(f"[Analyze] Extracted components: {components}")

    total_analyzed_items = len(components)
    categorized_items_count = 0

    # Create a quick lookup for additive details by canonical name
    # This map is now populated directly in load_data_lookups from FDA_SUBSTANCE_DETAILS
    print(f"[Analyze] Using FDA_SUBSTANCE_DETAILS map with {len(FDA_SUBSTANCE_DETAILS)} entries.")


    for original_component in components:
        normalized_component = original_component.lower().strip()
        normalized_component = re.sub(r'\s+', ' ', normalized_component)
        normalized_component = normalized_component.replace('no.', 'no ')
        normalized_component = normalized_component.rstrip('.,\'"').strip()

        if not normalized_component:
            continue

        component_categorized = False

        # Pass 1: Try to match against FDA Additives (longest match first for phrases)
        matched_additive_canonical = None
        # Iterate through TECHNICAL_EFFECT_CATEGORIES to prioritize matching based on common effect terms
        # This helps in cases where the ingredient name itself might be generic but its effect is specific
        # We need to find the canonical name from ADDITIVES_LOOKUP for the full component or a phrase within it.
        # This logic is slightly complex as it needs to link a phrase match to a canonical name and then to FDA_SUBSTANCE_DETAILS.

        # First, try direct match or longest phrase match from ADDITIVES_LOOKUP
        words = normalized_component.split()
        for i in range(len(words)):
            for j in range(len(words), i, -1):
                phrase = " ".join(words[i:j])
                if phrase in ADDITIVES_LOOKUP:
                    matched_additive_canonical = ADDITIVES_LOOKUP[phrase]
                    break
            if matched_additive_canonical:
                break
        
        if matched_additive_canonical:
            # Retrieve full details from FDA_SUBSTANCE_DETAILS
            substance_details = FDA_SUBSTANCE_DETAILS.get(matched_additive_canonical, {})
            
            ingredient_obj = {
                "name": original_component, # Keep original casing from ingredient list
                "canonical_name": substance_details.get("original_name", matched_additive_canonical),
                "used_for_raw": substance_details.get("used_for_raw", "N/A"),
                "used_for_categories": substance_details.get("used_for_categories", []),
                "used_for_colors": substance_details.get("used_for_colors", []),
                "individual_technical_effects": substance_details.get("individual_technical_effects", []), # Use pre-analyzed individual effects
                "other_names": substance_details.get("other_names", []),
                "cas_no": substance_details.get("cas_no", "N/A")
            }

            if matched_additive_canonical in COMMON_FDA_SUBSTANCES_SET:
                identified_fda_common.append(ingredient_obj)
                print(f"[Analyze] Identified FDA Common: {original_component} (Categories: {ingredient_obj['used_for_categories']})")
            else:
                identified_fda_non_common.append(ingredient_obj)
                print(f"[Analyze] Identified FDA Non-Common: {original_component} (Categories: {ingredient_obj['used_for_categories']})")
            component_categorized = True
        else:
            # Pass 2: If not an FDA Additive, try to match against Common Ingredients (longest match first)
            matched_common_ingredient_original_casing = None
            words = normalized_component.split()
            for i in range(len(words)):
                for j in range(len(words), i, -1):
                    phrase = " ".join(words[i:j])
                    if phrase in COMMON_INGREDIENTS_LOOKUP:
                        # Ensure it's not an FDA substance that we already caught in Pass 1
                        if phrase not in ADDITIVES_LOOKUP or ADDITIVES_LOOKUP[phrase] not in COMMON_FDA_SUBSTANCES_SET:
                            matched_common_ingredient_original_casing = COMMON_INGREDIENTS_LOOKUP[phrase]
                            break
                if matched_common_ingredient_original_casing:
                    break

            if matched_common_ingredient_original_casing:
                identified_common_ingredients_only.add(matched_common_ingredient_original_casing)
                print(f"[Analyze] Identified Common Only: {original_component}")
                component_categorized = True
            else:
                truly_unidentified_ingredients.add(original_component)
                print(f"[Analyze] Identified Unidentified: {original_component}")

        if component_categorized:
            categorized_items_count += 1

    # Convert sets to lists for consistent return type
    identified_common_ingredients_only_list = list(identified_common_ingredients_only)
    truly_unidentified_ingredients_list = list(truly_unidentified_ingredients)

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

    # Calculate NOVA score - CORRECTED ARGUMENT ORDER HERE
    nova_score, nova_description = calculate_nova_score(
        identified_fda_non_common, # This is correct
        identified_fda_common,     # This is correct
        identified_common_ingredients_only_list, # Corrected
        truly_unidentified_ingredients_list      # Corrected
    )
    print(f"[Analyze] Analysis complete. Data Score: {data_score_percentage}%, NOVA: {nova_score}")
    print(f"[Analyze] FDA Non-Common ({len(identified_fda_non_common)}): {identified_fda_non_common}")
    print(f"[Analyze] FDA Common ({len(identified_fda_common)}): {identified_fda_common}")


    return (identified_fda_non_common, identified_fda_common,
            identified_common_ingredients_only_list, truly_unidentified_ingredients_list,
            data_score_percentage, data_completeness_level, nova_score, nova_description)

def check_airtable_cache(gtin):
    """
    Checks if a GTIN exists in the Airtable cache.
    If found, updates lookup count and last access timestamp.
    Returns the raw fields from Airtable if found, otherwise None.
    """
    if not airtable:
        print("[Backend] Airtable not initialized. Skipping cache check.")
        return None

    print(f"[Backend] Checking Airtable cache for GTIN: {gtin}")
    try:
        records = airtable.search('gtin_upc', gtin)
        if records:
            record = records[0]
            record_id = record['id']
            fields = record['fields']

            # Update usage stats: increment lookup_count and update last_access
            updated_fields = {
                'lookup_count': fields.get('lookup_count', 0) + 1,
                'last_access': datetime.now().isoformat()
            }
            airtable.update(record_id, updated_fields)
            print(f"[Backend] ✅ Cache hit. Updated lookup_count: {updated_fields['lookup_count']}")

            # Return the full fields, which now include the individual ingredient lists, NOVA, etc.
            # Ensure JSON strings are loaded back into Python objects.
            for key in ['identified_fda_non_common', 'identified_fda_common', 
                         'identified_common_ingredients_only', 'truly_unidentified_ingredients']:
                if key in fields:
                    field_data = fields[key]
                    if isinstance(field_data, str):
                        try:
                            fields[key] = json.loads(field_data)
                        except json.JSONDecodeError:
                            print(f"[Backend] ⚠️ Error decoding JSON for field '{key}' from cache. Setting to empty list.")
                            fields[key] = [] # Default to empty list on error
                    elif not isinstance(field_data, list):
                        # If it's not a string and not already a list, default to empty list
                        print(f"[Backend] ⚠️ Unexpected type for field '{key}' in cache ({type(field_data).__name__}). Setting to empty list.")
                        fields[key] = []
            
            # Ensure nova_score is an int/float if it was stored as string
            if 'nova_score' in fields and isinstance(fields['nova_score'], str):
                try:
                    fields['nova_score'] = int(fields['nova_score'])
                except ValueError:
                    pass # Keep as string if not convertible to int

            return fields
        else:
            print("[Backend] Cache miss.")
    except Exception as e:
        print(f"[Backend] ⚠️ Airtable lookup error: {e}")
    return None

def fetch_from_usda_api(gtin):
    """
    NEW: Looks up FDC ID for a given GTIN in the local map,
    then fetches product details from USDA API using the FDC ID.
    This replaces the unreliable direct GTIN search on USDA API.
    """
    if not USDA_API_KEY:
        print("[Render Backend] USDA API Key not set. Cannot fetch from USDA API.")
        return None

    # Step 1: Look up FDC ID in the local GTIN_TO_FDCID_MAP
    fdc_id = GTIN_TO_FDCID_MAP.get(gtin)

    if not fdc_id:
        print(f"[Render Backend] ❌ GTIN '{gtin}' not found in local GTIN-FDC ID map. Cannot proceed with FDC ID lookup.")
        return None

    print(f"[Render Backend] ✅ GTIN '{gtin}' mapped to FDC ID: '{fdc_id}' locally. Querying USDA API by FDC ID...")

    # Step 2: Fetch product details from USDA API using the FDC ID
    api_url = f"{USDA_GET_FOOD_BY_FDCID_URL}{fdc_id}?api_key={USDA_API_KEY}"
    
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        data = response.json()

        print(f"[Render Backend] ✅ Successfully fetched data for FDC ID '{fdc_id}'.")
        return data
    except requests.exceptions.RequestException as e:
        print(f"[Render Backend] ❌ Error fetching from USDA API for FDC ID '{fdc_id}': {e}")
        traceback.print_exc()
    except json.JSONDecodeError as e:
        print(f"[Render Backend] ❌ JSON Decode Error from USDA API for FDC ID '{fdc_id}'. Response: {response.text.strip()}")
        traceback.print_exc()
    except Exception as e:
        print(f"[Render Backend] ❌ An unexpected error occurred: {e}")
        traceback.print_exc()
        
    return None

def store_to_airtable(gtin, usda_data, analyzed_data):
    """
    Stores product data pulled from USDA API (and analysis results) into the Airtable cache.
    analyzed_data is a dictionary containing all structured analysis results.
    """
    if not airtable:
        print("[Render Backend] Airtable client not initialized. Skipping store to Airtable.")
        return

    print(f"[Render Backend] Attempting to store GTIN {gtin} to Airtable...")

    # Extracting data from usda_data
    product_description = usda_data.get("description", "")
    product_ingredients = usda_data.get("ingredients", "")

    # Extracting data from analyzed_data
    # These are now lists of dictionaries, so they need to be dumped to JSON strings
    identified_fda_non_common = analyzed_data.get("identified_fda_non_common", [])
    identified_fda_common = analyzed_data.get("identified_fda_common", [])
    identified_common_ingredients_only = analyzed_data.get("identified_common_ingredients_only", [])
    truly_unidentified_ingredients = analyzed_data.get("truly_unidentified_ingredients", [])
    data_score = analyzed_data.get("data_score", 0.0)
    data_completeness_level = analyzed_data.get("data_completeness_level", "N/A")
    nova_score = analyzed_data.get("nova_score", "N/A")
    nova_description = analyzed_data.get("nova_description", "N/A")

    fields = {
        "gtin_upc": gtin,
        "fdc_id": str(usda_data.get("fdcId", "")),
        "brand_name": usda_data.get("brandName", ""),
        "brand_owner": usda_data.get("brandOwner", ""),
        "description": product_description,
        "ingredients": product_ingredients,
        "lookup_count": 1, # Initialize lookup_count to 1 on first insertion
        "last_access": datetime.now().isoformat(),
        "source": "USDA API",
        # Store structured data points as JSON strings
        "identified_fda_non_common": json.dumps(identified_fda_non_common), 
        "identified_fda_common": json.dumps(identified_fda_common),
        "identified_common_ingredients_only": json.dumps(identified_common_ingredients_only),
        "truly_unidentified_ingredients": json.dumps(truly_unidentified_ingredients),
        "data_score": data_score,
        "data_completeness_level": data_completeness_level,
        "nova_score": str(nova_score), # Store as string to handle "N/A" and numbers
        "nova_description": nova_description
    }

    try:
        airtable.insert(fields)
        print(f"[Render Backend] ✅ Stored to Airtable: {fields.get('description', gtin)}")
    except Exception as e:
        print(f"[Render Backend] ❌ Failed to store to Airtable for GTIN {gtin}: {e}")
        # Print a more detailed traceback for debugging
        traceback.print_exc()

def count_airtable_rows():
    """Counts the total number of records in the Airtable table."""
    if not airtable:
        print("[Render Backend] Airtable client not initialized. Skipping row count.")
        return 0

    print("[Render Backend] Counting Airtable rows...")
    try:
        # Corrected: Fetch all records without specifying fields to avoid "id" field issue
        records = airtable.get_all()
        return len(records)
    except Exception as e:
        print(f"[Render Backend] ⚠️ Error counting Airtable rows: {e}")
        return 0

def delete_least_valuable_row():
    """
    Deletes the least valuable record in Airtable based on an effective score
    that combines lookup_count and freshness (last_access).
    Least valuable = lowest effective score, then oldest last_access for ties.
    """
    if not airtable:
        print("[Render Backend] Airtable client not initialized. Skipping row deletion.")
        return

    print("[Render Backend] Checking for least valuable row to evict using effective score...")
    try:
        # Fetch records with 'lookup_count' and 'last_access' fields
        records = airtable.get_all(fields=['lookup_count', 'last_access'])

        if records:
            # Calculate effective score for each record
            records_with_effective_score = []
            now = datetime.now()
            for r in records:
                fields = r["fields"]
                lookup_count = fields.get("lookup_count", 0)
                last_access_str = fields.get("last_access", "0000-01-01T00:00:00.000Z")
                
                try:
                    last_access_dt = datetime.fromisoformat(last_access_str.replace('Z', '+00:00')) # Handle 'Z' for UTC
                except ValueError:
                    last_access_dt = datetime.min # Fallback for invalid date string

                effective_score = lookup_count

                # Apply freshness bonus if within the freshness window
                if now - last_access_dt < timedelta(days=FRESHNESS_WINDOW_DAYS):
                    effective_score += FRESHNESS_BONUS
                
                records_with_effective_score.append({
                    'id': r['id'],
                    'fields': fields, # Keep original fields for logging
                    'effective_score': effective_score,
                    'last_access_dt': last_access_dt # Store datetime object for direct comparison
                })

            # Sort records: first by effective_score (ascending), then by last_access_dt (ascending for oldest)
            records_sorted = sorted(records_with_effective_score, key=lambda r: (
                r["effective_score"],
                r["last_access_dt"]
            ))

            least_valuable_record_info = records_sorted[0]
            record_id_to_delete = least_valuable_record_info['id']
            
            airtable.delete(record_id_to_delete)
            print(f"[Render Backend] 🗑️ Deleted least valuable entry (ID: {record_id_to_delete}, "
                  f"Lookup Count: {least_valuable_record_info['fields'].get('lookup_count', 0)}, "
                  f"Last Access: {least_valuable_record_info['fields'].get('last_access', 'N/A')}), "
                  f"Effective Score: {least_valuable_record_info['effective_score']}).")
        else:
            print("[Render Backend] No records to evict.")
    except Exception as e:
        print(f"[Render Backend] ❌ Error deleting least valuable row: {e}")


@app.route('/api/gtin-lookup', methods=['POST'])
def gtin_lookup():
    """
    API endpoint for GTIN lookup.
    Expects a POST request with a JSON body containing 'gtin'.
    Returns JSON response.
    """
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Type': 'application/json'
    }

    if request.method == 'OPTIONS':
        return '', 204, headers

    try:
        request_data = request.get_json(force=True)
        gtin = request_data.get('gtin')

        if not gtin:
            return jsonify({"error": "Bad Request", "message": "GTIN is required in the request body."}), 400, headers

        # Initialize variables for the response
        product_description = "N/A"
        product_ingredients = "N/A"
        status = "not_found"
        nova_score = "N/A"
        nova_description = "N/A"
        identified_fda_non_common = []
        identified_fda_common = []
        identified_common_ingredients_only = []
        truly_unidentified_ingredients = []
        data_score = 0.0
        data_completeness_level = "N/A"


        # 1. Check Airtable Cache
        cached_data = check_airtable_cache(gtin)
        if cached_data:
            product_description = cached_data.get('description', "N/A")
            product_ingredients = cached_data.get('ingredients', "N/A")

            # Retrieve pre-analyzed data from cache or re-analyze if ingredients changed/not present
            # We assume if product_ingredients are in cache, the analyzed lists are too.
            # Convert JSON strings back to Python lists
            # IMPORTANT: The check_airtable_cache function now handles the JSON parsing,
            # so these should already be lists of dicts or lists of strings.
            identified_fda_non_common = cached_data.get('identified_fda_non_common', [])
            identified_fda_common = cached_data.get('identified_fda_common', [])
            identified_common_ingredients_only = cached_data.get('identified_common_ingredients_only', [])
            truly_unidentified_ingredients = cached_data.get('truly_unidentified_ingredients', [])
            
            data_score = cached_data.get('data_score', 0.0)
            data_completeness_level = cached_data.get('data_completeness_level', "N/A")
            nova_score = cached_data.get('nova_score', "N/A")
            nova_description = cached_data.get('nova_description', "N/A")

            # In case an older cache entry doesn't have the granular data, re-analyze
            # This block is crucial for ensuring the detailed ingredient objects are returned
            if (not identified_fda_non_common and not identified_fda_common and 
                not identified_common_ingredients_only and not truly_unidentified_ingredients and product_ingredients != "N/A"):
                print("[Backend] Cached data missing granular ingredient breakdown, re-analyzing...")
                (identified_fda_non_common, identified_fda_common, identified_common_ingredients_only,
                 truly_unidentified_ingredients, data_score, data_completeness_level,
                 nova_score, nova_description) = analyze_ingredients(product_ingredients)
                # Potentially update the Airtable record with new granular data here if desired
                # For now, we just ensure the response contains the re-analyzed data.
            elif product_ingredients != "N/A": # If ingredients exist, but the lists might be empty from cache
                 # Re-analyze to ensure ingredient objects with 'used_for' etc. are created
                 # This is a defensive measure if Airtable somehow stored empty lists or simple strings
                 # instead of the full objects.
                 # Only re-analyze if the lists are empty, but ingredients string is not "N/A"
                if not identified_fda_non_common and not identified_fda_common:
                    print("[Backend] Cached FDA lists are empty, re-analyzing to populate details...")
                    (identified_fda_non_common, identified_fda_common, identified_common_ingredients_only,
                     truly_unidentified_ingredients, data_score, data_completeness_level,
                     nova_score, nova_description) = analyze_ingredients(product_ingredients)


            status = "found_in_cache"

            # Prepare the response with structured data
            response_data = {
                "gtin": gtin,
                "description": product_description,
                "ingredients": product_ingredients,
                "status": status,
                "nova_score": nova_score,
                "nova_description": nova_description,
                "identified_fda_non_common": identified_fda_non_common,
                "identified_fda_common": identified_fda_common,
                "identified_common_ingredients_only": identified_common_ingredients_only,
                "truly_unidentified_ingredients": truly_unidentified_ingredients,
                "data_score": data_score,
                "data_completeness_level": data_completeness_level
            }
            return jsonify(response_data), 200, headers

        # 2. If not in cache, fetch from USDA API
        usda_product_data = fetch_from_usda_api(gtin)

        if usda_product_data:
            product_description = usda_product_data.get('description', "N/A")
            product_ingredients = usda_product_data.get('ingredients', "N/A")

            # Analyze ingredients and get all structured results
            (identified_fda_non_common, identified_fda_common, identified_common_ingredients_only,
             truly_unidentified_ingredients, data_score, data_completeness_level,
             nova_score, nova_description) = analyze_ingredients(product_ingredients)

            status = "pulled_from_usda_and_cached"

            # Prepare a dictionary of analyzed data to pass to store_to_airtable
            analyzed_data_for_cache = {
                "identified_fda_non_common": identified_fda_non_common,
                "identified_fda_common": identified_fda_common,
                "identified_common_ingredients_only": identified_common_ingredients_only,
                "truly_unidentified_ingredients": truly_unidentified_ingredients,
                "data_score": data_score,
                "data_completeness_level": data_completeness_level,
                "nova_score": nova_score,
                "nova_description": nova_description
            }

            # Check if cache is full before adding new entry
            current_row_count = count_airtable_rows()
            if current_row_count >= AIRTABLE_MAX_ROWS:
                delete_least_valuable_row()

            # Store the new product data to Airtable, including the structured analysis results
            store_to_airtable(gtin, usda_product_data, analyzed_data_for_cache)

            # Prepare the response with structured data
            response_data = {
                "gtin": gtin,
                "description": product_description,
                "ingredients": product_ingredients,
                "status": status,
                "nova_score": nova_score,
                "nova_description": nova_description,
                "identified_fda_non_common": identified_fda_non_common,
                "identified_fda_common": identified_fda_common,
                "identified_common_ingredients_only": identified_common_ingredients_only,
                "truly_unidentified_ingredients": truly_unidentified_ingredients,
                "data_score": data_score,
                "data_completeness_level": data_completeness_level
            }
            return jsonify(response_data), 200, headers
        else:
            # Product not found scenario
            return jsonify({
                "gtin": gtin,
                "description": "N/A",
                "ingredients": "N/A",
                "status": "not_found",
                "nova_score": "N/A",
                "nova_description": "Cannot determine NOVA score.",
                "identified_fda_non_common": [],
                "identified_fda_common": [],
                "identified_common_ingredients_only": [],
                "truly_unidentified_ingredients": [],
                "data_score": 0.0,
                "data_completeness_level": "N/A"
            }), 404, headers

    except requests.exceptions.RequestException as e:
        print(f"[Render Backend] Network or USDA API error caught: {e}")
        return jsonify({"error": "Failed to connect to USDA FoodData Central or network issue.", "details": str(e)}), 500, headers
    except Exception as e:
        print(f"[Render Backend] An unexpected error occurred in handler: {e}")
        traceback.print_exc()
        return jsonify({"error": "An internal server error occurred.", "details": str(e)}), 500, headers


# Standard way to run Flask app for local testing
if __name__ == "__main__":
    if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, USDA_API_KEY]):
        print(
            "WARNING: Missing one or more environment variables (AIRTABLE_API_KEY, AIRTABLE_BASE_ID, USDA_API_KEY)."
        )
        print("Please set them for local testing or deployment.")
    app.run(debug=True, host='0.0.0.0', port=os.environ.get('PORT', 5000))
