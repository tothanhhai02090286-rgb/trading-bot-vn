# -*- coding: utf-8 -*-
"""
v19_position_trade_management_engine_vi.py

V19 — POSITION & TRADE MANAGEMENT ENGINE
(V19 — Bộ quản lý vị thế và vòng đời lệnh)

Vai trò:
- V19 KHÔNG phải signal scanner (không phải bot quét tín hiệu mới).
- V19 KHÔNG tự override V15.5 / V16 / V17.1 / V18.2.
- V19 đọc trạng thái upstream risk từ V17.1/V18.2 và quản lý vị thế sau khi có lệnh.
- V19 giúp trả lời:
  "Đang giữ mã này thì nên GIỮ, ADD, REDUCE, EXIT hay TRAIL STOP như thế nào?"

Input chính:
1. intraday_watchlist_v17.csv
   - File watchlist đã qua V17.1/V18.2, có Final Decision / Decision Mode / Meta Allocation % nếu có.

2. positions_v19.csv
   - Nhật ký vị thế hiện tại do người dùng hoặc hệ thống nhập.
   - Nếu chưa có file này, V19 tự tạo file mẫu positions_v19_template.csv.

3. cache_stock/*.csv
   - Dữ liệu giá lịch sử để tính MA5/MA20, ATR, trailing stop.

Output:
- v19_position_management.csv
- v19_trade_actions.csv
- v19_position_state.csv
- v19_position_report.txt
- v19_position_dashboard.html
- positions_v19_template.csv nếu chưa có positions_v19.csv
"""

from __future__ import annotations

import os
import warnings
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

SYSTEM_VERSION = "V19_POSITION_TRADE_MANAGEMENT_ENGINE_VI_FULL_BUILD"

WATCHLIST_PATH = os.getenv("V19_WATCHLIST_PATH", "intraday_watchlist_v17.csv")
POSITIONS_PATH = os.getenv("V19_POSITIONS_PATH", "positions_v19.csv")
CACHE_DIR = os.getenv("CACHE_STOCK_DIR", "cache_stock")

OUTPUT_POSITION_MANAGEMENT = "v19_position_management.csv"
OUTPUT_TRADE_ACTIONS = "v19_trade_actions.csv"
OUTPUT_POSITION_STATE = "v19_position_state.csv"
OUTPUT_REPORT = "v19_position_report.txt"
OUTPUT_HTML = "v19_position_dashboard.html"
OUTPUT_TEMPLATE = "positions_v19_template.csv"

DEFAULT_ATR_PERIOD = int(os.getenv("V19_ATR_PERIOD", "14"))
INITIAL_STOP_PCT = float(os.getenv("V19_INITIAL_STOP_PCT", "5.0"))
BREAKEVEN_TRIGGER_PCT = float(os.getenv("V19_BREAKEVEN_TRIGGER_PCT", "2.0"))
TRAIL_TRIGGER_PCT = float(os.getenv("V19_TRAIL_TRIGGER_PCT", "5.0"))
PROFIT_TAKE_1_PCT = float(os.getenv("V19_PROFIT_TAKE_1_PCT", "7.0"))
PROFIT_TAKE_2_PCT = float(os.getenv("V19_PROFIT_TAKE_2_PCT", "12.0"))

MAX_ADD_COUNT = int(os.getenv("V19_MAX_ADD_COUNT", "2"))
MAX_POSITION_ALLOCATION_PCT = float(os.getenv("V19_MAX_POSITION_ALLOCATION_PCT", "15.0"))
MAX_PORTFOLIO_HEAT_PCT = float(os.getenv("V19_MAX_PORTFOLIO_HEAT_PCT", "60.0"))
MAX_SECTOR_HEAT_PCT = float(os.getenv("V19_MAX_SECTOR_HEAT_PCT", "30.0"))
MIN_ADD_PROFIT_PCT = float(os.getenv("V19_MIN_ADD_PROFIT_PCT", "3.0"))

