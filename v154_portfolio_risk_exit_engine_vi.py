# -*- coding: utf-8 -*-
"""
v154_portfolio_risk_exit_engine_vi.py

V15.4 - PORTFOLIO RISK + EXIT ENGINE - FULL BUILD

Research layer độc lập, KHÔNG sửa V17/V18.
Tính năng:
1) Volatility targeting: mã biến động mạnh thì giảm tỷ trọng.
2) Max exposure: giới hạn tổng tiền mua theo trạng thái thị trường.
3) Regime cash mode: thị trường xấu giữ nhiều tiền mặt.
4) Correlation filter: hạn chế chọn nhiều mã đi cùng nhau quá mạnh.
5) Exit simulation: trailing stop, take profit, ATR stop, time stop.
6) Multi-regime weighting: regime ảnh hưởng trực tiếp tới tỷ trọng.

Input ưu tiên:
- v153_pro_research.csv
- cache_stock/*.csv
- VNINDEX/VN30 trong cache_stock

Output:
- v154_portfolio_risk_exit.csv
- v154_portfolio_risk_exit_detail.csv
- v154_portfolio_equity.csv
- v154_portfolio_risk_exit.html
- v154_portfolio_risk_exit_report.txt
"""

from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Tuple, Any

import numpy as np
import pandas as pd

CACHE_DIR = os.getenv("CACHE_DIR", "cache_stock")
V153_SCORE_CSV = os.getenv("V153_PRO_RESEARCH_CSV", "v153_pro_research.csv")
V17_CSV = os.getenv("V17_FINAL_DECISION_CSV", "v17_final_decision.csv")
WATCHLIST_CSV = os.getenv("INTRADAY_WATCHLIST_CSV", "intraday_watchlist_v17.csv")

OUT_CSV = os.getenv("V154_OUT_CSV", "v154_portfolio_risk_exit.csv")
OUT_DETAIL_CSV = os.getenv("V154_DETAIL_CSV", "v154_portfolio_risk_exit_detail.csv")
OUT_EQUITY_CSV = os.getenv("V154_EQUITY_CSV", "v154_portfolio_equity.csv")
OUT_HTML = os.getenv("V154_HTML", "v154_portfolio_risk_exit.html")
OUT_TXT = os.getenv("V154_REPORT", "v154_portfolio_risk_exit_report.txt")

LOOKBACK_DAYS = int(os.getenv("V154_LOOKBACK_DAYS", "1260"))
EXCLUDE_RECENT_DAYS = int(os.getenv("V154_EXCLUDE_RECENT_DAYS", "7"))
ROUNDTRIP_COST_PCT = float(os.getenv("V154_ROUNDTRIP_COST_PCT", "0.80"))
MAX_HOLD_DAYS = int(os.getenv("V154_MAX_HOLD_DAYS", "10"))
TAKE_PROFIT_PCT = float(os.getenv("V154_TAKE_PROFIT_PCT", "7.0"))
TRAILING_STOP_PCT = float(os.getenv("V154_TRAILING_STOP_PCT", "4.0"))
ATR_STOP_MULT = float(os.getenv("V154_ATR_STOP_MULT", "2.0"))
TARGET_VOL_PCT = float(os.getenv("V154_TARGET_VOL_PCT", "3.0"))
MAX_WEIGHT_PER_STOCK = float(os.getenv("V154_MAX_WEIGHT_PER_STOCK", "0.20"))
MIN_WEIGHT_PER_STOCK = float(os.getenv("V154_MIN_WEIGHT_PER_STOCK", "0.03"))
CORRELATION_LIMIT = float(os.getenv("V154_CORRELATION_LIMIT", "0.80"))
PORTFOLIO_TOP_N = int(os.getenv("V154_PORTFOLIO_TOP_N", "5"))
MIN_SCORE = int(os.getenv("V154_MIN_SCORE", "55"))
EXPOSURE_RISK_ON = float(os.getenv("V154_EXPOSURE_RISK_ON", "1.00"))
EXPOSURE_SIDEWAY = float(os.getenv("V154_EXPOSURE_SIDEWAY", "0.55"))
EXPOSURE_RISK_OFF = float(os.getenv("V154_EXPOSURE_RISK_OFF", "0.20"))
EXPOSURE_UNKNOWN = float(os.getenv("V154_EXPOSURE_UNKNOWN", "0.40"))


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_csv_safe(path: str) -> pd.DataFrame:
    try:
        if Path(path).exists():
            return pd.read_csv(path)
    except Exception as e:
        print(f"WARN: không đọc được {path}: {repr(e)}", flush=True)
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
        k = str(n).strip().lower()
        if k in lower:
            return lower[k]
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


