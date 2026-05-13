# -*- coding: utf-8 -*-
"""
v17_export_intraday_watchlist_vi.py

Nguồn chuẩn:
- Đọc top_render_candidates.csv được xuất trực tiếp từ dashboard TOP MUA THẬT + TOP THEO DÕI.
- Không đọc HTML.
- Không fallback CSV thô.
- Không lấy mã ❌ LOẠI.
Output:
- intraday_watchlist_v17.csv
"""

from __future__ import annotations

import os
from pathlib import Path
import pandas as pd
import requests

SOURCE_CSV = os.getenv("TOP_RENDER_CANDIDATES_CSV", "top_render_candidates.csv")
OUTPUT_CSV = os.getenv("INTRADAY_WATCHLIST_OUTPUT", "intraday_watchlist_v17.csv")
MAX_ROWS = int(os.getenv("MAX_WATCHLIST_ROWS", "10"))


def find_col(df, names):
    if df is None or df.empty:
        return None
    low = {str(c).strip().lower(): c for c in df.columns}
    for n in names:
        k = str(n).strip().lower()
        if k in low:
            return low[k]
    for c in df.columns:
        t = str(c).strip().lower()
        for n in names:
            if str(n).strip().lower() in t:
                return c
    return None


def send_telegram(text):
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("WARN: thiếu Telegram env")
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=20)
        print("TELEGRAM STATUS:", r.status_code, r.text[:250])
    except Exception as e:
        print("WARN Telegram:", repr(e))


def main():
    print("V17 EXPORT WATCHLIST FROM top_render_candidates.csv START")

    if not Path(SOURCE_CSV).exists():
        out = pd.DataFrame(columns=["Mã", "Nhóm realtime", "Nguồn watchlist"])
        out.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
        msg = (
            "⚠️ V17 EXPORT WATCHLIST CHO RENDER\n\n"
            f"Không thấy nguồn chuẩn: {SOURCE_CSV}\n"
            f"Đã tạo {OUTPUT_CSV} rỗng để tránh lấy nhầm mã ❌ LOẠI."
        )
        print(msg)
        send_telegram(msg)
        return

    df = pd.read_csv(SOURCE_CSV)
    if df.empty:
        out = pd.DataFrame(columns=["Mã", "Nhóm realtime", "Nguồn watchlist"])
        out.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
        msg = (
            "⚠️ V17 EXPORT WATCHLIST CHO RENDER\n\n"
            f"{SOURCE_CSV} rỗng.\n"
            f"Đã tạo {OUTPUT_CSV} rỗng."
        )
        print(msg)
        send_telegram(msg)
        return

    ma_col = find_col(df, ["Mã", "Ma", "Ticker", "Symbol"])
    if ma_col is None:
        out = pd.DataFrame(columns=["Mã", "Nhóm realtime", "Nguồn watchlist"])
        out.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
        msg = (
            "⚠️ V17 EXPORT WATCHLIST CHO RENDER\n\n"
            f"{SOURCE_CSV} không có cột Mã/Ma.\n"
            f"Đã tạo {OUTPUT_CSV} rỗng."
        )
        print(msg)
        send_telegram(msg)
        return

    out = df.copy()
    out["Mã"] = out[ma_col].astype(str).str.upper().str.strip()
    out = out[out["Mã"].str.match(r"^[A-Z0-9]{2,10}$", na=False)].copy()

    # Chỉ giữ Risk PASS nếu có cột Risk.
    risk_col = find_col(out, ["Risk", "Risk Status"])
    if risk_col is not None:
        risk_text = out[risk_col].astype(str).str.upper()
        if risk_text.str.contains("PASS", na=False).any():
            out = out[risk_text.str.contains("PASS", na=False)].copy()

    # Chặn tuyệt đối mã bị loại nếu có cột quyết định/hành động.
    block_cols = []
    for names in [
        ["Quyết định V17", "Quyet dinh V17"],
        ["QUYẾT ĐỊNH TỰ ĐỘNG", "Quyet dinh tu dong"],
        ["Hành động hiện tại", "Hanh dong hien tai", "Action"],
    ]:
        c = find_col(out, names)
        if c is not None:
            block_cols.append(c)

    if block_cols:
        combined = pd.Series("", index=out.index, dtype="object")
        for c in block_cols:
            combined = combined + " " + out[c].astype(str).str.upper()
        bad = combined.str.contains("❌|LOẠI|LOAI|SKIP|BỎ QUA|BO QUA|FAIL", na=False)
        out = out[~bad].copy()

    # Ưu tiên TOP MUA THẬT trước TOP THEO DÕI nếu có cột nhóm.
    group_col = find_col(out, ["Nhóm realtime", "Nhom realtime", "Nguồn watchlist", "Nguon watchlist"])
    if group_col is not None:
        group = out[group_col].astype(str).str.upper()
        out["_priority"] = group.apply(lambda x: 0 if "MUA" in x else 1 if "THEO" in x or "WATCH" in x else 9)
    else:
        out["_priority"] = 9

    score_col = find_col(out, ["Score", "Điểm", "Diem", "AI"])
    if score_col is not None:
        out["_score"] = pd.to_numeric(out[score_col], errors="coerce").fillna(0)
    else:
        out["_score"] = 0

    out = out.sort_values(["_priority", "_score"], ascending=[True, False])
    out = out.drop_duplicates("Mã", keep="first")
    if MAX_ROWS > 0:
        out = out.head(MAX_ROWS).copy()

    out = out.drop(columns=[c for c in ["_priority", "_score"] if c in out.columns])
    out.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    tickers = out["Mã"].tolist()
    lines = [
        "✅ V17 EXPORT WATCHLIST CHO RENDER HOÀN TẤT",
        "",
        f"Nguồn: {SOURCE_CSV}",
        f"Output: {OUTPUT_CSV}",
        f"Số mã theo dõi: {len(out)}",
        "",
        "TOP WATCHLIST RENDER",
    ]
    for _, r in out.iterrows():
        ma = r.get("Mã", "")
        group = str(r.get(group_col, "")) if group_col else ""
        label = "MUA ƯU TIÊN" if "MUA" in group.upper() else "THEO DÕI"
        score_txt = ""
        if score_col is not None:
            try:
                score_txt = f" | Điểm {float(r.get(score_col)):.2f}"
            except Exception:
                score_txt = ""
        lines.append(f"🔹 {ma} | 🟢 {label}{score_txt} | WATCH")

    msg = "\n".join(lines)
    print(msg)
    send_telegram(msg)


if __name__ == "__main__":
    main()
