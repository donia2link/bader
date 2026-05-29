from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from datetime import datetime, timezone, timedelta
from ai_analyzer import analyze_market
import os
import json
import sqlite3
import hashlib
import secrets

app = FastAPI()

latest_signals = {}
WATCH_TFS = ["M1", "M5", "M15", "H1", "H4", "D1"]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "signals.db")

ACCESS_CONFIG_PATH = os.path.join(BASE_DIR, "access_config.json")
ACCESS_COOKIE_NAME = "qb_access"
SESSION_COOKIE_NAME = "qb_session"
PUBLIC_PREFIX = "/test-ai"
PUBLIC_PATHS = {
    "/health",
    "/analyze",
    "/login",
    "/logout",
    "/access-status",
}


def default_access_config():
    return {
        "enabled": True,
        "security": {
            "session_hours": 3,
            "lock_ip": True,
            "owner_bypass_ip_lock": True
        },
        "plans": {
            "owner": {
                "features": ["mobile", "dashboard", "performance", "history", "admin"],
                "allowed_symbols": ["*"],
                "allowed_timeframes": ["*"],
                "max_symbols": 0
            },
            "pro": {
                "features": ["mobile", "dashboard", "performance", "history"],
                "allowed_symbols": ["*"],
                "allowed_timeframes": ["M1", "M5", "M15", "H1", "H4", "D1"],
                "max_symbols": 0
            },
            "basic": {
                "features": ["mobile", "history"],
                "allowed_symbols": ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY"],
                "allowed_timeframes": ["M5", "M15", "H1"],
                "max_symbols": 10
            },
            "trial": {
                "features": ["mobile"],
                "allowed_symbols": ["XAUUSD"],
                "allowed_timeframes": ["M5"],
                "max_symbols": 1
            }
        },
        "users": [
            {
                "name": "Bedir",
                "key": "test123",
                "plan": "owner",
                "enabled": True,
                "expires_at": "",
                "allowed_symbols": ["*"],
                "allowed_timeframes": ["*"],
                "max_symbols": 0,
                "features": ["*"]
            },
            {
                "name": "Basic Demo",
                "key": "basic123",
                "plan": "basic",
                "enabled": True,
                "expires_at": "",
                "allowed_symbols": ["XAUUSD", "EURUSD", "GBPUSD"],
                "allowed_timeframes": ["M5", "M15"],
                "max_symbols": 3,
                "features": []
            },
            {
                "name": "Pro Demo",
                "key": "pro123",
                "plan": "pro",
                "enabled": True,
                "expires_at": "",
                "allowed_symbols": ["*"],
                "allowed_timeframes": ["M1", "M5", "M15", "H1", "H4", "D1"],
                "max_symbols": 0,
                "features": []
            }
        ]
    }


def ensure_access_config():
    if not os.path.exists(ACCESS_CONFIG_PATH):
        with open(ACCESS_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(default_access_config(), f, ensure_ascii=False, indent=2)


def load_access_config():
    try:
        ensure_access_config()
        with open(ACCESS_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            return default_access_config()
        cfg.setdefault("enabled", False)
        cfg.setdefault("security", default_access_config().get("security", {}))
        cfg.setdefault("users", [])
        return cfg
    except Exception:
        return default_access_config()


def _access_hash(key: str) -> str:
    return hashlib.sha256(str(key or "").encode("utf-8")).hexdigest()


def save_access_config(cfg: dict):
    cfg = cfg if isinstance(cfg, dict) else default_access_config()
    cfg.setdefault("enabled", True)
    cfg.setdefault("security", default_access_config().get("security", {}))
    cfg.setdefault("plans", default_access_config().get("plans", {}))
    cfg.setdefault("users", [])
    with open(ACCESS_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def access_plan(plan_name: str) -> dict:
    cfg = load_access_config()
    plans = cfg.get("plans") or default_access_config().get("plans", {})
    return dict(plans.get(plan_name or "", plans.get("trial", {})))


def _list_value(value, fallback=None):
    if fallback is None:
        fallback = []
    if value is None or value == "":
        return list(fallback)
    if isinstance(value, list):
        return [str(x).strip().upper() for x in value if str(x).strip()]
    if isinstance(value, str):
        return [x.strip().upper() for x in value.replace(";", ",").split(",") if x.strip()]
    return list(fallback)


def normalize_access_user(user: dict) -> dict:
    user = dict(user or {})
    plan_name = str(user.get("plan") or "trial").strip().lower()
    plan = access_plan(plan_name)
    user["plan"] = plan_name
    user["enabled"] = bool(user.get("enabled", True))
    user["expires_at"] = str(user.get("expires_at") or "").strip()
    user["allowed_symbols"] = _list_value(user.get("allowed_symbols"), plan.get("allowed_symbols", ["*"]))
    user["allowed_timeframes"] = _list_value(user.get("allowed_timeframes"), plan.get("allowed_timeframes", ["*"]))
    try:
        user["max_symbols"] = int(user.get("max_symbols", plan.get("max_symbols", 0)) or 0)
    except Exception:
        user["max_symbols"] = 0
    user["features"] = _list_value(user.get("features"), [])
    return user


def access_user_expired(user: dict) -> bool:
    exp = str((user or {}).get("expires_at") or "").strip()
    if not exp:
        return False
    try:
        # Accept YYYY-MM-DD or full ISO.
        if "T" in exp:
            exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
        else:
            exp_dt = datetime.fromisoformat(exp + "T23:59:59+00:00")
        if exp_dt.tzinfo is None:
            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > exp_dt
    except Exception:
        # Invalid expiry should fail closed.
        return True


def access_user_valid(user: dict) -> bool:
    if not user:
        return False
    user = normalize_access_user(user)
    if not user.get("enabled", True):
        return False
    if access_user_expired(user):
        return False
    return True


def user_features(user: dict) -> set:
    user = normalize_access_user(user or {})
    plan = access_plan(user.get("plan"))
    features = set(str(x).lower() for x in (plan.get("features") or []))
    extra = set(str(x).lower() for x in (user.get("features") or []))
    if "*" in extra:
        features.update(["mobile", "dashboard", "performance", "history", "admin"])
    else:
        features.update(extra)
    return features


def user_can(user: dict, feature: str) -> bool:
    if not user:
        return False
    user = normalize_access_user(user)
    if user.get("plan") == "open":
        return True
    return feature in user_features(user)


def access_allowed_symbols(user: dict) -> list:
    user = normalize_access_user(user or {})
    symbols = user.get("allowed_symbols") or ["*"]
    max_symbols = int(user.get("max_symbols") or 0)
    if "*" in symbols:
        return ["*"]
    clean = []
    for s in symbols:
        c = clean_symbol(str(s))
        if c and c not in clean:
            clean.append(c)
    if max_symbols > 0:
        clean = clean[:max_symbols]
    return clean


def access_allowed_timeframes(user: dict) -> list:
    user = normalize_access_user(user or {})
    tfs = [str(x).upper() for x in (user.get("allowed_timeframes") or ["*"])]
    if "*" in tfs:
        return WATCH_TFS[:]
    return [tf for tf in WATCH_TFS if tf in tfs]


def user_symbol_allowed(user: dict, symbol: str) -> bool:
    allowed = access_allowed_symbols(user)
    if "*" in allowed:
        return True
    return clean_symbol(symbol) in allowed


def user_timeframe_allowed(user: dict, timeframe: str) -> bool:
    return str(timeframe or "").upper() in access_allowed_timeframes(user)


def require_feature_json(request: Request, feature: str):
    user = get_access_user(request)
    if not user:
        return access_denied_json()
    if not user_can(user, feature):
        return JSONResponse(status_code=403, content={
            "status": "forbidden",
            "message": f"Feature not allowed for this plan: {feature}",
            "feature": feature,
            "login_url": f"{PUBLIC_PREFIX}/login"
        })
    return None


def require_feature_page(request: Request, feature: str):
    user = get_access_user(request)
    if not user:
        return access_login_redirect(request)
    if not user_can(user, feature):
        return HTMLResponse(f"""
<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Access denied</title>
<style>body{{margin:0;min-height:100vh;background:#05070b;color:#e5eef8;font-family:Arial,Tahoma,sans-serif;display:flex;align-items:center;justify-content:center;padding:20px}}.card{{max-width:440px;background:#0f172a;border:1px solid #263244;border-radius:24px;padding:22px;text-align:center}}a{{color:#38bdf8}}</style></head>
<body><div class="card"><h2>غير مسموح</h2><p>هذه الصفحة غير متاحة لخطة اشتراكك الحالية.</p><p>الميزة: <b>{feature}</b></p><a href="{PUBLIC_PREFIX}/mobile">الرجوع للموبايل</a></div></body></html>
""", status_code=403)
    return None


def filter_symbols_for_user(user: dict, symbols_map: dict) -> dict:
    if not user:
        return {}
    allowed = access_allowed_symbols(user)
    max_symbols = int(normalize_access_user(user).get("max_symbols") or 0)
    if "*" in allowed:
        values = sorted_symbol_items(symbols_map)
    else:
        values = [x for x in sorted_symbol_items(symbols_map) if clean_symbol(x.get("symbol", "")) in allowed]
    if max_symbols > 0:
        values = values[:max_symbols]
    return {x.get("symbol", ""): x for x in values if x.get("symbol")}


def filter_signals_for_user(user: dict, signals: dict) -> dict:
    if not user:
        return {}
    allowed_tfs = set(access_allowed_timeframes(user))
    out = {}
    for key, value in (signals or {}).items():
        symbol = value.get("symbol", "")
        tf = (value.get("requested_timeframe") or value.get("timeframe") or "").upper()
        if user_symbol_allowed(user, symbol) and tf in allowed_tfs:
            out[key] = value
    return out


def generate_access_key(prefix: str = "qb") -> str:
    return prefix + "_" + secrets.token_urlsafe(9).replace("-", "").replace("_", "")


def _find_access_user_by_key(key: str):
    cfg = load_access_config()
    for user in cfg.get("users", []):
        if str(user.get("key", "")) == str(key or ""):
            user = normalize_access_user(user)
            return user if access_user_valid(user) else None
    return None


def _find_access_user_by_hash(token_hash: str):
    cfg = load_access_config()
    for user in cfg.get("users", []):
        if _access_hash(user.get("key", "")) == str(token_hash or ""):
            user = normalize_access_user(user)
            return user if access_user_valid(user) else None
    return None


def get_access_user(request: Request):
    cfg = load_access_config()
    if not cfg.get("enabled", False):
        return {"name": "Access disabled", "plan": "open", "allowed_symbols": ["*"], "allowed_timeframes": ["*"], "features": ["*"], "enabled": True}

    key = request.query_params.get("key") or ""
    if key:
        user = _find_access_user_by_key(key)
        if user:
            return user

    token = request.cookies.get(ACCESS_COOKIE_NAME) or ""
    if token:
        user = _find_access_user_by_hash(token)
        if user and session_cookie_valid(request, user, token):
            return user

    return None


def is_access_allowed(request: Request) -> bool:
    return get_access_user(request) is not None


def access_denied_json():
    return JSONResponse(
        status_code=401,
        content={
            "status": "unauthorized",
            "message": "Login required",
            "login_url": f"{PUBLIC_PREFIX}/login"
        }
    )


def _safe_next_url(request: Request) -> str:
    path = request.url.path or "/mobile"
    query = request.url.query
    if not path.startswith(PUBLIC_PREFIX):
        path = PUBLIC_PREFIX + path
    return path + (("?" + query) if query else "")


def access_login_redirect(request: Request):
    return RedirectResponse(url=f"{PUBLIC_PREFIX}/login?next={_safe_next_url(request)}", status_code=302)


def set_access_cookie(response, key: str, session_id: str = ""):
    max_age = session_max_age_seconds()
    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=_access_hash(key),
        httponly=True,
        samesite="lax",
        max_age=max_age,
        path="/"
    )
    if session_id:
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=session_id,
            httponly=True,
            samesite="lax",
            max_age=max_age,
            path="/"
        )
    return response


CURRENCY_AR = {
    "USD": "الدولار الأمريكي", "EUR": "اليورو", "GBP": "الجنيه الإسترليني",
    "JPY": "الين الياباني", "CHF": "الفرنك السويسري", "CAD": "الدولار الكندي",
    "AUD": "الدولار الأسترالي", "NZD": "الدولار النيوزيلندي", "TRY": "الليرة التركية",
}
CURRENCY_EN = {
    "USD": "US Dollar", "EUR": "Euro", "GBP": "British Pound",
    "JPY": "Japanese Yen", "CHF": "Swiss Franc", "CAD": "Canadian Dollar",
    "AUD": "Australian Dollar", "NZD": "New Zealand Dollar", "TRY": "Turkish Lira",
}

SYMBOL_AR = {
    "XAUUSD": "الذهب مقابل الدولار", "XAGUSD": "الفضة مقابل الدولار",
    "XAUEUR": "الذهب مقابل اليورو", "XAGEUR": "الفضة مقابل اليورو",
    "XPTUSD": "البلاتين مقابل الدولار", "XPDUSD": "البلاديوم مقابل الدولار",
    "SOYBEANS": "فول الصويا", "SOYBEAN": "فول الصويا", "WHEAT": "القمح",
    "CORN": "الذرة", "COTTON": "القطن", "SUGAR": "السكر", "COFFEE": "القهوة",
    "COCOA": "الكاكاو", "ALUMINIUM": "الألمنيوم", "ALUMINUM": "الألمنيوم",
    "COPPER": "النحاس", "LEAD": "الرصاص", "NICKEL": "النيكل", "ZINC": "الزنك",
    "SPOTBRENT": "نفط برنت الفوري", "SPOTCRUDE": "النفط الخام الفوري",
    "BRENT": "نفط برنت", "CRUDE": "النفط الخام", "USOIL": "النفط الأمريكي",
    "UKOIL": "نفط برنت", "WTI": "النفط الأمريكي", "OIL": "النفط",
    "NATGAS": "الغاز الطبيعي", "NGAS": "الغاز الطبيعي",
    "BTCUSD": "بيتكوين مقابل الدولار", "ETHUSD": "إيثيريوم مقابل الدولار",
    "XRPUSD": "ريبل مقابل الدولار", "SOLUSD": "سولانا مقابل الدولار",
    "DOGEUSD": "دوجكوين مقابل الدولار", "LTCUSD": "لايتكوين مقابل الدولار",
    "ADAUSD": "كاردانو مقابل الدولار", "BNBUSD": "بينانس كوين مقابل الدولار",
    "US30": "مؤشر داو جونز", "US100": "مؤشر ناسداك", "NAS100": "مؤشر ناسداك",
    "USTEC": "مؤشر ناسداك", "US500": "مؤشر إس آند بي 500",
    "SPX500": "مؤشر إس آند بي 500", "SP500": "مؤشر إس آند بي 500",
    "GER40": "مؤشر داكس الألماني", "GER30": "مؤشر داكس الألماني",
    "DAX": "مؤشر داكس الألماني", "UK100": "مؤشر فوتسي البريطاني",
    "JP225": "مؤشر نيكاي الياباني", "JPN225": "مؤشر نيكاي الياباني",
    "HK50": "مؤشر هونغ كونغ", "FRA40": "مؤشر فرنسا 40", "AUS200": "مؤشر أستراليا 200",
}

SYMBOL_EN = {
    "XAUUSD": "Gold vs US Dollar", "XAGUSD": "Silver vs US Dollar",
    "XAUEUR": "Gold vs Euro", "XAGEUR": "Silver vs Euro",
    "XPTUSD": "Platinum vs US Dollar", "XPDUSD": "Palladium vs US Dollar",
    "SOYBEANS": "Soybeans", "SOYBEAN": "Soybeans", "WHEAT": "Wheat",
    "CORN": "Corn", "COTTON": "Cotton", "SUGAR": "Sugar", "COFFEE": "Coffee",
    "COCOA": "Cocoa", "ALUMINIUM": "Aluminium", "ALUMINUM": "Aluminum",
    "COPPER": "Copper", "LEAD": "Lead", "NICKEL": "Nickel", "ZINC": "Zinc",
    "SPOTBRENT": "Spot Brent Oil", "SPOTCRUDE": "Spot Crude Oil",
    "BRENT": "Brent Oil", "CRUDE": "Crude Oil", "USOIL": "US Oil",
    "UKOIL": "Brent Oil", "WTI": "US Oil", "OIL": "Oil",
    "NATGAS": "Natural Gas", "NGAS": "Natural Gas",
    "BTCUSD": "Bitcoin vs US Dollar", "ETHUSD": "Ethereum vs US Dollar",
    "XRPUSD": "Ripple vs US Dollar", "SOLUSD": "Solana vs US Dollar",
    "DOGEUSD": "Dogecoin vs US Dollar", "LTCUSD": "Litecoin vs US Dollar",
    "ADAUSD": "Cardano vs US Dollar", "BNBUSD": "Binance Coin vs US Dollar",
    "US30": "Dow Jones Index", "US100": "Nasdaq Index", "NAS100": "Nasdaq Index",
    "USTEC": "Nasdaq Index", "US500": "S&P 500 Index", "SPX500": "S&P 500 Index",
    "SP500": "S&P 500 Index", "GER40": "German DAX Index", "GER30": "German DAX Index",
    "DAX": "German DAX Index", "UK100": "UK FTSE Index",
    "JP225": "Japan Nikkei Index", "JPN225": "Japan Nikkei Index",
    "HK50": "Hong Kong Index", "FRA40": "France 40 Index", "AUS200": "Australia 200 Index",
}


# Favorite / priority symbols: these appear first in every list.
# You can edit these lists anytime. Use the broker's exact symbol names when needed.
FAVORITE_SYMBOLS = [
    "XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD",
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
    "US100", "NAS100", "USTEC", "US30", "US500", "SPX500",
    "GER40", "UK100", "JP225",
    "USOIL", "UKOIL", "SPOTBRENT", "SPOTCRUDE", "NATGAS",
]

PRIORITY_BY_CATEGORY = {
    "forex": [
        "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
        "EURJPY", "GBPJPY", "EURGBP", "AUDJPY", "CADJPY", "CHFJPY",
    ],
    "commodity": [
        "XAUUSD", "XAGUSD", "XAUEUR", "XAGEUR", "USOIL", "UKOIL",
        "SPOTBRENT", "SPOTCRUDE", "NATGAS", "COPPER", "SILVER", "GOLD",
    ],
    "index": [
        "US100", "NAS100", "USTEC", "US30", "US500", "SPX500", "SP500",
        "GER40", "DAX", "UK100", "JP225", "JPN225", "HK50", "FRA40", "AUS200",
    ],
    "crypto": [
        "BTCUSD", "ETHUSD", "SOLUSD", "BNBUSD", "XRPUSD", "ADAUSD", "DOGEUSD", "LTCUSD",
    ],
}


def symbol_rank(symbol: str, category: str = "other") -> tuple:
    clean = clean_symbol(symbol)
    fav_rank = FAVORITE_SYMBOLS.index(clean) if clean in FAVORITE_SYMBOLS else 999
    cat_list = PRIORITY_BY_CATEGORY.get(category, [])
    cat_rank = cat_list.index(clean) if clean in cat_list else 999
    return (fav_rank, cat_rank, clean)


def sorted_symbol_items(symbols_map: dict) -> list:
    return sorted(
        symbols_map.values(),
        key=lambda x: symbol_rank(x.get("symbol", ""), x.get("category", "other"))
    )


def is_favorite_symbol(symbol: str) -> bool:
    return clean_symbol(symbol) in FAVORITE_SYMBOLS


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _client_ip(request: Request) -> str:
    try:
        forwarded = request.headers.get("x-forwarded-for") or ""
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("x-real-ip") or ""
        if real_ip:
            return real_ip.strip()
        return request.client.host if request.client else ""
    except Exception:
        return ""


def _short_ua(request: Request) -> str:
    try:
        return str(request.headers.get("user-agent") or "")[:300]
    except Exception:
        return ""


def log_access_event(request: Request, event: str, status: str = "ok", user: dict = None, note: str = "", target_key: str = ""):
    try:
        if user is None:
            user = get_access_user(request)
        user = normalize_access_user(user) if user else {}
        key = str(user.get("key") or "")
        target_key = str(target_key or "")
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO access_logs
        (event, status, user_name, user_plan, user_key_hash, target_key_hash, path, method, ip, user_agent, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(event or "access")[:80],
            str(status or "ok")[:40],
            str(user.get("name") or "")[:120],
            str(user.get("plan") or "")[:40],
            _access_hash(key) if key else "",
            _access_hash(target_key) if target_key else "",
            str(request.url.path or "")[:200],
            str(request.method or "")[:20],
            _client_ip(request)[:80],
            _short_ua(request),
            str(note or "")[:500],
            now_iso(),
        ))
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_access_logs(limit: int = 250, event: str = "", user_hash: str = "") -> list:
    limit = max(1, min(int(limit or 250), 1000))
    conn = get_db()
    cur = conn.cursor()
    query = """
    SELECT id, event, status, user_name, user_plan, user_key_hash, target_key_hash,
           path, method, ip, user_agent, note, created_at
    FROM access_logs
    WHERE 1=1
    """
    params = []
    if event:
        query += " AND event = ?"
        params.append(event)
    if user_hash:
        query += " AND user_key_hash = ?"
        params.append(user_hash)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    cur.execute(query, params)
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows


