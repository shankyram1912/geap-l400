"""Tax assessment data retrieval tool for real estate investment opportunity analysis."""

import json
import os
from typing import Any, Dict, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAB_ROOT = os.path.dirname(PROJECT_ROOT)
TOOLS_DATA_DIR = (
    os.path.join(LAB_ROOT, "tools_data")
    if os.path.exists(os.path.join(LAB_ROOT, "tools_data"))
    else os.path.join(PROJECT_ROOT, "tools_data")
)
TAX_DB_PATH = os.path.join(TOOLS_DATA_DIR, "tax_database.json")

# Module-level memory cache for tax database
_TAX_DB_CACHE: Optional[Dict[str, Any]] = None


def _get_tax_db() -> Dict[str, Any]:
    """Loads and caches the tax assessments database JSON in memory."""
    global _TAX_DB_CACHE
    if _TAX_DB_CACHE is None:
        if not os.path.exists(TAX_DB_PATH):
            raise FileNotFoundError(f"Tax database not found at {TAX_DB_PATH}")
        with open(TAX_DB_PATH, "r", encoding="utf-8") as f:
            _TAX_DB_CACHE = json.load(f)
    return _TAX_DB_CACHE


def get_tax_assessment_data(parcel_apn: str) -> str:
    """Retrieves official county tax assessment records for a parcel by its APN.

    Args:
        parcel_apn: The Assessor's Parcel Number (APN) (e.g., '049-382-011-000').

    Returns:
        A JSON string containing annual tax amount, assessed valuations, tax year,
        and payment status.
    """
    try:
        tax_db = _get_tax_db()
        apn_clean = parcel_apn.strip()
        if apn_clean in tax_db:
            return json.dumps(tax_db[apn_clean], indent=2)

        return f"No tax assessment record found for APN '{parcel_apn}'."
    except Exception as e:
        return f"[Error retrieving tax assessment for APN {parcel_apn}: {str(e)}]"
