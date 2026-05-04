# ============================================================
# V11 MARKET OVERLAY - VIET HOA
# Layer phu sau V10. KHONG thay doi core signal goc.
# ============================================================

import pandas as pd
import numpy as np


def _safe_float(x, default=np.nan):
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _norm_text(x):
    try:
        return str(x).strip().upper()
    except Exception:
        return ""


def _norm_regime(x):
    try:
        s = str(x).strip().upper()
        if "/" in s:
            s = s.split("/")[-1].strip()
        return s.replace(" ", "")
    except Exception:
        return ""


def tinh_ret1_tu_df(df):
    if df is None or df.empty:
        return df
    out = df.copy()

    if "Ret1 %" in out.columns:
        out["Ret1_tmp"] = pd.to_numeric(out["Ret1 %"], errors="coerce")
        return out
    if "Ret1" in out.columns:
        out["Ret1_tmp"] = pd.to_numeric(out["Ret1"], errors="coerce")
        return out

    close_col = "Close" if "Close" in out.columns else "close" if "close" in out.columns else None
    prev_col = None
    for c in ["Prev Close", "PrevClose", "Close Prev", "close_prev", "prev_close"]:
        if c in out.columns:
            prev_col = c
            break

    if close_col and prev_col:
        close = pd.to_numeric(out[close_col], errors="coerce")
        prev = pd.to_numeric(out[prev_col], errors="coerce")
        out["Ret1_tmp"] = (close / prev - 1) * 100
    else:
        out["Ret1_tmp"] = np.nan
    return out


def tinh_do_rong_thi_truong(df):
    if df is None or df.empty:
        return 0.0, 0, 0, "KHONG CO DU LIEU"

    d = tinh_ret1_tu_df(df)

    if "Ret1_tmp" in d.columns and d["Ret1_tmp"].notna().sum() > 0:
        valid = d["Ret1_tmp"].dropna()
        so_ma = len(valid)
        so_ma_tang = int((valid > 0).sum())
        breadth = (so_ma_tang / so_ma * 100) if so_ma > 0 else 0
        return round(breadth, 2), so_ma_tang, so_ma, "RET1"

    if "RS20" in d.columns:
        rs = pd.to_numeric(d["RS20"], errors="coerce").dropna()
        so_ma = len(rs)
        so_ma_manh = int((rs > 0).sum())
        breadth = (so_ma_manh / so_ma * 100) if so_ma > 0 else 0
        return round(breadth, 2), so_ma_manh, so_ma, "RS20_FALLBACK"

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
    reasons = [f"Thi truong: {market_label}", f"Nguong RS20 V11: {nguong_rs20}"]
    rs20 = _safe_float(row.get("RS20"), np.nan)
    risk = _norm_text(row.get("Risk Status", ""))
    if not pd.isna(rs20):
        reasons.append("RS20 dat nguong V11" if rs20 >= nguong_rs20 else "RS20 chua dat nguong V11")
    if risk == "FAIL":
        reasons.append("Risk FAIL")
    return "; ".join(reasons)


def ap_dung_v11_market_overlay(df, market_score=0):
    if df is None or df.empty:
        summary = pd.DataFrame([{"Chi tieu": "Trang thai", "Gia tri": "Khong co du lieu"}])
        return pd.DataFrame(), summary

    out = df.copy()
    breadth, so_ma_tang, tong_ma, breadth_source = tinh_do_rong_thi_truong(out)
    market_label = danh_gia_chat_luong_thi_truong(market_score, breadth)
    rs20_threshold = nguong_rs20_theo_thi_truong(market_label)

    out["V11 Danh Gia Thi Truong"] = market_label
    out["V11 Do Rong Thi Truong %"] = breadth
    out["V11 Nguong RS20"] = rs20_threshold
    out["V11 Xep Hang RS20"] = out.get("RS20", pd.Series([np.nan] * len(out))).apply(xep_hang_leader_rs20)
    out["V11 Hanh Dong"] = out.apply(lambda r: dieu_chinh_hanh_dong_v11(r, rs20_threshold), axis=1)
    out["V11 Ly Do"] = out.apply(lambda r: ly_do_overlay_v11(r, market_label, rs20_threshold), axis=1)

    summary = pd.DataFrame([
        {"Chi tieu": "Market Score V10", "Gia tri": round(_safe_float(market_score, 0), 2)},
        {"Chi tieu": "Do rong thi truong", "Gia tri": f"{breadth}%"},
        {"Chi tieu": "So ma tang/manh", "Gia tri": f"{so_ma_tang}/{tong_ma}"},
        {"Chi tieu": "Nguon do rong", "Gia tri": breadth_source},
        {"Chi tieu": "Ket luan V11", "Gia tri": market_label},
        {"Chi tieu": "Nguong RS20 ap dung", "Gia tri": rs20_threshold},
    ])
    return out, summary


def tao_bang_v11_leader(df, limit=10):
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    cols = [c for c in ["Ngay", "Ma", "Close", "Rec", "V11 Hanh Dong", "V11 Xep Hang RS20",
                        "RS20", "Score", "AI Confidence", "Risk Status", "V11 Ly Do"] if c in out.columns]
    view = out[cols].copy()
    view = view.rename(columns={
        "Close": "Gia", "Rec": "Hanh dong V10", "V11 Hanh Dong": "Hanh dong V11",
        "V11 Xep Hang RS20": "Xep hang RS20", "AI Confidence": "AI",
        "Risk Status": "Risk", "V11 Ly Do": "Ly do V11",
    })
    for c in ["RS20", "Score", "AI"]:
        if c in view.columns:
            view[c] = pd.to_numeric(view[c], errors="coerce")
    sort_cols = [c for c in ["RS20", "AI", "Score"] if c in view.columns]
    if sort_cols:
        view = view.sort_values(sort_cols, ascending=[False] * len(sort_cols))
    return view.head(limit).replace({np.nan: ""})


def tao_bang_v11_bi_ha_hang(df, limit=20):
    if df is None or df.empty or "V11 Hanh Dong" not in df.columns:
        return pd.DataFrame()
    rec_col = "Rec" if "Rec" in df.columns else "Action" if "Action" in df.columns else None
    if rec_col is None:
        return pd.DataFrame()
    out = df[df[rec_col].astype(str) != df["V11 Hanh Dong"].astype(str)].copy()
    if out.empty:
        return pd.DataFrame()
    cols = [c for c in ["Ngay", "Ma", "Close", rec_col, "V11 Hanh Dong", "RS20",
                        "V11 Nguong RS20", "Risk Status", "V11 Ly Do"] if c in out.columns]
    view = out[cols].rename(columns={
        "Close": "Gia", rec_col: "Hanh dong V10", "V11 Hanh Dong": "Hanh dong V11",
        "V11 Nguong RS20": "Nguong RS20 V11", "Risk Status": "Risk", "V11 Ly Do": "Ly do V11",
    })
    return view.head(limit).replace({np.nan: ""})
