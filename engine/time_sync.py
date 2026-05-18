from datetime import datetime, timezone


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def timestamp_to_utc_iso(timestamp):
    try:
        return datetime.fromtimestamp(int(timestamp), tz=timezone.utc).isoformat()
    except Exception:
        return None


def build_time_context(broker_timestamp=None):
    return {
        "server_time_utc": utc_now_iso(),
        "broker_time_utc": timestamp_to_utc_iso(broker_timestamp) if broker_timestamp else None
    }