BLOCK_ADD_MODES = {"CASH MODE", "ĐÁNH RẤT NHỎ"}


def log(msg: str) -> None:
    print(f"[V19] {msg}", flush=True)


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
    if df is None or df.empty:
        return None
    lower_map = {str(c).lower(): c for c in df.columns}
    for c in candidates:
        if c in df.columns:
            return c
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return None


def create_positions_template() -> pd.DataFrame:
    template = pd.DataFrame([
        {
            "Mã": "HPG",
            "Số lượng": 1000,
            "Giá vốn": 25.5,
            "Ngày mua": "2026-05-16",
            "Tỷ trọng hiện tại %": 5.0,
            "Số lần add": 0,
            "Giá cao nhất từ khi mua": 26.8,
            "Stop hiện tại": "",
            "Ghi chú": "Ví dụ mẫu - xóa dòng này khi dùng thật",
        }
    ])
    template.to_csv(OUTPUT_TEMPLATE, index=False, encoding="utf-8-sig")
    return template


def load_watchlist() -> pd.DataFrame:
    if not os.path.exists(WATCHLIST_PATH):
        log(f"Không tìm thấy {WATCHLIST_PATH}. V19 vẫn chạy với watchlist rỗng.")
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


def load_positions() -> Tuple[pd.DataFrame, bool]:
    if not os.path.exists(POSITIONS_PATH):
        log(f"Không có {POSITIONS_PATH}. Tạo template {OUTPUT_TEMPLATE}.")
        create_positions_template()
        return pd.DataFrame(), True

    df = read_csv_smart(POSITIONS_PATH)

    if "Mã" not in df.columns:
        for c in ["Ma", "Symbol", "Ticker", "ticker", "Mã CP"]:
            if c in df.columns:
                df["Mã"] = df[c]
                break

    if "Mã" not in df.columns:
        raise ValueError("positions_v19.csv thiếu cột Mã.")

    df["Mã"] = df["Mã"].astype(str).str.upper().str.strip()

    defaults = {
        "Số lượng": 0,
        "Giá vốn": 0,
        "Ngày mua": "",
        "Tỷ trọng hiện tại %": 0,
        "Số lần add": 0,
        "Giá cao nhất từ khi mua": 0,
        "Stop hiện tại": "",
        "Ghi chú": "",
    }

    for c, default in defaults.items():
        if c not in df.columns:
            df[c] = default

    df["Số lượng"] = pd.to_numeric(df["Số lượng"], errors="coerce").fillna(0)
    df["Giá vốn"] = pd.to_numeric(df["Giá vốn"], errors="coerce").fillna(0)
    df["Tỷ trọng hiện tại %"] = pd.to_numeric(df["Tỷ trọng hiện tại %"], errors="coerce").fillna(0)
    df["Số lần add"] = pd.to_numeric(df["Số lần add"], errors="coerce").fillna(0).astype(int)
    df["Giá cao nhất từ khi mua"] = pd.to_numeric(df["Giá cao nhất từ khi mua"], errors="coerce").fillna(0)

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

    if date_col:
        out["date_norm"] = pd.to_datetime(out[date_col], errors="coerce")
    else:
        out["date_norm"] = pd.RangeIndex(start=0, stop=len(out), step=1)

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


def compute_atr(df: pd.DataFrame, period: int = DEFAULT_ATR_PERIOD) -> float:
    if df is None or df.empty or len(df) < 2:
        return 0.0

    h = pd.to_numeric(df["high"], errors="coerce")
    l = pd.to_numeric(df["low"], errors="coerce")
    c = pd.to_numeric(df["close"], errors="coerce")
    prev_c = c.shift(1)

    tr = pd.concat([
        (h - l).abs(),
        (h - prev_c).abs(),
        (l - prev_c).abs(),
    ], axis=1).max(axis=1)

    atr = tr.rolling(period).mean().iloc[-1]

    if pd.isna(atr):
        atr = tr.tail(period).mean()

    return float(atr) if not pd.isna(atr) else 0.0


