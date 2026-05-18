import json
from pathlib import Path
from datetime import datetime, timezone


BASE_DIR = Path("C:/QuantProject")
LOGS_DIR = BASE_DIR / "logs"
PERFORMANCE_FILE = LOGS_DIR / "performance_signals.jsonl"

FINAL_STATUSES = ["TP Hit", "SL Hit", "Expired"]


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def record_closed_signal(signal_data):
    """
    Save closed/final signal to performance log.
    Only records TP Hit / SL Hit / Expired.
    """

    if not signal_data:
        return {
            "recorded": False,
            "reason": "No signal data"
        }

    status = signal_data.get("signal_status")

    if status not in FINAL_STATUSES:
        return {
            "recorded": False,
            "reason": "Signal is not final",
            "status": status
        }

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    payload = {
        "record_type": "CLOSED_SIGNAL",
        "recorded_at": utc_now_iso(),
        "signal_id": signal_data.get("signal_id", ""),
        "user_key": signal_data.get("user_key", ""),
        "symbol": signal_data.get("symbol", ""),
        "timeframe": signal_data.get("timeframe", ""),
        "signal": signal_data.get("signal", ""),
        "signal_status": status,
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


def build_performance_summary():
    records = load_performance_records()

    total = len(records)
    tp_hits = sum(1 for r in records if r.get("signal_status") == "TP Hit")
    sl_hits = sum(1 for r in records if r.get("signal_status") == "SL Hit")
    expired = sum(1 for r in records if r.get("signal_status") == "Expired")

    buy_count = sum(1 for r in records if r.get("signal") == "BUY")
    sell_count = sum(1 for r in records if r.get("signal") == "SELL")

    win_rate = round((tp_hits / total) * 100, 2) if total else 0
    loss_rate = round((sl_hits / total) * 100, 2) if total else 0
    expired_rate = round((expired / total) * 100, 2) if total else 0

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

    return {
        "status": "ok",
        "total_closed_signals": total,
        "tp_hits": tp_hits,
        "sl_hits": sl_hits,
        "expired": expired,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "win_rate": win_rate,
        "loss_rate": loss_rate,
        "expired_rate": expired_rate,
        "avg_confidence": avg_confidence,
        "best_symbol_by_count": best_symbol,
        "best_timeframe_by_count": best_timeframe
    }