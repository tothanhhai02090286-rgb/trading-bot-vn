import os
import sys
import runpy
import pandas as pd
from datetime import datetime, time as dtime

from config import BOT_DIR
BOT_DIR = str(BOT_DIR)
if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)

os.chdir(BOT_DIR)

print("🚀 RUN DAILY SYSTEM START")
print("⏰", datetime.now())

def is_trading_time():
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    return (dtime(9, 0) <= now.time() <= dtime(11, 30)) or (dtime(13, 0) <= now.time() <= dtime(14, 45))

def build_bottom_common_priority_inline():
    all_path = f"{BOT_DIR}/bottom_backtest_result.csv"
    sel_path = f"{BOT_DIR}/bottom_backtest_selected_result.csv"
    out_path = f"{BOT_DIR}/bottom_common_priority.csv"

    if not os.path.exists(all_path) or not os.path.exists(sel_path):
        print("⚠️ Thiếu file backtest bottom để tạo common")
        return pd.DataFrame()

    all_bt = pd.read_csv(all_path)
    sel_bt = pd.read_csv(sel_path)

    def stat(df):
        return df.groupby("Mã").agg(
            signals=("Mã", "count"),
            winrate_5P=("return_5P_%", lambda x: round((x > 0).mean() * 100, 2)),
            avg_return_5P=("return_5P_%", "mean"),
            winrate_10P=("return_10P_%", lambda x: round((x > 0).mean() * 100, 2)),
            avg_return_10P=("return_10P_%", "mean"),
            avg_dd_5P=("max_dd_5P_%", "mean")
        ).round(2).reset_index()

    all_stat = stat(all_bt)
    sel_stat = stat(sel_bt)

    all_top = all_stat[
        (all_stat["signals"] >= 50) &
        (all_stat["winrate_5P"] >= 55) &
        (all_stat["avg_return_5P"] > 0.8)
    ]

    sel_top = sel_stat[
        (sel_stat["signals"] >= 50) &
        (sel_stat["winrate_5P"] >= 55) &
        (sel_stat["avg_return_5P"] > 0.3)
    ]

    common = sel_top.merge(
        all_top,
        on="Mã",
        suffixes=("_selected", "_universe")
    )

    if not common.empty:
        common["Chú thích"] = common.apply(
            lambda r: "🔥 ƯU TIÊN CAO" if r["winrate_5P_selected"] >= 60 and r["avg_return_5P_selected"] >= 1 else "✅ ƯU TIÊN",
            axis=1
        )

        common = common.sort_values(
            ["winrate_5P_selected", "avg_return_5P_selected"],
            ascending=False
        )

    common.to_csv(out_path, index=False, encoding="utf-8-sig")
    print("💾 Saved:", out_path)
    print(common)

    return common

# STEP 1
try:
    print("\n📊 STEP 1: UPDATE DATA + EOD")
    from runner import run_daily_full
    run_daily_full()
except Exception as e:
    print("❌ STEP 1 FAIL:", e)

# STEP 2
try:
    print("\n🧲 STEP 2: RUN BOTTOM BOT")
    runpy.run_path(f"{BOT_DIR}/main_bottom.py")
except Exception as e:
    print("❌ STEP 2 FAIL:", e)

# STEP 3
try:
    print("\n🧪 STEP 3: BACKTEST BOTTOM SELECTED")
    if "backtest_bottom_selected" in sys.modules:
        del sys.modules["backtest_bottom_selected"]

    from backtest_bottom_selected import run_backtest_bottom_selected
    run_backtest_bottom_selected(min_score=45)

    build_bottom_common_priority_inline()
except Exception as e:
    print("❌ STEP 3 FAIL:", e)

# STEP 4
try:
    print("\n🚀 STEP 4: BACKTEST MOMENTUM")
    if "backtest_momentum" in sys.modules:
        del sys.modules["backtest_momentum"]

    from backtest_momentum import run_backtest_momentum_selected, build_momentum_common_priority
    run_backtest_momentum_selected()
    build_momentum_common_priority()
except Exception as e:
    print("❌ STEP 4 FAIL:", e)

# STEP 5
try:
    print("\n📋 STEP 5: ENTRY PLAN")
    if is_trading_time():
        print("⚠️ Đang trong phiên → bỏ qua entry plan để tránh chạy intraday loop")
    else:
        runpy.run_path(f"{BOT_DIR}/main_entry_hybrid.py")
except Exception as e:
    print("❌ STEP 5 FAIL:", e)

print("\n✅ DAILY SYSTEM DONE")
