# -*- coding: utf-8 -*-
"""
v151_bottom_quality_engine_vi.py
Runner V15.1 modular: đọc danh sách mã, gọi core, xuất CSV/HTML/TXT/Telegram.
"""

from __future__ import annotations
import os
from pathlib import Path
from datetime import datetime
import pandas as pd
import requests

from v151_bottom_core_vi import analyze_bottom_symbol, find_col, safe_read_csv

INPUT_FILES = [
    os.getenv("AI_RISK_PATH", "ai_risk_filtered.csv"),
    os.getenv("ALL_RESULT_PATH", "all_signal_results.csv"),
    os.getenv("INTRADAY_WATCHLIST_PATH", "intraday_watchlist.csv"),
]

OUT_CSV = os.getenv("V151_BOTTOM_CSV", "v151_bottom_quality.csv")
OUT_HTML = os.getenv("V151_BOTTOM_HTML", "v151_bottom_quality.html")
OUT_TXT = os.getenv("V151_BOTTOM_TXT", "v151_bottom_quality_report.txt")


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def fmt(x, digits=2):
    try:
        if pd.isna(x):
            return ""
        return f"{float(x):.{digits}f}"
    except Exception:
        return str(x)


def load_candidates():
    for path in INPUT_FILES:
        df = safe_read_csv(path)
        if df.empty:
            continue

        ma_col = find_col(df, ["Mã", "Ma", "Symbol", "Ticker"])
        if ma_col is None:
            continue

        strat_col = find_col(df, ["Strategy", "Chiến lược", "Chien luoc"])
        action_col = find_col(df, ["Action", "Hành động", "Hanh dong", "Hành động hiện tại", "Hanh dong hien tai"])

        temp = df.copy()
        temp["__ma"] = temp[ma_col].astype(str).str.upper().str.strip()

        mask = pd.Series(False, index=temp.index)

        if strat_col:
            mask = mask | temp[strat_col].astype(str).str.upper().str.contains("BOTTOM", na=False)

        if action_col:
            mask = mask | temp[action_col].astype(str).str.upper().str.contains("WATCHLIST|WAIT|BUY NOW", na=False)

        picked = temp[mask].copy()
        if picked.empty:
            picked = temp.copy()

        symbols = picked["__ma"].dropna().drop_duplicates().tolist()
        symbols = [s for s in symbols if s and s not in ["NAN", "NO_SIGNAL"]]

        if symbols:
            return symbols, path

    return [], ""


def html_style():
    return """
<style>
body{font-family:Arial,sans-serif;background:#0f172a;color:#e5e7eb;padding:18px}
h2,h3{color:#fff}
.note{background:#111827;border:1px solid #334155;border-radius:10px;padding:12px;margin:12px 0}
table{border-collapse:collapse;width:100%;font-size:12px;background:#111827}
th{background:#1f2937;color:#fff;position:sticky;top:0}
td,th{border:1px solid #334155;padding:7px;white-space:nowrap;vertical-align:top}
tr:nth-child(even){background:#0b1220}
</style>
"""


def build_report(df, source):
    lines = [
        "✅ <b>V15.1 BOTTOM QUALITY HOÀN TẤT</b>",
        "",
        f"Nguồn mã: <b>{source}</b>",
        f"Số mã kiểm tra: <b>{len(df)}</b>",
        "",
        "<b>TOP BOTTOM QUALITY</b>",
    ]

    if df is None or df.empty:
        lines.append("Không có dữ liệu.")
        return "\n".join(lines)

    for _, r in df.head(8).iterrows():
        lines.append("")
        lines.append(f"🔹 <b>{r.get('Mã','')}</b> | {r.get('Phân loại Bottom V15.1','')} | Điểm {fmt(r.get('Điểm Bottom V15.1'))}")
        lines.append(f"RSI: {fmt(r.get('RSI'))} | DD20: {fmt(r.get('Drawdown 20 phiên %'))}% | Hồi đáy: {fmt(r.get('Hồi từ đáy 20 phiên %'))}%")
        lines.append(f"Win T+5: {fmt(r.get('Win T+5 %'))}% | Lợi TB T+5: {fmt(r.get('Lợi TB T+5 %'))}%")

        good = str(r.get("Điểm mạnh", "") or "")
        bad = str(r.get("Điểm yếu", "") or "")

        if good and good.lower() != "nan":
            lines.append(f"Điểm mạnh: {good}")
        if bad and bad.lower() != "nan":
            lines.append(f"Điểm yếu: {bad}")

    return "\n".join(lines)


def send_telegram(text):
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        print("WARN: thiếu Telegram token/chat_id, bỏ qua V15.1", flush=True)
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
        print("TELEGRAM V15.1 STATUS:", resp.status_code, resp.text[:200], flush=True)
        return resp.status_code == 200
    except Exception as e:
        print("WARN: gửi Telegram V15.1 lỗi:", repr(e), flush=True)
        return False


def main():
    print("V15.1 BOTTOM QUALITY ENGINE STARTED", flush=True)

    symbols, source = load_candidates()

    if not symbols:
        out = pd.DataFrame([{"Trạng thái": "Không tìm thấy danh sách mã đầu vào"}])
        out.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
        Path(OUT_TXT).write_text("Không tìm thấy danh sách mã đầu vào", encoding="utf-8")
        print("WARN: không tìm thấy danh sách mã đầu vào", flush=True)
        return

    rows = []
    for i, symbol in enumerate(symbols, 1):
        print(f"[{i}/{len(symbols)}] Bottom quality {symbol}", flush=True)
        rows.append(analyze_bottom_symbol(symbol))

    df = pd.DataFrame(rows)

    if "Điểm Bottom V15.1" in df.columns:
        df["__score"] = pd.to_numeric(df["Điểm Bottom V15.1"], errors="coerce")
        df = df.sort_values("__score", ascending=False, na_position="last")
        df = df.drop(columns=["__score"]).reset_index(drop=True)

    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>V15.1 Bottom Quality</title>
{html_style()}
</head>
<body>
<h2>V15.1 - BOTTOM QUALITY ENGINE</h2>
<div class="note">
<b>Generated:</b> {now_str()}<br>
<b>Nguồn danh sách mã:</b> {source}<br>
<b>Ý nghĩa:</b> Phân loại đáy chất lượng / hồi kỹ thuật / bull trap / dao rơi. Không thay đổi tín hiệu gốc.
</div>
{df.to_html(index=False, escape=True)}
</body>
</html>
"""
    Path(OUT_HTML).write_text(html, encoding="utf-8")

    report = build_report(df, source)
    Path(OUT_TXT).write_text(report, encoding="utf-8")

    print(report.replace("<b>", "").replace("</b>", ""), flush=True)
    print(f"OK: wrote {OUT_CSV}", flush=True)
    print(f"OK: wrote {OUT_HTML}", flush=True)
    print(f"OK: wrote {OUT_TXT}", flush=True)

    send_telegram(report)


if __name__ == "__main__":
    main()
