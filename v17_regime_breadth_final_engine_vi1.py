# -*- coding: utf-8 -*-
"""
v17_regime_breadth_final_engine_vi.py

V17 - REGIME + BREADTH FINAL ENGINE
- Doc output hien co: ai_risk_filtered/all_signal_results, V14.3, V15.1, V15.2.
- Tinh market breadth tu cache_stock/*.csv.
- Them hard gate + dynamic weight cho thi truong Viet Nam.

Output:
- v17_final_decision.csv
- v17_final_decision.html
- v17_final_decision_report.txt
"""

from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd
import requests

CACHE_DIR = os.getenv("CACHE_DIR", "cache_stock")
BASE_FILES = [
    os.getenv("AI_RISK_PATH", "ai_risk_filtered.csv"),
    os.getenv("ALL_RESULT_PATH", "all_signal_results.csv"),
    os.getenv("INTRADAY_WATCHLIST_PATH", "intraday_watchlist.csv"),
]
HEAT_FILE = os.getenv("V143_HEAT_CSV", "v143_heat_combo.csv")
BOTTOM_FILE = os.getenv("V151_BOTTOM_CSV", "v151_bottom_quality.csv")
WF_BOTTOM_FILE = os.getenv("V152_BOTTOM_WF_CSV", "v152_bottom_walkforward.csv")
WF_MOM_FILE = os.getenv("V152_MOM_WF_CSV", "v152_momentum_walkforward.csv")
OUT_CSV = "v17_final_decision.csv"
OUT_HTML = "v17_final_decision.html"
OUT_TXT = "v17_final_decision_report.txt"


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_csv(path):
    try:
        return pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()
    except Exception as e:
        print(f"WARN: cannot read {path}: {e}", flush=True)
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


def normalize(df):
    if df is None or df.empty:
        return pd.DataFrame()
    ma = find_col(df, ["Mã", "Ma", "Symbol", "Ticker"])
    if ma is None:
        return pd.DataFrame()
    out = df.copy()
    out["__ma"] = out[ma].astype(str).str.upper().str.strip()
    out = out[(out["__ma"] != "") & (out["__ma"] != "NAN") & (out["__ma"] != "NO_SIGNAL")]
    return out.drop_duplicates("__ma", keep="first").reset_index(drop=True)


def first_existing(files):
    for f in files:
        df = normalize(read_csv(f))
        if not df.empty:
            return df, f
    return pd.DataFrame(), ""


def row_map(df):
    if df is None or df.empty or "__ma" not in df.columns:
        return {}
    return {r["__ma"]: r for _, r in df.iterrows()}


def val(row, names, default=""):
    if row is None:
        return default
    for n in names:
        if n in row.index:
            x = row.get(n, default)
            if not pd.isna(x):
                return x
    lower = {str(c).strip().lower(): c for c in row.index}
    for n in names:
        k = str(n).strip().lower()
        if k in lower:
            x = row.get(lower[k], default)
            if not pd.isna(x):
                return x
    return default


def fnum(x, default=np.nan):
    try:
        if pd.isna(x) or x == "":
            return default
        return float(x)
    except Exception:
        return default


def fmt(x, d=2):
    try:
        if pd.isna(x) or x == "":
            return ""
        return f"{float(x):.{d}f}"
    except Exception:
        return str(x)


def calc_rsi(close, window=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window).mean()
    avg_loss = loss.rolling(window).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def normalize_cache(df):
    if df is None or df.empty:
        return pd.DataFrame()
    date_col = find_col(df, ["time", "date", "Ngày", "Ngay", "Date"])
    close_col = find_col(df, ["close", "Close", "Giá", "Gia"])
    volume_col = find_col(df, ["volume", "Volume", "vol"])
    if date_col is None or close_col is None:
        return pd.DataFrame()
    out = pd.DataFrame()
    out["date"] = pd.to_datetime(df[date_col], errors="coerce")
    out["close"] = pd.to_numeric(df[close_col], errors="coerce")
    out["volume"] = pd.to_numeric(df[volume_col], errors="coerce") if volume_col else np.nan
    out = out.dropna(subset=["date", "close"]).sort_values("date").drop_duplicates("date")
    return out.reset_index(drop=True)


