# -*- coding: utf-8 -*-
"""
V19.4.1 — SIGNAL FAMILY COMPARISON ENGINE VI
============================================

Bản nâng cấp V19.4:
- So sánh Breakout family: BREAKOUT_5D / 10D / 20D
- So sánh Pullback family: PULLBACK_MA5 / MA10 / MA20
- So sánh Relative Strength family: RS5 / RS10 / RS20
- So sánh Volume filter family: VOL_FILTER_1.2 / 1.5 / 2.0

Mục tiêu:
- Kiểm chứng nhóm tín hiệu nào hiệu quả hơn.
- Không tối ưu học vẹt bằng cách trộn quá nhiều tham số.
- Giữ kiểm soát:
  + Không look-ahead
  + Entry T+1 open
  + Fee + slippage
  + T+2.5
  + Liquidity filter
  + Regime split
  + Cooldown
  + Daily cap
  + Baseline VNINDEX

Input:
- cache_stock/*.csv
- cache_stock/VNINDEX.csv nếu có

Output:
- tracker_output/v194_historical_signal_validation.csv
- tracker_output/v194_signal_stats.csv
- tracker_output/v194_family_compare.csv
- tracker_output/v194_regime_stats.csv
- tracker_output/v194_baseline_comparison.csv
- tracker_output/v194_bad_signal_patterns.csv
- tracker_output/v194_report.txt
"""

from __future__ import annotations

import os
import glob
import math
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

SYSTEM_VERSION = "V19.4.1_SIGNAL_FAMILY_COMPARISON_ENGINE_VI"

CACHE_DIR = os.getenv("V194_CACHE_DIR", "cache_stock")
OUTPUT_DIR = os.getenv("V194_OUTPUT_DIR", "tracker_output")
BENCHMARK_SYMBOL = os.getenv("V194_BENCHMARK_SYMBOL", "VNINDEX")

MIN_HISTORY_BARS = int(os.getenv("V194_MIN_HISTORY_BARS", "80"))
MAIN_HORIZON = int(os.getenv("V194_MAIN_HORIZON", "5"))
HORIZONS = [1, 3, 5, 10]

VN_TPLUS_SELLABLE_DAYS = float(os.getenv("V194_VN_TPLUS_SELLABLE_DAYS", "2.5"))
MIN_EXIT_HOLD_BARS = int(math.ceil(VN_TPLUS_SELLABLE_DAYS))

BUY_SLIPPAGE_PCT = float(os.getenv("V194_BUY_SLIPPAGE_PCT", "0.15"))
SELL_SLIPPAGE_PCT = float(os.getenv("V194_SELL_SLIPPAGE_PCT", "0.15"))
FEE_PCT_PER_SIDE = float(os.getenv("V194_FEE_PCT_PER_SIDE", "0.15"))

MIN_AVG_VOLUME_20 = float(os.getenv("V194_MIN_AVG_VOLUME_20", "100000"))
MIN_CLOSE_PRICE = float(os.getenv("V194_MIN_CLOSE_PRICE", "3.0"))

SIGNAL_COOLDOWN_DAYS = int(os.getenv("V194_SIGNAL_COOLDOWN_DAYS", "5"))
MAX_SIGNALS_PER_DAY = int(os.getenv("V194_MAX_SIGNALS_PER_DAY", "30"))

BREAKOUT_LOOKBACKS = [5, 10, 20]
PULLBACK_MAS = [5, 10, 20]
RS_LOOKBACKS = [5, 10, 20]
VOLUME_FILTERS = [1.2, 1.5, 2.0]

RS_MIN = float(os.getenv("V194_RS_MIN", "0.0"))
PULLBACK_TOLERANCE_PCT = float(os.getenv("V194_PULLBACK_TOLERANCE_PCT", "2.0"))
MAX_EXTENDED_ABOVE_MA20_PCT = float(os.getenv("V194_MAX_EXTENDED_ABOVE_MA20_PCT", "8.0"))


def log(msg: str) -> None:
    print(f"[V19.4.1] {msg}", flush=True)


def to_num(x: Any, default=np.nan) -> float:
    try:
        if x is None:
            return default
        if isinstance(x, str):
            x = x.replace("%", "").replace(",", ".").strip()
            if not x:
                return default
        v = pd.to_numeric(pd.Series([x]), errors="coerce").iloc[0]
        return default if pd.isna(v) else float(v)
    except Exception:
        return default


