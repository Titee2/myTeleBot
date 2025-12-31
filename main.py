# ==========================================================
# AI TREND NAVIGATOR — FINAL SAFE VERSION
# GITHUB ACTIONS • 5M • NO REPAINT
# ==========================================================

import requests
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import os
import sys

BINANCE = "https://api.binance.com"

# =========================
# TELEGRAM CONFIG
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    print("❌ Missing Telegram credentials")
    sys.exit(1)

def send_telegram(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg},
            timeout=10
        )
    except:
        pass

# =========================
# STRATEGY CONFIG
# =========================
TIMEFRAME = "5m"
PRICE_LEN = 5
TARGET_LEN = 5
NUM_CLOSEST = 3
SCAN_INTERVAL = 60

CSV_FILE = "signals.csv"

if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, "w") as f:
        f.write("Time,Symbol,Signal,Value\n")

# =========================
# SAFE API HELPERS
# =========================
def safe_json(resp):
    try:
        return resp.json()
    except:
        return None

def top_25():
    try:
        r = requests.get(f"{BINANCE}/api/v3/ticker/24hr", timeout=10)
        data = safe_json(r)

        if not isinstance(data, list):
            return []

        result = []

        for obj in data:
            if not isinstance(obj, dict):
                continue

            symbol = obj.get("symbol")
            vol = obj.get("quoteVolume")

            if isinstance(symbol, str) and symbol.endswith("USDT"):
                try:
                    result.append((symbol, float(vol)))
                except:
                    continue

        result.sort(key=lambda x: x[1], reverse=True)
        return [x[0] for x in result[:25]]

    except:
        return []

def klines(symbol):
    try:
        r = requests.get(
            f"{BINANCE}/api/v3/klines",
            params={"symbol": symbol, "interval": TIMEFRAME, "limit": 200},
            timeout=10
        )

        data = safe_json(r)

        if not isinstance(data, list):
            return None

        rows = []
        for row in data:
            if isinstance(row, list) and len(row) >= 6:
                rows.append(row)

        if len(rows) < 50:
            return None

        df = pd.DataFrame(rows, columns=[
            "ot","o","h","l","c","v",
            "ct","q","n","tbb","tbq","ig"
        ])

        df[["h","l","c"]] = df[["h","l","c"]].astype(float)
        return df

    except:
        return None

# =========================
# INDICATORS (UNCHANGED)
# =========================
def mean_of_k_closest(value, target, k):
    window = max(k, 30)
    out = np.full(len(value), np.nan)

    for i in range(window, len(value)):
        distances = np.abs(value[i-window:i] - target[i])
        idx = np.argsort(distances)[:k]
        out[i] = value[i-window:i][idx].mean()

    return out

def wma(series, length):
    w = np.arange(1, length + 1)
    return series.rolling(length).apply(
        lambda x: np.dot(x, w) / w.sum(), raw=True
    )

# =========================
# MAIN LOOP
# =========================
def run():
    last_state = {}

    send_telegram("✅ Bot started (5M, confirmed candles only)")

    while True:
        symbols = top_25()
        if not symbols:
            time.sleep(20)
            continue

        for sym in symbols:
            df = klines(sym)
            if df is None:
                continue

            df = df.iloc[:-1]

            hl2 = (df["h"] + df["l"]) / 2
            value = hl2.rolling(PRICE_LEN).mean()
            target = df["c"].rolling(TARGET_LEN).mean()

            knn = mean_of_k_closest(value.values, target.values, NUM_CLOSEST)
            knn = wma(pd.Series(knn, index=df.index), 5)

            a, b, c = knn.iloc[-3], knn.iloc[-2], knn.iloc[-1]
            if np.isnan([a, b, c]).any():
                continue

            up = b < c and b <= a
            dn = b > c and b >= a

            prev = last_state.get(sym)
            ts = (datetime.utcnow()+timedelta(hours=5,minutes=30)).strftime("%Y-%m-%d %H:%M:%S")

            if up and prev != "BUY":
                send_telegram(f"🟢 BUY {sym}\n{ts}")
                last_state[sym] = "BUY"
                with open(CSV_FILE, "a") as f:
                    f.write(f"{ts},{sym},BUY,{c}\n")

            elif dn and prev != "SELL":
                send_telegram(f"🔴 SELL {sym}\n{ts}")
                last_state[sym] = "SELL"
                with open(CSV_FILE, "a") as f:
                    f.write(f"{ts},{sym},SELL,{c}\n")

        time.sleep(SCAN_INTERVAL)

# =========================
# SAFE AUTO-RESTART
# =========================
while True:
    try:
        run()
    except Exception as e:
        send_telegram(f"⚠️ BOT ERROR:\n{e}")
        time.sleep(15)
