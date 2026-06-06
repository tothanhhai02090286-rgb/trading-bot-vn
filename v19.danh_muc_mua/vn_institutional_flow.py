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
import json
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



SECTOR_PERSISTENCE_HISTORY_PATH = os.getenv(
    "VN_SECTOR_PERSISTENCE_HISTORY_PATH",
    "sector_persistence_history.json",
)
SECTOR_PERSISTENCE_LOOKBACK = int(os.getenv("VN_SECTOR_PERSISTENCE_LOOKBACK", "10"))
SECTOR_PERSISTENCE_TOP_N = int(os.getenv("VN_SECTOR_PERSISTENCE_TOP_N", "5"))
SECTOR_PERSISTENCE_MIN_DAYS = int(os.getenv("VN_SECTOR_PERSISTENCE_MIN_DAYS", "5"))


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
    """Load sector map theo kiểu MERGE, không dừng ở file map đầu tiên.

    Lý do production:
    - v19.danh_muc_mua/sector_mapping.csv có thể là map cũ và còn UNKNOWN.
    - configs/stock_sector_map.csv trong repo hiện đã đủ 138 mã.
    - Nếu return ngay ở file đầu tiên thì Institutional Flow chỉ tính được 109/138 mã.

    Quy tắc merge:
    1. Đọc nhiều nguồn sector map.
    2. Bỏ qua UNKNOWN / trống.
    3. File đọc sau được phép bổ sung mã còn thiếu.
    4. Không ghi đè sector đã có, trừ khi sector cũ là UNKNOWN/trống.
    """
    candidates = []
    if sector_mapping_path:
        candidates.append(sector_mapping_path)

    # Ưu tiên master map trong configs vì file này đang đủ universe cache_stock 138 mã.
    candidates.extend([
        os.getenv("VN_SECTOR_MAPPING_PATH", ""),
        os.path.join(os.getcwd(), "configs", "stock_sector_map.csv"),
        os.path.join(os.getcwd(), "v19.danh_muc_mua", "sector_mapping.csv"),
        "configs/stock_sector_map.csv",
        "v19.danh_muc_mua/sector_mapping.csv",
        "sector_mapping.csv",
    ])

    merged: Dict[str, str] = {}
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
            for _, r in df.iterrows():
                sym = _safe_str(r.get(sym_col, "")).upper()
                sec = _safe_str(r.get(sec_col, "UNKNOWN"), "UNKNOWN")
                if not sym:
                    continue
                if not sec or sec.upper() in {"UNKNOWN", "N/A", "NA", "NONE", "NULL"}:
                    continue
                if sym not in merged or not merged.get(sym) or str(merged.get(sym)).upper() == "UNKNOWN":
                    merged[sym] = sec
        except Exception:
            continue
    return merged

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
    ma50 = float(close.tail(50).mean()) if len(close) >= 50 else ma20
    above_ma20 = cur >= ma20 if ma20 > 0 else False
    above_ma50 = cur >= ma50 if ma50 > 0 else above_ma20
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
        "above_ma50": bool(above_ma50),
        "close": cur,
        "ma20": ma20,
        "ma50": ma50,
        "volume_ratio20": vol_ratio,
        "last_update": last_update,
    }





def _symbol_flow_metrics_at_offset(symbol: str, cache_dir: str, offset: int = 0) -> Optional[Dict[str, Any]]:
    """Tính metrics như _symbol_flow_metrics nhưng lùi về N phiên trước.

    Dùng để dựng Persistence 10 phiên trực tiếp từ cache lịch sử,
    không phụ thuộc vào file history json có được commit hay không.
    """
    h = _load_history(symbol, cache_dir)
    if h.empty:
        return None
    if offset and offset > 0:
        if len(h) <= offset:
            return None
        h = h.iloc[:len(h) - offset].copy()
    if h.empty or len(h) < 21:
        return None
    close = pd.to_numeric(h["close"], errors="coerce").dropna()
    vol = pd.to_numeric(h["volume"], errors="coerce").fillna(0)
    if len(close) < 21:
        return None
    cur = float(close.iloc[-1])
    ret5 = (cur / float(close.iloc[-6]) - 1.0) * 100.0 if len(close) >= 6 and close.iloc[-6] else 0.0
    ret10 = (cur / float(close.iloc[-11]) - 1.0) * 100.0 if len(close) >= 11 and close.iloc[-11] else ret5
    ret20 = (cur / float(close.iloc[-21]) - 1.0) * 100.0 if len(close) >= 21 and close.iloc[-21] else ret10
    ma20 = float(close.tail(20).mean())
    ma50 = float(close.tail(50).mean()) if len(close) >= 50 else ma20
    above_ma20 = cur >= ma20 if ma20 > 0 else False
    above_ma50 = cur >= ma50 if ma50 > 0 else above_ma20
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
        "above_ma50": bool(above_ma50),
        "close": cur,
        "ma20": ma20,
        "ma50": ma50,
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

