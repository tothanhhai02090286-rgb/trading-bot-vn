# -*- coding: utf-8 -*-
"""
============================================================
V16 META ALLOCATION INTELLIGENCE ENGINE VI
============================================================

Tên dễ hiểu:
- V16 = Bộ não phân bổ vốn thông minh

Vai trò:
- KHÔNG phải signal engine.
- KHÔNG scan tín hiệu mới.
- KHÔNG thêm indicator retail kiểu RSI/MACD.
- KHÔNG override risk từ V15.5.
- Chỉ đọc trạng thái risk/survival từ V15.5 và phân bổ vốn thông minh hơn.

Input chính:
- v155_equity_survival_allocation.csv
- v155_equity_survival_equity.csv

Input phụ nếu có:
- v1541_portfolio_risk_exit.csv
- v1541_portfolio_equity.csv

Output:
- v16_meta_allocation.csv
- v16_meta_risk_state.csv
- v16_capital_map.csv
- v16_rotation_plan.csv
- v16_meta_allocation_report.txt
- v16_meta_allocation.html

V16 trả lời câu hỏi:
"Hôm nay hệ thống nên phân bổ vốn thông minh như thế nào?"
============================================================
"""

import os
import math
import warnings
from datetime import datetime

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

SYSTEM_VERSION = "V16_META_ALLOCATION_INTELLIGENCE_ENGINE_VI"


# ============================================================
# FILE INPUT / OUTPUT
# ============================================================

INPUT_V155_ALLOCATION = "v155_equity_survival_allocation.csv"
INPUT_V155_EQUITY = "v155_equity_survival_equity.csv"

INPUT_V1541_RISK = "v1541_portfolio_risk_exit.csv"
INPUT_V1541_EQUITY = "v1541_portfolio_equity.csv"

OUTPUT_META_ALLOCATION = "v16_meta_allocation.csv"
OUTPUT_RISK_STATE = "v16_meta_risk_state.csv"
OUTPUT_CAPITAL_MAP = "v16_capital_map.csv"
OUTPUT_ROTATION_PLAN = "v16_rotation_plan.csv"
OUTPUT_REPORT = "v16_meta_allocation_report.txt"
OUTPUT_HTML = "v16_meta_allocation.html"


# ============================================================
# THAM SỐ META ALLOCATION
# ============================================================

MAX_META_POSITION = 0.25
MIN_META_POSITION = 0.00

MAX_SECTOR_META_WEIGHT = 0.35

VOL_CLUSTER_LOW = 4.0
VOL_CLUSTER_MEDIUM = 7.0
VOL_CLUSTER_HIGH = 10.0

DRAWDOWN_SAFE = 5.0
DRAWDOWN_CAUTION = 10.0
DRAWDOWN_DANGER = 15.0

CORRELATION_HEAT_LOW = 0.35
CORRELATION_HEAT_MEDIUM = 0.60
CORRELATION_HEAT_HIGH = 0.75


# ============================================================
# TIỆN ÍCH
# ============================================================

def log(msg):
    print(f"[V16] {msg}")


def require_file(path):
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"THIẾU INPUT BẮT BUỘC: {path}. "
            f"V16 chỉ đọc output V15.5, không tự scan tín hiệu mới."
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


def safe_div(a, b, default=0.0):
    try:
        if b == 0:
            return default
        return a / b
    except Exception:
        return default


# ============================================================
# ĐỌC TRẠNG THÁI V15.5
# ============================================================

def load_inputs():
    require_file(INPUT_V155_ALLOCATION)
    require_file(INPUT_V155_EQUITY)

    alloc_df = read_csv_smart(INPUT_V155_ALLOCATION)
    equity_df = read_csv_smart(INPUT_V155_EQUITY)

    risk1541_df = read_csv_smart(INPUT_V1541_RISK) if os.path.exists(INPUT_V1541_RISK) else pd.DataFrame()
    equity1541_df = read_csv_smart(INPUT_V1541_EQUITY) if os.path.exists(INPUT_V1541_EQUITY) else pd.DataFrame()

    return alloc_df, equity_df, risk1541_df, equity1541_df


