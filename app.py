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
import time

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
FDA_SUBSTANCE_DETAILS_LOOKUP = {} # NEW: Stores full FDA substance entry by its normalized canonical name

def load_data_lookups():
    """
    Loads the additive data and common ingredients data from JSON files
    and builds the optimized lookup dictionaries/sets.
    This function should be called once at application startup.
    """
    global ADDITIVES_LOOKUP, COMMON_INGREDIENTS_LOOKUP, COMMON_FDA_SUBSTANCES_SET, FDA_SUBSTANCE_DETAILS_LOOKUP

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

            # Store the full entry by its normalized canonical name for later lookup
            FDA_SUBSTANCE_DETAILS_LOOKUP[normalized_canonical_name_for_key] = entry

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
            # ADDITION: Silicon Dioxide
            if "silicon dioxide" in normalized_canonical_name_for_key:
                names_to_add.add("silicon dioxide")


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
        # ADDITION: Debug for Silicon Dioxide
        print(f"[Backend Init] DEBUG: 'silicon dioxide' in ADDITIVES_LOOKUP: {'silicon dioxide' in ADDITIVES_LOOKUP}")
        print(f"[Backend Init] DEBUG: Value for 'silicon dioxide': {ADDITIVES_LOOKUP.get('silicon dioxide')}")


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
    print(f"[Backend Init] DEBUG: Value for 'sodium chloride': {ADDITIVES_LOOKUP.get('sodium chloride')}")
    print(f"[Backend Init] DEBUG: 'red 40' in COMMON_FDA_SUBSTANCES_SET: {'red 40' in COMMON_FDA_SUBSTANCES_SET}")


# Call load_data_lookups() immediately after app creation to ensure data is loaded when Gunicorn runs the app
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
    # This is a heuristic and can be refined. A high number of unidentified might also suggest UPF.
    if truly_unidentified_ingredients:
        # If there are many unidentified, it's more likely UPF.
        # This threshold can be adjusted.
        if len(truly_unidentified_ingredients) > 2: # Heuristic: more than 2 unidentified ingredients
            return 4, "Ultra-Processed Food (Unidentified Ingredients)"
    
    # Rule 3: If no non-common FDA substances, and no significant unidentified,
    # check for combinations of common ingredients and common FDA-regulated substances.
    # This implies NOVA 3 (Processed Food).
    if (identified_common_ingredients_only and identified_fda_common) or \
       (len(identified_common_ingredients_only) > 0 and not identified_fda_common and not identified_fda_non_common and not truly_unidentified_ingredients):
        return 3, "Processed Food"

    # Rule 4: If only common FDA-regulated substances (like salt, sugar, oil) are present, it's NOVA 2.
    # This would be for products like a bag of salt, a bottle of sugar, or cooking oil.
    if identified_fda_common and not identified_common_ingredients_only and not truly_unidentified_ingredients:
        return 2, "Processed Culinary Ingredient"

    # Rule 5: If only common ingredients (like water, milk, fresh produce) are present, it's NOVA 1.
    if identified_common_ingredients_only and not identified_fda_common and not identified_fda_non_common and not truly_unidentified_ingredients:
        return 1, "Unprocessed or Minimally Processed Food"
    
    # Fallback for edge cases or very minimal products not fitting above rules
    # If no ingredients, or only very few that don't fit clear categories, default to a reasonable group.
    # For an empty ingredient list, it's hard to classify, but 1 or 2 might be reasonable.
    if not identified_fda_non_common and not identified_fda_common and not identified_common_ingredients_only and not truly_unidentified_ingredients:
        return 1, "Unprocessed or Minimally Processed Food (No Ingredients Listed)" # Default for empty list
    
    # If none of the above, it's a bit ambiguous, but likely leans processed or ultra-processed
    # based on the presence of some identified components.
    return 3, "Processed Food (Categorization Ambiguous)"


