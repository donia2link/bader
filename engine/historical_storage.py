import json
from pathlib import Path
from datetime import datetime, timezone


BASE_DIR = Path("C:/QuantProject")
LOGS_DIR = BASE_DIR / "logs"
HISTORICAL_FILE = LOGS_DIR / "historical_storage.jsonl"


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def save_record(record_type, payload):
    """
    Save a historical record to logs/historical_storage.jsonl.
    Used for candles, analysis results, signals, scores, and market state.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    record = {
        "record_type": record_type,
        "time_utc": utc_now_iso(),
        "payload": payload or {}
    }

    with HISTORICAL_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record


def save_analysis(user_key, symbol, timeframe, candles_count, result):
    return save_record(
        "ANALYSIS_RESULT",
        {
            "user_key": user_key,
            "symbol": symbol,
            "timeframe": timeframe,
            "candles_count": candles_count,
            "result": result
        }
    )


def save_candles_snapshot(user_key, symbol, timeframe, candles):
    return save_record(
        "CANDLES_SNAPSHOT",
        {
            "user_key": user_key,
            "symbol": symbol,
            "timeframe": timeframe,
            "candles_count": len(candles) if candles else 0,
            "candles": candles or []
        }
    )


def save_signal(user_key, symbol, timeframe, signal_data):
    return save_record(
        "SIGNAL",
        {
            "user_key": user_key,
            "symbol": symbol,
            "timeframe": timeframe,
            "signal": signal_data
        }
    )



