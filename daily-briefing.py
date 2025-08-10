#!/usr/bin/env python3

from dotenv import load_dotenv
import os
load_dotenv()
import smtplib
import logging
import json
import time
from openai import OpenAI
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, Any, List
from email.mime.text import MIMEText
from jinja2 import Environment, FileSystemLoader

# ---------------------------
# 1) Configuration
# ---------------------------

# Use Asia/Manila for timezone-aware operations
PHT = ZoneInfo("Asia/Manila")

# Required environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMAIL_USER = os.getenv("EMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
EMAIL_TO = os.getenv("EMAIL_TO", EMAIL_USER)

# Optional environment variables
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))

# Configuration values for the briefing
WATCHLIST_UNIVERSE = ["MSFT", "NVDA", "ETN", "LLY", "NOC", "MA", "ANET", "CRWD"]
OPEN_POSITIONS = {
    "NVDA": 182.72,
    "MSFT": 530.26,
    "ANET": 139.85,
}
RISK_LOWER = 5.5
RISK_UPPER = 7.0

# ---------------------------
# 2) Logging
# ---------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("daily-briefing")

# ---------------------------
# 3) Validation
# ---------------------------

def _require_env(var_name: str, value: Any) -> Any:
    if not value:
        raise RuntimeError(f"Missing required environment variable: {var_name}")
    return value

OPENAI_API_KEY = _require_env("OPENAI_API_KEY", OPENAI_API_KEY)
EMAIL_USER = _require_env("EMAIL_USER", EMAIL_USER)
GMAIL_APP_PASSWORD = _require_env("GMAIL_APP_PASSWORD", GMAIL_APP_PASSWORD)

# ---------------------------
# 4) Prompt
# ---------------------------

def build_prompt(now_pht: datetime) -> str:
    """Builds the market analyst prompt in a structured JSON format."""
    date_str = now_pht.strftime("%A, %B %d, %Y")

    watchlist_items = [
        {"ticker": ticker, "rsi": "number", "macd": "bullish|bearish|neutral", "rank": "string", "action": "string"}
        for ticker in WATCHLIST_UNIVERSE
    ]
    open_positions_items = [
        {"ticker": ticker, "entry_price": entry_price, "current_price": "find current price (number)"}
        for ticker, entry_price in OPEN_POSITIONS.items()
    ]

    return f"""
You are a market analyst. Return ONLY valid JSON, no prose, matching this schema exactly:

{{
  "date": "{date_str}",
  "market_overview": {{
    "sentiment": "string",
    "indexes": {{"sp500": "string", "nasdaq": "string"}},
    "news": ["string", "string"]
  }},
  "watchlist": {json.dumps(watchlist_items)},
  "open_positions": {json.dumps(open_positions_items)},
  "journal": {{
    "did_right": ["string"],
    "improve": ["string"],
    "traps": ["string"]
  }},
  "opportunities": [
    {{
      "ticker": "identify ticker from universe",
      "setup": "oversold bounce|breakout|trend continuation",
      "entry_hint": "string describing entry trigger"
    }}
  ],
  "reminders": [
    "Max risk per trade: {RISK_LOWER:.1f}%–{RISK_UPPER:.1f}%",
    "Stop-loss discipline check",
    "Emotional check-in & predicted mood"
  ]
}}

Guidance:
- Watchlist universe: {', '.join(WATCHLIST_UNIVERSE)}.
- For `open_positions`, find the latest price for the given tickers.
- For `opportunities`, identify new trade setups from the watchlist universe.
- Be concise and realistic with indicators.
- Use USD numbers for entries and prices.
- Do not include any text outside JSON.
""".strip()

# ---------------------------
# 5) Core actions
# ---------------------------