# --- Ingredient Analysis Function (Revised for Data Score and Phrase Matching) ---
def analyze_ingredients(ingredients_string):
    """
    Analyzes an ingredient string to identify FDA-regulated substances and common ingredients.
    Calculates a Data Score based on the completeness of identification.
    Returns categorized lists of ingredients for the four categories, plus estimated NOVA score.
    """
    
    identified_fda_non_common = set()  # New category 1
    identified_fda_common = set()      # New category 2
    identified_common_ingredients_only = set() # New category 3
    truly_unidentified_ingredients = set() # New category 4

    # Keep track of identified ingredient phrases to calculate data score
    identified_phrases = set()

    # Normalize the entire ingredient string for initial processing (e.g., remove parentheticals)
    processed_ingredients_string = re.sub(r'\([^)]*\)', '', ingredients_string).lower()
    
    # Split by common delimiters. Using a regex to split by comma, semicolon, or "and"
    ingredient_phrases = re.split(r',|;|\band\b', processed_ingredients_string)
    
    # Further split phrases that might contain multiple items separated by " " or "/" or "or"
    # Example: "corn starch / potato starch" should be treated as two distinct phrases.
    final_ingredient_phrases = []
    for phrase in ingredient_phrases:
        sub_phrases = re.split(r'\s/\s|\sor\s', phrase.strip())
        final_ingredient_phrases.extend([p.strip() for p in sub_phrases if p.strip()])

    # --- Phase 1: Identify direct FDA additives ---
    for original_phrase in final_ingredient_phrases:
        normalized_phrase = re.sub(r'[^a-z0-9\s\&\.\-#\(\)]', '', original_phrase.lower()).strip()
        normalized_phrase = re.sub(r'\s+', ' ', normalized_phrase)
        normalized_phrase = normalized_phrase.replace('no.', 'no ')

        if normalized_phrase in ADDITIVES_LOOKUP:
            canonical_fda_name = ADDITIVES_LOOKUP[normalized_phrase]
            # Check if this FDA substance is also considered a common ingredient
            if canonical_fda_name in COMMON_FDA_SUBSTANCES_SET:
                identified_fda_common.add(FDA_SUBSTANCE_DETAILS_LOOKUP.get(canonical_fda_name, {}).get("Substance Name (Heading)", canonical_fda_name))
            else:
                identified_fda_non_common.add(FDA_SUBSTANCE_DETAILS_LOOKUP.get(canonical_fda_name, {}).get("Substance Name (Heading)", canonical_fda_name))
            
            # Add the original phrase to identified_phrases set for data score calculation
            identified_phrases.add(original_phrase.lower()) # Use lowercased original phrase for consistency

    # --- Phase 2: Identify common ingredients and re-evaluate remaining ---
    for original_phrase in final_ingredient_phrases:
        normalized_phrase = re.sub(r'[^a-z0-9\s\&\.\-#\(\)]', '', original_phrase.lower()).strip()
        normalized_phrase = re.sub(r'\s+', ' ', normalized_phrase)
        normalized_phrase = normalized_phrase.replace('no.', 'no ')

        # If it's already identified as an FDA substance (of any type), skip
        # We need to check against the *normalized canonical name* because that's what's stored in ADDITIVES_LOOKUP values.
        # So, we need to normalize the original phrase and then check if its canonical form is already identified.
        canonical_form_of_phrase = ADDITIVES_LOOKUP.get(normalized_phrase)
        if canonical_form_of_phrase and (canonical_form_of_phrase in {re.sub(r'[^a-z0-9\s\&\.\-#]', '', s.lower()).strip() for s in identified_fda_non_common} or \
                                         canonical_form_of_phrase in {re.sub(r'[^a-z0-9\s\&\.\-#]', '', s.lower()).strip() for s in identified_fda_common}):
            continue


        if normalized_phrase in COMMON_INGREDIENTS_LOOKUP:
            identified_common_ingredients_only.add(COMMON_INGREDIENTS_LOOKUP[normalized_phrase])
            identified_phrases.add(original_phrase.lower())
        else:
            # If it's not an FDA substance (of any type) and not a common ingredient, it's truly unidentified
            # Ensure it's not already covered by an FDA-common entry or a common ingredient already.
            # This check prevents duplicates if an ingredient was first identified as common,
            # then also found to be an FDA common substance.
            
            is_covered_by_fda_common = False
            for fda_common_item in identified_fda_common:
                if fda_common_item.lower() in normalized_phrase:
                    is_covered_by_fda_common = True
                    break
            
            is_covered_by_common_only = False
            for common_only_item in identified_common_ingredients_only:
                if common_only_item.lower() in normalized_phrase:
                    is_covered_by_common_only = True
                    break

            if not is_covered_by_fda_common and not is_covered_by_common_only and original_phrase.strip() != "":
                truly_unidentified_ingredients.add(original_phrase.strip())


    # --- Calculate Data Score ---
    total_phrases = len(final_ingredient_phrases)
    if total_phrases == 0:
        data_score_percentage = 100 # If no ingredients, assume 100% identified vacuously
    else:
        # Data score is the percentage of distinct phrases that were identified
        data_score_percentage = (len(identified_phrases) / total_phrases) * 100

    # Calculate NOVA score
    nova_score, nova_description = calculate_nova_score(
        identified_fda_non_common,
        identified_fda_common,
        identified_common_ingredients_only,
        truly_unidentified_ingredients
    )

    return {
        "identified_fda_non_common": list(identified_fda_non_common),
        "identified_fda_common": list(identified_fda_common),
        "identified_common_ingredients_only": list(identified_common_ingredients_only),
        "truly_unidentified_ingredients": list(truly_unidentified_ingredients),
        "data_score_percentage": round(data_score_percentage), # Round to nearest whole number
        "nova_score": nova_score,
        "nova_description": nova_description
    }

