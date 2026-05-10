# -*- coding: utf-8 -*-
"""
v17_export_intraday_watchlist_vi.py

Xuất watchlist cuối ngày từ V17 để Render theo dõi trong phiên ngày hôm sau.

Input:
- v17_final_decision.csv

Output:
- intraday_watchlist_v17.csv
- intraday_watchlist_v17_report.txt

Logic:
- Giữ các mã:
  + 🟢 ƯU TIÊN CAO
  + 🟡 THEO DÕI
  + 🟠 CHỜ ĐIỂM ĐẸP
- Loại:
  + ❌ LOẠI
  + Risk FAIL
- Sắp xếp theo Điểm V17 giảm dần.
"""

from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime
import pandas as pd
import requests


INPUT_FILE = os.getenv("V17_FINAL_CSV", "v17_final_decision.csv")
OUT_CSV = os.getenv("V17_INTRADAY_WATCHLIST", "intraday_watchlist_v17.csv")
OUT_TXT = os.getenv("V17_INTRADAY_REPORT", "intraday_watchlist_v17_report.txt")


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_csv(path):
    try:
        if not os.path.exists(path):
            return pd.DataFrame()
        return pd.read_csv(path)
    except Exception as e:
        print(f"WARN: không đọc được {path}: {repr(e)}", flush=True)
        return pd.DataFrame()


def find_col(df, names):
    if df is None or df.empty:
        return None

    lower = {str(c).strip().lower(): c for c in df.columns}

    for n in names:
        k = str(n).strip().lower()
        if k in lower:
            return lower[k]

    for c in df.columns:
        text = str(c).strip().lower()
        for n in names:
            if str(n).strip().lower() in text:
                return c

    return None


def send_telegram(text):
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        print("WARN: thiếu Telegram token/chat_id, bỏ qua export report", flush=True)
        return False

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        print("TELEGRAM V17 EXPORT STATUS:", resp.status_code, resp.text[:160], flush=True)
        return resp.status_code == 200
    except Exception as e:
        print("WARN: gửi Telegram V17 export lỗi:", repr(e), flush=True)
        return False


def build_watchlist():
    df = read_csv(INPUT_FILE)

    if df.empty:
        out = pd.DataFrame([{"Trạng thái": "Không tìm thấy v17_final_decision.csv"}])
        return out

    ma_col = find_col(df, ["Mã", "Ma", "Symbol", "Ticker"])
    decision_col = find_col(df, ["Quyết định V17", "Quyet dinh V17"])
    risk_col = find_col(df, ["Risk", "Risk Status"])
    score_col = find_col(df, ["Điểm V17", "Diem V17"])
    price_col = find_col(df, ["Giá", "Gia", "Close"])

    if ma_col is None or decision_col is None:
        out = pd.DataFrame([{"Trạng thái": "Thiếu cột Mã hoặc Quyết định V17"}])
        return out

    temp = df.copy()
    temp["Mã"] = temp[ma_col].astype(str).str.upper().str.strip()
    temp["Quyết định V17"] = temp[decision_col].astype(str)

    if risk_col:
        temp["Risk"] = temp[risk_col].astype(str)
    else:
        temp["Risk"] = ""

    temp["__decision_upper"] = temp["Quyết định V17"].str.upper()
    temp["__risk_upper"] = temp["Risk"].str.upper()

    keep_mask = (
        temp["__decision_upper"].str.contains("ƯU TIÊN|THEO DÕI|CHỜ", na=False)
        & ~temp["__decision_upper"].str.contains("LOẠI", na=False)
        & ~temp["__risk_upper"].str.contains("FAIL", na=False)
    )

    out = temp[keep_mask].copy()

    if out.empty:
        out = pd.DataFrame([{"Trạng thái": "Không có mã phù hợp cho Render theo dõi"}])
        return out

    if score_col:
        out["Điểm V17"] = pd.to_numeric(out[score_col], errors="coerce")
    else:
        out["Điểm V17"] = 0

    if price_col:
        out["Giá tham chiếu V17"] = out[price_col]
    else:
        out["Giá tham chiếu V17"] = ""

    strategy_col = find_col(out, ["Strategy V17"])
    market_col = find_col(out, ["Market mode"])
    reason_col = find_col(out, ["Lý do V17", "Ly do V17"])

    final = pd.DataFrame()
    final["Mã"] = out["Mã"]
    final["Giá tham chiếu V17"] = out["Giá tham chiếu V17"]
    final["Quyết định V17"] = out["Quyết định V17"]
    final["Điểm V17"] = out["Điểm V17"]
    final["Strategy V17"] = out[strategy_col] if strategy_col else ""
    final["Risk"] = out["Risk"]
    final["Market mode"] = out[market_col] if market_col else ""
    final["Lý do V17"] = out[reason_col] if reason_col else ""
    final["Ngày xuất watchlist"] = now_str()

    # Nhãn dùng cho Render đọc dễ hơn
    final["Render Action"] = final["Quyết định V17"].apply(
        lambda x: "PRIORITY" if "ƯU TIÊN" in str(x).upper()
        else ("WATCH" if "THEO DÕI" in str(x).upper() else "WAIT")
    )

    final = final.sort_values("Điểm V17", ascending=False, na_position="last")
    final = final.drop_duplicates("Mã", keep="first").reset_index(drop=True)

    return final


def main():
    print("V17 EXPORT INTRADAY WATCHLIST STARTED", flush=True)

    out = build_watchlist()
    out.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    count = len(out) if "Mã" in out.columns else 0

    lines = [
        "✅ <b>V17 EXPORT WATCHLIST CHO RENDER HOÀN TẤT</b>",
        "",
        f"Nguồn: <b>{INPUT_FILE}</b>",
        f"Output: <b>{OUT_CSV}</b>",
        f"Số mã theo dõi: <b>{count}</b>",
    ]

    if "Mã" in out.columns and count > 0:
        lines.append("")
        lines.append("<b>TOP WATCHLIST RENDER</b>")
        for _, r in out.head(10).iterrows():
            lines.append(
                f"🔹 <b>{r.get('Mã','')}</b> | {r.get('Quyết định V17','')} | "
                f"Điểm {r.get('Điểm V17','')} | {r.get('Render Action','')}"
            )

    report = "\n".join(lines)
    Path(OUT_TXT).write_text(report, encoding="utf-8")

    print(report.replace("<b>", "").replace("</b>", ""), flush=True)
    print(f"OK: wrote {OUT_CSV}", flush=True)
    print(f"OK: wrote {OUT_TXT}", flush=True)

    send_telegram(report)


if __name__ == "__main__":
    main()
