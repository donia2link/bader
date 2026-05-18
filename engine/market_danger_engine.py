def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def analyze_market_danger(candles):
    """
    QuantBado Market Danger Engine v0.1

    Detects:
    - whipsaw risk
    - fake market risk
    - manipulation risk
    - unstable candle behavior
    """

    if not candles or len(candles) < 30:
        return {
            "danger_level": "unknown",
            "danger_score": 0,
            "whipsaw": False,
            "fake_market": False,
            "manipulation_risk": False,
            "danger_reason": "Need at least 30 candles for danger analysis"
        }

    opens = [_safe_float(c["open"]) for c in candles]
    highs = [_safe_float(c["high"]) for c in candles]
    lows = [_safe_float(c["low"]) for c in candles]
    closes = [_safe_float(c["close"]) for c in candles]

    recent_high = max(highs[-20:])
    recent_low = min(lows[-20:])
    recent_range = max(recent_high - recent_low, 0.00001)

    danger_score = 0
    reason_parts = []

    # 1. Long wick / rejection behavior
    long_wick_count = 0

    for i in range(-10, 0):
        candle_range = max(highs[i] - lows[i], 0.00001)
        body = abs(closes[i] - opens[i])
        upper_wick = highs[i] - max(opens[i], closes[i])
        lower_wick = min(opens[i], closes[i]) - lows[i]

        if upper_wick > body * 2 or lower_wick > body * 2:
            if body < candle_range * 0.45:
                long_wick_count += 1

    if long_wick_count >= 5:
        danger_score += 25
        reason_parts.append("Many recent candles have long wicks, indicating rejection and unstable price action")

    # 2. Whipsaw: frequent direction changes
    direction_changes = 0
    previous_direction = None

    for i in range(-12, 0):
        if closes[i] > opens[i]:
            direction = "bullish"
        elif closes[i] < opens[i]:
            direction = "bearish"
        else:
            direction = "neutral"

        if previous_direction and direction != "neutral" and previous_direction != "neutral":
            if direction != previous_direction:
                direction_changes += 1

        previous_direction = direction

    whipsaw = direction_changes >= 7

    if whipsaw:
        danger_score += 25
        reason_parts.append("Frequent candle direction changes indicate whipsaw risk")

    # 3. Fake market: low body commitment inside range
    weak_body_count = 0

    for i in range(-10, 0):
        candle_range = max(highs[i] - lows[i], 0.00001)
        body = abs(closes[i] - opens[i])

        if body < candle_range * 0.25:
            weak_body_count += 1

    fake_market = weak_body_count >= 6

    if fake_market:
        danger_score += 20
        reason_parts.append("Many candles have weak bodies, indicating low commitment/fake movement")

    # 4. Manipulation risk: sweep both sides recently
    recent_10_high = max(highs[-10:])
    recent_10_low = min(lows[-10:])
    previous_20_high = max(highs[-30:-10])
    previous_20_low = min(lows[-30:-10])

    swept_high = recent_10_high > previous_20_high
    swept_low = recent_10_low < previous_20_low

    manipulation_risk = swept_high and swept_low

    if manipulation_risk:
        danger_score += 30
        reason_parts.append("Price swept both high and low liquidity zones recently")

    # 5. Range instability
    close_position = (closes[-1] - recent_low) / recent_range

    if 0.42 <= close_position <= 0.58 and danger_score >= 30:
        danger_score += 10
        reason_parts.append("Price is trapped near the middle of the range while danger signs are present")

    if danger_score >= 60:
        danger_level = "high"
    elif danger_score >= 30:
        danger_level = "medium"
    else:
        danger_level = "low"

    if not reason_parts:
        reason_parts.append("No major market danger detected")

    danger_score = max(0, min(100, danger_score))

    return {
        "danger_level": danger_level,
        "danger_score": danger_score,
        "whipsaw": whipsaw,
        "fake_market": fake_market,
        "manipulation_risk": manipulation_risk,
        "danger_reason": " | ".join(reason_parts)
    }
