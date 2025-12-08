"""
PDF Summariser Tool

Provides functionality to summarize PDF text using OpenAI API.
"""

import re
import time
import os
from typing import Dict, Optional

try:
    from openai import OpenAI
except ImportError:
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "openai"])
    from openai import OpenAI


def summarize_pdf_text(
    text: str,
    company_name: str,
    config: Optional[Dict] = None
) -> str:
    """Query OpenAI API for text summarization with a custom prompt."""
    default_config = {
        "api_key": os.getenv("OPENAI_API_KEY"),
        "model": "gpt-3.5-turbo",
        "max_tokens": 1000,
        "temperature": 0.3,
        "max_text_length": 12000,
        "timeout": 60,
    }
    if config:
        default_config.update(config)
    config = default_config
    
    api_key = config.get("api_key")
    if not api_key or api_key.strip() == "":
        return "OpenAI API Error: API key not found. Please set OPENAI_API_KEY environment variable or provide it in config."
    
    cleaned_text = text.strip()
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text)
    
    max_text_length = config.get("max_text_length", 12000)
    if len(cleaned_text) > max_text_length:
        cleaned_text = cleaned_text[:max_text_length] + "..."
    
    if not cleaned_text.strip():
        return "No meaningful text to summarize"
    
    prompt = f"""
                You are acting as a senior equity analyst specializing in Indian stock market corporate disclosures. Your task is to distill and interpret the following disclosure from {company_name}.

                Document:
                {cleaned_text}

                Please produce a summary using the following WhatsApp-optimized structure and rules:

                *Summary:* Write 2–3 sharply concise sentences that capture the single most material announcement(s) or development(s). Prioritize clarity, directness, and the likely intent or impact. Avoid generic language, background, or unnecessary context.

                *Key Points:*
                - List 2–4 numbered or bulleted, highly specific highlights or outcomes.
                - Each bullet should state a concrete fact, decision, or event (e.g., earnings results, deal announcements, board changes, regulatory actions, material incidents, guidance changes).
                - Minimize repetition or generic phrasing. Do not restate from the "Summary."
                - Be maximally informative but extremely concise.

                *Sentiment:* Assign Positive, Negative, or Neutral. Justify in one brief sentence (maximum 100 characters) referencing market, valuation, or investor impact.

                Ensure your response:
                - Contains ONLY these sections, no extra comments or text
                - Strictly follows the format and order above
                - Is always professional, factual, and free from boilerplate
                - Is concise, suitable for WhatsApp broadcast, but do not cut off or truncate the message mid-sentence or mid-point
            """
    
    try:
        client = OpenAI(api_key=config.get("api_key"))
        response = client.chat.completions.create(
            model=config.get("model", "gpt-3.5-turbo"),
            messages=[
                {"role": "system", "content": "You are a professional financial analyst. Provide concise, clear summaries suitable for WhatsApp messages."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=config.get("max_tokens", 1000),
            temperature=config.get("temperature", 0.3),
            timeout=config.get("timeout", 60)
        )
        
        if response.choices and len(response.choices) > 0:
            choice = response.choices[0]
            finish_reason = getattr(choice, 'finish_reason', None)
            
            if finish_reason == 'content_filter':
                return f"*Summary*: Corporate announcement from {company_name}. Full details available in the PDF document.\n\n*Sentiment Analysis*: Neutral - Please review the document for specific details."
            
            content = getattr(choice.message, 'content', None)
            if content and content.strip():
                return content.strip()
            else:
                return f"*Summary*: Corporate announcement from {company_name}. Full details available in the PDF document.\n\n*Sentiment Analysis*: Neutral - Please review the document for specific details."
        else:
            return f"*Summary*: Corporate announcement from {company_name}. Full details available in the PDF document.\n\n*Sentiment Analysis*: Neutral - Please review the document for specific details."
        
    except Exception as e:
        error_str = str(e)
        error_type = type(e).__name__
        
        try:
            from openai import APIConnectionError, APITimeoutError, AuthenticationError, RateLimitError
        except ImportError:
            APIConnectionError = None
            APITimeoutError = None
            AuthenticationError = None
            RateLimitError = None
        
        if (AuthenticationError and isinstance(e, AuthenticationError)) or \
           "authentication" in error_str.lower() or "401" in error_str or \
           "invalid_api_key" in error_str.lower():
            return "OpenAI API Error: Invalid API key. Please check your OPENAI_API_KEY environment variable or config."
        
        elif (APIConnectionError and isinstance(e, APIConnectionError)) or \
             "Connection" in error_type or "connection" in error_str.lower() or \
             "connect" in error_str.lower() or "network" in error_str.lower():
            return "OpenAI API Error: Connection failed. Please check your internet connection."
        
        elif (APITimeoutError and isinstance(e, APITimeoutError)) or \
             "timeout" in error_str.lower() or "Timeout" in error_type:
            return f"OpenAI API Error: Request timed out after {config.get('timeout', 60)} seconds."
        
        elif (RateLimitError and isinstance(e, RateLimitError)) or \
             "rate_limit" in error_str.lower() or "429" in error_str:
            time.sleep(60)
            return summarize_pdf_text(text, company_name, config)
        
        else:
            return f"OpenAI API Error ({error_type}): {error_str}"

