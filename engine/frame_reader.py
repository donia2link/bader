from market_reader import analyze_market


FRAME_READER_VERSION = "frame_reader_v1.1"

DEFAULT_FRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]

FRAME_WEIGHTS = {
    "M1": 1,
    "M5": 2,
    "M15": 3,
    "M30": 3,
    "H1": 4,
    "H4": 5,
    "D1": 6,
}


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _trend_direction(result):
    trend = result.get("trend", "range")
    momentum = result.get("momentum_direction", "flat")
    structure = result.get("structure", "mixed_structure")

    buy = 0
    sell = 0

    if trend == "bullish":
        buy += 2
    elif trend == "bearish":
        sell += 2

    if momentum == "up":
        buy += 1
    elif momentum == "down":
        sell += 1

    if structure == "bullish_structure":
        buy += 1
    elif structure == "bearish_structure":
        sell += 1

    if buy > sell:
        return "UP"

    if sell > buy:
        return "DOWN"

    return "FLAT"


def _setup_direction(result):
    signal = result.get("signal", "WAIT")
    if signal in ["BUY", "SELL"]:
        return signal

    buy_quality = _safe_float(result.get("buy_quality_score", 0))
    sell_quality = _safe_float(result.get("sell_quality_score", 0))
    trend_dir = _trend_direction(result)

    buy_blocks = result.get("buy_failed_blocks", [])
    sell_blocks = result.get("sell_failed_blocks", [])

    if buy_quality >= sell_quality + 12 and len(buy_blocks) <= 2:
        return "BUY"

    if sell_quality >= buy_quality + 12 and len(sell_blocks) <= 2:
        return "SELL"

    if trend_dir == "UP" and buy_quality >= 70 and len(buy_blocks) <= 2:
        return "BUY"

    if trend_dir == "DOWN" and sell_quality >= 70 and len(sell_blocks) <= 2:
        return "SELL"

    return "WAIT"


def _is_blocked_hard(result, setup):
    dead_market = bool(result.get("dead_market", False))
    danger_level = result.get("danger_level", "low")
    session_status = result.get("session_status", "unknown")
    blocked_reasons = result.get("blocked_reasons", [])

    if dead_market:
        return True, "Dead market"

    if danger_level == "high":
        return True, "High danger"

    if "Low activity session" in blocked_reasons:
        return True, "Low activity"

    if setup == "BUY":
        failed = result.get("buy_failed_blocks", [])
        hard_blocks = {"not_near_resistance_zone", "not_near_resistance", "danger_ok", "session_ok"}
        if len(set(failed).intersection(hard_blocks)) >= 2:
            return True, "BUY blocked"

    if setup == "SELL":
        failed = result.get("sell_failed_blocks", [])
        hard_blocks = {"not_near_support_zone", "not_near_support", "danger_ok", "session_ok"}
        if len(set(failed).intersection(hard_blocks)) >= 2:
            return True, "SELL blocked"

    if session_status == "low_activity":
        return True, "Low activity"

    return False, ""


def _quality(result):
    signal = result.get("signal", "WAIT")
    confidence = _safe_float(result.get("confidence", 0))
    grade = result.get("signal_grade", "WAIT")
    setup = _setup_direction(result)

    if signal in ["BUY", "SELL"]:
        if "Strong" in grade or confidence >= 85:
            return f"{signal} Strong"
        if confidence >= 65:
            return f"{signal} Medium"
        return f"{signal} Weak"

    if setup in ["BUY", "SELL"]:
        blocked, reason = _is_blocked_hard(result, setup)
        if blocked:
            return f"WAIT {reason}"

        buy_quality = _safe_float(result.get("buy_quality_score", 0))
        sell_quality = _safe_float(result.get("sell_quality_score", 0))
        q = buy_quality if setup == "BUY" else sell_quality

        if q >= 90:
            return f"{setup} Setup A"
        if q >= 78:
            return f"{setup} Setup B"
        if q >= 68:
            return f"{setup} Setup C"

        return "WAIT Weak"

    return "WAIT"


def _entry(result):
    value = _safe_float(result.get("entry", 0))
    if value > 0:
        return value

    support = _safe_float(result.get("support", 0))
    resistance = _safe_float(result.get("resistance", 0))

    if support > 0 and resistance > 0:
        return round((support + resistance) / 2, 5)

    return 0


def _sl(result):
    value = _safe_float(result.get("sl", 0))
    if value > 0:
        return value

    setup = _setup_direction(result)
    entry = _entry(result)
    atr = _safe_float(result.get("atr", 0))

    if entry <= 0:
        return 0

    if atr <= 0:
        atr = max(entry * 0.001, 0.00001)

    if setup == "BUY":
        return round(entry - atr, 5)

    if setup == "SELL":
        return round(entry + atr, 5)

    return 0


