#!/usr/bin/env python3
"""
Twilio WhatsApp Announcement Processor
Sends the latest corporate announcement via Twilio WhatsApp API

This script:
1. Fetches HTML from screener.in announcements page
2. Extracts the latest company-PDF pair from the HTML
3. Downloads and processes the PDF using Docker-hosted model for summarization
4. Sends the summary via Twilio WhatsApp API

Usage:
    python3 twilio_whatsapp_processor.py           # Process latest announcement
    python3 twilio_whatsapp_processor.py test      # Test mode (use sample data)
    python3 twilio_whatsapp_processor.py sample    # Sample mode (use sample data)

Requirements:
    - Twilio account with WhatsApp API access
    - twilio library: pip install twilio
    - python-dotenv library: pip install python-dotenv
    - Environment variables configured in .env file
"""

import requests
import time
import io
import re
import json
import os
import hashlib
from typing import Dict, Optional, List, Tuple
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Try to import openai, install if not available
try:
    from openai import OpenAI
except ImportError:
    print("❌ openai library not found. Installing...")
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "openai"])
    from openai import OpenAI

# Try to import twilio, install if not available
try:
    from twilio.rest import Client
except ImportError:
    print("❌ twilio library not found. Installing...")
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "twilio"])
    from twilio.rest import Client

# Configuration - Load from environment variables
# Docker Model Configuration
DOCKER_MODEL_BASE_URL = os.getenv("DOCKER_MODEL_BASE_URL", "http://localhost:12434/engines/llama.cpp/v1")
DOCKER_MODEL_API_KEY = os.getenv("DOCKER_MODEL_API_KEY", "dummy_value")
DEFAULT_MODEL = os.getenv("DOCKER_MODEL", "ai/mistral")
MAX_TOKENS = int(os.getenv("DOCKER_MAX_TOKENS", "1000"))
TEMPERATURE = float(os.getenv("DOCKER_TEMPERATURE", "0.3"))
MAX_TEXT_LENGTH = int(os.getenv("DOCKER_MAX_TEXT_LENGTH", "12000"))
DELAY_BETWEEN_REQUESTS = int(os.getenv("DELAY_BETWEEN_REQUESTS", "2"))

# Initialize OpenAI client with custom base_url for local Docker model
docker_model_client = OpenAI(
    api_key=DOCKER_MODEL_API_KEY,
    base_url=DOCKER_MODEL_BASE_URL
)

# Twilio Configuration - Load from environment variables
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")

# Recipients - Load from environment variables (comma-separated string)
WHATSAPP_RECIPIENTS_STR = os.getenv("WHATSAPP_RECIPIENTS", "")
WHATSAPP_RECIPIENTS = [phone.strip() for phone in WHATSAPP_RECIPIENTS_STR.split(",") if phone.strip()] if WHATSAPP_RECIPIENTS_STR else []

# File to store last sent message hash
LAST_MESSAGE_FILE = "last_sent_message.json"

# PDF regex pattern
PDF_REGEX = re.compile(r"\.pdf(?:[#?].*)?$", re.IGNORECASE)


def parse_cookie_header(cookie_header: str) -> Dict[str, str]:
    """
    Convert a raw 'Cookie:' header string into a dict for requests.
    """
    cookies = {}
    for part in cookie_header.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


def generate_announcement_hash(company_name: str, pdf_url: str) -> str:
    """
    Generate a hash based on the announcement (company and PDF URL only).
    This is the most efficient way to detect duplicates without processing PDF content.
    """
    # Create a hash based on company and PDF URL only
    content = f"{company_name}|{pdf_url}"
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def generate_message_hash(message: str) -> str:
    """
    Generate a hash for the message content to detect duplicates.
    Excludes timestamp and other dynamic content
    """
    # Remove timestamp and other dynamic content for consistent hashing
    clean_message = re.sub(r'\*Time:\* \d{4}-\d{2}-\d{2} \d{2}:\d{2}', '', message)
    clean_message = re.sub(r'---\n\*Powered by FinVarta AI\*', '', clean_message)
    clean_message = clean_message.strip()
    
    return hashlib.md5(clean_message.encode('utf-8')).hexdigest()