# --- Markdown Report Generation ---
def generate_data_report_markdown(analysis_results, usda_product_data):
    # Ensure GTIN is passed correctly
    gtin = usda_product_data.get('gtin', 'N/A')
    description = usda_product_data.get('description', 'N/A')
    ingredients = usda_product_data.get('ingredients', 'N/A')
    data_score_percentage = analysis_results.get("data_score_percentage", 0)
    nova_score = analysis_results.get("nova_score", "N/A")
    nova_description = analysis_results.get("nova_description", "N/A")

    fda_non_common = analysis_results.get("identified_fda_non_common", [])
    fda_common = analysis_results.get("identified_fda_common", [])
    common_ingredients_only = analysis_results.get("identified_common_ingredients_only", [])
    unidentified = analysis_results.get("truly_unidentified_ingredients", [])

    report_parts = []

    report_parts.append(f"# Product Scan Report for GTIN: {gtin}\n\n")
    report_parts.append(f"**Description:** {description}\n\n")
    report_parts.append(f"**Ingredients List:** {ingredients}\n\n")
    report_parts.append(f"**Data Score:** {data_score_percentage}% of ingredients identified.\n\n")
    report_parts.append(f"**NOVA Score Estimate:** {nova_score} ({nova_description})\n\n")
    report_parts.append("---\n\n")


    if fda_non_common:
        report_parts.append("## Detected FDA Substances (Non-Commonly Found in Whole Foods) 🧪\n\n")
        for substance_heading in sorted(fda_non_common):
            normalized_substance_key = re.sub(r'[^a-z0-9\s\&\.\-#]', '', substance_heading.lower()).strip()
            normalized_substance_key = re.sub(r'\s+', ' ', normalized_substance_key)
            normalized_substance_key = normalized_substance_key.replace('no.', 'no ')

            details = FDA_SUBSTANCE_DETAILS_LOOKUP.get(normalized_substance_key, {})
            functions = details.get("Used for (Technical Effect)", "N/A")
            source = details.get("Source", "FDA Additive Database")
            report_parts.append(f"- **{substance_heading}**\n")
            report_parts.append(f"  * Used for: {functions}\n")
            report_parts.append(f"  * Source: {source}\n\n")
        report_parts.append("\n")

    if fda_common:
        report_parts.append("## Detected Common FDA-Regulated Substances (e.g., Salt, Sugar) 🌱\n\n")
        for substance in sorted(fda_common):
            report_parts.append(f"- {substance}\n")
        report_parts.append("\n")

    if common_ingredients_only:
        report_parts.append("## Detected Common Ingredients (Non-FDA Regulated) 🍎\n\n")
        for ingredient in sorted(common_ingredients_only):
            report_parts.append(f"- {ingredient}\n")
        report_parts.append("\n")

    if unidentified:
        report_parts.append("## Unidentified Ingredients ❓\n")
        report_parts.append("The following ingredients could not be identified in our databases:\n\n")
        for ingredient in sorted(unidentified):
            report_parts.append(f"- {ingredient}\n")
        report_parts.append("\n")

    report_parts.append("---\n")
    report_parts.append("*Disclaimer: This report is an estimate based on available data and ingredient analysis. Consult a professional for dietary advice.*")
    
    return "".join(report_parts)


