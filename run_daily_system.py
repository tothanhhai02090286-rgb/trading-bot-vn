import os
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pandas.errors import EmptyDataError

from universe import UNIVERSE

SYSTEM_VERSION = "PRO_V1_2026_04_28"

BATCH_SIZE = 30
SLEEP_SEC = 1
CACHE_DIR = "cache_stock"

STATE_PATH = "progress_state.csv"
ALL_RESULT_PATH = "all_signal_results.csv"

RAW_SIGNAL_PATH = "raw_signal_candidates.csv"
AI_RISK_PATH = "ai_risk_filtered.csv"
BOTTOM_PATH = "bottom_common_priority.csv"
MOMENTUM_PATH = "momentum_common_priority.csv"
ENTRY_PATH = "entry_plan_next_session.csv"
DASHBOARD_PATH = "ai_risk_dashboard.html"

PORTFOLIO_PATH = "portfolio_current.csv"
PORTFOLIO_TRACKER_PATH = "portfolio_tracker.csv"
ACTION_PLAN_PATH = "action_plan.csv"


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


def fetch_history(symbol):
    from vnstock import Vnstock

    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"{symbol}.csv")

    # Giờ Việt Nam
    now_vn = datetime.utcnow() + timedelta(hours=7)
    today = now_vn.strftime("%Y-%m-%d")
    close_hour = 16  # sau 16h mới tin dữ liệu ngày hôm nay

    if os.path.exists(cache_path):
        try:
            df = pd.read_csv(cache_path)

            if df is not None and not df.empty and "close" in df.columns:
                last_date = None

                if "time" in df.columns:
                    last_date = str(df["time"].iloc[-1])[:10]
                elif "date" in df.columns:
                    last_date = str(df["date"].iloc[-1])[:10]

                # Lấy giờ file cache được lưu
                cache_mtime_vn = datetime.utcfromtimestamp(os.path.getmtime(cache_path)) + timedelta(hours=7)
                 cache_hour = cache_mtime_vn.hour

                # ================================
                # 1. Nếu đang trước 16h → dùng cache, không gọi API
                # ================================
                if now_vn.hour < close_hour:
                    print(f"⏳ Trước 16h VN → dùng cache: {symbol}")
                    return df

                # ================================
                # 2. Nếu cache là ngày hôm nay và được lưu sau 16h → dùng cache
                # ================================
                if last_date == today and cache_hour >= close_hour:
                    print(f"⚡ Cache OK sau phiên: {symbol}")
                    return df

                # ================================
                # 3. Nếu cache ngày hôm nay nhưng lưu trước 16h → fetch lại
                # ================================
                if last_date == today and cache_hour < close_hour:
                    print(f"🔄 Cache ngày {today} nhưng lưu trước 16h → update lại: {symbol}")

                # ================================
                # 4. Nếu cache ngày cũ → fetch lại
                # ================================
                elif last_date != today:
                    print(f"🔄 Cache cũ {symbol}: {last_date} → update ngày {today}")

                else:
                    print(f"🔄 Cache cần update: {symbol}")

        except Exception as e:
            print(f"⚠️ Cache lỗi {symbol}: {e}")

    print(f"🌐 API fetch/update: {symbol}")

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

    df.to_csv(cache_path, index=False, encoding="utf-8-sig")
    print(f"💾 Updated cache: {cache_path}")

    return df


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

    if pd.isna(close) or pd.isna(ma5) or pd.isna(ma20) or pd.isna(rsi):
        return None

    ret5 = safe_float(last.get("Ret5 %"), 0)
    ret10 = safe_float(last.get("Ret10 %"), 0)
    ret20 = safe_float(last.get("Ret20 %"), 0)
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
        "Volume Ratio": round(safe_float(last.get("Volume Ratio"), 0), 2),
        "ADX": round(safe_float(last.get("ADX"), 0), 2),
        "ATR %": round(safe_float(last.get("ATR %"), 999), 2),
        "MACD Hist": round(safe_float(last.get("MACD Hist"), 0), 4),
        "MACD Hist Up": bool(last.get("MACD Hist Up")),
        "Dist MA20 %": round(safe_float(last.get("Dist MA20 %"), 0), 2),
        "Drawdown20 %": round(safe_float(last.get("Drawdown20 %"), 0), 2),
        "Rebound Low20 %": round(safe_float(last.get("Rebound Low20 %"), 0), 2),
        "Low20": round(safe_float(last.get("Low20"), 0), 2),
        "High20": round(safe_float(last.get("High20"), 0), 2),
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


