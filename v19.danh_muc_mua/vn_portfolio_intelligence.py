# -*- coding: utf-8 -*-
"""
vn_portfolio_intelligence.py

Portfolio Intelligence Engine (PIE) cho V19.2.

Mục tiêu:
- Gộp Phase 10 -> 14 thành một module danh mục duy nhất.
- Chỉ bổ sung context quản trị vốn/danh mục, KHÔNG ghi đè logic mua/bán hiện có.
- Dùng dữ liệu sẵn có từ Position Health, Mini Market Regime, Leader Rotation.

Các lớp trong PIE:
1) Portfolio Exposure Manager
2) Portfolio Health Engine
3) Risk Budget Engine
4) Position Sizing Guardrail
5) Drawdown Protection
"""
from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

import pandas as pd


@dataclass
class PortfolioIntelligenceResult:
    status: str
    icon: str
    portfolio_health_score: Any
    portfolio_health_level: str
    portfolio_health_icon: str
    position_count: int
    healthy_count: int
    warning_count: int
    danger_count: int
    critical_count: int
    near_stop_count: int
    exit_risk_count: int
    loss_count: int
    profit_count: int
    current_stock_exposure_pct: Any
    target_cash_pct: Any
    target_stock_pct: Any
    target_margin_pct: Any
    max_new_position_pct: Any
    max_position_pct: Any
    used_risk_budget_pct: Any
    max_risk_budget_pct: Any
    remaining_risk_budget_pct: Any
    drawdown_pct: Any
    protection_level: str
    protection_icon: str
    exposure_reason: str
    risk_reason: str
    sizing_note: str
    recommendation_lines: str
    notes: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _to_num(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        if isinstance(x, str):
            x = x.replace("%", "").replace(",", ".").strip()
            if x == "":
                return default
        v = pd.to_numeric(pd.Series([x]), errors="coerce").iloc[0]
        if pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default


def _safe_str(x: Any, default: str = "") -> str:
    try:
        if pd.isna(x):
            return default
    except Exception:
        pass
    s = str(x).strip()
    return s if s else default


def _clip(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(v)))


def _level_from_health(score: float) -> tuple[str, str]:
    if score >= 80:
        return "EXCELLENT", "🟢"
    if score >= 60:
        return "GOOD", "🟢"
    if score >= 40:
        return "WARNING", "🟡"
    if score >= 20:
        return "DANGER", "🟠"
    return "CRITICAL", "🔴"


def _regime_to_exposure(universe_score: float, qualified_score: float, adjusted_rotation: float) -> tuple[float, float, float, str]:
    """Trả về target_cash, target_stock, target_margin, reason.

    Dùng nguyên tắc bảo thủ cho TTCK Việt Nam:
    - Universe rất yếu thì ưu tiên bảo toàn vốn, kể cả có vài leader.
    - Adjusted Rotation chỉ nâng nhẹ exposure nếu thị trường không panic.
    """
    base = min(universe_score, (universe_score * 0.7 + qualified_score * 0.3))
    if universe_score < 25:
        stock = 10.0
        reason = "Universe PANIC, ưu tiên bảo toàn vốn"
    elif universe_score < 40:
        stock = 25.0
        reason = "Universe WEAK, chỉ giữ tỷ trọng thấp"
    elif universe_score < 55:
        stock = 40.0
        reason = "Universe SIDEWAY, giải ngân chọn lọc"
    elif universe_score < 75:
        stock = 60.0
        reason = "Universe SIDEWAY_UP, có thể nâng tỷ trọng có kiểm soát"
    else:
        stock = 80.0
        reason = "Universe BULL, cho phép tỷ trọng cổ phiếu cao hơn"

    # Rotation adjusted xác nhận dòng tiền, nhưng không được đảo chiều panic.
    if universe_score >= 25:
        if adjusted_rotation >= 70:
            stock += 10.0
            reason += "; rotation adjusted mạnh"
        elif adjusted_rotation < 30:
            stock -= 10.0
            reason += "; rotation adjusted yếu"
    else:
        if adjusted_rotation < 30:
            reason += "; rotation adjusted cũng yếu"
        else:
            reason += "; có leader nhưng không đủ để mở risk khi panic"

    stock = _clip(stock, 0.0, 90.0)
    cash = round(100.0 - stock, 1)
    margin = 0.0 if universe_score < 75 or adjusted_rotation < 70 else 10.0
    return round(cash, 1), round(stock, 1), round(margin, 1), reason


