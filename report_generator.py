import html

# --- RENAMED HELPER FUNCTION (Your original code, but with a new name) ---
def _generate_fda_additives_html_block(fda_additives):
    """
    Generate the HTML block for FDA additives with collapsible details.
    Each additive shows name, and on expand: used_for, other_names.
    This is a helper function for the main trust report.

    :param fda_additives: List of dicts, each with:
        - name
        - used_for (list)
        - other_names (list)
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

        # Collapsible container
        output.append("""
        <div class='border rounded-xl p-4 shadow-sm bg-white'>
            <div class='flex items-center justify-between cursor-pointer' onclick='toggleCollapse(this)'>
                <span class='font-medium text-base'>%s</span>
                <span class='text-xl font-bold'>+</span>
            </div>
            <div class='mt-2 hidden text-sm text-gray-700 space-y-2'>
        """ % name)

        # Used For badges
        if used_for:
            tags = " ".join([
                f"<span class='inline-block px-2 py-1 text-xs bg-green-100 text-green-800 rounded-full'>{html.escape(tag)}</span>"
                for tag in used_for
            ])
            output.append(f"<div><strong>Used for:</strong> {tags}</div>")

        # Other Names
        if other_names:
            others = ", ".join([html.escape(n) for n in other_names])
            output.append(f"<div><strong>Other Names:</strong> {others}</div>")

        # Risk Factors placeholder (MVP+1)
        output.append("<div><strong>Risk Factors:</strong> <em>Coming soon — EU bans, ADHD links, and more.</em></div>")

        # Close collapsible
        output.append("</div></div>")

    # Footer for this section
    output.append("""
        <p class='text-xs text-gray-400 mt-4'>
        Built from sources like FDA/USDA. We’re improving every day. The more you use, the better we get!
        </p>
    """)
    output.append("</div>")

    return "\n".join(output)


# --- NEW MAIN REPORT GENERATION FUNCTION ---
def generate_trust_report_html(
    product_name,
    brand_name,
    ingredients_raw,
    parsed_ingredients, # Full list of parsed ingredient dicts
    parsed_fda_common,
    parsed_fda_non_common,
    parsed_common_only,
    truly_unidentified,
    data_completeness_score,
    data_completeness_level,
    nova_score,
    nova_description,
    all_fda_parsed_for_report # This is the data for the FDA additives block
):
    """
    Generates the complete HTML for the Trust Report.
    This is the main function called by the service.
    """
    # Basic HTML structure (you can expand on this with more CSS/styling)
    html_output = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        "    <meta charset='UTF-8'>",
        "    <meta name='viewport' content='width=device-width, initial-scale=1.0'>",
        "    <title>Smart Grocery Lens Trust Report</title>",
        "    <script src='https://cdn.tailwindcss.com'></script>", # Basic Tailwind for quick styling
        "    <style>",
        "        .container { max-width: 800px; margin: 20px auto; padding: 20px; background-color: #f9f9f9; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }",
        "        .nova-score-4 { background-color: #fee2e2; color: #dc2626; }", # Example red background for Nova 4
        "        .nova-score-3 { background-color: #fef9c3; color: #ca8a04; }", # Example yellow background for Nova 3
        "        .nova-score-2 { background-color: #dbeafe; color: #2563eb; }", # Example blue background for Nova 2
        "        .nova-score-1 { background-color: #d1fae5; color: #047857; }", # Example green background for Nova 1
        "        .category-truly-unidentified { background-color: #fef2f2; color: #ef4444; border-color: #fca5a5; }",
        "        .category-fda-non-common { background-color: #fffbeb; color: #f59e0b; border-color: #fbbf24; }",
        "        .category-fda-common { background-color: #eff6ff; color: #3b82f6; border-color: #93c5fd; }",
        "        .category-common-only { background-color: #ecfdf5; color: #10b981; border-color: #6ee7b7; }",
        "    </style>",
        "</head>",
        "<body class='bg-gray-100 font-sans'>",
        "    <div class='container p-6 space-y-6'>",
        "        <h1 class='text-3xl font-bold text-center text-gray-800 mb-6'>Smart Grocery Lens Trust Report</h1>",

        # 1. Product Identification
        f"        <div class='bg-white p-4 rounded-lg shadow-sm'>",
        f"            <h2 class='text-2xl font-semibold text-gray-700'>{html.escape(product_name)}</h2>",
        f"            <p class='text-gray-600'><strong>Brand:</strong> {html.escape(brand_name) if brand_name else 'N/A'}</p>",
        f"        </div>",

        # 2. Key Insights / Overall Summary
        f"        <div class='bg-white p-4 rounded-lg shadow-sm border-l-4 border-indigo-500'>",
        f"            <h2 class='text-xl font-semibold text-gray-700'>Key Insights</h2>",
        f"            <p class='text-gray-800 text-lg'>This product is classified as a <strong class='nova-score-{nova_score} px-2 py-1 rounded'>{nova_description}</strong>.</p>",
        f"            <p class='text-gray-800 text-lg'>Data completeness: <strong class='text-indigo-600'>{data_completeness_score}% ({data_completeness_level})</strong> - Identified {len(parsed_ingredients) - len(truly_unidentified)} of {len(parsed_ingredients)} total components.</p>",
        "        </div>",

        # 3. Raw Ingredients
        f"        <div class='bg-white p-4 rounded-lg shadow-sm'>",
        f"            <h2 class='text-xl font-semibold text-gray-700 cursor-pointer' onclick='toggleCollapse(this)'>Raw Ingredients List <span class='text-xl font-bold'>+</span></h2>",
        f"            <div class='mt-2 hidden text-sm text-gray-700'>",
        f"                <p>{html.escape(ingredients_raw)}</p>",
        "            </div>",
        "        </div>",

        # 4. Detailed Ingredient Breakdown
        f"        <div class='bg-white p-4 rounded-lg shadow-sm'>",
        f"            <h2 class='text-xl font-semibold text-gray-700'>Ingredient Breakdown</h2>",
        f"            <p class='text-gray-600 text-sm mb-4'>Categorized based on FDA additive database and common ingredient lists.</p>",
        f"            <div class='grid grid-cols-1 md:grid-cols-2 gap-4'>",
        f"                <div class='p-3 border rounded-lg category-common-only'><strong>Common & Minimally Processed:</strong> {len(parsed_common_only)}</div>",
        f"                <div class='p-3 border rounded-lg category-fda-common'><strong>Common FDA-Regulated:</strong> {len(parsed_fda_common)}</div>",
        f"                <div class='p-3 border rounded-lg category-fda-non-common'><strong>FDA Substances (Non-Common):</strong> {len(parsed_fda_non_common)}</div>",
        f"                <div class='p-3 border rounded-lg category-truly-unidentified'><strong>Truly Unidentified:</strong> {len(truly_unidentified)}</div>",
        f"            </div>",
        f"            <ul class='mt-4 space-y-2'>",
        # List all parsed ingredients with their category
        *[f"""
                <li class='border rounded-lg p-3 shadow-sm bg-white category-{p['attributes'].get('trust_report_category', 'unknown').replace('_', '-')}'>
                    <div class='flex items-center justify-between cursor-pointer' onclick='toggleCollapse(this)'>
                        <span class='font-medium text-base'>
                            {html.escape(p['original_string'])}
                        </span>
                        <span class='text-xl font-bold'>+</span>
                    </div>
                    <div class='mt-2 hidden text-sm text-gray-700 space-y-1'>
                        <div><strong>Category:</strong> {p['attributes'].get('trust_report_category', 'Unknown').replace('_', ' ').title()}</div>
                        <div><strong>Base Ingredient:</strong> {html.escape(p['base_ingredient'])}</div>
                        {'<div><strong>Modifiers:</strong> ' + ', '.join([html.escape(m) for m in p['modifiers']]) + '</div>' if p['modifiers'] else ''}
                        {'<div><strong>Parenthetical Info:</strong> ' + html.escape(p['parenthetical_info'].get('content', '')) + '</div>' if p['parenthetical_info'] and p['parenthetical_info'].get('content') else ''}
                    </div>
                </li>
            """ for p in parsed_ingredients], # Loop through all parsed_ingredients to display them
        "            </ul>",
        "        </div>",

        # 5. FDA Additives (calls the renamed helper function)
        _generate_fda_additives_html_block(all_fda_parsed_for_report), # Call the helper function here

        "    </div>", # Close container
        "</body>",
        # Include JS needed for collapsibles (to be included in index.html or inline)
        COLLAPSIBLE_JS,
        "</html>"
    ]

    return "\n".join(html_output)


# Include JS needed for collapsibles (to be included in index.html or inline)
COLLAPSIBLE_JS = """
<script>
  function toggleCollapse(el) {
    const content = el.nextElementSibling;
    if (content.classList.contains('hidden')) {
      content.classList.remove('hidden');
      el.querySelector('span:last-child').textContent = '-'; // Change + to -
    } else {
      content.classList.add('hidden');
      el.querySelector('span:last-child').textContent = '+'; // Change - to +
    }
  }
</script>
"""