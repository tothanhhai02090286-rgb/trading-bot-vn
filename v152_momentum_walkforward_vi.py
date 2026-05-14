# -*- coding: utf-8 -*-
"""
v152_momentum_walkforward_vi.py

V15.2 - MOMENTUM WALK-FORWARD VALIDATION
Dùng core chung v152_walkforward_core_vi.py để kiểm định V14.3 Heat Combo / Momentum:

Quy ước:
- Học 2 tháng
- Test tháng thứ 3
- Trượt cửa sổ từng tháng liên tục

Mục tiêu:
- Chống học vẹt cho tín hiệu momentum / continuation.
- Kiểm tra mã đang khỏe có thật sự ổn định qua nhiều giai đoạn lịch sử không.

Input:
- v143_heat_combo.csv nếu có
- nếu không có thì lấy v141_top_quality_picks.csv / ai_risk_filtered.csv / all_signal_results.csv

Dữ liệu lịch sử:
- cache_stock/{MÃ}.csv

Output:
- v152_momentum_walkforward.csv
- v152_momentum_walkforward.html
- v152_momentum_walkforward_report.txt
"""

from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import requests

from v151_bottom_core_vi import find_col, safe_read_csv, load_cache, normalize_cache, calc_rsi
from v152_walkforward_core_vi import (
    WalkForwardConfig,
    run_walkforward_validation,
    default_momentum_match_func,
)


CACHE_DIR = os.getenv("CACHE_DIR", "cache_stock")

INPUT_FILES = [
    os.getenv("V143_HEAT_CSV", "v143_heat_combo.csv"),
    os.getenv("V141_TOP_PATH", "v141_top_quality_picks.csv"),
    os.getenv("AI_RISK_PATH", "ai_risk_filtered.csv"),
    os.getenv("ALL_RESULT_PATH", "all_signal_results.csv"),
]

OUT_CSV = os.getenv("V152_MOM_WF_CSV", "v152_momentum_walkforward.csv")
OUT_HTML = os.getenv("V152_MOM_WF_HTML", "v152_momentum_walkforward.html")
OUT_TXT = os.getenv("V152_MOM_WF_TXT", "v152_momentum_walkforward_report.txt")


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
    """
    Ưu tiên đọc từ v143_heat_combo.csv để giữ đúng danh sách momentum/heat đã chấm.
    Nếu không có thì fallback về output bot.
    """
    for path in INPUT_FILES:
        df = safe_read_csv(path)
        if df.empty:
            continue

        ma_col = find_col(df, ["Mã", "Ma", "Symbol", "Ticker"])
        if ma_col is None:
            continue

        temp = df.copy()
        temp["__ma"] = temp[ma_col].astype(str).str.upper().str.strip()

        # Nếu là file v143 thì ưu tiên các mã có kết luận heat combo.
        status_col = find_col(temp, ["Kết luận Heat Combo", "Ket luan Heat Combo"])
        if status_col:
            temp = temp[temp[status_col].astype(str).str.len() > 0].copy()

        symbols = temp["__ma"].dropna().drop_duplicates().tolist()
        symbols = [s for s in symbols if s and s not in ["NAN", "NO_SIGNAL"]]

        if symbols:
            return symbols, path

    return [], ""


def add_momentum_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ma5"] = out["close"].rolling(5).mean()
    out["ma20"] = out["close"].rolling(20).mean()
    out["rsi"] = calc_rsi(out["close"], 14)

    out["dist_ma20_pct"] = (out["close"] / out["ma20"] - 1) * 100

    out["vol_ma20"] = out["volume"].rolling(20).mean()
    out["volume_ratio"] = out["volume"] / out["vol_ma20"]

    out["ret_5"] = (out["close"] / out["close"].shift(5) - 1) * 100
    out["ret_10"] = (out["close"] / out["close"].shift(10) - 1) * 100
    out["ret_20"] = (out["close"] / out["close"].shift(20) - 1) * 100

    out["ret_t3_pct"] = (out["close"].shift(-3) / out["close"] - 1) * 100
    out["ret_t5_pct"] = (out["close"].shift(-5) / out["close"] - 1) * 100
    out["ret_t10_pct"] = (out["close"].shift(-10) / out["close"] - 1) * 100

    future_min_5 = pd.concat([out["low"].shift(-i) for i in range(1, 6)], axis=1).min(axis=1)
    out["max_dd_t5_pct"] = (future_min_5 / out["close"] - 1) * 100

    return out


