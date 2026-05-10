# -*- coding: utf-8 -*-
"""
v15_bottom_quality_engine_vi.py

V15 - BOTTOM QUALITY ENGINE
Phân loại: ĐÁY CHẤT LƯỢNG / HỒI KỸ THUẬT / BULL TRAP / DAO RƠI.

Không sửa tín hiệu gốc, không sửa dashboard chính.
Đọc cache_stock/{MÃ}.csv và danh sách mã từ ai_risk_filtered.csv / all_signal_results.csv.
"""

from __future__ import annotations
import os
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd
import requests

CACHE_DIR = os.getenv("CACHE_DIR", "cache_stock")
INPUT_FILES = [
    os.getenv("AI_RISK_PATH", "ai_risk_filtered.csv"),
    os.getenv("ALL_RESULT_PATH", "all_signal_results.csv"),
    os.getenv("INTRADAY_WATCHLIST_PATH", "intraday_watchlist.csv"),
]
OUT_CSV = "v15_bottom_quality.csv"
OUT_HTML = "v15_bottom_quality.html"
OUT_TXT = "v15_bottom_quality_report.txt"

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def safe_read_csv(path):
    try:
        return pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()
    except Exception as e:
        print(f"WARN đọc lỗi {path}: {repr(e)}", flush=True)
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
        t = str(c).strip().lower()
        for n in names:
            if str(n).strip().lower() in t:
                return c
    return None

def fmt(x, d=2):
    try:
        if pd.isna(x):
            return ""
        return f"{float(x):.{d}f}"
    except Exception:
        return str(x)

def load_candidates():
    for path in INPUT_FILES:
        df = safe_read_csv(path)
        if df.empty:
            continue
        ma_col = find_col(df, ["Mã", "Ma", "Symbol", "Ticker"])
        if not ma_col:
            continue
        strat_col = find_col(df, ["Strategy", "Chiến lược", "Chien luoc"])
        temp = df.copy()
        temp["__ma"] = temp[ma_col].astype(str).str.upper().str.strip()
        if strat_col:
            bottom = temp[temp[strat_col].astype(str).str.upper().str.contains("BOTTOM", na=False)].copy()
            if not bottom.empty:
                temp = bottom
        syms = temp["__ma"].dropna().drop_duplicates().tolist()
        syms = [s for s in syms if s and s not in ["NAN", "NO_SIGNAL"]]
        if syms:
            return syms, path
    return [], ""

def load_cache(symbol):
    for s in [symbol, symbol.upper(), symbol.lower()]:
        p = Path(CACHE_DIR) / f"{s}.csv"
        if p.exists():
            return safe_read_csv(str(p))
    return pd.DataFrame()

def normalize_cache(df):
    if df is None or df.empty:
        return pd.DataFrame()
    date_col = find_col(df, ["time", "date", "Ngày", "Ngay", "Date"])
    open_col = find_col(df, ["open", "Open"])
    high_col = find_col(df, ["high", "High"])
    low_col = find_col(df, ["low", "Low"])
    close_col = find_col(df, ["close", "Close", "Giá", "Gia"])
    volume_col = find_col(df, ["volume", "Volume", "vol"])
    if not date_col or not close_col:
        return pd.DataFrame()
    out = pd.DataFrame()
    out["date"] = pd.to_datetime(df[date_col], errors="coerce")
    out["close"] = pd.to_numeric(df[close_col], errors="coerce")
    out["open"] = pd.to_numeric(df[open_col], errors="coerce") if open_col else out["close"]
    out["high"] = pd.to_numeric(df[high_col], errors="coerce") if high_col else out["close"]
    out["low"] = pd.to_numeric(df[low_col], errors="coerce") if low_col else out["close"]
    out["volume"] = pd.to_numeric(df[volume_col], errors="coerce") if volume_col else np.nan
    return out.dropna(subset=["date", "close"]).sort_values("date").drop_duplicates("date").reset_index(drop=True)

