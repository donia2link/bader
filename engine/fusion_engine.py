def build_decision_blocks(
    trend,
    momentum_direction,
    structure,
    liquidity_direction,
    nearest_zone,
    volatility,
    dead_market,
    session_status,
    regime,
    danger_level,
    near_resistance,
    near_support
):
    buy_blocks = {
        "trend_bullish": trend == "bullish",
        "momentum_up": momentum_direction == "up",
        "structure_bullish": structure == "bullish_structure",
        "liquidity_ok_for_buy": liquidity_direction in ["bullish", "none"],
        "not_near_resistance_zone": nearest_zone != "resistance",
        "not_near_resistance": not near_resistance,
        "not_dead_market": not dead_market,
        "session_ok": session_status != "low_activity",
        "regime_allows_buy": regime in [
            "bullish_trend",
            "bullish_breakout",
            "bullish_pullback",
            "range",
            "range_compression",
            "accumulation"
        ],
        "danger_ok": danger_level != "high"
    }

    sell_blocks = {
        "trend_bearish": trend == "bearish",
        "momentum_down": momentum_direction == "down",
        "structure_bearish": structure == "bearish_structure",
        "liquidity_ok_for_sell": liquidity_direction in ["bearish", "none"],
        "not_near_support_zone": nearest_zone != "support",
        "not_near_support": not near_support,
        "not_dead_market": not dead_market,
        "session_ok": session_status != "low_activity",
        "regime_allows_sell": regime in [
            "bearish_trend",
            "bearish_breakout",
            "bearish_pullback",
            "range",
            "range_compression",
            "distribution"
        ],
        "danger_ok": danger_level != "high"
    }

    return {
        "buy_blocks": buy_blocks,
        "sell_blocks": sell_blocks,
        "buy_pass_count": sum(1 for value in buy_blocks.values() if value),
        "sell_pass_count": sum(1 for value in sell_blocks.values() if value)
    }


def _failed_blocks(blocks):
    return [name for name, passed in blocks.items() if not passed]


def _quality_score(pass_count, fusion_score, danger_score, risk_penalty):
    score = 0

    score += pass_count * 8
    score += max(0, min(100, fusion_score)) * 0.35

    if danger_score >= 60:
        score -= 30
    elif danger_score >= 30:
        score -= 15
    else:
        score += 5

    score += risk_penalty

    return max(0, min(100, round(score, 2)))


def _detect_trade_mode(final_confidence, danger_score, session_score, volatility_score, risk_penalty):
    """
    Basic trade mode classification.
    Later this can become user configurable.
    """

    if danger_score >= 60 or risk_penalty <= -35:
        return "blocked"

    if final_confidence >= 85 and danger_score <= 25 and risk_penalty >= -15:
        return "scalp"

    if final_confidence >= 70 and danger_score <= 35:
        return "intraday"

    if final_confidence >= 55 and danger_score <= 25 and session_score >= 0:
        return "safe"

    return "no_trade"


def _grade_signal(direction, quality_score, pass_count, final_confidence, danger_score, risk_penalty):
    if danger_score >= 60 or risk_penalty <= -40:
        return "WAIT"

    if direction == "BUY":
        if quality_score >= 82 and pass_count >= 9 and final_confidence >= 75:
            return "Strong BUY"
        if quality_score >= 62 and pass_count >= 7 and final_confidence >= 55:
            return "Weak BUY"

    if direction == "SELL":
        if quality_score >= 82 and pass_count >= 9 and final_confidence >= 75:
            return "Strong SELL"
        if quality_score >= 62 and pass_count >= 7 and final_confidence >= 55:
            return "Weak SELL"

    return "WAIT"


