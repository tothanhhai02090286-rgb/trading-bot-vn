# -*- coding: utf-8 -*-
"""
intraday_alert_bot_v18_execution.py

V18 Intraday Execution Layer for Render - REFACTORED FOR V17.1 / V16.

Vai trò chuẩn:
- V18 chỉ canh timing realtime.
- V18 KHÔNG tự quyết định mua lớn.
- V18 KHÔNG override V15.5 / V16 / V17.1.
- Nếu upstream chỉ cho WATCHLIST / ĐÁNH RẤT NHỎ thì V18 chỉ báo THEO DÕI / BUY NHỎ.

Input chính:
- intraday_watchlist_v17.csv do V17.1 tạo ra

Giữ lại:
- VWAP reclaim
- Breakout confirmation
- Pullback vùng mua
- False breakout detection
- Cooldown Telegram
- Rotate scan để giảm rate limit
"""

from __future__ import annotations

import os
import time
import json
from datetime import datetime, time as dtime
from typing import Optional, Set, Dict, Any, List, Tuple

import pandas as pd
import requests

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

WATCHLIST_PATH = os.getenv("INTRADAY_WATCHLIST_PATH", "../intraday_watchlist_v17.csv")
RAW_URL = (os.getenv("GITHUB_RAW_WATCHLIST_URL", "").strip() or os.getenv("RAW_URL", "").strip())
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()

CHECK_INTERVAL_SEC = int(os.getenv("CHECK_INTERVAL_SEC", "120"))
MARKET_START = os.getenv("MARKET_START", "09:00")
MARKET_END = os.getenv("MARKET_END", "14:50")
TZ_NAME = os.getenv("TZ", "Asia/Ho_Chi_Minh")
STATE_PATH = os.getenv("INTRADAY_ALERT_STATE", "intraday_alert_state.json")

MOMENTUM_FROM_REF_PCT = float(os.getenv("MOMENTUM_FROM_REF_PCT", "1.0"))
WEAKNESS_FROM_REF_PCT = float(os.getenv("WEAKNESS_FROM_REF_PCT", "-1.5"))
TOO_FAR_ABOVE_BUY_ZONE_PCT = float(os.getenv("TOO_FAR_ABOVE_BUY_ZONE_PCT", "2.0"))

V18_ENABLE_EXECUTION = os.getenv("V18_ENABLE_EXECUTION", "1").strip() == "1"
V18_MIN_VOLUME_RATIO = float(os.getenv("V18_MIN_VOLUME_RATIO", "1.5"))
V18_BREAKOUT_BUFFER_PCT = float(os.getenv("V18_BREAKOUT_BUFFER_PCT", "0.3"))
V18_PULLBACK_TOLERANCE_PCT = float(os.getenv("V18_PULLBACK_TOLERANCE_PCT", "0.7"))
V18_VWAP_TOLERANCE_PCT = float(os.getenv("V18_VWAP_TOLERANCE_PCT", "0.2"))
V18_ALERT_COOLDOWN_MIN = int(os.getenv("V18_ALERT_COOLDOWN_MIN", "30"))

MAX_SYMBOLS_REALTIME = int(os.getenv("MAX_SYMBOLS_REALTIME", "5"))
SCAN_ONE_SYMBOL_PER_LOOP = os.getenv("SCAN_ONE_SYMBOL_PER_LOOP", "1").strip() == "1"
V18_OBEY_UPSTREAM_RISK = os.getenv("V18_OBEY_UPSTREAM_RISK", "1").strip() == "1"

_LAST_SYMBOLS: Set[str] = set()
_SCAN_INDEX = 0


def _now():
    if ZoneInfo:
        return datetime.now(ZoneInfo(TZ_NAME))
    return datetime.now()


def _parse_hhmm(s: str) -> dtime:
    hh, mm = s.split(":")[:2]
    return dtime(int(hh), int(mm))


