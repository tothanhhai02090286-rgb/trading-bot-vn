import os
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pandas.errors import EmptyDataError

from universe import UNIVERSE

SYSTEM_VERSION = "PRO_V1_2026_04_28"

BATCH_SIZE = 10
SLEEP_SEC = 5

STATE_PATH = "progress_state.csv"
ALL_RESULT_PATH = "all_signal_results.csv"

OUTPUT_AI_RISK = "ai_risk_filtered.csv"
OUTPUT_BOTTOM = "bottom_common_priority.csv"
OUTPUT_MOMENTUM = "momentum_common_priority.csv"
OUTPUT_ENTRY = "entry_plan_next_session.csv"
OUTPUT_DASHBOARD = "ai_risk_dashboard.html"


# ================================
# SAFE UTILS
# ================================

def safe_read_csv(path):
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except EmptyDataError:
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def safe_float(x, default=np.nan):
    try:
        if pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default


def load_state():
    df = safe_read_csv(STATE_PATH)
    if df.empty or "next_start" not in df.columns:
        return 0
    try:
        return int(df["next_start"].iloc[-1])
    except Exception:
        return 0


def save_state(next_start):
    pd.DataFrame([{
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "next_start": next_start,
        "version": SYSTEM_VERSION
    }]).to_csv(STATE_PATH, index=False, encoding="utf-8-sig")


# ================================
# DATA FETCH
# ================================

def fetch_history(symbol):
    from vnstock import Vnstock

    end = datetime.now()
    start = end - timedelta(days=260)

    stock = Vnstock().stock(symbol=symbol, source="KBS")
    df = stock.quote.history(
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        interval="1D"
    )

    if df is None or df.empty:
        return pd.DataFrame()

    df.columns = [str(c).lower() for c in df.columns]

    if "close" not in df.columns:
        return pd.DataFrame()

    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["close"]).reset_index(drop=True)
    return df


# ================================
# INDICATORS
# ================================

def calc_rsi(close, period=14):
    close = pd.Series(close).astype(float)
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))


def add_indicators(df):
    df = df.copy()

    close = df["close"]
    high = df["high"] if "high" in df.columns else close
    low = df["low"] if "low" in df.columns else close
    volume = df["volume"] if "volume" in df.columns else pd.Series([np.nan] * len(df))

    df["MA5"] = close.rolling(5).mean()
    df["MA20"] = close.rolling(20).mean()

    df["RSI"] = calc_rsi(close, 14)

    df["Ret5 %"] = close.pct_change(5) * 100
    df["Ret10 %"] = close.pct_change(10) * 100
    df["Ret20 %"] = close.pct_change(20) * 100

    df["VolMA20"] = volume.rolling(20).mean()
    df["Volume Ratio"] = volume / (df["VolMA20"] + 1e-9)

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    df["ATR"] = tr.rolling(14).mean()
    df["ATR %"] = df["ATR"] / close * 100

    df["High20"] = high.rolling(20).max()
    df["Low20"] = low.rolling(20).min()
    df["Drawdown20 %"] = (close / df["High20"] - 1) * 100
    df["Rebound Low20 %"] = (close / df["Low20"] - 1) * 100
    df["Dist MA20 %"] = (close / df["MA20"] - 1) * 100

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()

    df["MACD Hist"] = macd - signal
    df["MACD Hist Up"] = df["MACD Hist"] > df["MACD Hist"].shift(1)

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

    plus_di = 100 * pd.Series(plus_dm).rolling(14).mean() / (df["ATR"] + 1e-9)
    minus_di = 100 * pd.Series(minus_dm).rolling(14).mean() / (df["ATR"] + 1e-9)

    dx = (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9)) * 100
    df["ADX"] = dx.rolling(14).mean()

    return df


# ================================
# MARKET BENCHMARK
# ================================

