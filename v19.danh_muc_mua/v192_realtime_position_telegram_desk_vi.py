# -*- coding: utf-8 -*-
"""
v192_realtime_position_telegram_desk_vi.py

V19.2.1 — REALTIME POSITION TELEGRAM DESK + PRICE GUARD

Patch chính:
- Ưu tiên giá intraday trong giờ thị trường.
- Telegram hiện Nguồn giá / Realtime OK / Thời gian giá.
- Nếu đang trong giờ thị trường mà không lấy được giá intraday:
  không báo THOÁT VỊ THẾ mạnh, đổi sang KIỂM TRA GIÁ TRƯỚC KHI BÁN.
"""

from __future__ import annotations

import os
import time
import json
import warnings
from datetime import datetime, time as dtime
from typing import Dict, Any, Optional, Tuple, List

import numpy as np
import pandas as pd
import requests
import sys

sys.path.append("/opt/render/project/src/v19.3_alert_lichsu_canhbao")

from v193_alert_journal_layer import log_position_alert
from v1931_github_journal_sync import sync_journal_to_github

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

try:
    from vn_trade_safety import evaluate_entry_safety, adjust_exit_action
    VN_TRADE_SAFETY_ON = os.getenv("VN_TRADE_SAFETY_ON", "1").strip() == "1"
except Exception as e:
    print("WARN VN trade safety import failed:", repr(e), flush=True)
    VN_TRADE_SAFETY_ON = False

try:
    from sector_money_flow import evaluate_sector_money_flow, adjust_add_by_sector
    VN_SECTOR_FLOW_ON = os.getenv("VN_SECTOR_FLOW_ON", "1").strip() == "1"
except Exception as e:
    print("WARN VN sector money flow import failed:", repr(e), flush=True)
    VN_SECTOR_FLOW_ON = False

try:
    from vn_position_state import (
        classify_position_state,
        adjust_action_by_position_state,
        position_state_summary,
    )
    VN_POSITION_STATE_ON = os.getenv("VN_POSITION_STATE_ON", "1").strip() == "1"
except Exception as e:
    print("WARN VN position state import failed:", repr(e), flush=True)
    VN_POSITION_STATE_ON = False

try:
    from vn_position_health import calculate_position_health
    VN_POSITION_HEALTH_ON = os.getenv("VN_POSITION_HEALTH_ON", "1").strip() == "1"
except Exception as e:
    print("WARN VN position health import failed:", repr(e), flush=True)
    VN_POSITION_HEALTH_ON = False

try:
    from vn_mini_market_regime import evaluate_mini_market_regime
    VN_MINI_MARKET_REGIME_ON = os.getenv("VN_MINI_MARKET_REGIME_ON", "1").strip() == "1"
except Exception as e:
    print("WARN VN mini market regime import failed:", repr(e), flush=True)
    VN_MINI_MARKET_REGIME_ON = False

try:
    from vn_leader_rotation import evaluate_leader_rotation
    VN_LEADER_ROTATION_ON = os.getenv("VN_LEADER_ROTATION_ON", "1").strip() == "1"
except Exception as e:
    print("WARN VN leader rotation import failed:", repr(e), flush=True)
    VN_LEADER_ROTATION_ON = False

try:
    from vn_institutional_flow import evaluate_institutional_flow
    VN_INSTITUTIONAL_FLOW_ON = os.getenv("VN_INSTITUTIONAL_FLOW_ON", "1").strip() == "1"
except Exception as e:
    print("WARN VN institutional flow import failed:", repr(e), flush=True)
    VN_INSTITUTIONAL_FLOW_ON = False

try:
    from vn_market_internals import evaluate_market_internals
    VN_MARKET_INTERNALS_ON = os.getenv("VN_MARKET_INTERNALS_ON", "1").strip() == "1"
except Exception as e:
    print("WARN VN market internals import failed:", repr(e), flush=True)
    VN_MARKET_INTERNALS_ON = False

try:
    from vn_portfolio_intelligence import evaluate_portfolio_intelligence
    VN_PORTFOLIO_INTELLIGENCE_ON = os.getenv("VN_PORTFOLIO_INTELLIGENCE_ON", "1").strip() == "1"
except Exception as e:
    print("WARN VN portfolio intelligence import failed:", repr(e), flush=True)
    VN_PORTFOLIO_INTELLIGENCE_ON = False


warnings.filterwarnings("ignore")

SYSTEM_VERSION = "V19.2.1_REALTIME_POSITION_PRICE_GUARD_VI"

WATCHLIST_PATH = os.getenv("V19_WATCHLIST_PATH", "intraday_watchlist_v17.csv")
POSITIONS_PATH = os.getenv("V19_POSITIONS_PATH", "positions_v19.csv")
CACHE_DIR = os.getenv("CACHE_STOCK_DIR", "cache_stock")

STATE_PATH = os.getenv("V192_STATE_PATH", "v192_position_alert_state.json")
OUTPUT_SNAPSHOT = "v192_position_snapshot.csv"
OUTPUT_ALERTS = "v192_position_alerts.csv"
OUTPUT_REPORT = "v192_position_report.txt"

TZ_NAME = os.getenv("TZ", "Asia/Ho_Chi_Minh")
RUN_ONCE = os.getenv("V192_RUN_ONCE", "1").strip() == "1"
LOOP_INTERVAL_SEC = int(os.getenv("V192_LOOP_INTERVAL_SEC", "120"))

MARKET_START = os.getenv("MARKET_START", "09:00")
MARKET_END = os.getenv("MARKET_END", "14:50")
LUNCH_START = os.getenv("LUNCH_START", "11:30")
LUNCH_END = os.getenv("LUNCH_END", "13:00")

HARD_STOP_PCT = float(os.getenv("V192_HARD_STOP_PCT", "5.0"))
ATR_PERIOD = int(os.getenv("V192_ATR_PERIOD", "14"))
ATR_STOP_MULTIPLIER = float(os.getenv("V192_ATR_STOP_MULTIPLIER", "2.0"))
SWING_LOOKBACK = int(os.getenv("V192_SWING_LOOKBACK", "10"))
SWING_BUFFER_PCT = float(os.getenv("V192_SWING_BUFFER_PCT", "0.5"))
MA20_BUFFER_PCT = float(os.getenv("V192_MA20_BUFFER_PCT", "1.0"))

BREAKEVEN_TRIGGER_PCT = float(os.getenv("V192_BREAKEVEN_TRIGGER_PCT", "2.0"))
TRAIL_TRIGGER_PCT = float(os.getenv("V192_TRAIL_TRIGGER_PCT", "5.0"))
PROFIT_TAKE_1_PCT = float(os.getenv("V192_PROFIT_TAKE_1_PCT", "7.0"))
PROFIT_TAKE_2_PCT = float(os.getenv("V192_PROFIT_TAKE_2_PCT", "12.0"))

MAX_ADD_COUNT = int(os.getenv("V192_MAX_ADD_COUNT", "2"))
MIN_ADD_PROFIT_PCT = float(os.getenv("V192_MIN_ADD_PROFIT_PCT", "3.0"))
MAX_POSITION_ALLOCATION_PCT = float(os.getenv("V192_MAX_POSITION_ALLOCATION_PCT", "15.0"))
MAX_PORTFOLIO_HEAT_PCT = float(os.getenv("V192_MAX_PORTFOLIO_HEAT_PCT", "60.0"))

VN_TPLUS_SELLABLE_DAYS = float(os.getenv("V192_VN_TPLUS_SELLABLE_DAYS", "2.5"))
ALERT_COOLDOWN_MIN = int(os.getenv("V192_ALERT_COOLDOWN_MIN", "30"))
SEND_STARTUP_SUMMARY = os.getenv("V192_SEND_STARTUP_SUMMARY", "1").strip() == "1"
SEND_HOLD_ALERTS = os.getenv("V192_SEND_HOLD_ALERTS", "0").strip() == "1"

MINI_MARKET_MAX_SYMBOLS = int(os.getenv("VN_MINI_MARKET_MAX_SYMBOLS", "0"))
LEADER_ROTATION_MAX_SYMBOLS = int(os.getenv("VN_LEADER_ROTATION_MAX_SYMBOLS", "0"))
LEADER_ROTATION_SECTOR_MAPPING_PATH = os.getenv("VN_SECTOR_MAPPING_PATH", "v19.danh_muc_mua/sector_mapping.csv")
INSTITUTIONAL_FLOW_MAX_SYMBOLS = int(os.getenv("VN_INSTITUTIONAL_FLOW_MAX_SYMBOLS", "0"))
INSTITUTIONAL_FLOW_SECTOR_MAPPING_PATH = os.getenv("VN_SECTOR_MAPPING_PATH", "v19.danh_muc_mua/sector_mapping.csv")

PRICE_GUARD_ON = os.getenv("V192_PRICE_GUARD_ON", "1").strip() == "1"
BLOCK_SELL_IF_NOT_INTRADAY = os.getenv("V192_BLOCK_SELL_IF_NOT_INTRADAY", "1").strip() == "1"

BLOCK_ADD_MODES = {"CASH MODE", "ĐÁNH RẤT NHỎ"}
SELL_ACTIONS = {"THOÁT VỊ THẾ", "GIẢM VỊ THẾ", "CHỐT BỚT NHẸ", "CHỐT MẠNH", "CẮT LỖ", "GIẢM TỶ TRỌNG"}


def now_dt():
    if ZoneInfo:
        return datetime.now(ZoneInfo(TZ_NAME))
    return datetime.now()


def now_str() -> str:
    return now_dt().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str) -> None:
    print(f"[V19.2] {msg}", flush=True)


def parse_hhmm(s: str) -> dtime:
    hh, mm = s.split(":")[:2]
    return dtime(int(hh), int(mm))


def in_market_time() -> bool:
    n = now_dt()
    if n.weekday() >= 5:
        return False
    t = n.time()
    return parse_hhmm(MARKET_START) <= t <= parse_hhmm(MARKET_END) and not (
        parse_hhmm(LUNCH_START) <= t < parse_hhmm(LUNCH_END)
    )


def read_csv_smart(path: str) -> pd.DataFrame:
    for enc in ["utf-8-sig", "utf-8", "cp1258", "latin1"]:
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            pass
    return pd.read_csv(path)


def to_num(x: Any, default: float = 0.0) -> float:
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


def safe_str(x: Any, default: str = "") -> str:
    try:
        if pd.isna(x):
            return default
    except Exception:
        pass
    s = str(x).strip()
    return s if s else default


def normalize_text(x: Any) -> str:
    return safe_str(x).upper()


def normalize_price(x: Any) -> Optional[float]:
    v = to_num(x, default=np.nan)
    if pd.isna(v):
        return None
    if v > 1000:
        v = v / 1000.0
    return round(float(v), 3)


def find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    if df is None or df.empty:
        return None
    lower_map = {str(c).lower(): c for c in df.columns}
    for c in candidates:
        if c in df.columns:
            return c
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return None


def send_telegram(text: str) -> bool:
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        log("Thiếu TELEGRAM_TOKEN hoặc TELEGRAM_CHAT_ID")
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=20,
        )
        log(f"TELEGRAM STATUS: {r.status_code} {r.text[:160]}")
        return r.status_code == 200
    except Exception as e:
        log(f"Lỗi Telegram: {repr(e)}")
        return False


def load_state() -> Dict[str, Any]:
    try:
        if os.path.exists(STATE_PATH):
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("date") == now_dt().strftime("%Y-%m-%d"):
                return data
    except Exception as e:
        log(f"Lỗi load state: {repr(e)}")
    return {"date": now_dt().strftime("%Y-%m-%d"), "last_alert_ts": {}, "sent": []}


def save_state(state: Dict[str, Any]) -> None:
    try:
        state["date"] = now_dt().strftime("%Y-%m-%d")
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"Lỗi save state: {repr(e)}")


def cooldown_ok(state: Dict[str, Any], symbol: str, action: str) -> bool:
    key = f"{symbol}:{action}"
    last_ts = state.setdefault("last_alert_ts", {}).get(key)
    if last_ts is None:
        return True
    return int(time.time()) - int(last_ts) >= ALERT_COOLDOWN_MIN * 60