def get_last_message_hash() -> Optional[str]:
    """
    Get the hash of the last sent message from file.
    
    Returns:
        Hash string if file exists and contains valid data, None otherwise
    """
    try:
        if os.path.exists(LAST_MESSAGE_FILE):
            with open(LAST_MESSAGE_FILE, 'r') as f:
                data = json.load(f)
                return data.get('last_message_hash')
    except (json.JSONDecodeError, KeyError, IOError) as e:
        print(f"⚠️  Warning: Could not read last message file: {e}")
    return None


def save_message_hash(message_hash: str) -> None:
    """
    Save the message hash to file for future comparison.
    
    Args:
        message_hash: Hash of the message that was sent
    """
    try:
        data = {
            'last_message_hash': message_hash,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        with open(LAST_MESSAGE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"✅ Message hash saved for future duplicate detection")
    except IOError as e:
        print(f"⚠️  Warning: Could not save message hash: {e}")


def is_duplicate_announcement(company_name: str, pdf_url: str) -> bool:
    """
    Check if the current announcement is the same as the last sent announcement.
    
    Args:
        company_name: Name of the company
        pdf_url: URL of the PDF
        
    Returns:
        True if this is a duplicate announcement, False otherwise
    """
    current_hash = generate_announcement_hash(company_name, pdf_url)
    last_hash = get_last_message_hash()
    
    if last_hash is None:
        print("📝 No previous announcement found - this will be the first announcement")
        return False
    
    is_duplicate = current_hash == last_hash
    if is_duplicate:
        print("🔄 Duplicate announcement detected - skipping send")
    else:
        print("📝 New announcement detected - proceeding with send")
    
    return is_duplicate


def is_duplicate_message(message: str) -> bool:
    """
    Check if the current message is the same as the last sent message.
    
    Args:
        message: Current message content
        
    Returns:
        True if this is a duplicate message, False otherwise
    """
    current_hash = generate_message_hash(message)
    last_hash = get_last_message_hash()
    
    if last_hash is None:
        print("📝 No previous message found - this will be the first message")
        return False
    
    is_duplicate = current_hash == last_hash
    if is_duplicate:
        print("🔄 Duplicate message detected - skipping send")
    else:
        print("📝 New message detected - proceeding with send")
    
    return is_duplicate


def get_screener_announcements(
    cookie_header: Optional[str] = None,
    timeout: int = 20
) -> str:
    """
    Fetches https://www.screener.in/announcements/ and returns the HTML as text.
    """
    url = "https://www.screener.in/announcements/user-filters/192898/"

    # Headers mirroring your browser request
    headers = {
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
    }

    cookies = parse_cookie_header(cookie_header) if cookie_header else None

    with requests.Session() as s:
        resp = s.get(url, headers=headers, cookies=cookies, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        
        return resp.text


def extract_latest_announcement(html_text: str) -> Optional[Tuple[str, str]]:
    """
    Extract the latest company-PDF pair from HTML content.
    
    Args:
        html_text: HTML content as string
        
    Returns:
        Tuple of (company_url, pdf_url) for the latest announcement, or None if not found
    """
    # Parse HTML
    soup = BeautifulSoup(html_text, "lxml")

    # Collect hrefs
    all_links = soup.find_all("a")
    hrefs = [a.get("href").strip() for a in all_links if a.get("href")]
    
    if len(hrefs) == 0:
        return None
    
    # Look for consecutive company -> pdf pairs
    found_pairs = []
    for i in range(len(hrefs) - 1):
        if "/company" in hrefs[i] and PDF_REGEX.search(hrefs[i + 1]):
            pair = (hrefs[i], hrefs[i + 1])
            found_pairs.append(pair)
    
    if found_pairs:
        return found_pairs[0]
    
    return None


def test_docker_model_connection() -> bool:
    """Test if Docker model is accessible before making actual requests"""
    try:
        # Extract base host and port from DOCKER_MODEL_BASE_URL
        from urllib.parse import urlparse
        parsed = urlparse(DOCKER_MODEL_BASE_URL)
        base_host = parsed.hostname or "localhost"
        base_port = parsed.port or 12434
        
        # Try a simple socket connection test
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex((base_host, base_port))
        sock.close()
        
        return result == 0
    except Exception:
        return False


def query_docker_model(text: str, company_name: str) -> str:
    """Query Docker-hosted model API for text summarization with a custom prompt"""
    
    # Clean and truncate text to avoid token limits
    cleaned_text = text.strip()
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text)
    
    # Truncate if too long (model has token limits)
    if len(cleaned_text) > MAX_TEXT_LENGTH:
        cleaned_text = cleaned_text[:MAX_TEXT_LENGTH] + "..."
        print(f"Text truncated to {len(cleaned_text)} characters")
    
    if not cleaned_text.strip():
        return "No meaningful text to summarize"
    
    # Create a concise prompt for WhatsApp message
    prompt = f"""
                You are a financial analyst specializing in Indian stock market announcements. Please analyze and summarize the following corporate announcement document for {company_name}.

                Document Text:
                {cleaned_text}

                Please provide a structured summary that includes:

                1. *Summary*: A concise 2-3 sentence summary of the most important information

                2. *Sentiment Analysis*: Assess the overall sentiment of the announcement (e.g., Positive, Negative, Neutral) and briefly explain your reasoning. Keep it under 100 characters.

                Format your response as a clear, structured summary that would be useful for investors and analysts. Keep it under 1000 characters.
            """

    # Test connection first
    if not test_docker_model_connection():
        error_msg = f"Docker Model Connection Error: Cannot connect to {DOCKER_MODEL_BASE_URL}. Is the Docker model running?"
        print(f"\n❌ {error_msg}")
        print("\n💡 TROUBLESHOOTING:")
        print("   1. Make sure your local LLM server is running")
        print("   2. Check if the service is listening on the correct port")
        print("   3. Verify DOCKER_MODEL_BASE_URL environment variable is correct")
        print(f"   4. Current DOCKER_MODEL_BASE_URL: {DOCKER_MODEL_BASE_URL}")
        print("\n   To check if your service is running:")
        print(f"   - Try: curl http://localhost:12434/engines/llama.cpp/v1/models")
        print("   - Or check with: lsof -i :12434")
        print("   - Or check with: netstat -an | grep 12434")
        return error_msg
    
    try:
        # Use OpenAI client with custom base_url
        # Note: The client will append /chat/completions to the base_url
        response = docker_model_client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": "You are a professional financial analyst. Provide concise, clear summaries suitable for WhatsApp messages."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            timeout=60
        )
        
        # Extract response content
        if response.choices and len(response.choices) > 0:
            return response.choices[0].message.content.strip()
        else:
            return f"Docker Model Error: Unexpected response format: {response}"
        
    except Exception as e:
        error_str = str(e)
        error_type = type(e).__name__
        print(f"❌ Error ({error_type}): {error_str}")
        
        # Check for connection errors
        if "Connection" in error_type or "connection" in error_str.lower() or "refused" in error_str.lower():
            print(f"❌ Connection Error: Cannot connect to Docker model at {DOCKER_MODEL_BASE_URL}")
            print("\n💡 TROUBLESHOOTING:")
            print("   1. Make sure your Docker model is running")
            print("   2. Check if the model is accessible at the configured URL")
            print("   3. Verify DOCKER_MODEL_BASE_URL environment variable is correct")
            print(f"   4. Current DOCKER_MODEL_BASE_URL: {DOCKER_MODEL_BASE_URL}")
            print("\n   The OpenAI client will call:")
            print(f"   {DOCKER_MODEL_BASE_URL}/chat/completions")
            print("\n   To test manually:")
            print(f"   curl -X POST {DOCKER_MODEL_BASE_URL}/chat/completions \\")
            print(f"     -H 'Content-Type: application/json' \\")
            print(f"     -d '{{\"model\":\"{DEFAULT_MODEL}\",\"messages\":[{{\"role\":\"user\",\"content\":\"test\"}}]}}'")
            return f"Docker Model Connection Error: Cannot connect to {DOCKER_MODEL_BASE_URL}. Is the Docker model running?"
        
        # Check for timeout errors
        elif "timeout" in error_str.lower() or "Timeout" in error_type:
            print(f"❌ Timeout Error: Request to {DOCKER_MODEL_BASE_URL} timed out after 60 seconds")
            return f"Docker Model Timeout Error: Request timed out. The model may be overloaded or slow."
        
        # Check for rate limit errors
        elif "rate_limit" in error_str.lower() or "429" in error_str:
            print("⚠️  Rate limit exceeded, waiting 60 seconds...")
            time.sleep(60)
            return query_docker_model(text, company_name)  # Retry once
        
        # Other errors
        else:
            return f"Docker Model Error ({error_type}): {error_str}"


