# report_generator.py
import html

def generate_trust_report_html(fda_additives):
    """
    Generate the HTML block for FDA additives with collapsible details.
    Each additive shows name, and on expand: used_for, other_names, risk_factors (placeholder).

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

    # Footer
    output.append("""
        <p class='text-xs text-gray-400 mt-4'>
        Built from sources like FDA/USDA. We’re improving every day. The more you use, the better we get!
        </p>
    """)
    output.append("</div>")

    return "\n".join(output)


# Include JS needed for collapsibles (to be included in index.html or inline)
COLLAPSIBLE_JS = """
<script>
  function toggleCollapse(el) {
    const content = el.nextElementSibling;
    if (content.classList.contains('hidden')) {
      content.classList.remove('hidden');
    } else {
      content.classList.add('hidden');
    }
  }
</script>
"""
