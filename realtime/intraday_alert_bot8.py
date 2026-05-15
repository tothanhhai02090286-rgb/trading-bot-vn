# -*- coding: utf-8 -*-
"""
intraday_alert_bot_v182_unified_execution_recommendation.py

V18.2 UNIFIED EXECUTION RECOMMENDATION ENGINE FOR RENDER

Bản hợp nhất:
- V18.1 = Execution Quality Filter
- V18.2 = Recommendation Engine + Telegram Decision Compression

Vai trò:
- V18.2 chỉ canh timing realtime.
- KHÔNG tự quyết định mua lớn.
- KHÔNG override V15.5 / V16 / V17.1.
- Chỉ đọc intraday_watchlist_v17.csv do V17.1 tạo.
- Obey upstream risk:
  + Final Decision
  + Nhóm realtime
  + Decision Mode
  + Meta Allocation %
  + Meta Exposure
  + Regime Strength
  + Equity State

Mục tiêu Telegram:
- Luôn có KẾT LUẬN CUỐI:
  + KHÔNG VÀO
  + WATCH
  + TEST NHỎ
  + BUY NHỎ
  + BUY CÓ KIỂM SOÁT
- Có Confidence: HIGH / MEDIUM / LOW
- Có 3 lý do chính dễ hiểu.
"""

from __future__ import annotations

import os
import time
import json
from datetime import datetime, time as dtime
from typing import Optional, Dict, Any, List, Tuple, Set

import pandas as pd
import requests

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None


WATCHLIST_PATH = os.getenv("INTRADAY_WATCHLIST_PATH", "../intraday_watchlist_v17.csv")
RAW_URL = os.getenv("GITHUB_RAW_WATCHLIST_URL", "").strip() or os.getenv("RAW_URL", "").strip()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()

CHECK_INTERVAL_SEC = int(os.getenv("CHECK_INTERVAL_SEC", "120"))
MARKET_START = os.getenv("MARKET_START", "09:00")
MARKET_END = os.getenv("MARKET_END", "14:50")
TZ_NAME = os.getenv("TZ", "Asia/Ho_Chi_Minh")
STATE_PATH = os.getenv("INTRADAY_ALERT_STATE", "intraday_alert_state.json")

MAX_SYMBOLS_REALTIME = int(os.getenv("MAX_SYMBOLS_REALTIME", "5"))
SCAN_ONE_SYMBOL_PER_LOOP = os.getenv("SCAN_ONE_SYMBOL_PER_LOOP", "1").strip() == "1"

V18_OBEY_UPSTREAM_RISK = os.getenv("V18_OBEY_UPSTREAM_RISK", "1").strip() == "1"
V182_ENABLE_EXECUTION = os.getenv("V182_ENABLE_EXECUTION", "1").strip() == "1"

V182_MIN_VOLUME_RATIO = float(os.getenv("V182_MIN_VOLUME_RATIO", "1.2"))
V182_STRONG_VOLUME_RATIO = float(os.getenv("V182_STRONG_VOLUME_RATIO", "1.8"))
V182_BREAKOUT_BUFFER_PCT = float(os.getenv("V182_BREAKOUT_BUFFER_PCT", "0.3"))
V182_VWAP_TOLERANCE_PCT = float(os.getenv("V182_VWAP_TOLERANCE_PCT", "0.2"))
V182_PULLBACK_TOLERANCE_PCT = float(os.getenv("V182_PULLBACK_TOLERANCE_PCT", "0.7"))

OPENING_TRAP_END = os.getenv("OPENING_TRAP_END", "09:20")
END_SESSION_CAUTION_START = os.getenv("END_SESSION_CAUTION_START", "14:20")
LUNCH_START = os.getenv("LUNCH_START", "11:30")
LUNCH_END = os.getenv("LUNCH_END", "13:00")

MAX_INTRADAY_EXTENDED_PCT = float(os.getenv("MAX_INTRADAY_EXTENDED_PCT", "3.0"))
MAX_DISTANCE_ABOVE_VWAP_PCT = float(os.getenv("MAX_DISTANCE_ABOVE_VWAP_PCT", "2.0"))
FAKE_BREAKOUT_MIN_HOLD_BARS = int(os.getenv("FAKE_BREAKOUT_MIN_HOLD_BARS", "2"))

MOMENTUM_FROM_REF_PCT = float(os.getenv("MOMENTUM_FROM_REF_PCT", "1.0"))
WEAKNESS_FROM_REF_PCT = float(os.getenv("WEAKNESS_FROM_REF_PCT", "-1.5"))
TOO_FAR_ABOVE_BUY_ZONE_PCT = float(os.getenv("TOO_FAR_ABOVE_BUY_ZONE_PCT", "2.0"))

BASE_COOLDOWN_MIN = int(os.getenv("V18_ALERT_COOLDOWN_MIN", "30"))
STRONG_SIGNAL_COOLDOWN_MIN = int(os.getenv("STRONG_SIGNAL_COOLDOWN_MIN", "15"))
WEAK_SIGNAL_COOLDOWN_MIN = int(os.getenv("WEAK_SIGNAL_COOLDOWN_MIN", "45"))

_LAST_SYMBOLS: Set[str] = set()
_SCAN_INDEX = 0


def _now():
    if ZoneInfo:
        return datetime.now(ZoneInfo(TZ_NAME))
    return datetime.now()


def _parse_hhmm(s: str) -> dtime:
    hh, mm = s.split(":")[:2]
    return dtime(int(hh), int(mm))


