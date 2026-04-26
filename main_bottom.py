import os
import sys
import pandas as pd

from config import BOT_DIR
BOT_DIR = str(BOT_DIR)

if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)

os.chdir(BOT_DIR)

from bottom_bot import run_bottom_bot

print("🧲 MAIN BOTTOM BOT START")

# chạy bot bắt đáy
bottom = run_bottom_bot(top_n=50)

if bottom is None or bottom.empty:
    print("❌ Không có mã bắt đáy phù hợp")
else:
    df = bottom.copy()

    # làm tròn điểm cho dễ nhìn
    for c in ["bottom_score", "price", "rsi", "rsi_rebound", "drawdown20", "ret1", "ret3", "ret5", "vol_ratio", "close_pos_day"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").round(2)

    # top hồi đẹp nhất
    top = df[
        df["Nhóm"].isin(["🟢 BẮT ĐÁY TỐT", "🟡 THEO DÕI HỒI"])
    ].copy()

    top = top.sort_values(
        ["bottom_score", "rsi_rebound", "close_pos_day", "vol_ratio"],
        ascending=[False, False, False, False]
    ).head(10)

    print("\n" + "="*70)
    print("🔥 TOP MÃ BẮT ĐÁY / HỒI ĐẸP NHẤT")
    print("="*70)

    if top.empty:
        print("⚠️ Chưa có mã hồi đủ đẹp.")
    else:
        print(top[[
            "date", "Mã", "Nhóm", "bottom_score", "price",
            "rsi", "rsi_rebound", "drawdown20",
            "ret1", "ret3", "ret5",
            "vol_ratio", "close_pos_day", "Lý do"
        ]].to_string(index=False))

        top.to_csv(
            "{BOT_DIR}/bottom_top_today.csv",
            index=False,
            encoding="utf-8-sig"
        )

        print("\n💾 Đã lưu TOP:", "{BOT_DIR}/bottom_top_today.csv")

    print("\n" + "="*70)
    print("📋 FULL LIST BẮT ĐÁY")
    print("="*70)

    view = df[[
        "date", "Mã", "Nhóm", "bottom_score", "price",
        "rsi", "rsi_rebound", "drawdown20",
        "ret1", "ret3", "ret5",
        "vol_ratio", "close_pos_day", "Lý do"
    ]].head(50)

    print(view.to_string(index=False))

    print("\n💾 Full list:", "{BOT_DIR}/bottom_candidates.csv")
