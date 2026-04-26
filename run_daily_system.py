import pandas as pd
from datetime import datetime

print("🚀 RUN DAILY SYSTEM")

df = pd.DataFrame({
    "Stock": ["VNM", "FPT", "HPG"],
    "Signal": ["BUY", "HOLD", "SELL"],
    "Score": [85, 60, 40],
    "Time": [datetime.now()] * 3
})

df.to_csv("ai_risk_filtered.csv", index=False)

print("✅ Created ai_risk_filtered.csv")
