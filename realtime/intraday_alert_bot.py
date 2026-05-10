# -*- coding: utf-8 -*-
"""
intraday_alert_bot.py
Render intraday light scanner - RAW URL AUTO UPDATE VERSION.

Mục tiêu:
- GitHub Actions có thể cập nhật intraday_watchlist.csv trong phiên.
- Render KHÔNG cần redeploy.
- Mỗi vòng quét, Render tự tải lại watchlist từ GITHUB_RAW_WATCHLIST_URL nếu có.
- Nếu có mã mới trong watchlist, Render tự nhận và bắt đầu canh.
- Nếu mã bị xóa khỏi watchlist, Render không quét mã đó nữa.
- Chỉ quét các mã trong intraday_watchlist.csv, không quét toàn thị trường.
- Render tự kéo giá hiện tại trong phiên bằng vnstock/yfinance fallback.

Biến môi trường cần có trên Render:
- TELEGRAM_TOKEN
- TELEGRAM_CHAT_ID

Nên thêm:
- GITHUB_RAW_WATCHLIST_URL=https://raw.githubusercontent.com/<user>/<repo>/main/intraday_watchlist.csv

Nếu repo private:
- GITHUB_TOKEN=<GitHub token có quyền đọc repo>

Tùy chọn:
- CHECK_INTERVAL_SEC=120
- MARKET_START=09:00
- MARKET_END=14:50
- TZ=Asia/Ho_Chi_Minh
- MOMENTUM_FROM_REF_PCT=1.0
- WEAKNESS_FROM_REF_PCT=-1.5
- TOO_FAR_ABOVE_BUY_ZONE_PCT=2.0
"""

from __future__ import annotations

import os
import time
import json
from datetime import datetime, time as dtime
from typing import Optional, Set

import pandas as pd
import requests

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None


WATCHLIST_PATH = os.getenv("INTRADAY_WATCHLIST_PATH", "../intraday_watchlist.csv")
RAW_URL = (
    os.getenv("GITHUB_RAW_WATCHLIST_URL", "").strip()
    or os.getenv("RAW_URL", "").strip()
)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()

CHECK_INTERVAL_SEC = int(os.getenv("CHECK_INTERVAL_SEC", "120"))
MARKET_START = os.getenv("MARKET_START", "09:00")
MARKET_END = os.getenv("MARKET_END", "14:50")
TZ_NAME = os.getenv("TZ", "Asia/Ho_Chi_Minh")
STATE_PATH = os.getenv("INTRADAY_ALERT_STATE", "intraday_alert_state.json")

MOMENTUM_FROM_REF_PCT = float(os.getenv("MOMENTUM_FROM_REF_PCT", "1.0"))
WEAKNESS_FROM_REF_PCT = float(os.getenv("WEAKNESS_FROM_REF_PCT", "-1.5"))
TOO_FAR_ABOVE_BUY_ZONE_PCT = float(os.getenv("TOO_FAR_ABOVE_BUY_ZONE_PCT", "2.0"))

_LAST_SYMBOLS: Set[str] = set()


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


def load_state() -> Set[str]:
    try:
        if os.path.exists(STATE_PATH):
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            today = _now().strftime("%Y-%m-%d")
            if data.get("date") == today:
                return set(data.get("sent", []))
    except Exception as e:
        print("WARN load state:", repr(e), flush=True)
    return set()


def save_state(sent: Set[str]):
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(
                {"date": _now().strftime("%Y-%m-%d"), "sent": sorted(sent)},
                f,
                ensure_ascii=False,
                indent=2,
            )
    except Exception as e:
        print("WARN save state:", repr(e), flush=True)