def build_access_log_summary():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM access_logs")
    total = int(cur.fetchone()["c"] or 0)
    cur.execute("""
    SELECT event, COUNT(*) AS count
    FROM access_logs
    GROUP BY event
    ORDER BY count DESC
    LIMIT 20
    """)
    by_event = [dict(row) for row in cur.fetchall()]
    cur.execute("""
    SELECT user_name, user_plan, user_key_hash, COUNT(*) AS count, MAX(created_at) AS last_seen
    FROM access_logs
    WHERE user_key_hash != ''
    GROUP BY user_key_hash
    ORDER BY last_seen DESC
    LIMIT 100
    """)
    by_user = [dict(row) for row in cur.fetchall()]
    conn.close()
    return {"total": total, "by_event": by_event, "by_user": by_user}




def _parse_dt(value: str):
    try:
        if not value:
            return None
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def access_security_config() -> dict:
    cfg = load_access_config()
    sec = cfg.get("security") or default_access_config().get("security", {})
    return dict(sec)


def session_hours() -> float:
    try:
        return max(0.25, float(access_security_config().get("session_hours", 3) or 3))
    except Exception:
        return 3.0


def session_max_age_seconds() -> int:
    return int(session_hours() * 3600)


def ip_lock_enabled(user: dict) -> bool:
    sec = access_security_config()
    if not bool(sec.get("lock_ip", True)):
        return False
    user = normalize_access_user(user or {})
    if user.get("plan") == "owner" and bool(sec.get("owner_bypass_ip_lock", True)):
        return False
    return True


def cleanup_expired_sessions():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE active_sessions SET active = 0 WHERE active = 1 AND expires_at < ?", (now_iso(),))
        conn.commit()
        conn.close()
    except Exception:
        pass


def create_access_session(request: Request, user: dict, key: str) -> dict:
    cleanup_expired_sessions()
    user = normalize_access_user(user or {})
    key_hash = _access_hash(key)
    ip = _client_ip(request)
    ua = _short_ua(request)
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=session_max_age_seconds())).isoformat()

    if ip_lock_enabled(user):
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
        SELECT id, ip, created_at, expires_at
        FROM active_sessions
        WHERE user_key_hash = ? AND active = 1 AND expires_at > ?
        ORDER BY id DESC
        LIMIT 1
        """, (key_hash, now_iso()))
        row = cur.fetchone()
        conn.close()
        if row and str(row["ip"] or "") != str(ip or ""):
            return {"ok": False, "reason": "active_on_other_ip", "ip": row["ip"], "expires_at": row["expires_at"]}

    session_id = secrets.token_urlsafe(24)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO active_sessions
    (session_id, user_key_hash, user_name, user_plan, ip, user_agent, created_at, expires_at, last_seen, active)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
    """, (session_id, key_hash, user.get("name", ""), user.get("plan", ""), ip, ua, now_iso(), expires_at, now_iso()))
    conn.commit()
    conn.close()
    return {"ok": True, "session_id": session_id, "expires_at": expires_at}


def session_cookie_valid(request: Request, user: dict, token_hash: str) -> bool:
    session_id = request.cookies.get(SESSION_COOKIE_NAME) or ""
    if not session_id:
        return False
    cleanup_expired_sessions()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    SELECT * FROM active_sessions
    WHERE session_id = ? AND user_key_hash = ? AND active = 1
    ORDER BY id DESC LIMIT 1
    """, (session_id, token_hash))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False
    exp = _parse_dt(row["expires_at"])
    if not exp or datetime.now(timezone.utc) > exp:
        cur.execute("UPDATE active_sessions SET active = 0 WHERE id = ?", (row["id"],))
        conn.commit()
        conn.close()
        return False
    if ip_lock_enabled(user) and str(row["ip"] or "") != str(_client_ip(request) or ""):
        conn.close()
        return False
    cur.execute("UPDATE active_sessions SET last_seen = ? WHERE id = ?", (now_iso(), row["id"]))
    conn.commit()
    conn.close()
    return True


def deactivate_current_session(request: Request):
    try:
        session_id = request.cookies.get(SESSION_COOKIE_NAME) or ""
        if not session_id:
            return
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE active_sessions SET active = 0 WHERE session_id = ?", (session_id,))
        conn.commit()
        conn.close()
    except Exception:
        pass

def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS latest_signals (
        key TEXT PRIMARY KEY,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        category TEXT,
        signal TEXT,
        confidence REAL,
        updated_at TEXT,
        data_json TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS signal_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_hash TEXT UNIQUE,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        category TEXT,
        signal TEXT,
        confidence REAL,
        entry REAL,
        sl REAL,
        tp1 REAL,
        tp2 REAL,
        tp3 REAL,
        tp4 REAL,
        tp5 REAL,
        status TEXT DEFAULT 'active',
        reason TEXT,
        created_at TEXT NOT NULL,
        data_json TEXT NOT NULL
    )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_latest_symbol ON latest_signals(symbol)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_latest_category ON latest_signals(category)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_latest_timeframe ON latest_signals(timeframe)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_history_symbol ON signal_history(symbol)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_history_timeframe ON signal_history(timeframe)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_history_created ON signal_history(created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_history_status ON signal_history(status)")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS access_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event TEXT NOT NULL,
        status TEXT,
        user_name TEXT,
        user_plan TEXT,
        user_key_hash TEXT,
        target_key_hash TEXT,
        path TEXT,
        method TEXT,
        ip TEXT,
        user_agent TEXT,
        note TEXT,
        created_at TEXT NOT NULL
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_access_logs_created ON access_logs(created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_access_logs_user ON access_logs(user_key_hash)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_access_logs_event ON access_logs(event)")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS active_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT UNIQUE NOT NULL,
        user_key_hash TEXT NOT NULL,
        user_name TEXT,
        user_plan TEXT,
        ip TEXT,
        user_agent TEXT,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        last_seen TEXT,
        active INTEGER DEFAULT 1
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_active_sessions_key ON active_sessions(user_key_hash)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_active_sessions_ip ON active_sessions(ip)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_active_sessions_active ON active_sessions(active)")

    # V16 lifecycle migration: keep old databases safe while adding lifecycle fields.
    cur.execute("PRAGMA table_info(signal_history)")
    existing_cols = {row[1] for row in cur.fetchall()}
    lifecycle_columns = {
        "closed_at": "TEXT",
        "last_price": "REAL",
        "status_reason": "TEXT",
        "tp4": "REAL",
        "tp5": "REAL"
    }
    for col_name, col_type in lifecycle_columns.items():
        if col_name not in existing_cols:
            cur.execute(f"ALTER TABLE signal_history ADD COLUMN {col_name} {col_type}")

    conn.commit()
    conn.close()


def clean_symbol(symbol: str) -> str:
    s = (symbol or "").upper()
    for suffix in [".R", ".M", ".PRO", ".RAW", ".ECN", "_I", "-I"]:
        s = s.replace(suffix, "")
    return s


def category_icon(category: str) -> str:
    return {"forex": "💱", "commodity": "🟡", "index": "📈", "crypto": "₿"}.get(category, "•")


LIFECYCLE_LABELS_AR = {
    "active": "فعالة",
    "tp1_hit": "TP1 تحقق",
    "tp2_hit": "TP2 تحقق",
    "sl_hit": "ضربت ستوب",
    "cancelled": "ملغاة",
    "expired": "منتهية",
    "wait": "انتظار",
    "none": "لا توجد إشارة",
}

LIFECYCLE_LABELS_EN = {
    "active": "Active",
    "tp1_hit": "TP1 Hit",
    "tp2_hit": "TP2 Hit",
    "sl_hit": "SL Hit",
    "cancelled": "Cancelled",
    "expired": "Expired",
    "wait": "Waiting",
    "none": "No Signal",
}

LIFECYCLE_CLASS = {
    "active": "life-active",
    "tp1_hit": "life-tp1",
    "tp2_hit": "life-tp2",
    "sl_hit": "life-sl",
    "cancelled": "life-cancelled",
    "expired": "life-expired",
    "wait": "life-wait",
    "none": "life-none",
}


def lifecycle_label(status: str, lang: str = "ar") -> str:
    key = (status or "none").strip().lower()
    labels = LIFECYCLE_LABELS_AR if lang == "ar" else LIFECYCLE_LABELS_EN
    return labels.get(key, labels.get("none"))


def lifecycle_class(status: str) -> str:
    key = (status or "none").strip().lower()
    return LIFECYCLE_CLASS.get(key, "life-none")


def get_latest_history_state(symbol: str, timeframe: str):
    if not symbol or not timeframe:
        return None
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    SELECT id, status, status_reason, closed_at, last_price, created_at
    FROM signal_history
    WHERE symbol = ? AND timeframe = ?
    ORDER BY id DESC
    LIMIT 1
    """, (symbol, timeframe))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def apply_lifecycle_badge(compact: dict) -> dict:
    """Add user-facing lifecycle status fields for dashboard/mobile display."""
    data = dict(compact or {})
    symbol = data.get("symbol", "")
    tf = data.get("requested_timeframe") or data.get("timeframe", "")
    hist = get_latest_history_state(symbol, tf)

    if hist and hist.get("status"):
        status = str(hist.get("status") or "none").lower()
        data["lifecycle_id"] = hist.get("id")
        data["lifecycle_reason"] = hist.get("status_reason") or ""
        data["lifecycle_closed_at"] = hist.get("closed_at")
        data["lifecycle_last_price"] = hist.get("last_price")
        data["lifecycle_created_at"] = hist.get("created_at")
    else:
        sig = str(data.get("signal") or "WAIT").upper()
        status = "active" if sig in ["BUY", "SELL"] else "wait"
        data["lifecycle_reason"] = ""
        data["lifecycle_closed_at"] = None
        data["lifecycle_last_price"] = None

    data["lifecycle_status"] = status
    data["lifecycle_label_ar"] = lifecycle_label(status, "ar")
    data["lifecycle_label_en"] = lifecycle_label(status, "en")
    data["lifecycle_class"] = lifecycle_class(status)
    return data


def symbol_name(symbol: str, category: str, lang: str) -> str:
    s = clean_symbol(symbol)
    symbol_dict = SYMBOL_AR if lang == "ar" else SYMBOL_EN
    currency_dict = CURRENCY_AR if lang == "ar" else CURRENCY_EN

    if s in symbol_dict:
        return symbol_dict[s]

    for key, value in symbol_dict.items():
        if key in s:
            return value

    if category == "forex":
        found = [c for c in currency_dict.keys() if c in s]
        if len(found) >= 2:
            if lang == "ar":
                return f"{currency_dict.get(found[0], found[0])} مقابل {currency_dict.get(found[1], found[1])}"
            return f"{currency_dict.get(found[0], found[0])} vs {currency_dict.get(found[1], found[1])}"

    if category == "commodity":
        return "سلعة / معدن" if lang == "ar" else "Commodity / Metal"
    if category == "index":
        return "مؤشر عالمي" if lang == "ar" else "Global Index"
    if category == "crypto":
        return "عملة رقمية" if lang == "ar" else "Cryptocurrency"
    return "غير مصنف" if lang == "ar" else "Unclassified"


def cf(value, digits=5):
    try:
        if value is None:
            return None
        return round(float(value), digits)
    except Exception:
        return value


def compact_signal(result: dict) -> dict:
    symbol = result.get("symbol", "")
    category = result.get("category", "other")
    tf = result.get("requested_timeframe") or result.get("timeframe", "")

    return {
        "status": result.get("status", "ok"),
        "symbol": symbol,
        "symbol_ar": result.get("symbol_ar") or symbol_name(symbol, category, "ar"),
        "symbol_en": result.get("symbol_en") or symbol_name(symbol, category, "en"),
        "category": category,
        "icon": category_icon(category),
        "requested_timeframe": tf,
        "timeframe": tf,
        "signal": result.get("signal", "WAIT"),
        "confidence": cf(result.get("confidence", 0), 2),
        "current_price": cf(result.get("current_price") or result.get("price") or result.get("entry"), 5),
        "entry": cf(result.get("entry"), 5),
        "sl": cf(result.get("sl"), 5),
        "tp1": cf(result.get("tp1"), 5),
        "tp2": cf(result.get("tp2"), 5),
        "tp3": cf(result.get("tp3"), 5),
        "tp4": cf(result.get("tp4"), 5),
        "tp5": cf(result.get("tp5"), 5),
        "support": cf(result.get("support"), 5),
        "resistance": cf(result.get("resistance"), 5),
        "rsi": cf(result.get("rsi"), 2),
        "ma9": cf(result.get("ma9"), 5),
        "ma21": cf(result.get("ma21"), 5),
        "ma50": cf(result.get("ma50"), 5),
        "atr": cf(result.get("atr"), 5),
        "buy_score": cf(result.get("buy_score"), 2),
        "sell_score": cf(result.get("sell_score"), 2),
        "quality_score": cf(result.get("quality_score", result.get("confidence", 0)), 2),
        "quality_label": result.get("quality_label", "-"),
        "setup_type": result.get("setup_type", "-"),
        "risk_reward": cf(result.get("risk_reward"), 2),
        "warnings": result.get("warnings", []) if isinstance(result.get("warnings", []), list) else [],
        "reason": str(result.get("reason", ""))[:500],
        "lifecycle_status": result.get("lifecycle_status", result.get("status", "ok")),
        "lifecycle": result.get("lifecycle", {}),
        "updated_at": result.get("updated_at", now_iso()),
        "server_version": "test-ai-premium-v25-4-refresh-stable-colors",
    }


def signal_event_hash(compact: dict) -> str:
    raw = "|".join([
        str(compact.get("symbol", "")), str(compact.get("requested_timeframe", "")),
        str(compact.get("signal", "")), str(compact.get("entry", "")),
        str(compact.get("sl", "")), str(compact.get("tp1", "")),
        str(compact.get("tp2", "")), str(compact.get("tp3", "")),
        str(compact.get("tp4", "")), str(compact.get("tp5", "")),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def save_signal_to_db(key, result):
    compact = compact_signal(result)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    INSERT OR REPLACE INTO latest_signals
    (key, symbol, timeframe, category, signal, confidence, updated_at, data_json)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        key, compact.get("symbol", ""), compact.get("requested_timeframe", ""),
        compact.get("category", "other"), compact.get("signal", "WAIT"),
        float(compact.get("confidence", 0) or 0), compact.get("updated_at", now_iso()),
        json.dumps(compact, ensure_ascii=False),
    ))
    conn.commit()
    conn.close()



def get_active_signal(symbol: str, timeframe: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    SELECT *
    FROM signal_history
    WHERE symbol = ? AND timeframe = ? AND status = 'active'
    ORDER BY id DESC
    LIMIT 1
    """, (symbol, timeframe))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def update_signal_status(signal_id: int, status: str, last_price=None, status_reason: str = ""):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    UPDATE signal_history
    SET status = ?, closed_at = ?, last_price = ?, status_reason = ?
    WHERE id = ?
    """, (status, now_iso(), last_price, status_reason, signal_id))
    conn.commit()
    conn.close()


