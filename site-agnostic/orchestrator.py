"""
Orchestrator

Main orchestrator that combines all tools to process announcements and send WhatsApp messages.
"""

import os
import sys
import json
import hashlib
import re
from typing import Dict, List, Optional
from datetime import datetime

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, current_dir)
    from pdf_summariser import summarize_pdf_text
    from html_extractor import extract_pdf_text_from_url
    from whatsapp_sender import send_whatsapp_message
    from website_adapters.screener_adapter import fetch_screener_announcements
    from website_adapters.nse_adapter import fetch_nse_announcements
    from website_adapters.bse_adapter import fetch_bse_announcements
else:
    from .pdf_summariser import summarize_pdf_text
    from .html_extractor import extract_pdf_text_from_url
    from .whatsapp_sender import send_whatsapp_message
    from .website_adapters.screener_adapter import fetch_screener_announcements
    from .website_adapters.nse_adapter import fetch_nse_announcements
    from .website_adapters.bse_adapter import fetch_bse_announcements


LAST_MESSAGE_FILE = "last_sent_message.json"


def generate_announcement_hash(company_name: str, pdf_url: str) -> str:
    """Generate hash for duplicate detection."""
    content = f"{company_name}|{pdf_url}"
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def generate_message_hash(message: str) -> str:
    """Generate hash for message content, excluding dynamic elements."""
    clean_message = re.sub(r'\*Time:\* \d{4}-\d{2}-\d{2} \d{2}:\d{2}', '', message)
    clean_message = re.sub(r'---\n\*Powered by FinVarta AI\*', '', clean_message)
    clean_message = clean_message.strip()
    return hashlib.md5(clean_message.encode('utf-8')).hexdigest()


def get_last_message_hash() -> Optional[str]:
    """Get hash of last sent message from file."""
    try:
        if os.path.exists(LAST_MESSAGE_FILE):
            with open(LAST_MESSAGE_FILE, 'r') as f:
                data = json.load(f)
                return data.get('last_message_hash')
    except (json.JSONDecodeError, KeyError, IOError):
        pass
    return None


