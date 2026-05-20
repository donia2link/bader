from market_reader import analyze_market
from signal_lifecycle import build_new_signal, update_signal_status
from signal_store import get_active_signal, save_active_signal, update_active_signal


DEFAULT_TIMEFRAMES = ["M1", "M5", "M15", "H1", "H4"]
MTF_TIMEFRAME_KEY = "MTF"


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _get_result(results, timeframe):
    return results.get(timeframe, {})


def _score_direction(results):
    weights = {
        "M1": 1,
        "M5": 2,
        "M15": 3,
        "H1": 4,
        "H4": 5
    }

    buy_score = 0
    sell_score = 0
    details = {}

    for tf, result in results.items():
        weight = weights.get(tf, 1)

        signal = result.get("signal", "WAIT")
        trend = result.get("trend", "range")
        momentum_direction = result.get("momentum_direction", "flat")
        structure = result.get("structure", "mixed_structure")
        signal_grade = result.get("signal_grade", "WAIT")

        local_buy = 0
        local_sell = 0

        if signal == "BUY":
            local_buy += 3
        elif signal == "SELL":
            local_sell += 3

        if trend == "bullish":
            local_buy += 2
        elif trend == "bearish":
            local_sell += 2

        if momentum_direction == "up":
            local_buy += 2
        elif momentum_direction == "down":
            local_sell += 2

        if structure == "bullish_structure":
            local_buy += 2
        elif structure == "bearish_structure":
            local_sell += 2

        if "Strong BUY" in signal_grade:
            local_buy += 3
        elif "Weak BUY" in signal_grade:
            local_buy += 1

        if "Strong SELL" in signal_grade:
            local_sell += 3
        elif "Weak SELL" in signal_grade:
            local_sell += 1

        buy_score += local_buy * weight
        sell_score += local_sell * weight

        details[tf] = {
            "weight": weight,
            "local_buy": local_buy,
            "local_sell": local_sell,
            "signal": signal,
            "signal_grade": signal_grade,
            "trend": trend,
            "momentum_direction": momentum_direction,
            "structure": structure
        }

    return {
        "buy_score": buy_score,
        "sell_score": sell_score,
        "details": details
    }


def _select_entry_timeframe(results, direction):
    for tf in ["M1", "M5"]:
        result = _get_result(results, tf)

        if not result:
            continue

        signal = result.get("signal", "WAIT")
        grade = result.get("signal_grade", "WAIT")

        if direction == "BUY" and signal == "BUY":
            return tf

        if direction == "SELL" and signal == "SELL":
            return tf

        if direction == "BUY" and "BUY" in grade:
            return tf

        if direction == "SELL" and "SELL" in grade:
            return tf

    return "M5" if "M5" in results else "M1"


def _build_mtf_levels(results, direction, entry_tf):
    entry_result = _get_result(results, entry_tf)

    entry = _safe_float(entry_result.get("entry", 0))
    sl = _safe_float(entry_result.get("sl", 0))
    tp1 = _safe_float(entry_result.get("tp1", 0))
    tp2 = _safe_float(entry_result.get("tp2", 0))
    tp3 = _safe_float(entry_result.get("tp3", 0))
    atr = _safe_float(entry_result.get("atr", 0))

    if entry <= 0:
        support = _safe_float(entry_result.get("support", 0))
        resistance = _safe_float(entry_result.get("resistance", 0))

        if support > 0 and resistance > 0:
            entry = (support + resistance) / 2

    if entry <= 0:
        return {
            "entry": 0,
            "sl": 0,
            "tp1": 0,
            "tp2": 0,
            "tp3": 0,
            "atr": round(atr, 5)
        }

    safe_atr = atr if atr > 0 else max(entry * 0.001, 0.00001)
    max_risk_distance = safe_atr * 2.0
    min_risk_distance = max(safe_atr * 0.6, entry * 0.0005)

    if direction == "BUY":
        if not (sl < entry < tp1 < tp2 < tp3):
            risk_distance = min(max(safe_atr, min_risk_distance), max_risk_distance)
            sl = entry - risk_distance
            tp1 = entry + risk_distance * 1.0
            tp2 = entry + risk_distance * 1.5
            tp3 = entry + risk_distance * 2.0

    elif direction == "SELL":
        if not (tp3 < tp2 < tp1 < entry < sl):
            risk_distance = min(max(safe_atr, min_risk_distance), max_risk_distance)
            sl = entry + risk_distance
            tp1 = entry - risk_distance * 1.0
            tp2 = entry - risk_distance * 1.5
            tp3 = entry - risk_distance * 2.0

    else:
        entry = 0
        sl = 0
        tp1 = 0
        tp2 = 0
        tp3 = 0

    return {
        "entry": round(entry, 5),
        "sl": round(sl, 5),
        "tp1": round(tp1, 5),
        "tp2": round(tp2, 5),
        "tp3": round(tp3, 5),
        "atr": round(atr, 5)
    }


