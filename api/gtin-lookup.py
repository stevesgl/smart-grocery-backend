# api/gtin-lookup.py
import os
import json
import requests
from datetime import datetime
from airtable import Airtable # This library will be installed by Vercel

# ========================== CONFIGURATION (from Environment Variables) ==========================
# Vercel will inject these as environment variables during deployment.
# You MUST set these in your Vercel project settings.
AIRTABLE_BASE_ID = os.environ.get('AIRTABLE_BASE_ID')
AIRTABLE_TABLE_NAME = os.environ.get('AIRTABLE_TABLE_NAME')
AIRTABLE_API_KEY = os.environ.get('AIRTABLE_API_KEY') # This is your Airtable Personal Access Token (PAT)
USDA_API_KEY = os.environ.get('USDA_API_KEY')

# Airtable max rows for the free tier (for eviction logic)
AIRTABLE_MAX_ROWS = 1000 
# ===============================================================================================

# Initialize Airtable client
# We add a check for None in case environment variables are not set during local testing
# or if there's an issue with Vercel env var loading.
airtable = None
if AIRTABLE_BASE_ID and AIRTABLE_TABLE_NAME and AIRTABLE_API_KEY:
    try:
        airtable = Airtable(AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME, AIRTABLE_API_KEY)
    except Exception as e:
        print(f"Error initializing Airtable client: {e}")
        # In a production system, you'd want more robust error handling here.

# USDA API search URL
USDA_SEARCH_URL = 'https://api.nal.usda.gov/fdc/v1/foods/search'

# ===================================================================
# Functions from gtin_cache_manager.py (adapted for serverless context)
# ===================================================================

def check_airtable_cache(gtin):
    """
    Checks if a GTIN exists in the Airtable cache.
    If found, it updates the lookup_count and last_access fields for that record.
    """
    if not airtable:
        print("Airtable client not initialized. Skipping cache check.")
        return None
    
    print(f"  Checking Airtable cache for GTIN: {gtin}...")
    try:
        results = airtable.search('gtin_upc', gtin)
        
        if results:
            record = results[0] # Get the first matching record
            record_id = record['id']
            current_fields = record['fields']
            
            new_lookup_count = current_fields.get('lookup_count', 0) + 1
            new_last_access = datetime.now().isoformat()
            
            update_data = {
                'lookup_count': new_lookup_count,
                'last_access': new_last_access
            }
            
            airtable.update(record_id, update_data)
            print(f"  ✅ Found in Airtable cache. Updated lookup_count to {new_lookup_count}.")
            return current_fields
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
        'dataType': ['Branded'],
        'pageSize': 1
    }
    
    try:
        response = requests.get(USDA_SEARCH_URL, params=params)
        response.raise_for_status()
        data = response.json()
        
        if data.get('foods'):
            print("  📥 Pulled from USDA API.")
            return data['foods'][0]
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
    """
    if not airtable:
        print("Airtable client not initialized. Skipping store to Airtable.")
        return
        
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
    if not airtable:
        print("Airtable client not initialized. Skipping row count.")
        return 0
        
    print("  Counting Airtable rows...")
    try:
        records = airtable.get_all(fields=['id']) 
        return len(records)
    except Exception as e:
        print(f"  ⚠️ Error counting Airtable rows: {e}")
        return 0

def delete_least_valuable_row():
    """
    Deletes the least valuable record in Airtable based on lookup_count and last_access.
    Least valuable = lowest lookup_count, then oldest last_access for ties.
    """
    if not airtable:
        print("Airtable client not initialized. Skipping row deletion.")
        return
        
    print("  Checking for least valuable row to evict...")
    try:
        records = airtable.get_all(fields=['lookup_count', 'last_access'])
        
        if records:
            records_sorted = sorted(reco