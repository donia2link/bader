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
    if danger_score >= 60 or risk_penalty <= -35:
        return "blocked"

    if final_confidence >= 85 and danger_score <= 25 and risk_penalty >= -15:
        return "scalp"

    if final_confidence >= 70 and danger_score <= 35:
        return "intraday"

    if final_confidence >= 55 and danger_score <= 25 and session_score >= 0:
        return "safe"

    return "no_trade"


def _has_hard_block(direction, blocks):
    """
    Hard blocks prevent bad weak signals.

    BUY hard blocks:
    - liquidity against buy
    - near resistance
    - dead market
    - low activity session
    - high danger

    SELL hard blocks:
    - liquidity against sell
    - near support
    - dead market
    - low activity session
    - high danger
    """

    if direction == "BUY":
        hard_block_names = [
            "liquidity_ok_for_buy",
            "not_near_resistance_zone",
            "not_near_resistance",
            "not_dead_market",
            "session_ok",
            "danger_ok"
        ]
    else:
        hard_block_names = [
            "liquidity_ok_for_sell",
            "not_near_support_zone",
            "not_near_support",
            "not_dead_market",
            "session_ok",
            "danger_ok"
        ]

    failed = [name for name in hard_block_names if not blocks.get(name, False)]

    return {
        "has_hard_block": len(failed) > 0,
        "hard_failed_blocks": failed
    }


def _grade_signal(direction, quality_score, pass_count, final_confidence, danger_score, risk_penalty, blocks):
    if danger_score >= 60 or risk_penalty <= -40:
        return "WAIT"

    hard = _has_hard_block(direction, blocks)

    if hard["has_hard_block"]:
        return "WAIT"

    if direction == "BUY":
        trend_ok = blocks.get("trend_bullish", False)
        momentum_ok = blocks.get("momentum_up", False)
        structure_ok = blocks.get("structure_bullish", False)

        if (
            quality_score >= 86
            and pass_count >= 9
            and final_confidence >= 75
            and trend_ok
            and momentum_ok
            and structure_ok
        ):
            return "Strong BUY"

        if (
            quality_score >= 72
            and pass_count >= 8
            and final_confidence >= 60
            and trend_ok
            and momentum_ok
        ):
            return "Weak BUY"

    if direction == "SELL":
        trend_ok = blocks.get("trend_bearish", False)
        momentum_ok = blocks.get("momentum_down", False)
        structure_ok = blocks.get("structure_bearish", False)

        if (
            quality_score >= 86
            and pass_count >= 9
            and final_confidence >= 75
            and trend_ok
            and momentum_ok
            and structure_ok
        ):
            return "Strong SELL"

        if (
            quality_score >= 72
            and pass_count >= 8
            and final_confidence >= 60
            and trend_ok
            and momentum_ok
        ):
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
    QuantBado Decision Fusion Engine v0.3

    v0.3 changes:
    - Blocks BUY if liquidity is against buy.
    - Blocks SELL if liquidity is against sell.
    - Blocks weak signals near opposite SR zone.
    - Strong signals now require trend + momentum + structure alignment.
    - Weak signals require trend + momentum alignment.
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

    buy_hard = _has_hard_block("BUY", buy_blocks)
    sell_hard = _has_hard_block("SELL", sell_blocks)

    blocked_reasons = []

    if buy_hard["has_hard_block"] and sell_hard["has_hard_block"]:
        blocked_reasons.append(
            "Both directions have hard blocks"
        )

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

    buy_grade = _grade_signal(
        direction="BUY",
        quality_score=buy_quality_score,
        pass_count=buy_pass_count,
        final_confidence=final_confidence,
        danger_score=danger_score,
        risk_penalty=risk_penalty,
        blocks=buy_blocks
    )

    sell_grade = _grade_signal(
        direction="SELL",
        quality_score=sell_quality_score,
        pass_count=sell_pass_count,
        final_confidence=final_confidence,
        danger_score=danger_score,
        risk_penalty=risk_penalty,
        blocks=sell_blocks
    )

    final_signal = "WAIT"
    signal_grade = "WAIT"
    final_risk = "high"
    reason_parts = []

    if buy_grade in ["Strong BUY", "Weak BUY"] and buy_quality_score >= sell_quality_score:
        final_signal = "BUY"
        signal_grade = buy_grade
        reason_parts.append(f"{signal_grade} confirmed by strict fusion v0.3")

    elif sell_grade in ["Strong SELL", "Weak SELL"] and sell_quality_score > buy_quality_score:
        final_signal = "SELL"
        signal_grade = sell_grade
        reason_parts.append(f"{signal_grade} confirmed by strict fusion v0.3")

    else:
        final_signal = "WAIT"
        signal_grade = "WAIT"

        wait_reasons = []

        if buy_hard["has_hard_block"]:
            wait_reasons.append("BUY blocked: " + ", ".join(buy_hard["hard_failed_blocks"]))

        if sell_hard["has_hard_block"]:
            wait_reasons.append("SELL blocked: " + ", ".join(sell_hard["hard_failed_blocks"]))

        if not wait_reasons:
            wait_reasons.append("Not enough aligned strict conditions")

        reason_parts.append(" | ".join(wait_reasons))

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
        "buy_hard_failed_blocks": buy_hard["hard_failed_blocks"],
        "sell_hard_failed_blocks": sell_hard["hard_failed_blocks"],
        "fusion_version": "fusion_engine_v0.3"
    }