def get_market_ret20():
    for benchmark in ["VNINDEX", "VN30"]:
        try:
            df = fetch_history(benchmark)
            if df.empty or len(df) < 30:
                continue
            df = add_indicators(df)
            ret20 = safe_float(df["Ret20 %"].iloc[-1], 0)
            print(f"📊 Market benchmark {benchmark} Ret20: {ret20:.2f}%")
            return ret20
        except Exception:
            continue

    print("⚠️ Không lấy được benchmark, RS20 tạm tính = Ret20")
    return 0


# ================================
# SCORE LOGIC
# ================================

def score_momentum(row):
    score = 0

    if row["MA5"] > row["MA20"]:
        score += 15
    if 55 <= row["RSI"] <= 75:
        score += 15
    if row["Ret5 %"] > 2:
        score += 10
    if row["Ret10 %"] > 3:
        score += 10
    if row["RS20"] > 0:
        score += 10
    if row["Volume Ratio"] > 1.2:
        score += 10
    if row["ADX"] > 20:
        score += 10
    if row["ATR %"] <= 8:
        score += 10
    if row["MACD Hist Up"]:
        score += 5
    if 0 <= row["Dist MA20 %"] <= 12:
        score += 5

    return score


def score_bottom(row):
    score = 0

    if 30 <= row["RSI"] <= 48:
        score += 15
    if row["Drawdown20 %"] <= -5:
        score += 15
    if row["Rebound Low20 %"] >= 1:
        score += 10
    if row["Volume Ratio"] >= 0.8:
        score += 10
    if row["Close"] >= row["Low20"]:
        score += 10
    if row["ATR %"] <= 9:
        score += 10
    if row["RS20"] > -8:
        score += 10
    if row["Dist MA20 %"] <= 3:
        score += 10
    if row["MACD Hist Up"]:
        score += 10

    return score


def classify_strategy(row):
    if row["Momentum Score"] >= 75 and row["Momentum Score"] >= row["Bottom Score"]:
        return "MOMENTUM"

    if row["Bottom Score"] >= 70 and row["Bottom Score"] > row["Momentum Score"]:
        return "BOTTOM"

    if row["Momentum Score"] >= 60:
        return "MOMENTUM_WATCH"

    if row["Bottom Score"] >= 55:
        return "BOTTOM_WATCH"

    return "WATCH"


def risk_filter(row):
    reasons = []

    if row["RSI"] >= 90:
        reasons.append("RSI quá nóng")

    if row["ATR %"] > 10:
        reasons.append("ATR quá cao")

    if row["Volume Ratio"] < 0.7:
        reasons.append("Volume yếu")

    if row["RS20"] < -10:
        reasons.append("RS20 yếu")

    if row["Chiến lược"] == "MOMENTUM" and row["Close"] < row["MA20"]:
        reasons.append("Momentum nhưng giá dưới MA20")

    if len(reasons) == 0:
        return "PASS", ""

    return "FAIL", "; ".join(reasons)


def classify_action(row):
    if row["Risk Status"] == "FAIL":
        return "SKIP"

    if row["RSI"] >= 90:
        return "SKIP"

    if 85 <= row["RSI"] < 90:
        return "WATCHLIST"

    if 75 <= row["RSI"] < 85:
        return "WAIT"

    if row["Chiến lược"] == "MOMENTUM" and row["Momentum Score"] >= 80:
        return "BUY NOW"

    if row["Chiến lược"] == "BOTTOM" and row["Bottom Score"] >= 75:
        return "BUY NOW"

    if row["Chiến lược"] in ["MOMENTUM", "BOTTOM"]:
        return "WAIT"

    if row["Chiến lược"] in ["MOMENTUM_WATCH", "BOTTOM_WATCH"]:
        return "WATCHLIST"

    return "SKIP"


def make_signal(row):
    if row["Chiến lược"] == "MOMENTUM":
        return "🚀 MOMENTUM"
    if row["Chiến lược"] == "BOTTOM":
        return "🧲 BOTTOM"
    if row["Chiến lược"] == "MOMENTUM_WATCH":
        return "👀 MOMENTUM WATCH"
    if row["Chiến lược"] == "BOTTOM_WATCH":
        return "👀 BOTTOM WATCH"
    return "👀 WATCH"


# ================================
# ANALYZE SYMBOL
# ================================

