# =========================================================
# V12 CORE STABLE - CLEAN FROM V10 (GITHUB READY)
# =========================================================

import os
import time
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta

# ===== CONFIG =====
SYSTEM_VERSION = "V12_CORE_STABLE"
DATA_DIR = "data"
OUTPUT_DIR = "output"

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ===== TIME =====
def now_vietnam():
    return datetime.utcnow() + timedelta(hours=7)

# ===== SAFE =====
def safe_float(x, default=0):
    try:
        if pd.isna(x):
            return default
        return float(x)
    except:
        return default

def safe_read_csv(path):
    if not os.path.exists(path):
        return pd.DataFrame()
    for enc in ["utf-8-sig", "utf-8", "latin1"]:
        try:
            return pd.read_csv(path, encoding=enc)
        except:
            continue
    return pd.DataFrame()

# ===== LOAD DATA =====
def load_stock(path):
    df = safe_read_csv(path)
    if df.empty:
        return df

    df.columns = [c.lower() for c in df.columns]

    if "time" in df.columns:
        df = df.rename(columns={"time": "date"})

    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["close"]).sort_values("date")
    return df

# ===== INDICATOR =====
def calc_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def add_indicators(df):
    df["MA5"] = df["close"].rolling(5).mean()
    df["MA20"] = df["close"].rolling(20).mean()
    df["RSI"] = calc_rsi(df["close"])

    df["Ret5"] = df["close"].pct_change(5) * 100
    df["Ret10"] = df["close"].pct_change(10) * 100

    df["VolMA20"] = df["volume"].rolling(20).mean()
    df["VolRatio"] = df["volume"] / (df["VolMA20"] + 1e-9)

    df["ATR"] = (df["high"] - df["low"]).rolling(14).mean()
    df["ATR%"] = df["ATR"] / df["close"] * 100

    df["DistMA20"] = (df["close"] / df["MA20"] - 1) * 100

    return df

# ===== SCORE =====
def score_momentum(r):
    s = 0
    if r["MA5"] > r["MA20"]: s += 20
    if 55 <= r["RSI"] <= 75: s += 20
    if r["Ret5"] > 2: s += 15
    if r["Ret10"] > 3: s += 15
    if r["VolRatio"] > 1.2: s += 15
    if r["ATR%"] <= 8: s += 10
    if 0 <= r["DistMA20"] <= 12: s += 5
    return s

def score_bottom(r):
    s = 0
    if 30 <= r["RSI"] <= 48: s += 25
    if r["Ret5"] > 0: s += 10
    if r["VolRatio"] >= 0.8: s += 15
    if r["ATR%"] <= 9: s += 15
    if r["DistMA20"] <= 3: s += 10
    return s

# ===== ACTION =====
def classify(r):
    m = r["Momentum"]
    b = r["Bottom"]
    rsi = r["RSI"]
    atr = r["ATR%"]

    if rsi > 85: return "SKIP"
    if atr > 10: return "SKIP"

    score = max(m, b)

    if score >= 80: return "BUY"
    if score >= 65: return "WAIT"
    if score >= 50: return "WATCH"
    return "SKIP"

# ===== ANALYZE =====
def analyze(symbol, path):
    df = load_stock(path)
    if len(df) < 40:
        return None

    df = add_indicators(df)
    r = df.iloc[-1]

    row = {
        "Code": symbol,
        "Close": round(r["close"], 2),
        "RSI": round(r["RSI"], 1),
        "Momentum": score_momentum(r),
        "Bottom": score_bottom(r),
    }

    row["Score"] = max(row["Momentum"], row["Bottom"])
    row["Action"] = classify({
        **row,
        "RSI": r["RSI"],
        "ATR%": r["ATR%"]
    })

    return row

# ===== RUN =====
def run():
    results = []

    files = [f for f in os.listdir(DATA_DIR) if f.endswith(".csv")]

    for f in files:
        symbol = f.replace(".csv", "")
        path = os.path.join(DATA_DIR, f)

        try:
            r = analyze(symbol, path)
            if r:
                results.append(r)
                print("OK", symbol)
        except Exception as e:
            print("ERR", symbol, e)

    df = pd.DataFrame(results)

    if not df.empty:
        df = df.sort_values(["Action", "Score"], ascending=[True, False])
        df.to_csv(f"{OUTPUT_DIR}/result.csv", index=False)

    return df

# ===== TELEGRAM =====
def send_telegram(msg):
    token = os.getenv("TELEGRAM_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")

    if not token:
        return

    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat, "text": msg}
    )

# ===== MAIN =====
if __name__ == "__main__":
    df = run()

    if df is not None and not df.empty:
        msg = f"V12 CORE\nBUY: {len(df[df.Action=='BUY'])}\nWAIT: {len(df[df.Action=='WAIT'])}"
        send_telegram(msg)

    print("DONE")