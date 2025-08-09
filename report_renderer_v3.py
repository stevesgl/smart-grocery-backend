# ## 5. `report_renderer.py` – **HTML Trust Report Generator**
# - **Purpose:** Takes classified ingredient data and formats it into a user-friendly HTML report for the frontend.
# - **Key Functions:**
#   - Receives:
#     - Product details (name, brand, etc.)
#     - Raw and classified ingredients
#     - NOVA score
#     - Flags (future use)
#   - Structures data into HTML sections:
#     - FDA Additives
#     - Classified Ingredients
#     - Unclassified Ingredients
#   - Outputs final HTML string.
# - **Workflow Role:** **Presentation Layer** – converts parsed backend results into the Trust Report format.


# FILE: backend/report_renderer.py

"""
This module is responsible ONLY for rendering the Trust Report HTML.
It does not fetch data, classify ingredients, or interact with APIs.
It takes structured product data + classified ingredients and outputs
a complete HTML report following our Tailwind UI spec.
"""

from html import escape

def generate_trust_report_html(
    parsed_fda_additives,
    parsed_classified_ingredients,
    unclassified,
    product_meta
):
    """
    Generate the Trust Report HTML from the three classification buckets and product meta.
    Inputs:
      - parsed_fda_additives: list[dict]  # [{token,resolved,classification}]
      - parsed_classified_ingredients: list[dict]
      - unclassified: list[dict]
      - product_meta: dict  # {gtin, product_name, brand_name, brand_owner, source, nova_score}
    Returns: str (HTML)
    """

    # --- Start HTML ---
    html_parts = []

    # --- Header / product info ---
    title = escape(product_meta.get("product_name") or "Unknown Product")
    brand_line = product_meta.get("brand_owner") or product_meta.get("brand_name") or ""
    brand_line = escape(brand_line)

    html_parts.append(f"""
    <div class="p-4 border-b border-gray-200">
        <h1 class="text-2xl font-bold">{title}</h1>
        <p class="text-gray-600">{brand_line}</p>
    </div>
    """)

    # --- Sections ---
    html_parts.append(_render_list_section("FDA Additives", parsed_fda_additives))
    html_parts.append(_render_list_section("Ingredients (Classified)", parsed_classified_ingredients))
    html_parts.append(_render_list_section("Ingredients (Unclassified)", unclassified))

    # --- Flags placeholder ---
    html_parts.append(_render_flags_placeholder())

    # --- Footer ---
    html_parts.append("""
    <div class="mt-6 text-xs text-gray-500 text-center">
      Built from sources like FDA/USDA. We’re improving every day.
      The more you use, the better we get!
    </div>
    """)

    return "\n".join(html_parts)

def _render_list_section(title: str, items: list[dict]) -> str:
    """
    Render a simple list section. Items are classifier dicts:
      { "token": str, "resolved": str, "classification": str }
    """
    if not items:
        return ""

    def _name(i: dict) -> str:
        # Prefer original token for display; fallback to resolved
        val = (i.get("token") or i.get("resolved") or "").strip()
        return escape(val or "Unknown")

    lis = "\n".join(f"<li class='list-disc ml-6'>{_name(i)}</li>" for i in items)

    return f"""
    <div class="mt-4">
        <h2 class="text-xl font-bold mb-2">{escape(title)}</h2>
        <ul>{lis}</ul>
    </div>
    """

def _render_flags_placeholder() -> str:
    return """
    <div class="mt-6 p-4 border border-gray-200 rounded-md bg-gray-50">
      <h3 class="font-semibold mb-1">Your Flags (Coming Soon)</h3>
      <p class="text-sm text-gray-600">Personalized flags and family profiles arrive in a future update.</p>
    </div>
    """

