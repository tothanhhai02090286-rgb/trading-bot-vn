import os
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
    except Exception:
        return default


def safe_read_csv(path):
    if not os.path.exists(path):
        return pd.DataFrame()
    for enc in ["utf-8-sig", "utf-8", "latin1"]:
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            continue
    return pd.DataFrame()

# ===== LOAD DATA =====
def load_stock(path):
    df = safe_read_csv(path)
    if df.empty:
        return df

    df.columns = [str(c).strip().lower() for c in df.columns]

    if "time" in df.columns:
        df = df.rename(columns={"time": "date"})
    if "tradingdate" in df.columns:
        df = df.rename(columns={"tradingdate": "date"})

    required = ["date", "open", "high", "low", "close", "volume"]
    for col in required:
        if col not in df.columns:
            print(f"MISSING COLUMN {col} in {path}")
            return pd.DataFrame()

    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["date", "close"]).sort_values("date").drop_duplicates("date")
    return df

# ===== INDICATOR =====
def calc_rsi(close, period=14):
    close = pd.Series(close).astype(float)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))


def add_indicators(df):
    df = df.copy()

    df["MA5"] = df["close"].rolling(5).mean()
    df["MA20"] = df["close"].rolling(20).mean()
    df["RSI"] = calc_rsi(df["close"])

    df["Ret5"] = df["close"].pct_change(5) * 100
    df["Ret10"] = df["close"].pct_change(10) * 100

    df["VolMA20"] = df["volume"].rolling(20).mean()
    df["VolRatio"] = df["volume"] / (df["VolMA20"] + 1e-9)

    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - df["close"].shift(1)).abs()
    tr3 = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(14).mean()
    df["ATR%"] = df["ATR"] / df["close"] * 100

    df["DistMA20"] = (df["close"] / df["MA20"] - 1) * 100

    return df

# ===== SCORE =====
def score_momentum(r):
    s = 0
    if safe_float(r.get("MA5")) > safe_float(r.get("MA20")):
        s += 20
    if 55 <= safe_float(r.get("RSI")) <= 75:
        s += 20
    if safe_float(r.get("Ret5")) > 2:
        s += 15
    if safe_float(r.get("Ret10")) > 3:
        s += 15
    if safe_float(r.get("VolRatio")) > 1.2:
        s += 15
    if safe_float(r.get("ATR%"), 999) <= 8:
        s += 10
    if 0 <= safe_float(r.get("DistMA20")) <= 12:
        s += 5
    return min(s, 100)


def score_bottom(r):
    s = 0
    if 30 <= safe_float(r.get("RSI")) <= 48:
        s += 25
    if safe_float(r.get("Ret5")) > 0:
        s += 10
    if safe_float(r.get("VolRatio")) >= 0.8:
        s += 15
    if safe_float(r.get("ATR%"), 999) <= 9:
        s += 15
    if safe_float(r.get("DistMA20")) <= 3:
        s += 10
    return min(s, 100)

# ===== ACTION =====
def classify_action(momentum_score, bottom_score, rsi, atr_pct):
    if rsi > 85:
        return "SKIP"
    if atr_pct > 10:
        return "SKIP"

    score = max(momentum_score, bottom_score)

    if score >= 80:
        return "BUY"
    if score >= 65:
        return "WAIT"
    if score >= 50:
        return "WATCH"
    return "SKIP"


def explain_signal(row, momentum_score, bottom_score, action):
    rsi = safe_float(row.get("RSI"))
    ret5 = safe_float(row.get("Ret5"))
    vol = safe_float(row.get("VolRatio"))
    atr = safe_float(row.get("ATR%"))

    if action == "BUY":
        if momentum_score >= bottom_score:
            return f"Momentum tot: RSI {rsi:.1f}, Ret5 {ret5:.1f}%, Volume {vol:.2f}x."
        return f"Bottom hoi phuc: RSI {rsi:.1f}, Ret5 {ret5:.1f}%, Volume {vol:.2f}x."
    if action == "WAIT":
        return f"Tin hieu kha nhung can xac nhan them: RSI {rsi:.1f}, ATR {atr:.1f}%."
    if action == "WATCH":
        return f"Chi nen theo doi: RSI {rsi:.1f}, Volume {vol:.2f}x."
    return "Bo qua do tin hieu yeu hoac rui ro cao."