def mark_alert(state: Dict[str, Any], symbol: str, action: str) -> None:
    key = f"{symbol}:{action}"
    state.setdefault("last_alert_ts", {})[key] = int(time.time())
    sent = set(state.get("sent", []))
    sent.add(key)
    state["sent"] = sorted(sent)
    save_state(state)


def load_watchlist() -> pd.DataFrame:
    if not os.path.exists(WATCHLIST_PATH):
        log(f"Không thấy {WATCHLIST_PATH}")
        return pd.DataFrame()
    df = read_csv_smart(WATCHLIST_PATH)
    if "Mã" not in df.columns:
        for c in ["Ma", "Symbol", "Ticker", "ticker", "Mã CP"]:
            if c in df.columns:
                df["Mã"] = df[c]
                break
    if "Mã" in df.columns:
        df["Mã"] = df["Mã"].astype(str).str.upper().str.strip()
    return df


def load_positions() -> pd.DataFrame:
    if not os.path.exists(POSITIONS_PATH):
        log(f"Không thấy {POSITIONS_PATH}. Không có vị thế để quản lý.")
        return pd.DataFrame()
    df = read_csv_smart(POSITIONS_PATH)
    if "Mã" not in df.columns:
        for c in ["Ma", "Symbol", "Ticker", "ticker", "Mã CP"]:
            if c in df.columns:
                df["Mã"] = df[c]
                break
    if "Mã" not in df.columns:
        raise ValueError("positions_v19.csv thiếu cột Mã")
    df["Mã"] = df["Mã"].astype(str).str.upper().str.strip()

    defaults = {
        "Ngày mua": "",
        "Giá vốn": 0,
        "Số lượng": 0,
        "Tỷ trọng hiện tại %": 0,
        "Số lần mua thêm": 0,
        "Giá cao nhất từ khi mua": 0,
        "Stop hiện tại": "",
        "Ghi chú": "",
        # Vietnam settlement inventory layer:
        # KL_T0/KL_T1/KL_T2 are informational buckets. Only KL_Bán_Được is treated as sellable quantity.
        "KL_T0": 0,
        "KL_T1": 0,
        "KL_T2": 0,
        "KL_Bán_Được": 0,
    }
    for c, default in defaults.items():
        if c not in df.columns:
            if c == "Số lần mua thêm" and "Số lần add" in df.columns:
                df[c] = df["Số lần add"]
            else:
                df[c] = default

    for c in [
        "Giá vốn", "Số lượng", "Tỷ trọng hiện tại %", "Số lần mua thêm", "Giá cao nhất từ khi mua",
        "KL_T0", "KL_T1", "KL_T2", "KL_Bán_Được"
    ]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    df["Số lần mua thêm"] = df["Số lần mua thêm"].astype(int)
    return df