def safe_round(x, ndigits=2):
    if pd.isna(x):
        return ""
    return round(float(x), ndigits)


def symbol_norm(x) -> str:
    return str(x).strip().upper()


def pct_mean(s: pd.Series) -> float:
    x = pd.to_numeric(s, errors="coerce")
    return float(x.mean()) if x.notna().any() else np.nan


def pct_winrate(s: pd.Series) -> float:
    x = pd.to_numeric(s, errors="coerce")
    return float((x > 0).mean() * 100) if x.notna().any() else np.nan


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    df = clean_cols(df)
    if df.empty:
        return pd.DataFrame()
    date_col = find_col(df, ["date", "time", "datetime", "Date", "Ngày", "Ngay"])
    close_col = find_col(df, ["close", "Close", "Đóng cửa", "Dong cua", "Gia dong cua"])
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
    out["ret1_pct"] = (out["close"] / out["close"].shift(1) - 1) * 100
    out["ret5_pct"] = (out["close"] / out["close"].shift(5) - 1) * 100
    out["ret20_pct"] = (out["close"] / out["close"].shift(20) - 1) * 100
    tr1 = out["high"] - out["low"]
    tr2 = (out["high"] - out["close"].shift(1)).abs()
    tr3 = (out["low"] - out["close"].shift(1)).abs()
    out["tr"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    out["atr14"] = out["tr"].rolling(14).mean()
    out["atr_pct"] = out["atr14"] / out["close"] * 100
    out["volatility20_pct"] = out["ret1_pct"].rolling(20).std()
    h20 = out["high"].rolling(20).max()
    out["drawdown20_pct"] = (out["close"] / h20 - 1) * 100
    out["dist_ma20_pct"] = (out["close"] / out["ma20"] - 1) * 100
    return out


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
        close = to_num(row.get("close")); ma5 = to_num(row.get("ma5")); ma20 = to_num(row.get("ma20"))
        ret20 = to_num(row.get("ret20_pct"), 0); rsi = to_num(row.get("rsi"), 50)
        if pd.isna(close) or pd.isna(ma5) or pd.isna(ma20): return "KHÔNG ĐỦ DỮ LIỆU"
        if close > ma20 and ma5 > ma20 and ret20 > 3: return "THỊ TRƯỜNG MẠNH"
        if close > ma20 and ma5 >= ma20: return "THỊ TRƯỜNG TÍCH CỰC"
        if close < ma20 and ma5 < ma20 and ret20 < -3: return "THỊ TRƯỜNG YẾU"
        if close < ma20 and rsi < 35: return "RISK OFF"
        return "SIDEWAY / TRUNG TÍNH"
    out["Regime thô"] = out.apply(classify, axis=1)
    out["Regime gộp"] = out["Regime thô"].map(group_regime)
    return out


def load_market_index() -> pd.DataFrame:
    candidates = [Path(CACHE_DIR)/"VNINDEX.csv", Path(CACHE_DIR)/"VNINDEX.VN.csv", Path(CACHE_DIR)/"VN30.csv", Path(CACHE_DIR)/"VN30.VN.csv", Path(CACHE_DIR)/"^VNINDEX.csv"]
    for fp in candidates:
        if fp.exists():
            df = normalize_ohlcv(read_csv_safe(str(fp)))
            if not df.empty:
                print(f"OK: dùng dữ liệu thị trường từ {fp}", flush=True)
                return add_market_regime(df)
    print("WARN: không thấy VNINDEX/VN30 trong cache_stock.", flush=True)
    return pd.DataFrame()


def current_market_regime(market: pd.DataFrame) -> str:
    if market is None or market.empty or "Regime gộp" not in market.columns:
        return "KHÔNG XÁC ĐỊNH"
    return str(market.dropna(subset=["Regime gộp"]).iloc[-1]["Regime gộp"])


def exposure_cap_for_regime(regime: str) -> float:
    return {"RISK ON": EXPOSURE_RISK_ON, "SIDEWAY": EXPOSURE_SIDEWAY, "RISK OFF": EXPOSURE_RISK_OFF}.get(regime, EXPOSURE_UNKNOWN)


def regime_allocation_multiplier(strategy: str, regime: str, best_regime: str) -> float:
    strategy = str(strategy).upper(); best_regime = str(best_regime).upper()
    if regime == "RISK ON" and strategy == "MOMENTUM": return 1.15
    if regime in ["SIDEWAY", "RISK OFF"] and strategy == "BOTTOM": return 1.10
    if regime == best_regime: return 1.05
    if regime == "RISK OFF" and strategy == "MOMENTUM": return 0.45
    if regime == "RISK ON" and strategy == "BOTTOM": return 0.85
    return 0.75


def load_v153_scores() -> pd.DataFrame:
    df = clean_cols(read_csv_safe(V153_SCORE_CSV))
    if df.empty:
        print("WARN: không có v153_pro_research.csv, fallback lấy mã từ watchlist/V17/cache.", flush=True)
        return pd.DataFrame()
    ma_col = find_col(df, ["Mã", "Ma", "Ticker", "Symbol"])
    score_col = find_col(df, ["Điểm V15.3 cuối cùng", "Diem V15.3 cuoi cung", "score", "Score"])
    strategy_col = find_col(df, ["Chiến lược", "Chien luoc", "strategy"])
    best_regime_col = find_col(df, ["Regime gộp tốt nhất", "Regime tốt nhất", "Best regime"])
    ret_col = find_col(df, ["Lợi nhuận TB T+5 sau phí %", "T+5 sau phí", "net_ret"])
    win_col = find_col(df, ["Winrate T+5 sau phí %", "winrate"])
    if ma_col is None: return pd.DataFrame()
    out = pd.DataFrame()
    out["Mã"] = df[ma_col].apply(symbol_norm)
    out["Chiến lược"] = df[strategy_col].astype(str).str.upper().str.strip() if strategy_col else "UNKNOWN"
    out["Điểm V15.3"] = pd.to_numeric(df[score_col], errors="coerce").fillna(50) if score_col else 50
    out["Regime tốt nhất"] = df[best_regime_col].astype(str).str.upper().str.strip() if best_regime_col else "KHÔNG XÁC ĐỊNH"
    out["T+5 sau phí %"] = pd.to_numeric(df[ret_col], errors="coerce") if ret_col else np.nan
    out["Winrate sau phí %"] = pd.to_numeric(df[win_col], errors="coerce") if win_col else np.nan
    return out[(out["Mã"] != "") & (out["Mã"] != "NAN")].copy()


def fallback_symbols() -> pd.DataFrame:
    symbols = []
    for path in [WATCHLIST_CSV, V17_CSV]:
        df = clean_cols(read_csv_safe(path)); col = find_col(df, ["Mã", "Ma", "Ticker", "Symbol"])
        if col: symbols.extend([symbol_norm(x) for x in df[col].dropna().tolist()])
    if not symbols:
        for fp in Path(CACHE_DIR).glob("*.csv"):
            name = fp.stem.upper().replace(".VN", "")
            if name not in ["VNINDEX", "VN30", "^VNINDEX"]: symbols.append(name)
    rows = []
    for s in sorted(set([x for x in symbols if x not in ["", "NAN"]])):
        rows.append({"Mã": s, "Chiến lược": "UNKNOWN", "Điểm V15.3": 50, "Regime tốt nhất": "KHÔNG XÁC ĐỊNH", "T+5 sau phí %": np.nan, "Winrate sau phí %": np.nan})
    return pd.DataFrame(rows)


def simulate_exit_for_signal(df: pd.DataFrame, signal_idx: int) -> Dict[str, Any]:
    if signal_idx >= len(df) - 2: return {}
    row = df.iloc[signal_idx]
    entry_price = to_num(row.get("close")); atr = to_num(row.get("atr14"))
    if pd.isna(entry_price) or entry_price <= 0: return {}
    atr_stop_price = entry_price - ATR_STOP_MULT * atr if not pd.isna(atr) and atr > 0 else entry_price * (1 - TRAILING_STOP_PCT / 100)
    highest = entry_price; exit_price = np.nan; exit_date = None; exit_reason = "TIME STOP"; hold_days = 0
    end_idx = min(len(df) - 1, signal_idx + MAX_HOLD_DAYS)
    for j in range(signal_idx + 1, end_idx + 1):
        day = df.iloc[j]; high = to_num(day.get("high")); low = to_num(day.get("low")); close = to_num(day.get("close"))
        if pd.isna(close): continue
        hold_days = j - signal_idx
        if not pd.isna(high): highest = max(highest, high)
        take_profit_price = entry_price * (1 + TAKE_PROFIT_PCT / 100)
        trailing_stop_price = highest * (1 - TRAILING_STOP_PCT / 100)
        stop_price = max(atr_stop_price, trailing_stop_price)
        if not pd.isna(low) and low <= stop_price:
            exit_price = stop_price; exit_date = day.get("date"); exit_reason = "TRAILING/ATR STOP"; break
        if not pd.isna(high) and high >= take_profit_price:
            exit_price = take_profit_price; exit_date = day.get("date"); exit_reason = "TAKE PROFIT"; break
        if j == end_idx:
            exit_price = close; exit_date = day.get("date"); exit_reason = "TIME STOP"
    if pd.isna(exit_price): return {}
    gross_ret = (exit_price / entry_price - 1) * 100
    return {"Ngày tín hiệu": row.get("date"), "Giá vào": entry_price, "Ngày thoát": exit_date, "Giá thoát": exit_price, "Lý do thoát": exit_reason, "Số ngày giữ": hold_days, "Lợi nhuận exit gốc %": gross_ret, "Lợi nhuận exit sau phí %": gross_ret - ROUNDTRIP_COST_PCT, "ATR stop price": atr_stop_price}


def generate_candidate_signal_dates(df: pd.DataFrame, strategy: str) -> pd.DataFrame:
    x = df.copy()
    if x.empty: return x
    if strategy == "MOMENTUM":
        mask = (x["close"] > x["ma20"]) & (x["ma5"] >= x["ma20"]) & (x["rsi"].between(45, 82)) & (x["ret5_pct"] > 0) & (x["dist_ma20_pct"].between(-5, 18))
    elif strategy == "BOTTOM":
        mask = (x["rsi"].between(25, 58)) & (x["drawdown20_pct"] <= -2) & (x["dist_ma20_pct"].between(-18, 10))
    else:
        mask = (x["close"] > x["ma20"]) | (x["rsi"].between(25, 58))
    return x[mask].copy()


def test_exit_engine(symbol: str, strategy: str) -> Tuple[Dict[str, Any], pd.DataFrame]:
    hist = load_symbol_history(symbol)
    if hist.empty or len(hist) < 100: return {}, pd.DataFrame()
    last_date = hist["date"].max(); start_date = last_date - pd.Timedelta(days=LOOKBACK_DAYS); cutoff = last_date - pd.Timedelta(days=EXCLUDE_RECENT_DAYS)
    hist = hist[(hist["date"] >= start_date) & (hist["date"] <= cutoff)].copy().reset_index(drop=True)
    signals = generate_candidate_signal_dates(hist, strategy)
    if signals.empty: return {}, pd.DataFrame()
    detail_rows = []
    for idx in signals.index.tolist():
        res = simulate_exit_for_signal(hist, int(idx))
        if res:
            res["Mã"] = symbol; res["Chiến lược"] = strategy; detail_rows.append(res)
    detail = pd.DataFrame(detail_rows)
    if detail.empty: return {}, detail
    summary = {"Exit samples": len(detail), "Exit lợi nhuận TB sau phí %": pct_mean(detail["Lợi nhuận exit sau phí %"]), "Exit winrate sau phí %": pct_winrate(detail["Lợi nhuận exit sau phí %"]), "Exit giữ TB ngày": pct_mean(detail["Số ngày giữ"]), "Take profit count": int((detail["Lý do thoát"] == "TAKE PROFIT").sum()), "Stop count": int((detail["Lý do thoát"] == "TRAILING/ATR STOP").sum()), "Time stop count": int((detail["Lý do thoát"] == "TIME STOP").sum())}
    return summary, detail


def calculate_correlation_block(selected: pd.DataFrame, histories: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    if selected.empty: return selected
    accepted_rows = []; accepted_symbols = []
    for _, row in selected.iterrows():
        sym = row["Mã"]; hist = histories.get(sym, pd.DataFrame())
        if hist.empty or "ret1_pct" not in hist.columns:
            accepted_rows.append(row); accepted_symbols.append(sym); continue
        keep = True
        for acc in accepted_symbols:
            h2 = histories.get(acc, pd.DataFrame())
            if h2.empty: continue
            a = hist[["date", "ret1_pct"]].dropna().tail(120); b = h2[["date", "ret1_pct"]].dropna().tail(120)
            merged = a.merge(b, on="date", suffixes=("_a", "_b"))
            if len(merged) < 30: continue
            corr = merged["ret1_pct_a"].corr(merged["ret1_pct_b"])
            if not pd.isna(corr) and corr >= CORRELATION_LIMIT:
                keep = False; break
        if keep:
            accepted_rows.append(row); accepted_symbols.append(sym)
    return pd.DataFrame(accepted_rows)


def compute_allocation(row: pd.Series, market_regime: str) -> float:
    score = to_num(row.get("Điểm V15.3", 50), 50); strategy = str(row.get("Chiến lược", "UNKNOWN")).upper(); best_regime = str(row.get("Regime tốt nhất", "KHÔNG XÁC ĐỊNH")).upper(); vol = to_num(row.get("Volatility20 %"), TARGET_VOL_PCT)
    score_weight = max(0.0, min(1.0, score / 100)); vol_adj = TARGET_VOL_PCT / max(vol, 0.5); vol_adj = max(0.35, min(1.25, vol_adj)); regime_adj = regime_allocation_multiplier(strategy, market_regime, best_regime)
    return float(max(0, min(MAX_WEIGHT_PER_STOCK, MAX_WEIGHT_PER_STOCK * score_weight * vol_adj * regime_adj)))


def build_risk_table(score_df: pd.DataFrame, market_regime: str) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame]]:
    histories = {}; rows = []
    for _, r in score_df.iterrows():
        sym = str(r.get("Mã", "")).upper().strip()
        if not sym: continue
        hist = load_symbol_history(sym); histories[sym] = hist
        vol = np.nan; atr_pct = np.nan
        if not hist.empty:
            last = hist.dropna(subset=["close"]).iloc[-1]
            vol = to_num(last.get("volatility20_pct")); atr_pct = to_num(last.get("atr_pct"))
        row = r.to_dict(); row["Volatility20 %"] = vol; row["ATR %"] = atr_pct; row["Tỷ trọng đề xuất thô"] = compute_allocation(pd.Series(row), market_regime); rows.append(row)
    out = pd.DataFrame(rows)
    if out.empty: return out, histories
    out = out[pd.to_numeric(out["Điểm V15.3"], errors="coerce").fillna(0) >= MIN_SCORE].copy()
    out = out.sort_values(["Điểm V15.3", "T+5 sau phí %"], ascending=[False, False]).head(PORTFOLIO_TOP_N * 3)
    filtered = calculate_correlation_block(out, histories)
    if filtered.empty: return filtered, histories
    filtered = filtered.head(PORTFOLIO_TOP_N).copy()
    cap = exposure_cap_for_regime(market_regime); total_raw = filtered["Tỷ trọng đề xuất thô"].sum(); scale = min(1.0, cap / total_raw) if total_raw > 0 else 0.0
    filtered["Tỷ trọng sau giới hạn"] = (filtered["Tỷ trọng đề xuất thô"] * scale).clip(lower=MIN_WEIGHT_PER_STOCK, upper=MAX_WEIGHT_PER_STOCK)
    if filtered["Tỷ trọng sau giới hạn"].sum() > cap:
        filtered["Tỷ trọng sau giới hạn"] = filtered["Tỷ trọng sau giới hạn"] / filtered["Tỷ trọng sau giới hạn"].sum() * cap
    filtered["Tiền mặt giữ lại"] = max(0.0, 1.0 - filtered["Tỷ trọng sau giới hạn"].sum())
    filtered["Regime thị trường hiện tại"] = market_regime; filtered["Max exposure theo regime"] = cap
    return filtered.reset_index(drop=True), histories