def fuse_decision(
    trend_score,
    momentum_score,
    structure_score,
    liquidity_score,
    sr_score,
    volatility_score,
    session_score,
    regime_score,
    danger_score,
    risk_penalty,
    decision_blocks
):
    """
    QuantBado Decision Fusion Engine v0.2

    Combines all engine scores and decision blocks into a final market decision.

    v0.2 adds:
    - signal_grade
    - trade_mode
    - buy_quality_score
    - sell_quality_score
    - direction_bias
    - blocked_reasons

    Compatibility:
    - final_signal still returns BUY / SELL / WAIT for market_reader.py
    """

    danger_penalty = -abs(danger_score)

    fusion_score = (
        trend_score
        + momentum_score
        + structure_score
        + liquidity_score
        + sr_score
        + volatility_score
        + session_score
        + regime_score
        + danger_penalty
        + risk_penalty
    )

    final_confidence = max(0, min(100, fusion_score))

    buy_pass_count = decision_blocks.get("buy_pass_count", 0)
    sell_pass_count = decision_blocks.get("sell_pass_count", 0)

    buy_blocks = decision_blocks.get("buy_blocks", {})
    sell_blocks = decision_blocks.get("sell_blocks", {})

    buy_quality_score = _quality_score(
        pass_count=buy_pass_count,
        fusion_score=fusion_score,
        danger_score=danger_score,
        risk_penalty=risk_penalty
    )

    sell_quality_score = _quality_score(
        pass_count=sell_pass_count,
        fusion_score=fusion_score,
        danger_score=danger_score,
        risk_penalty=risk_penalty
    )

    blocked_reasons = []

    if not buy_blocks.get("danger_ok", True) or not sell_blocks.get("danger_ok", True):
        blocked_reasons.append("High market danger")

    if not buy_blocks.get("not_dead_market", True) or not sell_blocks.get("not_dead_market", True):
        blocked_reasons.append("Dead market")

    if not buy_blocks.get("session_ok", True) or not sell_blocks.get("session_ok", True):
        blocked_reasons.append("Low activity session")

    if risk_penalty <= -35:
        blocked_reasons.append("Risk penalty too high")

    if buy_quality_score > sell_quality_score + 8:
        direction_bias = "buy"
    elif sell_quality_score > buy_quality_score + 8:
        direction_bias = "sell"
    else:
        direction_bias = "neutral"

    final_signal = "WAIT"
    final_risk = "high"
    reason_parts = []

    buy_grade = _grade_signal(
        direction="BUY",
        quality_score=buy_quality_score,
        pass_count=buy_pass_count,
        final_confidence=final_confidence,
        danger_score=danger_score,
        risk_penalty=risk_penalty
    )

    sell_grade = _grade_signal(
        direction="SELL",
        quality_score=sell_quality_score,
        pass_count=sell_pass_count,
        final_confidence=final_confidence,
        danger_score=danger_score,
        risk_penalty=risk_penalty
    )

    signal_grade = "WAIT"

    if blocked_reasons:
        final_signal = "WAIT"
        signal_grade = "WAIT"
        final_risk = "high"
        reason_parts.append("Trade blocked: " + ", ".join(blocked_reasons))

    elif buy_grade in ["Strong BUY", "Weak BUY"] and buy_quality_score >= sell_quality_score:
        signal_grade = buy_grade
        final_signal = "BUY"
        reason_parts.append(
            f"{signal_grade} confirmed by fusion quality score"
        )

    elif sell_grade in ["Strong SELL", "Weak SELL"] and sell_quality_score > buy_quality_score:
        signal_grade = sell_grade
        final_signal = "SELL"
        reason_parts.append(
            f"{signal_grade} confirmed by fusion quality score"
        )

    else:
        final_signal = "WAIT"
        signal_grade = "WAIT"
        reason_parts.append("Fusion engine did not confirm enough aligned conditions")

    trade_mode = _detect_trade_mode(
        final_confidence=final_confidence,
        danger_score=danger_score,
        session_score=session_score,
        volatility_score=volatility_score,
        risk_penalty=risk_penalty
    )

    if final_signal == "WAIT":
        final_risk = "high"
    elif final_confidence >= 75 and danger_score <= 25 and risk_penalty >= -20:
        final_risk = "low"
    elif final_confidence >= 55 and danger_score <= 40:
        final_risk = "medium"
    else:
        final_risk = "high"

    buy_failed_blocks = _failed_blocks(buy_blocks)
    sell_failed_blocks = _failed_blocks(sell_blocks)

    return {
        "final_signal": final_signal,
        "final_confidence": round(final_confidence, 2),
        "final_risk": final_risk,
        "fusion_score": round(fusion_score, 2),
        "fusion_reason": " | ".join(reason_parts),
        "decision_blocks": decision_blocks,
        "danger_penalty": danger_penalty,

        "signal_grade": signal_grade,
        "trade_mode": trade_mode,
        "buy_quality_score": buy_quality_score,
        "sell_quality_score": sell_quality_score,
        "direction_bias": direction_bias,
        "blocked_reasons": blocked_reasons,
        "buy_failed_blocks": buy_failed_blocks,
        "sell_failed_blocks": sell_failed_blocks,
        "fusion_version": "fusion_engine_v0.2"
    }