def compute_market_breadth(cache_dir=CACHE_DIR):
    p = Path(cache_dir)
    if not p.exists():
        return {"market_mode": "KHÔNG ĐỦ DỮ LIỆU", "market_score": 0, "breadth_above_ma20_pct": "", "breadth_ma5_gt_ma20_pct": "", "breadth_up_1d_pct": "", "breadth_rsi_hot_pct": "", "breadth_rsi_weak_pct": "", "universe_count": 0}
    rows = []
    for fp in p.glob("*.csv"):
        df = normalize_cache(read_csv(str(fp)))
        if len(df) < 30:
            continue
        d = df.copy()
        d["ma5"] = d["close"].rolling(5).mean()
        d["ma20"] = d["close"].rolling(20).mean()
        d["rsi"] = calc_rsi(d["close"], 14)
        d["ret1"] = (d["close"] / d["close"].shift(1) - 1) * 100
        dd = d.dropna(subset=["ma20", "rsi"])
        if dd.empty:
            continue
        last = dd.iloc[-1]
        rows.append({
            "symbol": fp.stem.upper(),
            "above_ma20": bool(last["close"] > last["ma20"]),
            "ma5_gt_ma20": bool(last["ma5"] > last["ma20"]),
            "up_1d": bool(last["ret1"] > 0),
            "rsi_hot": bool(last["rsi"] > 70),
            "rsi_weak": bool(last["rsi"] < 30),
        })
    if not rows:
        return {"market_mode": "KHÔNG ĐỦ DỮ LIỆU", "market_score": 0, "breadth_above_ma20_pct": "", "breadth_ma5_gt_ma20_pct": "", "breadth_up_1d_pct": "", "breadth_rsi_hot_pct": "", "breadth_rsi_weak_pct": "", "universe_count": 0}
    b = pd.DataFrame(rows)
    above = b["above_ma20"].mean() * 100
    trend = b["ma5_gt_ma20"].mean() * 100
    up1 = b["up_1d"].mean() * 100
    hot = b["rsi_hot"].mean() * 100
    weak = b["rsi_weak"].mean() * 100
    score = max(0, min(100, 0.45 * above + 0.35 * trend + 0.20 * up1))
    if score >= 70:
        mode = "THỊ TRƯỜNG MẠNH"
    elif score >= 55:
        mode = "THỊ TRƯỜNG TÍCH CỰC"
    elif score >= 40:
        mode = "SIDEWAY / TRUNG TÍNH"
    elif score >= 25:
        mode = "THỊ TRƯỜNG YẾU"
    else:
        mode = "RISK OFF"
    return {"market_mode": mode, "market_score": round(score, 2), "breadth_above_ma20_pct": round(above, 2), "breadth_ma5_gt_ma20_pct": round(trend, 2), "breadth_up_1d_pct": round(up1, 2), "breadth_rsi_hot_pct": round(hot, 2), "breadth_rsi_weak_pct": round(weak, 2), "universe_count": len(b)}


def wf_label_score(label):
    s = str(label).upper()
    if "ỔN ĐỊNH MẠNH" in s or "ON DINH MANH" in s:
        return 100
    if "ỔN ĐỊNH VỪA" in s or "ON DINH VUA" in s:
        return 75
    if "TRUNG TÍNH" in s or "TRUNG TINH" in s:
        return 55
    if "MẪU ÍT" in s or "MAU IT" in s:
        return 45
    if "YẾU" in s or "HỌC VẸT" in s or "HOC VET" in s:
        return 20
    return 50


def normalize_score(x, default=50):
    v = fnum(x, np.nan)
    if pd.isna(v):
        return default
    return max(0, min(100, v))


