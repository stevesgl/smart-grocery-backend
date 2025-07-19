# api/gtin-lookup.py
import os
import json
import re # Import re for regex operations
import requests # For making HTTP requests to USDA
from datetime import datetime
from airtable import Airtable # This library will be installed by Vercel

# ========================== CONFIGURATION (from Environment Variables) ==========================
# Vercel will inject these as environment variables during deployment.
# You MUST set these in your Vercel project settings.
AIRTABLE_API_KEY = os.environ.get('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = os.environ.get('AIRTABLE_BASE_ID')
AIRTABLE_TABLE_NAME = os.environ.get('AIRTABLE_TABLE_NAME', 'GTIN Cache') # Default table name
USDA_API_KEY = os.environ.get('USDA_API_KEY')

# Path to your full additives JSON file
# For Vercel, data files should be placed in a 'data' directory at the root of your serverless function's deployment
ADDITIVES_DATA_FILE = os.path.join(os.path.dirname(__file__), 'data', 'all_fda_substances_full.json')
# Path to your common ingredients JSON file
COMMON_INGREDIENTS_DATA_FILE = os.path.join(os.path.dirname(__file__), 'data', 'common_ingredients.json')

# Airtable max rows for the free tier (for eviction logic)
AIRTABLE_MAX_ROWS = 1000 
# ===============================================================================================

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
COMMON_INGREDIENTS_LOOKUP = set() # Changed to a set for faster lookup and correct usage

def load_data_lookups():
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

            for name in names_to_add:
                if name:
                    normalized_alias = re.sub(r'[^a-z0-9\s\&\.\-#\(\)]', '', name.lower()).strip()
                    normalized_alias = re.sub(r'\s+', ' ', normalized_alias)
                    normalized_alias = normalized_alias.replace('no.', 'no ')

                    if normalized_alias:
                        ADDITIVES_LOOKUP[normalized_alias] = normalized_canonical_name_for_key

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
            COMMON_INGREDIENTS_LOOKUP.add(normalized_ingredient) # Added to set
        print(f"✅ Successfully loaded {len(common_ingredients_raw)} common ingredients into lookup.")
    except FileNotFoundError:
        print(f"❌ Error: Common ingredients data file not found at '{COMMON_INGREDIENTS_DATA_FILE}'. Common ingredient lookup will not work.")
    except json.JSONDecodeError as e:
        print(f"❌ Error decoding JSON from '{COMMON_INGREDIENTS_DATA_FILE}': {e}")
    except Exception as e:
        print(f"❌ An unexpected error occurred while loading common ingredient data: {e}")

# --- Ingredient Analysis Function ---
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
        return [], [], [], 100.0, "High"

    # Step 1: Initial cleanup and pre-processing
    cleaned_string = re.sub(r'^(?:ingredients|contains|ingredient list|ingredients list):?\s*', '', ingredients_string, flags=re.IGNORECASE).strip()
    cleaned_string = re.sub(r'\s+and/or\s+', ', ', cleaned_string, flags=re.IGNORECASE)
    # Remove common parenthetical descriptors that are not part of the substance name
    # This is updated to be more comprehensive and prevent 'COLOR' from being left behind
    cleaned_string = re.sub(r'\s*\((?:color|flavour|flavor|emulsifier|stabilizer|thickener|preservative|antioxidant|acidifier|sweetener|gelling agent|firming agent|nutrient|vitamin [a-z0-9]+)\)\s*', '', cleaned_string, flags=re.IGNORECASE)
    cleaned_string = re.sub(r'\s*\[vitamin b\d\]\s*', '', cleaned_string, flags=re.IGNORECASE) # Remove [VITAMIN B#]


    # Step 2: Extract content within parentheses and process separately
    parenthetical_matches = re.findall(r'\(([^()]*?(?:\([^()]*?\)[^()]*?)*?)\)', cleaned_string)
    main_components_string = re.sub(r'\([^()]*?(?:\([^()]*?\)[^()]*?)*?\)', '', cleaned_string).strip()

    # Step 3: Split main string into components by commas and semicolons
    components = [comp.strip() for comp in re.split(r',\s*|;\s*', main_components_string) if comp.strip()]
    
    for p_content in parenthetical_matches:
        sub_components = [s.strip() for s in re.split(r',\s*', p_content) if s.strip()]
        components.extend(sub_components)

    components = [comp for comp in components if comp]

    total_analyzed_items = len(components)
    categorized_items_count = 0

    for original_component in components:
        # Normalize the component for matching, allowing relevant special characters
        # Also, strip trailing punctuation like periods
        normalized_component = re.sub(r'[^a-z0-9\s\&\.\-#\(\)]', '', original_component.lower()).strip()
        normalized_component = re.sub(r'\s+', ' ', normalized_component)
        normalized_component = normalized_component.replace('no.', 'no ')
        # NEW: Strip trailing non-alphanumeric characters (like periods)
        normalized_component = re.sub(r'[^\w\s\&\.\-#\(\)]+$', '', normalized_component).strip()


        if not normalized_component:
            continue

        component_categorized = False
        
        # Pass 1: Try to match against FDA Additives
        if normalized_component in ADDITIVES_LOOKUP:
            identified_fda_substances.add(ADDITIVES_LOOKUP[normalized_component])
            component_categorized = True
        else:
            words = normalized_component.split()
            for i in range(len(words)):
                for j in range(len(words), i, -1):
                    phrase = " ".join(words[i:j])
                    if phrase in ADDITIVES_LOOKUP:
                        identified_fda_substances.add(ADDITIVES_LOOKUP[phrase])
                        component_categorized = True
                        break
                if component_categorized:
                    break
        
        if component_categorized:
            categorized_items_count += 1
        else:
            # Pass 2: If not an FDA Additive, try to match against Common Ingredients
            if normalized_component in COMMON_INGREDIENTS_LOOKUP:
                identified_common_ingredients.add(original_component) # Store original for common ingredients
                categorized_items_count += 1
            else:
                # If still not categorized, it's truly unidentified
                truly_unidentified_ingredients.add(original_component)

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

    return (list(identified_fda_substances), list(identified_common_ingredients), 
            list(truly_unidentified_ingredients), data_score_percentage, data_completeness_level)

# --- Data Report Generation ---
def generate_data_report_markdown(identified_fda_substances, identified_common_ingredients, truly_unidentified_ingredients, data_score, data_completeness_level):
    """
    Generates a markdown-formatted data report for the product.
    """
    report = "## Ingredient Data Report\n\n"
    report += f"**Data Score:** {data_score:.1f}% ({data_completeness_level})\n\n"
    report += "The Data Score indicates the percentage of ingredients our system could categorize.\n\n"

    report += "### Identified FDA-Regulated Substances:\n"
    if identified_fda_substances:
        for sub in sorted(identified_fda_substances):
            report += f"* {sub.title()}\n"
    else:
        report += "* No specific FDA-regulated substances (additives) identified.\n"

    report += "\n### Identified Common Food Ingredients:\n"
    if identified_common_ingredients:
        for common_ing in sorted(identified_common_ingredients):
            report += f"* {common_ing.title()}\n"
    else:
        report += "* No common food ingredients identified (beyond FDA-regulated substances).\n"

    report += "\n### Truly Unidentified Ingredients/Phrases:\n"
    if truly_unidentified_ingredients:
        report += "The following components were not matched against our database of FDA-regulated substances or common ingredients. This means our system couldn't fully categorize them. These could be:\n"
        report += "* **Complex phrasing** not yet fully parsed.\n"
        report += "* **Obscure ingredients** not in our current database.\n"
        report += "* **Potential misspellings**.\n"
        for unident in sorted(truly_unidentified_ingredients):
            report += f"* {unident.title()}\n"
    else:
        report += "* All ingredient components were successfully categorized!\n"
    
    report += "\n---\n"
    report += "*Data Score reflects the percentage of parsed ingredient components that matched known FDA-regulated substances or common ingredients.*"
    return report

# --- Airtable Cache Management Functions ---
def check_airtable_cache(gtin):
    """
    Checks if a GTIN exists in the Airtable cache.
    If found, it updates the lookup_count and last_access fields for that record.
    """
    if not airtable:
        print("Airtable client not initialized. Skipping cache check.")
        return None
    
    print(f"  Checking Airtable cache for GTIN: {gtin}...")
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
            print(f"  ✅ Found in Airtable cache. Updated lookup_count to {new_lookup_count}.")
            return current_fields
    except Exception as e:
        print(f"  ⚠️ Error in check_airtable_cache for GTIN {gtin}: {e}")
    return None

def fetch_from_usda_api(gtin):
    """
    Queries the USDA FoodData Central API using the GTIN.
    Returns the first matching food item's data if found, otherwise None.
    """
    if not USDA_API_KEY:
        print("USDA API Key not set. Skipping USDA API fetch.")
        return None

    print(f"  Querying USDA API for GTIN: {gtin}...")
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
            print("  📥 Pulled from USDA API.")
            return data['foods'][0]
    except requests.exceptions.RequestException as e:
        print(f"  ❌ Error fetching from USDA API for GTIN {gtin}: {e}")
    except json.JSONDecodeError:
        print(f"  ❌ JSON Decode Error from USDA API for GTIN {gtin}. Response: {response.text.strip()}")
    except Exception as e:
        print(f"  ❌ Unexpected Error fetching from USDA: {e}")
            
    return None

def store_to_airtable(gtin, usda_data, data_report_markdown):
    """
    Stores product data pulled from USDA API into the Airtable cache,
    including the generated data report markdown.
    """
    if not airtable:
        print("Airtable client not initialized. Skipping store to Airtable.")
        return
        
    print(f"  Attempting to store GTIN {gtin} to Airtable...")
    fields = {
        "gtin_upc": gtin,
        "fdc_id": str(usda_data.get("fdcId", "")),
        "brand_name": usda_data.get("brandName", ""),
        "brand_owner": usda_data.get("brandOwner", ""),
        "description": usda_data.get("description", ""),
        "ingredients": usda_data.get("ingredients", ""),
        "lookup_count": 1,
        "last_access": datetime.now().isoformat(),
        "hot_score": 1, # Placeholder, can be calculated dynamically later
        "source": "USDA API",
        "data_report_markdown": data_report_markdown # Store the markdown report
    }
    
    try:
        airtable.insert(fields)
        print(f"  ✅ Stored to Airtable: {fields.get('description', gtin)}")
    except Exception as e:
        print(f"  ❌ Failed to store to Airtable for GTIN {gtin}: {e}")

def count_airtable_rows():
    """Counts the total number of records in the Airtable table."""
    if not airtable:
        print("Airtable client not initialized. Skipping row count.")
        return 0
        
    print("  Counting Airtable rows...")
    try:
        records = airtable.get_all() # FIX: Removed fields=['id']
        return len(records)
    except Exception as e:
        print(f"  ⚠️ Error counting Airtable rows: {e}")
        return 0

def delete_least_valuable_row():
    """
    Deletes the least valuable record in Airtable based on lookup_count and last_access.
    Least valuable = lowest lookup_count, then oldest last_access for ties.
    """
    if not airtable:
        print("Airtable client not initialized. Skipping row deletion.")
        return
        
    print("  Checking for least valuable row to evict...")
    try:
        records = airtable.get_all(fields=['lookup_count', 'last_access'])
        
        if records:
            records_sorted = sorted(records, key=lambda r: (
                r["fields"].get("lookup_count", 0), 
                r["fields"].get("last_access", "0000-01-01T00:00:00.000Z") 
            ))
            
            least_valuable_record = records_sorted[0] 
            record_id_to_delete = least_valuable_record['id']
            
            airtable.delete(record_id_to_delete)
            print(f"  🗑️ Deleted least valuable entry (ID: {record_id_to_delete}, "
                  f"Lookup: {least_valuable_record['fields'].get('lookup_count', 0)}, "
                  f"Last Access: {least_valuable_record['fields'].get('last_access', 'N/A')}).")
        else:
            print("  No records to evict.")
    except Exception as e:
        print(f"  ❌ Error deleting least valuable row: {e}")

# This is the main entry point for Vercel Python Serverless Functions
# The 'request' object will be provided by Vercel's runtime (similar to Flask's request)
def handler(request):
    """
    Vercel Serverless Function handler for GTIN lookup.
    Expects a POST request with a JSON body containing 'gtin'.
    Returns JSON response.
    """
    # Load data lookups only once per cold start of the serverless function
    # This ensures the lookup dictionaries are available for all requests
    # within the same function instance.
    if not ADDITIVES_LOOKUP or not COMMON_INGREDIENTS_LOOKUP:
        load_data_lookups()
    
    # Set CORS headers to allow requests from your frontend
    headers = {
        'Access-Control-Allow-Origin': '*', # Adjust this to your Vercel frontend URL in production
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Type': 'application/json'
    }

    # Handle OPTIONS preflight request for CORS
    if request.method == 'OPTIONS':
        return '', 204, headers

    if request.method != 'POST':
        return json.dumps({"error": "Method Not Allowed", "message": "Only POST requests are supported."}), 405, headers

    try:
        # Vercel's request object (from Werkzeug) has a get_json() method
        # force=True attempts to parse even if Content-Type header is not application/json
        request_data = request.get_json(force=True) 
        gtin = request_data.get('gtin')

        if not gtin:
            return json.dumps({"error": "Bad Request", "message": "GTIN is required in the request body."}), 400, headers

        product_description = "N/A"
        product_ingredients = "N/A"
        data_report_markdown = "N/A"
        status = "not_found"

        # 1. Check Airtable Cache
        cached_data = check_airtable_cache(gtin)
        if cached_data:
            print(f"DEBUG: Data found in cache for GTIN {gtin}. Fields: {cached_data.keys()}")
            product_description = cached_data.get('description', "N/A")
            product_ingredients = cached_data.get('ingredients', "N/A")
            data_report_markdown = cached_data.get('data_report_markdown', "N/A")
            status = "found_in_cache"
            print(f"DEBUG: Returning cached data for GTIN {gtin}")
            return json.dumps({
                "gtin": gtin,
                "description": product_description,
                "ingredients": product_ingredients,
                "data_report_markdown": data_report_markdown,
                "status": status
            }), 200, headers

        # 2. If not in cache, fetch from USDA API
        usda_product_data = fetch_from_usda_api(gtin)
        
        if usda_product_data:
            product_description = usda_product_data.get('description', "N/A")
            product_ingredients = usda_product_data.get('ingredients', "N/A")

            # Analyze ingredients and generate data report
            identified_fda_substances, identified_common_ingredients, truly_unidentified_ingredients, data_score, data_completeness_level = analyze_ingredients(product_ingredients)
            data_report_markdown = generate_data_report_markdown(identified_fda_substances, identified_common_ingredients, truly_unidentified_ingredients, data_score, data_completeness_level)
            status = "pulled_from_usda_and_cached"

            # Check if cache is full before adding new entry
            current_row_count = count_airtable_rows()
            if current_row_count >= AIRTABLE_MAX_ROWS:
                print(f"Cache is full ({current_row_count} rows). Evicting least valuable entry.")
                delete_least_valuable_row()
            
            # Store the new product data to Airtable, including the data report
            store_to_airtable(gtin, usda_product_data, data_report_markdown)
            
            print(f"DEBUG: Returning USDA data for GTIN {gtin}")
            return json.dumps({
                "gtin": gtin,
                "description": product_description,
                "ingredients": product_ingredients,
                "data_report_markdown": data_report_markdown,
                "status": status
            }), 200, headers
        else:
            print(f"DEBUG: Product not found for GTIN {gtin}")
            return json.dumps({
                "gtin": gtin,
                "description": "N/A",
                "ingredients": "N/A",
                "data_report_markdown": "Product not found in USDA FoodData Central.",
                "status": "not_found"
            }), 404, headers

    except requests.exceptions.RequestException as e:
        print(f"Network or USDA API error: {e}")
        return json.dumps({"error": "Failed to connect to USDA FoodData Central or network issue.", "details": str(e)}), 500, headers
    except Exception as e:
        print(f"An unexpected error occurred in handler: {e}")
        return json.dumps({"error": "An internal server error occurred.", "details": str(e)}), 500, headers

