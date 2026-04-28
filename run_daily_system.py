import os
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pandas.errors import EmptyDataError

from universe import UNIVERSE
SYSTEM_VERSION = "PRO_V1_2026_04_28"

print("🚀 RUN BATCH TRADING ENGINE - KBS")
print(f"📌 SYSTEM VERSION: {SYSTEM_VERSION}")
print("⏰", datetime.now())

BATCH_SIZE = 10
SLEEP_SEC = 5

STATE_PATH = "progress_state.csv"
ALL_RESULT_PATH = "all_signal_results.csv"

def safe_read_csv(path):
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except EmptyDataError:
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

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
        "next_start": next_start
    }]).to_csv(STATE_PATH, index=False, encoding="utf-8-sig")

def calc_rsi(close, period=14):
    close = pd.Series(close).astype(float)
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def fetch_history(symbol):
    from vnstock import Vnstock

    end = datetime.now()
    start = end - timedelta(days=160)

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

    return df

def analyze_symbol(symbol):
    df = fetch_history(symbol)

    if df.empty or len(df) < 30:
        return None

    close = pd.to_numeric(df["close"], errors="coerce").dropna()

    if len(close) < 30:
        return None

    last_close = float(close.iloc[-1])
    ma5 = float(close.tail(5).mean())
    ma20 = float(close.tail(20).mean())
    rsi = float(calc_rsi(close, 14).iloc[-1])

    ret5 = (last_close / close.iloc[-6] - 1) * 100 if len(close) >= 6 else 0
    dist_ma20 = (last_close / ma20 - 1) * 100

    if ma5 > ma20 and rsi >= 50 and ret5 > 0:
        signal = "🚀 MOMENTUM"
        strategy = "MOMENTUM"
        score = 70 + min(20, max(0, ret5 * 2)) + min(10, max(0, rsi - 50) / 2)

    elif rsi <= 45 and dist_ma20 <= 0:
        signal = "🧲 BOTTOM"
        strategy = "BOTTOM"
        score = 65 + min(20, max(0, 45 - rsi)) + min(10, abs(min(dist_ma20, 0)))

    else:
        signal = "👀 WATCH"
        strategy = "WATCH"
        score = 50 + min(20, max(0, ret5))

    return {
        "Ngày": datetime.now().strftime("%Y-%m-%d"),
        "Mã": symbol,
        "Close": round(last_close, 2),
        "Signal": signal,
        "Chiến lược": strategy,
        "Score": round(score, 2),
        "RSI": round(rsi, 2),
        "MA5": round(ma5, 2),
        "MA20": round(ma20, 2),
        "Ret5 %": round(ret5, 2),
        "Dist MA20 %": round(dist_ma20, 2),
        "Updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

start_idx = load_state()

if start_idx >= len(UNIVERSE):
    start_idx = 0

end_idx = min(start_idx + BATCH_SIZE, len(UNIVERSE))
batch = UNIVERSE[start_idx:end_idx]

print(f"📌 Batch: {start_idx} → {end_idx} / {len(UNIVERSE)}")
print("📋 Mã:", batch)

rows = []

for i, symbol in enumerate(batch, 1):
    print(f"📡 {i}/{len(batch)} Fetch {symbol}")
    try:
        result = analyze_symbol(symbol)
        if result:
            rows.append(result)
            print("✅", symbol, result["Signal"], result["Score"])
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
        "Mã": "NO_DATA",
        "Close": np.nan,
        "Signal": "NO DATA",
        "Chiến lược": "SYSTEM",
        "Score": 0,
        "RSI": np.nan,
        "MA5": np.nan,
        "MA20": np.nan,
        "Ret5 %": np.nan,
        "Dist MA20 %": np.nan,
        "Updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }])

combined = combined.sort_values("Score", ascending=False)

combined.to_csv(ALL_RESULT_PATH, index=False, encoding="utf-8-sig")
combined.to_csv("ai_risk_filtered.csv", index=False, encoding="utf-8-sig")

bottom = combined[combined["Chiến lược"] == "BOTTOM"].copy()
momentum = combined[combined["Chiến lược"] == "MOMENTUM"].copy()

bottom.to_csv("bottom_common_priority.csv", index=False, encoding="utf-8-sig")
momentum.to_csv("momentum_common_priority.csv", index=False, encoding="utf-8-sig")

entry = combined[combined["Chiến lược"].isin(["BOTTOM", "MOMENTUM"])].copy()
entry = entry.sort_values("Score", ascending=False).head(10)

if entry.empty:
    entry = pd.DataFrame([{
        "Ngày": datetime.now().strftime("%Y-%m-%d"),
        "Mã": "NO_SIGNAL",
        "Action": "WAIT",
        "Chiến lược": "SYSTEM",
        "Score": 0
    }])
else:
    entry["Action"] = "BUY/WATCH"
    keep = ["Ngày", "Mã", "Action", "Chiến lược", "Score", "RSI", "Close", "MA5", "MA20"]
    entry = entry[[c for c in keep if c in entry.columns]]

entry.to_csv("entry_plan_next_session.csv", index=False, encoding="utf-8-sig")

html = combined.to_html(index=False)
html_full = f"""
<html>
<head><meta charset="utf-8"></head>
<body>
<h2>📊 Batch Trading Dashboard - KBS</h2>
<p>Generated: {datetime.now()}</p>
<p>Batch: {start_idx} → {end_idx} / {len(UNIVERSE)}</p>
{html}
</body>
</html>
"""

with open("ai_risk_dashboard.html", "w", encoding="utf-8") as f:
    f.write(html_full)

next_start = end_idx

if next_start >= len(UNIVERSE):
    next_start = 0

save_state(next_start)

print("✅ CREATED OUTPUT FILES")
print("Rows combined:", len(combined))
print("Next batch start:", next_start)
