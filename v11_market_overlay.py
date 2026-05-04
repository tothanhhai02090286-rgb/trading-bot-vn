# -*- coding: utf-8 -*-
# ============================================================
# V11 MARKET OVERLAY PRO - CHUAN BREADTH TU CACHE
# Layer phu sau V10. KHONG thay doi core signal goc.
#
# Chuc nang:
# - Doc truc tiep cache_stock/*.csv de tinh Ret1 that
# - Breadth = % so ma tang trong phien moi nhat
# - Kiem tra data dong bo theo ngay moi nhat
# - Neu cache doc duoc -> dung RET1_CACHE
# - Neu cache khong doc duoc -> fallback an toan sang Ret1 co san / RS20
# - Tao dashboard Viet hoa:
#   DANH GIA THI TRUONG V11
#   V11 - TOP LEADER RS20
#   V11 - MA BI HA HANG DO BOI CANH THI TRUONG
# ============================================================

import os
from pathlib import Path
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


def _norm_text(x):
    try:
        return str(x).strip().upper()
    except Exception:
        return ""


def _pick_col(df, names):
    if df is None or df.empty:
        return None
    lower_map = {str(c).lower().strip(): c for c in df.columns}
    for name in names:
        if name in df.columns:
            return name
        key = str(name).lower().strip()
        if key in lower_map:
            return lower_map[key]
    return None


def _get_code_col(df):
    return _pick_col(df, ["Ma", "Code", "Mã", "symbol", "ticker"])


def _get_cache_dir():
    """
    Tim thu muc cache_stock theo cac vi tri pho bien trong he thong cua ban.
    Uu tien bien moi truong / v10_config neu co.
    """
    candidates = []

    # Environment
    for env_name in ["CACHE_DIR", "CACHE_STOCK_DIR", "STOCK_CACHE_DIR", "BOT_CACHE_DIR"]:
        v = os.environ.get(env_name)
        if v:
            candidates.append(v)

    # Common Google Drive paths
    candidates += [
        "/content/drive/MyDrive/cache_stock",
        "/content/drive/MyDrive/thumucbot/cache_stock",
        "/content/drive/MyDrive/stock_cache",
        "./cache_stock",
        "cache_stock",
    ]

    # Try v10_config if available
    try:
        import v10_config
        for attr in ["CACHE_DIR", "CACHE_STOCK_DIR", "STOCK_CACHE_DIR"]:
            if hasattr(v10_config, attr):
                candidates.insert(0, getattr(v10_config, attr))
    except Exception:
        pass

    for p in candidates:
        try:
            pp = Path(p)
            if pp.exists() and pp.is_dir():
                return pp
        except Exception:
            continue

    # default fallback
    return Path("/content/drive/MyDrive/cache_stock")


def _read_cache_csv_for_code(cache_dir, code):
    """
    Doc file cache cua 1 ma.
    Chap nhan ten CODE.csv.
    """
    try:
        code = str(code).strip().upper()
        if not code:
            return pd.DataFrame()

        paths = [
            Path(cache_dir) / f"{code}.csv",
            Path(cache_dir) / f"{code.lower()}.csv",
        ]

        for p in paths:
            if p.exists():
                return pd.read_csv(p)

    except Exception:
        return pd.DataFrame()

    return pd.DataFrame()


