# -*- coding: utf-8 -*-
"""
v151_bottom_core_vi.py
Core V15.1: tính dữ liệu bắt đáy, backtest lịch sử, chấm điểm bottom.
"""

from __future__ import annotations
from pathlib import Path
import os
import numpy as np
import pandas as pd

CACHE_DIR = os.getenv("CACHE_DIR", "cache_stock")


def find_col(df: pd.DataFrame, names: list[str]):
    if df is None or df.empty:
        return None
    lower = {str(c).strip().lower(): c for c in df.columns}
    for n in names:
        key = str(n).strip().lower()
        if key in lower:
            return lower[key]
    for c in df.columns:
        txt = str(c).strip().lower()
        for n in names:
            if str(n).strip().lower() in txt:
                return c
    return None


def safe_read_csv(path: str) -> pd.DataFrame:
    try:
        if not os.path.exists(path):
            return pd.DataFrame()
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def load_cache(symbol: str, cache_dir: str = CACHE_DIR) -> pd.DataFrame:
    for name in [symbol, symbol.upper(), symbol.lower()]:
        p = Path(cache_dir) / f"{name}.csv"
        if p.exists():
            return safe_read_csv(str(p))
    return pd.DataFrame()


def normalize_cache(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    date_col = find_col(df, ["time", "date", "Ngày", "Ngay", "Date"])
    open_col = find_col(df, ["open", "Open"])
    high_col = find_col(df, ["high", "High"])
    low_col = find_col(df, ["low", "Low"])
    close_col = find_col(df, ["close", "Close", "Giá", "Gia"])
    volume_col = find_col(df, ["volume", "Volume", "vol"])
    if date_col is None or close_col is None:
        return pd.DataFrame()

    out = pd.DataFrame()
    out["date"] = pd.to_datetime(df[date_col], errors="coerce")
    out["close"] = pd.to_numeric(df[close_col], errors="coerce")
    out["open"] = pd.to_numeric(df[open_col], errors="coerce") if open_col else out["close"]
    out["high"] = pd.to_numeric(df[high_col], errors="coerce") if high_col else out["close"]
    out["low"] = pd.to_numeric(df[low_col], errors="coerce") if low_col else out["close"]
    out["volume"] = pd.to_numeric(df[volume_col], errors="coerce") if volume_col else np.nan
    out = out.dropna(subset=["date", "close"]).sort_values("date").drop_duplicates("date").reset_index(drop=True)
    return out


def calc_rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window).mean()
    avg_loss = loss.rolling(window).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def add_bottom_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ma5"] = out["close"].rolling(5).mean()
    out["ma20"] = out["close"].rolling(20).mean()
    out["rsi"] = calc_rsi(out["close"], 14)
    out["vol_ma20"] = out["volume"].rolling(20).mean()
    out["volume_ratio"] = out["volume"] / out["vol_ma20"]

    out["ret_5"] = (out["close"] / out["close"].shift(5) - 1) * 100
    out["ret_10"] = (out["close"] / out["close"].shift(10) - 1) * 100
    out["ret_20"] = (out["close"] / out["close"].shift(20) - 1) * 100

    out["high20"] = out["high"].rolling(20).max()
    out["low20"] = out["low"].rolling(20).min()
    out["drawdown20_pct"] = (out["close"] / out["high20"] - 1) * 100
    out["rebound_low20_pct"] = (out["close"] / out["low20"] - 1) * 100
    out["break_low20"] = out["close"] < out["low20"].shift(1)

    rng = (out["high"] - out["low"]).replace(0, np.nan)
    out["close_position"] = (out["close"] - out["low"]) / rng

    out["ret_t3_pct"] = (out["close"].shift(-3) / out["close"] - 1) * 100
    out["ret_t5_pct"] = (out["close"].shift(-5) / out["close"] - 1) * 100
    out["ret_t10_pct"] = (out["close"].shift(-10) / out["close"] - 1) * 100
    future_min_5 = pd.concat([out["low"].shift(-i) for i in range(1, 6)], axis=1).min(axis=1)
    out["max_dd_t5_pct"] = (future_min_5 / out["close"] - 1) * 100
    return out


def win_rate(series: pd.Series) -> float:
    vals = pd.to_numeric(series, errors="coerce").dropna()
    if len(vals) == 0:
        return np.nan
    return float((vals > 0).mean() * 100)