def simulate_portfolio_equity(risk_table: pd.DataFrame, exit_detail: pd.DataFrame) -> pd.DataFrame:
    if risk_table.empty or exit_detail.empty: return pd.DataFrame()
    weight_map = {(str(r["Mã"]), str(r["Chiến lược"])): to_num(r.get("Tỷ trọng sau giới hạn"), 0) for _, r in risk_table.iterrows()}
    detail = exit_detail.copy(); detail["Ngày tín hiệu"] = pd.to_datetime(detail["Ngày tín hiệu"], errors="coerce"); detail["Lợi nhuận exit sau phí %"] = pd.to_numeric(detail["Lợi nhuận exit sau phí %"], errors="coerce")
    rows = []
    for d, g in detail.groupby("Ngày tín hiệu"):
        port_ret = 0.0; exposure = 0.0; used = []
        for _, row in g.iterrows():
            key = (str(row.get("Mã")), str(row.get("Chiến lược"))); w = weight_map.get(key, 0.0)
            if w <= 0: continue
            r = to_num(row.get("Lợi nhuận exit sau phí %"), 0); port_ret += w * r; exposure += w; used.append(f"{key[0]}-{key[1]}:{w:.2f}")
        if exposure <= 0: continue
        rows.append({"Ngày tín hiệu": d, "Exposure": round(exposure, 3), "Lợi nhuận danh mục exit sau phí %": round(port_ret, 2), "Win danh mục": 1 if port_ret > 0 else 0, "Danh mục": ", ".join(used)})
    out = pd.DataFrame(rows)
    if out.empty: return out
    out = out.sort_values("Ngày tín hiệu").reset_index(drop=True)
    out["Equity giả lập"] = (1 + out["Lợi nhuận danh mục exit sau phí %"] / 100).cumprod()
    out["Drawdown giả lập %"] = (out["Equity giả lập"] / out["Equity giả lập"].cummax() - 1) * 100
    return out