def normalize_price(x: Any) -> float:
    v = to_num(x)
    if pd.isna(v):
        return np.nan
    if v > 1000:
        v /= 1000.0
    return float(v)


def find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    lower = {str(c).lower(): c for c in df.columns}
    for c in candidates:
        if c in df.columns:
            return c
        if c.lower() in lower:
            return lower[c.lower()]
    return None


def read_csv_smart(path: str) -> pd.DataFrame:
    for enc in ["utf-8-sig", "utf-8", "cp1258", "latin1"]:
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            pass
    return pd.read_csv(path)


def normalize_history(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    date_col = find_col(df, ["date", "time", "Date", "datetime", "TradingDate", "Ngày"])
    open_col = find_col(df, ["open", "Open", "Giá mở cửa"])
    high_col = find_col(df, ["high", "High", "Giá cao nhất"])
    low_col = find_col(df, ["low", "Low", "Giá thấp nhất"])
    close_col = find_col(df, ["close", "Close", "adj_close", "price", "Giá đóng cửa"])
    vol_col = find_col(df, ["volume", "Volume", "vol", "Khối lượng"])

    if close_col is None:
        return pd.DataFrame()

    out = pd.DataFrame()
    out["date"] = pd.to_datetime(df[date_col], errors="coerce") if date_col else pd.date_range("2000-01-01", periods=len(df))
    out["close"] = pd.to_numeric(df[close_col], errors="coerce").apply(normalize_price)
    out["open"] = pd.to_numeric(df[open_col], errors="coerce").apply(normalize_price) if open_col else out["close"]
    out["high"] = pd.to_numeric(df[high_col], errors="coerce").apply(normalize_price) if high_col else out["close"]
    out["low"] = pd.to_numeric(df[low_col], errors="coerce").apply(normalize_price) if low_col else out["close"]
    out["volume"] = pd.to_numeric(df[vol_col], errors="coerce").fillna(0) if vol_col else 0

    out = out.dropna(subset=["date", "open", "high", "low", "close"]).copy()
    out = out[out["close"] > 0].copy()
    out["high"] = out[["open", "high", "low", "close"]].max(axis=1)
    out["low"] = out[["open", "high", "low", "close"]].min(axis=1)
    out = out.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)
    return out


def add_indicators(df: pd.DataFrame, benchmark: pd.DataFrame | None = None) -> pd.DataFrame:
    out = df.copy()
    c = out["close"]
    v = out["volume"]

    for ma in [5, 10, 20, 50]:
        out[f"ma{ma}"] = c.rolling(ma).mean()

    out["vol_ma20"] = v.rolling(20).mean()
    out["volume_ratio"] = np.where(out["vol_ma20"] > 0, v / out["vol_ma20"], np.nan)

    for lb in [5, 10, 20]:
        out[f"ret{lb}"] = c.pct_change(lb) * 100
        out[f"high{lb}_prev"] = out["high"].rolling(lb).max().shift(1)

    delta = c.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = np.where(loss > 0, gain / loss, np.nan)
    out["rsi14"] = 100 - 100 / (1 + rs)

    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    out["macd_hist"] = macd - macd.ewm(span=9, adjust=False).mean()
    out["macd_hist_up"] = out["macd_hist"] > out["macd_hist"].shift(1)

    prev_close = c.shift(1)
    tr = pd.concat([(out["high"] - out["low"]).abs(), (out["high"] - prev_close).abs(), (out["low"] - prev_close).abs()], axis=1).max(axis=1)
    out["atr14"] = tr.rolling(14).mean()
    out["atr_pct"] = np.where(c > 0, out["atr14"] / c * 100, np.nan)

    out["dist_ma5_pct"] = np.where(out["ma5"] > 0, (c / out["ma5"] - 1) * 100, np.nan)
    out["dist_ma10_pct"] = np.where(out["ma10"] > 0, (c / out["ma10"] - 1) * 100, np.nan)
    out["dist_ma20_pct"] = np.where(out["ma20"] > 0, (c / out["ma20"] - 1) * 100, np.nan)

    if benchmark is not None and not benchmark.empty:
        b = benchmark[["date", "close"]].rename(columns={"close": "bench_close"})
        out = out.merge(b, on="date", how="left")
        for lb in RS_LOOKBACKS:
            out[f"bench_ret{lb}"] = out["bench_close"].pct_change(lb) * 100
            out[f"rs{lb}"] = out[f"ret{lb}"] - out[f"bench_ret{lb}"]
    else:
        for lb in RS_LOOKBACKS:
            out[f"rs{lb}"] = out[f"ret{lb}"]

    return out


