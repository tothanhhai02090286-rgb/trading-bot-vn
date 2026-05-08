# -*- coding: utf-8 -*-
"""
intraday_alert_bot.py
Render Background Worker cho realtime/near-realtime alert.

Cách hoạt động:
- Đọc intraday_watchlist.csv do bot EOD xuất ra.
- Chỉ canh TOP MUA THẬT và TOP THEO DÕI.
- Kiểm tra mỗi CHECK_INTERVAL_SEC giây.
- Gửi Telegram khi:
  + giá chạm vùng mua,
  + giá vượt quá xa buy zone,
  + giá thủng stoploss tham khảo.

Biến môi trường cần có trên Render:
- TELEGRAM_TOKEN
- TELEGRAM_CHAT_ID

Tùy chọn:
- INTRADAY_WATCHLIST_PATH=intraday_watchlist.csv
- GITHUB_RAW_WATCHLIST_URL=<raw url nếu muốn đọc từ GitHub raw>
- GITHUB_TOKEN=<token nếu repo private>
- CHECK_INTERVAL_SEC=120
- MARKET_START=09:00
- MARKET_END=14:50
- TZ=Asia/Ho_Chi_Minh
"""

from __future__ import annotations

import os
import time
import json
from datetime import datetime, time as dtime
from typing import Optional, Dict, Any, Set

import pandas as pd
import requests

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None


WATCHLIST_PATH = os.getenv("INTRADAY_WATCHLIST_PATH", "intraday_watchlist.csv")
RAW_URL = os.getenv("GITHUB_RAW_WATCHLIST_URL", "").strip()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
CHECK_INTERVAL_SEC = int(os.getenv("CHECK_INTERVAL_SEC", "120"))
MARKET_START = os.getenv("MARKET_START", "09:00")
MARKET_END = os.getenv("MARKET_END", "14:50")
TZ_NAME = os.getenv("TZ", "Asia/Ho_Chi_Minh")
STATE_PATH = os.getenv("INTRADAY_ALERT_STATE", "intraday_alert_state.json")


def _now():
    if ZoneInfo:
        return datetime.now(ZoneInfo(TZ_NAME))
    return datetime.now()


def _parse_hhmm(s: str) -> dtime:
    hh, mm = s.split(":")[:2]
    return dtime(int(hh), int(mm))


def in_market_time() -> bool:
    n = _now()
    # nghỉ cuối tuần
    if n.weekday() >= 5:
        return False
    t = n.time()
    start = _parse_hhmm(MARKET_START)
    end = _parse_hhmm(MARKET_END)
    # nghỉ trưa VN: 11:30 - 13:00
    lunch_start = dtime(11, 30)
    lunch_end = dtime(13, 0)
    return (start <= t <= end) and not (lunch_start <= t < lunch_end)


