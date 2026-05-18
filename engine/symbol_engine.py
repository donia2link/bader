SYMBOL_MAP = {
    "XAUUSD": "XAUUSD",
    "XAUUSDm": "XAUUSD",
    "GOLD": "XAUUSD",
    "GOLDm": "XAUUSD",
    "BTCUSD": "BTCUSD",
    "BTCUSDm": "BTCUSD",
    "ETHUSD": "ETHUSD",
    "ETHUSDm": "ETHUSD",
    "EURUSD": "EURUSD",
    "EURUSDm": "EURUSD",
    "GBPUSD": "GBPUSD",
    "GBPUSDm": "GBPUSD",
    "USDJPY": "USDJPY",
    "USDJPYm": "USDJPY",
    "US30": "US30",
    "US30m": "US30",
    "NAS100": "NAS100",
    "NAS100m": "NAS100",
}


def normalize_symbol(symbol):
    if not symbol:
        return "UNKNOWN"

    clean_symbol = symbol.strip()

    if clean_symbol in SYMBOL_MAP:
        return SYMBOL_MAP[clean_symbol]

    suffixes = [".m", "m", ".pro", "pro", "_ecn", "ecn", ".raw", "raw"]

    for suffix in suffixes:
        if clean_symbol.endswith(suffix):
            base_symbol = clean_symbol[:-len(suffix)]
            if base_symbol in SYMBOL_MAP:
                return SYMBOL_MAP[base_symbol]
            return base_symbol

    return clean_symbol


def get_symbol_info(symbol):
    normalized = normalize_symbol(symbol)

    if normalized == "XAUUSD":
        asset_class = "metal"
    elif normalized in ["BTCUSD", "ETHUSD"]:
        asset_class = "crypto"
    elif normalized in ["US30", "NAS100"]:
        asset_class = "index"
    elif len(normalized) == 6:
        asset_class = "forex"
    else:
        asset_class = "unknown"

    return {
        "original_symbol": symbol,
        "normalized_symbol": normalized,
        "asset_class": asset_class
    }
(get_symbol_info("XAUUSDm"))
