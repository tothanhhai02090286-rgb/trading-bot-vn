# -*- coding: utf-8 -*-
# ============================================================
# V11 PATTERN STATS VI - THONG KE MAU CHUAN TIENG VIET
# Layer phu. KHONG thay doi core V10.
# ============================================================

import pandas as pd
import numpy as np


def _safe_float(x, default=np.nan):
    try:
        if x is None:
            return default
        s = str(x).strip()
        if s == "" or s.lower() in ["nan", "none"]:
            return default
        return float(x)
    except Exception:
        return default


def _find_col(df, names):
    if df is None or df.empty:
        return None
    lower = {str(c).lower().strip(): c for c in df.columns}
    for n in names:
        if n in df.columns:
            return n
        key = str(n).lower().strip()
        if key in lower:
            return lower[key]
    return None


def _format_pattern_ngan(pattern):
    try:
        parts = [p.strip() for p in str(pattern).split("|") if p.strip()]
        mapping = {
            "UPTREND": "Tang", "DOWNTREND": "Giam", "SIDEWAY": "Di ngang",
            "MOMENTUM": "Da tang", "MOMENTUM_WATCH": "Theo doi da tang",
            "BOTTOM": "Bat day", "BOTTOM_WATCH": "Theo doi day",
            "BUY NOW": "Mua", "WAIT": "Cho", "WATCHLIST": "Theo doi", "SKIP": "Bo",
            "RSI_LOW": "RSI thap", "RSI_WEAK": "RSI yeu", "RSI_MID": "RSI trung binh",
            "RSI_MID_HIGH": "RSI kha cao", "RSI_HIGH": "RSI cao",
            "RS_STRONG": "RS manh", "RS_WEAK": "RS yeu", "RS_BAD": "RS xau",
            "VOL_LOW": "Vol thap", "VOL_OK": "Vol on", "VOL_STRONG": "Vol manh",
            "ATR_LOW": "ATR thap", "ATR_OK": "ATR on", "ATR_HIGH": "ATR cao",
            "ABOVE_MA20": "Tren MA20", "BELOW_MA20": "Duoi MA20", "FAR_MA20": "Xa MA20",
        }
        return " | ".join([mapping.get(p, p) for p in parts])
    except Exception:
        return str(pattern)


def _chon_oos_cols(df):
    pattern_col = _find_col(df, ["Pattern", "Pattern Key", "pattern"])
    oos_pct_col = _find_col(df, ["OOS%", "OOS Win Probability", "OOS Win Rate", "Winrate"])
    oos_n_col = _find_col(df, ["OOS N", "OOSN", "OOS Samples", "Count", "Samples"])
    avg2_col = _find_col(df, ["Avg+2D", "OOS Avg Ret+2D %", "Avg 2D", "Ret+2D"])
    avg5_col = _find_col(df, ["Avg+5D", "OOS Avg Ret+5D %", "Avg 5D", "Ret+5D"])
    avg10_col = _find_col(df, ["Avg+10D", "OOS Avg Ret+10D %", "Avg 10D", "Ret+10D"])
    return pattern_col, oos_pct_col, oos_n_col, avg2_col, avg5_col, avg10_col


def _xep_hang_mau(winrate, count, avg5):
    wr = _safe_float(winrate, np.nan)
    n = _safe_float(count, 0)
    a5 = _safe_float(avg5, np.nan)

    if pd.isna(wr) or pd.isna(a5):
        return "CHUA DU DU LIEU"
    if n >= 10 and wr >= 75 and a5 >= 5:
        return "A+ RAT MANH"
    if n >= 5 and wr >= 70 and a5 >= 3:
        return "A MANH"
    if n >= 5 and wr >= 65 and a5 >= 1:
        return "B DUNG DUOC"
    if n < 5 and wr >= 80 and a5 > 0:
        return "CANH BAO: MAU IT"
    return "C YEU / BO QUA"


def _goi_y_hanh_dong(grade):
    g = str(grade).upper()
    if "A+ RAT MANH" in g:
        return "UU TIEN CAO / CO THE MUA THAM DO"
    if "A MANH" in g:
        return "UU TIEN / CHO DIEM VAO"
    if "B DUNG DUOC" in g:
        return "THEO DOI"
    if "MAU IT" in g:
        return "CHI THAM KHAO - CAN THEM MAU"
    return "BO QUA"


