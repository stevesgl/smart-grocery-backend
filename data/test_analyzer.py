import json
import re
import os # Import the os module for path manipulation
from pprint import pprint

# Path to your FDA substances JSON file
ADDITIVES_DATA_FILE = os.path.join(os.path.dirname(__file__), 'all_fda_substances_full.json')
# Path to your common ingredients JSON file
COMMON_INGREDIENTS_DATA_FILE = os.path.join(os.path.dirname(__file__), 'common_ingredients.json')

# --- Global Lookups (will be populated once) ---
ADDITIVES_LOOKUP = {}
# Change COMMON_INGREDIENTS_LOOKUP to a dict for phrase mapping
COMMON_INGREDIENTS_LOOKUP = {} 

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
            names_to_add.add(canonical_name) # Original canonical name
            names_to_add.add(normalized_canonical_name_for_key) # Explicitly add the normalized version as a key
            names_to_add.update(entry.get("Other Names", []))

            # --- Explicitly add common aliases for problematic cases ---
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
                        ADDITIVES_LOOKUP[normalized_alias] = normalized_canonical_name_for_key # Map to the consistent normalized canonical name

        print(f"✅ Successfully loaded {len(additives_raw)} additives and built lookup with {len(ADDITIVES_LOOKUP)} aliases.")
        # DEBUG: Print specific keys to verify
        print("DEBUG: Checking specific ADDITIVES_LOOKUP keys:")
        print(f"'fd&c red no 40' in lookup: {'fd&c red no 40' in ADDITIVES_LOOKUP}")
        print(f"Value for 'fd&c red no 40': {ADDITIVES_LOOKUP.get('fd&c red no 40')}")
        print(f"'fd&c yellow no 5' in lookup: {'fd&c yellow no 5' in ADDITIVES_LOOKUP}")
        print(f"Value for 'fd&c yellow no 5': {ADDITIVES_LOOKUP.get('fd&c yellow no 5')}")
        print(f"'fd&c blue no 1' in lookup: {'fd&c blue no 1' in ADDITIVES_LOOKUP}")
        print(f"Value for 'fd&c blue no 1': {ADDITIVES_LOOKUP.get('fd&c blue no 1')}")
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
            # Store the original casing for display purposes
            COMMON_INGREDIENTS_LOOKUP[normalized_ingredient] = ingredient
        print(f"✅ Successfully loaded {len(common_ingredients_raw)} common ingredients into lookup.")
    except FileNotFoundError:
        print(f"❌ Error: Common ingredients data file not found at '{COMMON_INGREDIENTS_DATA_FILE}'. Common ingredient lookup will not work.")
    except json.JSONDecodeError as e:
        print(f"❌ Error decoding JSON from '{COMMON_INGREDIENTS_DATA_FILE}': {e}")
    except Exception as e:
        print(f"❌ An unexpected error occurred while loading common ingredient data: {e}")

