def sma(values, period):
    if len(values) < period:
        return sum(values) / max(len(values), 1)
    return sum(values[-period:]) / period


def safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def round_price(value, digits=5):
    try:
        if value is None:
            return None
        return round(float(value), digits)
    except Exception:
        return value


def safe_slice(data, limit=300):
    if not isinstance(data, list):
        return []
    return data[-limit:]


def estimate_category(symbol: str) -> str:
    s = (symbol or "").upper()
    forex_codes = ["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "TRY"]
    crypto = ["BTC", "ETH", "XRP", "SOL", "DOGE", "LTC", "ADA", "BNB"]
    commodities = ["XAU", "XAG", "XPT", "XPD", "OIL", "BRENT", "CRUDE", "WTI", "NATGAS", "GAS", "COPPER", "WHEAT", "CORN", "COFFEE", "SUGAR", "COTTON", "COCOA", "SOY", "ALUMIN", "NICKEL", "LEAD"]
    indices = ["US30", "US100", "NAS100", "USTEC", "US500", "SPX", "GER", "DAX", "UK100", "JP225", "HK50", "FRA40", "AUS200"]
    if any(x in s for x in crypto):
        return "crypto"
    if any(x in s for x in commodities):
        return "commodity"
    if any(x in s for x in indices):
        return "index"
    found = [c for c in forex_codes if c in s]
    if len(found) >= 2:
        return "forex"
    return "other"


def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calc_atr(highs, lows, closes, period=14):
    if len(closes) < period + 1:
        return 0.0
    trs = []
    for i in range(-period, 0):
        high = highs[i]
        low = lows[i]
        prev_close = closes[i - 1]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    return sum(trs) / len(trs)


def detect_rejection(candles):
    if not candles:
        return (False, False, "")
    c = candles[-1]
    o = safe_float(c.get("open"), 0)
    h = safe_float(c.get("high"), 0)
    l = safe_float(c.get("low"), 0)
    close = safe_float(c.get("close"), 0)
    rng = max(h - l, 1e-9)
    body = abs(close - o)
    upper = h - max(o, close)
    lower = min(o, close) - l
    reject_support = lower > body * 1.5 and lower > rng * 0.35
    reject_resistance = upper > body * 1.5 and upper > rng * 0.35
    note = "support rejection" if reject_support else "resistance rejection" if reject_resistance else ""
    return reject_support, reject_resistance, note


def build_targets(signal, entry, atr, support, resistance, category):
    """Dynamic SL/TP built around ATR and current price. Returns TP1..TP5."""
    if entry is None or atr is None or atr <= 0:
        return None, None, None, None, None, None

    min_dist_factor = {
        "forex": 0.9,
        "commodity": 1.1,
        "index": 1.0,
        "crypto": 1.2,
        "other": 1.0,
    }.get(category, 1.0)
    dist = max(float(atr) * min_dist_factor, abs(float(entry)) * 0.00035)

    if signal == "BUY":
        sl = entry - dist
        if support is not None and support < entry:
            sl = min(sl, support - dist * 0.20)
        tp1 = entry + dist * 1.15
        tp2 = entry + dist * 1.75
        tp3 = entry + dist * 2.35
        tp4 = entry + dist * 3.00
        tp5 = entry + dist * 3.75
    elif signal == "SELL":
        sl = entry + dist
        if resistance is not None and resistance > entry:
            sl = max(sl, resistance + dist * 0.20)
        tp1 = entry - dist * 1.15
        tp2 = entry - dist * 1.75
        tp3 = entry - dist * 2.35
        tp4 = entry - dist * 3.00
        tp5 = entry - dist * 3.75
    else:
        return None, None, None, None, None, None

    return (
        round_price(sl),
        round_price(tp1),
        round_price(tp2),
        round_price(tp3),
        round_price(tp4),
        round_price(tp5),
    )


def build_quality(signal, confidence, entry, sl, tp1, atr, score_buy, score_sell, rsi,
                  breakout_buy, breakdown_sell, reject_support, reject_resistance,
                  ma21_break_up, ma21_break_down):
    warnings = []
    signal = (signal or "WAIT").upper()
    confidence = safe_float(confidence, 0) or 0
    atr = safe_float(atr, 0) or 0
    score_buy = safe_float(score_buy, 0) or 0
    score_sell = safe_float(score_sell, 0) or 0
    rsi = safe_float(rsi, 50) or 50

    risk_reward = None
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

    quality_score = confidence
    if signal == "WAIT":
        quality_score = min(45, confidence)
    if risk_reward is not None and risk_reward >= 1.5:
        quality_score += 8
    if risk_reward is not None and risk_reward >= 2.0:
        quality_score += 5
    if risk_reward is not None and risk_reward < 1.0:
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

    return quality_score, quality_label, setup_type, risk_reward, warnings


def analyze_market(data):
    symbol = data.get("symbol", "UNKNOWN")
    timeframe = data.get("timeframe", data.get("tf", "M1"))
    category = data.get("category") or estimate_category(symbol)
    candles = safe_slice(data.get("candles") or data.get("rates") or [], 400)

    if len(candles) < 30:
        return {
            "status": "ok",
            "symbol": symbol,
            "timeframe": timeframe,
            "category": category,
            "signal": "WAIT",
            "confidence": 0,
            "reason": "Not enough candle data",
            "quality_score": 0,
            "quality_label": "D",
            "setup_type": "range_wait",
            "risk_reward": None,
            "warnings": ["No actionable setup", "ATR unavailable"],
        }

    opens = [safe_float(c.get("open"), 0) for c in candles]
    highs = [safe_float(c.get("high"), 0) for c in candles]
    lows = [safe_float(c.get("low"), 0) for c in candles]
    closes = [safe_float(c.get("close"), 0) for c in candles]

    current_price = safe_float(data.get("current_price"), None)
    if current_price is None:
        current_price = safe_float(data.get("bid"), None)
    if current_price is None:
        current_price = safe_float(data.get("ask"), None)
    if current_price is None:
        current_price = closes[-1]

    ma9 = sma(closes, 9)
    ma21 = sma(closes, 21)
    ma50 = sma(closes, 50)
    rsi = calc_rsi(closes, 14)
    atr = calc_atr(highs, lows, closes, 14)

    recent_high = max(highs[-12:-1]) if len(highs) >= 13 else max(highs)
    recent_low = min(lows[-12:-1]) if len(lows) >= 13 else min(lows)
    support = min(lows[-25:])
    resistance = max(highs[-25:])

    last_close = closes[-1]
    prev_close = closes[-2]
    last_open = opens[-1]

    bullish_candle = last_close > last_open
    bearish_candle = last_close < last_open
    trend_up = last_close > ma21 > ma50 or (last_close > ma21 and ma9 > ma21)
    trend_down = last_close < ma21 < ma50 or (last_close < ma21 and ma9 < ma21)
    momentum_up = rsi > 54
    momentum_down = rsi < 46
    breakout_buy = last_close > recent_high and bullish_candle
    breakdown_sell = last_close < recent_low and bearish_candle
    ma21_break_up = prev_close <= ma21 and last_close > ma21
    ma21_break_down = prev_close >= ma21 and last_close < ma21
    reject_support, reject_resistance, rejection_note = detect_rejection(candles)

    buy_score = 0
    sell_score = 0

    if trend_up:
        buy_score += 24
    if trend_down:
        sell_score += 24
    if momentum_up:
        buy_score += 16
    if momentum_down:
        sell_score += 16
    if breakout_buy:
        buy_score += 22
    if breakdown_sell:
        sell_score += 22
    if ma21_break_up:
        buy_score += 10
    if ma21_break_down:
        sell_score += 10
    if reject_support:
        buy_score += 12
    if reject_resistance:
        sell_score += 12
    if bullish_candle:
        buy_score += 6
    if bearish_candle:
        sell_score += 6

    confidence = max(buy_score, sell_score)
    score_gap = abs(buy_score - sell_score)

    signal = "WAIT"
    reason = "No clean scalp setup. Market is mixed or inside range."
    if buy_score >= 58 and buy_score >= sell_score + 12:
        signal = "BUY"
        reason = "BUY: trend above MA21, RSI bullish momentum"
        if breakout_buy:
            reason += ", breakout above recent high"
        if reject_support:
            reason += ", support rejection"
        if ma21_break_up:
            reason += ", MA21 reclaim"
    elif sell_score >= 58 and sell_score >= buy_score + 12:
        signal = "SELL"
        reason = "SELL: trend below MA21, RSI bearish momentum"
        if breakdown_sell:
            reason += ", breakdown below recent low"
        if reject_resistance:
            reason += ", resistance rejection"
        if ma21_break_down:
            reason += ", MA21 rejection"

    if score_gap < 12 and signal != "WAIT":
        signal = "WAIT"
        reason = "Directional scores are mixed. Waiting for cleaner confirmation."

    entry = current_price
    sl, tp1, tp2, tp3, tp4, tp5 = build_targets(signal, entry, atr, support, resistance, category)

    # Final protection: never show invalid targets.
    if signal == "BUY":
        if sl is None or tp1 is None or not (sl < entry < tp1):
            sl = tp1 = tp2 = tp3 = tp4 = tp5 = None
    elif signal == "SELL":
        if sl is None or tp1 is None or not (tp1 < entry < sl):
            sl = tp1 = tp2 = tp3 = tp4 = tp5 = None
    else:
        sl = tp1 = tp2 = tp3 = tp4 = tp5 = None

    quality_score, quality_label, setup_type, risk_reward, warnings = build_quality(
        signal, confidence, entry, sl, tp1, atr, buy_score, sell_score, rsi,
        breakout_buy, breakdown_sell, reject_support, reject_resistance,
        ma21_break_up, ma21_break_down
    )

    return {
        "status": "ok",
        "symbol": symbol,
        "timeframe": timeframe,
        "category": category,
        "signal": signal,
        "confidence": round_price(confidence, 2),
        "quality_score": quality_score,
        "quality_label": quality_label,
        "setup_type": setup_type,
        "risk_reward": risk_reward,
        "warnings": warnings,
        "current_price": round_price(current_price, 5),
        "entry": round_price(entry, 5),
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "tp4": tp4,
        "tp5": tp5,
        "support": round_price(support, 5),
        "resistance": round_price(resistance, 5),
        "rsi": round_price(rsi, 2),
        "ma9": round_price(ma9, 5),
        "ma21": round_price(ma21, 5),
        "ma50": round_price(ma50, 5),
        "atr": round_price(atr, 5),
        "buy_score": round_price(buy_score, 2),
        "sell_score": round_price(sell_score, 2),
        "trend": "UP" if trend_up else "DOWN" if trend_down else "SIDEWAYS",
        "momentum_direction": "UP" if momentum_up else "DOWN" if momentum_down else "NEUTRAL",
        "reason": reason,
        "score_breakdown": {
            "buy_score": round_price(buy_score, 2),
            "sell_score": round_price(sell_score, 2),
            "gap": round_price(score_gap, 2),
        },
        "notes": "Market reader v25 targets quality",
    }
