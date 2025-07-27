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
    s = re.sub(r'\(.*?\)', '', s)
    s = re.sub(r'\[.*?\]', '', s)
    # Replace common punctuation with spaces
    s = re.sub(r'[.,;!?:/\\-_"\'`]+', ' ', s)
    s = re.strip()
    return s

def parse_ingredient_string(ingredient_string, patterns):
    """
    Parses a single ingredient string to extract base ingredient, modifiers,
    parenthetical info, and identify unusual punctuation.
    """
    parsed_info = {
        "original_string": ingredient_string,
        "base_ingredient": normalize_string(ingredient_string),
        "modifiers": [],
        "attributes": {"trust_report_category": "truly_unidentified"}, # Default category, updated later
        "parenthetical_info": {},
        "unusual_punctuation_found": []
    }

    # Extract parenthetical information
    parenthetical_matches = re.findall(r'\((.*?)\)|\[(.*?)\]', ingredient_string)
    if parenthetical_matches:
        for match in parenthetical_matches:
            # Take the non-empty group
            content = match[0] if match[0] else match[1]
            # Further parse parenthetical content if it contains a common modifier
            for key, pattern_list in patterns.get("parenthetical_examples", {}).items():
                for pattern in pattern_list:
                    if re.search(r'\b' + re.escape(pattern) + r'\b', content, re.IGNORECASE):
                        parsed_info["parenthetical_info"][key] = content
                        break
            # If not categorized, just store it under 'other'
            if not parsed_info["parenthetical_info"]:
                parsed_info["parenthetical_info"]["other"] = content
        
        # Remove parenthetical content from the base string for modifier extraction
        parsed_info["base_ingredient"] = re.sub(r'\s*\(.*?\)\s*|\s*\[.*?\]\s*', ' ', parsed_info["base_ingredient"]).strip()
        parsed_info["base_ingredient"] = normalize_string(parsed_info["base_ingredient"])


    # Extract modifiers
    processed_base_ingredient = parsed_info["base_ingredient"]
    found_modifiers = []
    
    # Sort modifiers by length in descending order to match longer phrases first
    sorted_modifiers = sorted(patterns.get("descriptive_modifiers", []), key=len, reverse=True)
    
    for modifier in sorted_modifiers:
        # Create a regex pattern to match the whole word modifier, handling punctuation and word boundaries
        # Use \b for word boundaries, but also allow for non-word characters around it for flexibility
        pattern = r'(?<!\w)' + re.escape(modifier) + r'(?!\w)'
        
        # Check if the modifier is present and not part of a larger word
        if re.search(pattern, processed_base_ingredient, re.IGNORECASE):
            found_modifiers.append(modifier)
            # Remove the modifier from the processed string to get closer to the base ingredient
            processed_base_ingredient = re.sub(pattern, ' ', processed_base_ingredient, flags=re.IGNORECASE)
            processed_base_ingredient = processed_base_ingredient.strip()

    parsed_info["modifiers"] = sorted(list(set(found_modifiers))) # Ensure unique and sorted modifiers

    # Re-normalize the base ingredient after modifier removal
    parsed_info["base_ingredient"] = normalize_string(processed_base_ingredient)

    # Identify unusual punctuation
    unusual_punctuation_patterns = patterns.get("unusual_punctuation", [])
    for punc_pattern in unusual_punctuation_patterns:
        if re.search(re.escape(punc_pattern), ingredient_string):
            parsed_info["unusual_punctuation_found"].append(punc_pattern)

    # If base ingredient becomes empty after parsing, try to use the original string
    if not parsed_info["base_ingredient"] and original_string:
        parsed_info["base_ingredient"] = normalize_string(original_string)
    
    return parsed_info

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
        "XANTHAN GUM (THICKENER)"
    ]

    print("\n--- Parsing and Categorization Test ---")
    parsed_test_ingredients = []
    for ingredient_string in test_ingredients:
        parsed_test_ingredients.append(parse_ingredient_string(ingredient_string, patterns))

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
    print(f"  Common FDA-regulated ({len(parsed_fda_common)}): {[p['base_ingredient'] for p in parsed_fda_common]}")
    print(f"  Non-Common FDA-regulated ({len(parsed_fda_non_common)}): {[p['base_ingredient'] for p in parsed_fda_non_common]}")
    print(f"  Common Food Only ({len(parsed_common_only)}): {[p['base_ingredient'] for p in parsed_common_only]}")
    print(f"  Truly Unidentified ({len(truly_unidentified)}): {[p['base_ingredient'] for p in truly_unidentified]}")
    print(f"  All FDA Additives for Report ({len(all_fda_parsed_for_report)}): {[p['name'] for p in all_fda_parsed_for_report]}")


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