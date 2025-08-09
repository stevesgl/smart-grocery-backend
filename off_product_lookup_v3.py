# FILE: off_product_lookup.py
# ## 2. `off_product_lookup.py` – **Primary Product Data Source**
# - **Purpose:** Queries the **Open Food Facts API** for product details using the GTIN.
# - **Key Functions:**
#   - Fetches JSON from OFF’s API endpoint.
#   - Extracts:
#     - `product_name` / description
#     - Brand info
#     - `ingredients_text` (string) and/or `ingredients` (list)
#     - NOVA group score
#   - Returns a dictionary to `trust_report_service.py`.
# - **Workflow Role:** **Primary Data Fetcher** – provides the first attempt at retrieving product details.


# FILE: backend/off_product_lookup.py

import requests

class OFFProductNotFound(Exception):
    """Raised when a product is not found in Open Food Facts."""
    pass

def fetch_product_from_off(barcode: str) -> dict:
    """
    Fetch product data from Open Food Facts for the given barcode.
    Prioritizes ingredients_text over structured ingredients list.
    """
    url = f"https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
    response = requests.get(url, timeout=10)

    if response.status_code != 200:
        raise OFFProductNotFound(f"OFF API request failed: {response.status_code}")

    data = response.json()

    # Ensure product exists in the response
    product = data.get("product")
    if not product:
        raise OFFProductNotFound(f"Product not found in OFF for barcode {barcode}")

    # ✅ Capture structured list early (outside the 'not product' block)
    ingredients_list = product.get("ingredients", [])
    if not isinstance(ingredients_list, list):
        ingredients_list = []

    # --- Extract key fields ---
    description = product.get("product_name", "N/A")
    brand_name = product.get("brands", "N/A")
    brand_owner = None  # OFF doesn't clearly provide brand owner

    # Prioritize ingredients_text over ingredients list
    ingredients_text = product.get("ingredients_text")
    if not ingredients_text:
        # ✅ Use the already-captured ingredients_list as fallback
        if ingredients_list:
            ingredients_text = ", ".join(
                (i.get("text") or "").strip() for i in ingredients_list if i.get("text")
            )
        else:
            ingredients_text = "N/A"

    nova_score = product.get("nova_group", None)
    fdc_id = None  # Not applicable for OFF

    return {
        "product_name": description,
        "brand_name": brand_name,
        "brand_owner": brand_owner,
        "ingredients_text": ingredients_text,   # used for MVP classification
        "ingredients_list": ingredients_list,   # reserved for MVP+1
        "nova_score": nova_score,
        "fdc_id": fdc_id
    }
