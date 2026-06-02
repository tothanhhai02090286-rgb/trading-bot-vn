# -*- coding: utf-8 -*-
"""
vn_leader_rotation.py

Leader Rotation Engine Lite cho V19.2 — Phase 9.1 + 9.2.

Phase 9.1 — Sector Mapping Engine:
- Ưu tiên lấy ngành từ watchlist nếu có cột Sector/Ngành.
- Nếu watchlist thiếu ngành, fallback sang sector_mapping.csv.
- Nếu vẫn thiếu, fallback UNKNOWN nhưng không làm crash workflow.

Phase 9.2 — Adjusted Rotation Score:
- Giữ Raw Rotation Score để thấy sức mạnh leader thuần.
- Tính Market Factor từ Mini Market Universe Score.
- Adjusted Rotation Score = Raw Rotation Score × Market Factor.
- Không can thiệp trực tiếp lệnh mua/bán của V19.2.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass
class LeaderRotationResult:
    status: str
    rotation_score: Any                 # adjusted score, dùng làm score chính sau Phase 9.2
    rotation_icon: str
    raw_rotation_score: Any
    market_factor: Any
    adjusted_rotation_score: Any
    universe_score: Any
    universe_size: int
    qualified_size: int
    sector_map_source: str
    mapped_universe_count: int
    mapped_qualified_count: int
    leading_sectors: str
    weak_sectors: str
    universe_leaders: str
    qualified_leaders: str
    flow_direction: str
    notes: str
    recommendation_lines: str

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


def _normalize_price(x: Any) -> Optional[float]:
    v = _to_num(x, default=np.nan)
    if pd.isna(v):
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


def _normalize_history(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    date_col = _find_col(out, ["time", "date", "Date", "datetime", "TradingDate", "Ngày"])
    close_col = _find_col(out, ["close", "Close", "adj_close", "price", "Giá đóng cửa"])
    high_col = _find_col(out, ["high", "High", "Giá cao nhất"])
    low_col = _find_col(out, ["low", "Low", "Giá thấp nhất"])
    vol_col = _find_col(out, ["volume", "Volume", "vol", "Khối lượng"])
    if close_col is None:
        return pd.DataFrame()
    out["date_norm"] = pd.to_datetime(out[date_col], errors="coerce") if date_col else pd.RangeIndex(start=0, stop=len(out), step=1)
    out["close"] = pd.to_numeric(out[close_col], errors="coerce").apply(_normalize_price)
    out["high"] = pd.to_numeric(out[high_col], errors="coerce").apply(_normalize_price) if high_col else out["close"]
    out["low"] = pd.to_numeric(out[low_col], errors="coerce").apply(_normalize_price) if low_col else out["close"]
    out["volume"] = pd.to_numeric(out[vol_col], errors="coerce").fillna(0) if vol_col else 0
    out = out.dropna(subset=["close"]).copy()
    if out.empty:
        return pd.DataFrame()
    return out.sort_values("date_norm").reset_index(drop=True)[["date_norm", "high", "low", "close", "volume"]]


def _cache_symbols(cache_dir: str) -> List[str]:
    if not os.path.isdir(cache_dir):
        return []
    symbols = []
    for fn in os.listdir(cache_dir):
        if not fn.lower().endswith(".csv"):
            continue
        sym = os.path.splitext(fn)[0].upper().strip()
        if sym and len(sym) <= 10:
            symbols.append(sym)
    return sorted(set(symbols))


def _sector_map_from_watchlist(watchlist_df: pd.DataFrame) -> Dict[str, str]:
    if watchlist_df is None or watchlist_df.empty:
        return {}
    sym_col = _find_col(watchlist_df, ["Mã", "Ma", "Symbol", "Ticker", "ticker", "Mã CP"])
    sector_col = _find_col(watchlist_df, ["Sector", "Ngành", "Nganh", "Industry", "industry"])
    if not sym_col or not sector_col:
        return {}
    mp: Dict[str, str] = {}
    for _, r in watchlist_df.iterrows():
        sym = _safe_str(r.get(sym_col, "")).upper()
        sec = _safe_str(r.get(sector_col, ""), "UNKNOWN")
        if sym and sec and sec.upper() != "UNKNOWN":
            mp[sym] = sec
    return mp


def _load_sector_mapping_file(path: Optional[str] = None) -> Dict[str, str]:
    candidates = []
    if path:
        candidates.append(path)
    candidates.extend([
        os.getenv("VN_SECTOR_MAPPING_PATH", ""),
        os.path.join(os.getcwd(), "v19.danh_muc_mua", "sector_mapping.csv"),
        os.path.join(os.getcwd(), "sector_mapping.csv"),
        "sector_mapping.csv",
    ])
    seen = set()
    for p in candidates:
        if not p or p in seen:
            continue
        seen.add(p)
        if not os.path.exists(p):
            continue
        try:
            df = _read_csv_smart(p)
            sym_col = _find_col(df, ["Ticker", "Mã", "Ma", "Symbol", "ticker"])
            sector_col = _find_col(df, ["Sector", "Ngành", "Nganh", "Industry", "industry"])
            if not sym_col or not sector_col:
                continue
            mp = {}
            for _, r in df.iterrows():
                sym = _safe_str(r.get(sym_col, "")).upper()
                sec = _safe_str(r.get(sector_col, ""), "UNKNOWN")
                if sym and sec and sec.upper() != "UNKNOWN":
                    mp[sym] = sec
            if mp:
                return mp
        except Exception:
            continue
    return {}


def _build_sector_map(watchlist_df: pd.DataFrame, sector_mapping_path: Optional[str] = None) -> Tuple[Dict[str, str], str]:
    wl = _sector_map_from_watchlist(watchlist_df)
    csv_map = _load_sector_mapping_file(sector_mapping_path)
    merged = dict(csv_map)
    # Watchlist override vì có thể là phân ngành tùy biến mới nhất của người dùng.
    merged.update(wl)
    if wl and csv_map:
        source = "watchlist + sector_mapping.csv"
    elif wl:
        source = "watchlist"
    elif csv_map:
        source = "sector_mapping.csv"
    else:
        source = "missing"
    return merged, source


def _qualified_symbols(watchlist_df: pd.DataFrame) -> List[str]:
    if watchlist_df is None or watchlist_df.empty:
        return []
    sym_col = _find_col(watchlist_df, ["Mã", "Ma", "Symbol", "Ticker", "ticker", "Mã CP"])
    if not sym_col:
        return []
    return sorted(set(str(x).upper().strip() for x in watchlist_df[sym_col].dropna().tolist() if str(x).strip()))


def _symbol_metrics(symbol: str, cache_dir: str, sector_map: Dict[str, str]) -> Optional[Dict[str, Any]]:
    path = os.path.join(cache_dir, f"{symbol}.csv")
    if not os.path.exists(path):
        path = os.path.join(cache_dir, f"{symbol.upper()}.csv")
    if not os.path.exists(path):
        return None
    try:
        hist = _normalize_history(_read_csv_smart(path))
    except Exception:
        return None
    if hist.empty or len(hist) < 5:
        return None
    c = pd.to_numeric(hist["close"], errors="coerce").dropna()
    if len(c) < 5:
        return None
    last = float(c.iloc[-1])
    prev1 = float(c.iloc[-2]) if len(c) >= 2 else last
    prev5 = float(c.iloc[-6]) if len(c) >= 6 else float(c.iloc[0])
    prev20 = float(c.iloc[-21]) if len(c) >= 21 else float(c.iloc[0])
    ma20 = float(c.tail(20).mean()) if len(c) >= 20 else float(c.mean())
    ma50 = float(c.tail(50).mean()) if len(c) >= 50 else float(c.mean())
    vol = pd.to_numeric(hist["volume"], errors="coerce").fillna(0)
    vol_ratio = 1.0
    if len(vol) >= 20 and float(vol.tail(20).mean()) > 0:
        vol_ratio = float(vol.iloc[-1] / vol.tail(20).mean())
    ret1 = (last / prev1 - 1.0) * 100 if prev1 > 0 else 0.0
    ret5 = (last / prev5 - 1.0) * 100 if prev5 > 0 else 0.0
    ret20 = (last / prev20 - 1.0) * 100 if prev20 > 0 else 0.0
    trend_bonus = 0
    if last >= ma20:
        trend_bonus += 12
    if last >= ma50:
        trend_bonus += 10
    score = 50 + ret5 * 2.0 + ret20 * 0.8 + trend_bonus + min(max((vol_ratio - 1.0) * 8, -8), 12)
    score = int(max(0, min(100, round(score))))
    sector = sector_map.get(symbol, "UNKNOWN")
    return {
        "symbol": symbol,
        "sector": sector,
        "has_sector": sector not in ["", "UNKNOWN"],
        "close": round(last, 3),
        "ret1": round(ret1, 2),
        "ret5": round(ret5, 2),
        "ret20": round(ret20, 2),
        "above_ma20": bool(last >= ma20),
        "above_ma50": bool(last >= ma50),
        "vol_ratio": round(vol_ratio, 2),
        "rotation_score": score,
    }


def _fmt_top_symbols(items: List[Dict[str, Any]], n: int = 5) -> str:
    if not items:
        return "Chưa đủ dữ liệu"
    top = sorted(items, key=lambda x: (x.get("rotation_score", 0), x.get("ret5", 0)), reverse=True)[:n]
    return ", ".join([f"{x['symbol']}({x.get('rotation_score', 0)})" for x in top])


def _sector_rank(items: List[Dict[str, Any]]) -> Tuple[str, str, str, int]:
    if not items:
        return "Chưa đủ dữ liệu", "Chưa đủ dữ liệu", "Chưa rõ", 0
    df = pd.DataFrame(items)
    if "sector" not in df.columns or df["sector"].fillna("UNKNOWN").eq("UNKNOWN").all():
        return "Thiếu map ngành", "Thiếu map ngành", "Chưa đủ map ngành để xác định luân chuyển ngành", 0
    df["sector"] = df["sector"].fillna("UNKNOWN")
    df = df[df["sector"] != "UNKNOWN"].copy()
    if df.empty:
        return "Thiếu map ngành", "Thiếu map ngành", "Chưa đủ map ngành để xác định luân chuyển ngành", 0
    g = df.groupby("sector", dropna=False).agg(
        count=("symbol", "count"),
        avg_score=("rotation_score", "mean"),
        avg_ret5=("ret5", "mean"),
        pct_above_ma20=("above_ma20", "mean"),
    ).reset_index()
    g = g[g["count"] >= 1].copy()
    if g.empty:
        return "Chưa đủ dữ liệu", "Chưa đủ dữ liệu", "Chưa rõ", 0
    g["sector_score"] = (
        g["avg_score"] * 0.65
        + (g["pct_above_ma20"] * 100) * 0.25
        + np.clip(g["avg_ret5"] * 3 + 50, 0, 100) * 0.10
    )
    g = g.sort_values("sector_score", ascending=False)
    lead = g.head(3)
    weak = g.tail(3).sort_values("sector_score", ascending=True)
    leading = ", ".join([f"{r['sector']}({int(round(r['sector_score']))})" for _, r in lead.iterrows()])
    weakening = ", ".join([f"{r['sector']}({int(round(r['sector_score']))})" for _, r in weak.iterrows()])
    if len(g) >= 2:
        flow = f"Dòng tiền nghiêng về {str(lead.iloc[0]['sector'])}; yếu nhất: {str(weak.iloc[0]['sector'])}"
    else:
        flow = f"Dòng tiền tập trung ở {str(lead.iloc[0]['sector'])}"
    rotation_score = int(round(float(g["sector_score"].head(3).mean())))
    return leading, weakening, flow, rotation_score


def _market_factor(universe_score: Any) -> float:
    s = _to_num(universe_score, default=np.nan)
    if pd.isna(s):
        return 1.0
    if s >= 75:
        return 1.00
    if s >= 55:
        return 0.85
    if s >= 40:
        return 0.70
    if s >= 25:
        return 0.55
    return 0.40


def _status_from_adjusted(raw_score: int, adjusted_score: int, factor: float) -> Tuple[str, str, str]:
    if adjusted_score >= 75:
        return "ROTATION XÁC NHẬN XU HƯỚNG", "🟢", "🟢 Leader mạnh và thị trường ủng hộ, ưu tiên quan sát nhóm dẫn dắt"
    if adjusted_score >= 60:
        return "CÓ LEADER HỢP LỆ", "🟡", "🟡 Có nhóm dẫn dắt, chỉ giải ngân khi setup và quản trị vốn cho phép"
    if adjusted_score >= 40:
        return "LEADER PHÂN HÓA", "🟠", "🟠 Có leader nhưng độ lan tỏa chưa đủ mạnh, không mua lan man"
    if raw_score >= 70 and factor <= 0.55:
        return "CÓ LEADER NHƯNG MARKET YẾU", "🟠", "🟠 Có leader riêng lẻ nhưng thị trường chung yếu; chỉ quan sát, không dùng để mua mới"
    return "KHÔNG CÓ ROTATION HỢP LỆ", "🔴", "🔴 Rotation sau điều chỉnh yếu, hạn chế mở vị thế mới"


def evaluate_leader_rotation(
    watchlist_df: pd.DataFrame,
    cache_dir: str = "cache_stock",
    max_symbols: int = 0,
    universe_score: Any = None,
    sector_mapping_path: Optional[str] = None,
) -> LeaderRotationResult:
    sector_map, sector_map_source = _build_sector_map(watchlist_df, sector_mapping_path)
    universe = _cache_symbols(cache_dir)
    if max_symbols and max_symbols > 0:
        universe = universe[:max_symbols]
    qualified = _qualified_symbols(watchlist_df)

    universe_items: List[Dict[str, Any]] = []
    for sym in universe:
        m = _symbol_metrics(sym, cache_dir, sector_map)
        if m is not None:
            universe_items.append(m)

    qualified_items: List[Dict[str, Any]] = []
    for sym in qualified:
        m = _symbol_metrics(sym, cache_dir, sector_map)
        if m is not None:
            qualified_items.append(m)

    q_lead, q_weak, q_flow, q_score = _sector_rank(qualified_items)
    u_lead, u_weak, u_flow, u_score = _sector_rank(universe_items)

    if q_score > 0:
        raw_score = q_score
        leading = q_lead
        weak = q_weak
        flow = q_flow
    elif u_score > 0:
        raw_score = u_score
        leading = u_lead
        weak = u_weak
        flow = u_flow
    else:
        all_scores = [x.get("rotation_score", 0) for x in universe_items]
        raw_score = int(round(float(np.mean(sorted(all_scores, reverse=True)[:10])))) if all_scores else 0
        leading = "Thiếu map ngành"
        weak = "Thiếu map ngành"
        flow = "Chưa đủ map ngành; tạm xem leader theo mã"

    factor = _market_factor(universe_score)
    adjusted_score = int(max(0, min(100, round(raw_score * factor))))
    status, icon, rec = _status_from_adjusted(raw_score, adjusted_score, factor)

    universe_leaders = _fmt_top_symbols(universe_items)
    qualified_leaders = _fmt_top_symbols(qualified_items)
    mapped_universe_count = sum(1 for x in universe_items if x.get("has_sector"))
    mapped_qualified_count = sum(1 for x in qualified_items if x.get("has_sector"))

    notes = []
    if sector_map_source == "missing":
        notes.append("Thiếu sector_mapping.csv và watchlist thiếu cột Sector/Ngành")
    else:
        notes.append(f"Sector map source: {sector_map_source}")
    if q_score <= 0:
        notes.append("Qualified chưa đủ dữ liệu ngành, engine dùng Universe/fallback")
    if len(universe_items) < len(universe):
        notes.append(f"Universe có {len(universe_items)}/{len(universe)} mã đủ dữ liệu cache")
    if factor < 1.0:
        notes.append(f"Adjusted theo Mini Market Universe Score {universe_score}: factor {factor:.2f}")

    return LeaderRotationResult(
        status=status,
        rotation_score=adjusted_score,
        rotation_icon=icon,
        raw_rotation_score=raw_score,
        market_factor=round(factor, 2),
        adjusted_rotation_score=adjusted_score,
        universe_score=universe_score if universe_score is not None else "",
        universe_size=len(universe),
        qualified_size=len(qualified),
        sector_map_source=sector_map_source,
        mapped_universe_count=mapped_universe_count,
        mapped_qualified_count=mapped_qualified_count,
        leading_sectors=leading,
        weak_sectors=weak,
        universe_leaders=universe_leaders,
        qualified_leaders=qualified_leaders,
        flow_direction=flow,
        notes="; ".join(notes),
        recommendation_lines=rec,
    )
