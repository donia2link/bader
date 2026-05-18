
from market_structure_engine import analyze_structure
from momentum_engine import analyze_momentum
from liquidity_engine import analyze_liquidity
from support_resistance_engine import analyze_support_resistance
from volatility_engine import analyze_volatility
from session_engine import analyze_session
from regime_detector import detect_regime
from market_danger_engine import analyze_market_danger
from fusion_engine import build_decision_blocks, fuse_decision
from signal_lifecycle import build_new_signal, update_signal_status
from signal_store import get_active_signal, save_active_signal, update_active_signal


def analyze_market(symbol, timeframe, candles, user_key="unknown"):
    """
    QuantBado Market Reader v1.4
    Persistent Signal Store integration.
    Active signals are kept stable until TP Hit / SL Hit / Expired.
    """

    if not candles or len(candles) < 40:
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "signal": "WAIT",
            "confidence": 0,
            "strength": 0,
            "trend": "not_enough_data",
            "momentum": "unknown",
            "momentum_direction": "flat",
            "momentum_score": 0,
            "structure": "unknown",
            "structure_score": 0,
            "liquidity_status": "unknown",
            "liquidity_score": 0,
            "support": 0,
            "resistance": 0,
            "sr_score": 0,
            "volatility": "unknown",
            "atr": 0,
            "volatility_score": 0,
            "session_name": "unknown",
            "session_score": 0,
            "regime": "unknown",
            "regime_score": 0,
            "danger_level": "unknown",
            "danger_score": 0,
            "entry": 0,
            "sl": 0,
            "tp1": 0,
            "tp2": 0,
            "tp3": 0,
            "risk": "high",
            "reason": "Need at least 40 candles",
            "smart_no_trade_reason": "Not enough candles for reliable analysis",
            "fusion_score": 0,
            "fusion_reason": "Not enough candles",
            "decision_blocks": {},
            "signal_lifecycle": {
                "has_signal": False,
                "signal_status": "No Signal",
                "signal_id": "",
                "lifecycle_reason": "Not enough candles"
            },
            "score_breakdown": {
                "trend": 0,
                "momentum": 0,
                "structure": 0,
                "liquidity": 0,
                "support_resistance": 0,
                "volatility": 0,
                "session": 0,
                "regime": 0,
                "danger": 0,
                "risk": -20
            },
            "strategy_version": "market_reader_v1.4",
            "notes": "Market reader v1.4"
        }

    closes = [float(c["close"]) for c in candles]
    last_close = closes[-1]

    lookback = 20
    recent_closes = closes[-lookback:]
    avg_20 = sum(recent_closes) / lookback
    avg_10 = sum(closes[-10:]) / 10

    if last_close > avg_20 and avg_10 > avg_20:
        trend = "bullish"
        trend_score = 25
    elif last_close < avg_20 and avg_10 < avg_20:
        trend = "bearish"
        trend_score = 25
    else:
        trend = "range"
        trend_score = 5

    momentum_result = analyze_momentum(candles)
    momentum = momentum_result.get("momentum", "unknown")
    momentum_direction = momentum_result.get("momentum_direction", "flat")
    momentum_score = momentum_result.get("momentum_score", 0)
    candle_pressure = momentum_result.get("candle_pressure", "unknown")
    impulse_status = momentum_result.get("impulse_status", "unknown")
    acceleration = momentum_result.get("acceleration", "unknown")
    momentum_reason = momentum_result.get("momentum_reason", "")

    structure_result = analyze_structure(candles)
    structure = structure_result.get("structure", "mixed_structure")
    pattern = structure_result.get("pattern", "mixed")
    bos = structure_result.get("bos", "none")
    choch = structure_result.get("choch", "none")
    structure_score = structure_result.get("structure_score", 5)
    structure_reason = structure_result.get("structure_reason", "")

    liquidity_result = analyze_liquidity(candles)
    liquidity_status = liquidity_result.get("liquidity_status", "unknown")
    liquidity_direction = liquidity_result.get("liquidity_direction", "none")
    liquidity_score = liquidity_result.get("liquidity_score", 0)
    sweep = liquidity_result.get("sweep", "none")
    stop_hunt = liquidity_result.get("stop_hunt", "none")
    fake_breakout = liquidity_result.get("fake_breakout", "none")
    buy_side_liquidity = liquidity_result.get("buy_side_liquidity", 0)
    sell_side_liquidity = liquidity_result.get("sell_side_liquidity", 0)
    liquidity_reason = liquidity_result.get("liquidity_reason", "")

    sr_result = analyze_support_resistance(candles)
    support = sr_result.get("support", 0)
    resistance = sr_result.get("resistance", 0)
    support_strength = sr_result.get("support_strength", 0)
    resistance_strength = sr_result.get("resistance_strength", 0)
    nearest_zone = sr_result.get("nearest_zone", "unknown")
    zone_risk = sr_result.get("zone_risk", "medium")
    sr_score = sr_result.get("sr_score", 0)
    sr_reason = sr_result.get("sr_reason", "")

    volatility_result = analyze_volatility(candles)
    volatility = volatility_result.get("volatility", "unknown")
    atr = volatility_result.get("atr", 0)
    atr_ratio = volatility_result.get("atr_ratio", 0)
    volatility_state = volatility_result.get("volatility_state", "unknown")
    volatility_score = volatility_result.get("volatility_score", 0)
    dead_market = volatility_result.get("dead_market", False)
    volatility_reason = volatility_result.get("volatility_reason", "")

    session_result = analyze_session(symbol=symbol, timeframe=timeframe)
    session_name = session_result.get("session_name", "unknown")
    session_status = session_result.get("session_status", "unknown")
    session_score = session_result.get("session_score", 0)
    session_hour_utc = session_result.get("session_hour_utc", 0)
    session_reason = session_result.get("session_reason", "")

    regime_result = detect_regime(candles)
    regime = regime_result.get("regime", "unknown")
    regime_score = regime_result.get("regime_score", 0)
    regime_reason = regime_result.get("regime_reason", "")

    danger_result = analyze_market_danger(candles)
    danger_level = danger_result.get("danger_level", "unknown")
    danger_score = danger_result.get("danger_score", 0)
    whipsaw = danger_result.get("whipsaw", False)
    fake_market = danger_result.get("fake_market", False)
    manipulation_risk = danger_result.get("manipulation_risk", False)
    danger_reason = danger_result.get("danger_reason", "")

    risk_penalty = 0
    smart_no_trade_reason = ""

    distance_to_resistance = resistance - last_close
    distance_to_support = last_close - support

    near_resistance = distance_to_resistance < atr * 0.6 if atr else False
    near_support = distance_to_support < atr * 0.6 if atr else False

    if volatility == "high":
        risk_penalty -= 10
        smart_no_trade_reason = "High volatility increases trade risk"
    elif volatility == "low":
        risk_penalty -= 5
        smart_no_trade_reason = "Low volatility may reduce follow-through"

    if dead_market:
        risk_penalty -= 10
        smart_no_trade_reason = "Dead market detected. Movement is too narrow"

    if zone_risk == "high":
        risk_penalty -= 10
        if not smart_no_trade_reason:
            smart_no_trade_reason = "Price is too close to an important support/resistance zone"

    if session_status == "low_activity":
        risk_penalty -= 10
        if not smart_no_trade_reason:
            smart_no_trade_reason = "Low activity session. Trade quality may be weak"

    if danger_level == "high":
        risk_penalty -= 35
        smart_no_trade_reason = "High market danger detected. No trade allowed"
    elif danger_level == "medium":
        risk_penalty -= 15
        if not smart_no_trade_reason:
            smart_no_trade_reason = "Medium market danger detected. Trade quality is reduced"

    decision_blocks = build_decision_blocks(
        trend=trend,
        momentum_direction=momentum_direction,
        structure=structure,
        liquidity_direction=liquidity_direction,
        nearest_zone=nearest_zone,
        volatility=volatility,
        dead_market=dead_market,
        session_status=session_status,
        regime=regime,
        danger_level=danger_level,
        near_resistance=near_resistance,
        near_support=near_support
    )

    fusion_result = fuse_decision(
        trend_score=trend_score,
        momentum_score=momentum_score,
        structure_score=structure_score,
        liquidity_score=liquidity_score,
        sr_score=sr_score,
        volatility_score=volatility_score,
        session_score=session_score,
        regime_score=regime_score,
        danger_score=danger_score,
        risk_penalty=risk_penalty,
        decision_blocks=decision_blocks
    )

    signal = fusion_result.get("final_signal", "WAIT")
    confidence = fusion_result.get("final_confidence", 0)
    strength = confidence
    risk = fusion_result.get("final_risk", "high")
    fusion_score = fusion_result.get("fusion_score", 0)
    fusion_reason = fusion_result.get("fusion_reason", "")
    danger_penalty = fusion_result.get("danger_penalty", -abs(danger_score))

    

    reason = fusion_reason
    if signal == "WAIT" and not smart_no_trade_reason:
        smart_no_trade_reason = "Fusion engine did not confirm enough aligned conditions"

    entry = last_close

    if signal == "BUY":
        sl = min(support, entry - atr * 1.2) if atr else support
        risk_distance = max(entry - sl, atr if atr else 0.00001)
        tp1 = entry + risk_distance * 1.0
        tp2 = entry + risk_distance * 1.5
        tp3 = entry + risk_distance * 2.0
    elif signal == "SELL":
        sl = max(resistance, entry + atr * 1.2) if atr else resistance
        risk_distance = max(sl - entry, atr if atr else 0.00001)
        tp1 = entry - risk_distance * 1.0
        tp2 = entry - risk_distance * 1.5
        tp3 = entry - risk_distance * 2.0
    else:
        entry = 0
        sl = 0
        tp1 = 0
        tp2 = 0
        tp3 = 0

    existing_signal = get_active_signal(
        user_key=user_key,
        symbol=symbol,
        timeframe=timeframe
    )

    if existing_signal:
        lifecycle = update_signal_status(existing_signal, last_close)

        update_active_signal(
            user_key=user_key,
            symbol=symbol,
            timeframe=timeframe,
            signal_data=lifecycle
        )

        signal = lifecycle.get("signal", signal)
        entry = float(lifecycle.get("entry", entry))
        sl = float(lifecycle.get("sl", sl))
        tp1 = float(lifecycle.get("tp1", tp1))
        tp2 = float(lifecycle.get("tp2", tp2))
        tp3 = float(lifecycle.get("tp3", tp3))

        reason = "Existing active signal is being tracked"
        smart_no_trade_reason = lifecycle.get("lifecycle_reason", smart_no_trade_reason)

    else:
        lifecycle = build_new_signal(
            user_key=user_key,
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            entry=round(entry, 5),
            sl=round(sl, 5),
            tp1=round(tp1, 5),
            tp2=round(tp2, 5),
            tp3=round(tp3, 5),
            reason=reason,
            ttl_minutes=60
        )

        if lifecycle.get("has_signal"):
            lifecycle = update_signal_status(lifecycle, last_close)

            save_active_signal(
                user_key=user_key,
                symbol=symbol,
                timeframe=timeframe,
                signal_data=lifecycle
            )

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "signal": signal,
        "confidence": round(confidence, 2),
        "strength": round(strength, 2),
        "trend": trend,

        "momentum": momentum,
        "momentum_direction": momentum_direction,
        "momentum_score": momentum_score,
        "candle_pressure": candle_pressure,
        "impulse_status": impulse_status,
        "acceleration": acceleration,
        "momentum_reason": momentum_reason,

        "structure": structure,
        "pattern": pattern,
        "bos": bos,
        "choch": choch,
        "last_swing_high": structure_result.get("last_swing_high", 0),
        "previous_swing_high": structure_result.get("previous_swing_high", 0),
        "last_swing_low": structure_result.get("last_swing_low", 0),
        "previous_swing_low": structure_result.get("previous_swing_low", 0),
        "structure_score": structure_score,
        "structure_reason": structure_reason,

        "liquidity_status": liquidity_status,
        "liquidity_direction": liquidity_direction,
        "liquidity_score": liquidity_score,
        "sweep": sweep,
        "stop_hunt": stop_hunt,
        "fake_breakout": fake_breakout,
        "buy_side_liquidity": buy_side_liquidity,
        "sell_side_liquidity": sell_side_liquidity,
        "liquidity_reason": liquidity_reason,

        "support": round(support, 5),
        "resistance": round(resistance, 5),
        "support_strength": support_strength,
        "resistance_strength": resistance_strength,
        "nearest_zone": nearest_zone,
        "zone_risk": zone_risk,
        "sr_score": sr_score,
        "sr_reason": sr_reason,

        "volatility": volatility,
        "atr": round(atr, 5),
        "atr_ratio": atr_ratio,
        "volatility_state": volatility_state,
        "volatility_score": volatility_score,
        "dead_market": dead_market,
        "volatility_reason": volatility_reason,

        "session_name": session_name,
        "session_status": session_status,
        "session_score": session_score,
        "session_hour_utc": session_hour_utc,
        "session_reason": session_reason,

        "regime": regime,
        "regime_score": regime_score,
        "regime_reason": regime_reason,

        "danger_level": danger_level,
        "danger_score": danger_score,
        "whipsaw": whipsaw,
        "fake_market": fake_market,
        "manipulation_risk": manipulation_risk,
        "danger_reason": danger_reason,

        "fusion_score": fusion_score,
        "fusion_reason": fusion_reason,
        "decision_blocks": decision_blocks,

        "signal_lifecycle": lifecycle,

        "entry": round(entry, 5),
        "sl": round(sl, 5),
        "tp1": round(tp1, 5),
        "tp2": round(tp2, 5),
        "tp3": round(tp3, 5),
        "risk": risk,
        "reason": reason,
        "smart_no_trade_reason": smart_no_trade_reason,
        "score_breakdown": {
            "trend": trend_score,
            "momentum": momentum_score,
            "structure": structure_score,
            "liquidity": liquidity_score,
            "support_resistance": sr_score,
            "volatility": volatility_score,
            "session": session_score,
            "regime": regime_score,
            "danger": danger_penalty,
            "risk": risk_penalty
        },
        "strategy_version": "market_reader_v1.4",
        "notes": "Market reader v1.4"
    }