def html_style() -> str:
    return """
<style>
body{font-family:Arial,sans-serif;background:#0f172a;color:#e5e7eb;padding:18px}
h2,h3{color:#fff}.note{background:#111827;border:1px solid #334155;border-radius:10px;padding:12px;margin:12px 0}.card{background:#111827;border:1px solid #334155;border-radius:12px;padding:12px;margin:14px 0;overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:12px;background:#111827}th{background:#1f2937;color:#fff;position:sticky;top:0}td,th{border:1px solid #334155;padding:7px;white-space:nowrap;vertical-align:top}tr:nth-child(even){background:#0b1220}
</style>
"""


def build_report(risk_table: pd.DataFrame, equity: pd.DataFrame, exit_summary: pd.DataFrame, market_regime: str) -> str:
    lines = ["✅ V15.4 PORTFOLIO RISK + EXIT ENGINE HOÀN TẤT", "", f"Thời gian chạy: {now_str()}", f"Regime thị trường hiện tại: {market_regime}", f"Max exposure theo regime: {exposure_cap_for_regime(market_regime):.0%}", "", "Nâng cấp đã áp dụng:", "1. Volatility targeting: mã biến động mạnh thì giảm tỷ trọng.", "2. Max exposure: giới hạn tổng tiền được mua theo trạng thái thị trường.", "3. Regime cash mode: thị trường xấu thì giữ nhiều tiền mặt hơn.", "4. Correlation filter: hạn chế chọn các mã đi cùng nhau quá mạnh.", "5. Exit simulation: trailing stop, take profit, ATR stop, time stop.", "6. Multi-regime weighting: regime ảnh hưởng trực tiếp tới tỷ trọng.", ""]
    if not equity.empty:
        avg_ret = pct_mean(equity["Lợi nhuận danh mục exit sau phí %"]); win = pct_winrate(equity["Lợi nhuận danh mục exit sau phí %"]); max_dd = to_num(equity["Drawdown giả lập %"].min(), 0)
        lines += ["PORTFOLIO SAU RISK ENGINE:", f"- Số phiên mô phỏng: {len(equity)}", f"- Lợi nhuận TB sau phí: {avg_ret:.2f}%", f"- Winrate danh mục: {win:.1f}%", f"- Max drawdown giả lập: {max_dd:.2f}%", ""]
    lines.append("DANH MỤC ĐỀ XUẤT HIỆN TẠI:")
    if risk_table.empty: lines.append("Không có mã đủ điều kiện.")
    else:
        for _, r in risk_table.iterrows():
            lines += ["", f"🔹 {r.get('Mã','')} | {r.get('Chiến lược','')} | điểm {r.get('Điểm V15.3','')}", f"Tỷ trọng: {safe_round(to_num(r.get('Tỷ trọng sau giới hạn')), 3)} | Vol20: {safe_round(r.get('Volatility20 %'), 2)}% | ATR: {safe_round(r.get('ATR %'), 2)}%", f"Regime tốt nhất: {r.get('Regime tốt nhất','')} | T+5 sau phí: {r.get('T+5 sau phí %','')}%"]
    return "\n".join(lines)


