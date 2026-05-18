def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def analyze_liquidity(candles):
    """
    QuantBado Liquidity Engine v0.1

    Detects:
    - liquidity sweep
    - stop hunt
    - fake breakout
    - liquidity pools
    - liquidity score
    """

    if not candles or len(candles) < 30:
        return {
            "liquidity_status": "unknown",
            "liquidity_direction": "none",
            "liquidity_score": 0,
            "sweep": "none",
            "stop_hunt": "none",
            "fake_breakout": "none",
            "buy_side_liquidity": 0,
            "sell_side_liquidity": 0,
            "liquidity_reason": "Need at least 30 candles for liquidity analysis"
        }

    opens = [_safe_float(c["open"]) for c in candles]
    highs = [_safe_float(c["high"]) for c in candles]
    lows = [_safe_float(c["low"]) for c in candles]
    closes = [_safe_float(c["close"]) for c in candles]

    last_open = opens[-1]
    last_high = highs[-1]
    last_low = lows[-1]
    last_close = closes[-1]

    previous_highs = highs[-21:-1]
    previous_lows = lows[-21:-1]

    buy_side_liquidity = max(previous_highs)
    sell_side_liquidity = min(previous_lows)

    recent_range = max(buy_side_liquidity - sell_side_liquidity, 0.00001)

    body = abs(last_close - last_open)
    candle_range = max(last_high - last_low, 0.00001)

    upper_wick = last_high - max(last_open, last_close)
    lower_wick = min(last_open, last_close) - last_low

    liquidity_score = 0
    liquidity_status = "normal"
    liquidity_direction = "none"
    sweep = "none"
    stop_hunt = "none"
    fake_breakout = "none"
    reason_parts = []

    swept_buy_side = last_high > buy_side_liquidity and last_close < buy_side_liquidity
    swept_sell_side = last_low < sell_side_liquidity and last_close > sell_side_liquidity

    if swept_buy_side:
        sweep = "buy_side_sweep"
        liquidity_status = "liquidity_sweep"
        liquidity_direction = "bearish"
        liquidity_score += 25
        reason_parts.append("Price swept buy-side liquidity and closed back below the liquidity level")

        if upper_wick > body * 1.5:
            stop_hunt = "buy_side_stop_hunt"
            liquidity_score += 15
            reason_parts.append("Large upper wick suggests buy-side stop hunt")

    if swept_sell_side:
        sweep = "sell_side_sweep"
        liquidity_status = "liquidity_sweep"
        liquidity_direction = "bullish"
        liquidity_score += 25
        reason_parts.append("Price swept sell-side liquidity and closed back above the liquidity level")

        if lower_wick > body * 1.5:
            stop_hunt = "sell_side_stop_hunt"
            liquidity_score += 15
            reason_parts.append("Large lower wick suggests sell-side stop hunt")

    broke_above = last_close > buy_side_liquidity
    broke_below = last_close < sell_side_liquidity

    if broke_above and body < candle_range * 0.35:
        fake_breakout = "possible_fake_bullish_breakout"
        liquidity_score += 10
        liquidity_direction = "bearish"
        reason_parts.append("Weak body after breaking above liquidity may indicate fake breakout")

    if broke_below and body < candle_range * 0.35:
        fake_breakout = "possible_fake_bearish_breakout"
        liquidity_score += 10
        liquidity_direction = "bullish"
        reason_parts.append("Weak body after breaking below liquidity may indicate fake breakout")

    near_buy_side = abs(buy_side_liquidity - last_close) < recent_range * 0.08
    near_sell_side = abs(last_close - sell_side_liquidity) < recent_range * 0.08

    if near_buy_side and liquidity_status == "normal":
        liquidity_status = "near_buy_side_liquidity"
        liquidity_score += 5
        reason_parts.append("Price is near buy-side liquidity")

    if near_sell_side and liquidity_status == "normal":
        liquidity_status = "near_sell_side_liquidity"
        liquidity_score += 5
        reason_parts.append("Price is near sell-side liquidity")

    if not reason_parts:
        reason_parts.append("No major liquidity event detected")

    liquidity_score = max(0, min(100, liquidity_score))

    return {
        "liquidity_status": liquidity_status,
        "liquidity_direction": liquidity_direction,
        "liquidity_score": liquidity_score,
        "sweep": sweep,
        "stop_hunt": stop_hunt,
        "fake_breakout": fake_breakout,
        "buy_side_liquidity": round(buy_side_liquidity, 5),
        "sell_side_liquidity": round(sell_side_liquidity, 5),
        "liquidity_reason": " | ".join(reason_parts)
    }

