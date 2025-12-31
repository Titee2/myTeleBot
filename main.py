import requests
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import os

# =========================
# CONFIG
# =========================
BINANCE = "https://api.binance.com"

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

TIMEFRAME = "5m"
PRICE_LEN = 5
TARGET_LEN = 5
NUM_CLOSEST = 3
SCAN_INTERVAL = 60

# =========================
# TELEGRAM (ABSOLUTE SAFE)
# =========================
def send_telegram(text):
    if not BOT_TOKEN or not CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={
                "chat_id": str(CHAT_ID),
                "text": str(text)
            },
            timeout=5
        )
    except:
        pass

# =========================
# BINANCE SAFE HELPERS
# =========================
def safe_get_json(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=10)
        try:
            return r.json()
        except:
            return None
    except:
        return None

def top_25():
    data = safe_get_json(f"{BINANCE}/api/v3/ticker/24hr")

    if not isinstance(data, list):
        return []

    pairs = []
    for item in data:
        if not isinstance(item, dict):
            continue

        symbol = item.get("symbol")
        volume = item.get("quoteVolume")

        if isinstance(symbol, str) and symbol.endswith("USDT"):
            try:
                pairs.append((symbol, float(volume)))
            except:
                pass

    pairs.sort(key=lambda x: x[1], reverse=True)
    return [p[0] for p in pairs[:25]]

def klines(symbol):
    data = safe_get_json(
        f"{BINANCE}/api/v3/klines",
        params={"symbol": symbol, "interval": TIMEFRAME, "limit": 200}
    )

    if not isinstance(data, list):
        return None

    rows = []
    for row in data:
        if isinstance(row, list) and len(row) >= 6:
            rows.append(row)

    if len(rows) < 60:
        return None

    df = pd.DataFrame(
        rows,
        columns=["ot","o","h","l","c","v","ct","q","n","tbb","tbq","ig"]
    )

    df[["h","l","c"]] = df[["h","l","c"]].astype(float)
    return df

# =========================
# INDICATORS (UNCHANGED)
# =========================
def mean_of_k_closest(value, target, k):
    window = max(k, 30)
    out = np.full(len(value), np.nan)

    for i in range(window, len(value)):
        dist = np.abs(value[i-window:i] - target[i])
        idx = np.argsort(dist)[:k]
        out[i] = value[i-window:i][idx].mean()

    return out

def wma(series, length):
    w = np.arange(1, length + 1)
    return series.rolling(length).apply(
        lambda x: np.dot(x, w) / w.sum(),
        raw=True
    )

# =========================
# MAIN LOOP
# =========================
def run():
    last_state = {}

    send_telegram("✅ Bot started (5M, confirmed candles only)")

    while True:
        symbols = top_25()

        for sym in symbols:
            df = klines(sym)
            if df is None:
                continue

            # confirmed candle only
            df = df.iloc[:-1]

            hl2 = (df["h"] + df["l"]) / 2
            value = hl2.rolling(PRICE_LEN).mean()
            target = df["c"].rolling(TARGET_LEN).mean()

            knn = mean_of_k_closest(
                value.values,
                target.values,
                NUM_CLOSEST
            )

            knn = wma(pd.Series(knn, index=df.index), 5)

            a, b, c = knn.iloc[-3], knn.iloc[-2], knn.iloc[-1]
            if np.isnan([a, b, c]).any():
                continue

            up = b < c and b <= a
            dn = b > c and b >= a

            prev = last_state.get(sym)
            ts = (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            if up and prev != "BUY":
                send_telegram(f"🟢 BUY {sym}\n{ts}")
                last_state[sym] = "BUY"

            elif dn and prev != "SELL":
                send_telegram(f"🔴 SELL {sym}\n{ts}")
                last_state[sym] = "SELL"

        time.sleep(SCAN_INTERVAL)

# =========================
# HARD RESTART LOOP
# =========================
while True:
    try:
        run()
    except:
        time.sleep(20)
