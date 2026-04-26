import runpy
from datetime import datetime

print("🚀 RUN FULL COLAB SYSTEM")
print("⏰", datetime.now())

# chạy pipeline giống Colab

runpy.run_path("runner.py")

print("✅ DONE")
