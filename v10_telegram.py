# -*- coding: utf-8 -*-
import os
import requests
import html as _html
import pandas as pd


def _tg_get_secret(name, default=""):
    try:
        val = os.environ.get(name, "")
        if val:
            return val.strip()
        env_path = "/content/drive/MyDrive/thumucbot/url.env"
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    if k.strip() == name:
                        return v.strip().strip('"').strip("'")
    except Exception:
        pass
    return default


def _tg_send_message(text):
    token = _tg_get_secret("TELEGRAM_TOKEN") or _tg_get_secret("TELEGRAM_BOT_TOKEN") or _tg_get_secret("BOT_TOKEN")
    chat_id = _tg_get_secret("TELEGRAM_CHAT_ID") or _tg_get_secret("CHAT_ID")
    if not token or not chat_id:
        print("WARN: Telegram token/chat_id missing, skip alert")
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(url, data={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=20)
        if resp.status_code >= 300:
            print("WARN: Telegram sendMessage failed", resp.status_code, resp.text[:300])
            return False
        return True
    except Exception as e:
        print("WARN: Telegram sendMessage exception", repr(e))
        return False


def _tg_send_document(path, caption="Dashboard HTML - open file to view details"):
    token = _tg_get_secret("TELEGRAM_TOKEN") or _tg_get_secret("TELEGRAM_BOT_TOKEN") or _tg_get_secret("BOT_TOKEN")
    chat_id = _tg_get_secret("TELEGRAM_CHAT_ID") or _tg_get_secret("CHAT_ID")
    if not token or not chat_id or not path or not os.path.exists(path):
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendDocument"
        with open(path, "rb") as f:
            resp = requests.post(url, data={"chat_id": chat_id, "caption": caption}, files={"document": f}, timeout=60)
        if resp.status_code >= 300:
            print("WARN: Telegram sendDocument failed", resp.status_code, resp.text[:300])
            return False
        return True
    except Exception as e:
        print("WARN: Telegram sendDocument exception", repr(e))
        return False


def _tg_find_col(df, names):
    if df is None:
        return None
    for n in names:
        if n in df.columns:
            return n
    low = {str(c).strip().lower(): c for c in df.columns}
    for n in names:
        key = str(n).strip().lower()
        if key in low:
            return low[key]
    return None


def _tg_fmt_num(x):
    try:
        if x is None or str(x) == "nan":
            return ""
        v = float(x)
        if abs(v - round(v)) < 1e-9:
            return str(int(round(v)))
        return f"{v:.2f}"
    except Exception:
        return str(x)


def _tg_build_rows(df, icon, limit=5):
    if df is None or getattr(df, "empty", True):
        return []
    ma_col = _tg_find_col(df, ["Mã", "Ma"])
    action_col = _tg_find_col(df, ["Hành động hiện tại", "Hanh dong hien tai", "Action"])
    strategy_col = _tg_find_col(df, ["Strategy", "Chiến lược", "Chien luoc"])
    risk_col = _tg_find_col(df, ["Risk", "Risk Status"])
    price_col = _tg_find_col(df, ["Giá", "Gia", "Close"])
    score_col = _tg_find_col(df, ["Score"])
    ai_col = _tg_find_col(df, ["AI", "AI Confidence"])
    t2_col = _tg_find_col(df, ["Lợi TB T+2 %", "Loi TB T+2 %", "Lợi T+2 %", "Loi T+2 %"])
    t5_col = _tg_find_col(df, ["Lợi TB T+5 %", "Loi TB T+5 %", "Lợi T+5 %", "Loi T+5 %"])
    hist_col = _tg_find_col(df, ["Độ tin cậy lịch sử", "Do tin cay lich su", "Độ mạnh mẫu", "Do manh mau"])
    win_col = _tg_find_col(df, ["Tỷ lệ thắng %", "Ty le thang %", "Tỷ lệ thắng", "Ty le thang"])

    lines = []
    for _, r in df.head(limit).iterrows():
        ma = _html.escape(str(r.get(ma_col, ""))) if ma_col else ""
        if not ma:
            continue
        action = _html.escape(str(r.get(action_col, ""))) if action_col else ""
        strat = _html.escape(str(r.get(strategy_col, ""))) if strategy_col else ""
        risk = _html.escape(str(r.get(risk_col, ""))) if risk_col else ""
        price = _tg_fmt_num(r.get(price_col, "")) if price_col else ""
        score = _tg_fmt_num(r.get(score_col, "")) if score_col else ""
        ai = _tg_fmt_num(r.get(ai_col, "")) if ai_col else ""
        t2 = _tg_fmt_num(r.get(t2_col, "")) if t2_col else ""
        t5 = _tg_fmt_num(r.get(t5_col, "")) if t5_col else ""
        hist = _html.escape(str(r.get(hist_col, ""))) if hist_col else ""
        win = _tg_fmt_num(r.get(win_col, "")) if win_col else ""
        detail = []
        if action: detail.append(action)
        if strat: detail.append(strat)
        if risk: detail.append("Risk " + risk)
        if price: detail.append("Giá " + price)
        if score: detail.append("Score " + score)
        if ai: detail.append("AI " + ai)
        if win: detail.append("Win " + win + "%")
        if t2: detail.append("T+2 " + t2 + "%")
        if t5: detail.append("T+5 " + t5 + "%")
        if hist and hist.lower() != "nan": detail.append(hist)
        lines.append(f"{icon} <b>{ma}</b> | " + " | ".join(detail))
    return lines


def send_telegram_alert(entry, action_plan, combined, tracker, buy_df, watch_df, macro_text, dashboard_path):
    """Gửi Telegram alert với top tables từ dashboard"""
    try:
        data_date = ""
        try:
            from v10_output import get_report_data_date
            data_date = str(get_report_data_date(combined, entry, action_plan))
        except Exception:
            data_date = ""
        
        market_text = ""
        try:
            market_text = str(globals().get("MARKET_REGIME", ""))
        except Exception:
            market_text = ""

        buy_lines = _tg_build_rows(buy_df, "🟢", limit=5)
        watch_lines = _tg_build_rows(watch_df, "🟡", limit=8)

        parts = []
        parts.append("<b>TRADING BOT - DASHBOARD SYNC</b>")
        if macro_text:
            parts.append(macro_text)
            parts.append("")
        if data_date:
            parts.append(f"Data date: <b>{_html.escape(data_date)}</b>")
        if market_text:
            parts.append(f"Market: <b>{_html.escape(market_text)}</b>")
        parts.append("")
        parts.append("<b>🟢 TOP MUA THẬT</b>")
        if buy_lines:
            parts.extend(buy_lines)
        else:
            parts.append("Không có mã mua thật hôm nay.")
        parts.append("")
        parts.append("<b>🟡 TOP THEO DÕI</b>")
        if watch_lines:
            parts.extend(watch_lines)
        else:
            parts.append("Không có mã theo dõi nổi bật.")
        parts.append("")
        parts.append("Dashboard HTML attached below.")
        text = "\n".join(parts)

        if len(text) > 3800:
            text = text[:3700] + "\n...\nDashboard HTML attached below."
        _tg_send_message(text)
        _tg_send_document(dashboard_path)
    except Exception as e:
        print("WARN: synced Telegram alert failed", repr(e))