# --- Airtable Cache Functions ---
def store_to_airtable(gtin, usda_product_data, data_report_markdown, nova_score, nova_description,
                      fda_substances, common_ingredients, unidentified_ingredients):
    if not airtable:
        print("[Airtable] Airtable client not initialized. Skipping cache storage.")
        return

    # Prepare data for Airtable
    record_data = {
        "GTIN": str(gtin),
        "Description": usda_product_data.get('description', 'N/A'),
        "Ingredients": usda_product_data.get('ingredients', 'N/A'),
        "Data Report Markdown": data_report_markdown,
        "NOVA Score": str(nova_score), # Store as string to handle "N/A"
        "NOVA Description": nova_description,
        "FDA Substances": json.dumps(fda_substances), # Store lists as JSON strings
        "Common Ingredients": json.dumps(common_ingredients),
        "Unidentified Ingredients": json.dumps(unidentified_ingredients),
        "Last Cached": datetime.now().isoformat()
    }
    
    try:
        # Check if record already exists by GTIN using a direct formula
        # Ensuring the field name in the formula exactly matches the Airtable column: 'gtin_upc'
        formula = f"{{gtin_upc}}='{gtin}'"
        print(f"[Airtable] Searching for existing record with formula: {formula}")
        existing_records = airtable.get_all(formula=formula) # Use get_all with formula

        if existing_records:
            record_id = existing_records[0]['id']
            airtable.update(record_id, record_data)
            print(f"[Airtable] Updated existing record for GTIN: {gtin}")
        else:
            # Check current row count and evict if necessary
            current_records = airtable.get_all()
            if len(current_records) >= AIRTABLE_MAX_ROWS:
                # Simple eviction: remove the oldest record
                oldest_record = min(current_records, key=lambda r: r['fields'].get('Last Cached', '1970-01-01'))
                airtable.delete(oldest_record['id'])
                print(f"[Airtable] Evicted oldest record (ID: {oldest_record['id']}) to make space.")
            
            airtable.insert(record_data)
            print(f"[Airtable] Stored new record for GTIN: {gtin}")
    except Exception as e:
        print(f"[Airtable] Error storing/updating to Airtable for GTIN {gtin}: {e}")
        traceback.print_exc()


def fetch_from_airtable(gtin):
    if not airtable:
        print("[Airtable] Airtable client not initialized. Skipping cache fetch.")
        return None

    try:
        # Fetch using a direct formula
        # Ensuring the field name in the formula exactly matches the Airtable column: 'gtin_upc'
        formula = f"{{gtin_upc}}='{gtin}'"
        print(f"[Airtable] Fetching with formula: {formula}")
        records = airtable.get_all(formula=formula) # Use get_all with formula

        if records:
            record = records[0]['fields']
            print(f"[Airtable] Cache hit for GTIN: {gtin}")
            # Parse JSON strings back into lists
            record['FDA Substances'] = json.loads(record.get('FDA Substances', '[]'))
            record['Common Ingredients'] = json.loads(record.get('Common Ingredients', '[]'))
            record['Unidentified Ingredients'] = json.loads(record.get('Unidentified Ingredients', '[]'))
            return record
        print(f"[Airtable] Cache miss for GTIN: {gtin}")
        return None
    except Exception as e:
        print(f"[Airtable] Error fetching from Airtable for GTIN {gtin}: {e}")
        traceback.print_exc()
        return None


