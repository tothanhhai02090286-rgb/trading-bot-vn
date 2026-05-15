# -*- coding: utf-8 -*-
"""
v153_regime_aware_walkforward_vi.py

V15.3 - REGIME-AWARE WALK-FORWARD TEST

Mục tiêu:
- Kiểm tra kết quả walk-forward Momentum/Bottom theo từng trạng thái thị trường.
- Chống học vẹt: tín hiệu có thắng bền trong nhiều regime hay chỉ thắng đúng một pha.
- Không sửa V16/V17, không đổi file cũ. Chỉ xuất file quan sát riêng.

Input:
- v152_momentum_walkforward.csv
- v152_bottom_walkforward.csv
- cache_stock/VNINDEX.csv hoặc cache_stock/VN30.csv

Output:
- v153_regime_aware_walkforward.csv
- v153_regime_aware_walkforward_detail.csv
- v153_regime_aware_walkforward.html
- v153_regime_aware_report.txt
"""

from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

import numpy as np
import pandas as pd


CACHE_DIR = os.getenv("CACHE_DIR", "cache_stock")

MOM_WF_CSV = os.getenv("V152_MOM_WF_CSV", "v152_momentum_walkforward.csv")
BOTTOM_WF_CSV = os.getenv("V152_BOTTOM_WF_CSV", "v152_bottom_walkforward.csv")

OUT_CSV = os.getenv("V153_REGIME_AWARE_CSV", "v153_regime_aware_walkforward.csv")
OUT_DETAIL_CSV = os.getenv("V153_REGIME_AWARE_DETAIL_CSV", "v153_regime_aware_walkforward_detail.csv")
OUT_HTML = os.getenv("V153_REGIME_AWARE_HTML", "v153_regime_aware_walkforward.html")
OUT_TXT = os.getenv("V153_REGIME_AWARE_TXT", "v153_regime_aware_report.txt")

MIN_TOTAL_SAMPLES = int(os.getenv("V153_MIN_TOTAL_SAMPLES", "5"))
MIN_REGIME_SAMPLES = int(os.getenv("V153_MIN_REGIME_SAMPLES", "2"))


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_csv_safe(path: str) -> pd.DataFrame:
    try:
        if Path(path).exists():
            return pd.read_csv(path)
    except Exception as e:
        print(f"WARN: Không đọc được {path}: {repr(e)}", flush=True)
    return pd.DataFrame()


def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
    return out


def find_col(df: pd.DataFrame, names: List[str]) -> Optional[str]:
    if df is None or df.empty:
        return None

    lower_map = {str(c).strip().lower(): c for c in df.columns}

    for name in names:
        key = str(name).strip().lower()
        if key in lower_map:
            return lower_map[key]

    for c in df.columns:
        c_low = str(c).strip().lower()
        for name in names:
            n_low = str(name).strip().lower()
            if n_low and n_low in c_low:
                return c

    return None


def to_num(x, default=np.nan) -> float:
    try:
        if x is None or pd.isna(x) or x == "":
            return default
        return float(x)
    except Exception:
        return default


def normalize_symbol(s: pd.Series) -> pd.Series:
    return s.astype(str).str.upper().str.strip()