def build_regime(benchmark: pd.DataFrame) -> pd.DataFrame:
    if benchmark is None or benchmark.empty:
        return pd.DataFrame()
    b = add_indicators(benchmark, None)
    score = pd.Series(0.0, index=b.index)
    score += np.where(b["close"] > b["ma20"], 25, 0)
    score += np.where(b["ma20"] > b["ma50"], 25, 0)
    score += np.where(b["ret20"] > 0, 20, 0)
    score += np.where(b["ret5"] > 0, 10, 0)
    score += np.where(b["rsi14"] > 50, 10, 0)
    score += np.where(b["volume_ratio"] > 1.0, 10, 0)
    b["regime_score"] = score.clip(0, 100)
    b["regime"] = np.select(
        [b["regime_score"] >= 75, b["regime_score"] >= 60, b["regime_score"] >= 45, b["regime_score"] >= 30],
        ["TĂNG MẠNH", "TÍCH CỰC", "BÌNH THƯỜNG", "YẾU"],
        default="RẤT YẾU",
    )
    return b[["date", "regime", "regime_score", "close"]].rename(columns={"close": "benchmark_close"})


def load_benchmark() -> pd.DataFrame:
    for name in [BENCHMARK_SYMBOL, "VNINDEX", "VN30"]:
        path = os.path.join(CACHE_DIR, f"{name}.csv")
        if os.path.exists(path):
            df = normalize_history(read_csv_smart(path))
            if not df.empty:
                log(f"Loaded benchmark {path}")
                return df
    log("No benchmark found. Regime = UNKNOWN.")
    return pd.DataFrame()


def symbol_from_path(path: str) -> str:
    return Path(path).stem.upper().strip()


def liquidity_ok(row: pd.Series) -> bool:
    return row["close"] >= MIN_CLOSE_PRICE and row["vol_ma20"] >= MIN_AVG_VOLUME_20


def signal_meta(signal: str) -> Tuple[str, str]:
    if signal.startswith("BREAKOUT_"):
        return "BREAKOUT", signal.replace("BREAKOUT_", "")
    if signal.startswith("PULLBACK_"):
        return "PULLBACK", signal.replace("PULLBACK_", "")
    if signal.startswith("RS") and signal.endswith("_MOMENTUM"):
        return "RELATIVE_STRENGTH", signal.replace("_MOMENTUM", "")
    if signal.startswith("VOL_FILTER_"):
        return "VOLUME_FILTER", signal.replace("VOL_FILTER_", "")
    return "OTHER", signal


