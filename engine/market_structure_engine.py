def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _swing_points(candles, left=2, right=2):
    """
    Detect simple swing highs and swing lows.
    A swing high is a candle high higher than nearby highs.
    A swing low is a candle low lower than nearby lows.
    """
    highs = [_safe_float(c["high"]) for c in candles]
    lows = [_safe_float(c["low"]) for c in candles]

    swing_highs = []
    swing_lows = []

    for i in range(left, len(candles) - right):
        current_high = highs[i]
        current_low = lows[i]

        left_highs = highs[i - left:i]
        right_highs = highs[i + 1:i + 1 + right]

        left_lows = lows[i - left:i]
        right_lows = lows[i + 1:i + 1 + right]

        if current_high > max(left_highs) and current_high > max(right_highs):
            swing_highs.append({
                "index": i,
                "time": candles[i].get("time"),
                "price": current_high
            })

        if current_low < min(left_lows) and current_low < min(right_lows):
            swing_lows.append({
                "index": i,
                "time": candles[i].get("time"),
                "price": current_low
            })

    return swing_highs, swing_lows


def analyze_structure(candles):
    """
    QuantBado Market Structure Engine v0.1

    Returns:
    - structure: bullish_structure / bearish_structure / mixed_structure / unknown
    - pattern: HH_HL / LH_LL / mixed
    - bos: bullish_bos / bearish_bos / none
    - choch: bullish_choch / bearish_choch / none
    - structure_score
    - structure_reason
    """

    if not candles or len(candles) < 30:
        return {
            "structure": "unknown",
            "pattern": "not_enough_data",
            "bos": "none",
            "choch": "none",
            "last_swing_high": 0,
            "previous_swing_high": 0,
            "last_swing_low": 0,
            "previous_swing_low": 0,
            "structure_score": 0,
            "structure_reason": "Need at least 30 candles for structure analysis"
        }

    highs = [_safe_float(c["high"]) for c in candles]
    lows = [_safe_float(c["low"]) for c in candles]
    closes = [_safe_float(c["close"]) for c in candles]

    last_close = closes[-1]

    swing_highs, swing_lows = _swing_points(candles)

    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return {
            "structure": "mixed_structure",
            "pattern": "not_enough_swings",
            "bos": "none",
            "choch": "none",
            "last_swing_high": 0,
            "previous_swing_high": 0,
            "last_swing_low": 0,
            "previous_swing_low": 0,
            "structure_score": 5,
            "structure_reason": "Not enough swing points to confirm structure"
        }

    previous_high = swing_highs[-2]["price"]
    last_high = swing_highs[-1]["price"]

    previous_low = swing_lows[-2]["price"]
    last_low = swing_lows[-1]["price"]

    higher_high = last_high > previous_high
    higher_low = last_low > previous_low

    lower_high = last_high < previous_high
    lower_low = last_low < previous_low

    structure = "mixed_structure"
    pattern = "mixed"
    structure_score = 5
    reason_parts = []

    if higher_high and higher_low:
        structure = "bullish_structure"
        pattern = "HH_HL"
        structure_score = 25
        reason_parts.append("Market is forming higher highs and higher lows")
    elif lower_high and lower_low:
        structure = "bearish_structure"
        pattern = "LH_LL"
        structure_score = 25
        reason_parts.append("Market is forming lower highs and lower lows")
    else:
        structure = "mixed_structure"
        pattern = "mixed"
        structure_score = 10
        reason_parts.append("Market structure is mixed")

    bos = "none"

    if last_close > last_high:
        bos = "bullish_bos"
        structure_score += 10
        reason_parts.append("Price closed above last swing high")
    elif last_close < last_low:
        bos = "bearish_bos"
        structure_score += 10
        reason_parts.append("Price closed below last swing low")

    choch = "none"

    if structure == "bearish_structure" and last_close > last_high:
        choch = "bullish_choch"
        structure_score += 15
        reason_parts.append("Possible bullish change of character")
    elif structure == "bullish_structure" and last_close < last_low:
        choch = "bearish_choch"
        structure_score += 15
        reason_parts.append("Possible bearish change of character")

    structure_score = max(0, min(100, structure_score))

    return {
        "structure": structure,
        "pattern": pattern,
        "bos": bos,
        "choch": choch,
        "last_swing_high": round(last_high, 5),
        "previous_swing_high": round(previous_high, 5),
        "last_swing_low": round(last_low, 5),
        "previous_swing_low": round(previous_low, 5),
        "structure_score": structure_score,
        "structure_reason": " | ".join(reason_parts)
    }



