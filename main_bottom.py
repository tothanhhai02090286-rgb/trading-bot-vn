import pandas as pd
import numpy as np
from datetime import datetime

print("🧲 RUN SIMPLE BOTTOM")

stocks = [
    "VNM","FPT","HPG","VCB","CTG","MBB","VPB","TCB",
    "SSI","VND","HCM","PNJ","MWG","GAS","PLX","REE"
]

rows = []

for s in stocks:
    rsi = np.random.uniform(20, 70)
    score = int(100 - rsi)

    if rsi < 40:
        signal = "BOTTOM"
    elif rsi < 55:
        signal = "WATCH"
    else:
        signal = "SKIP"

    rows.append({
        "Ngày": datetime.now().strftime("%Y-%m-%d"),
        "Mã": s,
        "Signal": signal,
        "Score": score,
        "RSI": round(rsi,2)
    })

df = pd.DataFrame(rows)

# lọc top cơ hội
df = df[df["Signal"] != "SKIP"].sort_values("Score", ascending=False)

df.to_csv("bottom_common_priority.csv", index=False)

print("✅ CREATED bottom_common_priority.csv")
print(df.head())