def _last_price_from_results(results, entry_tf):
    result = _get_result(results, entry_tf)

    entry = _safe_float(result.get("entry", 0))
    if entry > 0:
        return entry

    for tf in ["M1", "M5", "M15", "H1", "H4"]:
        r = _get_result(results, tf)
        value = _safe_float(r.get("entry", 0))
        if value > 0:
            return value

    return 0


def _quality_from_result(result):
    signal = result.get("signal", "WAIT")
    confidence = _safe_float(result.get("confidence", 0))
    grade = result.get("signal_grade", "WAIT")

    if signal not in ["BUY", "SELL"]:
        return "No Trade"

    if "Strong" in grade or confidence >= 85:
        return f"{signal} Strong"

    if confidence >= 65:
        return f"{signal} Medium"

    return f"{signal} Weak"


def _preferred_target(result):
    """
    For compact panel display.
    Shows a practical target based on available levels.
    """
    signal = result.get("signal", "WAIT")

    tp1 = _safe_float(result.get("tp1", 0))
    tp2 = _safe_float(result.get("tp2", 0))
    tp3 = _safe_float(result.get("tp3", 0))

    if signal not in ["BUY", "SELL"]:
        return 0

    if tp2 > 0:
        return tp2

    if tp1 > 0:
        return tp1

    return tp3


def _build_individual_signals(results):
    output = {}

    for tf in DEFAULT_TIMEFRAMES:
        r = results.get(tf)

        if not r:
            output[tf] = {
                "timeframe": tf,
                "signal": "WAIT",
                "trend": "unknown",
                "trend_direction": "FLAT",
                "quality": "No Data",
                "confidence": 0,
                "entry": 0,
                "sl": 0,
                "tp1": 0,
                "tp2": 0,
                "tp3": 0,
                "target": 0,
                "signal_grade": "WAIT",
                "reason": "No candles"
            }
            continue

        trend = r.get("trend", "range")
        momentum_direction = r.get("momentum_direction", "flat")

        trend_direction = "FLAT"
        if trend == "bullish" or momentum_direction == "up":
            trend_direction = "UP"
        elif trend == "bearish" or momentum_direction == "down":
            trend_direction = "DOWN"

        output[tf] = {
            "timeframe": tf,
            "signal": r.get("signal", "WAIT"),
            "trend": trend,
            "trend_direction": trend_direction,
            "quality": _quality_from_result(r),
            "confidence": r.get("confidence", 0),
            "entry": r.get("entry", 0),
            "sl": r.get("sl", 0),
            "tp1": r.get("tp1", 0),
            "tp2": r.get("tp2", 0),
            "tp3": r.get("tp3", 0),
            "target": _preferred_target(r),
            "signal_grade": r.get("signal_grade", "WAIT"),
            "reason": r.get("reason", "")
        }

    return output


def _build_wait_response(symbol, results, direction_score, individual_signals, reason):
    return {
        "status": "ok",
        "symbol": symbol,
        "signal": "WAIT",
        "confidence": 0,
        "bias": "neutral",
        "reason": reason,
        "buy_score": direction_score["buy_score"],
        "sell_score": direction_score["sell_score"],
        "individual_signals": individual_signals,
        "timeframe_results": results,
        "direction_details": direction_score["details"],
        "signal_lifecycle": {
            "has_signal": False,
            "signal_status": "No Signal",
            "signal_id": "",
            "lifecycle_reason": reason
        },
        "mtf_version": "multi_timeframe_engine_v0.4"
    }