# --- Main GTIN Lookup API Endpoint ---
@app.route('/gtin-lookup', methods=['POST'])
def gtin_lookup_api():
    headers = {'Content-Type': 'application/json'}  # Set content type for all responses
    overall_start = time.time()
    print("🔍 [TIMER] Lookup route started")

    try:
        step1_start = time.time()
        data = request.get_json()
        gtin = data.get('gtin')

        if not gtin:
            print("[Render Backend] Missing GTIN in request.")
            return jsonify({"error": "GTIN is required."}), 400, headers
        print(f"✅ [TIMER] Parsed GTIN: {time.time() - step1_start:.2f}s")

        # 1. Try fetching from Airtable cache first
        step2_start = time.time()
        cached_data = fetch_from_airtable(gtin)
        print(f"📦 [TIMER] Airtable cache fetch: {time.time() - step2_start:.2f}s")

        if cached_data:
            total_time = time.time() - overall_start
            print(f"🚀 [TIMER] Total response time (cache hit): {total_time:.2f}s")
            return jsonify({
                "gtin": gtin,
                "description": cached_data.get('Description', 'N/A'),
                "ingredients": cached_data.get('Ingredients', 'N/A'),
                "data_report_markdown": cached_data.get('Data Report Markdown', 'We’re improving every day. The more you use it, the smarter it gets!'),
                "status": "cached",
                "nova_score": cached_data.get('NOVA Score', 'N/A'),
                "nova_description": cached_data.get('NOVA Description', 'Cannot determine NOVA score.'),
                "fda_substances": cached_data.get('FDA Substances', []),
                "common_ingredients": cached_data.get('Common Ingredients', []),
                "unidentified_ingredients": cached_data.get('Unidentified Ingredients', [])
            }), 200, headers

        # 2. If not in cache, query USDA FoodData Central
        step3_start = time.time()
        print(f"[Render Backend] Querying USDA for GTIN: {gtin}")
        params = {
            'query': gtin,
            'dataType': 'Branded',
            'api_key': USDA_API_KEY
        }
        usda_response = requests.get(USDA_SEARCH_URL, params=params)
        usda_response.raise_for_status()
        usda_data = usda_response.json()
        print(f"🌽 [TIMER] USDA fetch: {time.time() - step3_start:.2f}s")

        # 3. Process the USDA product data
        usda_product_data = {}
        if usda_data and usda_data.get('foods'):
            step4_start = time.time()

            for food_item in usda_data['foods']:
                if food_item.get('gtinV1') == gtin:
                    usda_product_data = food_item
                    break
            if not usda_product_data:
                usda_product_data = usda_data['foods'][0]

            product_description = usda_product_data.get('description', 'N/A')
            product_ingredients = usda_product_data.get('ingredients', 'N/A')

            # Analyze ingredients and calculate NOVA score
            analysis_results = analyze_ingredients(product_ingredients)

            # Generate Markdown report
            usda_product_data['gtin'] = gtin
            data_report_markdown = generate_data_report_markdown(analysis_results, usda_product_data)

            # Prepare counts for future frontend use (MVP+)
            summary_counts = {
            "fda_additives": len(analysis_results["identified_fda_non_common"]),
            "fda_common_substances": len(analysis_results["identified_fda_common"]),
            "common_ingredients": len(analysis_results["identified_common_ingredients_only"]),
            "unidentified": len(analysis_results["truly_unidentified_ingredients"])
         }

            print("[Backend] ✅ Generated Markdown Report:")
            print(data_report_markdown)

            fda_substances = analysis_results.get("identified_fda_non_common", [])
            fda_common = analysis_results.get("identified_fda_common", [])
            common_ingredients = analysis_results.get("identified_common_ingredients_only", [])
            unidentified_ingredients = analysis_results.get("truly_unidentified_ingredients", [])

            nova_score = analysis_results.get("nova_score", "N/A")
            nova_description = analysis_results.get("nova_description", "Cannot determine NOVA score.")
            print(f"🧪 [TIMER] Analysis + Markdown: {time.time() - step4_start:.2f}s")

            # 4. Store to Airtable
            step5_start = time.time()
            store_to_airtable(gtin, usda_product_data, data_report_markdown, nova_score, nova_description,
            fda_substances, common_ingredients, unidentified_ingredients)
            print(f"🗃️ [TIMER] Stored to Airtable: {time.time() - step5_start:.2f}s")

            total_time = time.time() - overall_start
            print(f"🚀 [TIMER] Total response time (USDA): {total_time:.2f}s")

            return jsonify({
                "gtin": gtin,
                "description": product_description,
                "ingredients": product_ingredients,
                "data_report_markdown": data_report_markdown,
                "status": "success",
                "nova_score": nova_score,
                "nova_description": nova_description,
                "fda_substances": fda_substances,
                "common_ingredients": common_ingredients,
                "unidentified_ingredients": unidentified_ingredients
                "summary_counts": summary_counts  # ✅ MVP+ prep
            }), 200, headers

        else:
            print(f"[Render Backend] Product not found in USDA for GTIN {gtin}")
            return jsonify({
                "gtin": gtin,
                "description": "N/A",
                "ingredients": "N/A",
                "data_report_markdown": "Product not found in USDA FoodData Central.",
                "status": "not_found",
                "nova_score": "N/A",
                "nova_description": "Cannot determine NOVA score."
            }), 404, headers

    except requests.exceptions.RequestException as e:
        print(f"[Render Backend] Network or USDA API error: {e}")
        return jsonify({"error": "Failed to connect to USDA or network issue.", "details": str(e)}), 500, headers
    except Exception as e:
        print(f"[Render Backend] Unexpected error in GTIN Lookup: {e}")
        traceback.print_exc()
        return jsonify({"error": "Internal server error", "details": str(e)}), 500, headers


# Standard way to run Flask app for local testing
if __name__ == '__main__':
    if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, USDA_API_KEY]):
        print("WARNING: Missing one or more environment variables (AIRTABLE_API_KEY, AIRTABLE_BASE_ID, USDA_API_KEY).")
        print("Please set them for local testing or ensure they are...")