# --- Ingredient Analysis Function (Revised for Data Score and Phrase Matching) ---
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
        return [], [], [], 100.0, "High" # No ingredients, assume 100% data completeness

    # Step 1: Initial cleanup and pre-processing
    cleaned_string = re.sub(r'^(?:ingredients|contains|ingredient list|ingredients list):?\s*', '', ingredients_string, flags=re.IGNORECASE).strip()
    cleaned_string = re.sub(r'\s+and/or\s+', ', ', cleaned_string, flags=re.IGNORECASE)
    # Remove common parenthetical descriptors that are not part of the substance name
    cleaned_string = re.sub(r'\s*\((?:color|flavour|flavor|emulsifier|stabilizer|thickener|preservative|antioxidant|acidifier|sweetener|gelling agent|firming agent|nutrient|vitamin [a-z0-9]+)\)\s*', '', cleaned_string, flags=re.IGNORECASE)
    cleaned_string = re.sub(r'\s*\[vitamin b\d\]\s*', '', cleaned_string, flags=re.IGNORECASE) # Remove [VITAMIN B#]


    # Step 2: Extract content within parentheses and process separately
    # This regex handles nested parentheses to some extent
    parenthetical_matches = re.findall(r'\(([^()]*?(?:\([^()]*?\)[^()]*?)*?)\)', cleaned_string)
    main_components_string = re.sub(r'\([^()]*?(?:\([^()]*?\)[^()]*?)*?\)', '', cleaned_string).strip()

    # Step 3: Split main string into components by commas and semicolons
    components = [comp.strip() for comp in re.split(r',\s*|;\s*', main_components_string) if comp.strip()]
    
    for p_content in parenthetical_matches:
        # Split content inside parentheses by commas or ' and '
        sub_components = [s.strip() for s in re.split(r',\s*| and\s*', p_content) if s.strip()]
        components.extend(sub_components)

    components = [comp for comp in components if comp]

    total_analyzed_items = len(components)
    categorized_items_count = 0

    for original_component in components:
        # Normalize the component for matching
        normalized_component = original_component.lower().strip()
        normalized_component = re.sub(r'\s+', ' ', normalized_component) # Normalize internal whitespace
        normalized_component = normalized_component.replace('no.', 'no ') # Handle 'no.' specifically

        # Aggressively strip common punctuation from both ends (periods, commas, single/double quotes, etc.)
        # This regex now targets non-word characters (excluding spaces, & . - #) at the start/end
        # It should remove trailing periods more effectively.
        # FIX: Changed regex to specifically strip common trailing punctuation like '.', ',' and '''
        normalized_component = normalized_component.rstrip('.,\'"').strip()


        print(f"DEBUG: Original: '{original_component}', Normalized: '{normalized_component}'") # Added debug print

        if not normalized_component:
            continue

        component_categorized = False
        
        # Pass 1: Try to match against FDA Additives (longest match first for phrases)
        words = normalized_component.split()
        matched_additive = None
        for i in range(len(words)):
            for j in range(len(words), i, -1):
                phrase = " ".join(words[i:j])
                if phrase in ADDITIVES_LOOKUP:
                    matched_additive = ADDITIVES_LOOKUP[phrase]
                    break
            if matched_additive:
                break
        
        if matched_additive:
            identified_fda_substances.add(matched_additive)
            component_categorized = True
        else:
            # Pass 2: If not an FDA Additive, try to match against Common Ingredients (longest match first)
            matched_common_ingredient = None
            for i in range(len(words)):
                for j in range(len(words), i, -1):
                    phrase = " ".join(words[i:j])
                    if phrase in COMMON_INGREDIENTS_LOOKUP:
                        matched_common_ingredient = COMMON_INGREDIENTS_LOOKUP[phrase]
                        break
                if matched_common_ingredient:
                    break

            if matched_common_ingredient:
                identified_common_ingredients.add(matched_common_ingredient) # Store the preferred original casing
                categorized_items_count += 1
            else:
                # If still not categorized, it's truly unidentified
                truly_unidentified_ingredients.add(original_component)
        
        if component_categorized: # Only increment if categorized by FDA additive, common ingredients are handled in their block
            categorized_items_count += 1

    # Calculate Data Score
    if total_analyzed_items == 0:
        data_score_percentage = 100.0
    else:
        # The score should reflect all items that were successfully categorized
        data_score_percentage = ((len(identified_fda_substances) + len(identified_common_ingredients)) / total_analyzed_items) * 100.0
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
        report += "* **Obscure ingredients** not yet in our database.\n"
        report += "* **Potential misspellings** from the label.\n\n"
        report += "We'll keep improving. The more you use, the better we get!!\n" # Updated message
        for unident in sorted(truly_unidentified_ingredients):
            report += f"* {unident.title()}\n"
    else:
        report += "* All ingredient components were successfully categorized!\n"
    
    report += "\n---\n"
    report += "*Data Score reflects the percentage of parsed ingredient components that matched known FDA-regulated substances or common food ingredients.*"
    return report