def analyze_multi_timeframe(symbol, candles_by_timeframe, user_key="unknown"):
    """
    QuantBado Multi-Timeframe Engine v0.4

    - Analyzes M1/M5/M15/H1/H4.
    - Returns individual_signals for each timeframe.
    - Keeps combined MTF signal lifecycle using timeframe key: MTF.
    """

    results = {}

    for timeframe in DEFAULT_TIMEFRAMES:
        candles = candles_by_timeframe.get(timeframe)

        if not candles:
            continue

        results[timeframe] = analyze_market(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            user_key=user_key
        )

    if not results:
        return {
            "status": "error",
            "message": "No timeframe candle data provided",
            "mtf_version": "multi_timeframe_engine_v0.4"
        }

    direction_score = _score_direction(results)
    individual_signals = _build_individual_signals(results)

    buy_score = direction_score["buy_score"]
    sell_score = direction_score["sell_score"]

    final_signal = "WAIT"
    final_bias = "neutral"

    if buy_score >= sell_score + 8:
        final_signal = "BUY"
        final_bias = "buy"

    elif sell_score >= buy_score + 8:
        final_signal = "SELL"
        final_bias = "sell"

    else:
        final_signal = "WAIT"
        final_bias = "neutral"

    existing_signal = get_active_signal(
        user_key=user_key,
        symbol=symbol,
        timeframe=MTF_TIMEFRAME_KEY
    )

    entry_tf = _select_entry_timeframe(results, final_signal if final_signal != "WAIT" else "BUY")
    current_price = _last_price_from_results(results, entry_tf)

    if existing_signal:
        lifecycle = update_signal_status(existing_signal, current_price)

        update_active_signal(
            user_key=user_key,
            symbol=symbol,
            timeframe=MTF_TIMEFRAME_KEY,
            signal_data=lifecycle
        )

        return {
            "status": "ok",
            "symbol": symbol,
            "signal": lifecycle.get("signal", "WAIT"),
            "confidence": lifecycle.get("confidence", 0),
            "bias": lifecycle.get("signal", "WAIT").lower(),
            "entry_timeframe": lifecycle.get("entry_timeframe", entry_tf),
            "entry": lifecycle.get("entry", 0),
            "sl": lifecycle.get("sl", 0),
            "tp1": lifecycle.get("tp1", 0),
            "tp2": lifecycle.get("tp2", 0),
            "tp3": lifecycle.get("tp3", 0),
            "max_tp_hit": lifecycle.get("max_tp_hit", "none"),
            "buy_score": buy_score,
            "sell_score": sell_score,
            "reason": "Existing MTF active signal is being tracked",
            "individual_signals": individual_signals,
            "signal_lifecycle": lifecycle,
            "timeframe_results": results,
            "direction_details": direction_score["details"],
            "mtf_version": "multi_timeframe_engine_v0.4"
        }

    if final_signal == "WAIT":
        return _build_wait_response(
            symbol=symbol,
            results=results,
            direction_score=direction_score,
            individual_signals=individual_signals,
            reason="Multi-timeframe scores are not aligned enough"
        )

    entry_tf = _select_entry_timeframe(results, final_signal)
    levels = _build_mtf_levels(results, final_signal, entry_tf)

    if levels["entry"] <= 0:
        return _build_wait_response(
            symbol=symbol,
            results=results,
            direction_score=direction_score,
            individual_signals=individual_signals,
            reason="MTF levels invalid, no trade"
        )

    confidence_gap = abs(buy_score - sell_score)
    confidence = min(100, max(50, confidence_gap * 5))

    lifecycle = build_new_signal(
        user_key=user_key,
        symbol=symbol,
        timeframe=MTF_TIMEFRAME_KEY,
        signal=final_signal,
        confidence=round(confidence, 2),
        entry=levels["entry"],
        sl=levels["sl"],
        tp1=levels["tp1"],
        tp2=levels["tp2"],
        tp3=levels["tp3"],
        reason=f"MTF {final_signal} selected from {entry_tf}",
        ttl_minutes=60
    )

    lifecycle["entry_timeframe"] = entry_tf
    lifecycle["mtf_signal"] = True
    lifecycle["buy_score"] = buy_score
    lifecycle["sell_score"] = sell_score
    lifecycle["direction_details"] = direction_score["details"]

    lifecycle = update_signal_status(lifecycle, current_price)

    save_active_signal(
        user_key=user_key,
        symbol=symbol,
        timeframe=MTF_TIMEFRAME_KEY,
        signal_data=lifecycle
    )

    return {
        "status": "ok",
        "symbol": symbol,
        "signal": final_signal,
        "confidence": round(confidence, 2),
        "bias": final_bias,
        "entry_timeframe": entry_tf,
        "entry": levels["entry"],
        "sl": levels["sl"],
        "tp1": levels["tp1"],
        "tp2": levels["tp2"],
        "tp3": levels["tp3"],
        "atr": levels["atr"],
        "max_tp_hit": lifecycle.get("max_tp_hit", "none"),
        "buy_score": buy_score,
        "sell_score": sell_score,
        "reason": f"Multi-timeframe {final_signal} selected from {entry_tf}",
        "individual_signals": individual_signals,
        "signal_lifecycle": lifecycle,
        "timeframe_results": results,
        "direction_details": direction_score["details"],
        "mtf_version": "multi_timeframe_engine_v0.4"
    }