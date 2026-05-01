# =========================================================
# V12 CORE STABLE - TRADING BOT CO PHIEU VIET NAM
# Muc tieu:
# - Chay on dinh
# - Khong loi font
# - Khong patch chong
# - Co CSV + Dashboard HTML + Telegram
# =========================================================

import os
import time
import traceback
import warnings
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

warnings.filterwarnings("ignore")

# =========================
# 1. CONFIG
# =========================

BOT_DIR = "/content/drive/MyDrive/thumucbot"

DATA_DIR = f"{BOT_DIR}/data"
OUTPUT_DIR = f"{BOT_DIR}/output"
ENV_PATH = f"{BOT_DIR}/url.env"

os.makedirs(OUTPUT_DIR, exist_ok=True)

RESULT_CSV = f"{OUTPUT_DIR}/v12_core_result.csv"
DASHBOARD_HTML = f"{OUTPUT_DIR}/dashboard_v12_core.html"

SYSTEM_VERSION = "V12_CORE_STABLE"

# Neu chay GitHub, sua lai duong dan thanh:
# BOT_DIR = "."
# DATA_DIR = "./data"
# OUTPUT_DIR = "./output"


# =========================
# 2. TIME VIETNAM
# =========================

def now_vietnam():
    return datetime.utcnow() + timedelta(hours=7)


def today_str():
    return now_vietnam().strftime("%Y-%m-%d %H:%M:%S")


# =========================
# 3. LOAD DATA SAFE
# =========================

def load_stock_csv(path):
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except:
        try:
            df = pd.read_csv(path, encoding="utf-8")
        except:
            df = pd.read_csv(path, encoding="latin1")

    df.columns = [str(c).strip().lower() for c in df.columns]

    # chuan hoa cot ngay
    if "time" in df.columns:
        df = df.rename(columns={"time": "date"})
    if "tradingdate" in df.columns:
        df = df.rename(columns={"tradingdate": "date"})

    required = ["date", "open", "high", "low", "close", "volume"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Thieu cot {col}")

    df = df[required].copy()

    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["date", "close"])
    df = df.sort_values("date").drop_duplicates("date")

    return df


# =========================
# 4. INDICATORS
# =========================

def calc_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def calc_atr(df, period=14):
    high = df["high"]
    low = df["low"]
    close = df["close"]

    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    return atr


def add_indicators(df):
    df = df.copy()

    df["ma5"] = df["close"].rolling(5).mean()
    df["ma20"] = df["close"].rolling(20).mean()

    df["rsi"] = calc_rsi(df["close"], 14)

    df["atr"] = calc_atr(df, 14)
    df["atr_pct"] = df["atr"] / df["close"] * 100

    df["vol_ma20"] = df["volume"].rolling(20).mean()
    df["volume_ratio"] = df["volume"] / df["vol_ma20"].replace(0, np.nan)

    df["ret5"] = df["close"].pct_change(5) * 100
    df["ret10"] = df["close"].pct_change(10) * 100

    df["low20"] = df["low"].rolling(20).min()
    df["high20"] = df["high"].rolling(20).max()

    df["drawdown20"] = (df["close"] / df["high20"] - 1) * 100
    df["rebound_low20"] = (df["close"] / df["low20"] - 1) * 100

    df["dist_ma20"] = (df["close"] / df["ma20"] - 1) * 100

    return df


# =========================
# 5. SCORING CORE
# =========================

def safe_float(x, default=0):
    try:
        if pd.isna(x):
            return default
        return float(x)
    except:
        return default


def score_momentum(row):
    score = 0

    close = safe_float(row.get("close"))
    ma5 = safe_float(row.get("ma5"))
    ma20 = safe_float(row.get("ma20"))
    rsi = safe_float(row.get("rsi"))
    ret5 = safe_float(row.get("ret5"))
    ret10 = safe_float(row.get("ret10"))
    vol = safe_float(row.get("volume_ratio"))
    atr = safe_float(row.get("atr_pct"))
    dist = safe_float(row.get("dist_ma20"))

    if ma5 > ma20:
        score += 20
    if 55 <= rsi <= 75:
        score += 20
    if ret5 > 2:
        score += 15
    if ret10 > 3:
        score += 15
    if vol > 1.2:
        score += 15
    if atr <= 8:
        score += 10
    if 0 <= dist <= 12:
        score += 5

    return min(score, 100)


def score_bottom(row):
    score = 0

    rsi = safe_float(row.get("rsi"))
    drawdown20 = safe_float(row.get("drawdown20"))
    rebound = safe_float(row.get("rebound_low20"))
    vol = safe_float(row.get("volume_ratio"))
    atr = safe_float(row.get("atr_pct"))
    dist = safe_float(row.get("dist_ma20"))

    if 30 <= rsi <= 48:
        score += 25
    if drawdown20 <= -5:
        score += 20
    if rebound >= 1:
        score += 15
    if vol >= 0.8:
        score += 15
    if atr <= 9:
        score += 15
    if dist <= 3:
        score += 10

    return min(score, 100)


