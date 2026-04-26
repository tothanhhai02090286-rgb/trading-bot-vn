import pandas as pd
from pathlib import Path
from datetime import datetime
from config import BOT_DIR

BOT_DIR = str(BOT_DIR)

csv_path = f"{BOT_DIR}/ai_risk_filtered.csv"
html_path = f"{BOT_DIR}/ai_risk_dashboard.html"

df = pd.read_csv(csv_path)

html = df.to_html(index=False)

html_full = f"""
<html>
<head>
<meta charset="utf-8">
<title>AI Risk Dashboard</title>
</head>
<body>
<h2>🤖 AI RISK DASHBOARD</h2>
<p>{datetime.now()}</p>
{html}
</body>
</html>
"""

Path(html_path).write_text(html_full, encoding="utf-8")
print("🌐 Saved:", html_path)