def detect_v155_columns(alloc_df):
    symbol_col = pick_col(alloc_df, ["Mã", "Ma", "Symbol", "Ticker"], True, "Mã")
    sector_col = pick_col(alloc_df, ["Sector", "Ngành", "Nhóm ngành"], False)
    score_col = pick_col(alloc_df, ["Điểm V15.3", "Score", "Điểm"], False)
    final_alloc_col = pick_col(alloc_df, ["Final Allocation %", "Tỷ trọng V15.5 %", "Allocation %"], False)
    final_weight_col = pick_col(alloc_df, ["Final Weight", "Tỷ trọng sau V15.5", "Weight"], False)
    vol_col = pick_col(alloc_df, ["Volatility20 %", "Volatility %", "Vol20 %"], False)
    atr_col = pick_col(alloc_df, ["ATR %", "ATR"], False)
    regime_col = pick_col(alloc_df, ["Market Regime", "Regime", "Regime tốt nhất"], False)
    kill_col = pick_col(alloc_df, ["Kill Switch", "KillSwitch"], False)
    global_exposure_col = pick_col(alloc_df, ["Global Exposure", "Exposure"], False)

    return {
        "symbol_col": symbol_col,
        "sector_col": sector_col,
        "score_col": score_col,
        "final_alloc_col": final_alloc_col,
        "final_weight_col": final_weight_col,
        "vol_col": vol_col,
        "atr_col": atr_col,
        "regime_col": regime_col,
        "kill_col": kill_col,
        "global_exposure_col": global_exposure_col
    }


def get_latest_equity_state(equity_df):
    equity_col = pick_col(equity_df, ["Adjusted Equity", "Equity giả lập", "Equity"], False)
    dd_col = pick_col(equity_df, ["Drawdown giả lập %", "Drawdown %", "Current Drawdown"], False)
    exposure_col = pick_col(equity_df, ["Survival Exposure", "Exposure"], False)
    kill_col = pick_col(equity_df, ["Kill Switch", "KillSwitch"], False)

    if equity_df.empty:
        return {
            "equity_latest": 100.0,
            "drawdown_pct": 0.0,
            "survival_exposure": 0.0,
            "kill_switch": False,
            "equity_slope": 0.0,
            "loss_streak": 0
        }

    latest = equity_df.iloc[-1]

    equity_latest = to_num(latest[equity_col], 100.0) if equity_col else 100.0

    if dd_col:
        drawdown_pct = abs(to_num(latest[dd_col], 0.0))
    elif equity_col:
        curve = equity_df[equity_col].apply(to_num)
        peak = curve.cummax()
        drawdown_pct = abs(((curve.iloc[-1] / peak.iloc[-1]) - 1) * 100) if peak.iloc[-1] > 0 else 0.0
    else:
        drawdown_pct = 0.0

    survival_exposure = to_num(latest[exposure_col], 0.0) if exposure_col else 0.0

    kill_switch = False
    if kill_col:
        kill_switch = str(latest[kill_col]).strip().lower() in ["true", "1", "yes", "có"]

    equity_slope = 0.0
    if equity_col and len(equity_df) >= 5:
        recent = equity_df[equity_col].tail(5).apply(to_num).tolist()
        if recent[0] > 0:
            equity_slope = (recent[-1] / recent[0] - 1) * 100

    loss_streak = 0
    win_col = pick_col(equity_df, ["Win danh mục"], False)
    if win_col:
        recent_win = equity_df[win_col].tail(10).tolist()
        for v in reversed(recent_win):
            if int(to_num(v, 0)) == 0:
                loss_streak += 1
            else:
                break

    return {
        "equity_latest": round(equity_latest, 4),
        "drawdown_pct": round(drawdown_pct, 4),
        "survival_exposure": round(survival_exposure, 4),
        "kill_switch": kill_switch,
        "equity_slope": round(equity_slope, 4),
        "loss_streak": loss_streak
    }


# ============================================================
# META STATE
# ============================================================

