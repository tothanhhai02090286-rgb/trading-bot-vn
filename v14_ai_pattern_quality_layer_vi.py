# -*- coding: utf-8 -*-
"""
v14_ai_pattern_quality_layer_vi.py

V14 - LỚP CHẤM CHẤT LƯỢNG AI / PATTERN

Mục tiêu:
- Chấm điểm chất lượng các mã đã được hệ thống lọc sẵn.
- Không tìm tín hiệu mới.
- Không sửa tín hiệu gốc.
- Không sửa dashboard chính.
- Không sửa ai_risk_filtered.csv.
- Không ảnh hưởng Render realtime bot.

Input ưu tiên:
1. ai_risk_filtered.csv
2. nếu rỗng thì dùng all_signal_results.csv

Output:
- v14_ai_pattern_quality.csv
- v14_top_quality_picks.csv
- v14_ai_pattern_quality.html
- v14_ai_pattern_quality_report.txt
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests


AI_RISK_PATH = os.getenv("AI_RISK_PATH", "ai_risk_filtered.csv")
ALL_RESULT_PATH = os.getenv("ALL_RESULT_PATH", "all_signal_results.csv")

OUT_FULL = os.getenv("V14_QUALITY_PATH", "v14_ai_pattern_quality.csv")
OUT_TOP = os.getenv("V14_TOP_PATH", "v14_top_quality_picks.csv")
OUT_HTML = os.getenv("V14_HTML_PATH", "v14_ai_pattern_quality.html")
OUT_TXT = os.getenv("V14_TXT_PATH", "v14_ai_pattern_quality_report.txt")

TOP_LIMIT = int(os.getenv("V14_TOP_LIMIT", "15"))


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
    for name in names:
        key = str(name).strip().lower()
        if key in lower:
            return lower[key]
    for c in df.columns:
        text = str(c).strip().lower()
        for name in names:
            if str(name).strip().lower() in text:
                return c
    return None


def to_num(x, default=np.nan) -> float:
    try:
        if pd.isna(x):
            return default
        text = str(x).replace("%", "").replace(",", ".").strip()
        if text == "":
            return default
        return float(text)
    except Exception:
        return default


def upper_text(x) -> str:
    return str(x).upper().strip()


def latest_date(df: pd.DataFrame) -> str:
    col = find_col(df, ["Ngay", "Ngày", "Date", "time", "date"])
    if col is None:
        return ""
    try:
        s = pd.to_datetime(df[col], errors="coerce")
        if s.notna().any():
            return str(s.max().date())
    except Exception:
        pass
    try:
        vals = df[col].dropna().astype(str)
        return vals.max() if len(vals) else ""
    except Exception:
        return ""


def fmt_num(x, digits=2) -> str:
    try:
        if pd.isna(x):
            return ""
        return f"{float(x):.{digits}f}"
    except Exception:
        return str(x)


def quality_grade(score: float) -> str:
    if score >= 85:
        return "A+ RẤT MẠNH"
    if score >= 75:
        return "A MẠNH"
    if score >= 65:
        return "B THEO DÕI TỐT"
    if score >= 55:
        return "C TRUNG BÌNH"
    return "D YẾU / BỎ QUA"


def signal_tier(score: float) -> str:
    if score >= 85:
        return "ƯU TIÊN CAO"
    if score >= 75:
        return "CÓ THỂ ƯU TIÊN"
    if score >= 65:
        return "THEO DÕI TỐT"
    if score >= 55:
        return "CHỈ THEO DÕI"
    return "KHÔNG ƯU TIÊN"


def get_columns(df: pd.DataFrame) -> dict:
    return {
        "ma": find_col(df, ["Mã", "Ma", "Symbol", "Ticker"]),
        "ngay": find_col(df, ["Ngày", "Ngay", "Date"]),
        "gia": find_col(df, ["Giá", "Gia", "Close", "close"]),
        "action": find_col(df, ["Hành động hiện tại", "Hanh dong hien tai", "Action", "AI Action", "Final Action"]),
        "decision": find_col(df, ["QUYẾT ĐỊNH TỰ ĐỘNG", "Quyet dinh tu dong", "Final Decision", "Final Action"]),
        "strategy": find_col(df, ["Strategy", "Chiến lược", "Chien luoc"]),
        "risk": find_col(df, ["Risk Status", "Risk", "Rủi ro", "Rui ro"]),
        "score": find_col(df, ["Score"]),
        "ai": find_col(df, ["AI Confidence", "AI"]),
        "win": find_col(df, ["Win Probability", "Tỷ lệ thắng", "Ty le thang"]),
        "oos_win": find_col(df, ["OOS Win Probability", "OOS Win"]),
        "regime_win": find_col(df, ["Regime Win Probability", "Regime Win"]),
        "hist_samples": find_col(df, ["History Samples", "Số mẫu lịch sử", "So mau lich su"]),
        "oos_samples": find_col(df, ["OOS Samples", "Số mẫu OOS", "So mau OOS"]),
        "regime_samples": find_col(df, ["Regime Samples", "Số mẫu regime", "So mau regime"]),
        "rsi": find_col(df, ["RSI"]),
        "rs20": find_col(df, ["RS20"]),
        "vol": find_col(df, ["Volume Ratio", "Vol Ratio", "volume_ratio"]),
        "adx": find_col(df, ["ADX"]),
        "atr": find_col(df, ["ATR %", "ATR"]),
        "dist_ma20": find_col(df, ["Dist MA20 %", "Dist MA20"]),
        "t2": find_col(df, ["Lợi TB T+2 %", "Loi TB T+2 %", "Lợi T+2 %", "Loi T+2 %"]),
        "t5": find_col(df, ["Lợi TB T+5 %", "Loi TB T+5 %", "Lợi T+5 %", "Loi T+5 %"]),
    }


def score_one_row(row: pd.Series, cols: dict) -> tuple[float, list[str]]:
    score = 50.0
    reasons = []

    action = upper_text(row.get(cols["action"], "")) if cols.get("action") else ""
    decision = upper_text(row.get(cols["decision"], "")) if cols.get("decision") else ""
    strategy = upper_text(row.get(cols["strategy"], "")) if cols.get("strategy") else ""
    risk = upper_text(row.get(cols["risk"], "")) if cols.get("risk") else ""
    combined_action = action + " " + decision

    core_score = to_num(row.get(cols["score"])) if cols.get("score") else np.nan
    ai = to_num(row.get(cols["ai"])) if cols.get("ai") else np.nan
    win = to_num(row.get(cols["win"])) if cols.get("win") else np.nan
    oos_win = to_num(row.get(cols["oos_win"])) if cols.get("oos_win") else np.nan
    regime_win = to_num(row.get(cols["regime_win"])) if cols.get("regime_win") else np.nan
    hist_samples = to_num(row.get(cols["hist_samples"])) if cols.get("hist_samples") else np.nan
    oos_samples = to_num(row.get(cols["oos_samples"])) if cols.get("oos_samples") else np.nan
    regime_samples = to_num(row.get(cols["regime_samples"])) if cols.get("regime_samples") else np.nan
    rsi = to_num(row.get(cols["rsi"])) if cols.get("rsi") else np.nan
    rs20 = to_num(row.get(cols["rs20"])) if cols.get("rs20") else np.nan
    vol = to_num(row.get(cols["vol"])) if cols.get("vol") else np.nan
    adx = to_num(row.get(cols["adx"])) if cols.get("adx") else np.nan
    atr = to_num(row.get(cols["atr"])) if cols.get("atr") else np.nan
    dist_ma20 = to_num(row.get(cols["dist_ma20"])) if cols.get("dist_ma20") else np.nan
    t2 = to_num(row.get(cols["t2"])) if cols.get("t2") else np.nan
    t5 = to_num(row.get(cols["t5"])) if cols.get("t5") else np.nan

    if "BUY NOW" in combined_action or "MUA" in combined_action:
        score += 12
        reasons.append("Tín hiệu mua rõ")
    elif "WATCHLIST" in combined_action or "THEO DÕI" in combined_action or "THEO DOI" in combined_action:
        score += 6
        reasons.append("Tín hiệu theo dõi tốt")
    elif "WAIT" in combined_action or "CHỜ" in combined_action or "CHO" in combined_action:
        score -= 4
        reasons.append("Tín hiệu còn chờ")
    elif "SKIP" in combined_action or "BỎ QUA" in combined_action or "BO QUA" in combined_action:
        score -= 18
        reasons.append("Tín hiệu bị loại")

    if "PASS" in risk:
        score += 12
        reasons.append("Risk PASS")
    elif "FAIL" in risk:
        score -= 30
        reasons.append("Risk FAIL")

    if not np.isnan(core_score):
        score += max(min((core_score - 60) * 0.25, 10), -10)
        reasons.append(f"Score {core_score:.0f}")

    if not np.isnan(ai):
        score += max(min((ai - 60) * 0.18, 10), -10)
        reasons.append(f"AI {ai:.0f}")

    if not np.isnan(win):
        score += max(min((win - 50) * 0.20, 8), -8)
        reasons.append(f"Win {win:.1f}%")

    if not np.isnan(oos_win):
        score += max(min((oos_win - 50) * 0.22, 9), -9)
        reasons.append(f"OOS {oos_win:.1f}%")

    if not np.isnan(regime_win):
        score += max(min((regime_win - 50) * 0.20, 8), -8)
        reasons.append(f"Regime {regime_win:.1f}%")

    if not np.isnan(hist_samples):
        if hist_samples >= 50:
            score += 4
            reasons.append("Mẫu lịch sử mạnh")
        elif hist_samples >= 20:
            score += 2
            reasons.append("Mẫu lịch sử đủ dùng")
        elif hist_samples < 5:
            score -= 4
            reasons.append("Mẫu lịch sử ít")

    if not np.isnan(oos_samples):
        if oos_samples >= 30:
            score += 3
            reasons.append("Mẫu OOS tốt")
        elif oos_samples < 5:
            score -= 3
            reasons.append("Mẫu OOS ít")

    if not np.isnan(regime_samples):
        if regime_samples >= 20:
            score += 2
            reasons.append("Mẫu regime ổn")
        elif regime_samples < 5:
            score -= 2
            reasons.append("Mẫu regime ít")

    if not np.isnan(rs20):
        if rs20 >= 20:
            score += 7
            reasons.append("RS20 rất khỏe")
        elif rs20 >= 10:
            score += 5
            reasons.append("RS20 khỏe")
        elif rs20 >= 0:
            score += 2
            reasons.append("RS20 dương")
        elif rs20 < -10:
            score -= 8
            reasons.append("RS20 yếu")

    if not np.isnan(rsi):
        if 50 <= rsi <= 68:
            score += 5
            reasons.append("RSI vùng đẹp")
        elif 68 < rsi <= 75:
            score += 1
            reasons.append("RSI hơi cao")
        elif rsi > 80:
            score -= 8
            reasons.append("RSI quá nóng")
        elif rsi < 35:
            score -= 4
            reasons.append("RSI yếu")

    if not np.isnan(vol):
        if vol >= 1.5:
            score += 5
            reasons.append("Volume mạnh")
        elif vol >= 1.0:
            score += 2
            reasons.append("Volume ổn")
        elif vol < 0.7:
            score -= 5
            reasons.append("Volume yếu")

    if not np.isnan(adx):
        if adx >= 25:
            score += 3
            reasons.append("ADX có xu hướng")
        elif adx < 15:
            score -= 2
            reasons.append("ADX yếu")

    if not np.isnan(atr):
        if atr <= 6:
            score += 3
            reasons.append("ATR an toàn")
        elif atr > 10:
            score -= 8
            reasons.append("ATR rủi ro cao")

    if not np.isnan(dist_ma20):
        if 0 <= dist_ma20 <= 8:
            score += 3
            reasons.append("Khoảng cách MA20 hợp lý")
        elif dist_ma20 > 15:
            score -= 5
            reasons.append("Xa MA20")

    if not np.isnan(t2):
        if t2 > 0:
            score += 3
            reasons.append("T+2 dương")
        elif t2 < 0:
            score -= 4
            reasons.append("T+2 âm")

    if not np.isnan(t5):
        if t5 > 0:
            score += 4
            reasons.append("T+5 dương")
        elif t5 < 0:
            score -= 6
            reasons.append("T+5 âm")

    if "MOMENTUM" in strategy:
        score += 1
    if "BOTTOM" in strategy:
        score += 1

    score = float(max(min(score, 100), 0))
    return score, reasons


def build_v14_quality(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame([{"Trạng thái": "Không có dữ liệu để chấm V14"}])

    data = df.copy()
    cols = get_columns(data)
    rows = []

    for _, r in data.iterrows():
        q_score, reasons = score_one_row(r, cols)
        rows.append({
            "Ngày": r.get(cols["ngay"], "") if cols.get("ngay") else "",
            "Mã": str(r.get(cols["ma"], "") if cols.get("ma") else "").upper().strip(),
            "Giá": r.get(cols["gia"], "") if cols.get("gia") else "",
            "Hành động": r.get(cols["action"], "") if cols.get("action") else "",
            "Quyết định": r.get(cols["decision"], "") if cols.get("decision") else "",
            "Chiến lược": r.get(cols["strategy"], "") if cols.get("strategy") else "",
            "Risk Status": r.get(cols["risk"], "") if cols.get("risk") else "",
            "Score gốc": r.get(cols["score"], "") if cols.get("score") else "",
            "AI Confidence": r.get(cols["ai"], "") if cols.get("ai") else "",
            "RS20": r.get(cols["rs20"], "") if cols.get("rs20") else "",
            "RSI": r.get(cols["rsi"], "") if cols.get("rsi") else "",
            "Volume Ratio": r.get(cols["vol"], "") if cols.get("vol") else "",
            "Lợi TB T+2 %": r.get(cols["t2"], "") if cols.get("t2") else "",
            "Lợi TB T+5 %": r.get(cols["t5"], "") if cols.get("t5") else "",
            "Điểm chất lượng V14": round(q_score, 2),
            "Hạng chất lượng V14": quality_grade(q_score),
            "Nhóm ưu tiên V14": signal_tier(q_score),
            "Lý do V14": " | ".join(reasons[:10]),
        })

    out = pd.DataFrame(rows)
    if "Điểm chất lượng V14" in out.columns:
        out = out.sort_values("Điểm chất lượng V14", ascending=False, na_position="last").reset_index(drop=True)
    return out


def html_style() -> str:
    return """
