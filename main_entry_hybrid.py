import os
import sys
import time
import pandas as pd
from datetime import datetime, time as dtime, timedelta

from config import BOT_DIR
BOT_DIR = str(BOT_DIR)
if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)

os.chdir(BOT_DIR)

from vnstock import Trading
from portfolio import load_price
from telegram_utils import send_telegram

PRIORITY_PATH = f"{BOT_DIR}/bottom_common_priority.csv"

PLAN_PATH = f"{BOT_DIR}/entry_plan_next_session.csv"
SENT_PATH = f"{BOT_DIR}/entry_hybrid_sent.csv"
TICK_PATH = f"{BOT_DIR}/entry_hybrid_ticks.csv"
STATE_PATH = f"{BOT_DIR}/entry_hybrid_state.csv"

INTERVAL_SEC = 180

MIN_CONFIRM = 2
MIN_RSI = 50
MIN_CLOSE_POS_5M = 0.65
MIN_VOLUME_SPIKE = 1.2


def is_trading_time():
    now = datetime.now()

    # Thứ 7, Chủ nhật
    if now.weekday() >= 5:
        return False

    current = now.time()

    morning = dtime(9, 0) <= current <= dtime(11, 30)
    afternoon = dtime(13, 0) <= current <= dtime(14, 45)

    return morning or afternoon


def calc_rsi(close, period=14):
    close = pd.Series(close).astype(float)
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))


def load_priority():
    if not os.path.exists(PRIORITY_PATH):
        print("❌ Chưa có bottom_common_priority.csv")
        return pd.DataFrame()

    df = pd.read_csv(PRIORITY_PATH)

    if "Mã" not in df.columns:
        print("❌ bottom_common_priority.csv không có cột Mã")
        return pd.DataFrame()

    return df


def build_entry_plan():
    print("📋 ENTRY PLAN MODE - NGOÀI PHIÊN / NGÀY NGHỈ")

    priority = load_priority()
    if priority.empty:
        return pd.DataFrame()

    rows = []

    for _, row in priority.iterrows():
        code = str(row["Mã"]).upper().strip()
        df = load_price(code)

        if df is None or df.empty or len(df) < 20:
            continue

        close = pd.to_numeric(df["close"], errors="coerce").dropna()
        high = pd.to_numeric(df["high"], errors="coerce").dropna()
        low = pd.to_numeric(df["low"], errors="coerce").dropna()

        last_close = float(close.iloc[-1])
        ma5 = float(close.tail(5).mean())
        rsi = float(calc_rsi(close).iloc[-1])

        recent_high = float(high.tail(5).max())
        recent_low = float(low.tail(5).min())

        buy_zone_low = round(ma5 * 0.995, 2)
        buy_zone_high = round(max(ma5, last_close) * 1.005, 2)

        trigger_price = round(max(last_close, recent_high) * 1.002, 2)

        stoploss = round(min(ma5, recent_low) * 0.985, 2)

        tp1 = round(trigger_price * 1.04, 2)
        tp2 = round(trigger_price * 1.07, 2)

        risk_pct = round((trigger_price / stoploss - 1) * 100, 2) if stoploss > 0 else None

        if rsi < 45:
            action = "👀 CHỜ - RSI chưa đủ khỏe"
        elif last_close < ma5:
            action = "👀 CHỜ VƯỢT MA5"
        else:
            action = "✅ CANH KÍCH HOẠT"

        rows.append({
            "Ngày lập kế hoạch": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Mã": code,
            "Giá đóng cửa": round(last_close, 2),
            "MA5": round(ma5, 2),
            "RSI": round(rsi, 2),
            "Vùng mua thấp": buy_zone_low,
            "Vùng mua cao": buy_zone_high,
            "Giá kích hoạt": trigger_price,
            "Stoploss": stoploss,
            "TP1 +4%": tp1,
            "TP2 +7%": tp2,
            "Risk %": risk_pct,
            "Hành động": action,
            "Backtest note": row.get("Chú thích", "")
        })

    plan = pd.DataFrame(rows)

    if plan.empty:
        print("❌ Không tạo được entry plan")
        return plan

    plan.to_csv(PLAN_PATH, index=False, encoding="utf-8-sig")

    print("\n📋 ENTRY PLAN CHO PHIÊN TỚI")
    display(plan)

    print("\n💾 Saved:", PLAN_PATH)

    msg = "📋 ENTRY PLAN CHO PHIÊN TỚI\n\n"
    for _, r in plan.iterrows():
        msg += f"""Mã: {r['Mã']}
Hành động: {r['Hành động']}
Vùng mua: {r['Vùng mua thấp']} - {r['Vùng mua cao']}
Kích hoạt: {r['Giá kích hoạt']}
SL: {r['Stoploss']} | TP1: {r['TP1 +4%']} | TP2: {r['TP2 +7%']}
RSI: {r['RSI']} | MA5: {r['MA5']}

"""

    send_telegram(msg[:3900])

    return plan