def detect_signals(row: pd.Series, prev: pd.Series) -> List[Tuple[str, float, str]]:
    signals: List[Tuple[str, float, str]] = []

    # 1. Breakout family: 5D / 10D / 20D
    for lb in BREAKOUT_LOOKBACKS:
        high_col = f"high{lb}_prev"
        rs_col = "rs20"
        if high_col not in row or pd.isna(row[high_col]):
            continue
        cond = (
            row["close"] > row[high_col]
            and row["close"] > row["ma20"]
            and row["volume_ratio"] >= 1.5
            and row[rs_col] >= RS_MIN
            and row["dist_ma20_pct"] <= MAX_EXTENDED_ABOVE_MA20_PCT
        )
        if cond:
            score = 50 + min(max(row["volume_ratio"] - 1, 0), 2) * 10 + min(max(row[rs_col], 0), 20)
            score += 10 if row["macd_hist_up"] else 0
            if lb == 5:
                score -= 3
            elif lb == 20:
                score += 3
            signals.append((f"BREAKOUT_{lb}D", float(max(0, min(100, score))), f"Vượt đỉnh {lb} phiên"))

    # 2. Pullback family: MA5 / MA10 / MA20
    for ma in PULLBACK_MAS:
        ma_col = f"ma{ma}"
        dist_col = f"dist_ma{ma}_pct"
        if ma_col not in row or pd.isna(row[ma_col]):
            continue
        trend_ok = row["ma20"] >= row["ma50"] if not pd.isna(row["ma50"]) else False
        cond = (
            abs(row[dist_col]) <= PULLBACK_TOLERANCE_PCT
            and row["close"] >= row[ma_col] * 0.98
            and trend_ok
            and row["close"] > prev["close"]
            and row["rsi14"] >= 45
            and row["volume_ratio"] >= 1.1
            and row["rs20"] >= RS_MIN
        )
        if cond:
            score = 50 + min(max(row["rs20"], 0), 20)
            score += 10 if row["macd_hist_up"] else 0
            score -= abs(row[dist_col]) * 1
            signals.append((f"PULLBACK_MA{ma}", float(max(0, min(100, score))), f"Pullback MA{ma} trong trend tốt"))

    # 3. Relative strength family: RS5 / RS10 / RS20
    for lb in RS_LOOKBACKS:
        rs_col = f"rs{lb}"
        ret_col = f"ret{lb}"
        if rs_col not in row or pd.isna(row[rs_col]):
            continue
        cond = (
            row[rs_col] >= 5
            and row["close"] > row["ma20"]
            and row["ma20"] > row["ma50"]
            and row[ret_col] > 0
            and row["volume_ratio"] >= 1.0
            and row["dist_ma20_pct"] <= MAX_EXTENDED_ABOVE_MA20_PCT
        )
        if cond:
            score = 50 + min(max(row[rs_col], 0), 25) * 1.2
            score += 10 if row["macd_hist_up"] else 0
            signals.append((f"RS{lb}_MOMENTUM", float(max(0, min(100, score))), f"RS{lb} mạnh hơn benchmark"))

    # 4. Volume filter family: same core trend, compare volume ratio levels
    for vr in VOLUME_FILTERS:
        cond = (
            row["close"] > row["ma20"]
            and row["ma20"] > row["ma50"]
            and row["rs20"] >= RS_MIN
            and row["ret5"] > 0
            and row["volume_ratio"] >= vr
            and row["dist_ma20_pct"] <= MAX_EXTENDED_ABOVE_MA20_PCT
        )
        if cond:
            score = 45 + min(max(row["rs20"], 0), 20) + min(max(row["volume_ratio"] - 1, 0), 2) * 10
            score += 10 if row["macd_hist_up"] else 0
            signals.append((f"VOL_FILTER_{vr:.1f}X", float(max(0, min(100, score))), f"Trend + RS20 + volume ratio >= {vr:.1f}"))

    return sorted(signals, key=lambda x: x[1], reverse=True)


def evaluate_signal(df: pd.DataFrame, i: int, symbol: str, signal: str, score: float, note: str) -> Dict[str, Any]:
    entry_i = i + 1
    entry_raw = float(df.iloc[entry_i]["open"])
    entry_price = entry_raw * (1 + BUY_SLIPPAGE_PCT / 100)
    sig_row = df.iloc[i]
    family, variant = signal_meta(signal)

    out: Dict[str, Any] = {
        "symbol": symbol,
        "signal_date": pd.Timestamp(sig_row["date"]).strftime("%Y-%m-%d"),
        "entry_date": pd.Timestamp(df.iloc[entry_i]["date"]).strftime("%Y-%m-%d"),
        "signal": signal,
        "family": family,
        "variant": variant,
        "signal_score": round(score, 3),
        "regime": sig_row.get("regime", "UNKNOWN"),
        "regime_score": round(to_num(sig_row.get("regime_score", np.nan)), 3) if not pd.isna(to_num(sig_row.get("regime_score", np.nan))) else "",
        "close_signal_day": round(float(sig_row["close"]), 3),
        "entry_price": round(entry_price, 3),
        "raw_entry_open": round(entry_raw, 3),
        "volume_ratio": round(to_num(sig_row["volume_ratio"]), 3),
        "rs5": round(to_num(sig_row.get("rs5", np.nan)), 3) if not pd.isna(to_num(sig_row.get("rs5", np.nan))) else "",
        "rs10": round(to_num(sig_row.get("rs10", np.nan)), 3) if not pd.isna(to_num(sig_row.get("rs10", np.nan))) else "",
        "rs20": round(to_num(sig_row.get("rs20", np.nan)), 3) if not pd.isna(to_num(sig_row.get("rs20", np.nan))) else "",
        "rsi14": round(to_num(sig_row["rsi14"]), 3),
        "dist_ma20_pct": round(to_num(sig_row["dist_ma20_pct"]), 3),
        "atr_pct": round(to_num(sig_row["atr_pct"]), 3),
        "min_exit_hold_bars": MIN_EXIT_HOLD_BARS,
        "notes": note,
    }

    for h in HORIZONS:
        j = entry_i + h
        if j < len(df):
            exit_close = float(df.iloc[j]["close"])
            net = (exit_close / entry_price - 1) * 100 - FEE_PCT_PER_SIDE - SELL_SLIPPAGE_PCT
            out[f"ret_t{h}_pct"] = round(net, 3)
        else:
            out[f"ret_t{h}_pct"] = ""

    end_i = min(entry_i + MAIN_HORIZON, len(df) - 1)
    period = df.iloc[entry_i:end_i + 1]
    total_buy_cost = BUY_SLIPPAGE_PCT + FEE_PCT_PER_SIDE
    total_round_cost = BUY_SLIPPAGE_PCT + SELL_SLIPPAGE_PCT + FEE_PCT_PER_SIDE * 2
    out["max_favorable_t5_pct"] = round((period["high"].max() / entry_price - 1) * 100 - total_round_cost, 3)
    out["max_drawdown_t5_pct"] = round((period["low"].min() / entry_price - 1) * 100 - total_buy_cost, 3)

    sell_i = min(entry_i + MIN_EXIT_HOLD_BARS, len(df) - 1)
    sell_close = float(df.iloc[sell_i]["close"])
    out["sellable_date_tplus"] = pd.Timestamp(df.iloc[sell_i]["date"]).strftime("%Y-%m-%d")
    out["ret_sellable_tplus_pct"] = round((sell_close / entry_price - 1) * 100 - FEE_PCT_PER_SIDE - SELL_SLIPPAGE_PCT, 3)

    main_ret = out.get(f"ret_t{MAIN_HORIZON}_pct", "")
    if main_ret == "":
        out["result_t5"] = "UNKNOWN"
    elif main_ret > 1:
        out["result_t5"] = "WIN"
    elif main_ret < -1:
        out["result_t5"] = "FAIL"
    else:
        out["result_t5"] = "FLAT"

    return out


