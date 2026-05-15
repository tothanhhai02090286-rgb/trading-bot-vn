# -*- coding: utf-8 -*-
"""
============================================================
V15.4.1 PORTFOLIO RISK + EXIT ENGINE VI - FIXED BUILD
============================================================

Vai trò:
- Đọc output V15.3 PRO.
- Lọc setup có edge yếu / expectancy âm.
- Mô phỏng exit chặt hơn:
  + trailing stop
  + take profit
  + ATR stop
  + time stop
- Giảm exposure khi risk-off.
- Position sizing theo risk thật, không chia đều.
- Correlation filter nghiêm hơn.
- Giới hạn nhóm/ngành.
- Export đúng output cho V15.5.

Input bắt buộc:
- v153_pro_research.csv
- v153_pro_research_detail.csv
- v153_pro_research_portfolio.csv nếu có
- cache_stock/*.csv nếu có để tính volatility / ATR / correlation

Output:
- v1541_portfolio_risk_exit.csv
- v1541_portfolio_risk_exit_detail.csv
- v1541_portfolio_equity.csv
- v1541_portfolio_risk_exit.html
- v1541_portfolio_risk_exit_report.txt

Lưu ý kiến trúc:
- Không tự scan tín hiệu mới.
- Không thêm indicator retail mới.
- Không fallback sang V17/watchlist.
- Nếu thiếu v153_pro_research.csv thì báo lỗi rõ.
============================================================
"""

import os
import glob
import math
import warnings
from datetime import datetime

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

SYSTEM_VERSION = "V15.4.1_FIXED_RISK_EXIT_ENGINE_VI"

INPUT_RESEARCH = "v153_pro_research.csv"
INPUT_RESEARCH_DETAIL = "v153_pro_research_detail.csv"
INPUT_RESEARCH_PORTFOLIO = "v153_pro_research_portfolio.csv"
CACHE_DIR = "cache_stock"

OUTPUT_MAIN = "v1541_portfolio_risk_exit.csv"
OUTPUT_DETAIL = "v1541_portfolio_risk_exit_detail.csv"
OUTPUT_EQUITY = "v1541_portfolio_equity.csv"
OUTPUT_HTML = "v1541_portfolio_risk_exit.html"
OUTPUT_REPORT = "v1541_portfolio_risk_exit_report.txt"

# ============================================================
# THAM SỐ RISK ĐÃ FIX
# ============================================================

MIN_EXPECTANCY_AFTER_FEE = 0.05        # Không nhận expectancy âm / gần 0
MIN_WINRATE_AFTER_FEE = 35.0           # Không nhận winrate quá thấp
MAX_SINGLE_TRADE_DD = -12.0            # Loại setup có loss/exit quá xấu
MAX_ATR_PCT = 8.0                      # ATR quá cao thì giảm/loại
MAX_VOL20_PCT = 10.0                   # Volatility quá cao thì giảm/loại

MAX_POSITION_WEIGHT = 0.20             # Giới hạn 1 mã
MIN_POSITION_WEIGHT = 0.03
MAX_TOTAL_EXPOSURE_RISK_ON = 1.00
MAX_TOTAL_EXPOSURE_SIDEWAY = 0.55
MAX_TOTAL_EXPOSURE_RISK_OFF = 0.20

MAX_SECTOR_WEIGHT = 0.35
MAX_CORRELATION = 0.75

TRAILING_STOP_PCT = 5.0
TAKE_PROFIT_PCT = 8.0
ATR_STOP_MULTIPLIER = 1.6
TIME_STOP_DAYS = 5

FEE_SLIPPAGE_PCT = 0.35


# ============================================================
# TIỆN ÍCH
# ============================================================

def log(msg):
    print(f"[V15.4.1 FIX] {msg}")


def require_file(path):
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"THIẾU INPUT BẮT BUỘC: {path}. "
            f"V15.4.1 chỉ đọc output V15.3, không fallback sang watchlist/V17/cache."
        )


def read_csv_smart(path):
    for enc in ["utf-8-sig", "utf-8", "cp1258", "latin1"]:
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            pass
    return pd.read_csv(path)