def infer_strategy(base_row, heat_row, bottom_row):
    base_strategy = str(val(base_row, ["Strategy", "Chiến lược", "Chien luoc"], "")).upper()
    if "BOTTOM" in base_strategy:
        return "BOTTOM"
    if "MOMENTUM" in base_strategy:
        return "MOMENTUM"
    texts = []
    for r in [base_row, heat_row, bottom_row]:
        if r is not None:
            texts.append(" ".join([str(x) for x in r.values]))
    s = " ".join(texts).upper()
    if "BOTTOM" in s or "ĐÁY" in s or "HỒI KỸ THUẬT" in s or "BULL TRAP" in s:
        return "BOTTOM"
    if "MOMENTUM" in s or "HEAT" in s or "KHỎE" in s:
        return "MOMENTUM"
    return "MIXED"


def weights(strategy, market_mode):
    mode = str(market_mode).upper()
    if strategy == "MOMENTUM":
        if "MẠNH" in mode or "TÍCH CỰC" in mode:
            return {"base": .15, "heat": .25, "bottom": .05, "wf_mom": .35, "wf_bottom": .05, "regime": .15}
        if "YẾU" in mode or "RISK OFF" in mode:
            return {"base": .15, "heat": .20, "bottom": .05, "wf_mom": .30, "wf_bottom": .05, "regime": .25}
        return {"base": .15, "heat": .25, "bottom": .05, "wf_mom": .30, "wf_bottom": .05, "regime": .20}
    if strategy == "BOTTOM":
        if "YẾU" in mode or "RISK OFF" in mode:
            return {"base": .10, "heat": .05, "bottom": .30, "wf_mom": .05, "wf_bottom": .35, "regime": .15}
        return {"base": .15, "heat": .10, "bottom": .25, "wf_mom": .05, "wf_bottom": .30, "regime": .15}
    return {"base": .20, "heat": .20, "bottom": .20, "wf_mom": .15, "wf_bottom": .15, "regime": .10}


def base_component(row):
    risk = str(val(row, ["Risk", "Risk Status", "Rủi ro", "Rui ro"], "")).upper()
    action = str(val(row, ["Action", "Hành động hiện tại", "Hanh dong hien tai", "Hành động", "Hanh dong"], "")).upper()
    score, reasons = 50, []
    if "PASS" in risk:
        score += 20; reasons.append("risk pass")
    if "FAIL" in risk:
        score -= 50; reasons.append("risk fail")
    if "BUY NOW" in action:
        score += 20; reasons.append("buy now")
    elif "WATCH" in action or "WAIT" in action or "THEO" in action:
        score += 5; reasons.append("watch/wait")
    elif "SKIP" in action:
        score -= 30; reasons.append("skip")
    return max(0, min(100, score)), reasons


def heat_component(hr):
    if hr is None:
        return 50, "", []
    txt = " ".join([str(x) for x in hr.values]).upper()
    label = str(val(hr, ["Kết luận Heat Combo", "Ket luan Heat Combo", "Trạng thái", "Trang thai"], ""))
    score = normalize_score(val(hr, ["Heat", "Điểm Heat", "Diem Heat", "Điểm", "Diem"], ""), 60)
    reasons = []
    if "KHỎE" in txt or "KHOE" in txt:
        score += 10; reasons.append("heat khỏe")
    if "ỔN NHƯNG" in txt or "ON NHUNG" in txt:
        score -= 5; reasons.append("heat ổn nhưng không mua đuổi")
    if "QUÁ NÓNG" in txt or "QUA NONG" in txt:
        score -= 30; reasons.append("quá nóng")
    if "GIẢM TỶ TRỌNG" in txt or "GIAM TY TRONG" in txt:
        score -= 15; reasons.append("giảm tỷ trọng")
    return max(0, min(100, score)), label, reasons


def bottom_component(br):
    if br is None:
        return 50, "", []
    txt = " ".join([str(x) for x in br.values]).upper()
    label = str(val(br, ["Phân loại Bottom V15.1", "Phan loai Bottom V15.1"], ""))
    score = normalize_score(val(br, ["Điểm Bottom V15.1", "Diem Bottom V15.1"], ""), 60)
    reasons = []
    if "ĐÁY CHẤT LƯỢNG" in txt or "DAY CHAT LUONG" in txt:
        score += 10; reasons.append("đáy chất lượng")
    elif "HỒI KỸ THUẬT" in txt or "HOI KY THUAT" in txt:
        score -= 5; reasons.append("hồi kỹ thuật")
    if "BULL TRAP" in txt:
        score -= 35; reasons.append("bull trap")
    if "DAO RƠI" in txt or "DAO ROI" in txt:
        score -= 50; reasons.append("dao rơi")
    return max(0, min(100, score)), label, reasons