def run_symbol(path: str, benchmark: pd.DataFrame, regime: pd.DataFrame) -> List[Dict[str, Any]]:
    symbol = symbol_from_path(path)
    raw = normalize_history(read_csv_smart(path))
    if raw.empty or len(raw) < MIN_HISTORY_BARS + max(HORIZONS) + 5:
        return []

    df = add_indicators(raw, benchmark if benchmark is not None and not benchmark.empty else None)
    if regime is not None and not regime.empty:
        df = df.merge(regime[["date", "regime", "regime_score"]], on="date", how="left")
    else:
        df["regime"] = "UNKNOWN"
        df["regime_score"] = np.nan

    rows: List[Dict[str, Any]] = []
    last_signal_date: Dict[str, pd.Timestamp] = {}

    for i in range(MIN_HISTORY_BARS, len(df) - max(HORIZONS) - 2):
        row = df.iloc[i]
        prev = df.iloc[i - 1]

        if pd.isna(row["ma20"]) or pd.isna(row["ma50"]):
            continue
        if not liquidity_ok(row):
            continue

        signals = detect_signals(row, prev)
        if not signals:
            continue

        for sig, score, note in signals:
            cur_dt = pd.Timestamp(row["date"])
            cooldown_key = f"{sig}"
            last_dt = last_signal_date.get(cooldown_key)
            if last_dt is not None and (cur_dt - last_dt).days < SIGNAL_COOLDOWN_DAYS:
                continue

            rows.append(evaluate_signal(df, i, symbol, sig, score, note))
            last_signal_date[cooldown_key] = cur_dt

    return rows


