    # api/gtin-lookup.py
    import os
    import json
    import requests
    from datetime import datetime
    from airtable import Airtable
    from flask import Flask, request, jsonify # Import Flask components

    # Initialize Flask app
    app = Flask(__name__)

    # ========================== CONFIGURATION (from Environment Variables) ==========================
    # Render will inject these as environment variables during deployment.
    AIRTABLE_BASE_ID = os.environ.get('AIRTABLE_BASE_ID')
    AIRTABLE_TABLE_NAME = os.environ.get('AIRTABLE_TABLE_NAME')
    AIRTABLE_API_KEY = os.environ.get('AIRTABLE_API_KEY')
    USDA_API_KEY = os.environ.get('USDA_API_KEY')

    # Airtable max rows for the free tier (for eviction logic)
    AIRTABLE_MAX_ROWS = 1000 
    # ===============================================================================================

    # Initialize Airtable client
    airtable = None
    if AIRTABLE_BASE_ID and AIRTABLE_TABLE_NAME and AIRTABLE_API_KEY:
        try:
            airtable = Airtable(AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME, AIRTABLE_API_KEY)
        except Exception as e:
            print(f"Error initializing Airtable client: {e}")

    # USDA API search URL
    USDA_SEARCH_URL = 'https://api.nal.usda.gov/fdc/v1/foods/search'

    # ===================================================================
    # Functions (remain largely the same)
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
                record = results[0]
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
                records_sorted = sorted(records, key=lambda r: (
                    r["fields"].get("lookup_count", 0), 
                    r["fields"].get("last_access", "0000-01-01T00:00:00.000Z") 
                ))
                
                least_valuable_record = records_sorted[0] 
                record_id_to_delete = least_valuable_record['id']
                
                airtable.delete(record_id_to_delete)
                print(f"  🗑️ Deleted least valuable entry (ID: {record_id_to_delete}, "
                      f"Lookup: {least_valuable_record['fields'].get('lookup_count', 0)}, "
                      f"Last Access: {least_valuable_record['fields'].get('last_access', 'N/A')}).")
            else:
                print("  No records to evict.")
        except Exception as e:
            print(f"  ❌ Error deleting least valuable row: {e}")

    # ===================================================================
    # Flask API Endpoint
    # ===================================================================

    @app.route('/api/gtin-lookup', methods=['POST', 'OPTIONS'])
    def gtin_lookup_api():
        """
        Flask API endpoint for GTIN lookup.
        Expects a POST request with a JSON body containing 'gtin'.
        Returns JSON response.
        """
        # Set CORS headers to allow requests from your frontend
        # In production, replace '*' with your actual frontend domain (e.g., 'https://your-frontend.vercel.app')
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Content-Type': 'application/json'
        }

        # Handle OPTIONS preflight request for CORS
        if request.method == 'OPTIONS':
            return '', 204, headers

        if request.method != 'POST':
            return jsonify({"error": "Method Not Allowed", "message": "Only POST requests are supported."}), 405, headers

        try:
            request_data = request.get_json()
            gtin = request_data.get('gtin')

            if not gtin:
                return jsonify({"error": "Bad Request", "message": "GTIN is required in the request body."}), 400, headers

            # 1. Check Airtable Cache
            cached_data = check_airtable_cache(gtin)
            if cached_data:
                response_data = {"status": "found_in_cache", "gtin": gtin, "data": cached_data}
                return jsonify(response_data), 200, headers

            # 2. If not in cache, fetch from USDA API
            usda_product_data = fetch_from_usda_api(gtin)
            
            if usda_product_data:
                # Check if cache is full before adding new entry
                current_row_count = count_airtable_rows()
                if current_row_count >= AIRTABLE_MAX_ROWS:
                    print(f"Cache is full ({current_row_count} rows). Evicting least valuable entry.")
                    delete_least_valuable_row()
                
                # Store the new product data to Airtable
                store_to_airtable(gtin, usda_product_data)
                response_data = {"status": "pulled_from_usda_and_cached", "gtin": gtin, "data": usda_product_data}
                return jsonify(response_data), 200, headers
            else:
                response_data = {"status": "not_found", "gtin": gtin, "message": "Product not found in USDA API."}
                return jsonify(response_data), 404, headers

        except Exception as e:
            # Catch all other exceptions and return a 500 error
            response_data = {"error": "Internal Server Error", "message": str(e)}
            return jsonify(response_data), 500, headers

    # Standard way to run Flask app for local testing
    if __name__ == '__main__':
        app.run(debug=True)
    