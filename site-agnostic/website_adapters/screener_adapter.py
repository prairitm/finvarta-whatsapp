"""
Screener.in Adapter

Website-specific adapter for fetching announcements from screener.in.
"""

import re
import os
import sys
import requests
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
from datetime import datetime

try:
    from .base_adapter import validate_announcement, normalize_announcement
except ImportError:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    from website_adapters.base_adapter import validate_announcement, normalize_announcement


PDF_REGEX = re.compile(r"\.pdf(?:[#?].*)?$", re.IGNORECASE)


def parse_cookie_header(cookie_header: str) -> Dict[str, str]:
    """Convert raw cookie header string into dict for requests."""
    cookies = {}
    for part in cookie_header.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


def get_company_name_from_url(company_url: str) -> str:
    """Extract company name from screener.in company URL."""
    match = re.search(r'/company/([^/]+)/?', company_url)
    if match:
        return match.group(1)
    return "Unknown Company"


def fetch_screener_announcements(config: Optional[Dict] = None) -> List[Dict]:
    """Fetch announcements from screener.in and return standardized format."""
    default_config = {
        "url": "https://www.screener.in/announcements/user-filters/192898/",
        "timeout": 20,
    }
    if config:
        default_config.update(config)
    config = default_config
    
    url = config.get("url")
    timeout = config.get("timeout", 20)
    cookie_header = config.get("cookie_header")
    
    headers = config.get("headers", {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
        "priority": "u=0, i",
        "referer": "https://www.screener.in/announcements/user-filters/86082/",
        "sec-ch-ua": "\"Not;A=Brand\";v=\"99\", \"Google Chrome\";v=\"139\", \"Chromium\";v=\"139\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"macOS\"",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    })
    
    cookies = parse_cookie_header(cookie_header) if cookie_header else None
    
    try:
        with requests.Session() as s:
            resp = s.get(url, headers=headers, cookies=cookies, timeout=timeout, allow_redirects=True)
            resp.raise_for_status()
            html_content = resp.text
    except Exception:
        return []
    
    soup = BeautifulSoup(html_content, "lxml")
    all_links = soup.find_all("a")
    hrefs = [a.get("href").strip() for a in all_links if a.get("href")]
    
    if len(hrefs) == 0:
        return []
    
    found_pairs = []
    for i in range(len(hrefs) - 1):
        if "/company" in hrefs[i] and PDF_REGEX.search(hrefs[i + 1]):
            found_pairs.append((hrefs[i], hrefs[i + 1]))
    
    announcements = []
    for company_url, pdf_url in found_pairs:
        company_name = get_company_name_from_url(company_url)
        
        if company_url.startswith("http"):
            match = re.search(r'/company/[^/]+/?', company_url)
            if match:
                company_url = match.group(0)
        
        if pdf_url.startswith("/"):
            pdf_url = "https://www.screener.in" + pdf_url
        elif not pdf_url.startswith("http"):
            pdf_url = "https://www.screener.in/" + pdf_url
        
        announcement = {
            "company_name": company_name,
            "company_url": company_url,
            "pdf_url": pdf_url,
            "announcement_date": datetime.now().isoformat(),
            "announcement_title": "",
            "source": "screener"
        }
        
        if validate_announcement(announcement):
            announcements.append(announcement)
    
    return announcements

