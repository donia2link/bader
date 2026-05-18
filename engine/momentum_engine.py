def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def analyze_momentum(candles):
    """
    QuantBado Momentum Engine v0.1

    Measures:
    - momentum strength
    - direction
    - candle pressure
    - impulse status
    - acceleration
    - momentum score
    """

    if not candles or len(candles) < 20:
        return {
            "momentum": "unknown",
            "momentum_direction": "flat",
            "momentum_score": 0,
            "candle_pressure": "unknown",
            "impulse_status": "unknown",
            "acceleration": "unknown",
            "momentum_reason": "Need at least 20 candles for momentum analysis"
        }

    opens = [_safe_float(c["open"]) for c in candles]
    highs = [_safe_float(c["high"]) for c in candles]
    lows = [_safe_float(c["low"]) for c in candles]
    closes = [_safe_float(c["close"]) for c in candles]

    last_close = closes[-1]

    recent_high = max(highs[-20:])
    recent_low = min(lows[-20:])
    market_range = max(recent_high - recent_low, 0.00001)

    change_3 = closes[-1] - closes[-4]
    change_5 = closes[-1] - closes[-6]
    change_10 = closes[-1] - closes[-11]

    # Direction
    if change_5 > 0:
        momentum_direction = "up"
    elif change_5 < 0:
        momentum_direction = "down"
    else:
        momentum_direction = "flat"

    # Strength
    abs_change_5 = abs(change_5)

    if abs_change_5 > market_range * 0.30:
        momentum = "strong"
        momentum_score = 30
    elif abs_change_5 > market_range * 0.15:
        momentum = "medium"
        momentum_score = 20
    elif abs_change_5 > market_range * 0.05:
        momentum = "weak"
        momentum_score = 10
    else:
        momentum = "dead"
        momentum_score = 0

    # Candle pressure from last 10 candles
    bullish_count = 0
    bearish_count = 0
    bullish_body_total = 0.0
    bearish_body_total = 0.0

    for i in range(-10, 0):
        body = closes[i] - opens[i]

        if body > 0:
            bullish_count += 1
            bullish_body_total += abs(body)
        elif body < 0:
            bearish_count += 1
            bearish_body_total += abs(body)

    if bullish_count >= 7 and bullish_body_total > bearish_body_total:
        candle_pressure = "bullish_pressure"
        momentum_score += 10
    elif bearish_count >= 7 and bearish_body_total > bullish_body_total:
        candle_pressure = "bearish_pressure"
        momentum_score += 10
    else:
        candle_pressure = "mixed_pressure"

    # Impulse detection
    last_body = abs(closes[-1] - opens[-1])
    avg_body = sum(abs(closes[i] - opens[i]) for i in range(-10, 0)) / 10

    if avg_body <= 0:
        impulse_status = "no_impulse"
    elif last_body > avg_body * 1.8:
        impulse_status = "impulse_candle"
        momentum_score += 10
    else:
        impulse_status = "normal_candle"

    # Acceleration
    if abs(change_3) > abs(change_5) * 0.65 and abs(change_5) > abs(change_10) * 0.55:
        acceleration = "accelerating"
        momentum_score += 10
    elif abs(change_3) < abs(change_5) * 0.35:
        acceleration = "slowing"
        momentum_score -= 5
    else:
        acceleration = "stable"

    momentum_score = max(0, min(100, momentum_score))

    reason_parts = [
        "Momentum direction is " + momentum_direction,
        "Momentum strength is " + momentum,
        "Candle pressure is " + candle_pressure,
        "Impulse status is " + impulse_status,
        "Acceleration is " + acceleration
    ]

    return {
        "momentum": momentum,
        "momentum_direction": momentum_direction,
        "momentum_score": momentum_score,
        "candle_pressure": candle_pressure,
        "impulse_status": impulse_status,
        "acceleration": acceleration,
        "momentum_reason": " | ".join(reason_parts)
    }


