# ==========================================================
# AI TREND NAVIGATOR — OKX VERSION (1:1 LOGIC MATCH)
# 5M CONFIRMED CANDLE CLOSE + TELEGRAM ALERTS
# ==========================================================

import requests
import pandas as pd
import numpy as np
import time
import os
from datetime import datetime

# =========================
# WAIT FOR CONFIRMED CANDLE
# =========================
time.sleep(35)

# =========================
# CONFIG
# =========================
TIMEFRAME = "5m"
PRICE_LEN = 5
TARGET_LEN = 5
NUM_CLOSEST = 3
SMOOTHING = 5

OKX = "https://www.okx.com"

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# =========================
# TELEGRAM
# =========================
def send_telegram(msg):
    if not BOT_TOKEN or not CHAT_ID:
        return

    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg},
            timeout=10
        )
    except Exception as e:
        print("Telegram error:", e)

# =========================
# SYMBOLS (TOP 25 USDT)
# =========================
def top_25():
    r = requests.get(f"{OKX}/api/v5/market/tickers?instType=SPOT", timeout=10).json()
    data = r.get("data", [])

    usdt = [x for x in data if x["instId"].endswith("-USDT")]
    usdt.sort(key=lambda x: float(x["volCcy24h"]), reverse=True)

    return [x["instId"] for x in usdt[:25]]

# =========================
# KLINES
# =========================
def klines(symbol):
    r = requests.get(
        f"{OKX}/api/v5/market/candles",
        params={
            "instId": symbol,
            "bar": TIMEFRAME,
            "limit": 200
        },
        timeout=10
    ).json()

    data = r.get("data")
    if not data:
        return None

    # OKX candles are newest → oldest
    data.reverse()

    df = pd.DataFrame(data, columns=[
        "ts","o","h","l","c","v","volCcy","volCcyQuote","confirm"
    ])

    df[["h","l","c"]] = df[["h","l","c"]].astype(float)
    return df

# =========================
# INDICATORS (UNCHANGED)
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
# SCAN ONCE (CONFIRMED CANDLE)
# =========================
def scan_once():
    symbols = top_25()
    if not symbols:
        print("No symbols fetched.")
        return

    for sym in symbols:
        df = klines(sym)
        if df is None or len(df) < 50:
            continue

        hl2 = (df["h"] + df["l"]) / 2
        value_in = hl2.rolling(PRICE_LEN).mean()
        target = df["c"].rolling(TARGET_LEN).mean()

        knn = mean_of_k_closest(
            value_in.values,
            target.values,
            NUM_CLOSEST
        )

        knn = wma(pd.Series(knn), SMOOTHING)

        if len(knn) < 3:
            continue

        # CONFIRMED CANDLE ONLY
        a, b, c = knn.iloc[-3], knn.iloc[-2], knn.iloc[-1]
        if np.isnan([a, b, c]).any():
            continue

        switch_up = b < c and b <= a
        switch_dn = b > c and b >= a

        if switch_up or switch_dn:
            side = "BUY" if switch_up else "SELL"
            strength = round(abs(c - b) / abs(b) * 100, 2)

            msg = (
                f"📈 {side} SIGNAL (OKX)\n"
                f"Symbol: {sym}\n"
                f"Timeframe: 5m\n"
                f"Strength: {strength}%\n"
                f"Confirmed candle close\n"
                f"UTC: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
            )

            send_telegram(msg)

# =========================
# START
# =========================
if __name__ == "__main__":
    send_telegram(
        "🚀 Bot Started (OKX)\n"
        "Timeframe: 5m\n"
        "Mode: Confirmed candle close only"
    )
    scan_once()
