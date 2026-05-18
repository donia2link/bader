import json
import shutil
from pathlib import Path
from datetime import datetime, timezone


BASE_DIR = Path("C:/QuantProject")
LOGS_DIR = BASE_DIR / "logs"
PERFORMANCE_FILE = LOGS_DIR / "performance_signals.jsonl"


def utc_stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def load_records():
    if not PERFORMANCE_FILE.exists():
        return []

    records = []

    with PERFORMANCE_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                records.append(json.loads(line))
            except Exception:
                pass

    return records


def save_records(records):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    with PERFORMANCE_FILE.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def cleanup_duplicates():
    if not PERFORMANCE_FILE.exists():
        return {
            "status": "ok",
            "message": "performance file does not exist",
            "before": 0,
            "after": 0,
            "removed": 0
        }

    backup_file = LOGS_DIR / f"performance_signals_backup_{utc_stamp()}.jsonl"
    shutil.copy2(PERFORMANCE_FILE, backup_file)

    records = load_records()

    seen = set()
    cleaned = []
    removed = 0

    for record in records:
        signal_id = record.get("signal_id", "")

        if not signal_id:
            cleaned.append(record)
            continue

        if signal_id in seen:
            removed += 1
            continue

        seen.add(signal_id)
        cleaned.append(record)

    save_records(cleaned)

    return {
        "status": "ok",
        "backup_file": str(backup_file),
        "before": len(records),
        "after": len(cleaned),
        "removed": removed
    }


if __name__ == "__main__":
    result = cleanup_duplicates()
    print(json.dumps(result, ensure_ascii=False, indent=2))