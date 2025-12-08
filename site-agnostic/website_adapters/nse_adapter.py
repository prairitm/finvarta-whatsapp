"""
NSE India Adapter

Website-specific adapter for fetching announcements from NSE India corporate filings page.
Returns standardized announcement data structure.
"""

import re
import os
import sys
import requests
import json
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

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
# NSE date/time formats: "DD-MMM-YYYY HH:MM:SS" or "DD-MM-YYYY HH:MM" etc.
NSE_DATETIME_REGEX = re.compile(r"(\d{1,2}[-/]\w{3}[-/]\d{2,4}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\s*(\d{1,2}:\d{2}(?::\d{2})?)?", re.IGNORECASE)


def parse_date(date_str: str) -> Optional[datetime]:
    """
    Parse date string from NSE format to datetime object.
    Handles NSE's BROADCAST DATE/TIME format and other common formats.
    
    Args:
        date_str: Date string in various formats (DD-MM-YYYY, DD-MMM-YYYY HH:MM:SS, etc.)
    
    Returns:
        datetime object or None if parsing fails
    """
    if not date_str:
        return None
    
    date_str = date_str.strip()
    
    # Try NSE datetime format first: "DD-MMM-YYYY HH:MM:SS" or "DD-MMM-YYYY HH:MM"
    nse_match = NSE_DATETIME_REGEX.search(date_str)
    if nse_match:
        date_part = nse_match.group(1)
        time_part = nse_match.group(2) if nse_match.lastindex >= 2 else None
        
        # Try NSE format: DD-MMM-YYYY (e.g., "08-Dec-2025")
        for fmt in ["%d-%b-%Y", "%d-%B-%Y", "%d/%b/%Y", "%d/%B/%Y"]:
            try:
                dt = datetime.strptime(date_part, fmt)
                # Add time if present
                if time_part:
                    time_parts = time_part.split(':')
                    if len(time_parts) >= 2:
                        dt = dt.replace(hour=int(time_parts[0]), minute=int(time_parts[1]))
                        if len(time_parts) >= 3:
                            dt = dt.replace(second=int(time_parts[2]))
                return dt
            except ValueError:
                continue
    
    # Try standard date formats
    match = DATE_REGEX.search(date_str)
    if match:
        date_part = match.group(1)
        # Extract time part if present in the original string
        time_match = re.search(r'(\d{1,2}:\d{2}(?::\d{2})?)', date_str)
        time_str = time_match.group(1) if time_match else None
        
        # Try to parse common formats
        formats = [
            "%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S",
            "%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M",
            "%d-%m-%Y", "%d/%m/%Y",
            "%d-%m-%y", "%d/%m/%y",
            "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
            "%Y-%m-%d"
        ]
        for fmt in formats:
            try:
                if "%H" in fmt and time_str:
                    dt = datetime.strptime(date_part + " " + time_str, fmt)
                else:
                    dt = datetime.strptime(date_part, fmt)
                return dt
            except ValueError:
                continue
    
    return None