def avg_ret(series: pd.Series) -> float:
    vals = pd.to_numeric(series, errors="coerce").dropna()
    if len(vals) == 0:
        return np.nan
    return float(vals.mean())


def similar_bottom_band(feat: pd.DataFrame, cur: pd.Series) -> pd.DataFrame:
    pool = feat.iloc[:-10].dropna(subset=["rsi", "drawdown20_pct", "rebound_low20_pct", "ret_t5_pct"]).copy()
    if pool.empty:
        return pool
    rsi = cur["rsi"]
    dd = cur["drawdown20_pct"]
    rb = cur["rebound_low20_pct"]

    cond = (
        pool["rsi"].between(rsi - 8, rsi + 8)
        & pool["drawdown20_pct"].between(dd - 6, dd + 6)
        & pool["rebound_low20_pct"].between(max(0, rb - 5), rb + 5)
    )
    band = pool[cond].copy()

    if len(band) < 10:
        cond = pool["rsi"].between(rsi - 12, rsi + 12) & pool["drawdown20_pct"].between(dd - 10, dd + 10)
        band = pool[cond].copy()
    return band


def classify_bottom(score: float, cur: pd.Series):
    if bool(cur.get("break_low20", False)) and cur.get("rebound_low20_pct", 0) < 1:
        return "⚫ DAO RƠI", "Thủng đáy 20 phiên và chưa có hồi đáng kể."
    if score >= 75:
        return "🟢 ĐÁY CHẤT LƯỢNG", "Có hồi, có xác nhận và lịch sử vùng tương tự ủng hộ."
    if score >= 60:
        return "🟡 HỒI KỸ THUẬT", "Có hồi nhưng chưa đủ mạnh để xác nhận đáy chất lượng."
    if score >= 45:
        return "🔴 BULL TRAP", "Có hồi nhưng rủi ro gãy lại còn cao."
    return "⚫ DAO RƠI", "Giảm yếu, chưa có xác nhận hồi đáng tin."


