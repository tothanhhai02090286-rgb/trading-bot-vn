# -*- coding: utf-8 -*-
"""
v142_ma20_heat_backtest_vi.py

V14.2 - MA20 HEAT BACKTEST
- Chỉ kiểm tra các mã trong top/watchlist hiện có.
- Dùng cache_stock/{MÃ}.csv để so với lịch sử riêng từng mã.
- Không sửa tín hiệu gốc, không sửa dashboard chính.

Output:
- v142_ma20_heat_backtest.csv
- v142_ma20_heat_backtest.html
- v142_ma20_heat_report.txt
"""

from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
import requests


CACHE_DIR = os.getenv("CACHE_DIR", "cache_stock")

INPUT_FILES = [
    os.getenv("V141_TOP_PATH", "v141_top_quality_picks.csv"),
    os.getenv("V14_TOP_PATH", "v14_top_quality_picks.csv"),
    os.getenv("INTRADAY_WATCHLIST_PATH", "intraday_watchlist.csv"),
    os.getenv("AI_RISK_PATH", "ai_risk_filtered.csv"),
]

OUT_CSV = os.getenv("V142_OUT_CSV", "v142_ma20_heat_backtest.csv")
OUT_HTML = os.getenv("V142_OUT_HTML", "v142_ma20_heat_backtest.html")
OUT_TXT = os.getenv("V142_OUT_TXT", "v142_ma20_heat_report.txt")

MA_WINDOW = int(os.getenv("V142_MA_WINDOW", "20"))
MIN_ROWS = int(os.getenv("V142_MIN_ROWS", "80"))


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_read_csv(path: str) -> pd.DataFrame:
    try:
        if not os.path.exists(path):
            return pd.DataFrame()
        return pd.read_csv(path)
    except Exception as e:
        print(f"WARN: không đọc được {path}: {repr(e)}", flush=True)
        return pd.DataFrame()


def find_col(df: pd.DataFrame, names: list[str]) -> Optional[str]:
    if df is None or df.empty:
        return None
    lower = {str(c).strip().lower(): c for c in df.columns}
    for n in names:
        if str(n).strip().lower() in lower:
            return lower[str(n).strip().lower()]
    for c in df.columns:
        t = str(c).strip().lower()
        for n in names:
            if str(n).strip().lower() in t:
                return c
    return None


def to_num(x, default=np.nan):
    try:
        if pd.isna(x):
            return default
        s = str(x).replace("%", "").replace(",", ".").strip()
        return float(s) if s else default
    except Exception:
        return default


def fmt(x, digits=2):
    try:
        if pd.isna(x):
            return ""
        return f"{float(x):.{digits}f}"
    except Exception:
        return str(x)


def load_symbol_list():
    for path in INPUT_FILES:
        df = safe_read_csv(path)
        if df.empty:
            continue
        col = find_col(df, ["Mã", "Ma", "Symbol", "Ticker"])
        if not col:
            continue
        symbols = (
            df[col].dropna().astype(str).str.upper().str.strip()
            .replace("", np.nan).dropna().drop_duplicates().tolist()
        )
        symbols = [s for s in symbols if s and s != "NAN"]
        if symbols:
            return symbols, path
    return [], ""


def load_cache(symbol: str) -> pd.DataFrame:
    for name in [symbol, symbol.upper(), symbol.lower()]:
        p = Path(CACHE_DIR) / f"{name}.csv"
        if p.exists():
            return safe_read_csv(str(p))
    return pd.DataFrame()