def _fmt_symbol_list(items: List[Tuple[str, float]], max_items: int = 3) -> str:
    """Format danh sách mã theo kiểu ngắn gọn cho Telegram."""
    out = []
    for sym, ret in items[:max_items]:
        try:
            out.append(f"{sym} {ret:+.2f}%")
        except Exception:
            out.append(str(sym))
    return ", ".join(out) if out else "-"


def _sector_symbol_leaders(g: pd.DataFrame, max_items: int = 3) -> Tuple[str, str]:
    """Trả về mã mạnh/yếu trong ngành, tránh trùng lặp khi ngành quá ít mã.

    Nếu ngành có dưới 5 mã hợp lệ thì chỉ hiển thị nhóm mạnh/leader;
    nhóm yếu trả về ghi chú để tránh tình trạng cùng một mã vừa mạnh vừa yếu.
    """
    if g is None or g.empty or "Mã" not in g.columns:
        return "-", "-"
    tmp = g.copy()
    tmp["ret5_pct"] = pd.to_numeric(tmp.get("ret5_pct"), errors="coerce")
    tmp = tmp.dropna(subset=["ret5_pct"])
    if tmp.empty:
        return "-", "-"

    top_rows = tmp.sort_values("ret5_pct", ascending=False).head(max_items)
    top = [(str(r["Mã"]).upper(), float(r["ret5_pct"])) for _, r in top_rows.iterrows()]

    # Với ngành quá ít mã, top và bottom sẽ trùng nhau, gây hiểu nhầm.
    if len(tmp) < 5:
        return _fmt_symbol_list(top, max_items), "không đủ mã để tách nhóm yếu"

    top_syms = {sym for sym, _ in top}
    weak_rows = tmp.sort_values("ret5_pct", ascending=True)
    weak: List[Tuple[str, float]] = []
    for _, r in weak_rows.iterrows():
        sym = str(r["Mã"]).upper()
        if sym in top_syms:
            continue
        weak.append((sym, float(r["ret5_pct"])))
        if len(weak) >= max_items:
            break
    return _fmt_symbol_list(top, max_items), _fmt_symbol_list(weak, max_items) if weak else "không đủ mã để tách nhóm yếu"


def _fmt_true_leaders(items: List[Tuple[str, float]], max_items: int = 4) -> str:
    return _fmt_symbol_list(items, max_items) if items else "-"


def _true_leader_symbols(g: pd.DataFrame, max_items: int = 4) -> Tuple[int, str]:
    """Đếm leader thật trong ngành.

    Leader thật = trên MA20 + trên MA50 + 5D dương + volume >= 0.8x TB20.
    Đây là tiêu chí thực chiến, giúp lọc ngành chỉ hồi kỹ thuật.
    """
    if g is None or g.empty or "Mã" not in g.columns:
        return 0, "-"
    tmp = g.copy()
    for c in ["ret5_pct", "volume_ratio20"]:
        tmp[c] = pd.to_numeric(tmp.get(c), errors="coerce")
    tmp["above_ma20"] = tmp.get("above_ma20", False).astype(bool)
    tmp["above_ma50"] = tmp.get("above_ma50", False).astype(bool)
    cond = (
        tmp["above_ma20"]
        & tmp["above_ma50"]
        & (tmp["ret5_pct"] > 0)
        & (tmp["volume_ratio20"].fillna(1.0) >= 0.8)
    )
    leaders = tmp[cond].sort_values("ret5_pct", ascending=False)
    items = [(str(r["Mã"]).upper(), float(r["ret5_pct"])) for _, r in leaders.head(max_items).iterrows()]
    return int(len(leaders)), _fmt_true_leaders(items, max_items)


