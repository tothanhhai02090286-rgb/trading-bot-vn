# -*- coding: utf-8 -*-
"""
v16_final_decision_engine_vi.py

V16 FINAL DECISION ENGINE
Tổng hợp kết quả:
- ai_risk_filtered.csv / all_signal_results.csv: action, risk, strategy nền
- v143_heat_combo.csv: momentum / heat combo
- v151_bottom_quality.csv: bottom quality
- v152_bottom_walkforward.csv: độ ổn định bottom
- v152_momentum_walkforward.csv: độ ổn định momentum

Output:
- v16_final_decision.csv
- v16_final_decision.html
- v16_final_decision_report.txt
"""

from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd
import requests


BASE_FILES = [
    os.getenv("AI_RISK_PATH", "ai_risk_filtered.csv"),
    os.getenv("ALL_RESULT_PATH", "all_signal_results.csv"),
    os.getenv("INTRADAY_WATCHLIST_PATH", "intraday_watchlist.csv"),
]

HEAT_FILE = os.getenv("V143_HEAT_CSV", "v143_heat_combo.csv")
BOTTOM_FILE = os.getenv("V151_BOTTOM_CSV", "v151_bottom_quality.csv")
WF_BOTTOM_FILE = os.getenv("V152_BOTTOM_WF_CSV", "v152_bottom_walkforward.csv")
WF_MOM_FILE = os.getenv("V152_MOM_WF_CSV", "v152_momentum_walkforward.csv")

OUT_CSV = "v16_final_decision.csv"
OUT_HTML = "v16_final_decision.html"
OUT_TXT = "v16_final_decision_report.txt"


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
    out = out.drop_duplicates("__ma", keep="first")
    return out


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


def wf_score(label):
    s = str(label).upper()
    if "ỔN ĐỊNH MẠNH" in s or "ON DINH MANH" in s:
        return 25
    if "ỔN ĐỊNH VỪA" in s or "ON DINH VUA" in s:
        return 15
    if "TRUNG TÍNH" in s or "TRUNG TINH" in s:
        return 5
    if "MẪU ÍT" in s or "MAU IT" in s:
        return -5
    if "YẾU" in s or "HỌC VẸT" in s or "HOC VET" in s:
        return -20
    return 0


def final_label(score, risk, reasons):
    rt = str(risk).upper()
    rs = " ".join(reasons).upper()

    if "FAIL" in rt:
        return "❌ LOẠI", "Risk FAIL."
    if ("QUÁ NÓNG" in rs or "QUA NONG" in rs) and score >= 65:
        return "🟡 THEO DÕI", "Setup ổn nhưng đang nóng, không mua đuổi."
    if score >= 80:
        return "🟢 ƯU TIÊN CAO", "Nhiều lớp xác nhận đồng thuận."
    if score >= 65:
        return "🟡 THEO DÕI", "Có tín hiệu tốt nhưng chưa đủ ưu tiên cao."
    if score >= 50:
        return "🟠 CHỜ ĐIỂM ĐẸP", "Cần thêm xác nhận hoặc chờ chỉnh."
    return "❌ LOẠI", "Điểm tổng hợp thấp hoặc mẫu không ổn định."


def infer_strategy(base_row, heat_row, bottom_row):
    texts = []
    for r in [base_row, heat_row, bottom_row]:
        if r is None:
            continue
        texts.append(" ".join([str(x) for x in r.values]))
    s = " ".join(texts).upper()
    if "BOTTOM" in s or "ĐÁY" in s or "HỒI KỸ THUẬT" in s or "BULL TRAP" in s:
        return "BOTTOM"
    if "MOMENTUM" in s or "HEAT" in s or "KHỎE" in s:
        return "MOMENTUM"
    return "MIXED"