def normalize_watchlist(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()

    if "Mã" not in out.columns:
        for col in ["Ma", "Symbol", "Ticker", "Mã CP"]:
            if col in out.columns:
                out["Mã"] = out[col]
                break

    if "Mã" not in out.columns:
        print("WARN: watchlist missing Mã column", flush=True)
        return pd.DataFrame()

    out["Mã"] = out["Mã"].astype(str).str.upper().str.strip()
    out = out[out["Mã"].notna() & (out["Mã"] != "") & (out["Mã"] != "NAN")].copy()

    if "Nhóm realtime" in out.columns:
        mask = out["Nhóm realtime"].astype(str).str.upper().str.contains("MUA|THEO|WATCH", na=False)
        out = out[mask].copy()

    out = out.drop_duplicates(subset=["Mã"], keep="first").reset_index(drop=True)
    return out


def _notify_watchlist_changes(df: pd.DataFrame):
    global _LAST_SYMBOLS

    symbols = set(df["Mã"].astype(str).str.upper().str.strip()) if not df.empty and "Mã" in df.columns else set()

    if not _LAST_SYMBOLS:
        _LAST_SYMBOLS = symbols
        print(f"WATCHLIST INIT symbols={len(symbols)}", flush=True)
        return

    added = sorted(symbols - _LAST_SYMBOLS)
    removed = sorted(_LAST_SYMBOLS - symbols)

    if added:
        msg = "🆕 <b>Watchlist realtime có mã mới</b>\n" + ", ".join(added)
        send_telegram(msg)
        print("WATCHLIST ADDED:", added, flush=True)

    if removed:
        print("WATCHLIST REMOVED:", removed, flush=True)

    _LAST_SYMBOLS = symbols


def load_watchlist() -> pd.DataFrame:
    # Ưu tiên RAW_URL để luôn nhận file mới nhất từ GitHub mà không cần deploy.
    if RAW_URL:
        headers = {"Cache-Control": "no-cache", "Pragma": "no-cache"}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

        try:
            url = RAW_URL
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}t={int(time.time())}"  # chống cache
            r = requests.get(url, headers=headers, timeout=30)
            r.raise_for_status()
            from io import StringIO
            df = pd.read_csv(StringIO(r.text))
            df = normalize_watchlist(df)
            print(
                f"WATCHLIST loaded from RAW_URL: rows={len(df)} | time={_now().strftime('%H:%M:%S')}",
                flush=True,
            )
            _notify_watchlist_changes(df)
            return df
        except Exception as e:
            print("WARN raw watchlist, fallback local:", repr(e), flush=True)

    candidates = [
        WATCHLIST_PATH,
        "intraday_watchlist.csv",
        "../intraday_watchlist.csv",
        "./intraday_watchlist.csv",
    ]

    for path in candidates:
        if os.path.exists(path):
            df = pd.read_csv(path)
            df = normalize_watchlist(df)
            print(f"WATCHLIST loaded local: {path} | rows={len(df)}", flush=True)
            _notify_watchlist_changes(df)
            return df

    print(f"WARN: watchlist not found. Tried: {candidates}", flush=True)
    return pd.DataFrame()


def _num(x) -> Optional[float]:
    try:
        if x is None:
            return None
        v = pd.to_numeric(pd.Series([x]), errors="coerce").iloc[0]
        if pd.isna(v):
            return None
        return float(v)
    except Exception:
        return None


def _row_float(row: pd.Series, col: str) -> Optional[float]:
    if col not in row:
        return None
    return _num(row[col])


def get_current_price_vnstock(symbol: str) -> Optional[float]:
    try:
        from vnstock import Vnstock
        stock = Vnstock().stock(symbol=symbol, source="VCI")
        q = getattr(stock, "quote", None)

        if q is not None and hasattr(q, "intraday"):
            df = q.intraday(page_size=20)
            if df is not None and not df.empty:
                for col in ["price", "match_price", "last_price", "close"]:
                    if col in df.columns:
                        v = pd.to_numeric(df[col], errors="coerce").dropna()
                        if len(v):
                            return float(v.iloc[-1])

        if q is not None and hasattr(q, "history"):
            df = q.history(period="1D")
            if df is not None and not df.empty:
                for col in ["close", "Close"]:
                    if col in df.columns:
                        v = pd.to_numeric(df[col], errors="coerce").dropna()
                        if len(v):
                            return float(v.iloc[-1])
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
                    return float(v.iloc[-1])
    except Exception as e:
        print(f"WARN yfinance price {symbol}: {repr(e)}", flush=True)
    return None


def get_current_price(symbol: str) -> Optional[float]:
    symbol = str(symbol).strip().upper()
    if not symbol:
        return None

    price = get_current_price_vnstock(symbol)
    if price is not None:
        return price

    return get_current_price_yfinance(symbol)


def detect_intraday_signal(row: pd.Series, current_price: float) -> Optional[str]:
    ref = _row_float(row, "Giá tham chiếu")
    buy_low = _row_float(row, "Buy zone thấp")
    buy_high = _row_float(row, "Buy zone cao")
    stop = _row_float(row, "Stoploss tham khảo")

    if stop is not None and current_price <= stop:
        return "THỦNG STOPLOSS THAM KHẢO"

    if buy_low is not None and buy_high is not None and buy_low <= current_price <= buy_high:
        return "CHẠM VÙNG MUA"

    if buy_high is not None and current_price > buy_high * (1 + TOO_FAR_ABOVE_BUY_ZONE_PCT / 100):
        return "VƯỢT BUY ZONE QUÁ XA"

    if ref is not None and ref > 0:
        intraday_ret = (current_price / ref - 1.0) * 100.0

        if intraday_ret >= MOMENTUM_FROM_REF_PCT:
            if buy_high is None or current_price <= buy_high * (1 + TOO_FAR_ABOVE_BUY_ZONE_PCT / 100):
                return "INTRADAY MOMENTUM"

        if intraday_ret <= WEAKNESS_FROM_REF_PCT:
            return "INTRADAY WEAKNESS"

    return None


