import json
import re
import os
import pandas as pd

def normalize_string(s):
    """
    Normalizes a string by converting to lowercase, removing extra spaces,
    and handling special characters or punctuation for consistent processing.
    """
    if not isinstance(s, str):
        return ""
    s = s.lower()
    # Remove anything that's not a letter, number, space, or common punctuation used in ingredients
    # This regex needs to be carefully chosen. For ingredients, we typically want to keep
    # commas, semicolons, hyphens, and perhaps parentheses.
    # Let's refine it to be more suitable for ingredient lists.
    # Keep letters, numbers, spaces, commas, semicolons, hyphens, periods, parentheses, slashes.
    s = re.sub(r'[^a-z0-9\s,;:/&()\-.\[\]]+', '', s)
    s = re.sub(r'\s+', ' ', s).strip() # Replace multiple spaces with single, and strip
    return s

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

        # This will store {lowercase_name_or_alias: full_substance_dict}
        fda_substances_map = {}
        for item in data:
            primary_name = item.get("name")
            if primary_name:
                fda_substances_map[primary_name.lower()] = item
            for alias in item.get("other_names", []):
                fda_substances_map[alias.lower()] = item # Map aliases to the same full object
        print(f"Loaded FDA substances from: {file_path}")
        return fda_substances_map
    except FileNotFoundError:
        print(f"Error: FDA substances file not found at {file_path}. Please ensure it exists.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {file_path}. Please check file format.")
    return {}

def load_common_ingredients(file_path="data/structured_common_ingredients_live.json"):
    """
    Loads common ingredients into a set for quick lookup.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Store as a set of normalized base ingredients for quick lookup
        common_ingredients = {normalize_string(item['base_ingredient']) for item in data}
        print(f"Loaded common ingredients from: {file_path}")
        return common_ingredients
    except FileNotFoundError:
        print(f"Error: Common ingredients file not found at {file_path}. Please ensure it exists.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {file_path}. Please check file format.")
    return set()

def parse_ingredient_string(ingredient_string, ingredient_patterns, fda_substances_map, common_ingredients_set):
    """
    Parses a raw ingredient string into structured components, identifying FDA additives,
    common ingredients, and truly unidentified items.
    """
    ingredients_raw_list = [item.strip() for item in ingredient_string.split(',') if item.strip()]

    parsed_ingredients = []
    parsed_fda_non_common = [] # FDA substances that are not considered "common" food items
    parsed_fda_common = []      # FDA substances that are also very common food items (e.g., citric acid)
    parsed_common_only = []     # Common ingredients that are not FDA substances
    truly_unidentified = []

    for raw_ing in ingredients_raw_list:
        original_ing = raw_ing # Keep original for output
        normalized_ing = normalize_string(raw_ing) # Normalize for internal matching

        base_ingredient = normalized_ing
        modifiers = []
        parenthetical_info = {}
        unusual_punctuation_found = []

        # 1. Handle parenthetical information
        parenthetical_match = re.search(r'\((.*?)\)', base_ingredient)
        if parenthetical_match:
            parenthetical_content = parenthetical_match.group(1)
            # You can further process parenthetical_content if needed
            # For now, just remove it from base_ingredient for primary classification
            base_ingredient = base_ingredient.replace(parenthetical_match.group(0), '').strip()
            parenthetical_info = {"content": parenthetical_content} # Store as dict for future expansion

        # 2. Check for "contains X and Y" patterns or similar complex structures
        # This is a simplification. A robust parser would handle "contains", "made from", etc.
        # For MVP, we split by common delimiters and treat each as a potential ingredient.

        # 3. Classify the ingredient
        # Check FDA substances first, as they are a priority for the Trust Report
        is_fda_substance = False
        fda_substance_info = fda_substances_map.get(base_ingredient)

        # Also check if any part of the normalized ingredient string matches an FDA substance
        # This is crucial for handling phrases like "modified corn starch" where "corn starch" might be FDA
        # Or if "natural flavors" is in the FDA list.
        found_fda_match = None
        for fda_name, fda_obj in fda_substances_map.items():
            if fda_name in normalized_ing:
                found_fda_match = fda_name
                fda_substance_info = fda_obj # Use the full object
                is_fda_substance = True
                break # Take the first match for now, could be improved with longest match etc.

        if is_fda_substance and fda_substance_info:
            # Check if this FDA substance is also considered a common ingredient
            if found_fda_match in common_ingredients_set: # Use the matched FDA name for common check
                parsed_fda_common.append(fda_substance_info['name']) # Store original name from map
                trust_report_category = "common_fda_regulated"
            else:
                parsed_fda_non_common.append(fda_substance_info['name']) # Store original name from map
                trust_report_category = "fda_non_common"
            # Use the official name from the FDA substance map
            base_ingredient = fda_substance_info['name']
        elif base_ingredient in common_ingredients_set:
            parsed_common_only.append(original_ing) # Store original string
            trust_report_category = "common_food"
        else:
            truly_unidentified.append(original_ing) # Store original string
            trust_report_category = "unidentified"

        # Add to the general parsed list with attributes for report generation if needed
        parsed_ingredients.append({
            "original_string": original_ing,
            "base_ingredient": base_ingredient,
            "modifiers": modifiers, # This needs more sophisticated parsing to populate
            "attributes": {}, # Placeholder for future attributes (e.g., source_type)
            "parenthetical_info": parenthetical_info,
            "unusual_punctuation_found": unusual_punctuation_found, # Placeholder
            "trust_report_category": trust_report_category
        })

    return {
        "parsed": parsed_ingredients,
        "parsed_fda_non_common": list(set(parsed_fda_non_common)), # Remove duplicates
        "parsed_fda_common": list(set(parsed_fda_common)),       # Remove duplicates
        "parsed_common_only": list(set(parsed_common_only)),     # Remove duplicates
        "truly_unidentified": list(set(truly_unidentified))      # Remove duplicates
    }

if __name__ == '__main__':
    print("Running ingredient_parser.py directly for testing...")
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    print(f"Loading data from: {DATA_DIR}")
    ingredient_patterns = load_patterns(os.path.join(DATA_DIR, "ingredient_naming_patterns.json"))
    fda_substances_map = load_fda_substances(os.path.join(DATA_DIR, "all_fda_substances_full_live.json"))
    common_ingredients_set = load_common_ingredients(os.path.join(DATA_DIR, "structured_common_ingredients_live.json"))

    # Test cases
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
        print(f"\n--- Test Case {i+1} ---")
        print(f"Input: {s}")
        parsed = parse_ingredient_string(s, ingredient_patterns, fda_substances_map, common_ingredients_set)
        print("Parsed Result:")
        for key, value in parsed.items():
            if key == "parsed":
                print(f"  {key}:")
                for item in value:
                    print(f"    - Original: '{item['original_string']}', Base: '{item['base_ingredient']}', Category: '{item['trust_report_category']}'")
            else:
                print(f"  {key}: {value}")

    # Example of an FDA substance that is also common
    print("\n--- Test Case: Citric Acid ---")
    test_string_citric = "water, sugar, citric acid"
    print(f"Input: {test_string_citric}")
    parsed_citric = parse_ingredient_string(test_string_citric, ingredient_patterns, fda_substances_map, common_ingredients_set)
    print("Parsed Result:")
    for key, value in parsed_citric.items():
        if key == "parsed":
            print(f"  {key}:")
            for item in value:
                print(f"    - Original: '{item['original_string']}', Base: '{item['base_ingredient']}', Category: '{item['trust_report_category']}'")
        else:
            print(f"  {key}: {value}")