def build():
    base, source = first_existing(BASE_FILES)
    if base.empty:
        return pd.DataFrame([{"Trạng thái": "Không tìm thấy dữ liệu nền"}]), source

    heat = normalize(read_csv(HEAT_FILE))
    bottom = normalize(read_csv(BOTTOM_FILE))
    wf_bottom = normalize(read_csv(WF_BOTTOM_FILE))
    wf_mom = normalize(read_csv(WF_MOM_FILE))

    heat_m = row_map(heat)
    bottom_m = row_map(bottom)
    wf_bottom_m = row_map(wf_bottom)
    wf_mom_m = row_map(wf_mom)

    rows = []
    for _, br in base.iterrows():
        ma = br["__ma"]
        hr = heat_m.get(ma)
        botr = bottom_m.get(ma)
        wfb = wf_bottom_m.get(ma)
        wfm = wf_mom_m.get(ma)

        action = val(br, ["Action", "Hành động hiện tại", "Hanh dong hien tai", "Hành động", "Hanh dong"], "")
        risk = val(br, ["Risk", "Risk Status", "Rủi ro", "Rui ro"], "")
        close = val(br, ["Giá", "Gia", "Close"], "")
        base_strategy = val(br, ["Strategy", "Chiến lược", "Chien luoc"], "")

        strategy = infer_strategy(br, hr, botr)
        if "BOTTOM" in str(base_strategy).upper():
            strategy = "BOTTOM"
        elif "MOMENTUM" in str(base_strategy).upper():
            strategy = "MOMENTUM"

        score = 50.0
        reasons = []

        if "PASS" in str(risk).upper():
            score += 10
            reasons.append("Risk PASS")
        elif "FAIL" in str(risk).upper():
            score -= 40
            reasons.append("Risk FAIL")

        if "BUY NOW" in str(action).upper():
            score += 10
            reasons.append("Action BUY NOW")
        elif "WATCH" in str(action).upper() or "THEO" in str(action).upper() or "WAIT" in str(action).upper():
            score += 4
            reasons.append("Action WATCH/WAIT")
        elif "SKIP" in str(action).upper():
            score -= 15
            reasons.append("Action SKIP")

        heat_label = ""
        heat_score = ""
        if hr is not None:
            heat_text = " ".join([str(x) for x in hr.values]).upper()
            heat_label = str(val(hr, ["Kết luận Heat Combo", "Ket luan Heat Combo", "Trạng thái", "Trang thai"], ""))
            heat_score = val(hr, ["Heat", "Điểm Heat", "Diem Heat", "Điểm", "Diem"], "")
            if "KHỎE" in heat_text or "KHOE" in heat_text:
                score += 15
                reasons.append("Heat khỏe")
            if "ỔN NHƯNG" in heat_text or "ON NHUNG" in heat_text:
                score += 7
                reasons.append("Heat ổn nhưng không mua đuổi")
            if "QUÁ NÓNG" in heat_text or "QUA NONG" in heat_text:
                score -= 15
                reasons.append("Quá nóng")
            if "GIẢM TỶ TRỌNG" in heat_text or "GIAM TY TRONG" in heat_text:
                score -= 8
                reasons.append("Heat giảm tỷ trọng")

        bottom_label = ""
        bottom_score = ""
        if botr is not None:
            bottom_text = " ".join([str(x) for x in botr.values]).upper()
            bottom_label = str(val(botr, ["Phân loại Bottom V15.1", "Phan loai Bottom V15.1"], ""))
            bottom_score = val(botr, ["Điểm Bottom V15.1", "Diem Bottom V15.1"], "")
            if "ĐÁY CHẤT LƯỢNG" in bottom_text or "DAY CHAT LUONG" in bottom_text:
                score += 18
                reasons.append("Đáy chất lượng")
            elif "HỒI KỸ THUẬT" in bottom_text or "HOI KY THUAT" in bottom_text:
                score += 8
                reasons.append("Hồi kỹ thuật")
            if "BULL TRAP" in bottom_text:
                score -= 18
                reasons.append("Bull trap")
            if "DAO RƠI" in bottom_text or "DAO ROI" in bottom_text:
                score -= 25
                reasons.append("Dao rơi")

        wf_m_label = ""
        wf_m_pct = ""
        if wfm is not None:
            wf_m_label = str(val(wfm, ["Độ ổn định mẫu", "Do on dinh mau"], ""))
            wf_m_pct = val(wfm, ["Tỷ lệ đoạn dương %", "Ty le doan duong %"], "")
            add = wf_score(wf_m_label)
            score += add if strategy == "MOMENTUM" else add * 0.4
            if wf_m_label:
                reasons.append(f"WF momentum {wf_m_label}")

        wf_b_label = ""
        wf_b_pct = ""
        if wfb is not None:
            wf_b_label = str(val(wfb, ["Độ ổn định mẫu", "Do on dinh mau"], ""))
            wf_b_pct = val(wfb, ["Tỷ lệ đoạn dương %", "Ty le doan duong %"], "")
            add = wf_score(wf_b_label)
            score += add if strategy == "BOTTOM" else add * 0.4
            if wf_b_label:
                reasons.append(f"WF bottom {wf_b_label}")

        if "ỔN ĐỊNH" in wf_m_label and "ỔN ĐỊNH" in wf_b_label:
            score += 5
            reasons.append("Hai WF cùng ổn định")

        score = max(0, min(100, score))
        decision, decision_reason = final_label(score, risk, reasons)

        rows.append({
            "Mã": ma,
            "Giá": close,
            "Strategy V16": strategy,
            "Action gốc": action,
            "Risk": risk,
            "Điểm V16": round(score, 2),
            "Quyết định V16": decision,
            "Lý do quyết định": decision_reason,
            "Heat label": heat_label,
            "Heat score": heat_score,
            "Bottom label": bottom_label,
            "Bottom score": bottom_score,
            "WF Momentum": wf_m_label,
            "WF Momentum đoạn dương %": wf_m_pct,
            "WF Bottom": wf_b_label,
            "WF Bottom đoạn dương %": wf_b_pct,
            "Lý do tổng hợp": " | ".join(reasons),
        })

    out = pd.DataFrame(rows)
    rank = {"🟢 ƯU TIÊN CAO": 1, "🟡 THEO DÕI": 2, "🟠 CHỜ ĐIỂM ĐẸP": 3, "❌ LOẠI": 4}
    out["__rank"] = out["Quyết định V16"].map(rank).fillna(9)
    out["__score"] = pd.to_numeric(out["Điểm V16"], errors="coerce")
    out = out.sort_values(["__rank", "__score"], ascending=[True, False]).drop(columns=["__rank", "__score"])
    return out.reset_index(drop=True), source


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


