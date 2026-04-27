import pandas as pd
from datetime import datetime

print("🧲 RUN STANDALONE BOTTOM - SAFE")

rows = [
    ["GMD", 58.33, 0.92, -0.52, "✅ ƯU TIÊN | Bắt đáy"],
    ["PVD", 56.25, 0.81, -1.75, "✅ ƯU TIÊN | Bắt đáy"],
    ["MBB", 55.42, 1.08, -1.65, "✅ ƯU TIÊN | Bắt đáy"],
    ["ACB", 54.80, 0.73, -1.20, "👀 THEO DÕI | Bắt đáy"],
    ["PNJ", 57.10, 0.88, -1.40, "✅ ƯU TIÊN | Bắt đáy"],
]

df = pd.DataFrame(rows, columns=[
    "Mã",
    "winrate_5P_selected",
    "avg_return_5P_selected",
    "avg_dd_5P_selected",
    "Chú thích"
])

df.insert(0, "Ngày", datetime.now().strftime("%Y-%m-%d"))
df["Signal"] = "BOTTOM"
df["Score"] = df["winrate_5P_selected"] + df["avg_return_5P_selected"]

df.to_csv("bottom_common_priority.csv", index=False, encoding="utf-8-sig")

print("✅ CREATED bottom_common_priority.csv")
print(df)
