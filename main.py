# ==========================================================
# AI TREND NAVIGATOR — TELEGRAM ALERT BOT
# CLOUD / REPLIT / GITHUB ACTIONS READY
# IST TIMEZONE
# ==========================================================

import requests
import pandas as pd
import numpy as np
import time
from datetime import datetime, timezone, timedelta
import os

# =========================
# TELEGRAM CONFIG (ENV VARS)
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("❌ BOT_TOKEN or CHAT_ID not set in environment variables")

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": msg}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Telegram error:", e)

# =========================
# TIMEZONE (IST)
# =========================
IST = timezone(timedelta(hours=5, minutes=30))

def now_ist():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")

# =========================
# STRATEGY CONFIG
# =========================
TIMEFRAME = "1h"
PRICE_LEN = 5
TARGET_LEN = 5
NUM_CLOSEST = 3
SCAN_INTERVAL = 120  # seconds (safe for Binance)

CSV_FILE = "ai_trend_navigator_log.csv"
BINANCE = "https://api.binance.com"

# =========================
# CSV INIT
# =========================
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, "w") as f:
        f.write("Time,Symbol,Signal,knnMA\n")

# =========================
# BINANCE DATA (SAFE)
# =========================
def top_25():
    try:
        r = requests.get(f"{BINANCE}/api/v3/ticker/24hr", timeout=10)
        data = r.json()

        # Binance sometimes returns dict on error
        if not isinstance(data, list):
            print("Binance non-list response:", data)
            return []

        usdt = [x for x in data if x.get("symbol", "").endswith("USDT")]
        usdt.sort(key=lambda x: float(x.get("quoteVolume", 0)), reverse=True)
        return [x["symbol"] for x in usdt[:25]]

    except Exception as e:
        print("top_25 error:", e)
        return []

def klines(symbol):
    r = requests.get(
        f"{BINANCE}/api/v3/klines",
        params={"symbol": symbol, "interval": TIMEFRAME, "limit": 200},
        timeout=10
    ).json()

    if not isinstance(r, list):
        return None

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
    window = max(k, 30)
    out = np.full(len(value), np.nan)

    for i in range(window, len(value)):
        distances = np.abs(value[i-window:i] - target[i])
        idx = np.argsort(distances)[:k]
        out[i] = value[i-window:i][idx].mean()

    return out

def wma(series, length):
    w = np.arange(1, length + 1)
    return series.rolling(length).apply(lambda x: np.dot(x, w) / w.sum(), raw=True)

# =========================
# MAIN LOOP
# =========================
last_state = {}

send_telegram(f"✅ AI Trend Navigator started\n{now_ist()}")

while True:
    try:
        symbols = top_25()
        if not symbols:
            time.sleep(30)
            continue

        for sym in symbols:
            df = klines(sym)
            if df is None or len(df) < 50:
                continue

            hl2 = (df["h"] + df["l"]) / 2
            value_in = hl2.rolling(PRICE_LEN).mean()
            target = df["c"].rolling(TARGET_LEN).mean()

            knnMA = mean_of_k_closest(value_in.values, target.values, NUM_CLOSEST)
            knnMA = pd.Series(knnMA)
            knnMA_ = wma(knnMA, 5)

            a, b, c = knnMA_.iloc[-3], knnMA_.iloc[-2], knnMA_.iloc[-1]
            if np.isnan([a, b, c]).any():
                continue

            switch_up = b < c and b <= a
            switch_dn = b > c and b >= a

            prev = last_state.get(sym)

            if switch_up and prev != "BUY":
                msg = f"🟢 BUY\n{sym}\nknnMA: {round(c,6)}\nTF: 1H\n{now_ist()}"
                send_telegram(msg)
                last_state[sym] = "BUY"

                with open(CSV_FILE, "a") as f:
                    f.write(f"{now_ist()},{sym},BUY,{round(c,6)}\n")

            elif switch_dn and prev != "SELL":
                msg = f"🔴 SELL\n{sym}\nknnMA: {round(c,6)}\nTF: 1H\n{now_ist()}"
                send_telegram(msg)
                last_state[sym] = "SELL"

                with open(CSV_FILE, "a") as f:
                    f.write(f"{now_ist()},{sym},SELL,{round(c,6)}\n")

        time.sleep(SCAN_INTERVAL)

    except Exception as e:
        send_telegram(f"⚠️ BOT ERROR:\n{str(e)}\n{now_ist()}")
        time.sleep(60)
