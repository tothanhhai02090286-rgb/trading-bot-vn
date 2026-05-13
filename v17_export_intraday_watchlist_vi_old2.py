# -*- coding: utf-8 -*-
"""
v17_export_intraday_watchlist_vi.py

FIX ĐÚNG 1 VẤN ĐỀ:
- Watchlist Render CHỈ lấy từ 2 bảng cuối trong ai_risk_dashboard.html:
  1) TOP MUA THẬT
  2) TOP THEO DÕI
- KHÔNG fallback sang CSV nữa, để tránh kéo nhầm mã ❌ LOẠI từ V17 nền.
- Nếu không đọc được 2 bảng dashboard: tạo intraday_watchlist_v17.csv rỗng và gửi cảnh báo Telegram.
"""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import List, Optional

import pandas as pd
import requests

DASHBOARD_PATH = os.getenv("AI_RISK_DASHBOARD_PATH", "ai_risk_dashboard.html")
OUTPUT_PATH = os.getenv("INTRADAY_WATCHLIST_OUTPUT", "intraday_watchlist_v17.csv")
MAX_WATCHLIST_ROWS = int(os.getenv("MAX_WATCHLIST_ROWS", "10"))

TOP_MUA_TITLE = "TOP MUA THẬT"
TOP_THEO_DOI_TITLE = "TOP THEO DÕI"


def strip_accents(s: str) -> str:
    s = str(s)
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def norm_text(s: str) -> str:
    s = strip_accents(str(s)).upper()
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def norm_col(c: str) -> str:
    c = strip_accents(str(c)).lower().strip()
    c = re.sub(r"[^a-z0-9]+", "_", c)
    return c.strip("_")


def find_col(df: pd.DataFrame, names: List[str]) -> Optional[str]:
    if df is None or df.empty:
        return None
    mp = {norm_col(c): c for c in df.columns}
    for n in names:
        k = norm_col(n)
        if k in mp:
            return mp[k]
    for c in df.columns:
        nc = norm_col(c)
        for n in names:
            if norm_col(n) in nc:
                return c
    return None


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
    return out


def find_table_after_heading(html: str, heading_keyword: str) -> Optional[pd.DataFrame]:
    """
    Tìm table đầu tiên sau heading.
    Dùng tìm không dấu để tránh lỗi encoding/HTML entity.
    """
    html_norm = norm_text(html)
    key_norm = norm_text(heading_keyword)
    idx_norm = html_norm.find(key_norm)

    # Nếu không tìm bằng normalized text, fallback tìm thẳng.
    idx_raw = html.find(heading_keyword)

    if idx_raw >= 0:
        sub_html = html[idx_raw:]
    elif idx_norm >= 0:
        # Không thể map chính xác index normalized về raw, fallback đọc toàn bộ HTML rồi chọn bảng theo thứ tự.
        sub_html = html
    else:
        return None

    try:
        tables = pd.read_html(sub_html)
    except Exception as e:
        print(f"WARN: Không đọc được table sau heading {heading_keyword}: {e}", flush=True)
        return None

    if not tables:
        return None

    # Nếu đọc từ đoạn sau heading raw, bảng đầu tiên là đúng.
    if idx_raw >= 0:
        return normalize_columns(tables[0])

    return None


def standardize_for_render(df: pd.DataFrame, source_group: str) -> pd.DataFrame:
    out = normalize_columns(df)

    ma_col = find_col(out, ["Mã", "Ma", "Ticker", "Symbol", "Mã CP", "Stock"])
    if ma_col is None:
        return pd.DataFrame()

    out["Mã"] = out[ma_col].astype(str).str.upper().str.strip()
    out = out[out["Mã"].str.match(r"^[A-Z0-9]{2,10}$", na=False)].copy()
    if out.empty:
        return out

    # Chuẩn hóa một số cột Render/V18 có thể đọc.
    action_col = find_col(out, ["Hành động hiện tại", "Hành động", "Action", "Hanh dong"])
    if action_col and "Hành động" not in out.columns:
        out["Hành động"] = out[action_col]

    gia_col = find_col(out, ["Giá", "Gia", "Close", "Price"])
    if gia_col and "Giá tham chiếu" not in out.columns:
        out["Giá tham chiếu"] = out[gia_col]

    qd_col = find_col(out, ["QUYẾT ĐỊNH TỰ ĐỘNG", "Quyet dinh tu dong", "Quyết định"])
    if qd_col and "Quyết định tự động" not in out.columns:
        out["Quyết định tự động"] = out[qd_col]

    # Nhóm realtime rõ ràng.
    if source_group == "TOP_MUA_THAT":
        out["Nhóm realtime"] = "MUA - TOP MUA THẬT"
    else:
        out["Nhóm realtime"] = "THEO DÕI - TOP THEO DÕI"

    for col in ["Buy zone thấp", "Buy zone cao", "Stoploss tham khảo"]:
        if col not in out.columns:
            out[col] = ""

    out["Nguồn watchlist"] = source_group
    return out


