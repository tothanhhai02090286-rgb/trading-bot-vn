import os
from pathlib import Path

BOT_DIR = Path(os.getenv("BOT_DIR", ".")).resolve()
OUTPUT_DIR = BOT_DIR / "outputs"
DATA_DIR = BOT_DIR / "data"

OUTPUT_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
