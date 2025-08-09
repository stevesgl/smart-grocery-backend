# usda_product_lookup_v3.py
# ## 3. `usda_product_lookup_v3.py` – **USDA Fallback Product Data Source (GTIN-first)**
# - **Purpose:** Queries the **USDA FoodData Central API** when OFF does not have the product, or when the service
#   explicitly forces USDA (e.g., debug/verification).
# - **Behavior (v3, locked):**
#   - **No local map**: We no longer depend on `gtin_map.json`.
#   - **Exact-match GTIN** via `gtinUpc` first, then a narrow **search** fallback by the same GTIN string.
#   - **Deterministic**: No fuzzy logic; returns the first USDA record found for that GTIN, normalized to our MVP contract.
# - **Inputs:** GTIN (as string)
# - **Outputs:** Dict with normalized fields expected by `trust_report_service_v3.py`:
#     {
#       "product_name": str,
#       "brand_name": str,
#       "brand_owner": str | None,
#       "ingredients_text": str,
#       "nova_score": None,            # USDA does not provide NOVA; we keep shape stable
#       "ingredients_list": []         # OFF-only concept; left as empty list for consistency
#     }
# - **Workflow Role:** **Backup Data Fetcher** – used by `trust_report_service_v3.py`
#     1) OFF-first (handled elsewhere)
#     2) If OFF misses (or `force_usda=True`): call `fetch_product_from_usda(gtin)`
#     3) Return normalized payload to classifier → renderer.
#
# 🚧 Security:
# - Reads `USDA_API_KEY` from environment (NEVER hardcode). Works locally and on Render.
#
# 🔗 Endpoints used (official FDC API):
# - Direct GTIN:   GET https://api.nal.usda.gov/fdc/v1/foods?gtinUpc=<GTIN>&api_key=...
# - Search (alt):  GET https://api.nal.usda.gov/fdc/v1/foods/search?query=<GTIN>&pageSize=5&api_key=...
#
# ✅ Why this design for MVP v3:
# - Removes hidden failure modes from stale/partial local maps.
# - Keeps behavior simple, explainable, and aligned with trust-first, exact-match principles.
# - If we ever need caching or offline resilience, we’ll add it in **MVP+1** without changing this contract.

from __future__ import annotations

import os
import requests
from typing import Any, Dict, Optional

API_BASE = "https://api.nal.usda.gov/fdc/v1"
API_TIMEOUT_S = 12  # conservative timeout for single-GTIN MVP flow

# Flip on to see simple request traces while debugging locally:
SGL_DEBUG = os.getenv("SGL_DEBUG", "").lower() in ("1", "true", "yes", "on")


# === Custom Exception =========================================================
class USDAProductNotFound(Exception):
    """Raised when no USDA product is found (or when configuration is invalid)."""
    pass


# === Helpers =================================================================
def _auth_params(extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build query params including API key."""
    api_key = os.getenv("USDA_API_KEY", "")
    if not api_key:
        # We raise here so the caller returns a clean 4xx/5xx as appropriate.
        raise USDAProductNotFound("USDA_API_KEY missing")
    params: Dict[str, Any] = {"api_key": api_key}
    if extra:
        params.update(extra)
    return params


def _normalize_usda(usda_obj: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize USDA payloads (from either /foods?gtinUpc or /foods/search) into the
    minimal contract the rest of v3 expects. We do not invent data; we map fields.
    """
    product_name = (
        usda_obj.get("description")
        or usda_obj.get("brandName")
        or ""
    )

    brand_owner = usda_obj.get("brandOwner")
    brand_name = brand_owner or usda_obj.get("brandName") or ""

    ingredients = (
        usda_obj.get("ingredients")
        or usda_obj.get("ingredientsText")
        or ""
    )

    return {
        "product_name": product_name,
        "brand_name": brand_name,
        "brand_owner": brand_owner,
        "ingredients_text": ingredients.strip(),
        "nova_score": None,      # Not provided by USDA; keep stable shape for renderer.
        "ingredients_list": []   # OFF-only concept; preserve contract for caller.
    }


def _get(url: str, params: Dict[str, Any]) -> requests.Response:
    if SGL_DEBUG:
        print(f"[SGL][USDA] GET {url} params={params}")
    return requests.get(url, params=params, timeout=API_TIMEOUT_S)


# === Main Function ============================================================
def fetch_product_from_usda(gtin: str) -> Dict[str, Any]:
    """
    Fetch product details from USDA by **GTIN** (exact) with a search fallback.

    Order:
      1) Direct GTIN endpoint: /foods?gtinUpc=<GTIN>
      2) Search fallback:      /foods/search?query=<GTIN>&pageSize=5
    """
    gtin = (gtin or "").strip()
    if not gtin:
        raise USDAProductNotFound("Empty GTIN")

    # --- 1) Direct GTIN endpoint (canonical) ---
    try:
        r = _get(f"{API_BASE}/foods", _auth_params({"gtinUpc": gtin}))
    except USDAProductNotFound:
        # Bubble up cleanly (missing API key)
        raise
    except Exception as e:
        # Network/transport issues
        if SGL_DEBUG:
            print(f"[SGL][USDA] ERROR direct gtinUpc: {e}")
        r = None

    if r is not None and r.status_code == 200:
        try:
            data = r.json() or []
        except Exception:
            data = []
        if isinstance(data, list) and data:
            return _normalize_usda(data[0])

    # --- 2) Search fallback (still GTIN string; choose exact match if present) ---
    try:
        r2 = _get(
            f"{API_BASE}/foods/search",
            _auth_params({"query": gtin, "pageSize": 5})
        )
    except USDAProductNotFound:
        raise
    except Exception as e:
        if SGL_DEBUG:
            print(f"[SGL][USDA] ERROR search fallback: {e}")
        r2 = None

    if r2 is not None and r2.status_code == 200:
        try:
            j = r2.json() or {}
        except Exception:
            j = {}
        foods = j.get("foods") or []
        # prefer exact gtinUpc match if available
        for f in foods:
            if str(f.get("gtinUpc") or "") == gtin:
                return _normalize_usda(f)
        # else take first result if present (still deterministic within page)
        if foods:
            return _normalize_usda(foods[0])

    # --- No match found ---
    raise USDAProductNotFound(f"No USDA match for {gtin}")