def classify_equity_state(drawdown_pct, kill_switch, equity_slope, loss_streak):
    if kill_switch or drawdown_pct >= DRAWDOWN_DANGER:
        return "PHÒNG THỦ MẠNH"

    if drawdown_pct >= DRAWDOWN_CAUTION:
        return "THẬN TRỌNG"

    if drawdown_pct >= DRAWDOWN_SAFE:
        return "GIẢM TỐC"

    if equity_slope > 0 and loss_streak == 0:
        return "ỔN ĐỊNH TĂNG"

    return "ỔN ĐỊNH"


def classify_volatility_cluster(avg_vol, avg_atr):
    combined = (avg_vol + avg_atr) / 2.0

    if combined >= VOL_CLUSTER_HIGH:
        return "BIẾN ĐỘNG CAO"

    if combined >= VOL_CLUSTER_MEDIUM:
        return "BIẾN ĐỘNG TRUNG BÌNH CAO"

    if combined >= VOL_CLUSTER_LOW:
        return "BIẾN ĐỘNG TRUNG BÌNH"

    return "BIẾN ĐỘNG THẤP"


def classify_regime_strength(market_regime, equity_state, volatility_cluster):
    regime = normalize_text(market_regime)

    if "RISK OFF" in regime:
        return "RISK OFF MẠNH"

    if "SIDEWAY" in regime:
        if "BIẾN ĐỘNG CAO" in volatility_cluster:
            return "SIDEWAY YẾU"
        return "SIDEWAY TRUNG TÍNH"

    if "RISK ON" in regime:
        if equity_state in ["ỔN ĐỊNH TĂNG", "ỔN ĐỊNH"] and volatility_cluster in ["BIẾN ĐỘNG THẤP", "BIẾN ĐỘNG TRUNG BÌNH"]:
            return "RISK ON MẠNH"
        return "RISK ON YẾU"

    return "TRUNG TÍNH"


def meta_exposure_multiplier(regime_strength, equity_state, volatility_cluster):
    """
    Hệ số này KHÔNG override V15.5.
    Nó chỉ nhân tiếp vào survival exposure của V15.5 để tinh chỉnh thông minh hơn.
    """

    multiplier = 1.0

    if regime_strength == "RISK OFF MẠNH":
        multiplier *= 0.50
    elif regime_strength == "SIDEWAY YẾU":
        multiplier *= 0.65
    elif regime_strength == "SIDEWAY TRUNG TÍNH":
        multiplier *= 0.80
    elif regime_strength == "RISK ON YẾU":
        multiplier *= 0.90
    elif regime_strength == "RISK ON MẠNH":
        multiplier *= 1.00

    if equity_state == "PHÒNG THỦ MẠNH":
        multiplier *= 0.35
    elif equity_state == "THẬN TRỌNG":
        multiplier *= 0.60
    elif equity_state == "GIẢM TỐC":
        multiplier *= 0.80

    if volatility_cluster == "BIẾN ĐỘNG CAO":
        multiplier *= 0.60
    elif volatility_cluster == "BIẾN ĐỘNG TRUNG BÌNH CAO":
        multiplier *= 0.80

    return round(max(min(multiplier, 1.0), 0.05), 4)


def decision_mode_from_state(meta_exposure, equity_state, regime_strength):
    if equity_state == "PHÒNG THỦ MẠNH" or meta_exposure <= 0.10:
        return "CASH MODE"

    if meta_exposure <= 0.25:
        return "ĐÁNH RẤT NHỎ"

    if meta_exposure <= 0.50:
        return "ĐÁNH NHỎ"

    if meta_exposure <= 0.75:
        return "ĐÁNH VỪA"

    if "RISK ON MẠNH" in regime_strength:
        return "ĐÁNH MẠNH CÓ KIỂM SOÁT"

    return "ĐÁNH VỪA CÓ KIỂM SOÁT"


# ============================================================
# CORRELATION HEAT / SECTOR HEAT
# ============================================================