def analyze_symbol_walkforward(symbol: str) -> dict:
    raw = load_cache(symbol, cache_dir=CACHE_DIR)
    df = normalize_cache(raw)

    if df.empty or len(df) < 120:
        return {
            "Mã": symbol,
            "Trạng thái dữ liệu": "KHÔNG ĐỦ DỮ LIỆU",
            "Số đoạn test": 0,
            "Độ ổn định mẫu": "KHÔNG ĐỦ DỮ LIỆU",
            "Lý do ổn định": "Không đủ dữ liệu lịch sử để chia 2 tháng học → 1 tháng test.",
        }

    feat = add_momentum_features(df).dropna(subset=["ma20", "rsi", "dist_ma20_pct", "ret_t5_pct"]).copy()

    if feat.empty or len(feat) < 100:
        return {
            "Mã": symbol,
            "Trạng thái dữ liệu": "KHÔNG TÍNH ĐƯỢC",
            "Số đoạn test": 0,
            "Độ ổn định mẫu": "KHÔNG ĐỦ DỮ LIỆU",
            "Lý do ổn định": "Không đủ feature momentum để kiểm định.",
        }

    current_row = feat.iloc[-1]

    cfg = WalkForwardConfig(
        train_months=4,
        test_months=1,
        step_months=1,
        min_train_samples=20,
        min_test_samples=5,
        return_col="ret_t5_pct",
    )

    wf_detail, summary = run_walkforward_validation(
        feature_df=feat,
        current_row=current_row,
        match_func=default_momentum_match_func,
        config=cfg,
        date_col="date",
    )

    out = {
        "Mã": symbol,
        "Trạng thái dữ liệu": "OK",
        "Ngày hiện tại": str(pd.to_datetime(current_row["date"]).date()),
        "RSI hiện tại": round(float(current_row["rsi"]), 2),
        "Dist MA20 %": round(float(current_row["dist_ma20_pct"]), 2),
        "Volume Ratio": round(float(current_row["volume_ratio"]), 2) if not pd.isna(current_row["volume_ratio"]) else "",
        "Ret 5 phiên %": round(float(current_row["ret_5"]), 2) if not pd.isna(current_row["ret_5"]) else "",
        "Ret 10 phiên %": round(float(current_row["ret_10"]), 2) if not pd.isna(current_row["ret_10"]) else "",
    }
    out.update(summary)

    try:
        detail_path = f"v152_momentum_wf_detail_{symbol}.csv"
        wf_detail.to_csv(detail_path, index=False, encoding="utf-8-sig")
    except Exception:
        pass

    return out


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


def build_report(df: pd.DataFrame, source: str) -> str:
    lines = [
        "✅ <b>V15.2 MOMENTUM WALK-FORWARD HOÀN TẤT</b>",
        "",
        f"Nguồn mã: <b>{source}</b>",
        f"Số mã kiểm tra: <b>{len(df)}</b>",
        "",
        "<b>KIỂM ĐỊNH 2 THÁNG HỌC → 1 THÁNG TEST</b>",
    ]

    if df is None or df.empty:
        lines.append("Không có dữ liệu.")
        return "\n".join(lines)

    for _, r in df.head(8).iterrows():
        lines.append("")
        lines.append(f"🔹 <b>{r.get('Mã','')}</b> | {r.get('Độ ổn định mẫu','')}")

        lines.append(
            f"Đoạn test: {r.get('Số đoạn test','')} | "
            f"Đoạn dương: {r.get('Số đoạn dương','')} | "
            f"Tỷ lệ dương: {fmt(r.get('Tỷ lệ đoạn dương %'))}%"
        )

        lines.append(
            f"Win TB: {fmt(r.get('Win T+5 TB các đoạn %'))}% | "
            f"Lợi TB: {fmt(r.get('Lợi TB T+5 các đoạn %'))}%"
        )

        lines.append(
            f"RSI: {fmt(r.get('RSI hiện tại'))} | "
            f"Dist MA20: {fmt(r.get('Dist MA20 %'))}% | "
            f"Volume: {fmt(r.get('Volume Ratio'))}"
        )

        lines.append(f"Lý do: {r.get('Lý do ổn định','')}")

    return "\n".join(lines)


def send_telegram(text: str):
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        print("WARN: thiếu Telegram token/chat_id, bỏ qua V15.2 momentum", flush=True)
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
        print("TELEGRAM V15.2 MOMENTUM STATUS:", resp.status_code, resp.text[:200], flush=True)
        return resp.status_code == 200
    except Exception as e:
        print("WARN: gửi Telegram V15.2 momentum lỗi:", repr(e), flush=True)
        return False


def main():
    print("V15.2 MOMENTUM WALK-FORWARD STARTED", flush=True)

    symbols, source = load_candidates()

    if not symbols:
        out = pd.DataFrame([{"Trạng thái": "Không tìm thấy danh sách mã đầu vào"}])
        out.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
        Path(OUT_TXT).write_text("Không tìm thấy danh sách mã đầu vào", encoding="utf-8")
        print("WARN: không tìm thấy danh sách mã đầu vào", flush=True)
        return

    rows = []
    for i, symbol in enumerate(symbols, 1):
        print(f"[{i}/{len(symbols)}] Walk-forward momentum {symbol}", flush=True)
        rows.append(analyze_symbol_walkforward(symbol))

    df = pd.DataFrame(rows)

    stability_rank = {
        "ỔN ĐỊNH MẠNH": 1,
        "ỔN ĐỊNH VỪA": 2,
        "TRUNG TÍNH": 3,
        "MẪU ÍT": 4,
        "YẾU / DỄ HỌC VẸT": 5,
        "KHÔNG ĐỦ DỮ LIỆU": 6,
    }

    if "Độ ổn định mẫu" in df.columns:
        df["__rank"] = df["Độ ổn định mẫu"].map(stability_rank).fillna(9)
        if "Tỷ lệ đoạn dương %" in df.columns:
            df["__pos"] = pd.to_numeric(df["Tỷ lệ đoạn dương %"], errors="coerce")
        else:
            df["__pos"] = 0
        df = df.sort_values(["__rank", "__pos"], ascending=[True, False], na_position="last")
        df = df.drop(columns=["__rank", "__pos"]).reset_index(drop=True)

    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>V15.2 Momentum WalkForward</title>
{html_style()}
</head>
<body>
<h2>V15.2 - MOMENTUM WALK-FORWARD VALIDATION</h2>
<div class="note">
<b>Generated:</b> {now_str()}<br>
<b>Nguồn danh sách mã:</b> {source}<br>
<b>Quy ước:</b> Học 2 tháng → test tháng thứ 3 → trượt liên tục từng tháng.<br>
<b>Ý nghĩa:</b> Kiểm tra momentum/heat combo có ổn định qua nhiều giai đoạn hay chỉ đẹp do học vẹt.
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
