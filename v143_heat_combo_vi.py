# -*- coding: utf-8 -*-
"""
v143_heat_combo_vi.py

V14.3 - HEAT COMBO CHECK
Kết hợp:
- Dist MA20 heat: giá xa MA20 so với lịch sử riêng từng mã
- RSI heat: RSI hiện tại có quá nóng không
- Volume heat: volume có xác nhận hay chỉ kéo nóng
- Win T+5 vùng tương tự

Mục tiêu:
- Chỉ kiểm tra các mã đã lọc trong top/watchlist.
- Không tìm tín hiệu mới.
- Không sửa tín hiệu gốc.
- Không sửa dashboard chính.
- Không ảnh hưởng Render realtime.

Input danh sách mã ưu tiên:
1. v142_ma20_heat_backtest.csv
2. v141_top_quality_picks.csv
3. intraday_watchlist.csv
4. ai_risk_filtered.csv

Dữ liệu lịch sử:
- cache_stock/{MÃ}.csv

Output:
- v143_heat_combo.csv
- v143_heat_combo.html
- v143_heat_combo_report.txt
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
    os.getenv("V142_OUT_CSV", "v142_ma20_heat_backtest.csv"),
    os.getenv("V141_TOP_PATH", "v141_top_quality_picks.csv"),
    os.getenv("INTRADAY_WATCHLIST_PATH", "intraday_watchlist.csv"),
    os.getenv("AI_RISK_PATH", "ai_risk_filtered.csv"),
]

OUT_CSV = os.getenv("V143_OUT_CSV", "v143_heat_combo.csv")
OUT_HTML = os.getenv("V143_OUT_HTML", "v143_heat_combo.html")
OUT_TXT = os.getenv("V143_OUT_TXT", "v143_heat_combo_report.txt")

MA_WINDOW = int(os.getenv("V143_MA_WINDOW", "20"))
RSI_WINDOW = int(os.getenv("V143_RSI_WINDOW", "14"))
VOL_WINDOW = int(os.getenv("V143_VOL_WINDOW", "20"))
MIN_ROWS = int(os.getenv("V143_MIN_ROWS", "80"))


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_read_csv(path):
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
        key = str(n).strip().lower()
        if key in lower:
            return lower[key]
    for c in df.columns:
        t = str(c).strip().lower()
        for n in names:
            if str(n).strip().lower() in t:
                return c
    return None


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


def load_cache(symbol):
    for name in [symbol, symbol.upper(), symbol.lower()]:
        p = Path(CACHE_DIR) / f"{name}.csv"
        if p.exists():
            return safe_read_csv(str(p))
    return pd.DataFrame()


def normalize_cache(df):
    if df is None or df.empty:
        return pd.DataFrame()

    date_col = find_col(df, ["time", "date", "Ngày", "Ngay", "Date"])
    close_col = find_col(df, ["close", "Close", "Giá", "Gia"])
    low_col = find_col(df, ["low", "Low"])
    volume_col = find_col(df, ["volume", "Volume", "vol"])

    if not date_col or not close_col:
        return pd.DataFrame()

    out = pd.DataFrame()
    out["date"] = pd.to_datetime(df[date_col], errors="coerce")
    out["close"] = pd.to_numeric(df[close_col], errors="coerce")
    out["low"] = pd.to_numeric(df[low_col], errors="coerce") if low_col else out["close"]
    out["volume"] = pd.to_numeric(df[volume_col], errors="coerce") if volume_col else np.nan
    out = out.dropna(subset=["date", "close"]).sort_values("date").drop_duplicates("date").reset_index(drop=True)
    return out


def calc_rsi(close, window=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window).mean()
    avg_loss = loss.rolling(window).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def add_features(df):
    out = df.copy()
    out["ma20"] = out["close"].rolling(MA_WINDOW).mean()
    out["dist_ma20_pct"] = (out["close"] / out["ma20"] - 1) * 100
    out["rsi"] = calc_rsi(out["close"], RSI_WINDOW)
    out["vol_ma20"] = out["volume"].rolling(VOL_WINDOW).mean()
    out["volume_ratio"] = out["volume"] / out["vol_ma20"]
    out["ret_t5_pct"] = (out["close"].shift(-5) / out["close"] - 1) * 100
    future_min_5 = pd.concat([out["low"].shift(-i) for i in range(1, 6)], axis=1).min(axis=1)
    out["max_dd_t5_pct"] = (future_min_5 / out["close"] - 1) * 100
    return out


def percentile_rank(series, current):
    v = pd.to_numeric(series, errors="coerce").dropna()
    if len(v) == 0 or pd.isna(current):
        return np.nan
    return float((v <= current).mean() * 100)


def win_rate(s):
    v = pd.to_numeric(s, errors="coerce").dropna()
    if len(v) == 0:
        return np.nan
    return float((v > 0).mean() * 100)


def avg_ret(s):
    v = pd.to_numeric(s, errors="coerce").dropna()
    if len(v) == 0:
        return np.nan
    return float(v.mean())


def heat_score(dist_pct_rank, rsi, vol_ratio, win5, avg5):
    score = 50
    reasons_good = []
    reasons_bad = []

    # MA20 heat
    if not pd.isna(dist_pct_rank):
        if dist_pct_rank >= 95:
            score -= 25
            reasons_bad.append("MA20 thuộc top 5% nóng nhất lịch sử")
        elif dist_pct_rank >= 85:
            score -= 15
            reasons_bad.append("MA20 thuộc vùng nóng cao")
        elif dist_pct_rank <= 60:
            score += 8
            reasons_good.append("MA20 chưa quá nóng")

    # RSI heat
    if not pd.isna(rsi):
        if rsi >= 82:
            score -= 22
            reasons_bad.append(f"RSI quá nóng {rsi:.1f}")
        elif rsi >= 75:
            score -= 14
            reasons_bad.append(f"RSI nóng {rsi:.1f}")
        elif 52 <= rsi <= 68:
            score += 12
            reasons_good.append(f"RSI vùng đẹp {rsi:.1f}")
        elif rsi < 40:
            score -= 8
            reasons_bad.append(f"RSI yếu {rsi:.1f}")

    # Volume confirm
    if not pd.isna(vol_ratio):
        if vol_ratio >= 1.5:
            score += 10
            reasons_good.append(f"Volume xác nhận mạnh {vol_ratio:.2f}")
        elif vol_ratio >= 1.0:
            score += 5
            reasons_good.append(f"Volume ổn {vol_ratio:.2f}")
        elif vol_ratio < 0.7:
            score -= 10
            reasons_bad.append(f"Volume yếu {vol_ratio:.2f}")

    # Historical forward
    if not pd.isna(win5):
        if win5 >= 58:
            score += 12
            reasons_good.append(f"Win T+5 vùng tương tự tốt {win5:.1f}%")
        elif win5 < 48:
            score -= 12
            reasons_bad.append(f"Win T+5 vùng tương tự yếu {win5:.1f}%")

    if not pd.isna(avg5):
        if avg5 >= 1.0:
            score += 8
            reasons_good.append(f"Lợi TB T+5 tốt {avg5:.2f}%")
        elif avg5 < 0:
            score -= 10
            reasons_bad.append(f"Lợi TB T+5 âm {avg5:.2f}%")

    score = max(min(score, 100), 0)
    return score, reasons_good, reasons_bad


def heat_label(score, dist_pct_rank, rsi):
    if score >= 75:
        return "✅ KHỎE - CÒN THEO DÕI/MUA CÓ KIỂM SOÁT"
    if score >= 60:
        return "🟡 ỔN NHƯNG KHÔNG MUA ĐUỔI"
    if score >= 45:
        return "⚠️ NÓNG - CHỈ THĂM DÒ / CHỜ CHỈNH"
    return "⛔ NÓNG THẬT - TRÁNH MUA ĐUỔI"


def analyze_symbol(symbol):
    raw = load_cache(symbol)
    df = normalize_cache(raw)
    if df.empty or len(df) < MIN_ROWS:
        return {"Mã": symbol, "Trạng thái dữ liệu": "KHÔNG ĐỦ DỮ LIỆU", "Số dòng lịch sử": len(df)}

    feat = add_features(df).dropna(subset=["ma20", "dist_ma20_pct", "rsi"]).copy()
    if feat.empty:
        return {"Mã": symbol, "Trạng thái dữ liệu": "KHÔNG TÍNH ĐƯỢC HEAT COMBO", "Số dòng lịch sử": len(df)}

    cur = feat.iloc[-1]
    dist = float(cur["dist_ma20_pct"])
    rsi = float(cur["rsi"])
    vol_ratio = float(cur["volume_ratio"]) if not pd.isna(cur.get("volume_ratio", np.nan)) else np.nan

    dist_pct = percentile_rank(feat["dist_ma20_pct"], dist)
    rsi_pct = percentile_rank(feat["rsi"], rsi)

    width = max(2.0, abs(dist) * 0.15)
    low, high = dist - width, dist + width
    band = feat[(feat["dist_ma20_pct"] >= low) & (feat["dist_ma20_pct"] <= high)].dropna(subset=["ret_t5_pct"]).copy()

    win5 = win_rate(band["ret_t5_pct"])
    avg5 = avg_ret(band["ret_t5_pct"])
    dd5 = avg_ret(band["max_dd_t5_pct"])

    combo_score, good, bad = heat_score(dist_pct, rsi, vol_ratio, win5, avg5)
    label = heat_label(combo_score, dist_pct, rsi)

    return {
        "Mã": symbol,
        "Trạng thái dữ liệu": "OK",
        "Ngày": str(pd.to_datetime(cur["date"]).date()),
        "Giá": round(float(cur["close"]), 2),
        "MA20": round(float(cur["ma20"]), 2),
        "Dist MA20 %": round(dist, 2),
        "Phân vị nóng MA20 %": round(dist_pct, 2) if not pd.isna(dist_pct) else "",
        "RSI": round(rsi, 2),
        "Phân vị nóng RSI %": round(rsi_pct, 2) if not pd.isna(rsi_pct) else "",
        "Volume Ratio": round(vol_ratio, 2) if not pd.isna(vol_ratio) else "",
        "Số mẫu vùng MA20 tương tự": int(len(band)),
        "Win T+5 vùng tương tự %": round(win5, 2) if not pd.isna(win5) else "",
        "Lợi TB T+5 vùng tương tự %": round(avg5, 2) if not pd.isna(avg5) else "",
        "Drawdown TB T+5 vùng tương tự %": round(dd5, 2) if not pd.isna(dd5) else "",
        "Điểm Heat Combo": round(combo_score, 2),
        "Kết luận Heat Combo": label,
        "Điểm mạnh": " | ".join(good[:5]),
        "Điểm yếu": " | ".join(bad[:5]),
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


def build_report(df, source):
    lines = [
        "✅ <b>V14.3 HEAT COMBO HOÀN TẤT</b>",
        "",
        f"Nguồn mã: <b>{source or 'N/A'}</b>",
        f"Số mã kiểm tra: <b>{len(df)}</b>",
        "",
        "<b>KẾT QUẢ HEAT COMBO</b>",
    ]

    for _, r in df.head(8).iterrows():
        lines.append(f"🔹 <b>{r.get('Mã','')}</b> | Heat: <b>{fmt(r.get('Điểm Heat Combo'))}</b> | {r.get('Kết luận Heat Combo','')}")
        lines.append(f"   MA20: {fmt(r.get('Dist MA20 %'))}% | MA20 hot: {fmt(r.get('Phân vị nóng MA20 %'))}% | RSI: {fmt(r.get('RSI'))}")
        lines.append(f"   Win T+5: {fmt(r.get('Win T+5 vùng tương tự %'))}% | Lợi TB T+5: {fmt(r.get('Lợi TB T+5 vùng tương tự %'))}%")
        good = str(r.get("Điểm mạnh", ""))
        bad = str(r.get("Điểm yếu", ""))
        if good and good.lower() != "nan":
            lines.append(f"   Mạnh: {good}")
        if bad and bad.lower() != "nan":
            lines.append(f"   Yếu: {bad}")
    return "\n".join(lines)


def send_telegram(text):
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("WARN: thiếu TELEGRAM_TOKEN/TELEGRAM_CHAT_ID, bỏ qua gửi V14.3", flush=True)
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = requests.post(url, data={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=20)
        print("TELEGRAM V14.3 STATUS:", r.status_code, r.text[:200], flush=True)
        return r.status_code == 200
    except Exception as e:
        print("WARN: gửi Telegram V14.3 lỗi:", repr(e), flush=True)
        return False


def main():
    print("V14.3 HEAT COMBO STARTED", flush=True)
    symbols, source = load_symbol_list()
    if not symbols:
        out = pd.DataFrame([{"Trạng thái": "Không tìm thấy danh sách mã đầu vào"}])
        out.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
        Path(OUT_TXT).write_text("Không tìm thấy danh sách mã đầu vào", encoding="utf-8")
        return

    rows = []
    for i, symbol in enumerate(symbols, 1):
        print(f"[{i}/{len(symbols)}] Heat combo {symbol}", flush=True)
        rows.append(analyze_symbol(symbol))

    df = pd.DataFrame(rows)
    if "Điểm Heat Combo" in df.columns:
        df["__score"] = pd.to_numeric(df["Điểm Heat Combo"], errors="coerce")
        df = df.sort_values("__score", ascending=False, na_position="last").drop(columns=["__score"]).reset_index(drop=True)

    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>V14.3 Heat Combo</title>{html_style()}</head>
<body><h2>V14.3 - HEAT COMBO</h2><div class="note"><b>Generated:</b> {now_str()}<br><b>Nguồn danh sách mã:</b> {source}<br><b>Ý nghĩa:</b> Kết hợp MA20 heat + RSI heat + Volume + lịch sử T+5 để phân biệt đang khỏe hay nóng thật.</div>{df.to_html(index=False, escape=True)}</body></html>"""
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
