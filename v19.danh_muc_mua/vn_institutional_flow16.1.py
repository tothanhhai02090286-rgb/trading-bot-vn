# -*- coding: utf-8 -*-
"""
vn_institutional_flow.py

PHASE 15 — Institutional Flow Layer Lite cho V19.2.

Production-safe design:
- Chạy độc lập, không thay đổi action mua/bán.
- Dùng cache_stock/*.csv + sector_mapping.csv hiện có.
- Nếu thiếu dữ liệu thì trả UNKNOWN, không làm crash Render/GitHub Actions.
- Phân biệt Leader Rotation với Money Flow: đo dòng tiền theo ngành bằng return + breadth + volume expansion.
"""
from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


@dataclass
class InstitutionalFlowResult:
    status: str = "UNKNOWN"
    icon: str = "⚪"
    market_flow_score: Any = ""
    market_flow_label: str = "UNKNOWN"
    sector_count: int = 0
    symbol_count: int = 0
    data_count: int = 0
    data_last_updated: str = ""
    data_freshness_status: str = "UNKNOWN"
    data_freshness_icon: str = "⚪"
    data_freshness_label: str = "Không rõ độ mới dữ liệu"
    data_age_hours: Any = ""
    top_sectors: str = ""
    weak_sectors: str = ""
    accumulation_sectors: str = ""
    distribution_sectors: str = ""
    banking_score: Any = ""
    securities_score: Any = ""
    real_estate_score: Any = ""
    position_sector_notes: str = ""
    notes: str = ""
    recommendation_lines: str = ""

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
    # Một số nguồn lưu giá dạng đồng, một số dạng nghìn đồng.
    if x > 1000:
        x = x / 1000.0
    return float(x)


def _load_sector_map(sector_mapping_path: Optional[str] = None) -> Dict[str, str]:
    candidates = []
    if sector_mapping_path:
        candidates.append(sector_mapping_path)
    candidates.extend([
        os.getenv("VN_SECTOR_MAPPING_PATH", ""),
        os.path.join(os.getcwd(), "v19.danh_muc_mua", "sector_mapping.csv"),
        os.path.join(os.getcwd(), "configs", "stock_sector_map.csv"),
        "v19.danh_muc_mua/sector_mapping.csv",
        "configs/stock_sector_map.csv",
        "sector_mapping.csv",
    ])
    seen = set()
    for p in candidates:
        if not p or p in seen or not os.path.exists(p):
            continue
        seen.add(p)
        try:
            df = _read_csv_smart(p)
            sym_col = _find_col(df, ["Ticker", "Mã", "Ma", "Symbol", "ticker"])
            sec_col = _find_col(df, ["Sector", "Ngành", "Nganh", "Industry", "industry"])
            if not sym_col or not sec_col:
                continue
            mp: Dict[str, str] = {}
            for _, r in df.iterrows():
                sym = _safe_str(r.get(sym_col, "")).upper()
                sec = _safe_str(r.get(sec_col, "UNKNOWN"), "UNKNOWN")
                if sym and sec and sec.upper() != "UNKNOWN":
                    mp[sym] = sec
            if mp:
                return mp
        except Exception:
            continue
    return {}


def _cache_symbols(cache_dir: str, max_symbols: int = 0) -> List[str]:
    if not cache_dir or not os.path.isdir(cache_dir):
        return []
    syms = []
    for fn in sorted(os.listdir(cache_dir)):
        if not fn.lower().endswith(".csv"):
            continue
        sym = os.path.splitext(fn)[0].upper().strip()
        if sym and len(sym) <= 10:
            syms.append(sym)
    syms = sorted(set(syms))
    if max_symbols and max_symbols > 0:
        return syms[:max_symbols]
    return syms


def _load_history(symbol: str, cache_dir: str) -> pd.DataFrame:
    candidates = [
        os.path.join(cache_dir, f"{symbol}.csv"),
        os.path.join(cache_dir, f"{symbol.upper()}.csv"),
    ]
    for p in candidates:
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


