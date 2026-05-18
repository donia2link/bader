import json
from pathlib import Path


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


def get_active_signal(user_key, symbol, timeframe):
    data = _load_all_signals()
    key = make_signal_key(user_key, symbol, timeframe)

    signal = data.get(key)

    if not signal:
        return None

    status = signal.get("signal_status")

    if status in FINAL_STATUSES:
        return None

    return signal


def save_active_signal(user_key, symbol, timeframe, signal_data):
    data = _load_all_signals()
    key = make_signal_key(user_key, symbol, timeframe)

    data[key] = signal_data
    _save_all_signals(data)

    return signal_data


def update_active_signal(user_key, symbol, timeframe, signal_data):
    return save_active_signal(user_key, symbol, timeframe, signal_data)


def close_active_signal(user_key, symbol, timeframe, signal_data):
    data = _load_all_signals()
    key = make_signal_key(user_key, symbol, timeframe)

    data[key] = signal_data
    _save_all_signals(data)

    return signal_data


def clear_final_signals():
    data = _load_all_signals()
    cleaned = {}

    for key, signal in data.items():
        if signal.get("signal_status") not in FINAL_STATUSES:
            cleaned[key] = signal

    _save_all_signals(cleaned)

    return {
        "before": len(data),
        "after": len(cleaned),
        "removed": len(data) - len(cleaned)
    }