def build_portfolio_and_action_plan(combined, ai_risk):
    portfolio = safe_read_csv(PORTFOLIO_PATH)

    if not portfolio.empty and "Mã" in portfolio.columns:
        tracker = portfolio.merge(
            combined,
            on="Mã",
            how="left",
            suffixes=("", "_signal")
        )

        tracker["Giá vốn"] = pd.to_numeric(tracker.get("Giá vốn"), errors="coerce")
        tracker["Số lượng"] = pd.to_numeric(tracker.get("Số lượng"), errors="coerce")
        tracker["Close"] = pd.to_numeric(tracker.get("Close"), errors="coerce")

        tracker["Giá trị vốn"] = tracker["Giá vốn"] * tracker["Số lượng"]
        tracker["Giá trị hiện tại"] = tracker["Close"] * tracker["Số lượng"]
        tracker["Lãi/Lỗ %"] = (tracker["Close"] / tracker["Giá vốn"] - 1) * 100
        tracker["Lãi/Lỗ tiền"] = tracker["Giá trị hiện tại"] - tracker["Giá trị vốn"]

        def holding_action(row):
            pnl = safe_float(row.get("Lãi/Lỗ %"), 0)
            action = str(row.get("Action", ""))
            risk = str(row.get("Risk Status", ""))
            rsi = safe_float(row.get("RSI"), 0)
            strategy = str(row.get("Chiến lược", ""))

            if pd.isna(row.get("Close")):
                return "CHƯA CÓ DATA"
            if risk == "FAIL":
                return "GIẢM / BÁN"
            if pnl <= -5:
                return "CẮT LỖ"
            if pnl >= 10 and rsi >= 75:
                return "CHỐT LỜI MỘT PHẦN"
            if pnl >= 7:
                return "GIỮ / CANH CHỐT"
            if action == "BUY NOW":
                return "GIỮ MẠNH"
            if strategy in ["MOMENTUM", "BOTTOM", "MOMENTUM_WATCH", "BOTTOM_WATCH"]:
                return "GIỮ"
            return "THEO DÕI"

        tracker["Hành động"] = tracker.apply(holding_action, axis=1)

        def risk_flag(row):
            pnl = safe_float(row.get("Lãi/Lỗ %"), 0)
            rsi = safe_float(row.get("RSI"), 0)
            risk = str(row.get("Risk Status", ""))

            if risk == "FAIL":
                return "❌ RISK FAIL"
            if pnl <= -4:
                return "🔴 NGUY HIỂM"
            if pnl <= -2:
                return "🟡 CẢNH BÁO"
            if rsi >= 80:
                return "⚠️ QUÁ MUA"
            if pnl > 0:
                return "🟢 ĐANG LÃI"
            return "🟢 ỔN"

        tracker["Cảnh báo"] = tracker.apply(risk_flag, axis=1)

        keep_tracker = [
            "Mã", "Giá vốn", "Close", "Số lượng",
            "Giá trị vốn", "Giá trị hiện tại",
            "Lãi/Lỗ %", "Lãi/Lỗ tiền",
            "Signal", "Chiến lược", "Score", "RSI",
            "Risk Status", "Risk Reason", "Action",
            "Hành động", "Cảnh báo"
        ]
        tracker = tracker[[c for c in keep_tracker if c in tracker.columns]]

    else:
        tracker = pd.DataFrame([{
            "Mã": "NO_PORTFOLIO",
            "Hành động": "Chưa có portfolio_current.csv",
            "Cảnh báo": "⚠️ CHƯA CÓ DANH MỤC"
        }])

    tracker.to_csv(PORTFOLIO_TRACKER_PATH, index=False, encoding="utf-8-sig")

    buy_plan = ai_risk[ai_risk["Action"] == "BUY NOW"].copy()

    if not buy_plan.empty:
        buy_plan["Hành động"] = "MUA MỚI"
        buy_plan["Lý do"] = buy_plan["Signal"].astype(str) + " | Score " + buy_plan["Score"].astype(str)
        keep_buy = [
            "Ngày", "Mã", "Hành động", "Lý do",
            "Signal", "Chiến lược", "Score",
            "RSI", "Close", "RS20", "Volume Ratio",
            "ADX", "ATR %", "Risk Status"
        ]
        buy_plan = buy_plan[[c for c in keep_buy if c in buy_plan.columns]]
    else:
        buy_plan = pd.DataFrame()

    hold_plan = tracker.copy()

    if not hold_plan.empty and "Mã" in hold_plan.columns:
        hold_plan["Ngày"] = datetime.now().strftime("%Y-%m-%d")
        hold_plan["Lý do"] = "Theo dõi danh mục hiện có"

        keep_hold = [
            "Ngày", "Mã", "Hành động", "Cảnh báo", "Lý do",
            "Lãi/Lỗ %", "Lãi/Lỗ tiền",
            "Signal", "Chiến lược", "Score",
            "RSI", "Close", "Risk Status", "Risk Reason"
        ]
        hold_plan = hold_plan[[c for c in keep_hold if c in hold_plan.columns]]
    else:
        hold_plan = pd.DataFrame()

    action_plan = pd.concat([buy_plan, hold_plan], ignore_index=True)

    if action_plan.empty:
        action_plan = pd.DataFrame([{
            "Ngày": datetime.now().strftime("%Y-%m-%d"),
            "Mã": "NO_ACTION",
            "Hành động": "KHÔNG LÀM GÌ",
            "Lý do": "Không có tín hiệu mua và chưa có danh mục"
        }])

    action_plan.to_csv(ACTION_PLAN_PATH, index=False, encoding="utf-8-sig")

    return tracker, action_plan


