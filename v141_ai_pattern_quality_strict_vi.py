# -*- coding: utf-8 -*-
"""
v141_ai_pattern_quality_strict_vi.py

V14.1 - LỚP CHẤM CHẤT LƯỢNG AI / PATTERN NGHIÊM NGẶT

Mục tiêu:
- Xếp hạng chất lượng các mã đã lọc xong.
- Không tìm tín hiệu mới.
- Không sửa tín hiệu gốc.
- Không sửa dashboard chính.
- Không sửa ai_risk_filtered.csv.
- Không ảnh hưởng Render realtime.

Khác V14:
- Không cho A+ nếu mẫu lịch sử/OOS/regime quá ít.
- Tách điểm cộng và điểm trừ rõ ràng.
- Trừ mạnh nếu T+5 âm, RSI quá nóng, ATR cao, volume yếu, xa MA20.
- Tạo lý do khác biệt để tránh mã nào cũng giống nhau.

Input:
- ai_risk_filtered.csv
- fallback all_signal_results.csv

Output:
- v141_ai_pattern_quality.csv
- v141_top_quality_picks.csv
- v141_ai_pattern_quality.html
- v141_ai_pattern_quality_report.txt
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

OUT_FULL = os.getenv("V141_QUALITY_PATH", "v141_ai_pattern_quality.csv")
OUT_TOP = os.getenv("V141_TOP_PATH", "v141_top_quality_picks.csv")
OUT_HTML = os.getenv("V141_HTML_PATH", "v141_ai_pattern_quality.html")
OUT_TXT = os.getenv("V141_TXT_PATH", "v141_ai_pattern_quality_report.txt")

TOP_LIMIT = int(os.getenv("V141_TOP_LIMIT", "15"))


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


def fmt_num(x, digits=2) -> str:
    try:
        if pd.isna(x):
            return ""
        return f"{float(x):.{digits}f}"
    except Exception:
        return str(x)


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


def quality_grade(score: float, cap_reason: str = "") -> str:
    if score >= 90 and not cap_reason:
        return "A+ RẤT MẠNH"
    if score >= 80:
        return "A MẠNH"
    if score >= 70:
        return "B+ TỐT"
    if score >= 60:
        return "B THEO DÕI"
    if score >= 50:
        return "C YẾU / CHỈ QUAN SÁT"
    return "D BỎ QUA"


def signal_tier(score: float) -> str:
    if score >= 90:
        return "ƯU TIÊN CAO"
    if score >= 80:
        return "CÓ THỂ ƯU TIÊN"
    if score >= 70:
        return "THEO DÕI TỐT"
    if score >= 60:
        return "THEO DÕI THẬN TRỌNG"
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
        "momentum_score": find_col(df, ["Momentum Score"]),
        "bottom_score": find_col(df, ["Bottom Score"]),
    }


def add_bonus(value: float, reason: str, bonuses: list, amount: float):
    bonuses.append((reason, amount))
    return value + amount


def add_penalty(value: float, reason: str, penalties: list, amount: float):
    penalties.append((reason, amount))
    return value - abs(amount)


def score_one_row(row: pd.Series, cols: dict) -> dict:
    base = 50.0
    bonuses = []
    penalties = []
    notes = []

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
    momentum_score = to_num(row.get(cols["momentum_score"])) if cols.get("momentum_score") else np.nan
    bottom_score = to_num(row.get(cols["bottom_score"])) if cols.get("bottom_score") else np.nan

    score = base

    # Action
    if "BUY NOW" in combined_action or "MUA" in combined_action:
        score = add_bonus(score, "Tín hiệu mua rõ", bonuses, 10)
    elif "WATCHLIST" in combined_action or "THEO DÕI" in combined_action or "THEO DOI" in combined_action:
        score = add_bonus(score, "Tín hiệu theo dõi", bonuses, 4)
    elif "WAIT" in combined_action or "CHỜ" in combined_action or "CHO" in combined_action:
        score = add_penalty(score, "Tín hiệu còn chờ", penalties, 6)
    elif "SKIP" in combined_action or "BỎ QUA" in combined_action or "BO QUA" in combined_action:
        score = add_penalty(score, "Tín hiệu bị loại", penalties, 25)

    # Risk
    if "PASS" in risk:
        score = add_bonus(score, "Risk PASS", bonuses, 12)
    elif "FAIL" in risk:
        score = add_penalty(score, "Risk FAIL", penalties, 35)

    # Core score and AI
    if not np.isnan(core_score):
        if core_score >= 85:
            score = add_bonus(score, f"Score gốc mạnh {core_score:.0f}", bonuses, 8)
        elif core_score >= 75:
            score = add_bonus(score, f"Score gốc tốt {core_score:.0f}", bonuses, 5)
        elif core_score < 60:
            score = add_penalty(score, f"Score gốc yếu {core_score:.0f}", penalties, 6)

    if not np.isnan(ai):
        if ai >= 90:
            score = add_bonus(score, f"AI rất cao {ai:.0f}", bonuses, 8)
        elif ai >= 75:
            score = add_bonus(score, f"AI tốt {ai:.0f}", bonuses, 5)
        elif ai < 55:
            score = add_penalty(score, f"AI thấp {ai:.0f}", penalties, 6)

    # Historical edge
    if not np.isnan(win):
        if win >= 60:
            score = add_bonus(score, f"Win lịch sử tốt {win:.1f}%", bonuses, 5)
        elif 52 <= win < 60:
            score = add_bonus(score, f"Win lịch sử hơi tốt {win:.1f}%", bonuses, 2)
        elif win < 48:
            score = add_penalty(score, f"Win lịch sử yếu {win:.1f}%", penalties, 5)

    if not np.isnan(oos_win):
        if oos_win >= 58:
            score = add_bonus(score, f"OOS tốt {oos_win:.1f}%", bonuses, 6)
        elif oos_win < 48:
            score = add_penalty(score, f"OOS yếu {oos_win:.1f}%", penalties, 7)

    if not np.isnan(regime_win):
        if regime_win >= 58:
            score = add_bonus(score, f"Regime phù hợp {regime_win:.1f}%", bonuses, 5)
        elif regime_win < 48:
            score = add_penalty(score, f"Regime yếu {regime_win:.1f}%", penalties, 6)

    # Sample quality - stricter
    sample_weak_count = 0
    if not np.isnan(hist_samples):
        if hist_samples >= 50:
            score = add_bonus(score, "Mẫu lịch sử mạnh", bonuses, 4)
        elif hist_samples >= 20:
            score = add_bonus(score, "Mẫu lịch sử đủ dùng", bonuses, 2)
        elif hist_samples < 10:
            sample_weak_count += 1
            score = add_penalty(score, "Mẫu lịch sử ít", penalties, 8)

    if not np.isnan(oos_samples):
        if oos_samples >= 30:
            score = add_bonus(score, "Mẫu OOS tốt", bonuses, 4)
        elif oos_samples < 10:
            sample_weak_count += 1
            score = add_penalty(score, "Mẫu OOS ít", penalties, 7)

    if not np.isnan(regime_samples):
        if regime_samples >= 20:
            score = add_bonus(score, "Mẫu regime ổn", bonuses, 3)
        elif regime_samples < 8:
            sample_weak_count += 1
            score = add_penalty(score, "Mẫu regime ít", penalties, 6)

    # Technical differentiators
    if not np.isnan(rs20):
        if rs20 >= 25:
            score = add_bonus(score, f"RS20 rất khỏe {rs20:.1f}", bonuses, 10)
        elif rs20 >= 15:
            score = add_bonus(score, f"RS20 khỏe {rs20:.1f}", bonuses, 7)
        elif rs20 >= 5:
            score = add_bonus(score, f"RS20 dương tốt {rs20:.1f}", bonuses, 4)
        elif rs20 >= 0:
            score = add_bonus(score, f"RS20 dương nhẹ {rs20:.1f}", bonuses, 1)
        elif rs20 < -8:
            score = add_penalty(score, f"RS20 yếu {rs20:.1f}", penalties, 10)

    if not np.isnan(rsi):
        if 52 <= rsi <= 67:
            score = add_bonus(score, f"RSI vùng đẹp {rsi:.1f}", bonuses, 7)
        elif 67 < rsi <= 75:
            score = add_bonus(score, f"RSI hơi cao {rsi:.1f}", bonuses, 1)
        elif 75 < rsi <= 82:
            score = add_penalty(score, f"RSI nóng {rsi:.1f}", penalties, 7)
        elif rsi > 82:
            score = add_penalty(score, f"RSI quá nóng {rsi:.1f}", penalties, 12)
        elif rsi < 40:
            score = add_penalty(score, f"RSI yếu {rsi:.1f}", penalties, 5)

    if not np.isnan(vol):
        if vol >= 2.0:
            score = add_bonus(score, f"Volume rất mạnh {vol:.2f}", bonuses, 7)
        elif vol >= 1.3:
            score = add_bonus(score, f"Volume mạnh {vol:.2f}", bonuses, 5)
        elif vol >= 1.0:
            score = add_bonus(score, f"Volume ổn {vol:.2f}", bonuses, 2)
        elif vol < 0.7:
            score = add_penalty(score, f"Volume yếu {vol:.2f}", penalties, 8)

    if not np.isnan(adx):
        if adx >= 25:
            score = add_bonus(score, f"ADX xu hướng tốt {adx:.1f}", bonuses, 4)
        elif adx < 15:
            score = add_penalty(score, f"ADX yếu {adx:.1f}", penalties, 3)

    if not np.isnan(atr):
        if atr <= 5:
            score = add_bonus(score, f"ATR an toàn {atr:.1f}", bonuses, 5)
        elif 5 < atr <= 8:
            score = add_bonus(score, f"ATR chấp nhận {atr:.1f}", bonuses, 2)
        elif 8 < atr <= 10:
            score = add_penalty(score, f"ATR hơi cao {atr:.1f}", penalties, 4)
        elif atr > 10:
            score = add_penalty(score, f"ATR rủi ro cao {atr:.1f}", penalties, 10)

    if not np.isnan(dist_ma20):
        if 0 <= dist_ma20 <= 6:
            score = add_bonus(score, f"Khoảng cách MA20 đẹp {dist_ma20:.1f}%", bonuses, 5)
        elif 6 < dist_ma20 <= 12:
            score = add_bonus(score, f"Khoảng cách MA20 chấp nhận {dist_ma20:.1f}%", bonuses, 2)
        elif dist_ma20 > 15:
            score = add_penalty(score, f"Xa MA20 {dist_ma20:.1f}%", penalties, 8)

    # T+2 / T+5 stricter
    if not np.isnan(t2):
        if t2 >= 0.5:
            score = add_bonus(score, f"T+2 tốt {t2:.2f}%", bonuses, 5)
        elif 0 < t2 < 0.5:
            score = add_bonus(score, f"T+2 dương nhẹ {t2:.2f}%", bonuses, 2)
        elif t2 < 0:
            score = add_penalty(score, f"T+2 âm {t2:.2f}%", penalties, 7)

    if not np.isnan(t5):
        if t5 >= 1.0:
            score = add_bonus(score, f"T+5 tốt {t5:.2f}%", bonuses, 7)
        elif 0 < t5 < 1.0:
            score = add_bonus(score, f"T+5 dương nhẹ {t5:.2f}%", bonuses, 3)
        elif t5 < 0:
            score = add_penalty(score, f"T+5 âm {t5:.2f}%", penalties, 12)

    # Strategy internal score
    if not np.isnan(momentum_score) and momentum_score >= 80:
        score = add_bonus(score, f"Momentum mạnh {momentum_score:.0f}", bonuses, 3)
    if not np.isnan(bottom_score) and bottom_score >= 75:
        score = add_bonus(score, f"Bottom mạnh {bottom_score:.0f}", bonuses, 3)

    # Cap rules: prevent fake A+
    cap_reason = ""
    cap = 100.0

    if sample_weak_count >= 2:
        cap = min(cap, 82.0)
        cap_reason = "Bị chặn A+ vì mẫu lịch sử/OOS/regime còn ít"
    elif sample_weak_count == 1:
        cap = min(cap, 88.0)
        cap_reason = "Bị giới hạn điểm vì có một nhóm mẫu còn ít"

    if not np.isnan(t5) and t5 < 0:
        cap = min(cap, 78.0)
        cap_reason = "Bị chặn điểm cao vì T+5 âm"

    if "FAIL" in risk:
        cap = min(cap, 55.0)
        cap_reason = "Bị chặn điểm vì Risk FAIL"

    if not np.isnan(rsi) and rsi > 82:
        cap = min(cap, 80.0)
        cap_reason = "Bị chặn điểm vì RSI quá nóng"

    if not np.isnan(atr) and atr > 10:
        cap = min(cap, 80.0)
        cap_reason = "Bị chặn điểm vì ATR cao"

    score_before_cap = score
    score = min(score, cap)
    score = float(max(min(score, 100), 0))

    if cap_reason:
        notes.append(cap_reason)

    bonus_text = " | ".join([f"+{v:g} {k}" for k, v in bonuses[:8]])
    penalty_text = " | ".join([f"-{v:g} {k}" for k, v in penalties[:8]])
    different_text = " | ".join(notes + [x[0] for x in penalties[:5]] + [x[0] for x in bonuses[:5]])

    return {
        "score": score,
        "score_before_cap": round(score_before_cap, 2),
        "bonus_total": round(sum(v for _, v in bonuses), 2),
        "penalty_total": round(sum(v for _, v in penalties), 2),
        "bonus_text": bonus_text,
        "penalty_text": penalty_text,
        "different_text": different_text,
        "cap_reason": cap_reason,
    }


def build_v141_quality(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame([{"Trạng thái": "Không có dữ liệu để chấm V14.1"}])

    data = df.copy()
    cols = get_columns(data)
    rows = []

    for _, r in data.iterrows():
        q = score_one_row(r, cols)
        grade = quality_grade(q["score"], q["cap_reason"])

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
            "ATR %": r.get(cols["atr"], "") if cols.get("atr") else "",
            "Dist MA20 %": r.get(cols["dist_ma20"], "") if cols.get("dist_ma20") else "",
            "Lợi TB T+2 %": r.get(cols["t2"], "") if cols.get("t2") else "",
            "Lợi TB T+5 %": r.get(cols["t5"], "") if cols.get("t5") else "",
            "Điểm V14.1": round(q["score"], 2),
            "Điểm trước chặn": q["score_before_cap"],
            "Tổng điểm cộng": q["bonus_total"],
            "Tổng điểm trừ": q["penalty_total"],
            "Hạng V14.1": grade,
            "Nhóm ưu tiên V14.1": signal_tier(q["score"]),
            "Lý do cộng điểm": q["bonus_text"],
            "Lý do trừ điểm": q["penalty_text"],
            "Lý do khác biệt": q["different_text"],
            "Lý do chặn điểm": q["cap_reason"],
        })

    out = pd.DataFrame(rows)
    if "Điểm V14.1" in out.columns:
        out = out.sort_values(
            ["Điểm V14.1", "Tổng điểm trừ", "Tổng điểm cộng"],
            ascending=[False, True, False],
            na_position="last"
        ).reset_index(drop=True)

    return out


def html_style() -> str:
    return """