def calc_rsi(close, window=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window).mean()
    avg_loss = loss.rolling(window).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def add_features(df):
    out = df.copy()
    out["ma5"] = out["close"].rolling(5).mean()
    out["ma20"] = out["close"].rolling(20).mean()
    out["rsi"] = calc_rsi(out["close"], 14)
    out["vol_ma20"] = out["volume"].rolling(20).mean()
    out["volume_ratio"] = out["volume"] / out["vol_ma20"]
    out["ret_5"] = (out["close"] / out["close"].shift(5) - 1) * 100
    out["ret_10"] = (out["close"] / out["close"].shift(10) - 1) * 100
    out["high20"] = out["high"].rolling(20).max()
    out["low20"] = out["low"].rolling(20).min()
    out["drawdown20_pct"] = (out["close"] / out["high20"] - 1) * 100
    out["rebound_low20_pct"] = (out["close"] / out["low20"] - 1) * 100
    out["break_low20"] = out["close"] < out["low20"].shift(1)
    rng = (out["high"] - out["low"]).replace(0, np.nan)
    out["close_position"] = (out["close"] - out["low"]) / rng
    out["ret_t3_pct"] = (out["close"].shift(-3) / out["close"] - 1) * 100
    out["ret_t5_pct"] = (out["close"].shift(-5) / out["close"] - 1) * 100
    out["ret_t10_pct"] = (out["close"].shift(-10) / out["close"] - 1) * 100
    future_min = pd.concat([out["low"].shift(-i) for i in range(1, 6)], axis=1).min(axis=1)
    out["max_dd_t5_pct"] = (future_min / out["close"] - 1) * 100
    return out

def win_rate(s):
    v = pd.to_numeric(s, errors="coerce").dropna()
    return np.nan if len(v) == 0 else float((v > 0).mean() * 100)

def avg_ret(s):
    v = pd.to_numeric(s, errors="coerce").dropna()
    return np.nan if len(v) == 0 else float(v.mean())

def similar_band(feat, cur):
    pool = feat.iloc[:-10].dropna(subset=["rsi", "drawdown20_pct", "rebound_low20_pct", "ret_t5_pct"]).copy()
    if pool.empty:
        return pool
    rsi = cur["rsi"]; dd = cur["drawdown20_pct"]; rb = cur["rebound_low20_pct"]
    cond = pool["rsi"].between(rsi - 8, rsi + 8) & pool["drawdown20_pct"].between(dd - 6, dd + 6) & pool["rebound_low20_pct"].between(max(0, rb - 5), rb + 5)
    band = pool[cond].copy()
    if len(band) < 10:
        cond = pool["rsi"].between(rsi - 12, rsi + 12) & pool["drawdown20_pct"].between(dd - 10, dd + 10)
        band = pool[cond].copy()
    return band

def classify(score, cur):
    if bool(cur.get("break_low20", False)) and cur.get("rebound_low20_pct", 0) < 1:
        return "⚫ DAO RƠI", "Thủng đáy 20 phiên và chưa có hồi đáng kể."
    if score >= 75:
        return "🟢 ĐÁY CHẤT LƯỢNG", "Có hồi, có xác nhận và lịch sử vùng tương tự ủng hộ."
    if score >= 60:
        return "🟡 HỒI KỸ THUẬT", "Có hồi nhưng chưa đủ mạnh để xác nhận đáy chất lượng."
    if score >= 45:
        return "🔴 BULL TRAP", "Có hồi nhưng rủi ro gãy lại còn cao."
    return "⚫ DAO RƠI", "Giảm yếu, chưa có xác nhận hồi đáng tin."

