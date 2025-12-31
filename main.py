import requests
import pandas as pd
import numpy as np
import time
from datetime import datetime
import os
import pytz

# =========================
# ENV CONFIG (REQUIRED)
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("❌ BOT_TOKEN or CHAT_ID not set")

# =========================
# TELEGRAM
# =========================
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg}, timeout=10)

# =========================
# SETTINGS
# =========================
TIMEFRAME = "1h"
PRICE_LEN = 5
TARGET_LEN = 5
NUM_CLOSEST = 3
SCAN_INTERVAL = 60
BINANCE = "https://api.binance.com"
IST = pytz.timezone("Asia/Kolkata")

# =========================
# DATA
# =========================
def top_25():
    data = requests.get(f"{BINANCE}/api/v3/ticker/24hr").json()
    usdt = [x for x in data if x["symbol"].endswith("USDT")]
    usdt.sort(key=lambda x: float(x["quoteVolume"]), reverse=True)
    return [x["symbol"] for x in usdt[:25]]

def klines(symbol):
    r = requests.get(f"{BINANCE}/api/v3/klines", params={
        "symbol": symbol,
        "interval": TIMEFRAME,
        "limit": 200
    }).json()

    df = pd.DataFrame(r, columns=[
        "ot","o","h","l","c","v",
        "ct","q","n","tbb","tbq","ig"
    ])
    df[["h","l","c"]] = df[["h","l","c"]].astype(float)
    return df

# =========================
# INDICATORS
# =========================
def mean_of_k_closest(value, target, k):
    out = np.full(len(value), np.nan)
    window = max(k, 30)

    for i in range(window, len(value)):
        d = np.abs(value[i-window:i] - target[i])
        idx = np.argsort(d)[:k]
        out[i] = value[i-window:i][idx].mean()
    return out

def wma(series, length):
    w = np.arange(1, length + 1)
    return series.rolling(length).apply(lambda x: np.dot(x, w) / w.sum(), raw=True)

# =========================
# START
# =========================
send_telegram("✅ AI Trend Navigator started (IST)")

last_state = {}
last_heartbeat = time.time()

while True:
    try:
        for sym in top_25():
            df = klines(sym)

            hl2 = (df["h"] + df["l"]) / 2
            value_in = hl2.rolling(PRICE_LEN).mean()
            target = df["c"].rolling(TARGET_LEN).mean()

            knn = mean_of_k_closest(value_in.values, target.values, NUM_CLOSEST)
            knn = wma(pd.Series(knn), 5)

            a, b, c = knn.iloc[-3], knn.iloc[-2], knn.iloc[-1]
            if np.isnan([a,b,c]).any():
                continue

            now = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
            prev = last_state.get(sym)

            if b < c and b <= a and prev != "BUY":
                send_telegram(f"🟢 BUY {sym}\nknnMA: {round(c,6)}\n{now} IST")
                last_state[sym] = "BUY"

            elif b > c and b >= a and prev != "SELL":
                send_telegram(f"🔴 SELL {sym}\nknnMA: {round(c,6)}\n{now} IST")
                last_state[sym] = "SELL"

        if time.time() - last_heartbeat > 1800:
            send_telegram("❤️ Heartbeat: bot running")
            last_heartbeat = time.time()

        time.sleep(SCAN_INTERVAL)

    except Exception as e:
        send_telegram(f"⚠️ ERROR: {str(e)}")
        time.sleep(60)
