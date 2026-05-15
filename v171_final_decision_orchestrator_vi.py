# -*- coding: utf-8 -*-
"""
V17.1 FINAL DECISION ORCHESTRATOR VI - FULL REBUILD

Vai trò:
- Cầu nối giữa V16 meta allocation và V18 realtime execution.
- Không scan tín hiệu mới, không thêm indicator retail.
- Không override V15.5/V16.
- Nếu có V17 cũ thì chỉ dùng như tín hiệu tham khảo.
- Xuất intraday_watchlist_v17.csv với schema mới để V18 obey upstream risk.

Input bắt buộc:
- v16_meta_allocation.csv
- v16_meta_risk_state.csv

Input phụ nếu có:
- v155_equity_survival_allocation.csv
- v155_equity_survival_equity.csv
- v17_final_decision_legacy.csv / v17_final_decision_old.csv / v17_legacy_final_decision.csv

Output:
- v17_final_decision.csv
- intraday_watchlist_v17.csv
- v171_orchestrator_report.txt
- v171_orchestrator.html
"""

from __future__ import annotations

import os
import warnings
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import pandas as pd

warnings.filterwarnings("ignore")

SYSTEM_VERSION = "V17.1_FINAL_DECISION_ORCHESTRATOR_VI_FULL_REBUILD"

INPUT_V16_META = "v16_meta_allocation.csv"
INPUT_V16_RISK = "v16_meta_risk_state.csv"
INPUT_V155_ALLOCATION = "v155_equity_survival_allocation.csv"
INPUT_V155_EQUITY = "v155_equity_survival_equity.csv"

LEGACY_V17_CANDIDATES = [
    "v17_final_decision_legacy.csv",
    "v17_final_decision_old.csv",
    "v17_legacy_final_decision.csv",
]

OUTPUT_FINAL = "v17_final_decision.csv"
OUTPUT_INTRADAY = "intraday_watchlist_v17.csv"
OUTPUT_REPORT = "v171_orchestrator_report.txt"
OUTPUT_HTML = "v171_orchestrator.html"

MIN_BUY_NOW_ALLOCATION = 8.0
MIN_WATCH_ALLOCATION = 1.0
DEFAULT_BUY_ZONE_LOW_PCT = -1.5
DEFAULT_BUY_ZONE_HIGH_PCT = 1.5
DEFAULT_STOPLOSS_PCT = -5.0

BLOCK_BUY_NOW_MODES = {"CASH MODE", "ĐÁNH RẤT NHỎ", "ĐÁNH NHỎ"}


def log(msg: str) -> None:
    print(f"[V17.1] {msg}")


def require_file(path: str) -> None:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"THIẾU INPUT BẮT BUỘC: {path}. V17.1 bắt buộc đọc V16, không tự quyết định độc lập."
        )


def read_csv_smart(path: str) -> pd.DataFrame:
    for enc in ["utf-8-sig", "utf-8", "cp1258", "latin1"]:
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            pass
    return pd.read_csv(path)