def in_market_time() -> bool:
    n = _now()
    if n.weekday() >= 5:
        return False
    t = n.time()
    start = _parse_hhmm(MARKET_START)
    end = _parse_hhmm(MARKET_END)
    lunch_start = dtime(11, 30)
    lunch_end = dtime(13, 0)
    return (start <= t <= end) and not (lunch_start <= t < lunch_end)


def send_telegram(text: str) -> bool:
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("WARN: missing TELEGRAM_TOKEN/TELEGRAM_CHAT_ID", flush=True)
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(
            url,
            data={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
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
            today = _now().strftime("%Y-%m-%d")
            if data.get("date") == today:
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


# ============================================================
# UPSTREAM RISK GATE: ép V18 obey V16/V17.1
# ============================================================


def get_upstream_fields(row: pd.Series) -> Dict[str, Any]:
    final_decision = normalize_text(row.get("Final Decision", row.get("Hành động", "")))
    realtime_group = normalize_text(row.get("Nhóm realtime", ""))
    decision_mode = normalize_text(row.get("Decision Mode", ""))
    regime_strength = normalize_text(row.get("Regime Strength", ""))
    equity_state = normalize_text(row.get("Equity State", ""))
    priority = normalize_text(row.get("Ưu tiên", ""))
    meta_alloc = _num(row.get("Meta Allocation %", 0.0)) or 0.0
    meta_exposure = _num(row.get("Meta Exposure", 0.0)) or 0.0
    return {
        "final_decision": final_decision,
        "realtime_group": realtime_group,
        "decision_mode": decision_mode,
        "regime_strength": regime_strength,
        "equity_state": equity_state,
        "priority": priority,
        "meta_alloc": meta_alloc,
        "meta_exposure": meta_exposure,
    }


def upstream_allows_alert(row: pd.Series) -> Tuple[bool, str]:
    f = get_upstream_fields(row)
    if not V18_OBEY_UPSTREAM_RISK:
        return True, "Upstream gate đang tắt"
    if f["final_decision"] in ["AVOID", "BỎ QUA", "REDUCE", "GIẢM"]:
        return False, "V17.1 final decision không cho realtime entry"
    if f["realtime_group"] in ["BỎ QUA", "AVOID"]:
        return False, "Nhóm realtime bị loại"
    if f["decision_mode"] == "CASH MODE":
        return False, "V16 CASH MODE - V18 không báo entry"
    if f["meta_alloc"] <= 0.01:
        return False, "Meta allocation gần 0"
    return True, "Upstream cho phép theo dõi"


def upstream_execution_action(row: pd.Series, timing_signal: str) -> Tuple[str, str, str]:
    f = get_upstream_fields(row)
    final_decision = f["final_decision"]
    realtime_group = f["realtime_group"]
    decision_mode = f["decision_mode"]
    meta_alloc = f["meta_alloc"]
    regime_strength = f["regime_strength"]

    if final_decision == "BUY NOW" and realtime_group == "MUA":
        if decision_mode in ["ĐÁNH VỪA", "ĐÁNH MẠNH CÓ KIỂM SOÁT", "ĐÁNH VỪA CÓ KIỂM SOÁT"]:
            return "BUY NOW CÓ KIỂM SOÁT", "UPSTREAM PASS", "🟢"

    if decision_mode == "CASH MODE":
        return "KHÔNG MUA - CHỈ QUAN SÁT", "UPSTREAM CASH MODE", "⚪"

    if decision_mode in ["ĐÁNH RẤT NHỎ", "ĐÁNH NHỎ"]:
        if meta_alloc >= 5:
            return "THEO DÕI / BUY NHỎ", "UPSTREAM LIMITED - KHÔNG BUY NOW", "🟡"
        return "THEO DÕI", "UPSTREAM LIMITED - WATCH ONLY", "🟡"

    if "RISK OFF" in regime_strength:
        return "THEO DÕI", "REGIME RISK-OFF - KHÔNG AGGRESSIVE", "🟡"

    if final_decision == "WATCHLIST":
        if meta_alloc >= 5:
            return "THEO DÕI / BUY NHỎ", "WATCHLIST THEO V17.1", "🟡"
        return "THEO DÕI", "WATCHLIST THEO V17.1", "🟡"

    if final_decision == "BUY NOW":
        return "BUY NOW CÓ KIỂM SOÁT", "UPSTREAM PASS", "🟢"

    return "THEO DÕI", "UPSTREAM DEFAULT WATCH", "🟡"


# ============================================================
# WATCHLIST
# ============================================================


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
    out = out.drop_duplicates(subset=["Mã"], keep="first").reset_index(drop=True)
    return out


def select_top_watchlist(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if "Meta Allocation %" in out.columns:
        out["Meta Allocation %"] = pd.to_numeric(out["Meta Allocation %"], errors="coerce").fillna(0)
    else:
        out["Meta Allocation %"] = 0.0
    out["priority_group"] = 0
    if "Final Decision" in out.columns:
        decision_text = out["Final Decision"].astype(str).str.upper()
        out.loc[decision_text.str.contains("BUY NOW|MUA", na=False), "priority_group"] += 100
        out.loc[decision_text.str.contains("WATCHLIST|WATCH|THEO", na=False), "priority_group"] += 40
    if "Nhóm realtime" in out.columns:
        group_text = out["Nhóm realtime"].astype(str).str.upper()
        out.loc[group_text.str.contains("MUA", na=False), "priority_group"] += 50
        out.loc[group_text.str.contains("THEO", na=False), "priority_group"] += 30
        out.loc[group_text.str.contains("WATCH", na=False), "priority_group"] += 10
    if "Ưu tiên" in out.columns:
        p = out["Ưu tiên"].astype(str).str.upper()
        out.loc[p.str.contains("CAO", na=False), "priority_group"] += 30
        out.loc[p.str.contains("VỪA", na=False), "priority_group"] += 20
        out.loc[p.str.contains("THẤP", na=False), "priority_group"] += 10

    legacy_cols = ["Momentum Score", "Bottom Score", "RS20", "Volume Ratio", "Lợi TB T+5 %"]
    for col in legacy_cols:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0)
    momentum = out["Momentum Score"] if "Momentum Score" in out.columns else 0
    bottom = out["Bottom Score"] if "Bottom Score" in out.columns else 0
    rs20 = out["RS20"] if "RS20" in out.columns else 0
    vol = out["Volume Ratio"] if "Volume Ratio" in out.columns else 0
    t5 = out["Lợi TB T+5 %"] if "Lợi TB T+5 %" in out.columns else 0
    out["realtime_score"] = out["priority_group"] + out["Meta Allocation %"] * 5 + momentum * 0.15 + bottom * 0.10 + rs20 * 0.5 + vol * 2 + t5
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
            print(f"WATCHLIST loaded from RAW_URL: rows={len(df)} | tickers={df['Mã'].tolist() if not df.empty and 'Mã' in df.columns else []} | time={_now().strftime('%H:%M:%S')}", flush=True)
            _notify_watchlist_changes(df)
            return df
        except Exception as e:
            print("WARN raw watchlist, fallback local:", repr(e), flush=True)
    candidates = [WATCHLIST_PATH, "intraday_watchlist_v17.csv", "../intraday_watchlist_v17.csv", "intraday_watchlist.csv", "../intraday_watchlist.csv", "./intraday_watchlist.csv"]
    for path in candidates:
        if os.path.exists(path):
            df = pd.read_csv(path)
            df = normalize_watchlist(df)
            print(f"WATCHLIST loaded local: {path} | rows={len(df)}", flush=True)
            _notify_watchlist_changes(df)
            return df
    print(f"WARN: watchlist not found. Tried: {candidates}", flush=True)
    return pd.DataFrame()


# ============================================================
# PRICE DATA
# ============================================================


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
    out["volume_norm"] = pd.to_numeric(out[vol_col], errors="coerce").fillna(0) if vol_col is not None else 0
    out = out[out["price_norm"].notna()].copy()
    if out.empty:
        return pd.DataFrame()
    return out.reset_index(drop=True)


def get_current_price_vnstock(symbol: str) -> Optional[float]:
    try:
        df_raw = get_intraday_bars_vnstock(symbol)
        df = normalize_intraday_bars(df_raw)
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
            data = yf.download(yf_symbol, period="5d", interval="1d", progress=False, auto_adjust=False, threads=False)
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
    price = get_current_price_vnstock(symbol)
    if price is not None:
        return normalize_vn_price(price)
    return normalize_vn_price(get_current_price_yfinance(symbol))


def build_intraday_snapshot(symbol: str) -> Dict[str, Any]:
    bars_raw = get_intraday_bars_vnstock(symbol)
    bars = normalize_intraday_bars(bars_raw)
    snap: Dict[str, Any] = {"bars_ok": False, "current_price": None, "vwap": None, "prev_price": None, "volume_ratio": None, "session_high_prev": None, "session_low": None}
    if bars.empty:
        snap["current_price"] = normalize_vn_price(get_current_price(symbol))
        return snap
    price = normalize_vn_price(bars["price_norm"].iloc[-1])
    prev = normalize_vn_price(bars["price_norm"].iloc[-2]) if len(bars) >= 2 else None
    vol = pd.to_numeric(bars["volume_norm"], errors="coerce").fillna(0)
    px = pd.to_numeric(bars["price_norm"], errors="coerce").apply(normalize_vn_price)
    total_vol = float(vol.sum())
    vwap = normalize_vn_price((px * vol).sum() / total_vol) if total_vol > 0 else normalize_vn_price(px.mean())
    last_vol = float(vol.iloc[-1]) if len(vol) else 0
    avg_vol = float(vol.tail(20).mean()) if len(vol.tail(20)) else 0
    volume_ratio = (last_vol / avg_vol) if avg_vol > 0 else None
    prev_prices = px.iloc[:-1] if len(px) >= 2 else px
    session_high_prev = normalize_vn_price(prev_prices.max()) if len(prev_prices) else price
    session_low = normalize_vn_price(px.min()) if len(px) else price
    snap.update({"bars_ok": True, "current_price": price, "vwap": vwap, "prev_price": prev, "volume_ratio": volume_ratio, "session_high_prev": session_high_prev, "session_low": session_low})
    return snap


# ============================================================
# BUY ZONE / STOPLOSS
# ============================================================


def get_reference_price(row: pd.Series, current_price: Optional[float]) -> Optional[float]:
    ref = _row_float(row, "Giá tham chiếu", price_mode=True)
    if ref is not None:
        return ref
    return current_price


def get_buy_zone(row: pd.Series, current_price: Optional[float]) -> Tuple[Optional[float], Optional[float]]:
    buy_low = _row_float(row, "Buy zone thấp", price_mode=True)
    buy_high = _row_float(row, "Buy zone cao", price_mode=True)
    if buy_low is not None and buy_high is not None:
        return buy_low, buy_high
    low_pct = _row_float(row, "Buy zone thấp %", price_mode=False)
    high_pct = _row_float(row, "Buy zone cao %", price_mode=False)
    ref = get_reference_price(row, current_price)
    if ref is not None and low_pct is not None and high_pct is not None:
        return normalize_vn_price(ref * (1 + low_pct / 100.0)), normalize_vn_price(ref * (1 + high_pct / 100.0))
    return None, None


def get_stoploss(row: pd.Series, current_price: Optional[float]) -> Optional[float]:
    stop = _row_float(row, "Stoploss tham khảo", price_mode=True)
    if stop is not None:
        return stop
    stop_pct = _row_float(row, "Stoploss tham khảo %", price_mode=False)
    ref = get_reference_price(row, current_price)
    if ref is not None and stop_pct is not None:
        return normalize_vn_price(ref * (1 + stop_pct / 100.0))
    return None


# ============================================================
# SIGNAL DETECTION
# ============================================================


def detect_v17_legacy_signal(row: pd.Series, current_price: float) -> Optional[str]:
    current_price = normalize_vn_price(current_price)
    if current_price is None:
        return None
    ref = get_reference_price(row, current_price)
    buy_low, buy_high = get_buy_zone(row, current_price)
    stop = get_stoploss(row, current_price)
    if stop is not None and current_price <= stop:
        return "🔴 THỦNG STOPLOSS"
    if buy_low is not None and buy_high is not None and buy_low <= current_price <= buy_high:
        return "🟢 PULLBACK VÙNG MUA"
    if buy_high is not None and current_price > buy_high * (1 + TOO_FAR_ABOVE_BUY_ZONE_PCT / 100):
        return "⚠️ VƯỢT BUY ZONE QUÁ XA"
    if ref is not None and ref > 0:
        intraday_ret = (current_price / ref - 1.0) * 100.0
        if intraday_ret >= MOMENTUM_FROM_REF_PCT:
            if buy_high is None or current_price <= buy_high * (1 + TOO_FAR_ABOVE_BUY_ZONE_PCT / 100):
                return "🟡 INTRADAY MOMENTUM"
        if intraday_ret <= WEAKNESS_FROM_REF_PCT:
            return "⚠️ INTRADAY WEAKNESS"
    return None


def detect_v18_execution_signal(row: pd.Series, snap: Dict[str, Any]) -> Optional[str]:
    allowed, reason = upstream_allows_alert(row)
    if not allowed:
        print(f"UPSTREAM BLOCK: {row.get('Mã', '')} | {reason}", flush=True)
        return None
    current_price = normalize_vn_price(snap.get("current_price"))
    if current_price is None:
        return None
    snap["current_price"] = current_price
    if not V18_ENABLE_EXECUTION or not snap.get("bars_ok"):
        return detect_v17_legacy_signal(row, float(current_price))

    price = float(current_price)
    prev_price = normalize_vn_price(snap.get("prev_price"))
    vwap = normalize_vn_price(snap.get("vwap"))
    volume_ratio = snap.get("volume_ratio")
    session_high_prev = normalize_vn_price(snap.get("session_high_prev"))
    ref = get_reference_price(row, price)
    buy_low, buy_high = get_buy_zone(row, price)
    stop = get_stoploss(row, price)

    if stop is not None and price <= stop:
        return "🔴 THỦNG STOPLOSS"
    if vwap is None:
        return detect_v17_legacy_signal(row, price)

    vwap_reclaim = prev_price is not None and prev_price <= vwap and price >= vwap * (1 + V18_VWAP_TOLERANCE_PCT / 100)
    vol_ok = volume_ratio is not None and volume_ratio >= V18_MIN_VOLUME_RATIO

    if vwap_reclaim and vol_ok:
        return "🔥 VWAP RECLAIM + VOLUME"

    breakout_levels = []
    if session_high_prev is not None:
        breakout_levels.append(float(session_high_prev))
    if buy_high is not None:
        breakout_levels.append(float(buy_high))
    if ref is not None:
        breakout_levels.append(float(ref))
    breakout_level = max(breakout_levels) if breakout_levels else None
    if breakout_level is not None:
        breakout_price = breakout_level * (1 + V18_BREAKOUT_BUFFER_PCT / 100)
        if price >= breakout_price and price >= vwap and vol_ok:
            return "🚀 BREAKOUT XÁC NHẬN"
        if price >= breakout_price and price < vwap:
            return "⚠️ FALSE BREAKOUT RISK"

    if buy_low is not None and buy_high is not None:
        in_buy_zone = buy_low <= price <= buy_high
        not_lost_vwap = price >= vwap * (1 - V18_PULLBACK_TOLERANCE_PCT / 100)
        if in_buy_zone and not_lost_vwap:
            return "🟢 PULLBACK VÙNG MUA"

    legacy = detect_v17_legacy_signal(row, price)
    if legacy and price >= vwap * (1 - V18_VWAP_TOLERANCE_PCT / 100):
        return f"{legacy} + VWAP OK"
    return None


# ============================================================
# ALERT
# ============================================================


def build_alert(row: pd.Series, snap: Dict[str, Any], alert_type: str) -> str:
    symbol = str(row.get("Mã", "")).strip().upper()
    fields = get_upstream_fields(row)
    action_text, risk_text, emoji = upstream_execution_action(row, alert_type)
    current_price = normalize_vn_price(snap.get("current_price"))
    vwap = normalize_vn_price(snap.get("vwap"))
    volume_ratio = snap.get("volume_ratio")
    ref = get_reference_price(row, current_price)
    buy_low, buy_high = get_buy_zone(row, current_price)
    stop = get_stoploss(row, current_price)
    intraday_ret_text = ""
    if ref is not None and ref > 0 and current_price is not None:
        intraday_ret_text = f"{(float(current_price) / ref - 1.0) * 100:.2f}%"
    price_line = f"Giá hiện tại: <b>{float(current_price):.2f}</b>\n" if current_price is not None else "Giá hiện tại: \n"
    vwap_line = f"VWAP: <b>{vwap:.2f}</b>\n" if vwap is not None else ""
    volume_line = f"Volume ratio: <b>{volume_ratio:.2f}</b>\n" if volume_ratio is not None else ""
    return (
        f"{emoji} <b>{symbol}</b> - <b>{alert_type}</b>\n"
        f"Final Decision: <b>{fields['final_decision']}</b>\n"
        f"Nhóm realtime: <b>{fields['realtime_group']}</b>\n"
        f"Decision Mode: <b>{fields['decision_mode']}</b>\n"
        f"Meta Allocation: <b>{fields['meta_alloc']:.2f}%</b>\n"
        f"Meta Exposure: <b>{fields['meta_exposure']:.4f}</b>\n"
        f"Regime: <b>{fields['regime_strength']}</b>\n"
        f"Equity State: <b>{fields['equity_state']}</b>\n"
        f"{price_line}{vwap_line}{volume_line}"
        f"Giá tham chiếu: {ref if ref is not None else ''}\n"
        f"Biến động intraday: <b>{intraday_ret_text}</b>\n"
        f"Buy zone: {buy_low if buy_low is not None else ''} - {buy_high if buy_high is not None else ''}\n"
        f"Stoploss: {stop if stop is not None else ''}\n"
        f"Action: <b>{action_text}</b>\n"
        f"Risk: <b>{risk_text}</b>\n"
        f"Time: {_now().strftime('%Y-%m-%d %H:%M:%S')}"
    )


def _cooldown_ok(state: Dict[str, Any], symbol: str, signal: str) -> bool:
    key = f"{symbol}:{signal}"
    last_map = state.setdefault("last_alert_ts", {})
    last_ts = last_map.get(key)
    now_ts = int(time.time())
    if last_ts is None:
        return True
    return now_ts - int(last_ts) >= V18_ALERT_COOLDOWN_MIN * 60


def _mark_alert(state: Dict[str, Any], symbol: str, signal: str):
    key = f"{symbol}:{signal}"
    sent = set(state.get("sent", []))
    sent.add(key)
    state["sent"] = sorted(sent)
    state.setdefault("last_alert_ts", {})[key] = int(time.time())
    save_state_obj(state)


# ============================================================
# SCAN LOOP
# ============================================================


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
        current_price = normalize_vn_price(snap.get("current_price"))
        snap["current_price"] = current_price
        if current_price is None:
            print(f"No current price: {symbol}", flush=True)
            continue
        signal = detect_v18_execution_signal(row, snap)
        if signal:
            key = f"{symbol}:{signal}"
            if key not in set(state.get("sent", [])) or _cooldown_ok(state, symbol, signal):
                send_telegram(build_alert(row, snap, signal))
                _mark_alert(state, symbol, signal)
                print("ALERT", key, flush=True)
            else:
                print("Cooldown / already sent", key, flush=True)
        else:
            vwap = snap.get("vwap")
            vr = snap.get("volume_ratio")
            print(f"OK {symbol}: price={float(current_price):.2f}, vwap={vwap if vwap is not None else ''}, vol_ratio={vr if vr is not None else ''}, no V18 signal", flush=True)
    return state


def startup_message(df: pd.DataFrame) -> str:
    startup_symbols = df["Mã"].astype(str).str.upper().str.strip().tolist() if not df.empty and "Mã" in df.columns else []
    decision_modes = sorted(set(df["Decision Mode"].astype(str).tolist())) if not df.empty and "Decision Mode" in df.columns else []
    final_counts = df["Final Decision"].astype(str).value_counts().to_dict() if not df.empty and "Final Decision" in df.columns else {}
    return (
        "✅ <b>V18 Intraday Execution Scanner STARTED</b>\n"
        "<b>MODE:</b> OBEY V16/V17.1 RISK\n"
        f"RAW_URL: <code>{RAW_URL[:80]}...</code>\n"
        f"ROWS: <b>{len(df)}</b>\n"
        f"TICKERS: <b>{', '.join(startup_symbols)}</b>\n"
        f"Decision Mode: <b>{', '.join(decision_modes) if decision_modes else 'UNKNOWN'}</b>\n"
        f"Final Counts: <b>{final_counts}</b>\n"
        f"VWAP: <b>ON</b> | BREAKOUT: <b>ON</b> | PULLBACK: <b>ON</b>\n"
        f"UPSTREAM GATE: <b>{'ON' if V18_OBEY_UPSTREAM_RISK else 'OFF'}</b>\n"
        f"COOLDOWN: <b>{V18_ALERT_COOLDOWN_MIN} phút</b>\n"
        f"TIME: {_now().strftime('%Y-%m-%d %H:%M:%S')}"
    )


def main():
    print("V18 INTRADAY EXECUTION SCANNER STARTED - OBEY V16/V17.1", flush=True)
    print(f"TIME NOW: {_now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print(f"WATCHLIST_PATH={WATCHLIST_PATH}", flush=True)
    print(f"RAW_URL={'SET' if RAW_URL else 'EMPTY'}", flush=True)
    print(f"CHECK_INTERVAL_SEC={CHECK_INTERVAL_SEC}", flush=True)
    print(f"MARKET_START={MARKET_START} MARKET_END={MARKET_END}", flush=True)
    print(f"V18_ENABLE_EXECUTION={V18_ENABLE_EXECUTION} V18_MIN_VOLUME_RATIO={V18_MIN_VOLUME_RATIO} V18_ALERT_COOLDOWN_MIN={V18_ALERT_COOLDOWN_MIN} V18_OBEY_UPSTREAM_RISK={V18_OBEY_UPSTREAM_RISK}", flush=True)

    startup_df = load_watchlist()
    startup_df = select_top_watchlist(startup_df)
    ok = send_telegram(startup_message(startup_df))
    print(f"TELEGRAM START MESSAGE SENT={ok}", flush=True)
    state = load_state()

    while True:
        print(f"SCANNER ALIVE {_now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        try:
            # Reload watchlist mỗi vòng để Render đọc file mới nếu GitHub vừa cập nhật.
            df = load_watchlist()
            df = select_top_watchlist(df)
            if in_market_time():
                print("Inside market time - scanning", flush=True)
                state = check_once(state, df)
            else:
                print("Outside market time", _now().strftime("%Y-%m-%d %H:%M:%S"), flush=True)
        except Exception as e:
            print("ERROR loop:", repr(e), flush=True)
            send_telegram(f"⚠️ Intraday scanner lỗi: <code>{repr(e)}</code>")
        time.sleep(CHECK_INTERVAL_SEC)


if __name__ == "__main__":
    main()
