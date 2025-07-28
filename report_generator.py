import html

# --- Step 1: Module-level Constants ---
CATEGORY_DISPLAY_NAMES = {
    'truly_unidentified': 'Unidentified',
    'fda_non_common': 'Additives',        # RED category
    'common_fda_regulated': 'Common Substances', # YELLOW category
    'common_only': 'Whole Ingredients'     # GREEN category
}

# Define a priority for sorting ingredients for display
# Lower number means higher priority (comes first)
CATEGORY_SORT_PRIORITY = {
    'fda_non_common': 1,        # Additives (RED)
    'common_fda_regulated': 2,  # Common Substances (YELLOW)
    'common_only': 3,           # Whole Ingredients (GREEN)
    'truly_unidentified': 4     # Unidentified (GREY)
}

# NOVA Score Colors mapping
NOVA_COLOR_CLASSES = {
    1: 'bg-green-300',
    2: 'bg-cyan-300',
    3: 'bg-amber-300',
    4: 'bg-red-500'
}
# --- END Step 1 ---


def _generate_fda_additives_html_block(fda_additives):
    """
    Generate the HTML block for FDA additives with collapsible details.
    Each additive shows name, and on expand: used_for, other_names.
    This is a helper function for the main trust report.

    :param fda_additives: List of dicts, each with:
        - name
        - used_for (list)
        - other_names (list)
        - trust_report_category (added for styling)
    :return: HTML string
    """
    if not fda_additives:
        return ""

    additives_html = []
    for idx, additive in enumerate(fda_additives):
        used_for_html = ''
        if additive.get('used_for'):
            used_for_html = f"<div><strong>Used For:</strong> {', '.join(html.escape(u) for u in additive['used_for'])}</div>"

        other_names_html = ''
        if additive.get('other_names'):
            other_names_html = f"<div><strong>Other Names:</strong> {', '.join(html.escape(o) for o in additive['other_names'])}</div>"

        additives_html.append(f"""
                <li class="p-3 rounded-md bg-red-100 text-red-900">
                    <div class="flex justify-between items-center cursor-pointer" onclick="toggleItem('fda-additive-item-{idx}', 'fda-additive-icon-{idx}')">
                        <span class="font-medium text-base">{html.escape(additive['name'])}</span>
                        <span id="fda-additive-icon-{idx}" class="text-xl font-bold">+</span>
                    </div>
                    <div id="fda-additive-item-{idx}" class="mt-2 text-sm text-gray-700 space-y-1" style="display: none;">
                        <div><strong>Category:</strong> Additive</div>
                        {used_for_html}
                        {other_names_html}
                    </div>
                </li>
        """)
    return f"""
    <div class="bg-white p-6 rounded-md shadow-sm mb-6">
        <div class="flex justify-between items-center cursor-pointer mb-4" onclick="toggleSection('fda-additives-section', 'toggle-icon-fda-additives')">
            <h2 class="text-xl font-bold">FDA Additives Details</h2>
            <span id="toggle-icon-fda-additives" class="text-2xl font-bold">+</span>
        </div>
        <ul id="fda-additives-section" class="space-y-3" style="display: none;">
            {''.join(additives_html)}
        </ul>
    </div>
    """

# REMOVED: COLLAPSIBLE_JS constant is no longer defined here.