<style>
body { font-family: Arial, sans-serif; background: #0f172a; color: #e5e7eb; padding: 18px; }
h2, h3 { color: #ffffff; }
.note { background: #111827; border: 1px solid #334155; border-radius: 10px; padding: 12px; margin: 12px 0; }
table { border-collapse: collapse; width: 100%; font-size: 12px; background: #111827; }
th { background: #1f2937; color: #ffffff; position: sticky; top: 0; }
td, th { border: 1px solid #334155; padding: 7px; white-space: nowrap; }
tr:nth-child(even) { background: #0b1220; }
</style>
"""


def build_html(full_df: pd.DataFrame, top_df: pd.DataFrame, source_name: str, data_date: str) -> str:
    top_html = top_df.to_html(index=False, escape=True)
    full_html = full_df.to_html(index=False, escape=True)
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>V14 AI Pattern Quality</title>
{html_style()}
</head>
<body>
<h2>V14 - AI / PATTERN QUALITY LAYER</h2>
<div class="note">
<b>Generated:</b> {now_str()}<br>
<b>Nguồn dữ liệu:</b> {source_name}<br>
<b>Data date:</b> {data_date or "N/A"}<br>
<b>Ý nghĩa:</b> V14 chỉ xếp hạng chất lượng các mã đã được bot lọc sẵn. Không thay đổi tín hiệu gốc.
</div>
<h3>TOP QUALITY PICKS</h3>
{top_html}
<h3>BẢNG ĐẦY ĐỦ V14</h3>
{full_html}
</body>
</html>
"""


def send_telegram(text: str) -> bool:
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("WARN: thiếu TELEGRAM_TOKEN/TELEGRAM_CHAT_ID, bỏ qua gửi V14", flush=True)
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(
            url,
            data={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=20,
        )
        print("TELEGRAM V14 STATUS:", resp.status_code, resp.text[:200], flush=True)
        return resp.status_code == 200
    except Exception as e:
        print("WARN: gửi Telegram V14 lỗi:", repr(e), flush=True)
        return False


def build_report(top_df: pd.DataFrame, source_name: str, data_date: str) -> str:
    lines = [
        "✅ <b>V14 AI/PATTERN QUALITY HOÀN TẤT</b>",
        "",
        f"Nguồn: <b>{source_name}</b>",
        f"Data date: <b>{data_date or 'N/A'}</b>",
        f"Số mã top: <b>{len(top_df)}</b>",
        "",
        "<b>TOP QUALITY PICKS</b>",
    ]

    if top_df is None or top_df.empty:
        lines.append("Không có mã phù hợp.")
        return "\n".join(lines)

    for _, r in top_df.head(8).iterrows():
        ma = str(r.get("Mã", ""))
        grade = str(r.get("Hạng chất lượng V14", ""))
        q = fmt_num(r.get("Điểm chất lượng V14", ""))
        action = str(r.get("Hành động", ""))
        risk = str(r.get("Risk Status", ""))
        reason = str(r.get("Lý do V14", ""))
        if len(reason) > 120:
            reason = reason[:120] + "..."
        lines.append(f"🔹 <b>{ma}</b> | {grade} | Điểm {q} | {action} | Risk {risk}")
        if reason:
            lines.append(f"   {reason}")

    return "\n".join(lines)


def main():
    print("V14 AI/PATTERN QUALITY STARTED", flush=True)

    source_name = AI_RISK_PATH
    df = safe_read_csv(AI_RISK_PATH)

    if df.empty:
        source_name = ALL_RESULT_PATH
        df = safe_read_csv(ALL_RESULT_PATH)

    if df.empty:
        out = pd.DataFrame([{"Trạng thái": "Không có dữ liệu đầu vào cho V14"}])
        out.to_csv(OUT_FULL, index=False, encoding="utf-8-sig")
        out.to_csv(OUT_TOP, index=False, encoding="utf-8-sig")
        Path(OUT_TXT).write_text("Không có dữ liệu đầu vào cho V14", encoding="utf-8")
        print("WARN: không có dữ liệu đầu vào cho V14", flush=True)
        return

    data_date = latest_date(df)
    full = build_v14_quality(df)

    if "Điểm chất lượng V14" in full.columns:
        top = full[full["Điểm chất lượng V14"].apply(lambda x: to_num(x, 0)) >= 65].copy()
        if top.empty:
            top = full.head(TOP_LIMIT).copy()
        else:
            top = top.head(TOP_LIMIT).copy()
    else:
        top = full.head(TOP_LIMIT).copy()

    full.to_csv(OUT_FULL, index=False, encoding="utf-8-sig")
    top.to_csv(OUT_TOP, index=False, encoding="utf-8-sig")
    Path(OUT_HTML).write_text(build_html(full, top, source_name, data_date), encoding="utf-8")

    report = build_report(top, source_name, data_date)
    Path(OUT_TXT).write_text(report, encoding="utf-8")

    print(report.replace("<b>", "").replace("</b>", ""), flush=True)
    print(f"OK: wrote {OUT_FULL}", flush=True)
    print(f"OK: wrote {OUT_TOP}", flush=True)
    print(f"OK: wrote {OUT_HTML}", flush=True)
    print(f"OK: wrote {OUT_TXT}", flush=True)

    send_telegram(report)


if __name__ == "__main__":
    main()