def html_style():
    return """
<style>
body {
    background-color: #0f1117;
    color: #f1f1f1;
    font-family: Arial, sans-serif;
    padding: 20px;
}
h2 {
    font-size: 34px;
}
h3 {
    margin-top: 35px;
    color: #ff4d4f;
}
table {
    border-collapse: collapse;
    width: 100%;
    margin-bottom: 24px;
    font-size: 14px;
}
th {
    background-color: #1f2430;
    color: #ffffff;
    padding: 8px;
    border: 1px solid #333;
}
td {
    padding: 8px;
    border: 1px solid #333;
}
tr:nth-child(even) {
    background-color: #171b24;
}
tr:nth-child(odd) {
    background-color: #11151d;
}
</style>
"""


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

needed_cols = ["Risk Status", "Action", "Chiến lược", "Score", "Mã"]
for col in needed_cols:
    if col not in combined.columns:
        combined[col] = ""

combined["Score"] = pd.to_numeric(combined["Score"], errors="coerce").fillna(0)
combined = combined.sort_values("Score", ascending=False)

combined.to_csv(ALL_RESULT_PATH, index=False, encoding="utf-8-sig")

raw_signals = combined[
    combined["Chiến lược"].isin([
        "MOMENTUM", "BOTTOM", "MOMENTUM_WATCH", "BOTTOM_WATCH", "WATCH"
    ])
].copy()
raw_signals = raw_signals.sort_values("Score", ascending=False)
raw_signals.to_csv(RAW_SIGNAL_PATH, index=False, encoding="utf-8-sig")

ai_risk = combined[
    (combined["Risk Status"] == "PASS") &
    (combined["Action"].isin(["BUY NOW", "WAIT", "WATCHLIST"]))
].copy()
ai_risk = ai_risk.sort_values("Score", ascending=False)
ai_risk.to_csv(AI_RISK_PATH, index=False, encoding="utf-8-sig")

bottom = ai_risk[
    ai_risk["Chiến lược"].isin(["BOTTOM", "BOTTOM_WATCH"])
].copy()
momentum = ai_risk[
    ai_risk["Chiến lược"].isin(["MOMENTUM", "MOMENTUM_WATCH"])
].copy()

bottom.to_csv(BOTTOM_PATH, index=False, encoding="utf-8-sig")
momentum.to_csv(MOMENTUM_PATH, index=False, encoding="utf-8-sig")

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

entry.to_csv(ENTRY_PATH, index=False, encoding="utf-8-sig")

tracker, action_plan = build_portfolio_and_action_plan(combined, ai_risk)

raw_html = raw_signals.to_html(index=False)
ai_html = ai_risk.to_html(index=False)
entry_html = entry.to_html(index=False)
tracker_html = tracker.to_html(index=False)
action_html = action_plan.to_html(index=False)

html_full = f"""
<html>
<head>
<meta charset="utf-8">
<title>Trading Dashboard</title>
{html_style()}
</head>
<body>

<h2>📊 TRADING BOT CONTROL CENTER</h2>
<p><b>Generated:</b> {datetime.now()}</p>
<p><b>Version:</b> {SYSTEM_VERSION}</p>
<p><b>Batch:</b> {start_idx} → {end_idx} / {len(UNIVERSE)}</p>

<h3>🔎 RAW SIGNAL - Lọc thô</h3>
{raw_html}

<h3>🔥 AI FINAL - Lọc tinh</h3>
{ai_html}

<h3>📋 ENTRY</h3>
{entry_html}

<h3>📦 PORTFOLIO TRACKER</h3>
{tracker_html}

<h3>🎯 ACTION PLAN</h3>
{action_html}

</body>
</html>
"""

with open(DASHBOARD_PATH, "w", encoding="utf-8") as f:
    f.write(html_full)

next_start = end_idx
if next_start >= len(UNIVERSE):
    next_start = 0

save_state(next_start)

print("✅ CREATED OUTPUT FILES")
print("Rows combined:", len(combined))
print("Raw signals:", len(raw_signals))
print("AI risk rows:", len(ai_risk))
print("Bottom rows:", len(bottom))
print("Momentum rows:", len(momentum))
print("Entry rows:", len(entry))
print("Portfolio rows:", len(tracker))
print("Action plan rows:", len(action_plan))
print("Next batch start:", next_start)
