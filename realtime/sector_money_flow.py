# -*- coding: utf-8 -*-
"""
sector_money_flow.py

VN Sector Money Flow helper for the Vietnamese stock trading bot.

Design goals:
- Lightweight and safe: if sector data/cache is missing, return UNKNOWN instead of crashing.
- Use a local stock->sector map plus cache_stock/*.csv to estimate sector strength.
- Never upgrade a buy recommendation mechanically; only cap/downgrade when the sector is weak.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


DEFAULT_MAP_CANDIDATES = [
    "configs/stock_sector_map.csv",
    "../configs/stock_sector_map.csv",
    "stock_sector_map.csv",
    "../stock_sector_map.csv",
]


@dataclass
class SectorFlowResult:
    symbol: str
    sector: str = "UNKNOWN"
    status: str = "UNKNOWN"      # MẠNH / KHÁ / TRUNG TÍNH / YẾU / UNKNOWN
    score: float = 50.0
    rank_in_sector: str = ""
    sector_size: int = 0
    data_count: int = 0
    avg_ret5_pct: Optional[float] = None
    avg_ret20_pct: Optional[float] = None
    above_ma20_pct: Optional[float] = None
    avg_volume_ratio20: Optional[float] = None
    leaders: str = ""
    laggards: str = ""
    note: str = ""

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


def _find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    lower_map = {str(c).lower(): c for c in df.columns}
    for c in candidates:
        if c in df.columns:
            return c
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return None


def _read_csv_smart(path: str) -> pd.DataFrame:
    for enc in ["utf-8-sig", "utf-8", "cp1258", "latin1"]:
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            pass
    return pd.read_csv(path)


def load_sector_map(map_path: Optional[str] = None) -> pd.DataFrame:
    candidates = []
    if map_path:
        candidates.append(map_path)
    candidates += DEFAULT_MAP_CANDIDATES

    for p in candidates:
        if p and os.path.exists(p):
            df = _read_csv_smart(p)
            symbol_col = _find_col(df, ["Mã", "Ma", "Symbol", "Ticker", "ticker"])
            sector_col = _find_col(df, ["Ngành", "Nganh", "Sector", "sector", "Industry"])
            if symbol_col and sector_col:
                out = df[[symbol_col, sector_col]].copy()
                out.columns = ["Mã", "Ngành"]
                out["Mã"] = out["Mã"].astype(str).str.upper().str.strip()
                out["Ngành"] = out["Ngành"].astype(str).str.strip()
                out = out[(out["Mã"] != "") & (out["Mã"] != "NAN") & (out["Ngành"] != "")]
                return out.drop_duplicates(subset=["Mã"], keep="first").reset_index(drop=True)
    return pd.DataFrame(columns=["Mã", "Ngành"])


def get_sector(symbol: str, map_df: Optional[pd.DataFrame] = None, map_path: Optional[str] = None) -> str:
    symbol = str(symbol).upper().strip()
    if map_df is None:
        map_df = load_sector_map(map_path)
    if map_df is None or map_df.empty or "Mã" not in map_df.columns:
        return "UNKNOWN"
    m = map_df[map_df["Mã"].astype(str).str.upper().str.strip() == symbol]
    if m.empty:
        return "UNKNOWN"
    return _safe_str(m.iloc[0].get("Ngành"), "UNKNOWN")


def _load_history(symbol: str, cache_dir: str) -> pd.DataFrame:
    candidates = [
        os.path.join(cache_dir, f"{symbol}.csv"),
        os.path.join(cache_dir, f"{symbol.upper()}.csv"),
        os.path.join("..", cache_dir, f"{symbol}.csv"),
        os.path.join("..", cache_dir, f"{symbol.upper()}.csv"),
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                df = _read_csv_smart(p)
                close_col = _find_col(df, ["close", "Close", "adj_close", "price", "Giá đóng cửa"])
                vol_col = _find_col(df, ["volume", "Volume", "vol", "Khối lượng"])
                date_col = _find_col(df, ["time", "date", "Date", "datetime", "TradingDate", "Ngày"])
                if not close_col:
                    continue
                out = pd.DataFrame()
                out["close"] = pd.to_numeric(df[close_col], errors="coerce").apply(_normalize_price)
                out["volume"] = pd.to_numeric(df[vol_col], errors="coerce").fillna(0) if vol_col else 0
                out["date_norm"] = pd.to_datetime(df[date_col], errors="coerce") if date_col else range(len(out))
                out = out.dropna(subset=["close"]).copy()
                return out.sort_values("date_norm").reset_index(drop=True)
            except Exception:
                continue
    return pd.DataFrame()


def _symbol_metrics(symbol: str, cache_dir: str) -> Optional[Dict[str, Any]]:
    hist = _load_history(symbol, cache_dir)
    if hist.empty or len(hist) < 6:
        return None
    close = pd.to_numeric(hist["close"], errors="coerce").dropna()
    vol = pd.to_numeric(hist["volume"], errors="coerce").fillna(0)
    if len(close) < 6:
        return None
    current = float(close.iloc[-1])
    ret5 = (current / float(close.iloc[-6]) - 1.0) * 100.0 if len(close) >= 6 and close.iloc[-6] else 0.0
    ret20 = (current / float(close.iloc[-21]) - 1.0) * 100.0 if len(close) >= 21 and close.iloc[-21] else ret5
    ma20 = float(close.tail(20).mean()) if len(close) >= 20 else float(close.mean())
    above_ma20 = current >= ma20 if ma20 > 0 else False
    volume_ratio20 = None
    if len(vol) >= 20 and float(vol.tail(20).mean()) > 0:
        volume_ratio20 = float(vol.iloc[-1] / vol.tail(20).mean())
    return {
        "Mã": symbol,
        "close": current,
        "ret5_pct": ret5,
        "ret20_pct": ret20,
        "above_ma20": bool(above_ma20),
        "volume_ratio20": volume_ratio20,
    }


def _status_from_score(score: float, data_count: int) -> str:
    if data_count <= 0:
        return "UNKNOWN"
    if score >= 72:
        return "MẠNH"
    if score >= 60:
        return "KHÁ"
    if score >= 45:
        return "TRUNG TÍNH"
    return "YẾU"


def evaluate_sector_money_flow(
    symbol: str,
    watchlist_df: Optional[pd.DataFrame] = None,
    cache_dir: str = "cache_stock",
    map_path: Optional[str] = None,
) -> SectorFlowResult:
    """Evaluate sector money flow for a symbol.

    Uses the local sector map and cache history. If data is missing, returns UNKNOWN safely.
    """
    symbol = str(symbol).upper().strip()
    map_df = load_sector_map(map_path)
    sector = get_sector(symbol, map_df, map_path)
    if sector == "UNKNOWN":
        return SectorFlowResult(symbol=symbol, sector="UNKNOWN", note="Chưa có mã trong stock_sector_map.csv")

    members = map_df[map_df["Ngành"] == sector]["Mã"].astype(str).str.upper().str.strip().dropna().unique().tolist()
    metrics: List[Dict[str, Any]] = []
    for m in members:
        sm = _symbol_metrics(m, cache_dir)
        if sm:
            metrics.append(sm)

    if not metrics:
        return SectorFlowResult(symbol=symbol, sector=sector, sector_size=len(members), note="Chưa đủ cache lịch sử để chấm dòng tiền ngành")

    df = pd.DataFrame(metrics)
    avg_ret5 = float(pd.to_numeric(df["ret5_pct"], errors="coerce").mean())
    avg_ret20 = float(pd.to_numeric(df["ret20_pct"], errors="coerce").mean())
    above_ma20_pct = float(pd.to_numeric(df["above_ma20"], errors="coerce").mean() * 100.0)
    vr = pd.to_numeric(df.get("volume_ratio20"), errors="coerce").dropna()
    avg_vr = float(vr.mean()) if len(vr) else None

    score = 50.0
    score += max(min(avg_ret5 * 3.0, 18.0), -18.0)
    score += max(min(avg_ret20 * 1.5, 18.0), -18.0)
    score += (above_ma20_pct - 50.0) * 0.30
    if avg_vr is not None:
        score += max(min((avg_vr - 1.0) * 12.0, 12.0), -8.0)

    # Small boost if sector has several names in the current realtime watchlist.
    if watchlist_df is not None and not watchlist_df.empty and "Mã" in watchlist_df.columns:
        wl = set(watchlist_df["Mã"].astype(str).str.upper().str.strip().tolist())
        sector_hits = len([m for m in members if m in wl])
        if sector_hits >= 3:
            score += 6
        elif sector_hits >= 2:
            score += 3

    score = round(max(0.0, min(100.0, score)), 1)
    status = _status_from_score(score, len(df))

    df_rank = df.sort_values("ret20_pct", ascending=False).reset_index(drop=True)
    leaders = ", ".join(df_rank.head(3)["Mã"].tolist())
    laggards = ", ".join(df_rank.tail(3)["Mã"].tolist())
    rank_text = ""
    if symbol in df_rank["Mã"].tolist():
        rank = int(df_rank.index[df_rank["Mã"] == symbol][0]) + 1
        rank_text = f"{rank}/{len(df_rank)}"

    note = {
        "MẠNH": "Ngành đang hút tiền, tín hiệu cùng ngành đáng tin hơn.",
        "KHÁ": "Ngành khá ổn, có thể ủng hộ tín hiệu nếu mã không quá đuổi giá.",
        "TRUNG TÍNH": "Dòng tiền ngành chưa quá rõ, không cộng điểm mạnh.",
        "YẾU": "Ngành yếu, hạn chế mua mới hoặc mua thêm.",
        "UNKNOWN": "Chưa đủ dữ liệu ngành.",
    }.get(status, "")

    return SectorFlowResult(
        symbol=symbol,
        sector=sector,
        status=status,
        score=score,
        rank_in_sector=rank_text,
        sector_size=len(members),
        data_count=len(df),
        avg_ret5_pct=round(avg_ret5, 2),
        avg_ret20_pct=round(avg_ret20, 2),
        above_ma20_pct=round(above_ma20_pct, 1),
        avg_volume_ratio20=round(avg_vr, 2) if avg_vr is not None else None,
        leaders=leaders,
        laggards=laggards,
        note=note,
    )


def adjust_entry_by_sector(recommendation: str, sector_flow: SectorFlowResult) -> Tuple[str, str]:
    """Cap entry recommendations when the sector is weak. Never upgrades recommendation."""
    rec = str(recommendation or "WATCH").strip().upper()
    status = sector_flow.status
    if status == "YẾU":
        if rec in ["BUY CÓ KIỂM SOÁT", "BUY NHỎ"]:
            return "TEST NHỎ", f"Sector Flow yếu ({sector_flow.sector}, score {sector_flow.score}) nên hạ từ {recommendation} xuống TEST NHỎ"
        if rec == "TEST NHỎ":
            return "WATCH", f"Sector Flow yếu ({sector_flow.sector}, score {sector_flow.score}) nên hạ TEST NHỎ xuống WATCH"
    if status == "UNKNOWN":
        return recommendation, "Sector Flow chưa đủ dữ liệu, không cộng điểm"
    return recommendation, f"Sector Flow {status}: {sector_flow.sector}, score {sector_flow.score}"


def adjust_add_by_sector(add_ok: bool, add_reason: str, sector_flow: SectorFlowResult) -> Tuple[bool, str]:
    """Block add when sector is weak/unknown and the bot is considering adding to an existing position."""
    if not add_ok:
        return add_ok, add_reason
    if sector_flow.status == "YẾU":
        return False, f"Không mua thêm vì Sector Flow yếu: {sector_flow.sector}, score {sector_flow.score}"
    if sector_flow.status == "UNKNOWN":
        return False, "Không mua thêm vì chưa đủ dữ liệu Sector Flow"
    return add_ok, add_reason
