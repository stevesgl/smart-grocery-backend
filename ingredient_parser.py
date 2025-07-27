# FILE: backend/ingredient_parser.py

import json
import re
import os
import pandas as pd # Ensure pandas is installed if this is used elsewhere

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
    try:
        # Construct absolute path for consistency
        abs_file_path = os.path.join(os.path.dirname(__file__), file_path)
        with open(abs_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        fda_substances_map = {}
        for item in data:
            primary_name = item.get("name")
            if primary_name:
                fda_substances_map[primary_name.lower()] = item
            for alias in item.get("other_names", []):
                fda_substances_map[alias.lower()] = item # Store the same full item for aliases
        print(f"Loaded FDA substances map from: {abs_file_path}")
        return fda_substances_map
    except FileNotFoundError:
        print(f"Error: FDA substances file not found at {abs_file_path}. Please ensure it exists.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {abs_file_path}. Please check file format.")
    return {} # Return an empty dict on error

def load_common_ingredients(file_path="data/common_ingredients_live.json"):
    """
    Loads common ingredients into a normalized lowercase set for quick lookup.
    Assumes the file contains a JSON list of strings.
    """
    try:
        # Construct absolute path for consistency
        abs_file_path = os.path.join(os.path.dirname(__file__), file_path)
        with open(abs_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        ingredients = set()
        for item in data:
            if isinstance(item, str): # Ensure it's a string before lowering and adding
                ingredients.add(item.lower())
            else:
                print(f"Warning: Unexpected item type in common ingredients file: {type(item)}. Expected string.")
        print(f"Loaded common ingredients from: {abs_file_path}")
        return ingredients
    except FileNotFoundError:
        print(f"Error: Common ingredients file not found at {abs_file_path}. Please ensure it exists.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {abs_file_path}. Please check file format.")
    return set()

# --- Parsing and Categorization Logic (Keep as is unless other errors appear) ---

def normalize_string(s):
    """Normalizes a string by lowercasing and removing extra spaces/punctuation."""
    s = s.lower()
    s = re.sub(r'[^a-z0-9\s]', '', s) # Remove non-alphanumeric except spaces
    s = re.sub(r'\s+', ' ', s).strip() # Replace multiple spaces with one, strip leading/trailing
    return s

def parse_ingredient_string(ingredient_string, patterns, common_ingredients_set, fda_substances_map):
    """
    Parses a raw ingredient string into a list of structured ingredient dictionaries.
    Each dictionary includes original string, base ingredient, modifiers, and category.
    """
    # Split by comma, but not if comma is inside parentheses
    ingredients = [s.strip() for s in re.split(r',(?![^(]*\))', ingredient_string) if s.strip()]
    parsed_results = []

    for original_string in ingredients:
        base_ingredient = normalize_string(original_string)
        modifiers = []
        attributes = {}
        parenthetical_info = {}
        unusual_punctuation_found = []

        # Step 1: Extract and store parenthetical information
        parenthetical_matches = re.findall(r'\((.*?)\)', original_string)
        if parenthetical_matches:
            # For simplicity, store the content of the first parenthesis
            parenthetical_info = {"raw": parenthetical_matches[0]}
            # Remove parentheses content for base ingredient determination
            base_ingredient = re.sub(r'\s*\(.*?\)\s*', '', original_string).strip()
            base_ingredient = normalize_string(base_ingredient)

        # Step 2: Identify and remove common descriptive modifiers (e.g., "organic", "fresh")
        # Ensure patterns.get("descriptive_modifiers", {}) exists to prevent KeyError
        for modifier_type, modifier_list in patterns.get("descriptive_modifiers", {}).items():
            for modifier in modifier_list:
                # Use word boundaries (\b) to match whole words
                if re.search(r'\b' + re.escape(modifier) + r'\b', base_ingredient):
                    modifiers.append(modifier)
                    # Remove the matched modifier from the base ingredient
                    base_ingredient = re.sub(r'\b' + re.escape(modifier) + r'\b', '', base_ingredient).strip()
                    # Example of adding to attributes: attributes["preparation_method"] = modifier_type

        # Step 3: Clean up base ingredient after modifier removal
        base_ingredient = normalize_string(base_ingredient)

        # Step 4: Determine ingredient type and initial category
        trust_report_category = "truly_unidentified" # Default category

        # Check if it's an FDA substance
        if base_ingredient in fda_substances_map:
            if base_ingredient in common_ingredients_set:
                trust_report_category = "common_fda_regulated"
            else:
                trust_report_category = "fda_non_common"
        # If not FDA, check if it's a common food
        elif base_ingredient in common_ingredients_set:
            trust_report_category = "common_food"
        # Special handling for "flavors" (if not already categorized by FDA lookup)
        if "flavor" in base_ingredient:
            if "natural and artificial" in original_string.lower():
                attributes["source_type"] = "artificial"
                trust_report_category = "fda_non_common" # Categorize specifically as non-common due to "artificial"
            elif "artificial flavor" in original_string.lower():
                attributes["source_type"] = "artificial"
                trust_report_category = "fda_non_common"
            elif "natural flavor" in original_string.lower():
                attributes["source_type"] = "natural"
                if trust_report_category == "truly_unidentified": # Only assign if not already more specific
                    trust_report_category = "common_food" # Generally considered common

        # Add initial category to attributes for easier filtering later if needed
        attributes["trust_report_category"] = trust_report_category

        parsed_results.append({
            "original_string": original_string,
            "base_ingredient": base_ingredient,
            "modifiers": modifiers,
            "attributes": attributes,
            "parenthetical_info": parenthetical_info,
            "unusual_punctuation_found": unusual_punctuation_found,
            "trust_report_category": trust_report_category # Redundant with attributes, but useful for direct access
        })
    return parsed_results

def categorize_parsed_ingredients(parsed_ingredients, fda_substances_map):
    """
    Categorizes parsed ingredients into common FDA, non-common FDA, common only,
    and truly unidentified.
    Returns: parsed_fda_common, parsed_fda_non_common, parsed_common_only, truly_unidentified, all_fda_parsed_for_report
    """
    parsed_fda_common = []
    parsed_fda_non_common = []
    parsed_common_only = []
    truly_unidentified = []
    all_fda_parsed_for_report = {} # Use a dictionary to store unique FDA items by their lowercase name

    for ingredient in parsed_ingredients:
        category = ingredient.get("trust_report_category")
        base_ingredient = ingredient.get("base_ingredient")

        # Get the original FDA substance object from the map if it exists
        fda_substance_obj = fda_substances_map.get(base_ingredient)

        if category == "common_fda_regulated":
            parsed_fda_common.append(ingredient)
            if fda_substance_obj:
                all_fda_parsed_for_report[fda_substance_obj['name'].lower()] = fda_substance_obj
        elif category == "fda_non_common":
            parsed_fda_non_common.append(ingredient)
            if fda_substance_obj:
                all_fda_parsed_for_report[fda_substance_obj['name'].lower()] = fda_substance_obj
        elif category == "common_food":
            parsed_common_only.append(ingredient)
        else: # "truly_unidentified" or any other unhandled category
            truly_unidentified.append(ingredient)

    # Convert the dictionary values to a list for the report
    return parsed_fda_common, parsed_fda_non_common, parsed_common_only, truly_unidentified, list(all_fda_parsed_for_report.values())

def calculate_data_completeness(parsed_ingredients, truly_unidentified):
    """Calculates the data completeness score and level."""
    total_ingredients = len(parsed_ingredients)
    unidentified_count = len(truly_unidentified)

    if total_ingredients == 0:
        return 0.0, "None"

    identified_count = total_ingredients - unidentified_count
    score = (identified_count / total_ingredients) * 100

    if score >= 90:
        completeness = "High"
    elif score >= 70:
        completeness = "Medium"
    else:
        completeness = "Low"

    return round(score, 2), completeness

def calculate_nova_score(parsed_ingredients):
    """
    Calculates the NOVA score based on parsed ingredients.
    This is a simplified example. A real NOVA scoring system is complex.
    For MVP, we'll use a basic heuristic: if any identified ingredient is
    "fda_non_common" or contains "artificial flavor", it's ultra-processed.
    Otherwise, if there are some common foods and no unidentified, it's minimally processed.
    This logic needs to be refined based on actual NOVA criteria.
    """
    has_fda_non_common = False
    has_common_food = False
    for ingredient in parsed_ingredients:
        category = ingredient.get("trust_report_category")
        if category == "fda_non_common" or (ingredient.get("base_ingredient") == "flavors" and ingredient.get("attributes", {}).get("source_type") == "artificial"):
            has_fda_non_common = True
        if category == "common_food":
            has_common_food = True

    if has_fda_non_common:
        return 4 # Ultra-Processed Food
    elif has_common_food and not has_fda_non_common and len(parsed_ingredients) > 0:
        return 1 # Unprocessed or minimally processed
    else:
        return 3 # Processed or culinary ingredients (default if not clearly 1 or 4)


def get_nova_description(nova_score):
    """Returns a descriptive string for the NOVA score."""
    if nova_score == 1:
        return "Unprocessed or minimally processed food"
    elif nova_score == 2:
        return "Processed culinary ingredients" # Not currently calculated, but placeholder
    elif nova_score == 3:
        return "Processed food"
    elif nova_score == 4:
        return "Ultra-Processed Food"
    else:
        return "Not Classified"

# --- Main execution for testing purposes (keep as is) ---
if __name__ == '__main__':
    print("Running ingredient_parser.py directly for testing...")
    # Load data for testing
    patterns_data_test = load_patterns()
    fda_substances_map_test = load_fda_substances()
    common_ingredients_set_test = load_common_ingredients()

    if not patterns_data_test or not fda_substances_map_test or not common_ingredients_set_test:
        print("Failed to load necessary data for testing. Exiting.")
        sys.exit(1)

    test_strings = [
        "chicken breast, boneless, skinless, raw",
        "enriched bleached wheat flour (niacin, reduced iron, thiamin mononitrate, riboflavin, folic acid)",
        "water (filtered) and sugar",
        "natural and artificial flavors",
        "sugar, brown",
        "sodium selenite",
        "calcium carbonate (fortified)",
        "milk, whole, pasteurized, vitamin d added",
        "WATER, PINTO BEANS, ONION, TOMATO, SALT, JALAPENO PEPPER, SOYBEAN OIL, SPICES",
        "ENRICHED WHEAT FLOUR (WHEAT FLOUR, NIACIN, REDUCED IRON, THIAMIN MONONITRATE, RIBOFLAVIN, FOLIC ACID), WATER, HIGH FRUCTOSE CORN SYRUP, YEAST, SALT, VEGETABLE OIL (SOYBEAN OIL, PALM OIL, CANOLA OIL), MONOGLYCERIDES, CALCIUM PROPIONATE (PRESERVATIVE), CALCIUM SULFATE, ENZYMES, AMMONIUM SULFATE, ASCORBIC ACID (DOUGH CONDITIONER), AZODICARBONAMIDE, L-CYSTEINE HYDROCHLORIDE."
    ]

    print("\n--- Running ingredient parsing tests ---")
    for i, s in enumerate(test_strings):
        print(f"\n--- Test Case {i+1}: {s} ---")
        parsed = parse_ingredient_string(s, patterns_data_test, common_ingredients_set_test, fda_substances_map_test)
        print("Parsed Ingredients:")
        for p_ing in parsed:
            print(f"  - Original: '{p_ing['original_string']}' -> Base: '{p_ing['base_ingredient']}' (Category: {p_ing['trust_report_category']})")
            if p_ing['modifiers']:
                print(f"    Modifiers: {p_ing['modifiers']}")
            if p_ing['parenthetical_info']:
                print(f"    Parenthetical: {p_ing['parenthetical_info']['raw']}")
            if p_ing['attributes']:
                print(f"    Attributes: {p_ing['attributes']}")

        # Test categorization
        parsed_fda_common, parsed_fda_non_common, parsed_common_only, truly_unidentified, all_fda_parsed_for_report = \
            categorize_parsed_ingredients(parsed, fda_substances_map_test)

        print("\nCategorized Results:")
        print(f"  Common FDA-regulated ({len(parsed_fda_common)}): {[p['base_ingredient'] for p in parsed_fda_common]}")
        print(f"  Non-Common FDA-regulated ({len(parsed_fda_non_common)}): {[p['base_ingredient'] for p in parsed_fda_non_common]}")
        print(f"  Common Food Only ({len(parsed_common_only)}): {[p['base_ingredient'] for p in parsed_common_only]}")
        print(f"  Truly Unidentified ({len(truly_unidentified)}): {[p['base_ingredient'] for p in truly_unidentified]}")
        print(f"  All FDA Additives for Report ({len(all_fda_parsed_for_report)}): {[p['name'] for p in all_fda_parsed_for_report]}")


        # Test data completeness
        score, completeness_level = calculate_data_completeness(parsed, truly_unidentified)
        print(f"Data Completeness: {score}% ({completeness_level})")

        # Test NOVA score
        nova_score_val = calculate_nova_score(parsed)
        nova_desc = get_nova_description(nova_score_val)
        print(f"NOVA Score: {nova_score_val} ({nova_desc})")

        # Test HTML generation (optional, requires report_generator.py to be importable)
        try:
            from report_generator import generate_trust_report_html
            html_report = generate_trust_report_html(all_fda_parsed_for_report)
            # print("\nGenerated HTML (first 500 chars):\n", html_report[:500])
        except ImportError:
            print("report_generator.py not found, skipping HTML generation test.")