def load_sent():
    if os.path.exists(SENT_PATH):
        try:
            return set(pd.read_csv(SENT_PATH)["key"].astype(str))
        except:
            return set()
    return set()


def save_sent(key):
    row = pd.DataFrame([{
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "key": key
    }])

    if os.path.exists(SENT_PATH):
        row.to_csv(SENT_PATH, mode="a", header=False, index=False)
    else:
        row.to_csv(SENT_PATH, index=False)


def load_state():
    if os.path.exists(STATE_PATH):
        try:
            df = pd.read_csv(STATE_PATH)
            return dict(zip(df["Mã"], df["confirm_count"]))
        except:
            return {}
    return {}


def save_state(state):
    pd.DataFrame(
        [{"Mã": k, "confirm_count": v} for k, v in state.items()]
    ).to_csv(STATE_PATH, index=False)


def fetch_live(codes):
    try:
        board = Trading(source="KBS").price_board(codes)
        df = pd.DataFrame(board)
        df.columns = [str(c).strip() for c in df.columns]

        out = {}

        for _, r in df.iterrows():
            code = str(r.get("symbol", "")).upper().strip()
            price = pd.to_numeric(r.get("close_price"), errors="coerce")
            volume = pd.to_numeric(r.get("volume_accumulated"), errors="coerce")

            if code and pd.notna(price) and price > 0:
                out[code] = {
                    "price": float(price) / 1000,
                    "volume": float(volume) if pd.notna(volume) else None
                }

        return out

    except Exception as e:
        print("❌ live fail:", e)
        return {}


def append_ticks(live_map):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []

    for code, d in live_map.items():
        rows.append({
            "time": now,
            "Mã": code,
            "price": d.get("price"),
            "volume": d.get("volume")
        })

    if not rows:
        return

    df = pd.DataFrame(rows)

    if os.path.exists(TICK_PATH):
        df.to_csv(TICK_PATH, mode="a", header=False, index=False)
    else:
        df.to_csv(TICK_PATH, index=False)


def get_5m_signal(code):
    if not os.path.exists(TICK_PATH):
        return {"ok": False, "vol_ok": False}

    df = pd.read_csv(TICK_PATH)
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df = df.dropna(subset=["time"])
    df = df[df["Mã"].astype(str).str.upper() == code.upper()].copy()

    if len(df) < 2:
        return {"ok": False, "vol_ok": False}

    now = datetime.now()
    last5 = df[df["time"] >= now - timedelta(minutes=5)].copy()

    if len(last5) < 2:
        return {"ok": False, "vol_ok": False}

    prices = pd.to_numeric(last5["price"], errors="coerce").dropna()

    open5 = float(prices.iloc[0])
    close5 = float(prices.iloc[-1])
    high5 = float(prices.max())
    low5 = float(prices.min())

    close_pos = (close5 - low5) / (high5 - low5 + 1e-9)
    candle_ok = close5 > open5 and close_pos >= MIN_CLOSE_POS_5M

    full = df.sort_values("time").copy()
    full["volume"] = pd.to_numeric(full["volume"], errors="coerce")
    full["vol_delta"] = full["volume"].diff()

    recent_delta = full["vol_delta"].iloc[-1]
    avg_delta = full["vol_delta"].tail(5).mean()

    vol_ok = False
    if pd.notna(recent_delta) and pd.notna(avg_delta) and avg_delta > 0:
        vol_ok = recent_delta >= avg_delta * MIN_VOLUME_SPIKE

    return {
        "ok": candle_ok,
        "vol_ok": vol_ok,
        "open5": round(open5, 2),
        "high5": round(high5, 2),
        "low5": round(low5, 2),
        "close5": round(close5, 2),
        "close_pos": round(close_pos, 2),
        "vol_delta": round(recent_delta, 0) if pd.notna(recent_delta) else None
    }


