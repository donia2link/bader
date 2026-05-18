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
    QuantBado Decision Fusion Engine v0.1

    Combines all engine scores and decision blocks into one final market decision.
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

    final_signal = "WAIT"
    final_risk = "high"
    reason_parts = []

    if buy_pass_count >= 9 and fusion_score >= 80:
        final_signal = "BUY"
        final_risk = "medium"
        reason_parts.append("BUY decision passed enough fusion blocks with strong score")
    elif sell_pass_count >= 9 and fusion_score >= 80:
        final_signal = "SELL"
        final_risk = "medium"
        reason_parts.append("SELL decision passed enough fusion blocks with strong score")
    else:
        final_signal = "WAIT"
        reason_parts.append("Fusion engine did not confirm enough aligned conditions")

    if not buy_blocks.get("danger_ok", True) or not sell_blocks.get("danger_ok", True):
        final_signal = "WAIT"
        final_risk = "high"
        reason_parts.append("High market danger blocks trade entry")

    if final_confidence >= 75 and final_risk != "high":
        final_risk = "low"
    elif final_confidence >= 55 and final_risk != "high":
        final_risk = "medium"
    else:
        final_risk = "high"

    return {
        "final_signal": final_signal,
        "final_confidence": round(final_confidence, 2),
        "final_risk": final_risk,
        "fusion_score": round(fusion_score, 2),
        "fusion_reason": " | ".join(reason_parts),
        "decision_blocks": decision_blocks,
        "danger_penalty": danger_penalty
    }