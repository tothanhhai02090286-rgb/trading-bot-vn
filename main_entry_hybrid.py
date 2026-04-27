import pandas as pd
from datetime import datetime

print("📋 ENTRY PLAN START")

# ===== LOAD =====
try:
    bottom = pd.read_csv("bottom_common_priority.csv")
except:
    bottom = pd.DataFrame()

try:
    momentum = pd.read_csv("momentum_common_priority.csv")
except:
    momentum = pd.DataFrame()

rows = []

# ===== FROM BOTTOM =====
if not bottom.empty:
    for _, r in bottom.head(5).iterrows():
        rows.append({
            "Ngày": datetime.now().strftime("%Y-%m-%d"),
            "Mã": r.get("Mã", "UNK"),
            "Action": "BUY",
            "Chiến lược": "BOTTOM",
            "Score": r.get("Score", 50)
        })

# ===== FROM MOMENTUM =====
if not momentum.empty:
    for _, r in momentum.head(5).iterrows():
        rows.append({
            "Ngày": datetime.now().strftime("%Y-%m-%d"),
            "Mã": r.get("Mã", "UNK"),
            "Action": "BUY",
            "Chiến lược": "MOMENTUM",
            "Score": r.get("Score", 50)
        })

# ===== FALLBACK =====
if len(rows) == 0:
    rows.append({
        "Ngày": datetime.now().strftime("%Y-%m-%d"),
        "Mã": "NO_DATA",
        "Action": "WAIT",
        "Chiến lược": "SYSTEM",
        "Score": 0
    })

df = pd.DataFrame(rows)

# ===== SAVE =====
df.to_csv("entry_plan_next_session.csv", index=False, encoding="utf-8-sig")

print("✅ CREATED entry_plan_next_session.csv")
print(df.head())