def _target(result):
    setup = _setup_direction(result)

    if setup not in ["BUY", "SELL"]:
        return 0

    tp2 = _safe_float(result.get("tp2", 0))
    tp1 = _safe_float(result.get("tp1", 0))
    tp3 = _safe_float(result.get("tp3", 0))

    if tp2 > 0:
        return tp2

    if tp1 > 0:
        return tp1

    if tp3 > 0:
        return tp3

    entry = _entry(result)
    atr = _safe_float(result.get("atr", 0))

    if entry <= 0:
        return 0

    if atr <= 0:
        atr = max(entry * 0.001, 0.00001)

    if setup == "BUY":
        return round(entry + atr, 5)

    if setup == "SELL":
        return round(entry - atr, 5)

    return 0


def _frame_score(frame, result):
    setup = _setup_direction(result)
    quality = _quality(result)
    confidence = _safe_float(result.get("confidence", 0))
    weight = FRAME_WEIGHTS.get(frame, 1)

    if setup not in ["BUY", "SELL"]:
        return 0

    if quality.startswith("WAIT"):
        return 0

    score = 10 + weight * 3

    if "Strong" in quality:
        score += 35
    elif "Medium" in quality:
        score += 25
    elif "Setup A" in quality:
        score += 30
    elif "Setup B" in quality:
        score += 20
    elif "Setup C" in quality:
        score += 10
    elif "Weak" in quality:
        score += 3

    score += min(confidence, 100) * 0.2

    if result.get("danger_level") == "medium":
        score -= 8

    if result.get("danger_level") == "high":
        score -= 25

    if bool(result.get("dead_market", False)):
        score -= 30

    return round(max(score, 0), 2)


def _build_frame_payload(frame, result):
    setup = _setup_direction(result)
    quality = _quality(result)

    if quality.startswith("WAIT"):
        setup = "WAIT"

    return {
        "timeframe": frame,
        "signal": result.get("signal", "WAIT"),
        "setup_direction": setup,
        "trend_direction": _trend_direction(result),
        "quality": quality,
        "confidence": result.get("confidence", 0),
        "entry": _entry(result) if setup in ["BUY", "SELL"] else 0,
        "sl": _sl(result) if setup in ["BUY", "SELL"] else 0,
        "target": _target(result) if setup in ["BUY", "SELL"] else 0,
        "tp1": result.get("tp1", 0),
        "tp2": result.get("tp2", 0),
        "tp3": result.get("tp3", 0),
        "trend": result.get("trend", "range"),
        "structure": result.get("structure", "mixed_structure"),
        "liquidity_status": result.get("liquidity_status", "normal"),
        "volatility": result.get("volatility", "normal"),
        "session_status": result.get("session_status", "unknown"),
        "danger_level": result.get("danger_level", "low"),
        "reason": result.get("reason", ""),
        "score": _frame_score(frame, result),
    }


def _best_opportunity(frames):
    best = None

    for _, data in frames.items():
        if data.get("setup_direction") not in ["BUY", "SELL"]:
            continue

        if data.get("entry", 0) <= 0:
            continue

        if data.get("score", 0) < 35:
            continue

        if best is None or data.get("score", 0) > best.get("score", 0):
            best = data

    if best is None:
        return {
            "timeframe": "NONE",
            "signal": "WAIT",
            "setup_direction": "WAIT",
            "quality": "No clear opportunity",
            "entry": 0,
            "sl": 0,
            "target": 0,
            "score": 0,
        }

    return best


def _overall_bias(frames):
    buy = 0
    sell = 0

    for frame, data in frames.items():
        weight = FRAME_WEIGHTS.get(frame, 1)
        setup = data.get("setup_direction", "WAIT")
        score = _safe_float(data.get("score", 0))

        if score <= 0:
            continue

        if setup == "BUY":
            buy += weight + score / 20
        elif setup == "SELL":
            sell += weight + score / 20

    if buy > sell + 2:
        return "BUY"

    if sell > buy + 2:
        return "SELL"

    return "NEUTRAL"


def analyze_frame_reader(symbol, frames, user_key="unknown"):
    results = {}
    frame_payloads = {}

    for frame in DEFAULT_FRAMES:
        candles = frames.get(frame)

        if not candles:
            frame_payloads[frame] = {
                "timeframe": frame,
                "signal": "WAIT",
                "setup_direction": "WAIT",
                "trend_direction": "FLAT",
                "quality": "No Data",
                "confidence": 0,
                "entry": 0,
                "sl": 0,
                "target": 0,
                "score": 0,
                "reason": "No candles provided",
            }
            continue

        result = analyze_market(
            symbol=symbol,
            timeframe=frame,
            candles=candles,
            user_key=user_key
        )

        results[frame] = result
        frame_payloads[frame] = _build_frame_payload(frame, result)

    best = _best_opportunity(frame_payloads)
    bias = _overall_bias(frame_payloads)

    return {
        "status": "ok",
        "symbol": symbol,
        "overall_bias": bias,
        "best_opportunity": best,
        "frames": frame_payloads,
        "raw_results": results,
        "reader_version": FRAME_READER_VERSION,
    }