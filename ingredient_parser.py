import json
import re
import os
import pandas as pd

def load_patterns(file_path="data/ingredient_naming_patterns.json"):
    """
    Loads descriptive modifiers, parenthetical examples, and punctuation patterns from JSON.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            patterns = json.load(f)
        print(f"Loaded patterns from: {file_path}")
        return patterns
    except FileNotFoundError:
        print(f"Error: Pattern file not found at {file_path}. Please ensure it exists.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {file_path}. Please check file format.")
    return {}

def load_fda_substances(file_path="data/all_fda_substances_full_live.json"):
    """
    Loads FDA substances into a dictionary for quick lookup by name or alias,
    returning the full substance object.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        fda_substances_map = {}
        for item in data:
            # Store by primary name
            primary_name = item.get("name")
            if primary_name:
                fda_substances_map[primary_name.lower()] = item
            # Store by other names/aliases
            for alias in item.get("other_names", []):
                fda_substances_map[alias.lower()] = item # Store the same full object for aliases
        print(f"Loaded FDA substances from: {file_path}")
        return fda_substances_map
    except FileNotFoundError:
        print(f"Error: FDA substances file not found at {file_path}.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {file_path}. Check file format.")
    return {}

def load_common_ingredients(file_path="data/common_ingredients_live.json"):
    """
    Loads common ingredients into a normalized lowercase set for quick lookup.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            common_ingredients = json.load(f)
        common_ingredients_set = {item.lower() for item in common_ingredients}
        print(f"Loaded common ingredients from: {file_path}")
        return common_ingredients_set
    except FileNotFoundError:
        print(f"Error: Common ingredients file not found at {file_path}.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {file_path}. Check file format.")
    return set()

def _remove_parentheticals(segment):
    """Removes text within parentheses and their content from a segment."""
    return re.sub(r'\s*\(.*?\)\s*', '', segment).strip()

def _clean_segment(segment):
    """
    Cleans a segment by removing extra spaces, dashes, and periods.
    Converts to lowercase.
    """
    segment = segment.lower().strip()
    segment = re.sub(r'[-\.]', '', segment) # Remove dashes and periods
    segment = re.sub(r'\s+', ' ', segment) # Replace multiple spaces with single
    return segment

def _match_pattern(segment, patterns):
    """
    Checks if a segment matches any predefined patterns.
    Returns (True, cleaned_segment) if matched, (False, original_segment) otherwise.
    """
    for pattern_group in patterns.get("descriptive_modifiers", []):
        for pattern in pattern_group["patterns"]:
            if re.search(r'\b' + re.escape(pattern.lower()) + r'\b', segment):
                # If a pattern is found, remove it and return the cleaned segment
                cleaned_segment = re.sub(r'\b' + re.escape(pattern.lower()) + r'\b', '', segment).strip()
                return True, _clean_segment(cleaned_segment)
    return False, segment

def _classify_ingredient(segment, patterns_data, common_ingredients_set, fda_substances_map):
    """
    Classifies a single ingredient segment based on common ingredients and FDA substances.
    """
    original_string = segment
    segment_no_parentheticals = _remove_parentheticals(segment)
    cleaned_segment = _clean_segment(segment_no_parentheticals)

    base_name = ""
    trust_report_category = "unknown"
    used_for = []
    other_names = []
    ingredient_type = "specific" # Default type

    # Attempt to match patterns first (e.g., "enriched wheat flour")
    matched_pattern, processed_segment = _match_pattern(cleaned_segment, patterns_data)
    if matched_pattern:
        base_name = processed_segment # Use the processed segment as base name
    else:
        base_name = cleaned_segment

    # Try to find an exact match in common ingredients
    if base_name in common_ingredients_set:
        trust_report_category = "common_only"
        # If it's a common ingredient, check if it's also an FDA common substance
        if base_name in fda_substances_map:
            fda_info = fda_substances_map.get(base_name)
            if fda_info and base_name in load_common_ingredients(): # Re-check against the common set for FDA common
                trust_report_category = "fda_common"
                used_for = fda_info.get("used_for", [])
                other_names = fda_info.get("other_names", [])

    # If not a common ingredient, check if it's an FDA substance (non-common)
    elif base_name in fda_substances_map:
        fda_info = fda_substances_map.get(base_name)
        if fda_info:
            used_for = fda_info.get("used_for", [])
            other_names = fda_info.get("other_names", [])
        trust_report_category = "fda_non_common"

    # Default to unknown if no category is found
    if not trust_report_category:
        trust_report_category = "unknown"


    # Additional checks for categories (e.g., "flavors")
    for category in patterns_data.get("categories", []):
        for keyword in category["keywords"]:
            if keyword.lower() in base_name:
                base_name = category["name"] # Use category name as base_ingredient
                ingredient_type = "category"
                if category["name"].lower() in fda_substances_map: # Check if category itself is an FDA substance
                    fda_info = fda_substances_map.get(category["name"].lower())
                    if fda_info:
                        used_for = fda_info.get("used_for", [])
                        other_names = fda_info.get("other_names", [])
                    if base_name.lower() in common_ingredients_set: # Is it a common FDA regulated substance?
                        trust_report_category = "fda_common"
                    else:
                        trust_report_category = "fda_non_common"
                break
        if ingredient_type == "category":
            break

    # If still unknown and contains "flavor" but not "natural and artificial flavors" (handled above)
    if trust_report_category == "unknown" and "flavor" in base_name:
        base_name = "flavors"
        ingredient_type = "category"
        if "natural" in original_string.lower() and "artificial" not in original_string.lower():
            trust_report_category = "common_only" # Assuming "natural flavors" is common
        elif "artificial" in original_string.lower():
             trust_report_category = "fda_non_common" # Assuming "artificial flavors" is non-common FDA
        else: # Just "flavor" without modifiers
            trust_report_category = "common_only" # Default to common if no strong indication

    # Default to unknown if no classification
    if not base_name and original_string:
        base_name = _clean_segment(original_string)
        trust_report_category = "unknown"


    return {
        "original_string": original_string,
        "base_ingredient": base_name,
        "modifiers": [], # Not extracting modifiers in this version
        "attributes": {
            "ingredient_type": ingredient_type,
            "trust_report_category": trust_report_category,
            "used_for": used_for,
            "other_names": other_names
        },
        "parenthetical_info": {}, # Not extracting parenthetical_info in this version
        "unusual_punctuation_found": [], # Not extracting unusual_punctuation_found in this version
    }

def parse_ingredient_string(ingredient_string, patterns_data, common_ingredients_set, fda_substances_map):
    """
    Parses a full ingredient string into individual ingredient objects.
    """
    if not ingredient_string:
        return []

    segments = [s.strip() for s in ingredient_string.split(',') if s.strip()]
    parsed_ingredients = []

    for segment in segments:
        classification = _classify_ingredient(
            segment, patterns_data, common_ingredients_set, fda_substances_map
        )
        parsed_ingredients.append(classification)

    return parsed_ingredients

if __name__ == '__main__':
    print("--- Testing Ingredient Parser ---")
    print("Loading reference data...")
    patterns_data = load_patterns()
    fda_substances_map = load_fda_substances()
    common_ingredients_set = load_common_ingredients()

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

    print("\n--- Additional Specific Test Cases ---")
    for i, s in enumerate(test_strings):
        print(f"\n--- Test Case {i+1}: '{s}' ---")
        parsed_result = parse_ingredient_string(s, patterns_data, common_ingredients_set, fda_substances_map)
        for item in parsed_result:
            print(f"  - Original: '{item['original_string']}' | Base: '{item['base_ingredient']}' | Category: '{item['attributes']['trust_report_category']}' | Used For: {item['attributes'].get('used_for', [])} | Other Names: {item['attributes'].get('other_names', [])}")