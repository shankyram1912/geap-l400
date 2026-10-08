"""Property lot data retrieval tool for real estate investment opportunity analysis."""

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
LOTS_DB_PATH = os.path.join(TOOLS_DATA_DIR, "lots_database.json")

# Module-level memory cache for lots database
_LOTS_DB_CACHE: Optional[Dict[str, Any]] = None


def _get_lots_db() -> Dict[str, Any]:
    """Loads and caches the lots database JSON in memory."""
    global _LOTS_DB_CACHE
    if _LOTS_DB_CACHE is None:
        if not os.path.exists(LOTS_DB_PATH):
            raise FileNotFoundError(f"Lots database not found at {LOTS_DB_PATH}")
        with open(LOTS_DB_PATH, "r", encoding="utf-8") as f:
            _LOTS_DB_CACHE = json.load(f)
    return _LOTS_DB_CACHE


def get_lot_data(plot_id: str) -> str:
    """Retrieves county property records and zoning data for a specified land parcel.

    Args:
        plot_id: The unique lot identifier to lookup (e.g., 'LOT-8472').

    Returns:
        A JSON string containing the property attributes including acreage, zoning,
        flood zone, topography, last sale price, and parcel_apn.
    """
    try:
        lots_db = _get_lots_db()
        plot_id_clean = plot_id.strip().upper()
        if plot_id_clean in lots_db:
            return json.dumps(lots_db[plot_id_clean], indent=2)
        
        # Fallback case-insensitive check
        for key, val in lots_db.items():
            if key.upper() == plot_id_clean:
                return json.dumps(val, indent=2)

        return f"No property record found for lot ID '{plot_id}'."
    except Exception as e:
        return f"[Error retrieving lot data for {plot_id}: {str(e)}]"