def generate_trust_report_html(
    product_name: str,
    brand_name: str,
    brand_owner: str,
    ingredients_raw: str,
    parsed_ingredients: list, # List of parsed ingredient dicts
    parsed_fda_common: list, # Used for summary count
    parsed_fda_non_common: list, # Used for summary count
    parsed_common_only: list, # Used for summary count
    truly_unidentified: list, # Used for summary count
    data_completeness_score: float,
    data_completeness_level: str,
    nova_score: int, # The integer NOVA score (1-4)
    nova_description: str,
    all_fda_parsed_for_report: list # This parameter is no longer used for a separate section, but kept for compatibility
) -> str:
    """
    Generates a comprehensive Trust Report in HTML format.

    :param product_name: Name of the product.
    :param brand_name: Brand name of the product.
    :param brand_owner: Owner of the brand.
    :param ingredients_raw: The raw, unparsed ingredient string.
    :param parsed_ingredients: A list of dictionaries, each representing a parsed ingredient
                                with 'original_string', 'base_ingredient', 'modifiers',
                                'parenthetical_info', and 'attributes' (including 'trust_report_category').
    :param parsed_fda_common: List of ingredients categorized as 'common_fda_regulated'.
    :param parsed_fda_non_common: List of ingredients categorized as 'fda_non_common'.
    :param parsed_common_only: List of ingredients categorized as 'common_only'.
    :param truly_unidentified: List of ingredients categorized as 'truly_unidentified'.
    :param data_completeness_score: The percentage score for data completeness.
    :param data_completeness_level: The qualitative level for data completeness (e.g., "High").
    :param nova_score: The NOVA score (integer 1-4).
    :param nova_description: The description for the NOVA score (e.g., "Ultra-Processed Food").
    :param all_fda_parsed_for_report: This parameter is no longer used for a separate section, but kept for compatibility.
    :return: A string containing the full HTML of the trust report.
    """

    html_content = []

    # Head and basic body structure
    # REMOVED: COLLAPSIBLE_JS from here
    html_content.append("""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Smart Grocery Lens - Trust Report Mockup</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
</head>
<body class="bg-gray-50 text-gray-900">
    <div class="max-w-4xl mx-auto bg-white p-8 rounded-lg shadow-lg mt-10">
    """)

    # 1. Product Header
    html_content.append(f"""
        <div class="text-center">
            <h1 class="text-3xl font-bold mb-2">{html.escape(product_name)}</h1>
            <p class="text-lg text-gray-600 mb-6">Brand: {html.escape(brand_name)} ({(html.escape(brand_owner))})</p>
        </div>
    """)

    # 2. NOVA Score Section
    nova_circles_html = []
    for i in range(nova_score):
        color_class = NOVA_COLOR_CLASSES.get(i + 1, 'bg-red-500')
        nova_circles_html.append(f'<div class="w-6 h-6 rounded-full {color_class} {"mr-1.5" if i < nova_score - 1 else ""}"></div>')

    html_content.append(f"""
        <div class="bg-purple-50 p-6 rounded-md border border-purple-200 mb-6 text-center">
            <h2 class="text-xl font-semibold text-purple-800 mb-3">NOVA Score</h2>
            <div class="flex justify-center items-center mb-3">
                {''.join(nova_circles_html)}
            </div>
            <div class="text-[2.5rem] font-bold text-purple-700">{nova_score}</div>
            <p class="text-md text-gray-700">{html.escape(nova_description)}</p>
        </div>
    """)

    # 3. Ingredient Breakdown Summary
    html_content.append(f"""
        <div class="bg-white p-6 rounded-md shadow-sm mb-6">
            <h2 class="text-xl font-bold mb-4">Ingredient Breakdown Summary</h2>
            <div class="grid grid-cols-2 gap-4">
                <div class="p-4 rounded-md border border-yellow-300 bg-yellow-100 text-yellow-900">
                    <div class="text-lg font-semibold">Common Substances</div>
                    <div class="text-2xl font-bold text-gray-900">{len(parsed_fda_common)}</div>
                </div>
                <div class="p-4 rounded-md border border-red-300 bg-red-100 text-red-900">
                    <div class="text-lg font-semibold">Additives</div>
                    <div class="text-2xl font-bold text-gray-900">{len(parsed_fda_non_common)}</div>
                </div>
                <div class="p-4 rounded-md border border-green-300 bg-green-100 text-green-900">
                    <div class="text-lg font-semibold">Whole Ingredients</div>
                    <div class="text-2xl font-bold text-gray-900">{len(parsed_common_only)}</div>
                </div>
                <div class="p-4 rounded-md border border-blue-300 bg-blue-100 text-blue-900">
                    <div class="text-lg font-semibold">Unidentified</div>
                    <div class="text-2xl font-bold text-gray-900">{len(truly_unidentified)}</div>
                </div>
            </div>
        </div>
    """)

    # Sort parsed_ingredients for display based on CATEGORY_SORT_PRIORITY
    sorted_parsed_ingredients = sorted(
        parsed_ingredients,
        key=lambda x: CATEGORY_SORT_PRIORITY.get(x['attributes'].get('trust_report_category'), 99)
    )

    # Full Ingredient Breakdown
    parsed_ingredients_html_list = []
    for idx, p in enumerate(sorted_parsed_ingredients):
        category = p['attributes'].get('trust_report_category', 'truly_unidentified')
        display_category_name = CATEGORY_DISPLAY_NAMES.get(category, 'Unknown')

        # Determine color classes based on category for individual items
        bg_color = 'bg-gray-100' # Default for unknown
        text_color = 'text-gray-900'
        border_color = 'border-gray-300'

        if category == 'common_fda_regulated':
            bg_color = 'bg-yellow-100'
            text_color = 'text-yellow-900'
            border_color = 'border-yellow-300'
        elif category == 'fda_non_common':
            bg_color = 'bg-red-100'
            text_color = 'text-red-900'
            border_color = 'border-red-300'
        elif category == 'common_only':
            bg_color = 'bg-green-100'
            text_color = 'text-green-900'
            border_color = 'border-green-900'
        elif category == 'truly_unidentified':
            bg_color = 'bg-blue-100'
            text_color = 'text-blue-900'
            border_color = 'border-blue-300'

        modifiers_html = ''
        if p.get('modifiers'):
            modifiers_html = f"<div><strong>Modifiers:</strong> {', '.join(html.escape(m) for m in p['modifiers'])}</div>"

        parenthetical_html = ''
        if p.get('parenthetical_info') and p['parenthetical_info'].get('content'):
            parenthetical_html = f"<div><strong>Parenthetical Info:</strong> {html.escape(p['parenthetical_info'].get('content', ''))}</div>"

        punctuation_html = ''
        if p.get('punctuation'):
            punctuation_html = f"<div><strong>Punctuation:</strong> {html.escape(p['punctuation'])}</div>"


        parsed_ingredients_html_list.append(f"""
                <li class="p-3 rounded-md {bg_color} {text_color} border {border_color}">
                    <div class="flex justify-between items-center cursor-pointer" onclick="toggleItem('parsed-item-{idx}', 'parsed-icon-{idx}')">
                        <span class="font-medium text-base">
                            {html.escape(p['original_string'])}
                        </span>
                        <span id="parsed-icon-{idx}" class="text-xl font-bold">+</span>
                    </div>
                    <div id="parsed-item-{idx}" class="mt-2 text-sm text-gray-700 space-y-1" style="display: none;">
                        <div><strong>Category:</strong> {display_category_name}</div>
                        <div><strong>Base Ingredient:</strong> {html.escape(p['base_ingredient'])}</div>
                        {modifiers_html}
                        {parenthetical_html}
                        {punctuation_html}
                    </div>
                </li>
        """)

    html_content.append(f"""
        <div class="bg-white p-6 rounded-md shadow-sm mb-6">
            <div class="flex justify-between items-center cursor-pointer mb-4" onclick="toggleSection('parsed-ingredients-section', 'toggle-icon-1')">
                <h2 class="text-xl font-bold">Full Ingredient Breakdown</h2>
                <span id="toggle-icon-1" class="text-2xl font-bold">+</span>
            </div>
            <ul id="parsed-ingredients-section" class="space-y-3" style="display: none;">
                {''.join(parsed_ingredients_html_list)}
            </ul>
        </div>
    """)

    # Simple List of Raw Ingredients
    raw_ingredients_list_html = "".join([f"<li>{html.escape(item.strip())}</li>" for item in ingredients_raw.split(',') if item.strip()])
    html_content.append(f"""
        <div class="bg-white p-6 rounded-md shadow-sm mb-6">
            <div class="flex justify-between items-center cursor-pointer mb-4" onclick="toggleSection('raw-ingredients-section', 'toggle-icon-2')">
                <h2 class="text-xl font-bold">Simple List of Raw Ingredients</h2>
                <span id="toggle-icon-2" class="text-2xl font-bold">+</span>
            </div>
            <ul id="raw-ingredients-section" class="list-disc pl-5 space-y-1 text-gray-700" style="display: none;">
                {raw_ingredients_list_html}
            </ul>
        </div>
    """)


    # Data Completeness Section
    html_content.append(f"""
        <div class="bg-blue-50 p-6 rounded-md border border-blue-200 mb-6">
            <h2 class="text-xl font-semibold text-blue-800 mb-3">Data Completeness</h2>
            <div class="w-full bg-gray-200 rounded-full h-4 mb-2">
                <div class="bg-blue-600 h-4 rounded-full" style="width: {data_completeness_score}%;"></div>
            </div>
            <p class="text-lg font-medium text-blue-700">{data_completeness_score}% Complete</p>
            <p class="text-sm text-gray-600">{html.escape(data_completeness_level)}</p>
        </div>
    """)

    # Closing tags
    html_content.append("""
    </div>
</body>
</html>
    """)

    return "".join(html_content)