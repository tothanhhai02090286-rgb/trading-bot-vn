# -*- coding: utf-8 -*-
"""
v153_regime_aware_walkforward_vi.py

V15.3 REGIME-AWARE WALK-FORWARD - RELAXED V2

Mục tiêu:
- Giảm tình trạng n=1 quá nhiều.
- Không chỉ đọc summary V15.2 nữa, mà tự quét lịch sử trong cache_stock.
- Tăng historical depth, nới tolerance matching, gộp regime, fallback KNN.

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
from typing import Optional, List, Tuple, Dict, Any

import numpy as np
import pandas as pd


CACHE_DIR = os.getenv("CACHE_DIR", "cache_stock")

MOM_WF_CSV = os.getenv("V152_MOM_WF_CSV", "v152_momentum_walkforward.csv")
BOTTOM_WF_CSV = os.getenv("V152_BOTTOM_WF_CSV", "v152_bottom_walkforward.csv")
V17_CSV = os.getenv("V17_FINAL_DECISION_CSV", "v17_final_decision.csv")
WATCHLIST_CSV = os.getenv("INTRADAY_WATCHLIST_CSV", "intraday_watchlist_v17.csv")

OUT_CSV = os.getenv("V153_REGIME_AWARE_CSV", "v153_regime_aware_walkforward.csv")
OUT_DETAIL_CSV = os.getenv("V153_REGIME_AWARE_DETAIL_CSV", "v153_regime_aware_walkforward_detail.csv")
OUT_HTML = os.getenv("V153_REGIME_AWARE_HTML", "v153_regime_aware_walkforward.html")
OUT_TXT = os.getenv("V153_REGIME_AWARE_TXT", "v153_regime_aware_report.txt")

LOOKBACK_DAYS = int(os.getenv("V153_LOOKBACK_DAYS", "1260"))
EXCLUDE_RECENT_DAYS = int(os.getenv("V153_EXCLUDE_RECENT_DAYS", "7"))

MIN_TOTAL_SAMPLES = int(os.getenv("V153_MIN_TOTAL_SAMPLES", "8"))
MIN_REGIME_SAMPLES = int(os.getenv("V153_MIN_REGIME_SAMPLES", "3"))
MIN_RELAXED_MATCHES = int(os.getenv("V153_MIN_RELAXED_MATCHES", "8"))
MAX_MATCHES = int(os.getenv("V153_MAX_MATCHES", "80"))
KNN_FALLBACK_N = int(os.getenv("V153_KNN_FALLBACK_N", "20"))

MOM_RSI_TOL = float(os.getenv("V153_MOM_RSI_TOL", "12"))
MOM_DIST_MA20_TOL = float(os.getenv("V153_MOM_DIST_MA20_TOL", "6"))
MOM_RET5_TOL = float(os.getenv("V153_MOM_RET5_TOL", "7"))

BOT_RSI_TOL = float(os.getenv("V153_BOTTOM_RSI_TOL", "14"))
BOT_DD_TOL = float(os.getenv("V153_BOTTOM_DRAWDOWN_TOL", "12"))
BOT_DIST_TOL = float(os.getenv("V153_BOTTOM_DIST_MA20_TOL", "8"))


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_csv_safe(path: str) -> pd.DataFrame:
    try:
        if Path(path).exists():
            return pd.read_csv(path)
    except Exception as e:
        print(f"WARN: Không đọc được {path}: {repr(e)}", flush=True)
    return pd.DataFrame()


def clean_cols(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
    return out


def find_col(df: pd.DataFrame, names: List[str]) -> Optional[str]:
    if df is None or df.empty:
        return None
    lower = {str(c).strip().lower(): c for c in df.columns}

    for n in names:
        key = str(n).strip().lower()
        if key in lower:
            return lower[key]

    for c in df.columns:
        cl = str(c).strip().lower()
        for n in names:
            nl = str(n).strip().lower()
            if nl and nl in cl:
                return c
    return None


def to_num(x, default=np.nan) -> float:
    try:
        if x is None or pd.isna(x) or x == "":
            return default
        return float(x)
    except Exception:
        return default


def symbol_norm(x) -> str:
    return str(x).strip().upper()


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    df = clean_cols(df)
    if df.empty:
        return pd.DataFrame()

    date_col = find_col(df, ["date", "time", "datetime", "Date", "Ngày", "Ngay"])
    close_col = find_col(df, ["close", "Close", "Đóng cửa", "Dong cua"])
    open_col = find_col(df, ["open", "Open", "Mở cửa", "Mo cua"])
    high_col = find_col(df, ["high", "High", "Cao nhất", "Cao nhat"])
    low_col = find_col(df, ["low", "Low", "Thấp nhất", "Thap nhat"])
    vol_col = find_col(df, ["volume", "Volume", "vol", "Khối lượng", "Khoi luong"])

    if date_col is None or close_col is None:
        return pd.DataFrame()

    out = pd.DataFrame()
    out["date"] = pd.to_datetime(df[date_col], errors="coerce")
    out["close"] = pd.to_numeric(df[close_col], errors="coerce")
    out["open"] = pd.to_numeric(df[open_col], errors="coerce") if open_col else out["close"]
    out["high"] = pd.to_numeric(df[high_col], errors="coerce") if high_col else out["close"]
    out["low"] = pd.to_numeric(df[low_col], errors="coerce") if low_col else out["close"]
    out["volume"] = pd.to_numeric(df[vol_col], errors="coerce") if vol_col else np.nan
    out = out.dropna(subset=["date", "close"])
    out = out.sort_values("date").drop_duplicates("date").reset_index(drop=True)
    return out


def calc_rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window).mean()
    avg_loss = loss.rolling(window).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ma5"] = out["close"].rolling(5).mean()
    out["ma20"] = out["close"].rolling(20).mean()
    out["ma50"] = out["close"].rolling(50).mean()
    out["rsi"] = calc_rsi(out["close"], 14)

    out["ret5_pct"] = (out["close"] / out["close"].shift(5) - 1) * 100
    out["ret10_pct"] = (out["close"] / out["close"].shift(10) - 1) * 100
    out["ret20_pct"] = (out["close"] / out["close"].shift(20) - 1) * 100

    out["future_ret_t2_pct"] = (out["close"].shift(-2) / out["close"] - 1) * 100
    out["future_ret_t5_pct"] = (out["close"].shift(-5) / out["close"] - 1) * 100

    h20 = out["high"].rolling(20).max()
    l20 = out["low"].rolling(20).min()
    out["drawdown20_pct"] = (out["close"] / h20 - 1) * 100
    out["rebound_low20_pct"] = (out["close"] / l20 - 1) * 100
    out["dist_ma20_pct"] = (out["close"] / out["ma20"] - 1) * 100

    vol_ma20 = out["volume"].rolling(20).mean()
    out["volume_ratio"] = out["volume"] / vol_ma20.replace(0, np.nan)
    return out


def group_regime(raw: str) -> str:
    s = str(raw).upper()
    if "MẠNH" in s or "TÍCH CỰC" in s:
        return "RISK ON"
    if "YẾU" in s or "RISK OFF" in s:
        return "RISK OFF"
    if "SIDEWAY" in s or "TRUNG TÍNH" in s:
        return "SIDEWAY"
    return "KHÔNG XÁC ĐỊNH"


def add_market_regime(df: pd.DataFrame) -> pd.DataFrame:
    out = add_features(df)

    def classify(row: pd.Series) -> str:
        close = to_num(row.get("close"))
        ma5 = to_num(row.get("ma5"))
        ma20 = to_num(row.get("ma20"))
        ret20 = to_num(row.get("ret20_pct"), 0)
        rsi = to_num(row.get("rsi"), 50)

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

    out["Regime thô"] = out.apply(classify, axis=1)
    out["Regime gộp"] = out["Regime thô"].map(group_regime)
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
            df = normalize_ohlcv(read_csv_safe(str(fp)))
            if not df.empty:
                print(f"OK: dùng dữ liệu thị trường từ {fp}", flush=True)
                return add_market_regime(df)

    print("WARN: Không thấy VNINDEX/VN30 trong cache_stock.", flush=True)
    return pd.DataFrame()


def get_regime_for_dates(dates: pd.Series, market: pd.DataFrame) -> pd.DataFrame:
    x = pd.DataFrame({"date": pd.to_datetime(dates, errors="coerce")}).sort_values("date")

    if market is None or market.empty:
        x["Regime thô"] = "KHÔNG XÁC ĐỊNH"
        x["Regime gộp"] = "KHÔNG XÁC ĐỊNH"
        return x

    m = market[["date", "Regime thô", "Regime gộp"]].dropna(subset=["date"]).sort_values("date")
    merged = pd.merge_asof(
        x,
        m,
        on="date",
        direction="backward",
        tolerance=pd.Timedelta(days=7),
    )
    merged["Regime thô"] = merged["Regime thô"].fillna("KHÔNG XÁC ĐỊNH")
    merged["Regime gộp"] = merged["Regime gộp"].fillna("KHÔNG XÁC ĐỊNH")
    return merged


def candidate_symbols_from_file(path: str) -> List[str]:
    df = clean_cols(read_csv_safe(path))
    if df.empty:
        return []
    col = find_col(df, ["Mã", "Ma", "Ticker", "Symbol"])
    if col is None:
        return []
    return sorted({
        symbol_norm(x)
        for x in df[col].dropna().tolist()
        if symbol_norm(x) not in ["", "NAN"]
    })


def load_candidate_symbols() -> List[str]:
    symbols = []
    for p in [WATCHLIST_CSV, V17_CSV, MOM_WF_CSV, BOTTOM_WF_CSV]:
        symbols.extend(candidate_symbols_from_file(p))

    if not symbols:
        for fp in Path(CACHE_DIR).glob("*.csv"):
            name = fp.stem.upper().replace(".VN", "")
            if name not in ["VNINDEX", "VN30", "^VNINDEX"]:
                symbols.append(name)

    symbols = sorted(set(symbols))
    print(f"OK: số mã ứng viên V15.3 = {len(symbols)}", flush=True)
    return symbols


def load_symbol_history(symbol: str) -> pd.DataFrame:
    candidates = [
        Path(CACHE_DIR) / f"{symbol}.csv",
        Path(CACHE_DIR) / f"{symbol}.VN.csv",
        Path(CACHE_DIR) / f"{symbol}.HM.csv",
        Path(CACHE_DIR) / f"{symbol}.HN.csv",
    ]

    for fp in candidates:
        if fp.exists():
            df = normalize_ohlcv(read_csv_safe(str(fp)))
            if not df.empty:
                return add_features(df)

    return pd.DataFrame()


def filter_lookback(feat: pd.DataFrame) -> pd.DataFrame:
    if feat.empty:
        return feat
    last_date = feat["date"].max()
    start_date = last_date - pd.Timedelta(days=LOOKBACK_DAYS)
    cutoff = last_date - pd.Timedelta(days=EXCLUDE_RECENT_DAYS)
    return feat[(feat["date"] >= start_date) & (feat["date"] <= cutoff)].copy()


def diff_ok(series: pd.Series, current_value: float, tol: float) -> pd.Series:
    if pd.isna(current_value):
        return pd.Series(False, index=series.index)
    return (series - current_value).abs() <= tol


def momentum_matches(hist: pd.DataFrame, current: pd.Series) -> Tuple[pd.DataFrame, str]:
    if hist.empty:
        return hist, "KHÔNG CÓ LỊCH SỬ"

    cur_rsi = to_num(current.get("rsi"))
    cur_dist = to_num(current.get("dist_ma20_pct"))
    cur_ret5 = to_num(current.get("ret5_pct"))

    base = hist.dropna(subset=["rsi", "dist_ma20_pct", "ret5_pct", "future_ret_t5_pct"]).copy()

    strict = base[
        (base["close"] > base["ma20"]) &
        (base["ma5"] >= base["ma20"]) &
        (base["ret5_pct"] > 0) &
        diff_ok(base["rsi"], cur_rsi, MOM_RSI_TOL) &
        diff_ok(base["dist_ma20_pct"], cur_dist, MOM_DIST_MA20_TOL) &
        diff_ok(base["ret5_pct"], cur_ret5, MOM_RET5_TOL)
    ].copy()

    if len(strict) >= MIN_RELAXED_MATCHES:
        return strict.tail(MAX_MATCHES), "MATCH TƯƠNG ĐỒNG NỚI LỎNG"

    relaxed = base[
        (base["close"] > base["ma20"]) &
        (base["ma5"] >= base["ma20"]) &
        (base["rsi"].between(45, 82)) &
        (base["ret5_pct"] > 0) &
        (base["dist_ma20_pct"].between(-5, 18))
    ].copy()

    if len(relaxed) >= MIN_RELAXED_MATCHES:
        return relaxed.tail(MAX_MATCHES), "ĐIỀU KIỆN MOMENTUM NỚI LỎNG"

    knn = base.copy()
    knn["distance"] = (
        ((knn["rsi"] - cur_rsi) / max(MOM_RSI_TOL, 1)) ** 2 +
        ((knn["dist_ma20_pct"] - cur_dist) / max(MOM_DIST_MA20_TOL, 1)) ** 2 +
        ((knn["ret5_pct"] - cur_ret5) / max(MOM_RET5_TOL, 1)) ** 2
    )
    return knn.sort_values("distance").head(KNN_FALLBACK_N).copy(), "KNN NỚI LỎNG"


def bottom_matches(hist: pd.DataFrame, current: pd.Series) -> Tuple[pd.DataFrame, str]:
    if hist.empty:
        return hist, "KHÔNG CÓ LỊCH SỬ"

    cur_rsi = to_num(current.get("rsi"))
    cur_dd = to_num(current.get("drawdown20_pct"))
    cur_dist = to_num(current.get("dist_ma20_pct"))

    base = hist.dropna(subset=["rsi", "drawdown20_pct", "dist_ma20_pct", "future_ret_t5_pct"]).copy()

    strict = base[
        (base["drawdown20_pct"] <= 0) &
        diff_ok(base["rsi"], cur_rsi, BOT_RSI_TOL) &
        diff_ok(base["drawdown20_pct"], cur_dd, BOT_DD_TOL) &
        diff_ok(base["dist_ma20_pct"], cur_dist, BOT_DIST_TOL)
    ].copy()

    if len(strict) >= MIN_RELAXED_MATCHES:
        return strict.tail(MAX_MATCHES), "MATCH TƯƠNG ĐỒNG NỚI LỎNG"

    relaxed = base[
        (base["rsi"].between(25, 58)) &
        (base["drawdown20_pct"] <= -2) &
        (base["dist_ma20_pct"].between(-18, 10))
    ].copy()

    if len(relaxed) >= MIN_RELAXED_MATCHES:
        return relaxed.tail(MAX_MATCHES), "ĐIỀU KIỆN BOTTOM NỚI LỎNG"

    knn = base.copy()
    knn["distance"] = (
        ((knn["rsi"] - cur_rsi) / max(BOT_RSI_TOL, 1)) ** 2 +
        ((knn["drawdown20_pct"] - cur_dd) / max(BOT_DD_TOL, 1)) ** 2 +
        ((knn["dist_ma20_pct"] - cur_dist) / max(BOT_DIST_TOL, 1)) ** 2
    )
    return knn.sort_values("distance").head(KNN_FALLBACK_N).copy(), "KNN NỚI LỎNG"


def attach_regime(matches: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    if matches.empty:
        return matches
    reg = get_regime_for_dates(matches["date"], market)[["date", "Regime thô", "Regime gộp"]]
    out = pd.merge(matches, reg, on="date", how="left")
    out["Regime thô"] = out["Regime thô"].fillna("KHÔNG XÁC ĐỊNH")
    out["Regime gộp"] = out["Regime gộp"].fillna("KHÔNG XÁC ĐỊNH")
    return out


def expected_groups(strategy: str) -> List[str]:
    if strategy == "MOMENTUM":
        return ["RISK ON"]
    return ["SIDEWAY", "RISK OFF"]


def classify_result(strategy: str, total_n: int, all_ret: float, best_group: str, positive_groups: int) -> str:
    if total_n < 3:
        return "MẪU CỰC ÍT - CHỈ THAM KHẢO"
    if total_n < MIN_TOTAL_SAMPLES:
        return "MẪU ÍT - CHƯA KẾT LUẬN"
    if pd.isna(all_ret):
        return "THIẾU DỮ LIỆU LỢI NHUẬN"

    exp = expected_groups(strategy)
    if all_ret > 0 and best_group in exp and positive_groups >= 2:
        return "REGIME FIT MẠNH"
    if all_ret > 0 and best_group in exp:
        return "REGIME FIT VỪA"
    if all_ret > 0 and positive_groups == 1:
        return "CHỈ HỢP MỘT PHA"
    if all_ret <= 0:
        return "KHÔNG ỔN ĐỊNH THEO REGIME"
    return "CẦN THEO DÕI THÊM"


def score_label(label: str, total_n: int) -> int:
    s = str(label).upper()
    base = 20
    if "FIT MẠNH" in s:
        base = 100
    elif "FIT VỪA" in s:
        base = 75
    elif "CHỈ HỢP MỘT PHA" in s:
        base = 55
    elif "MẪU ÍT" in s:
        base = 45
    elif "CỰC ÍT" in s:
        base = 35
    elif "THIẾU" in s:
        base = 30

    if total_n < 3:
        return min(base, 35)
    if total_n < MIN_TOTAL_SAMPLES:
        return min(base, 45)
    if total_n >= 30:
        return min(base + 5, 100)
    return base


def analyze_symbol_strategy(symbol: str, strategy: str, market: pd.DataFrame) -> Tuple[Dict[str, Any], pd.DataFrame]:
    feat = load_symbol_history(symbol)
    if feat.empty or len(feat) < 80:
        return {
            "Mã": symbol,
            "Chiến lược": strategy,
            "Trạng thái": "KHÔNG ĐỦ DỮ LIỆU",
            "Tổng số mẫu": 0,
            "Kết luận regime-aware": "KHÔNG ĐỦ DỮ LIỆU",
            "Điểm regime-aware": 0,
        }, pd.DataFrame()

    feat = feat.dropna(subset=["close", "ma20", "rsi"]).copy()
    current = feat.iloc[-1]
    hist = filter_lookback(feat)

    if strategy == "MOMENTUM":
        matches, method = momentum_matches(hist, current)
    else:
        matches, method = bottom_matches(hist, current)

    matches = attach_regime(matches, market)
    matches = matches.copy()
    matches["Mã"] = symbol
    matches["Chiến lược"] = strategy
    matches["Phương pháp match"] = method

    if matches.empty:
        return {
            "Mã": symbol,
            "Chiến lược": strategy,
            "Trạng thái": "KHÔNG CÓ MATCH",
            "Tổng số mẫu": 0,
            "Kết luận regime-aware": "KHÔNG CÓ MATCH",
            "Điểm regime-aware": 0,
            "Phương pháp match": method,
        }, matches

    ret = pd.to_numeric(matches["future_ret_t5_pct"], errors="coerce")
    all_ret = float(ret.mean()) if ret.notna().any() else np.nan
    all_win = float((ret > 0).mean() * 100) if ret.notna().any() else np.nan

    group_rows = []
    for group, g in matches.groupby("Regime gộp", dropna=False):
        r = pd.to_numeric(g["future_ret_t5_pct"], errors="coerce")
        n = len(g)
        avg = float(r.mean()) if r.notna().any() else np.nan
        win = float((r > 0).mean() * 100) if r.notna().any() else np.nan
        group_rows.append({"group": group, "n": n, "avg": avg, "win": win})

    group_rows = sorted(group_rows, key=lambda x: -999 if pd.isna(x["avg"]) else x["avg"], reverse=True)
    best = group_rows[0] if group_rows else {"group": "", "n": 0, "avg": np.nan, "win": np.nan}
    positive_groups = sum(1 for x in group_rows if x["n"] >= MIN_REGIME_SAMPLES and not pd.isna(x["avg"]) and x["avg"] > 0)

    label = classify_result(strategy, len(matches), all_ret, best["group"], positive_groups)

    detail_txt = []
    for x in group_rows:
        avg_txt = "" if pd.isna(x["avg"]) else f"{x['avg']:.2f}%"
        win_txt = "" if pd.isna(x["win"]) else f"{x['win']:.1f}%"
        detail_txt.append(f"{x['group']}: n={x['n']}, TB={avg_txt}, Win={win_txt}")

    summary = {
        "Mã": symbol,
        "Chiến lược": strategy,
        "Trạng thái": "OK",
        "Tổng số mẫu": len(matches),
        "Lợi nhuận TB T+5 %": round(all_ret, 2) if not pd.isna(all_ret) else "",
        "Winrate T+5 %": round(all_win, 1) if not pd.isna(all_win) else "",
        "Regime gộp tốt nhất": best["group"],
        "Số mẫu regime tốt nhất": best["n"],
        "Lợi nhuận TB regime tốt nhất %": round(best["avg"], 2) if not pd.isna(best["avg"]) else "",
        "Winrate regime tốt nhất %": round(best["win"], 1) if not pd.isna(best["win"]) else "",
        "Số regime gộp có lợi nhuận dương": positive_groups,
        "Kết luận regime-aware": label,
        "Điểm regime-aware": score_label(label, len(matches)),
        "Phương pháp match": method,
        "Ngày hiện tại": current.get("date"),
        "Giá hiện tại": round(to_num(current.get("close")), 2),
        "RSI hiện tại": round(to_num(current.get("rsi")), 2),
        "Ret5 hiện tại %": round(to_num(current.get("ret5_pct")), 2),
        "Dist MA20 hiện tại %": round(to_num(current.get("dist_ma20_pct")), 2),
        "Drawdown20 hiện tại %": round(to_num(current.get("drawdown20_pct")), 2),
        "Chi tiết theo regime gộp": " | ".join(detail_txt),
    }

    detail_cols = [
        "Mã", "Chiến lược", "date", "close", "rsi", "ret5_pct", "dist_ma20_pct",
        "drawdown20_pct", "volume_ratio", "future_ret_t2_pct", "future_ret_t5_pct",
        "Regime thô", "Regime gộp", "Phương pháp match"
    ]
    existing = [c for c in detail_cols if c in matches.columns]
    detail = matches[existing].copy()

    detail = detail.rename(columns={
        "date": "Ngày tín hiệu quá khứ",
        "close": "Giá tín hiệu",
        "rsi": "RSI",
        "ret5_pct": "Ret5 %",
        "dist_ma20_pct": "Cách MA20 %",
        "drawdown20_pct": "Drawdown20 %",
        "volume_ratio": "Volume ratio",
        "future_ret_t2_pct": "Lợi T+2 %",
        "future_ret_t5_pct": "Lợi T+5 %",
    })

    return summary, detail


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


def build_report(summary: pd.DataFrame) -> str:
    lines = [
        "✅ V15.3 REGIME-AWARE WALK-FORWARD RELAXED V2 HOÀN TẤT",
        "",
        f"Thời gian chạy: {now_str()}",
        f"Số mã/chiến lược tổng hợp: {len(summary)}",
        f"Lookback days: {LOOKBACK_DAYS}",
        f"Min total samples: {MIN_TOTAL_SAMPLES}",
        "",
        "Nâng cấp đã áp dụng:",
        "1. Tăng historical depth bằng cách quét cache_stock theo lookback dài hơn.",
        "2. Nới tolerance matching cho Momentum/Bottom.",
        "3. Gộp regime thành RISK ON / SIDEWAY / RISK OFF.",
        "4. Dùng fallback KNN nới lỏng nếu setup quá hiếm.",
        "",
        "TOP REGIME FIT:",
    ]

    if summary.empty:
        lines.append("Không có dữ liệu.")
        return "\n".join(lines)

    for _, r in summary.head(15).iterrows():
        lines += [
            "",
            f"🔹 {r.get('Mã','')} | {r.get('Chiến lược','')} | {r.get('Kết luận regime-aware','')}",
            f"Điểm: {r.get('Điểm regime-aware','')} | n={r.get('Tổng số mẫu','')} | TB T+5: {r.get('Lợi nhuận TB T+5 %','')}% | Win: {r.get('Winrate T+5 %','')}%",
            f"Regime tốt nhất: {r.get('Regime gộp tốt nhất','')} | TB: {r.get('Lợi nhuận TB regime tốt nhất %','')}% | method: {r.get('Phương pháp match','')}",
        ]

    return "\n".join(lines)


def main():
    print("V15.3 REGIME-AWARE WALK-FORWARD RELAXED V2 START", flush=True)

    symbols = load_candidate_symbols()
    market = load_market_index()

    rows = []
    details = []

    for i, sym in enumerate(symbols, 1):
        if sym in ["VNINDEX", "VN30", "^VNINDEX"]:
            continue

        print(f"[{i}/{len(symbols)}] Analyze {sym}", flush=True)

        for strategy in ["MOMENTUM", "BOTTOM"]:
            summary, detail = analyze_symbol_strategy(sym, strategy, market)
            rows.append(summary)
            if detail is not None and not detail.empty:
                details.append(detail)

    summary_df = pd.DataFrame(rows)
    if not summary_df.empty:
        summary_df["_score"] = pd.to_numeric(summary_df.get("Điểm regime-aware", 0), errors="coerce").fillna(0)
        summary_df["_n"] = pd.to_numeric(summary_df.get("Tổng số mẫu", 0), errors="coerce").fillna(0)
        summary_df["_ret"] = pd.to_numeric(summary_df.get("Lợi nhuận TB T+5 %", -999), errors="coerce").fillna(-999)
        summary_df = summary_df.sort_values(["_score", "_n", "_ret"], ascending=[False, False, False])
        summary_df = summary_df.drop(columns=["_score", "_n", "_ret"])
        summary_df = summary_df.reset_index(drop=True)

    detail_df = pd.concat(details, ignore_index=True, sort=False) if details else pd.DataFrame()

    summary_df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    detail_df.to_csv(OUT_DETAIL_CSV, index=False, encoding="utf-8-sig")

    report = build_report(summary_df)
    Path(OUT_TXT).write_text(report, encoding="utf-8")

    summary_html = summary_df.to_html(index=False, escape=True) if not summary_df.empty else "<p>Không có dữ liệu tổng hợp.</p>"
    detail_html = detail_df.head(500).to_html(index=False, escape=True) if not detail_df.empty else "<p>Không có dữ liệu chi tiết.</p>"
    market_html = market.tail(50).to_html(index=False, escape=True) if market is not None and not market.empty else "<p>Không có dữ liệu VNINDEX/VN30.</p>"

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>V15.3 Regime-aware Walk-forward Relaxed V2</title>
{html_style()}
</head>
<body>
<h2>V15.3 - REGIME-AWARE WALK-FORWARD RELAXED V2</h2>
<div class="note">
<b>Generated:</b> {now_str()}<br>
<b>Lookback:</b> {LOOKBACK_DAYS} ngày<br>
<b>Mục tiêu:</b> tăng sample, nới matching, gộp regime để giảm tình trạng n=1 quá nhiều.<br>
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
<h3>3. CHI TIẾT MATCH QUÁ KHỨ</h3>
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
