def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def detect_regime(candles):
    """
    QuantBado Regime Detector v0.1

    Detects:
    - trend
    - range
    - breakout
    - pullback
    - accumulation
    - distribution
    """

    if not candles or len(candles) < 40:
        return {
            "regime": "unknown",
            "regime_score": 0,
            "regime_reason": "Need at least 40 candles for regime detection"
        }

    opens = [_safe_float(c["open"]) for c in candles]
    highs = [_safe_float(c["high"]) for c in candles]
    lows = [_safe_float(c["low"]) for c in candles]
    closes = [_safe_float(c["close"]) for c in candles]

    last_close = closes[-1]

    recent_high = max(highs[-20:])
    recent_low = min(lows[-20:])
    previous_high = max(highs[-40:-20])
    previous_low = min(lows[-40:-20])

    recent_range = max(recent_high - recent_low, 0.00001)
    previous_range = max(previous_high - previous_low, 0.00001)

    avg_10 = sum(closes[-10:]) / 10
    avg_20 = sum(closes[-20:]) / 20
    avg_40 = sum(closes[-40:]) / 40

    bullish_trend = avg_10 > avg_20 > avg_40 and last_close > avg_20
    bearish_trend = avg_10 < avg_20 < avg_40 and last_close < avg_20

    range_compression = recent_range < previous_range * 0.75
    range_expansion = recent_range > previous_range * 1.25

    close_near_high = (recent_high - last_close) < recent_range * 0.2
    close_near_low = (last_close - recent_low) < recent_range * 0.2

    bullish_breakout = last_close > previous_high and range_expansion
    bearish_breakout = last_close < previous_low and range_expansion

    pullback_bullish = bullish_trend and last_close < avg_10 and last_close > avg_20
    pullback_bearish = bearish_trend and last_close > avg_10 and last_close < avg_20

    bullish_candles = 0
    bearish_candles = 0

    for i in range(-20, 0):
        if closes[i] > opens[i]:
            bullish_candles += 1
        elif closes[i] < opens[i]:
            bearish_candles += 1

    regime = "range"
    regime_score = 10
    reason_parts = []

    if bullish_breakout:
        regime = "bullish_breakout"
        regime_score = 30
        reason_parts.append("Price broke above previous range with expansion")
    elif bearish_breakout:
        regime = "bearish_breakout"
        regime_score = 30
        reason_parts.append("Price broke below previous range with expansion")
    elif pullback_bullish:
        regime = "bullish_pullback"
        regime_score = 25
        reason_parts.append("Bullish trend with price pulling back into moving average zone")
    elif pullback_bearish:
        regime = "bearish_pullback"
        regime_score = 25
        reason_parts.append("Bearish trend with price pulling back into moving average zone")
    elif bullish_trend:
        regime = "bullish_trend"
        regime_score = 25
        reason_parts.append("Moving averages show bullish trend")
    elif bearish_trend:
        regime = "bearish_trend"
        regime_score = 25
        reason_parts.append("Moving averages show bearish trend")
    elif range_compression:
        if close_near_low and bullish_candles > bearish_candles:
            regime = "accumulation"
            regime_score = 15
            reason_parts.append("Compressed range with buying pressure near lows")
        elif close_near_high and bearish_candles > bullish_candles:
            regime = "distribution"
            regime_score = 15
            reason_parts.append("Compressed range with selling pressure near highs")
        else:
            regime = "range_compression"
            regime_score = 10
            reason_parts.append("Market is compressed inside a narrow range")
    else:
        regime = "range"
        regime_score = 10
        reason_parts.append("Market is ranging without clear expansion or trend")

    return {
        "regime": regime,
        "regime_score": regime_score,
        "regime_reason": " | ".join(reason_parts)
    }