def regime_component(strategy, market):
    mode, score = market["market_mode"], fnum(market["market_score"], 50)
    if strategy == "MOMENTUM":
        if "MẠNH" in mode or "TÍCH CỰC" in mode:
            score += 15
        elif "YẾU" in mode or "RISK OFF" in mode:
            score -= 25
    elif strategy == "BOTTOM":
        if "YẾU" in mode or "RISK OFF" in mode:
            score += 5
        elif "MẠNH" in mode:
            score -= 5
    return max(0, min(100, score))


def hard_gate(score, row, heat_reasons, bottom_reasons, wf_m, wf_b, strategy, market):
    action = str(val(row, ["Action", "Hành động hiện tại", "Hanh dong hien tai", "Hành động", "Hanh dong"], "")).upper()
    risk = str(val(row, ["Risk", "Risk Status", "Rủi ro", "Rui ro"], "")).upper()
    cap, reasons = 100, []
    if "FAIL" in risk:
        cap = min(cap, 40); reasons.append("Risk FAIL")
    if "SKIP" in action:
        cap = min(cap, 45); reasons.append("Action SKIP")
    if "WATCH" in action or "WAIT" in action:
        cap = min(cap, 85); reasons.append("Action WATCH/WAIT")
    if any("quá nóng" in r for r in heat_reasons):
        cap = min(cap, 75); reasons.append("Quá nóng không mua đuổi")
    if any("bull trap" in r for r in bottom_reasons):
        cap = min(cap, 45); reasons.append("Bull trap")
    if any("dao rơi" in r for r in bottom_reasons):
        cap = min(cap, 35); reasons.append("Dao rơi")
    if strategy == "MOMENTUM":
        if "YẾU" in str(wf_m) or "HỌC VẸT" in str(wf_m):
            cap = min(cap, 55); reasons.append("WF momentum yếu")
        if "TRUNG TÍNH" in str(wf_m):
            cap = min(cap, 82); reasons.append("WF momentum trung tính")
    if strategy == "BOTTOM":
        if "YẾU" in str(wf_b) or "HỌC VẸT" in str(wf_b):
            cap = min(cap, 55); reasons.append("WF bottom yếu")
        if "TRUNG TÍNH" in str(wf_b):
            cap = min(cap, 82); reasons.append("WF bottom trung tính")
    if strategy == "MOMENTUM" and ("YẾU" in market["market_mode"] or "RISK OFF" in market["market_mode"]):
        cap = min(cap, 75); reasons.append("Market yếu giảm momentum")
    return min(score, cap), cap, reasons


def final_label(score):
    if score >= 85:
        return "🟢 ƯU TIÊN CAO"
    if score >= 70:
        return "🟡 THEO DÕI"
    if score >= 55:
        return "🟠 CHỜ ĐIỂM ĐẸP"
    return "❌ LOẠI"