def evaluate_active_signal_status(active_signal: dict, current_price):
    """
    V16 signal lifecycle:
    - BUY: SL is hit when current price <= SL, TP2 when >= TP2, TP1 when >= TP1.
    - SELL: SL is hit when current price >= SL, TP2 when <= TP2, TP1 when <= TP1.
    TP2 has priority over TP1 so the final win is not downgraded.
    """
    if not active_signal:
        return None

    try:
        price = float(current_price)
    except Exception:
        return None

    sig = str(active_signal.get("signal") or "").upper()

    def f(v):
        try:
            return float(v) if v is not None else None
        except Exception:
            return None

    sl = f(active_signal.get("sl"))
    tp1 = f(active_signal.get("tp1"))
    tp2 = f(active_signal.get("tp2"))

    if sig == "BUY":
        if sl is not None and price <= sl:
            return ("sl_hit", f"BUY SL hit at {price}")
        if tp2 is not None and price >= tp2:
            return ("tp2_hit", f"BUY TP2 hit at {price}")
        if tp1 is not None and price >= tp1:
            return ("tp1_hit", f"BUY TP1 hit at {price}")

    if sig == "SELL":
        if sl is not None and price >= sl:
            return ("sl_hit", f"SELL SL hit at {price}")
        if tp2 is not None and price <= tp2:
            return ("tp2_hit", f"SELL TP2 hit at {price}")
        if tp1 is not None and price <= tp1:
            return ("tp1_hit", f"SELL TP1 hit at {price}")

    return None


def process_signal_lifecycle(compact: dict):
    """
    V16 backend-only lifecycle manager.
    It prevents duplicate active signals on the same symbol/timeframe and closes old signals
    when SL/TP is reached. It only opens a reversed signal when confidence is strong enough.
    """
    sig = str(compact.get("signal", "WAIT") or "WAIT").upper()
    symbol = compact.get("symbol", "")
    tf = compact.get("requested_timeframe") or compact.get("timeframe", "")
    price = compact.get("current_price") or compact.get("entry")

    if not symbol or not tf:
        return {"action": "ignored", "status": None}

    active = get_active_signal(symbol, tf)

    # First update any already-active signal based on latest market price.
    if active:
        hit = evaluate_active_signal_status(active, price)
        if hit:
            status, status_reason = hit
            update_signal_status(active["id"], status, price, status_reason)
            active = None

    if sig not in ["BUY", "SELL"]:
        return {"action": "updated_active_status_only", "status": None}

    # Re-check active after possible close.
    active = get_active_signal(symbol, tf)

    if not active:
        save_signal_to_history(compact)
        return {"action": "opened", "status": "active"}

    active_sig = str(active.get("signal") or "").upper()

    # Same signal is already active: do not spam duplicates.
    if active_sig == sig:
        return {"action": "kept_existing", "status": "active", "active_id": active.get("id")}

    # Opposite signal: only reverse if confidence is strong.
    try:
        confidence = float(compact.get("confidence") or 0)
    except Exception:
        confidence = 0

    if confidence >= 70:
        update_signal_status(
            active["id"],
            "cancelled",
            price,
            f"Cancelled by opposite {sig} signal with confidence {confidence}"
        )
        save_signal_to_history(compact)
        return {"action": "reversed", "status": "active"}

    return {"action": "opposite_ignored_low_confidence", "status": "active", "active_id": active.get("id")}


def save_signal_to_history(compact):
    sig = compact.get("signal", "WAIT")
    symbol = compact.get("symbol", "")
    tf = compact.get("requested_timeframe", "")

    if not symbol or not tf or sig not in ["BUY", "SELL"]:
        return

    event_hash = signal_event_hash(compact)
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
        INSERT INTO signal_history
        (event_hash, symbol, timeframe, category, signal, confidence, entry, sl, tp1, tp2, tp3, tp4, tp5, status, reason, created_at, data_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event_hash, compact.get("symbol", ""), compact.get("requested_timeframe", ""),
            compact.get("category", "other"), compact.get("signal", "WAIT"),
            float(compact.get("confidence", 0) or 0), compact.get("entry"), compact.get("sl"),
            compact.get("tp1"), compact.get("tp2"), compact.get("tp3"), compact.get("tp4"), compact.get("tp5"), "active",
            compact.get("reason", ""), compact.get("updated_at", now_iso()),
            json.dumps(compact, ensure_ascii=False),
        ))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()


def load_latest_from_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT key, data_json FROM latest_signals WHERE category != 'other'")
    rows = cur.fetchall()
    conn.close()

    data = {}
    for row in rows:
        try:
            data[row["key"]] = json.loads(row["data_json"])
        except Exception:
            pass
    return data


def cleanup_old_other():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM latest_signals WHERE category = 'other'")
    conn.commit()
    conn.close()


def get_history(limit=100):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    SELECT id, symbol, timeframe, category, signal, confidence,
           entry, sl, tp1, tp2, tp3, tp4, tp5, status, reason, created_at,
           closed_at, last_price, status_reason
    FROM signal_history
    ORDER BY id DESC
    LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


init_db()
cleanup_old_other()
latest_signals.update(load_latest_from_db())



@app.get("/access-status")
def access_status(request: Request):
    cfg = load_access_config()
    user = get_access_user(request)
    return {
        "status": "ok",
        "version": "test-ai-premium-v25-4-refresh-stable-colors",
        "access_enabled": bool(cfg.get("enabled", False)),
        "logged_in": user is not None,
        "user": {
            "name": user.get("name", "") if user else "",
            "plan": user.get("plan", "") if user else "",
            "enabled": user.get("enabled", False) if user else False,
            "expires_at": user.get("expires_at", "") if user else "",
            "expired": access_user_expired(user) if user else False,
            "features": sorted(list(user_features(user))) if user else [],
            "allowed_symbols": access_allowed_symbols(user) if user else [],
            "allowed_timeframes": access_allowed_timeframes(user) if user else [],
            "max_symbols": user.get("max_symbols", 0) if user else 0,
            "session_hours": session_hours(),
            "ip": _client_ip(request),
        },
        "config_path": ACCESS_CONFIG_PATH,
    }


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, key: str = "", next: str = ""):
    cfg = load_access_config()
    target = next or f"{PUBLIC_PREFIX}/mobile"
    if not cfg.get("enabled", False):
        response = RedirectResponse(url=target, status_code=302)
        return response

    if key:
        user = _find_access_user_by_key(key)
        if user:
            session = create_access_session(request, user, key)
            if not session.get("ok"):
                log_access_event(request, "login_blocked_ip", "denied", user=user, note=f"Active session on another IP: {session.get('ip','')}", target_key=key)
                return HTMLResponse("""
<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Access blocked</title>
<style>body{margin:0;min-height:100vh;background:#05070b;color:#e5eef8;font-family:Arial,Tahoma,sans-serif;display:flex;align-items:center;justify-content:center;padding:20px}.card{max-width:430px;background:#0f172a;border:1px solid #334155;border-radius:24px;padding:22px;text-align:center}.err{color:#fecaca;background:rgba(239,68,68,.15);border:1px solid rgba(239,68,68,.35);padding:12px;border-radius:14px}a{color:#38bdf8}</style></head>
<body><div class="card"><h2>تم منع الدخول</h2><div class="err">هذا الحساب مفتوح حالياً من IP آخر. سجّل خروج من الجهاز الآخر أو انتظر انتهاء الجلسة خلال 3 ساعات.</div><p><a href="/test-ai/login">رجوع لصفحة الدخول</a></p></div></body></html>
""", status_code=403)
            log_access_event(request, "login_success", "ok", user=user, note=f"next={target}")
            response = RedirectResponse(url=target, status_code=302)
            return set_access_cookie(response, key, session.get("session_id", ""))
        log_access_event(request, "login_failed", "denied", user=None, note="Invalid access key", target_key=key)

    error = "" if not key else "<div class='err'>مفتاح الدخول غير صحيح</div>"
    return HTMLResponse(f"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>QuantBado Login</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;background:linear-gradient(180deg,#05070b,#020617);color:#e5eef8;font-family:Arial,Tahoma,sans-serif;display:flex;align-items:center;justify-content:center;padding:18px}}.card{{width:100%;max-width:420px;background:rgba(15,23,42,.92);border:1px solid rgba(148,163,184,.18);border-radius:28px;padding:22px;box-shadow:0 24px 70px rgba(0,0,0,.45)}}.title{{font-size:26px;font-weight:900;color:#38bdf8;margin-bottom:6px}}.sub{{color:#94a3b8;font-size:13px;margin-bottom:18px;line-height:1.6}}input{{width:100%;background:#070d18;color:white;border:1px solid #263244;border-radius:16px;padding:14px;font-size:16px;outline:none;margin-bottom:12px}}button{{width:100%;border:0;border-radius:16px;padding:14px;font-size:16px;font-weight:900;background:linear-gradient(135deg,#38bdf8,#22c55e);color:#00111f;cursor:pointer}}.err{{background:rgba(239,68,68,.14);border:1px solid rgba(239,68,68,.28);color:#fecaca;padding:11px;border-radius:14px;margin-bottom:12px;font-size:13px}}.hint{{color:#64748b;font-size:12px;margin-top:12px;line-height:1.5}}
</style>
</head>
<body><div class="card"><div class="title">QuantBado Login</div><div class="sub">أدخل مفتاح الدخول للوصول إلى لوحة السوق.</div>{error}<form method="get" action="{PUBLIC_PREFIX}/login"><input type="hidden" name="next" value="{target}"><input name="key" placeholder="Access key" autocomplete="off" autofocus><button type="submit">دخول</button></form><div class="hint">يتم حفظ الدخول على هذا الجهاز لمدة 30 يوم.</div></div></body>
</html>
""")


@app.get("/logout")
def logout(request: Request):
    log_access_event(request, "logout", "ok", note="User logged out")
    deactivate_current_session(request)
    response = RedirectResponse(url=f"{PUBLIC_PREFIX}/login", status_code=302)
    response.delete_cookie(ACCESS_COOKIE_NAME, path="/")
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return response



@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    denied = require_feature_page(request, "admin")
    if denied:
        return denied
    log_access_event(request, "view_admin", "ok", note="Opened admin users page")
    return HTMLResponse(r"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<title>QuantBado Admin</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:linear-gradient(180deg,#05070b,#020617);color:#e5eef8;font-family:Arial,Tahoma,sans-serif;padding:14px}.app{max-width:1280px;margin:auto}.top{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:14px}.title{font-size:28px;font-weight:900;color:#38bdf8}.sub{font-size:12px;color:#94a3b8;margin-top:4px}.link{color:#7dd3fc;text-decoration:none;background:rgba(56,189,248,.12);border:1px solid rgba(56,189,248,.25);border-radius:14px;padding:9px 11px;font-weight:900;font-size:13px}.grid{display:grid;grid-template-columns:1fr;gap:14px}.card{background:rgba(15,23,42,.9);border:1px solid rgba(148,163,184,.16);border-radius:24px;padding:14px}.card h3{margin:0 0 12px;font-size:18px}label{font-size:12px;color:#94a3b8;margin:8px 0 5px;display:block}input,select,textarea{width:100%;background:#070d18;color:#e5eef8;border:1px solid #263244;border-radius:14px;padding:12px;font-size:14px;outline:none}textarea{min-height:80px;resize:vertical}button{border:0;border-radius:14px;padding:11px 13px;font-weight:900;cursor:pointer;background:linear-gradient(135deg,#38bdf8,#22c55e);color:#00111f}.btn2{background:#1e293b;color:#e5eef8;border:1px solid #334155}.danger{background:rgba(239,68,68,.18);color:#fecaca;border:1px solid rgba(239,68,68,.35)}.row{display:grid;grid-template-columns:1fr;gap:9px}.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.table-wrap{overflow-x:auto}.table{width:100%;border-collapse:separate;border-spacing:0 8px;min-width:950px}th{text-align:right;color:#94a3b8;font-size:12px;padding:8px}td{background:#070d18;border-top:1px solid #1e293b;border-bottom:1px solid #1e293b;padding:10px 8px;font-size:13px;vertical-align:top}.pill{display:inline-block;border-radius:999px;padding:5px 8px;font-size:12px;font-weight:900}.ok{color:#86efac;background:rgba(34,197,94,.12)}.off{color:#fecaca;background:rgba(239,68,68,.14)}.muted{color:#94a3b8}.msg{margin:10px 0;color:#86efac;font-size:13px}@media(min-width:900px){.grid{grid-template-columns:390px 1fr}.row.two{grid-template-columns:1fr 1fr}}
</style>
</head>
<body>
<div class="app">
  <div class="top">
    <div><div class="title">إدارة المستخدمين</div><div class="sub">V21 Admin Users Page</div></div>
    <div style="display:flex;gap:8px;flex-wrap:wrap"><a class="link" href="/test-ai/mobile">الموبايل</a><a class="link" href="/test-ai/dashboard">الداشبورد</a><a class="link" href="/test-ai/admin-users-audit">تدقيق المستخدمين</a><a class="link" href="/test-ai/admin-success">سجل النجاح</a><a class="link" href="/test-ai/admin-logs">السجلات</a><a class="link" href="/test-ai/logout">خروج</a></div>
  </div>
  <div class="grid">
    <div class="card">
      <h3 id="formTitle">إضافة / تعديل مستخدم</h3>
      <input type="hidden" id="original_key">
      <label>الاسم</label><input id="name" placeholder="Client name">
      <div class="row two">
        <div><label>Access Key</label><input id="key" placeholder="اتركه فارغ لتوليد مفتاح"></div>
        <div><label>الخطة</label><select id="plan"><option value="trial">trial</option><option value="basic">basic</option><option value="pro">pro</option><option value="owner">owner</option></select></div>
      </div>
      <div class="row two">
        <div><label>تاريخ الانتهاء</label><input id="expires_at" placeholder="YYYY-MM-DD أو فارغ"></div>
        <div><label>فعال؟</label><select id="enabled"><option value="true">نعم</option><option value="false">لا</option></select></div>
      </div>
      <label>الرموز المسموحة</label><textarea id="allowed_symbols" placeholder="* أو XAUUSD,EURUSD,GBPUSD"></textarea>
      <label>الفريمات المسموحة</label><input id="allowed_timeframes" placeholder="* أو M5,M15,H1">
      <div class="row two">
        <div><label>أقصى عدد رموز</label><input id="max_symbols" type="number" value="0"></div>
        <div><label>ميزات إضافية</label><input id="features" placeholder="mobile,dashboard,performance,history,admin أو *"></div>
      </div>
      <div class="actions">
        <button onclick="saveUser()">حفظ المستخدم</button>
        <button class="btn2" onclick="clearForm()">تفريغ</button>
        <button class="btn2" onclick="generateKey()">توليد مفتاح</button>
      </div>
      <div class="msg" id="msg"></div>
      <div class="muted">ملاحظة: owner فقط يستطيع فتح هذه الصفحة.</div>
    </div>
    <div class="card">
      <h3>المستخدمون</h3>
      <div class="table-wrap"><table class="table"><thead><tr><th>الاسم</th><th>الخطة</th><th>الحالة</th><th>ينتهي</th><th>الرموز</th><th>الفريمات</th><th>المفتاح</th><th>إجراءات</th></tr></thead><tbody id="users"></tbody></table></div>
    </div>
  </div>
</div>
<script>
let users=[];function $(id){return document.getElementById(id)}function csv(v){if(Array.isArray(v))return v.join(',');return v||''}function arr(v){return String(v||'').split(',').map(x=>x.trim()).filter(Boolean)}function msg(t){$('msg').innerText=t;setTimeout(()=>$('msg').innerText='',3500)}
async function load(){const r=await fetch('/test-ai/admin-data',{cache:'no-store'});const d=await r.json();users=d.users||[];render()}
function render(){const body=$('users');if(!users.length){body.innerHTML='<tr><td colspan="8">لا يوجد مستخدمون</td></tr>';return}body.innerHTML=users.map((u,i)=>`<tr><td><b>${u.name||'-'}</b></td><td>${u.plan||'-'}</td><td><span class="pill ${u.enabled&&!u.expired?'ok':'off'}">${u.enabled?(u.expired?'منتهي':'فعال'):'موقوف'}</span></td><td>${u.expires_at||'مفتوح'}</td><td>${csv(u.allowed_symbols)}</td><td>${csv(u.allowed_timeframes)}</td><td><code>${u.key||''}</code></td><td><div class="actions"><button class="btn2" onclick="editUser(${i})">تعديل</button><button class="btn2" onclick="toggleUser(${i})">${u.enabled?'إيقاف':'تفعيل'}</button><button class="danger" onclick="deleteUser(${i})">حذف</button></div></td></tr>`).join('')}
function clearForm(){['original_key','name','key','expires_at','allowed_symbols','allowed_timeframes','features'].forEach(id=>$(id).value='');$('plan').value='trial';$('enabled').value='true';$('max_symbols').value='0';$('formTitle').innerText='إضافة / تعديل مستخدم'}
function editUser(i){const u=users[i];$('formTitle').innerText='تعديل: '+(u.name||u.key);$('original_key').value=u.key||'';$('name').value=u.name||'';$('key').value=u.key||'';$('plan').value=u.plan||'trial';$('expires_at').value=u.expires_at||'';$('enabled').value=String(u.enabled!==false);$('allowed_symbols').value=csv(u.allowed_symbols||[]);$('allowed_timeframes').value=csv(u.allowed_timeframes||[]);$('max_symbols').value=u.max_symbols||0;$('features').value=csv(u.features||[]);scrollTo({top:0,behavior:'smooth'})}
async function generateKey(){const r=await fetch('/test-ai/admin-generate-key',{method:'POST'});const d=await r.json();$('key').value=d.key||''}
async function saveUser(){const payload={original_key:$('original_key').value,name:$('name').value,key:$('key').value,plan:$('plan').value,expires_at:$('expires_at').value,enabled:$('enabled').value==='true',allowed_symbols:arr($('allowed_symbols').value||'*'),allowed_timeframes:arr($('allowed_timeframes').value||'*'),max_symbols:Number($('max_symbols').value||0),features:arr($('features').value)};const r=await fetch('/test-ai/admin-save-user',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const d=await r.json();if(!r.ok){alert(d.message||'خطأ');return}msg('تم الحفظ');clearForm();load()}
async function toggleUser(i){const u=users[i];const r=await fetch('/test-ai/admin-toggle-user',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:u.key})});const d=await r.json();if(!r.ok){alert(d.message||'خطأ');return}load()}
async function deleteUser(i){const u=users[i];if(!confirm('حذف '+(u.name||u.key)+'؟'))return;const r=await fetch('/test-ai/admin-delete-user',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:u.key})});const d=await r.json();if(!r.ok){alert(d.message||'خطأ');return}load()}
load();
</script>
</body>
</html>
""")