def get_latest_metrics(symbol: str) -> Dict[str, Any]:
    hist = load_price_history(symbol)

    if hist.empty:
        return {
            "current_price": None,
            "ma5": None,
            "ma20": None,
            "atr": 0.0,
            "atr_pct": 0.0,
            "recent_low": None,
            "recent_high": None,
            "trend_state": "NO_DATA",
            "data_ok": False,
        }

    close = pd.to_numeric(hist["close"], errors="coerce").dropna()
    current = normalize_price(close.iloc[-1]) if len(close) else None

    ma5 = float(close.tail(5).mean()) if len(close) >= 5 else float(close.mean())
    ma20 = float(close.tail(20).mean()) if len(close) >= 20 else float(close.mean())

    atr = compute_atr(hist)
    atr_pct = (atr / current * 100.0) if current and current > 0 else 0.0

    recent_low = normalize_price(hist["low"].tail(10).min()) if "low" in hist.columns else current
    recent_high = normalize_price(hist["high"].tail(10).max()) if "high" in hist.columns else current

    if current is None:
        trend_state = "NO_DATA"
    elif current >= ma5 >= ma20:
        trend_state = "TREND TỐT"
    elif current >= ma20:
        trend_state = "TRÊN MA20"
    elif current < ma20:
        trend_state = "DƯỚI MA20"
    else:
        trend_state = "TRUNG TÍNH"

    return {
        "current_price": current,
        "ma5": round(ma5, 3) if ma5 else None,
        "ma20": round(ma20, 3) if ma20 else None,
        "atr": round(atr, 3),
        "atr_pct": round(atr_pct, 3),
        "recent_low": recent_low,
        "recent_high": recent_high,
        "trend_state": trend_state,
        "data_ok": True,
    }


def watchlist_info_for_symbol(watchlist: pd.DataFrame, symbol: str) -> Dict[str, Any]:
    if watchlist is None or watchlist.empty or "Mã" not in watchlist.columns:
        return {}

    match = watchlist[watchlist["Mã"].astype(str).str.upper().str.strip() == symbol]

    if match.empty:
        return {}

    row = match.iloc[0]

    return {
        "Final Decision": safe_str(row.get("Final Decision", "")),
        "Decision Mode": safe_str(row.get("Decision Mode", "")),
        "Meta Allocation %": to_num(row.get("Meta Allocation %", 0.0)),
        "Meta Exposure": to_num(row.get("Meta Exposure", 0.0)),
        "Regime Strength": safe_str(row.get("Regime Strength", "")),
        "Equity State": safe_str(row.get("Equity State", "")),
        "Ưu tiên": safe_str(row.get("Ưu tiên", "")),
        "Nhóm realtime": safe_str(row.get("Nhóm realtime", "")),
        "Sector": safe_str(row.get("Sector", row.get("Ngành", ""))),
    }


def calc_unrealized_pnl_pct(current_price: Optional[float], entry_price: float) -> float:
    if current_price is None or entry_price <= 0:
        return 0.0
    return (current_price / entry_price - 1.0) * 100.0


