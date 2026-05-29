def sma(values, period):
    if len(values) < period:
        return sum(values) / len(values)
    return sum(values[-period:]) / period


def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0

    gains = []
    losses = []

    for i in range(-period, 0):
        change = closes[i] - closes[i - 1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def avg_range(highs, lows, period=14):
    count = min(period, len(highs), len(lows))
    if count <= 0:
        return 0.0

    ranges = []
    for i in range(-count, 0):
        ranges.append(highs[i] - lows[i])

    return sum(ranges) / len(ranges)


def analyze_market(data: dict) -> dict:
    symbol = data.get("symbol", "")
    timeframe = data.get("timeframe", "")
    candles = data.get("candles", [])
    # Use the actual current price from MT5 if provided.
    # Some EAs send price as 0 or with too few decimals; in that case use the latest candle close.
    try:
        price = float(data.get("price", 0) or 0)
    except Exception:
        price = 0.0

    if len(candles) < 50:
        return {
            "status": "error",
            "symbol": symbol,
            "timeframe": timeframe,
            "signal": "WAIT",
            "confidence": 0,
            "reason": "Not enough candles. Need at least 50 candles."
        }

    opens = [float(c["open"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    closes = [float(c["close"]) for c in candles]

    last_open = opens[-1]
    last_high = highs[-1]
    last_low = lows[-1]
    last_close = closes[-1]

    if price <= 0:
        price = last_close

    prev_open = opens[-2]
    prev_close = closes[-2]

    ma9 = sma(closes, 9)
    ma21 = sma(closes, 21)
    ma50 = sma(closes, 50)

    rsi = calc_rsi(closes, 14)
    atr = avg_range(highs, lows, 14)

    support = min(lows[-15:])
    resistance = max(highs[-15:])

    recent_high = max(highs[-6:-1])
    recent_low = min(lows[-6:-1])

    body = abs(last_close - last_open)
    candle_range = max(last_high - last_low, 0.01)

    upper_wick = last_high - max(last_open, last_close)
    lower_wick = min(last_open, last_close) - last_low

    bullish_candle = last_close > last_open
    bearish_candle = last_close < last_open

    strong_body = body >= candle_range * 0.45

    trend_up = last_close > ma21 and ma9 > ma21 and ma21 >= ma50
    trend_down = last_close < ma21 and ma9 < ma21 and ma21 <= ma50

    momentum_up = last_close > prev_close and rsi >= 55
    momentum_down = last_close < prev_close and rsi <= 45

    breakout_buy = last_close > recent_high and trend_up and momentum_up
    breakdown_sell = last_close < recent_low and trend_down and momentum_down

    reject_resistance = (
        last_high >= resistance - max(atr * 0.25, 0.5)
        and upper_wick > body * 1.2
        and bearish_candle
        and rsi < 60
    )

    reject_support = (
        last_low <= support + max(atr * 0.25, 0.5)
        and lower_wick > body * 1.2
        and bullish_candle
        and rsi > 40
    )

    ma21_break_down = prev_close >= ma21 and last_close < ma21 and bearish_candle
    ma21_break_up = prev_close <= ma21 and last_close > ma21 and bullish_candle

    signal = "WAIT"
    confidence = 45
    reason = "No clean scalp setup. Market is mixed or inside range."

    # Keep broker decimals, but avoid ugly float tails.
    current_price = round(price, 5)
    entry = current_price
    sl = None
    tp1 = None
    tp2 = None
    tp3 = None
    tp4 = None
    tp5 = None

    score_buy = 0
    score_sell = 0
    reasons_buy = []
    reasons_sell = []

    if trend_up:
        score_buy += 20
        reasons_buy.append("trend above MA21")

    if trend_down:
        score_sell += 20
        reasons_sell.append("trend below MA21")

    if momentum_up:
        score_buy += 20
        reasons_buy.append("RSI bullish momentum")

    if momentum_down:
        score_sell += 20
        reasons_sell.append("RSI bearish momentum")

    if breakout_buy:
        score_buy += 25
        reasons_buy.append("breakout above recent high")

    if breakdown_sell:
        score_sell += 25
        reasons_sell.append("breakdown below recent low")

    if reject_support:
        score_buy += 20
        reasons_buy.append("support rejection")

    if reject_resistance:
        score_sell += 20
        reasons_sell.append("resistance rejection")

    if ma21_break_up:
        score_buy += 15
        reasons_buy.append("MA21 reclaim")

    if ma21_break_down:
        score_sell += 15
        reasons_sell.append("MA21 break down")

    if strong_body and bullish_candle:
        score_buy += 10
        reasons_buy.append("strong bullish candle")

    if strong_body and bearish_candle:
        score_sell += 10
        reasons_sell.append("strong bearish candle")

    # Dynamic distance. Old fixed 1.2 was breaking low-price symbols such as EURCAD.
    # Example: EURCAD entry 1.61 with TP1 0.41 was caused by subtracting 1.2.
    min_distance = max(atr, price * 0.0015)
    min_distance = max(min_distance, price * 0.0005)

    # Dynamic SL buffer. Never use a fixed 0.7 for all symbols; it breaks low-price FX pairs.
    sl_buffer = max(atr * 0.35, price * 0.0008)

    if score_buy >= 60 and score_buy > score_sell + 10:
        signal = "BUY"
        confidence = min(90, score_buy)

        sl_price = min(support, last_low) - sl_buffer
        tp1_price = entry + min_distance
        tp2_price = entry + min_distance * 2
        tp3_price = entry + min_distance * 3
        tp4_price = entry + min_distance * 4
        tp5_price = entry + min_distance * 5

        sl = round(sl_price, 5)
        tp1 = round(tp1_price, 5)
        tp2 = round(tp2_price, 5)
        tp3 = round(tp3_price, 5)
        tp4 = round(tp4_price, 5)
        tp5 = round(tp5_price, 5)

        reason = "BUY: " + ", ".join(reasons_buy[:4])

    elif score_sell >= 60 and score_sell > score_buy + 10:
        signal = "SELL"
        confidence = min(90, score_sell)

        sl_price = max(resistance, last_high) + sl_buffer
        tp1_price = entry - min_distance
        tp2_price = entry - min_distance * 2
        tp3_price = entry - min_distance * 3
        tp4_price = entry - min_distance * 4
        tp5_price = entry - min_distance * 5

        sl = round(sl_price, 5)
        tp1 = round(tp1_price, 5)
        tp2 = round(tp2_price, 5)
        tp3 = round(tp3_price, 5)
        tp4 = round(tp4_price, 5)
        tp5 = round(tp5_price, 5)

        reason = "SELL: " + ", ".join(reasons_sell[:4])

    # Safety guard: if SL/TP is mathematically wrong, hide the levels instead of showing bad prices.
    if signal == "BUY":
        if sl is not None and sl >= entry:
            sl = None
        if tp1 is not None and tp1 <= entry:
            tp1 = None
        if tp2 is not None and tp2 <= entry:
            tp2 = None
        if tp3 is not None and tp3 <= entry:
            tp3 = None
        if tp4 is not None and tp4 <= entry:
            tp4 = None
        if tp5 is not None and tp5 <= entry:
            tp5 = None
    elif signal == "SELL":
        if sl is not None and sl <= entry:
            sl = None
        if tp1 is not None and tp1 >= entry:
            tp1 = None
        if tp2 is not None and tp2 >= entry:
            tp2 = None
        if tp3 is not None and tp3 >= entry:
            tp3 = None
        if tp4 is not None and tp4 >= entry:
            tp4 = None
        if tp5 is not None and tp5 >= entry:
            tp5 = None

    # V23 Signal Quality Engine: evaluate setup quality independently from raw direction score.
    risk_reward = None
    try:
        if signal == "BUY" and entry is not None and sl is not None and tp1 is not None:
            risk = float(entry) - float(sl)
            reward = float(tp1) - float(entry)
            if risk > 0 and reward > 0:
                risk_reward = round(reward / risk, 2)
        elif signal == "SELL" and entry is not None and sl is not None and tp1 is not None:
            risk = float(sl) - float(entry)
            reward = float(entry) - float(tp1)
            if risk > 0 and reward > 0:
                risk_reward = round(reward / risk, 2)
    except Exception:
        risk_reward = None

    warnings = []
    if signal == "WAIT":
        warnings.append("No actionable setup")
    if signal in ["BUY", "SELL"] and (sl is None or tp1 is None):
        warnings.append("Risk levels incomplete")
    if atr <= 0:
        warnings.append("ATR unavailable")
    if abs(score_buy - score_sell) < 15:
        warnings.append("Mixed directional scores")
    if signal == "BUY" and rsi >= 75:
        warnings.append("Momentum may be stretched")
    if signal == "SELL" and rsi <= 25:
        warnings.append("Momentum may be stretched")

    if signal == "BUY" and breakout_buy:
        setup_type = "trend_breakout"
    elif signal == "SELL" and breakdown_sell:
        setup_type = "trend_breakdown"
    elif reject_support or reject_resistance:
        setup_type = "rejection"
    elif ma21_break_up or ma21_break_down:
        setup_type = "ma_reclaim"
    elif signal == "WAIT":
        setup_type = "range_wait"
    else:
        setup_type = "momentum_setup"

    quality_score = float(confidence or 0)
    if signal == "WAIT":
        quality_score = min(45, quality_score)
    else:
        if risk_reward is not None:
            if risk_reward >= 1.5:
                quality_score += 8
            if risk_reward >= 2.0:
                quality_score += 5
            if risk_reward < 1.0:
                quality_score -= 12
        if setup_type in ["trend_breakout", "trend_breakdown"]:
            quality_score += 8
        if setup_type == "rejection":
            quality_score += 5
        if "Risk levels incomplete" in warnings:
            quality_score -= 20
        if "Mixed directional scores" in warnings:
            quality_score -= 10
        if "Momentum may be stretched" in warnings:
            quality_score -= 6

    quality_score = round(max(0, min(100, quality_score)), 2)
    if quality_score >= 80:
        quality_label = "A+"
    elif quality_score >= 70:
        quality_label = "A"
    elif quality_score >= 60:
        quality_label = "B"
    elif quality_score >= 50:
        quality_label = "C"
    else:
        quality_label = "D"

    return {
        "status": "ok",
        "symbol": symbol,
        "timeframe": timeframe,
        "signal": signal,
        "confidence": confidence,
        "current_price": current_price,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "tp4": tp4,
        "tp5": tp5,
        "support": round(support, 5),
        "resistance": round(resistance, 5),
        "ma9": round(ma9, 5),
        "ma21": round(ma21, 5),
        "ma50": round(ma50, 5),
        "rsi": round(rsi, 2),
        "atr": round(atr, 5),
        "buy_score": score_buy,
        "sell_score": score_sell,
        "quality_score": quality_score,
        "quality_label": quality_label,
        "setup_type": setup_type,
        "risk_reward": risk_reward,
        "warnings": warnings,
        "reason": reason
    }