def _symbol_flow_metrics(symbol: str, cache_dir: str) -> Optional[Dict[str, Any]]:
    h = _load_history(symbol, cache_dir)
    if h.empty or len(h) < 21:
        return None
    close = pd.to_numeric(h["close"], errors="coerce").dropna()
    vol = pd.to_numeric(h["volume"], errors="coerce").fillna(0)
    if len(close) < 21:
        return None
    cur = float(close.iloc[-1])
    ret5 = (cur / float(close.iloc[-6]) - 1.0) * 100.0 if close.iloc[-6] else 0.0
    ret10 = (cur / float(close.iloc[-11]) - 1.0) * 100.0 if len(close) >= 11 and close.iloc[-11] else ret5
    ret20 = (cur / float(close.iloc[-21]) - 1.0) * 100.0 if close.iloc[-21] else ret10
    ma20 = float(close.tail(20).mean())
    above_ma20 = cur >= ma20 if ma20 > 0 else False
    vol_ratio = None
    if len(vol) >= 21:
        base = float(vol.iloc[-21:-1].mean())
        if base > 0:
            vol_ratio = float(vol.iloc[-1] / base)
    last_update = ""
    try:
        lu = h["date_norm"].iloc[-1]
        if hasattr(lu, "strftime") and not pd.isna(lu):
            last_update = lu.strftime("%Y-%m-%d %H:%M") if getattr(lu, "hour", 0) or getattr(lu, "minute", 0) else lu.strftime("%Y-%m-%d")
        else:
            last_update = str(lu)
    except Exception:
        last_update = ""

    return {
        "Mã": symbol,
        "ret5_pct": ret5,
        "ret10_pct": ret10,
        "ret20_pct": ret20,
        "above_ma20": bool(above_ma20),
        "volume_ratio20": vol_ratio,
        "last_update": last_update,
    }



def _parse_last_update(value: Any) -> Optional[datetime]:
    s = _safe_str(value, "")
    if not s:
        return None
    try:
        ts = pd.to_datetime(s, errors="coerce")
        if pd.isna(ts):
            return None
        if hasattr(ts, "to_pydatetime"):
            return ts.to_pydatetime().replace(tzinfo=None)
    except Exception:
        return None
    return None


def _data_freshness(last_update: str) -> Dict[str, Any]:
    dt = _parse_last_update(last_update)
    try:
        now_vn = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).replace(tzinfo=None)
    except Exception:
        now_vn = datetime.now()
    if not dt:
        return {
            "data_last_updated": last_update or "UNKNOWN",
            "data_freshness_status": "UNKNOWN",
            "data_freshness_icon": "⚪",
            "data_freshness_label": "Không rõ độ mới dữ liệu",
            "data_age_hours": "",
        }
    age_hours = round(max(0.0, (now_vn - dt).total_seconds() / 3600.0), 1)
    if dt.date() == now_vn.date():
        status = "FRESH_INTRADAY"
        icon = "🟢"
        label = "MỚI (TRONG PHIÊN / HÔM NAY)"
    else:
        status = "STALE_LAST_AVAILABLE"
        icon = "🟠"
        label = "CŨ (CHÚ Ý) — đang dùng dữ liệu gần nhất có sẵn"
    return {
        "data_last_updated": last_update,
        "data_freshness_status": status,
        "data_freshness_icon": icon,
        "data_freshness_label": label,
        "data_age_hours": age_hours,
    }