def _normalize_cache_df(df):
    """
    Chuan hoa cot date/time va close.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()

    date_col = _pick_col(out, ["time", "date", "datetime", "Ngay", "Ngày"])
    close_col = _pick_col(out, ["close", "Close", "Gia", "Giá"])

    if date_col is None or close_col is None:
        return pd.DataFrame()

    out["_date"] = pd.to_datetime(out[date_col], errors="coerce")
    out["_close"] = pd.to_numeric(out[close_col], errors="coerce")
    out = out.dropna(subset=["_date", "_close"]).sort_values("_date").reset_index(drop=True)

    return out


def tinh_ret1_cache_1_ma(cache_dir, code):
    """
    Ret1 = close phien moi nhat / close phien truoc - 1.
    """
    raw = _read_cache_csv_for_code(cache_dir, code)
    df = _normalize_cache_df(raw)

    if df.empty or len(df) < 2:
        return {
            "Ma": code,
            "Ngay moi nhat": "",
            "Close moi nhat": np.nan,
            "Close truoc": np.nan,
            "Ret1 %": np.nan,
            "Co data": False,
        }

    last = df.iloc[-1]
    prev = df.iloc[-2]

    close_last = _safe_float(last["_close"], np.nan)
    close_prev = _safe_float(prev["_close"], np.nan)

    if pd.isna(close_last) or pd.isna(close_prev) or close_prev == 0:
        ret1 = np.nan
    else:
        ret1 = (close_last / close_prev - 1) * 100

    return {
        "Ma": str(code).upper(),
        "Ngay moi nhat": str(pd.to_datetime(last["_date"]).date()),
        "Close moi nhat": close_last,
        "Close truoc": close_prev,
        "Ret1 %": ret1,
        "Co data": True,
    }


def tinh_breadth_tu_cache(signal_df=None, universe=None, cache_dir=None):
    """
    Tinh breadth that tu cache:
    - Lay danh sach ma tu signal_df neu co
    - Hoac universe neu co
    - Doc cache cua tung ma
    - Chi tinh cac ma co cung ngay moi nhat nhieu nhat
    """
    if cache_dir is None:
        cache_dir = _get_cache_dir()

    codes = []

    if universe is not None:
        try:
            codes = [str(x).strip().upper() for x in universe if str(x).strip()]
        except Exception:
            codes = []

    if not codes and signal_df is not None and not signal_df.empty:
        code_col = _get_code_col(signal_df)
        if code_col:
            codes = sorted(set(signal_df[code_col].dropna().astype(str).str.upper().tolist()))

    if not codes:
        return pd.DataFrame(), {
            "breadth": 0.0,
            "so_tang": 0,
            "tong_ma": 0,
            "source": "CACHE_KHONG_CO_DANH_SACH_MA",
            "data_date": "",
            "coverage_pct": 0.0,
        }

    rows = []
    for code in codes:
        rows.append(tinh_ret1_cache_1_ma(cache_dir, code))

    df = pd.DataFrame(rows)
    if df.empty or "Co data" not in df.columns:
        return df, {
            "breadth": 0.0,
            "so_tang": 0,
            "tong_ma": 0,
            "source": "CACHE_DOC_LOI",
            "data_date": "",
            "coverage_pct": 0.0,
        }

    valid = df[df["Co data"] == True].copy()
    if valid.empty:
        return df, {
            "breadth": 0.0,
            "so_tang": 0,
            "tong_ma": len(codes),
            "source": "CACHE_KHONG_CO_DATA",
            "data_date": "",
            "coverage_pct": 0.0,
        }

    # Chon ngay moi nhat co nhieu ma nhat de tranh partial date
    date_counts = valid["Ngay moi nhat"].value_counts()
    data_date = date_counts.index[0]
    same_date = valid[valid["Ngay moi nhat"] == data_date].copy()

    tong_ma = len(same_date)
    so_tang = int((pd.to_numeric(same_date["Ret1 %"], errors="coerce") > 0).sum())
    breadth = round(so_tang / tong_ma * 100, 2) if tong_ma > 0 else 0.0
    coverage_pct = round(tong_ma / max(len(codes), 1) * 100, 2)

    return df, {
        "breadth": breadth,
        "so_tang": so_tang,
        "tong_ma": tong_ma,
        "source": "RET1_CACHE",
        "data_date": data_date,
        "coverage_pct": coverage_pct,
    }


def tinh_do_rong_fallback(df):
    """
    Fallback neu khong doc duoc cache:
    1) Ret1 co san trong df
    2) RS20 > 0
    """
    if df is None or df.empty:
        return 0.0, 0, 0, "KHONG CO DU LIEU"

    ret_col = _pick_col(df, ["Ret1 %", "Ret1", "ret1", "ret1_pct"])
    if ret_col:
        ret = pd.to_numeric(df[ret_col], errors="coerce").dropna()
        if len(ret) > 0:
            so_tang = int((ret > 0).sum())
            breadth = round(so_tang / len(ret) * 100, 2)
            return breadth, so_tang, len(ret), "RET1_DF"

    rs_col = _pick_col(df, ["RS20", "rs20"])
    if rs_col:
        rs = pd.to_numeric(df[rs_col], errors="coerce").dropna()
        if len(rs) > 0:
            so_manh = int((rs > 0).sum())
            breadth = round(so_manh / len(rs) * 100, 2)
            return breadth, so_manh, len(rs), "RS20_FALLBACK"

    return 0.0, 0, len(df), "KHONG CO RET1/RS20"


def danh_gia_chat_luong_thi_truong(market_score=0, breadth=0, coverage_pct=100):
    """
    Danh gia thi truong dua tren:
    - market_score V10
    - breadth that
    - coverage data cache
    """
    ms = _safe_float(market_score, 0)
    br = _safe_float(breadth, 0)
    cov = _safe_float(coverage_pct, 0)

    if cov < 80:
        return "DATA CHUA DONG BO - KHONG DANH GIA"

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

    if "DATA CHUA DONG BO" in label:
        return -999  # khong ha hang khi data chua dong bo

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


def dieu_chinh_hanh_dong_v11(row, nguong_rs20, market_label):
    rec = str(row.get("Rec", row.get("Action", row.get("Final Action", ""))))
    risk = _norm_text(row.get("Risk Status", ""))
    rs20 = _safe_float(row.get("RS20"), np.nan)

    if "DATA CHUA DONG BO" in _norm_text(market_label):
        return rec

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
        f"Nguong RS20 V11: {nguong_rs20}",
    ]

    rs20 = _safe_float(row.get("RS20"), np.nan)
    risk = _norm_text(row.get("Risk Status", ""))

    if not pd.isna(rs20):
        reasons.append("RS20 dat nguong V11" if rs20 >= nguong_rs20 else "RS20 chua dat nguong V11")

    if risk == "FAIL":
        reasons.append("Risk FAIL")

    return "; ".join(reasons)


def ap_dung_v11_market_overlay(df, market_score=0, universe=None, cache_dir=None):
    """
    Ham chinh runner goi.
    Input:
    - df: bang signal V10
    - market_score: diem thi truong V10 neu co
    - universe/cache_dir: optional. Neu khong co, ham tu tim cache_stock.

    Output:
    - df them cot V11
    - bang tom tat V11
    """
    try:
        if df is None or df.empty:
            summary = pd.DataFrame([{"Chi tieu": "Trang thai", "Gia tri": "Khong co du lieu dau vao"}])
            return pd.DataFrame(), summary

        out = df.copy()

        cache_detail, cache_info = tinh_breadth_tu_cache(out, universe=universe, cache_dir=cache_dir)

        if cache_info.get("source") == "RET1_CACHE" and cache_info.get("tong_ma", 0) > 0:
            breadth = cache_info["breadth"]
            so_ma_tang = cache_info["so_tang"]
            tong_ma = cache_info["tong_ma"]
            source = cache_info["source"]
            data_date = cache_info["data_date"]
            coverage_pct = cache_info["coverage_pct"]
        else:
            breadth, so_ma_tang, tong_ma, source = tinh_do_rong_fallback(out)
            data_date = ""
            coverage_pct = 100 if tong_ma > 0 else 0

        market_label = danh_gia_chat_luong_thi_truong(market_score, breadth, coverage_pct)
        rs20_threshold = nguong_rs20_theo_thi_truong(market_label)

        out["V11 Danh Gia Thi Truong"] = market_label
        out["V11 Do Rong Thi Truong %"] = breadth
        out["V11 Nguong RS20"] = rs20_threshold
        out["V11 Data Date"] = data_date
        out["V11 Coverage %"] = coverage_pct

        if "RS20" in out.columns:
            out["V11 Xep Hang RS20"] = out["RS20"].apply(xep_hang_leader_rs20)
        else:
            out["V11 Xep Hang RS20"] = "CHUA CO RS20"

        out["V11 Hanh Dong"] = out.apply(
            lambda r: dieu_chinh_hanh_dong_v11(r, rs20_threshold, market_label),
            axis=1
        )

        out["V11 Ly Do"] = out.apply(
            lambda r: ly_do_overlay_v11(r, market_label, rs20_threshold),
            axis=1
        )

        summary = pd.DataFrame([
            {"Chi tieu": "Market Score V10", "Gia tri": round(_safe_float(market_score, 0), 2)},
            {"Chi tieu": "Data date cache", "Gia tri": data_date if data_date else "Khong xac dinh"},
            {"Chi tieu": "Do rong thi truong", "Gia tri": f"{breadth}%"},
            {"Chi tieu": "So ma tang/manh", "Gia tri": f"{so_ma_tang}/{tong_ma}"},
            {"Chi tieu": "Coverage cache", "Gia tri": f"{coverage_pct}%"},
            {"Chi tieu": "Nguon do rong", "Gia tri": source},
            {"Chi tieu": "Ket luan V11", "Gia tri": market_label},
            {"Chi tieu": "Nguong RS20 ap dung", "Gia tri": rs20_threshold},
        ])

        return out, summary

    except Exception as e:
        summary = pd.DataFrame([{"Chi tieu": "Loi V11 Overlay", "Gia tri": repr(e)}])
        return df.copy() if df is not None else pd.DataFrame(), summary


def tao_bang_v11_leader(df, limit=10):
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