def get_market_briefing_data(prompt: str) -> Dict[str, Any]:
    logger.info("Requesting market briefing JSON via Chat Completions API…")
    client = OpenAI(api_key=OPENAI_API_KEY)
    try:
        response = client.chat.completions.create(
            model="gpt-4o",  # Use a valid and available model, like gpt-4o or gpt-3.5-turbo
            messages=[
                {"role": "system", "content": "You are a helpful assistant that provides a market briefing."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        json_string = response.choices[0].message.content
        return json.loads(json_string)
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        raise RuntimeError("Failed to fetch dynamic data.")

# def get_market_briefing_data(prompt: str) -> Dict[str, Any]:
#     """Fetches market data. Using a dummy response for this example."""
#     logger.info("Requesting market briefing JSON...")

#     # Dummy response for demonstration purposes
#     dummy_response = {
#         "date": "Sunday, August 10, 2025",
#         "market_overview": {
#             "sentiment": "Slightly Bullish",
#             "indexes": {"sp500": "+0.5%", "nasdaq": "+1.2%"},
#             "news": ["Tech earnings beat expectations.", "Inflation data comes in flat."]
#         },
#         "watchlist": [
#             {"ticker": "MSFT", "rsi": 65, "macd": "bullish", "rank": "Excellent", "action": "Buy"},
#             {"ticker": "NVDA", "rsi": 78, "macd": "neutral", "rank": "Bad", "action": "Watch"},
#             {"ticker": "LLY", "rsi": 55, "macd": "bullish", "rank": "Good", "action": "Buy"},
#             {"ticker": "NOC", "rsi": 45, "macd": "bearish", "rank": "Poor", "action": "Sell"},
#             {"ticker": "MA", "rsi": 60, "macd": "neutral", "rank": "Fair", "action": "Hold"},
#             {"ticker": "ANET", "rsi": 70, "macd": "bullish", "rank": "Excellent", "action": "Buy"},
#             {"ticker": "CRWD", "rsi": 58, "macd": "bullish", "rank": "Good", "action": "Buy"},
#             {"ticker": "ETN", "rsi": 40, "macd": "bearish", "rank": "Poor", "action": "Watch"}
#         ],
#         "open_positions": [
#             {"ticker": "NVDA", "entry_price": 182.72, "current_price": 175.10},
#             {"ticker": "MSFT", "entry_price": 530.26, "current_price": 535.50},
#             {"ticker": "ANET", "entry_price": 139.85, "current_price": 145.20},
#         ],
#         "journal": {
#             "did_right": ["Held conviction on MSFT", "Avoided chasing momentum"],
#             "improve": ["Better risk management on NVDA", "Reviewing stop-loss strategy"],
#             "traps": ["Don't chase green candles", "Avoid emotional trading"]
#         },
#         "opportunities": [
#             {"ticker": "ETN", "setup": "breakout", "entry_hint": "Break above $300"},
#             {"ticker": "LLY", "setup": "trend continuation", "entry_hint": "Pullback to 20-day MA"}
#         ],
#         "reminders": [
#             "Max risk per trade: 5.5%–7.0%",
#             "Stop-loss discipline check",
#             "Emotional check-in & predicted mood",
#             "Reviewing macro trends"
#         ]
#     }
    
#     return dummy_response

def send_email(subject: str, body: str) -> None:
    """Sends an email using the configured SMTP server."""
    msg = MIMEText(body, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO

    for attempt in range(5):
        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
                server.starttls()
                server.login(EMAIL_USER, GMAIL_APP_PASSWORD)
                server.sendmail(EMAIL_USER, EMAIL_TO, msg.as_string())
            logger.info("Email sent successfully.")
            return
        except Exception as e:
            delay = 2 ** attempt  # Simple exponential backoff
            logger.warning(f"Email send failed (attempt {attempt+1}): {e}. Retrying in {delay:.1f}s")
            time.sleep(delay)
    raise RuntimeError("Failed to send email after retries.")

def to_currency(value: float) -> str:
    """Jinja filter to format a number as currency."""
    return f"${value:,.2f}"

def daily_job() -> None:
    """Main function to perform the daily briefing task."""
    now_pht = datetime.now(PHT)
    
    # 1. Generate prompt and get data
    prompt = build_prompt(now_pht)
    data = get_market_briefing_data(prompt)
    
    # 2. Build the HTML report using Jinja2
    env = Environment(loader=FileSystemLoader('.'))
    env.filters['to_currency'] = to_currency
    template = env.get_template('email_template.html')
    html_report = template.render(data)

    # 3. Send the email
    subject = f"📊 Daily Market Briefing – {now_pht.strftime('%B %d, %Y')}"
    send_email(subject, html_report)

if __name__ == "__main__":
    daily_job()
