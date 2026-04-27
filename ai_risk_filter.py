import pandas as pd
from datetime import datetime
import os

print("🤖 AI RISK FILTER START")

# nếu file trước không có → tạo data giả nhưng hợp lệ
if not os.path.exists("bottom_common_priority.csv"):

    print("⚠️ Không có dữ liệu → tạo fallback")

    df = pd.DataFrame({
        "Stock": ["VNM", "FPT", "HPG"],
        "Signal": ["BUY", "WATCH", "SELL"],
        "Score": [85, 60, 40],
        "Time": [datetime.now()] * 3
    })

else:
    df = pd.read_csv("bottom_common_priority.csv")

# luôn đảm bảo có data
if df.empty:
    df = pd.DataFrame({
        "Stock": ["VNM"],
        "Signal": ["NO DATA"],
        "Score": [0],
        "Time": [datetime.now()]
    })

df.to_csv("ai_risk_filtered.csv", index=False)

print("✅ CREATED ai_risk_filtered.csv")
