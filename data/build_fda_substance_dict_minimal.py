# FILE: build_fda_substance_dict_minimal.py
import json
import os
from tqdm import tqdm

# Set fixed paths (no CLI args)
INPUT_PATH = r"C:\Users\steve\OneDrive\Documents\MyGroceryScanner\backend\data\all_fda_substances_full_live.json"
OUTPUT_PATH = r"C:\Users\steve\OneDrive\Documents\MyGroceryScanner\backend\data\fda_substance_dict.json"

def normalize(name):
    return name.strip().upper()

def build_minimal_fda_substance_dict():
    print(f"🔍 Loading input file from:\n{INPUT_PATH}")
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        full_data = json.load(f)

    print(f"⚙️  Building dictionary from {len(full_data):,} entries...\n")
    minimal_dict = {}

    for entry in tqdm(full_data, desc="🔄 Processing substances", unit="entry"):
        main_name = normalize(entry.get("Substance", ""))
        other_names = entry.get("Other Names", [])
        aliases = list(set([normalize(name) for name in [main_name] + other_names if name.strip()]))

        if main_name:
            minimal_dict[main_name] = {
                "aliases": aliases
            }

    print(f"\n💾 Writing output to:\n{OUTPUT_PATH}")
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f_out:
        json.dump(minimal_dict, f_out, indent=2)

    print("✅ Done! Minimal FDA substance dictionary saved successfully.")

if __name__ == "__main__":
    build_minimal_fda_substance_dict()
