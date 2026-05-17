# -*- coding: utf-8 -*-
"""
V19.4.2 — QUALITY FILTER TEST ENGINE VI
======================================

Mục tiêu:
- Không kiểm chứng tràn lan tất cả tín hiệu thô.
- Chỉ tập trung nhóm tốt nhất hiện tại: PULLBACK_MA20.
- Chỉ giữ tín hiệu khi qua bộ lọc chất lượng.

Quality filter:
1. Regime không quá xấu
2. Không mua khi giá quá xa MA20
3. Volume đủ nhưng không quá FOMO
4. RS20 mạnh nhưng không tăng nóng
5. Drawdown trước đó không quá sâu
6. Tín hiệu lõi là PULLBACK_MA20

Anti-overfit controls:
- Không look-ahead
- Entry T+1 open
- Fee + slippage
- T+2.5
- Liquidity filter
- Regime split
- Cooldown
- Baseline VNINDEX

Input:
- cache_stock/*.csv
- cache_stock/VNINDEX.csv nếu có

Output:
- tracker_output/v1942_quality_filtered_signals.csv
- tracker_output/v1942_quality_stats.csv
- tracker_output/v1942_quality_regime_stats.csv
- tracker_output/v1942_quality_baseline_comparison.csv
- tracker_output/v1942_quality_bad_patterns.csv
- tracker_output/v1942_quality_report.txt
"""

from __future__ import annotations

import os
import glob
import math
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

SYSTEM_VERSION = "V19.4.2_QUALITY_FILTER_PULLBACK_MA20_VI"

CACHE_DIR = os.getenv("V194_CACHE_DIR", "cache_stock")
OUTPUT_DIR = os.getenv("V194_OUTPUT_DIR", "tracker_output")
BENCHMARK_SYMBOL = os.getenv("V194_BENCHMARK_SYMBOL", "VNINDEX")

MIN_HISTORY_BARS = int(os.getenv("V1942_MIN_HISTORY_BARS", "80"))
HORIZONS = [1, 2, 3, 5, 10]
MAIN_HORIZON = int(os.getenv("V1942_MAIN_HORIZON", "5"))

VN_TPLUS_SELLABLE_DAYS = float(os.getenv("V1942_VN_TPLUS_SELLABLE_DAYS", "2.5"))
MIN_EXIT_HOLD_BARS = int(math.ceil(VN_TPLUS_SELLABLE_DAYS))

BUY_SLIPPAGE_PCT = float(os.getenv("V1942_BUY_SLIPPAGE_PCT", "0.15"))
SELL_SLIPPAGE_PCT = float(os.getenv("V1942_SELL_SLIPPAGE_PCT", "0.15"))
FEE_PCT_PER_SIDE = float(os.getenv("V1942_FEE_PCT_PER_SIDE", "0.15"))

MIN_AVG_VOLUME_20 = float(os.getenv("V1942_MIN_AVG_VOLUME_20", "100000"))
MIN_CLOSE_PRICE = float(os.getenv("V1942_MIN_CLOSE_PRICE", "3.0"))

SIGNAL_COOLDOWN_DAYS = int(os.getenv("V1942_SIGNAL_COOLDOWN_DAYS", "5"))
MAX_SIGNALS_PER_DAY = int(os.getenv("V1942_MAX_SIGNALS_PER_DAY", "20"))

# Quality filter thresholds: intentionally rounded, not curve-fitted.
ALLOWED_REGIMES = set(os.getenv("V1942_ALLOWED_REGIMES", "TĂNG MẠNH,TÍCH CỰC,BÌNH THƯỜNG").split(","))
MAX_DIST_ABOVE_MA20_PCT = float(os.getenv("V1942_MAX_DIST_ABOVE_MA20_PCT", "3.0"))
MIN_DIST_BELOW_MA20_PCT = float(os.getenv("V1942_MIN_DIST_BELOW_MA20_PCT", "-2.0"))
MIN_VOLUME_RATIO = float(os.getenv("V1942_MIN_VOLUME_RATIO", "1.1"))
MAX_VOLUME_RATIO = float(os.getenv("V1942_MAX_VOLUME_RATIO", "2.8"))
MIN_RS20 = float(os.getenv("V1942_MIN_RS20", "3.0"))
MAX_RET5_HOT_PCT = float(os.getenv("V1942_MAX_RET5_HOT_PCT", "8.0"))
MAX_RET20_HOT_PCT = float(os.getenv("V1942_MAX_RET20_HOT_PCT", "25.0"))
MAX_PRIOR_DRAWDOWN20_PCT = float(os.getenv("V1942_MAX_PRIOR_DRAWDOWN20_PCT", "-15.0"))
PULLBACK_TOLERANCE_PCT = float(os.getenv("V1942_PULLBACK_TOLERANCE_PCT", "2.0"))