def _score_sector(g: pd.DataFrame) -> Dict[str, Any]:
    avg_ret5 = float(pd.to_numeric(g["ret5_pct"], errors="coerce").mean())
    avg_ret10 = float(pd.to_numeric(g["ret10_pct"], errors="coerce").mean())
    avg_ret20 = float(pd.to_numeric(g["ret20_pct"], errors="coerce").mean())
    breadth = float(pd.to_numeric(g["above_ma20"], errors="coerce").mean() * 100.0)
    vr = pd.to_numeric(g["volume_ratio20"], errors="coerce").dropna()
    avg_vr = float(vr.mean()) if len(vr) else 1.0

    score = 50.0
    score += max(min(avg_ret5 * 2.8, 18.0), -18.0)
    score += max(min(avg_ret10 * 1.8, 18.0), -18.0)
    score += max(min(avg_ret20 * 1.1, 15.0), -15.0)
    score += (breadth - 50.0) * 0.25
    score += max(min((avg_vr - 1.0) * 14.0, 14.0), -10.0)
    score = round(max(0.0, min(100.0, score)), 1)

    # Dùng ngôn ngữ trung tính: đây là điểm dòng tiền TƯƠNG ĐỐI theo ngành,
    # không kết luận có/không có dòng tiền tổ chức thật sự mua/bán.
    if score >= 75:
        label = "🟢 DÒNG TIỀN RẤT MẠNH"
    elif score >= 62:
        label = "🟢 DÒNG TIỀN MẠNH"
    elif score >= 48:
        label = "🟡 TRUNG TÍNH"
    elif score >= 35:
        label = "🟠 DÒNG TIỀN YẾU"
    else:
        label = "🔴 RẤT YẾU / KÉM LAN TỎA"

    return {
        "score": score,
        "label": label,
        "members": int(len(g)),
        "avg_ret5_pct": round(avg_ret5, 2),
        "avg_ret10_pct": round(avg_ret10, 2),
        "avg_ret20_pct": round(avg_ret20, 2),
        "above_ma20_pct": round(breadth, 1),
        "avg_volume_ratio20": round(avg_vr, 2),
    }


def _fmt_sector_row(sec: str, r: Dict[str, Any]) -> str:
    return f"- {sec}: {r.get('score')}/100 | {r.get('label')} | 5D {r.get('avg_ret5_pct')}% | Vol {r.get('avg_volume_ratio20')}x"


def _fmt_position_flow_note(sym: str, sec: str, ss: Dict[str, Any]) -> str:
    return f"- {sym}: {sec} | {ss.get('score')}/100 | {ss.get('label')}"


def _canonical_sector_score(sector_scores: Dict[str, Dict[str, Any]], names: List[str]) -> Any:
    for name in names:
        if name in sector_scores:
            return sector_scores[name].get("score", "")
    return ""


