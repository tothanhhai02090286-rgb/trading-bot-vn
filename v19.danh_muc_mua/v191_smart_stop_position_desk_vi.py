# -*- coding: utf-8 -*-
"""
v191_smart_stop_position_desk_vi.py

V19.1 — SMART STOP & POSITION DESK
(V19.1 — Bộ stop thông minh và bàn quản lý vị thế)

Nâng cấp so với V19:
- Không chỉ dùng stop cố định -5%.
- Tính nhiều loại stop:
  1. Hard Stop (stop cứng theo % giá vốn)
  2. ATR Stop (stop theo biên dao động trung bình)
  3. MA20 Stop (stop theo đường trung bình 20 phiên)
  4. Swing Low Stop (stop theo đáy gần nhất)
  5. Trailing Stop (stop kéo theo khi có lãi)
- Chọn stop đề xuất theo nguyên tắc:
  + Nếu đang lỗ / risk xấu: dùng stop phòng thủ chặt hơn.
  + Nếu đang lời: nâng stop để bảo vệ lãi.
- Tích hợp rule T+2.5:
  + Chưa đủ T+2.5 thì không báo bán thật.
  + Nếu tín hiệu gốc là bán, chuyển thành: CHƯA BÁN ĐƯỢC - THEO DÕI RỦI RO.
- Nhãn hành động dùng tiếng Việt dễ đọc.

Input:
- positions_v19.csv
- intraday_watchlist_v17.csv
- cache_stock/*.csv

Output:
- v191_position_management.csv
- v191_trade_actions.csv
- v191_position_report.txt
- v191_position_dashboard.html
"""

from __future__ import annotations

import os
import warnings
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

SYSTEM_VERSION = "V19.1_SMART_STOP_POSITION_DESK_VI"

WATCHLIST_PATH = os.getenv("V19_WATCHLIST_PATH", "intraday_watchlist_v17.csv")
POSITIONS_PATH = os.getenv("V19_POSITIONS_PATH", "positions_v19.csv")
CACHE_DIR = os.getenv("CACHE_STOCK_DIR", "cache_stock")

OUTPUT_POSITION_MANAGEMENT = "v191_position_management.csv"
OUTPUT_TRADE_ACTIONS = "v191_trade_actions.csv"
OUTPUT_REPORT = "v191_position_report.txt"
OUTPUT_HTML = "v191_position_dashboard.html"
OUTPUT_STATE = "v191_position_state.csv"
OUTPUT_TEMPLATE = "positions_v19_template.csv"

# Stop config
HARD_STOP_PCT = float(os.getenv("V191_HARD_STOP_PCT", "5.0"))
ATR_PERIOD = int(os.getenv("V191_ATR_PERIOD", "14"))
ATR_STOP_MULTIPLIER = float(os.getenv("V191_ATR_STOP_MULTIPLIER", "2.0"))
SWING_LOOKBACK = int(os.getenv("V191_SWING_LOOKBACK", "10"))
SWING_BUFFER_PCT = float(os.getenv("V191_SWING_BUFFER_PCT", "0.5"))
MA20_BUFFER_PCT = float(os.getenv("V191_MA20_BUFFER_PCT", "1.0"))

BREAKEVEN_TRIGGER_PCT = float(os.getenv("V191_BREAKEVEN_TRIGGER_PCT", "2.0"))
TRAIL_TRIGGER_PCT = float(os.getenv("V191_TRAIL_TRIGGER_PCT", "5.0"))
PROFIT_TAKE_1_PCT = float(os.getenv("V191_PROFIT_TAKE_1_PCT", "7.0"))
PROFIT_TAKE_2_PCT = float(os.getenv("V191_PROFIT_TAKE_2_PCT", "12.0"))

MAX_ADD_COUNT = int(os.getenv("V191_MAX_ADD_COUNT", "2"))
MIN_ADD_PROFIT_PCT = float(os.getenv("V191_MIN_ADD_PROFIT_PCT", "3.0"))
MAX_POSITION_ALLOCATION_PCT = float(os.getenv("V191_MAX_POSITION_ALLOCATION_PCT", "15.0"))
MAX_PORTFOLIO_HEAT_PCT = float(os.getenv("V191_MAX_PORTFOLIO_HEAT_PCT", "60.0"))
MAX_SECTOR_HEAT_PCT = float(os.getenv("V191_MAX_SECTOR_HEAT_PCT", "30.0"))