def calc_stop_levels(
    current_price: Optional[float],
    entry_price: float,
    highest_price: float,
    atr: float,
    current_stop: Optional[float],
) -> Dict[str, Any]:
    if current_price is None or entry_price <= 0:
        return {
            "initial_stop": None,
            "breakeven_stop": None,
            "atr_trailing_stop": None,
            "final_stop": current_stop,
            "stop_note": "Không có giá hiện tại",
        }

    initial_stop = entry_price * (1 - INITIAL_STOP_PCT / 100.0)
    pnl_pct = calc_unrealized_pnl_pct(current_price, entry_price)

    breakeven_stop = entry_price if pnl_pct >= BREAKEVEN_TRIGGER_PCT else None

    atr_trailing_stop = None
    if pnl_pct >= TRAIL_TRIGGER_PCT and highest_price > 0:
        atr_trailing_stop = highest_price - 2.0 * atr if atr > 0 else highest_price * 0.95

    candidates = [initial_stop]

    if current_stop is not None and current_stop > 0:
        candidates.append(current_stop)
    if breakeven_stop is not None:
        candidates.append(breakeven_stop)
    if atr_trailing_stop is not None:
        candidates.append(atr_trailing_stop)

    final_stop = max(candidates) if candidates else current_stop

    note_parts = []
    if pnl_pct >= BREAKEVEN_TRIGGER_PCT:
        note_parts.append("Đã đủ điều kiện nâng stop về hòa vốn")
    if pnl_pct >= TRAIL_TRIGGER_PCT:
        note_parts.append("Đã kích hoạt trailing stop")
    if not note_parts:
        note_parts.append("Dùng stop phòng thủ ban đầu")

    return {
        "initial_stop": round(initial_stop, 3),
        "breakeven_stop": round(breakeven_stop, 3) if breakeven_stop is not None else None,
        "atr_trailing_stop": round(atr_trailing_stop, 3) if atr_trailing_stop is not None else None,
        "final_stop": round(final_stop, 3) if final_stop is not None else None,
        "stop_note": "; ".join(note_parts),
    }


def classify_position_state(
    pnl_pct: float,
    current_price: Optional[float],
    final_stop: Optional[float],
    trend_state: str,
    final_decision: str,
    decision_mode: str,
) -> str:
    final_decision_u = normalize_text(final_decision)
    decision_mode_u = normalize_text(decision_mode)

    if current_price is not None and final_stop is not None and current_price <= final_stop:
        return "EXIT NGAY - CHẠM STOP"
    if final_decision_u in ["AVOID", "BỎ QUA", "REDUCE", "GIẢM"]:
        return "REDUCE/EXIT THEO UPSTREAM"
    if decision_mode_u == "CASH MODE":
        return "CASH MODE - GIẢM VỊ THẾ"
    if pnl_pct <= -INITIAL_STOP_PCT:
        return "EXIT - LỖ VƯỢT NGƯỠNG"
    if pnl_pct >= PROFIT_TAKE_2_PCT:
        return "CHỐT MẠNH / GIỮ CORE"
    if pnl_pct >= PROFIT_TAKE_1_PCT:
        return "CHỐT MỘT PHẦN"
    if trend_state in ["TREND TỐT", "TRÊN MA20"] and pnl_pct > 0:
        return "GIỮ TREND"
    if trend_state == "DƯỚI MA20":
        return "YẾU - CÂN NHẮC GIẢM"
    return "GIỮ / THEO DÕI"


def can_scale_in(
    pnl_pct: float,
    add_count: int,
    current_alloc: float,
    meta_alloc: float,
    decision_mode: str,
    final_decision: str,
    trend_state: str,
    portfolio_heat: float,
) -> Tuple[bool, str]:
    final_decision_u = normalize_text(final_decision)
    decision_mode_u = normalize_text(decision_mode)

    if decision_mode_u in BLOCK_ADD_MODES:
        return False, f"Không add vì Decision Mode = {decision_mode}"
    if final_decision_u not in ["BUY NOW", "WATCHLIST"]:
        return False, "Không add vì Final Decision không ủng hộ"
    if add_count >= MAX_ADD_COUNT:
        return False, "Đã đủ số lần add tối đa"
    if pnl_pct < MIN_ADD_PROFIT_PCT:
        return False, "Chưa đủ lãi để add an toàn"
    if current_alloc >= MAX_POSITION_ALLOCATION_PCT:
        return False, "Tỷ trọng mã đã chạm giới hạn"
    if meta_alloc > 0 and current_alloc >= meta_alloc:
        return False, "Tỷ trọng hiện tại đã >= Meta Allocation"
    if trend_state not in ["TREND TỐT", "TRÊN MA20"]:
        return False, "Trend chưa đủ tốt để add"
    if portfolio_heat >= MAX_PORTFOLIO_HEAT_PCT:
        return False, "Portfolio heat quá cao"
    return True, "Đủ điều kiện scale in nhỏ"


