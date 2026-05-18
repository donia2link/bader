from datetime import datetime, timezone


def _utc_hour():
    return datetime.now(timezone.utc).hour


def analyze_session(symbol=None, timeframe=None):
    """
    QuantBado Session Engine v0.1

    UTC-based session logic:
    - Asia: 00:00 - 07:00 UTC
    - London: 07:00 - 12:00 UTC
    - London/New York overlap: 12:00 - 16:00 UTC
    - New York: 16:00 - 21:00 UTC
    - Dead hours: 21:00 - 00:00 UTC
    """

    hour = _utc_hour()

    session_name = "unknown"
    session_status = "unknown"
    session_score = 0
    reason_parts = []

    if 0 <= hour < 7:
        session_name = "asia"
        session_status = "active"
        session_score = 5
        reason_parts.append("Asia session is active")

        if symbol in ["XAUUSD", "EURUSD", "GBPUSD"]:
            session_score -= 5
            reason_parts.append("This symbol may move slower during Asia session")

    elif 7 <= hour < 12:
        session_name = "london"
        session_status = "active"
        session_score = 15
        reason_parts.append("London session is active")

    elif 12 <= hour < 16:
        session_name = "london_new_york_overlap"
        session_status = "high_activity"
        session_score = 20
        reason_parts.append("London and New York overlap is active")

    elif 16 <= hour < 21:
        session_name = "new_york"
        session_status = "active"
        session_score = 15
        reason_parts.append("New York session is active")

    else:
        session_name = "dead_hours"
        session_status = "low_activity"
        session_score = -10
        reason_parts.append("Market is in dead hours")

    if timeframe in ["M1", "M5"] and session_status == "low_activity":
        session_score -= 10
        reason_parts.append("Scalping during dead hours is risky")

    if timeframe in ["H4", "D1"]:
        session_score += 5
        reason_parts.append("Higher timeframe analysis is less sensitive to session noise")

    session_score = max(-30, min(30, session_score))

    return {
        "session_name": session_name,
        "session_status": session_status,
        "session_score": session_score,
        "session_hour_utc": hour,
        "session_reason": " | ".join(reason_parts)
    }


