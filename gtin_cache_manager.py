import sys
import requests
from airtable import Airtable
from datetime import datetime
from pprint import pprint
import json # Import json for potential JSONDecodeError

# ========================== CONFIGURATION ==========================
# IMPORTANT: Replace these with your actual Airtable and USDA API keys/IDs
AIRTABLE_BASE_ID = 'app9Nq6hU74orpuLx'  # Your Airtable Base ID
AIRTABLE_TABLE_NAME = 'GTIN Cache'      # Your Airtable Table Name
AIRTABLE_API_KEY = 'patCALA6X3TClne9m.52679c670ca614bedd50203a0dbf61706cddade7299919af70780ab238f95e5b' # Your Airtable Personal Access Token (PAT)
USDA_API_KEY = '0w1T7VpMmQBm2x5i6zzx3lkDSvc0OmdVPN8EbaUg' # Your USDA FoodData Central API Key

# Airtable max rows for the free tier (for eviction logic)
AIRTABLE_MAX_ROWS = 1000
# ===================================================================

# Initialize Airtable client
airtable = Airtable(AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME, AIRTABLE_API_KEY)

# USDA API search URL
USDA_SEARCH_URL = 'https://api.nal.usda.gov/fdc/v1/foods/search'

# ===================================================================
# Core Functions
# ===================================================================

def check_airtable_cache(gtin):
    """
    Checks if a GTIN exists in the Airtable cache.
    If found, it updates the lookup_count and last_access fields for that record.
    """
    print(f"  Checking Airtable cache for GTIN: {gtin}...")
    try:
        # Using filterByFormula for precise search
        results = airtable.search('gtin_upc', gtin)
        
        if results:
            record = results[0] # Get the first matching record
            record_id = record['id']
            current_fields = record['fields']
            
            # Update lookup_count and last_access
            new_lookup_count = current_fields.get('lookup_count', 0) + 1
            new_last_access = datetime.now().isoformat()
            
            update_data = {
                'lookup_count': new_lookup_count,
                'last_access': new_last_access
            }
            
            # Use update method to modify existing record
            airtable.update(record_id, update_data)
            print(f"  ✅ Found in Airtable cache. Updated lookup_count to {new_lookup_count}.")
            return current_fields # Return the original fields (updated metadata is in Airtable)
    except Exception as e:
        print(f"  ⚠️ Error in check_airtable_cache for GTIN {gtin}: {e}")
    return None

def fetch_from_usda_api(gtin):
    """
    Queries the USDA FoodData Central API using the GTIN.
    Returns the first matching food item's data if found, otherwise None.
    """
    if not USDA_API_KEY:
        print("USDA API Key not set. Skipping USDA API fetch.")
        return None

    print(f"  Querying USDA API for GTIN: {gtin}...")
    params = {
        'query': gtin,
        'api_key': USDA_API_KEY,
        'dataType': ['Branded'], # Focus on branded foods
        'pageSize': 1           # Only need one result
    }
    
    try:
        response = requests.get(USDA_SEARCH_URL, params=params)
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        data = response.json()
        
        if data.get('foods'):
            print("  📥 Pulled from USDA API.")
            return data['foods'][0] # Return the first food item found
    except requests.exceptions.RequestException as e:
        print(f"  ❌ Error fetching from USDA API for GTIN {gtin}: {e}")
    except json.JSONDecodeError:
        print(f"  ❌ JSON Decode Error from USDA API for GTIN {gtin}. Response: {response.text.strip()}")
    except Exception as e:
        print(f"  ❌ Unexpected Error fetching from USDA: {e}")
        
    return None

