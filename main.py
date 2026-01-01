# ==========================================================
# AI TREND NAVIGATOR — DUAL MODE
# Desktop UI + GitHub Headless Safe
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
    from plyer import notification

# =========================
# TELEGRAM (HEADLESS)
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
BASE_SMOOTHING = 50
PRICE_LEN = 5
TARGET_LEN = 5
NUM_CLOSEST = 3
SCAN_INTERVAL = 60
BINANCE = "https://api.binance.com"

TF_MIN = int(TIMEFRAME.replace("m","")) if "m" in TIMEFRAME else 60
SMOOTHING = int(BASE_SMOOTHING * (BASE_TF_MIN / TF_MIN))

# =========================
# UI (DESKTOP ONLY)
# =========================
if not HEADLESS:
    root = tk.Tk()
    root.title("AI Trend Navigator — Dual Alerts")
    root.geometry("950x450")

    cols = ("Time","Symbol","Type","Signal","Strength","knnMA")
    tree = ttk.Treeview(root, columns=cols, show="headings")
    for c in cols:
        tree.heading(c, text=c)
        tree.column(c, width=150)
    tree.pack(fill=tk.BOTH, expand=True)

    status = tk.Label(root, text="Running", fg="green")
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
# SIGNAL STRENGTH
# =========================
def strength_score(a,b,c):
    raw = abs(b-a) + abs(c-b) + abs(c-a)
    return min(100, int(raw * 1000))

# =========================
# ALERT HANDLER
# =========================
def emit(sym, typ, signal, strength, value):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"{typ} {signal} {sym}\nStrength: {strength}\nknnMA: {round(value,6)}"

    if HEADLESS:
        send_telegram(msg)
    else:
        tree.insert("", 0, values=(ts, sym, typ, signal, strength, round(value,6)))
        notification.notify(title="AI Trend Navigator", message=msg, timeout=5)

# =========================
# SCANNER
# =========================
last_early = {}
last_conf = {}

def scan():
    while True:
        try:
            for sym in top_25():
                df = klines(sym)

                hl2 = (df["h"] + df["l"]) / 2
                value = hl2.rolling(PRICE_LEN).mean()
                target = df["c"].rolling(TARGET_LEN).mean()

                knn = mean_of_k_closest(value.values, target.values, NUM_CLOSEST)
                knn = pd.Series(knn)
                knnMA = wma(knn, SMOOTHING)

                if len(knnMA) < 4:
                    continue

                # EARLY (LIVE)
                a,b,c = knnMA.iloc[-3], knnMA.iloc[-2], knnMA.iloc[-1]
                if not np.isnan([a,b,c]).any():
                    up = b < c and b <= a
                    dn = b > c and b >= a
                    s = strength_score(a,b,c)

                    if up and last_early.get(sym) != "BUY":
                        emit(sym,"EARLY","BUY",s,c)
                        last_early[sym] = "BUY"

                    elif dn and last_early.get(sym) != "SELL":
                        emit(sym,"EARLY","SELL",s,c)
                        last_early[sym] = "SELL"

                # CONFIRMED
                a,b,c = knnMA.iloc[-4], knnMA.iloc[-3], knnMA.iloc[-2]
                if not np.isnan([a,b,c]).any():
                    up = b < c and b <= a
                    dn = b > c and b >= a
                    s = strength_score(a,b,c)

                    if up and last_conf.get(sym) != "BUY":
                        emit(sym,"CONFIRMED","BUY",s,c)
                        last_conf[sym] = "BUY"

                    elif dn and last_conf.get(sym) != "SELL":
                        emit(sym,"CONFIRMED","SELL",s,c)
                        last_conf[sym] = "SELL"

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
