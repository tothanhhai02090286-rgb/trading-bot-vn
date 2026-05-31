# -*- coding: utf-8 -*-
"""
vn_position_state.py

Position State Decision Tree for Vietnamese stock positions.

This module is intentionally defensive and dependency-light so V19.2 can
import it safely on Render/GitHub Actions. It classifies each holding before
final action selection, separating T+ holdings, available holdings, profit,
loss, near-stop, trailing-profit, and exit-liquidity risk states.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional, Tuple


NEAR_STOP_BUFFER_PCT = float(os.getenv("VN_POSITION_NEAR_STOP_BUFFER_PCT", "2.0"))
PROFIT_HOLD_PCT = float(os.getenv("VN_POSITION_PROFIT_HOLD_PCT", "5.0"))
TRAILING_PROFIT_PCT = float(os.getenv("VN_POSITION_TRAILING_PROFIT_PCT", "8.0"))
STOP_LOSS_WARN_PCT = float(os.getenv("VN_POSITION_STOP_LOSS_WARN_PCT", "3.0"))
STOP_LOSS_ACTION_PCT = float(os.getenv("VN_POSITION_STOP_LOSS_ACTION_PCT", "5.0"))
BLOCK_ADD_WHEN_LOSS = os.getenv("VN_POSITION_BLOCK_ADD_WHEN_LOSS", "1").strip() == "1"
BLOCK_ADD_WHEN_NOT_SELLABLE = os.getenv("VN_POSITION_BLOCK_ADD_WHEN_NOT_SELLABLE", "1").strip() == "1"

SELL_ACTIONS = {"THOÁT VỊ THẾ", "GIẢM VỊ THẾ", "CHỐT BỚT NHẸ", "CHỐT MẠNH", "CẮT LỖ"}
ADD_ACTIONS = {"MUA THÊM NHỎ", "MUA THÊM", "BUY MORE"}
HOLD_ACTIONS = {"GIỮ", "THEO DÕI VỊ THẾ"}


@dataclass
class PositionStateResult:
    state_code: str
    state_label: str
    action_hint: str
    risk_level: str
    reason: str
    can_sell: bool
    can_add: bool
    is_near_stop: bool
    is_trailing_profit: bool
    is_exit_risk: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _to_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        if isinstance(x, str):
            x = x.replace("%", "").replace(",", ".").strip()
            if x == "":
                return default
        return float(x)
    except Exception:
        return default


def _safe_str(x: Any, default: str = "") -> str:
    try:
        if x is None:
            return default
        s = str(x).strip()
        return s if s else default
    except Exception:
        return default


def _is_high_exit_risk(safety: Optional[Dict[str, Any]]) -> Tuple[bool, str]:
    if not safety:
        return False, ""
    exit_risk = _safe_str(safety.get("exit_risk", "")).upper()
    band = _safe_str(safety.get("liquidity_band", "")).upper()
    near_floor = bool(safety.get("near_floor", False))
    if near_floor:
        return True, "gần sàn"
    if exit_risk in {"HIGH", "CAO", "VERY_HIGH", "RẤT CAO"}:
        return True, f"exit risk {exit_risk}"
    if band in {"MỎNG", "YẾU", "THIN", "WEAK"}:
        return True, f"thanh khoản {band}"
    return False, ""


def classify_position_state(
    *,
    qty: Any,
    pnl_pct: float,
    current_price: Optional[float],
    stop_price: Optional[float],
    sellable: bool,
    holding_days: Optional[float] = None,
    available_qty: Any = None,
    safety: Optional[Dict[str, Any]] = None,
) -> PositionStateResult:
    """Classify a holding into a practical Vietnam-market position state."""
    qty_f = _to_float(qty, 0.0)
    available_f = _to_float(available_qty, qty_f if sellable else 0.0)

    if qty_f <= 0:
        return PositionStateResult(
            "NO_POSITION", "Chưa có hàng", "KHÔNG MUA", "LOW",
            "Không có vị thế trong positions_v19.csv", False, False, False, False, False,
        )

    exit_risk, exit_risk_reason = _is_high_exit_risk(safety)

    if not sellable or available_f <= 0:
        return PositionStateResult(
            "T0_T1_HOLDING", "Hàng T+0/T+1 chưa bán được", "THEO DÕI RỦI RO", "MEDIUM",
            "Hàng chưa đủ T+/chưa có khối lượng bán được; chỉ cảnh báo rủi ro, không báo bán thật",
            False, False, False, False, exit_risk,
        )

    if exit_risk:
        return PositionStateResult(
            "EXIT_RISK", "Rủi ro thoát hàng", "THOÁT KHI CÓ THANH KHOẢN", "HIGH",
            f"Có rủi ro thoát hàng do {exit_risk_reason}; không bán cơ học nếu thanh khoản không thuận lợi",
            True, False, False, False, True,
        )

    near_stop = False
    if current_price is not None and stop_price is not None and current_price > 0 and stop_price > 0:
        near_stop = current_price <= stop_price * (1 + NEAR_STOP_BUFFER_PCT / 100.0)

    if current_price is not None and stop_price is not None and current_price <= stop_price:
        return PositionStateResult(
            "NEAR_STOP", "Chạm/vượt stop", "CẮT LỖ", "HIGH",
            "Giá hiện tại đã chạm hoặc thấp hơn stop đề xuất", True, False, True, False, False,
        )

    if near_stop or pnl_pct <= -STOP_LOSS_WARN_PCT:
        level = "HIGH" if pnl_pct <= -STOP_LOSS_ACTION_PCT else "MEDIUM"
        hint = "CẮT LỖ" if pnl_pct <= -STOP_LOSS_ACTION_PCT else "GIẢM TỶ TRỌNG"
        return PositionStateResult(
            "NEAR_STOP", "Gần stoploss", hint, level,
            f"Lãi/lỗ {pnl_pct:.2f}% và/hoặc giá đang gần stop đề xuất", True, False, True, False, False,
        )

    if pnl_pct >= TRAILING_PROFIT_PCT:
        return PositionStateResult(
            "TRAILING_PROFIT", "Lãi tốt - cần trailing", "NÂNG TRAILING", "MEDIUM",
            f"Lãi {pnl_pct:.2f}% đã đủ vùng trailing/chốt một phần", True, True, False, True, False,
        )

    if pnl_pct >= PROFIT_HOLD_PCT:
        return PositionStateResult(
            "PROFIT_HOLDING", "Đang lãi", "GIỮ CÓ KIỂM SOÁT", "LOW",
            f"Lãi {pnl_pct:.2f}% nhưng chưa tới vùng chốt mạnh", True, True, False, False, False,
        )

    if pnl_pct < 0:
        return PositionStateResult(
            "LOSS_HOLDING", "Đang lỗ", "KHÔNG MUA THÊM", "MEDIUM",
            f"Vị thế đang lỗ {pnl_pct:.2f}%; không bình quân xuống nếu chưa có tín hiệu xác nhận", True, False, False, False, False,
        )

    return PositionStateResult(
        "AVAILABLE_HOLDING", "Hàng đã về", "GIỮ", "LOW",
        "Hàng đã bán được, chưa có tín hiệu rủi ro/lợi nhuận mạnh", True, True, False, False, False,
    )


def adjust_action_by_position_state(
    action: str,
    raw_action: str,
    state: PositionStateResult,
    *,
    pnl_pct: float = 0.0,
    add_ok: bool = False,
) -> Tuple[str, str]:
    """Apply state constraints to the existing V19.2 action.

    Returns (new_action, note). The function is conservative: it avoids
    strengthening buy/add decisions and mostly blocks impossible/risky actions.
    """
    current_action = _safe_str(action, "THEO DÕI VỊ THẾ")
    raw = _safe_str(raw_action, current_action)

    if state.state_code == "NO_POSITION":
        return current_action, state.reason

    if state.state_code == "T0_T1_HOLDING":
        if current_action in SELL_ACTIONS or raw in SELL_ACTIONS:
            return "CHƯA BÁN ĐƯỢC - THEO DÕI RỦI RO", state.reason
        if current_action in ADD_ACTIONS:
            return "THEO DÕI VỊ THẾ", "Không mua thêm khi hàng chưa về; " + state.reason
        return current_action, state.reason

    if state.state_code == "EXIT_RISK":
        if current_action in SELL_ACTIONS or raw in SELL_ACTIONS:
            return "THOÁT KHI CÓ THANH KHOẢN", state.reason
        if current_action in ADD_ACTIONS:
            return "THEO DÕI VỊ THẾ", "Không mua thêm khi exit risk cao; " + state.reason
        return current_action, state.reason

    if state.state_code == "NEAR_STOP":
        if current_action in ADD_ACTIONS:
            return "GIẢM TỶ TRỌNG", "Không mua thêm khi gần stop; " + state.reason
        if current_action in HOLD_ACTIONS:
            return state.action_hint, state.reason
        return current_action, state.reason

    if state.state_code == "TRAILING_PROFIT":
        if current_action in ADD_ACTIONS:
            return "NÂNG TRAILING", "Ưu tiên bảo vệ lãi hơn mua thêm; " + state.reason
        if current_action in HOLD_ACTIONS:
            return "NÂNG TRAILING", state.reason
        return current_action, state.reason

    if state.state_code == "PROFIT_HOLDING":
        if current_action in ADD_ACTIONS and not add_ok:
            return "GIỮ", "Chưa đủ điều kiện mua thêm; " + state.reason
        return current_action, state.reason

    if state.state_code == "LOSS_HOLDING":
        if BLOCK_ADD_WHEN_LOSS and current_action in ADD_ACTIONS:
            return "THEO DÕI VỊ THẾ", "Không bình quân xuống khi vị thế đang lỗ; " + state.reason
        return current_action, state.reason

    return current_action, state.reason


def position_state_summary(state: PositionStateResult) -> str:
    return f"{state.state_code} - {state.state_label}; gợi ý: {state.action_hint}; rủi ro: {state.risk_level}"
