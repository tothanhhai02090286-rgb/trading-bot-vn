
# -*- coding: utf-8 -*-
"""
========================================================
V15.5 EQUITY SURVIVAL ENGINE VI
========================================================

Vai trò:
- Dynamic exposure
- Equity curve protection
- Portfolio kill switch
- Adaptive position sizing
- Sector heat control
- Recovery mode

Input:
- v1541_portfolio_risk_exit.csv
- v1541_portfolio_equity.csv

Output:
- v155_equity_survival_allocation.csv
- v155_equity_survival_equity.csv
- v155_equity_survival_report.txt
- v155_equity_survival.html

Lưu ý:
- Không scan tín hiệu mới
- Không thêm indicator retail
- Không override signal layer
- Chỉ là survival / allocation engine
========================================================
"""

import os
import sys
import math
import warnings
from datetime import datetime

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

SYSTEM_VERSION = "V15.5_EQUITY_SURVIVAL_ENGINE_VI"


# ========================================================
# CONFIG
# ========================================================

INPUT_RISK_EXIT = "v1541_portfolio_risk_exit.csv"
INPUT_EQUITY = "v1541_portfolio_equity.csv"

OUTPUT_ALLOCATION = "v155_equity_survival_allocation.csv"
OUTPUT_EQUITY = "v155_equity_survival_equity.csv"
OUTPUT_REPORT = "v155_equity_survival_report.txt"
OUTPUT_HTML = "v155_equity_survival.html"

# Exposure theo regime
REGIME_EXPOSURE_MAP = {
    "RISK ON": 1.00,
    "RISK ON MẠNH": 1.00,
    "SIDEWAY": 0.55,
    "RISK OFF": 0.20
}

# Drawdown protection
DRAW_DOWN_WARNING = 5.0
DRAW_DOWN_STRONG = 10.0
DRAW_DOWN_KILL = 15.0

# Recovery mode
RECOVERY_LOSS_STREAK = 3

# Sector heat limit
MAX_SECTOR_WEIGHT = 0.35

# Allocation guard
MIN_POSITION_WEIGHT = 0.02
MAX_POSITION_WEIGHT = 0.25

# ========================================================
# UTIL
# ========================================================

def log(msg):
    print(f"[V15.5] {msg}")


