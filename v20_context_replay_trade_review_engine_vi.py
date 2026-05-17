# -*- coding: utf-8 -*-
"""
V20 — CONTEXT REPLAY & TRADE REVIEW ENGINE VI

Không tìm thêm indicator.
Replay bối cảnh trước tín hiệu để hiểu WIN khác FAIL ở đâu.

Input ưu tiên:
1. tracker_output/v195_weighted_signals.csv
2. tracker_output/v194_historical_signal_validation.csv
3. tracker_output/v1942_quality_filtered_signals.csv

Output:
- tracker_output/v20_context_replay.csv
- tracker_output/v20_win_fail_context_summary.csv
- tracker_output/v20_fail_patterns.csv
- tracker_output/v20_win_patterns.csv
- tracker_output/v20_context_report.txt
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

SYSTEM_VERSION = "V20_CONTEXT_REPLAY_TRADE_REVIEW_ENGINE_VI"

CACHE_DIR = os.getenv("V20_CACHE_DIR", "cache_stock")
OUTPUT_DIR = os.getenv("V20_OUTPUT_DIR", "tracker_output")
MIN_ROWS_PER_PATTERN = int(os.getenv("V20_MIN_ROWS_PER_PATTERN", "20"))

SIGNAL_INPUT_CANDIDATES = [
    os.getenv("V20_SIGNAL_INPUT", "").strip(),
    "tracker_output/v195_weighted_signals.csv",
    "tracker_output/v194_historical_signal_validation.csv",
    "tracker_output/v1942_quality_filtered_signals.csv",
]

LOOKBACKS = [5, 10, 20]


def log(msg: str) -> None:
    print(f"[V20] {msg}", flush=True)


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


def find_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
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
    return out.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)


def add_context_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    c = out["close"]
    v = out["volume"]

    for ma in [5, 10, 20, 50]:
        out[f"ma{ma}"] = c.rolling(ma).mean()
        out[f"dist_ma{ma}_pct"] = np.where(out[f"ma{ma}"] > 0, (c / out[f"ma{ma}"] - 1) * 100, np.nan)

    out["vol_ma20"] = v.rolling(20).mean()
    out["volume_ratio"] = np.where(out["vol_ma20"] > 0, v / out["vol_ma20"], np.nan)

    for lb in [1, 2, 3, 5, 10, 20]:
        out[f"ret{lb}"] = c.pct_change(lb) * 100

    out["high20_prev"] = out["high"].rolling(20).max().shift(1)
    out["low20_prev"] = out["low"].rolling(20).min().shift(1)
    out["drawdown20_pct"] = np.where(out["high20_prev"] > 0, (c / out["high20_prev"] - 1) * 100, np.nan)
    out["range20_pct"] = np.where(out["low20_prev"] > 0, (out["high20_prev"] / out["low20_prev"] - 1) * 100, np.nan)
    out["daily_range_pct"] = np.where(out["low"] > 0, (out["high"] / out["low"] - 1) * 100, np.nan)
    return out


def load_signals() -> tuple[pd.DataFrame, str]:
    for path in SIGNAL_INPUT_CANDIDATES:
        if path and os.path.exists(path):
            df = read_csv_smart(path)
            if not df.empty:
                log(f"Loaded signals: {path} rows={len(df)}")
                return df, path
    raise FileNotFoundError("Không tìm thấy signal input trong tracker_output")


def normalize_signals(df: pd.DataFrame) -> pd.DataFrame:
    symbol_col = find_col(df, ["symbol", "Mã", "ticker", "Ticker"])
    date_col = find_col(df, ["signal_date", "Ngày signal", "date", "Date"])
    result_col = find_col(df, ["result_t5", "result", "Kết quả"])
    signal_col = find_col(df, ["signal", "Signal", "family", "variant"])

    if symbol_col is None or date_col is None:
        raise ValueError("Signal file thiếu symbol hoặc signal_date")

    out = df.copy()
    out["symbol_norm"] = out[symbol_col].astype(str).str.upper().str.strip()
    out["signal_date_norm"] = pd.to_datetime(out[date_col], errors="coerce")
    out["signal_name_norm"] = out[signal_col].astype(str) if signal_col else "UNKNOWN"

    if result_col:
        out["result_norm"] = out[result_col].astype(str).str.upper().str.strip()
    else:
        ret_col = find_col(out, ["ret_t5_pct"])
        if ret_col:
            vals = pd.to_numeric(out[ret_col], errors="coerce")
            out["result_norm"] = np.where(vals > 1, "WIN", np.where(vals < -1, "FAIL", "FLAT"))
        else:
            out["result_norm"] = "UNKNOWN"

    return out.dropna(subset=["signal_date_norm"]).reset_index(drop=True)


def history_path(symbol: str) -> Optional[str]:
    for p in [Path(CACHE_DIR, f"{symbol}.csv"), Path(CACHE_DIR, f"{symbol.upper()}.csv")]:
        if p.exists():
            return str(p)
    return None


def window_metrics(df: pd.DataFrame, idx: int, lb: int) -> dict[str, Any]:
    start = max(0, idx - lb)
    w = df.iloc[start:idx + 1].copy()
    if len(w) < max(3, lb // 2):
        return {}

    close = w["close"]
    volume = w["volume"]
    base = close.iloc[0]

    ret = (close.iloc[-1] / base - 1) * 100 if base > 0 else np.nan
    max_up = (close.max() / base - 1) * 100 if base > 0 else np.nan
    max_dd = (close.min() / close.max() - 1) * 100 if close.max() > 0 else np.nan
    range_pct = (w["high"].max() / w["low"].min() - 1) * 100 if w["low"].min() > 0 else np.nan

    half = max(1, len(w) // 2)
    vol_first = volume.iloc[:half].mean()
    vol_second = volume.iloc[half:].mean()
    vol_trend = vol_second / vol_first if vol_first > 0 else np.nan
    vol_spike = volume.iloc[-1] / volume.mean() if volume.mean() > 0 else np.nan
    vol_dry = volume.tail(3).mean() / volume.mean() if volume.mean() > 0 else np.nan

    avg_range = w["daily_range_pct"].mean()
    sideway_score = 0
    if not pd.isna(range_pct) and range_pct <= 10:
        sideway_score += 1
    if not pd.isna(ret) and abs(ret) <= 5:
        sideway_score += 1
    if not pd.isna(avg_range) and avg_range <= 3:
        sideway_score += 1

    last_n = min(5, len(w))
    first_range = w["daily_range_pct"].head(last_n).mean()
    last_range = w["daily_range_pct"].tail(last_n).mean()
    contraction = last_range / first_range if first_range > 0 else np.nan

    return {
        f"ret_pre{lb}_pct": round(ret, 3) if not pd.isna(ret) else "",
        f"max_up_pre{lb}_pct": round(max_up, 3) if not pd.isna(max_up) else "",
        f"max_dd_pre{lb}_pct": round(max_dd, 3) if not pd.isna(max_dd) else "",
        f"range_pre{lb}_pct": round(range_pct, 3) if not pd.isna(range_pct) else "",
        f"avg_daily_range_pre{lb}_pct": round(avg_range, 3) if not pd.isna(avg_range) else "",
        f"vol_trend_pre{lb}": round(vol_trend, 3) if not pd.isna(vol_trend) else "",
        f"vol_spike_pre{lb}": round(vol_spike, 3) if not pd.isna(vol_spike) else "",
        f"vol_dry_pre{lb}": round(vol_dry, 3) if not pd.isna(vol_dry) else "",
        f"sideway_score_pre{lb}": sideway_score,
        f"volatility_contraction_pre{lb}": round(contraction, 3) if not pd.isna(contraction) else "",
    }


def classify_context(row: dict[str, Any]) -> dict[str, str]:
    labels = {}

    ret20 = to_num(row.get("ret_pre20_pct", np.nan))
    dist_ma20 = to_num(row.get("dist_ma20_pct", np.nan))
    vol_spike5 = to_num(row.get("vol_spike_pre5", np.nan))
    sideway20 = to_num(row.get("sideway_score_pre20", np.nan))
    vc20 = to_num(row.get("volatility_contraction_pre20", np.nan))
    dd20 = to_num(row.get("drawdown20_pct", np.nan))

    if not pd.isna(ret20):
        if ret20 >= 15:
            labels["extension_context"] = "TĂNG NÓNG TRƯỚC SIGNAL"
        elif ret20 <= -10:
            labels["extension_context"] = "SUY YẾU TRƯỚC SIGNAL"
        else:
            labels["extension_context"] = "KHÔNG QUÁ NÓNG"

    if not pd.isna(dist_ma20):
        if dist_ma20 > 8:
            labels["entry_context"] = "ENTRY XA MA20 / FOMO"
        elif -3 <= dist_ma20 <= 3:
            labels["entry_context"] = "ENTRY GẦN MA20"
        else:
            labels["entry_context"] = "ENTRY TRUNG TÍNH"

    if not pd.isna(vol_spike5):
        if vol_spike5 >= 3:
            labels["volume_context"] = "VOLUME SPIKE FOMO"
        elif 1.2 <= vol_spike5 < 3:
            labels["volume_context"] = "VOLUME TĂNG VỪA"
        elif vol_spike5 < 0.8:
            labels["volume_context"] = "VOLUME CẠN"
        else:
            labels["volume_context"] = "VOLUME TRUNG TÍNH"

    if not pd.isna(sideway20):
        labels["structure_context"] = "CÓ NỀN / SIDEWAY" if sideway20 >= 2 else "KHÔNG RÕ NỀN"

    if not pd.isna(vc20):
        if vc20 < 0.8:
            labels["volatility_context"] = "VOLATILITY CO HẸP"
        elif vc20 > 1.3:
            labels["volatility_context"] = "VOLATILITY MỞ RỘNG"
        else:
            labels["volatility_context"] = "VOLATILITY TRUNG TÍNH"

    if not pd.isna(dd20):
        if dd20 < -15:
            labels["risk_context"] = "DRAWDOWN SÂU"
        elif -10 <= dd20 <= 0:
            labels["risk_context"] = "PULLBACK LÀNH MẠNH"
        else:
            labels["risk_context"] = "RISK TRUNG TÍNH"

    return labels


def replay_signal(sig: pd.Series, hist_cache: dict[str, pd.DataFrame]) -> Optional[dict[str, Any]]:
    symbol = sig["symbol_norm"]
    sig_date = sig["signal_date_norm"]

    if symbol not in hist_cache:
        p = history_path(symbol)
        if not p:
            return None
        hist = add_context_indicators(normalize_history(read_csv_smart(p)))
        if hist.empty:
            return None
        hist_cache[symbol] = hist

    df = hist_cache[symbol]
    m = df[df["date"] <= sig_date]
    if m.empty:
        return None
    idx = m.index[-1]
    r = df.loc[idx]

    out = {
        "symbol": symbol,
        "signal_date": pd.Timestamp(r["date"]).strftime("%Y-%m-%d"),
        "source_signal_date": pd.Timestamp(sig_date).strftime("%Y-%m-%d"),
        "signal": sig.get("signal_name_norm", "UNKNOWN"),
        "result": sig.get("result_norm", "UNKNOWN"),
        "close": round(float(r["close"]), 3),
        "dist_ma20_pct": round(to_num(r.get("dist_ma20_pct", np.nan)), 3) if not pd.isna(to_num(r.get("dist_ma20_pct", np.nan))) else "",
        "drawdown20_pct": round(to_num(r.get("drawdown20_pct", np.nan)), 3) if not pd.isna(to_num(r.get("drawdown20_pct", np.nan))) else "",
        "range20_pct": round(to_num(r.get("range20_pct", np.nan)), 3) if not pd.isna(to_num(r.get("range20_pct", np.nan))) else "",
        "volume_ratio": round(to_num(r.get("volume_ratio", np.nan)), 3) if not pd.isna(to_num(r.get("volume_ratio", np.nan))) else "",
        "ret5": round(to_num(r.get("ret5", np.nan)), 3) if not pd.isna(to_num(r.get("ret5", np.nan))) else "",
        "ret10": round(to_num(r.get("ret10", np.nan)), 3) if not pd.isna(to_num(r.get("ret10", np.nan))) else "",
        "ret20": round(to_num(r.get("ret20", np.nan)), 3) if not pd.isna(to_num(r.get("ret20", np.nan))) else "",
    }

    for col in ["ret_t2_pct", "ret_t5_pct", "max_drawdown_t5_pct", "weighted_score", "score_bucket"]:
        if col in sig:
            out[col] = sig[col]

    for lb in LOOKBACKS:
        out.update(window_metrics(df, idx, lb))

    out.update(classify_context(out))
    return out


def context_stat(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    if df.empty or group_col not in df.columns:
        return pd.DataFrame()

    rows = []
    for key, g in df.groupby(group_col):
        n = len(g)
        win = int((g["result"] == "WIN").sum())
        fail = int((g["result"] == "FAIL").sum())
        flat = int((g["result"] == "FLAT").sum())
        ret5 = pd.to_numeric(g["ret_t5_pct"], errors="coerce").dropna() if "ret_t5_pct" in g.columns else pd.Series(dtype=float)
        dd = pd.to_numeric(g["max_drawdown_t5_pct"], errors="coerce").dropna() if "max_drawdown_t5_pct" in g.columns else pd.Series(dtype=float)

        rows.append({
            "context_group": group_col,
            "context_value": key,
            "n": n,
            "win": win,
            "fail": fail,
            "flat": flat,
            "winrate_pct": round(win / n * 100, 2) if n else 0,
            "failrate_pct": round(fail / n * 100, 2) if n else 0,
            "avg_ret_t5_pct": round(ret5.mean(), 3) if len(ret5) else "",
            "avg_drawdown_t5_pct": round(dd.mean(), 3) if len(dd) else "",
        })
    return pd.DataFrame(rows).sort_values(["context_group", "failrate_pct"], ascending=[True, False])


def build_summary(replay: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for col in [
        "extension_context",
        "entry_context",
        "volume_context",
        "structure_context",
        "volatility_context",
        "risk_context",
    ]:
        st = context_stat(replay, col)
        if not st.empty:
            frames.append(st)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def extract_patterns(summary: pd.DataFrame, mode: str) -> pd.DataFrame:
    if summary.empty:
        return pd.DataFrame()
    out = summary[summary["n"] >= MIN_ROWS_PER_PATTERN].copy()
    if mode == "FAIL":
        out = out[out["failrate_pct"] >= 50].copy()
        out["pattern_type"] = "FAIL_PATTERN"
        out["note"] = "Context này fail cao, nên giảm điểm/chặn khi gặp lại"
        return out.sort_values(["failrate_pct", "n"], ascending=[False, False])
    out = out[out["winrate_pct"] >= 45].copy()
    out["pattern_type"] = "WIN_PATTERN"
    out["note"] = "Context này win tương đối tốt, chỉ nên tăng nhẹ confidence"
    return out.sort_values(["winrate_pct", "n"], ascending=[False, False])


def write_report(replay: pd.DataFrame, summary: pd.DataFrame, fail_patterns: pd.DataFrame, win_patterns: pd.DataFrame, source_path: str) -> None:
    lines = []
    lines.append("=" * 96)
    lines.append("V20 — CONTEXT REPLAY & TRADE REVIEW ENGINE")
    lines.append("=" * 96)
    lines.append(f"Source signals: {source_path}")
    lines.append(f"Total replay rows: {len(replay)}")
    if not replay.empty:
        lines.append(f"Symbols: {replay['symbol'].nunique()}")
        lines.append(f"Date range: {replay['signal_date'].min()} → {replay['signal_date'].max()}")
        lines.append(f"Result counts: {replay['result'].value_counts().to_dict()}")
    lines.append("")
    lines.append("Mục tiêu:")
    lines.append("- Không tìm thêm indicator.")
    lines.append("- Tìm bối cảnh khiến signal WIN/FAIL khác nhau.")
    lines.append("")
    lines.append("Top FAIL patterns:")
    if fail_patterns.empty:
        lines.append("- Chưa có fail pattern đủ mẫu.")
    else:
        for _, r in fail_patterns.head(20).iterrows():
            lines.append(f"- {r['context_group']} = {r['context_value']}: n={r['n']}, fail={r['failrate_pct']}%, win={r['winrate_pct']}%")
    lines.append("")
    lines.append("Top WIN patterns:")
    if win_patterns.empty:
        lines.append("- Chưa có win pattern đủ mẫu.")
    else:
        for _, r in win_patterns.head(20).iterrows():
            lines.append(f"- {r['context_group']} = {r['context_value']}: n={r['n']}, win={r['winrate_pct']}%, fail={r['failrate_pct']}%")
    lines.append("")
    lines.append("Cách dùng:")
    lines.append("- FAIL pattern: đưa vào V17/V18/V19.5 để giảm score hoặc chặn.")
    lines.append("- WIN pattern: tăng nhẹ confidence, không tự động BUY lớn.")
    Path(OUTPUT_DIR).mkdir(exist_ok=True)
    Path(OUTPUT_DIR, "v20_context_report.txt").write_text("\n".join(lines), encoding="utf-8")


def main():
    Path(OUTPUT_DIR).mkdir(exist_ok=True)
    log(f"START {SYSTEM_VERSION}")

    sig_raw, source_path = load_signals()
    signals = normalize_signals(sig_raw)
    hist_cache = {}
    rows = []

    for idx, (_, sig) in enumerate(signals.iterrows(), 1):
        try:
            row = replay_signal(sig, hist_cache)
            if row:
                rows.append(row)
            if idx % 500 == 0:
                log(f"Processed {idx}/{len(signals)} | replay={len(rows)}")
        except Exception as e:
            log(f"WARN replay failed row={idx}: {repr(e)}")

    replay = pd.DataFrame(rows)
    summary = build_summary(replay)
    fail_patterns = extract_patterns(summary, "FAIL")
    win_patterns = extract_patterns(summary, "WIN")

    replay.to_csv(Path(OUTPUT_DIR, "v20_context_replay.csv"), index=False, encoding="utf-8-sig")
    summary.to_csv(Path(OUTPUT_DIR, "v20_win_fail_context_summary.csv"), index=False, encoding="utf-8-sig")
    fail_patterns.to_csv(Path(OUTPUT_DIR, "v20_fail_patterns.csv"), index=False, encoding="utf-8-sig")
    win_patterns.to_csv(Path(OUTPUT_DIR, "v20_win_patterns.csv"), index=False, encoding="utf-8-sig")
    write_report(replay, summary, fail_patterns, win_patterns, source_path)

    log("DONE")
    log(f"Output folder: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