def build_watchlist_from_dashboard(html_path: str = DASHBOARD_PATH) -> pd.DataFrame:
    p = Path(html_path)
    frames: List[pd.DataFrame] = []

    if not p.exists():
        print(f"ERROR: Không thấy dashboard: {html_path}", flush=True)
        return pd.DataFrame()

    html = p.read_text(encoding="utf-8", errors="ignore")

    top_mua = find_table_after_heading(html, TOP_MUA_TITLE)
    top_theo_doi = find_table_after_heading(html, TOP_THEO_DOI_TITLE)

    if top_mua is not None and not top_mua.empty:
        x = standardize_for_render(top_mua, "TOP_MUA_THAT")
        if not x.empty:
            frames.append(x)

    if top_theo_doi is not None and not top_theo_doi.empty:
        x = standardize_for_render(top_theo_doi, "TOP_THEO_DOI")
        if not x.empty:
            frames.append(x)

    if not frames:
        print("ERROR: Không đọc được TOP MUA THẬT / TOP THEO DÕI từ dashboard. Không fallback CSV để tránh lấy mã ❌ LOẠI.", flush=True)
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True, sort=False)

    # Chỉ giữ PASS nếu cột Risk có trong dashboard.
    risk_col = find_col(out, ["Risk", "Rủi ro", "Rui ro"])
    if risk_col is not None:
        risk_upper = out[risk_col].astype(str).str.upper()
        if risk_upper.str.contains("PASS", na=False).any():
            out = out[risk_upper.str.contains("PASS", na=False)].copy()

    # Bỏ trùng mã, ưu tiên TOP MUA THẬT trước TOP THEO DÕI.
    out["_priority_source"] = out["Nguồn watchlist"].map({"TOP_MUA_THAT": 0, "TOP_THEO_DOI": 1}).fillna(9)

    # Sort nhẹ theo điểm nếu có, không lấy thêm dữ liệu ngoài dashboard.
    score_col = find_col(out, ["Score", "Điểm", "Diem"])
    if score_col:
        out["_score_sort"] = pd.to_numeric(out[score_col], errors="coerce").fillna(0)
    else:
        out["_score_sort"] = 0

    ai_col = find_col(out, ["AI"])
    if ai_col:
        out["_ai_sort"] = pd.to_numeric(out[ai_col], errors="coerce").fillna(0)
    else:
        out["_ai_sort"] = 0

    out = out.sort_values(["_priority_source", "_score_sort", "_ai_sort"], ascending=[True, False, False])
    out = out.drop_duplicates(subset=["Mã"], keep="first")

    if MAX_WATCHLIST_ROWS > 0:
        out = out.head(MAX_WATCHLIST_ROWS).copy()

    out = out.drop(columns=[c for c in ["_priority_source", "_score_sort", "_ai_sort"] if c in out.columns])
    return out.reset_index(drop=True)


def send_telegram(text: str) -> None:
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("WARN: thiếu TELEGRAM_TOKEN hoặc TELEGRAM_CHAT_ID", flush=True)
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=20)
        print(f"TELEGRAM STATUS: {r.status_code} {r.text[:300]}", flush=True)
    except Exception as e:
        print(f"WARN: gửi Telegram lỗi: {e}", flush=True)


def build_message(watchlist: pd.DataFrame) -> str:
    lines = [
        "✅ V17 EXPORT WATCHLIST CHO RENDER HOÀN TẤT",
        "",
        "Nguồn: CHỈ TOP MUA THẬT + TOP THEO DÕI từ dashboard",
        f"Output: {OUTPUT_PATH}",
        f"Số mã theo dõi: {len(watchlist)}",
        "",
        "TOP WATCHLIST RENDER",
    ]

    if watchlist.empty:
        lines += [
            "⚠️ Không đọc được 2 bảng TOP trong dashboard.",
            "Đã tạo watchlist rỗng để tránh lấy nhầm mã ❌ LOẠI từ CSV fallback.",
        ]
        return "\n".join(lines)

    for _, r in watchlist.iterrows():
        ma = r.get("Mã", "")
        group = str(r.get("Nhóm realtime", ""))
        qd = str(r.get("Quyết định tự động", r.get("QUYẾT ĐỊNH TỰ ĐỘNG", "")))
        action = str(r.get("Hành động", r.get("Hành động hiện tại", r.get("Action", ""))))

        if "MUA" in group.upper() or "MUA" in qd.upper():
            label = "MUA ƯU TIÊN"
            state = "BUY/WATCH"
        else:
            label = "THEO DÕI"
            state = "WATCH"

        score_col = find_col(pd.DataFrame([r]), ["Score", "Điểm", "Diem"])
        score_txt = ""
        if score_col:
            try:
                score_txt = f" | Điểm {float(r.get(score_col)):.2f}"
            except Exception:
                score_txt = ""

        extra = f" | {qd}" if qd and qd.upper() != "NAN" else ""
        lines.append(f"🔹 {ma} | 🟢 {label}{score_txt} | {state}{extra}")

    return "\n".join(lines)


def main():
    print("V17 EXPORT WATCHLIST FROM DASHBOARD ONLY START", flush=True)

    watchlist = build_watchlist_from_dashboard(DASHBOARD_PATH)

    if watchlist.empty:
        watchlist = pd.DataFrame(columns=["Mã", "Nhóm realtime", "Nguồn watchlist"])

    watchlist.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    tickers = watchlist["Mã"].astype(str).tolist() if "Mã" in watchlist.columns else []
    print("EXPORT DONE", flush=True)
    print(f"SOURCE: {DASHBOARD_PATH}", flush=True)
    print(f"OUTPUT: {OUTPUT_PATH}", flush=True)
    print(f"ROWS: {len(watchlist)}", flush=True)
    print(f"TICKERS: {', '.join(tickers)}", flush=True)

    send_telegram(build_message(watchlist))


if __name__ == "__main__":
    main()