def _time_between(start: str, end: str) -> bool:
    t = _now().time()
    return _parse_hhmm(start) <= t <= _parse_hhmm(end)


def in_market_time() -> bool:
    n = _now()
    if n.weekday() >= 5:
        return False

    t = n.time()
    lunch_start = _parse_hhmm(LUNCH_START)
    lunch_end = _parse_hhmm(LUNCH_END)

    return (
        _parse_hhmm(MARKET_START) <= t <= _parse_hhmm(MARKET_END)
        and not (lunch_start <= t < lunch_end)
    )


def is_opening_trap_window() -> bool:
    return _time_between(MARKET_START, OPENING_TRAP_END)


def is_end_session_window() -> bool:
    return _time_between(END_SESSION_CAUTION_START, MARKET_END)


def send_telegram(text: str) -> bool:
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        print("WARN: missing TELEGRAM_TOKEN/TELEGRAM_CHAT_ID", flush=True)
        return False

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        print(f"TELEGRAM STATUS: {resp.status_code} {resp.text[:200]}", flush=True)
        return resp.status_code == 200
    except Exception as e:
        print("WARN telegram exception:", repr(e), flush=True)
        return False


def load_state() -> Dict[str, Any]:
    try:
        if os.path.exists(STATE_PATH):
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("date") == _now().strftime("%Y-%m-%d"):
                return data
    except Exception as e:
        print("WARN load state:", repr(e), flush=True)

    return {"date": _now().strftime("%Y-%m-%d"), "sent": [], "last_alert_ts": {}}


def save_state_obj(state: Dict[str, Any]):
    try:
        state["date"] = _now().strftime("%Y-%m-%d")
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("WARN save state:", repr(e), flush=True)


def _num(x) -> Optional[float]:
    try:
        if x is None:
            return None
        if isinstance(x, str):
            x = x.replace("%", "").replace(",", ".").strip()
            if x == "":
                return None
        v = pd.to_numeric(pd.Series([x]), errors="coerce").iloc[0]
        if pd.isna(v):
            return None
        return float(v)
    except Exception:
        return None


def normalize_text(x: Any) -> str:
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass
    return str(x).strip().upper()


def normalize_vn_price(price) -> Optional[float]:
    p = _num(price)
    if p is None:
        return None
    if p > 1000:
        p = p / 1000
    return round(float(p), 2)


def _find_col(df: pd.DataFrame, names: List[str]) -> Optional[str]:
    lower_map = {str(c).lower(): c for c in df.columns}
    for name in names:
        if name in df.columns:
            return name
        if name.lower() in lower_map:
            return lower_map[name.lower()]
    return None


def _row_float(row: pd.Series, col: str, price_mode: bool = True) -> Optional[float]:
    if col not in row:
        return None
    return normalize_vn_price(row[col]) if price_mode else _num(row[col])


def get_upstream_fields(row: pd.Series) -> Dict[str, Any]:
    return {
        "final_decision": normalize_text(row.get("Final Decision", row.get("Hành động", ""))),
        "realtime_group": normalize_text(row.get("Nhóm realtime", "")),
        "decision_mode": normalize_text(row.get("Decision Mode", "")),
        "regime_strength": normalize_text(row.get("Regime Strength", "")),
        "equity_state": normalize_text(row.get("Equity State", "")),
        "priority": normalize_text(row.get("Ưu tiên", "")),
        "meta_alloc": _num(row.get("Meta Allocation %", 0.0)) or 0.0,
        "meta_exposure": _num(row.get("Meta Exposure", 0.0)) or 0.0,
    }


def upstream_allows_alert(row: pd.Series) -> Tuple[bool, str]:
    f = get_upstream_fields(row)

    if not V18_OBEY_UPSTREAM_RISK:
        return True, "Upstream gate đang tắt"

    if f["final_decision"] in ["AVOID", "BỎ QUA", "REDUCE", "GIẢM"]:
        return False, "V17.1 không cho realtime entry"
    if f["realtime_group"] in ["BỎ QUA", "AVOID"]:
        return False, "Nhóm realtime bị loại"
    if f["decision_mode"] == "CASH MODE":
        return False, "V16 CASH MODE"
    if f["meta_alloc"] <= 0.01:
        return False, "Meta allocation gần 0"

    return True, "Upstream cho phép theo dõi"


def max_action_from_upstream(row: pd.Series) -> str:
    f = get_upstream_fields(row)

    if f["decision_mode"] == "CASH MODE":
        return "KHÔNG VÀO"
    if f["final_decision"] in ["AVOID", "BỎ QUA", "REDUCE", "GIẢM"]:
        return "KHÔNG VÀO"
    if f["decision_mode"] == "ĐÁNH RẤT NHỎ":
        return "TEST NHỎ"
    if f["decision_mode"] == "ĐÁNH NHỎ":
        return "BUY NHỎ"
    if "RISK OFF" in f["regime_strength"]:
        return "TEST NHỎ"
    if f["final_decision"] == "WATCHLIST":
        return "TEST NHỎ" if f["meta_alloc"] >= 5 else "WATCH"
    if f["final_decision"] == "BUY NOW":
        return "BUY CÓ KIỂM SOÁT" if f["meta_alloc"] >= 8 else "BUY NHỎ"

    return "WATCH"


def cap_recommendation(rec: str, max_action: str) -> str:
    rank = {
        "KHÔNG VÀO": 0,
        "WATCH": 1,
        "TEST NHỎ": 2,
        "BUY NHỎ": 3,
        "BUY CÓ KIỂM SOÁT": 4,
    }
    reverse = {v: k for k, v in rank.items()}
    return reverse[min(rank.get(rec, 1), rank.get(max_action, 1))]