def extract_pdf_text(url: str, headers: Dict[str, str]) -> str:
    """Extract text from PDF URL"""
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        with io.BytesIO(response.content) as open_pdf_file:
            reader = PdfReader(open_pdf_file)
            text = ""
            for page in reader.pages:
                text += page.extract_text() or ''
            return text
    except requests.RequestException as e:
        return f"Request Error: {e}"
    except Exception as e:
        return f"PDF Processing Error: {e}"


def get_company_name_from_url(company_url: str) -> str:
    """Extract company name from URL"""
    match = re.search(r'/company/([^/]+)/?', company_url)
    if match:
        return match.group(1)
    return "Unknown Company"


def get_sample_html_data() -> str:
    """Return sample HTML data for testing purposes"""
    return """
<div>
  <div class="card card-medium">
    <div class="sub margin-bottom-16">Today</div>
    
      <div class="bordered rounded padding-12-18 announcement-item margin-top-12">
        <div class="flex flex-gap-16">
          <img class="img-32" src="https://cdn-static.screener.in/icons/announcement.0a7339d57d0a.svg" alt="press release">
          <div class="flex flex-column">
            <a href="/company/MAHSCOOTER/" class="font-weight-500 font-size-14 sub-link" target="_blank">
              <span class="ink-900 hover-link">Mah. Scooters</span>
              <i class="icon-link-ext"></i>
            </a>
            <a href="https://www.bseindia.com/stockinfo/AnnPdfOpen.aspx?Pname=0b1f42b4-9fae-4035-af80-0ebf86322ba5.pdf" target="_blank" rel="noopener noreferrer">
              Intimation Under Regulation 42 Of The SEBI (LODR) Regulations, 2015 - Record Date
              <i class="icon-file-pdf font-size-14"></i>
              
                <span class="ink-600 smaller">25m ago</span>
              
                <div class="sub">Interim dividend Rs160 per share; record date 22 Sep 2025; payout ~13 Oct 2025; Company Secretary appointed 1 Oct.</div>
              
            </a>
          </div>
        </div>
      </div>
    
      <div class="bordered rounded padding-12-18 announcement-item margin-top-12">
        <div class="flex flex-gap-16">
          <img class="img-32" src="https://cdn-static.screener.in/icons/announcement.0a7339d57d0a.svg" alt="press release">
          <div class="flex flex-column">
            <a href="/company/TCS/consolidated/" class="font-weight-500 font-size-14 sub-link" target="_blank">
              <span class="ink-900 hover-link">TCS</span>
              <i class="icon-link-ext"></i>
            </a>
            <a href="https://www.bseindia.com/stockinfo/AnnPdfOpen.aspx?Pname=030da518-31d8-4310-9aa8-64d1212a352f.pdf" target="_blank" rel="noopener noreferrer">
              Press Release - The Warehouse Group Selects TCS To Lead Strategic IT Transformation Initiatives
              <i class="icon-file-pdf font-size-14"></i>
              
                <span class="ink-600 smaller">48m ago</span>
              
                <div class="sub">TCS to modernise TWG's IT; partnership estimated to cut licenses/managed services costs by up to $40 million over five years.</div>
              
            </a>
          </div>
        </div>
      </div>
    
  </div>
</div>
"""


