"""
DSA Streak & Problem of the Day Service for Devengers Platform.
Handles catalog loading, daily rotating POTD, and problem filtering.
Zero external dependencies.
"""

import os
import json
import hashlib
from datetime import datetime, timezone, timedelta

SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))
DSA_CATALOG_PATH = os.path.join(SERVICE_DIR, "Assest", "dsa", "dsa_sheet.json")

def get_dsa_catalog():
    if not os.path.exists(DSA_CATALOG_PATH):
        return {"total_problems": 0, "topics": [], "problems": []}
    try:
        with open(DSA_CATALOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[DSAService] Error reading catalog: {e}")
        return {"total_problems": 0, "topics": [], "problems": []}

def get_potd(target_date=None):
    """
    Returns the Problem of the Day (POTD) deterministically for the given or current date.
    Rotates daily at midnight.
    """
    catalog = get_dsa_catalog()
    problems = catalog.get("problems", [])
    if not problems:
        return None

    # Calculate IST Date (UTC + 5:30)
    now_utc = datetime.now(timezone.utc)
    ist_offset = timedelta(hours=5, minutes=30)
    now_ist = now_utc + ist_offset

    date_str = target_date or now_ist.strftime("%Y-%m-%d")
    date_display = now_ist.strftime("%A, %d %B %Y")

    # Deterministic selection based on date string hash
    hash_val = int(hashlib.sha256(date_str.encode("utf-8")).hexdigest(), 16)
    idx = hash_val % len(problems)
    potd_problem = dict(problems[idx])

    # Calculate seconds and milliseconds left until midnight IST
    midnight_ist = (now_ist + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    time_left = midnight_ist - now_ist
    total_seconds_left = max(0, int(time_left.total_seconds()))
    hours_left = total_seconds_left // 3600
    mins_left = (total_seconds_left % 3600) // 60
    secs_left = total_seconds_left % 60

    midnight_utc = midnight_ist - ist_offset
    reset_timestamp_ms = int(midnight_utc.timestamp() * 1000)

    quotes = [
        "Consistent code over chaotic cramming. One problem a day keeps the imposter syndrome away.",
        "Small daily DSA wins compound into FAANG offers.",
        "Master the fundamentals, and every complex algorithm becomes a combination of familiar patterns.",
        "A 30-day streak changes your problem-solving instinct forever.",
        "Code with intent. Understand the space-time tradeoff."
    ]
    quote_idx = hash_val % len(quotes)

    return {
        "date": date_str,
        "formatted_date": date_display,
        "countdown": f"{hours_left:02d}:{mins_left:02d}:{secs_left:02d}",
        "seconds_remaining": total_seconds_left,
        "reset_timestamp_ms": reset_timestamp_ms,
        "quote": quotes[quote_idx],
        "problem": potd_problem
    }