def analyze_symbol(symbol):
    df = normalize_cache(load_cache(symbol))
    if df.empty or len(df) < 80:
        return {"Mã": symbol, "Trạng thái dữ liệu": "KHÔNG ĐỦ DỮ LIỆU", "Số dòng lịch sử": len(df)}
    feat = add_features(df).dropna(subset=["ma20", "rsi", "drawdown20_pct"]).copy()
    if feat.empty:
        return {"Mã": symbol, "Trạng thái dữ liệu": "KHÔNG TÍNH ĐƯỢC", "Số dòng lịch sử": len(df)}
    cur = feat.iloc[-1]
    band = similar_band(feat, cur)
    win3, win5, win10 = win_rate(band["ret_t3_pct"]), win_rate(band["ret_t5_pct"]), win_rate(band["ret_t10_pct"])
    avg3, avg5, avg10 = avg_ret(band["ret_t3_pct"]), avg_ret(band["ret_t5_pct"]), avg_ret(band["ret_t10_pct"])
    dd5 = avg_ret(band["max_dd_t5_pct"])

    score = 50.0; good=[]; bad=[]
    rsi=float(cur["rsi"]); draw=float(cur["drawdown20_pct"]); rebound=float(cur["rebound_low20_pct"])
    ret5=float(cur["ret_5"]) if not pd.isna(cur["ret_5"]) else np.nan
    ret10=float(cur["ret_10"]) if not pd.isna(cur["ret_10"]) else np.nan
    vol=float(cur["volume_ratio"]) if not pd.isna(cur["volume_ratio"]) else np.nan
    close=float(cur["close"]); ma5=float(cur["ma5"])

    if 30 <= rsi <= 48: score += 12; good.append(f"RSI vùng bắt đáy {rsi:.1f}")
    elif rsi < 25: score -= 10; bad.append(f"RSI quá yếu {rsi:.1f}")
    elif rsi > 55: score -= 5; bad.append(f"RSI không còn vùng đáy {rsi:.1f}")

    if draw <= -12: score += 10; good.append(f"Chiết khấu sâu {draw:.1f}%")
    elif draw <= -6: score += 6; good.append(f"Có chiết khấu {draw:.1f}%")
    elif draw > -3: score -= 5; bad.append("Chưa giảm đủ sâu")

    if 1.5 <= rebound <= 8: score += 10; good.append(f"Hồi từ đáy {rebound:.1f}%")
    elif rebound < 1: score -= 8; bad.append("Chưa có hồi từ đáy")
    elif rebound > 12: score -= 5; bad.append("Hồi quá xa")

    if close > ma5: score += 8; good.append("Đã lấy lại MA5")
    else: score -= 6; bad.append("Chưa lấy lại MA5")

    cp = cur.get("close_position", np.nan)
    if not pd.isna(cp):
        if cp >= 0.65: score += 6; good.append("Nến đóng gần cao nhất phiên")
        elif cp <= 0.35: score -= 6; bad.append("Nến đóng yếu gần đáy phiên")

    if not pd.isna(vol):
        if 0.8 <= vol <= 1.8: score += 5; good.append(f"Volume hồi hợp lý {vol:.2f}")
        elif vol > 2.5: score -= 5; bad.append(f"Volume quá đột biến {vol:.2f}")
        elif vol < 0.5: score -= 5; bad.append(f"Volume quá yếu {vol:.2f}")

    if not pd.isna(ret5) and ret5 < -8: score -= 8; bad.append(f"Rơi 5 phiên mạnh {ret5:.1f}%")
    if not pd.isna(ret10) and ret10 < -15: score -= 10; bad.append(f"Rơi 10 phiên mạnh {ret10:.1f}%")
    if bool(cur["break_low20"]): score -= 15; bad.append("Thủng đáy 20 phiên")

    if not pd.isna(win5):
        if win5 >= 58: score += 10; good.append(f"Win T+5 tốt {win5:.1f}%")
        elif win5 < 45: score -= 10; bad.append(f"Win T+5 yếu {win5:.1f}%")
    if not pd.isna(avg5):
        if avg5 >= 1: score += 7; good.append(f"Lợi TB T+5 tốt {avg5:.2f}%")
        elif avg5 < 0: score -= 7; bad.append(f"Lợi TB T+5 âm {avg5:.2f}%")

    score = max(min(score, 100), 0)
    label, reason = classify(score, cur)
    return {
        "Mã": symbol, "Trạng thái dữ liệu": "OK", "Ngày": str(pd.to_datetime(cur["date"]).date()),
        "Giá": round(close,2), "RSI": round(rsi,2), "Drawdown 20 phiên %": round(draw,2),
        "Hồi từ đáy 20 phiên %": round(rebound,2), "Ret 5 phiên %": round(ret5,2) if not pd.isna(ret5) else "",
        "Ret 10 phiên %": round(ret10,2) if not pd.isna(ret10) else "", "Volume Ratio": round(vol,2) if not pd.isna(vol) else "",
        "Đã lấy lại MA5": "CÓ" if close > ma5 else "CHƯA", "Thủng đáy 20 phiên": "CÓ" if bool(cur["break_low20"]) else "KHÔNG",
        "Số mẫu bottom tương tự": int(len(band)), "Win T+3 %": round(win3,2) if not pd.isna(win3) else "",
        "Win T+5 %": round(win5,2) if not pd.isna(win5) else "", "Win T+10 %": round(win10,2) if not pd.isna(win10) else "",
        "Lợi TB T+3 %": round(avg3,2) if not pd.isna(avg3) else "", "Lợi TB T+5 %": round(avg5,2) if not pd.isna(avg5) else "",
        "Lợi TB T+10 %": round(avg10,2) if not pd.isna(avg10) else "", "Drawdown TB T+5 %": round(dd5,2) if not pd.isna(dd5) else "",
        "Điểm Bottom V15": round(score,2), "Phân loại Bottom V15": label, "Kết luận": reason,
        "Điểm mạnh": " | ".join(good[:6]), "Điểm yếu": " | ".join(bad[:6]), "Số dòng lịch sử": int(len(feat))
    }

