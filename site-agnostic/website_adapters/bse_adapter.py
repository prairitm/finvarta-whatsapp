"""
BSE India Adapter

Website-specific adapter for fetching announcements from BSE India corporate announcements page.
Returns standardized announcement data structure.
"""

import re
import os
import sys
import requests
import json
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
from datetime import datetime

# Handle imports for both script execution and module import
try:
    from .base_adapter import validate_announcement, normalize_announcement
except ImportError:
    # If relative import fails, try absolute import (for script execution)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    from website_adapters.base_adapter import validate_announcement, normalize_announcement


PDF_REGEX = re.compile(r"\.pdf(?:[#?].*)?$", re.IGNORECASE)
DATE_REGEX = re.compile(r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})")
BSE_DATE_REGEX = re.compile(r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4})", re.IGNORECASE)
BSE_DATETIME_REGEX = re.compile(r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4})\s+(\d{1,2}:\d{2}(?::\d{2})?)", re.IGNORECASE)


def parse_bse_api_response(api_data) -> List[Dict]:
    """
    Parse BSE API JSON response and convert to standardized announcement format.
    
    Args:
        api_data: JSON response from BSE API (can be list or dict)
    
    Returns:
        List of announcement dictionaries in standardized format
    """
    announcements = []
    
    # Handle different possible API response structures
    data_list = []
    if isinstance(api_data, list):
        data_list = api_data
    elif isinstance(api_data, dict):
        # Try common keys that BSE might use
        for key in ['Table', 'Table1', 'data', 'announcements', 'results', 'items', 'records', 'CorpannData']:
            if key in api_data:
                value = api_data[key]
                if isinstance(value, list):
                    data_list = value
                    break
                elif isinstance(value, dict):
                    # Nested structure like {"CorpannData": {"Table": [...]}} or {"CorpannData": {"Table1": [...]}}
                    for nested_key in ['Table', 'Table1', 'data', 'announcements']:
                        if nested_key in value and isinstance(value[nested_key], list):
                            data_list = value[nested_key]
                            break
                    if data_list:
                        break
        
        # Also check for nested CorpannData structure directly
        if not data_list and 'CorpannData' in api_data:
            corpann_data = api_data['CorpannData']
            if isinstance(corpann_data, dict):
                for table_key in ['Table', 'Table1']:
                    if table_key in corpann_data and isinstance(corpann_data[table_key], list):
                        data_list = corpann_data[table_key]
                        break
        
        # AnnGetData API typically returns data in 'Table' field directly
        if not data_list and 'Table' in api_data and isinstance(api_data['Table'], list):
            data_list = api_data['Table']
        
        # Check if this dict looks like an announcement (has required fields)
        if not data_list and api_data:
            has_announcement_fields = any(key in api_data for key in [
                'SLONGNAME', 'SCRIP_CD', 'ATTACHMENTNAME', 'NEWS_DT', 'CATEGORYNAME', 'NEWSSUB',
                'company_name', 'scrip_code', 'attachment', 'date', 'category', 'NEWSDT'
            ])
            if has_announcement_fields:
                data_list = [api_data]
    
    for item in data_list:
        if not isinstance(item, dict):
            continue
        
        # Extract fields using BSE API field names
        # BSE API fields based on template: SLONGNAME, SCRIP_CD, ATTACHMENTNAME, NEWS_DT, CATEGORYNAME, NSURL
        company_name = (
            item.get('SLONGNAME') or 
            item.get('company_name') or 
            item.get('CompanyName') or 
            item.get('COMPANY') or 
            item.get('company') or
            "Unknown Company"
        )
        scrip_code = item.get('SCRIP_CD') or item.get('scrip_code') or item.get('ScripCode') or ""
        
        # PDF URL from ATTACHMENTNAME field
        attachment_name = item.get('ATTACHMENTNAME') or item.get('attachment') or item.get('AttachmentName') or ""
        pdf_url = ""
        if attachment_name:
            # BSE attachment paths: /xml-data/corpfiling/AttachLive/ or /xml-data/corpfiling/AttachHis/
            if attachment_name.startswith('/'):
                pdf_url = "https://www.bseindia.com" + attachment_name
            elif '/xml-data/corpfiling/' in attachment_name.lower():
                pdf_url = "https://www.bseindia.com" + (attachment_name if attachment_name.startswith('/') else '/' + attachment_name)
            else:
                pdf_url = f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{attachment_name}"
        
        # Also check for direct PDF URL fields
        if not pdf_url:
            pdf_url = (
                item.get('PDF_URL') or 
                item.get('pdf_url') or 
                item.get('attachmentUrl') or 
                item.get('ATTACHMENTURL') or
                ""
            )
        
        # Announcement date from NEWS_DT or NEWSDT (BSE format: "dd MMM yyyy" or "YYYYMMDD")
        announcement_date_str = (
            item.get('NEWS_DT') or 
            item.get('NEWSDT') or
            item.get('DissemDT') or
            item.get('date') or 
            item.get('announcement_date') or 
            item.get('AnnouncementDate') or
            item.get('NEWS_DATE') or
            ""
        )
        
        # Title/description from CATEGORYNAME or NEWSSUB
        announcement_title = (
            item.get('NEWSSUB') or
            item.get('CATEGORYNAME') or 
            item.get('category') or 
            item.get('subject') or 
            item.get('title') or 
            item.get('SUBJECT') or 
            item.get('TITLE') or
            item.get('announcement') or
            ""
        )
        
        # Company URL from NSURL or construct from scrip code
        company_url = item.get('NSURL') or item.get('company_url') or item.get('CompanyUrl') or ""
        if not company_url and scrip_code:
            # Construct BSE company URL if we have scrip code
            company_url = f"https://www.bseindia.com/stock-share-price/{scrip_code}/"
        
        # Parse date - BSE format is typically "dd MMM yyyy" (e.g., "15 Jan 2024") or "YYYYMMDD" (e.g., "20241215")
        announcement_date_obj = None
        if announcement_date_str:
            date_str_clean = str(announcement_date_str).strip()
            
            # Try YYYYMMDD format first (common in API responses)
            if len(date_str_clean) == 8 and date_str_clean.isdigit():
                try:
                    announcement_date_obj = datetime.strptime(date_str_clean, "%Y%m%d")
                except ValueError:
                    pass
            
            # Try BSE datetime format: "dd MMM yyyy HH:MM" or "dd MMM yyyy HH:MM:SS"
            if not announcement_date_obj:
                match = BSE_DATETIME_REGEX.search(date_str_clean)
                if match:
                    date_part = match.group(1)
                    time_part = match.group(2) if match.lastindex >= 2 else None
                    try:
                        announcement_date_obj = datetime.strptime(date_part, "%d %b %Y")
                        # Add time if present
                        if time_part:
                            time_parts = time_part.split(':')
                            if len(time_parts) >= 2:
                                announcement_date_obj = announcement_date_obj.replace(hour=int(time_parts[0]), minute=int(time_parts[1]))
                                if len(time_parts) >= 3:
                                    announcement_date_obj = announcement_date_obj.replace(second=int(time_parts[2]))
                    except ValueError:
                        try:
                            announcement_date_obj = datetime.strptime(date_part, "%d %B %Y")
                            if time_part:
                                time_parts = time_part.split(':')
                                if len(time_parts) >= 2:
                                    announcement_date_obj = announcement_date_obj.replace(hour=int(time_parts[0]), minute=int(time_parts[1]))
                                    if len(time_parts) >= 3:
                                        announcement_date_obj = announcement_date_obj.replace(second=int(time_parts[2]))
                        except ValueError:
                            pass
            
            # Try BSE format: "dd MMM yyyy" (without time)
            if not announcement_date_obj:
                match = BSE_DATE_REGEX.search(date_str_clean)
                if match:
                    date_part = match.group(1)
                    try:
                        announcement_date_obj = datetime.strptime(date_part, "%d %b %Y")
                        # Set to end of day if no time specified
                        announcement_date_obj = announcement_date_obj.replace(hour=23, minute=59, second=59)
                    except ValueError:
                        try:
                            announcement_date_obj = datetime.strptime(date_part, "%d %B %Y")
                            announcement_date_obj = announcement_date_obj.replace(hour=23, minute=59, second=59)
                        except ValueError:
                            pass
            
            # Try standard formats with time if BSE format didn't work
            if not announcement_date_obj:
                datetime_match = re.search(r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\s+(\d{1,2}:\d{2}(?::\d{2})?)", date_str_clean)
                if datetime_match:
                    date_part = datetime_match.group(1)
                    time_part = datetime_match.group(2)
                    for fmt in ["%d-%m-%Y", "%d/%m/%Y", "%d-%m-%y", "%d/%m/%y", "%Y-%m-%d", "%Y/%m/%d"]:
                        try:
                            announcement_date_obj = datetime.strptime(date_part, fmt)
                            time_parts = time_part.split(':')
                            if len(time_parts) >= 2:
                                announcement_date_obj = announcement_date_obj.replace(hour=int(time_parts[0]), minute=int(time_parts[1]))
                                if len(time_parts) >= 3:
                                    announcement_date_obj = announcement_date_obj.replace(second=int(time_parts[2]))
                            break
                        except ValueError:
                            continue
            
            # Try standard formats without time
            if not announcement_date_obj:
                match = DATE_REGEX.search(date_str_clean)
                if match:
                    date_part = match.group(1)
                    for fmt in ["%d-%m-%Y", "%d/%m/%Y", "%d-%m-%y", "%d/%m/%y", "%Y-%m-%d", "%Y/%m/%d"]:
                        try:
                            announcement_date_obj = datetime.strptime(date_part, fmt)
                            announcement_date_obj = announcement_date_obj.replace(hour=23, minute=59, second=59)
                            break
                        except ValueError:
                            continue
        
        if not announcement_date_obj:
            announcement_date_obj = datetime.now()
        
        # Make PDF URL absolute if relative
        if pdf_url and not pdf_url.startswith('http'):
            if pdf_url.startswith('/'):
                pdf_url = "https://www.bseindia.com" + pdf_url
            else:
                pdf_url = "https://www.bseindia.com/" + pdf_url
        
        announcement = {
            "company_name": company_name,
            "company_url": company_url if company_url.startswith('http') else f"https://www.bseindia.com{company_url}" if company_url.startswith('/') else "",
            "pdf_url": pdf_url,
            "announcement_date": announcement_date_obj.isoformat(),
            "announcement_title": announcement_title,
            "source": "bse"
        }
        
        if validate_announcement(announcement):
            announcements.append(announcement)
            # Display with time if available
            date_display = announcement_date_obj.strftime('%Y-%m-%d %H:%M:%S')
            print(f"  ✅ Found announcement (API): {company_name} - {date_display}")
    
    return announcements


def parse_date(date_str: str) -> str:
    """
    Parse date string from BSE format to ISO format with time.
    
    BSE uses formats like "dd MMM yyyy" (e.g., "15 Jan 2024")
    May also include time: "dd MMM yyyy HH:MM" or "dd MMM yyyy HH:MM:SS"
    
    Args:
        date_str: Date string in various formats, optionally with time
    
    Returns:
        ISO format datetime string (YYYY-MM-DDTHH:MM:SS) or current datetime if parsing fails
    """
    if not date_str:
        return datetime.now().isoformat()
    
    # Try BSE datetime format first: "dd MMM yyyy HH:MM" or "dd MMM yyyy HH:MM:SS"
    match = BSE_DATETIME_REGEX.search(date_str)
    if match:
        date_part = match.group(1)
        time_part = match.group(2) if match.lastindex >= 2 else None
        
        try:
            dt = datetime.strptime(date_part, "%d %b %Y")
            # Add time if present
            if time_part:
                time_parts = time_part.split(':')
                if len(time_parts) >= 2:
                    dt = dt.replace(hour=int(time_parts[0]), minute=int(time_parts[1]))
                    if len(time_parts) >= 3:
                        dt = dt.replace(second=int(time_parts[2]))
            return dt.isoformat()
        except ValueError:
            try:
                dt = datetime.strptime(date_part, "%d %B %Y")
                # Add time if present
                if time_part:
                    time_parts = time_part.split(':')
                    if len(time_parts) >= 2:
                        dt = dt.replace(hour=int(time_parts[0]), minute=int(time_parts[1]))
                        if len(time_parts) >= 3:
                            dt = dt.replace(second=int(time_parts[2]))
                return dt.isoformat()
            except ValueError:
                pass
    
    # Try BSE date format without time: "dd MMM yyyy"
    match = BSE_DATE_REGEX.search(date_str)
    if match:
        date_part = match.group(1)
        try:
            dt = datetime.strptime(date_part, "%d %b %Y")
            # Set to end of day if no time specified (to prioritize later announcements)
            dt = dt.replace(hour=23, minute=59, second=59)
            return dt.isoformat()
        except ValueError:
            try:
                dt = datetime.strptime(date_part, "%d %B %Y")
                dt = dt.replace(hour=23, minute=59, second=59)
                return dt.isoformat()
            except ValueError:
                pass
    
    # Try standard date formats with optional time
    # Pattern: "dd-mm-yyyy HH:MM" or "dd/mm/yyyy HH:MM:SS"
    datetime_match = re.search(r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\s+(\d{1,2}:\d{2}(?::\d{2})?)", date_str)
    if datetime_match:
        date_part = datetime_match.group(1)
        time_part = datetime_match.group(2)
        for fmt in ["%d-%m-%Y", "%d/%m/%Y", "%d-%m-%y", "%d/%m/%y", "%Y-%m-%d", "%Y/%m/%d"]:
            try:
                dt = datetime.strptime(date_part, fmt)
                time_parts = time_part.split(':')
                if len(time_parts) >= 2:
                    dt = dt.replace(hour=int(time_parts[0]), minute=int(time_parts[1]))
                    if len(time_parts) >= 3:
                        dt = dt.replace(second=int(time_parts[2]))
                return dt.isoformat()
            except ValueError:
                continue
    
    # Try standard date formats without time
    match = DATE_REGEX.search(date_str)
    if match:
        date_part = match.group(1)
        for fmt in ["%d-%m-%Y", "%d/%m/%Y", "%d-%m-%y", "%d/%m/%y", "%Y-%m-%d", "%d %m %Y"]:
            try:
                dt = datetime.strptime(date_part, fmt)
                dt = dt.replace(hour=23, minute=59, second=59)
                return dt.isoformat()
            except ValueError:
                continue
    
    return datetime.now().isoformat()


def extract_company_name(text: str, link_href: Optional[str] = None) -> str:
    """
    Extract company name from text or URL.
    
    Args:
        text: Text content that may contain company name
        link_href: Optional URL that may contain company symbol/name
    
    Returns:
        Company name or "Unknown Company" if not found
    """
    if not text:
        text = ""
    
    # Clean up text
    text = text.strip()
    
    # Remove common prefixes/suffixes
    text = re.sub(r'^(LTD|LIMITED|INC|CORP|CORPORATION)[\s.]*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'[\s.]+(LTD|LIMITED|INC|CORP|CORPORATION)$', '', text, flags=re.IGNORECASE)
    
    # If text looks like a company name (has capital letters, reasonable length)
    if len(text) > 2 and len(text) < 100:
        if text:
            return text.strip()
    
    # Try to extract from URL
    if link_href:
        # Look for company name in path
        path_match = re.search(r'/([^/]+)/?$', link_href)
        if path_match:
            return path_match.group(1).replace('-', ' ').title()
    
    return "Unknown Company"


def fetch_bse_announcements(config: Optional[Dict] = None) -> List[Dict]:
    """
    Fetch announcements from BSE India corporate announcements page and return standardized format.
    
    Args:
        config: Optional configuration dictionary with the following keys:
            - url: BSE announcements URL (default: https://www.bseindia.com/corporates/ann.html)
            - timeout: Request timeout in seconds (default: 30)
            - headers: Optional custom headers dict
            - cookies: Optional cookie header string or dict
    
    Returns:
        List of announcement dictionaries in standardized format, ordered with latest first.
        Each dict contains:
            {
                "company_name": str,
                "company_url": str,
                "pdf_url": str,
                "announcement_date": str,
                "announcement_title": str,
                "source": "bse"
            }
    """
    # Default configuration
    default_config = {
        "url": "https://www.bseindia.com/corporates/ann.html",
        "timeout": 30,
    }
    
    # Merge with provided config
    if config:
        default_config.update(config)
    
    config = default_config
    
    url = config.get("url")
    timeout = config.get("timeout", 30)
    cookie_header = config.get("cookie_header")
    
    # Default headers for BSE
    headers = config.get("headers", {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.bseindia.com/",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })
    
    # Parse cookies if provided as string
    cookies = None
    if cookie_header:
        if isinstance(cookie_header, str):
            cookies = {}
            for part in cookie_header.split(";"):
                if "=" in part:
                    k, v = part.split("=", 1)
                    cookies[k.strip()] = v.strip()
        else:
            cookies = cookie_header
    
    try:
        # Fetch HTML content and try API endpoints
        with requests.Session() as s:
            # BSE may require a session with initial page visit
            print("🔗 Establishing session with BSE...")
            s.get("https://www.bseindia.com/", headers=headers, timeout=timeout)
            
            # Try to fetch the main page first
            resp = s.get(url, headers=headers, cookies=cookies, timeout=timeout, allow_redirects=True)
            resp.raise_for_status()
            html_content = resp.text
            
            # First, try to extract the API endpoint from the page
            print("🔍 Analyzing page to find API endpoint...")
            soup_temp = BeautifulSoup(html_content, "lxml")
            
            # Look for data attributes that might contain API endpoints
            found_endpoint = None
            for elem in soup_temp.find_all(attrs={'data-api': True}):
                api_url = elem.get('data-api')
                if api_url:
                    if not api_url.startswith('http'):
                        api_url = f"https://www.bseindia.com{api_url}" if api_url.startswith('/') else f"https://www.bseindia.com/{api_url}"
                    found_endpoint = ('get', api_url)
                    print(f"  ✅ Found API endpoint in data-api attribute: {api_url}")
                    break
            
            # Look for ng-controller or ng-init that might have API calls
            if not found_endpoint:
                for elem in soup_temp.find_all(attrs={'ng-init': True}):
                    ng_init = elem.get('ng-init', '')
                    # Look for URL patterns in ng-init
                    url_match = re.search(r'["\']([^"\']*(?:api|ann|corp)[^"\']*)["\']', ng_init, re.IGNORECASE)
                    if url_match:
                        api_url = url_match.group(1)
                        if not api_url.startswith('http'):
                            api_url = f"https://www.bseindia.com{api_url}" if api_url.startswith('/') else f"https://www.bseindia.com/{api_url}"
                        found_endpoint = ('get', api_url)
                        print(f"  ✅ Found API endpoint in ng-init: {api_url}")
                        break
            
            script_tags = soup_temp.find_all('script')
            
            found_endpoint = None
            
            # Check inline scripts first
            for script in script_tags:
                script_text = script.string or ""
                if not script_text:
                    continue
                
                # Look for $http.get/post calls with API endpoints
                http_matches = re.findall(r'\$http\.(get|post)\(["\']([^"\']+)["\']', script_text, re.IGNORECASE)
                for method, endpoint in http_matches:
                    if 'ann' in endpoint.lower() or 'corp' in endpoint.lower() or 'api' in endpoint.lower():
                        if not endpoint.startswith('http'):
                            endpoint = f"https://www.bseindia.com{endpoint}" if endpoint.startswith('/') else f"https://www.bseindia.com/{endpoint}"
                        found_endpoint = (method, endpoint)
                        print(f"  ✅ Found API endpoint in inline JavaScript: {method.upper()} {endpoint}")
                        break
                
                if found_endpoint:
                    break
                
                # Also look for fetch() calls
                fetch_matches = re.findall(r'fetch\(["\']([^"\']+)["\']', script_text, re.IGNORECASE)
                for endpoint in fetch_matches:
                    if 'ann' in endpoint.lower() or 'corp' in endpoint.lower() or 'api' in endpoint.lower():
                        if not endpoint.startswith('http'):
                            endpoint = f"https://www.bseindia.com{endpoint}" if endpoint.startswith('/') else f"https://www.bseindia.com/{endpoint}"
                        found_endpoint = ('get', endpoint)
                        print(f"  ✅ Found API endpoint in fetch(): {endpoint}")
                        break
                
                if found_endpoint:
                    break
            
            # If not found in inline scripts, try external JavaScript files (only BSE's own files)
            if not found_endpoint:
                print("  🔍 Checking external JavaScript files (BSE domain only)...")
                for script in script_tags:
                    src = script.get('src')
                    if src:
                        # Only process JavaScript files from BSE domain, skip external domains
                        if src.startswith('http') and 'bseindia.com' not in src:
                            continue
                        
                        try:
                            js_url = src if src.startswith('http') else f"https://www.bseindia.com{src}" if src.startswith('/') else f"https://www.bseindia.com/{src}"
                            
                            # Skip if it's not a BSE domain
                            if 'bseindia.com' not in js_url:
                                continue
                            
                            print(f"    Fetching: {js_url}")
                            js_resp = s.get(js_url, headers=headers, timeout=10)
                            if js_resp.status_code == 200:
                                js_content = js_resp.text
                                # Look for API endpoints in external JS
                                http_matches = re.findall(r'\$http\.(get|post)\(["\']([^"\']+)["\']', js_content, re.IGNORECASE)
                                for method, endpoint in http_matches:
                                    if 'ann' in endpoint.lower() or 'corp' in endpoint.lower() or 'api' in endpoint.lower():
                                        if not endpoint.startswith('http'):
                                            endpoint = f"https://www.bseindia.com{endpoint}" if endpoint.startswith('/') else f"https://www.bseindia.com/{endpoint}"
                                        found_endpoint = (method, endpoint)
                                        print(f"  ✅ Found API endpoint in {js_url}: {method.upper()} {endpoint}")
                                        break
                                
                                # Also check for fetch() calls
                                if not found_endpoint:
                                    fetch_matches = re.findall(r'fetch\(["\']([^"\']+)["\']', js_content, re.IGNORECASE)
                                    for endpoint in fetch_matches:
                                        if 'ann' in endpoint.lower() or 'corp' in endpoint.lower() or 'api' in endpoint.lower():
                                            if not endpoint.startswith('http'):
                                                endpoint = f"https://www.bseindia.com{endpoint}" if endpoint.startswith('/') else f"https://www.bseindia.com/{endpoint}"
                                            found_endpoint = ('get', endpoint)
                                            print(f"  ✅ Found API endpoint in fetch(): {endpoint}")
                                            break
                                
                                if found_endpoint:
                                    break
                        except Exception as e:
                            # Skip if we can't fetch the JS file
                            continue
            
            # Use the BSE API endpoint directly
            # Update headers for API calls
            api_headers = headers.copy()
            api_headers['Accept'] = 'application/json, text/plain, */*'
            api_headers['X-Requested-With'] = 'XMLHttpRequest'
            api_headers['Referer'] = url
            api_headers['Accept-Encoding'] = 'gzip, deflate, br'
            
            # Try the AnnGetData API endpoint (common BSE API pattern)
            from datetime import datetime, timedelta
            today = datetime.now()
            yesterday = today - timedelta(days=1)
            
            # Format dates as YYYYMMDD
            str_to_date = today.strftime('%Y%m%d')
            str_prev_date = yesterday.strftime('%Y%m%d')
            
            # BSE AnnGetData API endpoint with parameters
            ann_get_data_endpoints = [
                f"https://api.bseindia.com/BseIndiaAPI/api/AnnGetData/w?strCat=-1&strPrevDate={str_prev_date}&strScrip=&strSearch=P&strToDate={str_to_date}&strType=C&pageno=1",
                f"https://www.bseindia.com/BseIndiaAPI/api/AnnGetData/w?strCat=-1&strPrevDate={str_prev_date}&strScrip=&strSearch=P&strToDate={str_to_date}&strType=C&pageno=1",
                f"https://api.bseindia.com/BseIndiaAPI/api/AnnGetData/w",
            ]
            
            # Try multiple possible BSE API endpoints with GET requests
            api_endpoints = []
            
            # Add the found endpoint from JavaScript if available
            if found_endpoint:
                method, endpoint = found_endpoint
                api_endpoints.append((method, endpoint))
            
            # Add AnnGetData endpoints
            for endpoint in ann_get_data_endpoints:
                api_endpoints.append(('get', endpoint))
            
            # Add other common endpoints
            other_endpoints = [
                "https://www.bseindia.com/corporates/CorpAnnData.aspx",
                "https://www.bseindia.com/api/corporate-announcements",
                "https://www.bseindia.com/api/CorpAnnData",
                "https://www.bseindia.com/corporates/api/announcements",
                "https://www.bseindia.com/api/corpann",
            ]
            for endpoint in other_endpoints:
                api_endpoints.append(('get', endpoint))
            
            # Try each endpoint
            for method, endpoint in api_endpoints:
                try:
                    print(f"🔍 Trying {method.upper()}: {endpoint}")
                    
                    # For AnnGetData endpoints, they already have query params in URL
                    if 'AnnGetData' in endpoint and '?' in endpoint:
                        api_resp = s.get(endpoint, headers=api_headers, timeout=timeout)
                    elif method.lower() == 'post':
                        # Try with common POST payloads
                        payloads = [
                            {},
                            {"segment": "Equity", "pageno": 1},
                            {"Segment": "Equity", "pageno": 1},
                        ]
                        for payload in payloads:
                            try:
                                api_resp = s.post(endpoint, headers=api_headers, json=payload, timeout=timeout)
                                if api_resp.status_code == 200:
                                    break
                            except:
                                continue
                    else:
                        # Try GET with query params for endpoints that need them
                        query_params_list = [
                            {},
                            {"segment": "Equity", "pageno": "1"},
                            {"Segment": "Equity", "pageno": "1"},
                            {"strCat": "-1", "strPrevDate": str_prev_date, "strScrip": "", "strSearch": "P", "strToDate": str_to_date, "strType": "C", "pageno": "1"},
                        ]
                        api_resp = None
                        for params in query_params_list:
                            try:
                                api_resp = s.get(endpoint, headers=api_headers, params=params, timeout=timeout)
                                if api_resp.status_code == 200:
                                    break
                            except:
                                continue
                    
                    if api_resp and api_resp.status_code == 200:
                        content_type = api_resp.headers.get('Content-Type', '').lower()
                        
                        # Check if response is JSON or looks like JSON (starts with { or [)
                        response_text = api_resp.text.strip()
                        is_json = (
                            'application/json' in content_type or 
                            'text/json' in content_type or 
                            response_text.startswith('{') or 
                            response_text.startswith('[')
                        )
                        
                        # Skip HTML responses (they start with <!DOCTYPE or <html)
                        if response_text.startswith('<!DOCTYPE') or response_text.startswith('<html'):
                            print(f"   ⚠️  Got HTML response instead of JSON (likely redirect or error page)")
                            continue
                        
                        if is_json:
                            try:
                                api_data = api_resp.json()
                                if api_data:
                                    print(f"✅ Successfully fetched data from API endpoint: {endpoint}")
                                    # Process JSON data
                                    parsed = parse_bse_api_response(api_data)
                                    if parsed and len(parsed) > 0:
                                        print(f"✅ Parsed {len(parsed)} announcements from API")
                                        return parsed
                                    else:
                                        print(f"⚠️  No valid announcements parsed from response")
                                        print(f"   Response structure: {type(api_data)} - {str(api_data)[:500]}")
                            except (ValueError, json.JSONDecodeError) as e:
                                print(f"⚠️  Failed to parse JSON: {e}")
                                # Try to see what we got
                                print(f"   Response preview: {response_text[:500]}")
                        else:
                            print(f"⚠️  Response is not JSON (Content-Type: {content_type})")
                            print(f"   Response preview: {response_text[:200]}")
                    elif api_resp:
                        if api_resp.status_code == 404:
                            print(f"   ❌ 404 Not Found")
                        elif api_resp.status_code == 403:
                            print(f"   ❌ 403 Forbidden (may need authentication)")
                        else:
                            print(f"   ⚠️  Status: {api_resp.status_code}")
                except Exception as e:
                    print(f"   ⚠️  Error calling API endpoint: {e}")
            
            # Try POST requests for endpoints that might require POST
            print("🔍 Trying POST requests...")
            post_endpoints = [
                "https://www.bseindia.com/corporates/CorpAnnData.aspx",
                "https://www.bseindia.com/api/corporate-announcements",
                "https://www.bseindia.com/corporates/api/announcements",
            ]
            
            post_payloads = [
                {},
                {"segment": "Equity"},
                {"Segment": "Equity"},
                {"index": "equities"},
            ]
            
            for endpoint in post_endpoints:
                for payload in post_payloads:
                    try:
                        if payload:
                            print(f"🔍 Trying POST: {endpoint} with payload {payload}")
                        else:
                            print(f"🔍 Trying POST: {endpoint}")
                        api_resp = s.post(endpoint, headers=api_headers, json=payload, timeout=timeout)
                        content_type = api_resp.headers.get('Content-Type', '').lower()
                        
                        if api_resp.status_code == 200:
                            if 'application/json' in content_type or 'text/json' in content_type or api_resp.text.strip().startswith('{') or api_resp.text.strip().startswith('['):
                                try:
                                    api_data = api_resp.json()
                                    if api_data:
                                        print(f"✅ Successfully fetched data from POST endpoint: {endpoint}")
                                        parsed = parse_bse_api_response(api_data)
                                        if parsed and len(parsed) > 0:
                                            print(f"✅ Parsed {len(parsed)} announcements from API")
                                            return parsed
                                except (ValueError, json.JSONDecodeError):
                                    pass
                    except Exception as e:
                        if not payload:  # Only print error for first attempt
                            print(f"   ⚠️  Error: {e}")
            
            # If API didn't work, try to extract data from script tags (JSON data embedded in HTML)
            print("📄 Trying to extract data from HTML/JavaScript...")
            
            # Look for JSON data in script tags
            soup_temp = BeautifulSoup(html_content, "lxml")
            script_tags = soup_temp.find_all('script')
            for script in script_tags:
                script_text = script.string or ""
                # Look for BSE data structures
                if 'CorpannData' in script_text or 'corporate' in script_text.lower() or 'Table' in script_text:
                    # Try to extract JSON from script
                    json_matches = re.findall(r'\{[^{}]*"Table"[^{}]*\[.*?\]', script_text, re.DOTALL)
                    for json_str in json_matches:
                        try:
                            data = json.loads(json_str)
                            parsed = parse_bse_api_response(data)
                            if parsed:
                                print("✅ Found data in script tags")
                                return parsed
                        except (json.JSONDecodeError, ValueError):
                            continue
                    
                    # Also try to find CorpannData structure
                    if 'CorpannData' in script_text:
                        # Look for var CorpannData = {...} patterns
                        var_matches = re.findall(r'CorpannData\s*=\s*(\{.*?\})', script_text, re.DOTALL)
                        for json_str in var_matches:
                            try:
                                data = json.loads(json_str)
                                parsed = parse_bse_api_response(data)
                                if parsed:
                                    print("✅ Found CorpannData in script tags")
                                    return parsed
                            except (json.JSONDecodeError, ValueError):
                                continue
            
            # Continue with HTML parsing
            print("📄 Using HTML parsing method")
            
    except Exception as e:
        print(f"❌ Error fetching data from BSE: {e}")
        import traceback
        print(traceback.format_exc()[:300])
        return []
    
    # Parse HTML and extract announcements
    soup = BeautifulSoup(html_content, "lxml")
    
    announcements = []
    
    # Strategy 0: Look for div elements with announcement data (marketstartarea class)
    print("🔍 Strategy 0: Looking for announcement divs...")
    announcement_divs = soup.find_all('div', class_=lambda x: x and ('marketstartarea' in ' '.join(x) if isinstance(x, list) else 'marketstartarea' in str(x)))
    
    if not announcement_divs:
        # Also try finding divs with the text pattern
        all_divs = soup.find_all('div')
        for div in all_divs:
            div_text = div.get_text()
            if 'Total No of Announcements' in div_text or 'Current Page Number' in div_text:
                announcement_divs.append(div)
                break
    
    if announcement_divs:
        print(f"  ✅ Found {len(announcement_divs)} announcement div(s)")
        
        for div in announcement_divs:
            div_text = div.get_text()
            
            # Extract page info: "Current Page Number 1 out of 4"
            page_match = re.search(r'Current Page Number\s+(\d+)\s+out of\s+(\d+)', div_text, re.IGNORECASE)
            if page_match:
                current_page = int(page_match.group(1))
                total_pages = int(page_match.group(2))
                print(f"  📄 Page: {current_page}/{total_pages}")
            
            # Extract total announcements: "Total No of Announcements 196"
            total_match = re.search(r'Total No of Announcements\s+(\d+)', div_text, re.IGNORECASE)
            if total_match:
                total_announcements = int(total_match.group(1))
                print(f"  📊 Total announcements: {total_announcements}")
            
            # Extract date: "Till Date 08 Dec 2025"
            date_match = re.search(r'Till Date\s+(\d{1,2}\s+\w+\s+\d{4})', div_text, re.IGNORECASE)
            if date_match:
                till_date = date_match.group(1)
                print(f"  📅 Till Date: {till_date}")
            
            # Extract announcement details from the div text
            # Pattern 1: "08 Dec 2025 Oracle Financial Services Software Ltd - 532466 - Grant Of Options..."
            # Pattern 2: Multiple announcements might be separated by newlines or other delimiters
            
            # Split div text into lines and process each potential announcement
            lines = div_text.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line or len(line) < 20:  # Skip very short lines
                    continue
                
                # Look for pattern: DATE COMPANY_NAME - SCRIP_CODE - ANNOUNCEMENT_TITLE
                # More flexible pattern to handle variations
                patterns = [
                    r'(\d{1,2}\s+\w+\s+\d{4})\s+([^-]+?)\s+-\s+(\d+)\s+-\s+(.+)',  # DATE COMPANY - CODE - TITLE
                    r'(\d{1,2}\s+\w+\s+\d{4})\s+(.+?)\s+-\s+(\d+)\s+-\s+(.+)',  # More flexible
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, line, re.IGNORECASE)
                    if match:
                        ann_date_str = match.group(1)
                        company_name = match.group(2).strip()
                        scrip_code = match.group(3)
                        announcement_title = match.group(4).strip()
                        
                        # Clean up company name (remove extra spaces, common suffixes)
                        company_name = re.sub(r'\s+', ' ', company_name)
                        company_name = re.sub(r'\s+(Ltd|Limited|Inc|Corp|Corporation)\.?$', '', company_name, flags=re.IGNORECASE)
                        
                        # Look for PDF link - check in the div, parent, and siblings
                        pdf_url = ""
                        
                        # Check links in this div
                        links = div.find_all('a', href=True)
                        for link in links:
                            href = link.get('href', '')
                            link_text = link.get_text().strip()
                            # Match link to this announcement if link text contains company name or scrip code
                            if (scrip_code in link_text or company_name[:20] in link_text or 
                                PDF_REGEX.search(href) or 'attachment' in href.lower() or 
                                '/xml-data/corpfiling/' in href.lower()):
                                pdf_url = href
                                if not pdf_url.startswith('http'):
                                    pdf_url = f"https://www.bseindia.com{pdf_url}" if pdf_url.startswith('/') else f"https://www.bseindia.com/{pdf_url}"
                                break
                        
                        # Also check parent and sibling elements for links
                        if not pdf_url:
                            parent = div.parent
                            if parent:
                                parent_links = parent.find_all('a', href=True)
                                for link in parent_links:
                                    href = link.get('href', '')
                                    if PDF_REGEX.search(href) or 'attachment' in href.lower() or '/xml-data/corpfiling/' in href.lower():
                                        pdf_url = href
                                        if not pdf_url.startswith('http'):
                                            pdf_url = f"https://www.bseindia.com{pdf_url}" if pdf_url.startswith('/') else f"https://www.bseindia.com/{pdf_url}"
                                        break
                        
                        # Construct company URL
                        company_url = f"https://www.bseindia.com/stock-share-price/{scrip_code}/" if scrip_code else ""
                        
                        # Parse date
                        announcement_date = parse_date(ann_date_str)
                        
                        announcement = {
                            "company_name": company_name,
                            "company_url": company_url,
                            "pdf_url": pdf_url if pdf_url else f"https://www.bseindia.com/corporates/ann.html",  # Fallback
                            "announcement_date": announcement_date,
                            "announcement_title": announcement_title,
                            "source": "bse"
                        }
                        
                        if validate_announcement(announcement):
                            announcements.append(announcement)
                            print(f"  ✅ Found: {company_name} ({scrip_code}) - {announcement_title[:50]}...")
                        
                        break  # Found a match, move to next line
        
        # Also look for announcement rows in tables/lists near these divs
        # The actual announcements are likely in a table structure
        if announcement_divs and not announcements:
            print("  🔍 Looking for announcement table structure...")
            # Find tables or lists that are siblings or nearby
            for div in announcement_divs:
                # Look for next sibling table or any table nearby
                next_sibling = div.find_next_sibling(['table', 'ul', 'ol', 'div'])
                if not next_sibling:
                    # Try finding next table in the document
                    next_sibling = div.find_next('table')
                
                if next_sibling and next_sibling.name == 'table':
                    print(f"  ✅ Found announcement table")
                    rows = next_sibling.find_all('tr')
                    print(f"  📊 Processing {len(rows)} table rows...")
                    
                    for idx, row in enumerate(rows[1:]):  # Skip header
                        cells = row.find_all(['td', 'th'])
                        if len(cells) < 2:
                            continue
                        
                        # Extract data from table row
                        row_text = row.get_text()
                        
                        # Look for PDF links
                        pdf_links = row.find_all('a', href=lambda x: x and (
                            PDF_REGEX.search(x) or 
                            'attachment' in x.lower() or 
                            '/xml-data/corpfiling/' in x.lower() or
                            'AnnPdfOpen' in x
                        ))
                        
                        if not pdf_links:
                            # Also check for any links that might be PDFs
                            all_links = row.find_all('a', href=True)
                            for link in all_links:
                                href = link.get('href', '')
                                if 'pdf' in href.lower() or 'attachment' in href.lower() or 'AnnPdfOpen' in href:
                                    pdf_links = [link]
                                    break
                        
                        if pdf_links:
                            pdf_url = pdf_links[0].get('href')
                            if not pdf_url.startswith('http'):
                                pdf_url = f"https://www.bseindia.com{pdf_url}" if pdf_url.startswith('/') else f"https://www.bseindia.com/{pdf_url}"
                            
                            # Extract company name and other info from row
                            company_name = "Unknown Company"
                            scrip_code = ""
                            announcement_title = ""
                            announcement_date = datetime.now().isoformat()
                            
                            # Try to extract from cells
                            cell_texts = [cell.get_text(strip=True) for cell in cells]
                            
                            # Look for company name (usually first or second cell)
                            for cell_text in cell_texts[:3]:
                                if cell_text and len(cell_text) > 3 and not cell_text.isdigit():
                                    # Check if it looks like a company name
                                    if not re.match(r'^\d{1,2}\s+\w+\s+\d{4}', cell_text):  # Not a date
                                        company_name = cell_text
                                        break
                            
                            # Look for scrip code (usually numeric, 5-6 digits)
                            for cell_text in cell_texts:
                                if cell_text and cell_text.isdigit() and 4 <= len(cell_text) <= 7:
                                    scrip_code = cell_text
                                    break
                            
                            # Look for announcement title (longer text)
                            for cell_text in cell_texts:
                                if cell_text and len(cell_text) > 20:
                                    announcement_title = cell_text
                                    break
                            
                            # Look for date and time in row (prefer datetime format)
                            date_match = BSE_DATETIME_REGEX.search(row_text)
                            if date_match:
                                # Found date with time
                                announcement_date = parse_date(date_match.group(0))
                            else:
                                # Try BSE date format without time
                                date_match = BSE_DATE_REGEX.search(row_text)
                                if date_match:
                                    announcement_date = parse_date(date_match.group(1))
                                else:
                                    # Try to find date/time in cells
                                    for cell_text in cell_texts:
                                        # Try datetime first
                                        datetime_match = BSE_DATETIME_REGEX.search(cell_text)
                                        if datetime_match:
                                            announcement_date = parse_date(datetime_match.group(0))
                                            break
                                        # Then try date only
                                        date_match = BSE_DATE_REGEX.search(cell_text)
                                        if date_match:
                                            announcement_date = parse_date(date_match.group(1))
                                            break
                            
                            company_url = f"https://www.bseindia.com/stock-share-price/{scrip_code}/" if scrip_code else ""
                            
                            announcement = {
                                "company_name": company_name,
                                "company_url": company_url,
                                "pdf_url": pdf_url,
                                "announcement_date": announcement_date,
                                "announcement_title": announcement_title or "Corporate Announcement",
                                "source": "bse"
                            }
                            
                            if validate_announcement(announcement):
                                announcements.append(announcement)
                                # Display with time if available
                                try:
                                    if 'T' in announcement_date:
                                        dt = datetime.fromisoformat(announcement_date.replace('Z', '+00:00'))
                                        date_display = dt.strftime('%Y-%m-%d %H:%M:%S')
                                    else:
                                        date_display = announcement_date[:19] if len(announcement_date) >= 19 else announcement_date[:10]
                                except:
                                    date_display = announcement_date[:19] if len(announcement_date) >= 19 else announcement_date[:10]
                                print(f"  ✅ Row {idx+1}: {company_name} ({scrip_code}) - {date_display}")
                    
                    if announcements:
                        print(f"  ✅ Found {len(announcements)} announcements from table")
        
        if announcements:
            print(f"✅ Strategy 0 found {len(announcements)} announcement(s)")
            # Remove duplicates and sort
            seen_urls = set()
            unique_announcements = []
            for ann in announcements:
                key = ann.get('pdf_url') or f"{ann.get('company_name')}_{ann.get('announcement_date')}"
                if key not in seen_urls:
                    seen_urls.add(key)
                    unique_announcements.append(ann)
            
            # Sort by date (latest first) - convert to datetime for proper sorting
            try:
                def get_sort_date(ann):
                    date_str = ann.get('announcement_date', '')
                    try:
                        # Try parsing ISO format
                        if 'T' in date_str:
                            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                        elif len(date_str) >= 10:
                            return datetime.strptime(date_str[:10], '%Y-%m-%d')
                        else:
                            return datetime.now()
                    except:
                        return datetime.now()
                
                unique_announcements.sort(key=get_sort_date, reverse=True)
                print(f"  📅 Sorted {len(unique_announcements)} announcements (latest first)")
                if unique_announcements:
                    latest_date_str = unique_announcements[0].get('announcement_date', 'Unknown')
                    try:
                        if 'T' in latest_date_str:
                            latest_dt = datetime.fromisoformat(latest_date_str.replace('Z', '+00:00'))
                            latest_date_display = latest_dt.strftime('%Y-%m-%d %H:%M:%S')
                        else:
                            latest_date_display = latest_date_str[:19] if len(latest_date_str) >= 19 else latest_date_str
                    except:
                        latest_date_display = latest_date_str[:19] if len(latest_date_str) >= 19 else latest_date_str
                    print(f"  🕐 Latest announcement datetime: {latest_date_display}")
            except Exception as e:
                print(f"  ⚠️  Error sorting announcements: {e}")
            
            return unique_announcements
    
    # Strategy 1: Look for tables with announcement data
    tables = soup.find_all('table')
    for table in tables:
        rows = table.find_all('tr')
        if len(rows) < 2:  # Skip tables with only header or empty
            continue
        
        # Check if this looks like an announcements table
        header_row = rows[0]
        header_text = header_row.get_text().lower()
        if any(keyword in header_text for keyword in ['company', 'security', 'announcement', 'filing', 'date', 'pdf', 'attachment']):
            # Process data rows
            for row in rows[1:]:  # Skip header
                cells = row.find_all(['td', 'th'])
                if len(cells) < 2:
                    continue
                
                # Look for PDF links in the row
                pdf_links = row.find_all('a', href=lambda x: x and PDF_REGEX.search(x))
                if not pdf_links:
                    # Also check for links to attachment files
                    attachment_links = row.find_all('a', href=lambda x: x and (
                        'attachment' in x.lower() or 
                        'attach' in x.lower() or
                        '/xml-data/corpfiling/' in x.lower()
                    ))
                    pdf_links = attachment_links
                
                if not pdf_links:
                    continue
                
                pdf_url = pdf_links[0].get('href')
                if not pdf_url:
                    continue
                
                # Make PDF URL absolute if relative
                if pdf_url.startswith('/'):
                    pdf_url = "https://www.bseindia.com" + pdf_url
                elif not pdf_url.startswith('http'):
                    pdf_url = "https://www.bseindia.com/" + pdf_url
                
                # Extract company name from row
                company_name = "Unknown Company"
                company_url = ""
                announcement_date = datetime.now().isoformat()
                announcement_title = ""
                
                # Look for company links (BSE uses NSURL pattern)
                company_links = row.find_all('a', href=lambda x: x and (
                    'company' in x.lower() or 
                    'security' in x.lower() or 
                    'scrip' in x.lower() or
                    'equity' in x.lower() or
                    x.startswith('http')  # Any external link might be company link
                ))
                
                if company_links:
                    # Prefer links that look like company pages
                    for link in company_links:
                        href = link.get('href', '')
                        link_text = link.get_text(strip=True)
                        # Skip PDF links
                        if PDF_REGEX.search(href):
                            continue
                        # Prefer links with company-like text
                        if link_text and len(link_text) > 3 and len(link_text) < 100:
                            company_link = link
                            company_url = href
                            company_name = extract_company_name(link_text, company_url)
                            break
                    else:
                        # Use first non-PDF link
                        company_link = company_links[0]
                        company_url = company_link.get('href', '')
                        company_name = extract_company_name(company_link.get_text(), company_url)
                else:
                    # Try to extract from first cell
                    first_cell_text = cells[0].get_text(strip=True) if cells else ""
                    company_name = extract_company_name(first_cell_text)
                
                # Extract date from row (BSE format: "dd MMM yyyy")
                row_text = row.get_text()
                date_match = BSE_DATE_REGEX.search(row_text)
                if date_match:
                    announcement_date = parse_date(date_match.group(1))
                else:
                    # Try standard date formats
                    date_match = DATE_REGEX.search(row_text)
                    if date_match:
                        announcement_date = parse_date(date_match.group(1))
                
                # Extract title/description (category name or announcement subject)
                pdf_link_text = pdf_links[0].get_text(strip=True)
                if pdf_link_text and len(pdf_link_text) > 3:
                    announcement_title = pdf_link_text
                else:
                    # Try to get text from cells (look for category or subject)
                    for cell in cells:
                        cell_text = cell.get_text(strip=True)
                        if cell_text and len(cell_text) > 10 and not DATE_REGEX.match(cell_text):
                            # Skip if it looks like a company name (already extracted)
                            if cell_text.lower() != company_name.lower():
                                announcement_title = cell_text[:200]  # Limit length
                                break
                
                announcement = {
                    "company_name": company_name,
                    "company_url": company_url if company_url.startswith('http') else f"https://www.bseindia.com{company_url}" if company_url.startswith('/') else "",
                    "pdf_url": pdf_url,
                    "announcement_date": announcement_date,
                    "announcement_title": announcement_title,
                    "source": "bse"
                }
                
                # Validate and add
                if validate_announcement(announcement):
                    announcements.append(announcement)
    
    # Strategy 2: If no announcements found in tables, look for PDF links with nearby company info
    if not announcements:
        all_links = soup.find_all('a')
        pdf_links = [a for a in all_links if a.get('href') and PDF_REGEX.search(a.get('href', ''))]
        
        # Also look for attachment links
        attachment_links = [a for a in all_links if a.get('href') and (
            'attachment' in a.get('href', '').lower() or 
            'attach' in a.get('href', '').lower() or
            '/xml-data/corpfiling/' in a.get('href', '').lower()
        )]
        
        pdf_links.extend(attachment_links)
        
        for pdf_link in pdf_links:
            pdf_url = pdf_link.get('href')
            if not pdf_url:
                continue
            
            # Make absolute
            if pdf_url.startswith('/'):
                pdf_url = "https://www.bseindia.com" + pdf_url
            elif not pdf_url.startswith('http'):
                pdf_url = "https://www.bseindia.com/" + pdf_url
            
            # Look for company name in nearby elements
            parent = pdf_link.parent
            company_name = "Unknown Company"
            company_url = ""
            announcement_date = datetime.now().isoformat()
            announcement_title = pdf_link.get_text(strip=True) or ""
            
            # Search up the DOM tree for company info
            for _ in range(5):  # Check up to 5 levels up
                if not parent:
                    break
                
                # Look for company links
                company_links = parent.find_all('a', href=lambda x: x and (
                    'company' in x.lower() or 
                    'security' in x.lower() or 
                    'scrip' in x.lower() or
                    '/equity' in x.lower()
                ))
                if company_links:
                    company_link = company_links[0]
                    company_url = company_link.get('href', '')
                    company_name = extract_company_name(company_link.get_text(), company_url)
                    break
                
                # Look for date
                parent_text = parent.get_text()
                date_match = BSE_DATE_REGEX.search(parent_text)
                if date_match:
                    announcement_date = parse_date(date_match.group(1))
                else:
                    date_match = DATE_REGEX.search(parent_text)
                    if date_match:
                        announcement_date = parse_date(date_match.group(1))
                
                parent = parent.parent
            
            announcement = {
                "company_name": company_name,
                "company_url": company_url if company_url.startswith('http') else f"https://www.bseindia.com{company_url}" if company_url.startswith('/') else "",
                "pdf_url": pdf_url,
                "announcement_date": announcement_date,
                "announcement_title": announcement_title,
                "source": "bse"
            }
            
            if validate_announcement(announcement):
                announcements.append(announcement)
    
    # Remove duplicates based on PDF URL
    seen_urls = set()
    unique_announcements = []
    for ann in announcements:
        if ann['pdf_url'] not in seen_urls:
            seen_urls.add(ann['pdf_url'])
            unique_announcements.append(ann)
    
    # Sort by date (latest first) - convert to datetime for proper sorting
    try:
        def get_sort_date(ann):
            date_str = ann.get('announcement_date', '')
            try:
                # Try parsing ISO format
                if 'T' in date_str:
                    return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                elif len(date_str) >= 10:
                    return datetime.strptime(date_str[:10], '%Y-%m-%d')
                else:
                    return datetime.now()
            except:
                return datetime.now()
        
        unique_announcements.sort(key=get_sort_date, reverse=True)
        print(f"📅 Sorted {len(unique_announcements)} announcements (latest first)")
        if unique_announcements:
            latest_date_str = unique_announcements[0].get('announcement_date', 'Unknown')
            try:
                if 'T' in latest_date_str:
                    latest_dt = datetime.fromisoformat(latest_date_str.replace('Z', '+00:00'))
                    latest_date_display = latest_dt.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    latest_date_display = latest_date_str[:19] if len(latest_date_str) >= 19 else latest_date_str
            except:
                latest_date_display = latest_date_str[:19] if len(latest_date_str) >= 19 else latest_date_str
            print(f"🕐 Latest announcement datetime: {latest_date_display}")
    except Exception as e:
        print(f"⚠️  Error sorting announcements: {e}")
        # Keep original order if sorting fails
    
    return unique_announcements
