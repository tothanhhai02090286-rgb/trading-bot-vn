# -*- coding: utf-8 -*-
"""
vn_ma_proximity_scanner.py

PHASE 17 — BỘ QUÉT GẦN MA20 / MA50 (MA Proximity Scanner)

Mục tiêu:
- Quét cache_stock hiện có, không cần API mới.
- Tìm các mã có giá đóng cửa gần MA20 hoặc MA50 trong biên độ +/- 1% mặc định.
- Chỉ hiển thị cơ hội quan sát, không tạo lệnh mua/bán tự động.
- Tiếng Việt là chính, tiếng Anh chỉ chú thích.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


@dataclass
class MAProximityResult:
    status: str = "UNKNOWN"
    icon: str = "⚪"
    label_vi: str = "Không rõ trạng thái MA"
    tolerance_pct: Any = ""
    universe_count: Any = ""
    valid_count: Any = ""
    ma20_count: Any = ""
    ma50_count: Any = ""
    data_last_updated: str = ""
    data_freshness_icon: str = "⚪"
    data_freshness_label: str = "Không rõ độ mới dữ liệu"
    data_age_hours: Any = ""
    near_ma20_lines: str = ""
    near_ma50_lines: str = ""
    notes: str = ""

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
    # Một số nguồn cache lưu giá theo đồng, bot đang dùng đơn vị nghìn.
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
            close_col = _find_col(raw, ["close", "Close", "adj_close", "price", "Giá đóng cửa", "Gia dong cua"])
            vol_col = _find_col(raw, ["volume", "Volume", "vol", "Khối lượng", "Khoi luong"])
            date_col = _find_col(raw, ["time", "date", "Date", "datetime", "TradingDate", "Ngày", "Ngay"])
            if not close_col:
                continue
            out = pd.DataFrame()
            out["close"] = pd.to_numeric(raw[close_col], errors="coerce").apply(_normalize_price)
            out["volume"] = pd.to_numeric(raw[vol_col], errors="coerce").fillna(0) if vol_col else 0
            out["date_norm"] = pd.to_datetime(raw[date_col], errors="coerce") if date_col else range(len(out))
            out = out.dropna(subset=["close"]).copy()
            if len(out) < 50:
                return pd.DataFrame()
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


def _symbols_from_cache(cache_dir: str, max_symbols: int = 0) -> List[str]:
    if not os.path.isdir(cache_dir):
        return []
    syms: List[str] = []
    for fn in os.listdir(cache_dir):
        if not fn.lower().endswith(".csv"):
            continue
        sym = os.path.splitext(fn)[0].strip().upper()
        if not sym or sym in {"VNINDEX", "VN30", "VN30INDEX", "HNXINDEX", "UPCOMINDEX"}:
            continue
        syms.append(sym)
    syms = sorted(set(syms))
    return syms[:max_symbols] if max_symbols and max_symbols > 0 else syms


def _line(item: Dict[str, Any], ma_key: str) -> str:
    dist = item.get(f"dist_{ma_key}", 0.0)
    side = "trên" if dist >= 0 else "dưới"
    return (
        f"- {item['symbol']}: Giá {item['close']:.2f} | {ma_key.upper()} {item[ma_key]:.2f} "
        f"| {side} {abs(dist):.2f}%"
    )


def evaluate_ma_proximity(
    cache_dir: str = "cache_stock",
    tolerance_pct: float = 1.0,
    max_symbols: int = 0,
    top_n: int = 12,
) -> MAProximityResult:
    symbols = _symbols_from_cache(cache_dir, max_symbols=max_symbols)
    rows: List[Dict[str, Any]] = []
    last_updates: List[str] = []

    for sym in symbols:
        h = _load_history(sym, cache_dir)
        if h.empty or len(h) < 50:
            continue
        c = pd.to_numeric(h["close"], errors="coerce").dropna()
        if len(c) < 50:
            continue
        close = float(c.iloc[-1])
        ma20 = float(c.tail(20).mean())
        ma50 = float(c.tail(50).mean())
        if ma20 <= 0 or ma50 <= 0:
            continue
        d20 = (close / ma20 - 1.0) * 100.0
        d50 = (close / ma50 - 1.0) * 100.0
        last = _fmt_latest_date(h)
        if last:
            last_updates.append(last)
        rows.append({
            "symbol": sym,
            "close": close,
            "ma20": ma20,
            "ma50": ma50,
            "dist_ma20": d20,
            "dist_ma50": d50,
            "last_update": last,
        })

    near20_all = sorted([r for r in rows if abs(r["dist_ma20"]) <= tolerance_pct], key=lambda x: abs(x["dist_ma20"]))
    near50_all = sorted([r for r in rows if abs(r["dist_ma50"]) <= tolerance_pct], key=lambda x: abs(x["dist_ma50"]))
    near20 = near20_all[:top_n]
    near50 = near50_all[:top_n]

    if len(near20_all) + len(near50_all) >= 12:
        icon, status, label = "🟢", "ACTIVE", "Có nhiều mã đang gần MA20/MA50 để theo dõi"
    elif len(near20_all) + len(near50_all) >= 4:
        icon, status, label = "🟡", "WATCH", "Có một số mã gần MA20/MA50"
    elif rows:
        icon, status, label = "⚪", "QUIET", "Ít mã đang chạm vùng MA20/MA50"
    else:
        icon, status, label = "⚠️", "NO_DATA", "Không đủ dữ liệu để quét MA"

    # Lấy ngày mới nhất phổ biến nhất từ cache; nếu không được thì dùng max chuỗi ngày.
    last_update = ""
    try:
        parsed = [(pd.to_datetime(x, errors="coerce"), x) for x in last_updates]
        parsed = [(a, b) for a, b in parsed if not pd.isna(a)]
        if parsed:
            last_update = max(parsed, key=lambda t: t[0])[1]
    except Exception:
        last_update = max(last_updates) if last_updates else ""
    fr = _freshness(last_update)

    return MAProximityResult(
        status=status,
        icon=icon,
        label_vi=label,
        tolerance_pct=round(float(tolerance_pct), 2),
        universe_count=len(symbols),
        valid_count=len(rows),
        ma20_count=len(near20_all),
        ma50_count=len(near50_all),
        data_last_updated=last_update,
        data_freshness_icon=fr.get("icon", "⚪"),
        data_freshness_label=fr.get("label", "Không rõ độ mới dữ liệu"),
        data_age_hours=fr.get("age", ""),
        near_ma20_lines="\n".join(_line(x, "ma20") for x in near20) if near20 else "Không có mã nào trong biên độ.",
        near_ma50_lines="\n".join(_line(x, "ma50") for x in near50) if near50 else "Không có mã nào trong biên độ.",
        notes="Quét các mã có giá gần MA20/MA50 trong biên độ +/- tolerance. Đây là danh sách quan sát vùng hỗ trợ/kháng cự động, không phải lệnh mua/bán tự động.",
    )
