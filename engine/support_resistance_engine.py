def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _atr(candles, period=14):
    highs = [_safe_float(c["high"]) for c in candles]
    lows = [_safe_float(c["low"]) for c in candles]
    closes = [_safe_float(c["close"]) for c in candles]

    true_ranges = []

    for i in range(1, len(candles)):
        high = highs[i]
        low = lows[i]
        prev_close = closes[i - 1]

        true_ranges.append(
            max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
        )

    if not true_ranges:
        return 0.0

    period = min(period, len(true_ranges))
    return sum(true_ranges[-period:]) / period


def analyze_support_resistance(candles):
    """
    QuantBado Support & Resistance Engine v0.1

    Detects:
    - support
    - resistance
    - strength of each zone
    - nearest zone
    - zone risk
    - SR score
    """

    if not candles or len(candles) < 30:
        return {
            "support": 0,
            "resistance": 0,
            "support_strength": 0,
            "resistance_strength": 0,
            "nearest_zone": "unknown",
            "zone_risk": "high",
            "sr_score": 0,
            "sr_reason": "Need at least 30 candles for support and resistance analysis"
        }

    highs = [_safe_float(c["high"]) for c in candles]
    lows = [_safe_float(c["low"]) for c in candles]
    closes = [_safe_float(c["close"]) for c in candles]

    last_close = closes[-1]

    lookback = 30
    recent_highs = highs[-lookback:]
    recent_lows = lows[-lookback:]

    support = min(recent_lows)
    resistance = max(recent_highs)

    atr = _atr(candles)
    if atr <= 0:
        atr = max(resistance - support, 0.00001) / 10

    zone_tolerance = atr * 0.35

    support_touches = 0
    resistance_touches = 0

    for low in recent_lows:
        if abs(low - support) <= zone_tolerance:
            support_touches += 1

    for high in recent_highs:
        if abs(high - resistance) <= zone_tolerance:
            resistance_touches += 1

    support_strength = min(100, support_touches * 15)
    resistance_strength = min(100, resistance_touches * 15)

    distance_to_support = abs(last_close - support)
    distance_to_resistance = abs(resistance - last_close)

    if distance_to_support < distance_to_resistance:
        nearest_zone = "support"
        nearest_distance = distance_to_support
    elif distance_to_resistance < distance_to_support:
        nearest_zone = "resistance"
        nearest_distance = distance_to_resistance
    else:
        nearest_zone = "middle"
        nearest_distance = distance_to_support

    zone_risk = "medium"
    sr_score = 0
    reason_parts = []

    if nearest_distance <= atr * 0.5:
        zone_risk = "high"
        sr_score -= 10
        reason_parts.append("Price is very close to " + nearest_zone)
    elif nearest_distance <= atr * 1.2:
        zone_risk = "medium"
        sr_score += 5
        reason_parts.append("Price is near " + nearest_zone)
    else:
        zone_risk = "low"
        sr_score += 15
        reason_parts.append("Price has enough room from nearest zone")

    if support_strength >= 45:
        sr_score += 10
        reason_parts.append("Support zone has multiple touches")

    if resistance_strength >= 45:
        sr_score += 10
        reason_parts.append("Resistance zone has multiple touches")

    if support < last_close < resistance:
        sr_score += 10
        reason_parts.append("Price is trading inside valid support/resistance range")
    else:
        sr_score -= 10
        reason_parts.append("Price is outside the recent support/resistance range")

    sr_score = max(0, min(100, sr_score))

    return {
        "support": round(support, 5),
        "resistance": round(resistance, 5),
        "support_strength": support_strength,
        "resistance_strength": resistance_strength,
        "nearest_zone": nearest_zone,
        "zone_risk": zone_risk,
        "sr_score": sr_score,
        "sr_reason": " | ".join(reason_parts)
    }