def safe_read_csv(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Không tìm thấy file input: {path}")

    return pd.read_csv(path)


def normalize_text(x):
    if pd.isna(x):
        return "UNKNOWN"

    return str(x).strip().upper()


def detect_market_regime(df):
    if "Regime thị trường hiện tại" not in df.columns:
        return "SIDEWAY"

    regime = df["Regime thị trường hiện tại"].iloc[0]
    regime = normalize_text(regime)

    if "RISK ON" in regime:
        return "RISK ON"

    if "RISK OFF" in regime:
        return "RISK OFF"

    return "SIDEWAY"


def calculate_equity_state(equity_df):
    latest_equity = float(equity_df["Equity giả lập"].iloc[-1])

    max_equity = float(equity_df["Equity giả lập"].cummax().iloc[-1])

    current_dd = 0.0

    if max_equity > 0:
        current_dd = (max_equity - latest_equity) / max_equity * 100

    loss_streak = 0

    if "Win danh mục" in equity_df.columns:
        recent = equity_df["Win danh mục"].tail(10).tolist()

        for v in reversed(recent):
            if int(v) == 0:
                loss_streak += 1
            else:
                break

    return {
        "latest_equity": latest_equity,
        "max_equity": max_equity,
        "current_drawdown_pct": current_dd,
        "loss_streak": loss_streak
    }


def exposure_from_regime(regime):
    return REGIME_EXPOSURE_MAP.get(regime, 0.55)


def equity_protection_multiplier(drawdown_pct):
    if drawdown_pct >= DRAW_DOWN_KILL:
        return 0.10

    if drawdown_pct >= DRAW_DOWN_STRONG:
        return 0.35

    if drawdown_pct >= DRAW_DOWN_WARNING:
        return 0.60

    return 1.00


def recovery_multiplier(loss_streak):
    if loss_streak >= RECOVERY_LOSS_STREAK:
        return 0.50

    return 1.00


def build_sector_map(symbols):
    """
    Mapping đơn giản để tránh phụ thuộc external source.
    Có thể thay bằng sector thật ở V16.
    """

    mapping = {}

    banks = ["VCB", "BID", "CTG", "MBB", "TCB", "ACB", "SHB", "HDB"]
    oil = ["PVS", "PVD", "BSR", "PLX", "GAS"]
    real = ["VIC", "VHM", "NVL", "DXG", "KDH"]
    steel = ["HPG", "HSG", "NKG"]

    for s in symbols:
        if s in banks:
            mapping[s] = "BANK"

        elif s in oil:
            mapping[s] = "OIL_GAS"

        elif s in real:
            mapping[s] = "REAL_ESTATE"

        elif s in steel:
            mapping[s] = "STEEL"

        else:
            mapping[s] = "OTHER"

    return mapping


def apply_sector_heat_control(df):
    sector_sum = df.groupby("Sector")["Final Weight"].sum().to_dict()

    adjusted = []

    for _, row in df.iterrows():

        sector = row["Sector"]
        weight = row["Final Weight"]

        total_sector = sector_sum.get(sector, 0)

        if total_sector > MAX_SECTOR_WEIGHT:
            ratio = MAX_SECTOR_WEIGHT / total_sector
            weight = weight * ratio

        adjusted.append(weight)

    df["Final Weight"] = adjusted

    return df


def normalize_weights(df):
    total = df["Final Weight"].sum()

    if total <= 0:
        return df

    df["Final Weight"] = df["Final Weight"] / total

    return df


# ========================================================
# CORE ENGINE
# ========================================================

def run_engine():

    log("Đọc dữ liệu input...")

    risk_df = safe_read_csv(INPUT_RISK_EXIT)
    equity_df = safe_read_csv(INPUT_EQUITY)

    required_cols = [
        "Mã",
        "Điểm V15.3",
        "Volatility20 %",
        "ATR %",
        "Tỷ trọng sau giới hạn"
    ]

    for col in required_cols:
        if col not in risk_df.columns:
            raise ValueError(f"Thiếu cột bắt buộc trong V15.4.1: {col}")

    market_regime = detect_market_regime(risk_df)

    log(f"Regime hiện tại: {market_regime}")

    equity_state = calculate_equity_state(equity_df)

    current_dd = equity_state["current_drawdown_pct"]
    loss_streak = equity_state["loss_streak"]

    log(f"Drawdown hiện tại: {round(current_dd,2)}%")
    log(f"Loss streak: {loss_streak}")

    regime_exposure = exposure_from_regime(market_regime)

    dd_multiplier = equity_protection_multiplier(current_dd)

    recovery_mult = recovery_multiplier(loss_streak)

    global_exposure = (
        regime_exposure
        * dd_multiplier
        * recovery_mult
    )

    global_exposure = min(max(global_exposure, 0.05), 1.00)

    kill_switch = current_dd >= DRAW_DOWN_KILL

    if kill_switch:
        log("KÍCH HOẠT KILL SWITCH - CHUYỂN DEFENSIVE MODE")

    symbols = risk_df["Mã"].astype(str).tolist()

    sector_map = build_sector_map(symbols)

    allocation_rows = []

    for _, row in risk_df.iterrows():

        symbol = str(row["Mã"]).strip()

        score = float(row["Điểm V15.3"])

        vol = float(row["Volatility20 %"])

        atr = float(row["ATR %"])

        base_weight = float(row["Tỷ trọng sau giới hạn"])

        # ====================================================
        # Adaptive sizing
        # ====================================================

        score_factor = score / 100

        vol_factor = 1 / (1 + max(vol, 0.01))

        atr_factor = 1 / (1 + max(atr, 0.01))

        regime_factor = regime_exposure

        equity_factor = dd_multiplier * recovery_mult

        final_weight = (
            base_weight
            * score_factor
            * vol_factor
            * atr_factor
            * regime_factor
            * equity_factor
        )

        if kill_switch:
            final_weight *= 0.15

        final_weight = max(final_weight, MIN_POSITION_WEIGHT)
        final_weight = min(final_weight, MAX_POSITION_WEIGHT)

        allocation_rows.append({
            "Mã": symbol,
            "Chiến lược": row.get("Chiến lược", "UNKNOWN"),
            "Sector": sector_map.get(symbol, "OTHER"),
            "Điểm V15.3": score,
            "Volatility20 %": vol,
            "ATR %": atr,
            "Base Weight": base_weight,
            "Score Factor": round(score_factor, 4),
            "Volatility Factor": round(vol_factor, 4),
            "ATR Factor": round(atr_factor, 4),
            "Regime Factor": round(regime_factor, 4),
            "Equity Protection Factor": round(equity_factor, 4),
            "Final Weight": round(final_weight, 6),
            "Kill Switch": kill_switch,
            "Global Exposure": round(global_exposure, 4),
            "Market Regime": market_regime
        })

    allocation_df = pd.DataFrame(allocation_rows)

    allocation_df = apply_sector_heat_control(allocation_df)

    allocation_df = normalize_weights(allocation_df)

    allocation_df["Final Allocation %"] = (
        allocation_df["Final Weight"] * global_exposure * 100
    ).round(2)

    allocation_df = allocation_df.sort_values(
        by="Final Allocation %",
        ascending=False
    )

    # ========================================================
    # Equity survival curve
    # ========================================================

    equity_curve = equity_df.copy()

    equity_curve["Survival Exposure"] = global_exposure

    equity_curve["Protection Multiplier"] = dd_multiplier

    equity_curve["Recovery Multiplier"] = recovery_mult

    equity_curve["Kill Switch"] = kill_switch

    equity_curve["Adjusted Equity"] = (
        equity_curve["Equity giả lập"]
        * global_exposure
    )

    # ========================================================
    # REPORT
    # ========================================================

    report = []

    report.append("=" * 60)
    report.append("V15.5 EQUITY SURVIVAL ENGINE")
    report.append("=" * 60)

    report.append(f"Version: {SYSTEM_VERSION}")
    report.append(f"Generated: {datetime.now()}")

    report.append("")
    report.append("=== MARKET STATE ===")
    report.append(f"Market Regime: {market_regime}")
    report.append(f"Global Exposure: {round(global_exposure,4)}")
    report.append(f"Current Drawdown: {round(current_dd,2)}%")
    report.append(f"Loss Streak: {loss_streak}")
    report.append(f"Kill Switch: {kill_switch}")

    report.append("")
    report.append("=== EXPOSURE COMPONENTS ===")
    report.append(f"Regime Exposure: {round(regime_exposure,4)}")
    report.append(f"Equity Protection: {round(dd_multiplier,4)}")
    report.append(f"Recovery Multiplier: {round(recovery_mult,4)}")

    report.append("")
    report.append("=== TOP ALLOCATION ===")

    top_alloc = allocation_df.head(10)

    for _, row in top_alloc.iterrows():

        report.append(
            f"{row['Mã']} | "
            f"Alloc={row['Final Allocation %']}% | "
            f"Score={row['Điểm V15.3']} | "
            f"Sector={row['Sector']}"
        )

    report.append("")
    report.append("=== SURVIVAL CONCLUSION ===")

    if kill_switch:
        report.append(
            "Hệ thống đang ở trạng thái phòng thủ mạnh. "
            "Ưu tiên bảo toàn vốn."
        )

    elif global_exposure >= 0.8:
        report.append(
            "RISK ON mạnh. Có thể giải ngân cao."
        )

    elif global_exposure >= 0.5:
        report.append(
            "Thị trường trung tính. Giải ngân vừa phải."
        )

    else:
        report.append(
            "Rủi ro cao. Ưu tiên giữ tiền."
        )

    report_text = "\n".join(report)

    # ========================================================
    # HTML
    # ========================================================

    html = f"""
    <html>
    <head>
        <meta charset="utf-8">
        <title>V15.5 Equity Survival</title>
        <style>
            body {{
                font-family: Arial;
                margin: 20px;
            }}

            table {{
                border-collapse: collapse;
                width: 100%;
            }}

            th, td {{
                border: 1px solid #ccc;
                padding: 8px;
                text-align: center;
            }}

            th {{
                background: #efefef;
            }}
        </style>
    </head>

    <body>

    <h1>V15.5 Equity Survival Engine</h1>

    <h2>Market State</h2>

    <ul>
        <li>Regime: {market_regime}</li>
        <li>Global Exposure: {round(global_exposure,4)}</li>
        <li>Current Drawdown: {round(current_dd,2)}%</li>
        <li>Loss Streak: {loss_streak}</li>
        <li>Kill Switch: {kill_switch}</li>
    </ul>

    <h2>Allocation Table</h2>

    {allocation_df.to_html(index=False)}

    <h2>Equity Survival Curve</h2>

    {equity_curve.tail(50).to_html(index=False)}

    </body>
    </html>
    """

    # ========================================================
    # SAVE
    # ========================================================

    allocation_df.to_csv(OUTPUT_ALLOCATION, index=False, encoding="utf-8-sig")

    equity_curve.to_csv(OUTPUT_EQUITY, index=False, encoding="utf-8-sig")

    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        f.write(report_text)

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    log("Đã export toàn bộ output V15.5")

    return allocation_df, equity_curve


# ========================================================
# MAIN
# ========================================================

if __name__ == "__main__":

    try:

        alloc_df, eq_df = run_engine()

        log("RUN THÀNH CÔNG")

    except Exception as e:

        log(f"LỖI: {e}")

        raise