def send_twilio_whatsapp_message(message: str, recipients: List[str]) -> bool:
    """
    Send WhatsApp message via Twilio API to multiple recipients
    
    Args:
        message: Message content to send
        recipients: List of phone numbers with country code
        
    Returns:
        True if at least one message was sent successfully, False otherwise
    """
    print("📱 Sending WhatsApp messages via Twilio...")
    
    # Check if Twilio credentials are configured
    if (TWILIO_ACCOUNT_SID == "your_twilio_account_sid" or 
        TWILIO_AUTH_TOKEN == "your_twilio_auth_token"):
        print("⚠️  Twilio credentials not configured. Please update TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in the script.")
        print("   Get your credentials from: https://console.twilio.com/")
        return False
    
    # Check if recipients are configured
    if not recipients or recipients == ["+1234567890"]:
        print("⚠️  WhatsApp recipients not configured. Please update WHATSAPP_RECIPIENTS in the script.")
        return False
    
    try:
        # Initialize Twilio client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        successful_sends = 0
        
        for recipient in recipients:
            try:
                print(f"📤 Sending message to: {recipient}")
                
                # Send WhatsApp message
                message_obj = client.messages.create(
                    body=message,
                    from_=TWILIO_WHATSAPP_NUMBER,
                    to=f"whatsapp:{recipient}"
                )
                
                successful_sends += 1
                print(f"✅ Message sent to: {recipient} (SID: {message_obj.sid})")
                
                # Add small delay between recipients
                if len(recipients) > 1:
                    time.sleep(1)
                    
            except Exception as e:
                print(f"❌ Error sending message to {recipient}: {e}")
        
        print(f"✅ Successfully sent {successful_sends} out of {len(recipients)} messages")
        return successful_sends > 0
        
    except Exception as e:
        print(f"❌ Error connecting to Twilio: {e}")
        return False