@app.get("/admin-data")
def admin_data(request: Request):
    denied = require_feature_json(request, "admin")
    if denied:
        return denied
    cfg = load_access_config()
    users = []
    for user in cfg.get("users", []):
        u = normalize_access_user(user)
        u["expired"] = access_user_expired(u)
        users.append(u)
    return {
        "status": "ok",
        "version": "test-ai-premium-v25-4-refresh-stable-colors",
        "config_path": ACCESS_CONFIG_PATH,
        "access_enabled": bool(cfg.get("enabled", False)),
        "plans": cfg.get("plans", default_access_config().get("plans", {})),
        "users": users,
    }


@app.post("/admin-generate-key")
def admin_generate_key(request: Request):
    denied = require_feature_json(request, "admin")
    if denied:
        return denied
    key = generate_access_key()
    log_access_event(request, "admin_generate_key", "ok", note="Generated new access key")
    return {"status": "ok", "key": key}


@app.post("/admin-save-user")
async def admin_save_user(request: Request):
    denied = require_feature_json(request, "admin")
    if denied:
        return denied
    payload = await request.json()
    cfg = load_access_config()
    cfg.setdefault("plans", default_access_config().get("plans", {}))
    cfg.setdefault("users", [])

    original_key = str(payload.get("original_key") or "").strip()
    key = str(payload.get("key") or "").strip() or generate_access_key()
    user = {
        "name": str(payload.get("name") or "Client").strip(),
        "key": key,
        "plan": str(payload.get("plan") or "trial").strip().lower(),
        "enabled": bool(payload.get("enabled", True)),
        "expires_at": str(payload.get("expires_at") or "").strip(),
        "allowed_symbols": _list_value(payload.get("allowed_symbols"), ["*"]),
        "allowed_timeframes": _list_value(payload.get("allowed_timeframes"), ["*"]),
        "max_symbols": int(payload.get("max_symbols") or 0),
        "features": _list_value(payload.get("features"), []),
    }

    replaced = False
    new_users = []
    for existing in cfg.get("users", []):
        if str(existing.get("key", "")) == original_key or str(existing.get("key", "")) == key:
            if not replaced:
                new_users.append(user)
                replaced = True
            continue
        new_users.append(existing)

    if not replaced:
        new_users.append(user)

    cfg["users"] = new_users
    save_access_config(cfg)
    log_access_event(request, "admin_save_user", "ok", note=f"saved user={user.get('name','')} plan={user.get('plan','')}", target_key=key)
    return {"status": "ok", "message": "saved", "user": normalize_access_user(user)}


@app.post("/admin-delete-user")
async def admin_delete_user(request: Request):
    denied = require_feature_json(request, "admin")
    if denied:
        return denied
    payload = await request.json()
    key = str(payload.get("key") or "").strip()
    cfg = load_access_config()
    users = [u for u in cfg.get("users", []) if str(u.get("key", "")) != key]
    cfg["users"] = users
    save_access_config(cfg)
    log_access_event(request, "admin_delete_user", "ok", note="Deleted access user", target_key=key)
    return {"status": "ok", "message": "deleted", "key": key}


@app.post("/admin-toggle-user")
async def admin_toggle_user(request: Request):
    denied = require_feature_json(request, "admin")
    if denied:
        return denied
    payload = await request.json()
    key = str(payload.get("key") or "").strip()
    cfg = load_access_config()
    changed = False
    for user in cfg.get("users", []):
        if str(user.get("key", "")) == key:
            user["enabled"] = not bool(user.get("enabled", True))
            changed = True
            break
    save_access_config(cfg)
    log_access_event(request, "admin_toggle_user", "ok" if changed else "not_found", note=f"Toggle user changed={changed}", target_key=key)
    return {"status": "ok", "changed": changed, "key": key}



@app.get("/admin-logs-data")
def admin_logs_data(request: Request, limit: int = 250, event: str = "", user_hash: str = ""):
    denied = require_feature_json(request, "admin")
    if denied:
        return denied
    return {
        "status": "ok",
        "version": "test-ai-premium-v25-4-refresh-stable-colors",
        "summary": build_access_log_summary(),
        "items": get_access_logs(limit=limit, event=event, user_hash=user_hash),
        "time_utc": now_iso(),
    }


@app.get("/admin-logs", response_class=HTMLResponse)
def admin_logs_page(request: Request):
    denied = require_feature_page(request, "admin")
    if denied:
        return denied
    log_access_event(request, "view_admin_logs", "ok", note="Opened admin logs page")
    return HTMLResponse(r"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head><meta charset="UTF-8"><title>QuantBado Admin Logs</title><meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>*{box-sizing:border-box}body{margin:0;min-height:100vh;background:linear-gradient(180deg,#05070b,#020617);color:#e5eef8;font-family:Arial,Tahoma,sans-serif;padding:14px}.app{max-width:1280px;margin:auto}.top{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:14px}.title{font-size:28px;font-weight:900;color:#38bdf8}.sub{font-size:12px;color:#94a3b8;margin-top:4px}.link{color:#7dd3fc;text-decoration:none;background:rgba(56,189,248,.12);border:1px solid rgba(56,189,248,.25);border-radius:14px;padding:9px 11px;font-weight:900;font-size:13px}.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-bottom:14px}.card{background:rgba(15,23,42,.9);border:1px solid rgba(148,163,184,.16);border-radius:22px;padding:14px}.label{font-size:12px;color:#94a3b8}.value{font-size:22px;font-weight:900;margin-top:6px}.controls{display:grid;grid-template-columns:1fr 1fr auto;gap:8px;margin-bottom:12px}select,input{width:100%;background:#070d18;color:#e5eef8;border:1px solid #263244;border-radius:14px;padding:12px;outline:none}button{border:0;border-radius:14px;padding:11px 13px;font-weight:900;cursor:pointer;background:linear-gradient(135deg,#38bdf8,#22c55e);color:#00111f}.table-wrap{overflow-x:auto}.table{width:100%;border-collapse:separate;border-spacing:0 8px;min-width:1050px}th{text-align:right;color:#94a3b8;font-size:12px;padding:8px}td{background:#070d18;border-top:1px solid #1e293b;border-bottom:1px solid #1e293b;padding:10px 8px;font-size:12px;vertical-align:top}.pill{display:inline-block;border-radius:999px;padding:5px 8px;font-size:11px;font-weight:900}.ok{color:#86efac;background:rgba(34,197,94,.12)}.bad{color:#fecaca;background:rgba(239,68,68,.14)}.muted{color:#94a3b8}.hash{font-family:monospace;color:#cbd5e1}.ua{max-width:260px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.section{margin-top:14px}@media(min-width:850px){.grid{grid-template-columns:repeat(4,1fr)}}@media(max-width:640px){.controls{grid-template-columns:1fr}.title{font-size:22px}.grid{grid-template-columns:1fr 1fr}}</style>
</head><body><div class="app"><div class="top"><div><div class="title">سجلات الدخول والنشاط</div><div class="sub">V22 Admin Logs / User Activity</div></div><div style="display:flex;gap:8px;flex-wrap:wrap"><a class="link" href="/test-ai/admin">المستخدمون</a><a class="link" href="/test-ai/mobile">الموبايل</a><a class="link" href="/test-ai/dashboard">الداشبورد</a></div></div><div class="grid" id="summary"></div><div class="card section"><div class="controls"><select id="event"><option value="">كل الأحداث</option></select><input id="limit" type="number" value="250" min="1" max="1000"><button onclick="load()">تحديث</button></div><div class="table-wrap"><table class="table"><thead><tr><th>الوقت</th><th>الحدث</th><th>الحالة</th><th>المستخدم</th><th>الخطة</th><th>IP</th><th>المسار</th><th>ملاحظة</th><th>User Agent</th></tr></thead><tbody id="rows"></tbody></table></div></div></div>
<script>
function fmt(v){return(v===null||v===undefined||v==='')?'-':v}function shortHash(v){return v?String(v).slice(0,10)+'…':'-'}function localTime(iso){if(!iso)return'-';const d=new Date(iso);return isNaN(d.getTime())?iso:d.toLocaleString('tr-TR')}function pillStatus(s){s=String(s||'');return `<span class="pill ${s==='ok'?'ok':'bad'}">${s||'-'}</span>`}
async function load(){const ev=document.getElementById('event').value;const limit=document.getElementById('limit').value||250;const r=await fetch('/test-ai/admin-logs-data?limit='+encodeURIComponent(limit)+'&event='+encodeURIComponent(ev),{cache:'no-store'});const d=await r.json();const s=d.summary||{};const events=s.by_event||[];document.getElementById('summary').innerHTML=[['إجمالي السجلات',s.total||0],['عدد الأحداث',events.length],['آخر تحديث',localTime(d.time_utc)],['المعروض',(d.items||[]).length]].map(x=>`<div class="card"><div class="label">${x[0]}</div><div class="value">${x[1]}</div></div>`).join('');const sel=document.getElementById('event');const cur=sel.value;sel.innerHTML='<option value="">كل الأحداث</option>'+events.map(x=>`<option value="${x.event}">${x.event} (${x.count})</option>`).join('');sel.value=cur;const items=d.items||[];document.getElementById('rows').innerHTML=items.map(x=>`<tr><td>${localTime(x.created_at)}</td><td><b>${fmt(x.event)}</b></td><td>${pillStatus(x.status)}</td><td>${fmt(x.user_name)}<div class="muted hash">${shortHash(x.user_key_hash)}</div></td><td>${fmt(x.user_plan)}</td><td>${fmt(x.ip)}</td><td>${fmt(x.method)} ${fmt(x.path)}</td><td>${fmt(x.note)}</td><td class="ua" title="${fmt(x.user_agent)}">${fmt(x.user_agent)}</td></tr>`).join('')||'<tr><td colspan="9">لا توجد سجلات</td></tr>'}load();setInterval(load,15000);
</script></body></html>
""")


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "api": "online",
        "version": "test-ai-premium-v25-4-refresh-stable-colors",
        "time_utc": now_iso(),
        "db_path": DB_PATH,
        "cached_signals": len(latest_signals),
        "access_enabled": bool(load_access_config().get("enabled", False)),
    }


@app.post("/analyze")
async def analyze(request: Request):
    data = await request.json()
    result = analyze_market(data)

    symbol = data.get("symbol", "")
    timeframe = data.get("timeframe", "")
    category = data.get("category", "other")

    result["status"] = "ok"
    result["symbol"] = symbol
    result["symbol_ar"] = symbol_name(symbol, category, "ar")
    result["symbol_en"] = symbol_name(symbol, category, "en")
    result["category"] = category
    result["icon"] = category_icon(category)
    result["requested_timeframe"] = timeframe
    result["server_version"] = "test-ai-premium-v25-4-refresh-stable-colors"
    result["updated_at"] = now_iso()

    compact = compact_signal(result)
    key = f"{symbol}_{timeframe}"

    if category != "other":
        lifecycle = process_signal_lifecycle(compact)
        compact["lifecycle"] = lifecycle
        compact["lifecycle_status"] = lifecycle.get("status") or compact.get("signal", "WAIT")
        compact = apply_lifecycle_badge(compact)

        latest_signals[key] = compact
        save_signal_to_db(key, compact)

    return compact


@app.get("/latest")
def latest(request: Request):
    denied = require_feature_json(request, "dashboard")
    if denied:
        return denied
    user = get_access_user(request)
    symbols_map = {}
    clean_signals = {}

    for key, value in latest_signals.items():
        symbol = value.get("symbol", "")
        category = value.get("category", "other")
        if not symbol or category == "other":
            continue

        clean = apply_lifecycle_badge(compact_signal(value))
        clean_signals[key] = clean
        symbols_map[symbol] = {
            "symbol": symbol,
            "category": category,
            "icon": category_icon(category),
            "symbol_ar": value.get("symbol_ar") or symbol_name(symbol, category, "ar"),
            "symbol_en": value.get("symbol_en") or symbol_name(symbol, category, "en"),
            "favorite": is_favorite_symbol(symbol),
        }

    symbols_map = filter_symbols_for_user(user, symbols_map)
    clean_signals = filter_signals_for_user(user, clean_signals)
    allowed_timeframes = access_allowed_timeframes(user)

    # Limit payload for mobile browsers. The full market scan can produce hundreds of
    # symbol/timeframe entries; returning all of them makes Safari/Chrome mobile freeze.
    limited_signals = dict(list(clean_signals.items())[:180])

    return {
        "status": "ok",
        "version": "test-ai-premium-v25-4-refresh-stable-colors",
        "symbols": sorted_symbol_items(symbols_map),
        "timeframes": allowed_timeframes,
        "signals": limited_signals,
        "server_time": now_iso(),
        "cached_signals": len(limited_signals),
    }


@app.get("/history-data")
def history_data(request: Request):
    denied = require_feature_json(request, "history")
    if denied:
        return denied
    user = get_access_user(request)
    items = [
        row for row in get_history(100)
        if user_symbol_allowed(user, row.get("symbol", "")) and user_timeframe_allowed(user, row.get("timeframe", ""))
    ]
    return {
        "status": "ok",
        "version": "test-ai-premium-v25-4-refresh-stable-colors",
        "items": items,
        "time_utc": now_iso(),
    }


@app.get("/active-signals")
def active_signals(request: Request):
    denied = require_feature_json(request, "performance")
    if denied:
        return denied
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    SELECT id, symbol, timeframe, category, signal, confidence,
           entry, sl, tp1, tp2, tp3, tp4, tp5, status, reason, created_at,
           last_price, status_reason
    FROM signal_history
    WHERE status = 'active'
    ORDER BY id DESC
    LIMIT 200
    """)
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    user = get_access_user(request)
    rows = [
        row for row in rows
        if user_symbol_allowed(user, row.get("symbol", "")) and user_timeframe_allowed(user, row.get("timeframe", ""))
    ]
    return {
        "status": "ok",
        "version": "test-ai-premium-v25-4-refresh-stable-colors",
        "items": rows,
        "time_utc": now_iso(),
    }



def _rate(num, den):
    try:
        den = float(den or 0)
        if den <= 0:
            return 0.0
        return round((float(num or 0) / den) * 100, 2)
    except Exception:
        return 0.0


def _empty_bucket():
    return {
        "total": 0,
        "active": 0,
        "tp1_hit": 0,
        "tp2_hit": 0,
        "sl_hit": 0,
        "cancelled": 0,
        "expired": 0,
        "wins": 0,
        "losses": 0,
        "win_rate_tp1": 0.0,
        "win_rate_tp2": 0.0,
    }


def _update_bucket(bucket, item):
    status = str(item.get("status") or "").lower()
    bucket["total"] += 1
    if status in bucket:
        bucket[status] += 1

    if status in ["tp1_hit", "tp2_hit"]:
        bucket["wins"] += 1
    if status == "sl_hit":
        bucket["losses"] += 1

    resolved = bucket["tp1_hit"] + bucket["tp2_hit"] + bucket["sl_hit"]
    bucket["win_rate_tp1"] = _rate(bucket["tp1_hit"] + bucket["tp2_hit"], resolved)
    bucket["win_rate_tp2"] = _rate(bucket["tp2_hit"], resolved)


