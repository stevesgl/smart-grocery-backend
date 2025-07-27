# FILE: backend/ingredient_parser.py

import json
import re
import os
import pandas as pd
import sys

def load_patterns(file_path="data/ingredient_naming_patterns.json"):
    # ... (keep this function as is) ...
    try:
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
    # ... (keep this function as is) ...
    try:
        abs_file_path = os.path.join(os.path.dirname(__file__), file_path)
        with open(abs_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        fda_substances_map = {}
        for item in data:
            primary_name = item.get("name")
            if primary_name:
                fda_substances_map[primary_name.lower()] = item
            for alias in item.get("other_names", []):
                fda_substances_map[alias.lower()] = item
        print(f"Loaded FDA substances map from: {abs_file_path}")
        return fda_substances_map
    except FileNotFoundError:
        print(f"Error: FDA substances file not found at {abs_file_path}. Please ensure it exists.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {abs_file_path}. Please check file format.")
    return {}

def load_common_ingredients(file_path="data/common_ingredients_live.json"):
    # ... (keep this function as is) ...
    try:
        abs_file_path = os.path.join(os.path.dirname(__file__), file_path)
        with open(abs_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        ingredients = set()
        for item in data:
            if isinstance(item, str):
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

def normalize_string(s):
    """Normalizes a string by lowercasing and removing extra spaces/punctuation.
       This is for general normalization, specific parsing needs more logic."""
    s = s.lower()
    # Remove non-alphanumeric except spaces. Keep hyphen for now if part of a name.
    s = re.sub(r'[^a-z0-9\s-]', '', s) # Allow hyphens.
    s = re.sub(r'\s+', ' ', s).strip()
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
        current_processing_string = original_string # Use a working copy
        base_ingredient = ""
        modifiers = []
        attributes = {}
        parenthetical_info = {}
        unusual_punctuation_found = []

        # Step 1: Extract and store parenthetical information
        parenthetical_matches = re.findall(r'\((.*?)\)', current_processing_string)
        if parenthetical_matches:
            # For simplicity, store the content of the first parenthesis
            parenthetical_info = {"raw": parenthetical_matches[0]}
            # Remove parentheses content for base ingredient determination
            current_processing_string = re.sub(r'\s*\(.*?\)\s*', '', current_processing_string).strip()

        # Step 2: Remove percentages (e.g., "0.1%")
        # This regex matches numbers, optional decimal, optional %, followed by space
        current_processing_string = re.sub(r'\b\d+\.?\d*%\s*', '', current_processing_string).strip()

        # Step 3: Remove common descriptive phrases like "as a preservative", "added as a..."
        # This needs to be done *before* full normalization to preserve full words
        # Add more patterns here if needed
        current_processing_string = re.sub(r'\s*(as\s+a\s+\w+)\s*', '', current_processing_string, flags=re.IGNORECASE).strip()
        current_processing_string = re.sub(r'\s*(added\s+as\s+\w+)\s*', '', current_processing_string, flags=re.IGNORECASE).strip()
        current_processing_string = re.sub(r'\s*(contains\s+\w+)\s*', '', current_processing_string, flags=re.IGNORECASE).strip()


        # Step 4: Identify and remove common descriptive modifiers (e.g., "organic", "fresh")
        # Ensure patterns.get("descriptive_modifiers", {}) exists to prevent KeyError
        # Operate on the cleaned string for modifiers
        temp_base_for_modifiers = normalize_string(current_processing_string) # Normalize temp string for modifier matching
        for modifier_type, modifier_list in patterns.get("descriptive_modifiers", {}).items():
            for modifier in modifier_list:
                # Use word boundaries (\b) to match whole words in the normalized string
                if re.search(r'\b' + re.escape(modifier) + r'\b', temp_base_for_modifiers):
                    modifiers.append(modifier)
                    # Remove the matched modifier from the temp string for final base ingredient
                    temp_base_for_modifiers = re.sub(r'\b' + re.escape(modifier) + r'\b', '', temp_base_for_modifiers).strip()

        # The final base ingredient for lookup should be the cleanest version
        base_ingredient = normalize_string(temp_base_for_modifiers)


        # Step 5: Determine initial category (this is just an initial guess, refined in categorize_parsed_ingredients)
        trust_report_category = "truly_unidentified" # Default category

        # We'll rely more heavily on categorize_parsed_ingredients for final classification
        # but a preliminary check here can set a good starting point.
        if base_ingredient in fda_substances_map:
            # This is an FDA substance, determine common/non-common later in categorization
            trust_report_category = "fda_substance_candidate" # New intermediate category
        elif base_ingredient in common_ingredients_set:
            trust_report_category = "common_food"
        # Special handling for "flavors" (if not already categorized by FDA lookup)
        elif "flavor" in base_ingredient:
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

        attributes["trust_report_category"] = trust_report_category

        parsed_results.append({
            "original_string": original_string,
            "base_ingredient": base_ingredient,
            "modifiers": modifiers,
            "attributes": attributes,
            "parenthetical_info": parenthetical_info,
            "unusual_punctuation_found": unusual_punctuation_found,
            "trust_report_category": trust_report_category
        })
    return parsed_results

def categorize_parsed_ingredients(parsed_ingredients, fda_substances_map):
    parsed_fda_common = []
    parsed_fda_non_common = []
    parsed_common_only = []
    truly_unidentified = []
    all_fda_parsed_for_report = {}

    print(f"DEBUG_PARSER: Starting categorization for {len(parsed_ingredients)} ingredients.")

    for ingredient in parsed_ingredients:
        category = ingredient.get("trust_report_category") # Get initial category from parse_ingredient_string
        base_ingredient = ingredient.get("base_ingredient")
        original_string = ingredient.get("original_string")

        print(f"DEBUG_PARSER: Processing: '{original_string}' (Base: '{base_ingredient}') - Initial Category: '{category}'")

        fda_substance_obj = fda_substances_map.get(base_ingredient)

        if fda_substance_obj:
            print(f"DEBUG_PARSER: Match found in fda_substances_map for '{base_ingredient}': {fda_substance_obj['name']}")
            if fda_substance_obj.get("is_common_substance", False):
                ingredient["trust_report_category"] = "common_fda_regulated"
                parsed_fda_common.append(ingredient)
                all_fda_parsed_for_report[fda_substance_obj['name'].lower()] = fda_substance_obj
            else:
                ingredient["trust_report_category"] = "fda_non_common"
                parsed_fda_non_common.append(ingredient)
                all_fda_parsed_for_report[fda_substance_obj['name'].lower()] = fda_substance_obj
        elif category == "common_food": # If not FDA, check for common food (category passed from parser)
            parsed_common_only.append(ingredient)
        else: # If neither FDA nor common_food, it's unidentified
            ingredient["trust_report_category"] = "truly_unidentified"
            truly_unidentified.append(ingredient)

        print(f"DEBUG_PARSER: Final category for '{base_ingredient}': {ingredient.get('trust_report_category')}")

    return parsed_fda_common, parsed_fda_non_common, parsed_common_only, truly_unidentified, list(all_fda_parsed_for_report.values())

# ... (keep calculate_data_completeness, calculate_nova_score, get_nova_description as is) ...

# --- Main execution for testing purposes (keep as is) ---
if __name__ == '__main__':
    # ... (keep this block as is) ...
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
        "ENRICHED WHEAT FLOUR (WHEAT FLOUR, NIACIN, REDUCED IRON, THIAMIN MONONITRATE, RIBOFLAVIN, FOLIC ACID), WATER, HIGH FRUCTOSE CORN SYRUP, YEAST, SALT, VEGETABLE OIL (SOYBEAN OIL, PALM OIL, CANOLA OIL), MONOGLYCERIDES, CALCIUM PROPIONATE (PRESERVATIVE), CALCIUM SULFATE, ENZYMES, AMMONIUM SULFATE, ASCORBIC ACID (DOUGH CONDITIONER), AZODICARBONAMIDE, L-CYSTEINE HYDROCHLORIDE.",
        # Add a specific test case for Sodium Benzoate to confirm
        "0.1% SODIUM BENZOATE AS A PRESERVATIVE"
    ]

    print("\n--- Running ingredient parsing tests ---")
    for i, s in enumerate(test_strings):
        print(f"\n--- Test Case {i+1}: {s} ---")
        parsed = parse_ingredient_string(s, patterns_data_test, common_ingredients_set_test, fda_substances_map_test)
        print("Parsed Ingredients:")
        for p_ing in parsed:
            print(f"   - Original: '{p_ing['original_string']}' -> Base: '{p_ing['base_ingredient']}' (Category: {p_ing['trust_report_category']})")
            if p_ing['modifiers']:
                print(f"     Modifiers: {p_ing['modifiers']}")
            if p_ing['parenthetical_info']:
                print(f"     Parenthetical: {p_ing['parenthetical_info']['raw']}")
            if p_ing['attributes']:
                print(f"     Attributes: {p_ing['attributes']}")

        # Test categorization
        parsed_fda_common, parsed_fda_non_common, parsed_common_only, truly_unidentified, all_fda_parsed_for_report = \
            categorize_parsed_ingredients(parsed, fda_substances_map_test)

        print("\nCategorized Results:")
        print(f"   Common FDA-regulated ({len(parsed_fda_common)}): {[p['base_ingredient'] for p in parsed_fda_common]}")
        print(f"   Non-Common FDA-regulated ({len(parsed_fda_non_common)}): {[p['base_ingredient'] for p in parsed_fda_non_common]}")
        print(f"   Common Food Only ({len(parsed_common_only)}): {[p['base_ingredient'] for p in parsed_common_only]}")
        print(f"   Truly Unidentified ({len(truly_unidentified)}): {[p['base_ingredient'] for p in truly_unidentified]}")
        print(f"   All FDA Additives for Report ({len(all_fda_parsed_for_report)}): {[p['name'] for p in all_fda_parsed_for_report]}")


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