def process_latest_announcement(cookie_header: Optional[str] = None, use_sample_data: bool = False):
    """
    Main function to process the latest announcement and send via Twilio WhatsApp
    
    Args:
        cookie_header: Optional cookie header for authentication
        use_sample_data: If True, use sample HTML data instead of fetching from web
        
    Returns:
        True if announcement was processed and sent successfully, False otherwise
    """
    
    # Download headers for PDF requests
    download_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br'
    }
    
    print("=" * 80)
    print("TWILIO WHATSAPP ANNOUNCEMENT PROCESSOR")
    print("=" * 80)
    
    # Step 1: Get HTML content
    if use_sample_data:
        print("Step 1: Using sample HTML data...")
        html_content = get_sample_html_data()
        print(f"✅ Sample HTML data loaded ({len(html_content)} characters)")
    else:
        print("Step 1: Fetching HTML from screener.in...")
        try:
            html_content = get_screener_announcements(cookie_header)
            print(f"✅ HTML fetched successfully ({len(html_content)} characters)")
        except Exception as e:
            print(f"❌ Failed to fetch HTML: {e}")
            return False
    
    # Step 2: Extract latest announcement
    print("\nStep 2: Extracting latest announcement...")
    latest_announcement = extract_latest_announcement(html_content)
    
    if not latest_announcement:
        print("❌ No announcements found")
        return False
    
    company_url, pdf_url = latest_announcement
    company_name = get_company_name_from_url(company_url)
    
    print(f"✅ Found latest announcement: {company_name}")
    print(f"Company URL: https://www.screener.in{company_url}")
    print(f"PDF URL: {pdf_url}")
    
    # Step 3: Check for duplicate announcement (before any processing)
    print("\nStep 3: Checking for duplicate announcement...")
    
    if is_duplicate_announcement(company_name, pdf_url):
        print("🔄 Duplicate announcement detected - skipping send to avoid spam")
        print("✅ Process completed (no duplicate sent)")
        return True  # Return True as this is a successful "no-send" scenario
    
    # Step 4: Process PDF
    print("\nStep 4: Processing PDF...")
    pdf_text = extract_pdf_text(pdf_url, download_headers)
    
    if not pdf_text.strip() or pdf_text.startswith("Request Error") or pdf_text.startswith("PDF Processing Error"):
        print(f"❌ Failed to extract PDF text: {pdf_text}")
        return False
    
    print("✅ PDF text extracted successfully")
    
    # Step 5: Generate AI summary
    print("\nStep 5: Generating AI summary...")
    summary = query_docker_model(pdf_text, company_name)
    
    if summary.startswith("Docker Model") and "Error" in summary:
        print(f"❌ Failed to generate summary: {summary}")
        return False
    
    print("✅ AI summary generated successfully")
    
    # Step 6: Format WhatsApp message
    print("\nStep 6: Formatting WhatsApp message...")
    
    # Calculate fixed parts of the message (excluding summary)
    fixed_parts = f"""Company: {company_name}
https://www.screener.in{company_url}

Document: {pdf_url}

---
*Powered by FinVarta AI*"""
    
    # Calculate available space for summary (1000 char limit)
    available_space = 1000 - len(fixed_parts)
    
    # Truncate summary if needed
    if len(summary) > available_space:
        truncated_summary = summary[:available_space - 3] + "..."
        print(f"⚠️  Summary truncated to fit 1000 character limit ({len(summary)} -> {len(truncated_summary)} chars)")
        summary = truncated_summary
    
    # Create a formatted message for WhatsApp
    whatsapp_message = f"""Company: {company_name}
https://www.screener.in{company_url}

Document: {pdf_url}

{summary}
---
*Powered by FinVarta AI*"""
    
    # Final check to ensure message is under 1000 characters
    if len(whatsapp_message) > 1000:
        # More aggressive truncation if still over limit
        excess = len(whatsapp_message) - 1000
        summary = summary[:len(summary) - excess - 3] + "..."
        whatsapp_message = f"""Company: {company_name}
https://www.screener.in{company_url}

Document: {pdf_url}

{summary}
---
*Powered by FinVarta AI*"""
        print(f"⚠️  Message truncated to exactly 1000 characters")
    
    print(f"✅ WhatsApp message formatted ({len(whatsapp_message)} characters)")
    print("\n" + "=" * 80)
    print("MESSAGE TO BE SENT:")
    print("=" * 80)
    print(whatsapp_message)
    print("=" * 80 + "\n")
    
    # Step 7: Send WhatsApp message via Twilio
    print("\nStep 7: Sending WhatsApp message via Twilio...")
    
    if send_twilio_whatsapp_message(whatsapp_message, WHATSAPP_RECIPIENTS):
        print("✅ WhatsApp message sent successfully")
        
        # Save announcement hash for future duplicate detection
        announcement_hash = generate_announcement_hash(company_name, pdf_url)
        save_message_hash(announcement_hash)
        
        return True
    else:
        print("❌ Failed to send WhatsApp message")
        return False


