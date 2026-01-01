# ==========================================================
# AI TREND NAVIGATOR — CONFIRMED COLOR CHANGE TEST
# 5M Candle Close + Line Color Change ONLY
# ==========================================================

import requests
import pandas as pd
import numpy as np
import time
import threading
import os
from datetime import datetime

# =========================
# ENV DETECTION
# =========================
HEADLESS = os.getenv("GITHUB_ACTIONS") == "true"

if not HEADLESS:
    import tkinter as tk
    from tkinter import ttk

# =========================
# TELEGRAM (HEADLESS MODE)
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_telegram(msg):
    if not BOT_TOKEN or not CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg},
            timeout=5
        )
    except:
        pass

# =========================
# CONFIG
# =========================
TIMEFRAME = "5m"
BASE_TF_MIN = 60
BASE_SMOOTHING = 50     # original 1H tuning
PRICE_LEN = 5
TARGET_LEN = 5
NUM_CLOSEST = 3
SCAN_INTERVAL = 60
BINANCE = "https://api.binance.com"

# auto-scale smoothing
TF_MIN = int(TIMEFRAME.replace("m",""))
SMOOTHING = int(BASE_SMOOTHING * (BASE_TF_MIN / TF_MIN))

# =========================
# UI (DESKTOP ONLY)
# =========================
if not HEADLESS:
    root = tk.Tk()
    root.title("Confirmed Color Change — 5M")
    root.geometry("850x420")

    cols = ("Time", "Symbol", "Color")
    tree = ttk.Treeview(root, columns=cols, show="headings")
    for c in cols:
        tree.heading(c, text=c)
        tree.column(c, width=260)
    tree.pack(fill=tk.BOTH, expand=True)

    status = tk.Label(root, text="Running (confirmed candles only)", fg="green")
    status.pack(pady=4)

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
        "limit": 300
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
    window = max(k, 30)
    out = np.full(len(value), np.nan)
    for i in range(window, len(value)):
        dist = np.abs(value[i-window:i] - target[i])
        idx = np.argsort(dist)[:k]
        out[i] = value[i-window:i][idx].mean()
    return out

def wma(series, length):
    w = np.arange(1, length + 1)
    return series.rolling(length).apply(
        lambda x: np.dot(x, w) / w.sum(),
        raw=True
    )

# =========================
# SCANNER — CONFIRMED ONLY
# =========================
last_color = {}

def scan():
    while True:
        try:
            for sym in top_25():
                df = klines(sym)

                # === PRICE / TARGET ===
                hl2 = (df["h"] + df["l"]) / 2
                value = hl2.rolling(PRICE_LEN).mean()
                target = df["c"].rolling(TARGET_LEN).mean()

                knn = mean_of_k_closest(value.values, target.values, NUM_CLOSEST)
                knn = pd.Series(knn)
                knnMA = wma(knn, SMOOTHING)

                # need enough CLOSED candles
                if len(knnMA) < 5:
                    continue

                # --------------------------------------
                # USE ONLY CLOSED CANDLES
                # -1 = live (ignored)
                # -2 = last closed
                # -3 = previous closed
                # -4 = closed before that
                # --------------------------------------
                slope_prev = knnMA.iloc[-3] - knnMA.iloc[-4]
                slope_curr = knnMA.iloc[-2] - knnMA.iloc[-3]

                if slope_prev == 0 or slope_curr == 0:
                    continue

                prev_color = "GREEN" if slope_prev > 0 else "RED"
                curr_color = "GREEN" if slope_curr > 0 else "RED"

                # SIGNAL ONLY IF COLOR CHANGED AFTER CLOSE
                if prev_color != curr_color:
                    last = last_color.get(sym)
                    if last != curr_color:
                        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        msg = f"{curr_color} COLOR CHANGE (CONFIRMED)\n{sym}\nTF: 5M\n{ts}"

                        if HEADLESS:
                            send_telegram(msg)
                        else:
                            tree.insert("", 0, values=(ts, sym, curr_color))

                        last_color[sym] = curr_color

            if not HEADLESS:
                status.config(text=f"Last scan: {datetime.now().strftime('%H:%M:%S')}")

        except Exception as e:
            if not HEADLESS:
                status.config(text=str(e), fg="red")

        time.sleep(SCAN_INTERVAL)

# =========================
# START
# =========================
threading.Thread(target=scan, daemon=True).start()

if not HEADLESS:
    root.mainloop()
else:
    while True:
        time.sleep(3600)
