import os
import sys
import traceback
import pandas as pd

from config import BOT_DIR
BOT_DIR = str(BOT_DIR)
WATCHLIST_PATH = os.path.join(BOT_DIR, "watchlist_intraday.csv")

if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)

def run_eod(show_watchlist=True):
    print("🚀 EOD RUN START\n")
    os.chdir(BOT_DIR)

    try:
        from main_eod import format_eod_watchlist_report
        from system_core import run_v5_full_auto
        from watchlist_utils import save_watchlist_from_v5
        from telegram_utils import send_telegram

        print("📂 Working dir:", os.getcwd())

        v5 = run_v5_full_auto()
        if v5 is None:
            print("❌ V5 trả về None")
            return None

        watchlist = save_watchlist_from_v5(v5, min_wait_score=70)

        msg = format_eod_watchlist_report(watchlist)
        ok = send_telegram(msg)

        print("\n" + "=" * 60)
        print("📌 EOD RESULT")
        print("=" * 60)
        print("📤 Telegram:", "OK" if ok else "FAIL")
        print("📄 Watchlist file:", WATCHLIST_PATH)
        print("📊 Watchlist rows:", 0 if watchlist is None else len(watchlist))

        if show_watchlist:
            print("\n" + "-" * 60)
            print("📋 WATCHLIST PREVIEW")
            print("-" * 60)
            if watchlist is None or watchlist.empty:
                print("Không có watchlist.")
            else:
                cols = [c for c in ["Mã", "group_type", "entry", "signal", "score", "base_price"] if c in watchlist.columns]
                print(watchlist[cols].to_string(index=False))

        print("\n✅ EOD RUN DONE")
        return {
            "v5": v5,
            "watchlist": watchlist,
            "telegram_ok": ok,
            "watchlist_path": WATCHLIST_PATH
        }

    except Exception as e:
        print("❌ EOD RUN ERROR:", e)
        print(traceback.format_exc())
        return None

def run_daily_full(show_watchlist=True):
    print("🚀 DAILY FULL RUN START\n")
    os.chdir(BOT_DIR)

    try:
        from data_engine import run_engine

        print("📡 STEP 1: update toàn bộ dữ liệu market + universe")
        engine_result = run_engine()

        print("\n📊 STEP 2: chạy EOD")
        eod_result = run_eod(show_watchlist=show_watchlist)

        return {
            "engine": engine_result,
            "eod": eod_result
        }

    except Exception as e:
        print("❌ DAILY FULL RUN ERROR:", e)
        print(traceback.format_exc())
        return None

def show_watchlist():
    os.chdir(BOT_DIR)

    if not os.path.exists(WATCHLIST_PATH):
        print("❌ Chưa có watchlist_intraday.csv")
        return None

    df = pd.read_csv(WATCHLIST_PATH)
    print(df.to_string(index=False))
    return df

def run_intraday_once():
    os.chdir(BOT_DIR)

    from watchlist_utils import load_watchlist
    from live_price_provider import get_live_price_map_pro

    watchlist = load_watchlist()
    if watchlist is None or watchlist.empty:
        print("❌ Watchlist rỗng")
        return None

    codes = watchlist["Mã"].dropna().astype(str).tolist()
    live_map = get_live_price_map_pro(codes)

    print("📡 Live map:", live_map)
    return live_map