def log(msg: str) -> None:
    print(f"[V19.4.2] {msg}", flush=True)


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

    for lb in [1, 5, 10, 20]:
        out[f"ret{lb}"] = c.pct_change(lb) * 100

    out["high20_prev"] = out["high"].rolling(20).max().shift(1)
    out["drawdown20_pct"] = np.where(out["high20_prev"] > 0, (c / out["high20_prev"] - 1) * 100, np.nan)

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

    out["dist_ma20_pct"] = np.where(out["ma20"] > 0, (c / out["ma20"] - 1) * 100, np.nan)

    if benchmark is not None and not benchmark.empty:
        b = benchmark[["date", "close"]].rename(columns={"close": "bench_close"})
        out = out.merge(b, on="date", how="left")
        out["bench_ret20"] = out["bench_close"].pct_change(20) * 100
        out["rs20"] = out["ret20"] - out["bench_ret20"]
    else:
        out["rs20"] = out["ret20"]

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


def core_pullback_ma20_signal(row: pd.Series, prev: pd.Series) -> Tuple[bool, List[str]]:
    reasons = []

    if pd.isna(row["ma20"]) or pd.isna(row["ma50"]):
        return False, ["Thiếu MA20/MA50"]

    near_ma20 = abs(row["dist_ma20_pct"]) <= PULLBACK_TOLERANCE_PCT
    trend_ok = row["ma20"] >= row["ma50"]
    recovery = row["close"] > prev["close"] and row["rsi14"] >= 45

    if near_ma20:
        reasons.append("Gần MA20")
    if trend_ok:
        reasons.append("MA20 >= MA50")
    if recovery:
        reasons.append("Giá hồi + RSI >= 45")

    ok = near_ma20 and trend_ok and recovery
    return ok, reasons


def quality_filter(row: pd.Series) -> Tuple[bool, List[str], List[str]]:
    good = []
    bad = []

    regime = str(row.get("regime", "UNKNOWN")).strip()
    if regime in ALLOWED_REGIMES:
        good.append(f"Regime chấp nhận: {regime}")
    else:
        bad.append(f"Regime quá xấu: {regime}")

    dist = to_num(row.get("dist_ma20_pct", np.nan))
    if MIN_DIST_BELOW_MA20_PCT <= dist <= MAX_DIST_ABOVE_MA20_PCT:
        good.append(f"Giá không quá xa MA20: {dist:.2f}%")
    else:
        bad.append(f"Giá lệch MA20 quá mức: {dist:.2f}%")

    vr = to_num(row.get("volume_ratio", np.nan))
    if MIN_VOLUME_RATIO <= vr <= MAX_VOLUME_RATIO:
        good.append(f"Volume vừa đủ, không FOMO: {vr:.2f}x")
    else:
        bad.append(f"Volume không đạt chuẩn: {vr:.2f}x")

    rs20 = to_num(row.get("rs20", np.nan))
    ret5 = to_num(row.get("ret5", np.nan))
    ret20 = to_num(row.get("ret20", np.nan))
    if rs20 >= MIN_RS20:
        good.append(f"RS20 mạnh: {rs20:.2f}")
    else:
        bad.append(f"RS20 yếu: {rs20:.2f}")

    if ret5 <= MAX_RET5_HOT_PCT and ret20 <= MAX_RET20_HOT_PCT:
        good.append(f"Không tăng nóng: ret5={ret5:.2f}%, ret20={ret20:.2f}%")
    else:
        bad.append(f"Tăng nóng: ret5={ret5:.2f}%, ret20={ret20:.2f}%")

    dd20 = to_num(row.get("drawdown20_pct", np.nan))
    if dd20 >= MAX_PRIOR_DRAWDOWN20_PCT:
        good.append(f"Drawdown 20 phiên không quá sâu: {dd20:.2f}%")
    else:
        bad.append(f"Drawdown 20 phiên quá sâu: {dd20:.2f}%")

    return len(bad) == 0, good, bad


def build_quality_score(row: pd.Series, core_reasons: List[str], good_reasons: List[str]) -> float:
    score = 50.0
    score += min(max(to_num(row.get("rs20", 0)), 0), 20) * 1.2
    score += 10 if bool(row.get("macd_hist_up", False)) else 0
    score += min(max(to_num(row.get("volume_ratio", 1)) - 1, 0), 1.8) * 8
    score -= abs(to_num(row.get("dist_ma20_pct", 0))) * 1.5
    score += len(core_reasons) * 2
    score += min(len(good_reasons), 6) * 1
    return float(max(0, min(100, score)))