if __name__ == "__main__":
    print("--- Starting Local Data Score Analyzer Test ---")
    
    # Open the output file for writing
    output_file_path = "testresults.txt"
    with open(output_file_path, "w", encoding="utf-8") as f_out:
        # Redirect stdout to the file
        import sys
        original_stdout = sys.stdout
        sys.stdout = f_out

        try:
            # Load the additive and common ingredients data once at the start of the script
            load_data_lookups()

            # --- Test Cases ---
            test_cases = [
                "water, sugar, citric acid, natural flavors, red 40",
                "INGREDIENTS: ENRICHED FLOUR (WHEAT FLOUR, NIACIN, REDUCED IRON, THIAMIN MONONITRATE [VITAMIN B1], RIBOFLAVIN [VITAMIN B2], FOLIC ACID), SUGAR, VEGETABLE OIL (SOYBEAN, PALM AND PALM KERNEL OIL WITH TBHQ FOR FRESHNESS), HIGH FRUCTOSE CORN SYRUP, CONTAINS TWO PERCENT OR LESS OF SALT, CORNSTARCH, BAKING SODA, SOY LECITHIN, ARTIFICIAL FLAVOR, YELLOW 5, BLUE 1.''",
                "Potatoes, Vegetable Oil (Sunflower, Corn, and/or Canola Oil), Salt",
                "Milk, Cream, Sugar, Vanilla Extract",
                "Water, High Fructose Corn Syrup, Carbon Dioxide, Caramel Color, Phosphoric Acid, Natural Flavors, Caffeine",
                "Pure Cane Sugar",
                "Citric Acid, Sodium Bicarbonate",
                "Unrecognized Ingredient XYZ, Water, Sugar",
                "", # Empty string
                "just water",
                "Contains: Water, High-Fructose Corn Syrup, Phosphoric Acid, Caramel Color, Natural Flavors, Caffeine, Sodium Benzoate, Potassium Sorbate, Ascorbic Acid",
                "Ingredients: Enriched Bleached Flour (Wheat Flour, Niacin, Reduced Iron, Thiamin Mononitrate, Riboflavin, Folic Acid), Sugar, Corn Syrup, Leavening (Baking Soda, Calcium Phosphate, Sodium Aluminum Phosphate), Partially Hydrogenated Soybean Oil, Dextrose, Corn Starch, Salt, Artificial Flavor, Yellow 5, Red 40, Blue 1.",
                "MILK, CREAM, SUGAR, CORN SYRUP, WHEY, MONO AND DIGLYCERIDES, CELLULOSE GUM, GUAR GUM, CARRAGEENAN, ARTIFICIAL FLAVOR, ANNATTO (COLOR), VITAMIN A PALMITATE.",
                "FD&C Red No. 40, FD&C Yellow No. 5, FD&C Blue No. 1",
                "Mono- and Diglycerides, Polysorbate 80",
                "Salt, Sugar, Water, Natural Flavor",
                "Vegetable Oil (Soybean, Palm, Palm Kernel Oil)",
                "Enriched Flour (Wheat Flour, Niacin, Reduced Iron)",
                "Water, Dextrose, Citric Acid, Natural and Artificial Flavors, Salt, Potassium Citrate, Sodium Citrate, Modified Food Starch, Glycerol Ester of Rosin, Sucrose Acetate Isobutyrate, Yellow 5, Red 40." # New complex test case
            ]

            for i, ingredients_string in enumerate(test_cases):
                print(f"\n--- Test Case {i+1} ---")
                print(f"Input Ingredients: '{ingredients_string}'")
                
                identified_fda, identified_common, truly_unidentified, data_score, data_completeness_level = analyze_ingredients(ingredients_string)
                
                print("\nAnalysis Results:")
                print(f"  Data Score: {data_score:.1f}% ({data_completeness_level})")
                print(f"  Identified FDA-Regulated Substances:")
                pprint(identified_fda, stream=f_out) # Use stream=f_out for pprint
                print(f"  Identified Common Food Ingredients:")
                pprint(identified_common, stream=f_out) # Use stream=f_out for pprint
                print(f"  Truly Unidentified Ingredients/Phrases:")
                pprint(truly_unidentified, stream=f_out) # Use stream=f_out for pprint

                # Also print the full markdown report for visual inspection
                print("\n--- Generated Data Report Markdown ---")
                print(generate_data_report_markdown(identified_fda, identified_common, truly_unidentified, data_score, data_completeness_level))

            print("\n--- Local Data Score Analyzer Test Complete ---")

        finally:
            # Restore original stdout
            sys.stdout = original_stdout

    print(f"Test results saved to {output_file_path}")