# ===== ANALYZE =====
def analyze(symbol, path):
    df = load_stock(path)
    if df.empty or len(df) < 40:
        return None

    df = add_indicators(df)
    r = df.iloc[-1]

    close = safe_float(r.get("close"), np.nan)
    rsi = safe_float(r.get("RSI"), np.nan)
    atr = safe_float(r.get("ATR%"), 999)

    if pd.isna(close) or pd.isna(rsi):
        return None

    momentum = score_momentum(r)
    bottom = score_bottom(r)
    score = max(momentum, bottom)
    action = classify_action(momentum, bottom, rsi, atr)
    strategy = "MOMENTUM" if momentum >= bottom else "BOTTOM"

    return {
        "Ngay": str(r.get("date"))[:10] if "date" in r else now_vietnam().strftime("%Y-%m-%d"),
        "Ma": symbol,
        "Close": round(close, 2),
        "RSI": round(rsi, 2),
        "MA5": round(safe_float(r.get("MA5")), 2),
        "MA20": round(safe_float(r.get("MA20")), 2),
        "Ret5 %": round(safe_float(r.get("Ret5")), 2),
        "Ret10 %": round(safe_float(r.get("Ret10")), 2),
        "Volume Ratio": round(safe_float(r.get("VolRatio")), 2),
        "ATR %": round(atr, 2),
        "Dist MA20 %": round(safe_float(r.get("DistMA20")), 2),
        "Momentum Score": momentum,
        "Bottom Score": bottom,
        "Score": score,
        "Chien luoc": strategy,
        "Action": action,
        "Ly do": explain_signal(r, momentum, bottom, action),
        "Updated": now_vietnam().strftime("%Y-%m-%d %H:%M:%S"),
        "Version": SYSTEM_VERSION,
    }

# ===== RUN =====
def run():
    results = []

    files = [f for f in os.listdir(DATA_DIR) if f.lower().endswith(".csv")]
    print("CSV files:", len(files))

    for f in files:
        symbol = f.replace(".csv", "").replace(".CSV", "").upper()
        path = os.path.join(DATA_DIR, f)

        try:
            row = analyze(symbol, path)
            if row:
                results.append(row)
                print("OK", symbol, row["Action"], row["Score"])
            else:
                print("SKIP", symbol, "not enough data")
        except Exception as e:
            print("ERR", symbol, repr(e))

    df = pd.DataFrame(results)

    if not df.empty:
        action_rank = {"BUY": 1, "WAIT": 2, "WATCH": 3, "SKIP": 4}
        df["_rank"] = df["Action"].map(action_rank).fillna(9)
        df = df.sort_values(["_rank", "Score"], ascending=[True, False]).drop(columns=["_rank"])
        out_path = os.path.join(OUTPUT_DIR, "v12_core_result.csv")
        df.to_csv(out_path, index=False, encoding="utf-8-sig")
        print("Saved:", out_path)
    else:
        print("No result rows")

    return df

# ===== TELEGRAM =====
def send_telegram(msg):
    token = os.getenv("TELEGRAM_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")

    print("TOKEN loaded:", bool(token))
    print("CHAT_ID loaded:", bool(chat))

    if not token or not chat:
        print("THIEU TELEGRAM_TOKEN HOAC TELEGRAM_CHAT_ID")
        return False

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat, "text": msg},
            timeout=20,
        )

        print("Telegram status:", r.status_code)
        print("Telegram response:", r.text[:500])

        if r.status_code == 200:
            print("TELEGRAM SENT OK")
            return True

        print("TELEGRAM SEND FAILED")
        return False

    except Exception as e:
        print("TELEGRAM ERROR:", repr(e))
        return False


def build_telegram_message(df):
    if df is None or df.empty:
        return (
            "V12 CORE STABLE\n"
            f"Time: {now_vietnam().strftime('%Y-%m-%d %H:%M:%S')}\n"
            "Khong co du lieu tin hieu."
        )

    buy = df[df["Action"] == "BUY"]
    wait = df[df["Action"] == "WAIT"]
    watch = df[df["Action"] == "WATCH"]
    skip = df[df["Action"] == "SKIP"]

    lines = [
        "V12 CORE STABLE",
        f"Time: {now_vietnam().strftime('%Y-%m-%d %H:%M:%S')}",
        f"BUY: {len(buy)} | WAIT: {len(wait)} | WATCH: {len(watch)} | SKIP: {len(skip)}",
        "",
        "TOP SIGNALS:",
    ]

    focus = df[df["Action"].isin(["BUY", "WAIT", "WATCH"])].head(10)
    if focus.empty:
        lines.append("Khong co ma BUY/WAIT/WATCH.")
    else:
        for _, r in focus.iterrows():
            lines.append(
                f"- {r['Ma']} | {r['Action']} | Score {r['Score']} | RSI {r['RSI']} | {r['Chien luoc']}"
            )

    return "\n".join(lines)

# ===== MAIN =====
if __name__ == "__main__":
    print("RUN", SYSTEM_VERSION)
    print("Time VN:", now_vietnam().strftime("%Y-%m-%d %H:%M:%S"))

    df_result = run()
    msg = build_telegram_message(df_result)
    send_telegram(msg)

    print("DONE")
