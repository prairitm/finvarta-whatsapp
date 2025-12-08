"""
Site-Agnostic Modular Tools

This package provides modular, reusable tools for processing corporate announcements:
- PDF summarization
- HTML/PDF text extraction
- WhatsApp message sending
- Website-specific adapters for fetching announcements
- Orchestrator for combining all tools
"""

from .pdf_summariser import summarize_pdf_text
from .html_extractor import extract_pdf_text_from_url
from .whatsapp_sender import send_whatsapp_message
from .orchestrator import process_and_send_announcement, load_config_from_env

__all__ = [
    'summarize_pdf_text',
    'extract_pdf_text_from_url',
    'send_whatsapp_message',
    'process_and_send_announcement',
    'load_config_from_env',
]

