"""
Base Adapter Interface

This module documents the expected interface for website-specific adapters.
All adapters should follow this structure to ensure compatibility with the
HTML extraction and processing tools.
"""

from typing import List, Dict, Optional


def fetch_announcements(config: Optional[Dict] = None) -> List[Dict]:
    """
    Base interface for fetching announcements from a website.
    
    This is a template function showing the expected interface. Each website-specific
    adapter should implement a similar function that returns a standardized format.
    
    Args:
        config: Optional configuration dictionary. May include:
            - url: Website URL to fetch from
            - headers: HTTP headers for requests
            - cookies: Cookie header string or dict
            - timeout: Request timeout in seconds
            - Other website-specific settings
    
    Returns:
        List of announcement dictionaries, each containing:
            {
                "company_name": str,          # Name of the company
                "company_url": str,            # Full URL or relative path to company page
                "pdf_url": str,                # Full URL to the PDF document
                "announcement_date": str,      # ISO format date or timestamp
                "announcement_title": str,     # Optional title/description
                "source": str                  # Website identifier (e.g., "screener")
            }
        
        The list should be ordered with the latest announcement first.
        Returns empty list if no announcements found.
    
    Raises:
        May raise exceptions for network errors, parsing errors, etc.
        Callers should handle exceptions appropriately.
    
    Example:
        >>> config = {
        ...     "url": "https://example.com/announcements",
        ...     "timeout": 20
        ... }
        >>> announcements = fetch_announcements(config)
        >>> if announcements:
        ...     latest = announcements[0]
        ...     print(f"Latest: {latest['company_name']} - {latest['pdf_url']}")
    """
    # This is a template - actual adapters should implement this
    raise NotImplementedError("This is a base interface. Use a specific adapter implementation.")


# Standardized announcement structure
ANNOUNCEMENT_SCHEMA = {
    "company_name": str,          # Required: Name of the company
    "company_url": str,           # Required: Full URL or relative path
    "pdf_url": str,               # Required: Full PDF URL
    "announcement_date": str,     # Required: ISO format or timestamp
    "announcement_title": str,    # Optional: Title/description
    "source": str                 # Required: Website identifier
}


def validate_announcement(announcement: Dict) -> bool:
    """Validate that an announcement dict matches the expected schema."""
    required_keys = ["company_name", "company_url", "pdf_url", "announcement_date", "source"]
    
    for key in required_keys:
        if key not in announcement:
            return False
        if not isinstance(announcement[key], str):
            return False
    
    return True


def normalize_announcement(announcement: Dict, source: str) -> Dict:
    """
    Normalize an announcement dict to ensure it has all required fields.
    
    Args:
        announcement: Raw announcement dictionary
        source: Source website identifier
    
    Returns:
        Normalized announcement dictionary with all required fields
    """
    normalized = {
        "company_name": announcement.get("company_name", "Unknown Company"),
        "company_url": announcement.get("company_url", ""),
        "pdf_url": announcement.get("pdf_url", ""),
        "announcement_date": announcement.get("announcement_date", ""),
        "announcement_title": announcement.get("announcement_title", ""),
        "source": source
    }
    
    return normalized

