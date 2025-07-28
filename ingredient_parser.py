# FILE: backend/ingredient_parser.py

import json
import re
import os
import pandas as pd
import sys

def load_patterns(file_path="data/ingredient_naming_patterns.json"):
    """
    Loads descriptive modifiers, parenthetical examples, and punctuation patterns from JSON.
    """
    try:
        # Construct absolute path for consistency
        abs_file_path = os.path.join(os.path.dirname(__file__), file_path)
        with open(abs_file_path, 'r', encoding='utf-8') as f:
            patterns = json.load(f)
        print(f"Loaded patterns from: {abs_file_path}")
        return patterns
    except FileNotFoundError:
        print(f"Error: Pattern file not found at {abs_file_path}. Please ensure it exists.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {abs_file_path}. Please check file format.")
    return {}

def load_fda_substances(file_path="data/all_fda_substances_full_live.json"):
    """
    Loads FDA substances into a dictionary for quick lookup by normalized name or alias,
    returning the full substance object.
    The keys will be lowercase names/aliases, and values will be the original full dicts.
    """
    fda_substances_map = {}
    try:
        # Construct absolute path for consistency
        abs_file_path = os.path.join(os.path.dirname(__file__), file_path)
        with open(abs_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for item in data:
            # CORRECTED: Use the actual keys from your JSON file
            primary_name = item.get("Substance Name (Heading)")
            if primary_name:
                fda_substances_map[primary_name.lower()] = item
            
            # CORRECTED: Use the actual key for other names
            for alias in item.get("Other Names", []):
                fda_substances_map[alias.lower()] = item
        
        print(f"Loaded FDA substances map from: {abs_file_path} (Items loaded: {len(fda_substances_map)})")
        return fda_substances_map
    except FileNotFoundError:
        print(f"Error: FDA substances file not found at {abs_file_path}. Please ensure it exists.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {abs_file_path}. Please check file format.")
    return {}

def load_ingredient_aliases(file_path="data/ingredient_aliases.json"):
    """
    Loads ingredient alias mappings from a JSON file.
    The file should contain a dictionary where keys are alias names (lowercase)
    and values are their canonical names (lowercase).
    """
    aliases_map = {}
    try:
        abs_file_path = os.path.join(os.path.dirname(__file__), file_path)
        with open(abs_file_path, 'r', encoding='utf-8') as f:
            aliases_map = json.load(f)
        print(f"Loaded ingredient aliases from: {abs_file_path} (Items loaded: {len(aliases_map)})")
        return aliases_map
    except FileNotFoundError:
        print(f"Error: Ingredient aliases file not found at {abs_file_path}. Please ensure it exists.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {abs_file_path}. Please check file format.")
    return {}

def load_common_ingredients(file_path="data/common_ingredients_live.json"):
    """
    Loads common ingredients into a set for quick lookup.
    Assumes the JSON file is a flat list of strings.
    """
    common_ingredients_set = set()
    try:
        abs_file_path = os.path.join(os.path.dirname(__file__), file_path)
        with open(abs_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Assumes common_ingredients.json is a flat list of strings
        common_ingredients_set = set(item.lower() for item in data)
        print(f"Loaded common ingredients from: {abs_file_path} (Items loaded: {len(common_ingredients_set)})")
        return common_ingredients_set
    except FileNotFoundError:
        print(f"Error: Common ingredients file not found at {abs_file_path}. Please ensure it exists.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {abs_file_path}. Please check file format.")
    return set()

# NEW FUNCTION: Load common FDA additives from a separate file
def load_common_fda_additives(file_path="data/common_fda_additives.json"):
    """
    Loads a set of common FDA regulated additives for quick lookup.
    Assumes the JSON file is a flat list of lowercase strings.
    """
    common_fda_additives_set = set()
    try:
        abs_file_path = os.path.join(os.path.dirname(__file__), file_path)
        with open(abs_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        common_fda_additives_set = set(item.lower() for item in data)
        print(f"Loaded common FDA additives from: {abs_file_path} (Items loaded: {len(common_fda_additives_set)})")
        return common_fda_additives_set
    except FileNotFoundError:
        print(f"Warning: Common FDA additives file not found at {abs_file_path}. Proceeding without common FDA classification.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {abs_file_path}. Please check file format.")
    return set()

def normalize_string(s):
    """Normalizes a string by converting to lowercase and removing extra spaces and common punctuation."""
    if not isinstance(s, str):
        return ""
    s = s.lower()
    # Remove content in parentheses and brackets
    s = re.sub(r'\((.*?)\)', '', s)
    s = re.sub(r'\[.*?\]', '', s)
    # Replace common punctuation with spaces
    s = re.sub(r'[.,;!?:/\\-_"\'`]+', ' ', s)
    s = s.strip() # THIS IS THE PREVIOUS FIX: ensure it's s.strip()
    return s

# In backend/ingredient_parser.py

# ... (ensure normalize_string is defined above this function if it's a custom helper) ...
# Example:
# def normalize_string(s):
#     if isinstance(s, str):
#         return re.sub(r'[^a-z0-9\s]', '', s.lower()).strip()
#     return ""

def parse_ingredient_string(ingredients_raw, patterns_data, ingredient_aliases_map=None):
    """
    Parses a raw string of ingredients (e.g., from a food label) into a list of structured
    ingredient dictionaries. Each dictionary represents an individual parsed ingredient.
    """
    parsed_ingredients_list = []

    if not isinstance(ingredients_raw, str) or not ingredients_raw.strip():
        return parsed_ingredients_list

    # This regex splits by comma, semicolon, or "and", but not inside parentheses.
    # It accounts for various common delimiters and edge cases.
    # Note: Using `re.split` with a regex that handles "and" outside of parentheses is complex.
    # For simplicity and robustness, often a split by comma, then iterating and refining
    # is more manageable. Let's simplify the split and refine within the loop for now.
    # Original logic of splitting by comma is safer initially.
    individual_ingredient_phrases = [
        phrase.strip() for phrase in ingredients_raw.split(',') if phrase.strip()
    ]

    for ingredient_phrase in individual_ingredient_phrases:
        parsed_ingredient_info = {
            "original_string": ingredient_phrase,
            "base_ingredient": "", # Will be refined below
            "modifiers": [],
            "attributes": {"trust_report_category": "truly_unidentified"}, # Default
            "parenthetical_info": {},
            "unusual_punctuation_found": []
        }

        temp_base_ingredient = ingredient_phrase # Start with the full phrase

        # 1. Extract and store parenthetical information
        # Matches content in ( ) or [ ]
        parenthetical_matches = re.findall(r'\((.*?)\)|\[(.*?)\]', temp_base_ingredient)
        if parenthetical_matches:
            for match in parenthetical_matches:
                # Take the non-empty group (either from () or [])
                content = match[0] if match[0] else match[1]
                content = content.strip() # Clean content inside parentheses

                # Try to categorize parenthetical content using patterns
                categorized = False
                if patterns_data and "parenthetical_examples" in patterns_data:
                    for key, pattern_list in patterns_data["parenthetical_examples"].items():
                        for pattern in pattern_list:
                            if re.search(r'\b' + re.escape(pattern) + r'\b', content, re.IGNORECASE):
                                parsed_ingredient_info["parenthetical_info"][key] = content
                                categorized = True
                                break
                        if categorized:
                            break
                
                # If not categorized by specific examples, store it under 'other'
                if not categorized and content:
                    # Append to 'other' if it already exists, or create it
                    if "other" not in parsed_ingredient_info["parenthetical_info"]:
                        parsed_ingredient_info["parenthetical_info"]["other"] = []
                    parsed_ingredient_info["parenthetical_info"]["other"].append(content)
            
            # Remove ALL parenthetical content from the base string for primary parsing
            temp_base_ingredient = re.sub(r'\s*\(.*?\)\s*|\s*\[.*?\]\s*', ' ', temp_base_ingredient).strip()
            
        # 2. Aggressively clean the base_ingredient for lookup
        # Convert to lowercase for consistent processing
        cleaned_base = temp_base_ingredient.lower()

        # Remove percentages (e.g., "0.1% ", "5%")
        cleaned_base = re.sub(r'\d+(\.\d+)?%\s*', '', cleaned_base)
        
        # Remove "as a X", "for Y" phrases from the base for lookup
        # e.g., "citric acid as a preservative" -> "citric acid"
        cleaned_base = re.sub(r'\s*(as a|for)\s+\w+\b', '', cleaned_base)
        cleaned_base = re.sub(r'\s*used as\s+\w+\b', '', cleaned_base) # Catch "used as"

        # Remove "contains X" (e.g., "contains one or more of the following")
        cleaned_base = re.sub(r'contains\s+[\w\s,]+', '', cleaned_base)

        # Remove other common trailing descriptors for base ingredient clarity
        # These are usually flavor or color descriptors
        cleaned_base = re.sub(r'\b(natural|artificial)\s*flavor(ing)?s?\b', '', cleaned_base)
        cleaned_base = re.sub(r'\b(and\s*)?artificial\s*flavor(ing)?s?\b', '', cleaned_base)
        cleaned_base = re.sub(r'\b(color|colors|colour|colours)\b', '', cleaned_base) # Remove generic color/colour

        # Remove "modified", "enriched", "bleached" as they are modifiers, not core ingredients
        cleaned_base = re.sub(r'\b(modified|enriched|bleached|fortified)\s*', '', cleaned_base)
        
        # Remove "organic"
        cleaned_base = re.sub(r'\borganic\s*', '', cleaned_base)

        # Final cleaning: remove any remaining non-alphanumeric characters (keep spaces)
        # and reduce multiple spaces
        cleaned_base = re.sub(r'[^a-z\s]', '', cleaned_base).strip()
        cleaned_base = re.sub(r'\s+', ' ', cleaned_base).strip()
        
        # If after aggressive cleaning, the base_ingredient became empty or too short,
        # revert to a less aggressive clean for the base to ensure we don't lose the main ingredient.
        # This uses a slightly less aggressive regex for alphanumeric and space.
        if not cleaned_base or len(cleaned_base) < 2: # Very short strings might be single letters after cleaning
            cleaned_base = normalize_string(temp_base_ingredient) # Fallback to general normalize_string

        # ⭐️ NEW: Apply alias lookup AFTER initial aggressive cleaning
        if ingredient_aliases_map and cleaned_base in ingredient_aliases_map:
            cleaned_base = ingredient_aliases_map[cleaned_base]
            # print(f"DEBUG: Applied alias. '{original_string}' -> '{cleaned_base}'") # For debugging

        # Set the final base_ingredient
        parsed_ingredient_info["base_ingredient"] = cleaned_base

        # 3. Extract and store descriptive modifiers (e.g., "natural", "organic")
        # These are found from the *original* ingredient phrase before aggressive cleaning
        if patterns_data and "descriptive_modifiers" in patterns_data:
            for modifier_key, modifier_patterns in patterns_data["descriptive_modifiers"].items():
                for pattern in modifier_patterns:
                    # Search in the original phrase or a less cleaned version if needed
                    if re.search(r'\b' + re.escape(pattern) + r'\b', ingredient_phrase.lower()):
                        # Only add if not already in modifiers to avoid duplicates
                        if modifier_key not in parsed_ingredient_info["modifiers"]:
                            parsed_ingredient_info["modifiers"].append(modifier_key)
                        break # Found a pattern for this modifier key, move to next key

        # 4. Check for unusual punctuation (excluding those handled by parentheticals)
        # Use the original ingredient phrase, but strip parenthetical content from it first
        cleaned_phrase_for_punc_check = re.sub(r'\s*\(.*?\)\s*|\s*\[.*?\]\s*', ' ', ingredient_phrase)
        if re.search(r'[\[\]{}<>/\\~!@#$%^&*`"\'_+=|]', cleaned_phrase_for_punc_check):
            # Only add "other" if not already present
            if "other" not in parsed_ingredient_info["unusual_punctuation_found"]:
                parsed_ingredient_info["unusual_punctuation_found"].append("other")
        
        # Add the fully parsed individual ingredient to our list
        parsed_ingredients_list.append(parsed_ingredient_info)

    return parsed_ingredients_list

# MODIFIED FUNCTION: categorize_parsed_ingredients
def categorize_parsed_ingredients(parsed_ingredients, fda_substances_map, common_ingredients_set, common_fda_additives_set):
    parsed_fda_common = []
    parsed_fda_non_common = []
    parsed_common_only = []
    truly_unidentified = []
    all_fda_parsed_for_report = [] # Changed back to a list of dicts like {"name": ..., "is_common": ...}

    print(f"DEBUG_PARSER: Starting categorization for {len(parsed_ingredients)} ingredients.")

    for ingredient in parsed_ingredients:
        category = ingredient.get("trust_report_category")
        base_ingredient = ingredient.get("base_ingredient")
        original_string = ingredient.get("original_string")

        print(f"DEBUG_PARSER: Processing: '{original_string}' (Base: '{base_ingredient}') - Initial Category: '{category}'")

        fda_substance_obj = fda_substances_map.get(base_ingredient)

        if fda_substance_obj:
            # Get the correct substance name from the FDA object
            fda_substance_name = fda_substance_obj.get("Substance Name (Heading)", base_ingredient) # Use correct key

            print(f"DEBUG_PARSER: Match found in fda_substances_map for '{base_ingredient}': {fda_substance_name}")

            # Check if this FDA substance is in our list of common FDA additives
            if fda_substance_name.lower() in common_fda_additives_set: # Use the new set for lookup
                ingredient["trust_report_category"] = "common_fda_regulated"
                parsed_fda_common.append(ingredient)
                # Append dictionary with 'name' and 'is_common' as expected by report
                all_fda_parsed_for_report.append({"name": fda_substance_name, "is_common": True})
            else:
                ingredient["trust_report_category"] = "fda_non_common"
                parsed_fda_non_common.append(ingredient)
                # Append dictionary with 'name' and 'is_common' as expected by report
                all_fda_parsed_for_report.append({"name": fda_substance_name, "is_common": False})
        elif base_ingredient in common_ingredients_set: # If not FDA, check for common food
            ingredient["trust_report_category"] = "common_food_only" # Updated category name for clarity
            parsed_common_only.append(ingredient)
        else: # If neither FDA nor common_food, it's unidentified
            ingredient["trust_report_category"] = "truly_unidentified"
            truly_unidentified.append(ingredient)

        print(f"DEBUG_PARSER: Final category for '{original_string}' (Base: '{base_ingredient}'): {ingredient.get('trust_report_category')}")

    return parsed_fda_common, parsed_fda_non_common, parsed_common_only, truly_unidentified, all_fda_parsed_for_report

def calculate_data_completeness(parsed_ingredients, truly_unidentified_ingredients):
    """
    Calculates data completeness based on the proportion of identified ingredients.
    """
    total_ingredients = len(parsed_ingredients)
    identified_ingredients = total_ingredients - len(truly_unidentified_ingredients)

    if total_ingredients == 0:
        return 0.0, "No Ingredients Provided"

    completeness_score = (identified_ingredients / total_ingredients) * 100

    if completeness_score >= 90:
        completeness_level = "High"
    elif completeness_score >= 60:
        completeness_level = "Medium"
    else:
        completeness_level = "Low"

    return round(completeness_score, 2), completeness_level


def calculate_nova_score(parsed_ingredients):
    """
    Calculates the NOVA score based on ingredient categories.
    
    NOVA Score Categories:
    1: Unprocessed or minimally processed foods
    2: Processed culinary ingredients
    3: Processed foods
    4: Ultra-processed foods
    
    This function simplifies NOVA classification based on the trust_report_category.
    """
    # Initialize counts for each simplified NOVA group
    group_1_count = 0  # Common food only
    group_2_count = 0  # FDA non-common (preservatives, additives, etc.) - often indicates processed culinary ingredients/processed foods
    group_3_count = 0  # Complex, potentially ultra-processed (currently mapping common_fda_regulated, as these are often highly processed components)
    group_4_count = 0  # Truly unidentified (unknown impact, safer to lean towards higher processing)

    for ingredient in parsed_ingredients:
        category = ingredient.get("trust_report_category")
        if category == "common_food_only":
            group_1_count += 1
        elif category == "fda_non_common":
            group_2_count += 1
        elif category == "common_fda_regulated":
            group_3_count += 1 # These are specific additives often in processed/ultra-processed foods
        elif category == "truly_unidentified":
            group_4_count += 1 # Unknown, assume higher processing for safety/completeness

    total_count = len(parsed_ingredients)

    if total_count == 0:
        return 0 # Or handle as "N/A"

    # Determine overall NOVA score based on the highest category present
    # Prioritize higher NOVA categories if their ingredients are present
    if group_4_count > 0:
        return 4 # Ultra-processed if truly unidentified ingredients are present
    elif group_3_count > 0:
        return 4 # Common FDA regulated (e.g., Sodium Benzoate, HFCS) often indicate ultra-processed
    elif group_2_count > 0:
        return 3 # FDA non-common (other additives) implies processed foods
    elif group_1_count > 0:
        return 1 # Only common food items
    else:
        return 0 # Should not happen if there are ingredients, but a fallback

def get_nova_description(nova_score):
    """Returns the NOVA score description."""
    nova_descriptions = {
        1: "Unprocessed or minimally processed foods",
        2: "Processed culinary ingredients",
        3: "Processed foods",
        4: "Ultra-processed foods",
        0: "N/A - No ingredients or NOVA score calculated"
    }
    return nova_descriptions.get(nova_score, "Unknown NOVA score")


if __name__ == '__main__':
    # Test loading patterns
    patterns = load_patterns()
    if not patterns:
        print("Failed to load patterns. Exiting.")
        sys.exit(1)

    # Test loading FDA substances
    fda_substances_map = load_fda_substances()
    if not fda_substances_map:
        print("Failed to load FDA substances. Exiting.")
        # sys.exit(1) # Do not exit, continue with partial data for other tests

    # Test loading common ingredients
    common_ingredients_set = load_common_ingredients()
    if not common_ingredients_set:
        print("Failed to load common ingredients. Exiting.")
        # sys.exit(1) # Do not exit, continue with partial data for other tests
    
    # Test loading common FDA additives
    common_fda_additives_set = load_common_fda_additives()
    # No exit on warning, it's fine if this file isn't critical for initial tests

    # NEW: Load ingredient aliases
    ingredient_aliases_map = load_ingredient_aliases()

    test_ingredients = [
        "ORGANIC CANE SUGAR",
        "WATER",
        "0.1% SODIUM BENZOATE AS A PRESERVATIVE",
        "SALT (FOR FLAVOR)",
        "CHILI PEPPERS",
        "VINEGAR",
        "NATURAL FLAVORS (SPICE EXTRACTS)",
        "SPICES (INCLUDING PAPRIKA)",
        "HIGH FRUCTOSE CORN SYRUP",
        "CITRIC ACID",
        "XANTHAN GUM (THICKENER)",
        "CORN SYRUP SOLIDS" # Added for alias testing
    ]

    print("\n--- Parsing and Categorization Test ---")
    parsed_test_ingredients = []
    for ingredient_string in test_ingredients:
        # ⭐ IMPORTANT: Pass ingredient_aliases_map here!
        parsed_test_ingredients.append(parse_ingredient_string(ingredient_string, patterns, ingredient_aliases_map))

    (
        parsed_fda_common,
        parsed_fda_non_common,
        parsed_common_only,
        truly_unidentified,
        all_fda_parsed_for_report
    ) = categorize_parsed_ingredients(
        parsed_ingredients=parsed_test_ingredients,
        fda_substances_map=fda_substances_map,
        common_ingredients_set=common_ingredients_set,
        common_fda_additives_set=common_fda_additives_set
    )

    print("\n--- Categorized Results ---")
    print(f"   Common FDA-regulated ({len(parsed_fda_common)}): {[p['base_ingredient'] for p in parsed_fda_common]}")
    print(f"   Non-Common FDA-regulated ({len(parsed_fda_non_common)}): {[p['base_ingredient'] for p in parsed_fda_non_common]}")
    print(f"   Common Food Only ({len(parsed_common_only)}): {[p['base_ingredient'] for p in parsed_common_only]}")
    print(f"   Truly Unidentified ({len(truly_unidentified)}): {[p['base_ingredient'] for p in truly_unidentified]}")
    print(f"   All FDA Additives for Report ({len(all_fda_parsed_for_report)}): {[p['name'] for p in all_fda_parsed_for_report]}")


    # Test data completeness
    score, completeness_level = calculate_data_completeness(parsed_test_ingredients, truly_unidentified)
    print(f"Data Completeness: {score}% ({completeness_level})")

    # Test NOVA score
    nova_score_val = calculate_nova_score(parsed_test_ingredients)
    nova_desc = get_nova_description(nova_score_val)
    print(f"NOVA Score: {nova_score_val} ({nova_desc})")

    # Test HTML generation (optional, requires report_generator.py to be importable)
    try:
        from report_generator import generate_trust_report_html
        html_report = generate_trust_report_html(
            product_name="Test Product",
            ingredients_raw=", ".join(test_ingredients),
            parsed_ingredients=parsed_test_ingredients, # Pass the full parsed list for NOVA calc
            parsed_fda_common=parsed_fda_common,
            parsed_fda_non_common=parsed_fda_non_common,
            parsed_common_only=parsed_common_only,
            truly_unidentified=truly_unidentified,
            data_completeness_score=score,
            data_completeness_level=completeness_level,
            nova_score=nova_score_val,
            nova_description=nova_desc,
            all_fda_parsed_for_report=all_fda_parsed_for_report # Pass the list of simplified FDA dicts
        )
        with open("trust_report_test.html", "w", encoding="utf-8") as f:
            f.write(html_report)
        print("\nGenerated trust_report_test.html")
    except ImportError:
        print("\nSkipping HTML generation: report_generator.py not found or has errors.")
    except Exception as e:
        print(f"\nError generating HTML report: {e}")