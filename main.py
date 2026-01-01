# ==========================================================
# AI TREND NAVIGATOR — 5M CONFIRMED COLOR CHANGE ALERTS
# FULL DEBUG TELEGRAM VERSION (NO SILENT FAILURES)
# ==========================================================

import requests
import pandas as pd
import numpy as np
import time
from datetime import datetime
import os
import signal
import sys

# =========================
# CONFIG
# =========================
TIMEFRAME = "5m"
PRICE_LEN = 5
TARGET_LEN = 5
NUM_CLOSEST = 3
SCAN_INTERVAL = 60
HEARTBEAT_MIN = 30

BINANCE = "https://api.binance.com"

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CSV_FILE = "signals.csv"

print("BOT_TOKEN:", "SET" if BOT_TOKEN else "MISSING")
print("CHAT_ID:", "SET" if CHAT_ID else "MISSING")

# =========================
# TELEGRAM (LOUD MODE)
# =========================
def send_telegram(msg):
    if not BOT_TOKEN or not CHAT_ID:
        print("⚠️ Telegram not configured")
        return

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": CHAT_ID,
                "text": msg
            },
            timeout=10
        )

        print("📨 Telegram status:", r.status_code)

        if r.status_code != 200:
            print("❌ Telegram response:", r.text)

    except Exception as e:
        print("❌ Telegram exception:", e)

# =========================
# STARTUP MESSAGE
# =========================
send_telegram(
    "🚀 Bot Started\n"
    "Timeframe: 5m\n"
    "Mode: Confirmed candle close only"
)

# =========================
# SHUTDOWN HANDLER
# =========================
def shutdown_handler(sig, frame):
    send_telegram("🛑 Bot Stopped / Restarted")
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)

# =========================
# CSV INIT
# =========================
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, "w") as f:
        f.write("Time,Symbol,Signal,knnMA,Strength\n")

# =========================
# SYMBOLS
# =========================
def top_25():
    r = requests.get(f"{BINANCE}/api/v3/ticker/24hr", timeout=10)
    data = r.json()
    usdt = [x for x in data if x["symbol"].endswith("USDT")]
    usdt.sort(key=lambda x: float(x["quoteVolume"]), reverse=True)
    return [x["symbol"] for x in usdt[:25]]

# =========================
# KLINES
# =========================
def klines(symbol):
    r = requests.get(
        f"{BINANCE}/api/v3/klines",
        params={
            "symbol": symbol,
            "interval": TIMEFRAME,
            "limit": 200
        },
        timeout=10
    )

    data = r.json()

    df = pd.DataFrame(data, columns=[
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
# STRENGTH SCORE
# =========================
def strength_score(a, b, c):
    slope_now = abs(c - b)
    slope_prev = abs(b - a)

    if slope_prev == 0:
        return 0.0

    return round(min(100, (slope_now / slope_prev) * 50), 1)

# =========================
# SIGNAL
# =========================
def send_signal(symbol, side, value, score):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    line = f"{ts},{symbol},{side},{round(value,6)},{score}"
    print("SIGNAL:", line)

    with open(CSV_FILE, "a") as f:
        f.write(line + "\n")

    msg = (
        f"{side} SIGNAL\n"
        f"Symbol: {symbol}\n"
        f"Price: {round(value,6)}\n"
        f"Strength: {score}/100\n"
        f"TF: 5m closed\n"
        f"Time: {ts} UTC"
    )

    print("➡️ Sending Telegram message...")
    send_telegram(msg)

    # Telegram rate-limit safety
    time.sleep(1.5)

# =========================
# SCANNER
# =========================
last_state = {}
last_heartbeat = time.time()

def scan():
    global last_heartbeat

    print("Bot started (5M — signal at candle CLOSE)")

    while True:
        try:
            for sym in top_25():
                df = klines(sym)

                hl2 = (df["h"] + df["l"]) / 2
                value_in = hl2.rolling(PRICE_LEN).mean()
                target = df["c"].rolling(TARGET_LEN).mean()

                knn = mean_of_k_closest(
                    value_in.values,
                    target.values,
                    NUM_CLOSEST
                )

                knnMA = wma(pd.Series(knn), 5)

                if len(knnMA) < 5:
                    continue

                # EXACT arrow candle timing
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

            # HEARTBEAT
            if time.time() - last_heartbeat > HEARTBEAT_MIN * 60:
                send_telegram("❤️ Bot alive (heartbeat)")
                last_heartbeat = time.time()

        except Exception as e:
            print("⚠️ BOT ERROR:", e)

        time.sleep(SCAN_INTERVAL)

# =========================
# START
# =========================
scan()