def build_performance(limit=5000, user=None):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    SELECT id, symbol, timeframe, category, signal, confidence,
           entry, sl, tp1, tp2, tp3, tp4, tp5, status, reason, created_at,
           closed_at, last_price, status_reason
    FROM signal_history
    ORDER BY id DESC
    LIMIT ?
    """, (int(limit),))
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    if user:
        rows = [
            row for row in rows
            if user_symbol_allowed(user, row.get("symbol", "")) and user_timeframe_allowed(user, row.get("timeframe", ""))
        ]

    summary = _empty_bucket()
    by_symbol = {}
    by_timeframe = {}
    by_signal = {}
    recent_closed = []
    recent_active = []

    for item in rows:
        status = str(item.get("status") or "").lower()
        symbol = item.get("symbol") or "UNKNOWN"
        timeframe = item.get("timeframe") or "UNKNOWN"
        signal = item.get("signal") or "UNKNOWN"

        _update_bucket(summary, item)

        if symbol not in by_symbol:
            by_symbol[symbol] = _empty_bucket()
            by_symbol[symbol]["symbol"] = symbol
        _update_bucket(by_symbol[symbol], item)

        if timeframe not in by_timeframe:
            by_timeframe[timeframe] = _empty_bucket()
            by_timeframe[timeframe]["timeframe"] = timeframe
        _update_bucket(by_timeframe[timeframe], item)

        if signal not in by_signal:
            by_signal[signal] = _empty_bucket()
            by_signal[signal]["signal"] = signal
        _update_bucket(by_signal[signal], item)

        if status == "active" and len(recent_active) < 30:
            recent_active.append(item)
        elif status != "active" and len(recent_closed) < 30:
            recent_closed.append(item)

    resolved = summary["tp1_hit"] + summary["tp2_hit"] + summary["sl_hit"]
    summary["resolved"] = resolved
    summary["win_rate_tp1"] = _rate(summary["tp1_hit"] + summary["tp2_hit"], resolved)
    summary["win_rate_tp2"] = _rate(summary["tp2_hit"], resolved)
    summary["loss_rate"] = _rate(summary["sl_hit"], resolved)

    best_symbols = sorted(
        by_symbol.values(),
        key=lambda x: (x.get("win_rate_tp1", 0), x.get("wins", 0), x.get("total", 0)),
        reverse=True
    )[:12]

    best_timeframes = sorted(
        by_timeframe.values(),
        key=lambda x: (x.get("win_rate_tp1", 0), x.get("wins", 0), x.get("total", 0)),
        reverse=True
    )[:12]

    signal_breakdown = sorted(
        by_signal.values(),
        key=lambda x: x.get("total", 0),
        reverse=True
    )

    return {
        "status": "ok",
        "version": "test-ai-premium-v25-4-refresh-stable-colors",
        "time_utc": now_iso(),
        "summary": summary,
        "best_symbols": best_symbols,
        "best_timeframes": best_timeframes,
        "signal_breakdown": signal_breakdown,
        "recent_active": recent_active,
        "recent_closed": recent_closed,
        "sample_size": len(rows),
    }


@app.get("/performance")
def performance(request: Request):
    denied = require_feature_json(request, "performance")
    if denied:
        return denied
    return build_performance(user=get_access_user(request))


@app.get("/performance-page", response_class=HTMLResponse)
def performance_page(request: Request):
    denied = require_feature_page(request, "performance")
    if denied:
        return denied
    log_access_event(request, "view_performance", "ok", note="Opened performance page")
    return HTMLResponse(r"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<title>TEST AI Performance</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:linear-gradient(180deg,#05070b,#020617);color:#e5eef8;font-family:Arial,Tahoma,sans-serif;padding:14px}.app{width:100%;max-width:1250px;margin:auto}.top{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:14px}.title{font-size:26px;font-weight:900}.sub{font-size:12px;color:#94a3b8;margin-top:4px}.link{text-decoration:none;color:#7dd3fc;background:rgba(56,189,248,.12);border:1px solid rgba(56,189,248,.25);border-radius:14px;padding:10px 12px;font-weight:900;font-size:13px}.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}.card{background:rgba(15,23,42,.88);border:1px solid rgba(148,163,184,.16);border-radius:22px;padding:14px}.label{font-size:12px;color:#94a3b8}.value{font-size:24px;font-weight:900;margin-top:6px}.green{color:#22c55e}.red{color:#ef4444}.yellow{color:#facc15}.blue{color:#38bdf8}.section{margin-top:14px}.section-title{font-size:18px;font-weight:900;margin-bottom:10px}.table-wrap{overflow-x:auto}.table{width:100%;border-collapse:separate;border-spacing:0 8px;min-width:760px}th{text-align:right;color:#94a3b8;font-size:12px;padding:8px}td{background:#070d18;border-top:1px solid #1e293b;border-bottom:1px solid #1e293b;padding:11px 8px;font-size:13px}.pill{font-weight:900;border-radius:10px;padding:5px 8px;display:inline-block}.active{color:#7dd3fc;background:rgba(56,189,248,.12)}.tp{color:#22c55e;background:rgba(34,197,94,.12)}.sl{color:#ef4444;background:rgba(239,68,68,.12)}.cancel{color:#facc15;background:rgba(250,204,21,.12)}@media(min-width:800px){.grid{grid-template-columns:repeat(5,1fr)}}@media(max-width:520px){body{padding:10px}.title{font-size:22px}.grid{grid-template-columns:1fr 1fr}.value{font-size:20px}}
</style>
</head>
<body>
<div class="app">
  <div class="top">
    <div><div class="title">أداء التوصيات</div><div class="sub">Performance Tracker · V17</div></div>
    <div style="display:flex;gap:8px"><a class="link" href="/test-ai/mobile">الموبايل</a><a class="link" href="/test-ai/dashboard">الداشبورد</a></div>
  </div>
  <div class="grid" id="summary"></div>
  <div class="section">
    <div class="section-title">أفضل الرموز</div>
    <div class="table-wrap"><table class="table"><thead><tr><th>الرمز</th><th>الإجمالي</th><th>TP1</th><th>TP2</th><th>SL</th><th>نسبة TP1+</th></tr></thead><tbody id="symbols"></tbody></table></div>
  </div>
  <div class="section">
    <div class="section-title">أفضل الفريمات</div>
    <div class="table-wrap"><table class="table"><thead><tr><th>الفريم</th><th>الإجمالي</th><th>TP1</th><th>TP2</th><th>SL</th><th>نسبة TP1+</th></tr></thead><tbody id="timeframes"></tbody></table></div>
  </div>
  <div class="section">
    <div class="section-title">آخر النتائج المغلقة</div>
    <div class="table-wrap"><table class="table"><thead><tr><th>الرمز</th><th>الفريم</th><th>الإشارة</th><th>الحالة</th><th>الدخول</th><th>آخر سعر</th><th>الوقت</th></tr></thead><tbody id="closed"></tbody></table></div>
  </div>
</div>
<script>
function fmt(v){return(v===null||v===undefined||v==="")?"-":v}
function cls(s){s=String(s||"").toLowerCase();if(s==="active")return"active";if(s.includes("tp"))return"tp";if(s.includes("sl"))return"sl";return"cancel"}
function statusLabel(s){const m={active:"فعالة",tp1_hit:"TP1 تحقق",tp2_hit:"TP2 تحقق",sl_hit:"ضربت ستوب",cancelled:"ملغاة",expired:"منتهية"};return m[s]||s||"-"}
function rowMetric(x,key){return `<tr><td><strong>${fmt(x[key])}</strong></td><td>${fmt(x.total)}</td><td>${fmt(x.tp1_hit)}</td><td>${fmt(x.tp2_hit)}</td><td>${fmt(x.sl_hit)}</td><td><strong>${fmt(x.win_rate_tp1)}%</strong></td></tr>`}
async function load(){
  const res=await fetch("/test-ai/performance",{cache:"no-store"});
  const data=await res.json();
  const s=data.summary||{};
  document.getElementById("summary").innerHTML=[
    ["إجمالي التوصيات",s.total,"blue"],["فعالة",s.active,"blue"],["TP1",s.tp1_hit,"green"],["TP2",s.tp2_hit,"green"],["SL",s.sl_hit,"red"],
    ["نسبة TP1+",(s.win_rate_tp1||0)+"%","green"],["نسبة TP2",(s.win_rate_tp2||0)+"%","green"],["نسبة الخسارة",(s.loss_rate||0)+"%","red"]
  ].map(x=>`<div class="card"><div class="label">${x[0]}</div><div class="value ${x[2]}">${fmt(x[1])}</div></div>`).join("");
  document.getElementById("symbols").innerHTML=(data.best_symbols||[]).map(x=>rowMetric(x,"symbol")).join("")||`<tr><td colspan="6">لا توجد بيانات</td></tr>`;
  document.getElementById("timeframes").innerHTML=(data.best_timeframes||[]).map(x=>rowMetric(x,"timeframe")).join("")||`<tr><td colspan="6">لا توجد بيانات</td></tr>`;
  document.getElementById("closed").innerHTML=(data.recent_closed||[]).map(x=>`<tr><td><strong>${fmt(x.symbol)}</strong></td><td>${fmt(x.timeframe)}</td><td>${fmt(x.signal)}</td><td><span class="pill ${cls(x.status)}">${statusLabel(x.status)}</span></td><td>${fmt(x.entry)}</td><td>${fmt(x.last_price)}</td><td>${fmt(x.closed_at||x.created_at)}</td></tr>`).join("")||`<tr><td colspan="7">لا توجد بيانات مغلقة بعد</td></tr>`;
}
load();setInterval(load,10000);
</script>
</body>
</html>
""")