def send_telegram(text: str):
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("WARN: missing TELEGRAM_TOKEN/TELEGRAM_CHAT_ID")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(
            url,
            data={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=20,
        )
        if resp.status_code != 200:
            print("WARN telegram:", resp.status_code, resp.text[:300])
    except Exception as e:
        print("WARN telegram exception:", repr(e))


def load_state() -> Set[str]:
    try:
        if os.path.exists(STATE_PATH):
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            today = _now().strftime("%Y-%m-%d")
            if data.get("date") == today:
                return set(data.get("sent", []))
    except Exception:
        pass
    return set()


def save_state(sent: Set[str]):
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump({"date": _now().strftime("%Y-%m-%d"), "sent": sorted(sent)}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("WARN save state:", repr(e))


def load_watchlist() -> pd.DataFrame:
    if RAW_URL:
        headers = {}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
        r = requests.get(RAW_URL, headers=headers, timeout=30)
        r.raise_for_status()
        from io import StringIO
        return pd.read_csv(StringIO(r.text))

    if not os.path.exists(WATCHLIST_PATH):
        print(f"WARN: watchlist not found: {WATCHLIST_PATH}")
        return pd.DataFrame()
    return pd.read_csv(WATCHLIST_PATH)


def get_current_price(symbol: str) -> Optional[float]:
    """Lấy giá gần realtime. Thứ tự:
    1. vnstock nếu môi trường hỗ trợ.
    2. yfinance symbol.VN fallback.
    """
    symbol = str(symbol).strip().upper()
    if not symbol:
        return None

    # Try vnstock v3 style
    try:
        from vnstock import Vnstock
        stock = Vnstock().stock(symbol=symbol, source="VCI")
        # Một số bản vnstock có quote.intraday
        q = getattr(stock, "quote", None)
        if q is not None and hasattr(q, "intraday"):
            df = q.intraday(page_size=5)
            if df is not None and not df.empty:
                for col in ["price", "match_price", "close", "last_price"]:
                    if col in df.columns:
                        v = pd.to_numeric(df[col], errors="coerce").dropna()
                        if len(v):
                            return float(v.iloc[-1])
        # fallback history gần nhất
        if q is not None and hasattr(q, "history"):
            df = q.history(period="1D")
            if df is not None and not df.empty:
                for col in ["close", "Close"]:
                    if col in df.columns:
                        v = pd.to_numeric(df[col], errors="coerce").dropna()
                        if len(v):
                            return float(v.iloc[-1])
    except Exception as e:
        print(f"WARN vnstock price {symbol}: {repr(e)}")

    # Try yfinance fallback for Vietnamese tickers
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
                    return float(v.iloc[-1])
    except Exception as e:
        print(f"WARN yfinance price {symbol}: {repr(e)}")

    return None


def _float(row: pd.Series, col: str) -> Optional[float]:
    try:
        if col not in row:
            return None
        v = pd.to_numeric(pd.Series([row[col]]), errors="coerce").iloc[0]
        if pd.isna(v):
            return None
        return float(v)
    except Exception:
        return None


def build_alert(row: pd.Series, current_price: float, alert_type: str) -> str:
    symbol = str(row.get("Mã", "")).strip().upper()
    group = str(row.get("Nhóm realtime", ""))
    emoji = "🟢" if "MUA" in group.upper() else "🟡"
    ref = _float(row, "Giá tham chiếu")
    buy_low = _float(row, "Buy zone thấp")
    buy_high = _float(row, "Buy zone cao")
    stop = _float(row, "Stoploss tham khảo")
    action = str(row.get("Hành động", ""))
    risk = str(row.get("Risk", ""))
    rs20 = str(row.get("RS20", ""))
    t2 = str(row.get("Lợi TB T+2 %", ""))
    t5 = str(row.get("Lợi TB T+5 %", ""))

    return (
        f"{emoji} <b>{symbol}</b> - <b>{alert_type}</b>\n"
        f"Nhóm: <b>{group}</b>\n"
        f"Giá hiện tại: <b>{current_price:.2f}</b>\n"
        f"Giá tham chiếu: {ref if ref is not None else ''}\n"
        f"Buy zone: {buy_low if buy_low is not None else ''} - {buy_high if buy_high is not None else ''}\n"
        f"Stoploss: {stop if stop is not None else ''}\n"
        f"Action: {action} | Risk: {risk}\n"
        f"RS20: {rs20} | T+2: {t2} | T+5: {t5}\n"
        f"Time: {_now().strftime('%Y-%m-%d %H:%M:%S')}"
    )


def check_once(sent: Set[str]) -> Set[str]:
    df = load_watchlist()
    if df.empty:
        print("No watchlist rows")
        return sent

    if "Mã" not in df.columns:
        print("WARN: watchlist missing column Mã")
        return sent

    for _, row in df.iterrows():
        symbol = str(row.get("Mã", "")).strip().upper()
        if not symbol or symbol == "NAN":
            continue

        price = get_current_price(symbol)
        if price is None:
            print(f"No current price: {symbol}")
            continue

        buy_low = _float(row, "Buy zone thấp")
        buy_high = _float(row, "Buy zone cao")
        stop = _float(row, "Stoploss tham khảo")

        alert_type = None
        if buy_low is not None and buy_high is not None and buy_low <= price <= buy_high:
            alert_type = "CHẠM VÙNG MUA"
        elif stop is not None and price <= stop:
            alert_type = "THỦNG STOPLOSS THAM KHẢO"
        elif buy_high is not None and price > buy_high * 1.02:
            alert_type = "VƯỢT BUY ZONE QUÁ XA"

        if alert_type:
            key = f"{symbol}:{alert_type}"
            if key not in sent:
                send_telegram(build_alert(row, price, alert_type))
                sent.add(key)
                save_state(sent)
                print("ALERT", key)
            else:
                print("Already sent", key)
        else:
            print(f"OK {symbol}: price={price:.2f}, no alert")

    return sent


def main():
    print("INTRADAY BOT MAIN STARTED", flush=True)
    send_telegram("✅ <b>Intraday Alert Bot started</b>\nRender worker đang chạy và sẽ đọc intraday_watchlist.csv.")
    print("TELEGRAM START MESSAGE SENT", flush=True)
    sent = load_state()
    while True:
        try:
            if in_market_time():
                sent = check_once(sent)
            else:
                print("Outside market time", _now().strftime("%Y-%m-%d %H:%M:%S"))
        except Exception as e:
            print("ERROR loop:", repr(e))
            send_telegram(f"⚠️ Intraday bot lỗi vòng kiểm tra: <code>{repr(e)}</code>")
        time.sleep(CHECK_INTERVAL_SEC)


if __name__ == "__main__":
    main()
