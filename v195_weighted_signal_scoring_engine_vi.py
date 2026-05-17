# -*- coding: utf-8 -*-
"""
V19.5 — WEIGHTED SIGNAL SCORING ENGINE VI
=========================================

Mục tiêu:
- Không dùng 1 tín hiệu đơn lẻ như PULLBACK hoặc BREAKOUT để quyết định.
- Chấm điểm tổng hợp nhiều yếu tố:
  + Market regime
  + Trend structure
  + Relative strength RS
  + Pullback / distance MA20
  + Volume quality
  + Momentum quality
  + Drawdown risk
  + Breakout context
  + Anti-FOMO / extension risk

Sau đó kiểm chứng lịch sử:
- score >= 60
- score >= 70
- score >= 80

Anti-overfit controls:
- Không look-ahead: ngày T chỉ dùng dữ liệu đến T.
- Entry T+1 open + slippage.
- Fee + slippage.
- T+2.5 sell lock.
- Liquidity filter.
- Regime split.
- Daily cap.
- Baseline VNINDEX.
- Không tối ưu tham số lẻ.

Input:
- cache_stock/*.csv
- cache_stock/VNINDEX.csv nếu có

Output:
- tracker_output/v195_weighted_signals.csv
- tracker_output/v195_score_threshold_stats.csv
- tracker_output/v195_factor_bucket_stats.csv
- tracker_output/v195_regime_score_stats.csv
- tracker_output/v195_bad_score_patterns.csv
- tracker_output/v195_baseline_comparison.csv
- tracker_output/v195_report.txt
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

SYSTEM_VERSION = "V19.5_WEIGHTED_SIGNAL_SCORING_ENGINE_VI"

CACHE_DIR = os.getenv("V195_CACHE_DIR", "cache_stock")
OUTPUT_DIR = os.getenv("V195_OUTPUT_DIR", "tracker_output")
BENCHMARK_SYMBOL = os.getenv("V195_BENCHMARK_SYMBOL", "VNINDEX")

MIN_HISTORY_BARS = int(os.getenv("V195_MIN_HISTORY_BARS", "80"))
HORIZONS = [1, 2, 3, 5, 10]
MAIN_HORIZON = int(os.getenv("V195_MAIN_HORIZON", "5"))

VN_TPLUS_SELLABLE_DAYS = float(os.getenv("V195_VN_TPLUS_SELLABLE_DAYS", "2.5"))
MIN_EXIT_HOLD_BARS = int(math.ceil(VN_TPLUS_SELLABLE_DAYS))

BUY_SLIPPAGE_PCT = float(os.getenv("V195_BUY_SLIPPAGE_PCT", "0.15"))
SELL_SLIPPAGE_PCT = float(os.getenv("V195_SELL_SLIPPAGE_PCT", "0.15"))
FEE_PCT_PER_SIDE = float(os.getenv("V195_FEE_PCT_PER_SIDE", "0.15"))

MIN_AVG_VOLUME_20 = float(os.getenv("V195_MIN_AVG_VOLUME_20", "100000"))
MIN_CLOSE_PRICE = float(os.getenv("V195_MIN_CLOSE_PRICE", "3.0"))

MAX_SIGNALS_PER_DAY = int(os.getenv("V195_MAX_SIGNALS_PER_DAY", "20"))
SIGNAL_COOLDOWN_DAYS = int(os.getenv("V195_SIGNAL_COOLDOWN_DAYS", "5"))

SCORE_THRESHOLDS = [60, 70, 80]

# Score weights: rounded/simple, not curve-fitted.
W_REGIME = 20
W_TREND = 20
W_RS = 20
W_PULLBACK = 15
W_VOLUME = 10
W_MOMENTUM = 5
W_DRAWDOWN = 5
W_BREAKOUT = 5

MAX_EXTENDED_ABOVE_MA20_PCT = float(os.getenv("V195_MAX_EXTENDED_ABOVE_MA20_PCT", "8.0"))
MAX_FOMO_RET5_PCT = float(os.getenv("V195_MAX_FOMO_RET5_PCT", "10.0"))
MAX_DRAWDOWN20_DEEP_PCT = float(os.getenv("V195_MAX_DRAWDOWN20_DEEP_PCT", "-20.0"))


def log(msg: str) -> None:
    print(f"[V19.5] {msg}", flush=True)


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

    out["ma20_slope5"] = out["ma20"].pct_change(5) * 100
    out["vol_ma20"] = v.rolling(20).mean()
    out["volume_ratio"] = np.where(out["vol_ma20"] > 0, v / out["vol_ma20"], np.nan)

    for lb in [1, 2, 3, 5, 10, 20]:
        out[f"ret{lb}"] = c.pct_change(lb) * 100

    out["high20_prev"] = out["high"].rolling(20).max().shift(1)
    out["low20_prev"] = out["low"].rolling(20).min().shift(1)
    out["drawdown20_pct"] = np.where(out["high20_prev"] > 0, (c / out["high20_prev"] - 1) * 100, np.nan)
    out["rebound_low20_pct"] = np.where(out["low20_prev"] > 0, (c / out["low20_prev"] - 1) * 100, np.nan)

    for ma in [5, 10, 20]:
        out[f"dist_ma{ma}_pct"] = np.where(out[f"ma{ma}"] > 0, (c / out[f"ma{ma}"] - 1) * 100, np.nan)

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

    if benchmark is not None and not benchmark.empty:
        b = benchmark[["date", "close"]].rename(columns={"close": "bench_close"})
        out = out.merge(b, on="date", how="left")
        out["bench_ret5"] = out["bench_close"].pct_change(5) * 100
        out["bench_ret10"] = out["bench_close"].pct_change(10) * 100
        out["bench_ret20"] = out["bench_close"].pct_change(20) * 100
        out["rs5"] = out["ret5"] - out["bench_ret5"]
        out["rs10"] = out["ret10"] - out["bench_ret10"]
        out["rs20"] = out["ret20"] - out["bench_ret20"]
    else:
        out["rs5"] = out["ret5"]
        out["rs10"] = out["ret10"]
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


def score_regime(row: pd.Series) -> Tuple[float, str]:
    reg = str(row.get("regime", "UNKNOWN"))
    mapping = {
        "TĂNG MẠNH": W_REGIME,
        "TÍCH CỰC": W_REGIME * 0.75,
        "BÌNH THƯỜNG": W_REGIME * 0.35,
        "YẾU": -W_REGIME * 0.5,
        "RẤT YẾU": -W_REGIME,
    }
    s = mapping.get(reg, 0)
    return s, f"regime={reg}:{s:.1f}"


def score_trend(row: pd.Series) -> Tuple[float, str]:
    s = 0.0
    notes = []
    if row["close"] > row["ma20"]:
        s += 6
        notes.append("close>MA20")
    if row["ma5"] > row["ma20"]:
        s += 5
        notes.append("MA5>MA20")
    if row["ma20"] > row["ma50"]:
        s += 6
        notes.append("MA20>MA50")
    if row["ma20_slope5"] > 0:
        s += 3
        notes.append("MA20 slope up")
    return min(W_TREND, s), "|".join(notes)


def score_rs(row: pd.Series) -> Tuple[float, str]:
    rs20 = to_num(row.get("rs20", 0), 0)
    rs10 = to_num(row.get("rs10", 0), 0)
    rs5 = to_num(row.get("rs5", 0), 0)

    s = 0.0
    if rs20 >= 10:
        s += 10
    elif rs20 >= 5:
        s += 7
    elif rs20 >= 0:
        s += 3
    else:
        s -= 8

    if rs10 >= 5:
        s += 5
    elif rs10 < 0:
        s -= 3

    if rs5 >= 3:
        s += 3
    elif rs5 < -3:
        s -= 2

    return max(-W_RS, min(W_RS, s)), f"RS5={rs5:.2f},RS10={rs10:.2f},RS20={rs20:.2f}"


def score_pullback(row: pd.Series) -> Tuple[float, str]:
    dist = to_num(row.get("dist_ma20_pct", np.nan))
    if pd.isna(dist):
        return 0, "no dist_ma20"

    s = 0.0
    if -1.5 <= dist <= 2.0:
        s += W_PULLBACK
        note = "near MA20 ideal"
    elif -3.0 <= dist <= 4.0:
        s += W_PULLBACK * 0.6
        note = "near MA20 acceptable"
    elif dist > MAX_EXTENDED_ABOVE_MA20_PCT:
        s -= W_PULLBACK * 0.8
        note = "too far above MA20"
    else:
        note = "not pullback zone"
    return s, f"{note},dist={dist:.2f}%"


def score_volume(row: pd.Series) -> Tuple[float, str]:
    vr = to_num(row.get("volume_ratio", np.nan))
    if pd.isna(vr):
        return 0, "no volume ratio"
    if 1.2 <= vr <= 2.0:
        return W_VOLUME, f"volume good {vr:.2f}x"
    if 1.0 <= vr < 1.2:
        return W_VOLUME * 0.4, f"volume acceptable {vr:.2f}x"
    if 2.0 < vr <= 3.0:
        return W_VOLUME * 0.3, f"volume high but ok {vr:.2f}x"
    if vr > 3.0:
        return -W_VOLUME, f"volume FOMO {vr:.2f}x"
    return -W_VOLUME * 0.5, f"volume weak {vr:.2f}x"


def score_momentum(row: pd.Series) -> Tuple[float, str]:
    ret5 = to_num(row.get("ret5", 0), 0)
    rsi = to_num(row.get("rsi14", 0), 0)
    macd_up = bool(row.get("macd_hist_up", False))
    s = 0.0

    if 0 < ret5 <= MAX_FOMO_RET5_PCT:
        s += 2
    elif ret5 > MAX_FOMO_RET5_PCT:
        s -= 5

    if 45 <= rsi <= 70:
        s += 2
    elif rsi > 80:
        s -= 3

    if macd_up:
        s += 1

    return max(-W_MOMENTUM, min(W_MOMENTUM, s)), f"ret5={ret5:.2f},rsi={rsi:.1f},macd_up={macd_up}"


def score_drawdown(row: pd.Series) -> Tuple[float, str]:
    dd = to_num(row.get("drawdown20_pct", np.nan))
    if pd.isna(dd):
        return 0, "no dd20"
    if dd < MAX_DRAWDOWN20_DEEP_PCT:
        return -W_DRAWDOWN, f"deep drawdown {dd:.2f}%"
    if -10 <= dd <= 0:
        return W_DRAWDOWN, f"healthy pullback {dd:.2f}%"
    if dd > 0:
        return W_DRAWDOWN * 0.2, f"near high {dd:.2f}%"
    return W_DRAWDOWN * 0.4, f"moderate dd {dd:.2f}%"


def score_breakout(row: pd.Series) -> Tuple[float, str]:
    high20 = to_num(row.get("high20_prev", np.nan))
    if pd.isna(high20) or high20 <= 0:
        return 0, "no high20"
    if row["close"] > high20 and row["volume_ratio"] >= 1.5:
        return W_BREAKOUT, "breakout20 confirmed"
    return 0, "no breakout"


def weighted_score(row: pd.Series) -> Tuple[float, Dict[str, float], str]:
    parts = {}
    notes = []

    funcs = [
        ("regime", score_regime),
        ("trend", score_trend),
        ("rs", score_rs),
        ("pullback", score_pullback),
        ("volume", score_volume),
        ("momentum", score_momentum),
        ("drawdown", score_drawdown),
        ("breakout", score_breakout),
    ]

    total = 50.0  # neutral base
    for name, fn in funcs:
        s, note = fn(row)
        parts[name] = round(float(s), 3)
        notes.append(f"{name}:{note}")
        total += s

    total = max(0.0, min(100.0, total))
    return total, parts, " | ".join(notes)


def evaluate_signal(df: pd.DataFrame, i: int, symbol: str, score: float, parts: Dict[str, float], notes: str) -> Dict[str, Any]:
    entry_i = i + 1
    entry_raw = float(df.iloc[entry_i]["open"])
    entry_price = entry_raw * (1 + BUY_SLIPPAGE_PCT / 100)
    r = df.iloc[i]

    out: Dict[str, Any] = {
        "symbol": symbol,
        "signal_date": pd.Timestamp(r["date"]).strftime("%Y-%m-%d"),
        "entry_date": pd.Timestamp(df.iloc[entry_i]["date"]).strftime("%Y-%m-%d"),
        "signal": "WEIGHTED_SCORE",
        "weighted_score": round(score, 3),
        "score_bucket": "80+" if score >= 80 else ("70-79" if score >= 70 else ("60-69" if score >= 60 else "<60")),
        "regime": r.get("regime", "UNKNOWN"),
        "regime_score": round(to_num(r.get("regime_score", np.nan)), 3) if not pd.isna(to_num(r.get("regime_score", np.nan))) else "",
        "close_signal_day": round(float(r["close"]), 3),
        "entry_price": round(entry_price, 3),
        "raw_entry_open": round(entry_raw, 3),
        "volume_ratio": round(to_num(r["volume_ratio"]), 3),
        "rs5": round(to_num(r.get("rs5", np.nan)), 3) if not pd.isna(to_num(r.get("rs5", np.nan))) else "",
        "rs10": round(to_num(r.get("rs10", np.nan)), 3) if not pd.isna(to_num(r.get("rs10", np.nan))) else "",
        "rs20": round(to_num(r.get("rs20", np.nan)), 3) if not pd.isna(to_num(r.get("rs20", np.nan))) else "",
        "ret5": round(to_num(r.get("ret5", np.nan)), 3) if not pd.isna(to_num(r.get("ret5", np.nan))) else "",
        "ret20": round(to_num(r.get("ret20", np.nan)), 3) if not pd.isna(to_num(r.get("ret20", np.nan))) else "",
        "rsi14": round(to_num(r["rsi14"]), 3),
        "dist_ma20_pct": round(to_num(r["dist_ma20_pct"]), 3),
        "drawdown20_pct": round(to_num(r["drawdown20_pct"]), 3),
        "atr_pct": round(to_num(r["atr_pct"]), 3),
        "min_exit_hold_bars": MIN_EXIT_HOLD_BARS,
        "score_notes": notes,
    }

    for k, v in parts.items():
        out[f"factor_{k}"] = v

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

    rows = []
    last_date: Optional[pd.Timestamp] = None

    for i in range(MIN_HISTORY_BARS, len(df) - max(HORIZONS) - 2):
        row = df.iloc[i]

        if pd.isna(row["ma20"]) or pd.isna(row["ma50"]):
            continue
        if not liquidity_ok(row):
            continue

        score, parts, notes = weighted_score(row)
        if score < min(SCORE_THRESHOLDS):
            continue

        cur_dt = pd.Timestamp(row["date"])
        if last_date is not None and (cur_dt - last_date).days < SIGNAL_COOLDOWN_DAYS:
            continue

        rows.append(evaluate_signal(df, i, symbol, score, parts, notes))
        last_date = cur_dt

    return rows


def cap_daily(results: pd.DataFrame) -> pd.DataFrame:
    if results.empty:
        return results
    out = []
    for _, g in results.groupby("signal_date"):
        out.append(g.sort_values("weighted_score", ascending=False).head(MAX_SIGNALS_PER_DAY))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def stat_table(results: pd.DataFrame, group_cols: List[str]) -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame()

    ret_col = f"ret_t{MAIN_HORIZON}_pct"
    rows = []

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
            "avg_weighted_score": round(pd.to_numeric(g["weighted_score"], errors="coerce").mean(), 3),
            "conclusion": "MẪU ÍT" if n < 20 else ("TẠM DÙNG" if win / n >= 0.55 and avg > 0 else "YẾU/CẦN LỌC"),
        })
        rows.append(row)

    return pd.DataFrame(rows)


def threshold_stats(results: pd.DataFrame) -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame()

    rows = []
    for th in SCORE_THRESHOLDS:
        g = results[results["weighted_score"] >= th].copy()
        if g.empty:
            continue
        st = stat_table(g.assign(threshold=f">={th}"), ["threshold"])
        rows.append(st)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def factor_bucket_stats(results: pd.DataFrame) -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame()

    out = results.copy()
    out["rs20_bucket"] = pd.cut(pd.to_numeric(out["rs20"], errors="coerce"), bins=[-999, 0, 5, 10, 999], labels=["RS<0", "0-5", "5-10", ">10"])
    out["dist_ma20_bucket"] = pd.cut(pd.to_numeric(out["dist_ma20_pct"], errors="coerce"), bins=[-999, -3, 0, 3, 8, 999], labels=["<-3", "-3-0", "0-3", "3-8", ">8"])
    out["volume_bucket"] = pd.cut(pd.to_numeric(out["volume_ratio"], errors="coerce"), bins=[0, 1, 1.2, 2, 3, 999], labels=["<1", "1-1.2", "1.2-2", "2-3", ">3"])

    frames = []
    for col in ["rs20_bucket", "dist_ma20_bucket", "volume_bucket"]:
        st = stat_table(out.dropna(subset=[col]), [col])
        if not st.empty:
            st.insert(0, "factor", col)
            st = st.rename(columns={col: "bucket"})
            frames.append(st)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def baseline_comparison(results: pd.DataFrame, regime: pd.DataFrame) -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame()
    ret_col = f"ret_t{MAIN_HORIZON}_pct"
    vals = pd.to_numeric(results[ret_col], errors="coerce").dropna()
    rows = [{
        "strategy": "V19.5_WEIGHTED_SIGNALS",
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
    for (bucket, reg), g in results.groupby(["score_bucket", "regime"]):
        if len(g) < 10:
            continue
        vals = pd.to_numeric(g[ret_col], errors="coerce").dropna()
        fail_rate = (g["result_t5"] == "FAIL").mean() * 100
        avg = vals.mean() if len(vals) else np.nan
        if fail_rate >= 45 or (not pd.isna(avg) and avg < 0):
            rows.append({
                "pattern": f"score {bucket} / regime {reg}",
                "n": len(g),
                "fail_rate_pct": round(fail_rate, 2),
                f"avg_ret_t{MAIN_HORIZON}_pct": round(avg, 3) if not pd.isna(avg) else "",
                "warning": "Cần giảm trọng số/chặn điều kiện này",
            })
    return pd.DataFrame(rows)


def write_report(results, threshold, factor_stats, regime_stats, baseline, bad):
    lines = []
    lines.append("=" * 96)
    lines.append("V19.5 — WEIGHTED SIGNAL SCORING ENGINE")
    lines.append("=" * 96)
    lines.append("Mục tiêu: dùng trọng số tổng hợp thay vì tín hiệu đơn lẻ.")
    lines.append("")
    lines.append("Weights:")
    lines.append(f"- Regime: {W_REGIME}")
    lines.append(f"- Trend: {W_TREND}")
    lines.append(f"- RS: {W_RS}")
    lines.append(f"- Pullback / distance MA20: {W_PULLBACK}")
    lines.append(f"- Volume: {W_VOLUME}")
    lines.append(f"- Momentum: {W_MOMENTUM}")
    lines.append(f"- Drawdown: {W_DRAWDOWN}")
    lines.append(f"- Breakout context: {W_BREAKOUT}")
    lines.append("")
    lines.append(f"Total weighted signals: {len(results)}")
    if not results.empty:
        lines.append(f"Symbols: {results['symbol'].nunique()}")
        lines.append(f"Date range: {results['signal_date'].min()} → {results['signal_date'].max()}")
    lines.append("")
    lines.append("Threshold stats:")
    if threshold.empty:
        lines.append("- Không có tín hiệu đủ ngưỡng.")
    else:
        for _, r in threshold.iterrows():
            lines.append(
                f"- {r['threshold']}: n={r['n']}, winrate={r['winrate_pct']}%, "
                f"avg T+2={r.get('avg_ret_t2_pct','')}%, "
                f"avg T+5={r.get(f'avg_ret_t{MAIN_HORIZON}_pct','')}%, "
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
    lines.append("Note: Nếu cache chỉ gồm mã còn sống/mạnh thì vẫn có survivorship bias.")
    Path(OUTPUT_DIR).mkdir(exist_ok=True)
    Path(OUTPUT_DIR, "v195_report.txt").write_text("\n".join(lines), encoding="utf-8")


def main():
    Path(OUTPUT_DIR).mkdir(exist_ok=True)
    log(f"START {SYSTEM_VERSION}")

    benchmark = load_benchmark()
    regime = build_regime(benchmark) if not benchmark.empty else pd.DataFrame()

    files = sorted(glob.glob(os.path.join(CACHE_DIR, "*.csv")))
    files = [f for f in files if symbol_from_path(f) not in {BENCHMARK_SYMBOL.upper(), "VNINDEX", "VN30"}]
    log(f"Universe files: {len(files)}")

    all_rows = []
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
        results = results.sort_values(["signal_date", "weighted_score"], ascending=[True, False]).reset_index(drop=True)

    th_stats = threshold_stats(results)
    factor_stats = factor_bucket_stats(results)
    regime_stats = stat_table(results, ["score_bucket", "regime"]).sort_values(["score_bucket", "regime"]) if not results.empty else pd.DataFrame()
    baseline = baseline_comparison(results, regime)
    bad = bad_patterns(results)

    results.to_csv(Path(OUTPUT_DIR, "v195_weighted_signals.csv"), index=False, encoding="utf-8-sig")
    th_stats.to_csv(Path(OUTPUT_DIR, "v195_score_threshold_stats.csv"), index=False, encoding="utf-8-sig")
    factor_stats.to_csv(Path(OUTPUT_DIR, "v195_factor_bucket_stats.csv"), index=False, encoding="utf-8-sig")
    regime_stats.to_csv(Path(OUTPUT_DIR, "v195_regime_score_stats.csv"), index=False, encoding="utf-8-sig")
    baseline.to_csv(Path(OUTPUT_DIR, "v195_baseline_comparison.csv"), index=False, encoding="utf-8-sig")
    bad.to_csv(Path(OUTPUT_DIR, "v195_bad_score_patterns.csv"), index=False, encoding="utf-8-sig")
    write_report(results, th_stats, factor_stats, regime_stats, baseline, bad)

    log("DONE")
    log(f"Output folder: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