VN_TPLUS_SELLABLE_DAYS = float(os.getenv("V191_VN_TPLUS_SELLABLE_DAYS", "2.5"))
BLOCK_ADD_MODES = {"CASH MODE", "ĐÁNH RẤT NHỎ"}


def log(msg: str) -> None:
    print(f"[V19.1] {msg}", flush=True)


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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


def normalize_text(x: Any) -> str:
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass
    return str(x).strip().upper()


def safe_str(x: Any, default: str = "") -> str:
    try:
        if pd.isna(x):
            return default
    except Exception:
        pass
    s = str(x).strip()
    return s if s else default


def normalize_price(x: Any) -> Optional[float]:
    v = to_num(x, default=np.nan)
    if pd.isna(v):
        return None
    if v > 1000:
        v = v / 1000.0
    return round(float(v), 3)


def find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    lower_map = {str(c).lower(): c for c in df.columns}
    for c in candidates:
        if c in df.columns:
            return c
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return None


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
    today = pd.Timestamp(datetime.now().date())
    holding_days = float(max((today - buy_dt).days, 0))
    sellable_dt = buy_dt + pd.Timedelta(days=VN_TPLUS_SELLABLE_DAYS)
    sellable_date = sellable_dt.strftime("%Y-%m-%d")
    if holding_days >= VN_TPLUS_SELLABLE_DAYS:
        return True, "Đã đủ điều kiện bán theo T+2.5", holding_days, sellable_date
    return False, "CHƯA BÁN ĐƯỢC - chưa đủ T+2.5", holding_days, sellable_date


def load_watchlist() -> pd.DataFrame:
    if not os.path.exists(WATCHLIST_PATH):
        log(f"Không tìm thấy {WATCHLIST_PATH}, chạy với watchlist rỗng.")
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


def create_positions_template() -> None:
    df = pd.DataFrame([
        {
            "Mã": "HPG",
            "Ngày mua": "2026-05-16",
            "Giá vốn": 25.5,
            "Số lượng": 1000,
            "Tỷ trọng hiện tại %": 5.0,
            "Số lần mua thêm": 0,
            "Giá cao nhất từ khi mua": 26.8,
            "Stop hiện tại": "",
            "Ghi chú": "Ví dụ mẫu - xóa dòng này khi dùng thật",
        }
    ])
    df.to_csv(OUTPUT_TEMPLATE, index=False, encoding="utf-8-sig")


def load_positions() -> Tuple[pd.DataFrame, bool]:
    if not os.path.exists(POSITIONS_PATH):
        create_positions_template()
        log(f"Không có {POSITIONS_PATH}. Đã tạo {OUTPUT_TEMPLATE}.")
        return pd.DataFrame(), True

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
    return df, False


def normalize_price_history(df: pd.DataFrame) -> pd.DataFrame:
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