<style>
body { font-family: Arial, sans-serif; background: #0f172a; color: #e5e7eb; padding: 18px; }
h2, h3 { color: #ffffff; }
.note { background: #111827; border: 1px solid #334155; border-radius: 10px; padding: 12px; margin: 12px 0; }
table { border-collapse: collapse; width: 100%; font-size: 12px; background: #111827; }
th { background: #1f2937; color: #ffffff; position: sticky; top: 0; }
td, th { border: 1px solid #334155; padding: 7px; white-space: nowrap; vertical-align: top; }
tr:nth-child(even) { background: #0b1220; }
</style>
"""


def build_html(full_df: pd.DataFrame, top_df: pd.DataFrame, source_name: str, data_date: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>V14.1 Strict Quality Ranking</title>
{html_style()}
</head>
<body>
<h2>V14.1 - AI / PATTERN QUALITY RANKING NGHIÊM NGẶT</h2>
<div class="note">
<b>Generated:</b> {now_str()}<br>
<b>Nguồn dữ liệu:</b> {source_name}<br>
<b>Data date:</b> {data_date or "N/A"}<br>
<b>Ý nghĩa:</b> Chấm chất lượng mã đã được lọc sẵn. Không thay đổi tín hiệu gốc. Không cho A+ nếu mẫu ít/T+5 âm/risk xấu.
</div>
<h3>TOP QUALITY PICKS V14.1</h3>
{top_df.to_html(index=False, escape=True)}
<h3>BẢNG ĐẦY ĐỦ V14.1</h3>
{full_df.to_html(index=False, escape=True)}
</body>
</html>
"""


def send_telegram(text: str) -> bool:
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("WARN: thiếu TELEGRAM_TOKEN/TELEGRAM_CHAT_ID, bỏ qua gửi V14.1", flush=True)
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(
            url,
            data={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=20,
        )
        print("TELEGRAM V14.1 STATUS:", resp.status_code, resp.text[:200], flush=True)
        return resp.status_code == 200
    except Exception as e:
        print("WARN: gửi Telegram V14.1 lỗi:", repr(e), flush=True)
        return False


def build_report(top_df: pd.DataFrame, source_name: str, data_date: str) -> str:
    lines = [
        "✅ <b>V14.1 QUALITY RANKING HOÀN TẤT</b>",
        "",
        f"Nguồn: <b>{source_name}</b>",
        f"Data date: <b>{data_date or 'N/A'}</b>",
        f"Số mã top: <b>{len(top_df)}</b>",
        "",
        "<b>TOP QUALITY PICKS V14.1</b>",
    ]

    if top_df is None or top_df.empty:
        lines.append("Không có mã phù hợp.")
        return "\n".join(lines)

    for _, r in top_df.head(8).iterrows():
        ma = str(r.get("Mã", ""))
        grade = str(r.get("Hạng V14.1", ""))
        q = fmt_num(r.get("Điểm V14.1", ""))
        action = str(r.get("Hành động", ""))
        risk = str(r.get("Risk Status", ""))
        penalty = str(r.get("Lý do trừ điểm", ""))
        cap = str(r.get("Lý do chặn điểm", ""))
        diff = str(r.get("Lý do khác biệt", ""))

        lines.append(f"🔹 <b>{ma}</b> | {grade} | Điểm {q} | {action} | Risk {risk}")
        if penalty and penalty.lower() != "nan":
            lines.append(f"   Trừ điểm: {penalty[:140]}...")
        elif cap and cap.lower() != "nan":
            lines.append(f"   Chặn điểm: {cap}")
        elif diff and diff.lower() != "nan":
            lines.append(f"   Lý do: {diff[:140]}...")

    return "\n".join(lines)


def main():
    print("V14.1 STRICT QUALITY STARTED", flush=True)

    source_name = AI_RISK_PATH
    df = safe_read_csv(AI_RISK_PATH)

    if df.empty:
        source_name = ALL_RESULT_PATH
        df = safe_read_csv(ALL_RESULT_PATH)

    if df.empty:
        out = pd.DataFrame([{"Trạng thái": "Không có dữ liệu đầu vào cho V14.1"}])
        out.to_csv(OUT_FULL, index=False, encoding="utf-8-sig")
        out.to_csv(OUT_TOP, index=False, encoding="utf-8-sig")
        Path(OUT_TXT).write_text("Không có dữ liệu đầu vào cho V14.1", encoding="utf-8")
        print("WARN: không có dữ liệu đầu vào cho V14.1", flush=True)
        return

    data_date = latest_date(df)
    full = build_v141_quality(df)

    if "Điểm V14.1" in full.columns:
        top = full[full["Điểm V14.1"].apply(lambda x: to_num(x, 0)) >= 60].copy()
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