def estimate_correlation_heat(alloc_df):
    """
    Không tính indicator mới.
    Chỉ ước lượng heat dựa trên mức tập trung sector nếu không có ma trận correlation.
    """

    sector_col = pick_col(alloc_df, ["Sector", "Ngành", "Nhóm ngành"], False)
    weight_col = pick_col(alloc_df, ["Final Weight", "Final Allocation %", "Tỷ trọng sau giới hạn"], False)

    if not sector_col or not weight_col or alloc_df.empty:
        return {
            "correlation_heat_score": 0.50,
            "correlation_heat_level": "TRUNG BÌNH"
        }

    tmp = alloc_df.copy()
    tmp["_w"] = tmp[weight_col].apply(to_num)

    if weight_col == "Final Allocation %":
        tmp["_w"] = tmp["_w"] / 100.0

    total = tmp["_w"].sum()

    if total <= 0:
        return {
            "correlation_heat_score": 0.50,
            "correlation_heat_level": "TRUNG BÌNH"
        }

    sector_weights = tmp.groupby(sector_col)["_w"].sum() / total

    concentration = float((sector_weights ** 2).sum())

    if concentration >= CORRELATION_HEAT_HIGH:
        level = "CAO"
    elif concentration >= CORRELATION_HEAT_MEDIUM:
        level = "TRUNG BÌNH CAO"
    elif concentration >= CORRELATION_HEAT_LOW:
        level = "TRUNG BÌNH"
    else:
        level = "THẤP"

    return {
        "correlation_heat_score": round(concentration, 4),
        "correlation_heat_level": level
    }


def sector_heat_table(alloc_df, cols):
    sector_col = cols["sector_col"]
    weight_col = cols["final_alloc_col"] or cols["final_weight_col"]

    if not sector_col:
        alloc_df["Sector"] = "OTHER"
        sector_col = "Sector"

    if not weight_col:
        alloc_df["_meta_base_weight"] = 0.0
        weight_col = "_meta_base_weight"

    tmp = alloc_df.copy()
    tmp["_base_weight"] = tmp[weight_col].apply(to_num)

    if weight_col == cols["final_alloc_col"]:
        tmp["_base_weight"] = tmp["_base_weight"] / 100.0

    if tmp["_base_weight"].sum() > 0:
        tmp["_base_weight"] = tmp["_base_weight"] / tmp["_base_weight"].sum()

    sector = tmp.groupby(sector_col).agg(
        Số_mã=(cols["symbol_col"], "count"),
        Tỷ_trọng_gốc=("_base_weight", "sum")
    ).reset_index()

    sector = sector.rename(columns={sector_col: "Sector"})

    sector["Sector Heat"] = sector["Tỷ_trọng_gốc"].apply(
        lambda x: "QUÁ NÓNG" if x > MAX_SECTOR_META_WEIGHT else ("NÓNG" if x > 0.25 else "BÌNH THƯỜNG")
    )

    return sector


# ============================================================
# META ALLOCATION
# ============================================================

