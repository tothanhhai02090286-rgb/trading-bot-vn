# -*- coding: utf-8 -*-
"""
vn_mini_market_regime.py

Mini Market Regime Engine cho bot chứng khoán Việt Nam.

V2 — Dual Branch:
- Universe branch: toàn bộ universe gốc trong cache_stock, ví dụ 138 mã.
- Qualified branch: nhóm đã lọc trong intraday_watchlist_v17.csv, ví dụ 10 mã.

Mục tiêu:
- Nhìn được sức khỏe tổng thể của "thị trường mini".
- Đồng thời nhìn được chất lượng nhóm leader/qualified còn lại sau các lớp lọc.
- Không ghi đè Position State, VN Trade Safety, Smart Stop hay T+2.5.
- Chỉ cung cấp context thị trường và bias hành động mềm cho Telegram/CSV.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


@dataclass
class RegimeBranch:
    size: int
    valid_count: int
    score: int
    regime: str
    icon: str
    recommendation: str
    breadth_score: int
    leadership_score: int
    risk_pressure_score: int
    money_flow_score: int
    pct_up: float
    pct_above_ma20: float
    pct_above_ma50: float
    pct_healthy: float
    pct_very_healthy: float
    pct_weak: float
    pct_near_stop_proxy: float
    money_flow_label: str
    notes: List[str]


@dataclass
class MiniMarketRegimeResult:
    universe_size: int
    valid_count: int
    score: int
    regime: str
    icon: str
    recommendation: str
    breadth_score: int
    leadership_score: int
    risk_pressure_score: int
    money_flow_score: int
    pct_up: float
    pct_above_ma20: float
    pct_above_ma50: float
    pct_healthy: float
    pct_very_healthy: float
    pct_weak: float
    pct_near_stop_proxy: float
    money_flow_label: str
    notes: List[str]
    qualified_size: int = 0
    qualified_valid_count: int = 0
    qualified_score: int = 0
    qualified_regime: str = "UNKNOWN"
    qualified_icon: str = "⚪"
    qualified_recommendation: str = ""
    qualified_pct_up: float = 0.0
    qualified_pct_above_ma20: float = 0.0
    qualified_pct_above_ma50: float = 0.0
    qualified_pct_healthy: float = 0.0
    qualified_pct_very_healthy: float = 0.0
    qualified_pct_weak: float = 0.0
    qualified_money_flow_label: str = "UNKNOWN"
    qualified_money_flow_score: int = 0
    qualified_notes: List[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d.get("qualified_notes") is None:
            d["qualified_notes"] = []
        d["notes_text"] = "; ".join(self.notes or [])
        d["qualified_notes_text"] = "; ".join(self.qualified_notes or [])
        d["display_title"] = f"{self.icon} {self.regime}"
        d["recommendation_lines"] = _recommendation_lines(self.regime)
        d["qualified_display_title"] = f"{self.qualified_icon} {self.qualified_regime}"
        d["qualified_recommendation_lines"] = _recommendation_lines(self.qualified_regime)
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
        v = float(x)
        if pd.isna(v):
            return default
        return v
    except Exception:
        return default


def _text(x: Any) -> str:
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass
    return str(x).strip().upper()


def _clamp(v: float, lo: int = 0, hi: int = 100) -> int:
    try:
        return int(max(lo, min(hi, round(v))))
    except Exception:
        return lo


def _find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    if df is None or df.empty:
        return None
    lower = {str(c).lower(): c for c in df.columns}
    for c in candidates:
        if c in df.columns:
            return c
        if c.lower() in lower:
            return lower[c.lower()]
    return None


def _normalize_price(x: Any) -> Optional[float]:
    v = _num(x, None)
    if v is None:
        return None
    if v > 1000:
        v = v / 1000.0
    return float(v)


def _read_csv_smart(path: str) -> pd.DataFrame:
    for enc in ["utf-8-sig", "utf-8", "cp1258", "latin1"]:
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            pass
    return pd.read_csv(path)


def _load_history(symbol: str, cache_dir: str) -> pd.DataFrame:
    symbol = str(symbol).upper().strip()
    candidates = [
        os.path.join(cache_dir, f"{symbol}.csv"),
        os.path.join(cache_dir, f"{symbol.upper()}.csv"),
        f"{symbol}.csv",
    ]
    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            raw = _read_csv_smart(path)
            close_col = _find_col(raw, ["close", "Close", "adj_close", "price", "Giá đóng cửa"])
            open_col = _find_col(raw, ["open", "Open", "Giá mở cửa"])
            vol_col = _find_col(raw, ["volume", "Volume", "vol", "Khối lượng"])
            if close_col is None:
                continue
            out = pd.DataFrame()
            out["close"] = pd.to_numeric(raw[close_col], errors="coerce").apply(_normalize_price)
            out["open"] = pd.to_numeric(raw[open_col], errors="coerce").apply(_normalize_price) if open_col else out["close"].shift(1)
            out["volume"] = pd.to_numeric(raw[vol_col], errors="coerce").fillna(0) if vol_col else 0
            out = out.dropna(subset=["close"]).reset_index(drop=True)
            return out
        except Exception:
            continue
    return pd.DataFrame()


def _symbol_col(df: pd.DataFrame) -> Optional[str]:
    return _find_col(df, ["Mã", "Ma", "Symbol", "Ticker", "ticker", "Mã CP"])


def _infer_symbols(watchlist_df: pd.DataFrame) -> List[str]:
    if watchlist_df is None or watchlist_df.empty:
        return []
    c = _symbol_col(watchlist_df)
    if c is None:
        return []
    syms = []
    for x in watchlist_df[c].tolist():
        s = str(x).upper().strip()
        if s and s not in syms:
            syms.append(s)
    return syms


def _infer_cache_symbols(cache_dir: str) -> List[str]:
    if not cache_dir or not os.path.isdir(cache_dir):
        return []
    syms: List[str] = []
    for fn in sorted(os.listdir(cache_dir)):
        if not fn.lower().endswith(".csv"):
            continue
        name = os.path.splitext(fn)[0].upper().strip()
        if name and name not in syms:
            syms.append(name)
    return syms


def _watchlist_proxy(row: pd.Series) -> Dict[str, Any]:
    """Fallback/proxy từ watchlist nếu cache thiếu."""
    final_decision = _text(row.get("Final Decision", row.get("Hành động", "")))
    decision_mode = _text(row.get("Decision Mode", ""))
    regime = _text(row.get("Regime Strength", row.get("Regime", "")))
    group = _text(row.get("Nhóm realtime", ""))
    sector_flow = _text(row.get("Sector Flow", row.get("Dòng tiền ngành", "")))
    score = _num(row.get("Score", row.get("Điểm", row.get("Meta Score", None))), None)

    healthy_words = ["MUA", "BUY", "GIỮ", "GIU", "STRONG", "TỐT", "TOT", "LEADER", "BREAKOUT"]
    weak_words = ["BÁN", "BAN", "SELL", "YẾU", "YEU", "WEAK", "TRÁNH", "TRANH", "THOÁT", "THOAT"]
    blob = " ".join([final_decision, decision_mode, regime, group, sector_flow])
    healthy = any(w in blob for w in healthy_words) or (score is not None and score >= 60)
    very_healthy = any(w in blob for w in ["STRONG", "LEADER", "BREAKOUT"]) or (score is not None and score >= 80)
    weak = any(w in blob for w in weak_words) or (score is not None and score <= 40)
    return {"healthy": healthy, "very_healthy": very_healthy, "weak": weak, "sector_flow": sector_flow}


def _regime_from_score(score: int) -> Tuple[str, str, str]:
    if score >= 75:
        return "BULL", "🟢", "Có thể mua mới có kiểm soát, ưu tiên cổ phiếu khỏe và còn nền thanh khoản."
    if score >= 55:
        return "SIDEWAY_UP", "🟡", "Môi trường nghiêng tích cực, mua chọn lọc/test tỷ trọng vừa phải."
    if score >= 40:
        return "SIDEWAY", "🟡", "Thị trường phân hóa, ưu tiên cổ phiếu khỏe, hạn chế mua đuổi."
    if score >= 25:
        return "WEAK", "🟠", "Hạn chế mua mới, không bình quân giá xuống, ưu tiên quản trị vị thế."
    return "PANIC", "🔴", "Không mở vị thế mới, ưu tiên tiền mặt và thoát rủi ro khi có thanh khoản."


def _recommendation_lines(regime: str) -> str:
    if regime == "BULL":
        return "🟢 Có thể mua mới có kiểm soát\n🟢 Ưu tiên giữ cổ phiếu khỏe\n🟢 Có thể nâng tỷ trọng khi tín hiệu đồng thuận"
    if regime == "SIDEWAY_UP":
        return "🟡 Mua chọn lọc/test vừa phải\n🟡 Không mua đuổi quá xa nền giá\n🟢 Giữ cổ phiếu Health tốt"
    if regime == "SIDEWAY":
        return "🟡 Test nhỏ, chọn lọc cổ phiếu\n🟡 Ưu tiên quản trị vị thế\n🟠 Tránh full tỷ trọng"
    if regime == "WEAK":
        return "🟠 Hạn chế mua mới\n🟠 Không bình quân giá xuống\n🟠 Ưu tiên giữ tiền mặt/quản trị rủi ro"
    if regime == "PANIC":
        return "🔴 Không mở vị thế mới\n🔴 Ưu tiên tiền mặt\n🔴 Thoát rủi ro khi có thanh khoản"
    return "⚪ Chưa đủ dữ liệu để kết luận"


def _label_money_flow(value: float) -> str:
    if value >= 70:
        return "MẠNH"
    if value >= 55:
        return "TÍCH CỰC"
    if value >= 40:
        return "TRUNG TÍNH"
    if value >= 25:
        return "YẾU"
    return "RẤT YẾU"


def _build_row_by_symbol(watchlist_df: pd.DataFrame) -> Dict[str, pd.Series]:
    row_by_symbol: Dict[str, pd.Series] = {}
    sym_col = _symbol_col(watchlist_df)
    if sym_col:
        for _, r in watchlist_df.iterrows():
            s = str(r.get(sym_col, "")).upper().strip()
            if s and s not in row_by_symbol:
                row_by_symbol[s] = r
    return row_by_symbol


def _evaluate_branch(
    symbols: List[str],
    *,
    cache_dir: str,
    watchlist_df: pd.DataFrame,
    branch_name: str,
    use_proxy: bool,
) -> RegimeBranch:
    size = len(symbols)
    if size == 0:
        regime, icon, rec = _regime_from_score(50)
        return RegimeBranch(
            size=0, valid_count=0, score=50, regime="UNKNOWN", icon="⚪", recommendation="Không đủ dữ liệu.",
            breadth_score=50, leadership_score=50, risk_pressure_score=50, money_flow_score=50,
            pct_up=0.0, pct_above_ma20=0.0, pct_above_ma50=0.0, pct_healthy=0.0,
            pct_very_healthy=0.0, pct_weak=0.0, pct_near_stop_proxy=0.0,
            money_flow_label="UNKNOWN", notes=[f"{branch_name}: không có mã"],
        )

    row_by_symbol = _build_row_by_symbol(watchlist_df)
    up = above20 = above50 = valid = 0
    healthy = very_healthy = weak = near_stop_proxy = 0
    volume_positive = volume_weak = 0
    used_cache = 0

    for sym in symbols:
        hist = _load_history(sym, cache_dir)
        row_proxy = _watchlist_proxy(row_by_symbol.get(sym, pd.Series(dtype=object)))

        if not hist.empty and len(hist) >= 5:
            used_cache += 1
            valid += 1
            close = pd.to_numeric(hist["close"], errors="coerce").dropna()
            if len(close) == 0:
                continue
            current = float(close.iloc[-1])
            prev = float(close.iloc[-2]) if len(close) >= 2 else current
            ma20 = float(close.tail(20).mean()) if len(close) >= 20 else float(close.mean())
            ma50 = float(close.tail(50).mean()) if len(close) >= 50 else ma20
            if current > prev:
                up += 1
            if current >= ma20:
                above20 += 1
            if current >= ma50:
                above50 += 1
            if current >= ma20 and ma20 >= ma50:
                healthy += 1
            if current >= ma20 and current >= ma50 and current >= prev:
                very_healthy += 1
            if current < ma20:
                weak += 1
            if current <= ma20 * 1.01:
                near_stop_proxy += 1

            vol = pd.to_numeric(hist.get("volume", pd.Series(dtype=float)), errors="coerce").fillna(0)
            if len(vol) >= 20 and float(vol.tail(20).mean()) > 0:
                ratio = float(vol.iloc[-1] / vol.tail(20).mean())
                if ratio >= 1.1 and current >= prev:
                    volume_positive += 1
                elif ratio < 0.8 or current < prev:
                    volume_weak += 1
        elif use_proxy:
            valid += 1
            if row_proxy["healthy"]:
                healthy += 1
                above20 += 1
            if row_proxy["very_healthy"]:
                very_healthy += 1
            if row_proxy["weak"]:
                weak += 1

    # Với Universe, mẫu số là toàn bộ universe để phản ánh sức khỏe tổng thể.
    # Với Qualified, mẫu số là nhóm đã lọc để phản ánh chất lượng nhóm leader.
    denom = max(size, 1)
    pct_up = up / denom * 100.0
    pct_above_ma20 = above20 / denom * 100.0
    pct_above_ma50 = above50 / denom * 100.0
    pct_healthy = healthy / denom * 100.0
    pct_very_healthy = very_healthy / denom * 100.0
    pct_weak = weak / denom * 100.0
    pct_near_stop_proxy = near_stop_proxy / denom * 100.0

    breadth_score = _clamp(0.35 * pct_up + 0.40 * pct_above_ma20 + 0.25 * pct_above_ma50)
    leadership_score = _clamp(0.70 * pct_healthy + 0.30 * pct_very_healthy)
    raw_risk_pressure = _clamp(0.65 * pct_weak + 0.35 * pct_near_stop_proxy)
    risk_pressure_score = _clamp(100 - raw_risk_pressure)

    volume_denom = max(used_cache, 1)
    money_flow_raw = 50.0 + (volume_positive / volume_denom * 50.0) - (volume_weak / volume_denom * 35.0)
    money_flow_score = _clamp(0.55 * money_flow_raw + 0.30 * leadership_score + 0.15 * risk_pressure_score)
    money_flow_label = _label_money_flow(money_flow_score)

    score = _clamp(
        0.30 * breadth_score
        + 0.25 * leadership_score
        + 0.25 * risk_pressure_score
        + 0.20 * money_flow_score
    )

    if pct_weak >= 70 and pct_healthy <= 15:
        score = min(score, 24)
    elif pct_weak >= 60 and pct_healthy <= 25:
        score = min(score, 39)

    regime, icon, rec = _regime_from_score(score)
    notes: List[str] = []
    if used_cache < max(1, size * 0.5):
        notes.append(f"Cache hợp lệ thấp ({used_cache}/{size}), kết quả có thể thiếu dữ liệu")
    if pct_weak >= 50:
        notes.append("Nhiều mã đang yếu/gãy MA20")
    if pct_healthy >= 50:
        notes.append("Độ lan tỏa tích cực")
    if money_flow_score < 40:
        notes.append("Money Flow yếu, hạn chế mua mới")
    elif money_flow_score >= 60:
        notes.append("Money Flow tích cực")

    return RegimeBranch(
        size=size, valid_count=valid, score=score, regime=regime, icon=icon, recommendation=rec,
        breadth_score=breadth_score, leadership_score=leadership_score,
        risk_pressure_score=risk_pressure_score, money_flow_score=money_flow_score,
        pct_up=round(pct_up, 1), pct_above_ma20=round(pct_above_ma20, 1),
        pct_above_ma50=round(pct_above_ma50, 1), pct_healthy=round(pct_healthy, 1),
        pct_very_healthy=round(pct_very_healthy, 1), pct_weak=round(pct_weak, 1),
        pct_near_stop_proxy=round(pct_near_stop_proxy, 1), money_flow_label=money_flow_label,
        notes=notes,
    )


def evaluate_mini_market_regime(
    watchlist_df: pd.DataFrame,
    *,
    cache_dir: str = "cache_stock",
    max_symbols: int = 0,
) -> MiniMarketRegimeResult:
    """Đánh giá Mini Market Regime hai nhánh.

    - Universe: mặc định lấy toàn bộ mã có file CSV trong cache_stock. Đây là pool gốc, ví dụ 138 mã.
    - Qualified: lấy danh sách hiện tại trong intraday_watchlist_v17.csv. Đây là nhóm còn lại sau lọc, ví dụ 10 mã.
    - max_symbols chỉ giới hạn nhánh Qualified để tránh chạy quá nặng nếu cần; Universe vẫn dùng toàn bộ cache.
    """
    qualified_symbols = _infer_symbols(watchlist_df)
    if max_symbols and max_symbols > 0:
        qualified_symbols = qualified_symbols[:max_symbols]

    universe_symbols = _infer_cache_symbols(cache_dir)
    if not universe_symbols:
        universe_symbols = qualified_symbols[:]

    universe_branch = _evaluate_branch(
        universe_symbols,
        cache_dir=cache_dir,
        watchlist_df=watchlist_df,
        branch_name="Universe",
        use_proxy=False,
    )
    qualified_branch = _evaluate_branch(
        qualified_symbols,
        cache_dir=cache_dir,
        watchlist_df=watchlist_df,
        branch_name="Qualified",
        use_proxy=True,
    )

    # Regime chính dùng Universe để tránh bias do nhóm lọc quá hẹp.
    return MiniMarketRegimeResult(
        universe_size=universe_branch.size,
        valid_count=universe_branch.valid_count,
        score=universe_branch.score,
        regime=universe_branch.regime,
        icon=universe_branch.icon,
        recommendation=universe_branch.recommendation,
        breadth_score=universe_branch.breadth_score,
        leadership_score=universe_branch.leadership_score,
        risk_pressure_score=universe_branch.risk_pressure_score,
        money_flow_score=universe_branch.money_flow_score,
        pct_up=universe_branch.pct_up,
        pct_above_ma20=universe_branch.pct_above_ma20,
        pct_above_ma50=universe_branch.pct_above_ma50,
        pct_healthy=universe_branch.pct_healthy,
        pct_very_healthy=universe_branch.pct_very_healthy,
        pct_weak=universe_branch.pct_weak,
        pct_near_stop_proxy=universe_branch.pct_near_stop_proxy,
        money_flow_label=universe_branch.money_flow_label,
        notes=universe_branch.notes,
        qualified_size=qualified_branch.size,
        qualified_valid_count=qualified_branch.valid_count,
        qualified_score=qualified_branch.score,
        qualified_regime=qualified_branch.regime,
        qualified_icon=qualified_branch.icon,
        qualified_recommendation=qualified_branch.recommendation,
        qualified_pct_up=qualified_branch.pct_up,
        qualified_pct_above_ma20=qualified_branch.pct_above_ma20,
        qualified_pct_above_ma50=qualified_branch.pct_above_ma50,
        qualified_pct_healthy=qualified_branch.pct_healthy,
        qualified_pct_very_healthy=qualified_branch.pct_very_healthy,
        qualified_pct_weak=qualified_branch.pct_weak,
        qualified_money_flow_label=qualified_branch.money_flow_label,
        qualified_money_flow_score=qualified_branch.money_flow_score,
        qualified_notes=qualified_branch.notes,
    )