def build():
    market = compute_market_breadth()
    base, source = first_existing(BASE_FILES)
    if base.empty:
        return pd.DataFrame([{"Trạng thái": "Không tìm thấy dữ liệu nền"}]), source, market
    heat, bottom = normalize(read_csv(HEAT_FILE)), normalize(read_csv(BOTTOM_FILE))
    wf_bottom, wf_mom = normalize(read_csv(WF_BOTTOM_FILE)), normalize(read_csv(WF_MOM_FILE))
    hm, bm, wbm, wmm = row_map(heat), row_map(bottom), row_map(wf_bottom), row_map(wf_mom)
    rows = []
    for _, br in base.iterrows():
        ma = br["__ma"]
        hr, botr, wfb, wfm = hm.get(ma), bm.get(ma), wbm.get(ma), wmm.get(ma)
        strategy = infer_strategy(br, hr, botr)
        action = val(br, ["Action", "Hành động hiện tại", "Hanh dong hien tai", "Hành động", "Hanh dong"], "")
        risk = val(br, ["Risk", "Risk Status", "Rủi ro", "Rui ro"], "")
        close = val(br, ["Giá", "Gia", "Close"], "")
        base_s, base_r = base_component(br)
        heat_s, heat_label, heat_r = heat_component(hr)
        bottom_s, bottom_label, bottom_r = bottom_component(botr)
        wf_m_label = str(val(wfm, ["Độ ổn định mẫu", "Do on dinh mau"], "")) if wfm is not None else ""
        wf_b_label = str(val(wfb, ["Độ ổn định mẫu", "Do on dinh mau"], "")) if wfb is not None else ""
        wf_m_s, wf_b_s = wf_label_score(wf_m_label), wf_label_score(wf_b_label)
        regime_s = regime_component(strategy, market)
        w = weights(strategy, market["market_mode"])
        raw = base_s*w["base"] + heat_s*w["heat"] + bottom_s*w["bottom"] + wf_m_s*w["wf_mom"] + wf_b_s*w["wf_bottom"] + regime_s*w["regime"]
        gated, cap, gate_r = hard_gate(raw, br, heat_r, bottom_r, wf_m_label, wf_b_label, strategy, market)
        decision = final_label(gated)
        reasons = base_r + heat_r + bottom_r + gate_r
        if wf_m_label: reasons.append(f"WF momentum {wf_m_label}")
        if wf_b_label: reasons.append(f"WF bottom {wf_b_label}")
        reasons.append(f"Market {market['market_mode']}")
        rows.append({"Mã": ma, "Giá": close, "Strategy V17": strategy, "Action gốc": action, "Risk": risk, "Điểm thô": round(raw,2), "Điểm V17": round(gated,2), "Cap": round(cap,2), "Quyết định V17": decision, "Market mode": market["market_mode"], "Market score": market["market_score"], "Heat label": heat_label, "Bottom label": bottom_label, "WF Momentum": wf_m_label, "WF Bottom": wf_b_label, "Lý do V17": " | ".join([str(x) for x in reasons if str(x)])})
    out = pd.DataFrame(rows)
    rank = {"🟢 ƯU TIÊN CAO": 1, "🟡 THEO DÕI": 2, "🟠 CHỜ ĐIỂM ĐẸP": 3, "❌ LOẠI": 4}
    out["__rank"] = out["Quyết định V17"].map(rank).fillna(9)
    out["__score"] = pd.to_numeric(out["Điểm V17"], errors="coerce")
    out = out.sort_values(["__rank", "__score"], ascending=[True, False]).drop(columns=["__rank", "__score"])
    # Quota: toi da 3 ma uu tien cao
    high_idx = out.index[out["Quyết định V17"] == "🟢 ƯU TIÊN CAO"].tolist()
    if len(high_idx) > 3:
        for idx in high_idx[3:]:
            out.loc[idx, "Quyết định V17"] = "🟡 THEO DÕI"
            out.loc[idx, "Lý do V17"] = str(out.loc[idx, "Lý do V17"]) + " | Hạ do quota max 3 ưu tiên cao"
    out["__rank"] = out["Quyết định V17"].map(rank).fillna(9)
    out["__score"] = pd.to_numeric(out["Điểm V17"], errors="coerce")
    out = out.sort_values(["__rank", "__score"], ascending=[True, False]).drop(columns=["__rank", "__score"])
    return out.reset_index(drop=True), source, market


def html_style():
    return """
<style>
body{font-family:Arial,sans-serif;background:#0f172a;color:#e5e7eb;padding:18px}
h2,h3{color:#fff}.note{background:#111827;border:1px solid #334155;border-radius:10px;padding:12px;margin:12px 0}
.card{background:#111827;border:1px solid #334155;border-radius:12px;padding:12px;margin:14px 0;overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:12px;background:#111827}
th{background:#1f2937;color:#fff;position:sticky;top:0}
td,th{border:1px solid #334155;padding:7px;white-space:nowrap;vertical-align:top}
tr:nth-child(even){background:#0b1220}
</style>
"""