def build_meta_allocation(alloc_df, risk_state):
    cols = detect_v155_columns(alloc_df)

    work = alloc_df.copy()

    symbol_col = cols["symbol_col"]
    sector_col = cols["sector_col"]
    score_col = cols["score_col"]
    final_alloc_col = cols["final_alloc_col"]
    final_weight_col = cols["final_weight_col"]
    vol_col = cols["vol_col"]
    atr_col = cols["atr_col"]

    if sector_col is None:
        work["Sector"] = "OTHER"
        sector_col = "Sector"

    if score_col is None:
        work["Điểm V15.3"] = 50.0
        score_col = "Điểm V15.3"

    if final_alloc_col:
        work["_base_alloc"] = work[final_alloc_col].apply(to_num) / 100.0
    elif final_weight_col:
        work["_base_alloc"] = work[final_weight_col].apply(to_num)
    else:
        work["_base_alloc"] = 0.0

    if vol_col is None:
        work["Volatility20 %"] = 5.0
        vol_col = "Volatility20 %"

    if atr_col is None:
        work["ATR %"] = 5.0
        atr_col = "ATR %"

    work["_score_factor"] = work[score_col].apply(to_num) / 100.0
    work["_vol_factor"] = 1.0 / (1.0 + work[vol_col].apply(to_num).clip(lower=0.01))
    work["_atr_factor"] = 1.0 / (1.0 + work[atr_col].apply(to_num).clip(lower=0.01))

    # Meta score = không tạo tín hiệu mới, chỉ dùng lại score/risk/allocation từ V15.5
    work["Meta Score"] = (
        work["_base_alloc"]
        * work["_score_factor"]
        * work["_vol_factor"]
        * work["_atr_factor"]
    )

    if work["Meta Score"].sum() > 0:
        work["Meta Weight Raw"] = work["Meta Score"] / work["Meta Score"].sum()
    else:
        work["Meta Weight Raw"] = 0.0

    # Sector heat control ở tầng meta
    sector_sum = work.groupby(sector_col)["Meta Weight Raw"].sum().to_dict()

    adjusted = []

    for _, row in work.iterrows():
        sector = row[sector_col]
        w = row["Meta Weight Raw"]
        ssum = sector_sum.get(sector, 0.0)

        if ssum > MAX_SECTOR_META_WEIGHT and ssum > 0:
            w = w * MAX_SECTOR_META_WEIGHT / ssum

        adjusted.append(w)

    work["Meta Weight After Sector"] = adjusted

    total = work["Meta Weight After Sector"].sum()

    if total > 0:
        work["Meta Weight After Sector"] = work["Meta Weight After Sector"] / total

    meta_exposure = risk_state["meta_exposure"]

    work["Meta Allocation %"] = (
        work["Meta Weight After Sector"]
        * meta_exposure
        * 100.0
    ).clip(lower=MIN_META_POSITION * 100, upper=MAX_META_POSITION * 100)

    work["V16 Action"] = work["Meta Allocation %"].apply(action_from_allocation)

    out = pd.DataFrame({
        "Mã": work[symbol_col].astype(str).str.upper(),
        "Sector": work[sector_col],
        "Điểm V15.3": work[score_col].apply(to_num).round(2),
        "Allocation V15.5 gốc %": (work["_base_alloc"] * 100).round(3),
        "Meta Score": work["Meta Score"].round(6),
        "Meta Weight": work["Meta Weight After Sector"].round(6),
        "Meta Allocation %": work["Meta Allocation %"].round(3),
        "V16 Action": work["V16 Action"],
        "Regime Strength": risk_state["regime_strength"],
        "Equity State": risk_state["equity_state"],
        "Volatility Cluster": risk_state["volatility_cluster"],
        "Decision Mode": risk_state["decision_mode"]
    })

    out = out.sort_values(
        by=["Meta Allocation %", "Điểm V15.3", "Meta Score"],
        ascending=False
    ).reset_index(drop=True)

    return out


def action_from_allocation(x):
    x = to_num(x)

    if x <= 0.01:
        return "GIỮ TIỀN / KHÔNG MUA"

    if x < 2.0:
        return "WATCH RẤT NHỎ"

    if x < 5.0:
        return "PHÂN BỔ NHỎ"

    if x < 10.0:
        return "PHÂN BỔ VỪA"

    return "ƯU TIÊN CAO CÓ KIỂM SOÁT"


def build_capital_map(meta_df, risk_state):
    buckets = []

    total_alloc = meta_df["Meta Allocation %"].sum() if not meta_df.empty else 0.0

    cash = max(100.0 - total_alloc, 0.0)

    buckets.append({
        "Nhóm vốn": "Tiền mặt / phòng thủ",
        "Tỷ trọng %": round(cash, 3),
        "Ý nghĩa": "Phần vốn không giải ngân để bảo vệ tài khoản"
    })

    if not meta_df.empty:
        for action, g in meta_df.groupby("V16 Action"):
            buckets.append({
                "Nhóm vốn": action,
                "Tỷ trọng %": round(g["Meta Allocation %"].sum(), 3),
                "Ý nghĩa": explain_action(action)
            })

    buckets.append({
        "Nhóm vốn": "Decision Mode",
        "Tỷ trọng %": round(risk_state["meta_exposure"] * 100, 3),
        "Ý nghĩa": risk_state["decision_mode"]
    })

    return pd.DataFrame(buckets)