def analyze_bottom_symbol(symbol: str, cache_dir: str = CACHE_DIR, min_rows: int = 80) -> dict:
    raw = load_cache(symbol, cache_dir=cache_dir)
    df = normalize_cache(raw)
    if df.empty or len(df) < min_rows:
        return {"Mã": symbol, "Trạng thái dữ liệu": "KHÔNG ĐỦ DỮ LIỆU", "Số dòng lịch sử": len(df)}

    feat = add_bottom_features(df).dropna(subset=["ma20", "rsi", "drawdown20_pct"]).copy()
    if feat.empty:
        return {"Mã": symbol, "Trạng thái dữ liệu": "KHÔNG TÍNH ĐƯỢC", "Số dòng lịch sử": len(df)}

    cur = feat.iloc[-1]
    band = similar_bottom_band(feat, cur)

    win3 = win_rate(band["ret_t3_pct"]) if not band.empty else np.nan
    win5 = win_rate(band["ret_t5_pct"]) if not band.empty else np.nan
    win10 = win_rate(band["ret_t10_pct"]) if not band.empty else np.nan
    avg3 = avg_ret(band["ret_t3_pct"]) if not band.empty else np.nan
    avg5 = avg_ret(band["ret_t5_pct"]) if not band.empty else np.nan
    avg10 = avg_ret(band["ret_t10_pct"]) if not band.empty else np.nan
    dd5 = avg_ret(band["max_dd_t5_pct"]) if not band.empty else np.nan

    score = 50.0
    good, bad = [], []

    rsi = float(cur["rsi"])
    drawdown = float(cur["drawdown20_pct"])
    rebound = float(cur["rebound_low20_pct"])
    ret5 = float(cur["ret_5"]) if not pd.isna(cur["ret_5"]) else np.nan
    ret10 = float(cur["ret_10"]) if not pd.isna(cur["ret_10"]) else np.nan
    vol = float(cur["volume_ratio"]) if not pd.isna(cur["volume_ratio"]) else np.nan
    close = float(cur["close"])
    ma5 = float(cur["ma5"])
    close_pos = float(cur["close_position"]) if not pd.isna(cur["close_position"]) else np.nan

    if 30 <= rsi <= 48:
        score += 12; good.append(f"RSI vùng bắt đáy {rsi:.1f}")
    elif rsi < 25:
        score -= 10; bad.append(f"RSI quá yếu {rsi:.1f}")
    elif rsi > 55:
        score -= 5; bad.append(f"RSI không còn vùng đáy {rsi:.1f}")

    if drawdown <= -12:
        score += 10; good.append(f"Chiết khấu sâu {drawdown:.1f}%")
    elif drawdown <= -6:
        score += 6; good.append(f"Có chiết khấu {drawdown:.1f}%")
    elif drawdown > -3:
        score -= 5; bad.append("Chưa giảm đủ sâu")

    if 1.5 <= rebound <= 8:
        score += 10; good.append(f"Hồi từ đáy {rebound:.1f}%")
    elif rebound < 1:
        score -= 8; bad.append("Chưa có hồi từ đáy")
    elif rebound > 12:
        score -= 5; bad.append("Hồi quá xa, không còn điểm đáy đẹp")

    if close > ma5:
        score += 8; good.append("Đã lấy lại MA5")
    else:
        score -= 6; bad.append("Chưa lấy lại MA5")

    if not pd.isna(close_pos):
        if close_pos >= 0.65:
            score += 6; good.append("Nến đóng gần cao nhất phiên")
        elif close_pos <= 0.35:
            score -= 6; bad.append("Nến đóng yếu gần đáy phiên")

    if not pd.isna(vol):
        if 0.8 <= vol <= 1.8:
            score += 5; good.append(f"Volume hồi hợp lý {vol:.2f}")
        elif vol > 2.5:
            score -= 5; bad.append(f"Volume quá đột biến {vol:.2f}")
        elif vol < 0.5:
            score -= 5; bad.append(f"Volume quá yếu {vol:.2f}")

    if not pd.isna(ret5) and ret5 < -8:
        score -= 8; bad.append(f"Rơi 5 phiên mạnh {ret5:.1f}%")
    if not pd.isna(ret10) and ret10 < -15:
        score -= 10; bad.append(f"Rơi 10 phiên mạnh {ret10:.1f}%")
    if bool(cur["break_low20"]):
        score -= 15; bad.append("Thủng đáy 20 phiên")

    if not pd.isna(win5):
        if win5 >= 58:
            score += 10; good.append(f"Win T+5 tốt {win5:.1f}%")
        elif win5 < 45:
            score -= 10; bad.append(f"Win T+5 yếu {win5:.1f}%")

    if not pd.isna(avg5):
        if avg5 >= 1:
            score += 7; good.append(f"Lợi TB T+5 tốt {avg5:.2f}%")
        elif avg5 < 0:
            score -= 7; bad.append(f"Lợi TB T+5 âm {avg5:.2f}%")

    score = max(min(score, 100), 0)
    label, reason = classify_bottom(score, cur)

    return {
        "Mã": symbol,
        "Trạng thái dữ liệu": "OK",
        "Ngày": str(pd.to_datetime(cur["date"]).date()),
        "Giá": round(close, 2),
        "RSI": round(rsi, 2),
        "Drawdown 20 phiên %": round(drawdown, 2),
        "Hồi từ đáy 20 phiên %": round(rebound, 2),
        "Ret 5 phiên %": round(ret5, 2) if not pd.isna(ret5) else "",
        "Ret 10 phiên %": round(ret10, 2) if not pd.isna(ret10) else "",
        "Volume Ratio": round(vol, 2) if not pd.isna(vol) else "",
        "Đã lấy lại MA5": "CÓ" if close > ma5 else "CHƯA",
        "Thủng đáy 20 phiên": "CÓ" if bool(cur["break_low20"]) else "KHÔNG",
        "Số mẫu bottom tương tự": int(len(band)),
        "Win T+3 %": round(win3, 2) if not pd.isna(win3) else "",
        "Win T+5 %": round(win5, 2) if not pd.isna(win5) else "",
        "Win T+10 %": round(win10, 2) if not pd.isna(win10) else "",
        "Lợi TB T+3 %": round(avg3, 2) if not pd.isna(avg3) else "",
        "Lợi TB T+5 %": round(avg5, 2) if not pd.isna(avg5) else "",
        "Lợi TB T+10 %": round(avg10, 2) if not pd.isna(avg10) else "",
        "Drawdown TB T+5 %": round(dd5, 2) if not pd.isna(dd5) else "",
        "Điểm Bottom V15.1": round(score, 2),
        "Phân loại Bottom V15.1": label,
        "Kết luận": reason,
        "Điểm mạnh": " | ".join(good[:6]),
        "Điểm yếu": " | ".join(bad[:6]),
        "Số dòng lịch sử": int(len(feat)),
    }