def build_alert(row: pd.Series, current_price: float, alert_type: str) -> str:
    symbol = str(row.get("Mã", "")).strip().upper()
    group = str(row.get("Nhóm realtime", ""))
    emoji = "🟢" if "MUA" in group.upper() else "🟡"

    ref = _row_float(row, "Giá tham chiếu")
    buy_low = _row_float(row, "Buy zone thấp")
    buy_high = _row_float(row, "Buy zone cao")
    stop = _row_float(row, "Stoploss tham khảo")

    intraday_ret_text = ""
    if ref is not None and ref > 0:
        intraday_ret = (current_price / ref - 1.0) * 100
        intraday_ret_text = f"{intraday_ret:.2f}%"

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
        f"Biến động intraday: <b>{intraday_ret_text}</b>\n"
        f"Buy zone: {buy_low if buy_low is not None else ''} - {buy_high if buy_high is not None else ''}\n"
        f"Stoploss: {stop if stop is not None else ''}\n"
        f"Action: {action} | Risk: {risk}\n"
        f"RS20: {rs20} | T+2: {t2} | T+5: {t5}\n"
        f"Time: {_now().strftime('%Y-%m-%d %H:%M:%S')}"
    )


def check_once(sent: Set[str]) -> Set[str]:
    df = load_watchlist()
    if df.empty:
        print("No watchlist rows", flush=True)
        return sent

    print(f"Scanning watchlist: {len(df)} symbols", flush=True)

    for _, row in df.iterrows():
        symbol = str(row.get("Mã", "")).strip().upper()
        if not symbol or symbol == "NAN":
            continue

        current_price = get_current_price(symbol)
        if current_price is None:
            print(f"No current price: {symbol}", flush=True)
            continue

        signal = detect_intraday_signal(row, current_price)

        if signal:
            key = f"{symbol}:{signal}"
            if key not in sent:
                send_telegram(build_alert(row, current_price, signal))
                sent.add(key)
                save_state(sent)
                print("ALERT", key, flush=True)
            else:
                print("Already sent", key, flush=True)
        else:
            print(f"OK {symbol}: price={current_price:.2f}, no intraday signal", flush=True)

    return sent


def main():
    print("INTRADAY RAW URL LIGHT SCANNER STARTED", flush=True)
    print(f"TIME NOW: {_now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print(f"WATCHLIST_PATH={WATCHLIST_PATH}", flush=True)
    print(f"RAW_URL={'SET' if RAW_URL else 'EMPTY'}", flush=True)
    print(f"CHECK_INTERVAL_SEC={CHECK_INTERVAL_SEC}", flush=True)
    print(f"MARKET_START={MARKET_START} MARKET_END={MARKET_END}", flush=True)

    startup_df = load_watchlist()

if not startup_df.empty and "Mã" in startup_df.columns:
    startup_symbols = startup_df["Mã"].astype(str).str.upper().str.strip().tolist()
else:
    startup_symbols = []

ok = send_telegram(
    "✅ <b>V17 Intraday Scanner STARTED</b>\n"
    f"RAW_URL: <code>{RAW_URL[:80]}...</code>\n"
    f"ROWS: <b>{len(startup_df)}</b>\n"
    f"TICKERS: <b>{', '.join(startup_symbols)}</b>\n"
    f"TIME: {_now().strftime('%Y-%m-%d %H:%M:%S')}"
)
    print(f"TELEGRAM START MESSAGE SENT={ok}", flush=True)

    sent = load_state()

    while True:
        print(f"SCANNER ALIVE {datetime.now()}")
        try:
            if in_market_time():
                print("Inside market time - scanning", flush=True)
                sent = check_once(sent)
            else:
                print("Outside market time", _now().strftime("%Y-%m-%d %H:%M:%S"), flush=True)
                # Ngoài giờ vẫn thử đọc watchlist 1 lần để log trạng thái khi mới deploy.
                load_watchlist()
        except Exception as e:
            print("ERROR loop:", repr(e), flush=True)
            send_telegram(f"⚠️ Intraday scanner lỗi: <code>{repr(e)}</code>")

        time.sleep(CHECK_INTERVAL_SEC)


if __name__ == "__main__":
    main()