def classify_action(momentum_score, bottom_score, rsi, atr_pct):
    max_score = max(momentum_score, bottom_score)

    if rsi >= 85:
        return "SKIP", "RSI qua cao"
    if atr_pct > 10:
        return "SKIP", "Bien dong qua manh"

    if max_score >= 80:
        return "BUY", "Tin hieu manh"
    elif max_score >= 65:
        return "WAIT", "Can cho xac nhan"
    elif max_score >= 50:
        return "WATCH", "Theo doi them"
    else:
        return "SKIP", "Tin hieu yeu"


def explain_signal(row, momentum_score, bottom_score, action):
    rsi = safe_float(row.get("rsi"))
    ret5 = safe_float(row.get("ret5"))
    vol = safe_float(row.get("volume_ratio"))
    atr = safe_float(row.get("atr_pct"))

    if action == "BUY":
        if momentum_score >= bottom_score:
            return f"Gia co xu huong tang, RSI {rsi:.1f}, Ret5 {ret5:.1f}%, volume {vol:.2f} lan."
        else:
            return f"Co dau hieu hoi phuc tu vung thap, RSI {rsi:.1f}, volume {vol:.2f} lan."
    elif action == "WAIT":
        return f"Tin hieu kha nhung chua du manh, RSI {rsi:.1f}, ATR {atr:.1f}%."
    elif action == "WATCH":
        return f"Moi o muc theo doi, can them xac nhan gia va volume."
    else:
        return f"Bo qua do tin hieu yeu hoac rui ro cao."


# =========================
# 6. ANALYZE SYMBOL
# =========================

def analyze_symbol(symbol, path):
    df = load_stock_csv(path)

    if len(df) < 40:
        return None

    df = add_indicators(df)
    last = df.iloc[-1]

    momentum = score_momentum(last)
    bottom = score_bottom(last)

    rsi = safe_float(last.get("rsi"))
    atr_pct = safe_float(last.get("atr_pct"))

    action, reason = classify_action(momentum, bottom, rsi, atr_pct)

    strategy = "MOMENTUM" if momentum >= bottom else "BOTTOM"
    explain = explain_signal(last, momentum, bottom, action)

    return {
        "Ngay cap nhat": today_str(),
        "Ma": symbol,
        "Gia dong cua": round(safe_float(last.get("close")), 2),
        "RSI": round(rsi, 2),
        "MA5": round(safe_float(last.get("ma5")), 2),
        "MA20": round(safe_float(last.get("ma20")), 2),
        "ATR %": round(atr_pct, 2),
        "Volume Ratio": round(safe_float(last.get("volume_ratio")), 2),
        "Ret5 %": round(safe_float(last.get("ret5")), 2),
        "Ret10 %": round(safe_float(last.get("ret10")), 2),
        "Dist MA20 %": round(safe_float(last.get("dist_ma20")), 2),
        "Drawdown20 %": round(safe_float(last.get("drawdown20")), 2),
        "Momentum Score": momentum,
        "Bottom Score": bottom,
        "Chien luoc": strategy,
        "Action": action,
        "Ly do": reason,
        "Giai thich": explain,
        "Version": SYSTEM_VERSION
    }


# =========================
# 7. RUN ALL
# =========================

def run_v12_core():
    print("===================================")
    print("V12 CORE STABLE START")
    print("Time:", today_str())
    print("===================================")

    results = []
    errors = []

    files = [f for f in os.listdir(DATA_DIR) if f.lower().endswith(".csv")]

    print("So file CSV:", len(files))

    for i, file in enumerate(files, start=1):
        symbol = file.replace(".csv", "").upper()
        path = os.path.join(DATA_DIR, file)

        try:
            row = analyze_symbol(symbol, path)
            if row:
                results.append(row)
                print(f"[{i}/{len(files)}] OK {symbol}")
            else:
                print(f"[{i}/{len(files)}] SKIP {symbol} - du lieu ngan")
        except Exception as e:
            errors.append({
                "Ma": symbol,
                "Loi": str(e)
            })
            print(f"[{i}/{len(files)}] ERROR {symbol}: {e}")

    df_result = pd.DataFrame(results)

    if not df_result.empty:
        action_rank = {
            "BUY": 1,
            "WAIT": 2,
            "WATCH": 3,
            "SKIP": 4
        }

        df_result["rank"] = df_result["Action"].map(action_rank).fillna(9)
        df_result["Max Score"] = df_result[["Momentum Score", "Bottom Score"]].max(axis=1)

        df_result = df_result.sort_values(
            ["rank", "Max Score"],
            ascending=[True, False]
        ).drop(columns=["rank"])

        df_result.to_csv(RESULT_CSV, index=False, encoding="utf-8-sig")

    print("===================================")
    print("DONE")
    print("Ket qua:", RESULT_CSV)
    print("So ma OK:", len(results))
    print("So ma loi:", len(errors))
    print("===================================")

    return df_result, errors