def analyze_symbol(symbol, market_ret20):
    df = fetch_history(symbol)

    if df.empty or len(df) < 60:
        return None

    df = add_indicators(df)

    last = df.iloc[-1]

    close = safe_float(last.get("close"))
    ma5 = safe_float(last.get("MA5"))
    ma20 = safe_float(last.get("MA20"))
    rsi = safe_float(last.get("RSI"))
    ret5 = safe_float(last.get("Ret5 %"))
    ret10 = safe_float(last.get("Ret10 %"))
    ret20 = safe_float(last.get("Ret20 %"))
    volume_ratio = safe_float(last.get("Volume Ratio"), 0)
    atr = safe_float(last.get("ATR %"), 999)
    adx = safe_float(last.get("ADX"), 0)
    dist_ma20 = safe_float(last.get("Dist MA20 %"))
    drawdown20 = safe_float(last.get("Drawdown20 %"))
    rebound_low20 = safe_float(last.get("Rebound Low20 %"))
    low20 = safe_float(last.get("Low20"))
    high20 = safe_float(last.get("High20"))
    macd_hist = safe_float(last.get("MACD Hist"), 0)
    macd_up = bool(last.get("MACD Hist Up"))

    if pd.isna(close) or pd.isna(ma5) or pd.isna(ma20) or pd.isna(rsi):
        return None

    rs20 = ret20 - market_ret20

    row = {
        "Ngày": datetime.now().strftime("%Y-%m-%d"),
        "Mã": symbol,
        "Close": round(close, 2),
        "MA5": round(ma5, 2),
        "MA20": round(ma20, 2),
        "RSI": round(rsi, 2),
        "Ret5 %": round(ret5, 2),
        "Ret10 %": round(ret10, 2),
        "Ret20 %": round(ret20, 2),
        "RS20": round(rs20, 2),
        "Volume Ratio": round(volume_ratio, 2),
        "ADX": round(adx, 2),
        "ATR %": round(atr, 2),
        "MACD Hist": round(macd_hist, 4),
        "MACD Hist Up": macd_up,
        "Dist MA20 %": round(dist_ma20, 2),
        "Drawdown20 %": round(drawdown20, 2),
        "Rebound Low20 %": round(rebound_low20, 2),
        "Low20": round(low20, 2),
        "High20": round(high20, 2),
        "Updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Version": SYSTEM_VERSION
    }

    row["Momentum Score"] = score_momentum(row)
    row["Bottom Score"] = score_bottom(row)
    row["Score"] = max(row["Momentum Score"], row["Bottom Score"])

    row["Chiến lược"] = classify_strategy(row)

    risk_status, risk_reason = risk_filter(row)
    row["Risk Status"] = risk_status
    row["Risk Reason"] = risk_reason

    row["Action"] = classify_action(row)
    row["Signal"] = make_signal(row)

    return row


# ================================
# MAIN
# ================================

print("🚀 RUN BATCH TRADING ENGINE - KBS")
print(f"📌 SYSTEM VERSION: {SYSTEM_VERSION}")
print("⏰", datetime.now())

start_idx = load_state()

if start_idx >= len(UNIVERSE):
    start_idx = 0

end_idx = min(start_idx + BATCH_SIZE, len(UNIVERSE))
batch = UNIVERSE[start_idx:end_idx]

print(f"📌 Batch: {start_idx} → {end_idx} / {len(UNIVERSE)}")
print("📋 Mã:", batch)

market_ret20 = get_market_ret20()

rows = []

for i, symbol in enumerate(batch, 1):
    print(f"📡 {i}/{len(batch)} Fetch {symbol}")
    try:
        result = analyze_symbol(symbol, market_ret20)
        if result:
            rows.append(result)
            print("✅", symbol, result["Signal"], result["Action"], result["Score"])
        else:
            print("⚠️", symbol, "không đủ dữ liệu")
    except Exception as e:
        print("❌", symbol, repr(e))

    time.sleep(SLEEP_SEC)

new_df = pd.DataFrame(rows)
old_df = safe_read_csv(ALL_RESULT_PATH)