def explain_action(action):
    if action == "GIỮ TIỀN / KHÔNG MUA":
        return "Không giải ngân vì allocation quá thấp"
    if action == "WATCH RẤT NHỎ":
        return "Chỉ theo dõi hoặc vào rất nhỏ nếu V17/V18 xác nhận"
    if action == "PHÂN BỔ NHỎ":
        return "Có thể phân bổ nhỏ, vẫn ưu tiên quản trị rủi ro"
    if action == "PHÂN BỔ VỪA":
        return "Có thể phân bổ vừa nếu V17 đồng thuận"
    if action == "ƯU TIÊN CAO CÓ KIỂM SOÁT":
        return "Ưu tiên cao nhưng vẫn bị khống chế bởi risk engine"
    return "Không xác định"


def build_rotation_plan(meta_df):
    if meta_df.empty:
        return pd.DataFrame([{
            "Rotation Plan": "KHÔNG XOAY VÒNG",
            "Lý do": "Không có mã allocation hợp lệ"
        }])

    sector_group = meta_df.groupby("Sector").agg(
        Tổng_allocation=("Meta Allocation %", "sum"),
        Số_mã=("Mã", "count"),
        Điểm_TB=("Điểm V15.3", "mean")
    ).reset_index()

    sector_group = sector_group.sort_values(
        by=["Tổng_allocation", "Điểm_TB"],
        ascending=False
    )

    rows = []

    for _, row in sector_group.iterrows():
        alloc = row["Tổng_allocation"]

        if alloc > MAX_SECTOR_META_WEIGHT * 100:
            action = "GIẢM TỶ TRỌNG NGÀNH"
            reason = "Tỷ trọng ngành vượt giới hạn meta"
        elif alloc >= 10:
            action = "ƯU TIÊN NGÀNH"
            reason = "Ngành đang có allocation tốt"
        elif alloc >= 3:
            action = "THEO DÕI NGÀNH"
            reason = "Ngành có allocation vừa phải"
        else:
            action = "KHÔNG ƯU TIÊN"
            reason = "Allocation thấp"

        rows.append({
            "Sector": row["Sector"],
            "Tổng allocation %": round(alloc, 3),
            "Số mã": int(row["Số_mã"]),
            "Điểm TB": round(row["Điểm_TB"], 2),
            "Rotation Plan": action,
            "Lý do": reason
        })

    return pd.DataFrame(rows)


# ============================================================
# RUN ENGINE
# ============================================================