def calc_rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window).mean()
    avg_loss = loss.rolling(window).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def normalize_market_cache(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    df = clean_columns(df)

    date_col = find_col(df, ["date", "time", "Ngày", "Ngay", "Date"])
    close_col = find_col(df, ["close", "Close", "Giá", "Gia"])
    volume_col = find_col(df, ["volume", "Volume", "vol"])

    if date_col is None or close_col is None:
        return pd.DataFrame()

    out = pd.DataFrame()
    out["Ngày"] = pd.to_datetime(df[date_col], errors="coerce")
    out["Đóng cửa"] = pd.to_numeric(df[close_col], errors="coerce")

    if volume_col is not None:
        out["Khối lượng"] = pd.to_numeric(df[volume_col], errors="coerce")
    else:
        out["Khối lượng"] = np.nan

    out = out.dropna(subset=["Ngày", "Đóng cửa"])
    out = out.sort_values("Ngày").drop_duplicates("Ngày").reset_index(drop=True)
    return out


def add_market_regime(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["MA5"] = out["Đóng cửa"].rolling(5).mean()
    out["MA20"] = out["Đóng cửa"].rolling(20).mean()
    out["RSI14"] = calc_rsi(out["Đóng cửa"], 14)
    out["Ret20 %"] = (out["Đóng cửa"] / out["Đóng cửa"].shift(20) - 1) * 100

    def classify(row: pd.Series) -> str:
        close = to_num(row.get("Đóng cửa"))
        ma5 = to_num(row.get("MA5"))
        ma20 = to_num(row.get("MA20"))
        ret20 = to_num(row.get("Ret20 %"), 0)
        rsi = to_num(row.get("RSI14"), 50)

        if pd.isna(close) or pd.isna(ma5) or pd.isna(ma20):
            return "KHÔNG ĐỦ DỮ LIỆU"

        if close > ma20 and ma5 > ma20 and ret20 > 3:
            return "THỊ TRƯỜNG MẠNH"

        if close > ma20 and ma5 >= ma20:
            return "THỊ TRƯỜNG TÍCH CỰC"

        if close < ma20 and ma5 < ma20 and ret20 < -3:
            return "THỊ TRƯỜNG YẾU"

        if close < ma20 and rsi < 35:
            return "RISK OFF"

        return "SIDEWAY / TRUNG TÍNH"

    out["Regime thị trường"] = out.apply(classify, axis=1)
    return out


def load_market_index() -> pd.DataFrame:
    candidates = [
        Path(CACHE_DIR) / "VNINDEX.csv",
        Path(CACHE_DIR) / "VNINDEX.VN.csv",
        Path(CACHE_DIR) / "VN30.csv",
        Path(CACHE_DIR) / "VN30.VN.csv",
        Path(CACHE_DIR) / "^VNINDEX.csv",
    ]

    for fp in candidates:
        if fp.exists():
            raw = read_csv_safe(str(fp))
            m = normalize_market_cache(raw)
            if not m.empty:
                print(f"OK: dùng dữ liệu thị trường từ {fp}", flush=True)
                return add_market_regime(m)

    print("WARN: Không thấy VNINDEX/VN30 trong cache_stock.", flush=True)
    return pd.DataFrame()


def infer_date_col(df: pd.DataFrame) -> Optional[str]:
    return find_col(df, [
        "Ngày tín hiệu", "Ngay tin hieu", "Signal Date", "signal_date",
        "date", "Date", "Ngày", "Ngay", "Test start", "test_start",
        "Thời điểm", "time"
    ])


def infer_return_col(df: pd.DataFrame) -> Optional[str]:
    return find_col(df, [
        "ret_t5_pct", "Lợi TB T+5 %", "Loi TB T+5 %", "T+5",
        "ret_t2_pct", "Lợi TB T+2 %", "Loi TB T+2 %", "T+2",
        "return", "Return", "Lợi nhuận", "Loi nhuan"
    ])


def infer_winrate_col(df: pd.DataFrame) -> Optional[str]:
    return find_col(df, [
        "winrate", "Winrate", "Tỷ lệ thắng", "Ty le thang",
        "win_rate", "Win Rate"
    ])


def infer_samples_col(df: pd.DataFrame) -> Optional[str]:
    return find_col(df, [
        "samples", "Số mẫu", "So mau", "n", "count",
        "Test samples", "Số mẫu test", "So mau test"
    ])


def infer_label_col(df: pd.DataFrame) -> Optional[str]:
    return find_col(df, [
        "Độ ổn định mẫu", "Do on dinh mau", "Kết luận", "Ket luan",
        "Label", "label", "Stability", "stability"
    ])


def load_walkforward_file(path: str, strategy: str) -> pd.DataFrame:
    df = clean_columns(read_csv_safe(path))
    if df.empty:
        return pd.DataFrame()

    ma_col = find_col(df, ["Mã", "Ma", "Ticker", "Symbol"])
    if ma_col is None:
        print(f"WARN: {path} không có cột mã.", flush=True)
        return pd.DataFrame()

    out = df.copy()
    out["Mã"] = normalize_symbol(out[ma_col])
    out = out[(out["Mã"] != "") & (out["Mã"] != "NAN")].copy()
    out["Chiến lược"] = strategy

    date_col = infer_date_col(out)
    ret_col = infer_return_col(out)
    win_col = infer_winrate_col(out)
    sample_col = infer_samples_col(out)
    label_col = infer_label_col(out)

    if date_col is not None:
        out["Ngày tín hiệu"] = pd.to_datetime(out[date_col], errors="coerce")
    else:
        out["Ngày tín hiệu"] = pd.NaT

    if ret_col is not None:
        out["Lợi nhuận kiểm tra %"] = pd.to_numeric(out[ret_col], errors="coerce")
    else:
        out["Lợi nhuận kiểm tra %"] = np.nan

    if win_col is not None:
        out["Tỷ lệ thắng gốc"] = pd.to_numeric(out[win_col], errors="coerce")
    else:
        out["Tỷ lệ thắng gốc"] = np.nan

    if sample_col is not None:
        out["Số mẫu gốc"] = pd.to_numeric(out[sample_col], errors="coerce")
    else:
        out["Số mẫu gốc"] = np.nan

    if label_col is not None:
        out["Độ ổn định gốc"] = out[label_col].astype(str)
    else:
        out["Độ ổn định gốc"] = ""

    return out.reset_index(drop=True)


def attach_regime(wf: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    out = wf.copy()

    if market is None or market.empty or "Ngày tín hiệu" not in out.columns:
        out["Regime thị trường"] = "KHÔNG XÁC ĐỊNH"
        return out

    x = out.copy()
    x["Ngày tín hiệu"] = pd.to_datetime(x["Ngày tín hiệu"], errors="coerce")
    x = x.sort_values("Ngày tín hiệu")

    m = market[["Ngày", "Regime thị trường", "Đóng cửa", "MA5", "MA20", "Ret20 %", "RSI14"]].copy()
    m = m.dropna(subset=["Ngày"]).sort_values("Ngày")

    if x["Ngày tín hiệu"].notna().sum() == 0:
        x["Regime thị trường"] = "KHÔNG XÁC ĐỊNH"
        return x

    merged = pd.merge_asof(
        x,
        m,
        left_on="Ngày tín hiệu",
        right_on="Ngày",
        direction="backward",
        tolerance=pd.Timedelta(days=7),
    )

    merged["Regime thị trường"] = merged["Regime thị trường"].fillna("KHÔNG XÁC ĐỊNH")
    return merged.reset_index(drop=True)


def expected_regimes(strategy: str) -> List[str]:
    s = str(strategy).upper()
    if "MOMENTUM" in s:
        return ["THỊ TRƯỜNG MẠNH", "THỊ TRƯỜNG TÍCH CỰC"]
    if "BOTTOM" in s:
        return ["SIDEWAY / TRUNG TÍNH", "THỊ TRƯỜNG YẾU"]
    return ["THỊ TRƯỜNG MẠNH", "THỊ TRƯỜNG TÍCH CỰC", "SIDEWAY / TRUNG TÍNH"]


def classify_regime_fit(
    strategy: str,
    total_samples: int,
    best_regime: str,
    best_ret: float,
    all_ret: float,
    positive_regime_count: int,
) -> str:
    exp = expected_regimes(strategy)

    if total_samples < MIN_TOTAL_SAMPLES:
        return "MẪU ÍT - CHƯA KẾT LUẬN"

    if pd.isna(all_ret):
        return "THIẾU DỮ LIỆU LỢI NHUẬN"

    if all_ret > 0 and best_regime in exp and positive_regime_count >= 2:
        return "REGIME FIT MẠNH"

    if all_ret > 0 and best_regime in exp:
        return "REGIME FIT VỪA"

    if all_ret > 0 and positive_regime_count == 1:
        return "CHỈ HỢP MỘT PHA"

    if all_ret <= 0 and not pd.isna(best_ret) and best_ret > 0:
        return "CHỈ HỢP MỘT REGIME - CẨN TRỌNG"

    return "KHÔNG ỔN ĐỊNH THEO REGIME"


def regime_fit_score(label: str) -> int:
    s = str(label).upper()
    if "FIT MẠNH" in s:
        return 100
    if "FIT VỪA" in s:
        return 75
    if "CHỈ HỢP MỘT PHA" in s:
        return 55
    if "CHỈ HỢP MỘT REGIME" in s:
        return 45
    if "MẪU ÍT" in s:
        return 40
    if "THIẾU" in s:
        return 35
    return 20


def build_summary(detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame()

    rows: List[Dict[str, Any]] = []

    for (ma, strategy), g in detail.groupby(["Mã", "Chiến lược"], dropna=False):
        g = g.copy()
        ret = pd.to_numeric(g["Lợi nhuận kiểm tra %"], errors="coerce")
        total_samples = len(g)
        all_ret = float(ret.mean()) if ret.notna().any() else np.nan
        all_win = float((ret > 0).mean() * 100) if ret.notna().any() else np.nan

        regime_stats = []
        for regime_name, rg in g.groupby("Regime thị trường", dropna=False):
            r = pd.to_numeric(rg["Lợi nhuận kiểm tra %"], errors="coerce")
            n = len(rg)
            avg_ret = float(r.mean()) if r.notna().any() else np.nan
            winrate = float((r > 0).mean() * 100) if r.notna().any() else np.nan
            regime_stats.append({
                "regime": regime_name,
                "n": n,
                "avg_ret": avg_ret,
                "winrate": winrate,
            })

        regime_stats = sorted(
            regime_stats,
            key=lambda x: -999 if pd.isna(x["avg_ret"]) else x["avg_ret"],
            reverse=True,
        )

        if regime_stats:
            best = regime_stats[0]
        else:
            best = {"regime": "", "n": 0, "avg_ret": np.nan, "winrate": np.nan}

        positive_regime_count = sum(
            1 for x in regime_stats
            if x["n"] >= MIN_REGIME_SAMPLES and not pd.isna(x["avg_ret"]) and x["avg_ret"] > 0
        )

        label = classify_regime_fit(
            strategy=strategy,
            total_samples=total_samples,
            best_regime=best["regime"],
            best_ret=best["avg_ret"],
            all_ret=all_ret,
            positive_regime_count=positive_regime_count,
        )

        detail_txt = []
        for x in regime_stats:
            avg_txt = "" if pd.isna(x["avg_ret"]) else f"{x['avg_ret']:.2f}%"
            win_txt = "" if pd.isna(x["winrate"]) else f"{x['winrate']:.1f}%"
            detail_txt.append(f"{x['regime']}: n={x['n']}, TB={avg_txt}, Win={win_txt}")

        rows.append({
            "Mã": ma,
            "Chiến lược": strategy,
            "Tổng số mẫu": total_samples,
            "Lợi nhuận TB toàn bộ %": round(all_ret, 2) if not pd.isna(all_ret) else "",
            "Winrate toàn bộ %": round(all_win, 1) if not pd.isna(all_win) else "",
            "Regime tốt nhất": best["regime"],
            "Số mẫu regime tốt nhất": best["n"],
            "Lợi nhuận TB regime tốt nhất %": round(best["avg_ret"], 2) if not pd.isna(best["avg_ret"]) else "",
            "Winrate regime tốt nhất %": round(best["winrate"], 1) if not pd.isna(best["winrate"]) else "",
            "Số regime có lợi nhuận dương": positive_regime_count,
            "Kết luận regime-aware": label,
            "Điểm regime-aware": regime_fit_score(label),
            "Chi tiết theo regime": " | ".join(detail_txt),
        })

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    out["_score"] = pd.to_numeric(out["Điểm regime-aware"], errors="coerce").fillna(0)
    out["_ret"] = pd.to_numeric(out["Lợi nhuận TB toàn bộ %"], errors="coerce").fillna(-999)
    out = out.sort_values(["_score", "_ret", "Tổng số mẫu"], ascending=[False, False, False])
    return out.drop(columns=["_score", "_ret"]).reset_index(drop=True)


def html_style() -> str:
    return """
<style>
body{font-family:Arial,sans-serif;background:#0f172a;color:#e5e7eb;padding:18px}
h2,h3{color:#fff}
.note{background:#111827;border:1px solid #334155;border-radius:10px;padding:12px;margin:12px 0}
.card{background:#111827;border:1px solid #334155;border-radius:12px;padding:12px;margin:14px 0;overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:12px;background:#111827}
th{background:#1f2937;color:#fff;position:sticky;top:0}
td,th{border:1px solid #334155;padding:7px;white-space:nowrap;vertical-align:top}
tr:nth-child(even){background:#0b1220}
</style>
"""


def build_report(summary: pd.DataFrame, detail: pd.DataFrame, market: pd.DataFrame) -> str:
    lines = [
        "✅ V15.3 REGIME-AWARE WALK-FORWARD HOÀN TẤT",
        "",
        f"Thời gian chạy: {now_str()}",
        f"Số dòng chi tiết: {len(detail)}",
        f"Số mã/chiến lược tổng hợp: {len(summary)}",
        f"Dữ liệu regime thị trường: {'CÓ' if not market.empty else 'KHÔNG CÓ'}",
        "",
        "Ý nghĩa:",
        "- Kiểm tra Momentum/Bottom theo từng regime thị trường.",
        "- Dùng để phát hiện tín hiệu chỉ thắng trong một pha và giảm học vẹt.",
        "",
        "TOP REGIME FIT:",
    ]

    if summary.empty:
        lines.append("Không có dữ liệu.")
        return "\n".join(lines)

    for _, r in summary.head(10).iterrows():
        lines += [
            "",
            f"🔹 {r.get('Mã','')} | {r.get('Chiến lược','')} | {r.get('Kết luận regime-aware','')}",
            f"Điểm: {r.get('Điểm regime-aware','')} | TB toàn bộ: {r.get('Lợi nhuận TB toàn bộ %','')}% | Win: {r.get('Winrate toàn bộ %','')}%",
            f"Regime tốt nhất: {r.get('Regime tốt nhất','')} | TB: {r.get('Lợi nhuận TB regime tốt nhất %','')}% | n={r.get('Số mẫu regime tốt nhất','')}",
        ]

    return "\n".join(lines)


def main():
    print("V15.3 REGIME-AWARE WALK-FORWARD START", flush=True)

    mom = load_walkforward_file(MOM_WF_CSV, "MOMENTUM")
    bottom = load_walkforward_file(BOTTOM_WF_CSV, "BOTTOM")

    frames = []
    if not mom.empty:
        frames.append(mom)
        print(f"OK: đọc momentum WF rows={len(mom)}", flush=True)
    else:
        print(f"WARN: không có dữ liệu momentum từ {MOM_WF_CSV}", flush=True)

    if not bottom.empty:
        frames.append(bottom)
        print(f"OK: đọc bottom WF rows={len(bottom)}", flush=True)
    else:
        print(f"WARN: không có dữ liệu bottom từ {BOTTOM_WF_CSV}", flush=True)

    if not frames:
        empty = pd.DataFrame([{
            "Trạng thái": "Không có dữ liệu walk-forward để kiểm tra regime-aware",
            "File momentum": MOM_WF_CSV,
            "File bottom": BOTTOM_WF_CSV,
        }])
        empty.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
        empty.to_html(OUT_HTML, index=False)
        Path(OUT_TXT).write_text("Không có dữ liệu walk-forward để kiểm tra regime-aware.", encoding="utf-8")
        print("DONE EMPTY", flush=True)
        return

    wf = pd.concat(frames, ignore_index=True, sort=False)
    market = load_market_index()
    detail = attach_regime(wf, market)
    summary = build_summary(detail)

    summary.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    detail.to_csv(OUT_DETAIL_CSV, index=False, encoding="utf-8-sig")

    report = build_report(summary, detail, market)
    Path(OUT_TXT).write_text(report, encoding="utf-8")

    summary_html = summary.to_html(index=False, escape=True) if not summary.empty else "<p>Không có dữ liệu tổng hợp.</p>"
    detail_html = detail.head(300).to_html(index=False, escape=True) if not detail.empty else "<p>Không có dữ liệu chi tiết.</p>"
    market_html = market.tail(30).to_html(index=False, escape=True) if not market.empty else "<p>Không có dữ liệu VNINDEX/VN30.</p>"

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>V15.3 Regime-aware Walk-forward</title>
{html_style()}
</head>
<body>
<h2>V15.3 - REGIME-AWARE WALK-FORWARD</h2>
<div class="note">
<b>Generated:</b> {now_str()}<br>
<b>Mục tiêu:</b> kiểm tra Momentum/Bottom theo từng regime thị trường để chống học vẹt.<br>
<b>Output chính:</b> {OUT_CSV}<br>
<b>Output chi tiết:</b> {OUT_DETAIL_CSV}
</div>

<div class="card">
<h3>1. KẾT QUẢ TỔNG HỢP THEO MÃ / CHIẾN LƯỢC</h3>
{summary_html}
</div>

<div class="card">
<h3>2. REGIME THỊ TRƯỜNG GẦN ĐÂY</h3>
{market_html}
</div>

<div class="card">
<h3>3. CHI TIẾT WALK-FORWARD GẮN REGIME</h3>
{detail_html}
</div>
</body>
</html>
"""
    Path(OUT_HTML).write_text(html, encoding="utf-8")

    print(report, flush=True)
    print(f"OK: wrote {OUT_CSV}", flush=True)
    print(f"OK: wrote {OUT_DETAIL_CSV}", flush=True)
    print(f"OK: wrote {OUT_HTML}", flush=True)
    print(f"OK: wrote {OUT_TXT}", flush=True)


if __name__ == "__main__":
    main()