def write_html(risk_table: pd.DataFrame, exit_summary: pd.DataFrame, exit_detail: pd.DataFrame, equity: pd.DataFrame, market: pd.DataFrame):
    risk_html = risk_table.to_html(index=False, escape=True) if not risk_table.empty else "<p>Không có mã đủ điều kiện.</p>"
    exit_sum_html = exit_summary.to_html(index=False, escape=True) if not exit_summary.empty else "<p>Không có summary exit.</p>"
    exit_detail_html = exit_detail.head(500).to_html(index=False, escape=True) if not exit_detail.empty else "<p>Không có detail exit.</p>"
    equity_html = equity.tail(200).to_html(index=False, escape=True) if not equity.empty else "<p>Không có equity simulation.</p>"
    market_html = market.tail(50).to_html(index=False, escape=True) if market is not None and not market.empty else "<p>Không có dữ liệu market.</p>"
    html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'><title>V15.4 Portfolio Risk Exit Engine</title>{html_style()}</head><body><h2>V15.4 - PORTFOLIO RISK + EXIT ENGINE</h2><div class='note'><b>Generated:</b> {now_str()}<br><b>Lookback:</b> {LOOKBACK_DAYS} ngày<br><b>Roundtrip cost:</b> {ROUNDTRIP_COST_PCT:.2f}%<br><b>Take profit:</b> {TAKE_PROFIT_PCT:.2f}%<br><b>Trailing stop:</b> {TRAILING_STOP_PCT:.2f}%<br><b>ATR stop:</b> {ATR_STOP_MULT:.2f} ATR<br><b>Max hold:</b> {MAX_HOLD_DAYS} ngày</div><div class='card'><h3>1. DANH MỤC ĐỀ XUẤT SAU RISK ENGINE</h3>{risk_html}</div><div class='card'><h3>2. PORTFOLIO EQUITY SIMULATION</h3>{equity_html}</div><div class='card'><h3>3. EXIT SUMMARY</h3>{exit_sum_html}</div><div class='card'><h3>4. MARKET REGIME</h3>{market_html}</div><div class='card'><h3>5. EXIT DETAIL</h3>{exit_detail_html}</div></body></html>"""
    Path(OUT_HTML).write_text(html, encoding="utf-8")


