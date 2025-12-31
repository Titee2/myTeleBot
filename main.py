import requests
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import os
import sys

BINANCE = "https://api.binance.com"

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    sys.exit("Missing BOT_TOKEN or CHAT_ID")

def send_telegram(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": str(msg)},
            timeout=10
        )
    except:
        pass

TIMEFRAME = "5m"
PRICE_LEN = 5
TARGET_LEN = 5
NUM_CLOSEST = 3
SCAN_INTERVAL = 60

def top_25():
    try:
        r = requests.get(f"{BINANCE}/api/v3/ticker/24hr", timeout=10)
        data = r.json()
        if not isinstance(data, list):
            return []
        out = []
        for x in data:
            if isinstance(x, dict):
                s = x.get("symbol")
                v = x.get("quoteVolume")
                if isinstance(s, str) and s.endswith("USDT"):
                    try:
                        out.append((s, float(v)))
                    except:
                        pass
        out.sort(key=lambda x: x[1], reverse=True)
        return [x[0] for x in out[:25]]
    except:
        return []

def klines(symbol):
    try:
        r = requests.get(
            f"{BINANCE}/api/v3/klines",
            params={"symbol": symbol, "interval": TIMEFRAME, "limit": 200},
            timeout=10
        )
        data = r.json()
        if not isinstance(data, list):
            return None
        rows = [x for x in data if isinstance(x, list) and len(x) >= 6]
        if len(rows) < 50:
            return None
        df = pd.DataFrame(rows, columns=[
            "ot","o","h","l","c","v","ct","q","n","tbb","tbq","ig"
        ])
        df[["h","l","c"]] = df[["h","l","c"]].astype(float)
        return df
    except:
        return None

def mean_of_k_closest(value, target, k):
    window = max(k, 30)
    out = np.full(len(value), np.nan)
    for i in range(window, len(value)):
        d = np.abs(value[i-window:i] - target[i])
        idx = np.argsort(d)[:k]
        out[i] = value[i-window:i][idx].mean()
    return out

def wma(series, length):
    w = np.arange(1, length + 1)
    return series.rolling(length).apply(lambda x: np.dot(x, w)/w.sum(), raw=True)

def run():
    last_state = {}
    send_telegram("✅ Bot started (5M, confirmed candles only)")

    while True:
        symbols = top_25()
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
            ts = (datetime.utcnow()+timedelta(hours=5,minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
            if b < c and b <= a and last_state.get(sym) != "BUY":
                send_telegram(f"🟢 BUY {sym}\n{ts}")
                last_state[sym] = "BUY"
            elif b > c and b >= a and last_state.get(sym) != "SELL":
                send_telegram(f"🔴 SELL {sym}\n{ts}")
                last_state[sym] = "SELL"
        time.sleep(SCAN_INTERVAL)

while True:
    try:
        run()
    except Exception as e:
        send_telegram(f"⚠️ BOT ERROR:\n{e}")
        time.sleep(15)
