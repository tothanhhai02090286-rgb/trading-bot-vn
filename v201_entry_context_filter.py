# -*- coding: utf-8 -*-
"""
v201_entry_context_filter.py

V20.1 — ENTRY CONTEXT FILTER FOR V18.2 REALTIME
- Module để V18.2 import.
- Phát hiện entry lưng chừng / FOMO / yếu.
- Không tự quyết định mua bán, chỉ hạ recommendation.
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


def classify_market_context_realtime(
    market_regime: str = "",
    market_ret5: Optional[float] = None,
    market_ret20: Optional[float] = None,
    market_dist_ma20_pct: Optional[float] = None,
    market_volume_ratio: Optional[float] = None,
) -> Dict[str, Any]:
    regime = str(market_regime or "").upper().strip()
    ret5 = _num(market_ret5)
    ret20 = _num(market_ret20)
    dist = _num(market_dist_ma20_pct)
    vol = _num(market_volume_ratio)
    penalty = 0
    reasons = []

    if regime in ["RẤT YẾU", "YẾU", "RISK OFF", "MARKET RISK-OFF"]:
        label = "MARKET RISK-OFF"
        penalty += 35
        reasons.append("Regime thị trường yếu")
    elif regime in ["TĂNG MẠNH", "TÍCH CỰC"]:
        label = "MARKET ỦNG HỘ"
        reasons.append("Regime thị trường ủng hộ")
    else:
        label = "MARKET TRUNG TÍNH"
        penalty += 10
        reasons.append("Market trung tính")

    if ret5 is not None and ret5 > 4:
        label = "MARKET HƯNG PHẤN / DỄ FOMO"
        penalty += 15
        reasons.append("VNINDEX tăng nhanh 5 phiên")
    if dist is not None and dist > 5:
        label = "MARKET HƯNG PHẤN / DỄ FOMO"
        penalty += 15
        reasons.append("VNINDEX xa MA20")
    if ret20 is not None and ret20 < -5:
        label = "MARKET RISK-OFF"
        penalty += 25
        reasons.append("VNINDEX ret20 âm mạnh")
    if vol is not None and vol > 2.5:
        penalty += 10
        reasons.append("Volume thị trường spike")

    return {"market_context": label, "market_penalty": int(penalty), "market_reasons": reasons[:5]}


def classify_entry_context_realtime(
    price: Optional[float],
    vwap: Optional[float] = None,
    ref: Optional[float] = None,
    buy_low: Optional[float] = None,
    buy_high: Optional[float] = None,
    session_high_prev: Optional[float] = None,
    volume_ratio: Optional[float] = None,
    market_context: str = "",
) -> Dict[str, Any]:
    price = _num(price)
    vwap = _num(vwap)
    ref = _num(ref)
    buy_low = _num(buy_low)
    buy_high = _num(buy_high)
    session_high_prev = _num(session_high_prev)
    volume_ratio = _num(volume_ratio)
    reasons = []
    penalty = 0
    label = "ENTRY UNKNOWN"
    action_modifier = "KEEP"

    if price is None:
        return {"entry_context": "NO PRICE", "entry_penalty": 100, "action_modifier": "BLOCK", "reasons": ["Không có giá realtime"]}

    in_buy_zone = buy_low is not None and buy_high is not None and buy_low <= price <= buy_high
    near_buy_zone = False
    if buy_low is not None and buy_high is not None:
        near_buy_zone = buy_low * 0.995 <= price <= buy_high * 1.01

    above_vwap = vwap is not None and price >= vwap
    near_vwap = vwap is not None and abs(price / vwap - 1) * 100 <= 0.8
    breakout_ok = session_high_prev is not None and price >= session_high_prev * 1.003 and above_vwap
    fomo_volume = volume_ratio is not None and volume_ratio >= 3.0
    weak_volume = volume_ratio is not None and volume_ratio < 1.0

    if in_buy_zone and (above_vwap or near_vwap):
        label = "ENTRY PULLBACK ĐẸP"
        reasons.append("Giá trong buy zone và không lệch VWAP xấu")
    elif breakout_ok and not fomo_volume:
        label = "ENTRY BREAKOUT RÕ"
        reasons.append("Giá vượt vùng cao trước đó và trên VWAP")
    elif near_buy_zone:
        label = "ENTRY GẦN VÙNG MUA"
        penalty += 10
        action_modifier = "DOWNGRADE_ONE"
        reasons.append("Gần buy zone nhưng chưa thật sự đẹp")
    else:
        label = "ENTRY LƯNG CHỪNG"
        penalty += 30
        action_modifier = "DOWNGRADE_TO_WATCH"
        reasons.append("Không rõ pullback đẹp hay breakout rõ")

    if vwap is not None:
        dist_vwap = (price / vwap - 1) * 100
        if dist_vwap > 2.0:
            label = "ENTRY XA VWAP / FOMO"
            penalty += 20
            action_modifier = "DOWNGRADE_TO_WATCH"
            reasons.append(f"Giá xa VWAP {dist_vwap:.2f}%, dễ FOMO")
        elif dist_vwap < -0.8:
            label = "ENTRY DƯỚI VWAP / YẾU"
            penalty += 25
            action_modifier = "DOWNGRADE_TO_WATCH"
            reasons.append(f"Giá dưới VWAP {dist_vwap:.2f}%, entry yếu")

    if fomo_volume:
        penalty += 20
        action_modifier = "DOWNGRADE_TO_WATCH"
        reasons.append("Volume spike quá mạnh, dễ FOMO")
    elif weak_volume:
        penalty += 15
        if action_modifier == "KEEP":
            action_modifier = "DOWNGRADE_ONE"
        reasons.append("Volume chưa đủ ủng hộ")

    market_context_u = str(market_context or "").upper()
    if "RISK-OFF" in market_context_u or "RẤT YẾU" in market_context_u:
        penalty += 30
        action_modifier = "DOWNGRADE_TO_WATCH"
        reasons.append("Market context xấu, không nên nâng entry")
    elif "FOMO" in market_context_u or "HƯNG PHẤN" in market_context_u:
        penalty += 15
        if action_modifier == "KEEP":
            action_modifier = "DOWNGRADE_ONE"
        reasons.append("Market hưng phấn, tránh mua đuổi")

    if penalty >= 60:
        action_modifier = "BLOCK"

    return {"entry_context": label, "entry_penalty": int(penalty), "action_modifier": action_modifier, "reasons": reasons[:5]}


def apply_entry_context_cap(recommendation: str, ctx: Dict[str, Any]) -> str:
    rec = str(recommendation or "WATCH").upper()
    mod = ctx.get("action_modifier", "KEEP")
    order = ["KHÔNG VÀO", "WATCH", "TEST NHỎ", "BUY NHỎ", "BUY CÓ KIỂM SOÁT"]
    if rec not in order:
        rec = "WATCH"
    if mod == "KEEP":
        return rec
    if mod == "BLOCK":
        return "KHÔNG VÀO"
    if mod == "DOWNGRADE_TO_WATCH":
        return "WATCH" if order.index(rec) > order.index("WATCH") else rec
    if mod == "DOWNGRADE_ONE":
        return order[max(0, order.index(rec) - 1)]
    return rec
