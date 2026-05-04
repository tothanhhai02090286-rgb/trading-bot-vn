# ============================================================
# V11 MARKET OVERLAY SAFE - VIET HOA
# Layer phu sau V10. KHONG thay doi core signal goc.
#
# SAFE VERSION:
# - Khong crash neu thieu Ret1
# - Khong crash neu thieu cot
# - Tu fallback sang RS20 neu khong tinh duoc Ret1
# - Chi tao bang dashboard V11
# ============================================================

import pandas as pd
import numpy as np


def _safe_float(x, default=np.nan):
    try:
        if x is None:
            return default
        if str(x).strip() == "":
            return default
        return float(x)
    except Exception:
        return default


def _norm_text(x):
    try:
        return str(x).strip().upper()
    except Exception:
        return ""


def _pick_col(df, names):
    if df is None or df.empty:
        return None
    for c in names:
        if c in df.columns:
            return c
    return None


def tinh_ret1_an_toan(df):
    """
    Tao cot Ret1_tmp an toan.
    Uu tien:
    1. Ret1 %
    2. Ret1
    3. Close / Prev Close
    4. Neu khong co thi de NaN
    """
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()

    ret_col = _pick_col(out, ["Ret1 %", "Ret1", "ret1", "ret1_pct"])
    if ret_col:
        out["Ret1_tmp"] = pd.to_numeric(out[ret_col], errors="coerce")
        return out

    close_col = _pick_col(out, ["Close", "close", "Gia", "Giá"])
    prev_col = _pick_col(out, ["Prev Close", "PrevClose", "Close Prev", "close_prev", "prev_close"])

    if close_col and prev_col:
        close = pd.to_numeric(out[close_col], errors="coerce")
        prev = pd.to_numeric(out[prev_col], errors="coerce")
        out["Ret1_tmp"] = (close / prev - 1) * 100
    else:
        out["Ret1_tmp"] = np.nan

    return out


def tinh_do_rong_thi_truong(df):
    """
    Do rong thi truong:
    - Neu co Ret1: % so ma tang trong ngay
    - Neu khong co Ret1: fallback theo % so ma co RS20 > 0
    """
    if df is None or df.empty:
        return 0.0, 0, 0, "KHONG CO DU LIEU"

    d = tinh_ret1_an_toan(df)

    if "Ret1_tmp" in d.columns and d["Ret1_tmp"].notna().sum() > 0:
        valid = d["Ret1_tmp"].dropna()
        tong_ma = len(valid)
        so_ma_tang = int((valid > 0).sum())
        breadth = (so_ma_tang / tong_ma * 100) if tong_ma > 0 else 0
        return round(breadth, 2), so_ma_tang, tong_ma, "RET1"

    rs20_col = _pick_col(d, ["RS20", "rs20"])
    if rs20_col:
        rs = pd.to_numeric(d[rs20_col], errors="coerce").dropna()
        tong_ma = len(rs)
        so_ma_manh = int((rs > 0).sum())
        breadth = (so_ma_manh / tong_ma * 100) if tong_ma > 0 else 0
        return round(breadth, 2), so_ma_manh, tong_ma, "RS20_FALLBACK"

    return 0.0, 0, len(d), "KHONG CO RET1/RS20"


def danh_gia_chat_luong_thi_truong(market_score=0, breadth=0):
    ms = _safe_float(market_score, 0)
    br = _safe_float(breadth, 0)

    if ms >= 70 and br >= 55:
        return "TANG MANH THAT"

    if ms >= 70 and br < 40:
        return "TRU KEO - THI TRUONG YEU BEN TRONG"

    if ms >= 60 and br >= 50:
        return "TICH CUC"

    if ms >= 50 and br >= 40:
        return "TRUNG TINH"

    if ms < 50 and br < 40:
        return "THI TRUONG YEU"

    return "CAN THAN TRONG"


def nguong_rs20_theo_thi_truong(market_label):
    label = _norm_text(market_label)

    if label == "TANG MANH THAT":
        return -2

    if "TRU KEO" in label:
        return 5

    if label == "TICH CUC":
        return 0

    if label == "TRUNG TINH":
        return 0

    if "YEU" in label:
        return 5

    return 0


def xep_hang_leader_rs20(rs20):
    v = _safe_float(rs20, np.nan)

    if pd.isna(v):
        return "CHUA RO"
    if v >= 15:
        return "LEADER RAT MANH"
    if v >= 5:
        return "LEADER"
    if v >= 0:
        return "KHOE HON THI TRUONG"
    if v >= -5:
        return "YEU NHE"
    return "YEU HON THI TRUONG"


def dieu_chinh_hanh_dong_v11(row, nguong_rs20):
    rec = str(row.get("Rec", row.get("Action", row.get("Final Action", ""))))
    risk = _norm_text(row.get("Risk Status", ""))
    rs20 = _safe_float(row.get("RS20"), np.nan)

    if risk == "FAIL":
        return "BO QUA / SKIP (Risk FAIL)"

    if not pd.isna(rs20) and rs20 < nguong_rs20:
        if "MUA" in rec.upper() or "BUY" in rec.upper():
            return "THEO DOI / WATCH (RS20 chua dat V11)"
        return "THEO DOI / WATCH"

    return rec