def validate_environment_variables():
    """
    Validate that all required environment variables are set.
    
    Returns:
        True if all required variables are set, False otherwise
    """
    required_vars = {
        "DOCKER_MODEL_BASE_URL": DOCKER_MODEL_BASE_URL,
        "TWILIO_ACCOUNT_SID": TWILIO_ACCOUNT_SID,
        "TWILIO_AUTH_TOKEN": TWILIO_AUTH_TOKEN,
    }
    
    missing_vars = []
    for var_name, var_value in required_vars.items():
        if not var_value:
            missing_vars.append(var_name)
    
    if missing_vars:
        print("❌ Missing required environment variables:")
        for var in missing_vars:
            print(f"   - {var}")
        print("\nPlease create a .env file with the required variables.")
        print("Copy .env.example to .env and fill in your values.")
        return False
    
    # Check if recipients are configured
    if not WHATSAPP_RECIPIENTS:
        print("⚠️  Warning: WHATSAPP_RECIPIENTS not configured.")
        print("   Add phone numbers to WHATSAPP_RECIPIENTS in your .env file.")
        return False
    
    return True


def show_help():
    """Show usage help"""
    print("""
📱 TWILIO WHATSAPP ANNOUNCEMENT PROCESSOR
=========================================

This script processes the latest corporate announcement from screener.in and sends it via Twilio WhatsApp API.

USAGE:
    python3 twilio_whatsapp_processor.py [mode]

MODES:
    (no mode)     Process latest announcement from screener.in
    test          Use sample HTML data (for testing without web requests)
    sample        Use sample HTML data (same as test)

REQUIREMENTS:
    - Twilio account with WhatsApp API access
    - twilio library: pip install twilio
    - python-dotenv library: pip install python-dotenv
    - Docker-hosted model running with OpenAI-compatible API endpoint

CONFIGURATION:
    Before using, create a .env file with these settings:
    - DOCKER_MODEL_BASE_URL: Base URL of your Docker-hosted model API (default: http://localhost:12434/engines/llama.cpp/v1)
    - DOCKER_MODEL_API_KEY: API key for Docker model (default: dummy_value)
    - DOCKER_MODEL: Model name to use (default: ai/smollm2)
    - TWILIO_ACCOUNT_SID: Your Twilio Account SID
    - TWILIO_AUTH_TOKEN: Your Twilio Auth Token
    - WHATSAPP_RECIPIENTS: Comma-separated phone numbers with country code
    - TWILIO_WHATSAPP_NUMBER: Your Twilio WhatsApp number (optional)

SETUP STEPS:
    1. Copy .env.example to .env: cp .env.example .env
    2. Edit .env file with your actual credentials
    3. Create a Twilio account at https://www.twilio.com/
    4. Get your Account SID and Auth Token from the Twilio Console
    5. Enable WhatsApp API in your Twilio account
    6. For testing, use the Twilio Sandbox number
    7. For production, get your own WhatsApp Business number

EXAMPLES:
    python3 twilio_whatsapp_processor.py                    # Process latest announcement
    python3 twilio_whatsapp_processor.py test               # Test mode (sample data)
    python3 twilio_whatsapp_processor.py sample             # Sample mode (sample data)

OUTPUTS:
    - WhatsApp message with latest announcement summary
    - Console output showing processing steps
    - Duplicate detection to avoid sending the same message twice

FEATURES:
    - Automatic duplicate detection using message hashing
    - Stores last sent message hash in last_sent_message.json
    - Skips sending if the same announcement is detected again
    """)


def main():
    """Main entry point"""
    import sys
    
    # Check for help request
    if len(sys.argv) > 1 and sys.argv[1] in ["-h", "--help", "help"]:
        show_help()
        return
    
    # Validate environment variables
    if not validate_environment_variables():
        sys.exit(1)
    
    # Parse command line arguments
    sample_mode = len(sys.argv) > 1 and sys.argv[1] in ["test", "sample"]
    
    if sample_mode:
        print("📄 Running in SAMPLE MODE (using sample HTML data)")
    
    # Optional cookie header for authentication (load from environment variable)
    cookie_header = os.getenv("SCREENER_COOKIE_HEADER")
    
    # Process latest announcement
    success = process_latest_announcement(cookie_header=cookie_header, use_sample_data=sample_mode)
    
    if success:
        print("\n" + "=" * 80)
        print("✅ PROCESS COMPLETED SUCCESSFULLY")
        print("=" * 80)
    else:
        print("\n" + "=" * 80)
        print("❌ PROCESS FAILED")
        print("=" * 80)


if __name__ == "__main__":
    main()
