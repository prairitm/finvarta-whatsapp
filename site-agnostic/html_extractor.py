"""
HTML/PDF Extractor Tool

Provides functionality to extract text from PDFs via URL.
"""

import io
import requests
from typing import Dict, Optional

try:
    from PyPDF2 import PdfReader
except ImportError:
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "PyPDF2"])
    from PyPDF2 import PdfReader


def extract_pdf_text_from_url(
    pdf_url: str,
    headers: Optional[Dict[str, str]] = None
) -> str:
    """Extract text from PDF URL."""
    if headers is None:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br'
        }
    
    try:
        response = requests.get(pdf_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        content_type = response.headers.get('Content-Type', '').lower()
        if 'pdf' not in content_type and not response.content.startswith(b'%PDF'):
            if response.content.startswith(b'<') or b'<html' in response.content[:500].lower():
                return f"Request Error: Server returned HTML instead of PDF (Content-Type: {content_type}). The PDF may require authentication or a session."
            return f"Request Error: Server returned non-PDF content (Content-Type: {content_type})"

        with io.BytesIO(response.content) as open_pdf_file:
            reader = PdfReader(open_pdf_file)
            text = ""
            for page in reader.pages:
                text += page.extract_text() or ''
            
            if not text.strip():
                return f"PDF Processing Error: PDF extracted but contains no text (may be image-based or encrypted)"
            
            return text
    except requests.RequestException as e:
        status_code = getattr(e.response, 'status_code', None) if hasattr(e, 'response') else None
        if status_code:
            return f"Request Error: HTTP {status_code} - {e}"
        return f"Request Error: {e}"
    except Exception as e:
        return f"PDF Processing Error: {e}"

