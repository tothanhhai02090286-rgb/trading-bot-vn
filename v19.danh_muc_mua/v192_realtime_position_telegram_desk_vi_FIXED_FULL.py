# -*- coding: utf-8 -*-
"""
v192_realtime_position_telegram_desk_vi.py

V19.2 — REALTIME POSITION TELEGRAM DESK
(V19.2 — Bàn quản lý vị thế realtime qua Telegram)

Vai trò:
- KHÔNG thay thế V18.2.
- V18.2 vẫn gửi tín hiệu ENTRY (điểm mua / thị trường / mua thêm).
- V19.2 chỉ quản lý các mã đang giữ trong positions_v19.csv.
- Telegram của V19.2 có nhãn rõ: [V19.2 POSITION]
- Tích hợp rule T+2.5: chưa đủ ngày bán thì không báo bán thật.

Input:
- positions_v19.csv
- intraday_watchlist_v17.csv
- cache_stock/*.csv

Output:
- v192_position_snapshot.csv
- v192_position_alerts.csv
- v192_position_report.txt
- v192_position_alert_state.json

Env quan trọng:
- TELEGRAM_TOKEN
- TELEGRAM_CHAT_ID
- V192_RUN_ONCE=1              chạy một lần rồi thoát, phù hợp GitHub Actions
- V192_RUN_ONCE=0              chạy loop realtime, phù hợp Render/Mac
- V192_LOOP_INTERVAL_SEC=120
"""

from __future__ import annotations

import os
import time
import json
import warnings
from datetime import datetime, time as dtime
from typing import Dict, Any, Optional, Tuple, List, Set

import numpy as np
import pandas as pd
import requests
import sys
sys.path.append("/opt/render/project/src/v19.3_alert_lichsu_canhbao")

from v193_alert_journal_layer import log_position_alert

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

warnings.filterwarnings("ignore")

SYSTEM_VERSION = "V19.2_REALTIME_POSITION_TELEGRAM_DESK_VI"

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

# Smart stop config
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

BLOCK_ADD_MODES = {"CASH MODE", "ĐÁNH RẤT NHỎ"}


