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
        return "<p class='text-sm text-gray-500'>No FDA-recognized additives found in this product.</p>"

    output = [
        "<div class='space-y-4'>",
        "<h2 class='text-xl font-semibold'>FDA Additives</h2>"
    ]

    for additive in fda_additives:
        name = html.escape(additive.get("name", "Unknown Additive"))
        used_for = additive.get("used_for", [])
        other_names = additive.get("other_names", [])
        
        # --- Step 4: Add class based on category for FDA additives ---
        category_key = additive.get('trust_report_category', 'fda_non_common') # Default to fda_non_common
        css_class = f"category-{category_key.replace('_', '-')}"
        # --- END Step 4 ---

        # Collapsible container
        output.append(f"""
        <div class='border rounded-xl p-4 shadow-sm bg-white {css_class}'>
            <div class='flex items-center justify-between cursor-pointer' onclick='toggleCollapse(this)'>
                <span class='font-medium text-base'>{name}</span>
                <span class='text-xl font-bold'>+</span>
            </div>
            <div class='mt-2 hidden text-sm text-gray-700 space-y-2'>
                {"<p><strong>Used For:</strong> " + html.escape(', '.join(used_for)) + "</p>" if used_for else ""}
                {"<p><strong>Other Names:</strong> " + html.escape(', '.join(other_names)) + "</p>" if other_names else ""}
            </div>
        </div>
        """)
    output.append("</div>")
    return "\n".join(output)