def decide_trade_action(position_state: str, can_add: bool, pnl_pct: float, final_decision: str, decision_mode: str) -> str:
    state_u = normalize_text(position_state)
    mode_u = normalize_text(decision_mode)

    if "EXIT NGAY" in state_u:
        return "EXIT"
    if "EXIT" in state_u and "GIỮ CORE" not in state_u:
        return "EXIT"
    if "REDUCE" in state_u or "GIẢM" in state_u or mode_u == "CASH MODE":
        return "REDUCE"
    if "CHỐT MẠNH" in state_u:
        return "SCALE OUT MẠNH"
    if "CHỐT MỘT PHẦN" in state_u:
        return "SCALE OUT NHẸ"
    if can_add:
        return "ADD NHỎ"
    if "GIỮ TREND" in state_u:
        return "HOLD"
    return "WATCH POSITION"


def calculate_portfolio_heat(positions: pd.DataFrame, watchlist: pd.DataFrame) -> Dict[str, Any]:
    if positions is None or positions.empty:
        return {"portfolio_heat": 0.0, "sector_heat": {}, "max_sector_heat": 0.0, "heat_note": "Không có vị thế"}

    total_heat = float(pd.to_numeric(positions["Tỷ trọng hiện tại %"], errors="coerce").fillna(0).sum())
    sector_heat: Dict[str, float] = {}

    for _, row in positions.iterrows():
        symbol = safe_str(row.get("Mã", "")).upper()
        alloc = to_num(row.get("Tỷ trọng hiện tại %", 0.0))
        info = watchlist_info_for_symbol(watchlist, symbol)
        sector = safe_str(info.get("Sector", ""), "UNKNOWN")
        sector_heat[sector] = sector_heat.get(sector, 0.0) + alloc

    max_sector_heat = max(sector_heat.values()) if sector_heat else 0.0

    notes = []
    if total_heat >= MAX_PORTFOLIO_HEAT_PCT:
        notes.append("Portfolio heat cao")
    if max_sector_heat >= MAX_SECTOR_HEAT_PCT:
        notes.append("Sector heat cao")
    if not notes:
        notes.append("Portfolio heat trong ngưỡng")

    return {
        "portfolio_heat": round(total_heat, 3),
        "sector_heat": {k: round(v, 3) for k, v in sector_heat.items()},
        "max_sector_heat": round(max_sector_heat, 3),
        "heat_note": "; ".join(notes),
    }


def explain_action_vietnamese(action: str) -> str:
    mapping = {
        "EXIT": "Thoát vị thế",
        "REDUCE": "Giảm vị thế",
        "SCALE OUT MẠNH": "Chốt lời mạnh, có thể giữ một phần nhỏ nếu còn trend",
        "SCALE OUT NHẸ": "Chốt lời một phần",
        "ADD NHỎ": "Có thể mua thêm nhỏ nếu đúng kế hoạch vốn",
        "HOLD": "Tiếp tục giữ",
        "WATCH POSITION": "Theo dõi vị thế, chưa hành động mạnh",
    }
    return mapping.get(action, "Theo dõi")


def main_reason_for_action(row: Dict[str, Any]) -> str:
    action = normalize_text(row.get("Trade Action", ""))
    pnl = to_num(row.get("Lãi/lỗ %", 0))
    mode = safe_str(row.get("Decision Mode", ""))
    state = safe_str(row.get("Position State", ""))
    trend = safe_str(row.get("Trend State", ""))

    if action == "EXIT":
        return f"{state}; cần bảo vệ vốn"
    if action == "REDUCE":
        return f"{mode}; upstream risk yêu cầu giảm"
    if "SCALE OUT" in action:
        return f"Lãi {pnl:.2f}%, nên chốt bớt để khóa lợi nhuận"
    if action == "ADD NHỎ":
        return f"Lãi {pnl:.2f}%, trend {trend}, đủ điều kiện add nhỏ"
    if action == "HOLD":
        return f"Trend {trend}, vị thế còn ổn"
    return "Chưa có tín hiệu hành động mạnh"


