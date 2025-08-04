# off_lookup.py

import requests

class OFFProductNotFound(Exception):
    pass

def fetch_product_from_off(gtin: str) -> dict:
    """
    Query Open Food Facts for product info using GTIN.
    Returns dict with description, brand_name, ingredients_string, nova_score.
    Raises OFFProductNotFound if not found.
    """
    url = f"https://world.openfoodfacts.org/api/v0/product/{gtin}.json"
    print(f"🔍 Requesting OFF API: {url}")  # Debug line

    response = requests.get(url)
    
    if response.status_code != 200:
        raise Exception(f"OFF API error: HTTP {response.status_code}")

    data = response.json()
    if data.get("status") != 1:
        raise OFFProductNotFound(f"GTIN {gtin} not found in OFF")

    product = data["product"]

    result = {
        "description": product.get("product_name", "").strip(),
        "brand_name": product.get("brands", "").strip(),
        "ingredients_string": product.get("ingredients_text", "").strip(),
        "nova_score": product.get("nova_group", None)
    }

    return result

# 🔧 Test it manually
if __name__ == "__main__":
    test_gtin = "737628064502"
    try:
        result = fetch_product_from_off(test_gtin)
        print("✅ Product found:")
        for k, v in result.items():
            print(f"   {k}: {v}")
    except OFFProductNotFound:
        print("❌ Product not found in Open Food Facts.")
    except Exception as e:
        print(f"🔥 Unexpected error: {e}")
