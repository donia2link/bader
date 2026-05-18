import json
from pathlib import Path
from datetime import datetime, timezone


BASE_DIR = Path("C:/QuantProject")
LOGS_DIR = BASE_DIR / "logs"
EVENTS_FILE = LOGS_DIR / "events.jsonl"


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def emit_event(event_type, payload=None):
    """
    Write a system event to logs/events.jsonl.
    Every important system action should become an event.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    event = {
        "event_type": event_type,
        "time_utc": utc_now_iso(),
        "payload": payload or {}
    }

    with EVENTS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

    return event


def emit_analyze_request(user_key, symbol, timeframe, candles_count):
    return emit_event(
        "ANALYZE_REQUEST",
        {
            "user_key": user_key,
            "symbol": symbol,
            "timeframe": timeframe,
            "candles_count": candles_count
        }
    )


def emit_engine_error(user_key, symbol, timeframe, error):
    return emit_event(
        "ENGINE_ERROR",
        {
            "user_key": user_key,
            "symbol": symbol,
            "timeframe": timeframe,
            "error": str(error)
        }
    )


def emit_user_connected(user_key, symbol):
    return emit_event(
        "USER_CONNECTED",
        {
            "user_key": user_key,
            "symbol": symbol
        }
    )


def emit_new_signal(user_key, symbol, timeframe, signal_data):
    return emit_event(
        "NEW_SIGNAL",
        {
            "user_key": user_key,
            "symbol": symbol,
            "timeframe": timeframe,
            "signal": signal_data
        }
    )