def cap_daily(results: pd.DataFrame) -> pd.DataFrame:
    if results.empty:
        return results
    out = []
    for _, g in results.groupby("signal_date"):
        out.append(g.sort_values("signal_score", ascending=False).head(MAX_SIGNALS_PER_DAY))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def stat_table(results: pd.DataFrame, group_cols: List[str]) -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame()

    ret_col = f"ret_t{MAIN_HORIZON}_pct"
    rows: List[Dict[str, Any]] = []

    for keys, g in results.groupby(group_cols):
        if not isinstance(keys, tuple):
            keys = (keys,)

        vals = pd.to_numeric(g[ret_col], errors="coerce").dropna()
        dd = pd.to_numeric(g["max_drawdown_t5_pct"], errors="coerce").dropna()
        n = len(g)
        win = int((g["result_t5"] == "WIN").sum())
        fail = int((g["result_t5"] == "FAIL").sum())
        flat = int((g["result_t5"] == "FLAT").sum())
        avg = vals.mean() if len(vals) else np.nan

        row = {col: key for col, key in zip(group_cols, keys)}
        row.update({
            "n": n,
            "win": win,
            "fail": fail,
            "flat": flat,
            "winrate_pct": round(win / n * 100, 2) if n else 0,
            f"avg_ret_t{MAIN_HORIZON}_pct": round(avg, 3) if not pd.isna(avg) else "",
            f"median_ret_t{MAIN_HORIZON}_pct": round(vals.median(), 3) if len(vals) else "",
            "avg_drawdown_t5_pct": round(dd.mean(), 3) if len(dd) else "",
            "conclusion": "MẪU ÍT" if n < 20 else ("TẠM DÙNG" if win / n >= 0.55 and avg > 0 else "YẾU/CẦN LỌC"),
        })
        rows.append(row)

    return pd.DataFrame(rows)


def baseline_comparison(results: pd.DataFrame, regime: pd.DataFrame) -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame()
    ret_col = f"ret_t{MAIN_HORIZON}_pct"
    vals = pd.to_numeric(results[ret_col], errors="coerce").dropna()
    rows = [{
        "strategy": "V19.4.1_ALL_SIGNALS",
        "n": len(vals),
        f"avg_ret_t{MAIN_HORIZON}_pct": round(vals.mean(), 3) if len(vals) else "",
        "winrate_pct": round((results["result_t5"] == "WIN").mean() * 100, 2),
    }]
    if regime is not None and not regime.empty:
        b = regime.sort_values("date").copy()
        b[f"bench_ret_t{MAIN_HORIZON}_pct"] = b["benchmark_close"].shift(-MAIN_HORIZON) / b["benchmark_close"] * 100 - 100
        sig_dates = pd.to_datetime(results["signal_date"]).unique()
        bm = b[b["date"].isin(sig_dates)]
        bvals = pd.to_numeric(bm[f"bench_ret_t{MAIN_HORIZON}_pct"], errors="coerce").dropna()
        rows.append({
            "strategy": "VNINDEX_SAME_SIGNAL_DATES",
            "n": len(bvals),
            f"avg_ret_t{MAIN_HORIZON}_pct": round(bvals.mean(), 3) if len(bvals) else "",
            "winrate_pct": round((bvals > 1).mean() * 100, 2) if len(bvals) else "",
        })
    return pd.DataFrame(rows)


def bad_patterns(results: pd.DataFrame) -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame()
    ret_col = f"ret_t{MAIN_HORIZON}_pct"
    rows = []
    for (sig, reg), g in results.groupby(["signal", "regime"]):
        if len(g) < 10:
            continue
        vals = pd.to_numeric(g[ret_col], errors="coerce").dropna()
        fail_rate = (g["result_t5"] == "FAIL").mean() * 100
        avg = vals.mean() if len(vals) else np.nan
        if fail_rate >= 45 or (not pd.isna(avg) and avg < 0):
            rows.append({
                "pattern": f"{sig} / {reg}",
                "n": len(g),
                "fail_rate_pct": round(fail_rate, 2),
                f"avg_ret_t{MAIN_HORIZON}_pct": round(avg, 3) if not pd.isna(avg) else "",
                "warning": "Cần giảm score hoặc chặn trong điều kiện này",
            })
    return pd.DataFrame(rows)