def run_engine():
    log("Bắt đầu chạy V16 Meta Allocation Intelligence...")

    alloc_df, equity_df, risk1541_df, equity1541_df = load_inputs()

    cols = detect_v155_columns(alloc_df)

    equity_state_raw = get_latest_equity_state(equity_df)

    # Lấy market regime từ V15.5 allocation nếu có
    market_regime = "SIDEWAY"
    regime_col = cols["regime_col"]
    if regime_col and not alloc_df.empty:
        market_regime = normalize_text(alloc_df[regime_col].iloc[0])

    # Lấy global exposure từ V15.5
    v155_exposure = equity_state_raw["survival_exposure"]
    if v155_exposure <= 0 and cols["global_exposure_col"]:
        v155_exposure = to_num(alloc_df[cols["global_exposure_col"]].iloc[0], 0.0)

    # Nếu vẫn chưa có thì tính từ allocation thực tế
    if v155_exposure <= 0 and cols["final_alloc_col"]:
        v155_exposure = min(alloc_df[cols["final_alloc_col"]].apply(to_num).sum() / 100.0, 1.0)

    score_col = cols["score_col"]
    vol_col = cols["vol_col"]
    atr_col = cols["atr_col"]

    avg_score = alloc_df[score_col].apply(to_num).mean() if score_col else 50.0
    avg_vol = alloc_df[vol_col].apply(to_num).mean() if vol_col else 5.0
    avg_atr = alloc_df[atr_col].apply(to_num).mean() if atr_col else 5.0

    equity_state = classify_equity_state(
        equity_state_raw["drawdown_pct"],
        equity_state_raw["kill_switch"],
        equity_state_raw["equity_slope"],
        equity_state_raw["loss_streak"]
    )

    volatility_cluster = classify_volatility_cluster(avg_vol, avg_atr)

    regime_strength = classify_regime_strength(
        market_regime,
        equity_state,
        volatility_cluster
    )

    correlation_heat = estimate_correlation_heat(alloc_df)

    meta_mult = meta_exposure_multiplier(
        regime_strength,
        equity_state,
        volatility_cluster
    )

    # Không override risk V15.5: meta exposure chỉ nhỏ hơn hoặc bằng exposure V15.5
    meta_exposure = min(v155_exposure * meta_mult, v155_exposure)

    decision_mode = decision_mode_from_state(
        meta_exposure,
        equity_state,
        regime_strength
    )

    risk_state = {
        "system_version": SYSTEM_VERSION,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market_regime": market_regime,
        "regime_strength": regime_strength,
        "equity_state": equity_state,
        "volatility_cluster": volatility_cluster,
        "correlation_heat_score": correlation_heat["correlation_heat_score"],
        "correlation_heat_level": correlation_heat["correlation_heat_level"],
        "v155_survival_exposure": round(v155_exposure, 4),
        "meta_exposure_multiplier": round(meta_mult, 4),
        "meta_exposure": round(meta_exposure, 4),
        "decision_mode": decision_mode,
        "avg_score": round(avg_score, 3),
        "avg_volatility": round(avg_vol, 3),
        "avg_atr": round(avg_atr, 3),
        "drawdown_pct": equity_state_raw["drawdown_pct"],
        "equity_slope": equity_state_raw["equity_slope"],
        "loss_streak": equity_state_raw["loss_streak"],
        "kill_switch": equity_state_raw["kill_switch"]
    }

    meta_df = build_meta_allocation(alloc_df, risk_state)

    capital_map_df = build_capital_map(meta_df, risk_state)

    rotation_df = build_rotation_plan(meta_df)

    sector_df = sector_heat_table(alloc_df, cols)

    risk_state_df = pd.DataFrame([risk_state])

    # Xuất file
    meta_df.to_csv(OUTPUT_META_ALLOCATION, index=False, encoding="utf-8-sig")
    risk_state_df.to_csv(OUTPUT_RISK_STATE, index=False, encoding="utf-8-sig")
    capital_map_df.to_csv(OUTPUT_CAPITAL_MAP, index=False, encoding="utf-8-sig")
    rotation_df.to_csv(OUTPUT_ROTATION_PLAN, index=False, encoding="utf-8-sig")

    report = build_report(risk_state, meta_df, capital_map_df, rotation_df)

    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        f.write(report)

    html = build_html(risk_state, meta_df, risk_state_df, capital_map_df, rotation_df, sector_df)

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    log("Đã export toàn bộ output V16.")
    print(report)

    return meta_df, risk_state_df, capital_map_df, rotation_df


# ============================================================
# REPORT / HTML
# ============================================================