def evaluate_signal(df: pd.DataFrame, i: int, symbol: str, score: float, good: List[str], core: List[str]) -> Dict[str, Any]:
    entry_i = i + 1
    entry_raw = float(df.iloc[entry_i]["open"])
    entry_price = entry_raw * (1 + BUY_SLIPPAGE_PCT / 100)
    r = df.iloc[i]

    out: Dict[str, Any] = {
        "symbol": symbol,
        "signal_date": pd.Timestamp(r["date"]).strftime("%Y-%m-%d"),
        "entry_date": pd.Timestamp(df.iloc[entry_i]["date"]).strftime("%Y-%m-%d"),
        "signal": "PULLBACK_MA20_QUALITY",
        "family": "PULLBACK_QUALITY",
        "variant": "MA20_FILTERED",
        "quality_score": round(score, 3),
        "regime": r.get("regime", "UNKNOWN"),
        "regime_score": round(to_num(r.get("regime_score", np.nan)), 3) if not pd.isna(to_num(r.get("regime_score", np.nan))) else "",
        "close_signal_day": round(float(r["close"]), 3),
        "entry_price": round(entry_price, 3),
        "raw_entry_open": round(entry_raw, 3),
        "volume_ratio": round(to_num(r["volume_ratio"]), 3),
        "rs20": round(to_num(r.get("rs20", np.nan)), 3) if not pd.isna(to_num(r.get("rs20", np.nan))) else "",
        "ret5": round(to_num(r.get("ret5", np.nan)), 3) if not pd.isna(to_num(r.get("ret5", np.nan))) else "",
        "ret20": round(to_num(r.get("ret20", np.nan)), 3) if not pd.isna(to_num(r.get("ret20", np.nan))) else "",
        "rsi14": round(to_num(r["rsi14"]), 3),
        "dist_ma20_pct": round(to_num(r["dist_ma20_pct"]), 3),
        "drawdown20_pct": round(to_num(r["drawdown20_pct"]), 3),
        "atr_pct": round(to_num(r["atr_pct"]), 3),
        "min_exit_hold_bars": MIN_EXIT_HOLD_BARS,
        "core_reasons": " | ".join(core),
        "quality_reasons": " | ".join(good),
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
    last_date: Optional[pd.Timestamp] = None

    for i in range(MIN_HISTORY_BARS, len(df) - max(HORIZONS) - 2):
        row = df.iloc[i]
        prev = df.iloc[i - 1]

        if pd.isna(row["ma20"]) or pd.isna(row["ma50"]):
            continue
        if not liquidity_ok(row):
            continue

        core_ok, core_reasons = core_pullback_ma20_signal(row, prev)
        if not core_ok:
            continue

        q_ok, good, bad = quality_filter(row)
        if not q_ok:
            continue

        cur_dt = pd.Timestamp(row["date"])
        if last_date is not None and (cur_dt - last_date).days < SIGNAL_COOLDOWN_DAYS:
            continue

        score = build_quality_score(row, core_reasons, good)
        rows.append(evaluate_signal(df, i, symbol, score, good, core_reasons))
        last_date = cur_dt

    return rows


def cap_daily(results: pd.DataFrame) -> pd.DataFrame:
    if results.empty:
        return results
    out = []
    for _, g in results.groupby("signal_date"):
        out.append(g.sort_values("quality_score", ascending=False).head(MAX_SIGNALS_PER_DAY))
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
        t2 = pd.to_numeric(g["ret_t2_pct"], errors="coerce").dropna()
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
            "avg_ret_t2_pct": round(t2.mean(), 3) if len(t2) else "",
            f"avg_ret_t{MAIN_HORIZON}_pct": round(avg, 3) if not pd.isna(avg) else "",
            f"median_ret_t{MAIN_HORIZON}_pct": round(vals.median(), 3) if len(vals) else "",
            "avg_drawdown_t5_pct": round(dd.mean(), 3) if len(dd) else "",
            "avg_quality_score": round(pd.to_numeric(g["quality_score"], errors="coerce").mean(), 3),
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
        "strategy": "V19.4.2_QUALITY_FILTERED_PULLBACK_MA20",
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
    for reg, g in results.groupby("regime"):
        if len(g) < 10:
            continue
        vals = pd.to_numeric(g[ret_col], errors="coerce").dropna()
        fail_rate = (g["result_t5"] == "FAIL").mean() * 100
        avg = vals.mean() if len(vals) else np.nan
        if fail_rate >= 45 or (not pd.isna(avg) and avg < 0):
            rows.append({
                "pattern": f"PULLBACK_MA20_QUALITY / {reg}",
                "n": len(g),
                "fail_rate_pct": round(fail_rate, 2),
                f"avg_ret_t{MAIN_HORIZON}_pct": round(avg, 3) if not pd.isna(avg) else "",
                "warning": "Cần giảm score hoặc chặn trong regime này",
            })
    return pd.DataFrame(rows)


def write_report(results, stats, regime_stats, baseline, bad):
    lines = []
    lines.append("=" * 96)
    lines.append("V19.4.2 — QUALITY FILTER TEST ENGINE")
    lines.append("=" * 96)
    lines.append("Chỉ test PULLBACK_MA20 sau khi qua quality filter.")
    lines.append("")
    lines.append("Quality filter:")
    lines.append("- Regime không quá xấu")
    lines.append("- Không mua khi giá quá xa MA20")
    lines.append("- Volume đủ nhưng không quá FOMO")
    lines.append("- RS20 mạnh nhưng không tăng nóng")
    lines.append("- Drawdown trước đó không quá sâu")
    lines.append("- Chỉ test PULLBACK_MA20")
    lines.append("")
    lines.append(f"Allowed regimes: {', '.join(sorted(ALLOWED_REGIMES))}")
    lines.append(f"Dist MA20 range: {MIN_DIST_BELOW_MA20_PCT}% → {MAX_DIST_ABOVE_MA20_PCT}%")
    lines.append(f"Volume ratio range: {MIN_VOLUME_RATIO}x → {MAX_VOLUME_RATIO}x")
    lines.append(f"Min RS20: {MIN_RS20}")
    lines.append(f"Max ret5 hot: {MAX_RET5_HOT_PCT}%")
    lines.append(f"Max ret20 hot: {MAX_RET20_HOT_PCT}%")
    lines.append(f"Max prior drawdown20: {MAX_PRIOR_DRAWDOWN20_PCT}%")
    lines.append("")
    lines.append(f"Total quality signals: {len(results)}")
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
    lines.append("Stats:")
    if stats.empty:
        lines.append("- Không có tín hiệu qua lọc.")
    else:
        for _, r in stats.iterrows():
            lines.append(
                f"- {r['signal']}: n={r['n']}, winrate={r['winrate_pct']}%, "
                f"avg T+2={r.get('avg_ret_t2_pct','')}%, "
                f"avg T+{MAIN_HORIZON}={r.get(f'avg_ret_t{MAIN_HORIZON}_pct','')}%, "
                f"DD={r.get('avg_drawdown_t5_pct','')}%, {r['conclusion']}"
            )
    lines.append("")
    lines.append("Regime stats:")
    if regime_stats.empty:
        lines.append("- Không có regime stats.")
    else:
        for _, r in regime_stats.iterrows():
            lines.append(
                f"- {r['regime']}: n={r['n']}, winrate={r['winrate_pct']}%, "
                f"avg T+5={r.get(f'avg_ret_t{MAIN_HORIZON}_pct','')}%"
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
    Path(OUTPUT_DIR, "v1942_quality_report.txt").write_text("\n".join(lines), encoding="utf-8")


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
        results = results.sort_values(["signal_date", "quality_score"], ascending=[True, False]).reset_index(drop=True)

    stats = stat_table(results, ["signal"]).sort_values(["winrate_pct"], ascending=False) if not results.empty else pd.DataFrame()
    regime_stats = stat_table(results, ["regime"]).sort_values(["regime"]) if not results.empty else pd.DataFrame()
    baseline = baseline_comparison(results, regime)
    bad = bad_patterns(results)

    results.to_csv(Path(OUTPUT_DIR, "v1942_quality_filtered_signals.csv"), index=False, encoding="utf-8-sig")
    stats.to_csv(Path(OUTPUT_DIR, "v1942_quality_stats.csv"), index=False, encoding="utf-8-sig")
    regime_stats.to_csv(Path(OUTPUT_DIR, "v1942_quality_regime_stats.csv"), index=False, encoding="utf-8-sig")
    baseline.to_csv(Path(OUTPUT_DIR, "v1942_quality_baseline_comparison.csv"), index=False, encoding="utf-8-sig")
    bad.to_csv(Path(OUTPUT_DIR, "v1942_quality_bad_patterns.csv"), index=False, encoding="utf-8-sig")
    write_report(results, stats, regime_stats, baseline, bad)

    log("DONE")
    log(f"Output folder: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
