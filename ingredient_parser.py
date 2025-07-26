import json
import re
import os
import pandas as pd

def load_patterns(file_path="ingredient_naming_patterns.json"):
    """
    Loads the descriptive modifiers, parenthetical content examples, and unusual punctuation
    from the specified JSON file.

    Args:
        file_path (str): The path to the JSON file containing the patterns.

    Returns:
        dict: A dictionary containing the loaded patterns.
              Returns an empty dictionary if the file is not found or cannot be parsed.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            patterns = json.load(f)
        return patterns
    except FileNotFoundError:
        print(f"Error: Pattern file not found at {file_path}. Please ensure it exists.")
        return {}
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {file_path}. Please check file format.")
        return {}

def load_common_ingredients(file_path="common_ingredients_USDA.json"):
    """
    Loads common ingredients from the specified JSON file.

    Args:
        file_path (str): The path to the JSON file containing common ingredients.

    Returns:
        set: A set of normalized common ingredient names.
             Returns an empty set if the file is not found or cannot be parsed.
    """
    common_ingredients = set()
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            ingredients = json.load(f)
            for item in ingredients:
                common_ingredients.add(item.lower().strip())
        return common_ingredients
    except FileNotFoundError:
        print(f"Error: Common ingredients file not found at {file_path}. Please ensure it exists.")
        return set()
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {file_path}. Please check file format.")
        return set()

def load_fda_substances(file_path="all_fda_substances_full_live.json"):
    """
    Loads FDA substances from the specified JSON file.

    Args:
        file_path (str): The path to the JSON file containing FDA substances.

    Returns:
        set: A set of normalized FDA substance names.
             Returns an empty set if the file is not found or cannot be parsed.
    """
    fda_substances = set()
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            substances = json.load(f)
            for sub in substances:
                # Add the main substance name
                if 'Substance' in sub and sub['Substance']:
                    fda_substances.add(sub['Substance'].lower().strip())
                # Add other names/synonyms
                if 'Other Names' in sub and isinstance(sub['Other Names'], list):
                    for other_name in sub['Other Names']:
                        if other_name:
                            fda_substances.add(other_name.lower().strip())
                # Add Substance Name (Heading)
                if 'Substance Name (Heading)' in sub and sub['Substance Name (Heading)']:
                    fda_substances.add(sub['Substance Name (Heading)'].lower().strip())
        return fda_substances
    except FileNotFoundError:
        print(f"Error: FDA substances file not found at {file_path}. Please ensure it exists.")
        return set()
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {file_path}. Please check file format.")
        return set()

def _parse_single_ingredient_segment(ingredient_string, patterns, common_ingredients_set, fda_substances_set):
    """
    Parses a single ingredient segment to extract base ingredient, modifiers,
    and structured attributes, including parenthetical information.
    This is the core logic for parsing an *individual* ingredient.

    Args:
        ingredient_string (str): The raw ingredient description string for a single ingredient.
        patterns (dict): A dictionary containing 'descriptive_modifiers',
                         'parenthetical_content_examples', and 'unusual_punctuation_f
                         ound' patterns.
        common_ingredients_set (set): A set of known common ingredient names for base identification.
        fda_substances_set (set): A set of known FDA regulated substance names.

    Returns:
        dict: A structured dictionary of the parsed ingredient.
    """
    original_string = ingredient_string.strip()
    processed_string = original_string.lower()

    base_ingredient = "unknown"
    modifiers = []
    attributes = {}
    parenthetical_info = {}
    unusual_punctuation_found = []

    # 1. Extract and remove parenthetical content
    parenthetical_matches = re.findall(r'\(([^)]*)\)', processed_string)
    if parenthetical_matches:
        parenthetical_info['other_details'] = [p.strip() for p in parenthetical_matches if p.strip()]
        processed_string = re.sub(r'\([^)]*\)', '', processed_string).strip()

    # 2. Handle unusual punctuation (e.g., semicolons, multiple commas acting as separators)
    unusual_punctuation = patterns.get('unusual_punctuation_found', [])
    for punc in unusual_punctuation:
        if punc in processed_string:
            unusual_punctuation_found.append(punc)

    # Remove known separators that might interfere with modifier extraction but aren't parenthetical
    processed_string = re.sub(r'[,;]', ' ', processed_string).strip()
    processed_string = re.sub(r'\s+', ' ', processed_string).strip() # Normalize spaces

    # 3. Identify modifiers and base ingredient
    # Sort modifiers by length descending to match longer phrases first (e.g., "low fat" before "fat")
    descriptive_modifiers = sorted(patterns.get('descriptive_modifiers', []), key=len, reverse=True)
    found_modifiers = []

    temp_string = processed_string
    for modifier in descriptive_modifiers:
        # Use regex to match whole words or phrases to avoid partial matches
        pattern = r'\b' + re.escape(modifier.lower()) + r'\b'
        if re.search(pattern, temp_string):
            found_modifiers.append(modifier)
            temp_string = re.sub(pattern, '', temp_string).strip()
            temp_string = re.sub(r'\s+', ' ', temp_string).strip() # Normalize spaces after removal

    modifiers.extend(sorted(found_modifiers)) # Keep modifiers sorted for consistency

    potential_base = temp_string.strip()

    # Try to find the best base ingredient match from common ingredients set
    if potential_base:
        # Check for exact match first
        if potential_base in common_ingredients_set:
            base_ingredient = potential_base
        else:
            # If no exact match, try to find the longest common ingredient within the potential base
            found_common = ""
            # Sort common ingredients by length descending for longest match
            for common_ing in sorted(list(common_ingredients_set), key=len, reverse=True):
                if common_ing in potential_base:
                    if len(common_ing) > len(found_common): # Find the longest match
                        found_common = common_ing
            if found_common:
                base_ingredient = found_common
            else:
                base_ingredient = potential_base # If nothing common, take the remaining as base

    if base_ingredient == "unknown" and potential_base:
        base_ingredient = potential_base

    # 4. Assign attributes based on modifiers and other patterns
    if 'raw' in modifiers:
        attributes['state'] = 'raw'
    if 'cooked' in modifiers:
        attributes['state'] = 'cooked'
    if 'dried' in modifiers:
        attributes['state'] = 'dried'
    if 'frozen' in modifiers:
        attributes['state'] = 'frozen'
    if 'fresh' in modifiers:
        attributes['state'] = 'fresh'
    if 'canned' in modifiers:
        attributes['packaging'] = 'canned'
    if 'low fat' in modifiers:
        attributes['fat_content'] = 'low fat'
    if 'non-fat' in modifiers:
        attributes['fat_content'] = 'non-fat'
    if 'fat free' in modifiers:
        attributes['fat_content'] = 'fat free'
    if 'fortified' in modifiers or 'fortified with vitamin d' in modifiers:
        attributes['nutritional_enhancement'] = True
    if 'enriched' in modifiers:
        attributes['enrichment'] = True
    if 'artificial' in modifiers and 'natural' not in modifiers:
        attributes['source_type'] = 'artificial'
    elif 'natural' in modifiers and 'artificial' not in modifiers:
        attributes['source_type'] = 'natural'
    elif 'natural and artificial' in original_string.lower(): # Check original for combined term
        attributes['source_type'] = 'natural and artificial'

    # Determine ingredient type and trust report category
    normalized_base = base_ingredient.lower().strip()
    if normalized_base in fda_substances_set:
        attributes['ingredient_type'] = 'specific' # Often FDA regulated are specific substances
        attributes['trust_report_category'] = 'common_fda_regulated'
    elif normalized_base in common_ingredients_set:
        attributes['ingredient_type'] = 'specific'
        attributes['trust_report_category'] = 'common_food' # Default for common food
    # Check if the base ingredient itself is a known category (e.g., "flavors", "spices")
    elif normalized_base in ['flavors', 'spices', 'colors', 'leavening']:
        attributes['ingredient_type'] = 'category'
        attributes['trust_report_category'] = 'common_fda_regulated'
    # Check if any modifier indicates a category type
    elif any(m in ['flavors', 'spices', 'colors', 'leavening'] for m in [mod.lower() for mod in modifiers]):
        attributes['ingredient_type'] = 'category'
        attributes['trust_report_category'] = 'common_fda_regulated'
    else:
        # Fallback for anything not explicitly identified
        attributes['ingredient_type'] = 'unknown'
        attributes['trust_report_category'] = 'unknown'

    # Special handling for "natural and artificial flavors" as it's a common phrase
    if original_string.lower() == "natural and artificial flavors":
        base_ingredient = "flavors"
        modifiers = ["natural", "artificial"]
        attributes['source_type'] = 'natural and artificial'
        attributes['ingredient_type'] = 'category'
        attributes['trust_report_category'] = 'common_fda_regulated'

    return {
        "original_string": original_string,
        "base_ingredient": base_ingredient,
        "modifiers": modifiers,
        "attributes": attributes,
        "parenthetical_info": parenthetical_info,
        "unusual_punctuation_found": unusual_punctuation_found
    }


def parse_ingredient_string(full_ingredient_list_string, patterns, common_ingredients_set, fda_substances_set):
    """
    Parses a full ingredient list string (which may contain multiple ingredients)
    to extract structured information for each individual ingredient.

    Args:
        full_ingredient_list_string (str): The raw ingredient list string (e.g., "WATER, SUGAR, SALT").
        patterns (dict): Loaded patterns.
        common_ingredients_set (set): Set of common ingredients.
        fda_substances_set (set): Set of FDA substances.

    Returns:
        list: A list of structured dictionaries, each representing a parsed ingredient.
    """
    if not full_ingredient_list_string or not isinstance(full_ingredient_list_string, str):
        return []

    processed_string = full_ingredient_list_string.strip()

    # Temporarily replace parenthetical content with placeholders to avoid splitting inside them
    parenthetical_placeholders = {}
    placeholder_idx = 0

    def replace_parentheticals(match):
        nonlocal placeholder_idx
        placeholder = f"__PAREN_{placeholder_idx}__"
        parenthetical_placeholders[placeholder] = match.group(0)
        placeholder_idx += 1
        return placeholder

    # Use re.sub with a function for replacement
    string_with_placeholders = re.sub(r'\([^)]*\)', replace_parentheticals, processed_string)

    # Split by common delimiters. Prioritize comma, then 'and', then 'or'.
    # This regex attempts to split by commas or " and " or " or " outside of the placeholders.
    # It's a heuristic and might need more advanced NLP for perfect segmentation in complex cases.
    segments = re.split(r',\s*|\s+and\s+|\s+or\s+', string_with_placeholders, flags=re.IGNORECASE)

    parsed_ingredients = []
    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        # Restore parentheticals from placeholders
        for placeholder, original_paren in parenthetical_placeholders.items():
            segment = segment.replace(placeholder, original_paren)

        # Now, parse each individual segment using the helper function
        parsed_ingredient = _parse_single_ingredient_segment(segment, patterns, common_ingredients_set, fda_substances_set)
        parsed_ingredients.append(parsed_ingredient)

    return parsed_ingredients


if __name__ == "__main__":
    # Define file paths
    PATTERNS_FILE_PATH = "ingredient_naming_patterns.json"
    COMMON_INGREDIENTS_FILE_PATH = "common_ingredients_USDA.json"
    FDA_SUBSTANCES_FILE_PATH = "all_fda_substances_full_live.json"
    INPUT_CSV_FILE_PATH = "verified_products.csv"
    OUTPUT_FILE_PATH = "structured_verified_ingredients_reparsed_v2.json" # Updated output file name

    print("Loading patterns, common ingredients (USDA), and FDA substances...")
    patterns_data = load_patterns(PATTERNS_FILE_PATH)
    common_ingredients_set = load_common_ingredients(COMMON_INGREDIENTS_FILE_PATH)
    fda_substances_set = load_fda_substances(FDA_SUBSTANCES_FILE_PATH)

    if not patterns_data or not common_ingredients_set or not fda_substances_set:
        print("Failed to load necessary data. Exiting.")
    else:
        print("Data loaded successfully. Starting parsing of verified_products.csv.")

        # Load the list of ingredients to be parsed from the CSV
        all_ingredients_to_parse = []
        try:
            df = pd.read_csv(INPUT_CSV_FILE_PATH)
            if 'ingredients' in df.columns:
                # Filter out NaN values and convert to list of strings
                all_ingredients_to_parse = df['ingredients'].dropna().astype(str).tolist()
                print(f"Found {len(all_ingredients_to_parse)} ingredient strings in '{INPUT_CSV_FILE_PATH}'.")
            else:
                print(f"Error: 'ingredients' column not found in '{INPUT_CSV_FILE_PATH}'.")
        except FileNotFoundError:
            print(f"Error: Input CSV file not found at {INPUT_CSV_FILE_PATH}.")
        except Exception as e:
            print(f"Error reading CSV file '{INPUT_CSV_FILE_PATH}': {e}")

        structured_ingredients_flat_list = [] # This will store all parsed ingredients
        if all_ingredients_to_parse:
            print(f"Processing {len(all_ingredients_to_parse)} ingredient lists...")
            for i, ingredient_list_str in enumerate(all_ingredients_to_parse):
                if i % 1000 == 0:
                    print(f"  Processed {i}/{len(all_ingredients_to_parse)} ingredient lists...")
                try:
                    # parse_ingredient_string now returns a list of parsed ingredient dicts
                    parsed_list_for_entry = parse_ingredient_string(ingredient_list_str, patterns_data, common_ingredients_set, fda_substances_set)
                    structured_ingredients_flat_list.extend(parsed_list_for_entry)
                except Exception as e:
                    print(f"Error parsing ingredient list '{ingredient_list_str}': {e}")
                    # Append an error entry for the original string if parsing fails at the list level
                    structured_ingredients_flat_list.append({
                        "original_string": ingredient_list_str,
                        "parsing_error": str(e),
                        "base_ingredient": "ERROR_LIST_PARSE",
                        "modifiers": [],
                        "attributes": {},
                        "parenthetical_info": {},
                        "unusual_punctuation_found": []
                    })

            # Save the structured data to a new JSON file
            try:
                with open(OUTPUT_FILE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(structured_ingredients_flat_list, f, indent=4, ensure_ascii=False)
                print(f"\nSuccessfully processed and saved structured ingredients to {OUTPUT_FILE_PATH}")
            except Exception as e:
                print(f"Error saving structured ingredients to {OUTPUT_FILE_PATH}: {e}")
        else:
            print("No ingredient lists to process.")

        print("\n--- Example Test Cases (from common_ingredients_USDA.json and specific examples) ---")
        # Print a few examples from the newly generated file
        if len(structured_ingredients_flat_list) > 0:
            print(f"\nFirst 5 parsed ingredients from '{OUTPUT_FILE_PATH}':")
            for i in range(min(5, len(structured_ingredients_flat_list))):
                print(f"\n--- Example {i+1} ---")
                print(json.dumps(structured_ingredients_flat_list[i], indent=4, ensure_ascii=False))
        else:
            print("No ingredients were processed from the CSV.")

        # You can add specific test strings here to verify the parser's behavior
        test_strings = [
            "chicken breast, boneless, skinless, raw",
            "enriched bleached wheat flour (niacin, reduced iron, thiamin mononitrate, riboflavin, folic acid)",
            "water (filtered) and sugar",
            "natural and artificial flavors",
            "sugar, brown",
            "sodium selenite",
            "calcium carbonate (fortified)",
            "milk, whole, pasteurized, vitamin d added",
            "WATER, PINTO BEANS, ONION, TOMATO, SALT, JALAPENO PEPPER, SOYBEAN OIL, SPICES", # Multi-ingredient test
            "ENRICHED WHEAT FLOUR (WHEAT FLOUR, NIACIN, REDUCED IRON, THIAMIN MONONITRATE, RIBOFLAVIN, FOLIC ACID), WATER, HIGH FRUCTOSE CORN SYRUP, YEAST, SALT, VEGETABLE OIL (SOYBEAN OIL, PALM OIL, CANOLA OIL), MONOGLYCERIDES, CALCIUM PROPIONATE (PRESERVATIVE), CALCIUM SULFATE, ENZYMES, AMMONIUM SULFATE, ASCORBIC ACID (DOUGH CONDITIONER), AZODICARBONAMIDE, L-CYSTEINE HYDROCHLORIDE."
        ]
        print("\n--- Additional Specific Test Cases ---")
        for i, s in enumerate(test_strings):
            print(f"\n--- Test Case {i+1} ---")
            print(f"Input: '{s}'")
            # Call the new parse_ingredient_string which returns a list
            results = parse_ingredient_string(s, patterns_data, common_ingredients_set, fda_substances_set)
            for j, result in enumerate(results):
                print(f"  Parsed Ingredient {j+1}:")
                print(json.dumps(result, indent=4, ensure_ascii=False))
