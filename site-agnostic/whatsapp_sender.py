"""
WhatsApp Sender Tool

Provides functionality to send WhatsApp messages via Twilio API.
"""

import time
from typing import List, Dict, Optional

try:
    from twilio.rest import Client
except ImportError:
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "twilio"])
    from twilio.rest import Client


def send_whatsapp_message(
    message: str,
    recipients: List[str],
    config: Optional[Dict] = None
) -> bool:
    """Send WhatsApp message via Twilio API to multiple recipients."""
    default_config = {
        "whatsapp_number": "whatsapp:+14155238886",
    }
    if config:
        default_config.update(config)
    config = default_config
    
    account_sid = config.get("account_sid")
    auth_token = config.get("auth_token")
    whatsapp_number = config.get("whatsapp_number", "whatsapp:+14155238886")
    
    if not account_sid or not auth_token or not recipients:
        return False
    
    try:
        client = Client(account_sid, auth_token)
        successful_sends = 0
        
        for recipient in recipients:
            try:
                client.messages.create(
                    body=message,
                    from_=whatsapp_number,
                    to=f"whatsapp:{recipient}"
                )
                successful_sends += 1
                if len(recipients) > 1:
                    time.sleep(1)
            except Exception:
                continue
        
        return successful_sends > 0
    except Exception:
        return False

