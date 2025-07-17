# api/gtin-lookup.py

import os
import json
import requests
from airtable import Airtable

# Initialize Airtable (using environment variables)
AIRTABLE_BASE_ID = os.environ.get('AIRTABLE_BASE_ID')
AIRTABLE_TABLE_NAME = os.environ.get('AIRTABLE_TABLE_NAME')
AIRTABLE_API_KEY = os.environ.get('AIRTABLE_API_KEY')

# Initialize USDA API key
USDA_API_KEY = os.environ.get('USDA_API_KEY')

# Airtable setup
airtable = Airtable(AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME, AIRTABLE_API_KEY)

def handle_cors_preflight(request_headers):
    """Handles CORS preflight (OPTIONS) requests."""
    response_headers = {
        'Access-Control-Allow-Origin': '*',  # Allow all origins for now
        'Access-Control-Allow-Methods': 'POST, OPTIONS', # Allow POST and OPTIONS
        'Access-Control-Allow-Headers': 'Content-Type', # Allow Content-Type header
        'Access-Control-Max-Age': '86400' # Cache preflight for 24 hours
    }
    return {
        'statusCode': 204, # No Content for successful preflight
        'headers': response_headers,
        'body': ''
    }

def handler(request):
    # Set CORS headers for all responses
    cors_headers = {
        'Access-Control-Allow-Origin': '*', # Allow all origins for now
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
    }

    # Handle CORS preflight request
    if request.method == 'OPTIONS':
        return handle_cors_preflight(request.headers)

    # Ensure it's a POST request for actual data processing
    if request.method != 'POST':
        return {
            'statusCode': 405,
            'headers': cors_headers,
            'body': json.dumps({'error': 'Method Not Allowed'})
        }

    try:
        # Parse the request body
        body = json.loads(request.body)
        gtin = body.get('gtin')

        if not gtin:
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'GTIN not provided'})
            }

        # 1. Check Airtable Cache
        # Using a query to find records where 'GTIN' field matches the gtin
        # Airtable's filterByFormula requires a specific format
        # Using f"{{GTIN}} = '{gtin}'" might be problematic if GTIN is not a string type in Airtable
        # A safer approach is to fetch all and filter in Python if the table is small,
        # or use a more robust query if Airtable supports it (like exact match on a number field).
        # For simplicity, let's assume GTIN is text and filter by formula.
        
        # NOTE: Airtable's filterByFormula can be tricky with exact matches.
        # A more reliable way for exact match on a string field might be:
        # records = airtable.search('GTIN', gtin)
        
        # Let's use search which is more direct for exact matches
        cached_record = airtable.search('GTIN', gtin)
        
        if cached_record:
            print(f"GTIN {gtin} found in cache.")
            return {
                'statusCode': 200,
                'headers': cors_headers,
                'body': json.dumps({
                    'gtin': gtin,
                    'status': 'found_in_cache',
                    'data': {
                        'description': cached_record['Description'],
                        'ingredients': cached_record['Ingredients']
                    }
                })
            }

        # 2. If not in cache, query USDA FoodData Central
        print(f"GTIN {gtin} not in cache, querying USDA.")
        usda_url = f"https://api.nal.usda.gov/fdc/v1/foods/search?query={gtin}&api_key={USDA_API_KEY}"
        usda_response = requests.get(usda_url)
        usda_data = usda_response.json()

        product_description = 'N/A'
        product_ingredients = 'N/A'

        if usda_data and 'foods' in usda_data and usda_data['foods']:
            # Find the first food item that matches the GTIN closely
            for food in usda_data['foods']:
                # USDA API often returns 'gtinUpc' or similar for barcodes
                if str(food.get('gtinUpc')) == gtin:
                    product_description = food.get('description', 'N/A')
                    # Ingredients might be in 'ingredients' or 'foodNutrients' list
                    product_ingredients = food.get('ingredients', 'N/A')
                    break
            else: # If loop completes without finding a direct GTIN match
                # Fallback to description of the first food item if no direct GTIN match
                product_description = usda_data['foods'][0].get('description', 'N/A')
                product_ingredients = usda_data['foods'][0].get('ingredients', 'N/A')
        
        if product_description != 'N/A':
            # 3. Cache the result in Airtable
            airtable.insert({
                'GTIN': gtin,
                'Description': product_description,
                'Ingredients': product_ingredients
            })
            print(f"GTIN {gtin} pulled from USDA and cached.")
            return {
                'statusCode': 200,
                'headers': cors_headers,
                'body': json.dumps({
                    'gtin': gtin,
                    'status': 'pulled_from_usda_and_cached',
                    'data': {
                        'description': product_description,
                        'ingredients': product_ingredients
                    }
                })
            }
        else:
            print(f"GTIN {gtin} not found in USDA.")
            return {
                'statusCode': 200,
                'headers': cors_headers,
                'body': json.dumps({
                    'gtin': gtin,
                    'status': 'not_found',
                    'data': None
                })
            }

    except Exception as e:
        print(f"Error processing request: {e}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }