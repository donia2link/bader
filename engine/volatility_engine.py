def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def analyze_volatility(candles):
    """
    QuantBado Volatility Engine v0.1

    Detects:
    - ATR
    - volatility level
    - expansion / compression
    - dead market
    - volatility score
    """

    if not candles or len(candles) < 30:
        return {
            "volatility": "unknown",
            "atr": 0,
            "atr_ratio": 0,
            "volatility_state": "unknown",
            "volatility_score": 0,
            "dead_market": True,
            "volatility_reason": "Need at least 30 candles for volatility analysis"
        }

    highs = [_safe_float(c["high"]) for c in candles]
    lows = [_safe_float(c["low"]) for c in candles]
    closes = [_safe_float(c["close"]) for c in candles]

    last_close = closes[-1]

    true_ranges = []

    for i in range(1, len(candles)):
        high = highs[i]
        low = lows[i]
        prev_close = closes[i - 1]

        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )

        true_ranges.append(tr)

    if not true_ranges:
        return {
            "volatility": "unknown",
            "atr": 0,
            "atr_ratio": 0,
            "volatility_state": "unknown",
            "volatility_score": 0,
            "dead_market": True,
            "volatility_reason": "Cannot calculate true range"
        }

    atr_period = min(14, len(true_ranges))
    atr = sum(true_ranges[-atr_period:]) / atr_period

    short_period = min(5, len(true_ranges))
    long_period = min(20, len(true_ranges))

    short_atr = sum(true_ranges[-short_period:]) / short_period
    long_atr = sum(true_ranges[-long_period:]) / long_period

    atr_ratio = atr / last_close if last_close else 0

    volatility_score = 0
    reason_parts = []

    if atr_ratio > 0.015:
        volatility = "high"
        volatility_score -= 10
        reason_parts.append("ATR ratio is high")
    elif atr_ratio < 0.003:
        volatility = "low"
        volatility_score -= 5
        reason_parts.append("ATR ratio is low")
    else:
        volatility = "normal"
        volatility_score += 10
        reason_parts.append("ATR ratio is normal")

    if long_atr <= 0:
        volatility_state = "unknown"
    elif short_atr > long_atr * 1.25:
        volatility_state = "expansion"
        volatility_score += 10
        reason_parts.append("Short-term volatility is expanding")
    elif short_atr < long_atr * 0.75:
        volatility_state = "compression"
        volatility_score -= 5
        reason_parts.append("Short-term volatility is compressing")
    else:
        volatility_state = "stable"
        volatility_score += 5
        reason_parts.append("Volatility is stable")

    recent_range = max(highs[-20:]) - min(lows[-20:])
    dead_market = recent_range < atr * 1.2 if atr > 0 else True

    if dead_market:
        volatility_score -= 15
        reason_parts.append("Market movement is too narrow compared to ATR")

    volatility_score = max(-50, min(50, volatility_score))

    return {
        "volatility": volatility,
        "atr": round(atr, 5),
        "atr_ratio": round(atr_ratio, 8),
        "volatility_state": volatility_state,
        "volatility_score": volatility_score,
        "dead_market": dead_market,
        "volatility_reason": " | ".join(reason_parts)
    }

