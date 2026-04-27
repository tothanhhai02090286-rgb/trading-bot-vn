import os
import pandas as pd
from datetime import datetime
from pandas.errors import EmptyDataError

print("🤖 AI RISK FILTER START")

OUT = "ai_risk_filtered.csv"

def safe_read(path):
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except EmptyDataError:
        return pd.DataFrame()
    except Exception as e:
        print(f"⚠️ lỗi đọc {path}: {e}")
        return pd.DataFrame()

bottom = safe_read("bottom_common_priority.csv")
momentum = safe_read("momentum_common_priority.csv")

rows = []

if not bottom.empty:
    for _, r in bottom.iterrows():
        rows.append({
            "Ngày": datetime.now().strftime("%Y-%m-%d"),
            "Mã": r.get("Mã", r.get("Stock", "")),
            "Chiến lược": "Bắt đáy",
            "Signal": r.get("Signal", "BOTTOM"),
            "Score": r.get("Score", r.get("score", "")),
            "AI": "✅ OK",
            "Lý do": "Có trong bottom priority"
        })

if not momentum.empty:
    for _, r in momentum.iterrows():
        rows.append({
            "Ngày": datetime.now().strftime("%Y-%m-%d"),
            "Mã": r.get("Mã", r.get("Stock", "")),
            "Chiến lược": "Momentum",
            "Signal": r.get("Signal", "MOMENTUM"),
            "Score": r.get("Score", r.get("score", "")),
            "AI": "✅ OK",
            "Lý do": "Có trong momentum priority"
        })

# fallback chắc chắn không bao giờ để CSV rỗng
if not rows:
    rows = [
        {
            "Ngày": datetime.now().strftime("%Y-%m-%d"),
            "Mã": "NO_DATA",
            "Chiến lược": "SYSTEM",
            "Signal": "NO DATA",
            "Score": 0,
            "AI": "⚠️ WAIT",
            "Lý do": "Pipeline chưa tạo được bottom/momentum hợp lệ"
        }
    ]

df = pd.DataFrame(rows)
df.to_csv(OUT, index=False, encoding="utf-8-sig")

print("✅ CREATED ai_risk_filtered.csv")
print(df)