def parse_nse_api_response(api_data) -> List[Dict]:
    """
    Parse NSE API JSON response and convert to standardized announcement format.
    
    Args:
        api_data: JSON response from NSE API (can be list or dict)
    
    Returns:
        List of announcement dictionaries in standardized format
    """
    announcements = []
    
    # Handle different possible API response structures
    data_list = []
    if isinstance(api_data, list):
        data_list = api_data
    elif isinstance(api_data, dict):
        # Try common keys
        for key in ['data', 'announcements', 'results', 'items', 'records']:
            if key in api_data and isinstance(api_data[key], list):
                data_list = api_data[key]
                break
        
        # Don't treat wrapper dicts (like {"data": [], "msg": "..."}) as announcements
        # Only treat as single item if it has announcement-like fields
        if not data_list and api_data:
            # Check if this dict looks like an announcement (has required fields)
            has_announcement_fields = any(key in api_data for key in ['sm_name', 'symbol', 'attchmntFile', 'an_dt', 'desc'])
            if has_announcement_fields:
                data_list = [api_data]
    
    for item in data_list:
        if not isinstance(item, dict):
            continue
        
        # Extract fields using NSE API field names (based on actual API response)
        # NSE API fields: symbol, sm_name, desc, an_dt, attchmntFile, etc.
        company_name = item.get('sm_name') or item.get('companyName') or item.get('company_name') or item.get('COMPANY') or "Unknown Company"
        company_symbol = item.get('symbol') or ""
        
        # PDF URL from attchmntFile field
        pdf_url = item.get('attchmntFile') or item.get('pdfUrl') or item.get('pdf_url') or item.get('attachment') or item.get('PDF_URL') or ""
        
        # Announcement date from an_dt (BROADCAST DATE/TIME) or sort_date
        announcement_date_str = item.get('an_dt') or item.get('sort_date') or item.get('broadcastDate') or item.get('broadcast_date') or item.get('announcementDate') or item.get('announcement_date') or item.get('BROADCAST_DATE') or ""
        
        # Title/description
        announcement_title = item.get('desc') or item.get('attchmntText') or item.get('subject') or item.get('title') or item.get('SUBJECT') or item.get('announcement') or ""
        
        # Company URL - construct from symbol and company name
        company_url = ""
        if company_symbol:
            # Format company name for URL: lowercase, replace spaces/special chars with hyphens
            formatted_company_name = company_name.lower().strip()
            # Replace common special characters
            formatted_company_name = formatted_company_name.replace('&', 'and').replace('.', '').replace(',', '')
            # Replace spaces and other non-alphanumeric chars (except hyphens) with hyphens
            formatted_company_name = re.sub(r'[^a-z0-9\-]+', '-', formatted_company_name)
            # Remove leading/trailing hyphens and collapse multiple consecutive hyphens
            formatted_company_name = re.sub(r'-+', '-', formatted_company_name).strip('-')
            # Use formatted name if valid, otherwise just use symbol
            if formatted_company_name and formatted_company_name != 'unknown-company':
                company_url = f"https://www.nseindia.com/get-quote/equity/{company_symbol}/{formatted_company_name}"
            else:
                company_url = f"https://www.nseindia.com/get-quote/equity/{company_symbol}"
        else:
            company_url = item.get('companyUrl') or item.get('company_url') or ""
        
        # Parse date - NSE format is "08-Dec-2025 14:19:19" or "2025-12-08 14:19:19"
        announcement_date_obj = None
        if announcement_date_str:
            announcement_date_obj = parse_date(announcement_date_str)
        
        if not announcement_date_obj:
            # Fallback to sort_date if available
            sort_date_str = item.get('sort_date')
            if sort_date_str:
                announcement_date_obj = parse_date(sort_date_str)
        
        if not announcement_date_obj:
            announcement_date_obj = datetime.now()
        
        # Make PDF URL absolute if relative
        if pdf_url and not pdf_url.startswith('http'):
            if pdf_url.startswith('/'):
                pdf_url = "https://www.nseindia.com" + pdf_url
            else:
                pdf_url = "https://www.nseindia.com/" + pdf_url
        
        announcement = {
            "company_name": company_name,
            "company_url": company_url if company_url.startswith('http') else f"https://www.nseindia.com{company_url}" if company_url.startswith('/') else "",
            "pdf_url": pdf_url,
            "announcement_date": announcement_date_obj.isoformat(),
            "announcement_title": announcement_title,
            "source": "nse"
        }
        
        if validate_announcement(announcement):
            announcements.append(announcement)
    
    return announcements


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
    
    # If text looks like a company name (has capital letters, reasonable length)
    if len(text) > 2 and len(text) < 100:
        # Remove common prefixes/suffixes
        text = re.sub(r'^(LTD|LIMITED|INC|CORP|CORPORATION)[\s.]*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'[\s.]+(LTD|LIMITED|INC|CORP|CORPORATION)$', '', text, flags=re.IGNORECASE)
        if text:
            return text.strip()
    
    # Try to extract from URL
    if link_href:
        # Look for symbol in URL patterns like /equityList/equityList?symbol=XYZ
        symbol_match = re.search(r'[?&]symbol=([^&]+)', link_href)
        if symbol_match:
            return symbol_match.group(1).upper()
        
        # Look for company name in path
        path_match = re.search(r'/([^/]+)/?$', link_href)
        if path_match:
            return path_match.group(1).replace('-', ' ').title()
    
    return "Unknown Company"


def fetch_nse_announcements(config: Optional[Dict] = None) -> List[Dict]:
    """
    Fetch announcements from NSE India corporate filings page and return standardized format.
    
    Args:
        config: Optional configuration dictionary with the following keys:
            - url: NSE announcements URL (default: https://www.nseindia.com/companies-listing/corporate-filings-announcements)
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
                "source": "nse"
            }
    """
    # Default configuration
    default_config = {
        "url": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
        "timeout": 30,
    }
    
    # Merge with provided config
    if config:
        default_config.update(config)
    
    config = default_config
    
    url = config.get("url")
    timeout = config.get("timeout", 30)
    cookie_header = config.get("cookie_header")
    
    # Default headers for NSE
    headers = config.get("headers", {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.nseindia.com/",
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
        with requests.Session() as s:
            s.get("https://www.nseindia.com/", headers=headers, timeout=timeout)
            resp = s.get(url, headers=headers, cookies=cookies, timeout=timeout, allow_redirects=True)
            resp.raise_for_status()
            html_content = resp.text
            
            api_headers = headers.copy()
            api_headers['Accept'] = 'application/json, text/plain, */*'
            api_headers['X-Requested-With'] = 'XMLHttpRequest'
            api_headers['Referer'] = url
            api_headers['Accept-Encoding'] = 'gzip, deflate, br'
            
            endpoint = "https://www.nseindia.com/api/corporate-announcements?index=equities"
            
            try:
                api_resp = s.get(endpoint, headers=api_headers, timeout=timeout)
                content_type = api_resp.headers.get('Content-Type', '').lower()
                
                if api_resp.status_code == 200:
                    if 'application/json' in content_type or 'text/json' in content_type:
                        try:
                            api_data = api_resp.json()
                            if api_data:
                                parsed = parse_nse_api_response(api_data)
                                if parsed and len(parsed) > 0:
                                    return parsed
                        except (ValueError, json.JSONDecodeError):
                            pass
            except Exception:
                pass
            
            soup_temp = BeautifulSoup(html_content, "lxml")
            script_tags = soup_temp.find_all('script')
            for script in script_tags:
                script_text = script.string or ""
                if 'CFanncEquityTable' in script_text or 'corporateAnnouncement' in script_text.lower():
                    json_matches = re.findall(r'\{[^{}]*"data"[^{}]*\[.*?\]', script_text, re.DOTALL)
                    for json_str in json_matches:
                        try:
                            data = json.loads(json_str)
                            parsed = parse_nse_api_response(data)
                            if parsed:
                                return parsed
                        except (json.JSONDecodeError, ValueError):
                            continue
            
    except Exception:
        return []
    
    # Parse HTML and extract announcements
    soup = BeautifulSoup(html_content, "lxml")
    
    announcements = []
    
    target_table = None
    target_div = soup.find('div', id='table-CFanncEquity')
    
    if target_div:
        target_table = target_div.find('table')
    
    if not target_table:
        tables = soup.find_all('table')
        all_elements = list(tables) + soup.find_all('div', {'id': lambda x: x and 'CFannc' in str(x)})
        
        for elem in all_elements:
            elem_id = elem.get('id', '')
            elem_class = ' '.join(elem.get('class', []))
            
            if 'CFanncEquity' in elem_id or 'CFanncEquity' in elem_class:
                if elem.name == 'table':
                    target_table = elem
                    break
                elif elem.name == 'div':
                    inner_table = elem.find('table')
                    if inner_table:
                        target_table = inner_table
                        break
    
    if not target_table:
        tables = soup.find_all('table')
        for table in tables:
            header_spans = table.find_all('span', class_='columnheader-uppercase')
            for span in header_spans:
                if span.get('data-nse-translate-columnheader') == 'an_dt' or 'broadcast date' in span.get_text().lower():
                    target_table = table
                    break
            if target_table:
                break
    
    if not target_table:
        tables = soup.find_all('table')
        for table in tables:
            thead = table.find('thead')
            if thead:
                header_text = thead.get_text().lower()
                if 'broadcast' in header_text and 'date' in header_text:
                    target_table = table
                    break
    
    if target_table:
        rows = target_table.find_all('tr')
        if len(rows) >= 2:
            header_row = rows[0]
            header_cells = header_row.find_all(['th', 'td'])
            date_column_index = None
            
            for idx, cell in enumerate(header_cells):
                span = cell.find('span', {'data-nse-translate-columnheader': 'an_dt'})
                if span or 'broadcast date' in cell.get_text().lower() or 'an_dt' in cell.get('class', []):
                    date_column_index = idx
                    break
            
            # Process data rows
            for row_idx, row in enumerate(rows[1:], start=1):  # Skip header
                cells = row.find_all(['td', 'th'])
                if len(cells) < 2:
                    continue
                
                # Look for PDF links in the row
                pdf_links = row.find_all('a', href=lambda x: x and PDF_REGEX.search(x))
                if not pdf_links:
                    continue
                
                pdf_url = pdf_links[0].get('href')
                if not pdf_url:
                    continue
                
                # Make PDF URL absolute if relative
                if pdf_url.startswith('/'):
                    pdf_url = "https://www.nseindia.com" + pdf_url
                elif not pdf_url.startswith('http'):
                    pdf_url = "https://www.nseindia.com/" + pdf_url
                
                # Extract company name from row
                company_name = "Unknown Company"
                company_url = ""
                announcement_date_obj = None
                announcement_title = ""
                
                # Look for company links
                company_links = row.find_all('a', href=lambda x: x and (
                    'company' in x.lower() or 
                    'symbol' in x.lower() or 
                    '/equity' in x.lower() or
                    'equityList' in x.lower() or
                    '/company/' in x.lower()
                ))
                
                if company_links:
                    company_link = company_links[0]
                    company_url = company_link.get('href', '')
                    company_name = extract_company_name(company_link.get_text(), company_url)
                else:
                    # Try to extract from first cell
                    first_cell_text = cells[0].get_text(strip=True) if cells else ""
                    company_name = extract_company_name(first_cell_text)
                
                # Extract date from BROADCAST DATE/TIME column
                if date_column_index is not None and date_column_index < len(cells):
                    date_cell = cells[date_column_index]
                    date_text = date_cell.get_text(strip=True)
                    # Try to parse the date
                    announcement_date_obj = parse_date(date_text)
                    if not announcement_date_obj:
                        # Try looking for time elements or data attributes in the date cell
                        time_elem = date_cell.find('time')
                        if time_elem:
                            datetime_attr = time_elem.get('datetime') or time_elem.get_text(strip=True)
                            announcement_date_obj = parse_date(datetime_attr)
                        # Check for data attributes
                        for attr in ['data-date', 'data-time', 'data-datetime', 'datetime']:
                            attr_value = date_cell.get(attr)
                            if attr_value:
                                announcement_date_obj = parse_date(attr_value)
                                if announcement_date_obj:
                                    break
                
                # Fallback: Look for date in any cell
                if not announcement_date_obj:
                    for cell in cells:
                        cell_text = cell.get_text(strip=True)
                        parsed_date = parse_date(cell_text)
                        if parsed_date:
                            announcement_date_obj = parsed_date
                            break
                
                # Fallback: Look for date in row text
                if not announcement_date_obj:
                    row_text = row.get_text()
                    date_match = DATE_REGEX.search(row_text)
                    if date_match:
                        announcement_date_obj = parse_date(date_match.group(1))
                
                # Last resort: use order-based timestamp
                if not announcement_date_obj:
                    base_time = datetime.now()
                    announcement_date_obj = base_time.replace(microsecond=0) - timedelta(seconds=row_idx)
                
                announcement_date = announcement_date_obj.isoformat()
                
                # Extract title/description
                pdf_link_text = pdf_links[0].get_text(strip=True)
                if pdf_link_text and len(pdf_link_text) > 3:
                    announcement_title = pdf_link_text
                else:
                    # Try to get text from cells (skip date column)
                    for idx, cell in enumerate(cells):
                        if idx == date_column_index:
                            continue
                        cell_text = cell.get_text(strip=True)
                        if cell_text and len(cell_text) > 10 and not DATE_REGEX.match(cell_text):
                            announcement_title = cell_text[:200]  # Limit length
                            break
                
                announcement = {
                    "company_name": company_name,
                    "company_url": company_url if company_url.startswith('http') else f"https://www.nseindia.com{company_url}" if company_url.startswith('/') else "",
                    "pdf_url": pdf_url,
                    "announcement_date": announcement_date,
                    "announcement_title": announcement_title,
                    "source": "nse"
                }
                
                if validate_announcement(announcement):
                    announcements.append(announcement)
    
    if not announcements:
        for table in tables:
            rows = table.find_all('tr')
            if len(rows) < 2:  # Skip tables with only header or empty
                continue
            
            # Check if this looks like an announcements table
            header_row = rows[0]
            header_text = header_row.get_text().lower()
            if any(keyword in header_text for keyword in ['company', 'symbol', 'announcement', 'filing', 'date', 'pdf']):
                # Process data rows (same logic as before but simplified)
                for row in rows[1:]:  # Skip header
                    cells = row.find_all(['td', 'th'])
                    if len(cells) < 2:
                        continue
                    
                    # Look for PDF links in the row
                    pdf_links = row.find_all('a', href=lambda x: x and PDF_REGEX.search(x))
                    if not pdf_links:
                        continue
                    
                    pdf_url = pdf_links[0].get('href')
                    if not pdf_url:
                        continue
                    
                    # Make PDF URL absolute if relative
                    if pdf_url.startswith('/'):
                        pdf_url = "https://www.nseindia.com" + pdf_url
                    elif not pdf_url.startswith('http'):
                        pdf_url = "https://www.nseindia.com/" + pdf_url
                    
                    # Extract company name from row
                    company_name = "Unknown Company"
                    company_url = ""
                    announcement_date_obj = None
                    announcement_title = ""
                    
                    # Look for company links
                    company_links = row.find_all('a', href=lambda x: x and (
                        'company' in x.lower() or 
                        'symbol' in x.lower() or 
                        '/equity' in x.lower() or
                        'equityList' in x.lower()
                    ))
                    
                    if company_links:
                        company_link = company_links[0]
                        company_url = company_link.get('href', '')
                        company_name = extract_company_name(company_link.get_text(), company_url)
                    else:
                        # Try to extract from first cell
                        first_cell_text = cells[0].get_text(strip=True) if cells else ""
                        company_name = extract_company_name(first_cell_text)
                    
                    # Extract date from row
                    for cell in cells:
                        cell_text = cell.get_text(strip=True)
                        parsed_date = parse_date(cell_text)
                        if parsed_date:
                            announcement_date_obj = parsed_date
                            break
                    
                    if not announcement_date_obj:
                        row_text = row.get_text()
                        date_match = DATE_REGEX.search(row_text)
                        if date_match:
                            announcement_date_obj = parse_date(date_match.group(1))
                    
                    if not announcement_date_obj:
                        announcement_date_obj = datetime.now()
                    
                    announcement_date = announcement_date_obj.isoformat()
                    
                    # Extract title/description
                    pdf_link_text = pdf_links[0].get_text(strip=True)
                    if pdf_link_text and len(pdf_link_text) > 3:
                        announcement_title = pdf_link_text
                    else:
                        for cell in cells:
                            cell_text = cell.get_text(strip=True)
                            if cell_text and len(cell_text) > 10 and not DATE_REGEX.match(cell_text):
                                announcement_title = cell_text[:200]
                                break
                    
                    announcement = {
                        "company_name": company_name,
                        "company_url": company_url if company_url.startswith('http') else f"https://www.nseindia.com{company_url}" if company_url.startswith('/') else "",
                        "pdf_url": pdf_url,
                        "announcement_date": announcement_date,
                        "announcement_title": announcement_title,
                        "source": "nse"
                    }
                    
                    if validate_announcement(announcement):
                        announcements.append(announcement)
    
    if not announcements:
        all_links = soup.find_all('a')
        pdf_links = [a for a in all_links if a.get('href') and PDF_REGEX.search(a.get('href', ''))]
        
        # Track order to preserve HTML order when dates are missing
        for idx, pdf_link in enumerate(pdf_links):
            pdf_url = pdf_link.get('href')
            if not pdf_url:
                continue
            
            # Make absolute
            if pdf_url.startswith('/'):
                pdf_url = "https://www.nseindia.com" + pdf_url
            elif not pdf_url.startswith('http'):
                pdf_url = "https://www.nseindia.com/" + pdf_url
            
            # Look for company name in nearby elements
            parent = pdf_link.parent
            company_name = "Unknown Company"
            company_url = ""
            announcement_date_obj = None
            announcement_title = pdf_link.get_text(strip=True) or ""
            
            # Search up the DOM tree for company info and date
            search_depth = 0
            for _ in range(10):  # Check up to 10 levels up (increased for better coverage)
                if not parent:
                    break
                search_depth += 1
                
                # Look for company links
                company_links = parent.find_all('a', href=lambda x: x and (
                    'company' in x.lower() or 
                    'symbol' in x.lower() or 
                    '/equity' in x.lower() or
                    '/company/' in x.lower()
                ))
                if company_links:
                    company_link = company_links[0]
                    company_url = company_link.get('href', '')
                    company_name = extract_company_name(company_link.get_text(), company_url)
                
                # Look for date - try multiple strategies
                if not announcement_date_obj:
                    # Strategy 1: Look for date in parent text
                    parent_text = parent.get_text(strip=True)
                    date_match = DATE_REGEX.search(parent_text)
                    if date_match:
                        announcement_date_obj = parse_date(date_match.group(1))
                    
                    # Strategy 2: Look for time elements
                    if not announcement_date_obj:
                        time_elem = parent.find('time')
                        if time_elem:
                            datetime_attr = time_elem.get('datetime') or time_elem.get_text(strip=True)
                            announcement_date_obj = parse_date(datetime_attr)
                    
                    # Strategy 3: Look for date-like attributes
                    if not announcement_date_obj:
                        for attr in ['data-date', 'data-time', 'data-datetime', 'datetime']:
                            attr_value = parent.get(attr)
                            if attr_value:
                                announcement_date_obj = parse_date(attr_value)
                                if announcement_date_obj:
                                    break
                    
                    # Strategy 4: Look for date in sibling elements
                    if not announcement_date_obj and parent.parent:
                        siblings = parent.parent.find_all(['span', 'div', 'td'], limit=10)
                        for sibling in siblings:
                            sibling_text = sibling.get_text(strip=True)
                            if DATE_REGEX.search(sibling_text):
                                announcement_date_obj = parse_date(sibling_text)
                                if announcement_date_obj:
                                    break
                
                parent = parent.parent
            
            # Track if we actually parsed a date or are using fallback
            date_was_parsed = announcement_date_obj is not None
            
            # If no date found, use a timestamp based on order (first = latest)
            # This preserves the HTML order which is typically chronological
            if not announcement_date_obj:
                # Use current time minus index seconds to preserve order
                # First announcement gets current time, subsequent ones get slightly older times
                base_time = datetime.now()
                # Subtract seconds based on index to maintain order
                announcement_date_obj = base_time.replace(microsecond=0) - timedelta(seconds=idx)
            
            announcement_date = announcement_date_obj.isoformat()
            
            announcement = {
                "company_name": company_name,
                "company_url": company_url if company_url.startswith('http') else f"https://www.nseindia.com{company_url}" if company_url.startswith('/') else "",
                "pdf_url": pdf_url,
                "announcement_date": announcement_date,
                "announcement_title": announcement_title,
                "source": "nse"
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
    
    # Sort by date (latest first)
    # Parse dates to datetime objects for proper sorting
    def get_sort_key(ann):
        try:
            # Try to parse the ISO date string back to datetime
            date_str = ann['announcement_date']
            # Handle both full ISO format and date-only format
            if 'T' in date_str:
                return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            else:
                return datetime.fromisoformat(date_str)
        except (ValueError, AttributeError):
            # If parsing fails, use a very old date to push to end
            return datetime(1900, 1, 1)
    
    try:
        unique_announcements.sort(key=get_sort_key, reverse=True)
        print(f"✅ Sorted {len(unique_announcements)} unique announcement(s) by date (latest first)")
        if unique_announcements:
            latest_date = unique_announcements[0]['announcement_date']
            print(f"   Latest announcement date: {latest_date[:10] if len(latest_date) > 10 else latest_date}")
    except Exception as e:
        print(f"⚠️  Warning: Failed to sort announcements by date: {e}")
        # Keep original order if sorting fails
    
    return unique_announcements