def report_text(df, source, market):
    lines = ["✅ <b>V17 REGIME + BREADTH FINAL HOÀN TẤT</b>", "", f"Nguồn nền: <b>{source}</b>", f"Số mã tổng hợp: <b>{len(df)}</b>", f"Market: <b>{market['market_mode']}</b> | Score: <b>{market['market_score']}</b>", f"Above MA20: <b>{market['breadth_above_ma20_pct']}%</b> | MA5>MA20: <b>{market['breadth_ma5_gt_ma20_pct']}%</b>", "", "<b>TOP QUYẾT ĐỊNH V17</b>"]
    top = df[df["Quyết định V17"].astype(str).str.contains("ƯU TIÊN|THEO DÕI|CHỜ", na=False)].head(10)
    if top.empty: top = df.head(10)
    for _, r in top.iterrows():
        lines += ["", f"🔹 <b>{r.get('Mã','')}</b> | {r.get('Quyết định V17','')} | Điểm {fmt(r.get('Điểm V17'))}", f"Strategy: {r.get('Strategy V17','')} | Risk: {r.get('Risk','')} | Action: {r.get('Action gốc','')}", f"WF: Mom {r.get('WF Momentum','')} | Bottom {r.get('WF Bottom','')}", f"Lý do: {r.get('Lý do V17','')}"]
    return "\n".join(lines)


def send_telegram(text):
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("WARN: thiếu Telegram, bỏ qua V17", flush=True); return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = requests.post(url, data={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=20)
        print("TELEGRAM V17 STATUS:", r.status_code, r.text[:160], flush=True)
    except Exception as e:
        print("WARN Telegram V17:", repr(e), flush=True)


def main():
    print("V17 REGIME + BREADTH FINAL ENGINE STARTED", flush=True)
    df, source, market = build()
    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    high = df[df["Quyết định V17"].astype(str).str.contains("ƯU TIÊN", na=False)] if "Quyết định V17" in df.columns else pd.DataFrame()
    watch = df[df["Quyết định V17"].astype(str).str.contains("THEO DÕI|CHỜ", na=False)] if "Quyết định V17" in df.columns else pd.DataFrame()
    reject = df[df["Quyết định V17"].astype(str).str.contains("LOẠI", na=False)] if "Quyết định V17" in df.columns else pd.DataFrame()
    market_html = pd.DataFrame([market]).to_html(index=False, escape=True)
    html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'><title>V17 Final Decision</title>{html_style()}</head><body>
<h2>V17 - REGIME + BREADTH FINAL ENGINE</h2>
<div class='note'><b>Generated:</b> {now_str()}<br><b>Nguồn nền:</b> {source}<br><b>Ý nghĩa:</b> V16 + Market Regime + Breadth + Dynamic Weight + Hard Gate + Quota.</div>
<div class='card'><h3>0. MARKET REGIME / BREADTH</h3>{market_html}</div>
<div class='card'><h3>1. TOP ƯU TIÊN CAO</h3>{high.to_html(index=False, escape=True) if not high.empty else '<p>Không có mã ưu tiên cao.</p>'}</div>
<div class='card'><h3>2. THEO DÕI / CHỜ ĐIỂM ĐẸP</h3>{watch.to_html(index=False, escape=True) if not watch.empty else '<p>Không có mã theo dõi.</p>'}</div>
<div class='card'><h3>3. LOẠI / KHÔNG ƯU TIÊN</h3>{reject.to_html(index=False, escape=True) if not reject.empty else '<p>Không có mã loại.</p>'}</div>
<div class='card'><h3>4. BẢNG ĐẦY ĐỦ V17</h3>{df.to_html(index=False, escape=True)}</div>
</body></html>"""
    Path(OUT_HTML).write_text(html, encoding="utf-8")
    rep = report_text(df, source, market)
    Path(OUT_TXT).write_text(rep, encoding="utf-8")
    print(rep.replace("<b>", "").replace("</b>", ""), flush=True)
    print(f"OK: wrote {OUT_CSV}", flush=True)
    print(f"OK: wrote {OUT_HTML}", flush=True)
    print(f"OK: wrote {OUT_TXT}", flush=True)
    send_telegram(rep)

if __name__ == "__main__":
    main()
