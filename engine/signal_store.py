import json
from pathlib import Path

from performance_engine import record_closed_signal


BASE_DIR = Path("C:/QuantProject")
LOGS_DIR = BASE_DIR / "logs"
ACTIVE_SIGNALS_FILE = LOGS_DIR / "active_signals.json"


FINAL_STATUSES = [
    "TP Hit",
    "TP1 Hit",
    "TP2 Hit",
    "TP3 Hit",
    "SL Hit",
    "Expired"
]


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

    if not data:
        if ACTIVE_SIGNALS_FILE.exists():
            ACTIVE_SIGNALS_FILE.unlink()
        return

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


def _is_final(signal_data):
    if not signal_data:
        return False

    return signal_data.get("signal_status") in FINAL_STATUSES


def _record_if_final(signal_data):
    if not _is_final(signal_data):
        return {
            "recorded": False,
            "reason": "Signal is not final"
        }

    return record_closed_signal(signal_data)


def get_active_signal(user_key, symbol, timeframe):
    data = _load_all_signals()
    key = make_signal_key(user_key, symbol, timeframe)

    signal = data.get(key)

    if not signal:
        return None

    if _is_final(signal):
        _record_if_final(signal)

        if key in data:
            del data[key]
            _save_all_signals(data)

        return None

    return signal


def save_active_signal(user_key, symbol, timeframe, signal_data):
    data = _load_all_signals()
    key = make_signal_key(user_key, symbol, timeframe)

    signal_data = _ensure_user_key(signal_data, user_key)

    if _is_final(signal_data):
        record_result = _record_if_final(signal_data)

        if key in data:
            del data[key]

        _save_all_signals(data)

        return {
            **signal_data,
            "store_action": "recorded_and_removed",
            "record_result": record_result
        }

    data[key] = signal_data
    _save_all_signals(data)

    return signal_data


def update_active_signal(user_key, symbol, timeframe, signal_data):
    return save_active_signal(user_key, symbol, timeframe, signal_data)


def close_active_signal(user_key, symbol, timeframe, signal_data):
    return save_active_signal(user_key, symbol, timeframe, signal_data)


def clear_final_signals():
    data = _load_all_signals()
    cleaned = {}

    removed = 0
    recorded = 0

    for key, signal in data.items():
        if _is_final(signal):
            result = _record_if_final(signal)
            removed += 1

            if result.get("recorded"):
                recorded += 1
        else:
            cleaned[key] = signal

    _save_all_signals(cleaned)

    return {
        "before": len(data),
        "after": len(cleaned),
        "removed": removed,
        "recorded": recorded
    }