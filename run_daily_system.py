import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

print("🚀 RUN REAL DATA TRADING SYSTEM - VNSTOCK")

try:
    from vnstock import Vnstock
except Exception as e:
    print("❌ Không import được vnstock:", e)
    raise

tickers = [
    "VNM","FPT","HPG","MWG","VCB","SSI",
    "VIC","VHM","GAS","PLX","PNJ","REE",
    "CTG","TCB","MBB","ACB","HDB","VPB",
    "DXG","KDH"
]

def calc_rsi(close, period=14):
    close = pd.Series(close).astype(float)
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def fetch_history(symbol):
    end = datetime.now()
    start = end - timedelta(days=120)

    stock = Vnstock().stock(symbol=symbol, source="VCI")
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

rows = []

for i, t in enumerate(tickers, 1):
    print(f"📡 Fetch {i}/{len(tickers)}: {t}")

    try:
        df = fetch_history(t)

        if df.empty or len(df) < 30:
            print(f"⚠️ {t}: thiếu dữ liệu")
            continue

        close = pd.to_numeric(df["close"], errors="coerce").dropna()

        if len(close) < 30:
            print(f"⚠️ {t}: close không đủ")
            continue

        last_close = float(close.iloc[-1])
        ma5 = float(close.tail(5).mean())
        ma20 = float(close.tail(20).mean())
        rsi = float(calc_rsi(close, 14).iloc[-1])

        ret5 = (last_close / close.iloc[-6] - 1) * 100 if len(close) >= 6 else 0
        dist_ma20 = (last_close / ma20 - 1) * 100

        # ===== LOGIC THẬT NHẸ =====
        if ma5 > ma20 and rsi >= 50 and ret5 > 0:
            signal = "🚀 MOMENTUM"
            score = 70 + min(20, max(0, ret5 * 2)) + min(10, max(0, rsi - 50) / 2)

        elif rsi <= 45 and dist_ma20 <= 0:
            signal = "🧲 BOTTOM"
            score = 65 + min(20, max(0, 45 - rsi)) + min(10, abs(min(dist_ma20, 0)))

        else:
            signal = "👀 WATCH"
            score = 50 + min(20, max(0, ret5))

        rows.append({
            "Ngày": datetime.now().strftime("%Y-%m-%d"),
            "Mã": t,
            "Close": round(last_close, 2),
            "Signal": signal,
            "Score": round(score, 2),
            "RSI": round(rsi, 2),
            "MA5": round(ma5, 2),
            "MA20": round(ma20, 2),
            "Ret5 %": round(ret5, 2),
            "Dist MA20 %": round(dist_ma20, 2)
        })

        time.sleep(1.5)

    except Exception as e:
        print(f"❌ {t} lỗi:", e)

df = pd.DataFrame(rows)

if df.empty:
    print("❌ Không tạo được dữ liệu thật, giữ file báo lỗi")
    df = pd.DataFrame([{
        "Ngày": datetime.now().strftime("%Y-%m-%d"),
        "Mã": "ERROR",
        "Close": np.nan,
        "Signal": "❌ NO DATA",
        "Score": 0,
        "RSI": np.nan,
        "MA5": np.nan,
        "MA20": np.nan,
        "Ret5 %": np.nan,
        "Dist MA20 %": np.nan
    }])

df = df.sort_values("Score", ascending=False)

df.to_csv("ai_risk_filtered.csv", index=False, encoding="utf-8-sig")

df[df["Signal"].str.contains("BOTTOM", na=False)].to_csv(
    "bottom_common_priority.csv", index=False, encoding="utf-8-sig"
)

df[df["Signal"].str.contains("MOMENTUM", na=False)].to_csv(
    "momentum_common_priority.csv", index=False, encoding="utf-8-sig"
)

html = df.to_html(index=False)
html_full = f"""
<html>
<head><meta charset="utf-8"></head>
<body>
<h2>📊 REAL DATA TRADING DASHBOARD</h2>
<p>Generated: {datetime.now()}</p>
{html}
</body>
</html>
"""

with open("ai_risk_dashboard.html", "w", encoding="utf-8") as f:
    f.write(html_full)

print("✅ Created REAL DATA FILES")
print("Rows:", len(df))
print(df.head(10))