def load_price_history(symbol: str) -> pd.DataFrame:
    candidates = [
        os.path.join(CACHE_DIR, f"{symbol}.csv"),
        os.path.join(CACHE_DIR, f"{symbol.upper()}.csv"),
        f"{symbol}.csv",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return normalize_price_history(read_csv_smart(p))
            except Exception as e:
                log(f"Lỗi đọc cache {p}: {repr(e)}")
    return pd.DataFrame()


def compute_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> float:
    if df is None or df.empty or len(df) < 2:
        return 0.0
    h = pd.to_numeric(df["high"], errors="coerce")
    l = pd.to_numeric(df["low"], errors="coerce")
    c = pd.to_numeric(df["close"], errors="coerce")
    prev_c = c.shift(1)
    tr = pd.concat([(h - l).abs(), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    atr = tr.rolling(period).mean().iloc[-1]
    if pd.isna(atr):
        atr = tr.tail(period).mean()
    return float(atr) if not pd.isna(atr) else 0.0


def latest_metrics(symbol: str) -> Dict[str, Any]:
    hist = load_price_history(symbol)
    if hist.empty:
        return {
            "data_ok": False,
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
        "data_ok": True,
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


def pnl_pct(current: Optional[float], entry: float) -> float:
    if current is None or entry <= 0:
        return 0.0
    return (current / entry - 1) * 100


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
            "Giải thích stop": "Không có giá hiện tại để tính stop",
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

    candidates = []

    # luôn có hard stop để bảo vệ vốn
    candidates.append(("Hard Stop", hard_stop))

    # thêm stop kỹ thuật nếu có
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

    # Nếu đang lời: chọn stop cao nhất để khóa lãi tốt hơn.
    # Nếu đang lỗ: vẫn chọn stop cao nhất hợp lệ để phòng thủ chặt.
    best_name, best_value = max(candidates, key=lambda x: x[1])

    notes = []
    notes.append(f"Hard Stop = giá vốn -{HARD_STOP_PCT}%")
    if atr_stop is not None:
        notes.append("ATR Stop = giá hiện tại - 2 ATR")
    if ma20_stop is not None:
        notes.append("MA20 Stop = MA20 trừ buffer")
    if swing_stop is not None:
        notes.append("Swing Low Stop = đáy gần nhất trừ buffer")
    if p >= BREAKEVEN_TRIGGER_PCT:
        notes.append("Đủ điều kiện nâng stop về hòa vốn")
    if p >= TRAIL_TRIGGER_PCT:
        notes.append("Đủ điều kiện trailing stop")

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


def portfolio_heat(positions: pd.DataFrame, watchlist: pd.DataFrame) -> Dict[str, Any]:
    if positions is None or positions.empty:
        return {"portfolio_heat": 0.0, "sector_heat": {}, "max_sector_heat": 0.0, "note": "Không có vị thế"}
    total = float(pd.to_numeric(positions["Tỷ trọng hiện tại %"], errors="coerce").fillna(0).sum())
    sector_heat = {}
    for _, r in positions.iterrows():
        symbol = safe_str(r.get("Mã", "")).upper()
        alloc = to_num(r.get("Tỷ trọng hiện tại %", 0))
        sector = watchlist_info(watchlist, symbol).get("sector", "UNKNOWN")
        sector_heat[sector] = sector_heat.get(sector, 0.0) + alloc
    max_sector = max(sector_heat.values()) if sector_heat else 0.0
    notes = []
    if total >= MAX_PORTFOLIO_HEAT_PCT:
        notes.append("Độ nóng danh mục cao")
    if max_sector >= MAX_SECTOR_HEAT_PCT:
        notes.append("Độ nóng ngành cao")
    if not notes:
        notes.append("Độ nóng trong ngưỡng")
    return {
        "portfolio_heat": round(total, 3),
        "sector_heat": {k: round(v, 3) for k, v in sector_heat.items()},
        "max_sector_heat": round(max_sector, 3),
        "note": "; ".join(notes),
    }


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


def decide_state_and_action(p: float, current: Optional[float], stop: Optional[float], trend: str, final: str, mode: str, add_ok: bool) -> Tuple[str, str]:
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


def build_rows(positions: pd.DataFrame, watchlist: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    heat = portfolio_heat(positions, watchlist)
    rows = []
    actions = []

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
            heat=heat["portfolio_heat"],
        )

        state, raw_action = decide_state_and_action(
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

        row = {
            "Mã": symbol,
            "Ngành": info.get("sector", "UNKNOWN"),
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
            "Tỷ trọng meta %": round(info.get("meta_alloc", 0.0), 3),
            "Quyết định cuối": info.get("final_decision", "UNKNOWN"),
            "Chế độ đánh": info.get("decision_mode", "UNKNOWN"),
            "Meta Exposure": round(info.get("meta_exposure", 0.0), 4),
            "Sức mạnh regime": info.get("regime", "UNKNOWN"),
            "Trạng thái equity": info.get("equity", "UNKNOWN"),
            "Nhóm realtime": info.get("realtime_group", "UNKNOWN"),
            "Ưu tiên": info.get("priority", "UNKNOWN"),
            "Trạng thái xu hướng": metrics["trend"],
            "MA5": metrics["ma5"],
            "MA20": metrics["ma20"],
            "ATR": metrics["atr"],
            "ATR %": metrics["atr_pct"],
            "Swing Low": metrics["swing_low"],
            "Swing High": metrics["swing_high"],
            "Volume Ratio 20": metrics["volume_ratio_20"],
            "Giá cao nhất từ khi mua": round(highest, 3),
            "Hard Stop": stop_pack["Hard Stop"],
            "ATR Stop": stop_pack["ATR Stop"],
            "MA20 Stop": stop_pack["MA20 Stop"],
            "Swing Low Stop": stop_pack["Swing Low Stop"],
            "Trailing Stop": stop_pack["Trailing Stop"],
            "Stop đề xuất": stop_pack["Stop đề xuất"],
            "Loại stop chính": stop_pack["Loại stop chính"],
            "Giải thích stop": stop_pack["Giải thích stop"],
            "Trạng thái vị thế": state,
            "Có thể mua thêm?": "CÓ" if add_ok else "KHÔNG",
            "Lý do mua thêm": add_reason,
            "Hành động gốc": raw_action,
            "Hành động V19.1": action,
            "Kết luận dễ hiểu": explain_action(action),
            "Lý do chính": reason_text(action, raw_action, p, metrics["trend"], stop_pack["Loại stop chính"], tplus_note, state),
            "Độ nóng danh mục %": heat["portfolio_heat"],
            "Độ nóng ngành lớn nhất %": heat["max_sector_heat"],
            "Ghi chú heat": heat["note"],
            "Cập nhật lúc": now_str(),
        }

        rows.append(row)
        actions.append({
            "Mã": symbol,
            "Hành động V19.1": action,
            "Hành động gốc": raw_action,
            "Kết luận dễ hiểu": explain_action(action),
            "Trạng thái vị thế": state,
            "Lãi/lỗ %": round(p, 3),
            "Stop đề xuất": stop_pack["Stop đề xuất"],
            "Loại stop chính": stop_pack["Loại stop chính"],
            "Bán được chưa?": "CÓ" if sellable else "CHƯA",
            "Ghi chú T+2.5": tplus_note,
            "Lý do chính": row["Lý do chính"],
            "Cập nhật lúc": now_str(),
        })

    return pd.DataFrame(rows), pd.DataFrame(actions), heat


def build_report(mgmt: pd.DataFrame, actions: pd.DataFrame, heat: Dict[str, Any], no_positions: bool) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append("V19.1 — SMART STOP & POSITION DESK")
    lines.append("V19.1 — Bộ stop thông minh và bàn quản lý vị thế")
    lines.append("=" * 80)
    lines.append(f"Version: {SYSTEM_VERSION}")
    lines.append(f"Generated: {now_str()}")
    lines.append("")
    lines.append("=== DỊCH DỄ HIỂU ===")
    lines.append("V19.1 không chọn mã mới. V19.1 quản lý mã đang giữ.")
    lines.append("Stop đề xuất không còn chỉ là -5%, mà so sánh Hard Stop, ATR Stop, MA20 Stop, Swing Low Stop và Trailing Stop.")
    lines.append("V19.1 vẫn khóa bán nếu chưa đủ T+2.5.")
    lines.append("")
    lines.append("=== ĐỘ NÓNG DANH MỤC ===")
    lines.append(f"Độ nóng danh mục: {heat.get('portfolio_heat', 0)}%")
    lines.append(f"Độ nóng ngành lớn nhất: {heat.get('max_sector_heat', 0)}%")
    lines.append(f"Ghi chú: {heat.get('note', '')}")
    lines.append(f"Độ nóng ngành: {heat.get('sector_heat', {})}")

    if no_positions:
        lines.append("")
        lines.append("=== CHƯA CÓ FILE VỊ THẾ ===")
        lines.append(f"Không tìm thấy {POSITIONS_PATH}. Đã tạo {OUTPUT_TEMPLATE}.")
        return "\n".join(lines)

    lines.append("")
    lines.append("=== TÓM TẮT HÀNH ĐỘNG ===")
    if actions.empty:
        lines.append("Không có vị thế để phân tích.")
    else:
        for k, v in actions["Hành động V19.1"].value_counts().to_dict().items():
            lines.append(f"- {k}: {v} mã")

    lines.append("")
    lines.append("=== CHI TIẾT HÀNH ĐỘNG ===")
    if not actions.empty:
        for _, r in actions.iterrows():
            lines.append(
                f"◆ {r['Mã']} | {r['Hành động V19.1']} | "
                f"Lãi/lỗ: {r['Lãi/lỗ %']}% | "
                f"Stop: {r['Stop đề xuất']} ({r['Loại stop chính']}) | "
                f"Bán được: {r['Bán được chưa?']} | "
                f"Lý do: {r['Lý do chính']}"
            )

    lines.append("")
    lines.append("=== GIẢI THÍCH THUẬT NGỮ ===")
    lines.append("Hard Stop (stop cứng): mức dừng lỗ theo % giá vốn.")
    lines.append("ATR Stop (stop theo ATR): stop dựa trên biên dao động trung bình.")
    lines.append("MA20 Stop (stop theo MA20): stop dựa trên đường trung bình 20 phiên.")
    lines.append("Swing Low Stop (stop theo đáy gần nhất): stop dưới đáy gần nhất.")
    lines.append("Trailing Stop (stop kéo theo): stop nâng lên khi cổ phiếu có lãi.")
    lines.append("T+2.5 (thời gian bán được): sau khi mua cần chờ khoảng T+2.5 mới bán được.")

    return "\n".join(lines)


def build_html(mgmt: pd.DataFrame, actions: pd.DataFrame, report: str) -> str:
    actions_html = actions.to_html(index=False) if not actions.empty else "<p>Không có hành động.</p>"
    mgmt_html = mgmt.to_html(index=False) if not mgmt.empty else "<p>Không có vị thế.</p>"
    return f"""
<html>
<head>
<meta charset="utf-8">
<title>V19.1 Smart Stop Position Desk</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 20px; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 24px; font-size: 13px; }}
th, td {{ border: 1px solid #ccc; padding: 6px; text-align: center; }}
th {{ background: #f0f0f0; }}
.box {{ background: #f7f7f7; border: 1px solid #ddd; padding: 12px; margin-bottom: 20px; }}
pre {{ white-space: pre-wrap; }}
</style>
</head>
<body>
<h1>V19.1 — Bộ stop thông minh và bàn quản lý vị thế</h1>
<div class="box">
V19.1 quản lý mã đang giữ, dùng nhiều loại stop và có rule T+2.5.
</div>
<h2>Hành động V19.1</h2>
{actions_html}
<h2>Chi tiết vị thế</h2>
{mgmt_html}
<h2>Báo cáo</h2>
<pre>{report}</pre>
</body>
</html>
"""


def run_engine():
    log("Bắt đầu chạy V19.1 Smart Stop Position Desk...")
    watchlist = load_watchlist()
    positions, no_positions = load_positions()

    if no_positions:
        heat = {"portfolio_heat": 0.0, "sector_heat": {}, "max_sector_heat": 0.0, "note": "Chưa có vị thế"}
        mgmt = pd.DataFrame()
        actions = pd.DataFrame()
    else:
        mgmt, actions, heat = build_rows(positions, watchlist)

    mgmt.to_csv(OUTPUT_POSITION_MANAGEMENT, index=False, encoding="utf-8-sig")
    actions.to_csv(OUTPUT_TRADE_ACTIONS, index=False, encoding="utf-8-sig")

    state_cols = [
        "Mã", "Ngày mua", "Bán được chưa?", "Giá vốn", "Giá hiện tại",
        "Lãi/lỗ %", "Stop đề xuất", "Loại stop chính", "Trạng thái vị thế",
        "Hành động V19.1", "Cập nhật lúc"
    ]
    if not mgmt.empty:
        mgmt[[c for c in state_cols if c in mgmt.columns]].to_csv(OUTPUT_STATE, index=False, encoding="utf-8-sig")
    else:
        pd.DataFrame(columns=state_cols).to_csv(OUTPUT_STATE, index=False, encoding="utf-8-sig")

    report = build_report(mgmt, actions, heat, no_positions)
    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        f.write(report)

    html = build_html(mgmt, actions, report)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(report)
    log("Hoàn tất V19.1.")
    return mgmt, actions


if __name__ == "__main__":
    run_engine()
