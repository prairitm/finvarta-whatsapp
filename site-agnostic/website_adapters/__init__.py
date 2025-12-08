"""
Website Adapters

Website-specific adapters that fetch and normalize announcement data from different sources.
Each adapter returns a standardized data structure for processing by other tools.
"""

from .screener_adapter import fetch_screener_announcements
from .nse_adapter import fetch_nse_announcements
from .bse_adapter import fetch_bse_announcements

__all__ = [
    'fetch_screener_announcements',
    'fetch_nse_announcements',
    'fetch_bse_announcements',
]

