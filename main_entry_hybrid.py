import pandas as pd
from datetime import datetime

print("📋 RUN ENTRY PLAN (SAFE MODE)")

rows = [
    ["GMD", "BUY", 0.2, "Ưu tiên cao"],
    ["PVD", "BUY", 0.15, "Có tín hiệu"],
    ["VHM", "WAIT", 0.1, "Theo dõi"],
    ["TCB", "BUY", 0.15, "Momentum mạnh"],
    ["MBB", "WAIT", 0.1, "Chờ xác nhận"],
]

df = pd.DataFrame(rows, columns=[
    "Mã",
    "Action",
    "Tỷ trọng",
    "Ghi chú"
])

df.insert(0, "Ngày", datetime.now().strftime("%Y-%m-%d"))

df.to_csv("entry_plan_next_session.csv", index=False, encoding="utf-8-sig")

print("✅ CREATED entry_plan_next_session.csv")
print(df)