def _sector_strength_label(score: float, history_days: int = 999) -> str:
    try:
        score = float(score)
    except Exception:
        return "⚪ KHÔNG RÕ"
    if history_days < SECTOR_PERSISTENCE_MIN_DAYS:
        return "🟡 ĐANG TÍCH LŨY LỊCH SỬ"
    if score >= 75:
        return "🟢 LEADER BỀN VỮNG"
    if score >= 60:
        return "🟢 LEADER MỚI NỔI"
    if score >= 45:
        return "🟡 TRUNG TÍNH"
    if score >= 30:
        return "🟠 NHỊP HỒI KỸ THUẬT"
    return "🔴 SUY YẾU KÉO DÀI"


def _load_persistence_history(path: str = SECTOR_PERSISTENCE_HISTORY_PATH) -> Dict[str, Dict[str, Any]]:
    try:
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _save_persistence_history(history: Dict[str, Dict[str, Any]], path: str = SECTOR_PERSISTENCE_HISTORY_PATH) -> None:
    try:
        if not path:
            return
        # Giữ gọn lịch sử để repo không phình.
        keys = sorted(history.keys())[-60:]
        compact = {k: history[k] for k in keys}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(compact, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _history_date_from_update(latest_update: str) -> str:
    dt = _parse_last_update(latest_update)
    if dt:
        return dt.strftime("%Y-%m-%d")
    try:
        return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d")


def _update_sector_persistence_history(
    sector_scores: Dict[str, Dict[str, Any]],
    latest_update: str,
    path: str = SECTOR_PERSISTENCE_HISTORY_PATH,
) -> Dict[str, Dict[str, Any]]:
    history = _load_persistence_history(path)
    d = _history_date_from_update(latest_update)
    ranked = sorted(sector_scores.items(), key=lambda kv: kv[1].get("score", 0), reverse=True)
    top_set = {s for s, _ in ranked[:SECTOR_PERSISTENCE_TOP_N]}
    history[d] = {
        s: {
            "score": r.get("score", 0),
            "rank": idx + 1,
            "top": s in top_set,
        }
        for idx, (s, r) in enumerate(ranked)
    }
    _save_persistence_history(history, path)
    return history




def _metrics_from_loaded_history(symbol: str, h: pd.DataFrame, offset: int = 0) -> Optional[Dict[str, Any]]:
    """Tính metrics từ history đã load sẵn để tránh đọc file lặp 10 lần."""
    if h is None or h.empty:
        return None
    if offset and offset > 0:
        if len(h) <= offset:
            return None
        h = h.iloc[:len(h) - offset].copy()
    if h.empty or len(h) < 21:
        return None
    close = pd.to_numeric(h["close"], errors="coerce").dropna()
    vol = pd.to_numeric(h["volume"], errors="coerce").fillna(0)
    if len(close) < 21:
        return None
    cur = float(close.iloc[-1])
    ret5 = (cur / float(close.iloc[-6]) - 1.0) * 100.0 if len(close) >= 6 and close.iloc[-6] else 0.0
    ret10 = (cur / float(close.iloc[-11]) - 1.0) * 100.0 if len(close) >= 11 and close.iloc[-11] else ret5
    ret20 = (cur / float(close.iloc[-21]) - 1.0) * 100.0 if len(close) >= 21 and close.iloc[-21] else ret10
    ma20 = float(close.tail(20).mean())
    ma50 = float(close.tail(50).mean()) if len(close) >= 50 else ma20
    above_ma20 = cur >= ma20 if ma20 > 0 else False
    above_ma50 = cur >= ma50 if ma50 > 0 else above_ma20
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
        "above_ma50": bool(above_ma50),
        "close": cur,
        "ma20": ma20,
        "ma50": ma50,
        "volume_ratio20": vol_ratio,
        "last_update": last_update,
    }


