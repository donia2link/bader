import json
from pathlib import Path

from performance_engine import record_closed_signal


BASE_DIR = Path("C:/QuantProject")
LOGS_DIR = BASE_DIR / "logs"
ACTIVE_SIGNALS_FILE = LOGS_DIR / "active_signals.json"


FINAL_STATUSES = ["TP Hit", "SL Hit", "Expired"]


def _load_all_signals():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    if not ACTIVE_SIGNALS_FILE.exists():
        return {}

    try:
        return json.loads(ACTIVE_SIGNALS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_all_signals(data):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ACTIVE_SIGNALS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def make_signal_key(user_key, symbol, timeframe):
    return f"{user_key}|{symbol}|{timeframe}"


def _ensure_user_key(signal_data, user_key):
    if signal_data is None:
        return signal_data

    if not signal_data.get("user_key"):
        signal_data["user_key"] = user_key

    return signal_data


def _record_if_final(signal_data):
    if not signal_data:
        return

    if signal_data.get("signal_status") in FINAL_STATUSES:
        record_closed_signal(signal_data)


def get_active_signal(user_key, symbol, timeframe):
    data = _load_all_signals()
    key = make_signal_key(user_key, symbol, timeframe)

    signal = data.get(key)

    if not signal:
        return None

    status = signal.get("signal_status")

    if status in FINAL_STATUSES:
        _record_if_final(signal)
        return None

    return signal


def save_active_signal(user_key, symbol, timeframe, signal_data):
    data = _load_all_signals()
    key = make_signal_key(user_key, symbol, timeframe)

    signal_data = _ensure_user_key(signal_data, user_key)

    data[key] = signal_data
    _save_all_signals(data)

    _record_if_final(signal_data)

    return signal_data


def update_active_signal(user_key, symbol, timeframe, signal_data):
    return save_active_signal(user_key, symbol, timeframe, signal_data)


def close_active_signal(user_key, symbol, timeframe, signal_data):
    data = _load_all_signals()
    key = make_signal_key(user_key, symbol, timeframe)

    signal_data = _ensure_user_key(signal_data, user_key)

    data[key] = signal_data
    _save_all_signals(data)

    _record_if_final(signal_data)

    return signal_data


def clear_final_signals():
    data = _load_all_signals()
    cleaned = {}

    for key, signal in data.items():
        if signal.get("signal_status") in FINAL_STATUSES:
            _record_if_final(signal)
        else:
            cleaned[key] = signal

    _save_all_signals(cleaned)

    return {
        "before": len(data),
        "after": len(cleaned),
        "removed": len(data) - len(cleaned)
    }