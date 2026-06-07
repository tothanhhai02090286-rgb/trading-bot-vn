# -*- coding: utf-8 -*-
"""
vn_market_internals.py

PHASE 16 — NỘI LỰC THỊ TRƯỜNG (Market Internals Engine) cho V19.2.

Mục tiêu production-safe:
- Không tạo tín hiệu mua/bán mới.
- Không đụng dữ liệu positions_v19.csv.
- Dùng cache_stock hiện có + snapshot/positions hiện có.
- Hiển thị tiếng Việt trước, tiếng Anh chỉ là chú thích trong ngoặc.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional

import pandas as pd


@dataclass
class MarketInternalsResult:
    status: str = "UNKNOWN"
    icon: str = "⚪"
    internal_score: Any = ""
    label_vi: str = "Không rõ nội lực thị trường"
    data_last_updated: str = ""
    data_freshness_icon: str = "⚪"
    data_freshness_label: str = "Không rõ độ mới dữ liệu"
    data_age_hours: Any = ""

    flow_score: Any = ""
    flow_label: str = ""

    breadth_score: Any = ""
    breadth_label: str = ""
    pct_up: Any = ""
    pct_above_ma20: Any = ""
    pct_above_ma50: Any = ""

    participation_pct: Any = ""
    participation_label: str = ""
    market_liquidity_value_bn: Any = ""
    market_liquidity_avg20_bn: Any = ""
    market_liquidity_vs20_pct: Any = ""
    distribution_days_20: Any = ""
    distribution_label: str = ""
    distribution_recent_dates: str = ""
    distribution_latest_date: str = ""
    distribution_latest_note: str = ""
    distribution_latest_value_bn: Any = ""
    distribution_latest_avg20_bn: Any = ""
    distribution_latest_vs20_pct: Any = ""

    # PHASE 18.2 — DỰ BÁO XÁC SUẤT THỊ TRƯỜNG (Market Probability Forecast)
    distribution_pressure_score: Any = ""
    distribution_pressure_label: str = ""
    correction_prob_5d: Any = ""
    sideway_prob_5d: Any = ""
    recovery_prob_5d: Any = ""
    correction_prob_10d: Any = ""
    sideway_prob_10d: Any = ""
    breakout_prob_10d: Any = ""
    probability_forecast_label: str = ""
    probability_forecast_recommendation: str = ""

    concentration_pct: Any = ""
    concentration_symbol: str = ""
    concentration_label: str = ""

    relative_strength_notes: str = ""
    recommendation_lines: str = ""
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _safe_str(x: Any, default: str = "") -> str:
    try:
        if pd.isna(x):
            return default
    except Exception:
        pass
    s = str(x).strip()
    return s if s else default


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


def _read_csv_smart(path: str) -> pd.DataFrame:
    for enc in ["utf-8-sig", "utf-8", "cp1258", "latin1"]:
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            pass
    return pd.read_csv(path)


def _normalize_price(v: Any) -> Optional[float]:
    x = _to_num(v, default=float("nan"))
    try:
        if pd.isna(x):
            return None
    except Exception:
        return None
    if x > 1000:
        x = x / 1000.0
    return float(x)


def _load_history(symbol: str, cache_dir: str) -> pd.DataFrame:
    for name in [symbol, symbol.upper(), symbol.lower()]:
        p = os.path.join(cache_dir, f"{name}.csv")
        if not os.path.exists(p):
            continue
        try:
            raw = _read_csv_smart(p)
            close_col = _find_col(raw, ["close", "Close", "adj_close", "price", "Giá đóng cửa"])
            vol_col = _find_col(raw, ["volume", "Volume", "vol", "Khối lượng"])
            date_col = _find_col(raw, ["time", "date", "Date", "datetime", "TradingDate", "Ngày"])
            if not close_col:
                continue
            out = pd.DataFrame()
            out["close"] = pd.to_numeric(raw[close_col], errors="coerce").apply(_normalize_price)
            out["volume"] = pd.to_numeric(raw[vol_col], errors="coerce").fillna(0) if vol_col else 0
            out["date_norm"] = pd.to_datetime(raw[date_col], errors="coerce") if date_col else range(len(out))
            out = out.dropna(subset=["close"]).copy()
            return out.sort_values("date_norm").reset_index(drop=True)
        except Exception:
            continue
    return pd.DataFrame()


def _fmt_latest_date(df: pd.DataFrame) -> str:
    try:
        dt = df["date_norm"].iloc[-1]
        if hasattr(dt, "strftime") and not pd.isna(dt):
            return dt.strftime("%Y-%m-%d %H:%M") if getattr(dt, "hour", 0) or getattr(dt, "minute", 0) else dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return ""


def _date_key(x: Any) -> str:
    """Chuẩn hóa ngày để cộng GTGD toàn universe theo từng phiên."""
    try:
        ts = pd.to_datetime(x, errors="coerce")
        if pd.isna(ts):
            return ""
        return ts.strftime("%Y-%m-%d")
    except Exception:
        return ""


def _market_liquidity_series(cache_dir: str, max_symbols: int = 0) -> pd.DataFrame:
    """Tính GTGD toàn universe từ cache_stock.

    Giá trong cache đã chuẩn hóa theo nghìn đồng, volume là cổ phiếu.
    GTGD tỷ đồng ≈ close * volume / 1_000_000.
    Loại VNINDEX/VN30 vì đó là chỉ số, không phải cổ phiếu.
    """
    rows: List[Dict[str, Any]] = []
    try:
        files = [f for f in os.listdir(cache_dir) if f.lower().endswith(".csv")]
    except Exception:
        return pd.DataFrame(columns=["date", "value_bn"])

    skip = {"VNINDEX", "VN30", "HNXINDEX", "UPCOMINDEX"}
    used = 0
    for fn in sorted(files):
        sym = os.path.splitext(fn)[0].upper().strip()
        if sym in skip:
            continue
        if max_symbols and used >= max_symbols:
            break
        path = os.path.join(cache_dir, fn)
        try:
            raw = _read_csv_smart(path)
            close_col = _find_col(raw, ["close", "Close", "adj_close", "price", "Giá đóng cửa"])
            vol_col = _find_col(raw, ["volume", "Volume", "vol", "Khối lượng"])
            date_col = _find_col(raw, ["time", "date", "Date", "datetime", "TradingDate", "Ngày"])
            if not close_col or not vol_col or not date_col:
                continue
            tmp = pd.DataFrame()
            tmp["date"] = raw[date_col].apply(_date_key)
            tmp["close"] = pd.to_numeric(raw[close_col], errors="coerce").apply(_normalize_price)
            tmp["volume"] = pd.to_numeric(raw[vol_col], errors="coerce").fillna(0)
            tmp = tmp.dropna(subset=["close"])
            tmp = tmp[tmp["date"].astype(str) != ""]
            if tmp.empty:
                continue
            tmp["value_bn"] = tmp["close"].astype(float) * tmp["volume"].astype(float) / 1_000_000.0
            for d, v in tmp.groupby("date")["value_bn"].sum().items():
                rows.append({"date": d, "value_bn": float(v)})
            used += 1
        except Exception:
            continue

    if not rows:
        return pd.DataFrame(columns=["date", "value_bn"])
    out = pd.DataFrame(rows).groupby("date", as_index=False)["value_bn"].sum()
    return out.sort_values("date").reset_index(drop=True)


def _market_liquidity_snapshot(cache_dir: str) -> Dict[str, Any]:
    liq = _market_liquidity_series(cache_dir)
    if liq.empty or len(liq) < 21:
        return {"value_bn": "", "avg20_bn": "", "vs20_pct": ""}
    cur = float(liq["value_bn"].iloc[-1])
    avg20 = float(liq["value_bn"].iloc[-21:-1].mean())
    vs20 = (cur / avg20 * 100.0) if avg20 > 0 else 0.0
    return {"value_bn": round(cur, 1), "avg20_bn": round(avg20, 1), "vs20_pct": round(vs20, 1)}


def _market_liquidity_on_date(cache_dir: str, date_key: str) -> Dict[str, Any]:
    liq = _market_liquidity_series(cache_dir)
    if liq.empty or not date_key:
        return {"value_bn": "", "avg20_bn": "", "vs20_pct": ""}
    idxs = liq.index[liq["date"].astype(str) == str(date_key)].tolist()
    if not idxs:
        return {"value_bn": "", "avg20_bn": "", "vs20_pct": ""}
    i = idxs[-1]
    cur = float(liq.loc[i, "value_bn"])
    if i < 20:
        avg20 = float(liq["value_bn"].iloc[:i].mean()) if i > 0 else 0.0
    else:
        avg20 = float(liq["value_bn"].iloc[i-20:i].mean())
    vs20 = (cur / avg20 * 100.0) if avg20 > 0 else 0.0
    return {"value_bn": round(cur, 1), "avg20_bn": round(avg20, 1), "vs20_pct": round(vs20, 1)}


def _parse_dt(s: str) -> Optional[datetime]:
    try:
        ts = pd.to_datetime(s, errors="coerce")
        if pd.isna(ts):
            return None
        return ts.to_pydatetime().replace(tzinfo=None)
    except Exception:
        return None


def _freshness(last_update: str) -> Dict[str, Any]:
    dt = _parse_dt(last_update)
    try:
        now_vn = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).replace(tzinfo=None)
    except Exception:
        now_vn = datetime.now()
    if not dt:
        return {"icon": "⚪", "label": "Không rõ độ mới dữ liệu", "age": ""}
    age = round(max(0.0, (now_vn - dt).total_seconds() / 3600.0), 1)
    if dt.date() == now_vn.date():
        return {"icon": "🟢", "label": "MỚI (DỮ LIỆU HÔM NAY)", "age": age}
    return {"icon": "🟠", "label": "CŨ (CHÚ Ý) — dùng dữ liệu gần nhất", "age": age}


def _label_score(score: float) -> tuple[str, str]:
    if score >= 75:
        return "🟢", "Nội lực thị trường rất khỏe"
    if score >= 60:
        return "🟢", "Nội lực thị trường khỏe"
    if score >= 45:
        return "🟡", "Nội lực thị trường trung tính"
    if score >= 30:
        return "🟠", "Nội lực thị trường yếu"
    return "🔴", "Nội lực thị trường rất yếu / ưu tiên phòng thủ"


def _participation_from_index(cache_dir: str) -> Dict[str, Any]:
    h = _load_history("VNINDEX", cache_dir)
    if h.empty or len(h) < 21:
        liq0 = _market_liquidity_snapshot(cache_dir)
        return {"pct": "", "label": "⚪ Không đủ dữ liệu", "last_update": "", **liq0}
    vol = pd.to_numeric(h["volume"], errors="coerce").fillna(0)
    base = float(vol.iloc[-21:-1].mean()) if len(vol) >= 21 else 0.0
    cur = float(vol.iloc[-1]) if len(vol) else 0.0
    pct = round(cur / base * 100.0, 1) if base > 0 else 0.0
    if pct >= 130:
        label = "🟢 Dòng tiền tham gia mạnh"
    elif pct >= 95:
        label = "🟡 Tham gia bình thường"
    elif pct >= 70:
        label = "🟠 Tham gia yếu"
    else:
        label = "🔴 Thanh khoản rất yếu"
    liq = _market_liquidity_snapshot(cache_dir)
    return {"pct": pct, "label": label, "last_update": _fmt_latest_date(h), **liq}


def _distribution_days(cache_dir: str) -> Dict[str, Any]:
    h = _load_history("VNINDEX", cache_dir)
    if h.empty or len(h) < 25:
        return {
            "count": "", "label": "⚪ Không đủ dữ liệu", "last_update": "",
            "recent_dates": "", "latest_date": "", "latest_note": "", "latest_value_bn": "", "latest_avg20_bn": "", "latest_vs20_pct": ""
        }
    close = pd.to_numeric(h["close"], errors="coerce")
    vol = pd.to_numeric(h["volume"], errors="coerce").fillna(0)
    events: List[Dict[str, Any]] = []
    start = max(1, len(h) - 20)
    for i in range(start, len(h)):
        prev = close.iloc[i - 1]
        cur = close.iloc[i]
        if not prev or pd.isna(prev) or pd.isna(cur):
            continue
        ret = (cur / prev - 1.0) * 100.0
        vol_base = float(vol.iloc[max(0, i - 20):i].mean()) if i > 0 else 0.0
        cur_vol = float(vol.iloc[i]) if not pd.isna(vol.iloc[i]) else 0.0
        # Phiên phân phối thực chiến: chỉ số giảm rõ, khối lượng cao hơn nền.
        if ret <= -0.6 and vol_base > 0 and cur_vol >= vol_base * 1.10:
            dt = h["date_norm"].iloc[i] if "date_norm" in h.columns else None
            date_label = ""
            date_key = ""
            try:
                if hasattr(dt, "strftime") and not pd.isna(dt):
                    date_label = dt.strftime("%d/%m")
                    date_key = dt.strftime("%Y-%m-%d")
            except Exception:
                date_label = ""
                date_key = ""
            vol_pct = (cur_vol / vol_base - 1.0) * 100.0 if vol_base > 0 else 0.0
            events.append({"date": date_label, "date_key": date_key, "ret": ret, "vol_pct": vol_pct})
    cnt = len(events)
    if cnt >= 5:
        label = "🔴 Áp lực phân phối cao"
    elif cnt >= 3:
        label = "🟠 Có dấu hiệu phân phối"
    elif cnt >= 1:
        label = "🟡 Có vài phiên phân phối"
    else:
        label = "🟢 Chưa thấy phân phối rõ"

    recent_events = events[-3:]
    recent_dates = ", ".join([e.get("date", "") for e in recent_events if e.get("date")])
    latest_date = events[-1].get("date", "") if events else ""
    latest_note = ""
    latest_value_bn = ""
    latest_avg20_bn = ""
    latest_vs20_pct = ""
    if events:
        e = events[-1]
        liq = _market_liquidity_on_date(cache_dir, e.get("date_key", ""))
        latest_value_bn = liq.get("value_bn", "")
        latest_avg20_bn = liq.get("avg20_bn", "")
        latest_vs20_pct = liq.get("vs20_pct", "")
        liq_text = ""
        if latest_value_bn != "":
            # Chuẩn không look-ahead: GTGD ngày phân phối / GTGD TB20 trước chính ngày đó.
            liq_text = f" | GTGD ngày phân phối: {latest_value_bn:,.0f} tỷ; TB20 trước đó: {latest_avg20_bn:,.0f} tỷ; bằng {latest_vs20_pct}% TB20"
        latest_note = f"{e.get('date','')}: VNINDEX {round(e.get('ret',0.0),2)}%, Vol +{round(e.get('vol_pct',0.0),1)}% so với nền 20 phiên{liq_text}"
    return {
        "count": cnt,
        "label": label,
        "last_update": _fmt_latest_date(h),
        "recent_dates": recent_dates,
        "latest_date": latest_date,
        "latest_note": latest_note,
        "latest_value_bn": latest_value_bn,
        "latest_avg20_bn": latest_avg20_bn,
        "latest_vs20_pct": latest_vs20_pct,
    }

def _concentration(positions_df: Optional[pd.DataFrame]) -> Dict[str, Any]:
    if positions_df is None or positions_df.empty:
        return {"pct": "", "symbol": "", "label": "⚪ Không có vị thế"}
    sym_col = _find_col(positions_df, ["Mã", "Ma", "Symbol", "Ticker"])
    w_col = _find_col(positions_df, ["Tỷ trọng hiện tại %", "Ty trong hien tai %", "weight_pct", "Weight"])
    if not sym_col or not w_col:
        return {"pct": "", "symbol": "", "label": "⚪ Không đọc được tỷ trọng"}
    best_sym, best_w = "", -1.0
    for _, r in positions_df.iterrows():
        w = _to_num(r.get(w_col), 0.0)
        if w > best_w:
            best_w = w
            best_sym = _safe_str(r.get(sym_col, "")).upper()
    if best_w >= 70:
        label = "🔴 Rủi ro tập trung rất cao"
    elif best_w >= 45:
        label = "🟠 Rủi ro tập trung cao"
    elif best_w >= 25:
        label = "🟡 Tập trung vừa phải"
    else:
        label = "🟢 Phân bổ khá cân bằng"
    return {"pct": round(best_w, 2), "symbol": best_sym, "label": label}


def _relative_strength_notes(positions_df: Optional[pd.DataFrame], cache_dir: str) -> str:
    if positions_df is None or positions_df.empty:
        return ""
    idx = _load_history("VNINDEX", cache_dir)
    if idx.empty or len(idx) < 6:
        return "⚪ Không đủ dữ liệu VNINDEX để so sánh."
    idx_close = pd.to_numeric(idx["close"], errors="coerce").dropna()
    idx_ret5 = (float(idx_close.iloc[-1]) / float(idx_close.iloc[-6]) - 1.0) * 100.0 if len(idx_close) >= 6 and idx_close.iloc[-6] else 0.0
    sym_col = _find_col(positions_df, ["Mã", "Ma", "Symbol", "Ticker"])
    if not sym_col:
        return ""
    lines: List[str] = []
    for sym in positions_df[sym_col].astype(str).str.upper().str.strip().dropna().tolist()[:8]:
        h = _load_history(sym, cache_dir)
        if h.empty or len(h) < 6:
            lines.append(f"- {sym}: ⚪ chưa đủ dữ liệu")
            continue
        c = pd.to_numeric(h["close"], errors="coerce").dropna()
        if len(c) < 6 or not c.iloc[-6]:
            lines.append(f"- {sym}: ⚪ chưa đủ dữ liệu")
            continue
        r5 = (float(c.iloc[-1]) / float(c.iloc[-6]) - 1.0) * 100.0
        diff = r5 - idx_ret5
        if diff >= 2:
            tag = "🟢 mạnh hơn VNINDEX"
        elif diff <= -2:
            tag = "🟠 yếu hơn VNINDEX"
        else:
            tag = "🟡 ngang thị trường"
        lines.append(f"- {sym}: {round(r5,2)}% / VNINDEX {round(idx_ret5,2)}% | {tag}")
    return "\n".join(lines)




def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    try:
        return max(lo, min(hi, float(v)))
    except Exception:
        return lo


def _distribution_pressure_score(
    distribution_count_20: float,
    latest_vs20_pct: float,
    breadth_score: float,
    participation_pct: float,
    flow_score: float,
) -> tuple[float, str]:
    """Ước lượng áp lực phân phối 0-100.

    Đây là điểm thống kê nội bộ cho thị trường Việt Nam, không phải xác suất tuyệt đối.
    Các yếu tố chính:
    - Số phiên phân phối 20 phiên
    - Thanh khoản phiên phân phối gần nhất so với TB20 trước chính phiên đó
    - Độ rộng thị trường hiện tại
    - Thanh khoản tham gia hiện tại
    - Dòng tiền ngành hiện tại
    """
    cnt_score = _clamp(distribution_count_20 * 18.0, 0, 45)
    liq_score = _clamp((latest_vs20_pct - 100.0) * 0.55, 0, 30) if latest_vs20_pct else 0.0
    breadth_damage = _clamp(50.0 - breadth_score, 0, 35) * 0.45
    participation_damage = _clamp(100.0 - participation_pct, 0, 50) * 0.20 if participation_pct else 8.0
    flow_damage = _clamp(50.0 - flow_score, 0, 50) * 0.25 if flow_score else 8.0
    score = round(_clamp(cnt_score + liq_score + breadth_damage + participation_damage + flow_damage), 1)
    if score >= 75:
        label = "🔴 RẤT CAO — áp lực bán/phân phối mạnh"
    elif score >= 55:
        label = "🟠 CAO — cần phòng thủ"
    elif score >= 35:
        label = "🟡 TRUNG BÌNH — có dấu hiệu cần theo dõi"
    else:
        label = "🟢 THẤP — chưa có áp lực phân phối lớn"
    return score, label


def _market_probability_forecast(
    internal_score: float,
    breadth_score: float,
    flow_score: float,
    participation_pct: float,
    distribution_pressure: float,
    distribution_count_20: float,
) -> Dict[str, Any]:
    """PHASE 18.2 — Dự báo xác suất thị trường.

    Xác suất là ước lượng thống kê theo điều kiện hiện tại, không phải dự đoán chắc chắn.
    Công thức được thiết kế conservative cho TTCK Việt Nam: khi breadth/flow/liquidity yếu
    và distribution pressure cao, xác suất điều chỉnh tăng.
    """
    internal_score = _to_num(internal_score, 50.0)
    breadth_score = _to_num(breadth_score, 50.0)
    flow_score = _to_num(flow_score, 50.0)
    participation_pct = _to_num(participation_pct, 100.0)
    distribution_pressure = _to_num(distribution_pressure, 0.0)
    distribution_count_20 = _to_num(distribution_count_20, 0.0)

    correction5 = 35.0
    correction5 += _clamp(50.0 - internal_score, 0, 50) * 0.35
    correction5 += _clamp(50.0 - breadth_score, 0, 50) * 0.25
    correction5 += _clamp(50.0 - flow_score, 0, 50) * 0.18
    correction5 += _clamp(100.0 - participation_pct, 0, 60) * 0.10
    correction5 += distribution_pressure * 0.18
    correction5 += distribution_count_20 * 2.0
    correction5 = _clamp(correction5, 8, 88)

    recovery5 = 28.0
    recovery5 += _clamp(internal_score - 50.0, 0, 50) * 0.35
    recovery5 += _clamp(breadth_score - 50.0, 0, 50) * 0.20
    recovery5 += _clamp(flow_score - 50.0, 0, 50) * 0.18
    recovery5 += _clamp(participation_pct - 100.0, 0, 80) * 0.08
    recovery5 -= distribution_pressure * 0.12
    recovery5 -= distribution_count_20 * 2.0
    recovery5 = _clamp(recovery5, 5, 70)

    # Chuẩn hóa để 3 xác suất 5 phiên cộng xấp xỉ 100.
    if correction5 + recovery5 > 92:
        scale = 92.0 / (correction5 + recovery5)
        correction5 *= scale
        recovery5 *= scale
    sideway5 = _clamp(100.0 - correction5 - recovery5, 5, 75)
    total5 = correction5 + sideway5 + recovery5
    correction5 = round(correction5 / total5 * 100.0, 1)
    sideway5 = round(sideway5 / total5 * 100.0, 1)
    recovery5 = round(recovery5 / total5 * 100.0, 1)

    correction10 = _clamp(correction5 * 0.85 + distribution_pressure * 0.12 + distribution_count_20 * 2.5, 8, 90)
    breakout10 = _clamp(recovery5 * 0.85 + _clamp(internal_score - 55.0, 0, 45) * 0.25 - distribution_pressure * 0.07, 5, 75)
    if correction10 + breakout10 > 92:
        scale = 92.0 / (correction10 + breakout10)
        correction10 *= scale
        breakout10 *= scale
    sideway10 = _clamp(100.0 - correction10 - breakout10, 5, 75)
    total10 = correction10 + sideway10 + breakout10
    correction10 = round(correction10 / total10 * 100.0, 1)
    sideway10 = round(sideway10 / total10 * 100.0, 1)
    breakout10 = round(breakout10 / total10 * 100.0, 1)

    if correction5 >= 65 or correction10 >= 65:
        label = "🔴 NGHIÊNG MẠNH VỀ ĐIỀU CHỈNH"
        rec = "🛡️ Ưu tiên phòng thủ, không nâng tỷ trọng; chỉ giữ mã khỏe hơn VNINDEX và có hàng bán được."
    elif correction5 >= 50:
        label = "🟠 NGHIÊNG VỀ PHÒNG THỦ"
        rec = "🟠 Hạn chế mua mới; nếu mua chỉ test nhỏ ở nhóm có Conviction cao."
    elif recovery5 >= 45 or breakout10 >= 45:
        label = "🟢 CÓ CỬA HỒI PHỤC / BỨT PHÁ"
        rec = "🟢 Có thể quan sát nhóm leader bền vững, nhưng vẫn chờ xác nhận breadth và thanh khoản."
    else:
        label = "🟡 XÁC SUẤT ĐI NGANG CAO"
        rec = "🟡 Ưu tiên quan sát, tránh mua đuổi; chỉ xử lý theo Position State."

    return {
        "distribution_pressure_score": round(distribution_pressure, 1),
        "correction_prob_5d": correction5,
        "sideway_prob_5d": sideway5,
        "recovery_prob_5d": recovery5,
        "correction_prob_10d": correction10,
        "sideway_prob_10d": sideway10,
        "breakout_prob_10d": breakout10,
        "label": label,
        "recommendation": rec,
    }

def evaluate_market_internals(
    snapshot_df: Optional[pd.DataFrame] = None,
    positions_df: Optional[pd.DataFrame] = None,
    institutional_flow: Optional[Dict[str, Any]] = None,
    cache_dir: str = "cache_stock",
) -> MarketInternalsResult:
    flow = institutional_flow or {}
    flow_score = _to_num(flow.get("market_flow_score", ""), 0.0)
    flow_label = _safe_str(flow.get("market_flow_label", ""), "")

    # Reuse Mini Market Regime/Breadth đã có trong V19.2, không tính lại engine khác.
    row = {}
    if snapshot_df is not None and not snapshot_df.empty:
        try:
            row = snapshot_df.iloc[0].to_dict()
        except Exception:
            row = {}
    pct_up = _to_num(row.get("Mini Market Pct Up", ""), 0.0)
    ma20 = _to_num(row.get("Mini Market Pct Above MA20", ""), 0.0)
    ma50 = _to_num(row.get("Mini Market Pct Above MA50", ""), 0.0)
    mini_score = _to_num(row.get("Mini Market Score", ""), 0.0)
    breadth_score = mini_score if mini_score > 0 else round((pct_up * 0.35 + ma20 * 0.4 + ma50 * 0.25), 1)
    if breadth_score >= 70:
        breadth_label = "🟢 Sức khỏe thị trường tốt"
    elif breadth_score >= 50:
        breadth_label = "🟡 Sức khỏe thị trường trung tính"
    elif breadth_score >= 35:
        breadth_label = "🟠 Sức khỏe thị trường yếu"
    else:
        breadth_label = "🔴 Sức khỏe thị trường rất yếu"

    part = _participation_from_index(cache_dir)
    dist = _distribution_days(cache_dir)
    conc = _concentration(positions_df)
    rs_notes = _relative_strength_notes(positions_df, cache_dir)

    participation_pct = _to_num(part.get("pct", ""), 0.0)
    distribution_cnt = _to_num(dist.get("count", ""), 0.0)
    concentration_pct = _to_num(conc.get("pct", ""), 0.0)

    participation_score = max(0.0, min(100.0, participation_pct * 0.75)) if participation_pct else 50.0
    distribution_score = max(0.0, 100.0 - distribution_cnt * 14.0)
    concentration_score = max(0.0, 100.0 - max(0.0, concentration_pct - 25.0) * 1.25) if concentration_pct else 70.0

    parts = []
    weights = []
    if flow_score > 0:
        parts.append(flow_score); weights.append(0.30)
    if breadth_score > 0:
        parts.append(breadth_score); weights.append(0.30)
    parts.append(participation_score); weights.append(0.18)
    parts.append(distribution_score); weights.append(0.14)
    parts.append(concentration_score); weights.append(0.08)
    wsum = sum(weights) or 1.0
    internal_score = round(sum(v * w for v, w in zip(parts, weights)) / wsum, 1)
    icon, label = _label_score(internal_score)
    if internal_score >= 60:
        status = "THUAN_LOI"
    elif internal_score >= 45:
        status = "TRUNG_TINH"
    elif internal_score >= 30:
        status = "PHONG_THU"
    else:
        status = "RAT_YEU"

    latest_vs20 = _to_num(dist.get("latest_vs20_pct", ""), 0.0)
    distribution_pressure, distribution_pressure_label = _distribution_pressure_score(
        distribution_cnt, latest_vs20, breadth_score, participation_pct, flow_score
    )
    forecast = _market_probability_forecast(
        internal_score, breadth_score, flow_score, participation_pct, distribution_pressure, distribution_cnt
    )

    last_update = _safe_str(flow.get("data_last_updated", ""), "") or part.get("last_update", "")
    fr = _freshness(last_update)

    rec = []
    if internal_score >= 60:
        rec.append("✅ Có thể giao dịch chọn lọc theo ngành mạnh, vẫn tuân thủ Position State và VN Trade Safety.")
    elif internal_score >= 45:
        rec.append("🟡 Ưu tiên quan sát, chỉ xử lý mã thật sự mạnh hơn thị trường.")
    else:
        rec.append("🛡️ Ưu tiên phòng thủ, hạn chế nâng tỷ trọng khi nội lực thị trường yếu.")
    if concentration_pct >= 70:
        rec.append("⚠️ Danh mục đang tập trung rất cao vào một mã; tránh tăng thêm tỷ trọng cùng mã nếu không có xác nhận mạnh.")

    return MarketInternalsResult(
        status=status,
        icon=icon,
        internal_score=internal_score,
        label_vi=label,
        data_last_updated=last_update,
        data_freshness_icon=fr.get("icon", "⚪"),
        data_freshness_label=fr.get("label", "Không rõ độ mới dữ liệu"),
        data_age_hours=fr.get("age", ""),
        flow_score=flow_score if flow_score > 0 else "",
        flow_label=flow_label,
        breadth_score=round(breadth_score, 1) if breadth_score else "",
        breadth_label=breadth_label,
        pct_up=round(pct_up, 1) if pct_up else "",
        pct_above_ma20=round(ma20, 1) if ma20 else "",
        pct_above_ma50=round(ma50, 1) if ma50 else "",
        participation_pct=participation_pct if participation_pct else "",
        participation_label=part.get("label", ""),
        market_liquidity_value_bn=part.get("value_bn", ""),
        market_liquidity_avg20_bn=part.get("avg20_bn", ""),
        market_liquidity_vs20_pct=part.get("vs20_pct", ""),
        distribution_days_20=int(distribution_cnt) if dist.get("count", "") != "" else "",
        distribution_label=dist.get("label", ""),
        distribution_recent_dates=dist.get("recent_dates", ""),
        distribution_latest_date=dist.get("latest_date", ""),
        distribution_latest_note=dist.get("latest_note", ""),
        distribution_latest_value_bn=dist.get("latest_value_bn", ""),
        distribution_latest_avg20_bn=dist.get("latest_avg20_bn", ""),
        distribution_latest_vs20_pct=dist.get("latest_vs20_pct", ""),
        distribution_pressure_score=forecast.get("distribution_pressure_score", distribution_pressure),
        distribution_pressure_label=distribution_pressure_label,
        correction_prob_5d=forecast.get("correction_prob_5d", ""),
        sideway_prob_5d=forecast.get("sideway_prob_5d", ""),
        recovery_prob_5d=forecast.get("recovery_prob_5d", ""),
        correction_prob_10d=forecast.get("correction_prob_10d", ""),
        sideway_prob_10d=forecast.get("sideway_prob_10d", ""),
        breakout_prob_10d=forecast.get("breakout_prob_10d", ""),
        probability_forecast_label=forecast.get("label", ""),
        probability_forecast_recommendation=forecast.get("recommendation", ""),
        concentration_pct=concentration_pct if concentration_pct else "",
        concentration_symbol=conc.get("symbol", ""),
        concentration_label=conc.get("label", ""),
        relative_strength_notes=rs_notes,
        recommendation_lines="\n".join(rec),
        notes="Nội lực thị trường là điểm tổng hợp từ dòng tiền ngành, sức khỏe thị trường, mức độ tham gia dòng tiền, phiên phân phối, sức mạnh tương đối và rủi ro tập trung. Đây là bối cảnh hỗ trợ quyết định, không phải lệnh mua/bán tự động.",
    )