def ly_do_overlay_v11(row, market_label, nguong_rs20):
    reasons = [
        f"Thi truong: {market_label}",
        f"Nguong RS20 V11: {nguong_rs20}"
    ]

    rs20 = _safe_float(row.get("RS20"), np.nan)
    risk = _norm_text(row.get("Risk Status", ""))

    if not pd.isna(rs20):
        if rs20 >= nguong_rs20:
            reasons.append("RS20 dat nguong V11")
        else:
            reasons.append("RS20 chua dat nguong V11")

    if risk == "FAIL":
        reasons.append("Risk FAIL")

    return "; ".join(reasons)


def ap_dung_v11_market_overlay(df, market_score=0):
    """
    Ham chinh runner goi.
    Input:
    - df: bang signal V10
    - market_score: diem thi truong neu co

    Output:
    - df them cot V11
    - bang tom tat V11
    """
    try:
        if df is None or df.empty:
            summary = pd.DataFrame([{
                "Chi tieu": "Trang thai",
                "Gia tri": "Khong co du lieu dau vao"
            }])
            return pd.DataFrame(), summary

        out = df.copy()

        breadth, so_ma_tang, tong_ma, source = tinh_do_rong_thi_truong(out)
        market_label = danh_gia_chat_luong_thi_truong(market_score, breadth)
        rs20_threshold = nguong_rs20_theo_thi_truong(market_label)

        out["V11 Danh Gia Thi Truong"] = market_label
        out["V11 Do Rong Thi Truong %"] = breadth
        out["V11 Nguong RS20"] = rs20_threshold

        if "RS20" in out.columns:
            out["V11 Xep Hang RS20"] = out["RS20"].apply(xep_hang_leader_rs20)
        else:
            out["V11 Xep Hang RS20"] = "CHUA CO RS20"

        out["V11 Hanh Dong"] = out.apply(
            lambda r: dieu_chinh_hanh_dong_v11(r, rs20_threshold),
            axis=1
        )

        out["V11 Ly Do"] = out.apply(
            lambda r: ly_do_overlay_v11(r, market_label, rs20_threshold),
            axis=1
        )

        summary = pd.DataFrame([
            {"Chi tieu": "Market Score V10", "Gia tri": round(_safe_float(market_score, 0), 2)},
            {"Chi tieu": "Do rong thi truong", "Gia tri": f"{breadth}%"},
            {"Chi tieu": "So ma tang/manh", "Gia tri": f"{so_ma_tang}/{tong_ma}"},
            {"Chi tieu": "Nguon do rong", "Gia tri": source},
            {"Chi tieu": "Ket luan V11", "Gia tri": market_label},
            {"Chi tieu": "Nguong RS20 ap dung", "Gia tri": rs20_threshold},
        ])

        return out, summary

    except Exception as e:
        summary = pd.DataFrame([{
            "Chi tieu": "Loi V11 Overlay",
            "Gia tri": repr(e)
        }])
        return df.copy() if df is not None else pd.DataFrame(), summary


def tao_bang_v11_leader(df, limit=10):
    """
    Bang leader theo RS20.
    """
    try:
        if df is None or df.empty:
            return pd.DataFrame()

        out = df.copy()

        cols_map = {
            "Ngay": "Ngay",
            "Ma": "Ma",
            "Close": "Gia",
            "Rec": "Hanh dong V10",
            "V11 Hanh Dong": "Hanh dong V11",
            "V11 Xep Hang RS20": "Xep hang RS20",
            "RS20": "RS20",
            "Score": "Score",
            "AI Confidence": "AI",
            "AI": "AI",
            "Risk Status": "Risk",
            "V11 Ly Do": "Ly do V11",
        }

        cols = [c for c in cols_map.keys() if c in out.columns]
        if not cols:
            return pd.DataFrame()

        view = out[cols].copy().rename(columns=cols_map)

        for c in ["RS20", "Score", "AI"]:
            if c in view.columns:
                view[c] = pd.to_numeric(view[c], errors="coerce")

        sort_cols = [c for c in ["RS20", "AI", "Score"] if c in view.columns]
        if sort_cols:
            view = view.sort_values(sort_cols, ascending=[False] * len(sort_cols))

        return view.head(limit).replace({np.nan: ""})

    except Exception as e:
        return pd.DataFrame([{"Loi": repr(e)}])


def tao_bang_v11_bi_ha_hang(df, limit=20):
    """
    Cac ma bi V11 ha hang so voi V10.
    """
    try:
        if df is None or df.empty or "V11 Hanh Dong" not in df.columns:
            return pd.DataFrame()

        rec_col = "Rec" if "Rec" in df.columns else "Action" if "Action" in df.columns else None
        if rec_col is None:
            return pd.DataFrame()

        out = df[df[rec_col].astype(str) != df["V11 Hanh Dong"].astype(str)].copy()
        if out.empty:
            return pd.DataFrame()

        cols_map = {
            "Ngay": "Ngay",
            "Ma": "Ma",
            "Close": "Gia",
            rec_col: "Hanh dong V10",
            "V11 Hanh Dong": "Hanh dong V11",
            "RS20": "RS20",
            "V11 Nguong RS20": "Nguong RS20 V11",
            "Risk Status": "Risk",
            "V11 Ly Do": "Ly do V11",
        }

        cols = [c for c in cols_map.keys() if c in out.columns]
        view = out[cols].copy().rename(columns=cols_map)

        return view.head(limit).replace({np.nan: ""})

    except Exception as e:
        return pd.DataFrame([{"Loi": repr(e)}])
