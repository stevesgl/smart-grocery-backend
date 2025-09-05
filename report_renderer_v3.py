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
import re, unicodedata

FOOTER_COPY = "Built from sources like FDA/USDA. We’re improving every day. The more you use it, the better we get!"

def _render_segments(segments):
    """Original Ingredients highlighting (exact-match spans from backend)."""
    out = []
    for seg in segments or []:
        txt = _html_escape(seg.get("text", ""))
        cls = seg.get("class", "none")
        if cls == "fda_additive":
            out.append(f'<span data-class="fda_additive" class="px-1.5 py-0.5 rounded bg-amber-100">{txt}</span>')
        elif cls == "classified_ingredient":
            out.append(f'<span data-class="classified_ingredient" class="px-1.5 py-0.5 rounded bg-green-100">{txt}</span>')
        elif cls == "unclassified":
            out.append(f'<span data-class="unclassified" class="px-1.5 py-0.5 rounded bg-blue-100">{txt}</span>')
        else:
            out.append(txt)
    return "".join(out)

# --- Add these helper functions **before** generate_trust_report_html ---
def _slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii","ignore").decode("ascii")
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    return s

def _ul(items):
    return "<ul>" + "".join(f"<li>{_html_escape(str(x))}</li>" for x in items) + "</ul>"

def _render_additive_row(name: str, enrichment: dict, norm_map: dict, slug: str | None = None) -> str:
    safe = _html_escape(name or "")
    e = {}
    if slug and slug in enrichment:
        e = enrichment[slug]
    else:
        e = enrichment.get(name) or enrichment.get((name or "").strip()) or norm_map.get((name or "").strip().lower()) or {}
    slug = slug or e.get("slug") or _slugify(name or "")
    other = e.get("other_names") or [name]
    used  = e.get("used_for") or []
    used_html = _ul(used) if used else '<p class="text-sm text-gray-500">No additional details yet.</p>'
    return (
      "<li class='py-3 px-4 bg-white rounded-xl border border-amber-200'>"
      "  <div class='flex items-center justify-between'>"
      f"    <span class='font-medium'>{safe}</span>"
      f"    <button type='button' class='sgl-expand text-lg leading-none select-none' "
      f"            data-additive-toggle aria-expanded='false' aria-controls='add-{slug}-panel'>+</button>"
      "  </div>"
      f"  <div id='add-{slug}-panel' class='additive-panel mt-2 pl-6' hidden>"
      "    <div class='other-names mb-2'>"
      "      <h4 class='text-sm font-semibold'>Other names</h4>"
      f"      {_ul(other)}"
      "    </div>"
      "    <div class='used-for'>"
      "      <h4 class='text-sm font-semibold'>Used for</h4>"
      f"      {used_html}"
      "    </div>"
      "  </div>"
      "</li>"
    )

