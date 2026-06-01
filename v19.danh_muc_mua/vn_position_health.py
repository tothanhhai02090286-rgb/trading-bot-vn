# -*- coding: utf-8 -*-
"""
vn_position_health.py

Position Health Score cho bot chứng khoán Việt Nam.

Mục tiêu:
- Chấm điểm sức khỏe vị thế từ 0 đến 100.
- Điểm càng cao = vị thế càng khỏe/an toàn.
- Điểm càng thấp = vị thế càng xấu/rủi ro.
- Chỉ bổ sung thông tin quản trị rủi ro, không tự thay đổi lệnh mua/bán.

Thiết kế phù hợp TTCK Việt Nam:
- Ưu tiên bảo vệ vốn khi đã thủng stop hoặc lỗ sâu.
- Hàng chưa về T+2.5 bị trừ điểm thanh khoản hành động vì chưa bán thật được.
- Thanh khoản yếu/gần sàn bị trừ điểm mạnh vì rủi ro khó thoát hàng.
- Sector yếu bị trừ điểm; sector mạnh cộng điểm nhẹ.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class PositionHealthResult:
    score: int
    level: str
    verdict: str
    reasons: List[str]
    risk_score: int
    health_icon: str
    risk_level: str
    risk_icon: str
    action_hint: str
    action_icon: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Giữ field cũ để tương thích CSV/report hiện tại.
        d["reasons_text"] = "; ".join(self.reasons)
        # Field mới cho Telegram format trực quan đã chốt.
        d["reasons_bullets"] = "\n".join([_reason_icon(r) + " " + r for r in self.reasons])
        d["display_line"] = f"Sức khỏe: {self.score}/100 {self.health_icon} {self.level}"
        d["risk_display_line"] = f"Rủi ro: {self.risk_score}/100 {self.risk_icon} {self.risk_level}"
        d["recommendation_line"] = f"{self.action_icon} {self.action_hint}"
        return d


def _num(x: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if x is None:
            return default
        if isinstance(x, str):
            s = x.replace("%", "").replace(",", ".").strip()
            if not s:
                return default
            x = s
        return float(x)
    except Exception:
        return default


def _text(x: Any) -> str:
    if x is None:
        return ""
    return str(x).strip().upper()


def _boolish(x: Any) -> bool:
    if isinstance(x, bool):
        return x
    s = _text(x)
    return s in {"1", "TRUE", "YES", "Y", "CÓ", "CO", "ON"}


def _clamp_int(v: float, lo: int = 0, hi: int = 100) -> int:
    try:
        return int(max(lo, min(hi, round(v))))
    except Exception:
        return lo


def _score_to_level(score: int) -> Tuple[str, str, str]:
    """Health level: điểm càng cao càng tốt."""
    if score >= 80:
        return "EXCELLENT", "Vị thế rất khỏe", "🟢"
    if score >= 60:
        return "GOOD", "Giữ có kiểm soát", "🟢"
    if score >= 40:
        return "WARNING", "Theo dõi sát", "🟡"
    if score >= 20:
        return "DANGER", "Ưu tiên giảm rủi ro", "🟠"
    return "CRITICAL", "Rất xấu, ưu tiên thoát/cắt lỗ nếu bán được", "🔴"


def _risk_to_level(risk_score: int) -> Tuple[str, str]:
    """Risk level: điểm càng cao càng nguy hiểm."""
    if risk_score <= 25:
        return "LOW", "🟢"
    if risk_score <= 50:
        return "MEDIUM", "🟡"
    if risk_score <= 75:
        return "HIGH", "🟠"
    return "CRITICAL", "🔴"


def _action_icon(action_hint: Any, health_level: str) -> str:
    a = _text(action_hint)
    if any(k in a for k in ["CẮT LỖ", "CAT LO", "THOÁT", "THOAT"]):
        return "🔴"
    if any(k in a for k in ["GIẢM", "GIAM", "CHỐT", "CHOT"]):
        return "🟠"
    if any(k in a for k in ["TRAILING", "NÂNG", "NANG"]):
        return "🟣"
    if any(k in a for k in ["MUA", "KIỂM SOÁT", "KIEM SOAT"]):
        return "🔵"
    if any(k in a for k in ["THEO DÕI", "THEO DOI", "TEST"]):
        return "🟡"
    if "GIỮ" in a or "GIU" in a:
        return "🟢"
    if health_level in {"CRITICAL", "DANGER"}:
        return "🔴" if health_level == "CRITICAL" else "🟠"
    if health_level == "WARNING":
        return "🟡"
    return "🟢"


def _reason_icon(reason: str) -> str:
    r = _text(reason)
    if any(k in r for k in ["LỖ", "LO", "STOP", "DƯỚI", "DUOI", "YẾU", "YEU", "SÀN", "SAN", "RỦI RO", "RUI RO", "THOÁT", "THOAT", "CẮT", "CAT", "HIGH", "CRITICAL", "DANGER"]):
        return "❌"
    if any(k in r for k in ["LÃI", "LAI", "TRÊN", "TREN", "MẠNH", "MANH", "TỐT", "TOT", "ỔN", "ON", "THẤP", "THAP", "LOW", "KHỎE", "KHOE"]):
        return "✅"
    return "•"


def calculate_position_health(
    *,
    pnl_pct: Any = None,
    current_price: Any = None,
    stop_price: Any = None,
    position_state_code: Any = "",
    position_risk_level: Any = "",
    can_sell: Any = None,
    can_add: Any = None,
    realtime_ok: Any = None,
    trend: Any = "",
    liquidity_band: Any = "",
    exit_risk: Any = "",
    near_floor: Any = None,
    near_ceiling: Any = None,
    sector_flow: Any = "",
    sector_score: Any = None,
    action: Any = "",
) -> PositionHealthResult:
    """Tính Position Health Score 0-100.

    Hàm này cố tình độc lập với dataframe để dễ test và dễ dùng lại trong
    Render/GitHub Actions. Không tạo side-effect và không đổi action hiện tại.
    """

    score = 85.0  # điểm nền: vị thế bình thường; trừ dần theo rủi ro thực chiến
    reasons: List[str] = []

    pnl = _num(pnl_pct, 0.0) or 0.0
    cur = _num(current_price, None)
    stop = _num(stop_price, None)
    state = _text(position_state_code)
    risk_level = _text(position_risk_level)
    trend_text = _text(trend)
    liq = _text(liquidity_band)
    exit_risk_text = _text(exit_risk)
    flow = _text(sector_flow)
    act = _text(action)

    # 1) PnL: yếu tố thực chiến quan trọng nhất cho vị thế đang nắm giữ.
    if pnl <= -10:
        score -= 30
        reasons.append("Lỗ trên 10%, rủi ro rất cao")
    elif pnl <= -7:
        score -= 24
        reasons.append("Lỗ trên 7%, cần ưu tiên bảo vệ vốn")
    elif pnl <= -5:
        score -= 18
        reasons.append("Lỗ trên 5%, vùng cắt lỗ thực chiến")
    elif pnl <= -3:
        score -= 10
        reasons.append("Lỗ trên 3%, gần vùng stop")
    elif pnl >= 15:
        score += 18
        reasons.append("Lãi trên 15%, vị thế rất tốt nhưng cần trailing")
    elif pnl >= 10:
        score += 14
        reasons.append("Lãi trên 10%, vị thế khỏe")
    elif pnl >= 5:
        score += 8
        reasons.append("Lãi trên 5%, vị thế tích cực")
    elif pnl >= 2:
        score += 3
        reasons.append("Có lãi nhẹ")

    # 2) Position State Decision Tree.
    if state in {"NEAR_STOP"}:
        score -= 16
        reasons.append("Position State: gần/chạm stop")
    elif state in {"EXIT_RISK"}:
        score -= 24
        reasons.append("Position State: rủi ro thoát hàng")
    elif state in {"LOSS_HOLDING"}:
        score -= 10
        reasons.append("Position State: đang lỗ")
    elif state in {"T0_T1_HOLDING"}:
        score -= 6
        reasons.append("Hàng T+0/T+1, chưa linh hoạt xử lý")
    elif state in {"TRAILING_PROFIT"}:
        score += 10
        reasons.append("Position State: đang trailing profit")
    elif state in {"PROFIT_HOLDING"}:
        score += 8
        reasons.append("Position State: đang lãi")
    elif state in {"AVAILABLE_HOLDING"}:
        score += 2

    if risk_level == "CRITICAL":
        score -= 12
        reasons.append("Risk Level từ Position State: CRITICAL")
    elif risk_level == "HIGH":
        score -= 8
        reasons.append("Risk Level từ Position State: HIGH")
    elif risk_level == "LOW":
        score += 4

    # 3) Smart Stop / trend.
    if cur is not None and stop is not None and stop > 0:
        if cur <= stop:
            score -= 15
            reasons.append("Giá hiện tại đã dưới/chạm Smart Stop")
        elif cur <= stop * 1.01:
            score -= 7
            reasons.append("Giá sát Smart Stop dưới 1%")
        elif cur >= stop * 1.08:
            score += 5
            reasons.append("Giá còn cách xa stop")

    if "DƯỚI MA20" in trend_text or "DUOI MA20" in trend_text:
        score -= 5
        reasons.append("Xu hướng dưới MA20")
    elif "TRÊN MA20" in trend_text or "TREN MA20" in trend_text:
        score += 5
        reasons.append("Xu hướng trên MA20")

    # 4) VN Trade Safety: thanh khoản và rủi ro thoát hàng.
    if exit_risk_text in {"CAO", "HIGH"}:
        score -= 18
        reasons.append("Exit Risk cao, có thể khó thoát hàng")
    elif exit_risk_text in {"TRUNG BÌNH", "TRUNG BINH", "MEDIUM"}:
        score -= 8
        reasons.append("Exit Risk trung bình")
    elif exit_risk_text in {"THẤP", "THAP", "LOW"}:
        score += 4
        reasons.append("Exit Risk thấp")

    if liq in {"YẾU", "YEU", "LOW", "KÉM", "KEM"}:
        score -= 12
        reasons.append("Thanh khoản yếu")
    elif liq in {"ỔN", "ON", "TỐT", "TOT", "OK", "GOOD"}:
        score += 4
        reasons.append("Thanh khoản ổn")

    if _boolish(near_floor):
        score -= 14
        reasons.append("Gần giá sàn, rủi ro kẹt thanh khoản")
    if _boolish(near_ceiling):
        score -= 3
        reasons.append("Gần giá trần, hạn chế mua đuổi")

    # 5) Sector Flow.
    sector_score_num = _num(sector_score, None)
    if "YẾU" in flow or "YEU" in flow or flow == "WEAK":
        score -= 8
        reasons.append("Sector Flow yếu")
    elif "MẠNH" in flow or "MANH" in flow or flow == "STRONG":
        score += 8
        reasons.append("Sector Flow mạnh")
    elif sector_score_num is not None:
        if sector_score_num < 40:
            score -= 0
            # Không trừ thêm nếu đã có nhãn Sector Flow yếu để tránh double-count
        elif sector_score_num >= 70:
            score += 6
            reasons.append("Sector Score tốt")

    # 6) Khả năng hành động và độ tin cậy giá.
    if can_sell is not None and not _boolish(can_sell):
        score -= 6
        reasons.append("Chưa bán được theo T+2.5")
    if can_add is not None and _boolish(can_add) and pnl >= 3:
        score += 4
        reasons.append("Có thể mua thêm theo quản trị vị thế")
    if realtime_ok is not None and not _boolish(realtime_ok):
        score -= 4
        reasons.append("Giá không realtime, cần xác nhận lại trên app chứng khoán")

    # 7) Action hiện tại chỉ dùng làm tín hiệu xác nhận, không tự thay đổi action.
    if act in {"THOÁT VỊ THẾ", "CẮT LỖ"}:
        score -= 3
        reasons.append("Action hiện tại ưu tiên thoát/cắt lỗ")
    elif act in {"GIẢM VỊ THẾ", "GIẢM TỶ TRỌNG"}:
        score -= 2
        reasons.append("Action hiện tại yêu cầu giảm rủi ro")
    elif act in {"GIỮ", "THEO DÕI VỊ THẾ"}:
        score += 2

    final_score = _clamp_int(score)
    level, verdict, health_icon = _score_to_level(final_score)
    risk_score = 100 - final_score
    risk_level, risk_icon = _risk_to_level(risk_score)

    # Giữ danh sách lý do gọn để Telegram không quá dài.
    compact_reasons: List[str] = []
    for r in reasons:
        if r and r not in compact_reasons:
            compact_reasons.append(r)
    compact_reasons = compact_reasons[:6]
    if not compact_reasons:
        compact_reasons = ["Không có yếu tố rủi ro nổi bật"]

    return PositionHealthResult(
        score=final_score,
        level=level,
        verdict=verdict,
        reasons=compact_reasons,
        risk_score=risk_score,
        health_icon=health_icon,
        risk_level=risk_level,
        risk_icon=risk_icon,
        action_hint=str(action).strip() or verdict,
        action_icon=_action_icon(action, level),
    )