@app.get("/history", response_class=HTMLResponse)
def history_page(request: Request):
    denied = require_feature_page(request, "history")
    if denied:
        return denied
    log_access_event(request, "view_history", "ok", note="Opened history page")
    return HTMLResponse(r"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8"><title>TEST AI Signal History</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:linear-gradient(180deg,#05070b,#020617);color:#e5eef8;font-family:Arial,Tahoma,sans-serif;padding:14px}.app{width:100%;max-width:1200px;margin:auto}.topbar{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:14px}.brand-title{font-size:24px;font-weight:900}.brand-sub{font-size:12px;color:#94a3b8;margin-top:2px}.link{text-decoration:none;color:#7dd3fc;background:rgba(56,189,248,.12);border:1px solid rgba(56,189,248,.25);border-radius:14px;padding:10px 12px;font-weight:900;font-size:13px}.card{background:rgba(15,23,42,.88);border:1px solid rgba(148,163,184,.16);border-radius:26px;padding:14px}.controls{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:12px}select,input{width:100%;background:#070d18;color:white;border:1px solid #263244;border-radius:14px;padding:12px;font-size:14px;outline:none}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:separate;border-spacing:0 8px;min-width:880px}th{text-align:right;color:#94a3b8;font-size:12px;font-weight:800;padding:8px}td{background:#070d18;border-top:1px solid #1e293b;border-bottom:1px solid #1e293b;padding:12px 8px;font-size:13px}.sig{font-weight:900;padding:6px 9px;border-radius:10px;display:inline-block}.buy{color:#22c55e;background:rgba(34,197,94,.13);border:1px solid rgba(34,197,94,.25)}.sell{color:#ef4444;background:rgba(239,68,68,.13);border:1px solid rgba(239,68,68,.25)}.status{color:#7dd3fc;font-weight:900}.empty{text-align:center;color:#94a3b8;padding:22px}@media(max-width:600px){body{padding:12px}.controls{grid-template-columns:1fr}}
</style></head>
<body><div class="app"><div class="topbar"><div><div class="brand-title">سجل الإشارات</div><div class="brand-sub">Signal History · آخر 100 توصية</div></div><a class="link" href="/test-ai/dashboard">الداشبورد</a></div><div class="card"><div class="controls"><input id="search" placeholder="بحث عن رمز..."><select id="signalFilter"><option value="all">كل الإشارات</option><option value="BUY">شراء</option><option value="SELL">بيع</option></select><select id="tfFilter"><option value="all">كل الفريمات</option><option value="M1">M1</option><option value="M5">M5</option><option value="M15">M15</option><option value="H1">H1</option><option value="H4">H4</option><option value="D1">D1</option></select></div><div class="table-wrap"><table><thead><tr><th>الوقت</th><th>الرمز</th><th>الفريم</th><th>الإشارة</th><th>الثقة</th><th>الدخول</th><th>SL</th><th>TP1</th><th>TP2</th><th>الحالة</th></tr></thead><tbody id="rows"><tr><td colspan="10" class="empty">تحميل...</td></tr></tbody></table></div></div></div>
<script>
let items=[];function fmt(v){return(v===null||v===undefined||v==="")?"-":v}function sigClass(s){return s==="BUY"?"buy":"sell"}function sigLabel(s){if(s==="BUY")return"شراء";if(s==="SELL")return"بيع";return s||"-"}function localTime(iso){if(!iso)return"-";const d=new Date(iso);if(isNaN(d.getTime()))return iso;return d.toLocaleString("tr-TR")}function render(){const q=document.getElementById("search").value.trim().toUpperCase();const sig=document.getElementById("signalFilter").value;const tf=document.getElementById("tfFilter").value;let filtered=items.filter(x=>{if(q&&!String(x.symbol||"").toUpperCase().includes(q))return false;if(sig!=="all"&&x.signal!==sig)return false;if(tf!=="all"&&x.timeframe!==tf)return false;return true});const body=document.getElementById("rows");if(filtered.length===0){body.innerHTML=`<tr><td colspan="10" class="empty">لا توجد بيانات</td></tr>`;return}body.innerHTML=filtered.map(x=>`<tr><td>${localTime(x.created_at)}</td><td><strong>${fmt(x.symbol)}</strong></td><td>${fmt(x.timeframe)}</td><td><span class="sig ${sigClass(x.signal)}">${sigLabel(x.signal)}</span></td><td>${fmt(x.confidence)}%</td><td>${fmt(x.entry)}</td><td>${fmt(x.sl)}</td><td>${fmt(x.tp1)}</td><td>${fmt(x.tp2)}</td><td><span class="status">${fmt(x.status)}</span></td></tr>`).join("")}async function load(){try{const res=await fetch("/test-ai/history-data");const data=await res.json();items=data.items||[];render()}catch(e){document.getElementById("rows").innerHTML=`<tr><td colspan="10" class="empty">خطأ في تحميل البيانات</td></tr>`}}document.getElementById("search").addEventListener("input",render);document.getElementById("signalFilter").addEventListener("change",render);document.getElementById("tfFilter").addEventListener("change",render);load();setInterval(load,10000);
</script></body></html>
""")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    denied = require_feature_page(request, "dashboard")
    if denied:
        return denied
    log_access_event(request, "view_dashboard", "ok", note="Opened dashboard pro responsive UI")
    return HTMLResponse(r"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<title>QuantBado Dashboard</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<style>
:root{--bg:#05070b;--panel:#0b1220;--panel2:#101827;--line:#23314a;--muted:#8fa1bd;--text:#eaf2ff;--blue:#38bdf8;--green:#22c55e;--red:#ef4444;--yellow:#facc15;--shadow:0 18px 50px rgba(0,0,0,.32)}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;min-height:100vh;background:radial-gradient(circle at 80% 0%,rgba(56,189,248,.17),transparent 30%),radial-gradient(circle at 15% 110%,rgba(34,197,94,.12),transparent 32%),linear-gradient(180deg,#05070b,#020617);color:var(--text);font-family:Arial,Tahoma,sans-serif;padding:18px}.app{max-width:1480px;margin:auto}.top{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:14px}.brand-title{font-size:30px;font-weight:900;color:var(--blue);letter-spacing:.2px}.brand-sub{font-size:12px;color:var(--muted);margin-top:4px}.links{display:flex;gap:8px;flex-wrap:wrap}.link,.mini-btn{color:#7dd3fc;text-decoration:none;background:rgba(56,189,248,.12);border:1px solid rgba(56,189,248,.25);border-radius:14px;padding:9px 12px;font-weight:900;font-size:13px}.live{display:inline-flex;align-items:center;gap:7px;color:#86efac;background:rgba(34,197,94,.12);border:1px solid rgba(34,197,94,.25);padding:8px 12px;border-radius:999px;font-size:12px;font-weight:900}.dot{width:8px;height:8px;background:var(--green);border-radius:50%;box-shadow:0 0 0 5px rgba(34,197,94,.1)}.toolbar{position:sticky;top:10px;z-index:30;background:rgba(8,13,24,.92);border:1px solid rgba(148,163,184,.16);box-shadow:var(--shadow);backdrop-filter:blur(16px);border-radius:24px;padding:12px;margin-bottom:14px}.quick{display:grid;grid-template-columns:110px 150px 140px 150px 1fr auto auto;gap:9px;align-items:center}select,input,button{width:100%;background:#070d18;color:var(--text);border:1px solid #263244;border-radius:14px;padding:12px;font-size:14px;outline:none}button{cursor:pointer;font-weight:900;background:linear-gradient(135deg,#38bdf8,#22c55e);color:#00111f;border:0}.ghost{background:#111827;color:var(--text);border:1px solid #334155}.search{position:relative}.search input{padding-inline-start:42px}.search:before{content:'⌕';position:absolute;left:14px;top:9px;color:#7dd3fc;font-size:22px}.filter-panel{display:none;margin-top:10px;border-top:1px solid rgba(148,163,184,.12);padding-top:10px}.filter-panel.open{display:grid;grid-template-columns:1fr 1.4fr;gap:10px}.filter-box{background:#07101e;border:1px solid #1d2a40;border-radius:18px;padding:10px}.filter-title{font-size:12px;color:#94a3b8;margin-bottom:8px;font-weight:900}.chips{display:flex;flex-wrap:wrap;gap:7px;max-height:160px;overflow:auto;padding:1px}.chip{display:inline-flex;align-items:center;gap:6px;border:1px solid #263244;background:#0b1424;color:#dbeafe;border-radius:999px;padding:8px 10px;font-size:12px;font-weight:900;cursor:pointer;user-select:none}.chip input{display:none}.chip:has(input:checked){border-color:#38bdf8;background:rgba(56,189,248,.16);color:#7dd3fc}.stats{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-bottom:14px}.stat{background:rgba(15,23,42,.88);border:1px solid rgba(148,163,184,.16);border-radius:20px;padding:14px}.stat-label{font-size:12px;color:var(--muted)}.stat-value{font-size:24px;font-weight:900;margin-top:6px}.green{color:var(--green)}.red{color:var(--red)}.yellow{color:var(--yellow)}.blue{color:var(--blue)}.layout{display:grid;grid-template-columns:minmax(0,1fr) 410px;gap:14px}.panel{background:rgba(15,23,42,.88);border:1px solid rgba(148,163,184,.16);border-radius:26px;padding:14px;box-shadow:0 10px 36px rgba(0,0,0,.18)}.panel-title{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:10px}.panel-title strong{font-size:18px}.panel-title span{font-size:12px;color:var(--muted)}.opp-list{display:flex;gap:10px;overflow-x:auto;padding-bottom:5px}.opp{min-width:218px;background:#070d18;border:1px solid #1e293b;border-radius:18px;padding:12px;cursor:pointer;transition:.16s}.opp:hover{border-color:#38bdf8;transform:translateY(-1px)}.opp-symbol{font-weight:900;font-size:18px}.opp-name{color:var(--muted);font-size:11px;margin-top:4px;min-height:28px}.opp-row{display:flex;justify-content:space-between;align-items:center;margin-top:9px}.cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.card{background:linear-gradient(180deg,rgba(17,24,39,.95),rgba(2,6,23,.98));border:1px solid rgba(148,163,184,.18);border-radius:24px;padding:14px;box-shadow:0 18px 42px rgba(0,0,0,.24);animation:softIn .18s ease-out}@keyframes softIn{from{opacity:.92;transform:translateY(2px)}to{opacity:1;transform:none}}.card-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.sym{font-size:24px;font-weight:900}.name{font-size:12px;color:#cbd5e1;margin-top:4px}.meta{font-size:11px;color:var(--muted);margin-top:5px}.pill,.sig{display:inline-flex;align-items:center;justify-content:center;border-radius:999px;padding:7px 10px;font-size:12px;font-weight:900;border:1px solid rgba(148,163,184,.18)}.sig{min-width:78px;font-size:15px;border-radius:15px}.buy{color:#22c55e;background:rgba(34,197,94,.12);border-color:rgba(34,197,94,.28)}.sell{color:#ef4444;background:rgba(239,68,68,.12);border-color:rgba(239,68,68,.28)}.wait{color:#facc15;background:rgba(250,204,21,.10);border-color:rgba(250,204,21,.25)}.quality-a{color:#22c55e}.quality-b{color:#7dd3fc}.quality-c{color:#facc15}.quality-d{color:#f87171}.bar{height:8px;background:#1e293b;border-radius:999px;overflow:hidden;margin-top:12px}.fill{height:100%;background:linear-gradient(90deg,#22c55e,#38bdf8);border-radius:999px}.learn{margin-top:10px;background:rgba(56,189,248,.07);border:1px solid rgba(56,189,248,.12);border-radius:16px;padding:11px;color:#dbeafe;font-size:13px;line-height:1.55}.learn b{color:#7dd3fc}.qrow{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:12px}.qbox{background:#070d18;border:1px solid #1e293b;border-radius:16px;padding:10px}.label{font-size:11px;color:var(--muted)}.val{font-size:17px;font-weight:900;margin-top:5px;word-break:break-word}.tp-main{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-top:10px}.tp-more{margin-top:8px}.tp-more summary{cursor:pointer;color:#7dd3fc;font-size:12px;font-weight:900;padding:8px 10px;background:#07101e;border:1px solid #1e293b;border-radius:12px}.tp-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-top:8px}.tp{background:#07101e;border:1px solid #1e293b;border-radius:12px;padding:8px;text-align:center}.tp span{display:block;color:var(--muted);font-size:10px}.tp strong{display:block;font-size:13px;margin-top:4px}.trend-strip{margin-top:10px;background:rgba(56,189,248,.06);border:1px solid rgba(56,189,248,.13);border-radius:14px;padding:10px}.trend-title{font-size:12px;color:#7dd3fc;font-weight:900;margin-bottom:8px}.trend-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:7px}.tbox{background:#070d18;border:1px solid #1e293b;border-radius:12px;padding:8px;text-align:center}.tbox span{display:block;color:var(--muted);font-size:10px}.tbox strong{display:block;font-size:12px;margin-top:4px}.tbox.tr-up{border-color:rgba(34,197,94,.40);background:rgba(34,197,94,.10)}.tbox.tr-up strong{color:#22c55e}.tbox.tr-down{border-color:rgba(239,68,68,.40);background:rgba(239,68,68,.10)}.tbox.tr-down strong{color:#ef4444}.tbox.tr-side{border-color:rgba(250,204,21,.36);background:rgba(250,204,21,.09)}.tbox.tr-side strong{color:#facc15}.tbox.tr-none{border-color:rgba(148,163,184,.20);background:rgba(148,163,184,.06)}.tbox.tr-none strong{color:#94a3b8}.warns{margin-top:10px;background:rgba(250,204,21,.08);border:1px solid rgba(250,204,21,.18);border-radius:14px;padding:10px;color:#fde68a;font-size:12px;line-height:1.5}.table-wrap{overflow-x:auto}.table{width:100%;border-collapse:separate;border-spacing:0 8px;min-width:620px}th{text-align:right;color:var(--muted);font-size:12px;padding:8px}td{background:#070d18;border-top:1px solid #1e293b;border-bottom:1px solid #1e293b;padding:10px 8px;font-size:13px}.right{position:sticky;top:100px;align-self:start}.empty{text-align:center;color:var(--muted);padding:22px}.footer{margin-top:12px;text-align:center;color:#64748b;font-size:11px}@media(max-width:1100px){.layout{grid-template-columns:1fr}.right{position:static}.quick{grid-template-columns:repeat(4,1fr)}.filter-panel.open{grid-template-columns:1fr}.cards{grid-template-columns:1fr}.stats{grid-template-columns:repeat(3,1fr)}}@media(max-width:620px){body{padding:10px}.top{flex-direction:column}.brand-title{font-size:24px}.toolbar{top:6px;border-radius:20px}.quick{grid-template-columns:1fr 1fr}.search{grid-column:1/-1}.quick button{padding:11px 8px}.stats{grid-template-columns:repeat(2,1fr)}.qrow{grid-template-columns:1fr 1fr}.trend-grid{grid-template-columns:repeat(2,1fr)}.cards{gap:10px}.card{border-radius:20px;padding:12px}.sym{font-size:21px}}
</style>
</head>
<body>
<div class="app">
  <div class="top"><div><div class="brand-title">QuantBado AI</div><div class="brand-sub">لوحة احترافية مبسطة · V25.3</div></div><div class="links"><span class="live"><span class="dot"></span>LIVE</span><a class="link" href="/test-ai/mobile?v=253">الموبايل</a><a class="link" href="/test-ai/performance-page">الأداء</a><a class="link" href="/test-ai/admin">Admin</a></div></div>
  <div class="toolbar">
    <div class="quick"><select id="tf"><option>M1</option><option>M5</option><option>M15</option><option>H1</option><option>H4</option><option>D1</option></select><select id="cat"><option value="all">كل التصنيفات</option><option value="favorite">المفضلة</option><option value="forex">فوركس</option><option value="commodity">سلع</option><option value="index">مؤشرات</option><option value="crypto">كريبتو</option></select><select id="sig"><option value="all">كل الإشارات</option><option value="BUY">شراء</option><option value="SELL">بيع</option><option value="WAIT">انتظار</option></select><select id="sort"><option value="quality_desc">الأفضل</option><option value="confidence_desc">الثقة</option><option value="updated_desc">الأحدث</option><option value="symbol_asc">الرمز</option></select><div class="search"><input id="q" placeholder="بحث..."/></div><button class="ghost" onclick="toggleFilters()">الفلاتر</button><button onclick="load(true)">تحديث</button><button class="ghost" onclick="resetDashboardFilters()">تصفير</button></div>
    <div id="filterPanel" class="filter-panel"><div class="filter-box"><div class="filter-title">اختر جودة واحدة أو أكثر</div><div class="chips" id="qualityChips"></div></div><div class="filter-box"><div class="filter-title">اختر زوج أو أكثر</div><div class="chips" id="symbolChips"><span class="label">تظهر الرموز بعد أول تحميل</span></div></div></div>
  </div>
  <div class="stats" id="stats"></div>
  <div class="layout"><div><div class="panel"><div class="panel-title"><strong>أفضل الفرص</strong><span id="sync">تحميل...</span></div><div class="opp-list" id="opps"></div></div><div class="panel"><div class="panel-title"><strong>النتائج</strong><span id="count"></span></div><div class="cards" id="cards"><div class="empty">تحميل البيانات...</div></div></div></div><div class="right"><div class="panel"><div class="panel-title"><strong>شرح سريع للمبتدئ</strong><span id="summaryTime"></span></div><div class="learn"><b>الجودة</b> تقيس قوة الفرصة، و<b>R/R</b> يقارن الربح المتوقع بالمخاطرة. الاتجاه العام يوضح وضع كل فريم قبل الدخول.</div><div class="table-wrap"><table class="table"><thead><tr><th>الرمز</th><th>إشارة</th><th>جودة</th><th>R/R</th></tr></thead><tbody id="qualityRows"></tbody></table></div></div></div></div><div class="footer">QuantBado · v25.3</div>
</div>
<script>
const $=id=>document.getElementById(id);let symbolList=[];let selectedSymbols=new Set();let selectedQualities=new Set();const qualityOptions=[['A+','قوي جداً'],['A','ممتاز'],['B','جيد'],['C','متوسط'],['D','ضعيف']];
function fmt(v){return(v===null||v===undefined||v==='')?'-':v}function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function sigClass(s){s=String(s||'WAIT').toUpperCase();return s==='BUY'?'buy':s==='SELL'?'sell':'wait'}function sigLabel(s){s=String(s||'WAIT').toUpperCase();return s==='BUY'?'شراء':s==='SELL'?'بيع':'انتظار'}
function qWord(label,q){if(label==='A+'||q>=80)return'قوي جداً';if(label==='A'||q>=70)return'ممتاز';if(label==='B'||q>=60)return'جيد';if(label==='C'||q>=50)return'متوسط';return'ضعيف'}function qClass(label,q){if(label==='A+'||label==='A'||q>=70)return'quality-a';if(label==='B'||q>=60)return'quality-b';if(label==='C'||q>=50)return'quality-c';return'quality-d'}
function setupText(v){const m={trend_breakout:'اختراق مع الاتجاه',trend_breakdown:'كسر مع الاتجاه',rejection:'ارتداد من منطقة مهمة',ma_reclaim:'استرجاع متوسط MA21',range_wait:'انتظار داخل نطاق',momentum_setup:'زخم سعري'};return m[v]||v||'-'}function warnText(v){const m={'No actionable setup':'لا توجد فرصة واضحة','Risk levels incomplete':'مستويات المخاطرة غير مكتملة','ATR unavailable':'ATR غير متوفر','Mixed directional scores':'الاتجاه غير محسوم','Momentum may be stretched':'الزخم قد يكون مبالغاً فيه'};return m[v]||v}
function qBadge(s){let q=Number(s.quality_score??s.confidence??0);let label=s.quality_label||'-';return `<span class="${qClass(label,q)}"><b>${q.toFixed(1)}%</b> · ${qWord(label,q)}</span>`}function localTime(iso){if(!iso)return'-';const d=new Date(iso);return isNaN(d.getTime())?iso:d.toLocaleTimeString('tr-TR')}function trendText(s){return `${fmt(s.trend_direction_ar||'عرضي')} ${fmt(s.trend_strength_ar||'ضعيف')}`}
function trendClass(x){const d=String((x&&x.direction)||'');if(d.includes('صاعد'))return 'tr-up';if(d.includes('هابط'))return 'tr-down';if(d.includes('عرض'))return 'tr-side';return 'tr-none'}
function trendStrip(s){const arr=s.timeframe_trends||[];if(!arr.length)return'';return `<div class="trend-strip"><div class="trend-title">الاتجاه العام الحالي لكل الفريمات</div><div class="trend-grid">${arr.map(x=>`<div class="tbox ${trendClass(x)}"><span>${esc(x.timeframe)}</span><strong>${esc(x.direction)} ${esc(x.strength)}</strong></div>`).join('')}</div></div>`}
function targets(s){return `<div class="tp-main"><div class="tp"><span>TP1</span><strong>${fmt(s.tp1)}</strong></div><div class="tp"><span>TP2</span><strong>${fmt(s.tp2)}</strong></div></div><details class="tp-more"><summary>عرض باقي الأهداف</summary><div class="tp-grid"><div class="tp"><span>TP3</span><strong>${fmt(s.tp3)}</strong></div><div class="tp"><span>TP4</span><strong>${fmt(s.tp4)}</strong></div><div class="tp"><span>TP5</span><strong>${fmt(s.tp5)}</strong></div></div></details>`}
function card(s){const sig=s.signal||'WAIT';const warns=Array.isArray(s.warnings)?s.warnings:[];return `<div class="card"><div class="card-head"><div><div class="sym">${fmt(s.symbol)} ${fmt(s.icon)}</div><div class="name">${fmt(s.symbol_ar)}</div><div class="name">${fmt(s.symbol_en)}</div><div class="meta">${fmt(s.timeframe||s.requested_timeframe)} · ${fmt(s.lifecycle_label_ar||'')} · ${localTime(s.updated_at)}</div></div><div class="sig ${sigClass(sig)}">${sigLabel(sig)}</div></div>${trendStrip(s)}<div class="bar"><div class="fill" style="width:${Math.max(0,Math.min(100,Number(s.quality_score||0)))}%"></div></div><div class="qrow"><div class="qbox"><div class="label">جودة الفرصة</div><div class="val">${qBadge(s)}</div></div><div class="qbox"><div class="label">R/R</div><div class="val">${fmt(s.risk_reward)}</div></div><div class="qbox"><div class="label">اتجاه الفريم</div><div class="val">${trendText(s)}</div></div><div class="qbox"><div class="label">الدخول</div><div class="val">${fmt(s.entry)}</div></div><div class="qbox"><div class="label">SL</div><div class="val">${fmt(s.sl)}</div></div><div class="qbox"><div class="label">الثقة</div><div class="val">${fmt(s.confidence)}%</div></div></div>${targets(s)}<div class="learn"><b>${setupText(s.setup_type)}</b><br>${fmt(s.reason)}</div>${warns.length?`<div class="warns">${warns.map(w=>'⚠ '+warnText(w)).join('<br>')}</div>`:''}</div>`}
function opp(s){return `<div class="opp" onclick="pick('${esc(s.symbol)}')"><div class="opp-symbol">${fmt(s.symbol)}</div><div class="opp-name">${fmt(s.symbol_ar)}<br>${fmt(s.symbol_en)}</div><div class="opp-row"><span class="pill ${sigClass(s.signal)}">${sigLabel(s.signal)}</span><span>${qBadge(s)}</span></div></div>`}
function toggleFilters(){ $('filterPanel').classList.toggle('open') }
function renderQualityChips(){ $('qualityChips').innerHTML=qualityOptions.map(([v,t])=>`<label class="chip"><input type="checkbox" value="${v}" ${selectedQualities.has(v)?'checked':''} onchange="toggleQuality(this)">${t}</label>`).join('') }
function toggleQuality(el){el.checked?selectedQualities.add(el.value):selectedQualities.delete(el.value);load(true)}
function renderSymbolChips(list){symbolList=list||symbolList;let html=symbolList.map(x=>`<label class="chip"><input type="checkbox" value="${esc(x.symbol)}" ${selectedSymbols.has(x.symbol)?'checked':''} onchange="toggleSymbol(this)">${esc(x.symbol)} · ${esc(x.symbol_ar||x.symbol_en||'')}</label>`).join('');$('symbolChips').innerHTML=html||'<span class="label">لا توجد رموز</span>'}
function toggleSymbol(el){el.checked?selectedSymbols.add(el.value):selectedSymbols.delete(el.value);load(true)}function pick(symbol){selectedSymbols=new Set([symbol]);renderSymbolChips();load(true)}
async function load(silent=false){
  try{
    if(!silent){$('sync').innerText='جاري التحديث...'}
    const params=new URLSearchParams({tf:$('tf').value,category:$('cat').value,q:$('q').value.trim(),signal:$('sig').value,sort:$('sort').value,limit:'100',offset:'0'});
    if(selectedQualities.size)params.set('qualities',[...selectedQualities].join(','));
    if(selectedSymbols.size)params.set('symbols',[...selectedSymbols].join(','));
    const res=await fetch('/test-ai/mobile-data?'+params.toString(),{cache:'no-store'});
    const data=await res.json();
    if(!res.ok||data.status==='unauthorized'){location.href='/test-ai/login?next=/test-ai/dashboard';return}
    renderSymbolChips(data.symbols||[]);
    const items=data.items||[];
    const buy=items.filter(x=>x.signal==='BUY').length;
    const sell=items.filter(x=>x.signal==='SELL').length;
    const wait=items.filter(x=>x.signal==='WAIT').length;
    const avg=items.length?items.reduce((a,x)=>a+Number(x.quality_score||0),0)/items.length:0;
    const best=items.filter(x=>Number(x.quality_score||0)>=70).length;
    $('stats').innerHTML=[['النتائج',data.total_filtered??items.length,'blue'],['شراء',buy,'green'],['بيع',sell,'red'],['انتظار',wait,'yellow'],['فرص ممتازة',best,'green'],['متوسط الجودة',avg.toFixed(1)+'%','blue']].map(x=>`<div class="stat"><div class="stat-label">${x[0]}</div><div class="stat-value ${x[2]}">${x[1]}</div></div>`).join('');
    const newCards=items.length?items.map(card).join(''):'<div class="empty">لا توجد نتائج حسب الفلاتر الحالية</div>';
    $('cards').innerHTML=newCards;
    $('opps').innerHTML=items.filter(x=>['BUY','SELL'].includes(x.signal)).slice(0,18).map(opp).join('')||'<div class="empty">لا توجد فرص قوية حالياً</div>';
    $('qualityRows').innerHTML=items.slice(0,28).map(s=>`<tr><td><b>${fmt(s.symbol)}</b></td><td><span class="pill ${sigClass(s.signal)}">${sigLabel(s.signal)}</span></td><td>${qBadge(s)}</td><td>${fmt(s.risk_reward)}</td></tr>`).join('')||'<tr><td colspan="4">لا توجد بيانات</td></tr>';
    $('count').innerText=`${items.length} / ${data.total_filtered??items.length}`;
    $('sync').innerText='آخر تحديث '+localTime(data.server_time);
    $('summaryTime').innerText=localTime(data.server_time)
  }catch(e){
    if(!silent){$('cards').innerHTML='<div class="empty">تعذر تحميل البيانات</div>';}
    $('sync').innerText='تعذر التحديث، بقيت البيانات السابقة ظاهرة';
    console.error(e)
  }
}
function resetDashboardFilters(){['tf','cat','sig','sort','q'].forEach(id=>{const el=$(id);if(id==='tf')el.value='M1';else if(id==='cat'||id==='sig')el.value='all';else if(id==='sort')el.value='quality_desc';else el.value=''});selectedSymbols.clear();selectedQualities.clear();renderQualityChips();renderSymbolChips();load(true)}
['tf','cat','sig','sort'].forEach(id=>$(id).addEventListener('change',()=>load(true)));let timer=null;$('q').addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(()=>load(true),350)});renderQualityChips();load(false);setInterval(()=>load(true),12000);
</script>
</body>
</html>
""")


def trend_direction_label(s: dict) -> str:
    sig = str((s or {}).get("signal") or "WAIT").upper()
    if sig == "BUY":
        return "صاعد"
    if sig == "SELL":
        return "هابط"
    return "عرضي"


def trend_strength_label(s: dict) -> str:
    try:
        q = float((s or {}).get("quality_score") or (s or {}).get("confidence") or 0)
    except Exception:
        q = 0
    if q >= 75:
        return "قوي"
    if q >= 55:
        return "متوسط"
    if q > 0:
        return "ضعيف"
    return "لا بيانات"


def trend_pack(symbol: str, user: dict) -> list:
    out = []
    for tf in access_allowed_timeframes(user):
        key = f"{symbol}_{tf}"
        item = latest_signals.get(key)
        if not item:
            out.append({"timeframe": tf, "direction": "لا بيانات", "strength": "لا بيانات", "signal": "WAIT", "quality_score": 0})
            continue
        c = apply_lifecycle_badge(compact_signal(item))
        out.append({
            "timeframe": tf,
            "direction": trend_direction_label(c),
            "strength": trend_strength_label(c),
            "signal": c.get("signal", "WAIT"),
            "quality_score": c.get("quality_score", 0),
            "quality_label": c.get("quality_label", "-"),
            "updated_at": c.get("updated_at", ""),
        })
    return out


@app.get("/symbol-trends")
def symbol_trends(request: Request, symbol: str = ""):
    denied = require_feature_json(request, "mobile")
    if denied:
        return denied
    user = get_access_user(request)
    s = clean_symbol(symbol)
    if not s or not user_symbol_allowed(user, s):
        return {"status": "ok", "items": []}
    return {"status": "ok", "version": "test-ai-premium-v25-4-refresh-stable-colors", "symbol": s, "items": trend_pack(s, user), "server_time": now_iso()}

@app.get("/mobile-data")
def mobile_data(
    request: Request,
    tf: str = "M1",
    category: str = "all",
    q: str = "",
    signal: str = "all",
    sort: str = "quality_desc",
    min_quality: float = 0,
    limit: int = 40,
    offset: int = 0,
    symbol: str = "",
    symbols: str = "",
    qualities: str = ""
):
    denied = require_feature_json(request, "mobile")
    if denied:
        return denied

    user = get_access_user(request)
    tf = (tf or "M1").upper()
    category = category or "all"
    q_clean = (q or "").strip().upper()
    selected_signal = (signal or "all").upper()
    selected_symbol = clean_symbol((symbol or "").strip().upper())
    raw_symbols = symbols or symbol or ""
    selected_symbols = {clean_symbol(x) for x in str(raw_symbols).replace(";", ",").split(",") if clean_symbol(x)}

    def _normalize_quality(v):
        raw = str(v or "").strip().upper().replace(" ", "")
        word_map = {
            "قويجداً": "A+", "قويجدا": "A+", "VERYSTRONG": "A+", "A+": "A+",
            "ممتاز": "A", "EXCELLENT": "A", "A": "A",
            "جيد": "B", "GOOD": "B", "B": "B",
            "متوسط": "C", "MEDIUM": "C", "C": "C",
            "ضعيف": "D", "WEAK": "D", "D": "D",
        }
        return word_map.get(raw, raw if raw in ["A+", "A", "B", "C", "D"] else "")

    selected_qualities = {_normalize_quality(x) for x in str(qualities or "").replace(";", ",").split(",")}
    selected_qualities.discard("")

    try:
        limit = max(1, min(int(limit or 40), 100))
    except Exception:
        limit = 40
    try:
        offset = max(0, int(offset or 0))
    except Exception:
        offset = 0
    try:
        min_quality = max(0.0, float(min_quality or 0))
    except Exception:
        min_quality = 0.0

    allowed_timeframes = access_allowed_timeframes(user)
    empty_response = {
        "status": "ok",
        "version": "test-ai-premium-v25-4-refresh-stable-colors",
        "timeframe": tf,
        "category": category,
        "symbols": [],
        "timeframes": allowed_timeframes,
        "signals": {},
        "items": [],
        "total": 0,
        "total_filtered": 0,
        "has_more": False,
        "next_offset": None,
        "limit": limit,
        "offset": offset,
        "buy": 0,
        "sell": 0,
        "server_time": now_iso(),
    }
    if tf not in allowed_timeframes:
        return empty_response

    symbols_map = {}
    rows = []

    for key, value in latest_signals.items():
        symbol_value = value.get("symbol", "")
        sig_cat = value.get("category", "other")
        sig_tf = (value.get("requested_timeframe") or value.get("timeframe") or "").upper()

        if not symbol_value or sig_cat == "other":
            continue
        if not user_symbol_allowed(user, symbol_value):
            continue

        symbols_map[symbol_value] = {
            "symbol": symbol_value,
            "category": sig_cat,
            "icon": category_icon(sig_cat),
            "symbol_ar": value.get("symbol_ar") or symbol_name(symbol_value, sig_cat, "ar"),
            "symbol_en": value.get("symbol_en") or symbol_name(symbol_value, sig_cat, "en"),
            "favorite": is_favorite_symbol(symbol_value),
        }

        if sig_tf != tf:
            continue
        if selected_symbols and clean_symbol(symbol_value) not in selected_symbols:
            continue
        elif selected_symbol and clean_symbol(symbol_value) != selected_symbol:
            continue
        if category == "favorite" and not is_favorite_symbol(symbol_value):
            continue
        if category not in ["all", "favorite"] and sig_cat != category:
            continue
        if q_clean and q_clean not in symbol_value.upper() and q_clean not in (value.get("symbol_ar", "") or "").upper() and q_clean not in (value.get("symbol_en", "") or "").upper():
            continue

        compact = apply_lifecycle_badge(compact_signal(value))
        row_signal = str(compact.get("signal") or "WAIT").upper()
        if selected_signal != "ALL" and row_signal != selected_signal:
            continue
        try:
            qscore = float(compact.get("quality_score") or 0)
        except Exception:
            qscore = 0.0
        if min_quality > 0 and qscore < min_quality:
            continue

        qlabel = _normalize_quality(compact.get("quality_label") or "")
        if selected_qualities and qlabel not in selected_qualities:
            continue

        compact["trend_strength_ar"] = trend_strength_label(compact)
        compact["trend_direction_ar"] = trend_direction_label(compact)
        compact["timeframe_trends"] = trend_pack(symbol_value, user)
        compact["rank"] = symbol_rank(symbol_value, sig_cat)
        rows.append(compact)

    def _num(v):
        try:
            return float(v or 0)
        except Exception:
            return 0.0

    if sort == "quality_desc":
        rows.sort(key=lambda x: (-_num(x.get("quality_score")), -_num(x.get("confidence")), x.get("rank", (999, 999, x.get("symbol", ""))), x.get("symbol", "")))
    elif sort == "confidence_desc":
        rows.sort(key=lambda x: (-_num(x.get("confidence")), x.get("rank", (999, 999, x.get("symbol", ""))), x.get("symbol", "")))
    elif sort == "updated_desc":
        rows.sort(key=lambda x: str(x.get("updated_at") or ""), reverse=True)
    elif sort == "symbol_asc":
        rows.sort(key=lambda x: clean_symbol(x.get("symbol", "")))
    else:
        rows.sort(key=lambda x: (x.get("rank", (999, 999, x.get("symbol", ""))), x.get("symbol", "")))

    total_filtered = len(rows)
    page_rows = rows[offset:offset + limit]
    has_more = offset + limit < total_filtered
    next_offset = offset + limit if has_more else None

    buy_count = sum(1 for x in rows if x.get("signal") == "BUY")
    sell_count = sum(1 for x in rows if x.get("signal") == "SELL")

    symbols_map = filter_symbols_for_user(user, symbols_map)

    return {
        "status": "ok",
        "version": "test-ai-premium-v25-4-refresh-stable-colors",
        "timeframe": tf,
        "category": category,
        "signal_filter": selected_signal,
        "quality_filters": sorted(list(selected_qualities)),
        "symbol_filters": sorted(list(selected_symbols or ({selected_symbol} if selected_symbol else set()))),
        "sort": sort,
        "symbols": sorted_symbol_items(symbols_map),
        "timeframes": allowed_timeframes,
        "signals": {f"{x.get('symbol')}_{tf}": x for x in page_rows},
        "items": page_rows,
        "total": len(page_rows),
        "total_filtered": total_filtered,
        "has_more": has_more,
        "next_offset": next_offset,
        "limit": limit,
        "offset": offset,
        "buy": buy_count,
        "sell": sell_count,
        "server_time": now_iso(),
    }


@app.get("/latest-mobile")
def latest_mobile(request: Request):
    denied = require_feature_json(request, "mobile")
    if denied:
        return denied
    user = get_access_user(request)
    symbols_map = {}
    signals = {}

    # Keep mobile payload small: only non-WAIT signals first, then remaining recent cached signals.
    values = []
    for key, value in latest_signals.items():
        symbol = value.get("symbol", "")
        category = value.get("category", "other")
        if not symbol or category == "other":
            continue
        if not user_symbol_allowed(user, symbol):
            continue
        compact = apply_lifecycle_badge(compact_signal(value))
        tf = (compact.get("requested_timeframe") or compact.get("timeframe") or "").upper()
        if tf not in access_allowed_timeframes(user):
            continue
        values.append((key, compact))
        symbols_map[symbol] = {
            "symbol": symbol,
            "category": category,
            "icon": category_icon(category),
            "symbol_ar": value.get("symbol_ar") or symbol_name(symbol, category, "ar"),
            "symbol_en": value.get("symbol_en") or symbol_name(symbol, category, "en"),
            "favorite": is_favorite_symbol(symbol),
        }

    symbols_map = filter_symbols_for_user(user, symbols_map)
    allowed_timeframes = access_allowed_timeframes(user)

    # Prioritize actionable signals on mobile.
    values.sort(key=lambda kv: (0 if kv[1].get("signal") in ["BUY", "SELL"] else 1, -float(kv[1].get("confidence") or 0)))
    for key, compact in values[:160]:
        signals[key] = compact

    return {
        "status": "ok",
        "version": "test-ai-premium-v25-4-refresh-stable-colors",
        "symbols": sorted_symbol_items(symbols_map),
        "timeframes": allowed_timeframes,
        "signals": signals,
        "server_time": now_iso(),
        "cached_signals": len(signals),
    }


@app.get("/mobile", response_class=HTMLResponse)
def mobile_page(request: Request):
    denied = require_feature_page(request, "mobile")
    if denied:
        return denied
    return HTMLResponse(r"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<title>QuantBado Mobile</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<style>
:root{--bg:#05070b;--panel:#0b1220;--line:#23314a;--muted:#8fa1bd;--text:#eaf2ff;--blue:#38bdf8;--green:#22c55e;--red:#ef4444;--yellow:#facc15}*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(circle at 85% 0%,rgba(56,189,248,.18),transparent 30%),linear-gradient(180deg,#05070b,#020617);color:var(--text);font-family:Arial,Tahoma,sans-serif;padding:10px;padding-bottom:22px}.app{width:100%;max-width:560px;margin:0 auto}.head{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}.brand{font-size:24px;font-weight:900;color:var(--blue)}.sub{font-size:11px;color:var(--muted);margin-top:2px}.live{display:inline-flex;align-items:center;gap:6px;color:#86efac;background:rgba(34,197,94,.12);border:1px solid rgba(34,197,94,.25);padding:7px 10px;border-radius:999px;font-size:12px;font-weight:900}.dot{width:7px;height:7px;background:var(--green);border-radius:50%}.dock{position:sticky;top:6px;z-index:50;background:rgba(8,13,24,.94);border:1px solid rgba(148,163,184,.18);backdrop-filter:blur(16px);box-shadow:0 16px 45px rgba(0,0,0,.34);border-radius:22px;padding:10px;margin-bottom:10px}.dock-row{display:grid;grid-template-columns:1fr 1fr 1fr auto;gap:8px}select,input,button{width:100%;background:#070d18;color:var(--text);border:1px solid #263244;border-radius:14px;padding:11px;font-size:13px;outline:none;min-height:42px}button{cursor:pointer;font-weight:900;background:linear-gradient(135deg,#38bdf8,#22c55e);color:#00111f;border:0}.ghost{background:#111827;color:var(--text);border:1px solid #334155}.search-line{display:none;margin-top:8px;grid-template-columns:1fr auto;gap:8px}.search-line.open{display:grid}.filter-drawer{display:none;margin-top:8px;border-top:1px solid rgba(148,163,184,.12);padding-top:8px}.filter-drawer.open{display:block}.drawer-title{font-size:12px;color:#94a3b8;font-weight:900;margin:6px 0}.chips{display:flex;gap:7px;overflow-x:auto;padding-bottom:4px}.chip{white-space:nowrap;display:inline-flex;align-items:center;gap:6px;border:1px solid #263244;background:#0b1424;color:#dbeafe;border-radius:999px;padding:8px 10px;font-size:12px;font-weight:900;cursor:pointer}.chip input{display:none}.chip:has(input:checked){border-color:#38bdf8;background:rgba(56,189,248,.16);color:#7dd3fc}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:10px}.stat{background:rgba(15,23,42,.88);border:1px solid rgba(148,163,184,.16);border-radius:16px;padding:10px;text-align:center}.stat .l{font-size:10px;color:var(--muted)}.stat .v{font-size:17px;font-weight:900;margin-top:4px}.green{color:var(--green)}.red{color:var(--red)}.yellow{color:var(--yellow)}.blue{color:var(--blue)}.best{background:rgba(15,23,42,.88);border:1px solid rgba(148,163,184,.16);border-radius:20px;padding:12px;margin-bottom:10px}.section-title{display:flex;justify-content:space-between;font-size:14px;font-weight:900;margin-bottom:8px}.section-title span{font-size:11px;color:var(--muted)}.best-list{display:flex;gap:8px;overflow-x:auto;padding-bottom:4px}.opp{min-width:160px;background:#070d18;border:1px solid #1e293b;border-radius:16px;padding:10px}.opp b{font-size:15px}.opp small{display:block;color:var(--muted);margin-top:4px;line-height:1.35}.pill{display:inline-flex;align-items:center;justify-content:center;border-radius:999px;padding:6px 9px;font-size:11px;font-weight:900;border:1px solid rgba(148,163,184,.18)}.buy{color:#22c55e;background:rgba(34,197,94,.12);border-color:rgba(34,197,94,.28)}.sell{color:#ef4444;background:rgba(239,68,68,.12);border-color:rgba(239,68,68,.28)}.wait{color:#facc15;background:rgba(250,204,21,.10);border-color:rgba(250,204,21,.25)}.cards{display:grid;gap:10px}.card{background:linear-gradient(180deg,rgba(17,24,39,.96),rgba(2,6,23,.99));border:1px solid rgba(148,163,184,.18);border-radius:22px;padding:12px;box-shadow:0 16px 38px rgba(0,0,0,.24);animation:softIn .18s ease-out}@keyframes softIn{from{opacity:.92;transform:translateY(2px)}to{opacity:1;transform:none}}.card-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.sym{font-size:23px;font-weight:900}.name{font-size:12px;color:#cbd5e1;margin-top:4px}.meta{font-size:11px;color:var(--muted);margin-top:5px}.sig{min-width:76px;text-align:center;font-size:15px;font-weight:900;padding:9px 10px;border-radius:15px}.quality-a{color:#22c55e}.quality-b{color:#7dd3fc}.quality-c{color:#facc15}.quality-d{color:#f87171}.bar{height:8px;background:#1e293b;border-radius:999px;overflow:hidden;margin-top:11px}.fill{height:100%;background:linear-gradient(90deg,#22c55e,#38bdf8);border-radius:999px}.trend-strip{margin-top:10px;background:rgba(56,189,248,.06);border:1px solid rgba(56,189,248,.13);border-radius:14px;padding:10px}.trend-title{font-size:12px;color:#7dd3fc;font-weight:900;margin-bottom:8px}.trend-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:7px}.tbox{background:#070d18;border:1px solid #1e293b;border-radius:12px;padding:8px;text-align:center}.tbox span{display:block;color:var(--muted);font-size:10px}.tbox strong{display:block;font-size:12px;margin-top:4px}.tbox.tr-up{border-color:rgba(34,197,94,.40);background:rgba(34,197,94,.10)}.tbox.tr-up strong{color:#22c55e}.tbox.tr-down{border-color:rgba(239,68,68,.40);background:rgba(239,68,68,.10)}.tbox.tr-down strong{color:#ef4444}.tbox.tr-side{border-color:rgba(250,204,21,.36);background:rgba(250,204,21,.09)}.tbox.tr-side strong{color:#facc15}.tbox.tr-none{border-color:rgba(148,163,184,.20);background:rgba(148,163,184,.06)}.tbox.tr-none strong{color:#94a3b8}.qrow{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-top:10px}.qbox{background:#070d18;border:1px solid #1e293b;border-radius:15px;padding:10px}.label{font-size:11px;color:var(--muted)}.val{font-size:16px;font-weight:900;margin-top:5px;word-break:break-word}.tp-main{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-top:10px}.tp-more summary{cursor:pointer;color:#7dd3fc;font-size:12px;font-weight:900;padding:8px 10px;background:#07101e;border:1px solid #1e293b;border-radius:12px;margin-top:8px}.tp-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-top:8px}.tp{background:#07101e;border:1px solid #1e293b;border-radius:12px;padding:8px;text-align:center}.tp span{display:block;color:var(--muted);font-size:10px}.tp strong{display:block;font-size:13px;margin-top:4px}.explain{margin-top:10px;background:rgba(56,189,248,.07);border:1px solid rgba(56,189,248,.12);border-radius:15px;padding:10px;color:#dbeafe;font-size:12px;line-height:1.55}.warns{margin-top:10px;background:rgba(250,204,21,.08);border:1px solid rgba(250,204,21,.18);border-radius:14px;padding:10px;color:#fde68a;font-size:12px;line-height:1.5}.empty{text-align:center;color:var(--muted);padding:22px}.loader{text-align:center;color:#7dd3fc;padding:14px;font-size:12px}.footer{text-align:center;color:#64748b;font-size:11px;margin:16px 0}@media(max-width:390px){body{padding:8px}.dock-row{grid-template-columns:1fr 1fr}.dock-row button{grid-column:auto}.stats{grid-template-columns:repeat(2,1fr)}.trend-grid{grid-template-columns:repeat(2,1fr)}.sym{font-size:20px}.qrow{grid-template-columns:1fr 1fr}}
</style>
</head><body><div class="app"><div class="head"><div><div class="brand">QuantBado AI</div><div class="sub">لوحة موبايل مبسطة للمبتدئ · V25.3</div></div><span class="live"><span class="dot"></span>LIVE</span></div><div class="dock"><div class="dock-row"><select id="tf"><option>M1</option><option>M5</option><option>M15</option><option>H1</option><option>H4</option><option>D1</option></select><select id="cat"><option value="all">كل التصنيفات</option><option value="favorite">المفضلة</option><option value="forex">فوركس</option><option value="commodity">سلع</option><option value="index">مؤشرات</option><option value="crypto">كريبتو</option></select><select id="sig"><option value="all">كل الإشارات</option><option value="BUY">شراء</option><option value="SELL">بيع</option><option value="WAIT">انتظار</option></select><button class="ghost" onclick="toggleSearch()">🔎</button><button class="ghost" onclick="toggleFilters()">فلاتر</button><button onclick="reloadHard()">تحديث</button></div><div id="searchLine" class="search-line"><input id="q" placeholder="ابحث عن رمز أو اسم..."><button class="ghost" onclick="clearSearch()">مسح</button></div><div id="drawer" class="filter-drawer"><div class="drawer-title">الجودة</div><div class="chips" id="qualityChips"></div><div class="drawer-title">الأزواج</div><div class="chips" id="symbolChips"><span class="label">تظهر الرموز بعد التحميل</span></div><div class="drawer-title">الترتيب</div><select id="sort"><option value="quality_desc">الأفضل</option><option value="confidence_desc">الثقة</option><option value="updated_desc">الأحدث</option><option value="symbol_asc">الرمز</option></select><button class="ghost" style="margin-top:8px" onclick="resetFilters()">إعادة تعيين</button></div></div><div class="stats" id="stats"></div><div class="best"><div class="section-title">الأفضل الآن <span id="sync">تحميل...</span></div><div class="best-list" id="bestList"></div></div><div class="cards" id="cards"><div class="empty">تحميل البيانات...</div></div><div id="loader" class="loader"></div><div class="footer">QuantBado · v25.3</div></div>
<script>
const $=id=>document.getElementById(id);let selectedSymbols=new Set(),selectedQualities=new Set(),symbolList=[],nextOffset=0,hasMore=true,loading=false,requestSeq=0;const qualityOptions=[['A+','قوي جداً'],['A','ممتاز'],['B','جيد'],['C','متوسط'],['D','ضعيف']];
function fmt(v){return(v===null||v===undefined||v==='')?'-':v}function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}function toggleSearch(){ $('searchLine').classList.toggle('open'); if($('searchLine').classList.contains('open')) $('q').focus() }function toggleFilters(){ $('drawer').classList.toggle('open') }
function sigClass(s){s=String(s||'WAIT').toUpperCase();return s==='BUY'?'buy':s==='SELL'?'sell':'wait'}function sigLabel(s){s=String(s||'WAIT').toUpperCase();return s==='BUY'?'شراء':s==='SELL'?'بيع':'انتظار'}function qWord(label,q){if(label==='A+'||q>=80)return'قوي جداً';if(label==='A'||q>=70)return'ممتاز';if(label==='B'||q>=60)return'جيد';if(label==='C'||q>=50)return'متوسط';return'ضعيف'}function qClass(label,q){if(label==='A+'||label==='A'||q>=70)return'quality-a';if(label==='B'||q>=60)return'quality-b';if(label==='C'||q>=50)return'quality-c';return'quality-d'}function qBadge(s){let q=Number(s.quality_score??s.confidence??0);let label=s.quality_label||'-';return `<span class="${qClass(label,q)}"><b>${q.toFixed(1)}%</b> · ${qWord(label,q)}</span>`}function setupText(v){const m={trend_breakout:'اختراق مع الاتجاه',trend_breakdown:'كسر مع الاتجاه',rejection:'ارتداد من منطقة مهمة',ma_reclaim:'استرجاع متوسط MA21',range_wait:'انتظار داخل نطاق',momentum_setup:'زخم سعري'};return m[v]||v||'-'}function warnText(v){const m={'No actionable setup':'لا توجد فرصة واضحة','Risk levels incomplete':'مستويات المخاطرة غير مكتملة','ATR unavailable':'ATR غير متوفر','Mixed directional scores':'الاتجاه غير محسوم','Momentum may be stretched':'الزخم قد يكون مبالغاً فيه'};return m[v]||v}function localTime(iso){if(!iso)return'-';const d=new Date(iso);return isNaN(d.getTime())?iso:d.toLocaleTimeString('tr-TR')}function trendText(s){return `${fmt(s.trend_direction_ar||'عرضي')} ${fmt(s.trend_strength_ar||'ضعيف')}`}
function trendClass(x){const d=String((x&&x.direction)||'');if(d.includes('صاعد'))return 'tr-up';if(d.includes('هابط'))return 'tr-down';if(d.includes('عرض'))return 'tr-side';return 'tr-none'}
function trendStrip(s){const arr=s.timeframe_trends||[];if(!arr.length)return'';return `<div class="trend-strip"><div class="trend-title">الاتجاه العام لكل الفريمات</div><div class="trend-grid">${arr.map(x=>`<div class="tbox ${trendClass(x)}"><span>${esc(x.timeframe)}</span><strong>${esc(x.direction)} ${esc(x.strength)}</strong></div>`).join('')}</div></div>`}function targets(s){return `<div class="tp-main"><div class="tp"><span>TP1</span><strong>${fmt(s.tp1)}</strong></div><div class="tp"><span>TP2</span><strong>${fmt(s.tp2)}</strong></div></div><details class="tp-more"><summary>عرض باقي الأهداف</summary><div class="tp-grid"><div class="tp"><span>TP3</span><strong>${fmt(s.tp3)}</strong></div><div class="tp"><span>TP4</span><strong>${fmt(s.tp4)}</strong></div><div class="tp"><span>TP5</span><strong>${fmt(s.tp5)}</strong></div></div></details>`}
function card(s){const sig=s.signal||'WAIT';const warns=Array.isArray(s.warnings)?s.warnings:[];return `<div class="card"><div class="card-head"><div><div class="sym">${fmt(s.symbol)} ${fmt(s.icon)}</div><div class="name">${fmt(s.symbol_ar)}</div><div class="name">${fmt(s.symbol_en)}</div><div class="meta">${fmt(s.timeframe||s.requested_timeframe)} · ${fmt(s.lifecycle_label_ar||'')} · ${localTime(s.updated_at)}</div></div><div class="sig ${sigClass(sig)}">${sigLabel(sig)}</div></div>${trendStrip(s)}<div class="bar"><div class="fill" style="width:${Math.max(0,Math.min(100,Number(s.quality_score||0)))}%"></div></div><div class="qrow"><div class="qbox"><div class="label">جودة الفرصة</div><div class="val">${qBadge(s)}</div></div><div class="qbox"><div class="label">R/R</div><div class="val">${fmt(s.risk_reward)}</div></div><div class="qbox"><div class="label">الاتجاه</div><div class="val">${trendText(s)}</div></div><div class="qbox"><div class="label">الدخول</div><div class="val">${fmt(s.entry)}</div></div><div class="qbox"><div class="label">SL</div><div class="val">${fmt(s.sl)}</div></div><div class="qbox"><div class="label">الثقة</div><div class="val">${fmt(s.confidence)}%</div></div></div>${targets(s)}<div class="explain"><b>${setupText(s.setup_type)}</b><br>${fmt(s.reason)}</div>${warns.length?`<div class="warns">${warns.map(w=>'⚠ '+warnText(w)).join('<br>')}</div>`:''}</div>`}
function opp(s){return `<div class="opp" onclick="pick('${esc(s.symbol)}')"><b>${fmt(s.symbol)}</b><small>${fmt(s.symbol_ar)}</small><div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px"><span class="pill ${sigClass(s.signal)}">${sigLabel(s.signal)}</span><span>${qBadge(s)}</span></div></div>`}function pick(symbol){selectedSymbols=new Set([symbol]);renderSymbolChips();load(true)}
function renderQualityChips(){ $('qualityChips').innerHTML=qualityOptions.map(([v,t])=>`<label class="chip"><input type="checkbox" value="${v}" ${selectedQualities.has(v)?'checked':''} onchange="toggleQuality(this)">${t}</label>`).join('') }function toggleQuality(el){el.checked?selectedQualities.add(el.value):selectedQualities.delete(el.value);load(true)}function renderSymbolChips(list){symbolList=list||symbolList;let html=symbolList.map(x=>`<label class="chip"><input type="checkbox" value="${esc(x.symbol)}" ${selectedSymbols.has(x.symbol)?'checked':''} onchange="toggleSymbol(this)">${esc(x.symbol)}</label>`).join('');$('symbolChips').innerHTML=html||'<span class="label">لا توجد رموز</span>'}function toggleSymbol(el){el.checked?selectedSymbols.add(el.value):selectedSymbols.delete(el.value);load(true)}
async function load(reset=true,silent=false){
  if(loading)return;
  loading=true;
  const seq=++requestSeq;
  if(reset){
    nextOffset=0;
    hasMore=true;
    if(!silent)$('cards').innerHTML='<div class="empty">تحميل البيانات...</div>';
  }
  try{
    const params=new URLSearchParams({tf:$('tf').value,category:$('cat').value,q:$('q').value.trim(),signal:$('sig').value,sort:$('sort').value,limit:'40',offset:String(nextOffset)});
    if(selectedQualities.size)params.set('qualities',[...selectedQualities].join(','));
    if(selectedSymbols.size)params.set('symbols',[...selectedSymbols].join(','));
    const res=await fetch('/test-ai/mobile-data?'+params.toString(),{cache:'no-store'});
    const data=await res.json();
    if(seq!==requestSeq)return;
    if(!res.ok||data.status==='unauthorized'){location.href='/test-ai/login?next=/test-ai/mobile';return}
    renderSymbolChips(data.symbols||[]);
    const items=data.items||[];
    if(reset){
      const buy=items.filter(x=>x.signal==='BUY').length;
      const sell=items.filter(x=>x.signal==='SELL').length;
      const best=items.filter(x=>Number(x.quality_score||0)>=70).length;
      $('stats').innerHTML=[['النتائج',data.total_filtered??items.length,'blue'],['شراء',buy,'green'],['بيع',sell,'red'],['الأفضل',best,'green']].map(x=>`<div class="stat"><div class="l">${x[0]}</div><div class="v ${x[2]}">${x[1]}</div></div>`).join('');
      $('bestList').innerHTML=items.filter(x=>Number(x.quality_score||0)>=70).slice(0,12).map(opp).join('')||'<div class="empty">لا توجد فرص ممتازة حالياً</div>';
      $('cards').innerHTML=items.length?items.map(card).join(''):'<div class="empty">لا توجد نتائج حسب الفلاتر الحالية</div>'
    }else{
      if(items.length)$('cards').insertAdjacentHTML('beforeend',items.map(card).join(''))
    }
    nextOffset=data.next_offset||0;
    hasMore=data.has_more===true;
    $('sync').innerText='آخر تحديث '+localTime(data.server_time);
    $('loader').innerText=hasMore?'اسحب للأسفل لتحميل المزيد':'نهاية القائمة'
  }catch(e){
    if(reset&&!silent)$('cards').innerHTML='<div class="empty">تعذر تحميل البيانات</div>';
    $('loader').innerText='تعذر التحديث، بقيت البيانات السابقة ظاهرة';
    console.error(e)
  }finally{loading=false}
}
function reloadHard(){load(true)}function clearSearch(){$('q').value='';load(true)}function resetFilters(){selectedSymbols.clear();selectedQualities.clear();['tf','cat','sig','sort','q'].forEach(id=>{const el=$(id);if(id==='tf')el.value='M1';else if(id==='cat'||id==='sig')el.value='all';else if(id==='sort')el.value='quality_desc';else el.value=''});renderQualityChips();renderSymbolChips();load(true)}
['tf','cat','sig','sort'].forEach(id=>$(id).addEventListener('change',()=>load(true)));let timer=null;$('q').addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(()=>load(true),350)});window.addEventListener('scroll',()=>{if(hasMore&&!loading&&window.innerHeight+window.scrollY>document.body.offsetHeight-450)load(false)});renderQualityChips();load(true);setInterval(()=>load(true,true),15000);
</script></body></html>
""")


@app.get("/admin-success", response_class=HTMLResponse)
def admin_success_page(request: Request):
    denied = require_feature_page(request, "admin")
    if denied:
        return denied
    data = build_performance()
    return HTMLResponse(f"""
