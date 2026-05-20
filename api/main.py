import sys
import json
from pathlib import Path
from typing import List, Dict

from fastapi import FastAPI
from pydantic import BaseModel, Field

sys.path.append("C:/QuantProject/engine")

from market_reader import analyze_market
from multi_timeframe_engine import analyze_multi_timeframe
from symbol_engine import get_symbol_info
from time_sync import utc_now_iso
from event_bus import emit_analyze_request, emit_engine_error, emit_user_connected
from historical_storage import save_analysis, save_candles_snapshot
from signal_lifecycle import build_new_signal
from signal_store import (
    save_active_signal,
    update_active_signal,
    clear_final_signals,
    _load_all_signals,
    ACTIVE_SIGNALS_FILE,
)
from performance_engine import build_performance_summary, reset_performance_records


app = FastAPI(
    title="QuantBado Market Reader",
    version="2.4.0"
)

BASE_DIR = Path("C:/QuantProject")
CONFIG_FILE = BASE_DIR / "config" / "settings.json"
USERS_FILE = BASE_DIR / "users" / "users.json"
LOGS_DIR = BASE_DIR / "logs"
MARKET_LOG_FILE = LOGS_DIR / "market_logs.jsonl"

FINAL_STATUSES = ["TP Hit", "TP1 Hit", "TP2 Hit", "TP3 Hit", "SL Hit", "Expired"]


