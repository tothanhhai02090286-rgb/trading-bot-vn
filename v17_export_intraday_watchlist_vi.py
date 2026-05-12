# -*- coding: utf-8 -*-
"""
v17_export_intraday_watchlist_vi.py

SAFE FIX:
- Ưu tiên lấy watchlist từ TOP MUA THẬT + TOP THEO DÕI trong ai_risk_dashboard.html.
- Nếu không đọc được HTML: fallback sang ai_risk_filtered.csv / v17_final_decision.csv / all_signal_results.csv.
- Không crash vì lỗi đọc HTML.
- Output giữ tên cũ: intraday_watchlist_v17.csv
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Optional

import pandas as pd
import requests

DASHBOARD_PATH = os.getenv("AI_RISK_DASHBOARD_PATH", "ai_risk_dashboard.html")
OUTPUT_PATH = os.getenv("INTRADAY_WATCHLIST_OUTPUT", "intraday_watchlist_v17.csv")
MAX_WATCHLIST_ROWS = int(os.getenv("MAX_WATCHLIST_ROWS", "10"))

FALLBACK_FILES = [
    "ai_risk_filtered.csv",
    "v17_final_decision.csv",
    "all_signal_results.csv",
]

TOP_MUA_TITLE = "TOP MUA THẬT"
TOP_THEO_DOI_TITLE = "TOP THEO DÕI"


def _safe_num(series: pd.Series, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
    return out


def _find_col(df: pd.DataFrame, names: List[str]) -> Optional[str]:
    lower_map = {str(c).strip().lower(): c for c in df.columns}
    for n in names:
        if n.lower() in lower_map:
            return lower_map[n.lower()]
    for c in df.columns:
        lc = str(c).strip().lower()
        for n in names:
            if n.lower() in lc:
                return c
    return None


def _find_table_after_heading(html: str, heading_keyword: str) -> Optional[pd.DataFrame]:
    idx = html.find(heading_keyword)
    if idx < 0:
        return None

    sub_html = html[idx:]
    try:
        tables = pd.read_html(sub_html)
    except Exception as e:
        print(f"WARN: không đọc được table sau heading {heading_keyword}: {e}")
        return None

    if not tables:
        return None

    return _normalize_columns(tables[0])


def _standardize_for_render(df: pd.DataFrame, source_group: str) -> pd.DataFrame:
    out = _normalize_columns(df)

    ma_col = _find_col(out, ["Mã", "Ma", "Ticker", "Symbol", "Mã CP", "Stock"])
    if ma_col is None:
        return pd.DataFrame()

    out["Mã"] = out[ma_col].astype(str).str.upper().str.strip()
    out = out[out["Mã"].str.match(r"^[A-Z0-9]{2,10}$", na=False)].copy()

    if out.empty:
        return out

    action_col = _find_col(out, ["Hành động hiện tại", "Hành động", "Action", "Hanh dong"])
    if action_col and "Hành động" not in out.columns:
        out["Hành động"] = out[action_col]

    gia_col = _find_col(out, ["Giá", "Gia", "Close", "price"])
    if gia_col and "Giá tham chiếu" not in out.columns:
        out["Giá tham chiếu"] = out[gia_col]

    if source_group == "TOP_MUA_THAT":
        out["Nhóm realtime"] = "MUA - TOP MUA THẬT"
    else:
        out["Nhóm realtime"] = "THEO DÕI - TOP THEO DÕI"

    for col in ["Buy zone thấp", "Buy zone cao", "Stoploss tham khảo"]:
        if col not in out.columns:
            out[col] = ""

    out["Nguồn watchlist"] = source_group
    return out


def _fallback_from_csv() -> pd.DataFrame:
    for f in FALLBACK_FILES:
        if not Path(f).exists():
            continue

        try:
            df = pd.read_csv(f)
            df = _normalize_columns(df)
            print(f"WARN: fallback đọc {f}, rows={len(df)}")

            ma_col = _find_col(df, ["Mã", "Ma", "Ticker", "Symbol", "Stock"])
            if ma_col is None:
                continue

            df["Mã"] = df[ma_col].astype(str).str.upper().str.strip()
            df = df[df["Mã"].str.match(r"^[A-Z0-9]{2,10}$", na=False)].copy()

            risk_col = _find_col(df, ["Risk", "Rủi ro", "Rui ro"])
            if risk_col is not None and df[risk_col].astype(str).str.upper().str.contains("PASS").any():
                df = df[df[risk_col].astype(str).str.upper().str.contains("PASS", na=False)].copy()

            action_col = _find_col(df, ["Action", "Hành động", "Hành động hiện tại", "Hanh dong"])
            if action_col is not None:
                bad = df[action_col].astype(str).str.upper().str.contains("SKIP|BỎ QUA|BO QUA|FAIL", na=False)
                df = df[~bad].copy()

            score_col = _find_col(df, ["Score", "Điểm", "Diem"])
            if score_col is not None:
                df["_score_sort"] = _safe_num(df[score_col])
            else:
                df["_score_sort"] = 0

            ai_col = _find_col(df, ["AI"])
            if ai_col is not None:
                df["_ai_sort"] = _safe_num(df[ai_col])
            else:
                df["_ai_sort"] = 0

            df = df.sort_values(["_score_sort", "_ai_sort"], ascending=False)
            df = df.drop_duplicates("Mã", keep="first").head(MAX_WATCHLIST_ROWS).copy()
            df["Nguồn watchlist"] = f"FALLBACK_{f}"
            df["Nhóm realtime"] = "FALLBACK - CSV"

            df = df.drop(columns=[c for c in ["_score_sort", "_ai_sort"] if c in df.columns])
            return df.reset_index(drop=True)

        except Exception as e:
            print(f"WARN: fallback {f} lỗi: {e}")

    return pd.DataFrame()


def build_watchlist_from_dashboard(html_path: str = DASHBOARD_PATH) -> pd.DataFrame:
    p = Path(html_path)
    frames: List[pd.DataFrame] = []

    if p.exists():
        html = p.read_text(encoding="utf-8", errors="ignore")

        top_mua = _find_table_after_heading(html, TOP_MUA_TITLE)
        top_theo_doi = _find_table_after_heading(html, TOP_THEO_DOI_TITLE)

        if top_mua is not None and not top_mua.empty:
            frames.append(_standardize_for_render(top_mua, "TOP_MUA_THAT"))

        if top_theo_doi is not None and not top_theo_doi.empty:
            frames.append(_standardize_for_render(top_theo_doi, "TOP_THEO_DOI"))
    else:
        print(f"WARN: không thấy file dashboard {html_path}")

    frames = [x for x in frames if x is not None and not x.empty]

    if frames:
        out = pd.concat(frames, ignore_index=True, sort=False)

        risk_col = _find_col(out, ["Risk", "Rủi ro", "Rui ro"])
        if risk_col is not None and out[risk_col].astype(str).str.upper().str.contains("PASS").any():
            out = out[out[risk_col].astype(str).str.upper().str.contains("PASS", na=False)].copy()

        out["_priority_source"] = out["Nguồn watchlist"].map({"TOP_MUA_THAT": 0, "TOP_THEO_DOI": 1}).fillna(9)

        score_col = _find_col(out, ["Score", "Điểm", "Diem"])
        out["_score_sort"] = _safe_num(out[score_col]) if score_col else 0

        ai_col = _find_col(out, ["AI"])
        out["_ai_sort"] = _safe_num(out[ai_col]) if ai_col else 0

        out = out.sort_values(["_priority_source", "_score_sort", "_ai_sort"], ascending=[True, False, False])
        out = out.drop_duplicates(subset=["Mã"], keep="first")

        if MAX_WATCHLIST_ROWS > 0:
            out = out.head(MAX_WATCHLIST_ROWS).copy()

        out = out.drop(columns=[c for c in ["_priority_source", "_score_sort", "_ai_sort"] if c in out.columns])
        return out.reset_index(drop=True)

    print("WARN: Không đọc được TOP MUA THẬT / TOP THEO DÕI từ HTML, fallback sang CSV")
    return _fallback_from_csv()


def _send_telegram(msg: str) -> None:
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("WARN: thiếu TELEGRAM_TOKEN hoặc TELEGRAM_CHAT_ID")
        return

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = requests.post(url, data={"chat_id": chat_id, "text": msg}, timeout=20)
        print(f"TELEGRAM STATUS: {r.status_code} {r.text[:300]}")
    except Exception as e:
        print(f"WARN: gửi Telegram lỗi: {e}")


def main():
    watchlist = build_watchlist_from_dashboard(DASHBOARD_PATH)

    if watchlist.empty:
        watchlist = pd.DataFrame(columns=["Mã", "Nhóm realtime", "Nguồn watchlist"])

    watchlist.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    tickers = watchlist["Mã"].astype(str).tolist() if "Mã" in watchlist.columns else []
    print("✅ V17 EXPORT WATCHLIST CHO RENDER HOÀN TẤT")
    print(f"Source: {DASHBOARD_PATH} hoặc fallback CSV")
    print(f"Output: {OUTPUT_PATH}")
    print(f"Rows: {len(watchlist)}")
    print(f"Tickers: {', '.join(tickers)}")

    lines = [
        "✅ V17 EXPORT WATCHLIST CHO RENDER HOÀN TẤT",
        "",
        f"Nguồn: TOP MUA THẬT + TOP THEO DÕI hoặc fallback CSV",
        f"Output: {OUTPUT_PATH}",
        f"Số mã theo dõi: {len(watchlist)}",
        "",
        "TOP WATCHLIST RENDER",
    ]

    for _, r in watchlist.iterrows():
        ma = r.get("Mã", "")
        score = r.get("Score", r.get("Điểm", ""))
        try:
            score_txt = f"{float(score):.2f}"
        except Exception:
            score_txt = str(score) if str(score) else "0"
        group = str(r.get("Nhóm realtime", ""))
        state = "WATCH" if "THEO" in group.upper() or "WATCH" in group.upper() else "WAIT"
        label = "THEO DÕI" if state == "WATCH" else "CHỜ ĐIỂM ĐẸP"
        lines.append(f"🔹 {ma} | 🟡 {label} | Điểm {score_txt} | {state}")

    _send_telegram("\n".join(lines))


if __name__ == "__main__":
    main()