# ============================================================
# BASIC UTILS
# ============================================================

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
    return (
        parse_hhmm(MARKET_START) <= t <= parse_hhmm(MARKET_END)
        and not (parse_hhmm(LUNCH_START) <= t < parse_hhmm(LUNCH_END))
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


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(text: str) -> bool:
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        log("Thiếu TELEGRAM_TOKEN hoặc TELEGRAM_CHAT_ID")
        return False

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
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


# ============================================================
# LOAD INPUTS
# ============================================================

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
    }

    for c, default in defaults.items():
        if c not in df.columns:
            if c == "Số lần mua thêm" and "Số lần add" in df.columns:
                df[c] = df["Số lần add"]
            else:
                df[c] = default

    for c in ["Giá vốn", "Số lượng", "Tỷ trọng hiện tại %", "Số lần mua thêm", "Giá cao nhất từ khi mua"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    df["Số lần mua thêm"] = df["Số lần mua thêm"].astype(int)

    return df


# ============================================================
# DATA / METRICS
# ============================================================

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
    out = out.sort_values("date_norm").reset_index(drop=True)

    return out[["date_norm", "open", "high", "low", "close", "volume"]]


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
        return {
            "current": None,
            "ma5": None,
            "ma20": None,
            "atr": 0.0,
            "atr_pct": 0.0,
            "swing_low": None,
            "swing_high": None,
            "trend": "KHÔNG CÓ DỮ LIỆU",
            "volume_ratio_20": None,
        }

    close = pd.to_numeric(hist["close"], errors="coerce").dropna()
    current = normalize_price(close.iloc[-1]) if len(close) else None
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
    elif current < ma20:
        trend = "DƯỚI MA20"
    else:
        trend = "TRUNG TÍNH"

    return {
        "current": current,
        "ma5": round(ma5, 3),
        "ma20": round(ma20, 3),
        "atr": round(atr, 3),
        "atr_pct": round(atr_pct, 3),
        "swing_low": swing_low,
        "swing_high": swing_high,
        "trend": trend,
        "volume_ratio_20": round(volume_ratio_20, 3) if volume_ratio_20 is not None else None,
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


# ============================================================
# T+2.5
# ============================================================

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


# ============================================================
# DECISION LOGIC
# ============================================================

def pnl_pct(current: Optional[float], entry: float) -> float:
    if current is None or entry <= 0:
        return 0.0
    return (current / entry - 1.0) * 100.0


def build_smart_stop(entry: float, current: Optional[float], highest: float, current_stop: Optional[float], metrics: Dict[str, Any]) -> Dict[str, Any]:
    if current is None or entry <= 0:
        return {
            "Hard Stop": None,
            "ATR Stop": None,
            "MA20 Stop": None,
            "Swing Low Stop": None,
            "Trailing Stop": None,
            "Stop đề xuất": current_stop,
            "Loại stop chính": "KHÔNG CÓ GIÁ",
            "Giải thích stop": "Không có giá hiện tại",
        }

    p = pnl_pct(current, entry)
    atr = to_num(metrics.get("atr", 0))
    ma20 = metrics.get("ma20")
    swing_low = metrics.get("swing_low")

    hard_stop = entry * (1 - HARD_STOP_PCT / 100)
    atr_stop = current - ATR_STOP_MULTIPLIER * atr if atr > 0 else None
    ma20_stop = ma20 * (1 - MA20_BUFFER_PCT / 100) if ma20 is not None and ma20 > 0 else None
    swing_stop = swing_low * (1 - SWING_BUFFER_PCT / 100) if swing_low is not None and swing_low > 0 else None
    breakeven_stop = entry if p >= BREAKEVEN_TRIGGER_PCT else None

    trailing_stop = None
    if p >= TRAIL_TRIGGER_PCT and highest > 0:
        trailing_stop = highest - ATR_STOP_MULTIPLIER * atr if atr > 0 else highest * 0.95

    candidates = [("Hard Stop", hard_stop)]

    for name, value in [
        ("ATR Stop", atr_stop),
        ("MA20 Stop", ma20_stop),
        ("Swing Low Stop", swing_stop),
        ("Stop hiện tại", current_stop),
        ("Stop hòa vốn", breakeven_stop),
        ("Trailing Stop", trailing_stop),
    ]:
        if value is not None and value > 0:
            candidates.append((name, value))

    best_name, best_value = max(candidates, key=lambda x: x[1])

    notes = []
    notes.append(f"Hard Stop = giá vốn -{HARD_STOP_PCT}%")
    if atr_stop is not None:
        notes.append("ATR Stop = giá hiện tại - 2 ATR")
    if ma20_stop is not None:
        notes.append("MA20 Stop = MA20 trừ buffer")
    if swing_stop is not None:
        notes.append("Swing Low Stop = đáy gần nhất trừ buffer")
    if breakeven_stop is not None:
        notes.append("Đã đủ điều kiện nâng stop về hòa vốn")
    if trailing_stop is not None:
        notes.append("Đã đủ điều kiện trailing stop")

    return {
        "Hard Stop": round(hard_stop, 3),
        "ATR Stop": round(atr_stop, 3) if atr_stop is not None else None,
        "MA20 Stop": round(ma20_stop, 3) if ma20_stop is not None else None,
        "Swing Low Stop": round(swing_stop, 3) if swing_stop is not None else None,
        "Trailing Stop": round(trailing_stop, 3) if trailing_stop is not None else None,
        "Stop đề xuất": round(best_value, 3),
        "Loại stop chính": best_name,
        "Giải thích stop": "; ".join(notes),
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


def decide_state_action(
    p: float,
    current: Optional[float],
    stop: Optional[float],
    trend: str,
    final: str,
    mode: str,
    add_ok: bool,
) -> Tuple[str, str]:
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
    sell_actions = {"THOÁT VỊ THẾ", "GIẢM VỊ THẾ", "CHỐT BỚT NHẸ", "CHỐT MẠNH"}
    if not sellable and action in sell_actions:
        return "CHƯA BÁN ĐƯỢC - THEO DÕI RỦI RO"
    return action


def alert_priority(action: str) -> int:
    return {
        "THOÁT VỊ THẾ": 5,
        "GIẢM VỊ THẾ": 4,
        "CHỐT MẠNH": 4,
        "CHỐT BỚT NHẸ": 3,
        "MUA THÊM NHỎ": 3,
        "CHƯA BÁN ĐƯỢC - THEO DÕI RỦI RO": 4,
        "GIỮ": 1,
        "THEO DÕI VỊ THẾ": 1,
    }.get(action, 1)


def explain_action(action: str) -> str:
    return {
        "THOÁT VỊ THẾ": "Bán thoát vị thế nếu đã đủ T+2.5",
        "GIẢM VỊ THẾ": "Giảm tỷ trọng nếu đã đủ T+2.5",
        "CHỐT MẠNH": "Chốt lời mạnh, có thể giữ một phần nhỏ nếu còn trend",
        "CHỐT BỚT NHẸ": "Chốt lời một phần",
        "MUA THÊM NHỎ": "Có thể mua thêm nhỏ nếu đúng kế hoạch vốn",
        "GIỮ": "Tiếp tục giữ",
        "THEO DÕI VỊ THẾ": "Theo dõi vị thế, chưa hành động mạnh",
        "CHƯA BÁN ĐƯỢC - THEO DÕI RỦI RO": "Chưa đủ T+2.5 nên chưa bán được; chỉ theo dõi rủi ro",
    }.get(action, "Theo dõi")


def reason_text(action: str, raw_action: str, p: float, trend: str, stop_type: str, tplus_note: str, state: str) -> str:
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
    if action in ["GIẢM VỊ THẾ", "CHỐT MẠNH", "CHỐT BỚT NHẸ"]:
        return "⚠️"
    if action == "MUA THÊM NHỎ":
        return "🟢"
    if action == "CHƯA BÁN ĐƯỢC - THEO DÕI RỦI RO":
        return "⛔"
    if action == "GIỮ":
        return "🟡"
    return "⚪"


# ============================================================
# SNAPSHOT + ALERTS
# ============================================================

def build_position_rows(positions: pd.DataFrame, watchlist: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    heat = portfolio_heat(positions)
    rows = []
    alerts = []

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

        metrics = latest_metrics(symbol)
        current = metrics["current"]
        if current is not None:
            highest = max(highest, current)

        p = pnl_pct(current, entry)
        info = watchlist_info(watchlist, symbol)
        stop_pack = build_smart_stop(entry, current, highest, current_stop, metrics)

        add_ok, add_reason = can_add(
            p=p,
            add_count=add_count,
            alloc=alloc,
            meta_alloc=info.get("meta_alloc", 0.0),
            mode=info.get("decision_mode", "UNKNOWN"),
            final=info.get("final_decision", "UNKNOWN"),
            trend=metrics["trend"],
            heat=heat,
        )

        state, raw_action = decide_state_action(
            p=p,
            current=current,
            stop=stop_pack["Stop đề xuất"],
            trend=metrics["trend"],
            final=info.get("final_decision", "UNKNOWN"),
            mode=info.get("decision_mode", "UNKNOWN"),
            add_ok=add_ok,
        )

        sellable, tplus_note, holding_days, sellable_date = is_sellable_vn(buy_date)
        action = constrain_tplus(raw_action, sellable)

        reason = reason_text(action, raw_action, p, metrics["trend"], stop_pack["Loại stop chính"], tplus_note, state)

        row = {
            "Mã": symbol,
            "Ngày mua": buy_date,
            "Số ngày giữ ước tính": round(holding_days, 2) if holding_days is not None else "",
            "Ngày dự kiến bán được": sellable_date,
            "Bán được chưa?": "CÓ" if sellable else "CHƯA",
            "Ghi chú T+2.5": tplus_note,
            "Số lượng": qty,
            "Giá vốn": round(entry, 3),
            "Giá hiện tại": current,
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
            "MA5": metrics["ma5"],
            "MA20": metrics["ma20"],
            "ATR": metrics["atr"],
            "ATR %": metrics["atr_pct"],
            "Swing Low": metrics["swing_low"],
            "Swing High": metrics["swing_high"],
            "Hard Stop": stop_pack["Hard Stop"],
            "ATR Stop": stop_pack["ATR Stop"],
            "MA20 Stop": stop_pack["MA20 Stop"],
            "Swing Low Stop": stop_pack["Swing Low Stop"],
            "Trailing Stop": stop_pack["Trailing Stop"],
            "Stop đề xuất": stop_pack["Stop đề xuất"],
            "Loại stop chính": stop_pack["Loại stop chính"],
            "Trạng thái vị thế": state,
            "Có thể mua thêm?": "CÓ" if add_ok else "KHÔNG",
            "Lý do mua thêm": add_reason,
            "Hành động gốc": raw_action,
            "Hành động V19.2": action,
            "Kết luận dễ hiểu": explain_action(action),
            "Lý do chính": reason,
            "Độ ưu tiên cảnh báo": alert_priority(action),
            "Cập nhật lúc": now_str(),
        }

        rows.append(row)

        if action not in ["GIỮ", "THEO DÕI VỊ THẾ"] or SEND_HOLD_ALERTS:
            alerts.append(row)

    snapshot = pd.DataFrame(rows)
    alerts_df = pd.DataFrame(alerts)

    return snapshot, alerts_df


def build_alert_message(row: Dict[str, Any]) -> str:
    symbol = row.get("Mã", "")
    action = row.get("Hành động V19.2", "")
    emoji = emoji_for_action(action)

    msg = (
        f"{emoji} <b>[V19.2 POSITION]</b> <b>{symbol}</b>\n\n"
        f"<b>KẾT LUẬN:</b>\n"
        f"<b>{action}</b>\n\n"
        f"<b>DỄ HIỂU:</b> {row.get('Kết luận dễ hiểu', '')}\n"
        f"<b>LÝ DO:</b> {row.get('Lý do chính', '')}\n\n"
        f"<b>Vị thế:</b>\n"
        f"Giá vốn: <b>{row.get('Giá vốn', '')}</b>\n"
        f"Giá hiện tại: <b>{row.get('Giá hiện tại', '')}</b>\n"
        f"Lãi/lỗ: <b>{row.get('Lãi/lỗ %', '')}%</b>\n"
        f"Tỷ trọng: <b>{row.get('Tỷ trọng hiện tại %', '')}%</b>\n\n"
        f"<b>Stop thông minh:</b>\n"
        f"Stop đề xuất: <b>{row.get('Stop đề xuất', '')}</b>\n"
        f"Loại stop: <b>{row.get('Loại stop chính', '')}</b>\n"
        f"Trend: <b>{row.get('Trạng thái xu hướng', '')}</b>\n\n"
        f"<b>T+2.5:</b>\n"
        f"Bán được chưa: <b>{row.get('Bán được chưa?', '')}</b>\n"
        f"Ngày dự kiến bán được: <b>{row.get('Ngày dự kiến bán được', '')}</b>\n"
        f"Ghi chú: {row.get('Ghi chú T+2.5', '')}\n\n"
        f"<b>Upstream Risk:</b>\n"
        f"Final: <b>{row.get('Quyết định cuối', '')}</b> | Mode: <b>{row.get('Chế độ đánh', '')}</b>\n"
        f"Meta Allocation: <b>{row.get('Meta Allocation %', '')}%</b> | Meta Exposure: <b>{row.get('Meta Exposure', '')}</b>\n\n"
        f"Time: {now_str()}"
    )
    return msg


def build_startup_message(snapshot: pd.DataFrame, alerts: pd.DataFrame) -> str:
    symbols = snapshot["Mã"].tolist() if not snapshot.empty and "Mã" in snapshot.columns else []
    counts = snapshot["Hành động V19.2"].value_counts().to_dict() if not snapshot.empty else {}
    return (
        f"✅ <b>[V19.2 POSITION]</b> STARTED\n"
        f"Mode: <b>{'RUN ONCE' if RUN_ONCE else 'REALTIME LOOP'}</b>\n"
        f"Positions: <b>{len(snapshot)}</b>\n"
        f"Tickers: <b>{', '.join(symbols)}</b>\n"
        f"Action Counts: <b>{counts}</b>\n"
        f"Alerts this scan: <b>{len(alerts)}</b>\n"
        f"T+2.5: <b>ON</b>\n"
        f"Smart Stop: <b>ON</b>\n"
        f"Time: {now_str()}"
    )


def write_outputs(snapshot: pd.DataFrame, alerts: pd.DataFrame) -> None:
    snapshot.to_csv(OUTPUT_SNAPSHOT, index=False, encoding="utf-8-sig")
    alerts.to_csv(OUTPUT_ALERTS, index=False, encoding="utf-8-sig")

    lines = []
    lines.append("=" * 80)
    lines.append("V19.2 — REALTIME POSITION TELEGRAM DESK")
    lines.append("V19.2 — Bàn quản lý vị thế realtime qua Telegram")
    lines.append("=" * 80)
    lines.append(f"Generated: {now_str()}")
    lines.append(f"Positions: {len(snapshot)}")
    lines.append(f"Alerts: {len(alerts)}")
    lines.append("")
    lines.append("=== TÓM TẮT HÀNH ĐỘNG ===")
    if not snapshot.empty:
        for k, v in snapshot["Hành động V19.2"].value_counts().to_dict().items():
            lines.append(f"- {k}: {v}")
    else:
        lines.append("Không có vị thế.")

    lines.append("")
    lines.append("=== GIẢI THÍCH ===")
    lines.append("V18.2 ENTRY: tín hiệu điểm mua / thị trường.")
    lines.append("V19.2 POSITION: quản lý mã đang giữ.")
    lines.append("T+2.5: chưa đủ ngày thì không báo bán thật.")
    lines.append("Smart Stop: stop thông minh gồm Hard Stop, ATR Stop, MA20 Stop, Swing Low Stop, Trailing Stop.")

    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def scan_once(state: Dict[str, Any], startup: bool = False) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    watchlist = load_watchlist()
    positions = load_positions()

    if positions.empty:
        snapshot = pd.DataFrame()
        alerts = pd.DataFrame()
        write_outputs(snapshot, alerts)
        if startup and SEND_STARTUP_SUMMARY:
            send_telegram(
                "⚠️ <b>[V19.2 POSITION]</b> Không có positions_v19.csv hoặc file rỗng.\n"
                "V19.2 cần danh mục đang giữ để gửi cảnh báo vị thế."
            )
        return snapshot, alerts, state

    snapshot, alerts = build_position_rows(positions, watchlist)
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
                symbol=symbol,
                alert_type=action,
                price=row.get("Giá hiện tại", ""),
                message=msg,
                position_qty=row.get("Số lượng", ""),
                position_avg_price=row.get("Giá vốn", ""),
                stoploss=row.get("Stop đề xuất", ""),
                decision_mode=row.get("Chế độ đánh", ""),
                market_regime=row.get("Regime", ""),
                reason=row.get("Lý do chính", ""),
            )

            mark_alert(state, symbol, action)
        else:
            log(f"Cooldown: {symbol}:{action}")

    return snapshot, alerts, state


def main():
    log(f"START {SYSTEM_VERSION}")
    log(f"RUN_ONCE={RUN_ONCE}, LOOP_INTERVAL_SEC={LOOP_INTERVAL_SEC}")
    log(f"POSITIONS_PATH={POSITIONS_PATH}, WATCHLIST_PATH={WATCHLIST_PATH}")

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
