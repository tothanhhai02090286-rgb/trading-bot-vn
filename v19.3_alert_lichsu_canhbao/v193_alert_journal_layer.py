# -*- coding: utf-8 -*-
"""
V19.3 Alert Journal Layer
=========================

Mục tiêu:
- Ghi lại mọi cảnh báo Telegram từ V18.2 ENTRY và V19.2 POSITION vào file CSV.
- Không chạy vòng lặp riêng.
- Không gọi API giá.
- Không làm tăng rate limit.
- Chỉ được gọi tại đúng điểm chuẩn bị gửi Telegram.

Output mặc định:
- alert_journal_v193.csv

Cách dùng trong V18.2 / V19.2:

from v193_alert_journal_layer import log_alert

log_alert(
    source="V18.2 ENTRY",
    symbol=symbol,
    alert_type=signal_type,
    price=current_price,
    message=message,
    buy_zone_low=buy_low,
    buy_zone_high=buy_high,
    stoploss=stoploss,
)

"""

from __future__ import annotations

import csv
import os
from datetime import datetime
from typing import Any, Dict, Optional

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None


DEFAULT_JOURNAL_FILE = os.getenv("V193_ALERT_JOURNAL_FILE", "alert_journal_v193.csv")
DEFAULT_TZ = os.getenv("TZ", "Asia/Ho_Chi_Minh")


FIELDNAMES = [
    "timestamp",
    "source",
    "symbol",
    "alert_type",
    "price",
    "buy_zone_low",
    "buy_zone_high",
    "sell_zone_low",
    "sell_zone_high",
    "stoploss",
    "position_qty",
    "position_avg_price",
    "decision_mode",
    "market_regime",
    "reason",
    "message",
]


def _now_str() -> str:
    """Trả về thời gian hiện tại theo TZ, fallback an toàn nếu môi trường không hỗ trợ zoneinfo."""
    try:
        if ZoneInfo is not None:
            return datetime.now(ZoneInfo(DEFAULT_TZ)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_text(value: Any) -> str:
    """Ép dữ liệu về text an toàn cho CSV."""
    if value is None:
        return ""
    try:
        text = str(value)
    except Exception:
        text = repr(value)
    return text.replace("\r", " ").replace("\n", " ").strip()


def _safe_number(value: Any) -> str:
    """Ép số về text, tránh crash khi None / NaN / object lạ."""
    if value is None:
        return ""
    try:
        # xử lý NaN
        if value != value:
            return ""
    except Exception:
        pass
    return _safe_text(value)


def ensure_journal_file(path: str = DEFAULT_JOURNAL_FILE) -> None:
    """Tạo file journal nếu chưa có."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)

    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()


def log_alert(
    source: str,
    symbol: str,
    alert_type: str,
    price: Any = None,
    message: str = "",
    buy_zone_low: Any = None,
    buy_zone_high: Any = None,
    sell_zone_low: Any = None,
    sell_zone_high: Any = None,
    stoploss: Any = None,
    position_qty: Any = None,
    position_avg_price: Any = None,
    decision_mode: str = "",
    market_regime: str = "",
    reason: str = "",
    journal_file: str = DEFAULT_JOURNAL_FILE,
    **extra: Any,
) -> bool:
    """
    Ghi 1 dòng cảnh báo vào alert_journal_v193.csv.

    Trả về:
    - True nếu ghi thành công
    - False nếu lỗi nhưng không làm crash bot chính
    """
    try:
        ensure_journal_file(journal_file)

        row: Dict[str, str] = {
            "timestamp": _now_str(),
            "source": _safe_text(source),
            "symbol": _safe_text(symbol).upper(),
            "alert_type": _safe_text(alert_type),
            "price": _safe_number(price),
            "buy_zone_low": _safe_number(buy_zone_low),
            "buy_zone_high": _safe_number(buy_zone_high),
            "sell_zone_low": _safe_number(sell_zone_low),
            "sell_zone_high": _safe_number(sell_zone_high),
            "stoploss": _safe_number(stoploss),
            "position_qty": _safe_number(position_qty),
            "position_avg_price": _safe_number(position_avg_price),
            "decision_mode": _safe_text(decision_mode),
            "market_regime": _safe_text(market_regime),
            "reason": _safe_text(reason),
            "message": _safe_text(message),
        }

        with open(journal_file, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writerow(row)

        return True

    except Exception as e:
        # Không để lỗi ghi journal làm chết V18.2/V19.2
        try:
            print(f"[V19.3 JOURNAL][WARN] Không ghi được alert journal: {e}", flush=True)
        except Exception:
            pass
        return False


def log_entry_alert(
    symbol: str,
    alert_type: str,
    price: Any = None,
    message: str = "",
    buy_zone_low: Any = None,
    buy_zone_high: Any = None,
    stoploss: Any = None,
    decision_mode: str = "",
    market_regime: str = "",
    reason: str = "",
    **kwargs: Any,
) -> bool:
    """Shortcut cho V18.2 ENTRY."""
    return log_alert(
        source="V18.2 ENTRY",
        symbol=symbol,
        alert_type=alert_type,
        price=price,
        message=message,
        buy_zone_low=buy_zone_low,
        buy_zone_high=buy_zone_high,
        stoploss=stoploss,
        decision_mode=decision_mode,
        market_regime=market_regime,
        reason=reason,
        **kwargs,
    )


def log_position_alert(
    symbol: str,
    alert_type: str,
    price: Any = None,
    message: str = "",
    position_qty: Any = None,
    position_avg_price: Any = None,
    stoploss: Any = None,
    decision_mode: str = "",
    market_regime: str = "",
    reason: str = "",
    **kwargs: Any,
) -> bool:
    """Shortcut cho V19.2 POSITION."""
    return log_alert(
        source="V19.2 POSITION",
        symbol=symbol,
        alert_type=alert_type,
        price=price,
        message=message,
        position_qty=position_qty,
        position_avg_price=position_avg_price,
        stoploss=stoploss,
        decision_mode=decision_mode,
        market_regime=market_regime,
        reason=reason,
        **kwargs,
    )


if __name__ == "__main__":
    # Test nhanh local / GitHub Actions
    ok = log_alert(
        source="TEST",
        symbol="GVR",
        alert_type="TEST JOURNAL",
        price=31.1,
        buy_zone_low=30.8,
        buy_zone_high=31.3,
        stoploss=29.9,
        decision_mode="NORMAL",
        market_regime="TÍCH CỰC",
        reason="Test ghi journal V19.3",
        message="[TEST] Đây là dòng test V19.3 Alert Journal",
    )
    print(f"[V19.3 JOURNAL] Test ghi file: {'OK' if ok else 'FAIL'}")
    print(f"[V19.3 JOURNAL] File: {DEFAULT_JOURNAL_FILE}")
