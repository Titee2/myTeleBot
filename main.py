# ==========================================================
# AI TREND NAVIGATOR — TELEGRAM ALERT BOT
# GITHUB ACTIONS SAFE • 5 MINUTE • NO REPAINT
# ==========================================================

import requests
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import os
import sys

# =========================
# TELEGRAM CONFIG
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    print("❌ BOT_TOKEN or CHAT_ID missing")
    sys.exit(1)

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(
            url,
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

CSV_FILE = "ai_trend_navigator_5m_log.csv"
BINANCE = "https://api.binance.com"

# =========================
# CSV INIT
# =========================
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, "w") as f:
        f.write("Time,Symbol,Signal,knnMA\n")

# =========================
# SAFE BINANCE FETCH
# =========================
def top_25():
    try:
        r = requests.get(
            f"{BINANCE}/api/v3/ticker/24hr",
            timeout=10
        )

        if r.status_code != 200:
            return []

        data = r.json()

        # 🚨 ABSOLUTE GUARD
        if not isinstance(data, list):
            return []

        usdt = []
        for item in data:
            if not isinstance(item, dict):
                continue

            symbol = item.get("symbol")
            volume = item.get("quoteVolume")

            if not symbol or not volume:
                continue

            if symbol.endswith("USDT"):
                usdt.append((symbol, float(volume)))

        usdt.sort(key=lambda x: x[1], reverse=True)
        return [x[0] for x in usdt[:25]]

    except:
        return []

def klines(symbol):
    try:
        r = requests.get(
            f"{BINANCE}/api/v3/klines",
            params={
                "symbol": symbol,
                "interval": TIMEFRAME,
                "limit": 200
            },
            timeout=10
        )

        if r.status_code != 200:
            return None

        data = r.json()

        # 🚨 ABSOLUTE GUARD
        if not isinstance(data, list) or len(data) == 0:
            return None

        df = pd.DataFrame(
            data,
            columns=[
                "ot","o","h","l","c","v",
                "ct","q","n","tbb","tbq","ig"
            ]
        )

        df[["h","l","c"]] = df[["h","l","c"]].astype(float)
        return df

    except:
        return None

# =========================
# INDICATOR CORE (UNCHANGED)
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
        lambda x: np.dot(x, weights) / weights.sum(),
        raw=True
    )

# =========================
# MAIN BOT LOOP
# =========================
def run_bot():
    last_state = {}
    last_heartbeat_block = None

    send_telegram(
        "✅ AI Trend Navigator STARTED\n"
        "TF: 5M • CONFIRMED CANDLES\n"
        f"{(datetime.utcnow()+timedelta(hours=5,minutes=30)).strftime('%Y-%m-%d %H:%M:%S')} IST"
    )

    while True:
        symbols = top_25()

        if not symbols:
            time.sleep(15)
            continue

        for sym in symbols:
            df = klines(sym)

            if df is None or len(df) < 60:
                continue

            # CONFIRMED CANDLE ONLY
            df = df.iloc[:-1]

            hl2 = (df["h"] + df["l"]) / 2
            value_in = hl2.rolling(PRICE_LEN).mean()
            target = df["c"].rolling(TARGET_LEN).mean()

            knnMA = mean_of_k_closest(
                value_in.values,
                target.values,
                NUM_CLOSEST
            )

            knnMA = pd.Series(knnMA, index=df.index)
            knnMA_ = wma(knnMA, 5)

            a = knnMA_.iloc[-3]
            b = knnMA_.iloc[-2]
            c = knnMA_.iloc[-1]

            if np.isnan([a, b, c]).any():
                continue

            switch_up = b < c and b <= a
            switch_dn = b > c and b >= a

            prev = last_state.get(sym)

            ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
            ts = ist.strftime("%Y-%m-%d %H:%M:%S")

            if switch_up and prev != "GREEN":
                send_telegram(
                    f"🟢 BUY SIGNAL\n"
                    f"{sym}\n"
                    f"ENTRY: {round(c,6)}\n"
                    f"TF: 5M\n"
                    f"{ts} IST"
                )
                last_state[sym] = "GREEN"
                with open(CSV_FILE, "a") as f:
                    f.write(f"{ts},{sym},BUY,{c}\n")

            elif switch_dn and prev != "RED":
                send_telegram(
                    f"🔴 SELL SIGNAL\n"
                    f"{sym}\n"
                    f"ENTRY: {round(c,6)}\n"
                    f"TF: 5M\n"
                    f"{ts} IST"
                )
                last_state[sym] = "RED"
                with open(CSV_FILE, "a") as f:
                    f.write(f"{ts},{sym},SELL,{c}\n")

        # ❤️ HEARTBEAT — once per 5m block
        block = ist.minute // 5
        if block != last_heartbeat_block:
            send_telegram(f"💓 Bot alive • scanning 5M\n{ts} IST")
            last_heartbeat_block = block

        time.sleep(SCAN_INTERVAL)

# =========================
# AUTO-RESTART (GITHUB ACTIONS SAFE)
# =========================
while True:
    try:
        run_bot()
    except Exception as e:
        send_telegram(f"🔥 BOT CRASHED — RESTARTING\n{e}")
        time.sleep(10)