def evaluate_institutional_flow(
    watchlist_df: Optional[pd.DataFrame] = None,
    positions_df: Optional[pd.DataFrame] = None,
    cache_dir: str = "cache_stock",
    sector_mapping_path: Optional[str] = None,
    max_symbols: int = 0,
) -> InstitutionalFlowResult:
    sector_map = _load_sector_map(sector_mapping_path)
    if not sector_map:
        return InstitutionalFlowResult(status="UNKNOWN", notes="Không tìm thấy sector_mapping.csv/configs stock sector map")

    symbols = _cache_symbols(cache_dir, max_symbols=max_symbols)
    if not symbols:
        return InstitutionalFlowResult(status="UNKNOWN", notes=f"Không tìm thấy cache CSV trong {cache_dir}")

    rows: List[Dict[str, Any]] = []
    for sym in symbols:
        sec = sector_map.get(sym, "UNKNOWN")
        if not sec or sec.upper() == "UNKNOWN":
            continue
        m = _symbol_flow_metrics(sym, cache_dir)
        if not m:
            continue
        m["Sector"] = sec
        rows.append(m)

    if not rows:
        return InstitutionalFlowResult(status="UNKNOWN", symbol_count=len(symbols), notes="Chưa đủ dữ liệu lịch sử >= 21 phiên để tính institutional flow")

    df = pd.DataFrame(rows)
    sector_scores: Dict[str, Dict[str, Any]] = {}
    for sec, g in df.groupby("Sector"):
        if len(g) < 2:
            continue
        sector_scores[str(sec)] = _score_sector(g)

    if not sector_scores:
        return InstitutionalFlowResult(status="UNKNOWN", symbol_count=len(symbols), data_count=len(df), notes="Ngành có quá ít mã hợp lệ để xếp hạng")

    last_updates = [_safe_str(x, "") for x in df.get("last_update", pd.Series(dtype=str)).dropna().tolist()]
    latest_update = ""
    if last_updates:
        parsed = [(_parse_last_update(x), x) for x in last_updates]
        parsed = [(d, x) for d, x in parsed if d is not None]
        if parsed:
            latest_update = max(parsed, key=lambda t: t[0])[1]
        else:
            latest_update = last_updates[-1]
    freshness = _data_freshness(latest_update)

    ranked = sorted(sector_scores.items(), key=lambda kv: kv[1]["score"], reverse=True)
    weak = sorted(sector_scores.items(), key=lambda kv: kv[1]["score"])
    market_score = round(float(pd.Series([v["score"] for v in sector_scores.values()]).mean()), 1)
    if market_score >= 70:
        status, icon, label = "RISK_ON", "🟢", "Dòng tiền lan tỏa tốt"
    elif market_score >= 55:
        status, icon, label = "SELECTIVE", "🟡", "Dòng tiền chọn lọc"
    elif market_score >= 42:
        status, icon, label = "CAUTION", "🟠", "Dòng tiền yếu/khó lan tỏa"
    else:
        status, icon, label = "RISK_OFF", "🔴", "Dòng tiền rất yếu / ưu tiên phòng thủ"

    accumulation = [(s, r) for s, r in ranked if r["score"] >= 62]
    distribution = [(s, r) for s, r in weak if r["score"] < 42]

    pos_notes = []
    if positions_df is not None and not positions_df.empty:
        sym_col = _find_col(positions_df, ["Mã", "Ma", "Symbol", "Ticker", "ticker", "Mã CP"])
        if sym_col:
            for sym in positions_df[sym_col].astype(str).str.upper().str.strip().dropna().tolist():
                sec = sector_map.get(sym, "UNKNOWN")
                ss = sector_scores.get(sec)
                if ss:
                    pos_notes.append(_fmt_position_flow_note(sym, sec, ss))
                else:
                    pos_notes.append(f"- {sym}: {sec} | ⚪ chưa đủ dữ liệu ngành")

    rec_lines = []
    if status == "RISK_ON":
        rec_lines.append("✅ Có thể ưu tiên mã thuộc ngành dòng tiền mạnh, nhưng vẫn theo Position State/Trade Safety.")
    elif status == "SELECTIVE":
        rec_lines.append("🟡 Chỉ ưu tiên leader trong top ngành, hạn chế mua lan man.")
    elif status == "CAUTION":
        rec_lines.append("⚠️ Giảm mua mới nếu mã không thuộc nhóm có dòng tiền rõ.")
    else:
        rec_lines.append("🛑 Ưu tiên phòng thủ, không nâng tỷ trọng khi dòng tiền tương đối yếu.")
    if ranked:
        rec_lines.append("Top ngành nên theo dõi: " + ", ".join([s for s, _ in ranked[:3]]))

    return InstitutionalFlowResult(
        status=status,
        icon=icon,
        market_flow_score=market_score,
        market_flow_label=label,
        sector_count=len(sector_scores),
        symbol_count=len(symbols),
        data_count=len(df),
        data_last_updated=freshness.get("data_last_updated", ""),
        data_freshness_status=freshness.get("data_freshness_status", "UNKNOWN"),
        data_freshness_icon=freshness.get("data_freshness_icon", "⚪"),
        data_freshness_label=freshness.get("data_freshness_label", "Không rõ độ mới dữ liệu"),
        data_age_hours=freshness.get("data_age_hours", ""),
        top_sectors="\n".join(_fmt_sector_row(s, r) for s, r in ranked[:5]),
        weak_sectors="\n".join(_fmt_sector_row(s, r) for s, r in weak[:5]),
        accumulation_sectors="\n".join(_fmt_sector_row(s, r) for s, r in accumulation[:5]),
        distribution_sectors="\n".join(_fmt_sector_row(s, r) for s, r in distribution[:5]),
        banking_score=_canonical_sector_score(sector_scores, ["Ngân hàng", "Banking", "Banks"]),
        securities_score=_canonical_sector_score(sector_scores, ["Chứng khoán", "Securities"]),
        real_estate_score=_canonical_sector_score(sector_scores, ["Bất động sản", "Real Estate"]),
        position_sector_notes="\n".join(pos_notes[:10]),
        notes=f"Score là dòng tiền tương đối theo giá + breadth + volume, không phải kết luận tiền lớn mua/bán thật. Luôn dùng dữ liệu gần nhất có sẵn; xem Last Updated và trạng thái dữ liệu. Tính từ {len(df)} mã hợp lệ / {len(symbols)} mã cache; {len(sector_scores)} ngành đủ dữ liệu.",
        recommendation_lines="\n".join(rec_lines),
    )