def main():
    print("V15.4 PORTFOLIO RISK + EXIT ENGINE START", flush=True)
    market = load_market_index(); market_regime = current_market_regime(market); print(f"MARKET REGIME: {market_regime}", flush=True)
    score_df = load_v153_scores()
    if score_df.empty: score_df = fallback_symbols()
    if score_df.empty:
        empty = pd.DataFrame([{"Trạng thái": "KHÔNG CÓ DỮ LIỆU"}]); empty.to_csv(OUT_CSV, index=False, encoding="utf-8-sig"); Path(OUT_TXT).write_text("Không có dữ liệu để chạy V15.4.", encoding="utf-8"); print("DONE EMPTY", flush=True); return
    risk_table, histories = build_risk_table(score_df, market_regime)
    exit_summary_rows = []; exit_details = []
    for _, row in score_df.iterrows():
        sym = str(row.get("Mã", "")).upper().strip(); strategy = str(row.get("Chiến lược", "UNKNOWN")).upper().strip()
        if not sym or strategy not in ["MOMENTUM", "BOTTOM"]: continue
        summary, detail = test_exit_engine(sym, strategy)
        if summary: summary["Mã"] = sym; summary["Chiến lược"] = strategy; exit_summary_rows.append(summary)
        if detail is not None and not detail.empty: exit_details.append(detail)
    exit_summary = pd.DataFrame(exit_summary_rows); exit_detail = pd.concat(exit_details, ignore_index=True, sort=False) if exit_details else pd.DataFrame()
    equity = simulate_portfolio_equity(risk_table, exit_detail)
    risk_table.to_csv(OUT_CSV, index=False, encoding="utf-8-sig"); exit_detail.to_csv(OUT_DETAIL_CSV, index=False, encoding="utf-8-sig"); equity.to_csv(OUT_EQUITY_CSV, index=False, encoding="utf-8-sig")
    report = build_report(risk_table, equity, exit_summary, market_regime); Path(OUT_TXT).write_text(report, encoding="utf-8"); write_html(risk_table, exit_summary, exit_detail, equity, market)
    print(report, flush=True); print(f"OK: wrote {OUT_CSV}", flush=True); print(f"OK: wrote {OUT_DETAIL_CSV}", flush=True); print(f"OK: wrote {OUT_EQUITY_CSV}", flush=True); print(f"OK: wrote {OUT_HTML}", flush=True); print(f"OK: wrote {OUT_TXT}", flush=True)


if __name__ == "__main__":
    main()