def to_num(x, default=0.0):
    try:
        if pd.isna(x):
            return default
        if isinstance(x, str):
            x = x.replace("%", "").replace(",", ".").strip()
        return float(x)
    except Exception:
        return default


def normalize_text(x):
    if pd.isna(x):
        return "UNKNOWN"
    return str(x).strip().upper()


def pick_col(df, candidates, required=False, label=""):
    for c in candidates:
        if c in df.columns:
            return c
    if required:
        raise ValueError(f"Thiếu cột bắt buộc: {label or candidates}")
    return None


def safe_symbol(x):
    return str(x).strip().upper()


def build_sector_map(symbols):
    banks = {"VCB", "BID", "CTG", "MBB", "TCB", "ACB", "SHB", "HDB", "STB", "VPB", "LPB", "EIB", "MSB", "VIB"}
    oil = {"PVS", "PVD", "BSR", "PLX", "GAS", "OIL"}
    real = {"VIC", "VHM", "NVL", "DXG", "KDH", "NLG", "PDR", "CEO", "DIG"}
    steel = {"HPG", "HSG", "NKG", "VGS"}
    securities = {"SSI", "VND", "VCI", "HCM", "SHS", "MBS", "FTS", "CTS"}
    retail = {"MWG", "FRT", "DGW", "PNJ"}
    construction = {"CTD", "HHV", "CII", "FCN", "LCG"}

    out = {}
    for s in symbols:
        if s in banks:
            out[s] = "BANK"
        elif s in oil:
            out[s] = "OIL_GAS"
        elif s in real:
            out[s] = "REAL_ESTATE"
        elif s in steel:
            out[s] = "STEEL"
        elif s in securities:
            out[s] = "SECURITIES"
        elif s in retail:
            out[s] = "RETAIL"
        elif s in construction:
            out[s] = "CONSTRUCTION"
        else:
            out[s] = "OTHER"
    return out


# ============================================================
# LOAD PRICE DATA
# ============================================================

def detect_price_columns(df):
    date_col = pick_col(df, ["Date", "date", "time", "datetime", "Ngày", "TradingDate"])
    close_col = pick_col(df, ["close", "Close", "Đóng cửa", "close_price", "ClosePrice"])
    high_col = pick_col(df, ["high", "High", "Cao nhất", "high_price", "HighPrice"])
    low_col = pick_col(df, ["low", "Low", "Thấp nhất", "low_price", "LowPrice"])
    return date_col, close_col, high_col, low_col


def load_price_data(symbol):
    candidates = [
        os.path.join(CACHE_DIR, f"{symbol}.csv"),
        os.path.join(CACHE_DIR, f"{symbol.upper()}.csv"),
        os.path.join(CACHE_DIR, f"{symbol.lower()}.csv"),
    ]

    for p in candidates:
        if os.path.exists(p):
            try:
                df = read_csv_smart(p)
                date_col, close_col, high_col, low_col = detect_price_columns(df)

                if close_col is None:
                    return None

                out = pd.DataFrame()
                if date_col:
                    out["Ngày"] = pd.to_datetime(df[date_col], errors="coerce")
                else:
                    out["Ngày"] = pd.RangeIndex(len(df))

                out["Close"] = pd.to_numeric(df[close_col], errors="coerce")
                out["High"] = pd.to_numeric(df[high_col], errors="coerce") if high_col else out["Close"]
                out["Low"] = pd.to_numeric(df[low_col], errors="coerce") if low_col else out["Close"]
                out = out.dropna(subset=["Close"]).reset_index(drop=True)
                return out
            except Exception:
                return None

    return None