if not old_df.empty and "Mã" in old_df.columns:
    old_df = old_df[~old_df["Mã"].isin(batch)]
    combined = pd.concat([old_df, new_df], ignore_index=True)
else:
    combined = new_df.copy()

if combined.empty:
    combined = pd.DataFrame([{
        "Ngày": datetime.now().strftime("%Y-%m-%d"),
        "Mã": "NO_SIGNAL",
        "Close": np.nan,
        "Signal": "NO SIGNAL",
        "Chiến lược": "SYSTEM",
        "Score": 0,
        "Action": "WAIT",
        "Risk Status": "SYSTEM",
        "Risk Reason": "",
        "Updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Version": SYSTEM_VERSION
    }])

combined = combined.sort_values("Score", ascending=False)

combined.to_csv(ALL_RESULT_PATH, index=False, encoding="utf-8-sig")

ai_risk = combined[
    (combined["Risk Status"] == "PASS") &
    (combined["Action"].isin(["BUY NOW", "WAIT", "WATCHLIST"]))
].copy()

ai_risk = ai_risk.sort_values("Score", ascending=False)
ai_risk.to_csv(OUTPUT_AI_RISK, index=False, encoding="utf-8-sig")

bottom = ai_risk[
    ai_risk["Chiến lược"].isin(["BOTTOM", "BOTTOM_WATCH"])
].copy()

momentum = ai_risk[
    ai_risk["Chiến lược"].isin(["MOMENTUM", "MOMENTUM_WATCH"])
].copy()

bottom.to_csv(OUTPUT_BOTTOM, index=False, encoding="utf-8-sig")
momentum.to_csv(OUTPUT_MOMENTUM, index=False, encoding="utf-8-sig")

entry = ai_risk[
    ai_risk["Action"].isin(["BUY NOW", "WAIT", "WATCHLIST"])
].copy()

entry = entry.sort_values("Score", ascending=False).head(10)

if entry.empty:
    entry = pd.DataFrame([{
        "Ngày": datetime.now().strftime("%Y-%m-%d"),
        "Mã": "NO_SIGNAL",
        "Action": "WAIT",
        "Chiến lược": "SYSTEM",
        "Score": 0,
        "Risk Reason": "Không có tín hiệu đạt chuẩn"
    }])
else:
    keep = [
        "Ngày", "Mã", "Action", "Signal", "Chiến lược", "Score",
        "Momentum Score", "Bottom Score", "Risk Status", "Risk Reason",
        "RSI", "Close", "MA5", "MA20", "Ret5 %", "Ret10 %",
        "RS20", "Volume Ratio", "ADX", "ATR %", "Dist MA20 %"
    ]
    entry = entry[[c for c in keep if c in entry.columns]]

entry.to_csv(OUTPUT_ENTRY, index=False, encoding="utf-8-sig")

html = combined.to_html(index=False)
html_full = f"""
<html>
<head>
<meta charset="utf-8">
<title>Batch Trading Dashboard - KBS</title>
</head>
<body>
<h2>📊 Batch Trading Dashboard - KBS</h2>
<p><b>Generated:</b> {datetime.now()}</p>
<p><b>Version:</b> {SYSTEM_VERSION}</p>
<p><b>Batch:</b> {start_idx} → {end_idx} / {len(UNIVERSE)}</p>
<p><b>BUY NOW:</b> {len(entry[entry["Action"] == "BUY NOW"]) if "Action" in entry.columns else 0}</p>
{html}
</body>
</html>
"""

with open(OUTPUT_DASHBOARD, "w", encoding="utf-8") as f:
    f.write(html_full)

next_start = end_idx

if next_start >= len(UNIVERSE):
    next_start = 0

save_state(next_start)

print("✅ CREATED OUTPUT FILES")
print("Rows combined:", len(combined))
print("AI risk rows:", len(ai_risk))
print("Bottom rows:", len(bottom))
print("Momentum rows:", len(momentum))
print("Entry rows:", len(entry))
print("Next batch start:", next_start)