def normalize_history(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    date_col = find_col(out, ["time", "date", "Date", "datetime", "TradingDate", "Ngày"])
    close_col = find_col(out, ["close", "Close", "adj_close", "price", "Giá đóng cửa"])
    high_col = find_col(out, ["high", "High", "Giá cao nhất"])
    low_col = find_col(out, ["low", "Low", "Giá thấp nhất"])
    open_col = find_col(out, ["open", "Open", "Giá mở cửa"])
    vol_col = find_col(out, ["volume", "Volume", "vol", "Khối lượng"])
    if close_col is None:
        return pd.DataFrame()

    out["date_norm"] = pd.to_datetime(out[date_col], errors="coerce") if date_col else pd.RangeIndex(start=0, stop=len(out), step=1)
    out["close"] = pd.to_numeric(out[close_col], errors="coerce").apply(normalize_price)
    out["high"] = pd.to_numeric(out[high_col], errors="coerce").apply(normalize_price) if high_col else out["close"]
    out["low"] = pd.to_numeric(out[low_col], errors="coerce").apply(normalize_price) if low_col else out["close"]
    out["open"] = pd.to_numeric(out[open_col], errors="coerce").apply(normalize_price) if open_col else out["close"]
    out["volume"] = pd.to_numeric(out[vol_col], errors="coerce").fillna(0) if vol_col else 0
    out = out.dropna(subset=["close"]).copy()
    return out.sort_values("date_norm").reset_index(drop=True)[["date_norm", "open", "high", "low", "close", "volume"]]


def load_history(symbol: str) -> pd.DataFrame:
    candidates = [
        os.path.join(CACHE_DIR, f"{symbol}.csv"),
        os.path.join(CACHE_DIR, f"{symbol.upper()}.csv"),
        f"{symbol}.csv",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return normalize_history(read_csv_smart(p))
            except Exception as e:
                log(f"Lỗi đọc cache {p}: {repr(e)}")
    return pd.DataFrame()


def get_intraday_price_vnstock(symbol: str) -> Dict[str, Any]:
    symbol = str(symbol).upper().strip()
    try:
        from vnstock import Vnstock
        stock = Vnstock().stock(symbol=symbol, source="VCI")
        q = getattr(stock, "quote", None)
        if q is not None and hasattr(q, "intraday"):
            df = q.intraday(page_size=50)
            if df is not None and not df.empty:
                price_col = find_col(df, ["price", "match_price", "last_price", "close", "Close"])
                time_col = find_col(df, ["time", "datetime", "tradingDate", "date"])
                if price_col:
                    px = pd.to_numeric(df[price_col], errors="coerce").dropna()
                    if len(px):
                        price = normalize_price(px.iloc[-1])
                        price_time = str(df[time_col].iloc[-1]) if time_col else now_str()
                        return {
                            "price": price,
                            "price_source": "intraday",
                            "price_time": price_time,
                            "realtime_ok": True,
                            "price_note": "Giá lấy từ intraday vnstock/VCI",
                        }
    except Exception as e:
        log(f"WARN intraday price {symbol}: {repr(e)}")

    return {
        "price": None,
        "price_source": "intraday_failed",
        "price_time": now_str(),
        "realtime_ok": False,
        "price_note": "Không lấy được giá intraday",
    }


def compute_atr(df: pd.DataFrame) -> float:
    if df is None or df.empty or len(df) < 2:
        return 0.0
    h = pd.to_numeric(df["high"], errors="coerce")
    l = pd.to_numeric(df["low"], errors="coerce")
    c = pd.to_numeric(df["close"], errors="coerce")
    prev_c = c.shift(1)
    tr = pd.concat([(h - l).abs(), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    atr = tr.rolling(ATR_PERIOD).mean().iloc[-1]
    if pd.isna(atr):
        atr = tr.tail(ATR_PERIOD).mean()
    return float(atr) if not pd.isna(atr) else 0.0


def latest_metrics(symbol: str) -> Dict[str, Any]:
    hist = load_history(symbol)

    if hist.empty:
        base = {
            "current": None, "ma5": None, "ma20": None, "atr": 0.0, "atr_pct": 0.0,
            "swing_low": None, "swing_high": None, "trend": "KHÔNG CÓ DỮ LIỆU",
            "volume_ratio_20": None, "price_source": "no_history", "price_time": now_str(),
            "realtime_ok": False, "price_note": "Không có cache lịch sử",
        }
        if in_market_time():
            intr = get_intraday_price_vnstock(symbol)
            base.update({"current": intr["price"], "price_source": intr["price_source"], "price_time": intr["price_time"], "realtime_ok": intr["realtime_ok"], "price_note": intr["price_note"]})
        return base

    close = pd.to_numeric(hist["close"], errors="coerce").dropna()
    hist_current = normalize_price(close.iloc[-1]) if len(close) else None
    price_info = {
        "price": hist_current,
        "price_source": "history_cache",
        "price_time": str(hist["date_norm"].iloc[-1]) if len(hist) else "",
        "realtime_ok": False,
        "price_note": "Giá từ cache/history, có thể trễ so với app chứng khoán",
    }

    if in_market_time():
        intr = get_intraday_price_vnstock(symbol)
        if intr.get("price") is not None:
            price_info = intr
        else:
            price_info["price_source"] = "history_cache_fallback"
            price_info["price_note"] = "Intraday fail, dùng cache để tham khảo; KHÔNG dùng để bán mạnh"

    current = normalize_price(price_info.get("price"))
    ma5 = float(close.tail(5).mean()) if len(close) >= 5 else float(close.mean())
    ma20 = float(close.tail(20).mean()) if len(close) >= 20 else float(close.mean())
    atr = compute_atr(hist)
    atr_pct = (atr / current * 100) if current and current > 0 else 0.0
    swing_low = normalize_price(hist["low"].tail(SWING_LOOKBACK).min())
    swing_high = normalize_price(hist["high"].tail(SWING_LOOKBACK).max())

    vol = pd.to_numeric(hist["volume"], errors="coerce").fillna(0)
    volume_ratio_20 = None
    if len(vol) >= 20 and vol.tail(20).mean() > 0:
        volume_ratio_20 = float(vol.iloc[-1] / vol.tail(20).mean())

    if current is None:
        trend = "KHÔNG CÓ DỮ LIỆU"
    elif current >= ma5 >= ma20:
        trend = "XU HƯỚNG TỐT"
    elif current >= ma20:
        trend = "TRÊN MA20"
    else:
        trend = "DƯỚI MA20"

    return {
        "current": current, "ma5": round(ma5, 3), "ma20": round(ma20, 3),
        "atr": round(atr, 3), "atr_pct": round(atr_pct, 3),
        "swing_low": swing_low, "swing_high": swing_high, "trend": trend,
        "volume_ratio_20": round(volume_ratio_20, 3) if volume_ratio_20 is not None else None,
        "price_source": price_info.get("price_source", ""),
        "price_time": price_info.get("price_time", ""),
        "realtime_ok": bool(price_info.get("realtime_ok", False)),
        "price_note": price_info.get("price_note", ""),
    }


def watchlist_info(watchlist: pd.DataFrame, symbol: str) -> Dict[str, Any]:
    if watchlist is None or watchlist.empty or "Mã" not in watchlist.columns:
        return {}
    m = watchlist[watchlist["Mã"].astype(str).str.upper().str.strip() == symbol]
    if m.empty:
        return {}
    row = m.iloc[0]
    return {
        "final_decision": safe_str(row.get("Final Decision", row.get("Hành động", "")), "UNKNOWN"),
        "decision_mode": safe_str(row.get("Decision Mode", ""), "UNKNOWN"),
        "meta_alloc": to_num(row.get("Meta Allocation %", 0.0)),
        "meta_exposure": to_num(row.get("Meta Exposure", 0.0)),
        "regime": safe_str(row.get("Regime Strength", ""), "UNKNOWN"),
        "equity": safe_str(row.get("Equity State", ""), "UNKNOWN"),
        "priority": safe_str(row.get("Ưu tiên", ""), "UNKNOWN"),
        "realtime_group": safe_str(row.get("Nhóm realtime", ""), "UNKNOWN"),
        "sector": safe_str(row.get("Sector", row.get("Ngành", "")), "UNKNOWN"),
    }


def parse_buy_date(x: Any) -> Optional[pd.Timestamp]:
    try:
        s = str(x).strip()
        if not s:
            return None
        dt = pd.to_datetime(s, errors="coerce")
        if pd.isna(dt):
            dt = pd.to_datetime(s, errors="coerce", dayfirst=True)
        if pd.isna(dt):
            return None
        return pd.Timestamp(dt).normalize()
    except Exception:
        return None


def is_sellable_vn(buy_date_value: Any) -> Tuple[bool, str, Optional[float], str]:
    buy_dt = parse_buy_date(buy_date_value)
    if buy_dt is None:
        return True, "Không có Ngày mua nên không kiểm tra được T+2.5", None, ""
    today = pd.Timestamp(now_dt().date())
    holding_days = float(max((today - buy_dt).days, 0))
    sellable_dt = buy_dt + pd.Timedelta(days=VN_TPLUS_SELLABLE_DAYS)
    sellable_date = sellable_dt.strftime("%Y-%m-%d")
    if holding_days >= VN_TPLUS_SELLABLE_DAYS:
        return True, "Đã đủ điều kiện bán theo T+2.5", holding_days, sellable_date
    return False, "CHƯA BÁN ĐƯỢC - chưa đủ T+2.5", holding_days, sellable_date


def pnl_pct(current: Optional[float], entry: float) -> float:
    if current is None or entry <= 0:
        return 0.0
    return (current / entry - 1.0) * 100.0


def build_smart_stop(entry: float, current: Optional[float], highest: float, current_stop: Optional[float], metrics: Dict[str, Any]) -> Dict[str, Any]:
    if current is None or entry <= 0:
        return {"Stop đề xuất": current_stop, "Loại stop chính": "KHÔNG CÓ GIÁ", "Hard Stop": None, "ATR Stop": None, "MA20 Stop": None, "Swing Low Stop": None, "Trailing Stop": None}
    p = pnl_pct(current, entry)
    atr = to_num(metrics.get("atr", 0))
    ma20 = metrics.get("ma20")
    swing_low = metrics.get("swing_low")
    hard_stop = entry * (1 - HARD_STOP_PCT / 100)
    atr_stop = current - ATR_STOP_MULTIPLIER * atr if atr > 0 else None
    ma20_stop = ma20 * (1 - MA20_BUFFER_PCT / 100) if ma20 is not None and ma20 > 0 else None
    swing_stop = swing_low * (1 - SWING_BUFFER_PCT / 100) if swing_low is not None and swing_low > 0 else None
    breakeven_stop = entry if p >= BREAKEVEN_TRIGGER_PCT else None
    trailing_stop = highest - ATR_STOP_MULTIPLIER * atr if p >= TRAIL_TRIGGER_PCT and highest > 0 and atr > 0 else None
    candidates = [("Hard Stop", hard_stop)]
    for name, value in [("ATR Stop", atr_stop), ("MA20 Stop", ma20_stop), ("Swing Low Stop", swing_stop), ("Stop hiện tại", current_stop), ("Stop hòa vốn", breakeven_stop), ("Trailing Stop", trailing_stop)]:
        if value is not None and value > 0:
            candidates.append((name, value))
    best_name, best_value = max(candidates, key=lambda x: x[1])
    return {
        "Hard Stop": round(hard_stop, 3),
        "ATR Stop": round(atr_stop, 3) if atr_stop is not None else None,
        "MA20 Stop": round(ma20_stop, 3) if ma20_stop is not None else None,
        "Swing Low Stop": round(swing_stop, 3) if swing_stop is not None else None,
        "Trailing Stop": round(trailing_stop, 3) if trailing_stop is not None else None,
        "Stop đề xuất": round(best_value, 3),
        "Loại stop chính": best_name,
    }


def portfolio_heat(positions: pd.DataFrame) -> float:
    if positions is None or positions.empty or "Tỷ trọng hiện tại %" not in positions.columns:
        return 0.0
    return float(pd.to_numeric(positions["Tỷ trọng hiện tại %"], errors="coerce").fillna(0).sum())


def can_add(p: float, add_count: int, alloc: float, meta_alloc: float, mode: str, final: str, trend: str, heat: float) -> Tuple[bool, str]:
    if normalize_text(mode) in BLOCK_ADD_MODES:
        return False, f"Không mua thêm vì Chế độ đánh = {mode}"
    if normalize_text(final) not in ["BUY NOW", "WATCHLIST"]:
        return False, "Không mua thêm vì Quyết định cuối không ủng hộ"
    if add_count >= MAX_ADD_COUNT:
        return False, "Đã đủ số lần mua thêm tối đa"
    if p < MIN_ADD_PROFIT_PCT:
        return False, "Chưa đủ lãi để mua thêm an toàn"
    if alloc >= MAX_POSITION_ALLOCATION_PCT:
        return False, "Tỷ trọng mã đã chạm giới hạn"
    if meta_alloc > 0 and alloc >= meta_alloc:
        return False, "Tỷ trọng hiện tại đã >= tỷ trọng meta"
    if trend not in ["XU HƯỚNG TỐT", "TRÊN MA20"]:
        return False, "Xu hướng chưa đủ tốt để mua thêm"
    if heat >= MAX_PORTFOLIO_HEAT_PCT:
        return False, "Độ nóng danh mục quá cao"
    return True, "Đủ điều kiện mua thêm nhỏ"


def decide_state_action(p: float, current: Optional[float], stop: Optional[float], trend: str, final: str, mode: str, add_ok: bool) -> Tuple[str, str]:
    final_u = normalize_text(final)
    mode_u = normalize_text(mode)
    if current is not None and stop is not None and current <= stop:
        return "CHẠM STOP THÔNG MINH", "THOÁT VỊ THẾ"
    if final_u in ["AVOID", "BỎ QUA", "REDUCE", "GIẢM"]:
        return "UPSTREAM YÊU CẦU GIẢM/THOÁT", "GIẢM VỊ THẾ"
    if mode_u == "CASH MODE":
        return "CASH MODE - GIẢM RỦI RO", "GIẢM VỊ THẾ"
    if p >= PROFIT_TAKE_2_PCT:
        return "LÃI LỚN - ƯU TIÊN KHÓA LÃI", "CHỐT MẠNH"
    if p >= PROFIT_TAKE_1_PCT:
        return "LÃI TỐT - CHỐT MỘT PHẦN", "CHỐT BỚT NHẸ"
    if add_ok:
        return "ĐỦ ĐIỀU KIỆN MUA THÊM NHỎ", "MUA THÊM NHỎ"
    if trend in ["XU HƯỚNG TỐT", "TRÊN MA20"] and p > 0:
        return "GIỮ THEO TREND", "GIỮ"
    if trend == "DƯỚI MA20":
        return "YẾU - THEO DÕI GIẢM", "THEO DÕI VỊ THẾ"
    return "GIỮ / THEO DÕI", "THEO DÕI VỊ THẾ"


def constrain_tplus(action: str, sellable: bool) -> str:
    if not sellable and action in SELL_ACTIONS:
        return "CHƯA BÁN ĐƯỢC - THEO DÕI RỦI RO"
    return action


def apply_price_guard(action: str, raw_action: str, metrics: Dict[str, Any]) -> Tuple[str, str]:
    if PRICE_GUARD_ON and in_market_time() and BLOCK_SELL_IF_NOT_INTRADAY and raw_action in SELL_ACTIONS and not bool(metrics.get("realtime_ok", False)):
        return "KIỂM TRA GIÁ TRƯỚC KHI BÁN", (
            f"Price Guard: đang trong giờ thị trường nhưng nguồn giá = {metrics.get('price_source')}; "
            "không xác nhận bán mạnh nếu chưa có giá intraday realtime."
        )
    return action, ""


def alert_priority(action: str) -> int:
    return {
        "THOÁT VỊ THẾ": 5, "CẮT LỖ": 5,
        "KIỂM TRA GIÁ TRƯỚC KHI BÁN": 4, "GIẢM VỊ THẾ": 4, "GIẢM TỶ TRỌNG": 4,
        "CHỐT MẠNH": 4, "CHƯA BÁN ĐƯỢC - THEO DÕI RỦI RO": 4,
        "THOÁT KHI CÓ THANH KHOẢN": 4, "NÂNG TRAILING": 3,
        "CHỐT BỚT NHẸ": 3, "MUA THÊM NHỎ": 3,
        "GIỮ CÓ KIỂM SOÁT": 2, "GIỮ": 1, "THEO DÕI VỊ THẾ": 1,
    }.get(action, 1)


def explain_action(action: str) -> str:
    return {
        "THOÁT VỊ THẾ": "Bán thoát vị thế nếu đã đủ T+2.5 và giá realtime xác nhận",
        "GIẢM VỊ THẾ": "Giảm tỷ trọng nếu đã đủ T+2.5",
        "CHỐT MẠNH": "Chốt lời mạnh",
        "CHỐT BỚT NHẸ": "Chốt lời một phần",
        "MUA THÊM NHỎ": "Có thể mua thêm nhỏ nếu đúng kế hoạch vốn",
        "GIỮ": "Tiếp tục giữ",
        "THEO DÕI VỊ THẾ": "Theo dõi vị thế, chưa hành động mạnh",
        "CHƯA BÁN ĐƯỢC - THEO DÕI RỦI RO": "Chưa đủ T+2.5 nên chưa bán được; chỉ theo dõi rủi ro",
        "KIỂM TRA GIÁ TRƯỚC KHI BÁN": "Giá chưa được xác nhận realtime; kiểm tra app chứng khoán trước khi bán",
        "THOÁT KHI CÓ THANH KHOẢN": "Có tín hiệu bán nhưng thanh khoản/giá sàn không thuận lợi; ưu tiên thoát khi có lực cầu",
        "NÂNG TRAILING": "Đang có lãi, ưu tiên nâng trailing stop/bảo vệ lợi nhuận",
        "GIỮ CÓ KIỂM SOÁT": "Đang lãi, tiếp tục giữ nhưng quản trị stop chặt",
        "GIẢM TỶ TRỌNG": "Giảm một phần để hạ rủi ro",
        "CẮT LỖ": "Cắt lỗ nếu hàng đã về và thanh khoản cho phép",
    }.get(action, "Theo dõi")


def reason_text(action: str, raw_action: str, p: float, trend: str, stop_type: str, tplus_note: str, state: str, price_guard_note: str = "") -> str:
    if price_guard_note:
        return price_guard_note + f"; tín hiệu gốc là {raw_action}"
    if action == "CHƯA BÁN ĐƯỢC - THEO DÕI RỦI RO":
        return f"{tplus_note}; tín hiệu gốc là {raw_action}"
    if action == "THOÁT VỊ THẾ":
        return f"{state}; stop chính: {stop_type}; ưu tiên bảo vệ vốn"
    if action == "GIẢM VỊ THẾ":
        return f"{state}; upstream risk đang xấu"
    if action in ["CHỐT MẠNH", "CHỐT BỚT NHẸ"]:
        return f"Lãi {p:.2f}%, nên khóa lợi nhuận"
    if action == "MUA THÊM NHỎ":
        return f"Lãi {p:.2f}%, xu hướng {trend}, đủ điều kiện mua thêm nhỏ"
    if action == "GIỮ":
        return f"Xu hướng {trend}, tiếp tục giữ"
    return "Chưa có tín hiệu hành động mạnh"


def emoji_for_action(action: str) -> str:
    if action == "THOÁT VỊ THẾ":
        return "🔴"
    if action == "KIỂM TRA GIÁ TRƯỚC KHI BÁN":
        return "🟠"
    if action == "THOÁT KHI CÓ THANH KHOẢN":
        return "🟠"
    if action in ["CẮT LỖ", "GIẢM TỶ TRỌNG"]:
        return "🔴"
    if action == "NÂNG TRAILING":
        return "🟠"
    if action in ["GIẢM VỊ THẾ", "CHỐT MẠNH", "CHỐT BỚT NHẸ"]:
        return "⚠️"
    if action == "MUA THÊM NHỎ":
        return "🟢"
    if action == "CHƯA BÁN ĐƯỢC - THEO DÕI RỦI RO":
        return "⛔"
    if action in ["GIỮ", "GIỮ CÓ KIỂM SOÁT"]:
        return "🟡"
    return "⚪"


def build_position_rows(positions: pd.DataFrame, watchlist: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    heat = portfolio_heat(positions)
    rows, alerts = [], []

    for _, pos in positions.iterrows():
        symbol = safe_str(pos.get("Mã", "")).upper()
        if not symbol:
            continue

        entry = to_num(pos.get("Giá vốn", 0))
        qty = to_num(pos.get("Số lượng", 0))
        buy_date = safe_str(pos.get("Ngày mua", ""))
        alloc = to_num(pos.get("Tỷ trọng hiện tại %", 0))
        add_count = int(to_num(pos.get("Số lần mua thêm", pos.get("Số lần add", 0))))
        highest = to_num(pos.get("Giá cao nhất từ khi mua", 0))
        current_stop = normalize_price(pos.get("Stop hiện tại", None))

        # Vietnam T+ inventory buckets. Only KL_Bán_Được is truly sellable.
        kl_t0 = to_num(pos.get("KL_T0", 0))
        kl_t1 = to_num(pos.get("KL_T1", 0))
        kl_t2 = to_num(pos.get("KL_T2", 0))
        sellable_qty = to_num(
            pos.get(
                "KL_Bán_Được",
                pos.get("Khối lượng bán được", pos.get("available_qty", 0))
            )
        )
        sellable_ratio = round((sellable_qty / qty * 100.0), 2) if qty and qty > 0 else 0.0

        metrics = latest_metrics(symbol)
        current = metrics["current"]
        if current is not None:
            highest = max(highest, current)

        p = pnl_pct(current, entry)
        info = watchlist_info(watchlist, symbol)
        stop_pack = build_smart_stop(entry, current, highest, current_stop, metrics)

        add_ok, add_reason = can_add(
            p, add_count, alloc, info.get("meta_alloc", 0.0),
            info.get("decision_mode", "UNKNOWN"), info.get("final_decision", "UNKNOWN"),
            metrics["trend"], heat
        )

        sector_dict: Dict[str, Any] = {}
        sector_note = ""
        if VN_SECTOR_FLOW_ON:
            try:
                sector_flow = evaluate_sector_money_flow(symbol, watchlist_df=watchlist, cache_dir=CACHE_DIR)
                sector_dict = sector_flow.to_dict()
                add_ok, add_reason = adjust_add_by_sector(add_ok, add_reason, sector_flow)
                sector_note = sector_dict.get("note", "")
            except Exception as e:
                sector_note = f"Không chạy được Sector Money Flow: {repr(e)}"

        state, raw_action = decide_state_action(
            p, current, stop_pack["Stop đề xuất"], metrics["trend"],
            info.get("final_decision", "UNKNOWN"), info.get("decision_mode", "UNKNOWN"), add_ok
        )

        sellable_by_date, tplus_note, holding_days, sellable_date = is_sellable_vn(buy_date)
        sellable = bool(sellable_by_date and sellable_qty > 0)
        if sellable_by_date and qty > 0 and sellable_qty <= 0:
            tplus_note = f"{tplus_note}; KL_Bán_Được = 0 nên chưa có khối lượng bán thực tế"
        elif not sellable_by_date:
            tplus_note = f"{tplus_note}; cổ phiếu vẫn đang ở T0/T1/T2"
        action = constrain_tplus(raw_action, sellable)
        action, price_guard_note = apply_price_guard(action, raw_action, metrics)

        safety_dict: Dict[str, Any] = {}
        safety_note = ""
        if VN_TRADE_SAFETY_ON:
            try:
                safety = evaluate_entry_safety(symbol, current, None, CACHE_DIR)
                safety_dict = safety.to_dict()
                action, safety_note = adjust_exit_action(action, current, None, safety)
            except Exception as e:
                safety_note = f"Không chạy được VN Trade Safety: {repr(e)}"

        position_state_dict: Dict[str, Any] = {}
        position_state_note = ""
        if VN_POSITION_STATE_ON:
            try:
                available_qty = sellable_qty
                ps = classify_position_state(
                    qty=qty,
                    pnl_pct=p,
                    current_price=current,
                    stop_price=stop_pack["Stop đề xuất"],
                    sellable=sellable,
                    holding_days=holding_days,
                    available_qty=available_qty,
                    safety=safety_dict,
                )
                position_state_dict = ps.to_dict()
                action, position_state_note = adjust_action_by_position_state(action, raw_action, ps, pnl_pct=p, add_ok=add_ok)
            except Exception as e:
                position_state_note = f"Không chạy được Position State: {repr(e)}"

        reason = reason_text(action, raw_action, p, metrics["trend"], stop_pack["Loại stop chính"], tplus_note, state, price_guard_note)
        if safety_note:
            reason = (reason + "; " if reason else "") + safety_note
        if sector_note:
            reason = (reason + "; " if reason else "") + f"Sector Flow: {sector_note}"
        if position_state_note:
            reason = (reason + "; " if reason else "") + position_state_note

        row = {
            "Mã": symbol, "Ngày mua": buy_date,
            "Số ngày giữ ước tính": round(holding_days, 2) if holding_days is not None else "",
            "Ngày dự kiến bán được": sellable_date,
            "Bán được chưa?": "CÓ" if sellable else "CHƯA",
            "Ghi chú T+2.5": tplus_note,
            "Số lượng": qty, "Giá vốn": round(entry, 3),
            "Giá hiện tại": current,
            "Nguồn giá": metrics.get("price_source", ""),
            "Thời gian giá": metrics.get("price_time", ""),
            "Realtime OK": "CÓ" if metrics.get("realtime_ok") else "KHÔNG",
            "Ghi chú giá": metrics.get("price_note", ""),
            "KL_T0": kl_t0,
            "KL_T1": kl_t1,
            "KL_T2": kl_t2,
            "KL_Bán_Được": sellable_qty,
            "Sellable Ratio %": sellable_ratio,
            "VN Safety Score": safety_dict.get("score", ""),
            "Thanh khoản band": safety_dict.get("liquidity_band", ""),
            "GTGD TB 20 phiên tỷ": round(safety_dict.get("avg_value_20d_bn", 0), 3) if isinstance(safety_dict.get("avg_value_20d_bn"), (int, float)) else "",
            "Exit Risk": safety_dict.get("exit_risk", ""),
            "Near Ceiling": "CÓ" if safety_dict.get("near_ceiling") else "KHÔNG",
            "Near Floor": "CÓ" if safety_dict.get("near_floor") else "KHÔNG",
            "Sector": sector_dict.get("sector", info.get("sector", "UNKNOWN")),
            "Sector Flow": sector_dict.get("status", ""),
            "Sector Score": sector_dict.get("score", ""),
            "Sector Rank": sector_dict.get("rank_in_sector", ""),
            "Sector Leaders": sector_dict.get("leaders", ""),
            "Sector Note": sector_dict.get("note", sector_note),
            "Lãi/lỗ %": round(p, 3),
            "Tỷ trọng hiện tại %": round(alloc, 3),
            "Quyết định cuối": info.get("final_decision", "UNKNOWN"),
            "Chế độ đánh": info.get("decision_mode", "UNKNOWN"),
            "Meta Allocation %": round(info.get("meta_alloc", 0.0), 3),
            "Meta Exposure": round(info.get("meta_exposure", 0.0), 4),
            "Regime": info.get("regime", "UNKNOWN"),
            "Equity State": info.get("equity", "UNKNOWN"),
            "Nhóm realtime": info.get("realtime_group", "UNKNOWN"),
            "Trạng thái xu hướng": metrics["trend"],
            "MA5": metrics["ma5"], "MA20": metrics["ma20"],
            "ATR": metrics["atr"], "ATR %": metrics["atr_pct"],
            "Swing Low": metrics["swing_low"], "Swing High": metrics["swing_high"],
            "Hard Stop": stop_pack["Hard Stop"], "ATR Stop": stop_pack["ATR Stop"],
            "MA20 Stop": stop_pack["MA20 Stop"], "Swing Low Stop": stop_pack["Swing Low Stop"],
            "Trailing Stop": stop_pack["Trailing Stop"],
            "Stop đề xuất": stop_pack["Stop đề xuất"],
            "Loại stop chính": stop_pack["Loại stop chính"],
            "Trạng thái vị thế": state,
            "Position State Code": position_state_dict.get("state_code", ""),
            "Position State": position_state_dict.get("state_label", ""),
            "Position Risk Level": position_state_dict.get("risk_level", ""),
            "Position Action Hint": position_state_dict.get("action_hint", ""),
            "Position State Reason": position_state_dict.get("reason", ""),
            "Position Can Sell": "CÓ" if position_state_dict.get("can_sell") else "KHÔNG",
            "Position Can Add": "CÓ" if position_state_dict.get("can_add") else "KHÔNG",
            "Có thể mua thêm?": "CÓ" if add_ok else "KHÔNG",
            "Lý do mua thêm": add_reason,
            "Hành động gốc": raw_action,
            "Hành động V19.2": action,
            "Kết luận dễ hiểu": explain_action(action),
            "Lý do chính": reason,
            "Độ ưu tiên cảnh báo": alert_priority(action),
            "Cập nhật lúc": now_str(),
        }

        if VN_POSITION_HEALTH_ON:
            try:
                health = calculate_position_health(
                    pnl_pct=row.get("Lãi/lỗ %", p),
                    current_price=row.get("Giá hiện tại", current),
                    stop_price=row.get("Stop đề xuất", stop_pack["Stop đề xuất"]),
                    position_state_code=row.get("Position State Code", ""),
                    position_risk_level=row.get("Position Risk Level", ""),
                    can_sell=row.get("Position Can Sell", row.get("Bán được chưa?", "")),
                    can_add=row.get("Position Can Add", ""),
                    realtime_ok=row.get("Realtime OK", ""),
                    trend=row.get("Trạng thái xu hướng", ""),
                    liquidity_band=row.get("Thanh khoản band", ""),
                    exit_risk=row.get("Exit Risk", ""),
                    near_floor=row.get("Near Floor", ""),
                    near_ceiling=row.get("Near Ceiling", ""),
                    sector_flow=row.get("Sector Flow", ""),
                    sector_score=row.get("Sector Score", ""),
                    action=row.get("Hành động V19.2", action),
                ).to_dict()
                row["Position Health Score"] = health.get("score", "")
                row["Position Health Level"] = health.get("level", "")
                row["Position Health Icon"] = health.get("health_icon", "")
                row["Position Health Verdict"] = health.get("verdict", "")
                row["Position Health Reasons"] = health.get("reasons_text", "")
                row["Position Health Reasons Bullets"] = health.get("reasons_bullets", "")
                row["Position Risk Score"] = health.get("risk_score", "")
                row["Position Risk Level"] = health.get("risk_level", "")
                row["Position Risk Icon"] = health.get("risk_icon", "")
                row["Position Health Action Icon"] = health.get("action_icon", "")
                row["Position Health Recommendation"] = health.get("recommendation_line", "")
            except Exception as e:
                row["Position Health Score"] = ""
                row["Position Health Level"] = "ERROR"
                row["Position Health Icon"] = ""
                row["Position Health Verdict"] = "Không tính được Position Health"
                row["Position Health Reasons"] = repr(e)
                row["Position Health Reasons Bullets"] = repr(e)
                row["Position Risk Score"] = ""
                row["Position Risk Level"] = ""
                row["Position Risk Icon"] = ""
                row["Position Health Action Icon"] = ""
                row["Position Health Recommendation"] = ""
        else:
            row["Position Health Score"] = ""
            row["Position Health Level"] = "OFF"
            row["Position Health Icon"] = ""
            row["Position Health Verdict"] = ""
            row["Position Health Reasons"] = ""
            row["Position Health Reasons Bullets"] = ""
            row["Position Risk Score"] = ""
            row["Position Risk Level"] = ""
            row["Position Risk Icon"] = ""
            row["Position Health Action Icon"] = ""
            row["Position Health Recommendation"] = ""

        rows.append(row)
        if action not in ["GIỮ", "THEO DÕI VỊ THẾ"] or SEND_HOLD_ALERTS:
            alerts.append(row)

    return pd.DataFrame(rows), pd.DataFrame(alerts)


def enrich_with_mini_market_regime(snapshot: pd.DataFrame, alerts: pd.DataFrame, watchlist: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """Tính Mini Market Regime một lần mỗi scan và gắn vào snapshot/alerts.

    Lớp này chỉ bổ sung context thị trường mini 138 mã, không đổi action V19.2.
    """
    if not VN_MINI_MARKET_REGIME_ON:
        regime = {
            "score": "", "regime": "OFF", "icon": "", "universe_size": len(watchlist) if watchlist is not None else 0,
            "valid_count": 0, "qualified_size": "", "qualified_valid_count": 0, "qualified_score": "",
            "qualified_regime": "OFF", "qualified_icon": "", "qualified_pct_up": "",
            "qualified_pct_above_ma20": "", "qualified_pct_above_ma50": "",
            "qualified_pct_healthy": "", "qualified_pct_very_healthy": "",
            "qualified_pct_weak": "", "qualified_money_flow_label": "",
            "qualified_money_flow_score": "", "qualified_recommendation_lines": "",
            "qualified_notes_text": "", "pct_up": "", "pct_above_ma20": "", "pct_above_ma50": "",
            "pct_healthy": "", "pct_very_healthy": "", "pct_weak": "", "pct_near_stop_proxy": "",
            "breadth_score": "", "leadership_score": "", "risk_pressure_score": "", "money_flow_score": "",
            "money_flow_label": "", "recommendation": "", "recommendation_lines": "", "notes_text": "",
        }
    else:
        try:
            regime = evaluate_mini_market_regime(
                watchlist, cache_dir=CACHE_DIR, max_symbols=MINI_MARKET_MAX_SYMBOLS
            ).to_dict()
        except Exception as e:
            regime = {
                "score": "", "regime": "ERROR", "icon": "⚠️", "universe_size": len(watchlist) if watchlist is not None else 0,
                "valid_count": 0, "qualified_size": "", "qualified_valid_count": 0, "qualified_score": "",
                "qualified_regime": "ERROR", "qualified_icon": "⚠️", "qualified_pct_up": "",
                "qualified_pct_above_ma20": "", "qualified_pct_above_ma50": "",
                "qualified_pct_healthy": "", "qualified_pct_very_healthy": "",
                "qualified_pct_weak": "", "qualified_money_flow_label": "",
                "qualified_money_flow_score": "", "qualified_recommendation_lines": "⚠️ Kiểm tra log Mini Market Regime",
                "qualified_notes_text": repr(e), "pct_up": "", "pct_above_ma20": "", "pct_above_ma50": "",
                "pct_healthy": "", "pct_very_healthy": "", "pct_weak": "", "pct_near_stop_proxy": "",
                "breadth_score": "", "leadership_score": "", "risk_pressure_score": "", "money_flow_score": "",
                "money_flow_label": "", "recommendation": "Không tính được Mini Market Regime",
                "recommendation_lines": "⚠️ Kiểm tra log Mini Market Regime", "notes_text": repr(e),
            }

    cols = {
        "Mini Market Regime": regime.get("regime", ""),
        "Mini Market Icon": regime.get("icon", ""),
        "Mini Market Score": regime.get("score", ""),
        "Mini Market Universe": regime.get("universe_size", ""),
        "Mini Market Valid Count": regime.get("valid_count", ""),
        "Mini Market Qualified": regime.get("qualified_size", ""),
        "Mini Market Qualified Valid Count": regime.get("qualified_valid_count", ""),
        "Mini Market Qualified Regime": regime.get("qualified_regime", ""),
        "Mini Market Qualified Icon": regime.get("qualified_icon", ""),
        "Mini Market Qualified Score": regime.get("qualified_score", ""),
        "Mini Market Qualified Pct Up": regime.get("qualified_pct_up", ""),
        "Mini Market Qualified Pct Above MA20": regime.get("qualified_pct_above_ma20", ""),
        "Mini Market Qualified Pct Above MA50": regime.get("qualified_pct_above_ma50", ""),
        "Mini Market Qualified Pct Healthy": regime.get("qualified_pct_healthy", ""),
        "Mini Market Qualified Pct Very Healthy": regime.get("qualified_pct_very_healthy", ""),
        "Mini Market Qualified Pct Weak": regime.get("qualified_pct_weak", ""),
        "Mini Market Qualified Money Flow": regime.get("qualified_money_flow_label", ""),
        "Mini Market Qualified Money Flow Score": regime.get("qualified_money_flow_score", ""),
        "Mini Market Qualified Recommendation Lines": regime.get("qualified_recommendation_lines", ""),
        "Mini Market Qualified Notes": regime.get("qualified_notes_text", ""),
        "Mini Market Pct Up": regime.get("pct_up", ""),
        "Mini Market Pct Above MA20": regime.get("pct_above_ma20", ""),
        "Mini Market Pct Above MA50": regime.get("pct_above_ma50", ""),
        "Mini Market Pct Healthy": regime.get("pct_healthy", ""),
        "Mini Market Pct Very Healthy": regime.get("pct_very_healthy", ""),
        "Mini Market Pct Weak": regime.get("pct_weak", ""),
        "Mini Market Breadth Score": regime.get("breadth_score", ""),
        "Mini Market Leadership Score": regime.get("leadership_score", ""),
        "Mini Market Risk Pressure Score": regime.get("risk_pressure_score", ""),
        "Mini Market Money Flow Score": regime.get("money_flow_score", ""),
        "Mini Market Money Flow": regime.get("money_flow_label", ""),
        "Mini Market Recommendation": regime.get("recommendation", ""),
        "Mini Market Recommendation Lines": regime.get("recommendation_lines", ""),
        "Mini Market Notes": regime.get("notes_text", ""),
    }

    def _add_cols(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return df
        out = df.copy()
        for k, v in cols.items():
            out[k] = v
        return out

    return _add_cols(snapshot), _add_cols(alerts), regime


def enrich_with_leader_rotation(snapshot: pd.DataFrame, alerts: pd.DataFrame, watchlist: pd.DataFrame, mini_market_regime: Optional[Dict[str, Any]] = None) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """Tính Leader Rotation Lite một lần mỗi scan và gắn vào snapshot/alerts.

    Lớp này chỉ bổ sung context dòng tiền/ngành, không đổi action V19.2.
    """
    if not VN_LEADER_ROTATION_ON:
        rotation = {
            "status": "OFF", "rotation_score": "", "rotation_icon": "",
            "raw_rotation_score": "", "market_factor": "", "adjusted_rotation_score": "",
            "universe_score": "", "sector_map_source": "",
            "mapped_universe_count": "", "mapped_qualified_count": "",
            "universe_size": "", "qualified_size": "",
            "leading_sectors": "", "weak_sectors": "",
            "universe_leaders": "", "qualified_leaders": "",
            "flow_direction": "", "notes": "", "recommendation_lines": "",
        }
    else:
        try:
            rotation = evaluate_leader_rotation(
                watchlist,
                cache_dir=CACHE_DIR,
                max_symbols=LEADER_ROTATION_MAX_SYMBOLS,
                universe_score=(mini_market_regime or {}).get("score", ""),
                sector_mapping_path=LEADER_ROTATION_SECTOR_MAPPING_PATH,
            ).to_dict()
        except Exception as e:
            rotation = {
                "status": "ERROR", "rotation_score": "", "rotation_icon": "⚠️",
                "raw_rotation_score": "", "market_factor": "", "adjusted_rotation_score": "",
                "universe_score": (mini_market_regime or {}).get("score", ""),
                "sector_map_source": "ERROR", "mapped_universe_count": "", "mapped_qualified_count": "",
                "universe_size": len(watchlist) if watchlist is not None else 0,
                "qualified_size": len(watchlist) if watchlist is not None else 0,
                "leading_sectors": "", "weak_sectors": "",
                "universe_leaders": "", "qualified_leaders": "",
                "flow_direction": "Không tính được Leader Rotation",
                "notes": repr(e),
                "recommendation_lines": "⚠️ Kiểm tra log Leader Rotation",
            }

    cols = {
        "Leader Rotation Status": rotation.get("status", ""),
        "Leader Rotation Score": rotation.get("rotation_score", ""),
        "Leader Rotation Icon": rotation.get("rotation_icon", ""),
        "Leader Rotation Raw Score": rotation.get("raw_rotation_score", ""),
        "Leader Rotation Market Factor": rotation.get("market_factor", ""),
        "Leader Rotation Adjusted Score": rotation.get("adjusted_rotation_score", ""),
        "Leader Rotation Universe Score": rotation.get("universe_score", ""),
        "Leader Rotation Sector Map Source": rotation.get("sector_map_source", ""),
        "Leader Rotation Mapped Universe": rotation.get("mapped_universe_count", ""),
        "Leader Rotation Mapped Qualified": rotation.get("mapped_qualified_count", ""),
        "Leader Rotation Universe": rotation.get("universe_size", ""),
        "Leader Rotation Qualified": rotation.get("qualified_size", ""),
        "Leading Sectors": rotation.get("leading_sectors", ""),
        "Weak Sectors": rotation.get("weak_sectors", ""),
        "Universe Leaders": rotation.get("universe_leaders", ""),
        "Qualified Leaders": rotation.get("qualified_leaders", ""),
        "Rotation Flow Direction": rotation.get("flow_direction", ""),
        "Leader Rotation Notes": rotation.get("notes", ""),
        "Leader Rotation Recommendation": rotation.get("recommendation_lines", ""),
    }

    def _add_cols(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return df
        out = df.copy()
        for k, v in cols.items():
            out[k] = v
        return out

    return _add_cols(snapshot), _add_cols(alerts), rotation


def enrich_with_institutional_flow(snapshot: pd.DataFrame, alerts: pd.DataFrame, watchlist: pd.DataFrame, positions: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """Tính Institutional Flow một lần mỗi scan và gắn vào snapshot/alerts.

    Lớp này chỉ bổ sung context dòng tiền tổ chức/ngành, không đổi action V19.2.
    """
    if not VN_INSTITUTIONAL_FLOW_ON:
        flow = {
            "status": "OFF", "icon": "", "market_flow_score": "", "market_flow_label": "",
            "sector_count": "", "symbol_count": "", "data_count": "",
            "data_last_updated": "", "data_freshness_status": "", "data_freshness_icon": "", "data_freshness_label": "", "data_age_hours": "",
            "top_sectors": "", "weak_sectors": "", "accumulation_sectors": "", "distribution_sectors": "",
            "banking_score": "", "securities_score": "", "real_estate_score": "",
            "position_sector_notes": "", "notes": "", "recommendation_lines": "",
        }
    else:
        try:
            flow = evaluate_institutional_flow(
                watchlist_df=watchlist,
                positions_df=positions,
                cache_dir=CACHE_DIR,
                sector_mapping_path=INSTITUTIONAL_FLOW_SECTOR_MAPPING_PATH,
                max_symbols=INSTITUTIONAL_FLOW_MAX_SYMBOLS,
            ).to_dict()
        except Exception as e:
            flow = {
                "status": "ERROR", "icon": "⚠️", "market_flow_score": "", "market_flow_label": "Không tính được Institutional Flow",
                "sector_count": "", "symbol_count": "", "data_count": "",
                "top_sectors": "", "weak_sectors": "", "accumulation_sectors": "", "distribution_sectors": "",
                "banking_score": "", "securities_score": "", "real_estate_score": "",
                "position_sector_notes": "", "notes": repr(e), "recommendation_lines": "⚠️ Kiểm tra log Institutional Flow",
            }

    cols = {
        "Institutional Flow Status": flow.get("status", ""),
        "Institutional Flow Icon": flow.get("icon", ""),
        "Institutional Flow Score": flow.get("market_flow_score", ""),
        "Institutional Flow Label": flow.get("market_flow_label", ""),
        "Institutional Flow Sector Count": flow.get("sector_count", ""),
        "Institutional Flow Symbol Count": flow.get("symbol_count", ""),
        "Institutional Flow Data Count": flow.get("data_count", ""),
        "Institutional Flow Last Updated": flow.get("data_last_updated", ""),
        "Institutional Flow Freshness Status": flow.get("data_freshness_status", ""),
        "Institutional Flow Freshness Icon": flow.get("data_freshness_icon", ""),
        "Institutional Flow Freshness Label": flow.get("data_freshness_label", ""),
        "Institutional Flow Data Age Hours": flow.get("data_age_hours", ""),
        "Institutional Flow Top Sectors": flow.get("top_sectors", ""),
        "Institutional Flow Weak Sectors": flow.get("weak_sectors", ""),
        "Institutional Flow Accumulation": flow.get("accumulation_sectors", ""),
        "Institutional Flow Distribution": flow.get("distribution_sectors", ""),
        "Institutional Flow Banking Score": flow.get("banking_score", ""),
        "Institutional Flow Securities Score": flow.get("securities_score", ""),
        "Institutional Flow Real Estate Score": flow.get("real_estate_score", ""),
        "Institutional Flow Position Notes": flow.get("position_sector_notes", ""),
        "Institutional Flow Notes": flow.get("notes", ""),
        "Institutional Flow Recommendation": flow.get("recommendation_lines", ""),
    }

    def _add_cols(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return df
        out = df.copy()
        for k, v in cols.items():
            out[k] = v
        return out

    return _add_cols(snapshot), _add_cols(alerts), flow


def enrich_with_market_internals(snapshot: pd.DataFrame, alerts: pd.DataFrame, positions: pd.DataFrame, institutional_flow: Optional[Dict[str, Any]] = None) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """PHASE 16 — NỘI LỰC THỊ TRƯỜNG (Market Internals).

    Chỉ bổ sung context tổng hợp, không thay đổi action mua/bán.
    Tên hiển thị ưu tiên tiếng Việt, tiếng Anh chỉ để chú thích.
    """
    if not VN_MARKET_INTERNALS_ON:
        mi = {
            "status": "OFF", "icon": "", "internal_score": "", "label_vi": "",
            "data_last_updated": "", "data_freshness_icon": "", "data_freshness_label": "", "data_age_hours": "",
            "flow_score": "", "flow_label": "", "breadth_score": "", "breadth_label": "",
            "pct_up": "", "pct_above_ma20": "", "pct_above_ma50": "",
            "participation_pct": "", "participation_label": "",
            "distribution_days_20": "", "distribution_label": "",
            "concentration_pct": "", "concentration_symbol": "", "concentration_label": "",
            "relative_strength_notes": "", "recommendation_lines": "", "notes": "",
        }
    else:
        try:
            res = evaluate_market_internals(
                snapshot_df=snapshot,
                positions_df=positions,
                institutional_flow=institutional_flow,
                cache_dir=CACHE_DIR,
            )
            mi = res.to_dict() if hasattr(res, "to_dict") else dict(res)
        except Exception as e:
            mi = {
                "status": "ERROR", "icon": "⚠️", "internal_score": "", "label_vi": "Không tính được nội lực thị trường",
                "data_last_updated": "", "data_freshness_icon": "⚪", "data_freshness_label": "Không rõ", "data_age_hours": "",
                "flow_score": "", "flow_label": "", "breadth_score": "", "breadth_label": "",
                "pct_up": "", "pct_above_ma20": "", "pct_above_ma50": "",
                "participation_pct": "", "participation_label": "",
                "distribution_days_20": "", "distribution_label": "",
                "concentration_pct": "", "concentration_symbol": "", "concentration_label": "",
                "relative_strength_notes": "", "recommendation_lines": "⚠️ Kiểm tra log Market Internals", "notes": repr(e),
            }

    cols = {
        "Market Internals Status": mi.get("status", ""),
        "Market Internals Icon": mi.get("icon", ""),
        "Market Internals Score": mi.get("internal_score", ""),
        "Market Internals Label VI": mi.get("label_vi", ""),
        "Market Internals Last Updated": mi.get("data_last_updated", ""),
        "Market Internals Freshness Icon": mi.get("data_freshness_icon", ""),
        "Market Internals Freshness Label": mi.get("data_freshness_label", ""),
        "Market Internals Age Hours": mi.get("data_age_hours", ""),
        "Market Internals Flow Score": mi.get("flow_score", ""),
        "Market Internals Flow Label": mi.get("flow_label", ""),
        "Market Internals Breadth Score": mi.get("breadth_score", ""),
        "Market Internals Breadth Label": mi.get("breadth_label", ""),
        "Market Internals Pct Up": mi.get("pct_up", ""),
        "Market Internals Above MA20": mi.get("pct_above_ma20", ""),
        "Market Internals Above MA50": mi.get("pct_above_ma50", ""),
        "Market Internals Participation Pct": mi.get("participation_pct", ""),
        "Market Internals Participation Label": mi.get("participation_label", ""),
        "Market Internals Distribution Days 20": mi.get("distribution_days_20", ""),
        "Market Internals Distribution Label": mi.get("distribution_label", ""),
        "Market Internals Concentration Pct": mi.get("concentration_pct", ""),
        "Market Internals Concentration Symbol": mi.get("concentration_symbol", ""),
        "Market Internals Concentration Label": mi.get("concentration_label", ""),
        "Market Internals RS Notes": mi.get("relative_strength_notes", ""),
        "Market Internals Recommendation": mi.get("recommendation_lines", ""),
        "Market Internals Notes": mi.get("notes", ""),
    }

    def _add_cols(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return df
        out = df.copy()
        for k, v in cols.items():
            out[k] = v
        return out

    return _add_cols(snapshot), _add_cols(alerts), mi

def enrich_with_portfolio_intelligence(snapshot: pd.DataFrame, alerts: pd.DataFrame, mini_market_regime: Optional[Dict[str, Any]] = None, leader_rotation: Optional[Dict[str, Any]] = None) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """Tính Portfolio Intelligence Engine một lần mỗi scan và gắn vào snapshot/alerts.

    PIE chỉ bổ sung context quản trị danh mục/vốn, không đổi action V19.2.
    """
    if not VN_PORTFOLIO_INTELLIGENCE_ON:
        pie = {
            "status": "OFF", "icon": "", "portfolio_health_score": "", "portfolio_health_level": "",
            "portfolio_health_icon": "", "position_count": 0, "healthy_count": 0, "warning_count": 0,
            "danger_count": 0, "critical_count": 0, "near_stop_count": 0, "exit_risk_count": 0,
            "loss_count": 0, "profit_count": 0, "current_stock_exposure_pct": "", "target_cash_pct": "",
            "target_stock_pct": "", "target_margin_pct": "", "max_new_position_pct": "", "max_position_pct": "",
            "used_risk_budget_pct": "", "max_risk_budget_pct": "", "remaining_risk_budget_pct": "",
            "drawdown_pct": "", "protection_level": "", "protection_icon": "", "exposure_reason": "",
            "risk_reason": "", "sizing_note": "", "recommendation_lines": "", "notes": "",
        }
    else:
        try:
            pie = evaluate_portfolio_intelligence(snapshot, mini_market=mini_market_regime, leader_rotation=leader_rotation).to_dict()
        except Exception as e:
            pie = {
                "status": "ERROR", "icon": "⚠️", "portfolio_health_score": "", "portfolio_health_level": "ERROR",
                "portfolio_health_icon": "⚠️", "position_count": len(snapshot) if snapshot is not None else 0,
                "healthy_count": 0, "warning_count": 0, "danger_count": 0, "critical_count": 0,
                "near_stop_count": 0, "exit_risk_count": 0, "loss_count": 0, "profit_count": 0,
                "current_stock_exposure_pct": "", "target_cash_pct": "", "target_stock_pct": "", "target_margin_pct": "",
                "max_new_position_pct": "", "max_position_pct": "", "used_risk_budget_pct": "", "max_risk_budget_pct": "",
                "remaining_risk_budget_pct": "", "drawdown_pct": "", "protection_level": "ERROR", "protection_icon": "⚠️",
                "exposure_reason": "Không tính được Portfolio Intelligence", "risk_reason": repr(e),
                "sizing_note": "Kiểm tra log PIE", "recommendation_lines": "⚠️ Kiểm tra log Portfolio Intelligence", "notes": repr(e),
            }

    cols = {
        "PIE Status": pie.get("status", ""),
        "PIE Icon": pie.get("icon", ""),
        "Portfolio Health Score": pie.get("portfolio_health_score", ""),
        "Portfolio Health Level": pie.get("portfolio_health_level", ""),
        "Portfolio Health Icon": pie.get("portfolio_health_icon", ""),
        "Portfolio Position Count": pie.get("position_count", ""),
        "Portfolio Healthy Count": pie.get("healthy_count", ""),
        "Portfolio Warning Count": pie.get("warning_count", ""),
        "Portfolio Danger Count": pie.get("danger_count", ""),
        "Portfolio Critical Count": pie.get("critical_count", ""),
        "Portfolio Near Stop Count": pie.get("near_stop_count", ""),
        "Portfolio Exit Risk Count": pie.get("exit_risk_count", ""),
        "Portfolio Loss Count": pie.get("loss_count", ""),
        "Portfolio Profit Count": pie.get("profit_count", ""),
        "Current Stock Exposure %": pie.get("current_stock_exposure_pct", ""),
        "Target Cash %": pie.get("target_cash_pct", ""),
        "Target Stock %": pie.get("target_stock_pct", ""),
        "Target Margin %": pie.get("target_margin_pct", ""),
        "Max New Position %": pie.get("max_new_position_pct", ""),
        "Max Position %": pie.get("max_position_pct", ""),
        "Used Risk Budget %": pie.get("used_risk_budget_pct", ""),
        "Max Risk Budget %": pie.get("max_risk_budget_pct", ""),
        "Remaining Risk Budget %": pie.get("remaining_risk_budget_pct", ""),
        "Portfolio Drawdown %": pie.get("drawdown_pct", ""),
        "Drawdown Protection Level": pie.get("protection_level", ""),
        "Drawdown Protection Icon": pie.get("protection_icon", ""),
        "Portfolio Exposure Reason": pie.get("exposure_reason", ""),
        "Portfolio Risk Reason": pie.get("risk_reason", ""),
        "Position Sizing Note": pie.get("sizing_note", ""),
        "Portfolio Recommendation": pie.get("recommendation_lines", ""),
        "Portfolio Intelligence Notes": pie.get("notes", ""),
    }

    def _add_cols(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return df
        out = df.copy()
        for k, v in cols.items():
            out[k] = v
        return out

    return _add_cols(snapshot), _add_cols(alerts), pie


def build_portfolio_intelligence_block(row: Dict[str, Any]) -> str:
    status = row.get("PIE Status", "")
    if not status or status == "OFF":
        return ""
    notes = row.get("Portfolio Intelligence Notes", "")
    notes_line = f"Ghi chú: {notes}\n" if notes else ""
    return (
        f"<b>📊 Portfolio Intelligence</b>\n\n"
        f"Trạng thái: <b>{row.get('PIE Icon', '')} {status}</b>\n"
        f"Portfolio Health: <b>{row.get('Portfolio Health Score', '')}/100</b> {row.get('Portfolio Health Icon', '')} {row.get('Portfolio Health Level', '')}\n"
        f"Vị thế: <b>{row.get('Portfolio Position Count', '')}</b> | Lãi: <b>{row.get('Portfolio Profit Count', '')}</b> | Lỗ: <b>{row.get('Portfolio Loss Count', '')}</b>\n"
        f"Near Stop: <b>{row.get('Portfolio Near Stop Count', '')}</b> | Critical: <b>{row.get('Portfolio Critical Count', '')}</b> | Exit Risk: <b>{row.get('Portfolio Exit Risk Count', '')}</b>\n\n"
        f"Exposure đề xuất:\n"
        f"Cash: <b>{row.get('Target Cash %', '')}%</b> | Stock: <b>{row.get('Target Stock %', '')}%</b> | Margin: <b>{row.get('Target Margin %', '')}%</b>\n"
        f"Exposure hiện tại: <b>{row.get('Current Stock Exposure %', '')}%</b>\n"
        f"Lý do: {row.get('Portfolio Exposure Reason', '')}\n\n"
        f"Risk Budget:\n"
        f"Used: <b>{row.get('Used Risk Budget %', '')}%</b> / Max: <b>{row.get('Max Risk Budget %', '')}%</b> | Còn lại: <b>{row.get('Remaining Risk Budget %', '')}%</b>\n"
        f"{row.get('Portfolio Risk Reason', '')}\n\n"
        f"Position Sizing:\n"
        f"Max vị thế mới: <b>{row.get('Max New Position %', '')}% NAV</b> | Max mỗi mã: <b>{row.get('Max Position %', '')}% NAV</b>\n"
        f"{row.get('Position Sizing Note', '')}\n\n"
        f"Drawdown Protection:\n"
        f"DD: <b>{row.get('Portfolio Drawdown %', '')}%</b> | Protection: <b>{row.get('Drawdown Protection Icon', '')} {row.get('Drawdown Protection Level', '')}</b>\n\n"
        f"Khuyến nghị danh mục:\n{row.get('Portfolio Recommendation', '')}\n"
        f"{notes_line}\n"
    )


def build_market_internals_block(row: Dict[str, Any]) -> str:
    status = row.get("Market Internals Status", "")
    if not status or status == "OFF":
        return ""
    return (
        f"<b>📈 NỘI LỰC THỊ TRƯỜNG</b>\n"
        f"<i>(Market Internals)</i>\n\n"
        f"Tổng điểm: <b>{row.get('Market Internals Icon', '')} {row.get('Market Internals Score', '')}/100</b> — <b>{row.get('Market Internals Label VI', '')}</b>\n"
        f"Dữ liệu: <b>{row.get('Market Internals Last Updated', '')}</b> | "
        f"{row.get('Market Internals Freshness Icon', '')} <b>{row.get('Market Internals Freshness Label', '')}</b>"
        f" | Age: <b>{row.get('Market Internals Age Hours', '')}h</b>\n\n"
        f"🏦 <b>DÒNG TIỀN NGÀNH</b> <i>(Institutional Flow)</i>\n"
        f"Score: <b>{row.get('Market Internals Flow Score', '')}/100</b> | {row.get('Market Internals Flow Label', '')}\n\n"
        f"📊 <b>SỨC KHỎE THỊ TRƯỜNG</b> <i>(Market Breadth)</i>\n"
        f"Score: <b>{row.get('Market Internals Breadth Score', '')}/100</b> | {row.get('Market Internals Breadth Label', '')}\n"
        f"Tăng: <b>{row.get('Market Internals Pct Up', '')}%</b> | Trên MA20: <b>{row.get('Market Internals Above MA20', '')}%</b> | Trên MA50: <b>{row.get('Market Internals Above MA50', '')}%</b>\n\n"
        f"💰 <b>MỨC ĐỘ THAM GIA DÒNG TIỀN</b> <i>(Liquidity Participation)</i>\n"
        f"So với TB 20 phiên: <b>{row.get('Market Internals Participation Pct', '')}%</b> | {row.get('Market Internals Participation Label', '')}\n\n"
        f"📉 <b>PHIÊN PHÂN PHỐI</b> <i>(Distribution Day)</i>\n"
        f"20 phiên: <b>{row.get('Market Internals Distribution Days 20', '')}</b> phiên | {row.get('Market Internals Distribution Label', '')}\n\n"
        f"⚔️ <b>SỨC MẠNH TƯƠNG ĐỐI</b> <i>(Relative Strength)</i>\n"
        f"{row.get('Market Internals RS Notes', '')}\n\n"
        f"⚠️ <b>RỦI RO TẬP TRUNG DANH MỤC</b> <i>(Concentration Risk)</i>\n"
        f"Mã lớn nhất: <b>{row.get('Market Internals Concentration Symbol', '')}</b> | Tỷ trọng: <b>{row.get('Market Internals Concentration Pct', '')}%</b> | {row.get('Market Internals Concentration Label', '')}\n\n"
        f"Khuyến nghị nội lực:\n{row.get('Market Internals Recommendation', '')}\n"
        f"Ghi chú: {row.get('Market Internals Notes', '')}\n\n"
    )

def build_institutional_flow_block(row: Dict[str, Any]) -> str:
    status = row.get("Institutional Flow Status", "")
    if not status or status == "OFF":
        return ""
    return (
        f"<b>🏦 Institutional Flow Layer</b>\n\n"
        f"Trạng thái: <b>{row.get('Institutional Flow Icon', '')} {status}</b> | Score: <b>{row.get('Institutional Flow Score', '')}/100</b>\n"
        f"Nhãn: <b>{row.get('Institutional Flow Label', '')}</b>\n"
        f"Dữ liệu: <b>{row.get('Institutional Flow Data Count', '')}</b> mã hợp lệ | <b>{row.get('Institutional Flow Sector Count', '')}</b> ngành\n"
        f"Last Updated: <b>{row.get('Institutional Flow Last Updated', '')}</b> | "
        f"{row.get('Institutional Flow Freshness Icon', '')} <b>{row.get('Institutional Flow Freshness Label', '')}</b>"
        f" | Age: <b>{row.get('Institutional Flow Data Age Hours', '')}h</b>\n"
        f"Giải thích: score là dòng tiền tương đối theo giá + breadth + volume, không phải kết luận tiền lớn mua/bán thật. Nếu chưa có dữ liệu hôm nay, bot dùng dữ liệu gần nhất có sẵn và gắn nhãn CŨ (CHÚ Ý).\n\n"
        f"Nhóm dòng tiền mạnh:\n{row.get('Institutional Flow Top Sectors', '')}\n\n"
        f"Nhóm dòng tiền yếu:\n{row.get('Institutional Flow Weak Sectors', '')}\n\n"
        f"Vị thế đang nắm theo flow ngành:\n{row.get('Institutional Flow Position Notes', '')}\n\n"
        f"Khuyến nghị Flow:\n{row.get('Institutional Flow Recommendation', '')}\n"
        f"Ghi chú: {row.get('Institutional Flow Notes', '')}\n\n"
    )

def build_leader_rotation_block(row: Dict[str, Any]) -> str:
    status = row.get("Leader Rotation Status", "")
    if not status or status == "OFF":
        return ""
    icon = row.get("Leader Rotation Icon", "")
    raw_score = row.get("Leader Rotation Raw Score", "")
    factor = row.get("Leader Rotation Market Factor", "")
    adjusted_score = row.get("Leader Rotation Adjusted Score", row.get("Leader Rotation Score", ""))
    universe_score = row.get("Leader Rotation Universe Score", "")
    notes = row.get("Leader Rotation Notes", "")
    notes_line = f"Ghi chú: {notes}\n" if notes else ""
    return (
        f"<b>🔥 Leader Rotation Lite 9.1 + 9.2</b>\n\n"
        f"Trạng thái: <b>{icon} {status}</b>\n"
        f"Raw Rotation: <b>{raw_score}/100</b>\n"
        f"Market Factor: <b>{factor}</b> từ Universe Score <b>{universe_score}/100</b>\n"
        f"Adjusted Rotation: <b>{adjusted_score}/100</b>\n\n"
        f"Universe: <b>{row.get('Leader Rotation Universe', '')} mã</b> | Qualified: <b>{row.get('Leader Rotation Qualified', '')} mã</b>\n"
        f"Sector Map: <b>{row.get('Leader Rotation Sector Map Source', '')}</b> | Mapped: <b>{row.get('Leader Rotation Mapped Universe', '')}/{row.get('Leader Rotation Universe', '')}</b> universe, <b>{row.get('Leader Rotation Mapped Qualified', '')}/{row.get('Leader Rotation Qualified', '')}</b> qualified\n\n"
        f"Ngành dẫn dắt:\n{row.get('Leading Sectors', '')}\n\n"
        f"Ngành suy yếu:\n{row.get('Weak Sectors', '')}\n\n"
        f"Leader Universe:\n{row.get('Universe Leaders', '')}\n\n"
        f"Leader Qualified:\n{row.get('Qualified Leaders', '')}\n\n"
        f"Dòng tiền:\n{row.get('Rotation Flow Direction', '')}\n\n"
        f"Khuyến nghị Lite:\n{row.get('Leader Rotation Recommendation', '')}\n"
        f"{notes_line}\n"
    )

def build_mini_market_block(row: Dict[str, Any]) -> str:
    regime = row.get("Mini Market Regime", "")
    if not regime or regime == "OFF":
        return ""

    universe = row.get("Mini Market Universe", "")
    qualified = row.get("Mini Market Qualified", "")
    score = row.get("Mini Market Score", "")
    icon = row.get("Mini Market Icon", "")
    q_score = row.get("Mini Market Qualified Score", "")
    q_icon = row.get("Mini Market Qualified Icon", "")
    q_regime = row.get("Mini Market Qualified Regime", "")
    rec_lines = row.get("Mini Market Recommendation Lines", "") or row.get("Mini Market Recommendation", "")
    q_rec_lines = row.get("Mini Market Qualified Recommendation Lines", "")
    notes = row.get("Mini Market Notes", "")
    q_notes = row.get("Mini Market Qualified Notes", "")
    notes_line = f"Ghi chú Universe: {notes}\n" if notes else ""
    q_notes_line = f"Ghi chú Qualified: {q_notes}\n" if q_notes else ""

    return (
        f"<b>🌏 Mini Market Regime</b>\n\n"
        f"Universe gốc: <b>{universe} mã</b> | Qualified sau lọc: <b>{qualified} mã</b>\n\n"
        f"<b>1) Universe - Tổng thể {universe} mã</b>\n"
        f"Trạng thái: <b>{icon} {regime}</b> | Điểm: <b>{score}/100</b>\n"
        f"Breadth: {row.get('Mini Market Pct Up', '')}% tăng | {row.get('Mini Market Pct Above MA20', '')}% trên MA20 | {row.get('Mini Market Pct Above MA50', '')}% trên MA50\n"
        f"Leadership: {row.get('Mini Market Pct Healthy', '')}% khỏe | Risk Pressure: {row.get('Mini Market Pct Weak', '')}% yếu\n"
        f"Money Flow: <b>{row.get('Mini Market Money Flow', '')}</b> | Score: <b>{row.get('Mini Market Money Flow Score', '')}</b>\n"
        f"{notes_line}\n"
        f"<b>2) Qualified - Nhóm sau lọc {qualified} mã</b>\n"
        f"Trạng thái: <b>{q_icon} {q_regime}</b> | Điểm: <b>{q_score}/100</b>\n"
        f"Breadth: {row.get('Mini Market Qualified Pct Up', '')}% tăng | {row.get('Mini Market Qualified Pct Above MA20', '')}% trên MA20 | {row.get('Mini Market Qualified Pct Above MA50', '')}% trên MA50\n"
        f"Leadership: {row.get('Mini Market Qualified Pct Healthy', '')}% khỏe | Risk Pressure: {row.get('Mini Market Qualified Pct Weak', '')}% yếu\n"
        f"Money Flow: <b>{row.get('Mini Market Qualified Money Flow', '')}</b> | Score: <b>{row.get('Mini Market Qualified Money Flow Score', '')}</b>\n"
        f"{q_notes_line}\n"
        f"Khuyến nghị theo Universe:\n{rec_lines}\n"
        f"Khuyến nghị Qualified:\n{q_rec_lines}\n\n"
    )


def build_position_health_block(row: Dict[str, Any]) -> str:
    level = row.get("Position Health Level", "")
    if not level or level == "OFF":
        return ""
    reasons = row.get("Position Health Reasons Bullets", "") or row.get("Position Health Reasons", "")
    recommendation = row.get("Position Health Recommendation", "")
    if not recommendation:
        recommendation = f"{row.get('Position Health Action Icon', '')} {row.get('Hành động V19.2', '')}".strip()
    return (
        f"<b>🩺 Position Health</b>\n\n"
        f"Sức khỏe: <b>{row.get('Position Health Score', '')}/100</b> {row.get('Position Health Icon', '')} {row.get('Position Health Level', '')}\n"
        f"Rủi ro: <b>{row.get('Position Risk Score', '')}/100</b> {row.get('Position Risk Icon', '')} {row.get('Position Risk Level', '')}\n\n"
        f"Nguyên nhân:\n{reasons}\n\n"
        f"Khuyến nghị:\n{recommendation}\n\n"
    )


def build_alert_message(row: Dict[str, Any]) -> str:
    symbol, action = row.get("Mã", ""), row.get("Hành động V19.2", "")
    emoji = emoji_for_action(action)
    return (
        f"{emoji} <b>[V19.2 POSITION]</b> <b>{symbol}</b>\n\n"
        f"<b>KẾT LUẬN:</b>\n<b>{action}</b>\n\n"
        f"<b>DỄ HIỂU:</b> {row.get('Kết luận dễ hiểu', '')}\n"
        f"<b>LÝ DO:</b> {row.get('Lý do chính', '')}\n\n"
        f"<b>Position State:</b>\n"
        f"Trạng thái: <b>{row.get('Position State Code', '')}</b> - {row.get('Position State', '')}\n"
        f"Risk Level: <b>{row.get('Position Risk Level', '')}</b>\n"
        f"Hành động: <b>{row.get('Position Action Hint', '')}</b>\n"
        f"Bán được: <b>{row.get('Position Can Sell', '')}</b> | Mua thêm: <b>{row.get('Position Can Add', '')}</b>\n"
        f"Lý do: {row.get('Position State Reason', '')}\n\n"
        f"{build_position_health_block(row)}"
        f"{build_mini_market_block(row)}"
        f"{build_leader_rotation_block(row)}"
        f"{build_institutional_flow_block(row)}"
        f"{build_market_internals_block(row)}"
        f"{build_portfolio_intelligence_block(row)}"
        f"<b>Vị thế:</b>\n"
        f"Giá vốn: <b>{row.get('Giá vốn', '')}</b>\n"
        f"Giá hiện tại: <b>{row.get('Giá hiện tại', '')}</b>\n"
        f"Lãi/lỗ: <b>{row.get('Lãi/lỗ %', '')}%</b>\n"
        f"Tỷ trọng: <b>{row.get('Tỷ trọng hiện tại %', '')}%</b>\n\n"
        f"<b>Kiểm tra giá:</b>\n"
        f"Nguồn giá: <b>{row.get('Nguồn giá', '')}</b>\n"
        f"Realtime OK: <b>{row.get('Realtime OK', '')}</b>\n"
        f"Thời gian giá: <b>{row.get('Thời gian giá', '')}</b>\n"
        f"Ghi chú giá: {row.get('Ghi chú giá', '')}\n\n"
        f"<b>VN Trade Safety:</b>\n"
        f"Thanh khoản: <b>{row.get('Thanh khoản band', '')}</b> | GTGD 20p: <b>{row.get('GTGD TB 20 phiên tỷ', '')} tỷ/ngày</b>\n"
        f"Exit Risk: <b>{row.get('Exit Risk', '')}</b> | Safety Score: <b>{row.get('VN Safety Score', '')}</b>\n"
        f"Gần trần: <b>{row.get('Near Ceiling', '')}</b> | Gần sàn: <b>{row.get('Near Floor', '')}</b>\n\n"
        f"<b>Sector Money Flow:</b>\n"
        f"Ngành: <b>{row.get('Sector', '')}</b> | Flow: <b>{row.get('Sector Flow', '')}</b> | Score: <b>{row.get('Sector Score', '')}</b>\n"
        f"Rank: <b>{row.get('Sector Rank', '')}</b> | Leader: <b>{row.get('Sector Leaders', '')}</b>\n"
        f"Ghi chú: {row.get('Sector Note', '')}\n\n"
        f"<b>Stop thông minh:</b>\n"
        f"Stop đề xuất: <b>{row.get('Stop đề xuất', '')}</b>\n"
        f"Loại stop: <b>{row.get('Loại stop chính', '')}</b>\n"
        f"Trend: <b>{row.get('Trạng thái xu hướng', '')}</b>\n\n"
        f"<b>T+2.5:</b>\n"
        f"Bán được chưa: <b>{row.get('Bán được chưa?', '')}</b>\n"
        f"Ngày dự kiến bán được: <b>{row.get('Ngày dự kiến bán được', '')}</b>\n"
        f"Ghi chú: {row.get('Ghi chú T+2.5', '')}\n\n"
        f"<b>T+ Inventory:</b>\n"
        f"T0: <b>{row.get('KL_T0', 0)}</b> | T1: <b>{row.get('KL_T1', 0)}</b> | T2: <b>{row.get('KL_T2', 0)}</b>\n"
        f"Bán được: <b>{row.get('KL_Bán_Được', 0)}</b> | Sellable Ratio: <b>{row.get('Sellable Ratio %', 0)}%</b>\n\n"
        f"<b>Upstream Risk:</b>\n"
        f"Final: <b>{row.get('Quyết định cuối', '')}</b> | Mode: <b>{row.get('Chế độ đánh', '')}</b>\n"
        f"Meta Allocation: <b>{row.get('Meta Allocation %', '')}%</b> | Meta Exposure: <b>{row.get('Meta Exposure', '')}</b>\n\n"
        f"Time: {now_str()}"
    )


def build_startup_message(snapshot: pd.DataFrame, alerts: pd.DataFrame) -> str:
    symbols = snapshot["Mã"].tolist() if not snapshot.empty and "Mã" in snapshot.columns else []
    counts = snapshot["Hành động V19.2"].value_counts().to_dict() if not snapshot.empty else {}

    # PHASE 15.2 — show Institutional Flow in startup summary too.
    # Previously the layer was loaded and available in detailed position alerts only;
    # this made the STARTED message show only "Sector Money Flow: ON" without details.
    institutional_flow_startup_block = ""
    market_internals_startup_block = ""
    try:
        if not snapshot.empty:
            first_row = snapshot.iloc[0].to_dict()
            institutional_flow_startup_block = build_institutional_flow_block(first_row)
            market_internals_startup_block = build_market_internals_block(first_row)
    except Exception as e:
        institutional_flow_startup_block = f"\n⚠️ Không dựng được Institutional Flow/Market Internals startup block: {repr(e)}\n"

    return (
        f"✅ <b>[V19.2 POSITION]</b> STARTED\n"
        f"Version: <b>{SYSTEM_VERSION}</b>\n"
        f"Mode: <b>{'RUN ONCE' if RUN_ONCE else 'REALTIME LOOP'}</b>\n"
        f"Positions: <b>{len(snapshot)}</b>\n"
        f"Tickers: <b>{', '.join(symbols)}</b>\n"
        f"Action Counts: <b>{counts}</b>\n"
        f"Alerts this scan: <b>{len(alerts)}</b>\n"
        f"T+2.5: <b>ON</b>\n"
        f"Smart Stop: <b>ON</b>\n"
        f"Price Guard: <b>{'ON' if PRICE_GUARD_ON else 'OFF'}</b>\n"
        f"VN Trade Safety: <b>{'ON' if VN_TRADE_SAFETY_ON else 'OFF'}</b>\n"
        f"Position State: <b>{'ON' if VN_POSITION_STATE_ON else 'OFF'}</b>\n"
        f"Position State Telegram Block: <b>ON</b>\n"
        f"Position Health Score: <b>{'ON' if VN_POSITION_HEALTH_ON else 'OFF'}</b>\n"
        f"Mini Market Regime: <b>{'ON' if VN_MINI_MARKET_REGIME_ON else 'OFF'}</b>\n"
        f"Leader Rotation Lite: <b>{'ON' if VN_LEADER_ROTATION_ON else 'OFF'}</b>\n"
        f"Portfolio Intelligence: <b>{'ON' if VN_PORTFOLIO_INTELLIGENCE_ON else 'OFF'}</b>\n"
        f"Vietnam Settlement Inventory: <b>ON</b>\n"
        f"Sector Money Flow: <b>{'ON' if VN_SECTOR_FLOW_ON else 'OFF'}</b>\n"
        f"Market Internals: <b>{'ON' if VN_MARKET_INTERNALS_ON else 'OFF'}</b>\n"
        f"Time: {now_str()}\n\n"
        f"{institutional_flow_startup_block}"
        f"{market_internals_startup_block}"
    )


def write_outputs(snapshot: pd.DataFrame, alerts: pd.DataFrame) -> None:
    snapshot.to_csv(OUTPUT_SNAPSHOT, index=False, encoding="utf-8-sig")
    alerts.to_csv(OUTPUT_ALERTS, index=False, encoding="utf-8-sig")
    lines = [
        "=" * 80,
        "V19.2.1 — REALTIME POSITION TELEGRAM DESK + PRICE GUARD",
        "=" * 80,
        f"Generated: {now_str()}",
        f"Positions: {len(snapshot)}",
        f"Alerts: {len(alerts)}",
        "",
        "=== TÓM TẮT HÀNH ĐỘNG ===",
    ]
    if not snapshot.empty:
        for k, v in snapshot["Hành động V19.2"].value_counts().to_dict().items():
            lines.append(f"- {k}: {v}")
    else:
        lines.append("Không có vị thế.")
    lines += [
        "",
        "=== PRICE GUARD ===",
        "Trong giờ thị trường, nếu không lấy được giá intraday realtime, V19.2.1 không cho bán mạnh.",
        "Telegram sẽ hiện Nguồn giá, Realtime OK, Thời gian giá.",
    ]
    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def scan_once(state: Dict[str, Any], startup: bool = False) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    watchlist = load_watchlist()
    positions = load_positions()

    if positions.empty:
        snapshot, alerts = pd.DataFrame(), pd.DataFrame()
        write_outputs(snapshot, alerts)
        if startup and SEND_STARTUP_SUMMARY:
            send_telegram("⚠️ <b>[V19.2 POSITION]</b> Không có positions_v19.csv hoặc file rỗng.")
        return snapshot, alerts, state

    snapshot, alerts = build_position_rows(positions, watchlist)
    snapshot, alerts, mini_market_regime = enrich_with_mini_market_regime(snapshot, alerts, watchlist)
    snapshot, alerts, leader_rotation = enrich_with_leader_rotation(snapshot, alerts, watchlist, mini_market_regime)
    snapshot, alerts, institutional_flow = enrich_with_institutional_flow(snapshot, alerts, watchlist, positions)
    snapshot, alerts, market_internals = enrich_with_market_internals(snapshot, alerts, positions, institutional_flow)
    snapshot, alerts, portfolio_intelligence = enrich_with_portfolio_intelligence(snapshot, alerts, mini_market_regime, leader_rotation)
    write_outputs(snapshot, alerts)

    if startup and SEND_STARTUP_SUMMARY:
        send_telegram(build_startup_message(snapshot, alerts))

    for _, row in alerts.iterrows():
        symbol = safe_str(row.get("Mã", ""))
        action = safe_str(row.get("Hành động V19.2", ""))
        if not symbol or not action:
            continue

        if cooldown_ok(state, symbol, action):
            msg = build_alert_message(row.to_dict())
            send_telegram(msg)
            log_position_alert(
                symbol=symbol, alert_type=action, price=row.get("Giá hiện tại", ""),
                message=msg, position_qty=row.get("Số lượng", ""),
                position_avg_price=row.get("Giá vốn", ""),
                stoploss=row.get("Stop đề xuất", ""),
                decision_mode=row.get("Chế độ đánh", ""),
                market_regime=row.get("Regime", ""),
                reason=row.get("Lý do chính", ""),
            )
            sync_journal_to_github()
            mark_alert(state, symbol, action)
        else:
            log(f"Cooldown: {symbol}:{action}")

    return snapshot, alerts, state


def main():
    log(f"START {SYSTEM_VERSION}")
    log(f"RUN_ONCE={RUN_ONCE}, LOOP_INTERVAL_SEC={LOOP_INTERVAL_SEC}")
    log(f"POSITIONS_PATH={POSITIONS_PATH}, WATCHLIST_PATH={WATCHLIST_PATH}")
    log(f"PRICE_GUARD_ON={PRICE_GUARD_ON}, BLOCK_SELL_IF_NOT_INTRADAY={BLOCK_SELL_IF_NOT_INTRADAY}")
    state = load_state()

    if RUN_ONCE:
        scan_once(state, startup=True)
        return

    first = True
    while True:
        try:
            if in_market_time():
                scan_once(state, startup=first)
                first = False
            else:
                log(f"Outside market time {now_str()}")
                if first:
                    scan_once(state, startup=True)
                    first = False
        except Exception as e:
            log(f"ERROR LOOP: {repr(e)}")
            send_telegram(f"⚠️ <b>[V19.2 POSITION]</b> Lỗi scanner: <code>{repr(e)}</code>")
        time.sleep(LOOP_INTERVAL_SEC)


if __name__ == "__main__":
    main()