<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>نجاح التوصيات</title>
<style>body{{margin:0;background:#05070b;color:#e5eef8;font-family:Arial,Tahoma,sans-serif;padding:14px}}.app{{max-width:1100px;margin:auto}}.top{{display:flex;justify-content:space-between;align-items:center}}a{{color:#7dd3fc;text-decoration:none}}.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}}.card{{background:#0f172a;border:1px solid #263244;border-radius:18px;padding:14px}}.v{{font-size:24px;font-weight:900}}table{{width:100%;border-collapse:separate;border-spacing:0 8px;margin-top:14px}}td,th{{background:#070d18;padding:10px;text-align:right}}@media(min-width:700px){{.grid{{grid-template-columns:repeat(4,1fr)}}}}</style></head><body><div class="app"><div class="top"><h2>سجل نجاح التوصيات - أدمن</h2><a href="/test-ai/admin">الإدارة</a></div><div id="root"></div></div>
<script>const data={json.dumps(data, ensure_ascii=False)};const s=data.summary||{{}};document.getElementById('root').innerHTML=`<div class="grid"><div class="card">إجمالي<div class="v">${{s.total||0}}</div></div><div class="card">TP1+<div class="v">${{s.win_rate_tp1||0}}%</div></div><div class="card">TP2<div class="v">${{s.win_rate_tp2||0}}%</div></div><div class="card">SL<div class="v">${{s.sl_hit||0}}</div></div></div><table><thead><tr><th>رمز</th><th>إجمالي</th><th>TP1</th><th>TP2</th><th>SL</th><th>نسبة</th></tr></thead><tbody>${{(data.best_symbols||[]).map(x=>`<tr><td><b>${{x.symbol}}</b></td><td>${{x.total}}</td><td>${{x.tp1_hit}}</td><td>${{x.tp2_hit}}</td><td>${{x.sl_hit}}</td><td>${{x.win_rate_tp1}}%</td></tr>`).join('')}}</tbody></table>`</script></body></html>""")


@app.get("/admin-users-audit", response_class=HTMLResponse)
def admin_users_audit_page(request: Request):
    denied = require_feature_page(request, "admin")
    if denied:
        return denied
    return HTMLResponse(r"""
<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>تدقيق المستخدمين</title>
<style>body{margin:0;background:#05070b;color:#e5eef8;font-family:Arial,Tahoma,sans-serif;padding:14px}.app{max-width:1200px;margin:auto}a{color:#7dd3fc}.controls{display:grid;grid-template-columns:1fr auto;gap:8px;margin:12px 0}input,button{background:#070d18;color:#e5eef8;border:1px solid #263244;border-radius:14px;padding:12px}button{font-weight:900;background:#1e293b}.grid{display:grid;grid-template-columns:1fr;gap:12px}.card{background:#0f172a;border:1px solid #263244;border-radius:18px;padding:14px}.item{background:#070d18;border:1px solid #1e293b;border-radius:14px;padding:10px;margin:8px 0}.bad{color:#fecaca}.ok{color:#86efac}@media(min-width:800px){.grid{grid-template-columns:1fr 1fr}}</style></head><body><div class="app"><h2>تدقيق المستخدمين والاشتراكات</h2><a href="/test-ai/admin">رجوع للإدارة</a><div class="controls"><input id="q" placeholder="بحث عن اسم مستخدم أو خطة أو مفتاح"><button onclick="load()">بحث</button></div><div class="grid"><div class="card"><h3>نتائج البحث</h3><div id="users"></div></div><div class="card"><h3>باقي للتجديد أسبوع</h3><div id="renewals"></div></div><div class="card"><h3>IP عليه أكثر من حساب</h3><div id="multi"></div></div><div class="card"><h3>الجلسات المفتوحة</h3><div id="sessions"></div></div></div></div><script>
function fmt(v){return v||'-'}function item(html){return `<div class="item">${html}</div>`}
async function load(){const q=document.getElementById('q').value||'';const r=await fetch('/test-ai/admin-users-audit-data?q='+encodeURIComponent(q),{cache:'no-store'});const d=await r.json();document.getElementById('users').innerHTML=(d.users||[]).map(u=>item(`<b>${u.name}</b> · ${u.plan}<br>ينتهي: ${fmt(u.expires_at)} · ${u.enabled&&!u.expired?'<span class=ok>فعال</span>':'<span class=bad>موقوف/منتهي</span>'}<br><small>${u.key}</small>`)).join('')||'لا توجد نتائج';document.getElementById('renewals').innerHTML=(d.expiring_soon||[]).map(u=>item(`<b>${u.name}</b><br>ينتهي: ${u.expires_at} · باقي ${u.days_left} يوم`)).join('')||'لا يوجد';document.getElementById('multi').innerHTML=(d.multi_account_ips||[]).map(x=>item(`<b>${x.ip}</b><br>${x.users.join('<br>')}`)).join('')||'لا يوجد';document.getElementById('sessions').innerHTML=(d.sessions||[]).map(s=>item(`<b>${s.user_name}</b> · ${s.user_plan}<br>IP: ${s.ip}<br>ينتهي: ${s.expires_at}`)).join('')||'لا يوجد'}load();</script></body></html>""")


@app.get("/admin-users-audit-data")
def admin_users_audit_data(request: Request, q: str = ""):
    denied = require_feature_json(request, "admin")
    if denied:
        return denied
    cfg = load_access_config()
    ql = (q or "").strip().lower()
    users = []
    expiring = []
    now = datetime.now(timezone.utc)
    for raw in cfg.get("users", []):
        u = normalize_access_user(raw)
        u["expired"] = access_user_expired(u)
        if ql and ql not in str(u.get("name", "")).lower() and ql not in str(u.get("plan", "")).lower() and ql not in str(u.get("key", "")).lower():
            pass
        else:
            users.append(u)
        exp = str(u.get("expires_at") or "")
        if exp:
            dt = _parse_dt(exp + "T23:59:59+00:00" if "T" not in exp else exp)
            if dt:
                days = (dt - now).days
                if 0 <= days <= 7:
                    x = dict(u); x["days_left"] = days; expiring.append(x)
    conn = get_db(); cur = conn.cursor()
    cur.execute("""SELECT user_name, user_plan, ip, expires_at, last_seen, active FROM active_sessions WHERE active = 1 ORDER BY id DESC LIMIT 300""")
    sessions = [dict(r) for r in cur.fetchall()]
    conn.close()
    by_ip = {}
    for s in sessions:
        ip = s.get("ip") or ""
        if not ip: continue
        by_ip.setdefault(ip, set()).add((s.get("user_name") or "") + " (" + (s.get("user_plan") or "") + ")")
    multi = [{"ip": ip, "users": sorted(list(vals))} for ip, vals in by_ip.items() if len(vals) > 1]
    return {"status":"ok", "version":"test-ai-premium-v25-4-refresh-stable-colors", "users": users, "expiring_soon": expiring, "sessions": sessions, "multi_account_ips": multi, "ip": _client_ip(request)}
