from datetime import datetime, timezone, timedelta
import hashlib


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def make_signal_id(user_key, symbol, timeframe, signal, entry):
    raw = f"{user_key}|{symbol}|{timeframe}|{signal}|{entry}|{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


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
    """
    Create a new signal lifecycle object.
    This does not save to database yet. It only builds the lifecycle structure.
    """

    if signal not in ["BUY", "SELL"]:
        return {
            "has_signal": False,
            "signal_status": "No Signal",
            "signal_id": "",
            "lifecycle_reason": "No trade signal to track"
        }

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=ttl_minutes)

    signal_id = make_signal_id(user_key, symbol, timeframe, signal, entry)

    return {
        "has_signal": True,
        "signal_id": signal_id,
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
        "lifecycle_reason": "Signal detected and waiting for confirmation"
    }


def update_signal_status(signal_data, current_price):
    """
    Update signal status based on current price.
    """

    if not signal_data or not signal_data.get("has_signal"):
        return {
            "has_signal": False,
            "signal_status": "No Signal",
            "lifecycle_reason": "No active signal data"
        }

    signal = signal_data.get("signal")
    entry = float(signal_data.get("entry", 0))
    sl = float(signal_data.get("sl", 0))
    tp1 = float(signal_data.get("tp1", 0))
    tp2 = float(signal_data.get("tp2", 0))
    tp3 = float(signal_data.get("tp3", 0))

    now = datetime.now(timezone.utc)

    expires_at_raw = signal_data.get("expires_at")
    try:
        expires_at = datetime.fromisoformat(expires_at_raw)
    except Exception:
        expires_at = now

    if now >= expires_at:
        signal_data["signal_status"] = "Expired"
        signal_data["updated_at"] = now.isoformat()
        signal_data["lifecycle_reason"] = "Signal expired before target or stop"
        return signal_data

    current_price = float(current_price)

    if signal == "BUY":
        if current_price <= sl:
            signal_data["signal_status"] = "SL Hit"
            signal_data["lifecycle_reason"] = "Buy signal stop loss hit"
        elif current_price >= tp3:
            signal_data["signal_status"] = "TP Hit"
            signal_data["lifecycle_reason"] = "Buy signal TP3 hit"
        elif current_price >= tp2:
            signal_data["signal_status"] = "In Profit"
            signal_data["lifecycle_reason"] = "Buy signal reached TP2 zone"
        elif current_price >= tp1:
            signal_data["signal_status"] = "In Profit"
            signal_data["lifecycle_reason"] = "Buy signal reached TP1 zone"
        elif current_price > entry:
            signal_data["signal_status"] = "Active"
            signal_data["lifecycle_reason"] = "Buy signal active and moving above entry"
        else:
            signal_data["signal_status"] = "Waiting Confirmation"
            signal_data["lifecycle_reason"] = "Buy signal waiting for price confirmation"

    elif signal == "SELL":
        if current_price >= sl:
            signal_data["signal_status"] = "SL Hit"
            signal_data["lifecycle_reason"] = "Sell signal stop loss hit"
        elif current_price <= tp3:
            signal_data["signal_status"] = "TP Hit"
            signal_data["lifecycle_reason"] = "Sell signal TP3 hit"
        elif current_price <= tp2:
            signal_data["signal_status"] = "In Profit"
            signal_data["lifecycle_reason"] = "Sell signal reached TP2 zone"
        elif current_price <= tp1:
            signal_data["signal_status"] = "In Profit"
            signal_data["lifecycle_reason"] = "Sell signal reached TP1 zone"
        elif current_price < entry:
            signal_data["signal_status"] = "Active"
            signal_data["lifecycle_reason"] = "Sell signal active and moving below entry"
        else:
            signal_data["signal_status"] = "Waiting Confirmation"
            signal_data["lifecycle_reason"] = "Sell signal waiting for price confirmation"

    else:
        signal_data["signal_status"] = "No Signal"
        signal_data["lifecycle_reason"] = "Unsupported signal type"

    signal_data["updated_at"] = now.isoformat()
    return signal_data