def normalize_cache(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    date_col = find_col(df, ["time", "date", "Ngày", "Ngay", "Date"])
    close_col = find_col(df, ["close", "Close", "Giá", "Gia"])
    low_col = find_col(df, ["low", "Low"])
    if not date_col or not close_col:
        return pd.DataFrame()

    out = pd.DataFrame()
    out["date"] = pd.to_datetime(df[date_col], errors="coerce")
    out["close"] = pd.to_numeric(df[close_col], errors="coerce")
    out["low"] = pd.to_numeric(df[low_col], errors="coerce") if low_col else out["close"]
    out = out.dropna(subset=["date", "close"]).sort_values("date").drop_duplicates("date").reset_index(drop=True)
    return out


def win_rate(s: pd.Series):
    v = pd.to_numeric(s, errors="coerce").dropna()
    if len(v) == 0:
        return np.nan
    return float((v > 0).mean() * 100)


def avg_ret(s: pd.Series):
    v = pd.to_numeric(s, errors="coerce").dropna()
    if len(v) == 0:
        return np.nan
    return float(v.mean())


def percentile_rank(series: pd.Series, current: float):
    v = pd.to_numeric(series, errors="coerce").dropna()
    if len(v) == 0 or pd.isna(current):
        return np.nan
    return float((v <= current).mean() * 100)


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ma20"] = out["close"].rolling(MA_WINDOW).mean()
    out["dist_ma20_pct"] = (out["close"] / out["ma20"] - 1) * 100
    out["ret_t2_pct"] = (out["close"].shift(-2) / out["close"] - 1) * 100
    out["ret_t5_pct"] = (out["close"].shift(-5) / out["close"] - 1) * 100
    out["ret_t10_pct"] = (out["close"].shift(-10) / out["close"] - 1) * 100
    future_min_5 = pd.concat([out["low"].shift(-i) for i in range(1, 6)], axis=1).min(axis=1)
    out["max_dd_t5_pct"] = (future_min_5 / out["close"] - 1) * 100
    return out


def make_recommendation(dist, pct, win5, avg5):
    if pd.isna(dist) or pd.isna(pct):
        return "KHÔNG ĐỦ DỮ LIỆU", "Không đủ dữ liệu để đánh giá."
    if pct >= 95:
        return "⛔ QUÁ NÓNG - KHÔNG MUA ĐUỔI", "Mức này nằm trong top 5% nóng nhất lịch sử."
    if dist >= 18 and (pd.isna(win5) or win5 < 45):
        return "⛔ QUÁ NÓNG - KHÔNG MUA ĐUỔI", "Dist MA20 rất cao và win T+5 vùng tương tự yếu."
    if dist >= 15 and not pd.isna(avg5) and avg5 < 0:
        return "⚠️ NÓNG - CHỈ MUA THĂM DÒ / CHỜ CHỈNH", "Lợi T+5 trung bình vùng tương tự âm."
    if pct >= 85:
        return "⚠️ HƠI NÓNG - GIẢM TỶ TRỌNG", "Mức hiện tại nằm trong nhóm nóng cao của lịch sử."
    if dist >= 12 and not pd.isna(win5) and win5 < 50:
        return "⚠️ HƠI NÓNG - CHỜ ĐIỂM VÀO ĐẸP HƠN", "Win T+5 vùng tương tự dưới 50%."
    if dist < 8:
        return "✅ CHƯA NÓNG", "Giá chưa cách MA20 quá xa."
    if not pd.isna(win5) and win5 >= 55 and (pd.isna(avg5) or avg5 >= 0):
        return "✅ CÒN CHẤP NHẬN ĐƯỢC", "Dù xa MA20 nhưng lịch sử vùng tương tự vẫn tích cực."
    return "🟡 TRUNG TÍNH - THEO DÕI", "Cần kết hợp thêm volume, risk và xu hướng."


def analyze_symbol(symbol: str) -> dict:
    raw = load_cache(symbol)
    df = normalize_cache(raw)
    if df.empty or len(df) < MIN_ROWS:
        return {"Mã": symbol, "Trạng thái dữ liệu": "KHÔNG ĐỦ DỮ LIỆU", "Số dòng lịch sử": len(df)}

    feat = add_features(df).dropna(subset=["ma20", "dist_ma20_pct"]).copy()
    if feat.empty:
        return {"Mã": symbol, "Trạng thái dữ liệu": "KHÔNG TÍNH ĐƯỢC MA20", "Số dòng lịch sử": len(df)}

    cur = feat.iloc[-1]
    dist = float(cur["dist_ma20_pct"])
    close = float(cur["close"])
    ma20 = float(cur["ma20"])
    date = str(pd.to_datetime(cur["date"]).date())

    max_idx = feat["dist_ma20_pct"].idxmax()
    max_row = feat.loc[max_idx]
    max_dist = float(max_row["dist_ma20_pct"])
    max_date = str(pd.to_datetime(max_row["date"]).date())

    pct = percentile_rank(feat["dist_ma20_pct"], dist)

    width = max(2.0, abs(dist) * 0.15)
    low, high = dist - width, dist + width
    band = feat[(feat["dist_ma20_pct"] >= low) & (feat["dist_ma20_pct"] <= high)].dropna(subset=["ret_t5_pct"]).copy()

    win2 = win_rate(band["ret_t2_pct"])
    win5 = win_rate(band["ret_t5_pct"])
    win10 = win_rate(band["ret_t10_pct"])
    avg2 = avg_ret(band["ret_t2_pct"])
    avg5 = avg_ret(band["ret_t5_pct"])
    avg10 = avg_ret(band["ret_t10_pct"])
    dd5 = avg_ret(band["max_dd_t5_pct"])

    rec, reason = make_recommendation(dist, pct, win5, avg5)

    return {
        "Mã": symbol,
        "Trạng thái dữ liệu": "OK",
        "Ngày hiện tại": date,
        "Giá hiện tại": round(close, 2),
        "MA20 hiện tại": round(ma20, 2),
        "Dist MA20 hiện tại %": round(dist, 2),
        "Dist MA20 cao nhất lịch sử %": round(max_dist, 2),
        "Ngày nóng nhất": max_date,
        "Phân vị nóng hiện tại %": round(pct, 2) if not pd.isna(pct) else "",
        "Vùng so sánh lịch sử": f"{low:.1f}% đến {high:.1f}%",
        "Số mẫu vùng tương tự": int(len(band)),
        "Win T+2 vùng tương tự %": round(win2, 2) if not pd.isna(win2) else "",
        "Win T+5 vùng tương tự %": round(win5, 2) if not pd.isna(win5) else "",
        "Win T+10 vùng tương tự %": round(win10, 2) if not pd.isna(win10) else "",
        "Lợi TB T+2 vùng tương tự %": round(avg2, 2) if not pd.isna(avg2) else "",
        "Lợi TB T+5 vùng tương tự %": round(avg5, 2) if not pd.isna(avg5) else "",
        "Lợi TB T+10 vùng tương tự %": round(avg10, 2) if not pd.isna(avg10) else "",
        "Drawdown TB T+5 vùng tương tự %": round(dd5, 2) if not pd.isna(dd5) else "",
        "Khuyến nghị MA20": rec,
        "Lý do MA20": reason,
        "Số dòng lịch sử": int(len(feat)),
    }


def html_style():
    return """<style>
body{font-family:Arial,sans-serif;background:#0f172a;color:#e5e7eb;padding:18px}
h2,h3{color:#fff}.note{background:#111827;border:1px solid #334155;border-radius:10px;padding:12px;margin:12px 0}
table{border-collapse:collapse;width:100%;font-size:12px;background:#111827}
th{background:#1f2937;color:#fff;position:sticky;top:0}
td,th{border:1px solid #334155;padding:7px;white-space:nowrap;vertical-align:top}
tr:nth-child(even){background:#0b1220}
</style>"""


def build_report(df: pd.DataFrame, source: str):
    lines = [
        "✅ <b>V14.2 MA20 HEAT BACKTEST HOÀN TẤT</b>",
        "",
        f"Nguồn mã: <b>{source or 'N/A'}</b>",
        f"Số mã kiểm tra: <b>{len(df)}</b>",
        "",
        "<b>KẾT QUẢ MA20</b>",
    ]
    for _, r in df.head(8).iterrows():
        lines.append(f"🔹 <b>{r.get('Mã','')}</b> | Dist MA20: <b>{fmt(r.get('Dist MA20 hiện tại %'))}%</b> | Phân vị nóng: <b>{fmt(r.get('Phân vị nóng hiện tại %'))}%</b>")
        lines.append(f"   Max lịch sử: {fmt(r.get('Dist MA20 cao nhất lịch sử %'))}% ({r.get('Ngày nóng nhất','')})")
        lines.append(f"   Win T+5 vùng tương tự: {fmt(r.get('Win T+5 vùng tương tự %'))}% | Lợi TB T+5: {fmt(r.get('Lợi TB T+5 vùng tương tự %'))}%")
        lines.append(f"   {r.get('Khuyến nghị MA20','')}")
        lines.append(f"   {r.get('Lý do MA20','')}")
    return "\n".join(lines)


def send_telegram(text: str):
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("WARN: thiếu TELEGRAM_TOKEN/TELEGRAM_CHAT_ID, bỏ qua gửi V14.2", flush=True)
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = requests.post(url, data={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=20)
        print("TELEGRAM V14.2 STATUS:", r.status_code, r.text[:200], flush=True)
        return r.status_code == 200
    except Exception as e:
        print("WARN: gửi Telegram V14.2 lỗi:", repr(e), flush=True)
        return False


def main():
    print("V14.2 MA20 HEAT BACKTEST STARTED", flush=True)
    symbols, source = load_symbol_list()
    if not symbols:
        out = pd.DataFrame([{"Trạng thái": "Không tìm thấy danh sách mã đầu vào"}])
        out.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
        Path(OUT_TXT).write_text("Không tìm thấy danh sách mã đầu vào", encoding="utf-8")
        print("WARN: không tìm thấy danh sách mã đầu vào", flush=True)
        return

    print(f"Input source: {source}", flush=True)
    rows = []
    for i, symbol in enumerate(symbols, 1):
        print(f"[{i}/{len(symbols)}] Kiểm tra MA20 heat {symbol}", flush=True)
        rows.append(analyze_symbol(symbol))

    df = pd.DataFrame(rows)
    if "Phân vị nóng hiện tại %" in df.columns:
        df["__pct"] = pd.to_numeric(df["Phân vị nóng hiện tại %"], errors="coerce")
        df["__dist"] = pd.to_numeric(df["Dist MA20 hiện tại %"], errors="coerce")
        df = df.sort_values(["__pct", "__dist"], ascending=[False, False], na_position="last").drop(columns=["__pct","__dist"]).reset_index(drop=True)

    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>V14.2 MA20 Heat Backtest</title>{html_style()}</head>
<body><h2>V14.2 - MA20 HEAT BACKTEST</h2><div class="note"><b>Generated:</b> {now_str()}<br><b>Nguồn danh sách mã:</b> {source}<br><b>Ý nghĩa:</b> So mức xa MA20 hiện tại với lịch sử riêng từng mã. Không thay đổi tín hiệu gốc.</div>{df.to_html(index=False, escape=True)}</body></html>"""
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