def generate_trust_report_html(
    product_name,
    ingredients_raw,
    parsed_ingredients,
    parsed_fda_common,
    parsed_fda_non_common,
    parsed_common_only,
    truly_unidentified,
    data_completeness_score,
    data_completeness_level,
    nova_score,
    nova_description,
    all_fda_parsed_for_report # This now contains simplified FDA dicts with category
):
    """
    Generates a comprehensive HTML trust report for a product.

    :param product_name: Name of the product.
    :param ingredients_raw: Raw ingredient string from the product.
    :param parsed_ingredients: List of all parsed ingredient dicts.
    :param parsed_fda_common: List of common FDA regulated ingredients.
    :param parsed_fda_non_common: List of non-common FDA regulated additives.
    :param parsed_common_only: List of common-only (whole) ingredients.
    :param truly_unidentified: List of ingredients that could not be identified.
    :param data_completeness_score: Numerical score for data completeness.
    :param data_completeness_level: Textual level for data completeness.
    :param nova_score: NOVA score for the product.
    :param nova_description: Description for the NOVA score.
    :param all_fda_parsed_for_report: List of FDA additive dicts (simplified for report).
    :return: Full HTML string for the trust report.
    """
    # Initialize the list to store HTML parts
    html_content = [] # <--- FIX for "html_content" not defined

    html_content.append(f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trust Report for {html.escape(product_name)}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .category-fda-non-common {{
            background-color: #fee2e2; /* Red-100 */
            border-color: #ef4444; /* Red-500 */
        }}
        .category-common-fda-regulated {{
            background-color: #fffbeb; /* Yellow-100 */
            border-color: #f59e0b; /* Yellow-500 */
        }}
        .category-common-only {{
            background-color: #ecfdf5; /* Green-100 */
            border-color: #10b981; /* Green-500 */
        }}
        .category-truly-unidentified {{
            background-color: #f3f4f6; /* Gray-100 */
            border-color: #6b7280; /* Gray-500 */
        }}
        .collapsible-content {{
            display: none;
        }}
    </style>
</head>
<body class="bg-gray-50 p-6 font-sans">

    <div class="max-w-3xl mx-auto bg-white p-8 rounded-lg shadow-xl space-y-8">

        <header class="text-center pb-4 border-b border-gray-200">
            <h1 class="text-3xl font-bold text-gray-800 mb-2">Trust Report</h1>
            <p class="text-xl text-blue-600">for {html.escape(product_name)}</p>
        </header>

        <section class="space-y-4">
            <h2 class="text-2xl font-semibold text-gray-700">Product Details</h2>
            <div class="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
                <p><strong>Raw Ingredients:</strong></p>
                <p class="text-gray-600 text-sm italic">{html.escape(ingredients_raw)}</p>
            </div>
        </section>

        <section class="space-y-4">
            <h2 class="text-2xl font-semibold text-gray-700">Key Insights</h2>
            
            <div class="bg-white p-4 rounded-lg shadow-sm">
                <h3 class="text-xl font-semibold text-gray-700">Data Completeness</h3>
                <p class="text-gray-600 text-sm mb-2">Confidence in the analysis based on ingredient recognition:</p>
                <div class="flex items-center space-x-2">
                    <div class="w-full bg-gray-200 rounded-full h-2.5">
                        <div class="bg-blue-600 h-2.5 rounded-full" style="width: {data_completeness_score * 100:.0f}%"></div>
                    </div>
                    <span class="text-sm font-medium text-gray-700">{data_completeness_level} ({data_completeness_score * 100:.0f}%)</span>
                </div>
            </div>

            <div class="bg-white p-4 rounded-lg shadow-sm">
                <h3 class="text-xl font-semibold text-gray-700">NOVA Score</h3>
                <p class="text-gray-600 text-sm mb-2">A classification of food processing levels:</p>
                <div class="flex items-baseline space-x-2">
                    <span class="text-2xl font-bold text-green-600">{nova_score}</span>
                    <span class="text-base text-gray-700">{html.escape(nova_description)}</span>
                </div>
            </div>

            {_generate_fda_additives_html_block(all_fda_parsed_for_report)}
        </section>
""")

    # --- Step 2: Detailed Ingredient Breakdown - Category Counts ---
    # This entire HTML block for the Ingredient Breakdown header and summary counts
    # should be ONE single f-string literal.
    html_content.append(f"""
    <div class='bg-white p-4 rounded-lg shadow-sm'>
        <h2 class='text-xl font-semibold text-gray-700'>Ingredient Breakdown</h2>
        <p class='text-gray-600 text-sm mb-4'>Categorized based on FDA additive database and common ingredient lists.</p>
        <div class='grid grid-cols-1 md:grid-cols-2 gap-4'>
            <div class='p-3 border rounded-lg category-fda-non-common'>
                <strong>{CATEGORY_DISPLAY_NAMES['fda_non_common']}:</strong> {len(parsed_fda_non_common)}
            </div>
            <div class='p-3 border rounded-lg category-common-only'>
                <strong>{CATEGORY_DISPLAY_NAMES['common_only']}:</strong> {len(parsed_common_only)}
            </div>
            <div class='p-3 border rounded-lg category-fda-common'>
                <strong>{CATEGORY_DISPLAY_NAMES['common_fda_regulated']}:</strong> {len(parsed_fda_common)}
            </div>
            <div class='p-3 border rounded-lg category-truly-unidentified'>
                <strong>{CATEGORY_DISPLAY_NAMES['truly_unidentified']}:</strong> {len(truly_unidentified)}
            </div>
        </div>
        <ul class='mt-4 space-y-2'>
""")
    # --- END Step 2 ---

    # --- Step 3: Detailed Ingredient Breakdown - Individual Ingredients (Sorted and Colored) ---
    # Sort parsed_ingredients based on defined priority
    sorted_parsed_ingredients = sorted(
        parsed_ingredients,
        key=lambda x: CATEGORY_SORT_PRIORITY.get(x.get('trust_report_category', 'truly_unidentified'), 99)
    )

    parsed_ingredients_html = ""
    for item in sorted_parsed_ingredients: # <--- Loop now uses the sorted list
        original_str = html.escape(item.get('original_string', 'N/A'))
        base_ing = html.escape(item.get('base_ingredient', 'N/A'))
        category_key = item.get('trust_report_category', 'truly_unidentified')

        # Get the CSS class name (e.g., 'category-fda-non-common')
        css_class = f"category-{category_key.replace('_', '-')}"
        
        # Get the user-friendly display name for the category
        display_category_name = CATEGORY_DISPLAY_NAMES.get(category_key, category_key.replace('_', ' ').title())

        # Build modifiers string
        modifiers_html = ""
        modifiers = item.get('modifiers')
        if modifiers:
            modifiers_html = f"<div><strong>Modifiers:</strong> {html.escape(', '.join(modifiers))}</div>"

        # Build parenthetical info string
        parenthetical_html = ""
        parenthetical_info = item.get('parenthetical_info')
        if parenthetical_info:
            for key, value in parenthetical_info.items():
                if value:
                    parenthetical_html += f"<div><strong>{html.escape(key.replace('_', ' ').title())}:</strong> {html.escape(value)}</div>"

        # Build unusual punctuation string
        punctuation_html = ""
        punctuation = item.get('unusual_punctuation_found')
        if punctuation:
            punctuation_html = f"<div><strong>Unusual Punctuation:</strong> {html.escape(', '.join(punctuation))}</div>"

        parsed_ingredients_html += f"""
                <li class='border rounded-lg p-3 shadow-sm bg-white {css_class}'>
                    <div class='flex items-center justify-between cursor-pointer' onclick='toggleCollapse(this)'>
                        <span class='font-medium text-base'>
                            {original_str}
                        </span>
                        <span class='text-xl font-bold'>+</span>
                    </div>
                    <div class='mt-2 hidden text-sm text-gray-700 space-y-1'>
                        <div><strong>Category:</strong> {display_category_name}</div>
                        <div><strong>Base Ingredient:</strong> {base_ing}</div>
                        {modifiers_html}
                        {parenthetical_html}
                        {punctuation_html}
                    </div>
                </li>
        """
    html_content.append(parsed_ingredients_html)
    # --- END Step 3 ---

    # Closing tags for the main ingredient breakdown section
    html_content.append(f"""
        </ul>
    </div>
    """)

    html_content.append(f"""
    </div> <script>
        function toggleCollapse(element) {{
            const content = element.nextElementSibling;
            if (content.classList.contains('hidden')) {{
                content.classList.remove('hidden');
                element.querySelector('span:last-child').textContent = '-';
            }} else {{
                content.classList.add('hidden');
                element.querySelector('span:last-child').textContent = '+';
            }}
        }}
    </script>

</body>
</html>
""")

    return "".join(html_content)