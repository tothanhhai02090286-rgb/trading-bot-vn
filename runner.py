import os
import runpy
from datetime import datetime

print("🚀 RUNNER START")
print("⏰", datetime.now())
print("📂 Current dir:", os.getcwd())
print("📁 Files:", os.listdir("."))

steps = [
    ("main_bottom.py", "🧲 MAIN BOTTOM"),
    ("backtest_bottom_selected.py", "🧪 BACKTEST BOTTOM SELECTED"),
    ("backtest_momentum.py", "🚀 BACKTEST MOMENTUM"),
    ("main_entry_hybrid.py", "📋 ENTRY PLAN"),
    ("dashboard_decision.py", "📊 DASHBOARD DECISION"),
    ("ai_risk_filter.py", "🤖 AI RISK FILTER"),
    ("create_html.py", "🌐 CREATE HTML"),
]

for file, name in steps:
    print("\n" + "=" * 60)
    print(f"▶️ STEP: {name}")
    print(f"📄 File: {file}")

    if not os.path.exists(file):
        print(f"⚠️ SKIP: không thấy {file}")
        continue

    try:
        runpy.run_path(file, run_name="__main__")
        print(f"✅ DONE: {file}")
    except Exception as e:
        print(f"❌ ERROR tại {file}: {repr(e)}")
        print("⚠️ Tiếp tục bước sau, không dừng toàn hệ.")

print("\n✅ RUNNER FINISHED")