def get_daily_signal(code, live_price):
    df = load_price(code)

    if df is None or df.empty or len(df) < 20:
        return None

    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    ma5 = float(close.tail(5).mean())
    rsi = float(calc_rsi(close).iloc[-1])

    return {
        "price": round(float(live_price), 2),
        "ma5": round(ma5, 2),
        "rsi": round(rsi, 2),
        "daily_ok": float(live_price) > ma5 and rsi > MIN_RSI
    }


def run_intraday_entry():
    print("⚡ ENTRY INTRADAY MODE - TRONG PHIÊN")

    priority = load_priority()
    if priority.empty:
        return

    codes = priority["Mã"].dropna().astype(str).str.upper().unique().tolist()

    sent = load_sent()
    state = load_state()

    print("📌 Theo dõi:", ", ".join(codes))
    print("✅ Điều kiện gửi Telegram:")
    print("- Giá live > MA5")
    print("- RSI > 50")
    print("- Xác nhận 2 lần liên tiếp")
    print("- Nến 5 phút xanh mạnh")
    print("- Volume tăng")

    while True:
        try:
            live_map = fetch_live(codes)
            print(f"\n📡 Live fetched: {len(live_map)} mã")

            append_ticks(live_map)

            for _, row in priority.iterrows():
                code = str(row["Mã"]).upper().strip()

                if code not in live_map:
                    continue

                daily = get_daily_signal(code, live_map[code]["price"])
                candle = get_5m_signal(code)

                if daily is None:
                    continue

                if daily["daily_ok"]:
                    state[code] = int(state.get(code, 0)) + 1
                else:
                    state[code] = 0

                confirm_ok = state[code] >= MIN_CONFIRM
                candle_ok = candle.get("ok", False)
                volume_ok = candle.get("vol_ok", False)

                final_ok = daily["daily_ok"] and confirm_ok and candle_ok and volume_ok

                print(
                    f"{code} | price={daily['price']} | MA5={daily['ma5']} | "
                    f"RSI={daily['rsi']} | count={state[code]} | "
                    f"5m={candle_ok} | vol={volume_ok} | FINAL={final_ok}"
                )

                key = f"{code}_ENTRY_HYBRID_{datetime.now().date()}"

                if final_ok and key not in sent:
                    msg = f"""🔥 ENTRY INTRADAY XÁC NHẬN

Mã: {code}

✅ Đủ 5 điều kiện:
- Giá live > MA5
- RSI > 50
- Giữ được 2 lần liên tiếp
- Nến 5 phút xanh mạnh
- Volume tăng

Giá: {daily['price']}
MA5: {daily['ma5']}
RSI: {daily['rsi']}

Nến 5 phút:
Open: {candle.get('open5')}
High: {candle.get('high5')}
Low: {candle.get('low5')}
Close: {candle.get('close5')}
Close position: {candle.get('close_pos')}
Volume delta: {candle.get('vol_delta')}

Backtest:
Winrate 5P selected: {row.get('winrate_5P_selected', '')}
Avg return 5P selected: {row.get('avg_return_5P_selected', '')}
Chú thích: {row.get('Chú thích', '')}

⚠️ Chỉ thăm dò, không all-in.
"""

                    ok = send_telegram(msg)

                    if ok:
                        sent.add(key)
                        save_sent(key)
                        print("✅ Đã gửi Telegram:", code)

            save_state(state)

        except Exception as e:
            print("❌ lỗi:", e)

        print(f"⏳ chờ {INTERVAL_SEC}s...")
        time.sleep(INTERVAL_SEC)


def run_entry_hybrid():
    if is_trading_time():
        run_intraday_entry()
    else:
        build_entry_plan()


run_entry_hybrid()