def save_message_hash(message_hash: str) -> None:
    """Save message hash to file for future comparison."""
    try:
        data = {
            'last_message_hash': message_hash,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        with open(LAST_MESSAGE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except IOError:
        pass


def is_duplicate_announcement(company_name: str, pdf_url: str) -> bool:
    """Check if announcement is duplicate of last sent."""
    current_hash = generate_announcement_hash(company_name, pdf_url)
    last_hash = get_last_message_hash()
    return last_hash is not None and current_hash == last_hash


def format_whatsapp_message(
    company_name: str,
    company_url: str,
    pdf_url: str,
    summary: str,
    base_url: str = "https://www.screener.in",
    max_length: int = 1000
) -> str:
    """Format WhatsApp message with company info and summary."""
    if not company_url.startswith("http"):
        company_url = base_url + company_url if company_url.startswith("/") else base_url + "/" + company_url
    
    fixed_parts = f"""Company: {company_name}
{company_url}

Document: {pdf_url}

---
*Powered by FinVarta AI*"""
    
    available_space = max_length - len(fixed_parts)
    if len(summary) > available_space:
        summary = summary[:available_space - 3] + "..."
    
    whatsapp_message = f"""Company: {company_name}
{company_url}

Document: {pdf_url}

{summary}
---
*Powered by FinVarta AI*"""
    
    if len(whatsapp_message) > max_length:
        excess = len(whatsapp_message) - max_length
        summary = summary[:len(summary) - excess - 3] + "..."
        whatsapp_message = f"""Company: {company_name}
{company_url}

Document: {pdf_url}

{summary}
---
*Powered by FinVarta AI*"""
    
    return whatsapp_message


def load_adapter(adapter_name: str):
    """Load website adapter by name."""
    adapters = {
        "screener": fetch_screener_announcements,
        "nse": fetch_nse_announcements,
        "bse": fetch_bse_announcements,
    }
    if adapter_name not in adapters:
        raise ValueError(f"Unknown adapter: {adapter_name}. Available adapters: {list(adapters.keys())}")
    return adapters[adapter_name]


def get_adapter_pdf_headers(adapter_name: str) -> Dict[str, str]:
    """Get adapter-specific headers for PDF extraction."""
    base_headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
        'Accept': 'application/pdf,application/octet-stream,*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }
    referers = {
        "bse": 'https://www.bseindia.com/',
        "nse": 'https://www.nseindia.com/',
        "screener": 'https://www.screener.in/'
    }
    if adapter_name in referers:
        base_headers['Referer'] = referers[adapter_name]
    return base_headers


def process_and_send_announcement(
    adapter_name: str = "screener",
    config: Optional[Dict] = None
) -> bool:
    """
    Main workflow orchestrator that processes announcements and sends WhatsApp messages.
    
    Steps:
    1. Load website adapter based on name
    2. Fetch latest announcement using adapter
    3. Check for duplicates (using hash from last_sent_message.json)
    4. Extract PDF text using html_extractor
    5. Summarize PDF using pdf_summariser
    6. Format WhatsApp message
    7. Send via whatsapp_sender
    8. Save hash for duplicate detection
    
    Args:
        adapter_name: Name of the website adapter to use (default: "screener")
        config: Configuration dictionary containing:
            - openai: OpenAI config (api_key, model, max_tokens, temperature, etc.)
            - twilio: Twilio config (account_sid, auth_token, whatsapp_number)
            - whatsapp_recipients: List of recipient phone numbers
            - adapter: Adapter-specific config (url, cookie_header, timeout, etc.)
            - pdf_headers: Optional headers for PDF download
            - base_url: Base URL for company links (default: https://www.screener.in)
            - max_message_length: Maximum WhatsApp message length (default: 1000)
    
    Returns:
        True if announcement was processed and sent successfully (or duplicate detected),
        False otherwise
    """
    default_config = {
        "base_url": "https://www.screener.in",
        "max_message_length": 1000,
    }
    if config:
        default_config.update(config)
    config = default_config
    
    openai_config = config.get("openai", {})
    twilio_config = config.get("twilio", {})
    adapter_config = config.get("adapter", {})
    recipients = config.get("whatsapp_recipients", [])
    pdf_headers = config.get("pdf_headers") or get_adapter_pdf_headers(adapter_name)
    base_url = config.get("base_url", "https://www.screener.in")
    max_message_length = config.get("max_message_length", 1000)
    
    try:
        adapter_func = load_adapter(adapter_name)
        announcements = adapter_func(adapter_config)
        if not announcements:
            return False
    except Exception:
        return False
    
    latest = announcements[0]
    company_name = latest["company_name"]
    company_url = latest["company_url"]
    pdf_url = latest["pdf_url"]
    
    if is_duplicate_announcement(company_name, pdf_url):
        return True
    
    pdf_text = extract_pdf_text_from_url(pdf_url, pdf_headers)
    
    pdf_extraction_failed = (
        not pdf_text.strip() or 
        pdf_text.startswith("Request Error") or 
        pdf_text.startswith("PDF Processing Error")
    )
    
    if pdf_extraction_failed:
        is_image_based = "image-based" in pdf_text.lower() or "no text" in pdf_text.lower()
        if is_image_based:
            summary = f"*Summary*: Corporate announcement from {company_name}. The PDF document is image-based and requires manual review.\n\n*Sentiment Analysis*: Neutral - Please review the PDF document for specific details.\n\n📎 View PDF: {pdf_url}"
        else:
            summary = f"*Summary*: Corporate announcement from {company_name}. Unable to extract text from PDF (Error: {pdf_text[:100]}).\n\n*Sentiment Analysis*: Neutral - Please review the PDF document for specific details.\n\n📎 View PDF: {pdf_url}"
    else:
        summary = summarize_pdf_text(pdf_text, company_name, openai_config)
        if summary.startswith("OpenAI API Error"):
            text_preview = pdf_text[:500] + "..." if len(pdf_text) > 500 else pdf_text
            summary = f"*Summary*: {text_preview}\n\n*Sentiment Analysis*: Neutral - Please review the full PDF document for complete details.\n\n📎 View PDF: {pdf_url}"
    
    whatsapp_message = format_whatsapp_message(
        company_name=company_name,
        company_url=company_url,
        pdf_url=pdf_url,
        summary=summary,
        base_url=base_url,
        max_length=max_message_length
    )
    
    if send_whatsapp_message(whatsapp_message, recipients, twilio_config):
        announcement_hash = generate_announcement_hash(company_name, pdf_url)
        save_message_hash(announcement_hash)
        return True
    return False


def process_multiple_adapters(
    adapter_names: List[str],
    config: Optional[Dict] = None,
    stop_on_first_send: bool = True
) -> Dict[str, bool]:
    """Process announcements from multiple adapters sequentially."""
    results = {}
    initial_hash = get_last_message_hash()
    
    for adapter_name in adapter_names:
        try:
            success = process_and_send_announcement(adapter_name=adapter_name, config=config)
            results[adapter_name] = success
            
            if success:
                current_hash = get_last_message_hash()
                message_sent = (current_hash is not None and current_hash != initial_hash)
                if message_sent and stop_on_first_send:
                    break
                initial_hash = current_hash
        except Exception:
            results[adapter_name] = False
            continue
    
    return results


def load_config_from_env() -> Dict:
    """Load configuration from environment variables."""
    config = {
        "openai": {
            "api_key": os.getenv("OPENAI_API_KEY"),
            "model": os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
            "max_tokens": int(os.getenv("OPENAI_MAX_TOKENS", "1000")),
            "temperature": float(os.getenv("OPENAI_TEMPERATURE", "0.3")),
            "max_text_length": int(os.getenv("OPENAI_MAX_TEXT_LENGTH", "12000")),
            "timeout": int(os.getenv("OPENAI_TIMEOUT", "60")),
        },
        "twilio": {
            "account_sid": os.getenv("TWILIO_ACCOUNT_SID"),
            "auth_token": os.getenv("TWILIO_AUTH_TOKEN"),
            "whatsapp_number": os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886"),
        },
        "whatsapp_recipients": [
            phone.strip() 
            for phone in os.getenv("WHATSAPP_RECIPIENTS", "").split(",") 
            if phone.strip()
        ],
        "adapter": {
            "cookie_header": os.getenv("SCREENER_COOKIE_HEADER"),
            "url": os.getenv("SCREENER_URL", "https://www.screener.in/announcements/user-filters/192898/"),
            "timeout": int(os.getenv("SCREENER_TIMEOUT", "20")),
        },
        "base_url": os.getenv("BASE_URL", "https://www.screener.in"),
        "max_message_length": int(os.getenv("MAX_MESSAGE_LENGTH", "1000")),
    }
    
    return config


def main():
    """Main entry point for running orchestrator as a script."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    
    config = load_config_from_env()
    
    if not config.get("openai", {}).get("api_key"):
        print("❌ Missing OPENAI_API_KEY")
        sys.exit(1)
    
    if not config.get("twilio", {}).get("account_sid"):
        print("❌ Missing TWILIO_ACCOUNT_SID")
        sys.exit(1)
    
    if not config.get("twilio", {}).get("auth_token"):
        print("❌ Missing TWILIO_AUTH_TOKEN")
        sys.exit(1)
    
    if not config.get("whatsapp_recipients"):
        print("❌ Missing WHATSAPP_RECIPIENTS")
        sys.exit(1)
    
    adapter_env = os.getenv("ADAPTER_NAME", "nse")
    if "," in adapter_env:
        adapter_names = [name.strip() for name in adapter_env.split(",") if name.strip()]
    else:
        adapter_names = [adapter_env.strip()] if adapter_env.strip() else ["nse"]
    
    if len(adapter_names) == 1 and adapter_names[0].lower() == "all":
        adapter_names = ["nse", "bse", "screener"]
    
    if len(adapter_names) == 1:
        success = process_and_send_announcement(adapter_name=adapter_names[0], config=config)
        sys.exit(0 if success else 1)
    else:
        results = process_multiple_adapters(adapter_names=adapter_names, config=config, stop_on_first_send=False)
        sys.exit(0 if any(results.values()) else 1)


if __name__ == "__main__":
    main()

