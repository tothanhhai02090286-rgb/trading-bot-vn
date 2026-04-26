import pandas as pd
import numpy as np
from datetime import datetime

print("🚀 RUN LIGHT TRADING SYSTEM")

# ===== Danh sách mã VN (nhẹ) =====
tickers = ["VNM", "FPT", "HPG", "MWG", "VCB", "SSI"]

rows = []

for t in tickers:
    # giả lập dữ liệu giá gần đây (logic thật nhẹ)
    prices = np.random.normal(100, 5, 20)

    ma5 = prices[-5:].mean()
    ma20 = prices.mean()

    rsi = np.random.uniform(30, 70)

    # ===== Logic momentum =====
    if ma5 > ma20 and rsi > 50:
        signal = "🚀 MOMENTUM"
        score = 80 + np.random.randint(0, 10)

    # ===== Logic bắt đáy =====
    elif rsi < 40:
        signal = "🧲 BOTTOM"
        score = 70 + np.random.randint(0, 10)

    else:
        signal = "👀 WATCH"
        score = 50 + np.random.randint(0, 10)

    rows.append({
        "Ngày": datetime.now().strftime("%Y-%m-%d"),
        "Mã": t,
        "Signal": signal,
        "Score": score,
        "RSI": round(rsi, 2),
        "MA5": round(ma5, 2),
        "MA20": round(ma20, 2)
    })

df = pd.DataFrame(rows)

# ===== Lưu file chính =====
df.to_csv("ai_risk_filtered.csv", index=False, encoding="utf-8-sig")

# ===== Bottom =====
df[df["Signal"].str.contains("BOTTOM")].to_csv(
    "bottom_common_priority.csv", index=False, encoding="utf-8-sig"
)

# ===== Momentum =====
df[df["Signal"].str.contains("MOMENTUM")].to_csv(
    "momentum_common_priority.csv", index=False, encoding="utf-8-sig"
)

# ===== HTML =====
html = df.to_html(index=False)

html_full = f"""
<html>
<head><meta charset="utf-8"></head>
<body>
<h2>📊 Trading Dashboard</h2>
{html}
</body>
</html>
"""

with open("ai_risk_dashboard.html", "w", encoding="utf-8") as f:
    f.write(html_full)

print("✅ Created ALL FILES")