def _build_sector_persistence_history_from_cache(
    symbols: List[str],
    sector_map: Dict[str, str],
    cache_dir: str,
    lookback: int = SECTOR_PERSISTENCE_LOOKBACK,
) -> Dict[str, Dict[str, Any]]:
    """Dựng lịch sử Top ngành từ cache_stock cho N phiên gần nhất.

    Đọc mỗi file mã đúng 1 lần để an toàn runtime trên GitHub Actions/Render.
    """
    history: Dict[str, Dict[str, Any]] = {}
    loaded: Dict[str, pd.DataFrame] = {}
    for sym in symbols:
        sec = sector_map.get(sym, "UNKNOWN")
        if not sec or str(sec).upper() == "UNKNOWN":
            continue
        h = _load_history(sym, cache_dir)
        if h is not None and not h.empty and len(h) >= 21:
            loaded[sym] = h

    for offset in range(max(1, int(lookback))):
        rows: List[Dict[str, Any]] = []
        for sym, h in loaded.items():
            sec = sector_map.get(sym, "UNKNOWN")
            m = _metrics_from_loaded_history(sym, h, offset=offset)
            if not m:
                continue
            m["Sector"] = sec
            rows.append(m)
        if not rows:
            continue
        day_df = pd.DataFrame(rows)
        day_scores: Dict[str, Dict[str, Any]] = {}
        for sec, g in day_df.groupby("Sector"):
            if len(g) < 2:
                continue
            day_scores[str(sec)] = _score_sector(g)
        if not day_scores:
            continue
        last_updates = [_safe_str(x, "") for x in day_df.get("last_update", pd.Series(dtype=str)).dropna().tolist()]
        latest_update = ""
        if last_updates:
            parsed = [(_parse_last_update(x), x) for x in last_updates]
            parsed = [(d, x) for d, x in parsed if d is not None]
            latest_update = max(parsed, key=lambda t: t[0])[1] if parsed else last_updates[-1]
        dkey = _history_date_from_update(latest_update)
        ranked_day = sorted(day_scores.items(), key=lambda kv: kv[1].get("score", 0), reverse=True)
        top_set = {s for s, _ in ranked_day[:SECTOR_PERSISTENCE_TOP_N]}
        history[dkey] = {
            s: {"score": r.get("score", 0), "rank": idx + 1, "top": s in top_set}
            for idx, (s, r) in enumerate(ranked_day)
        }
    return history


def _apply_sector_persistence_and_strength(
    sector_scores: Dict[str, Dict[str, Any]],
    history: Dict[str, Dict[str, Any]],
) -> None:
    dates = sorted(history.keys())[-SECTOR_PERSISTENCE_LOOKBACK:]
    denom = len(dates)
    if denom <= 0:
        denom = 1
    for sec, r in sector_scores.items():
        top_count = 0
        for d in dates:
            info = history.get(d, {}).get(sec, {})
            if isinstance(info, dict) and bool(info.get("top")):
                top_count += 1
        raw_persistence_score = round(top_count / denom * 100.0, 1) if denom else 0.0
        # Nếu lịch sử chưa đủ tối thiểu, không được kết luận "bền vững".
        # Dùng mức trung tính 50 để tránh một ngày đầu tiên làm ngành bị thổi điểm quá mạnh.
        persistence_score = raw_persistence_score if denom >= SECTOR_PERSISTENCE_MIN_DAYS else 50.0
        leader_count = int(r.get("true_leader_count", 0) or 0)
        members = max(int(r.get("members", 0) or 0), 1)
        leader_score = round(min(100.0, (leader_count / max(1, min(members, 5))) * 100.0), 1)
        flow_score = float(r.get("score", 0) or 0)
        strength = round(0.30 * flow_score + 0.40 * persistence_score + 0.30 * leader_score, 1)
        r["persistence_count"] = top_count
        r["persistence_denominator"] = denom
        r["persistence_score"] = persistence_score
        r["raw_persistence_score"] = raw_persistence_score
        r["persistence_min_days"] = SECTOR_PERSISTENCE_MIN_DAYS
        r["leader_score"] = leader_score
        r["sector_strength_score"] = strength
        r["sector_strength_label"] = _sector_strength_label(strength, denom)

def _flow_trend_status(score: float) -> str:
    """Trạng thái dòng tiền 5 cấp, dùng ngôn ngữ dễ hiểu cho Telegram.

    Đây là diễn giải theo score tương đối giá + breadth + volume,
    không phải kết luận mua/bán thật của tổ chức.
    """
    try:
        score = float(score)
    except Exception:
        return "⚪ KHÔNG RÕ"
    if score >= 70:
        return "🟢 TIỀN VÀO MẠNH"
    if score >= 55:
        return "🟢 TIỀN ĐANG VÀO"
    if score >= 45:
        return "🟡 TIỀN THĂM DÒ / TRUNG TÍNH"
    if score >= 25:
        return "🟠 TIỀN SUY YẾU"
    return "🔴 TIỀN ĐANG RÚT RA / KÉM LAN TỎA"


