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
        
        # This will store {lowercase_name_or_alias: full_substance_dict}
        fda_substances_map = {} 
        for item in data:
            primary_name = item.get("name")
            if primary_name:
                fda_substances_map[primary_name.lower()] = item
            for alias in item.get("other_names", []):
                fda_substances_map[alias.lower()] = item # Map aliases back to the full object
        print(f"Loaded FDA substances from: {file_path}")
        return fda_substances_map # Return the dictionary, not a set
    except FileNotFoundError:
        print(f"Error: FDA substances file not found at {file_path}. Please ensure it exists.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {file_path}. Please check file format.")
    return {}

def load_common_ingredients(file_path="data/structured_common_ingredients_live.json"):
    """
    Loads common ingredients from a JSON file (list of dictionaries) into a normalized lowercase set.
    It extracts the 'base_ingredient' or 'original_string' from each dictionary.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            common_ingredients_list = json.load(f)
        
        common_ingredients_set = set()
        for item_dict in common_ingredients_list:
            # Prioritize 'base_ingredient', fall back to 'original_string'
            ingredient_name = item_dict.get('base_ingredient') or item_dict.get('original_string')
            if ingredient_name:
                common_ingredients_set.add(ingredient_name.lower())
        
        print(f"Loaded common ingredients from: {file_path}")
        return common_ingredients_set
    except FileNotFoundError:
        print(f"Error: Common ingredients file not found at {file_path}. Please ensure it exists.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {file_path}. Please check file format.")
    return set()

def parse_ingredient_string(ingredient_string, patterns, fda_substances_map, common_ingredients_set):
    """
    Parses a single ingredient string into its components and categorizes it.
    """
    parsed_ingredients = []
    parsed_fda_non_common = []
    parsed_fda_common = []
    parsed_common_only = []
    truly_unidentified = []

    # Clean up common separators and split
    ingredients = re.split(r',|;', ingredient_string)
    ingredients = [ing.strip() for ing in ingredients if ing.strip()]

    for original_string in ingredients:
        clean_name = original_string.lower()
        
        # Initialize attributes for the parsed ingredient
        ingredient_data = {
            "original_string": original_string,
            "base_ingredient": clean_name, # Default, can be refined
            "modifiers": [],
            "attributes": {},
            "parenthetical_info": {},
            "unusual_punctuation_found": [],
            "trust_report_category": "unidentified" # Default category
        }

        # Check against FDA substances (using the map for full object lookup)
        is_fda_substance = False
        fda_substance_obj = None
        for fda_name in fda_substances_map:
            if fda_name in clean_name:
                is_fda_substance = True
                fda_substance_obj = fda_substances_map.get(fda_name)
                break
        
        is_common_ingredient = clean_name in common_ingredients_set

        if is_fda_substance:
            if is_common_ingredient:
                ingredient_data["trust_report_category"] = "fda_common_regulated"
                parsed_fda_common.append(fda_substance_obj.get("name", original_string))
            else:
                ingredient_data["trust_report_category"] = "fda_non_common"
                parsed_fda_non_common.append(fda_substance_obj.get("name", original_string))
        elif is_common_ingredient:
            ingredient_data["trust_report_category"] = "common_food"
            parsed_common_only.append(original_string)
        else:
            truly_unidentified.append(original_string)

        parsed_ingredients.append(ingredient_data)

    return {
        "parsed": parsed_ingredients,
        "parsed_fda_non_common": parsed_fda_non_common,
        "parsed_fda_common": parsed_fda_common,
        "parsed_common_only": parsed_common_only,
        "truly_unidentified": truly_unidentified
    }


# Example Usage (for local testing of this module)
if __name__ == "__main__":
    print("Running ingredient_parser.py local tests...")
    
    # Define paths relative to the script's location
    current_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(current_dir, "data")

    patterns_data = load_patterns(os.path.join(data_dir, "ingredient_naming_patterns.json"))
    fda_substances_map = load_fda_substances(os.path.join(data_dir, "all_fda_substances_full_live.json"))
    common_ingredients_set = load_common_ingredients(os.path.join(data_dir, "structured_common_ingredients_live.json"))

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
        print(f"Original: {s}")
        parsed_output = parse_ingredient_string(s, patterns_data, fda_substances_map, common_ingredients_set)
        
        print("\nParsed Ingredients (full objects):")
        for p_ing in parsed_output['parsed']:
            print(f"- {p_ing.get('original_string')} -> Category: {p_ing.get('trust_report_category')}")

        print("\nCategorized Lists:")
        print(f"  FDA Non-Common: {parsed_output['parsed_fda_non_common']}")
        print(f"  FDA Common: {parsed_output['parsed_fda_common']}")
        print(f"  Common Only: {parsed_output['parsed_common_only']}")
        print(f"  Truly Unidentified: {parsed_output['truly_unidentified']}")