# -*- coding: utf-8 -*-
"""
v152_walkforward_core_vi.py

V15.2 WALK-FORWARD CORE CHUNG
Quy ước:
- Học 2 tháng
- Test tháng thứ 3
- Trượt từng tháng liên tục

Dùng chung cho:
- V14.3 Momentum / Heat Combo
- V15.1 Bottom Quality

File này chỉ là core:
- Không gửi Telegram
- Không xuất dashboard
- Không quyết định mua/bán
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
import pandas as pd


@dataclass
class WalkForwardConfig:
    train_months: int = 2
    test_months: int = 1
    step_months: int = 1
    min_train_samples: int = 10
    min_test_samples: int = 3
    return_col: str = "ret_t5_pct"


def safe_num(x, default=np.nan):
    try:
        if pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default


def ensure_datetime(df: pd.DataFrame, date_col: str = "date") -> pd.DataFrame:
    if df is None or df.empty or date_col not in df.columns:
        return pd.DataFrame()
    out = df.copy()
    out[date_col] = pd.to_datetime(out[date_col], errors="coerce")
    out = out.dropna(subset=[date_col]).sort_values(date_col).reset_index(drop=True)
    return out


def win_rate(series: pd.Series) -> float:
    vals = pd.to_numeric(series, errors="coerce").dropna()
    if len(vals) == 0:
        return np.nan
    return float((vals > 0).mean() * 100)


def avg_return(series: pd.Series) -> float:
    vals = pd.to_numeric(series, errors="coerce").dropna()
    if len(vals) == 0:
        return np.nan
    return float(vals.mean())


def classify_stability(segment_count, positive_count, segment_positive_pct, avg_ret, avg_win):
    if segment_count <= 0:
        return "KHÔNG ĐỦ DỮ LIỆU", "Không có đủ đoạn walk-forward để kiểm định."

    if segment_count < 4:
        return "MẪU ÍT", "Số đoạn test quá ít, chỉ dùng tham khảo."

    if segment_positive_pct >= 70 and avg_ret > 0 and avg_win >= 52:
        return "ỔN ĐỊNH MẠNH", "Mẫu thắng ở đa số đoạn và lợi nhuận trung bình dương."

    if segment_positive_pct >= 55 and avg_ret >= 0:
        return "ỔN ĐỊNH VỪA", "Mẫu tương đối ổn định nhưng chưa thật sự mạnh."

    if segment_positive_pct >= 45:
        return "TRUNG TÍNH", "Mẫu không quá xấu nhưng độ ổn định chưa rõ."

    return "YẾU / DỄ HỌC VẸT", "Mẫu không ổn định qua các đoạn thời gian."


def summarize_walkforward(result_df: pd.DataFrame) -> dict:
    if result_df is None or result_df.empty:
        stability, reason = classify_stability(0, 0, np.nan, np.nan, np.nan)
        return {
            "Số đoạn test": 0,
            "Số đoạn dương": 0,
            "Tỷ lệ đoạn dương %": "",
            "Win T+5 TB các đoạn %": "",
            "Lợi TB T+5 các đoạn %": "",
            "Số mẫu test TB": "",
            "Độ ổn định mẫu": stability,
            "Lý do ổn định": reason,
        }

    df = result_df.dropna(subset=["test_avg_return"]).copy()
    n = int(len(df))
    pos = int((df["test_avg_return"] > 0).sum()) if n else 0
    pos_pct = (pos / n * 100) if n else np.nan
    avg_ret = avg_return(df["test_avg_return"]) if n else np.nan
    avg_win = avg_return(df["test_win_rate"]) if "test_win_rate" in df.columns and n else np.nan
    avg_n = avg_return(df["test_samples"]) if "test_samples" in df.columns and n else np.nan

    stability, reason = classify_stability(n, pos, pos_pct, avg_ret, avg_win)

    return {
        "Số đoạn test": n,
        "Số đoạn dương": pos,
        "Tỷ lệ đoạn dương %": round(pos_pct, 2) if not pd.isna(pos_pct) else "",
        "Win T+5 TB các đoạn %": round(avg_win, 2) if not pd.isna(avg_win) else "",
        "Lợi TB T+5 các đoạn %": round(avg_ret, 2) if not pd.isna(avg_ret) else "",
        "Số mẫu test TB": round(avg_n, 2) if not pd.isna(avg_n) else "",
        "Độ ổn định mẫu": stability,
        "Lý do ổn định": reason,
    }


def run_walkforward_validation(
    feature_df: pd.DataFrame,
    current_row: pd.Series,
    match_func: Callable[[pd.DataFrame, pd.Series], pd.DataFrame],
    config: Optional[WalkForwardConfig] = None,
    date_col: str = "date",
):
    cfg = config or WalkForwardConfig()
    df = ensure_datetime(feature_df, date_col=date_col)

    if df.empty or cfg.return_col not in df.columns:
        empty = pd.DataFrame()
        return empty, summarize_walkforward(empty)

    df = df.dropna(subset=[cfg.return_col]).copy()
    if df.empty:
        empty = pd.DataFrame()
        return empty, summarize_walkforward(empty)

    min_date = df[date_col].min()
    max_date = df[date_col].max()

    rows = []
    window_start = min_date

    while True:
        train_start = window_start
        train_end = train_start + pd.DateOffset(months=cfg.train_months)
        test_start = train_end
        test_end = test_start + pd.DateOffset(months=cfg.test_months)

        if test_start >= max_date:
            break

        train_df = df[(df[date_col] >= train_start) & (df[date_col] < train_end)].copy()
        test_df = df[(df[date_col] >= test_start) & (df[date_col] < test_end)].copy()

        if len(train_df) >= cfg.min_train_samples and len(test_df) >= cfg.min_test_samples:
            try:
                train_match = match_func(train_df, current_row)
            except Exception:
                train_match = pd.DataFrame()

            try:
                test_match = match_func(test_df, current_row)
            except Exception:
                test_match = pd.DataFrame()

            train_n = int(len(train_match)) if train_match is not None else 0
            test_n = int(len(test_match)) if test_match is not None else 0

            if train_n > 0 and test_n >= cfg.min_test_samples:
                rets = pd.to_numeric(test_match[cfg.return_col], errors="coerce").dropna()
                test_win = win_rate(rets)
                test_avg = avg_return(rets)

                rows.append({
                    "train_start": str(train_start.date()),
                    "train_end": str((train_end - pd.Timedelta(days=1)).date()),
                    "test_start": str(test_start.date()),
                    "test_end": str((test_end - pd.Timedelta(days=1)).date()),
                    "train_samples": train_n,
                    "test_samples": test_n,
                    "test_win_rate": round(test_win, 2) if not pd.isna(test_win) else np.nan,
                    "test_avg_return": round(test_avg, 2) if not pd.isna(test_avg) else np.nan,
                    "test_positive": bool(test_avg > 0) if not pd.isna(test_avg) else False,
                })

        window_start = window_start + pd.DateOffset(months=cfg.step_months)

    result = pd.DataFrame(rows)
    summary = summarize_walkforward(result)
    return result, summary


def default_bottom_match_func(pool: pd.DataFrame, current_row: pd.Series) -> pd.DataFrame:
    required = ["rsi", "drawdown20_pct", "rebound_low20_pct"]
    for c in required:
        if c not in pool.columns or c not in current_row.index:
            return pd.DataFrame()

    rsi = safe_num(current_row["rsi"])
    dd = safe_num(current_row["drawdown20_pct"])
    rb = safe_num(current_row["rebound_low20_pct"])

    if pd.isna(rsi) or pd.isna(dd) or pd.isna(rb):
        return pd.DataFrame()

    cond = (
        pool["rsi"].between(rsi - 8, rsi + 8)
        & pool["drawdown20_pct"].between(dd - 6, dd + 6)
        & pool["rebound_low20_pct"].between(max(0, rb - 5), rb + 5)
    )
    matched = pool[cond].copy()

    if len(matched) < 3:
        cond = (
            pool["rsi"].between(rsi - 12, rsi + 12)
            & pool["drawdown20_pct"].between(dd - 10, dd + 10)
        )
        matched = pool[cond].copy()

    return matched


def default_momentum_match_func(pool: pd.DataFrame, current_row: pd.Series) -> pd.DataFrame:
    required = ["dist_ma20_pct", "rsi"]
    for c in required:
        if c not in pool.columns or c not in current_row.index:
            return pd.DataFrame()

    dist = safe_num(current_row["dist_ma20_pct"])
    rsi = safe_num(current_row["rsi"])

    if pd.isna(dist) or pd.isna(rsi):
        return pd.DataFrame()

    cond = (
        pool["dist_ma20_pct"].between(dist - 3, dist + 3)
        & pool["rsi"].between(rsi - 8, rsi + 8)
    )

    if "volume_ratio" in pool.columns and "volume_ratio" in current_row.index:
        vol = safe_num(current_row["volume_ratio"])
        if not pd.isna(vol):
            cond = cond & pool["volume_ratio"].between(max(0, vol - 0.6), vol + 0.6)

    matched = pool[cond].copy()

    if len(matched) < 3:
        cond = (
            pool["dist_ma20_pct"].between(dist - 5, dist + 5)
            & pool["rsi"].between(rsi - 12, rsi + 12)
        )
        matched = pool[cond].copy()

    return matched
