# -*- coding: utf-8 -*-
"""
vn_trade_safety.py

Lớp an toàn giao dịch cho TTCK Việt Nam.
Tập trung vào 3 rủi ro thực chiến:
1) Thanh khoản có đủ để mua/bán thật không.
2) Giá gần trần/sàn có làm méo tín hiệu không.
3) Stoploss có khả thi không hay chỉ là cảnh báo khi kẹt thanh khoản.

Thiết kế: không phụ thuộc vnstock, chỉ dùng pandas + CSV cache/watchlist hiện có.
Có thể gọi từ V18 realtime entry và V19.2 position desk.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional, Tuple

import pandas as pd


def _num(x: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if x is None:
            return default
        if isinstance(x, str):
            x = x.replace("%", "").replace(",", ".").strip()
            if not x:
                return default
        v = pd.to_numeric(pd.Series([x]), errors="coerce").iloc[0]
        if pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default


def normalize_vn_price(x: Any) -> Optional[float]:
    v = _num(x)
    if v is None:
        return None
    # Nhiều nguồn trả giá theo đồng, hệ thống của bạn đang dùng nghìn đồng.
    if v > 1000:
        v = v / 1000.0
    return round(float(v), 3)


def _find_col(df: pd.DataFrame, names) -> Optional[str]:
    lower = {str(c).lower(): c for c in df.columns}
    for n in names:
        if n in df.columns:
            return n
        if str(n).lower() in lower:
            return lower[str(n).lower()]
    return None


def read_csv_smart(path: str) -> pd.DataFrame:
    for enc in ["utf-8-sig", "utf-8", "cp1258", "latin1"]:
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            pass
    return pd.read_csv(path)


def load_ohlcv_cache(symbol: str, cache_dir: str = "cache_stock") -> pd.DataFrame:
    candidates = [
        os.path.join(cache_dir, f"{symbol}.csv"),
        os.path.join(cache_dir, f"{symbol.upper()}.csv"),
        f"{symbol}.csv",
    ]
    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            raw = read_csv_smart(path)
            date_col = _find_col(raw, ["time", "date", "Date", "datetime", "TradingDate", "Ngày"])
            close_col = _find_col(raw, ["close", "Close", "adj_close", "price", "Giá đóng cửa"])
            high_col = _find_col(raw, ["high", "High", "Giá cao nhất"])
            low_col = _find_col(raw, ["low", "Low", "Giá thấp nhất"])
            vol_col = _find_col(raw, ["volume", "Volume", "vol", "Khối lượng"])
            if close_col is None:
                continue
            out = pd.DataFrame()
            out["date"] = pd.to_datetime(raw[date_col], errors="coerce") if date_col else pd.RangeIndex(len(raw))
            out["close"] = pd.to_numeric(raw[close_col], errors="coerce").apply(normalize_vn_price)
            out["high"] = pd.to_numeric(raw[high_col], errors="coerce").apply(normalize_vn_price) if high_col else out["close"]
            out["low"] = pd.to_numeric(raw[low_col], errors="coerce").apply(normalize_vn_price) if low_col else out["close"]
            out["volume"] = pd.to_numeric(raw[vol_col], errors="coerce").fillna(0) if vol_col else 0
            out = out.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
            return out
        except Exception:
            continue
    return pd.DataFrame()


def infer_limit_pct(symbol: str, exchange: str = "") -> float:
    ex = str(exchange or "").upper()
    if "UPCOM" in ex:
        return float(os.getenv("VN_UPCOM_LIMIT_PCT", "15"))
    if "HNX" in ex:
        return float(os.getenv("VN_HNX_LIMIT_PCT", "10"))
    return float(os.getenv("VN_HOSE_LIMIT_PCT", "7"))


@dataclass
class TradeSafety:
    score: int
    cap_action: str
    liquidity_band: str
    avg_value_20d_bn: Optional[float]
    avg_volume_20d: Optional[float]
    near_ceiling: bool
    near_floor: bool
    exit_risk: str
    reasons: list
    warnings: list

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def cap_action(current: str, cap: str) -> str:
    rank = {
        "KHÔNG VÀO": 0,
        "WATCH": 1,
        "TEST NHỎ": 2,
        "BUY NHỎ": 3,
        "BUY CÓ KIỂM SOÁT": 4,
        "GIỮ": 1,
        "THEO DÕI VỊ THẾ": 1,
        "MUA THÊM NHỎ": 3,
        "CHỐT BỚT NHẸ": 3,
        "CHỐT MẠNH": 4,
        "GIẢM VỊ THẾ": 4,
        "THOÁT VỊ THẾ": 5,
        "KIỂM TRA GIÁ TRƯỚC KHI BÁN": 4,
        "CHƯA BÁN ĐƯỢC - THEO DÕI RỦI RO": 4,
        "THOÁT KHI CÓ THANH KHOẢN": 4,
    }
    reverse_entry = {0: "KHÔNG VÀO", 1: "WATCH", 2: "TEST NHỎ", 3: "BUY NHỎ", 4: "BUY CÓ KIỂM SOÁT"}
    if current in reverse_entry.values() or cap in reverse_entry.values():
        return reverse_entry[min(rank.get(current, 1), rank.get(cap, 1))]
    return current


def evaluate_entry_safety(
    symbol: str,
    current_price: Optional[float],
    ref_price: Optional[float] = None,
    cache_dir: str = "cache_stock",
    exchange: str = "",
) -> TradeSafety:
    """Đánh giá an toàn cho tín hiệu mua mới/realtime."""
    hist = load_ohlcv_cache(symbol, cache_dir)
    avg_value_20d_bn = None
    avg_volume_20d = None
    reasons, warnings = [], []
    score = 100
    cap = "BUY CÓ KIỂM SOÁT"

    if not hist.empty and len(hist) >= 20:
        tail = hist.tail(20)
        avg_volume_20d = float(tail["volume"].mean())
        avg_close = float(tail["close"].mean())
        # close đang là nghìn đồng, volume là cổ phiếu => giá trị tỷ đồng.
        avg_value_20d_bn = avg_close * avg_volume_20d / 1_000_000.0
        if avg_value_20d_bn < float(os.getenv("VN_MIN_AVG_VALUE_BN_BLOCK", "10")):
            cap = "KHÔNG VÀO"
            score -= 45
            reasons.append(f"Thanh khoản 20 phiên thấp ({avg_value_20d_bn:.1f} tỷ/ngày)")
        elif avg_value_20d_bn < float(os.getenv("VN_MIN_AVG_VALUE_BN_TEST", "30")):
            cap = "TEST NHỎ"
            score -= 25
            warnings.append(f"Thanh khoản chỉ vừa đủ ({avg_value_20d_bn:.1f} tỷ/ngày), chỉ nên test nhỏ")
        elif avg_value_20d_bn < float(os.getenv("VN_MIN_AVG_VALUE_BN_NORMAL", "50")):
            cap = "BUY NHỎ"
            score -= 10
            warnings.append(f"Thanh khoản trung bình ({avg_value_20d_bn:.1f} tỷ/ngày), không mua lớn")
        else:
            reasons.append(f"Thanh khoản ổn ({avg_value_20d_bn:.1f} tỷ/ngày)")

        # Cảnh báo phân phối: volume tăng nhưng close không cải thiện.
        if len(hist) >= 21:
            last = hist.iloc[-1]
            prev = hist.iloc[-2]
            avg_vol = float(hist["volume"].tail(20).mean())
            if avg_vol > 0 and last["volume"] / avg_vol >= 1.8 and last["close"] <= prev["close"] * 1.003:
                score -= 20
                warnings.append("Volume tăng mạnh nhưng giá không cải thiện, có rủi ro phân phối")
    else:
        score -= 15
        warnings.append("Chưa đủ dữ liệu cache 20 phiên để kiểm tra thanh khoản")

    price = normalize_vn_price(current_price)
    ref = normalize_vn_price(ref_price) or (float(hist["close"].iloc[-2]) if len(hist) >= 2 else price)
    near_ceiling = near_floor = False
    limit_pct = infer_limit_pct(symbol, exchange)
    if price and ref:
        ceiling = ref * (1 + limit_pct / 100.0)
        floor = ref * (1 - limit_pct / 100.0)
        near_ceiling = price >= ceiling * (1 - float(os.getenv("VN_NEAR_CEIL_FLOOR_BUFFER", "0.01")))
        near_floor = price <= floor * (1 + float(os.getenv("VN_NEAR_CEIL_FLOOR_BUFFER", "0.01")))
        if near_ceiling:
            cap = cap_action(cap, "WATCH")
            score -= 35
            warnings.append("Giá gần trần, không đuổi mua")
        if near_floor:
            cap = "KHÔNG VÀO"
            score -= 50
            reasons.append("Giá gần sàn, rủi ro kẹt thanh khoản")

    if avg_value_20d_bn is None:
        band = "UNKNOWN"
    elif avg_value_20d_bn < 10:
        band = "MỎNG"
    elif avg_value_20d_bn < 30:
        band = "YẾU"
    elif avg_value_20d_bn < 50:
        band = "TRUNG BÌNH"
    else:
        band = "ỔN"

    exit_risk = "CAO" if near_floor or band in ["MỎNG", "YẾU"] else "TRUNG BÌNH" if band == "TRUNG BÌNH" else "THẤP"
    return TradeSafety(max(0, min(100, int(score))), cap, band, avg_value_20d_bn, avg_volume_20d, near_ceiling, near_floor, exit_risk, reasons, warnings)


def adjust_entry_recommendation(rec: str, safety: TradeSafety) -> Tuple[str, str]:
    adjusted = cap_action(rec, safety.cap_action)
    note_parts = []
    if adjusted != rec:
        note_parts.append(f"Safety cap: {rec} → {adjusted}")
    if safety.reasons:
        note_parts.extend(safety.reasons[:2])
    if safety.warnings:
        note_parts.extend(safety.warnings[:2])
    return adjusted, "; ".join(note_parts)


def adjust_exit_action(action: str, current_price: Optional[float], ref_price: Optional[float], safety: TradeSafety) -> Tuple[str, str]:
    sell_actions = {"THOÁT VỊ THẾ", "GIẢM VỊ THẾ", "CHỐT BỚT NHẸ", "CHỐT MẠNH"}
    if action in sell_actions and (safety.near_floor or safety.liquidity_band in ["MỎNG", "YẾU"]):
        return "THOÁT KHI CÓ THANH KHOẢN", "Tín hiệu bán có rủi ro khớp lệnh: thanh khoản yếu hoặc giá gần sàn; ưu tiên thoát khi có lực cầu thay vì đặt kỳ vọng stoploss khớp ngay."
    return action, ""
