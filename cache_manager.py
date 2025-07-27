import os
import json
import datetime
from airtable import Airtable

# ✅ Airtable config via environment variables
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID")
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_TABLE_NAME = os.environ.get("AIRTABLE_TABLE_NAME", "GTIN Cache")

if not all([AIRTABLE_BASE_ID, AIRTABLE_API_KEY]):
    raise ValueError("Airtable credentials are missing. Please set AIRTABLE_BASE_ID and AIRTABLE_API_KEY.")

airtable = Airtable(AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME, AIRTABLE_API_KEY)

# ✅ Normalize GTIN field name used in Airtable
GTIN_FIELD = "gtin_upc"


def get_cached_product(gtin):
    """
    Look up product info in Airtable cache using GTIN.
    Returns full record (dict) or None.
    """
    try:
        result = airtable.search(GTIN_FIELD, gtin)
        if result:
            return result[0]  # First matching row
        return None
    except Exception as e:
        print(f"[Airtable] ❌ Error searching cache for GTIN {gtin}: {e}")
        return None


def update_lookup_count(record_id):
    """
    Increment lookup_count and update last_access timestamp for a cached record.
    """
    try:
        existing_record = airtable.get(record_id)
        current_count = existing_record["fields"].get("lookup_count", 0)
        new_count = int(current_count) + 1

        airtable.update(record_id, {
            "lookup_count": new_count,
            "last_access": datetime.datetime.utcnow().isoformat()
        })
    except Exception as e:
        print(f"[Airtable] ❌ Error updating lookup_count for {record_id}: {e}")


def write_to_cache(gtin, fdc_id, brand_name, brand_owner, description, ingredients_raw,
                   parsed_fda_non_common, parsed_fda_common, parsed_common_only,
                   truly_unidentified, data_score, completeness, nova_score, nova_description,
                   parsed=None):
    """
    Insert a new product entry into the Airtable GTIN Cache.
    """
    try:
        airtable.insert({
            "gtin_upc": gtin,
            "fdc_id": fdc_id,
            "brand_name": brand_name,
            "brand_owner": brand_owner,
            "description": description,
            "ingredients": ingredients_raw,
            "Parsed Ingredients JSO": json.dumps(parsed, indent=2) if parsed else "",
            "lookup_count": 1,
            "last_access": datetime.datetime.utcnow().isoformat(),
            "hot_score": 0,
            "source": "USDA API",
            "identified_fda_non_common": parsed_fda_non_common,
            "identified_fda_common": parsed_fda_common,
            "identified_common_ingredients_only": parsed_common_only,
            "truly_unidentified_ingredients": truly_unidentified,
            "data_score": data_score,
            "data_completeness_level": completeness,
            "nova_score": nova_score,
            "nova_description": nova_description
        })
        print(f"[Airtable] ✅ Inserted GTIN {gtin} into cache.")
    except Exception as e:
        print(f"[Airtable] ❌ Error inserting GTIN {gtin} into cache: {e}")