# =========================
# 8. DASHBOARD HTML
# =========================

def make_dashboard(df):
    if df is None or df.empty:
        html = """
        <html>
        <head><meta charset="utf-8"></head>
        <body><h2>Khong co du lieu</h2></body>
        </html>
        """
        with open(DASHBOARD_HTML, "w", encoding="utf-8") as f:
            f.write(html)
        return

    buy_count = len(df[df["Action"] == "BUY"])
    wait_count = len(df[df["Action"] == "WAIT"])
    watch_count = len(df[df["Action"] == "WATCH"])
    skip_count = len(df[df["Action"] == "SKIP"])

    df_show = df.copy()

    html_table = df_show.to_html(
        index=False,
        escape=False,
        border=0
    )

    html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>V12 CORE STABLE DASHBOARD</title>

<style>
body {{
    font-family: Arial, Helvetica, sans-serif;
    background: #f4f6f8;
    color: #222;
    padding: 20px;
}}

h1 {{
    color: #111;
}}

.card {{
    display: inline-block;
    background: white;
    padding: 15px 25px;
    margin: 10px;
    border-radius: 12px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}}

.card-title {{
    font-size: 14px;
    color: #666;
}}

.card-value {{
    font-size: 28px;
    font-weight: bold;
    margin-top: 5px;
}}

table {{
    width: 100%;
    border-collapse: collapse;
    background: white;
    font-size: 14px;
}}

th {{
    background: #222;
    color: white;
    padding: 10px;
    position: sticky;
    top: 0;
}}

td {{
    padding: 9px;
    border-bottom: 1px solid #ddd;
}}

tr:hover {{
    background: #f1f1f1;
}}

.footer {{
    margin-top: 20px;
    color: #666;
    font-size: 13px;
}}
</style>
</head>

<body>

<h1>V12 CORE STABLE - Dashboard Tin Hieu</h1>

<div class="card">
    <div class="card-title">BUY</div>
    <div class="card-value">{buy_count}</div>
</div>

<div class="card">
    <div class="card-title">WAIT</div>
    <div class="card-value">{wait_count}</div>
</div>

<div class="card">
    <div class="card-title">WATCH</div>
    <div class="card-value">{watch_count}</div>
</div>

<div class="card">
    <div class="card-title">SKIP</div>
    <div class="card-value">{skip_count}</div>
</div>

<h2>Bang tin hieu</h2>

{html_table}

<div class="footer">
    Cap nhat: {today_str()} | Version: {SYSTEM_VERSION}
</div>

</body>
</html>
"""

    with open(DASHBOARD_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print("Dashboard:", DASHBOARD_HTML)


# =========================
# 9. TELEGRAM
# =========================

def send_telegram_message(text):
    load_dotenv(ENV_PATH)

    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("Thieu TELEGRAM_TOKEN hoac TELEGRAM_CHAT_ID")
        return False

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        res = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": text
            },
            timeout=20
        )

        print("Telegram status:", res.status_code)
        return res.status_code == 200

    except Exception as e:
        print("Loi Telegram:", e)
        return False


def make_telegram_summary(df):
    if df is None or df.empty:
        return "V12 CORE STABLE: Khong co du lieu tin hieu."

    buy_df = df[df["Action"] == "BUY"].head(10)
    wait_df = df[df["Action"] == "WAIT"].head(10)

    msg = f"V12 CORE STABLE - {today_str()}\n"
    msg += "========================\n"

    msg += f"BUY: {len(df[df['Action'] == 'BUY'])}\n"
    msg += f"WAIT: {len(df[df['Action'] == 'WAIT'])}\n"
    msg += f"WATCH: {len(df[df['Action'] == 'WATCH'])}\n"
    msg += f"SKIP: {len(df[df['Action'] == 'SKIP'])}\n\n"

    if not buy_df.empty:
        msg += "TOP BUY:\n"
        for _, r in buy_df.iterrows():
            msg += (
                f"- {r['Ma']} | Score {r['Max Score']} | "
                f"RSI {r['RSI']} | {r['Chien luoc']}\n"
            )
    else:
        msg += "Khong co ma BUY.\n"

    if not wait_df.empty:
        msg += "\nTOP WAIT:\n"
        for _, r in wait_df.iterrows():
            msg += (
                f"- {r['Ma']} | Score {r['Max Score']} | "
                f"RSI {r['RSI']} | {r['Chien luoc']}\n"
            )

    return msg


# =========================
# 10. MAIN
# =========================

if __name__ == "__main__":
    try:
        df, errors = run_v12_core()
        make_dashboard(df)

        msg = make_telegram_summary(df)
        send_telegram_message(msg)

        print("V12 CORE STABLE FINISH OK")

    except Exception as e:
        print("FATAL ERROR")
        print(str(e))
        traceback.print_exc()