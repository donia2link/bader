from datetime import datetime, timezone, timedelta
import uuid


FINAL_STATUSES = ["TP3 Hit", "SL Hit", "Expired"]
PARTIAL_STATUSES = ["TP1 Hit", "TP2 Hit"]
ALL_HIT_STATUSES = ["TP1 Hit", "TP2 Hit", "TP3 Hit", "SL Hit", "Expired"]


def utc_now():
    return datetime.now(timezone.utc)


def utc_now_iso():
    return utc_now().isoformat()


def build_new_signal(
    user_key,
    symbol,
    timeframe,
    signal,
    confidence,
    entry,
    sl,
    tp1,
    tp2,
    tp3,
    reason,
    ttl_minutes=60
):
    if signal not in ["BUY", "SELL"]:
        return {
            "has_signal": False,
            "signal_status": "No Signal",
            "signal_id": "",
            "lifecycle_reason": "No trade signal to track"
        }

    now = utc_now()
    expires_at = now + timedelta(minutes=ttl_minutes)

    return {
        "has_signal": True,
        "signal_id": str(uuid.uuid4())[:16],
        "signal_status": "Detected",
        "signal": signal,
        "symbol": symbol,
        "timeframe": timeframe,
        "confidence": confidence,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "max_tp_hit": "none",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "reason": reason,
        "lifecycle_reason": f"{signal} signal detected and waiting for confirmation"
    }


def _parse_time(value):
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _is_expired(signal_data):
    expires_at = _parse_time(signal_data.get("expires_at", ""))

    if not expires_at:
        return False

    return utc_now() >= expires_at


def _mark(signal_data, status, reason, max_tp_hit=None):
    signal_data["signal_status"] = status
    signal_data["updated_at"] = utc_now_iso()
    signal_data["lifecycle_reason"] = reason

    if max_tp_hit:
        signal_data["max_tp_hit"] = max_tp_hit

    return signal_data


def _current_max_tp(signal_data):
    return signal_data.get("max_tp_hit", "none")


def _tp_rank(tp):
    ranks = {
        "none": 0,
        "TP1 Hit": 1,
        "TP2 Hit": 2,
        "TP3 Hit": 3
    }
    return ranks.get(tp, 0)


def _upgrade_tp(signal_data, new_tp):
    old_tp = _current_max_tp(signal_data)

    if _tp_rank(new_tp) > _tp_rank(old_tp):
        signal_data["max_tp_hit"] = new_tp

    return signal_data.get("max_tp_hit", new_tp)


def update_signal_status(signal_data, current_price):
    """
    QuantBado Signal Lifecycle v0.3

    v0.3 logic:
    - TP1 Hit is partial, signal stays active.
    - TP2 Hit is partial, signal stays active.
    - TP3 Hit is final.
    - SL Hit is final.
    - Expired is final.
    - max_tp_hit tracks the highest target reached.
    """

    if not signal_data or not signal_data.get("has_signal"):
        return {
            "has_signal": False,
            "signal_status": "No Signal",
            "signal_id": "",
            "lifecycle_reason": "No trade signal to track"
        }

    current_status = signal_data.get("signal_status")

    if current_status in FINAL_STATUSES:
        return signal_data

    if current_status == "TP Hit":
        signal_data["signal_status"] = "TP1 Hit"
        signal_data["max_tp_hit"] = "TP1 Hit"

    if _is_expired(signal_data):
        max_tp = _current_max_tp(signal_data)

        if max_tp in ["TP1 Hit", "TP2 Hit"]:
            return _mark(
                signal_data,
                max_tp,
                f"Signal expired after reaching {max_tp}",
                max_tp_hit=max_tp
            )

        return _mark(
            signal_data,
            "Expired",
            "Signal expired before hitting target or stop"
        )

    side = signal_data.get("signal")
    entry = float(signal_data.get("entry", 0))
    sl = float(signal_data.get("sl", 0))
    tp1 = float(signal_data.get("tp1", 0))
    tp2 = float(signal_data.get("tp2", 0))
    tp3 = float(signal_data.get("tp3", 0))
    price = float(current_price)

    if side == "BUY":
        if sl > 0 and price <= sl:
            return _mark(signal_data, "SL Hit", "BUY signal hit stop loss")

        if tp3 > 0 and price >= tp3:
            max_tp = _upgrade_tp(signal_data, "TP3 Hit")
            return _mark(signal_data, "TP3 Hit", "BUY signal reached TP3 zone", max_tp)

        if tp2 > 0 and price >= tp2:
            max_tp = _upgrade_tp(signal_data, "TP2 Hit")
            return _mark(signal_data, "TP2 Hit", "BUY signal reached TP2 zone, waiting for TP3", max_tp)

        if tp1 > 0 and price >= tp1:
            max_tp = _upgrade_tp(signal_data, "TP1 Hit")
            return _mark(signal_data, "TP1 Hit", "BUY signal reached TP1 zone, waiting for TP2/TP3", max_tp)

        if entry > 0 and price > entry:
            current_max = _current_max_tp(signal_data)
            if current_max in ["TP1 Hit", "TP2 Hit"]:
                return _mark(signal_data, current_max, f"BUY signal holding after {current_max}", current_max)
            return _mark(signal_data, "Active", "BUY signal active and moving above entry")

        return _mark(signal_data, "Waiting Confirmation", "BUY signal waiting for price confirmation")

    if side == "SELL":
        if sl > 0 and price >= sl:
            return _mark(signal_data, "SL Hit", "SELL signal hit stop loss")

        if tp3 > 0 and price <= tp3:
            max_tp = _upgrade_tp(signal_data, "TP3 Hit")
            return _mark(signal_data, "TP3 Hit", "SELL signal reached TP3 zone", max_tp)

        if tp2 > 0 and price <= tp2:
            max_tp = _upgrade_tp(signal_data, "TP2 Hit")
            return _mark(signal_data, "TP2 Hit", "SELL signal reached TP2 zone, waiting for TP3", max_tp)

        if tp1 > 0 and price <= tp1:
            max_tp = _upgrade_tp(signal_data, "TP1 Hit")
            return _mark(signal_data, "TP1 Hit", "SELL signal reached TP1 zone, waiting for TP2/TP3", max_tp)

        if entry > 0 and price < entry:
            current_max = _current_max_tp(signal_data)
            if current_max in ["TP1 Hit", "TP2 Hit"]:
                return _mark(signal_data, current_max, f"SELL signal holding after {current_max}", current_max)
            return _mark(signal_data, "Active", "SELL signal active and moving below entry")

        return _mark(signal_data, "Waiting Confirmation", "SELL signal waiting for price confirmation")

    return _mark(signal_data, "No Signal", "Unknown signal side")