def normalize_watchlist(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()

    if "Mã" not in out.columns:
        for col in ["Ma", "Symbol", "Ticker", "ticker", "Mã CP"]:
            if col in out.columns:
                out["Mã"] = out[col]
                break

    if "Mã" not in out.columns:
        print("WARN: watchlist missing Mã column", flush=True)
        return pd.DataFrame()

    out["Mã"] = out["Mã"].astype(str).str.upper().str.strip()
    out = out[out["Mã"].notna() & (out["Mã"] != "") & (out["Mã"] != "NAN")].copy()

    if "Final Decision" in out.columns:
        out = out[~out["Final Decision"].astype(str).str.upper().str.contains("AVOID|BỎ QUA|REDUCE|GIẢM", na=False)].copy()

    if "Nhóm realtime" in out.columns:
        mask = out["Nhóm realtime"].astype(str).str.upper().str.contains("MUA|THEO|WATCH", na=False)
        out = out[mask].copy()

    return out.drop_duplicates(subset=["Mã"], keep="first").reset_index(drop=True)


def select_top_watchlist(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()
    if "Meta Allocation %" not in out.columns:
        out["Meta Allocation %"] = 0

    out["Meta Allocation %"] = pd.to_numeric(
        out["Meta Allocation %"],
        errors="coerce"
    ).fillna(0)
    out["priority_group"] = 0

    if "Final Decision" in out.columns:
        d = out["Final Decision"].astype(str).str.upper()
        out.loc[d.str.contains("BUY NOW|MUA", na=False), "priority_group"] += 100
        out.loc[d.str.contains("WATCHLIST|WATCH|THEO", na=False), "priority_group"] += 40

    if "Nhóm realtime" in out.columns:
        g = out["Nhóm realtime"].astype(str).str.upper()
        out.loc[g.str.contains("MUA", na=False), "priority_group"] += 50
        out.loc[g.str.contains("THEO", na=False), "priority_group"] += 30
        out.loc[g.str.contains("WATCH", na=False), "priority_group"] += 10

    if "Ưu tiên" in out.columns:
        p = out["Ưu tiên"].astype(str).str.upper()
        out.loc[p.str.contains("CAO", na=False), "priority_group"] += 30
        out.loc[p.str.contains("VỪA", na=False), "priority_group"] += 20
        out.loc[p.str.contains("THẤP", na=False), "priority_group"] += 10

    out["realtime_score"] = out["priority_group"] + out["Meta Allocation %"] * 5
    out = out.sort_values("realtime_score", ascending=False).head(MAX_SYMBOLS_REALTIME).reset_index(drop=True)

    print(f"TOP REALTIME selected: {len(out)} | {out['Mã'].tolist() if 'Mã' in out.columns else []}", flush=True)
    return out


def _notify_watchlist_changes(df: pd.DataFrame):
    global _LAST_SYMBOLS

    symbols = set(df["Mã"].astype(str).str.upper().str.strip()) if not df.empty and "Mã" in df.columns else set()

    if not _LAST_SYMBOLS:
        _LAST_SYMBOLS = symbols
        print(f"WATCHLIST INIT symbols={len(symbols)} tickers={sorted(symbols)}", flush=True)
        return

    added = sorted(symbols - _LAST_SYMBOLS)
    removed = sorted(_LAST_SYMBOLS - symbols)

    if added:
        send_telegram("🆕 <b>Watchlist realtime có mã mới</b>\n" + ", ".join(added))
        print("WATCHLIST ADDED:", added, flush=True)
    if removed:
        print("WATCHLIST REMOVED:", removed, flush=True)

    _LAST_SYMBOLS = symbols


def load_watchlist() -> pd.DataFrame:
    if RAW_URL:
        headers = {"Cache-Control": "no-cache", "Pragma": "no-cache"}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

        try:
            url = RAW_URL
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}t={int(time.time())}"
            r = requests.get(url, headers=headers, timeout=30)
            r.raise_for_status()

            from io import StringIO
            df = pd.read_csv(StringIO(r.text))
            df = normalize_watchlist(df)

            print(
                f"WATCHLIST loaded from RAW_URL: rows={len(df)} | "
                f"tickers={df['Mã'].tolist() if not df.empty and 'Mã' in df.columns else []} | "
                f"time={_now().strftime('%H:%M:%S')}",
                flush=True,
            )
            _notify_watchlist_changes(df)
            return df
        except Exception as e:
            print("WARN raw watchlist, fallback local:", repr(e), flush=True)

    candidates = [
        WATCHLIST_PATH,
        "intraday_watchlist_v17.csv",
        "../intraday_watchlist_v17.csv",
        "intraday_watchlist.csv",
        "../intraday_watchlist.csv",
    ]

    for path in candidates:
        if os.path.exists(path):
            df = normalize_watchlist(pd.read_csv(path))
            print(f"WATCHLIST loaded local: {path} | rows={len(df)}", flush=True)
            _notify_watchlist_changes(df)
            return df

    print("WARN: watchlist not found", flush=True)
    return pd.DataFrame()


def get_intraday_bars_vnstock(symbol: str) -> pd.DataFrame:
    try:
        from vnstock import Vnstock
        stock = Vnstock().stock(symbol=symbol, source="VCI")
        q = getattr(stock, "quote", None)
        if q is not None and hasattr(q, "intraday"):
            df = q.intraday(page_size=200)
            if df is not None and not df.empty:
                return df.copy()
    except Exception as e:
        print(f"WARN vnstock intraday bars {symbol}: {repr(e)}", flush=True)
    return pd.DataFrame()


def normalize_intraday_bars(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()
    price_col = _find_col(out, ["price", "match_price", "last_price", "close", "Close"])
    vol_col = _find_col(out, ["volume", "match_volume", "vol", "Volume"])

    if price_col is None:
        return pd.DataFrame()

    out["price_norm"] = pd.to_numeric(out[price_col], errors="coerce").apply(normalize_vn_price)
    out["volume_norm"] = pd.to_numeric(out[vol_col], errors="coerce").fillna(0) if vol_col else 0
    out = out[out["price_norm"].notna()].copy()
    return out.reset_index(drop=True)


def get_current_price_vnstock(symbol: str) -> Optional[float]:
    try:
        df = normalize_intraday_bars(get_intraday_bars_vnstock(symbol))
        if not df.empty:
            return normalize_vn_price(df["price_norm"].iloc[-1])

        from vnstock import Vnstock
        stock = Vnstock().stock(symbol=symbol, source="VCI")
        q = getattr(stock, "quote", None)
        if q is not None and hasattr(q, "history"):
            hist = q.history(period="1D")
            if hist is not None and not hist.empty:
                for col in ["close", "Close"]:
                    if col in hist.columns:
                        v = pd.to_numeric(hist[col], errors="coerce").dropna()
                        if len(v):
                            return normalize_vn_price(v.iloc[-1])
    except Exception as e:
        print(f"WARN vnstock price {symbol}: {repr(e)}", flush=True)
    return None


def get_current_price_yfinance(symbol: str) -> Optional[float]:
    try:
        import yfinance as yf
        for yf_symbol in [f"{symbol}.VN", f"{symbol}.HM", f"{symbol}.HN"]:
            data = yf.download(
                yf_symbol,
                period="5d",
                interval="1d",
                progress=False,
                auto_adjust=False,
                threads=False,
            )
            if data is not None and not data.empty and "Close" in data.columns:
                close = data["Close"]
                if isinstance(close, pd.DataFrame):
                    close = close.iloc[:, 0]
                v = pd.to_numeric(close, errors="coerce").dropna()
                if len(v):
                    return normalize_vn_price(v.iloc[-1])
    except Exception as e:
        print(f"WARN yfinance price {symbol}: {repr(e)}", flush=True)
    return None


def get_current_price(symbol: str) -> Optional[float]:
    symbol = str(symbol).strip().upper()
    if not symbol:
        return None
    p = get_current_price_vnstock(symbol)
    if p is not None:
        return normalize_vn_price(p)
    return normalize_vn_price(get_current_price_yfinance(symbol))


def build_intraday_snapshot(symbol: str) -> Dict[str, Any]:
    bars = normalize_intraday_bars(get_intraday_bars_vnstock(symbol))
    snap: Dict[str, Any] = {
        "bars_ok": False,
        "current_price": None,
        "vwap": None,
        "prev_price": None,
        "volume_ratio": None,
        "session_high_prev": None,
        "session_low": None,
        "bars_count": 0,
        "last_prices": [],
        "last_volumes": [],
    }

    if bars.empty:
        snap["current_price"] = normalize_vn_price(get_current_price(symbol))
        return snap

    px = pd.to_numeric(bars["price_norm"], errors="coerce").apply(normalize_vn_price)
    vol = pd.to_numeric(bars["volume_norm"], errors="coerce").fillna(0)

    price = normalize_vn_price(px.iloc[-1])
    prev = normalize_vn_price(px.iloc[-2]) if len(px) >= 2 else None

    total_vol = float(vol.sum())
    vwap = normalize_vn_price((px * vol).sum() / total_vol) if total_vol > 0 else normalize_vn_price(px.mean())

    avg_vol = float(vol.tail(20).mean()) if len(vol.tail(20)) else 0
    last_vol = float(vol.iloc[-1]) if len(vol) else 0
    volume_ratio = (last_vol / avg_vol) if avg_vol > 0 else None

    prev_prices = px.iloc[:-1] if len(px) >= 2 else px

    snap.update({
        "bars_ok": True,
        "current_price": price,
        "vwap": vwap,
        "prev_price": prev,
        "volume_ratio": volume_ratio,
        "session_high_prev": normalize_vn_price(prev_prices.max()) if len(prev_prices) else price,
        "session_low": normalize_vn_price(px.min()) if len(px) else price,
        "bars_count": len(bars),
        "last_prices": [normalize_vn_price(x) for x in px.tail(5).tolist()],
        "last_volumes": [float(x) for x in vol.tail(5).tolist()],
    })
    return snap


def get_reference_price(row: pd.Series, current_price: Optional[float]) -> Optional[float]:
    ref = _row_float(row, "Giá tham chiếu", price_mode=True)
    return ref if ref is not None else current_price


def get_buy_zone(row: pd.Series, current_price: Optional[float]) -> Tuple[Optional[float], Optional[float]]:
    low_abs = _row_float(row, "Buy zone thấp", price_mode=True)
    high_abs = _row_float(row, "Buy zone cao", price_mode=True)
    if low_abs is not None and high_abs is not None:
        return low_abs, high_abs

    low_pct = _row_float(row, "Buy zone thấp %", price_mode=False)
    high_pct = _row_float(row, "Buy zone cao %", price_mode=False)
    ref = get_reference_price(row, current_price)
    if ref is not None and low_pct is not None and high_pct is not None:
        return normalize_vn_price(ref * (1 + low_pct / 100.0)), normalize_vn_price(ref * (1 + high_pct / 100.0))

    return None, None


def get_stoploss(row: pd.Series, current_price: Optional[float]) -> Optional[float]:
    stop_abs = _row_float(row, "Stoploss tham khảo", price_mode=True)
    if stop_abs is not None:
        return stop_abs

    stop_pct = _row_float(row, "Stoploss tham khảo %", price_mode=False)
    ref = get_reference_price(row, current_price)
    if ref is not None and stop_pct is not None:
        return normalize_vn_price(ref * (1 + stop_pct / 100.0))
    return None


def detect_legacy_signal(row: pd.Series, price: float) -> Optional[str]:
    price = normalize_vn_price(price)
    if price is None:
        return None

    ref = get_reference_price(row, price)
    low, high = get_buy_zone(row, price)
    stop = get_stoploss(row, price)

    if stop is not None and price <= stop:
        return "🔴 THỦNG STOPLOSS"
    if low is not None and high is not None and low <= price <= high:
        return "🟢 PULLBACK VÙNG MUA"
    if high is not None and price > high * (1 + TOO_FAR_ABOVE_BUY_ZONE_PCT / 100):
        return "⚠️ VƯỢT BUY ZONE QUÁ XA"

    if ref is not None and ref > 0:
        intraday_ret = (price / ref - 1.0) * 100.0
        if intraday_ret >= MOMENTUM_FROM_REF_PCT:
            return "🟡 INTRADAY MOMENTUM"
        if intraday_ret <= WEAKNESS_FROM_REF_PCT:
            return "⚠️ INTRADAY WEAKNESS"

    return None


def detect_raw_signal(row: pd.Series, snap: Dict[str, Any]) -> Optional[str]:
    price = normalize_vn_price(snap.get("current_price"))
    if price is None:
        return None

    if not V182_ENABLE_EXECUTION or not snap.get("bars_ok"):
        return detect_legacy_signal(row, float(price))

    prev_price = normalize_vn_price(snap.get("prev_price"))
    vwap = normalize_vn_price(snap.get("vwap"))
    volume_ratio = snap.get("volume_ratio")
    session_high_prev = normalize_vn_price(snap.get("session_high_prev"))

    ref = get_reference_price(row, price)
    low, high = get_buy_zone(row, price)
    stop = get_stoploss(row, price)

    if stop is not None and price <= stop:
        return "🔴 THỦNG STOPLOSS"
    if vwap is None:
        return detect_legacy_signal(row, price)

    vol_ok = volume_ratio is not None and volume_ratio >= V182_MIN_VOLUME_RATIO

    vwap_reclaim = (
        prev_price is not None
        and prev_price <= vwap
        and price >= vwap * (1 + V182_VWAP_TOLERANCE_PCT / 100)
    )
    if vwap_reclaim and vol_ok:
        return "🔥 VWAP RECLAIM + VOLUME"

    breakout_levels = []
    for lv in [session_high_prev, high, ref]:
        if lv is not None:
            breakout_levels.append(float(lv))

    if breakout_levels:
        breakout_level = max(breakout_levels)
        breakout_price = breakout_level * (1 + V182_BREAKOUT_BUFFER_PCT / 100)
        if price >= breakout_price and price >= vwap and vol_ok:
            return "🚀 BREAKOUT XÁC NHẬN"
        if price >= breakout_price and price < vwap:
            return "⚠️ FALSE BREAKOUT RISK"

    if low is not None and high is not None:
        if low <= price <= high and price >= vwap * (1 - V182_PULLBACK_TOLERANCE_PCT / 100):
            return "🟢 PULLBACK VÙNG MUA"

    legacy = detect_legacy_signal(row, price)
    if legacy and price >= vwap * (1 - V182_VWAP_TOLERANCE_PCT / 100):
        return f"{legacy} + VWAP OK"

    return None


def execution_quality_filter(row: pd.Series, snap: Dict[str, Any], raw_signal: str) -> Dict[str, Any]:
    price = normalize_vn_price(snap.get("current_price"))
    vwap = normalize_vn_price(snap.get("vwap"))
    volume_ratio = snap.get("volume_ratio")
    session_high_prev = normalize_vn_price(snap.get("session_high_prev"))

    score = 50
    good_reasons: List[str] = []
    bad_reasons: List[str] = []
    warn_reasons: List[str] = []

    if price is None:
        return {
            "passed": False,
            "quality_label": "YẾU",
            "quality_score": 0,
            "good_reasons": [],
            "bad_reasons": ["Không có giá realtime"],
            "warn_reasons": [],
            "cooldown_min": WEAK_SIGNAL_COOLDOWN_MIN,
        }

    ref = get_reference_price(row, price)
    low, high = get_buy_zone(row, price)

    if is_opening_trap_window():
        warn_reasons.append("Đang trong vùng dễ bẫy đầu phiên")
        score -= 20
    if is_end_session_window():
        warn_reasons.append("Cuối phiên, dễ FOMO hoặc kéo xả")
        score -= 15

    if volume_ratio is None:
        warn_reasons.append("Không có volume ratio")
        score -= 10
    elif volume_ratio < V182_MIN_VOLUME_RATIO:
        bad_reasons.append("Volume yếu")
        score -= 15
    elif volume_ratio >= V182_STRONG_VOLUME_RATIO:
        good_reasons.append("Volume mạnh")
        score += 15
    else:
        good_reasons.append("Volume chấp nhận được")
        score += 5

    if vwap is not None and vwap > 0:
        dist = (price / vwap - 1.0) * 100
        if dist < -V182_VWAP_TOLERANCE_PCT:
            bad_reasons.append("Giá dưới VWAP")
            score -= 20
        elif abs(dist) <= MAX_DISTANCE_ABOVE_VWAP_PCT:
            good_reasons.append("Giá không quá xa VWAP")
        if dist > MAX_DISTANCE_ABOVE_VWAP_PCT:
            warn_reasons.append("Giá xa VWAP, dễ FOMO")
            score -= 15

    if ref is not None and ref > 0:
        intraday_ret = (price / ref - 1.0) * 100
        if intraday_ret > MAX_INTRADAY_EXTENDED_PCT:
            warn_reasons.append("Tăng quá nóng intraday")
            score -= 20
        if intraday_ret < WEAKNESS_FROM_REF_PCT:
            bad_reasons.append("Yếu hơn giá tham chiếu")
            score -= 15

    if "BREAKOUT" in raw_signal.upper() and session_high_prev is not None:
        recent = [x for x in snap.get("last_prices", []) if x is not None]
        hold_count = sum(1 for x in recent[-FAKE_BREAKOUT_MIN_HOLD_BARS:] if x >= session_high_prev)
        if hold_count < FAKE_BREAKOUT_MIN_HOLD_BARS:
            bad_reasons.append("Breakout chưa giữ được giá")
            score -= 25
        else:
            good_reasons.append("Breakout giữ được giá")

    if "PULLBACK" in raw_signal.upper() and low is not None and high is not None:
        if low <= price <= high:
            good_reasons.append("Giá nằm trong vùng mua")
            score += 10
        else:
            warn_reasons.append("Pullback chưa nằm chuẩn vùng mua")
            score -= 10

    if "FALSE BREAKOUT" in raw_signal.upper():
        bad_reasons.append("Có rủi ro breakout giả")
        score -= 30

    if "STOPLOSS" in raw_signal.upper():
        bad_reasons.append("Thủng stoploss tham khảo")
        score = min(score, 20)

    score = max(0, min(100, score))

    if score >= 80:
        quality_label = "MẠNH"
        cooldown = STRONG_SIGNAL_COOLDOWN_MIN
        passed = True
    elif score >= 65:
        quality_label = "KHÁ"
        cooldown = BASE_COOLDOWN_MIN
        passed = True
    elif score >= 45:
        quality_label = "TRUNG TÍNH"
        cooldown = BASE_COOLDOWN_MIN
        passed = True
    else:
        quality_label = "YẾU"
        cooldown = WEAK_SIGNAL_COOLDOWN_MIN
        passed = False

    return {
        "passed": passed,
        "quality_label": quality_label,
        "quality_score": score,
        "good_reasons": good_reasons,
        "bad_reasons": bad_reasons,
        "warn_reasons": warn_reasons,
        "cooldown_min": cooldown,
    }


def base_recommendation_from_quality(raw_signal: str, quality: Dict[str, Any]) -> str:
    q = quality["quality_label"]
    signal_text = raw_signal.upper()

    if any(k in signal_text for k in ["STOPLOSS", "FALSE BREAKOUT", "WEAKNESS"]):
        return "KHÔNG VÀO"
    if q == "YẾU":
        return "KHÔNG VÀO"
    if q == "TRUNG TÍNH":
        return "WATCH"
    if q == "KHÁ":
        if "BREAKOUT" in signal_text or "VWAP RECLAIM" in signal_text:
            return "TEST NHỎ"
        return "WATCH"
    if q == "MẠNH":
        if "BREAKOUT" in signal_text or "VWAP RECLAIM" in signal_text:
            return "BUY NHỎ"
        if "PULLBACK" in signal_text:
            return "TEST NHỎ"

    return "WATCH"


def confidence_from_recommendation(rec: str, quality: Dict[str, Any], row: pd.Series) -> str:
    score = quality["quality_score"]
    f = get_upstream_fields(row)

    if rec == "KHÔNG VÀO":
        return "HIGH" if quality["bad_reasons"] or score < 45 else "MEDIUM"
    if f["decision_mode"] in ["ĐÁNH RẤT NHỎ", "CASH MODE"]:
        return "MEDIUM" if rec in ["TEST NHỎ", "BUY NHỎ"] else "HIGH"
    if score >= 80:
        return "HIGH"
    if score >= 65:
        return "MEDIUM"
    return "LOW"


def suggested_size_from_recommendation(rec: str, row: pd.Series) -> str:
    f = get_upstream_fields(row)
    alloc = f["meta_alloc"]

    if rec == "KHÔNG VÀO":
        return "0%"
    if rec == "WATCH":
        return "0% - chỉ quan sát"
    if rec == "TEST NHỎ":
        return f"tối đa {min(alloc, 5):.1f}% vốn dự kiến"
    if rec == "BUY NHỎ":
        return f"tối đa {min(alloc, 10):.1f}% vốn dự kiến"
    if rec == "BUY CÓ KIỂM SOÁT":
        return f"tối đa {min(alloc, 20):.1f}% vốn dự kiến"
    return "không xác định"


def build_recommendation(row: pd.Series, raw_signal: str, quality: Dict[str, Any]) -> Dict[str, Any]:
    base_rec = base_recommendation_from_quality(raw_signal, quality)
    max_action = max_action_from_upstream(row)
    final_rec = cap_recommendation(base_rec, max_action)
    confidence = confidence_from_recommendation(final_rec, quality, row)
    suggested_size = suggested_size_from_recommendation(final_rec, row)

    return {
        "base_recommendation": base_rec,
        "max_action": max_action,
        "final_recommendation": final_rec,
        "confidence": confidence,
        "suggested_size": suggested_size,
    }


def pick_top_reasons(row: pd.Series, raw_signal: str, quality: Dict[str, Any], rec: Dict[str, Any]) -> List[str]:
    reasons: List[str] = []

    for r in quality["bad_reasons"][:2]:
        reasons.append(f"❌ {r}")
    for r in quality["good_reasons"][:2]:
        reasons.append(f"✅ {r}")
    for r in quality["warn_reasons"][:2]:
        reasons.append(f"⚠ {r}")

    f = get_upstream_fields(row)
    if rec["final_recommendation"] != rec["base_recommendation"]:
        reasons.append(f"⚠ Bị giới hạn bởi upstream: {f['decision_mode']}")

    if not reasons:
        reasons.append("ℹ Tín hiệu trung tính, cần theo dõi thêm")

    return reasons[:3]


def emoji_from_recommendation(rec: str) -> str:
    if rec == "KHÔNG VÀO":
        return "🔴"
    if rec == "WATCH":
        return "⚪"
    if rec == "TEST NHỎ":
        return "🟡"
    if rec == "BUY NHỎ":
        return "🟢"
    if rec == "BUY CÓ KIỂM SOÁT":
        return "🔥"
    return "🟡"


def detect_v182_signal_pack(row: pd.Series, snap: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    allowed, reason = upstream_allows_alert(row)
    if not allowed:
        print(f"UPSTREAM BLOCK: {row.get('Mã', '')} | {reason}", flush=True)
        return None

    raw_signal = detect_raw_signal(row, snap)
    if not raw_signal:
        return None

    quality = execution_quality_filter(row, snap, raw_signal)
    force_alert = any(k in raw_signal.upper() for k in ["STOPLOSS", "WEAKNESS", "FALSE BREAKOUT"])

    if not quality["passed"] and not force_alert:
        print(
            f"QUALITY BLOCK: {row.get('Mã', '')} | {raw_signal} | "
            f"score={quality['quality_score']} | bad={quality['bad_reasons']} | warn={quality['warn_reasons']}",
            flush=True,
        )
        return None

    rec = build_recommendation(row, raw_signal, quality)
    reasons = pick_top_reasons(row, raw_signal, quality, rec)

    return {
        "signal": raw_signal,
        "quality": quality,
        "recommendation": rec,
        "reasons": reasons,
    }


def build_alert(row: pd.Series, snap: Dict[str, Any], signal_pack: Dict[str, Any]) -> str:
    symbol = str(row.get("Mã", "")).strip().upper()
    raw_signal = signal_pack["signal"]
    quality = signal_pack["quality"]
    rec = signal_pack["recommendation"]
    reasons = signal_pack["reasons"]
    fields = get_upstream_fields(row)

    price = normalize_vn_price(snap.get("current_price"))
    vwap = normalize_vn_price(snap.get("vwap"))
    volume_ratio = snap.get("volume_ratio")

    ref = get_reference_price(row, price)
    low, high = get_buy_zone(row, price)
    stop = get_stoploss(row, price)

    intraday_ret_text = ""
    if ref is not None and ref > 0 and price is not None:
        intraday_ret_text = f"{(price / ref - 1.0) * 100:.2f}%"

    emoji = emoji_from_recommendation(rec["final_recommendation"])
    reason_text = "\n".join(reasons)

    msg = (
        f"{emoji} <b>{symbol}</b> — <b>{raw_signal}</b>\n\n"
        f"<b>KẾT LUẬN:</b>\n"
        f"<b>{rec['final_recommendation']}</b>\n\n"
        f"<b>ĐỘ TIN CẬY:</b> <b>{rec['confidence']}</b>\n"
        f"<b>SIZE GỢI Ý:</b> <b>{rec['suggested_size']}</b>\n\n"
        f"<b>3 LÝ DO CHÍNH:</b>\n"
        f"{reason_text}\n\n"
        f"<b>Risk Gate:</b>\n"
        f"Final: <b>{fields['final_decision']}</b> | Mode: <b>{fields['decision_mode']}</b>\n"
        f"Meta Allocation: <b>{fields['meta_alloc']:.2f}%</b> | Meta Exposure: <b>{fields['meta_exposure']:.4f}</b>\n\n"
        f"<b>Execution:</b>\n"
        f"Quality: <b>{quality['quality_label']}</b> | Score: <b>{quality['quality_score']}</b>\n"
    )

    if price is not None:
        msg += f"Giá: <b>{price:.2f}</b>\n"
    if vwap is not None:
        msg += f"VWAP: <b>{vwap:.2f}</b>\n"
    if volume_ratio is not None:
        msg += f"Volume ratio: <b>{volume_ratio:.2f}</b>\n"

    msg += (
        f"Biến động intraday: <b>{intraday_ret_text}</b>\n"
        f"Buy zone: {low if low is not None else ''} - {high if high is not None else ''}\n"
        f"Stoploss: {stop if stop is not None else ''}\n"
        f"Cooldown: <b>{quality['cooldown_min']} phút</b>\n"
        f"Time: {_now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    return msg


def _cooldown_ok(state: Dict[str, Any], symbol: str, signal: str, cooldown_min: int) -> bool:
    key = f"{symbol}:{signal}"
    last_ts = state.setdefault("last_alert_ts", {}).get(key)

    if last_ts is None:
        return True

    return int(time.time()) - int(last_ts) >= cooldown_min * 60


def _mark_alert(state: Dict[str, Any], symbol: str, signal: str):
    key = f"{symbol}:{signal}"
    sent = set(state.get("sent", []))
    sent.add(key)
    state["sent"] = sorted(sent)
    state.setdefault("last_alert_ts", {})[key] = int(time.time())
    save_state_obj(state)


def check_once(state: Dict[str, Any], df: pd.DataFrame) -> Dict[str, Any]:
    global _SCAN_INDEX

    if df is None or df.empty:
        print("No watchlist rows", flush=True)
        return state

    print(f"Scanning watchlist fixed: {len(df)} symbols", flush=True)

    if SCAN_ONE_SYMBOL_PER_LOOP:
        row = df.iloc[_SCAN_INDEX % len(df)]
        _SCAN_INDEX += 1
        rows_to_scan = [row]
    else:
        rows_to_scan = [row for _, row in df.iterrows()]

    for row in rows_to_scan:
        symbol = str(row.get("Mã", "")).strip().upper()
        if not symbol or symbol == "NAN":
            continue

        allowed, upstream_reason = upstream_allows_alert(row)
        print(f"SCAN SYMBOL: {symbol} | upstream_allowed={allowed} | {upstream_reason}", flush=True)
        if not allowed:
            continue

        snap = build_intraday_snapshot(symbol)
        price = normalize_vn_price(snap.get("current_price"))
        snap["current_price"] = price

        if price is None:
            print(f"No current price: {symbol}", flush=True)
            continue

        signal_pack = detect_v182_signal_pack(row, snap)

        if signal_pack:
            signal = signal_pack["signal"]
            quality = signal_pack["quality"]
            key = f"{symbol}:{signal}"

            if key not in set(state.get("sent", [])) or _cooldown_ok(state, symbol, signal, quality["cooldown_min"]):
                send_telegram(build_alert(row, snap, signal_pack))
                _mark_alert(state, symbol, signal)
                print("ALERT", key, flush=True)
            else:
                print("Cooldown / already sent", key, flush=True)
        else:
            print(
                f"OK {symbol}: price={price:.2f}, "
                f"vwap={snap.get('vwap') if snap.get('vwap') is not None else ''}, "
                f"vol_ratio={snap.get('volume_ratio') if snap.get('volume_ratio') is not None else ''}, "
                f"no V18.2 recommendation signal",
                flush=True,
            )

    return state


def startup_message(df: pd.DataFrame) -> str:
    symbols = df["Mã"].astype(str).str.upper().str.strip().tolist() if not df.empty and "Mã" in df.columns else []
    decision_modes = sorted(set(df["Decision Mode"].astype(str).tolist())) if not df.empty and "Decision Mode" in df.columns else []
    final_counts = df["Final Decision"].astype(str).value_counts().to_dict() if not df.empty and "Final Decision" in df.columns else {}

    return (
        "✅ <b>V18.2 Unified Execution Recommendation STARTED</b>\n"
        "<b>MODE:</b> OBEY V16/V17.1 RISK\n"
        f"RAW_URL: <code>{RAW_URL[:80]}...</code>\n"
        f"ROWS: <b>{len(df)}</b>\n"
        f"TICKERS: <b>{', '.join(symbols)}</b>\n"
        f"Decision Mode: <b>{', '.join(decision_modes) if decision_modes else 'UNKNOWN'}</b>\n"
        f"Final Counts: <b>{final_counts}</b>\n"
        f"QUALITY FILTER: <b>ON</b>\n"
        f"RECOMMENDATION ENGINE: <b>ON</b>\n"
        f"UPSTREAM GATE: <b>{'ON' if V18_OBEY_UPSTREAM_RISK else 'OFF'}</b>\n"
        f"COOLDOWN BASE: <b>{BASE_COOLDOWN_MIN} phút</b>\n"
        f"TIME: {_now().strftime('%Y-%m-%d %H:%M:%S')}"
    )


def main():
    print("V18.2 UNIFIED EXECUTION RECOMMENDATION STARTED", flush=True)
    print(f"TIME NOW: {_now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print(f"WATCHLIST_PATH={WATCHLIST_PATH}", flush=True)
    print(f"RAW_URL={'SET' if RAW_URL else 'EMPTY'}", flush=True)
    print(f"CHECK_INTERVAL_SEC={CHECK_INTERVAL_SEC}", flush=True)
    print(f"MARKET_START={MARKET_START} MARKET_END={MARKET_END}", flush=True)
    print(
        f"V182_ENABLE_EXECUTION={V182_ENABLE_EXECUTION} "
        f"V182_MIN_VOLUME_RATIO={V182_MIN_VOLUME_RATIO} "
        f"BASE_COOLDOWN_MIN={BASE_COOLDOWN_MIN} "
        f"V18_OBEY_UPSTREAM_RISK={V18_OBEY_UPSTREAM_RISK}",
        flush=True,
    )

    startup_df = select_top_watchlist(load_watchlist())
    send_telegram(startup_message(startup_df))

    state = load_state()

    while True:
        print(f"SCANNER ALIVE {_now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        try:
            df = select_top_watchlist(load_watchlist())
            if in_market_time():
                print("Inside market time - scanning", flush=True)
                state = check_once(state, df)
            else:
                print("Outside market time", _now().strftime("%Y-%m-%d %H:%M:%S"), flush=True)
        except Exception as e:
            print("ERROR loop:", repr(e), flush=True)
            send_telegram(f"⚠️ V18.2 scanner lỗi: <code>{repr(e)}</code>")

        time.sleep(CHECK_INTERVAL_SEC)


if __name__ == "__main__":
    main()
