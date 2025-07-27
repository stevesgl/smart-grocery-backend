# cache_manager.py
# This module provides caching functions, currently mocked out for MVP.
# In MVP+1, this will be replaced with actual caching logic (e.g., database, local file).

import json
import os
import datetime

# Mocked Airtable client for MVP. Remove/replace in MVP+1.
class MockAirtableClient:
    def __init__(self, *args, **kwargs):
        print("[Cache Manager - MOCKED] Initializing MockAirtableClient. No actual Airtable connection.")

    def get_all(self, *args, **kwargs):
        print("[Cache Manager - MOCKED] Attempted to get from Airtable. Caching is disabled for MVP.")
        return []

    def insert(self, *args, **kwargs):
        print("[Cache Manager - MOCKED] Attempted to insert into Airtable. Caching is disabled for MVP.")
        pass

    def update(self, *args, **kwargs):
        print("[Cache Manager - MOCKED] Attempted to update Airtable. Caching is disabled for MVP.")
        pass

    def search(self, *args, **kwargs):
        print("[Cache Manager - MOCKED] Attempted Airtable search. Caching is disabled for MVP.")
        return []


# Initialize the mocked Airtable instance (will not connect to real Airtable)
# from airtable import Airtable # Keep commented out for MVP
# try:
#     AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY")
#     AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID")
#     AIRTABLE_TABLE_NAME = os.environ.get("AIRTABLE_TABLE_NAME", "GTIN Cache")
#     AIRTABLE_LOOKUP_TABLE_NAME = os.environ.get("AIRTABLE_LOOKUP_TABLE_NAME", "GTIN Lookup Counts")
#
#     if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
#         print("[Airtable] Warning: AIRTABLE_API_KEY or AIRTABLE_BASE_ID not set. Airtable caching will not function.")
#         airtable_cache = MockAirtableClient()
#         airtable_lookup = MockAirtableClient()
#     else:
#         airtable_cache = Airtable(AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME, AIRTABLE_API_KEY)
#         airtable_lookup = Airtable(AIRTABLE_BASE_ID, AIRTABLE_LOOKUP_TABLE_NAME, AIRTABLE_API_KEY)
#         print("[Airtable] Connected to Airtable.")
# except Exception as e:
#     print(f"[Airtable] Error initializing Airtable: {e}. Using mocked client.")
#     airtable_cache = MockAirtableClient()
#     airtable_lookup = MockAirtableClient()


# Mocked functions for MVP (no-op)
def get_from_cache(gtin):
    """
    MOCKED: Attempts to retrieve product data from the cache.
    Returns None for MVP.
    """
    print(f"[Cache Manager] Caching is DISABLED. Not retrieving {gtin} from cache.")
    return None

def write_to_cache(
    gtin, fdc_id, brand_name, brand_owner, description, ingredients_raw,
    parsed_fda_non_common, parsed_fda_common, parsed_common_only,
    truly_unidentified, data_score, completeness, nova_score, nova_description,
    parsed
):
    """
    MOCKED: Writes product data to the cache.
    Does nothing for MVP.
    """
    print(f"[Cache Manager] Caching is DISABLED. Not writing {gtin} to cache.")
    pass

def update_lookup_count(gtin):
    """
    MOCKED: Increments the lookup count for a GTIN.
    Does nothing for MVP.
    """
    print(f"[Cache Manager] Caching is DISABLED. Not updating lookup count for {gtin}.")
    pass

# Original (commented out) Airtable implementation for reference in MVP+1
"""
# from airtable import Airtable
# import os
# import datetime
#
# AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY")
# AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID")
# AIRTABLE_TABLE_NAME = os.environ.get("AIRTABLE_TABLE_NAME", "GTIN Cache")
# AIRTABLE_LOOKUP_TABLE_NAME = os.environ.get("AIRTABLE_LOOKUP_TABLE_NAME", "GTIN Lookup Counts")
#
# airtable_cache = None
# airtable_lookup = None
#
# try:
#     if AIRTABLE_API_KEY and AIRTABLE_BASE_ID:
#         airtable_cache = Airtable(AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME, AIRTABLE_API_KEY)
#         airtable_lookup = Airtable(AIRTABLE_BASE_ID, AIRTABLE_LOOKUP_TABLE_NAME, AIRTABLE_API_KEY)
#         print("[Airtable] Connected to Airtable.")
#     else:
#         print("[Airtable] Warning: AIRTABLE_API_KEY or AIRTABLE_BASE_ID not set. Caching will not function.")
# except Exception as e:
#     print(f"[Airtable] Error initializing Airtable: {e}. Caching will be disabled.")
#     airtable_cache = None
#     airtable_lookup = None
#
#
# def get_from_cache(gtin):
#     \"\"\"
#     Attempts to retrieve product data from the Airtable cache.
#     \"\"\"
#     if not airtable_cache:
#         return None
#
#     try:
#         records = airtable_cache.search('GTIN', gtin)
#         if records:
#             print(f"[Airtable] Found {gtin} in cache.")
#             return records[0]['fields']
#     except Exception as e:
#         print(f"[Airtable] Error retrieving from cache for {gtin}: {e}")
#     return None
#
# def write_to_cache(
#     gtin, fdc_id, brand_name, brand_owner, description, ingredients_raw,
#     parsed_fda_non_common, parsed_fda_common, parsed_common_only,
#     truly_unidentified, data_score, completeness, nova_score, nova_description,
#     parsed
# ):
#     \"\"\"
#     Writes product data to the Airtable cache.
#     \"\"\"
#     if not airtable_cache:
#         return
#
#     try:
#         # Airtable has a limit on data size per cell.
#         # JSON fields should be stringified.
#         fields = {
#             "GTIN": gtin,
#             "FDC ID": fdc_id,
#             "Brand Name": brand_name,
#             "Brand Owner": brand_owner,
#             "Description": description,
#             "Ingredients Raw": ingredients_raw,
#             "Parsed FDA Non-Common": json.dumps(parsed_fda_non_common),
#             "Parsed FDA Common": json.dumps(parsed_fda_common),
#             "Parsed Common Only": json.dumps(parsed_common_only),
#             "Truly Unidentified": json.dumps(truly_unidentified),
#             "Data Score": data_score,
#             "Completeness": completeness,
#             "NOVA Score": nova_score,
#             "NOVA Description": nova_description,
#             "Parsed JSON": json.dumps(parsed),
#             "Last Cached": datetime.datetime.now().isoformat()
#         }
#         airtable_cache.insert(fields, typecast=True)
#         print(f"[Airtable] Successfully wrote {gtin} to cache.")
#     except Exception as e:
#         print(f"[Airtable] Error writing to cache for {gtin}: {e}")
#
# def update_lookup_count(gtin):
#     \"\"\"
#     Increments the lookup count for a GTIN in a separate Airtable table.
#     If the GTIN doesn't exist, it creates a new record.
#     \"\"\"
#     if not airtable_lookup:
#         return
#
#     try:
#         records = airtable_lookup.search('GTIN', gtin)
#         if records:
#             record_id = records[0]['id']
#             current_count = records[0]['fields'].get('Lookup Count', 0)
#             new_count = current_count + 1
#             airtable_lookup.update(record_id, {'Lookup Count': new_count})
#             print(f"[Airtable] Updated lookup_count for {gtin} to {new_count}.")
#         else:
#             airtable_lookup.insert({'GTIN': gtin, 'Lookup Count': 1})
#             print(f"[Airtable] Created new lookup_count record for {gtin}.")
#     except Exception as e:
#         print(f"[Airtable] ❌ Error updating lookup_count for {gtin}: {e}")
"""