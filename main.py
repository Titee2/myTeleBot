# ==========================================================
# AI TREND NAVIGATOR — 5M CONFIRMED COLOR CHANGE ALERTS
# Telegram + Signal Strength
# ==========================================================

import requests
import pandas as pd
import numpy as np
import time
from datetime import datetime
import os

# =========================
# CONFIG
# =========================
TIMEFRAME = "5m"
PRICE_LEN = 5
TARGET_LEN = 5
NUM_CLOSEST = 3
SCAN_INTERVAL = 60
BINANCE = "https://api.binance.com"

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CSV_FILE = "signals.csv"

# =========================
# CSV INIT
# =========================
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, "w") as f:
        f.write("Time,Symbol,Signal,knnMA,Strength\n")

# =========================
# TELEGRAM
# =========================
def send_telegram(msg):
    if not BOT_TOKEN or not CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown"
    }, timeout=10)

# =========================
# SYMBOLS
# =========================
def top_25():
    data = requests.get(f"{BINANCE}/api/v3/ticker/24hr", timeout=10).json()
    usdt = [x for x in data if x["symbol"].endswith("USDT")]
    usdt.sort(key=lambda x: float(x["quoteVolume"]), reverse=True)
    return [x["symbol"] for x in usdt[:25]]

# =========================
# KLINES
# =========================
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
        d = np.abs(value[i-window:i] - target[i])
        idx = np.argsort(d)[:k]
        out[i] = value[i-window:i][idx].mean()

    return out

def wma(series, length):
    w = np.arange(1, length + 1)
    return series.rolling(length).apply(
        lambda x: np.dot(x, w) / w.sum(),
        raw=True
    )

# =========================
# SIGNAL STRENGTH
# =========================
def strength_score(a, b, c):
    slope_now = abs(c - b)
    slope_prev = abs(b - a)

    if slope_prev == 0:
        return 0

    accel = slope_now / slope_prev
    score = min(100, accel * 50)
    return round(score, 1)

# =========================
# ALERT
# =========================
def send_signal(symbol, side, value, score):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    line = f"{ts},{symbol},{side},{round(value,6)},{score}"
    print("SIGNAL:", line)

    with open(CSV_FILE, "a") as f:
        f.write(line + "\n")

    emoji = "🟢" if side == "BUY" else "🔴"

    msg = (
        f"{emoji} *{side} SIGNAL*\n"
        f"*Symbol:* `{symbol}`\n"
        f"*Timeframe:* 5m (confirmed)\n"
        f"*knnMA:* `{round(value,6)}`\n"
        f"*Strength:* `{score}/100`"
    )

    send_telegram(msg)

# =========================
# SCANNER
# =========================
last_state = {}

def scan():
    print("Bot started (5M — confirmed candle close)")

    while True:
        try:
            for sym in top_25():
                df = klines(sym)

                hl2 = (df["h"] + df["l"]) / 2
                value_in = hl2.rolling(PRICE_LEN).mean()
                target = df["c"].rolling(TARGET_LEN).mean()

                knn = mean_of_k_closest(value_in.values, target.values, NUM_CLOSEST)
                knnMA = wma(pd.Series(knn), 5)

                if len(knnMA) < 5:
                    continue

                # ✅ EXACT arrow timing
                a = knnMA.iloc[-3]
                b = knnMA.iloc[-2]
                c = knnMA.iloc[-1]

                if np.isnan([a, b, c]).any():
                    continue

                switch_up = b < c and b <= a
                switch_dn = b > c and b >= a

                score = strength_score(a, b, c)
                prev = last_state.get(sym)

                if switch_up and prev != "GREEN":
                    send_signal(sym, "BUY", c, score)
                    last_state[sym] = "GREEN"

                elif switch_dn and prev != "RED":
                    send_signal(sym, "SELL", c, score)
                    last_state[sym] = "RED"

        except Exception as e:
            print("⚠️ BOT ERROR:", e)

        time.sleep(SCAN_INTERVAL)

# =========================
# START
# =========================
if __name__ == "__main__":
    scan()
