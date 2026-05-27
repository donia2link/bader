import json
import uuid
from pathlib import Path
from datetime import datetime, timezone, timedelta


FRAME_SIGNAL_VERSION = "frame_signal_lifecycle_v1.0"

BASE_DIR = Path("C:/QuantProject")
DATA_DIR = BASE_DIR / "data"
FRAME_SIGNALS_FILE = DATA_DIR / "frame_active_signals.json"

FINAL_STATUSES = ["TP Hit", "SL Hit", "Expired"]


def _utc_now():
    return datetime.now(timezone.utc)


def _utc_now_iso():
    return _utc_now().isoformat()


def _parse_time(value):
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return _utc_now()


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _load_all():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not FRAME_SIGNALS_FILE.exists():
        return {}

    try:
        return json.loads(FRAME_SIGNALS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_all(signals):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FRAME_SIGNALS_FILE.write_text(
        json.dumps(signals, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def _signal_key(user_key, symbol, trade_style):
    return f"{user_key}|{symbol}|{trade_style}"


def get_active_frame_signal(user_key, symbol, trade_style):
    signals = _load_all()
    key = _signal_key(user_key, symbol, trade_style)
    signal = signals.get(key)

    if not signal:
        return None

    if signal.get("signal_status") in FINAL_STATUSES:
        return None

    return signal


def save_frame_signal(user_key, symbol, trade_style, signal):
    signals = _load_all()
    key = _signal_key(user_key, symbol, trade_style)
    signals[key] = signal
    _save_all(signals)
    return signal


def build_frame_signal(user_key, symbol, trade_style, opportunity, ttl_minutes=60):
    now = _utc_now()
    expires_at = now + timedelta(minutes=ttl_minutes)

    setup = opportunity.get("setup_direction", opportunity.get("signal", "WAIT"))

    return {
        "has_signal": True,
        "signal_id": str(uuid.uuid4())[:14],
        "user_key": user_key,
        "symbol": symbol,
        "trade_style": trade_style,
        "timeframe": opportunity.get("timeframe", "NONE"),
        "signal": setup,
        "signal_status": "Active",
        "quality": opportunity.get("quality", ""),
        "confidence": opportunity.get("confidence", 0),
        "score": opportunity.get("score", 0),
        "entry": _safe_float(opportunity.get("entry", 0)),
        "sl": _safe_float(opportunity.get("sl", 0)),
        "target": _safe_float(opportunity.get("target", 0)),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "reason": opportunity.get("reason", ""),
        "lifecycle_reason": "New frame signal created",
        "lifecycle_version": FRAME_SIGNAL_VERSION
    }


def update_frame_signal_status(signal, current_price):
    now = _utc_now()
    expires_at = _parse_time(signal.get("expires_at", now.isoformat()))

    direction = signal.get("signal", "WAIT")
    entry = _safe_float(signal.get("entry", 0))
    sl = _safe_float(signal.get("sl", 0))
    target = _safe_float(signal.get("target", 0))
    price = _safe_float(current_price, 0)

    signal["updated_at"] = now.isoformat()

    if signal.get("signal_status") in FINAL_STATUSES:
        return signal

    if now >= expires_at:
        signal["signal_status"] = "Expired"
        signal["lifecycle_reason"] = "Frame signal expired"
        return signal

    if direction == "BUY":
        if price <= sl and sl > 0:
            signal["signal_status"] = "SL Hit"
            signal["lifecycle_reason"] = "BUY frame signal hit SL"
            return signal

        if price >= target and target > 0:
            signal["signal_status"] = "TP Hit"
            signal["lifecycle_reason"] = "BUY frame signal hit target"
            return signal

        if price >= entry:
            signal["lifecycle_reason"] = "BUY frame signal active above entry"
        else:
            signal["lifecycle_reason"] = "BUY frame signal waiting around entry"

    elif direction == "SELL":
        if price >= sl and sl > 0:
            signal["signal_status"] = "SL Hit"
            signal["lifecycle_reason"] = "SELL frame signal hit SL"
            return signal

        if price <= target and target > 0:
            signal["signal_status"] = "TP Hit"
            signal["lifecycle_reason"] = "SELL frame signal hit target"
            return signal

        if price <= entry:
            signal["lifecycle_reason"] = "SELL frame signal active below entry"
        else:
            signal["lifecycle_reason"] = "SELL frame signal waiting around entry"

    else:
        signal["signal_status"] = "No Signal"
        signal["lifecycle_reason"] = "No valid frame signal direction"

    return signal


def should_replace_signal(existing, new_opportunity):
    if not existing:
        return True

    if existing.get("signal_status") in FINAL_STATUSES:
        return True

    old_score = _safe_float(existing.get("score", 0))
    new_score = _safe_float(new_opportunity.get("score", 0))

    old_signal = existing.get("signal", "WAIT")
    new_signal = new_opportunity.get("setup_direction", new_opportunity.get("signal", "WAIT"))

    if new_signal not in ["BUY", "SELL"]:
        return False

    if old_signal != new_signal and new_score >= old_score + 15:
        return True

    if new_signal == old_signal and new_score >= old_score + 20:
        return True

    return False


def track_frame_signal(user_key, symbol, trade_style, best_opportunity, current_price, ttl_minutes=60):
    existing = get_active_frame_signal(user_key, symbol, trade_style)

    if existing:
        existing = update_frame_signal_status(existing, current_price)

        if existing.get("signal_status") not in FINAL_STATUSES:
            if should_replace_signal(existing, best_opportunity):
                new_signal = build_frame_signal(
                    user_key=user_key,
                    symbol=symbol,
                    trade_style=trade_style,
                    opportunity=best_opportunity,
                    ttl_minutes=ttl_minutes
                )
                save_frame_signal(user_key, symbol, trade_style, new_signal)
                return new_signal

            save_frame_signal(user_key, symbol, trade_style, existing)
            return existing

        save_frame_signal(user_key, symbol, trade_style, existing)

    setup = best_opportunity.get("setup_direction", best_opportunity.get("signal", "WAIT"))
    entry = _safe_float(best_opportunity.get("entry", 0))
    score = _safe_float(best_opportunity.get("score", 0))

    if setup not in ["BUY", "SELL"] or entry <= 0 or score < 35:
        return {
            "has_signal": False,
            "signal_status": "No Signal",
            "signal": "WAIT",
            "signal_id": "",
            "lifecycle_reason": "No valid frame signal to track",
            "lifecycle_version": FRAME_SIGNAL_VERSION
        }

    new_signal = build_frame_signal(
        user_key=user_key,
        symbol=symbol,
        trade_style=trade_style,
        opportunity=best_opportunity,
        ttl_minutes=ttl_minutes
    )

    new_signal = update_frame_signal_status(new_signal, current_price)

    save_frame_signal(user_key, symbol, trade_style, new_signal)
    return new_signal