def _drawdown_protection(drawdown_pct: float) -> tuple[str, str, float, str]:
    """drawdown_pct âm là lỗ. Trả về protection level, icon, exposure cap, note."""
    dd = float(drawdown_pct)
    if dd <= -20:
        return "LOCKDOWN", "🔴", 0.0, "Drawdown trên 20%, khóa mua mới"
    if dd <= -15:
        return "CASH_MODE", "🔴", 20.0, "Drawdown trên 15%, ưu tiên Cash Mode"
    if dd <= -10:
        return "HIGH", "🟠", 50.0, "Drawdown trên 10%, giảm mạnh exposure"
    if dd <= -5:
        return "MEDIUM", "🟡", 70.0, "Drawdown trên 5%, giảm size lệnh mới"
    return "NORMAL", "🟢", 100.0, "Drawdown trong ngưỡng bình thường"


def _estimate_used_risk(snapshot: pd.DataFrame, default_risk_per_position: float) -> float:
    if snapshot is None or snapshot.empty:
        return 0.0
    used = 0.0
    for _, r in snapshot.iterrows():
        alloc = _to_num(r.get("Tỷ trọng hiện tại %", 0.0))
        entry = _to_num(r.get("Giá vốn", 0.0))
        stop = _to_num(r.get("Stop đề xuất", 0.0))
        if alloc <= 0:
            continue
        if entry > 0 and stop > 0 and stop < entry:
            position_risk = alloc * ((entry - stop) / entry)
        else:
            position_risk = default_risk_per_position
        used += max(0.0, position_risk)
    return round(used, 2)


