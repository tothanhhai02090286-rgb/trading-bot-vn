# -*- coding: utf-8 -*-
"""
v17_export_intraday_watchlist_vi.py

FIX ONLY ONE ISSUE:
- Nguồn export watchlist cho Render KHÔNG lấy từ v17_final_decision.csv nữa.
- Thay bằng 2 bảng cuối đã lọc trong ai_risk_dashboard.html:
  1) TOP MUA THẬT - ƯU TIÊN CAO
  2) TOP THEO DÕI - CHƯA MUA VỘI

Output giữ tên cũ để Render không cần đổi RAW_URL:
- intraday_watchlist_v17.csv

Không sửa logic Render / V18.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import pandas as pd

DASHBOARD_PATH = os.getenv("AI_RISK_DASHBOARD_PATH", "ai_risk_dashboard.html")
OUTPUT_PATH = os.getenv("INTRADAY_WATCHLIST_OUTPUT", "intraday_watchlist_v17.csv")
MAX_WATCHLIST_ROWS = int(os.getenv("MAX_WATCHLIST_ROWS", "10"))

TOP_MUA_TITLE = "TOP MUA THẬT"
TOP_THEO_DOI_TITLE = "TOP THEO DÕI"


def _safe_num(series: pd.Series, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
    return out


def _find_table_after_heading(html: str, heading_keyword: str) -> Optional[pd.DataFrame]:
    """Tìm table đầu tiên sau heading có chứa heading_keyword."""
    idx = html.find(heading_keyword)
    if idx < 0:
        return None

    sub_html = html[idx:]
    try:
        tables = pd.read_html(sub_html)
    except Exception:
        return None

    if not tables:
        return None

    return _normalize_columns(tables[0])


def _standardize_for_render(df: pd.DataFrame, source_group: str) -> pd.DataFrame:
    """Chuẩn hóa cột để V18 Render đọc được."""
    out = df.copy()

    # Chuẩn hóa tên mã
    if "Mã" not in out.columns:
        for c in ["Ma", "Ticker", "Symbol", "Mã CP"]:
            if c in out.columns:
                out["Mã"] = out[c]
                break

    if "Mã" not in out.columns:
        return pd.DataFrame()

    out["Mã"] = out["Mã"].astype(str).str.upper().str.strip()
    out = out[(out["Mã"] != "") & (out["Mã"] != "NAN")].copy()

    # Render v18 đang dùng các cột này nếu có
    if "Hành động hiện tại" in out.columns and "Hành động" not in out.columns:
        out["Hành động"] = out["Hành động hiện tại"]

    if "Giá" in out.columns and "Giá tham chiếu" not in out.columns:
        out["Giá tham chiếu"] = out["Giá"]

    # Nhóm realtime cho V18 nhận diện MUA/THEO DÕI
    if source_group == "TOP_MUA_THAT":
        out["Nhóm realtime"] = "MUA - TOP MUA THẬT"
    else:
        out["Nhóm realtime"] = "THEO DÕI - TOP THEO DÕI"

    # Nếu HTML không có buy zone/stoploss thì để trống, V18 vẫn fallback bằng giá/ref/VWAP
    for col in ["Buy zone thấp", "Buy zone cao", "Stoploss tham khảo"]:
        if col not in out.columns:
            out[col] = ""

    # Cột nguồn để dễ kiểm tra
    out["Nguồn watchlist"] = source_group

    return out


def build_watchlist_from_dashboard(html_path: str = DASHBOARD_PATH) -> pd.DataFrame:
    p = Path(html_path)
    if not p.exists():
        raise FileNotFoundError(f"Không thấy file dashboard: {html_path}")

    html = p.read_text(encoding="utf-8", errors="ignore")

    top_mua = _find_table_after_heading(html, TOP_MUA_TITLE)
    top_theo_doi = _find_table_after_heading(html, TOP_THEO_DOI_TITLE)

    frames: List[pd.DataFrame] = []

    if top_mua is not None and not top_mua.empty:
        frames.append(_standardize_for_render(top_mua, "TOP_MUA_THAT"))

    if top_theo_doi is not None and not top_theo_doi.empty:
        frames.append(_standardize_for_render(top_theo_doi, "TOP_THEO_DOI"))

    if not frames:
        raise RuntimeError("Không đọc được bảng TOP MUA THẬT / TOP THEO DÕI từ ai_risk_dashboard.html")

    out = pd.concat(frames, ignore_index=True)

    # Chỉ lấy PASS nếu cột Risk có tồn tại trong HTML top tables
    if "Risk" in out.columns:
        out = out[out["Risk"].astype(str).str.upper().str.strip().eq("PASS")].copy()

    # Bỏ trùng mã: ưu tiên TOP MUA THẬT trước TOP THEO DÕI
    out["_priority_source"] = out["Nguồn watchlist"].map({"TOP_MUA_THAT": 0, "TOP_THEO_DOI": 1}).fillna(9)

    # Sort nhẹ theo nhóm + Score/AI nếu có, không thêm tiêu chí mới ngoài việc lấy từ top HTML
    if "Score" in out.columns:
        out["_score_sort"] = _safe_num(out["Score"])
    else:
        out["_score_sort"] = 0

    if "AI" in out.columns:
        out["_ai_sort"] = _safe_num(out["AI"])
    else:
        out["_ai_sort"] = 0

    out = out.sort_values(["_priority_source", "_score_sort", "_ai_sort"], ascending=[True, False, False])
    out = out.drop_duplicates(subset=["Mã"], keep="first")

    if MAX_WATCHLIST_ROWS > 0:
        out = out.head(MAX_WATCHLIST_ROWS).copy()

    out = out.drop(columns=[c for c in ["_priority_source", "_score_sort", "_ai_sort"] if c in out.columns])
    out = out.reset_index(drop=True)

    return out


def main():
    watchlist = build_watchlist_from_dashboard(DASHBOARD_PATH)
    watchlist.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    tickers = watchlist["Mã"].astype(str).tolist() if "Mã" in watchlist.columns else []
    print("EXPORT INTRADAY WATCHLIST FROM HTML TOP TABLES DONE")
    print(f"SOURCE HTML: {DASHBOARD_PATH}")
    print(f"OUTPUT: {OUTPUT_PATH}")
    print(f"ROWS: {len(watchlist)}")
    print(f"TICKERS: {', '.join(tickers)}")


if __name__ == "__main__":
    main()
