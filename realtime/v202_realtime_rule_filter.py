# -*- coding: utf-8 -*-
"""
v202_realtime_rule_filter.py

V20.2 — REALTIME RULE FILTER FOR V18.2

Vai trò:
- Module nhẹ để V18.2 gọi sau khi có recommendation.
- Không tự nâng BUY.
- Chỉ downgrade / block dựa trên context cụ thể.

Hàm chính:
- evaluate_v202_realtime_context(...)
- apply_v202_rule_cap(recommendation, result)
"""

from __future__ import annotations

from typing import Optional, Dict, Any


def _num(x):
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def evaluate_v202_realtime_context(
    price: Optional[float],
    vwap: Optional[float] = None,
    ma20: Optional[float] = None,
    ref: Optional[float] = None,
    volume_ratio: Optional[float] = None,
    stock_ret5: Optional[float] = None,
    stock_ret20: Optional[float] = None,
    market_ret5: Optional[float] = None,
    market_dist_ma20_pct: Optional[float] = None,
    market_context: str = "",
) -> Dict[str, Any]:
    price = _num(price)
    vwap = _num(vwap)
    ma20 = _num(ma20)
    ref = _num(ref)
    volume_ratio = _num(volume_ratio)
    stock_ret5 = _num(stock_ret5)
    stock_ret20 = _num(stock_ret20)
    market_ret5 = _num(market_ret5)
    market_dist_ma20_pct = _num(market_dist_ma20_pct)

    flags = []
    reasons = []
    penalty = 0
    action = "KEEP"

    if price is None:
        return {
            "v202_action": "BLOCK",
            "v202_penalty": 100,
            "v202_flags": ["NO_PRICE"],
            "v202_reasons": ["Không có giá realtime"],
        }

    if ma20 is not None and ma20 > 0:
        dist_ma20 = (price / ma20 - 1) * 100
        if dist_ma20 > 8:
            flags.append("STOCK_DIST_MA20_GT8")
            reasons.append(f"Giá xa MA20 {dist_ma20:.2f}%")
            penalty += 30
        elif 3 < dist_ma20 <= 8:
            flags.append("STOCK_DIST_MA20_3_8")
            reasons.append(f"Giá trên MA20 lưng chừng {dist_ma20:.2f}%")
            penalty += 15
        elif dist_ma20 < -3:
            flags.append("STOCK_BELOW_MA20")
            reasons.append(f"Giá dưới MA20 {dist_ma20:.2f}%")
            penalty += 25

    if vwap is not None and vwap > 0:
        dist_vwap = (price / vwap - 1) * 100
        if dist_vwap > 2:
            flags.append("PRICE_FAR_ABOVE_VWAP")
            reasons.append(f"Giá xa VWAP {dist_vwap:.2f}%")
            penalty += 20
        elif dist_vwap < -0.8:
            flags.append("PRICE_BELOW_VWAP")
            reasons.append(f"Giá dưới VWAP {dist_vwap:.2f}%")
            penalty += 25

    if volume_ratio is not None:
        if volume_ratio > 3:
            flags.append("VOLUME_SPIKE_GT3")
            reasons.append(f"Volume spike {volume_ratio:.2f}x")
            penalty += 25
        elif volume_ratio < 1:
            flags.append("VOLUME_WEAK_LT1")
            reasons.append(f"Volume yếu {volume_ratio:.2f}x")
            penalty += 10

    if stock_ret5 is not None and stock_ret5 > 8:
        flags.append("STOCK_RET5_HOT")
        reasons.append(f"Cổ phiếu tăng nóng 5 phiên {stock_ret5:.2f}%")
        penalty += 20

    if stock_ret20 is not None and stock_ret20 > 15:
        flags.append("STOCK_RET20_HOT")
        reasons.append(f"Cổ phiếu tăng nóng 20 phiên {stock_ret20:.2f}%")
        penalty += 20

    if market_ret5 is not None and market_ret5 > 4:
        flags.append("MARKET_RET5_HOT")
        reasons.append(f"VNINDEX tăng nóng 5 phiên {market_ret5:.2f}%")
        penalty += 15

    if market_dist_ma20_pct is not None and market_dist_ma20_pct > 5:
        flags.append("MARKET_DIST_MA20_GT5")
        reasons.append(f"VNINDEX xa MA20 {market_dist_ma20_pct:.2f}%")
        penalty += 15

    mc = str(market_context or "").upper()
    if "RISK-OFF" in mc or "RẤT YẾU" in mc:
        flags.append("MARKET_RISK_OFF")
        reasons.append("Market risk-off")
        penalty += 30
    elif "FOMO" in mc or "HƯNG PHẤN" in mc:
        flags.append("MARKET_FOMO")
        reasons.append("Market hưng phấn / dễ FOMO")
        penalty += 20

    # Combo penalties from V20.2 thinking.
    if "MARKET_RET5_HOT" in flags and ("STOCK_DIST_MA20_GT8" in flags or "VOLUME_SPIKE_GT3" in flags):
        flags.append("COMBO_MARKET_HOT_STOCK_FOMO")
        reasons.append("Market nóng + cổ phiếu FOMO")
        penalty += 25

    if "STOCK_RET20_HOT" in flags and "VOLUME_SPIKE_GT3" in flags:
        flags.append("COMBO_STOCK_HOT_VOLUME_SPIKE")
        reasons.append("Cổ phiếu đã tăng nóng + volume spike")
        penalty += 25

    if "STOCK_BELOW_MA20" in flags and "PRICE_BELOW_VWAP" in flags:
        flags.append("COMBO_WEAK_ENTRY")
        reasons.append("Giá dưới MA20 và dưới VWAP")
        penalty += 20

    if penalty >= 60:
        action = "BLOCK_OR_WATCH"
    elif penalty >= 30:
        action = "DOWNGRADE_TO_WATCH"
    elif penalty >= 15:
        action = "DOWNGRADE_ONE"
    else:
        action = "KEEP"

    return {
        "v202_action": action,
        "v202_penalty": int(penalty),
        "v202_flags": flags,
        "v202_reasons": reasons[:6],
    }


def apply_v202_rule_cap(recommendation: str, result: Dict[str, Any]) -> str:
    rec = str(recommendation or "WATCH").upper()
    action = result.get("v202_action", "KEEP")

    order = ["KHÔNG VÀO", "WATCH", "TEST NHỎ", "BUY NHỎ", "BUY CÓ KIỂM SOÁT"]
    if rec not in order:
        rec = "WATCH"

    if action == "KEEP":
        return rec
    if action == "BLOCK_OR_WATCH":
        return "WATCH" if order.index(rec) >= order.index("TEST NHỎ") else rec
    if action == "DOWNGRADE_TO_WATCH":
        return "WATCH" if order.index(rec) > order.index("WATCH") else rec
    if action == "DOWNGRADE_ONE":
        return order[max(0, order.index(rec) - 1)]
    return rec
