# ==========================================================
# AI TREND NAVIGATOR — OKX CONTINUOUS BOT
# ATR-BASED TP / SL
# CONFIRMED 5M CANDLE CLOSE ONLY
# ==========================================================

import requests
import pandas as pd
import numpy as np
import time
import os
from datetime import datetime, timedelta, timezone

# =========================
# CONFIG
# =========================
TIMEFRAME = "5m"

PRICE_LEN = 5
TARGET_LEN = 5
NUM_CLOSEST = 3
SMOOTHING = 5

ATR_LEN = 14
ATR_SL_MULT = 1.0
ATR_TP_MULT = 2.0

OKX = "https://www.okx.com"

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

IST = timezone(timedelta(hours=5, minutes=30))

# =========================
# TELEGRAM
# =========================
def send_telegram(msg):
    if not BOT_TOKEN or not CHAT_ID:
        return

    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg},
        timeout=10
    )

# =========================
# WAIT UNTIL NEXT 5M CLOSE
# =========================
def wait_for_next_5m():
    now = time.time()
    next_close = ((now // 300) + 1) * 300
    time.sleep(max(0, next_close - now + 35))

# =========================
# SYMBOLS
# =========================
def top_25():
    r = requests.get(
        f"{OKX}/api/v5/market/tickers?instType=SPOT",
        timeout=10
    ).json()

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
        params={"instId": symbol, "bar": TIMEFRAME, "limit": 200},
        timeout=10
    ).json()

    data = r.get("data")
    if not data:
        return None

    data.reverse()

    df = pd.DataFrame(
        data,
        columns=["ts","o","h","l","c","v","volCcy","volCcyQuote","confirm"]
    )

    df[["h","l","c"]] = df[["h","l","c"]].astype(float)
    return df

# =========================
# INDICATORS
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

def atr(df, length):
    high = df["h"]
    low = df["l"]
    close = df["c"].shift(1)

    tr = pd.concat([
        high - low,
        (high - close).abs(),
        (low - close).abs()
    ], axis=1).max(axis=1)

    return tr.rolling(length).mean()

# =========================
# STATE (ANTI-DUPLICATE)
# =========================
last_state = {}

# =========================
# SCAN
# =========================
def scan():
    symbols = top_25()
    if not symbols:
        return

    for sym in symbols:
        df = klines(sym)
        if df is None or len(df) < 50:
            continue

        hl2 = (df["h"] + df["l"]) / 2
        value_in = hl2.rolling(PRICE_LEN).mean()
        target = df["c"].rolling(TARGET_LEN).mean()

        knn = mean_of_k_closest(value_in.values, target.values, NUM_CLOSEST)
        knn = wma(pd.Series(knn), SMOOTHING)

        if len(knn) < 3:
            continue

        a, b, c = knn.iloc[-3], knn.iloc[-2], knn.iloc[-1]
        if np.isnan([a, b, c]).any():
            continue

        buy = b < c and b <= a
        sell = b > c and b >= a

        state = "GREEN" if buy else "RED" if sell else None
        if not state or last_state.get(sym) == state:
            continue

        last_state[sym] = state

        entry = round(df["c"].iloc[-2], 6)

        atr_val = atr(df, ATR_LEN).iloc[-2]
        if np.isnan(atr_val):
            continue

        if state == "GREEN":
            side = "🟢BUY"
            sl = round(entry - ATR_SL_MULT * atr_val, 6)
            tp = round(entry + ATR_TP_MULT * atr_val, 6)
        else:
            side = "🔴SELL"
            sl = round(entry + ATR_SL_MULT * atr_val, 6)
            tp = round(entry - ATR_TP_MULT * atr_val, 6)

        ist_time = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

        msg = (
            f"{side} SIGNAL (OKX)\n"
            f"Symbol: {sym}\n"
            f"Entry: {entry}\n"
            f"ATR({ATR_LEN}): {round(atr_val,6)}\n"
            f"TP: {tp}\n"
            f"SL: {sl}\n"
            f"IST: {ist_time}"
        )

        send_telegram(msg)

# =========================
# MAIN LOOP
# =========================
if __name__ == "__main__":
    send_telegram(
        "🚀 Bot Started (OKX)\n"
        "Timeframe: 5m\n"
        "TP/SL: ATR-based\n"
        "Mode: Confirmed candle close only"
    )

    while True:
        wait_for_next_5m()
        scan()