def write_report(results, signal_stats, family_compare, regime_stats, baseline, bad):
    lines = []
    lines.append("=" * 96)
    lines.append("V19.4.1 — SIGNAL FAMILY COMPARISON ENGINE")
    lines.append("=" * 96)
    lines.append("Bản này so sánh theo family để tránh dò tham số lộn xộn.")
    lines.append("")
    lines.append("Families:")
    lines.append("- BREAKOUT: 5D / 10D / 20D")
    lines.append("- PULLBACK: MA5 / MA10 / MA20")
    lines.append("- RELATIVE_STRENGTH: RS5 / RS10 / RS20")
    lines.append("- VOLUME_FILTER: 1.2x / 1.5x / 2.0x")
    lines.append("")
    lines.append(f"Total signals: {len(results)}")
    if not results.empty:
        lines.append(f"Symbols: {results['symbol'].nunique()}")
        lines.append(f"Date range: {results['signal_date'].min()} → {results['signal_date'].max()}")
    lines.append("")
    lines.append("Anti-overfit controls:")
    lines.append("- Signal T dùng dữ liệu đến ngày T")
    lines.append("- Entry T+1 open + slippage")
    lines.append("- Fee + slippage hai chiều")
    lines.append("- T+2.5 sell lock")
    lines.append("- Liquidity filter")
    lines.append("- Regime split")
    lines.append("- Cooldown + daily cap")
    lines.append("- Baseline comparison")
    lines.append("")
    lines.append("Family compare:")
    if family_compare.empty:
        lines.append("- Chưa có kết quả.")
    else:
        for _, r in family_compare.iterrows():
            lines.append(
                f"- {r['family']} / {r['variant']}: n={r['n']}, "
                f"winrate={r['winrate_pct']}%, avg T+{MAIN_HORIZON}={r.get(f'avg_ret_t{MAIN_HORIZON}_pct','')}%, "
                f"DD={r.get('avg_drawdown_t5_pct','')}%, {r['conclusion']}"
            )
    lines.append("")
    lines.append("Bad patterns:")
    if bad.empty:
        lines.append("- Chưa có pattern xấu đủ mẫu.")
    else:
        for _, r in bad.iterrows():
            lines.append(f"- {r['pattern']}: n={r['n']}, fail={r['fail_rate_pct']}%, {r['warning']}")
    lines.append("")
    lines.append("Note: Nếu cache chỉ gồm mã còn sống/mạnh thì vẫn có survivorship bias.")
    Path(OUTPUT_DIR).mkdir(exist_ok=True)
    Path(OUTPUT_DIR, "v194_report.txt").write_text("\n".join(lines), encoding="utf-8")


def main():
    Path(OUTPUT_DIR).mkdir(exist_ok=True)
    log(f"START {SYSTEM_VERSION}")

    benchmark = load_benchmark()
    regime = build_regime(benchmark) if not benchmark.empty else pd.DataFrame()

    files = sorted(glob.glob(os.path.join(CACHE_DIR, "*.csv")))
    files = [f for f in files if symbol_from_path(f) not in {BENCHMARK_SYMBOL.upper(), "VNINDEX", "VN30"}]
    log(f"Universe files: {len(files)}")

    all_rows: List[Dict[str, Any]] = []
    for idx, f in enumerate(files, 1):
        try:
            rows = run_symbol(f, benchmark, regime)
            all_rows.extend(rows)
            if idx % 50 == 0:
                log(f"Processed {idx}/{len(files)} | rows={len(all_rows)}")
        except Exception as e:
            log(f"WARN failed {symbol_from_path(f)}: {repr(e)}")

    results = pd.DataFrame(all_rows)
    results = cap_daily(results)
    if not results.empty:
        results = results.sort_values(["signal_date", "signal_score"], ascending=[True, False]).reset_index(drop=True)

    signal_stats = stat_table(results, ["signal"]).sort_values(["signal", "winrate_pct"], ascending=[True, False]) if not results.empty else pd.DataFrame()
    family_compare = stat_table(results, ["family", "variant"]).sort_values(["family", "variant"]) if not results.empty else pd.DataFrame()
    regime_stats = stat_table(results, ["signal", "regime"]).sort_values(["signal", "regime"]) if not results.empty else pd.DataFrame()
    baseline = baseline_comparison(results, regime)
    bad = bad_patterns(results)

    results.to_csv(Path(OUTPUT_DIR, "v194_historical_signal_validation.csv"), index=False, encoding="utf-8-sig")
    signal_stats.to_csv(Path(OUTPUT_DIR, "v194_signal_stats.csv"), index=False, encoding="utf-8-sig")
    family_compare.to_csv(Path(OUTPUT_DIR, "v194_family_compare.csv"), index=False, encoding="utf-8-sig")
    regime_stats.to_csv(Path(OUTPUT_DIR, "v194_regime_stats.csv"), index=False, encoding="utf-8-sig")
    baseline.to_csv(Path(OUTPUT_DIR, "v194_baseline_comparison.csv"), index=False, encoding="utf-8-sig")
    bad.to_csv(Path(OUTPUT_DIR, "v194_bad_signal_patterns.csv"), index=False, encoding="utf-8-sig")
    write_report(results, signal_stats, family_compare, regime_stats, baseline, bad)

    log("DONE")
    log(f"Output folder: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