def to_num(x: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(x):
            return default
        if isinstance(x, str):
            x = x.replace("%", "").replace(",", ".").strip()
            if x == "":
                return default
        return float(x)
    except Exception:
        return default


def normalize_text(x: Any) -> str:
    try:
        if pd.isna(x):
            return "UNKNOWN"
    except Exception:
        pass
    s = str(x).strip().upper()
    return s if s else "UNKNOWN"


def display_text(x: Any, default: str = "") -> str:
    try:
        if pd.isna(x):
            return default
    except Exception:
        pass
    s = str(x).strip()
    return s if s else default


def pick_col(df: pd.DataFrame, candidates, required: bool = False, label: str = "") -> Optional[str]:
    if df is None or df.empty:
        if required:
            raise ValueError(f"Thiếu cột bắt buộc: {label or candidates}")
        return None

    lower_map = {str(c).lower(): c for c in df.columns}
    for c in candidates:
        if c in df.columns:
            return c
        if str(c).lower() in lower_map:
            return lower_map[str(c).lower()]

    if required:
        raise ValueError(f"Thiếu cột bắt buộc: {label or candidates}")
    return None


def safe_symbol(x: Any) -> str:
    return str(x).strip().upper()


def bool_from_any(x: Any) -> bool:
    return str(x).strip().lower() in ["true", "1", "yes", "có", "co"]


def load_inputs():
    require_file(INPUT_V16_META)
    require_file(INPUT_V16_RISK)

    v16_meta = read_csv_smart(INPUT_V16_META)
    v16_risk = read_csv_smart(INPUT_V16_RISK)
    v155_alloc = read_csv_smart(INPUT_V155_ALLOCATION) if os.path.exists(INPUT_V155_ALLOCATION) else pd.DataFrame()
    v155_equity = read_csv_smart(INPUT_V155_EQUITY) if os.path.exists(INPUT_V155_EQUITY) else pd.DataFrame()

    legacy = pd.DataFrame()
    legacy_path = None
    for p in LEGACY_V17_CANDIDATES:
        if os.path.exists(p):
            legacy = read_csv_smart(p)
            legacy_path = p
            break

    return v16_meta, v16_risk, v155_alloc, v155_equity, legacy, legacy_path


def get_risk_state(v16_risk: pd.DataFrame) -> Dict[str, Any]:
    if v16_risk.empty:
        raise ValueError("v16_meta_risk_state.csv rỗng, không thể điều phối V17.1.")

    row = v16_risk.iloc[0].to_dict()
    return {
        "market_regime": display_text(row.get("market_regime", "SIDEWAY"), "SIDEWAY"),
        "regime_strength": display_text(row.get("regime_strength", "TRUNG TÍNH"), "TRUNG TÍNH"),
        "equity_state": display_text(row.get("equity_state", "ỔN ĐỊNH"), "ỔN ĐỊNH"),
        "volatility_cluster": display_text(row.get("volatility_cluster", "UNKNOWN"), "UNKNOWN"),
        "correlation_heat_level": display_text(row.get("correlation_heat_level", "TRUNG BÌNH"), "TRUNG BÌNH"),
        "v155_survival_exposure": to_num(row.get("v155_survival_exposure", 0.0)),
        "meta_exposure": to_num(row.get("meta_exposure", 0.0)),
        "decision_mode": display_text(row.get("decision_mode", "UNKNOWN"), "UNKNOWN"),
        "drawdown_pct": to_num(row.get("drawdown_pct", 0.0)),
        "kill_switch": bool_from_any(row.get("kill_switch", False)),
    }


def normalize_legacy_v17(legacy_df: pd.DataFrame) -> pd.DataFrame:
    if legacy_df is None or legacy_df.empty:
        return pd.DataFrame(columns=["Mã", "Legacy Decision", "Legacy Score", "Legacy Group", "Legacy Note"])

    symbol_col = pick_col(legacy_df, ["Mã", "Ma", "Symbol", "Ticker"], False)
    decision_col = pick_col(legacy_df, ["Final Decision", "Quyết định cuối", "Decision", "Hành động", "Action"], False)
    score_col = pick_col(legacy_df, ["Final Score", "Điểm cuối", "Score", "Tổng điểm", "AI"], False)
    group_col = pick_col(legacy_df, ["Nhóm realtime", "Realtime Group", "Group", "Nhóm"], False)

    if symbol_col is None:
        return pd.DataFrame(columns=["Mã", "Legacy Decision", "Legacy Score", "Legacy Group", "Legacy Note"])

    out = pd.DataFrame()
    out["Mã"] = legacy_df[symbol_col].astype(str).str.upper().str.strip()
    out["Legacy Decision"] = legacy_df[decision_col] if decision_col else "UNKNOWN"
    out["Legacy Score"] = legacy_df[score_col].apply(to_num) if score_col else 0.0
    out["Legacy Group"] = legacy_df[group_col] if group_col else "UNKNOWN"
    out["Legacy Note"] = "Đọc từ V17 cũ"
    return out.drop_duplicates(subset=["Mã"], keep="first")


def action_from_v16(meta_allocation: float, v16_action: Any) -> str:
    alloc = to_num(meta_allocation)
    action = normalize_text(v16_action)

    if alloc <= 0.01:
        return "AVOID"
    if "GIỮ TIỀN" in action or "KHÔNG MUA" in action:
        return "AVOID"
    if "WATCH" in action or "THEO" in action:
        return "WATCHLIST"
    if alloc >= MIN_BUY_NOW_ALLOCATION:
        return "BUY NOW"
    if alloc >= MIN_WATCH_ALLOCATION:
        return "WATCHLIST"
    return "AVOID"


def merge_legacy_decision(v16_base_decision: str, legacy_decision: Any, legacy_score: float) -> Tuple[str, str]:
    v16_dec = normalize_text(v16_base_decision)
    legacy_dec = normalize_text(legacy_decision)

    if legacy_dec in ["BUY NOW", "MUA NGAY", "MUA", "TOP MUA THẬT"]:
        if v16_dec == "AVOID":
            return "WATCHLIST", "V17 cũ mạnh nhưng V16 allocation yếu, chỉ nâng lên WATCHLIST"
        return "BUY NOW", "V17 cũ đồng thuận tín hiệu mạnh"

    if legacy_dec in ["WATCHLIST", "WATCH", "THEO DÕI", "TOP THEO DÕI"]:
        if v16_dec == "BUY NOW":
            return "WATCHLIST", "V17 cũ chỉ watch, downgrade BUY NOW về WATCHLIST"
        return "WATCHLIST", "V17 cũ watch"

    if legacy_dec in ["AVOID", "BỎ QUA", "REDUCE", "GIẢM"]:
        return "AVOID", "V17 cũ cảnh báo tránh/giảm"

    return v16_dec, "Không có tín hiệu rõ từ V17 cũ, dùng V16"


def apply_upstream_risk_gate(base_decision: str, meta_allocation: float, risk_state: Dict[str, Any]) -> Tuple[str, str]:
    decision = normalize_text(base_decision)
    alloc = to_num(meta_allocation)

    decision_mode = normalize_text(risk_state["decision_mode"])
    meta_exposure = to_num(risk_state["meta_exposure"])
    kill_switch = bool(risk_state["kill_switch"])
    equity_state = normalize_text(risk_state["equity_state"])
    regime_strength = normalize_text(risk_state["regime_strength"])

    if kill_switch:
        return "AVOID", "Kill switch từ upstream đang bật"

    if decision_mode == "CASH MODE":
        if alloc <= 0.01:
            return "AVOID", "V16 CASH MODE và allocation gần 0"
        return "WATCHLIST", "V16 CASH MODE, chỉ được watch"

    if meta_exposure <= 0.10:
        if decision == "BUY NOW":
            return "WATCHLIST", "Meta exposure quá thấp, downgrade BUY NOW về WATCHLIST"
        if alloc < MIN_WATCH_ALLOCATION:
            return "AVOID", "Meta exposure quá thấp và allocation nhỏ"
        return decision, "Meta exposure thấp, không aggressive"

    if decision_mode == "ĐÁNH RẤT NHỎ":
        if decision == "BUY NOW":
            return "WATCHLIST", "Decision mode ĐÁNH RẤT NHỎ, không cho BUY NOW"
        if alloc < MIN_WATCH_ALLOCATION:
            return "AVOID", "Allocation quá thấp trong mode ĐÁNH RẤT NHỎ"
        return "WATCHLIST", "Chỉ watch / phân bổ rất nhỏ"

    if decision_mode == "ĐÁNH NHỎ":
        if decision == "BUY NOW" and alloc < MIN_BUY_NOW_ALLOCATION:
            return "WATCHLIST", "ĐÁNH NHỎ nhưng allocation chưa đủ BUY NOW"
        if "RISK OFF" in regime_strength and decision == "BUY NOW":
            return "WATCHLIST", "Regime risk-off, downgrade BUY NOW"
        return decision, "ĐÁNH NHỎ có kiểm soát"

    if equity_state in ["PHÒNG THỦ MẠNH", "THẬN TRỌNG"]:
        if decision == "BUY NOW":
            return "WATCHLIST", "Equity state thận trọng, downgrade BUY NOW"
        return decision, "Equity state đang thận trọng"

    if "RISK OFF" in regime_strength:
        if decision == "BUY NOW":
            return "WATCHLIST", "Regime strength risk-off, không aggressive"
        return decision, "Regime risk-off"

    return decision, "Risk gate cho phép"


def realtime_group_from_decision(final_decision: str, meta_allocation: float, risk_state: Dict[str, Any]) -> str:
    decision = normalize_text(final_decision)
    mode = normalize_text(risk_state["decision_mode"])
    alloc = to_num(meta_allocation)

    if decision == "BUY NOW":
        if mode in BLOCK_BUY_NOW_MODES:
            return "THEO DÕI"
        return "MUA"
    if decision == "WATCHLIST":
        if alloc >= MIN_WATCH_ALLOCATION:
            return "THEO DÕI"
        return "WATCH"
    return "BỎ QUA"


def priority_from_allocation(meta_allocation: float, final_decision: str) -> str:
    alloc = to_num(meta_allocation)
    decision = normalize_text(final_decision)
    if decision == "BUY NOW" and alloc >= 10:
        return "CAO"
    if decision in ["BUY NOW", "WATCHLIST"] and alloc >= 5:
        return "VỪA"
    if decision in ["BUY NOW", "WATCHLIST"] and alloc >= 1:
        return "THẤP"
    return "RẤT THẤP"


def build_buy_zone_pct(meta_allocation: float) -> Tuple[float, float, float]:
    alloc = to_num(meta_allocation)
    if alloc >= 10:
        return -1.0, 1.0, -4.0
    if alloc >= 5:
        return -1.3, 1.2, -4.5
    return DEFAULT_BUY_ZONE_LOW_PCT, DEFAULT_BUY_ZONE_HIGH_PCT, DEFAULT_STOPLOSS_PCT


def build_final_decision(v16_meta: pd.DataFrame, v16_risk: pd.DataFrame, v155_alloc: pd.DataFrame, legacy_df: pd.DataFrame):
    risk_state = get_risk_state(v16_risk)

    symbol_col = pick_col(v16_meta, ["Mã", "Ma", "Symbol", "Ticker"], True, "Mã")
    sector_col = pick_col(v16_meta, ["Sector", "Ngành", "Nhóm ngành"], False)
    score_col = pick_col(v16_meta, ["Điểm V15.3", "Score", "Điểm"], False)
    alloc_col = pick_col(v16_meta, ["Meta Allocation %", "Allocation %"], True, "Meta Allocation %")
    action_col = pick_col(v16_meta, ["V16 Action", "Action"], False)

    legacy_norm = normalize_legacy_v17(legacy_df)
    rows = []

    for _, row in v16_meta.iterrows():
        symbol = safe_symbol(row[symbol_col])
        if not symbol or symbol == "NAN":
            continue

        sector = display_text(row[sector_col], "OTHER") if sector_col else "OTHER"
        score = to_num(row[score_col], 50.0) if score_col else 50.0
        meta_alloc = to_num(row[alloc_col])
        v16_action = display_text(row[action_col], "UNKNOWN") if action_col else "UNKNOWN"

        base_decision = action_from_v16(meta_alloc, v16_action)
        legacy_match = legacy_norm[legacy_norm["Mã"] == symbol]

        if not legacy_match.empty:
            legacy_decision = legacy_match["Legacy Decision"].iloc[0]
            legacy_score = to_num(legacy_match["Legacy Score"].iloc[0])
            legacy_group = display_text(legacy_match["Legacy Group"].iloc[0], "UNKNOWN")
        else:
            legacy_decision = "NO_LEGACY"
            legacy_score = 0.0
            legacy_group = "NO_LEGACY"

        merged_decision, merge_note = merge_legacy_decision(base_decision, legacy_decision, legacy_score)
        final_decision, risk_note = apply_upstream_risk_gate(merged_decision, meta_alloc, risk_state)
        realtime_group = realtime_group_from_decision(final_decision, meta_alloc, risk_state)
        priority = priority_from_allocation(meta_alloc, final_decision)
        buy_low_pct, buy_high_pct, stop_pct = build_buy_zone_pct(meta_alloc)

        rows.append({
            "Mã": symbol,
            "Sector": sector,
            "Điểm V15.3": round(score, 2),
            "Meta Allocation %": round(meta_alloc, 3),
            "V16 Action": v16_action,
            "Legacy Decision": legacy_decision,
            "Legacy Score": round(legacy_score, 3),
            "Legacy Group": legacy_group,
            "Base Decision từ V16": base_decision,
            "Merged Decision": merged_decision,
            "Final Decision": final_decision,
            "Nhóm realtime": realtime_group,
            "Ưu tiên": priority,
            "Decision Mode": risk_state["decision_mode"],
            "Meta Exposure": round(to_num(risk_state["meta_exposure"]), 4),
            "V15.5 Survival Exposure": round(to_num(risk_state["v155_survival_exposure"]), 4),
            "Market Regime": risk_state["market_regime"],
            "Regime Strength": risk_state["regime_strength"],
            "Equity State": risk_state["equity_state"],
            "Volatility Cluster": risk_state["volatility_cluster"],
            "Correlation Heat": risk_state["correlation_heat_level"],
            "Kill Switch": risk_state["kill_switch"],
            "Drawdown %": round(to_num(risk_state["drawdown_pct"]), 3),
            "Buy zone thấp %": buy_low_pct,
            "Buy zone cao %": buy_high_pct,
            "Stoploss tham khảo %": stop_pct,
            "Ghi chú merge": merge_note,
            "Ghi chú risk gate": risk_note,
        })

    final_df = pd.DataFrame(rows)
    if final_df.empty:
        return final_df, risk_state

    decision_rank = {"BUY NOW": 4, "WATCHLIST": 3, "AVOID": 1, "REDUCE": 0}
    priority_rank = {"CAO": 4, "VỪA": 3, "THẤP": 2, "RẤT THẤP": 1}
    final_df["_decision_rank"] = final_df["Final Decision"].map(decision_rank).fillna(0)
    final_df["_priority_rank"] = final_df["Ưu tiên"].map(priority_rank).fillna(0)
    final_df = final_df.sort_values(
        by=["_decision_rank", "Meta Allocation %", "_priority_rank", "Điểm V15.3"],
        ascending=False,
    ).drop(columns=["_decision_rank", "_priority_rank"])

    return final_df.reset_index(drop=True), risk_state


def build_intraday_watchlist(final_df: pd.DataFrame) -> pd.DataFrame:
    """
    Xuất schema mới cho V18.
    Không xuất cột legacy như Hành động/Risk để tránh V18 đọc nhầm BUY NOW/PASS cũ.
    """
    intraday_cols = [
        "Mã",
        "Nhóm realtime",
        "Final Decision",
        "Meta Allocation %",
        "Decision Mode",
        "Meta Exposure",
        "Regime Strength",
        "Equity State",
        "Ưu tiên",
        "Buy zone thấp %",
        "Buy zone cao %",
        "Stoploss tham khảo %",
        "Market Regime",
        "V15.5 Survival Exposure",
        "Kill Switch",
        "Drawdown %",
        "Sector",
        "Điểm V15.3",
        "V16 Action",
        "Ghi chú risk gate",
        "Ghi chú V18",
    ]

    if final_df is None or final_df.empty:
        return pd.DataFrame(columns=intraday_cols)

    allow = final_df[final_df["Nhóm realtime"].astype(str).isin(["MUA", "THEO DÕI", "WATCH"])].copy()
    allow["Ghi chú V18"] = allow.apply(
        lambda r: (
            "V18 chỉ canh timing. Không được vượt allocation/risk từ V16/V17.1. "
            f"Final={r['Final Decision']}; Mode={r['Decision Mode']}; Alloc={r['Meta Allocation %']}%."
        ),
        axis=1,
    )

    for c in intraday_cols:
        if c not in allow.columns:
            allow[c] = ""

    out = allow[intraday_cols].copy()
    if not out.empty:
        out = out.sort_values(by=["Meta Allocation %", "Điểm V15.3"], ascending=False).reset_index(drop=True)
    return out


def build_report(final_df: pd.DataFrame, watch_df: pd.DataFrame, risk_state: Dict[str, Any], legacy_path: Optional[str]) -> str:
    lines = []
    lines.append("=" * 70)
    lines.append("V17.1 FINAL DECISION ORCHESTRATOR - FULL REBUILD")
    lines.append("=" * 70)
    lines.append(f"Version: {SYSTEM_VERSION}")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("=== DỊCH DỄ HIỂU ===")
    lines.append("V17.1 = Bộ điều phối quyết định cuối cùng.")
    lines.append("V17.1 không tự scan tín hiệu mới.")
    lines.append("V17.1 ép V17 cũ/V18 phải tuân theo V15.5 và V16.")
    lines.append("intraday_watchlist_v17.csv đã xuất schema mới cho V18.")
    lines.append("")
    lines.append("=== INPUT STATE ===")
    lines.append(f"Legacy V17 dùng: {legacy_path if legacy_path else 'Không có'}")
    lines.append(f"Decision Mode: {risk_state['decision_mode']}")
    lines.append(f"Meta Exposure: {risk_state['meta_exposure']}")
    lines.append(f"V15.5 Survival Exposure: {risk_state['v155_survival_exposure']}")
    lines.append(f"Regime Strength: {risk_state['regime_strength']}")
    lines.append(f"Equity State: {risk_state['equity_state']}")
    lines.append(f"Kill Switch: {risk_state['kill_switch']}")
    lines.append(f"Drawdown: {risk_state['drawdown_pct']}%")
    lines.append("")
    lines.append("=== FINAL DECISION SUMMARY ===")
    if final_df.empty:
        lines.append("Không có mã nào từ V16.")
    else:
        for k, v in final_df["Final Decision"].value_counts().to_dict().items():
            lines.append(f"- {k}: {v} mã")
    lines.append("")
    lines.append("=== INTRADAY WATCHLIST SUMMARY ===")
    if watch_df.empty:
        lines.append("Không có mã nào đưa sang V18.")
    else:
        for k, v in watch_df["Nhóm realtime"].value_counts().to_dict().items():
            lines.append(f"- {k}: {v} mã")
    lines.append("")
    lines.append("=== TOP FINAL DECISION ===")
    if not final_df.empty:
        for _, row in final_df.head(15).iterrows():
            lines.append(
                f"◆ {row['Mã']} | Final={row['Final Decision']} | "
                f"Realtime={row['Nhóm realtime']} | Alloc={row['Meta Allocation %']}% | "
                f"Mode={row['Decision Mode']} | Ưu tiên={row['Ưu tiên']} | "
                f"RiskGate={row['Ghi chú risk gate']}"
            )
    lines.append("")
    lines.append("=== SCHEMA WATCHLIST CHO V18 ===")
    lines.append("intraday_watchlist_v17.csv đã có các cột:")
    lines.append("Mã, Nhóm realtime, Final Decision, Meta Allocation %, Decision Mode,")
    lines.append("Meta Exposure, Regime Strength, Equity State, Ưu tiên, Buy zone thấp %,")
    lines.append("Buy zone cao %, Stoploss tham khảo %, Ghi chú V18.")
    lines.append("")
    lines.append("=== KẾT LUẬN V17.1 ===")
    mode = normalize_text(risk_state["decision_mode"])
    if risk_state["kill_switch"]:
        lines.append("Kill switch bật. Không aggressive entry.")
    elif mode in ["CASH MODE", "ĐÁNH RẤT NHỎ", "ĐÁNH NHỎ"]:
        lines.append("Hệ thống chỉ được đánh nhỏ hoặc theo dõi. V18 không được vào mạnh.")
    else:
        lines.append("Có thể cho V18 canh timing, nhưng vẫn phải giữ allocation từ V16.")
    return "\n".join(lines)


def build_html(final_df: pd.DataFrame, watch_df: pd.DataFrame, risk_state: Dict[str, Any], report: str) -> str:
    final_html = final_df.to_html(index=False) if not final_df.empty else "<p>Không có dữ liệu.</p>"
    watch_html = watch_df.to_html(index=False) if not watch_df.empty else "<p>Không có dữ liệu realtime.</p>"
    return f"""
<html>
<head>
<meta charset="utf-8">
<title>V17.1 Final Decision Orchestrator</title>
<style>
body {{ font-family: Arial; margin: 20px; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 25px; }}
th, td {{ border: 1px solid #ccc; padding: 7px; text-align: center; }}
th {{ background: #efefef; }}
.box {{ background: #f7f7f7; border: 1px solid #ddd; padding: 12px; margin-bottom: 20px; }}
pre {{ white-space: pre-wrap; }}
</style>
</head>
<body>
<h1>V17.1 Final Decision Orchestrator - Full Rebuild</h1>
<div class="box">
<b>Dịch dễ hiểu:</b><br>
V17.1 = Bộ điều phối quyết định cuối cùng.<br>
Nó dùng V16/V15.5 làm risk boss, V17 cũ chỉ là tín hiệu tham khảo.<br>
Output cuối cùng đưa cho V18 là intraday_watchlist_v17.csv với schema mới.
</div>
<h2>Risk State</h2>
<ul>
<li>Decision Mode: <b>{risk_state['decision_mode']}</b></li>
<li>Meta Exposure: <b>{risk_state['meta_exposure']}</b></li>
<li>V15.5 Survival Exposure: <b>{risk_state['v155_survival_exposure']}</b></li>
<li>Regime Strength: <b>{risk_state['regime_strength']}</b></li>
<li>Equity State: <b>{risk_state['equity_state']}</b></li>
<li>Kill Switch: <b>{risk_state['kill_switch']}</b></li>
<li>Drawdown: <b>{risk_state['drawdown_pct']}%</b></li>
</ul>
<h2>Final Decision</h2>
{final_html}
<h2>Intraday Watchlist V17 cho V18</h2>
{watch_html}
<h2>Report</h2>
<pre>{report}</pre>
</body>
</html>
"""


def run_engine():
    log("Bắt đầu chạy V17.1 Final Decision Orchestrator FULL REBUILD...")
    v16_meta, v16_risk, v155_alloc, v155_equity, legacy_df, legacy_path = load_inputs()
    final_df, risk_state = build_final_decision(v16_meta, v16_risk, v155_alloc, legacy_df)
    watch_df = build_intraday_watchlist(final_df)
    report = build_report(final_df, watch_df, risk_state, legacy_path)
    html = build_html(final_df, watch_df, risk_state, report)

    final_df.to_csv(OUTPUT_FINAL, index=False, encoding="utf-8-sig")
    watch_df.to_csv(OUTPUT_INTRADAY, index=False, encoding="utf-8-sig")
    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        f.write(report)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    log("Đã export output V17.1.")
    log(f"Final decision: {OUTPUT_FINAL}")
    log(f"Intraday watchlist schema mới: {OUTPUT_INTRADAY}")
    print(report)
    return final_df, watch_df


if __name__ == "__main__":
    run_engine()