def _score_sector(g: pd.DataFrame) -> Dict[str, Any]:
    avg_ret5 = float(pd.to_numeric(g["ret5_pct"], errors="coerce").mean())
    avg_ret10 = float(pd.to_numeric(g["ret10_pct"], errors="coerce").mean())
    avg_ret20 = float(pd.to_numeric(g["ret20_pct"], errors="coerce").mean())
    breadth = float(pd.to_numeric(g["above_ma20"], errors="coerce").mean() * 100.0)
    vr = pd.to_numeric(g["volume_ratio20"], errors="coerce").dropna()
    avg_vr = float(vr.mean()) if len(vr) else 1.0
    leader_symbols, weak_symbols = _sector_symbol_leaders(g, max_items=3)
    true_leader_count, true_leader_symbols = _true_leader_symbols(g, max_items=4)

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
        "flow_status": _flow_trend_status(score),
        "members": int(len(g)),
        "avg_ret5_pct": round(avg_ret5, 2),
        "avg_ret10_pct": round(avg_ret10, 2),
        "avg_ret20_pct": round(avg_ret20, 2),
        "above_ma20_pct": round(breadth, 1),
        "avg_volume_ratio20": round(avg_vr, 2),
        "leader_symbols": leader_symbols,
        "weak_symbols": weak_symbols,
        "true_leader_count": true_leader_count,
        "true_leader_symbols": true_leader_symbols,
        "persistence_count": 0,
        "persistence_denominator": 0,
        "persistence_score": 0.0,
        "leader_score": 0.0,
        "sector_strength_score": score,
        "sector_strength_label": _sector_strength_label(score),
    }


def _fmt_sector_row(sec: str, r: Dict[str, Any]) -> str:
    # Giữ format gọn nhưng đủ phân biệt: hôm nay mạnh vs leader bền vững.
    pc = r.get("persistence_count", 0)
    pdn = r.get("persistence_denominator", 0)
    strength = r.get("sector_strength_score", r.get("score", ""))
    strength_label = r.get("sector_strength_label", "")
    true_count = r.get("true_leader_count", 0)
    true_syms = r.get("true_leader_symbols", "-")
    return (
        f"- {sec}: Flow {r.get('score')}/100 | {r.get('flow_status', '')} | Strength {strength}/100 {strength_label}\n"
        f"  5D {r.get('avg_ret5_pct')}% | Vol {r.get('avg_volume_ratio20')}x | Bền vững: {pc}/{pdn} phiên Top {SECTOR_PERSISTENCE_TOP_N} | Leader thật: {true_count} ({true_syms})\n"
        f"  Mã mạnh: {r.get('leader_symbols', '-')} | Mã yếu: {r.get('weak_symbols', '-')}"
    )

def _fmt_position_flow_note(sym: str, sec: str, ss: Dict[str, Any]) -> str:
    return (
        f"- {sym}: {sec} | Flow {ss.get('score')}/100 | "
        f"Strength {ss.get('sector_strength_score', '')}/100 {ss.get('sector_strength_label', '')} | "
        f"{ss.get('flow_status', ss.get('label', ''))}"
    )


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

    # PHASE 18.0 — Sector Persistence & True Leader Detection.
    # Dựng độ bền ngành trực tiếp từ cache_stock 10 phiên gần nhất, không cần chờ tích lũy file JSON.
    history = _build_sector_persistence_history_from_cache(symbols, sector_map, cache_dir, SECTOR_PERSISTENCE_LOOKBACK)
    if not history:
        history = _update_sector_persistence_history(sector_scores, latest_update)
    else:
        # Lưu thêm snapshot để tiện kiểm tra/debug, nhưng không phụ thuộc vào file này.
        try:
            _save_persistence_history(history)
        except Exception:
            pass
    _apply_sector_persistence_and_strength(sector_scores, history)

    ranked = sorted(sector_scores.items(), key=lambda kv: kv[1].get("sector_strength_score", kv[1]["score"]), reverse=True)
    weak = sorted(sector_scores.items(), key=lambda kv: kv[1].get("sector_strength_score", kv[1]["score"]))
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
        notes=f"Score Flow là dòng tiền tương đối theo giá + breadth + volume; Strength kết hợp Flow hôm nay + độ bền Top ngành + số leader thật. Không phải kết luận tiền lớn mua/bán thật. Luôn dùng dữ liệu gần nhất có sẵn; xem Last Updated và trạng thái dữ liệu. Tính từ {len(df)} mã hợp lệ / {len(symbols)} mã cache; {len(sector_scores)} ngành đủ dữ liệu.",
        recommendation_lines="\n".join(rec_lines),
    )