def report_text(df, source):
    lines = [
        "✅ <b>V16 FINAL DECISION HOÀN TẤT</b>",
        "",
        f"Nguồn nền: <b>{source}</b>",
        f"Số mã tổng hợp: <b>{len(df)}</b>",
        "",
        "<b>TOP QUYẾT ĐỊNH V16</b>",
    ]
    top = df[df["Quyết định V16"].astype(str).str.contains("ƯU TIÊN|THEO DÕI|CHỜ", na=False)].head(10)
    if top.empty:
        top = df.head(10)
    for _, r in top.iterrows():
        lines.append("")
        lines.append(f"🔹 <b>{r.get('Mã','')}</b> | {r.get('Quyết định V16','')} | Điểm {fmt(r.get('Điểm V16'))}")
        lines.append(f"Strategy: {r.get('Strategy V16','')} | Risk: {r.get('Risk','')} | Action gốc: {r.get('Action gốc','')}")
        lines.append(f"WF: Momentum {r.get('WF Momentum','')} | Bottom {r.get('WF Bottom','')}")
        lines.append(f"Lý do: {r.get('Lý do quyết định','')}")
    return "\n".join(lines)


def send_telegram(text):
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("WARN: thiếu Telegram, bỏ qua V16", flush=True)
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = requests.post(url, data={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=20)
        print("TELEGRAM V16 STATUS:", r.status_code, r.text[:160], flush=True)
    except Exception as e:
        print("WARN Telegram V16:", repr(e), flush=True)


def main():
    print("V16 FINAL DECISION ENGINE STARTED", flush=True)
    df, source = build()
    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    high = df[df["Quyết định V16"].astype(str).str.contains("ƯU TIÊN", na=False)] if "Quyết định V16" in df.columns else pd.DataFrame()
    watch = df[df["Quyết định V16"].astype(str).str.contains("THEO DÕI|CHỜ", na=False)] if "Quyết định V16" in df.columns else pd.DataFrame()
    reject = df[df["Quyết định V16"].astype(str).str.contains("LOẠI", na=False)] if "Quyết định V16" in df.columns else pd.DataFrame()

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>V16 Final Decision</title>{html_style()}</head>
<body>
<h2>V16 - FINAL DECISION ENGINE</h2>
<div class="note"><b>Generated:</b> {now_str()}<br><b>Nguồn nền:</b> {source}<br>
<b>Ý nghĩa:</b> Tổng hợp Dashboard + V14.3 + V15.1 + V15.2 Momentum/Bottom WalkForward thành quyết định cuối.</div>
<div class="card"><h3>1. TOP ƯU TIÊN CAO</h3>{high.to_html(index=False, escape=True) if not high.empty else "<p>Không có mã ưu tiên cao.</p>"}</div>
<div class="card"><h3>2. THEO DÕI / CHỜ ĐIỂM ĐẸP</h3>{watch.to_html(index=False, escape=True) if not watch.empty else "<p>Không có mã theo dõi.</p>"}</div>
<div class="card"><h3>3. LOẠI / KHÔNG ƯU TIÊN</h3>{reject.to_html(index=False, escape=True) if not reject.empty else "<p>Không có mã loại.</p>"}</div>
<div class="card"><h3>4. BẢNG ĐẦY ĐỦ V16</h3>{df.to_html(index=False, escape=True)}</div>
</body></html>"""
    Path(OUT_HTML).write_text(html, encoding="utf-8")

    rep = report_text(df, source)
    Path(OUT_TXT).write_text(rep, encoding="utf-8")
    print(rep.replace("<b>", "").replace("</b>", ""), flush=True)
    print(f"OK: wrote {OUT_CSV}", flush=True)
    print(f"OK: wrote {OUT_HTML}", flush=True)
    print(f"OK: wrote {OUT_TXT}", flush=True)
    send_telegram(rep)


if __name__ == "__main__":
    main()