def compute_price_risk(symbol):
    df = load_price_data(symbol)

    if df is None or len(df) < 30:
        return {
            "Volatility20 %": 5.0,
            "ATR %": 5.0,
            "Có dữ liệu giá": False
        }

    close = df["Close"]
    ret = close.pct_change()
    vol20 = ret.tail(20).std() * math.sqrt(20) * 100

    tr1 = df["High"] - df["Low"]
    tr2 = (df["High"] - close.shift(1)).abs()
    tr3 = (df["Low"] - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    atr_pct = atr / close.iloc[-1] * 100 if close.iloc[-1] > 0 else 5.0

    return {
        "Volatility20 %": round(float(vol20), 2) if np.isfinite(vol20) else 5.0,
        "ATR %": round(float(atr_pct), 2) if np.isfinite(atr_pct) else 5.0,
        "Có dữ liệu giá": True
    }


def build_return_matrix(symbols):
    data = {}

    for s in symbols:
        df = load_price_data(s)
        if df is not None and len(df) >= 40:
            data[s] = df["Close"].pct_change().tail(60).reset_index(drop=True)

    if not data:
        return pd.DataFrame()

    mat = pd.DataFrame(data)
    return mat.dropna(how="all")


# ============================================================
# REGIME / EXPOSURE
# ============================================================

def detect_current_regime(portfolio_df=None, research_df=None):
    if portfolio_df is not None and "Drawdown giả lập %" in portfolio_df.columns:
        dd = to_num(portfolio_df["Drawdown giả lập %"].iloc[-1])
        if dd <= -15:
            return "RISK OFF"
        if dd <= -8:
            return "SIDEWAY"

    if research_df is not None:
        regime_col = pick_col(research_df, ["Regime tốt nhất", "Regime thị trường hiện tại", "Market Regime"])
        if regime_col:
            vals = research_df[regime_col].astype(str).str.upper()
            if vals.str.contains("RISK OFF").mean() > 0.40:
                return "RISK OFF"
            if vals.str.contains("SIDEWAY").mean() > 0.40:
                return "SIDEWAY"
            if vals.str.contains("RISK ON").mean() > 0.30:
                return "RISK ON"

    return "SIDEWAY"


def regime_exposure(regime):
    r = normalize_text(regime)
    if "RISK OFF" in r:
        return MAX_TOTAL_EXPOSURE_RISK_OFF
    if "RISK ON" in r:
        return MAX_TOTAL_EXPOSURE_RISK_ON
    return MAX_TOTAL_EXPOSURE_SIDEWAY


# ============================================================
# EXIT SIMULATION
# ============================================================

def exit_adjust_return(raw_return, atr_pct, regime):
    """
    Không tạo tín hiệu mới.
    Chỉ mô phỏng cách thoát lệnh chặt hơn từ return V15.3.
    """
    r = to_num(raw_return)
    atr = max(to_num(atr_pct), 0.1)

    atr_stop = -ATR_STOP_MULTIPLIER * atr
    trailing_stop = -TRAILING_STOP_PCT
    stop_level = max(atr_stop, trailing_stop)

    take_profit = TAKE_PROFIT_PCT

    if "RISK OFF" in normalize_text(regime):
        stop_level = max(stop_level, -3.0)
        take_profit = 5.0

    if r <= stop_level:
        exit_ret = stop_level
        exit_reason = "ATR/TRAILING STOP"

    elif r >= take_profit:
        exit_ret = take_profit
        exit_reason = "TAKE PROFIT"

    else:
        # time stop giữ return V15.3 nhưng trừ phí/slippage
        exit_ret = r
        exit_reason = "TIME STOP"

    exit_after_fee = exit_ret - FEE_SLIPPAGE_PCT

    return round(exit_after_fee, 3), exit_reason


# ============================================================
# BUILD CANDIDATES
# ============================================================

def build_candidates(research_df):
    symbol_col = pick_col(research_df, ["Mã", "Ma", "Symbol", "Ticker"], True, "Mã")
    strategy_col = pick_col(research_df, ["Chiến lược", "Strategy"], False)
    score_col = pick_col(research_df, ["Điểm V15.3", "Điểm", "Score", "Research Score"], False)
    ret_col = pick_col(research_df, ["Lợi nhuận TB T+5 sau phí %", "T+5 sau phí %", "Return T+5 sau phí %"], True, "Lợi nhuận TB T+5 sau phí %")
    win_col = pick_col(research_df, ["Winrate T+5 sau phí %", "Winrate sau phí %", "Winrate %"], True, "Winrate T+5 sau phí %")
    regime_col = pick_col(research_df, ["Regime tốt nhất", "Best Regime", "Regime"], False)

    rows = []

    for _, row in research_df.iterrows():
        symbol = safe_symbol(row[symbol_col])
        if not symbol or symbol == "NAN":
            continue

        strategy = row[strategy_col] if strategy_col else "UNKNOWN"
        score = to_num(row[score_col], 50.0) if score_col else 50.0
        avg_ret = to_num(row[ret_col])
        winrate = to_num(row[win_col])
        best_regime = row[regime_col] if regime_col else "UNKNOWN"

        price_risk = compute_price_risk(symbol)
        vol20 = price_risk["Volatility20 %"]
        atr = price_risk["ATR %"]

        exit_ret, exit_reason = exit_adjust_return(avg_ret, atr, best_regime)

        expectancy_ok = exit_ret >= MIN_EXPECTANCY_AFTER_FEE
        win_ok = winrate >= MIN_WINRATE_AFTER_FEE
        atr_ok = atr <= MAX_ATR_PCT
        vol_ok = vol20 <= MAX_VOL20_PCT
        dd_ok = exit_ret >= MAX_SINGLE_TRADE_DD

        pass_filter = expectancy_ok and win_ok and atr_ok and vol_ok and dd_ok

        rows.append({
            "Mã": symbol,
            "Chiến lược": strategy,
            "Điểm V15.3": round(score, 2),
            "Regime tốt nhất": normalize_text(best_regime),
            "T+5 sau phí %": round(avg_ret, 3),
            "T+5 exit sau phí %": exit_ret,
            "Winrate sau phí %": round(winrate, 2),
            "Volatility20 %": round(vol20, 2),
            "ATR %": round(atr, 2),
            "Exit reason": exit_reason,
            "Expectancy OK": expectancy_ok,
            "Winrate OK": win_ok,
            "ATR OK": atr_ok,
            "Volatility OK": vol_ok,
            "Drawdown Trade OK": dd_ok,
            "Pass Risk Filter": pass_filter,
            "Có dữ liệu giá": price_risk["Có dữ liệu giá"]
        })

    out = pd.DataFrame(rows)

    if len(out) == 0:
        raise ValueError("Không có mã hợp lệ sau khi đọc V15.3.")

    return out


def risk_position_sizing(df):
    work = df.copy()

    # Chỉ lấy mã pass filter
    work = work[work["Pass Risk Filter"] == True].copy()

    if work.empty:
        # Nếu không có mã nào pass, giữ top tốt nhất nhưng allocation = 0 để downstream thấy trạng thái phòng thủ.
        return pd.DataFrame(columns=[
            "Mã", "Chiến lược", "Điểm V15.3", "Regime tốt nhất", "T+5 sau phí %",
            "Winrate sau phí %", "Volatility20 %", "ATR %", "Tỷ trọng đề xuất thô",
            "Tỷ trọng sau giới hạn", "Sector", "Ghi chú risk"
        ])

    work["Score factor"] = work["Điểm V15.3"] / 100.0
    work["Expectancy factor"] = np.maximum(work["T+5 exit sau phí %"], 0.0) / 5.0
    work["Winrate factor"] = work["Winrate sau phí %"] / 100.0
    work["Risk factor"] = 1.0 / (1.0 + work["Volatility20 %"] + work["ATR %"])

    work["Raw score"] = (
        work["Score factor"]
        * work["Expectancy factor"]
        * work["Winrate factor"]
        * work["Risk factor"]
    )

    total_score = work["Raw score"].sum()

    if total_score <= 0:
        work["Tỷ trọng đề xuất thô"] = 0.0
    else:
        work["Tỷ trọng đề xuất thô"] = work["Raw score"] / total_score

    work["Tỷ trọng sau giới hạn"] = work["Tỷ trọng đề xuất thô"].clip(
        lower=MIN_POSITION_WEIGHT,
        upper=MAX_POSITION_WEIGHT
    )

    sector_map = build_sector_map(work["Mã"].tolist())
    work["Sector"] = work["Mã"].map(sector_map).fillna("OTHER")

    return work


def apply_correlation_filter(df):
    if df.empty:
        return df

    mat = build_return_matrix(df["Mã"].tolist())
    if mat.empty or mat.shape[1] <= 1:
        df["Correlation Filter"] = "NO_PRICE_MATRIX"
        return df

    corr = mat.corr().fillna(0)

    selected = []
    removed = set()

    ranked = df.sort_values(
        by=["Tỷ trọng sau giới hạn", "Điểm V15.3", "T+5 exit sau phí %"],
        ascending=False
    )

    for _, row in ranked.iterrows():
        s = row["Mã"]

        too_corr = False

        for keep in selected:
            if s in corr.index and keep in corr.columns:
                if corr.loc[s, keep] >= MAX_CORRELATION:
                    too_corr = True
                    break

        if too_corr:
            removed.add(s)
        else:
            selected.append(s)

    out = df.copy()
    out["Correlation Filter"] = np.where(out["Mã"].isin(removed), "LOẠI DO TƯƠNG QUAN CAO", "OK")
    out = out[out["Correlation Filter"] == "OK"].copy()

    return out


def apply_sector_limit(df):
    if df.empty:
        return df

    adjusted = []

    sector_sum = df.groupby("Sector")["Tỷ trọng sau giới hạn"].sum().to_dict()

    for _, row in df.iterrows():
        w = row["Tỷ trọng sau giới hạn"]
        sector = row["Sector"]
        ssum = sector_sum.get(sector, 0.0)

        if ssum > MAX_SECTOR_WEIGHT and ssum > 0:
            w = w * MAX_SECTOR_WEIGHT / ssum

        adjusted.append(w)

    df["Tỷ trọng sau giới hạn"] = adjusted

    total = df["Tỷ trọng sau giới hạn"].sum()
    if total > 0:
        df["Tỷ trọng sau giới hạn"] = df["Tỷ trọng sau giới hạn"] / total

    return df


# ============================================================
# EQUITY SIMULATION
# ============================================================

def build_equity_curve(portfolio_df, selected_df, market_regime):
    exposure = regime_exposure(market_regime)

    rows = []

    if portfolio_df is not None and "Ngày tín hiệu" in portfolio_df.columns:
        date_col = "Ngày tín hiệu"
        ret_col = pick_col(
            portfolio_df,
            ["Lợi nhuận danh mục T+5 sau phí %", "Lợi nhuận danh mục exit sau phí %"],
            False
        )
        win_col = pick_col(portfolio_df, ["Win danh mục"], False)
        symbols_col = pick_col(portfolio_df, ["Danh sách mã", "Danh mục"], False)

        equity = 100.0
        peak = 100.0

        if ret_col is None:
            return pd.DataFrame()

        for _, row in portfolio_df.iterrows():
            raw_ret = to_num(row[ret_col])

            # Fix risk: chỉ cho danh mục chịu exposure theo regime
            adjusted_ret = raw_ret * exposure

            equity = equity * (1.0 + adjusted_ret / 100.0)
            peak = max(peak, equity)
            dd = (equity / peak - 1.0) * 100.0 if peak > 0 else 0.0

            rows.append({
                "Ngày tín hiệu": row[date_col],
                "Exposure": round(exposure, 4),
                "Lợi nhuận danh mục exit sau phí %": round(adjusted_ret, 3),
                "Win danh mục": int(row[win_col]) if win_col else int(adjusted_ret > 0),
                "Danh mục": row[symbols_col] if symbols_col else ",".join(selected_df["Mã"].tolist()),
                "Equity giả lập": round(equity, 4),
                "Drawdown giả lập %": round(dd, 3)
            })

        return pd.DataFrame(rows)

    # Fallback chỉ khi thiếu portfolio file, vẫn dựa trên V15.3 main chứ không dùng watchlist/cache.
    equity = 100.0
    peak = 100.0

    for i, row in selected_df.iterrows():
        r = to_num(row["T+5 exit sau phí %"]) * to_num(row["Tỷ trọng sau giới hạn"]) * exposure
        equity = equity * (1.0 + r / 100.0)
        peak = max(peak, equity)
        dd = (equity / peak - 1.0) * 100.0 if peak > 0 else 0.0

        rows.append({
            "Ngày tín hiệu": i,
            "Exposure": round(exposure, 4),
            "Lợi nhuận danh mục exit sau phí %": round(r, 3),
            "Win danh mục": int(r > 0),
            "Danh mục": row["Mã"],
            "Equity giả lập": round(equity, 4),
            "Drawdown giả lập %": round(dd, 3)
        })

    return pd.DataFrame(rows)


# ============================================================
# MAIN ENGINE
# ============================================================

def run_engine():
    log("Bắt đầu chạy V15.4.1 FIXED...")

    require_file(INPUT_RESEARCH)

    research_df = read_csv_smart(INPUT_RESEARCH)

    detail_df = read_csv_smart(INPUT_RESEARCH_DETAIL) if os.path.exists(INPUT_RESEARCH_DETAIL) else pd.DataFrame()

    portfolio_df = read_csv_smart(INPUT_RESEARCH_PORTFOLIO) if os.path.exists(INPUT_RESEARCH_PORTFOLIO) else None

    market_regime = detect_current_regime(portfolio_df, research_df)

    log(f"Regime danh mục hiện tại: {market_regime}")

    candidates = build_candidates(research_df)

    selected = risk_position_sizing(candidates)

    selected = apply_correlation_filter(selected)

    selected = apply_sector_limit(selected)

    exposure = regime_exposure(market_regime)

    if selected.empty:
        log("Không có mã nào pass risk filter. Xuất trạng thái phòng thủ.")

        main_df = candidates.sort_values(
            by=["T+5 exit sau phí %", "Winrate sau phí %", "Điểm V15.3"],
            ascending=False
        ).head(10).copy()

        main_df["Tỷ trọng đề xuất thô"] = 0.0
        main_df["Tỷ trọng sau giới hạn"] = 0.0
        main_df["Sector"] = build_sector_map(main_df["Mã"].tolist()).values()
        main_df["Ghi chú risk"] = "KHÔNG PASS FILTER - GIỮ TIỀN"

    else:
        main_df = selected.copy()
        main_df["Ghi chú risk"] = "PASS RISK FILTER"

    equity_df = build_equity_curve(portfolio_df, main_df, market_regime)

    if equity_df.empty:
        equity_df = pd.DataFrame([{
            "Ngày tín hiệu": datetime.now().strftime("%Y-%m-%d"),
            "Exposure": exposure,
            "Lợi nhuận danh mục exit sau phí %": 0.0,
            "Win danh mục": 0,
            "Danh mục": ",".join(main_df["Mã"].astype(str).tolist()),
            "Equity giả lập": 100.0,
            "Drawdown giả lập %": 0.0
        }])

    # Chuẩn cột output chính tương thích V15.5
    output_cols = [
        "Mã",
        "Chiến lược",
        "Điểm V15.3",
        "Regime tốt nhất",
        "T+5 sau phí %",
        "Winrate sau phí %",
        "Volatility20 %",
        "ATR %",
        "Tỷ trọng đề xuất thô",
        "Tỷ trọng sau giới hạn"
    ]

    for c in output_cols:
        if c not in main_df.columns:
            main_df[c] = 0.0 if c not in ["Mã", "Chiến lược", "Regime tốt nhất"] else "UNKNOWN"

    main_out = main_df[output_cols + [
        "T+5 exit sau phí %",
        "Exit reason",
        "Sector",
        "Ghi chú risk"
    ]].copy()

    main_out = main_out.sort_values(
        by=["Tỷ trọng sau giới hạn", "Điểm V15.3", "T+5 exit sau phí %"],
        ascending=False
    )

    detail_out = candidates.copy()

    # Báo cáo
    avg_ret = equity_df["Lợi nhuận danh mục exit sau phí %"].mean()
    winrate_port = equity_df["Win danh mục"].mean() * 100 if len(equity_df) else 0.0
    max_dd = equity_df["Drawdown giả lập %"].min() if "Drawdown giả lập %" in equity_df.columns else 0.0

    report = []
    report.append("=" * 60)
    report.append("V15.4.1 PORTFOLIO RISK + EXIT ENGINE - FIXED")
    report.append("=" * 60)
    report.append(f"Version: {SYSTEM_VERSION}")
    report.append(f"Generated: {datetime.now()}")
    report.append("")
    report.append("CÁC FIX TRỌNG TÂM:")
    report.append("1. Không nhận setup có expectancy âm.")
    report.append("2. Không nhận mã có winrate quá thấp.")
    report.append("3. Risk-off giảm exposure mạnh.")
    report.append("4. Exit chặt hơn: ATR stop, trailing stop, take profit, time stop.")
    report.append("5. Correlation filter nghiêm hơn.")
    report.append("6. Giới hạn nhóm/ngành.")
    report.append("7. Position sizing theo risk thật.")
    report.append("")
    report.append("PORTFOLIO SAU RISK ENGINE:")
    report.append(f"- Regime hiện tại: {market_regime}")
    report.append(f"- Exposure áp dụng: {round(exposure, 4)}")
    report.append(f"- Số mã pass filter: {len(main_out[main_out['Tỷ trọng sau giới hạn'] > 0])}")
    report.append(f"- Số phiên mô phỏng: {len(equity_df)}")
    report.append(f"- Lợi nhuận TB danh mục sau exit/phí: {round(avg_ret, 3)}%")
    report.append(f"- Winrate danh mục: {round(winrate_port, 2)}%")
    report.append(f"- Max drawdown giả lập: {round(max_dd, 2)}%")
    report.append("")
    report.append("DANH MỤC ĐỀ XUẤT HIỆN TẠI:")

    if main_out.empty:
        report.append("- Không có mã pass filter.")
    else:
        for _, row in main_out.head(15).iterrows():
            report.append(
                f"◆ {row['Mã']} | {row['Chiến lược']} | điểm {row['Điểm V15.3']} | "
                f"Tỷ trọng: {round(to_num(row['Tỷ trọng sau giới hạn']), 4)} | "
                f"Vol20: {row['Volatility20 %']}% | ATR: {row['ATR %']}% | "
                f"Exit sau phí: {row['T+5 exit sau phí %']}% | {row['Ghi chú risk']}"
            )

    report_text = "\n".join(report)

    html = f"""
<html>
<head>
<meta charset="utf-8">
<title>V15.4.1 Fixed Portfolio Risk Exit</title>
<style>
body {{ font-family: Arial; margin: 20px; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 25px; }}
th, td {{ border: 1px solid #ccc; padding: 7px; text-align: center; }}
th {{ background: #efefef; }}
.good {{ color: green; font-weight: bold; }}
.bad {{ color: red; font-weight: bold; }}
</style>
</head>
<body>
<h1>V15.4.1 Portfolio Risk + Exit Engine - Fixed</h1>
<h2>Trạng thái danh mục</h2>
<ul>
<li>Regime hiện tại: <b>{market_regime}</b></li>
<li>Exposure áp dụng: <b>{round(exposure, 4)}</b></li>
<li>Lợi nhuận TB danh mục sau exit/phí: <b>{round(avg_ret, 3)}%</b></li>
<li>Winrate danh mục: <b>{round(winrate_port, 2)}%</b></li>
<li>Max drawdown giả lập: <b>{round(max_dd, 2)}%</b></li>
</ul>

<h2>Danh mục sau risk filter</h2>
{main_out.to_html(index=False)}

<h2>Chi tiết risk filter</h2>
{detail_out.to_html(index=False)}

<h2>Equity curve</h2>
{equity_df.tail(100).to_html(index=False)}
</body>
</html>
"""

    main_out.to_csv(OUTPUT_MAIN, index=False, encoding="utf-8-sig")
    detail_out.to_csv(OUTPUT_DETAIL, index=False, encoding="utf-8-sig")
    equity_df.to_csv(OUTPUT_EQUITY, index=False, encoding="utf-8-sig")

    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        f.write(report_text)

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    log("Đã export output V15.4.1 FIXED.")
    log(f"Main: {OUTPUT_MAIN}")
    log(f"Equity: {OUTPUT_EQUITY}")

    print(report_text)

    return main_out, detail_out, equity_df


if __name__ == "__main__":
    run_engine()
