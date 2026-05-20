from datetime import datetime, timezone


CRYPTO_KEYWORDS = [
    "BTC",
    "ETH",
    "XRP",
    "LTC",
    "BCH",
    "ADA",
    "DOT",
    "SOL",
    "DOGE",
    "BNB",
    "AVAX",
    "MATIC",
    "USDT",
    "USDC"
]


def is_crypto_symbol(symbol):
    symbol = str(symbol).upper()

    for keyword in CRYPTO_KEYWORDS:
        if keyword in symbol:
            return True

    return False


def analyze_session(symbol="", timeframe=""):
    """
    QuantBado Session Engine v0.2

    v0.2:
    - Crypto symbols are treated as 24/7 active markets.
    - Forex/metals still use session-based scoring.
    """

    now = datetime.now(timezone.utc)
    hour = now.hour

    if is_crypto_symbol(symbol):
        return {
            "session_name": "crypto_24_7",
            "session_status": "active",
            "session_score": 10,
            "session_hour_utc": hour,
            "session_reason": "Crypto market is active 24/7"
        }

    # UTC session logic
    if 0 <= hour < 6:
        session_name = "asia"
        session_status = "active"
        session_score = 5
        session_reason = "Asia session is active"

    elif 6 <= hour < 8:
        session_name = "london_open"
        session_status = "active"
        session_score = 15
        session_reason = "London open session is active"

    elif 8 <= hour < 13:
        session_name = "london"
        session_status = "active"
        session_score = 10
        session_reason = "London session is active"

    elif 13 <= hour < 17:
        session_name = "new_york_overlap"
        session_status = "active"
        session_score = 20
        session_reason = "London/New York overlap is active"

    elif 17 <= hour < 21:
        session_name = "new_york"
        session_status = "active"
        session_score = 10
        session_reason = "New York session is active"

    else:
        session_name = "dead_hours"
        session_status = "low_activity"
        session_score = -10
        session_reason = "Market is in dead hours"

    return {
        "session_name": session_name,
        "session_status": session_status,
        "session_score": session_score,
        "session_hour_utc": hour,
        "session_reason": session_reason
    }