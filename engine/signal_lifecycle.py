from datetime import datetime, timezone, timedelta
import uuid


FINAL_STATUSES = ["TP1 Hit", "TP2 Hit", "TP3 Hit", "SL Hit", "Expired"]


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


def _mark(signal_data, status, reason):
    signal_data["signal_status"] = status
    signal_data["updated_at"] = utc_now_iso()
    signal_data["lifecycle_reason"] = reason
    return signal_data


def update_signal_status(signal_data, current_price):
    """
    Updates signal status based on current market price.

    v0.2:
    - BUY:
      SL if price <= SL
      TP3 if price >= TP3
      TP2 if price >= TP2
      TP1 if price >= TP1
      Active if price > Entry
      Waiting Confirmation otherwise

    - SELL:
      SL if price >= SL
      TP3 if price <= TP3
      TP2 if price <= TP2
      TP1 if price <= TP1
      Active if price < Entry
      Waiting Confirmation otherwise
    """

    if not signal_data or not signal_data.get("has_signal"):
        return {
            "has_signal": False,
            "signal_status": "No Signal",
            "signal_id": "",
            "lifecycle_reason": "No trade signal to track"
        }

    current_status = signal_data.get("signal_status")

    if current_status in FINAL_STATUSES or current_status == "TP Hit":
        if current_status == "TP Hit":
            return _mark(signal_data, "TP1 Hit", "Legacy TP Hit normalized to TP1 Hit")
        return signal_data

    if _is_expired(signal_data):
        return _mark(signal_data, "Expired", "Signal expired before hitting target or stop")

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
            return _mark(signal_data, "TP3 Hit", "BUY signal reached TP3 zone")

        if tp2 > 0 and price >= tp2:
            return _mark(signal_data, "TP2 Hit", "BUY signal reached TP2 zone")

        if tp1 > 0 and price >= tp1:
            return _mark(signal_data, "TP1 Hit", "BUY signal reached TP1 zone")

        if entry > 0 and price > entry:
            return _mark(signal_data, "Active", "BUY signal active and moving above entry")

        return _mark(signal_data, "Waiting Confirmation", "BUY signal waiting for price confirmation")

    if side == "SELL":
        if sl > 0 and price >= sl:
            return _mark(signal_data, "SL Hit", "SELL signal hit stop loss")

        if tp3 > 0 and price <= tp3:
            return _mark(signal_data, "TP3 Hit", "SELL signal reached TP3 zone")

        if tp2 > 0 and price <= tp2:
            return _mark(signal_data, "TP2 Hit", "SELL signal reached TP2 zone")

        if tp1 > 0 and price <= tp1:
            return _mark(signal_data, "TP1 Hit", "SELL signal reached TP1 zone")

        if entry > 0 and price < entry:
            return _mark(signal_data, "Active", "SELL signal active and moving below entry")

        return _mark(signal_data, "Waiting Confirmation", "SELL signal waiting for price confirmation")

    return _mark(signal_data, "No Signal", "Unknown signal side")