def build_report(risk_state, meta_df, capital_map_df, rotation_df):
    lines = []

    lines.append("=" * 70)
    lines.append("V16 META ALLOCATION INTELLIGENCE ENGINE")
    lines.append("=" * 70)
    lines.append(f"Version: {risk_state['system_version']}")
    lines.append(f"Generated: {risk_state['generated_at']}")

    lines.append("")
    lines.append("=== DỊCH DỄ HIỂU ===")
    lines.append("V16 = Bộ não phân bổ vốn thông minh.")
    lines.append("V16 không tìm tín hiệu mua mới.")
    lines.append("V16 chỉ quyết định nên phân bổ vốn mạnh, vừa, nhỏ hay giữ tiền.")

    lines.append("")
    lines.append("=== META RISK STATE ===")
    lines.append(f"Market Regime: {risk_state['market_regime']}")
    lines.append(f"Regime Strength: {risk_state['regime_strength']}")
    lines.append(f"Equity State: {risk_state['equity_state']}")
    lines.append(f"Volatility Cluster: {risk_state['volatility_cluster']}")
    lines.append(f"Correlation Heat: {risk_state['correlation_heat_level']}")
    lines.append(f"V15.5 Survival Exposure: {risk_state['v155_survival_exposure']}")
    lines.append(f"V16 Meta Multiplier: {risk_state['meta_exposure_multiplier']}")
    lines.append(f"V16 Meta Exposure: {risk_state['meta_exposure']}")
    lines.append(f"Decision Mode: {risk_state['decision_mode']}")
    lines.append(f"Drawdown: {risk_state['drawdown_pct']}%")
    lines.append(f"Kill Switch: {risk_state['kill_switch']}")

    lines.append("")
    lines.append("=== CAPITAL MAP ===")
    for _, row in capital_map_df.iterrows():
        lines.append(
            f"- {row['Nhóm vốn']}: {row['Tỷ trọng %']}% | {row['Ý nghĩa']}"
        )

    lines.append("")
    lines.append("=== TOP META ALLOCATION ===")

    if meta_df.empty:
        lines.append("Không có mã allocation hợp lệ.")
    else:
        for _, row in meta_df.head(15).iterrows():
            lines.append(
                f"◆ {row['Mã']} | Sector={row['Sector']} | "
                f"Meta Allocation={row['Meta Allocation %']}% | "
                f"Action={row['V16 Action']}"
            )

    lines.append("")
    lines.append("=== ROTATION PLAN ===")
    for _, row in rotation_df.head(10).iterrows():
        if "Sector" in row:
            lines.append(
                f"- {row['Sector']}: {row['Rotation Plan']} | {row['Lý do']}"
            )
        else:
            lines.append(f"- {row['Rotation Plan']}: {row['Lý do']}")

    lines.append("")
    lines.append("=== KẾT LUẬN V16 ===")

    if risk_state["decision_mode"] == "CASH MODE":
        lines.append("Hệ thống nên ưu tiên giữ tiền. V17/V18 không được aggressive entry.")
    elif "NHỎ" in risk_state["decision_mode"]:
        lines.append("Hệ thống chỉ nên đánh nhỏ, không dùng full size.")
    elif "VỪA" in risk_state["decision_mode"]:
        lines.append("Hệ thống có thể phân bổ vừa, nhưng vẫn phải theo risk state.")
    else:
        lines.append("Hệ thống có thể đánh mạnh có kiểm soát nếu V17/V18 xác nhận.")

    return "\n".join(lines)


def build_html(risk_state, meta_df, risk_state_df, capital_map_df, rotation_df, sector_df):
    html = f"""
<html>
<head>
<meta charset="utf-8">
<title>V16 Meta Allocation Intelligence</title>
<style>
body {{ font-family: Arial; margin: 20px; }}
h1 {{ color: #222; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 25px; }}
th, td {{ border: 1px solid #ccc; padding: 7px; text-align: center; }}
th {{ background: #efefef; }}
.box {{ padding: 12px; background: #f7f7f7; border: 1px solid #ddd; margin-bottom: 20px; }}
</style>
</head>
<body>

<h1>V16 Meta Allocation Intelligence</h1>

<div class="box">
<b>Dịch dễ hiểu:</b><br>
V16 = Bộ não phân bổ vốn thông minh.<br>
V16 không scan tín hiệu mới, không thêm RSI/MACD, không override V15.5.<br>
V16 chỉ trả lời: hôm nay nên đánh mạnh, đánh nhỏ hay giữ tiền?
</div>

<h2>Meta Risk State</h2>
<ul>
<li>Market Regime: <b>{risk_state['market_regime']}</b></li>
<li>Regime Strength: <b>{risk_state['regime_strength']}</b></li>
<li>Equity State: <b>{risk_state['equity_state']}</b></li>
<li>Volatility Cluster: <b>{risk_state['volatility_cluster']}</b></li>
<li>Correlation Heat: <b>{risk_state['correlation_heat_level']}</b></li>
<li>V15.5 Survival Exposure: <b>{risk_state['v155_survival_exposure']}</b></li>
<li>V16 Meta Exposure: <b>{risk_state['meta_exposure']}</b></li>
<li>Decision Mode: <b>{risk_state['decision_mode']}</b></li>
</ul>

<h2>Risk State Table</h2>
{risk_state_df.to_html(index=False)}

<h2>Meta Allocation</h2>
{meta_df.to_html(index=False)}

<h2>Capital Map</h2>
{capital_map_df.to_html(index=False)}

<h2>Rotation Plan</h2>
{rotation_df.to_html(index=False)}

<h2>Sector Heat</h2>
{sector_df.to_html(index=False)}

</body>
</html>
"""
    return html


if __name__ == "__main__":
    run_engine()