def generate_trust_report_html(product_name, classification, brand=None, gtin=None, *, additive_enrichment=None):
    additive_enrichment = additive_enrichment or {}
    counts = classification.get("counts", {}) or {}
    nova = classification.get("nova_group")
    fda = classification.get("fda_additives", []) or []
    cls = classification.get("classified_ingredients", []) or []
    unc = classification.get("unclassified", []) or []
    segs = (classification.get("original_ingredients") or {}).get("segments", []) or []
    data_score = classification.get("data_score") or {"matched":0,"total":0,"percent":0}
    brand_display = _html_escape(brand) if brand else "—"
    gtin_display  = _html_escape(gtin) if gtin else "—"

    # build once per render: a case-insensitive fallback
    norm_map = { (k or "").strip().lower(): v for k, v in (additive_enrichment or {}).items() }

    # NOVA dots (fill up to nova 1..4)
    def _nova_badge(n):
        if not n:
            return ""
        dots = []
        for i in range(1, 5):
            filled = i <= n
            dots.append(
                f'<span class="inline-block w-2.5 h-2.5 rounded-full mx-0.5 {("bg-amber-400" if filled else "bg-gray-300")}"></span>'
            )

        # Standard NOVA category labels
        nova_labels = {
            1: "Unprocessed or minimally processed foods",
            2: "Processed culinary ingredients",
            3: "Processed foods",
            4: "Ultra-processed foods"
        }

        return (
            '<div class="text-right">'
            '<div class="text-sm font-semibold">NOVA Score</div>'
            f'<div class="mt-1">{"".join(dots)}</div>'
            f'<div class="text-xs text-gray-500 mt-1">{n} • {nova_labels.get(n, "Unknown")}</div>'
            "</div>"
        )

    # List card rows for the three buckets
    def _render_list(items, data_class):
        lis = []
        for it in items:
            name = _html_escape((it.get("display") if isinstance(it, dict) else str(it)) or "")
            if data_class == "fda_additive":
                # Use raw display string for enrichment lookup (with tolerant fallback)
                raw_name = (it.get("display") if isinstance(it, dict) else str(it)) or ""
                lis.append(_render_additive_row(raw_name, additive_enrichment, norm_map, it.get("slug")))

            else:
                border_cls = "border-green-200" if data_class == "classified_ingredient" else "border-blue-200"
                lis.append(
                    f"<li class='py-3 px-4 bg-white rounded-xl border {border_cls}'><span class='font-medium'>{name}</span></li>"
                )

        return "\n".join(lis)


    # Tabs header (counts)
    tabs = f"""
    <div class="flex gap-3 mb-4" role="tablist" aria-label="Ingredient buckets">
      <button class="sgl-tab active flex items-center gap-2 px-3 py-1.5 rounded-xl border border-amber-200 bg-amber-50" data-tab="fda">
        <span class="inline-block w-2.5 h-2.5 rounded-full bg-amber-500"></span>
        <span>FDA Additives</span>
        <span class="ml-1 rounded-full bg-amber-100 px-1.5 text-xs">{counts.get('fda_additive',0)}</span>
      </button>
      <button class="sgl-tab flex items-center gap-2 px-3 py-1.5 rounded-xl border border-green-200 bg-green-50" data-tab="classified">
        <span class="inline-block w-2.5 h-2.5 rounded-full bg-green-500"></span>
        <span>Ingredients (Classified)</span>
        <span class="ml-1 rounded-full bg-green-100 px-1.5 text-xs">{counts.get('classified_ingredient',0)}</span>
      </button>
      <button class="sgl-tab flex items-center gap-2 px-3 py-1.5 rounded-xl border border-blue-200 bg-blue-50" data-tab="unclassified">
        <span class="inline-block w-2.5 h-2.5 rounded-full bg-blue-500"></span>
        <span>Unclassified</span>
        <span class="ml-1 rounded-full bg-blue-100 px-1.5 text-xs">{counts.get('unclassified',0)}</span>
      </button>
    </div>
    """

    header_rows = f"""
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
        <div><span class="text-gray-500">Product</span><div class="font-medium">{_html_escape(product_name or "Unknown")}</div></div>
        <div><span class="text-gray-500">Brand</span><div class="font-medium">{brand_display}</div></div>
        <div><span class="text-gray-500">Barcode Number</span><div class="font-medium">{gtin_display}</div></div>
        <div class="hidden md:block">{_nova_badge(nova)}</div>
      </div>
    """


    html = f"""
<section id="sgl-report" class="max-w-5xl mx-auto bg-white shadow-xl rounded-2xl p-6 md:p-8">
  <header class="mb-5">
    <h1 class="text-3xl font-bold">Trust Report</h1>
    <div class="text-sm text-gray-600 mt-1">Built from sources like FDA and USDA. No fear. Just facts.</div>
    <div class="mt-4">{header_rows}</div>
  </header>

  <!-- Trust Report Intro Banner -->
  <section id="sgl-intro" class="rounded-2xl border bg-white shadow-sm p-4 mb-4">
    <!-- LOCKED COPY — DO NOT EDIT -->
    <button
      id="sgl-intro-toggle"
      type="button"
      class="w-full inline-flex items-start justify-between gap-3 text-left"
      aria-expanded="false"
      aria-controls="sgl-intro-panel"
    >
      <span class="font-semibold">The open secret:</span>
      <span id="sgl-intro-caret" class="shrink-0 select-none" aria-hidden="true">▶</span>
    </button>

    <!-- Collapsed one-liner (shown when aria-expanded=false) -->
    <p id="sgl-intro-collapsed" class="mt-2 text-sm">
      The open secret: Every food transparency app runs on crowdsourcing or AI guesses. That’s not good enough for your family.
    </p>

    <!-- Expanded panel (hidden by default) -->
    <div id="sgl-intro-panel" class="mt-3 hidden whitespace-pre-line text-sm">
      <!-- LOCKED COPY — DO NOT EDIT -->
      The open secret: Every food transparency app runs on crowdsourced data or AI guesses. Risky errors and bad data aren’t good enough for your family.

      <span class="font-semibold block mt-3">We started the same. But found a better way.</span>

      <span class="font-semibold block mt-3">Our promise:</span> FDA/USDA-verified pipeline. Slower, harder, but the only path to truth.

      <span class="font-semibold block mt-3">Want to help?</span> Just scan. No typing. No guessing. Every scan tells us what matters most.
    </div>
  </section>

  <section id="sgl-original" class="mb-6">

    <div class="flex items-center justify-between">
      <h2 class="text-base font-semibold">Original Ingredients (from label)</h2>
      <button type="button" class="text-sm text-gray-600 underline sgl-copy" data-copy-target="#sgl-original-text">Copy</button>
    </div>
    <p id="sgl-original-text" class="text-[15px] leading-7 bg-gray-50 p-4 rounded-xl border border-gray-200">
      {_render_segments(segs)}
    </p>
  </section>

  {tabs}

  <!-- Panels -->
  <section id="panel-fda" class="mb-8 rounded-2xl border border-amber-200 bg-amber-50 p-5">
    <h3 class="text-lg font-semibold mb-2">FDA Additives</h3>
    <p class="text-sm text-amber-900 mb-4">Click an item for more details. Names link to sources.</p>
    <ul class="space-y-3">{_render_list(fda, "fda_additive")}</ul>
  </section>

  <section id="panel-classified" class="mb-8 rounded-2xl border border-green-200 bg-green-50 p-5 hidden">
    <h3 class="text-lg font-semibold mb-2">Ingredients (Classified)</h3>
    <p class="text-sm text-green-900 mb-4">These ingredients are classified and verified against trusted food databases.</p>
    <ul class="grid md:grid-cols-2 gap-3">{_render_list(cls, "classified_ingredient")}</ul>
  </section>

  <section id="panel-unclassified" class="mb-2 rounded-2xl border border-blue-200 bg-blue-50 p-5 hidden">
    <div class="flex items-center justify-between">
      <h3 class="text-lg font-semibold">Unclassified</h3>
      <div class="text-sm text-gray-600">Data Score<br><span class="font-medium">{data_score.get('percent',0)}%</span> matched</div>
    </div>
    <p class="text-sm text-blue-900 mb-4">We don’t use AI to guess like others. Exact matches only. Thanks to your scan these items are on our radar for review.</p>
    <ul class="grid md:grid-cols-2 gap-3">{_render_list(unc, "unclassified")}</ul>
  </section>

  <footer class="mt-6 bg-slate-900 text-slate-100 text-center text-sm rounded-xl px-4 py-3">
    {_html_escape(FOOTER_COPY)}
  </footer>
</section>
"""
    return html