def store_to_airtable(gtin, usda_data):
    """
    Stores product data pulled from USDA API into the Airtable cache.
    This function assumes the Airtable table has the specified fields.
    """
    print(f"  Attempting to store GTIN {gtin} to Airtable...")
    fields = {
        "gtin_upc": gtin,
        "fdc_id": str(usda_data.get("fdcId", "")), # Ensure fdcId is a string for 'Single line text' field
        "brand_name": usda_data.get("brandName", ""),
        "brand_owner": usda_data.get("brandOwner", ""),
        "description": usda_data.get("description", ""),
        "ingredients": usda_data.get("ingredients", ""),
        "lookup_count": 1, # New entry, so count starts at 1
        "last_access": datetime.now().isoformat(), # Current timestamp
        "hot_score": 1, # Placeholder for hot score, can be calculated dynamically later
        "source": "USDA API" # Indicate source of data
    }
    
    try:
        airtable.insert(fields)
        print(f"  ✅ Stored to Airtable: {fields.get('description', gtin)}")
    except Exception as e:
        print(f"  ❌ Failed to store to Airtable for GTIN {gtin}: {e}")

def count_airtable_rows():
    """Counts the total number of records in the Airtable table."""
    print("  Counting Airtable rows...")
    try:
        # Fetch all records without specifying fields, then count them.
        # Airtable's get_all() returns record objects, which can be counted directly.
        records = airtable.get_all() 
        return len(records)
    except Exception as e:
        print(f"  ⚠️ Error counting Airtable rows: {e}")
        return 0

def delete_least_valuable_row():
    """
    Deletes the least valuable record in Airtable based on lookup_count and last_access.
    Least valuable = lowest lookup_count, then oldest last_access for ties.
    """
    print("  Checking for least valuable row to evict...")
    try:
        # Fetch all records, including lookup_count and last_access for sorting
        records = airtable.get_all(fields=['lookup_count', 'last_access'])
        
        if records:
            # Sort records:
            # Primary sort key: 'lookup_count' (ascending) - least frequently used first
            # Secondary sort key: 'last_access' (ascending) - least recently used for ties
            # Ensure 'lookup_count' is treated as a number and 'last_access' as a string for comparison
            records_sorted = sorted(records, key=lambda r: (
                r["fields"].get("lookup_count", 0), # Default to 0 if missing
                r["fields"].get("last_access", "0000-01-01T00:00:00.000Z") # Default to very old date if missing
            ))
            
            least_valuable_record = records_sorted[0] # The first record after sorting is the least valuable
            record_id_to_delete = least_valuable_record['id']
            
            airtable.delete(record_id_to_delete)
            print(f"  🗑️ Deleted least valuable entry (ID: {record_id_to_delete}, "
                  f"Lookup: {least_valuable_record['fields'].get('lookup_count', 0)}, "
                  f"Last Access: {least_valuable_record['fields'].get('last_access', 'N/A')}).")
        else:
            print("  No records to evict.")
    except Exception as e:
        print(f"  ❌ Error deleting least valuable row: {e}")

def main():
    """
    Main function to handle GTIN lookup, caching, and API fallback.
    Takes GTIN as a command-line argument.
    """
    if len(sys.argv) < 2:
        print("Usage: python gtin_cache_manager.py <GTIN>")
        return

    gtin = sys.argv[1]
    print(f"🔎 Looking up GTIN: {gtin}")

    # 1. Check Airtable Cache
    cached_data = check_airtable_cache(gtin)
    if cached_data:
        print("📦 Found in Airtable cache. Details:")
        pprint(cached_data)
        return # Exit if found in cache

    # 2. If not in cache, fetch from USDA API
    usda_product_data = fetch_from_usda_api(gtin)
    
    if usda_product_data:
        # Check if cache is full before adding new entry
        current_row_count = count_airtable_rows()
        if current_row_count >= AIRTABLE_MAX_ROWS:
            print(f"  Cache is full ({current_row_count} rows). Evicting least valuable entry.")
            delete_least_valuable_row() # Evict before inserting new
        
        # Store the new product data to Airtable
        store_to_airtable(gtin, usda_product_data)
        print("\n🔍 Final Result (from USDA API and stored to Airtable):")
        pprint(usda_product_data) # Print the data that was just fetched/stored
    else:
        print("❌ Not found in USDA API.")
        print("🔍 Final Result: None")

if __name__ == "__main__":
    main()