def _ly_do_mau(winrate, count, avg2, avg5, avg10):
    reasons = []
    wr = _safe_float(winrate, np.nan)
    n = _safe_float(count, 0)
    a2 = _safe_float(avg2, np.nan)
    a5 = _safe_float(avg5, np.nan)
    a10 = _safe_float(avg10, np.nan)

    if n >= 10:
        reasons.append("mau kha nhieu")
    elif n >= 5:
        reasons.append("mau vua")
    else:
        reasons.append("mau it")

    if not pd.isna(wr):
        if wr >= 80:
            reasons.append("ty le thang cao")
        elif wr >= 70:
            reasons.append("ty le thang dat")
        else:
            reasons.append("ty le thang chua manh")

    if not pd.isna(a5):
        if a5 >= 5:
            reasons.append("Avg+5D rat tot")
        elif a5 >= 3:
            reasons.append("Avg+5D tot")
        elif a5 >= 1:
            reasons.append("Avg+5D tam duoc")
        else:
            reasons.append("Avg+5D yeu")

    if not pd.isna(a2) and a2 < 0:
        reasons.append("T+2 am")
    if not pd.isna(a10) and a10 < 0:
        reasons.append("T+10 am")

    return "; ".join(reasons)


def build_pattern_stats_chuan_vi(pattern_df, min_count=3, limit=30):
    if pattern_df is None or pattern_df.empty:
        return pd.DataFrame([{"Trang thai": "Khong co du lieu pattern"}])

    df = pattern_df.copy()
    pattern_col, oos_pct_col, oos_n_col, avg2_col, avg5_col, avg10_col = _chon_oos_cols(df)

    if pattern_col is None:
        return pd.DataFrame([{"Trang thai": "Khong tim thay cot Pattern"}])

    out = pd.DataFrame()
    out["Mau tin hieu"] = df[pattern_col].astype(str)
    out["Mau de doc"] = out["Mau tin hieu"].apply(_format_pattern_ngan)

    out["Ty le thang %"] = pd.to_numeric(df[oos_pct_col], errors="coerce") if oos_pct_col else np.nan
    out["So lan test"] = pd.to_numeric(df[oos_n_col], errors="coerce").fillna(0).astype(int) if oos_n_col else 0

    out["So lan thang"] = np.where(
        out["Ty le thang %"].notna(),
        np.round(out["So lan test"] * out["Ty le thang %"] / 100).astype(int),
        0
    )
    out["So lan thua"] = (out["So lan test"] - out["So lan thang"]).clip(lower=0)

    out["Loi TB T+2 %"] = pd.to_numeric(df[avg2_col], errors="coerce") if avg2_col else np.nan
    out["Loi TB T+5 %"] = pd.to_numeric(df[avg5_col], errors="coerce") if avg5_col else np.nan
    out["Loi TB T+10 %"] = pd.to_numeric(df[avg10_col], errors="coerce") if avg10_col else np.nan

    out["Xep hang mau"] = out.apply(
        lambda r: _xep_hang_mau(r["Ty le thang %"], r["So lan test"], r["Loi TB T+5 %"]),
        axis=1
    )
    out["Goi y hanh dong"] = out["Xep hang mau"].apply(_goi_y_hanh_dong)
    out["Ly do"] = out.apply(
        lambda r: _ly_do_mau(r["Ty le thang %"], r["So lan test"], r["Loi TB T+2 %"], r["Loi TB T+5 %"], r["Loi TB T+10 %"]),
        axis=1
    )

    out = out[(out["So lan test"] >= min_count) | (out["Xep hang mau"].astype(str).str.contains("MAU IT", na=False))].copy()

    grade_rank = {
        "A+ RAT MANH": 1,
        "A MANH": 2,
        "B DUNG DUOC": 3,
        "CANH BAO: MAU IT": 4,
        "C YEU / BO QUA": 5,
        "CHUA DU DU LIEU": 9,
    }
    out["_rank"] = out["Xep hang mau"].map(grade_rank).fillna(9)
    out = out.sort_values(["_rank", "Loi TB T+5 %", "Ty le thang %", "So lan test"],
                          ascending=[True, False, False, False]).drop(columns=["_rank"])

    for c in ["Ty le thang %", "Loi TB T+2 %", "Loi TB T+5 %", "Loi TB T+10 %"]:
        out[c] = pd.to_numeric(out[c], errors="coerce").round(2)

    cols = [
        "Xep hang mau", "Goi y hanh dong", "Mau de doc",
        "So lan test", "So lan thang", "So lan thua",
        "Ty le thang %", "Loi TB T+2 %", "Loi TB T+5 %", "Loi TB T+10 %",
        "Ly do", "Mau tin hieu"
    ]
    return out[[c for c in cols if c in out.columns]].replace({np.nan: ""}).head(limit)


def build_pattern_stats_tom_tat_vi(pattern_view):
    if pattern_view is None or pattern_view.empty or "Xep hang mau" not in pattern_view.columns:
        return pd.DataFrame()
    out = pattern_view.groupby("Xep hang mau").size().reset_index(name="So mau")
    return out.sort_values("So mau", ascending=False)
