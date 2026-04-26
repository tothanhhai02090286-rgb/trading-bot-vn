import os, sys
import pandas as pd
import numpy as np

from config import BOT_DIR
BOT_DIR = str(BOT_DIR)
if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)
os.chdir(BOT_DIR)

from universe import get_master_tickers
from portfolio import load_price

BUY_FINAL_PATH = f"{BOT_DIR}/buy_final_latest.csv"
OUT_ALL = f"{BOT_DIR}/momentum_backtest_result.csv"
OUT_SELECTED = f"{BOT_DIR}/momentum_backtest_selected_result.csv"
OUT_COMMON = f"{BOT_DIR}/momentum_common_priority.csv"

HOLD_DAYS = [3, 5, 10, 20]

def calc_rsi(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def normalize(df):
    df = df.copy()
    if "time" not in df.columns:
        if isinstance(df.index, pd.DatetimeIndex):
            df = df.reset_index().rename(columns={"index": "time"})
        elif "Date" in df.columns:
            df = df.rename(columns={"Date": "time"})
        elif "date" in df.columns:
            df = df.rename(columns={"date": "time"})
        else:
            return None

    df = df.rename(columns={
        "Open":"open", "High":"high", "Low":"low",
        "Close":"close", "Volume":"volume"
    })

    need = ["time","open","high","low","close","volume"]
    for c in need:
        if c not in df.columns:
            return None

    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    for c in ["open","high","low","close","volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    return df.dropna(subset=["time","close"]).sort_values("time").reset_index(drop=True)

def forward_return(close, i, d):
    if i + d >= len(close):
        return np.nan
    return (close.iloc[i+d] / close.iloc[i] - 1) * 100

def max_dd(close, i, d):
    end = min(i+d, len(close)-1)
    future = close.iloc[i+1:end+1]
    if future.empty:
        return np.nan
    return (future.min() / close.iloc[i] - 1) * 100

def build_signals(tickers):
    rows = []

    for idx, code in enumerate(tickers, 1):
        print(f"⏳ {idx}/{len(tickers)} - {code}")
        raw = load_price(code)
        df = normalize(raw)

        if df is None or len(df) < 80:
            continue

        close = df["close"]
        df["ma5"] = close.rolling(5).mean()
        df["ma20"] = close.rolling(20).mean()
        df["ma50"] = close.rolling(50).mean()
        df["rsi"] = calc_rsi(close)

        for i in range(60, len(df) - max(HOLD_DAYS) - 1):
            live = close.iloc[i]
            ma5 = df["ma5"].iloc[i]
            ma20 = df["ma20"].iloc[i]
            ma50 = df["ma50"].iloc[i]
            rsi = df["rsi"].iloc[i]

            if pd.isna(ma5) or pd.isna(ma20) or pd.isna(ma50) or pd.isna(rsi):
                continue

            dist_ma20 = (live / ma20 - 1) * 100

            signal = (
                live > ma20 and
                live > ma50 and
                ma20 > ma50 and
                55 <= rsi <= 75 and
                dist_ma20 <= 8 and
                live > ma5
            )

            if not signal:
                continue

            rec = {
                "Mã": code,
                "signal_date": df["time"].iloc[i].date(),
                "entry_price": round(float(live), 2),
                "rsi": round(float(rsi), 2),
                "ma5": round(float(ma5), 2),
                "ma20": round(float(ma20), 2),
                "ma50": round(float(ma50), 2),
                "dist_ma20": round(float(dist_ma20), 2),
            }

            for d in HOLD_DAYS:
                rec[f"return_{d}P_%"] = round(forward_return(close, i, d), 2)
                rec[f"max_dd_{d}P_%"] = round(max_dd(close, i, d), 2)

            rows.append(rec)

    return pd.DataFrame(rows)

def summarize(df):
    return df.groupby("Mã").agg(
        signals=("Mã","count"),
        winrate_5P=("return_5P_%", lambda x: round((x > 0).mean()*100, 2)),
        avg_return_5P=("return_5P_%","mean"),
        winrate_10P=("return_10P_%", lambda x: round((x > 0).mean()*100, 2)),
        avg_return_10P=("return_10P_%","mean"),
        avg_dd_5P=("max_dd_5P_%","mean")
    ).round(2).reset_index()

def run_backtest_momentum_all():
    print("🧪 BACKTEST MOMENTUM ALL START")
    tickers = get_master_tickers()
    result = build_signals(tickers)

    result.to_csv(OUT_ALL, index=False, encoding="utf-8-sig")

    stat = summarize(result)
    print(stat.sort_values(["winrate_5P","avg_return_5P"], ascending=False).head(30))
    print("💾 Saved:", OUT_ALL)
    return result

def load_today_momentum_codes():
    if not os.path.exists(BUY_FINAL_PATH):
        print("❌ chưa có buy_final_latest.csv")
        return []

    df = pd.read_csv(BUY_FINAL_PATH)
    df.columns = [str(c).strip() for c in df.columns]

    if "Mã" not in df.columns:
        return []

    df["score"] = pd.to_numeric(df.get("score", 0), errors="coerce").fillna(0)
    entry = df.get("entry", "").astype(str)
    signal = df.get("signal", "").astype(str)

    mask = (
        (
            entry.str.contains("BUY NOW", case=False, na=False) |
            entry.str.contains("TOO HOT", case=False, na=False) |
            signal.str.contains("MUA", case=False, na=False)
        )
        & (~signal.str.contains("BỎ QUA", case=False, na=False))
        & (df["score"] >= 45)
    )

    return df[mask]["Mã"].dropna().astype(str).str.upper().unique().tolist()

def run_backtest_momentum_selected():
    print("🧪 BACKTEST MOMENTUM SELECTED START")
    codes = load_today_momentum_codes()
    print("📌 Selected:", codes)

    result = build_signals(codes)
    result.to_csv(OUT_SELECTED, index=False, encoding="utf-8-sig")

    stat = summarize(result)
    print(stat.sort_values(["winrate_5P","avg_return_5P"], ascending=False))
    print("💾 Saved:", OUT_SELECTED)
    return result


def get_market_filter_mode():
    market_path = f"{BOT_DIR}/market_mode_clean.csv"
    if not os.path.exists(market_path):
        return "NORMAL", "Không có market_mode_clean.csv → dùng NORMAL"

    try:
        m = pd.read_csv(market_path)
        last = m.iloc[-1]

        score = pd.to_numeric(last.get("Điểm tổng hợp", last.get("Điểm thị trường", 0)), errors="coerce")
        mode = str(last.get("Chế độ thị trường", "")).upper()
        vn_rsi = pd.to_numeric(last.get("VNINDEX RSI", 50), errors="coerce")

        if pd.isna(score):
            score = 0
        if pd.isna(vn_rsi):
            vn_rsi = 50

        if score >= 80 and "TÍCH CỰC" in mode:
            return "STRICT", f"Thị trường mạnh: score={score}, mode={mode}, RSI={vn_rsi}"
        elif score >= 60:
            return "NORMAL", f"Thị trường trung bình/tích cực vừa: score={score}, mode={mode}, RSI={vn_rsi}"
        else:
            return "DEFENSIVE", f"Thị trường yếu: score={score}, mode={mode}, RSI={vn_rsi}"

    except Exception as e:
        return "NORMAL", f"Lỗi đọc market mode: {e} → dùng NORMAL"


def build_momentum_common_priority():
    all_bt = pd.read_csv(OUT_ALL)
    sel_bt = pd.read_csv(OUT_SELECTED)

    all_stat = summarize(all_bt)
    sel_stat = summarize(sel_bt)

    market_mode, market_note = get_market_filter_mode()

    print("📈 MARKET FILTER:", market_mode)
    print("📝", market_note)

    if market_mode == "STRICT":
        # Thị trường rất mạnh → lọc chặt
        all_min_signals = 30
        all_min_winrate = 55
        all_min_return = 0.5

        sel_min_signals = 10
        sel_min_winrate = 55
        sel_min_return = 0.3

    elif market_mode == "NORMAL":
        # Thị trường vừa → nới hợp lý
        all_min_signals = 20
        all_min_winrate = 52
        all_min_return = 0.0

        sel_min_signals = 5
        sel_min_winrate = 50
        sel_min_return = -0.1

    else:
        # Thị trường yếu → không cố mua momentum
        print("⚠️ Thị trường yếu → không tạo danh sách mua momentum.")
        common = pd.DataFrame(columns=[
            "Mã",
            "signals_selected", "winrate_5P_selected", "avg_return_5P_selected",
            "winrate_10P_selected", "avg_return_10P_selected", "avg_dd_5P_selected",
            "signals_universe", "winrate_5P_universe", "avg_return_5P_universe",
            "winrate_10P_universe", "avg_return_10P_universe", "avg_dd_5P_universe",
            "Chú thích"
        ])
        common.to_csv(OUT_COMMON, index=False, encoding="utf-8-sig")
        print("💾 Saved:", OUT_COMMON)
        return common

    all_top = all_stat[
        (all_stat["signals"] >= all_min_signals) &
        (all_stat["winrate_5P"] >= all_min_winrate) &
        (all_stat["avg_return_5P"] > all_min_return)
    ]

    sel_top = sel_stat[
        (sel_stat["signals"] >= sel_min_signals) &
        (sel_stat["winrate_5P"] >= sel_min_winrate) &
        (sel_stat["avg_return_5P"] > sel_min_return)
    ]

    common = sel_top.merge(
        all_top,
        on="Mã",
        suffixes=("_selected", "_universe")
    )

    if common.empty:
        print("⚠️ Không có mã momentum đạt chuẩn adaptive.")
        print("👉 Đây là tín hiệu đứng ngoài, không ép trade.")
    else:
        def note(r):
            if r["winrate_5P_selected"] >= 60 and r["avg_return_5P_selected"] >= 1:
                return f"🔥 ƯU TIÊN CAO | {market_mode}"
            elif r["winrate_5P_selected"] >= 55:
                return f"✅ ƯU TIÊN | {market_mode}"
            else:
                return f"👀 THEO DÕI | {market_mode}"

        common["Chú thích"] = common.apply(note, axis=1)

        common = common.sort_values(
            ["winrate_5P_selected", "avg_return_5P_selected"],
            ascending=False
        )

    common.to_csv(OUT_COMMON, index=False, encoding="utf-8-sig")

    print(common)
    print("💾 Saved:", OUT_COMMON)
    return common
