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

from html import escape as _html_escape

FOOTER_COPY = "Built from sources like FDA/USDA. We’re improving every day. The more you use it, the better we get!"

def _render_segments(segments):
    """Original Ingredients highlighting (exact-match spans from backend)."""
    out = []
    for seg in segments or []:
        txt = _html_escape(seg.get("text", ""))
        cls = seg.get("class", "none")
        if cls == "fda_additive":
            out.append(f'<span data-class="fda_additive" class="px-1 rounded bg-amber-100">{txt}</span>')
        elif cls == "classified_ingredient":
            out.append(f'<span data-class="classified_ingredient" class="px-1 rounded bg-green-100">{txt}</span>')
        elif cls == "unclassified":
            out.append(f'<span data-class="unclassified" class="px-1 rounded bg-blue-100">{txt}</span>')
        else:
            out.append(txt)
    return "".join(out)

def _render_list(items, data_class):
    """Generic list renderer for FDA / Classified / Unclassified buckets."""
    lis = []
    for it in items or []:
        name = _html_escape(it["display"] if isinstance(it, dict) else str(it))
        if data_class == "fda_additive":
            details = (
                '<div class="mt-2 text-sm text-gray-600 hidden" data-panel="details">'
                '<div><span class="font-semibold">Used For:</span> (Coming Soon)</div>'
                '<div><span class="font-semibold">Other Names:</span> (Coming Soon)</div>'
                '<div class="italic text-gray-500">Risk Factors: (Coming Soon)</div>'
                "</div>"
            )
            toggle = (
                '<button class="sgl-toggle text-sm underline" data-expand="details" aria-expanded="false">Details</button>'
            )
            row = (
                f'<li class="py-3" data-class="{data_class}">'
                f'<div class="flex items-start justify-between">'
                f'<span class="font-medium">{name}</span>'
                f'{toggle}'
                f'</div>{details}</li>'
            )
        else:
            row = f'<li class="py-3" data-class="{data_class}"><span class="font-medium">{name}</span></li>'
        lis.append(row)
    return "\n".join(lis)

def generate_trust_report_html(product_name, classification):
    """
    NEW signature:
      product_name: str
      classification: dict with keys:
        - fda_additives, classified_ingredients, unclassified (lists of {"display","token"})
        - counts {fda_additive, classified_ingredient, unclassified}
        - data_score {matched,total,percent}
        - original_ingredients {segments:[{text,class}], source:"list|text"}
        - nova_group (optional, OFF only)
    """
    counts = classification.get("counts", {})
    nova = classification.get("nova_group")
    fda = classification.get("fda_additives", [])
    cls = classification.get("classified_ingredients", [])
    unc = classification.get("unclassified", [])
    segs = (classification.get("original_ingredients") or {}).get("segments", [])
    data_score = classification.get("data_score")

    tabs = f"""
    <div class="flex gap-2 mb-4" role="tablist" aria-label="Ingredient buckets">
      <button class="sgl-tab px-3 py-1 rounded-full bg-amber-50" data-tab="fda"><span>FDA Additives</span><span class="ml-2 rounded-full bg-amber-100 px-2 text-xs">{counts.get('fda_additive',0)}</span></button>
      <button class="sgl-tab px-3 py-1 rounded-full bg-green-50" data-tab="classified"><span>Ingredients</span><span class="ml-2 rounded-full bg-green-100 px-2 text-xs">{counts.get('classified_ingredient',0)}</span></button>
      <button class="sgl-tab px-3 py-1 rounded-full bg-blue-50" data-tab="unclassified"><span>Unclassified</span><span class="ml-2 rounded-full bg-blue-100 px-2 text-xs">{counts.get('unclassified',0)}</span></button>
    </div>
    """

    nova_badge = (
        f'<span class="ml-2 inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs">NOVA {nova}</span>'
        if nova else ""
    )

    html = f"""
<section id="sgl-report" class="max-w-3xl mx-auto bg-white shadow-xl rounded-2xl p-6 md:p-8">
  <header class="mb-6">
    <h1 class="text-2xl font-bold">Trust Report</h1>
    <div class="mt-1 text-sm text-gray-600">Product: <span class="font-medium">{_html_escape(product_name or 'Unknown')}</span>{nova_badge}</div>
  </header>

  <section id="sgl-original" class="mb-6">
    <h2 class="text-lg font-semibold mb-2">Original Ingredients (from label)</h2>
    <p class="text-sm leading-7 bg-gray-50 p-3 rounded-lg border border-gray-100">{_render_segments(segs)}</p>
  </section>

  {tabs}

  <section id="sgl-fda-additives" data-panel="tab-fda" class="mb-8">
    <h2 class="text-lg font-semibold mb-3">FDA Additives</h2>
    <ul class="divide-y divide-gray-100">{_render_list(fda, "fda_additive")}</ul>
  </section>

  <section id="sgl-classified" data-panel="tab-classified" class="mb-8 hidden">
    <h2 class="text-lg font-semibold mb-3">Ingredients (Classified)</h2>
    <ul class="divide-y divide-gray-100">{_render_list(cls, "classified_ingredient")}</ul>
  </section>

  <section id="sgl-unclassified" data-panel="tab-unclassified" class="mb-8 hidden">
    <div class="flex items-center justify-between">
      <h2 class="text-lg font-semibold mb-3">Ingredients (Unclassified)</h2>
      {f"<div class='text-sm text-gray-500'>Matched {data_score.get('matched',0)}/{data_score.get('total',0)} ({data_score.get('percent',0)}%)</div>" if data_score else ""}
    </div>
    <ul class="divide-y divide-gray-100">{_render_list(unc, "unclassified")}</ul>
  </section>

  <section id="sgl-flags-coming-soon" class="opacity-70">
    <h2 class="text-lg font-semibold">Your Flags — Coming Soon</h2>
  </section>

  <footer class="mt-8 text-sm text-gray-500">{_html_escape(FOOTER_COPY)}</footer>
</section>
"""
    return html
# --- /NEW RENDERER ---