def build_management_rows(positions: pd.DataFrame, watchlist: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    heat = calculate_portfolio_heat(positions, watchlist)
    rows = []
    actions = []

    for _, pos in positions.iterrows():
        symbol = safe_str(pos.get("Mã", "")).upper()
        if not symbol:
            continue

        qty = to_num(pos.get("Số lượng", 0))
        entry_price = to_num(pos.get("Giá vốn", 0))
        current_alloc = to_num(pos.get("Tỷ trọng hiện tại %", 0))
        add_count = int(to_num(pos.get("Số lần add", 0)))
        highest_price = to_num(pos.get("Giá cao nhất từ khi mua", 0))
        current_stop = normalize_price(pos.get("Stop hiện tại", None))

        metrics = get_latest_metrics(symbol)
        current_price = metrics["current_price"]

        if current_price is not None:
            highest_price = max(highest_price, current_price)

        pnl_pct = calc_unrealized_pnl_pct(current_price, entry_price)
        info = watchlist_info_for_symbol(watchlist, symbol)

        final_decision = safe_str(info.get("Final Decision", ""), "UNKNOWN")
        decision_mode = safe_str(info.get("Decision Mode", ""), "UNKNOWN")
        meta_alloc = to_num(info.get("Meta Allocation %", 0.0))
        meta_exposure = to_num(info.get("Meta Exposure", 0.0))
        regime_strength = safe_str(info.get("Regime Strength", ""), "UNKNOWN")
        equity_state = safe_str(info.get("Equity State", ""), "UNKNOWN")
        priority = safe_str(info.get("Ưu tiên", ""), "UNKNOWN")
        realtime_group = safe_str(info.get("Nhóm realtime", ""), "UNKNOWN")
        sector = safe_str(info.get("Sector", ""), "UNKNOWN")

        stop_info = calc_stop_levels(
            current_price=current_price,
            entry_price=entry_price,
            highest_price=highest_price,
            atr=metrics["atr"],
            current_stop=current_stop,
        )

        position_state = classify_position_state(
            pnl_pct=pnl_pct,
            current_price=current_price,
            final_stop=stop_info["final_stop"],
            trend_state=metrics["trend_state"],
            final_decision=final_decision,
            decision_mode=decision_mode,
        )

        add_ok, add_reason = can_scale_in(
            pnl_pct=pnl_pct,
            add_count=add_count,
            current_alloc=current_alloc,
            meta_alloc=meta_alloc,
            decision_mode=decision_mode,
            final_decision=final_decision,
            trend_state=metrics["trend_state"],
            portfolio_heat=heat["portfolio_heat"],
        )

        trade_action = decide_trade_action(
            position_state=position_state,
            can_add=add_ok,
            pnl_pct=pnl_pct,
            final_decision=final_decision,
            decision_mode=decision_mode,
        )

        market_value_est = qty * current_price if current_price is not None else 0.0
        cost_est = qty * entry_price if entry_price > 0 else 0.0
        pnl_value_est = market_value_est - cost_est

        row = {
            "Mã": symbol,
            "Sector": sector,
            "Số lượng": qty,
            "Giá vốn": round(entry_price, 3),
            "Giá hiện tại": current_price,
            "Lãi/lỗ %": round(pnl_pct, 3),
            "Lãi/lỗ ước tính": round(pnl_value_est, 3),
            "Tỷ trọng hiện tại %": round(current_alloc, 3),
            "Meta Allocation %": round(meta_alloc, 3),
            "Final Decision": final_decision,
            "Decision Mode": decision_mode,
            "Meta Exposure": round(meta_exposure, 4),
            "Regime Strength": regime_strength,
            "Equity State": equity_state,
            "Ưu tiên": priority,
            "Nhóm realtime": realtime_group,
            "Trend State": metrics["trend_state"],
            "MA5": metrics["ma5"],
            "MA20": metrics["ma20"],
            "ATR": metrics["atr"],
            "ATR %": metrics["atr_pct"],
            "Giá cao nhất từ khi mua": round(highest_price, 3),
            "Stop ban đầu": stop_info["initial_stop"],
            "Stop hòa vốn": stop_info["breakeven_stop"],
            "Trailing Stop ATR": stop_info["atr_trailing_stop"],
            "Stop đề xuất": stop_info["final_stop"],
            "Ghi chú stop": stop_info["stop_note"],
            "Position State": position_state,
            "Có thể add?": add_ok,
            "Lý do add": add_reason,
            "Trade Action": trade_action,
            "Portfolio Heat %": heat["portfolio_heat"],
            "Max Sector Heat %": heat["max_sector_heat"],
            "Ghi chú heat": heat["heat_note"],
            "Updated At": now_str(),
        }

        rows.append(row)
        actions.append({
            "Mã": symbol,
            "Trade Action": trade_action,
            "Kết luận dễ hiểu": explain_action_vietnamese(trade_action),
            "Position State": position_state,
            "Lãi/lỗ %": round(pnl_pct, 3),
            "Stop đề xuất": stop_info["final_stop"],
            "Có thể add?": add_ok,
            "Lý do chính": main_reason_for_action(row),
            "Updated At": now_str(),
        })

    return pd.DataFrame(rows), pd.DataFrame(actions), heat


def build_report(management_df: pd.DataFrame, actions_df: pd.DataFrame, heat: Dict[str, Any], no_positions: bool) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append("V19 POSITION & TRADE MANAGEMENT ENGINE")
    lines.append("V19 — Bộ quản lý vị thế và vòng đời lệnh")
    lines.append("=" * 80)
    lines.append(f"Version: {SYSTEM_VERSION}")
    lines.append(f"Generated: {now_str()}")

    lines.append("")
    lines.append("=== DỊCH DỄ HIỂU ===")
    lines.append("V19 không chọn mã mới.")
    lines.append("V19 quản lý các mã bạn đang giữ: giữ, add, chốt bớt, giảm, hoặc thoát.")
    lines.append("V19 đọc risk từ V17.1/V18.2 để không đánh ngược hệ thống.")

    lines.append("")
    lines.append("=== PORTFOLIO HEAT (Độ nóng danh mục) ===")
    lines.append(f"Portfolio Heat: {heat.get('portfolio_heat', 0)}%")
    lines.append(f"Max Sector Heat: {heat.get('max_sector_heat', 0)}%")
    lines.append(f"Ghi chú: {heat.get('heat_note', '')}")
    lines.append(f"Sector Heat: {heat.get('sector_heat', {})}")

    if no_positions:
        lines.append("")
        lines.append("=== CHƯA CÓ FILE VỊ THẾ ===")
        lines.append(f"Không tìm thấy {POSITIONS_PATH}.")
        lines.append(f"Đã tạo file mẫu {OUTPUT_TEMPLATE}.")
        lines.append("Bạn cần điền các mã đang giữ vào positions_v19.csv rồi chạy lại V19.")
        return "\n".join(lines)

    lines.append("")
    lines.append("=== ACTION SUMMARY ===")
    if actions_df.empty:
        lines.append("Không có vị thế để phân tích.")
    else:
        counts = actions_df["Trade Action"].value_counts().to_dict()
        for k, v in counts.items():
            lines.append(f"- {k}: {v} mã")

    lines.append("")
    lines.append("=== CHI TIẾT HÀNH ĐỘNG ===")
    if not actions_df.empty:
        for _, row in actions_df.iterrows():
            lines.append(
                f"◆ {row['Mã']} | {row['Trade Action']} | "
                f"{row['Kết luận dễ hiểu']} | "
                f"Lãi/lỗ: {row['Lãi/lỗ %']}% | "
                f"Stop đề xuất: {row['Stop đề xuất']} | "
                f"Lý do: {row['Lý do chính']}"
            )

    lines.append("")
    lines.append("=== GIẢI THÍCH THUẬT NGỮ ===")
    lines.append("Position Manager (bộ quản lý vị thế): theo dõi mã đang nắm, giá vốn, lãi/lỗ.")
    lines.append("Trailing Stop (dừng lỗ động): stop tự nâng lên khi cổ phiếu có lãi.")
    lines.append("Scale In (mua thêm từng phần): add vị thế khi lãi và trend xác nhận.")
    lines.append("Scale Out (chốt bớt từng phần): bán bớt khi lời tốt hoặc risk tăng.")
    lines.append("Portfolio Heat (độ nóng danh mục): tổng tỷ trọng đang chịu rủi ro.")

    return "\n".join(lines)


def build_html(management_df: pd.DataFrame, actions_df: pd.DataFrame, report: str) -> str:
    action_html = actions_df.to_html(index=False) if not actions_df.empty else "<p>Không có action.</p>"
    management_html = management_df.to_html(index=False) if not management_df.empty else "<p>Không có vị thế.</p>"

    return f"""
<html>
<head>
<meta charset="utf-8">
<title>V19 Position & Trade Management</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 20px; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 24px; }}
th, td {{ border: 1px solid #ccc; padding: 7px; text-align: center; }}
th {{ background: #f0f0f0; }}
.box {{ background: #f7f7f7; border: 1px solid #ddd; padding: 12px; margin-bottom: 20px; }}
pre {{ white-space: pre-wrap; }}
</style>
</head>
<body>
<h1>V19 Position & Trade Management Engine</h1>
<div class="box">
<b>Dịch dễ hiểu:</b><br>
V19 = Bộ quản lý vị thế và vòng đời lệnh.<br>
Nó không chọn mã mới, mà quản lý các mã đang nắm: HOLD, ADD, REDUCE, EXIT.
</div>

<h2>Trade Actions</h2>
{action_html}

<h2>Position Management Detail</h2>
{management_html}

<h2>Report</h2>
<pre>{report}</pre>
</body>
</html>
"""


def run_engine():
    log("Bắt đầu chạy V19 Position & Trade Management Engine...")

    watchlist = load_watchlist()
    positions, no_positions = load_positions()

    if no_positions:
        heat = {"portfolio_heat": 0.0, "sector_heat": {}, "max_sector_heat": 0.0, "heat_note": "Chưa có vị thế"}
        management_df = pd.DataFrame()
        actions_df = pd.DataFrame()
    else:
        management_df, actions_df, heat = build_management_rows(positions, watchlist)

    management_df.to_csv(OUTPUT_POSITION_MANAGEMENT, index=False, encoding="utf-8-sig")
    actions_df.to_csv(OUTPUT_TRADE_ACTIONS, index=False, encoding="utf-8-sig")

    if not management_df.empty:
        state_cols = [
            "Mã",
            "Số lượng",
            "Giá vốn",
            "Giá hiện tại",
            "Lãi/lỗ %",
            "Stop đề xuất",
            "Position State",
            "Trade Action",
            "Updated At",
        ]
        available_cols = [c for c in state_cols if c in management_df.columns]
        management_df[available_cols].to_csv(OUTPUT_POSITION_STATE, index=False, encoding="utf-8-sig")
    else:
        pd.DataFrame(columns=[
            "Mã", "Số lượng", "Giá vốn", "Giá hiện tại", "Lãi/lỗ %",
            "Stop đề xuất", "Position State", "Trade Action", "Updated At"
        ]).to_csv(OUTPUT_POSITION_STATE, index=False, encoding="utf-8-sig")

    report = build_report(management_df, actions_df, heat, no_positions)
    html = build_html(management_df, actions_df, report)

    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        f.write(report)

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(report)

    log("Đã hoàn tất V19.")
    log(f"Output: {OUTPUT_POSITION_MANAGEMENT}, {OUTPUT_TRADE_ACTIONS}, {OUTPUT_POSITION_STATE}")

    return management_df, actions_df


if __name__ == "__main__":
    run_engine()
