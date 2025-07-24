import json
import os
import sys
import requests
from pprint import pprint

# ========================== CONFIGURATION ==========================
# Your USDA FoodData Central API Key
USDA_API_KEY = 'INRDD92zQbcmfWGmAKsRXdR1dovDfeXnawBwBz8l' 

# The path to your locally created GTIN-to-FDC ID map JSON file
GTIN_FDCID_MAP_FILE = 'gtin_map.json'

# Base URL for fetching food details by FDC ID from USDA API
USDA_GET_FOOD_BY_FDCID_URL = 'https://api.nal.usda.gov/fdc/v1/food/'
# ===================================================================

# Load the GTIN-to-FDC ID map once when the script starts
gtin_to_fdcid_map = {}
if os.path.exists(GTIN_FDCID_MAP_FILE):
    try:
        with open(GTIN_FDCID_MAP_FILE, 'r', encoding='utf-8') as f:
            gtin_to_fdcid_map = json.load(f)
        print(f"✅ Loaded {len(gtin_to_fdcid_map)} GTIN-to-FDC ID mappings from {GTIN_FDCID_MAP_FILE}")
    except Exception as e:
        print(f"❌ Error loading '{GTIN_FDCID_MAP_FILE}': {e}. Local GTIN lookup will not function.")
else:
    print(f"❌ Error: '{GTIN_FDCID_MAP_FILE}' not found. Please ensure it has been created.")
    sys.exit(1) # Exit if the map file is not found

def lookup_and_fetch_by_fdcid(gtin):
    """
    Looks up FDC ID for a given GTIN in the local map,
    then fetches product details from USDA API using the FDC ID.
    """
    if not USDA_API_KEY:
        print("USDA API Key not set. Cannot fetch from USDA API.")
        return None

    # Step 1: Look up FDC ID in the local map
    fdc_id = gtin_to_fdcid_map.get(gtin)

    if not fdc_id:
        print(f"❌ GTIN '{gtin}' not found in local map ({GTIN_FDCID_MAP_FILE}).")
        return None

    print(f"✅ GTIN '{gtin}' mapped to FDC ID: '{fdc_id}' locally.")

    # Step 2: Fetch product details from USDA API using the FDC ID
    api_url = f"{USDA_GET_FOOD_BY_FDCID_URL}{fdc_id}?api_key={USDA_API_KEY}"
    print(f"  Querying USDA API for FDC ID: {fdc_id}...")

    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        data = response.json()

        print(f"  ✅ Successfully fetched data for FDC ID '{fdc_id}'.")
        return data
    except requests.exceptions.RequestException as e:
        print(f"  ❌ Error fetching from USDA API for FDC ID '{fdc_id}': {e}")
    except json.JSONDecodeError as e:
        print(f"  ❌ JSON Decode Error from USDA API for FDC ID '{fdc_id}'. Response: {response.text.strip()}")
    except Exception as e:
        print(f"  ❌ An unexpected error occurred: {e}")
        
    return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_gtin_lookup.py <GTIN>")
        print("Example: python test_gtin_lookup.py 00027000612323")
        sys.exit(1)

    test_gtin = sys.argv[1]
    print(f"--- Testing lookup for GTIN: {test_gtin} ---")

    product_data = lookup_and_fetch_by_fdcid(test_gtin)

    if product_data:
        print("\n--- Fetched Product Data ---")
        pprint(product_data)
        # You can add specific checks here, e.g.,
        # print(f"\nDescription: {product_data.get('description')}")
        # print(f"Data Type: {product_data.get('dataType')}")
        # print(f"GTIN from API: {product_data.get('gtinUpc')}") # Confirm GTIN is returned
    else:
        print(f"\n❌ Failed to retrieve data for GTIN: {test_gtin}")