def html_style():
    return "<style>body{font-family:Arial;background:#0f172a;color:#e5e7eb;padding:18px}h2{color:#fff}.note{background:#111827;border:1px solid #334155;border-radius:10px;padding:12px;margin:12px 0}table{border-collapse:collapse;width:100%;font-size:12px;background:#111827}th{background:#1f2937;color:#fff;position:sticky;top:0}td,th{border:1px solid #334155;padding:7px;white-space:nowrap;vertical-align:top}tr:nth-child(even){background:#0b1220}</style>"

def build_report(df, source):
    lines=["✅ <b>V15 BOTTOM QUALITY HOÀN TẤT</b>","",f"Nguồn mã: <b>{source}</b>",f"Số mã kiểm tra: <b>{len(df)}</b>","","<b>TOP BOTTOM QUALITY</b>"]
    for _, r in df.head(8).iterrows():
        lines.append(f"🔹 <b>{r.get('Mã','')}</b> | {r.get('Phân loại Bottom V15','')} | Điểm {fmt(r.get('Điểm Bottom V15'))}")
        lines.append(f"   RSI {fmt(r.get('RSI'))} | DD20 {fmt(r.get('Drawdown 20 phiên %'))}% | Hồi đáy {fmt(r.get('Hồi từ đáy 20 phiên %'))}%")
        lines.append(f"   Win T+5 {fmt(r.get('Win T+5 %'))}% | Lợi TB T+5 {fmt(r.get('Lợi TB T+5 %'))}%")
        if str(r.get("Điểm mạnh","")): lines.append(f"   Mạnh: {r.get('Điểm mạnh','')}")
        if str(r.get("Điểm yếu","")): lines.append(f"   Yếu: {r.get('Điểm yếu','')}")
    return "\\n".join(lines)

def send_telegram(text):
    token=os.getenv("TELEGRAM_TOKEN","").strip(); chat_id=os.getenv("TELEGRAM_CHAT_ID","").strip()
    if not token or not chat_id:
        print("WARN thiếu Telegram, bỏ qua V15", flush=True); return False
    try:
        url=f"https://api.telegram.org/bot{token}/sendMessage"
        r=requests.post(url,data={"chat_id":chat_id,"text":text,"parse_mode":"HTML","disable_web_page_preview":True},timeout=20)
        print("TELEGRAM V15 STATUS:", r.status_code, r.text[:200], flush=True); return r.status_code==200
    except Exception as e:
        print("WARN gửi Telegram V15 lỗi:", repr(e), flush=True); return False

def main():
    print("V15 BOTTOM QUALITY ENGINE STARTED", flush=True)
    symbols, source = load_candidates()
    if not symbols:
        out=pd.DataFrame([{"Trạng thái":"Không tìm thấy danh sách mã đầu vào"}])
        out.to_csv(OUT_CSV,index=False,encoding="utf-8-sig"); Path(OUT_TXT).write_text("Không tìm thấy danh sách mã đầu vào",encoding="utf-8"); return
    rows=[]
    for i,symbol in enumerate(symbols,1):
        print(f"[{i}/{len(symbols)}] Bottom quality {symbol}", flush=True)
        rows.append(analyze_symbol(symbol))
    df=pd.DataFrame(rows)
    if "Điểm Bottom V15" in df.columns:
        df["__score"]=pd.to_numeric(df["Điểm Bottom V15"],errors="coerce")
        df=df.sort_values("__score",ascending=False,na_position="last").drop(columns=["__score"]).reset_index(drop=True)
    df.to_csv(OUT_CSV,index=False,encoding="utf-8-sig")
    html=f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>V15 Bottom Quality</title>{html_style()}</head><body><h2>V15 - BOTTOM QUALITY ENGINE</h2><div class="note"><b>Generated:</b> {now_str()}<br><b>Nguồn danh sách mã:</b> {source}<br><b>Ý nghĩa:</b> Phân loại đáy chất lượng / hồi kỹ thuật / bull trap / dao rơi. Không thay đổi tín hiệu gốc.</div>{df.to_html(index=False,escape=True)}</body></html>'
    Path(OUT_HTML).write_text(html,encoding="utf-8")
    report=build_report(df,source); Path(OUT_TXT).write_text(report,encoding="utf-8")
    print(report.replace("<b>","").replace("</b>",""), flush=True)
    print(f"OK: wrote {OUT_CSV}", flush=True); print(f"OK: wrote {OUT_HTML}", flush=True); print(f"OK: wrote {OUT_TXT}", flush=True)
    send_telegram(report)

if __name__ == "__main__":
    main()