def evaluate_portfolio_intelligence(
    snapshot: pd.DataFrame,
    mini_market: Optional[Dict[str, Any]] = None,
    leader_rotation: Optional[Dict[str, Any]] = None,
) -> PortfolioIntelligenceResult:
    mini_market = mini_market or {}
    leader_rotation = leader_rotation or {}

    max_risk_budget = _to_num(os.getenv("VN_PORTFOLIO_MAX_RISK_BUDGET_PCT", "10"), 10.0)
    default_risk_per_position = _to_num(os.getenv("VN_PORTFOLIO_DEFAULT_RISK_PER_POSITION_PCT", "1"), 1.0)
    account_drawdown = _to_num(os.getenv("VN_PORTFOLIO_DRAWDOWN_PCT", "0"), 0.0)
    max_position_base = _to_num(os.getenv("VN_PORTFOLIO_MAX_POSITION_PCT", "15"), 15.0)
    max_new_base = _to_num(os.getenv("VN_PORTFOLIO_MAX_NEW_POSITION_PCT", "8"), 8.0)

    if snapshot is None:
        snapshot = pd.DataFrame()

    n = int(len(snapshot)) if not snapshot.empty else 0
    scores: List[float] = []
    healthy = warning = danger = critical = near_stop = exit_risk = loss = profit = 0

    for _, r in snapshot.iterrows():
        hs = _to_num(r.get("Position Health Score", 50), 50.0)
        scores.append(hs)
        if hs >= 60:
            healthy += 1
        elif hs >= 40:
            warning += 1
        elif hs >= 20:
            danger += 1
        else:
            critical += 1
        if _safe_str(r.get("Position State Code", "")).upper() == "NEAR_STOP":
            near_stop += 1
        if _safe_str(r.get("Exit Risk", "")).upper() in {"CAO", "HIGH"}:
            exit_risk += 1
        pnl = _to_num(r.get("Lãi/lỗ %", 0.0))
        if pnl < 0:
            loss += 1
        elif pnl > 0:
            profit += 1

    if scores:
        avg_health = sum(scores) / len(scores)
        # Phạt thêm nếu nhiều vị thế critical/near stop.
        penalty = min(20.0, critical * 5.0 + near_stop * 4.0 + exit_risk * 3.0)
        portfolio_health = _clip(avg_health - penalty)
    else:
        portfolio_health = 50.0

    health_level, health_icon = _level_from_health(portfolio_health)

    universe_score = _to_num(mini_market.get("score", mini_market.get("Mini Market Score", 50)), 50.0)
    qualified_score = _to_num(mini_market.get("qualified_score", mini_market.get("Mini Market Qualified Score", universe_score)), universe_score)
    adjusted_rotation = _to_num(leader_rotation.get("adjusted_rotation_score", leader_rotation.get("rotation_score", 50)), 50.0)

    target_cash, target_stock, target_margin, exposure_reason = _regime_to_exposure(universe_score, qualified_score, adjusted_rotation)

    prot_level, prot_icon, dd_exposure_cap, dd_note = _drawdown_protection(account_drawdown)
    if target_stock > dd_exposure_cap:
        target_stock = dd_exposure_cap
        target_cash = round(100.0 - target_stock, 1)
        target_margin = 0.0
        exposure_reason += f"; {dd_note}"

    current_exposure = 0.0
    if not snapshot.empty and "Tỷ trọng hiện tại %" in snapshot.columns:
        current_exposure = round(float(pd.to_numeric(snapshot["Tỷ trọng hiện tại %"], errors="coerce").fillna(0).sum()), 2)

    used_risk = _estimate_used_risk(snapshot, default_risk_per_position)
    remaining_risk = round(max(0.0, max_risk_budget - used_risk), 2)
    risk_reason = f"Đã dùng khoảng {used_risk}%/{max_risk_budget}% risk budget"

    # Size lệnh mới: bị kẹp bởi market, drawdown, remaining risk.
    if universe_score < 25 or adjusted_rotation < 25 or remaining_risk <= 0:
        max_new = 0.0
        sizing_note = "Không mở vị thế mới trong trạng thái risk-off"
    else:
        max_new = min(max_new_base, max(0.0, target_stock - current_exposure), remaining_risk * 5.0)
        sizing_note = "Size lệnh mới chỉ là trần tham khảo, cần khớp với entry/stop thực tế"
    max_new = round(_clip(max_new, 0.0, max_new_base), 1)
    max_position = round(min(max_position_base, max(target_stock, 0.0)), 1)

    # Status tổng hợp.
    if target_stock <= 10 or portfolio_health < 20 or prot_level in {"LOCKDOWN", "CASH_MODE"}:
        status, icon = "RISK OFF", "🔴"
        rec = ["🔴 Không mở vị thế mới", "🔴 Ưu tiên tiền mặt", "🔴 Chỉ giữ/thoát vị thế theo Position State"]
    elif target_stock <= 30 or portfolio_health < 40:
        status, icon = "DEFENSIVE", "🟠"
        rec = ["🟠 Hạn chế mua mới", "🟠 Không bình quân giá xuống", "🟠 Chỉ quan sát leader khỏe"]
    elif target_stock <= 60 or portfolio_health < 60:
        status, icon = "BALANCED", "🟡"
        rec = ["🟡 Giải ngân chọn lọc", "🟡 Ưu tiên setup có Health cao", "🟡 Giữ risk/lệnh nhỏ"]
    else:
        status, icon = "RISK ON", "🟢"
        rec = ["🟢 Có thể giải ngân có kiểm soát", "🟢 Ưu tiên leader ngành", "🟢 Vẫn giữ stop/risk budget"]

    notes = f"Universe {universe_score}/100; Qualified {qualified_score}/100; Adjusted Rotation {adjusted_rotation}/100; {dd_note}"

    return PortfolioIntelligenceResult(
        status=status,
        icon=icon,
        portfolio_health_score=round(portfolio_health, 1),
        portfolio_health_level=health_level,
        portfolio_health_icon=health_icon,
        position_count=n,
        healthy_count=healthy,
        warning_count=warning,
        danger_count=danger,
        critical_count=critical,
        near_stop_count=near_stop,
        exit_risk_count=exit_risk,
        loss_count=loss,
        profit_count=profit,
        current_stock_exposure_pct=current_exposure,
        target_cash_pct=target_cash,
        target_stock_pct=round(target_stock, 1),
        target_margin_pct=target_margin,
        max_new_position_pct=max_new,
        max_position_pct=max_position,
        used_risk_budget_pct=used_risk,
        max_risk_budget_pct=max_risk_budget,
        remaining_risk_budget_pct=remaining_risk,
        drawdown_pct=account_drawdown,
        protection_level=prot_level,
        protection_icon=prot_icon,
        exposure_reason=exposure_reason,
        risk_reason=risk_reason,
        sizing_note=sizing_note,
        recommendation_lines="\n".join(rec),
        notes=notes,
    )
