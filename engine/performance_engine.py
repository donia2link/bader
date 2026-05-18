import json
from pathlib import Path
from datetime import datetime, timezone


BASE_DIR = Path("C:/QuantProject")
LOGS_DIR = BASE_DIR / "logs"
PERFORMANCE_FILE = LOGS_DIR / "performance_signals.jsonl"

FINAL_STATUSES = ["TP Hit", "TP1 Hit", "TP2 Hit", "TP3 Hit", "SL Hit", "Expired"]


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def normalize_status(status):
    if status == "TP Hit":
        return "TP1 Hit"

    return status


def load_performance_records():
    if not PERFORMANCE_FILE.exists():
        return []

    records = []

    try:
        with PERFORMANCE_FILE.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                records.append(json.loads(line))
    except Exception:
        return []

    return records


def signal_already_recorded(signal_id):
    if not signal_id:
        return False

    records = load_performance_records()

    for record in records:
        if record.get("signal_id") == signal_id:
            return True

    return False


def record_closed_signal(signal_data):
    """
    Save closed/final signal to performance log.
    Supports TP1 Hit / TP2 Hit / TP3 Hit / SL Hit / Expired.

    v0.3:
    - Prevents duplicate records by signal_id.
    """

    if not signal_data:
        return {
            "recorded": False,
            "reason": "No signal data"
        }

    signal_id = signal_data.get("signal_id", "")

    if signal_already_recorded(signal_id):
        return {
            "recorded": False,
            "reason": "Signal already recorded",
            "signal_id": signal_id
        }

    raw_status = signal_data.get("signal_status")
    status = normalize_status(raw_status)

    if status not in FINAL_STATUSES:
        return {
            "recorded": False,
            "reason": "Signal is not final",
            "status": raw_status
        }

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    payload = {
        "record_type": "CLOSED_SIGNAL",
        "recorded_at": utc_now_iso(),
        "signal_id": signal_id,
        "user_key": signal_data.get("user_key", ""),
        "symbol": signal_data.get("symbol", ""),
        "timeframe": signal_data.get("timeframe", ""),
        "signal": signal_data.get("signal", ""),
        "signal_status": status,
        "raw_signal_status": raw_status,
        "confidence": signal_data.get("confidence", 0),
        "entry": signal_data.get("entry", 0),
        "sl": signal_data.get("sl", 0),
        "tp1": signal_data.get("tp1", 0),
        "tp2": signal_data.get("tp2", 0),
        "tp3": signal_data.get("tp3", 0),
        "created_at": signal_data.get("created_at", ""),
        "updated_at": signal_data.get("updated_at", ""),
        "expires_at": signal_data.get("expires_at", ""),
        "reason": signal_data.get("reason", ""),
        "lifecycle_reason": signal_data.get("lifecycle_reason", "")
    }

    with PERFORMANCE_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    return {
        "recorded": True,
        "signal_id": payload["signal_id"],
        "status": status
    }


def build_performance_summary():
    records = load_performance_records()

    total = len(records)

    tp1_hits = sum(1 for r in records if r.get("signal_status") in ["TP1 Hit", "TP Hit"])
    tp2_hits = sum(1 for r in records if r.get("signal_status") == "TP2 Hit")
    tp3_hits = sum(1 for r in records if r.get("signal_status") == "TP3 Hit")
    sl_hits = sum(1 for r in records if r.get("signal_status") == "SL Hit")
    expired = sum(1 for r in records if r.get("signal_status") == "Expired")

    tp_hits_total = tp1_hits + tp2_hits + tp3_hits

    buy_count = sum(1 for r in records if r.get("signal") == "BUY")
    sell_count = sum(1 for r in records if r.get("signal") == "SELL")

    win_rate = round((tp_hits_total / total) * 100, 2) if total else 0
    loss_rate = round((sl_hits / total) * 100, 2) if total else 0
    expired_rate = round((expired / total) * 100, 2) if total else 0

    tp1_rate = round((tp1_hits / total) * 100, 2) if total else 0
    tp2_rate = round((tp2_hits / total) * 100, 2) if total else 0
    tp3_rate = round((tp3_hits / total) * 100, 2) if total else 0

    avg_confidence = 0
    if total:
        avg_confidence = round(
            sum(float(r.get("confidence", 0)) for r in records) / total,
            2
        )

    symbols = {}
    timeframes = {}

    for r in records:
        symbol = r.get("symbol", "unknown")
        timeframe = r.get("timeframe", "unknown")

        symbols[symbol] = symbols.get(symbol, 0) + 1
        timeframes[timeframe] = timeframes.get(timeframe, 0) + 1

    best_symbol = max(symbols, key=symbols.get) if symbols else "none"
    best_timeframe = max(timeframes, key=timeframes.get) if timeframes else "none"

    unique_signal_ids = set()
    duplicate_count = 0

    for r in records:
        signal_id = r.get("signal_id", "")
        if signal_id in unique_signal_ids:
            duplicate_count += 1
        elif signal_id:
            unique_signal_ids.add(signal_id)

    return {
        "status": "ok",
        "total_closed_signals": total,
        "unique_closed_signals": len(unique_signal_ids),
        "duplicate_records_detected": duplicate_count,

        "tp_hits_total": tp_hits_total,
        "tp1_hits": tp1_hits,
        "tp2_hits": tp2_hits,
        "tp3_hits": tp3_hits,

        "sl_hits": sl_hits,
        "expired": expired,

        "buy_count": buy_count,
        "sell_count": sell_count,

        "win_rate": win_rate,
        "loss_rate": loss_rate,
        "expired_rate": expired_rate,

        "tp1_rate": tp1_rate,
        "tp2_rate": tp2_rate,
        "tp3_rate": tp3_rate,

        "avg_confidence": avg_confidence,
        "best_symbol_by_count": best_symbol,
        "best_timeframe_by_count": best_timeframe,
        "performance_version": "performance_engine_v0.3"
    }