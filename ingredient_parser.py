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
            
            # Also map all 'other_names' to the same substance item
            for alias in item.get("other_names", []):
                fda_substances_map[alias.lower()] = item
                
        print(f"Loaded FDA substances from: {file_path}")
        return fda_substances_map
    except FileNotFoundError:
        print(f"Error: FDA substances file not found at {file_path}. Please ensure it exists.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {file_path}. Please check file format.")
    return {}

def load_common_ingredients(file_path="data/structured_common_ingredients_live.json"):
    """
    Loads common ingredients into a normalized lowercase set for quick lookup.
    This uses the 'original_string' field from the structured JSON.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        common_ingredients = set()
        for item in data:
            # Ensure 'original_string' exists and is a string before converting to lowercase
            original_string = item.get("original_string")
            if isinstance(original_string, str):
                common_ingredients.add(original_string.lower())
        print(f"Loaded common ingredients from: {file_path}")
        return common_ingredients
    except FileNotFoundError:
        print(f"Error: Common ingredients file not found at {file_path}. Please ensure it exists.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {file_path}. Please check file format.")
    except Exception as e:
        print(f"An unexpected error occurred while loading common ingredients: {e}")
    return set()

def normalize_string(s):
    """
    Normalizes an ingredient string by removing non-alphanumeric characters and lowercasing it.
    """
    return re.sub(r'[^a-zA-Z0-9]', '', s.lower().strip())

def parse_ingredient_string(input_string, patterns, common_ingredients_set, fda_substances_set):
    """
    Parses an ingredient string into structured parts with classification.
    """
    raw_ingredients = re.split(r',\s*| and ', input_string)
    results = []

    for raw in raw_ingredients:
        original = raw.strip()
        base = original.lower()

        # Detect and remove parentheticals
        parenthetical_info = {}
        if "(" in base and ")" in base:
            match = re.search(r'\((.*?)\)', base)
            if match:
                parenthetical_info["content"] = match.group(1)
                base = re.sub(r'\(.*?\)', '', base).strip()

        # Detect punctuation issues
        unusual_punctuation = []
        if patterns:
            for punc in patterns.get("unusual_punctuation", []):
                if punc in original:
                    unusual_punctuation.append(punc)

        # Detect modifiers
        modifiers_found = []
        if patterns:
            for mod in patterns.get("descriptive_modifiers", []):
                if mod.lower() in base:
                    modifiers_found.append(mod)
                    base = base.replace(mod.lower(), "").strip()

        base = base.replace("  ", " ")
        base_normalized = base.lower().strip()

# Classification
        ingredient_type = "unknown"
        trust_report_category = "unknown"
        fda_details = {} # Initialize empty dictionary for FDA details

        # Use the fda_substances_map for lookup
        # fda_substances_set is now fda_substances_map
        if base_normalized in fda_substances_map: 
            ingredient_type = "fda_additive"
            trust_report_category = "fda_non_common" # Ensure this matches the category expected by ingredient_parser_service.py
            
            # Retrieve the full FDA substance details
            fda_item_data = fda_substances_map[base_normalized]
            fda_details = {
                "name": fda_item_data.get("name", original), # Use original string as fallback
                "used_for": fda_item_data.get("used_for", []),
                "other_names": fda_item_data.get("other_names", [])
            }
        elif base_normalized in common_ingredients_set:
            ingredient_type = "common_food"
            # Decide if this should be 'common_food' or 'common_fda_regulated' if applicable
            # Based on SGL pre MVP Trust Report.pdf, 'Common & Minimally Processed Ingredients' and 'Common FDA-Regulated Substances' are distinct categories.
            # Assuming for now 'common_food' maps to 'Common & Minimally Processed Ingredients'
            # and other file (e.g., structured_common_ingredients_live.json) handles 'common_fda_regulated'.
            # For this fix, we'll maintain the current logic of 'Common Ingredient' for common_ingredients_set.
            trust_report_category = "common_food" 
            
            # If common ingredients also have specific details, they would be added here.
            # For now, we only focus on enriching fda_non_common.


        # Construct the result dictionary
        result = {
            "original_string": original,
            "base_ingredient": base_normalized,
            "modifiers": modifiers_found,
            "parenthetical_info": parenthetical_info,
            "unusual_punctuation_found": unusual_punctuation,
            "attributes": {
                "ingredient_type": ingredient_type,
                "trust_report_category": trust_report_category
            }
        }
        
        # Add FDA details if the ingredient is an FDA additive
        if ingredient_type == "fda_additive":
            # Merge fda_details into the result dictionary. 
            # These keys (name, used_for, other_names) are directly expected by ingredient_parser_service.py
            result.update(fda_details)
            
        results.append(result)

    return results

# Optional test run block
if __name__ == "__main__":
    print("Loading ingredient data (patterns, FDA substances, common ingredients)...")
    patterns_data = load_patterns()
    fda_substances_set = load_fda_substances()
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
        print(f"\n--- Test Case {i+1} ---")
        print(f"Input: '{s}'")
        parsed = parse_ingredient_string(s, patterns_data, common_ingredients_set, fda_substances_set)
        for j, result in enumerate(parsed):
            print(f"  Parsed Ingredient {j+1}:")
            print(json.dumps(result, indent=4, ensure_ascii=False))
