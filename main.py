# ==========================================================
#TGRAM ALERT BOT
# GITHUB ACTIONS / CLOUD READY
# IST TIMEZONE
# ==========================================================

import requests
import pandas as pd
import numpy as np
import time
from datetime import datetime
import os
import pytz

# =========================
# TIMEZONE (IST)
# =========================
IST = pytz.timezone("Asia/Kolkata")

def now_ist():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

# =========================
# TELEGRAM CONFIG
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("❌ BOT_TOKEN or CHAT_ID not set in environment variables")

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg}
    requests.post(url, json=payload, timeout=10)

# =========================
# STRATEGY CONFIG
# =========================
TIMEFRAME = "1h"
PRICE_LEN = 5
TARGET_LEN = 5
NUM_CLOSEST = 3
SCAN_INTERVAL = 60  # seconds

CSV_FILE = "ai_trend_navigator_log.csv"
BINANCE = "https://api.binance.com"

# =========================
# CSV INIT
# =========================
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, "w") as f:
        f.write("Time(IST),Symbol,Signal,knnMA\n")

# =========================
# DATA FUNCTIONS
# =========================
def top_25():
    data = requests.get(f"{BINANCE}/api/v3/ticker/24hr", timeout=10).json()
    usdt = [x for x in data if x["symbol"].endswith("USDT")]
    usdt.sort(key=lambda x: float(x["quoteVolume"]), reverse=True)
    return [x["symbol"] for x in usdt[:25]]

def klines(symbol):
    r = requests.get(
        f"{BINANCE}/api/v3/klines",
        params={"symbol": symbol, "interval": TIMEFRAME, "limit": 200},
        timeout=10
    ).json()

    df = pd.DataFrame(r, columns=[
        "ot","o","h","l","c","v",
        "ct","q","n","tbb","tbq","ig"
    ])
    df[["h","l","c"]] = df[["h","l","c"]].astype(float)
    return df

# =========================
# INDICATOR CORE
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
    weights = np.arange(1, length + 1)
    return series.rolling(length).apply(
        lambda x: np.dot(x, weights) / weights.sum(), raw=True
    )

# =========================
# STARTUP + HEARTBEAT
# =========================
send_telegram("✅ AI Trend Navigator bot started (IST, confirmed candles)")
send_telegram("❤️ Heartbeat: bot is alive and scanning markets")

# =========================
# MAIN LOOP (GITHUB ACTIONS SAFE)
# =========================
START_TIME = time.time()
MAX_RUNTIME = 9 * 60  # 9 minutes per GitHub Actions run

last_state = {}

while time.time() - START_TIME < MAX_RUNTIME:
    try:
        for sym in top_25():
            df = klines(sym)

            # 🔒 CONFIRMED CANDLE ONLY (barstate.isconfirmed)
            df = df.iloc[:-1]

            hl2 = (df["h"] + df["l"]) / 2
            value_in = hl2.rolling(PRICE_LEN).mean()
            target = df["c"].rolling(TARGET_LEN).mean()

            knnMA = mean_of_k_closest(value_in.values, target.values, NUM_CLOSEST)
            knnMA = pd.Series(knnMA, index=df.index)
            knnMA_ = wma(knnMA, 5)

            a = knnMA_.iloc[-3]
            b = knnMA_.iloc[-2]
            c = knnMA_.iloc[-1]

            if np.isnan([a, b, c]).any():
                continue

            # 🎯 COLOR SWITCH LOGIC (EXACT PINE PORT)
            switch_up = b < c and b <= a
            switch_dn = b > c and b >= a

            prev = last_state.get(sym)
            timestamp = now_ist()

            if switch_up and prev != "GREEN":
                msg = (
                    f"🟢 BUY SIGNAL\n"
                    f"{sym}\n"
                    f"KNN: {round(c,6)}\n"
                    f"TF: 1H\n"
                    f"Time: {timestamp} IST"
                )
                send_telegram(msg)
                last_state[sym] = "GREEN"

                with open(CSV_FILE, "a") as f:
                    f.write(f"{timestamp},{sym},BUY,{c}\n")

            elif switch_dn and prev != "RED":
                msg = (
                    f"🔴 SELL SIGNAL\n"
                    f"{sym}\n"
                    f"KNN: {round(c,6)}\n"
                    f"TF: 1H\n"
                    f"Time: {timestamp} IST"
                )
                send_telegram(msg)
                last_state[sym] = "RED"

                with open(CSV_FILE, "a") as f:
                    f.write(f"{timestamp},{sym},SELL,{c}\n")

        time.sleep(SCAN_INTERVAL)

    except Exception as e:
        send_telegram(
            "🚨 BOT CRASH DETECTED\n"
            f"Error: {str(e)}\n"
            f"Time: {now_ist()} IST\n"
            "🔁 GitHub Actions will auto-restart"
        )
        raise  # force GitHub Actions restart