class Candle(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float


class AnalyzeRequest(BaseModel):
    user_key: str = Field(..., min_length=3)
    symbol: str
    timeframe: str
    candles: List[Candle]


class AnalyzeMTFRequest(BaseModel):
    user_key: str = Field(..., min_length=3)
    symbol: str
    candles_by_timeframe: Dict[str, List[Candle]]


class AdminRequest(BaseModel):
    admin_key: str = Field(..., min_length=3)


class TestSignalRequest(BaseModel):
    admin_key: str = Field(..., min_length=3)
    user_key: str = Field(..., min_length=3)
    symbol: str
    timeframe: str
    signal: str = "BUY"
    entry: float
    sl: float
    tp1: float
    tp2: float
    tp3: float
    confidence: float = 88
    ttl_minutes: int = 60


class ForceCloseSignalRequest(BaseModel):
    admin_key: str = Field(..., min_length=3)
    user_key: str = Field(..., min_length=3)
    symbol: str
    timeframe: str
    status: str = "TP1 Hit"


def load_settings():
    if not CONFIG_FILE.exists():
        return {}

    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_admin_key():
    settings = load_settings()
    return settings.get("admin_key", "")


def check_admin_key(admin_key: str):
    configured_key = get_admin_key()
    return bool(configured_key) and admin_key == configured_key


def admin_error():
    return {
        "status": "error",
        "code": "INVALID_ADMIN_KEY",
        "message": "Invalid admin key",
        "server_time_utc": utc_now_iso()
    }


def load_users():
    if not USERS_FILE.exists():
        return {}

    try:
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_market_log(payload: dict):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    with MARKET_LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def read_last_market_log():
    if not MARKET_LOG_FILE.exists():
        return None

    try:
        with MARKET_LOG_FILE.open("r", encoding="utf-8") as f:
            lines = f.readlines()

        if not lines:
            return None

        last_line = lines[-1].strip()

        if not last_line:
            return None

        return json.loads(last_line)
    except Exception as e:
        return {
            "error": str(e)
        }


@app.get("/")
def home():
    return {
        "status": "online",
        "project": "QuantBado Market Reader",
        "version": "2.4.0",
        "time_utc": utc_now_iso()
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "api": "online",
        "version": "2.4.0",
        "settings_file_exists": CONFIG_FILE.exists(),
        "users_file_exists": USERS_FILE.exists(),
        "logs_dir_exists": LOGS_DIR.exists(),
        "time_utc": utc_now_iso()
    }


@app.get("/signal")
def old_signal():
    return {
        "status": "ok",
        "message": "Use POST /analyze for real market reader",
        "endpoint": "/analyze"
    }


@app.post("/admin/system-status")
def admin_system_status(data: AdminRequest):
    if not check_admin_key(data.admin_key):
        return admin_error()

    active_signals = _load_all_signals()
    performance = build_performance_summary()
    users = load_users()
    last_market_log = read_last_market_log()

    return {
        "status": "ok",
        "api_version": "2.4.0",
        "server_time_utc": utc_now_iso(),
        "files": {
            "settings_file_exists": CONFIG_FILE.exists(),
            "users_file_exists": USERS_FILE.exists(),
            "logs_dir_exists": LOGS_DIR.exists(),
            "active_signals_file_exists": ACTIVE_SIGNALS_FILE.exists(),
            "market_log_file_exists": MARKET_LOG_FILE.exists()
        },
        "users": {
            "users_count": len(users),
            "active_users_count": sum(1 for user in users.values() if user.get("active", False))
        },
        "active_signals": {
            "count": len(active_signals),
            "signals": active_signals
        },
        "performance": performance,
        "last_market_log": last_market_log
    }


@app.post("/admin/active-signals")
def admin_active_signals(data: AdminRequest):
    if not check_admin_key(data.admin_key):
        return admin_error()

    return {
        "status": "ok",
        "file_exists": ACTIVE_SIGNALS_FILE.exists(),
        "signals": _load_all_signals(),
        "server_time_utc": utc_now_iso()
    }


@app.post("/admin/clear-signals")
def admin_clear_signals(data: AdminRequest):
    if not check_admin_key(data.admin_key):
        return admin_error()

    if ACTIVE_SIGNALS_FILE.exists():
        ACTIVE_SIGNALS_FILE.unlink()

    return {
        "status": "ok",
        "message": "Active signals cleared",
        "server_time_utc": utc_now_iso()
    }


@app.post("/admin/clear-final-signals")
def admin_clear_final_signals(data: AdminRequest):
    if not check_admin_key(data.admin_key):
        return admin_error()

    result = clear_final_signals()

    return {
        "status": "ok",
        "result": result,
        "server_time_utc": utc_now_iso()
    }


@app.post("/admin/performance-summary")
def admin_performance_summary(data: AdminRequest):
    if not check_admin_key(data.admin_key):
        return admin_error()

    summary = build_performance_summary()

    return {
        "status": "ok",
        "performance": summary,
        "server_time_utc": utc_now_iso()
    }


@app.post("/admin/reset-performance")
def admin_reset_performance(data: AdminRequest):
    if not check_admin_key(data.admin_key):
        return admin_error()

    result = reset_performance_records()

    return {
        "status": "ok",
        "result": result,
        "server_time_utc": utc_now_iso()
    }


@app.post("/admin/reset-test-environment")
def admin_reset_test_environment(data: AdminRequest):
    if not check_admin_key(data.admin_key):
        return admin_error()

    performance_reset = reset_performance_records()

    active_signals_before = 0
    if ACTIVE_SIGNALS_FILE.exists():
        current_signals = _load_all_signals()
        active_signals_before = len(current_signals)
        ACTIVE_SIGNALS_FILE.unlink()

    performance_after = build_performance_summary()

    return {
        "status": "ok",
        "message": "Test environment reset successfully",
        "performance_reset": performance_reset,
        "active_signals_cleared": active_signals_before,
        "performance_after": performance_after,
        "server_time_utc": utc_now_iso()
    }


@app.post("/admin/test-signal")
def admin_test_signal(data: TestSignalRequest):
    if not check_admin_key(data.admin_key):
        return admin_error()

    signal = data.signal.upper()

    if signal not in ["BUY", "SELL"]:
        return {
            "status": "error",
            "message": "signal must be BUY or SELL",
            "server_time_utc": utc_now_iso()
        }

    lifecycle = build_new_signal(
        user_key=data.user_key,
        symbol=data.symbol,
        timeframe=data.timeframe,
        signal=signal,
        confidence=data.confidence,
        entry=data.entry,
        sl=data.sl,
        tp1=data.tp1,
        tp2=data.tp2,
        tp3=data.tp3,
        reason="ADMIN TEST SIGNAL",
        ttl_minutes=data.ttl_minutes
    )

    save_active_signal(
        user_key=data.user_key,
        symbol=data.symbol,
        timeframe=data.timeframe,
        signal_data=lifecycle
    )

    return {
        "status": "ok",
        "message": "Test signal created",
        "signal": lifecycle,
        "server_time_utc": utc_now_iso()
    }


@app.post("/admin/force-close-signal")
def admin_force_close_signal(data: ForceCloseSignalRequest):
    if not check_admin_key(data.admin_key):
        return admin_error()

    status = data.status.strip()

    if status not in FINAL_STATUSES:
        return {
            "status": "error",
            "code": "INVALID_FINAL_STATUS",
            "message": "status must be one of: TP1 Hit, TP2 Hit, TP3 Hit, SL Hit, Expired",
            "server_time_utc": utc_now_iso()
        }

    signals = _load_all_signals()
    key = f"{data.user_key}|{data.symbol}|{data.timeframe}"
    signal = signals.get(key)

    if not signal:
        return {
            "status": "error",
            "code": "SIGNAL_NOT_FOUND",
            "message": "No active signal found for user_key + symbol + timeframe",
            "key": key,
            "server_time_utc": utc_now_iso()
        }

    if status == "TP Hit":
        status = "TP1 Hit"

    signal["signal_status"] = status
    signal["updated_at"] = utc_now_iso()
    signal["lifecycle_reason"] = f"Admin force closed signal as {status}"

    update_active_signal(
        user_key=data.user_key,
        symbol=data.symbol,
        timeframe=data.timeframe,
        signal_data=signal
    )

    return {
        "status": "ok",
        "message": "Signal force closed",
        "key": key,
        "signal": signal,
        "performance": build_performance_summary(),
        "server_time_utc": utc_now_iso()
    }


@app.post("/analyze-mtf")
def analyze_mtf(data: AnalyzeMTFRequest):
    request_time = utc_now_iso()

    users = load_users()

    if data.user_key not in users:
        return {
            "status": "error",
            "code": "INVALID_USER_KEY",
            "message": "Invalid user key",
            "server_time_utc": request_time
        }

    user = users[data.user_key]

    if not user.get("active", False):
        return {
            "status": "error",
            "code": "INACTIVE_USER",
            "message": "User account is inactive",
            "server_time_utc": request_time
        }

    candles_by_timeframe = {}

    for timeframe, candles in data.candles_by_timeframe.items():
        candles_by_timeframe[timeframe.upper()] = [c.model_dump() for c in candles]

    symbol_info = get_symbol_info(data.symbol)

    try:
        emit_user_connected(
            user_key=data.user_key,
            symbol=symbol_info["normalized_symbol"]
        )

        result = analyze_multi_timeframe(
            symbol=symbol_info["normalized_symbol"],
            candles_by_timeframe=candles_by_timeframe,
            user_key=data.user_key
        )

        response = {
            "status": "ok",
            "user": user.get("name", "Unknown"),
            "symbol": data.symbol,
            "normalized_symbol": symbol_info["normalized_symbol"],
            "asset_class": symbol_info["asset_class"],
            "server_time_utc": request_time,
            **result
        }

        write_market_log({
            "event": "ANALYZE_MTF_REQUEST",
            "time_utc": request_time,
            "user_key": data.user_key,
            "user_name": user.get("name", "Unknown"),
            "symbol": data.symbol,
            "normalized_symbol": symbol_info["normalized_symbol"],
            "asset_class": symbol_info["asset_class"],
            "timeframes": list(candles_by_timeframe.keys()),
            "result": result
        })

        return response

    except Exception as e:
        emit_engine_error(
            user_key=data.user_key,
            symbol=data.symbol,
            timeframe="MTF",
            error=e
        )

        write_market_log({
            "event": "ANALYZE_MTF_ERROR",
            "time_utc": request_time,
            "user_key": data.user_key,
            "symbol": data.symbol,
            "error": str(e)
        })

        return {
            "status": "error",
            "code": "MTF_ENGINE_ERROR",
            "message": str(e),
            "server_time_utc": request_time
        }


@app.post("/analyze")
def analyze(data: AnalyzeRequest):
    request_time = utc_now_iso()

    users = load_users()

    if data.user_key not in users:
        return {
            "status": "error",
            "code": "INVALID_USER_KEY",
            "message": "Invalid user key",
            "server_time_utc": request_time
        }

    user = users[data.user_key]

    if not user.get("active", False):
        return {
            "status": "error",
            "code": "INACTIVE_USER",
            "message": "User account is inactive",
            "server_time_utc": request_time
        }

    if len(data.candles) < 20:
        return {
            "status": "error",
            "code": "NOT_ENOUGH_CANDLES",
            "message": "At least 20 candles are required",
            "server_time_utc": request_time
        }

    candles = [c.model_dump() for c in data.candles]
    symbol_info = get_symbol_info(data.symbol)

    try:
        emit_user_connected(
            user_key=data.user_key,
            symbol=symbol_info["normalized_symbol"]
        )

        emit_analyze_request(
            user_key=data.user_key,
            symbol=symbol_info["normalized_symbol"],
            timeframe=data.timeframe,
            candles_count=len(candles)
        )

        result = analyze_market(
            symbol=symbol_info["normalized_symbol"],
            timeframe=data.timeframe,
            candles=candles,
            user_key=data.user_key
        )

        response = {
            "status": "ok",
            "user": user.get("name", "Unknown"),
            "symbol": data.symbol,
            "normalized_symbol": symbol_info["normalized_symbol"],
            "asset_class": symbol_info["asset_class"],
            "timeframe": data.timeframe,
            "candles_count": len(candles),
            "server_time_utc": request_time,
            **result
        }

        save_analysis(
            user_key=data.user_key,
            symbol=symbol_info["normalized_symbol"],
            timeframe=data.timeframe,
            candles_count=len(candles),
            result=result
        )

        save_candles_snapshot(
            user_key=data.user_key,
            symbol=symbol_info["normalized_symbol"],
            timeframe=data.timeframe,
            candles=candles
        )

        write_market_log({
            "event": "ANALYZE_REQUEST",
            "time_utc": request_time,
            "user_key": data.user_key,
            "user_name": user.get("name", "Unknown"),
            "symbol": data.symbol,
            "normalized_symbol": symbol_info["normalized_symbol"],
            "asset_class": symbol_info["asset_class"],
            "timeframe": data.timeframe,
            "candles_count": len(candles),
            "result": result
        })

        return response

    except Exception as e:
        emit_engine_error(
            user_key=data.user_key,
            symbol=data.symbol,
            timeframe=data.timeframe,
            error=e
        )

        write_market_log({
            "event": "ANALYZE_ERROR",
            "time_utc": request_time,
            "user_key": data.user_key,
            "symbol": data.symbol,
            "timeframe": data.timeframe,
            "error": str(e)
        })

        return {
            "status": "error",
            "code": "ENGINE_ERROR",
            "message": str(e),
            "server_time_utc": request_time
        }