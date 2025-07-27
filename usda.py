# usda.py

import requests
import os

API_KEY = os.getenv("USDA_API_KEY") or "your-api-key-here"

def fetch_product_from_usda(fdc_id: str) -> dict:
    """
    Fetch product data from the USDA FoodData Central API using the given FDC ID.
    Returns a dictionary with cleaned and relevant product data.
    """
    base_url = f"https://api.nal.usda.gov/fdc/v1/food/{fdc_id}"
    params = {"api_key": API_KEY}

    try:
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        return {
            "fdcId": data.get("fdcId"),
            "description": data.get("description", ""),
            "brandOwner": data.get("brandOwner", ""),
            "brandName": data.get("brandName", ""),
            "ingredients": data.get("ingredients", "")
        }

    except Exception as e:
        print(f"USDA fetch error for FDC ID {fdc_id}: {e}")
        return None
