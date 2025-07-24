import json
from collections import Counter
import re
import os

def analyze_technical_effects(json_file_path):
    """
    Analyzes the 'Used for (Technical Effect)' field in a JSON file,
    counts the occurrences of each unique effect, and prints them
    from most frequent to least frequent.

    Args:
        json_file_path (str): The path to the 'all_fda_substances_full.json' file.
    """
    # Check if the file exists before attempting to open it
    if not os.path.exists(json_file_path):
        print(f"Error: File not found at '{json_file_path}'")
        print("Please ensure 'all_fda_substances_full.json' is in the same directory as this script.")
        return

    # Initialize a Counter to store the frequency of each technical effect
    technical_effects_counter = Counter()

    try:
        # Open and load the JSON data from the specified file
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Iterate through each entry (substance) in the JSON data
        for entry in data:
            # Get the raw 'Used for (Technical Effect)' string.
            # Use .get() with a default empty string to handle missing keys gracefully.
            raw_effects_string = entry.get("Used for (Technical Effect)", "").strip()

            # If the string is empty after stripping whitespace, skip this entry
            if not raw_effects_string:
                continue

            # Split the string by common delimiters: comma (',') and '<br />' (case-insensitive)
            # re.split handles multiple delimiters and automatically removes empty strings
            # that might result from consecutive delimiters or leading/trailing delimiters.
            individual_effects = re.split(r',\s*|<br\s*/>', raw_effects_string, flags=re.IGNORECASE)

            # Process each individual effect found
            for effect in individual_effects:
                # Clean up leading/trailing whitespace from each individual effect
                cleaned_effect = effect.strip()
                # If the effect is not empty after cleaning, add it to the counter
                if cleaned_effect:
                    technical_effects_counter[cleaned_effect] += 1

        # Get the sorted list of (effect, count) pairs, from most common to least common
        sorted_effects = technical_effects_counter.most_common()

        # Print the header for the two columns
        print(f"{'Used for (Technical Effect)':<50} {'Count':<10}")
        # Print a separator line for readability
        print(f"{'-'*50:<50} {'-'*10:<10}")

        # Print each technical effect and its count
        for effect, count in sorted_effects:
            print(f"{effect:<50} {count:<10}")

    except json.JSONDecodeError as e:
        # Handle errors that occur if the JSON file is malformed
        print(f"Error decoding JSON from '{json_file_path}': {e}")
    except Exception as e:
        # Catch any other unexpected errors during file processing
        print(f"An unexpected error occurred: {e}")

# This block ensures the script runs when executed directly
if __name__ == "__main__":
    # Determine the directory where the script is located
    current_directory = os.path.dirname(os.path.abspath(__file__))
    # Construct the full path to the JSON file, assuming it's in the same directory
    json_file = os.path.join(current_directory, "all_fda_substances_full.json")
    
    # Call the analysis function
    analyze_technical_effects(json_file)
