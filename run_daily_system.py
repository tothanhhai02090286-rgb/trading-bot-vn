import runpy
from datetime import datetime

print("🚀 RUN DAILY SYSTEM START")
print("⏰", datetime.now())

try:
    runpy.run_path("runner.py", run_name="__main__")
    print("✅ DAILY SYSTEM DONE")
except Exception as e:
    print("❌ DAILY SYSTEM ERROR:", repr(e))
    raise
