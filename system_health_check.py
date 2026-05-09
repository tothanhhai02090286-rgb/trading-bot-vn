# -*- coding: utf-8 -*-
"""
system_health_check.py
Chạy sau run_daily_system.py để kiểm tra sức khỏe hệ thống.
Không đổi tín hiệu, không đổi dashboard, không can thiệp logic trading.

Output:
- system_health_check.csv
- system_health_report.txt
- Telegram health report nếu có TELEGRAM_TOKEN + TELEGRAM_CHAT_ID
"""

from __future__ import annotations

import os
import glob
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import requests


CACHE_DIR = os.getenv("CACHE_DIR", "cache_stock")
UNIVERSE_FILE = os.getenv("UNIVERSE_FILE", "universe.py")

ALL_RESULT_PATH = os.getenv("ALL_RESULT_PATH", "all_signal_results.csv")
AI_RISK_PATH = os.getenv("AI_RISK_PATH", "ai_risk_filtered.csv")
INTRADAY_WATCHLIST_PATH = os.getenv("INTRADAY_WATCHLIST_PATH", "intraday_watchlist.csv")
DASHBOARD_PATH = os.getenv("DASHBOARD_PATH", "ai_risk_dashboard.html")

HEALTH_CSV = os.getenv("HEALTH_CSV", "system_health_check.csv")
HEALTH_TXT = os.getenv("HEALTH_TXT", "system_health_report.txt")


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_read_csv(path: str) -> pd.DataFrame:
    try:
        if not os.path.exists(path):
            return pd.DataFrame()
        return pd.read_csv(path)
    except Exception as e:
        print(f"WARN cannot read {path}: {repr(e)}", flush=True)
        return pd.DataFrame()


def load_universe() -> list[str]:
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("universe_mod", UNIVERSE_FILE)
        if spec is None or spec.loader is None:
            return []
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        universe = getattr(mod, "UNIVERSE", [])
        return [str(x).upper().strip() for x in universe if str(x).strip()]
    except Exception as e:
        print("WARN cannot load universe.py:", repr(e), flush=True)
        return []


def find_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    if df is None or df.empty:
        return None
    lower = {str(c).strip().lower(): c for c in df.columns}
    for name in candidates:
        key = str(name).strip().lower()
        if key in lower:
            return lower[key]
    return None


def latest_date_in_df(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return ""
    date_col = find_col(df, ["Ngay", "Ngày", "Date", "time", "date"])
    if date_col is None:
        return ""
    try:
        s = pd.to_datetime(df[date_col], errors="coerce")
        if s.notna().any():
            return str(s.max().date())
    except Exception:
        pass
    try:
        vals = df[date_col].dropna().astype(str)
        return vals.max() if len(vals) else ""
    except Exception:
        return ""


def latest_cache_dates() -> tuple[str, dict[str, str]]:
    latest_map = {}
    paths = sorted(glob.glob(os.path.join(CACHE_DIR, "*.csv")))
    for p in paths:
        symbol = Path(p).stem.upper()
        df = safe_read_csv(p)
        d = latest_date_in_df(df)
        if d:
            latest_map[symbol] = d
    if not latest_map:
        return "", latest_map
    return max(latest_map.values()), latest_map


def file_status(path: str) -> dict:
    exists = os.path.exists(path)
    size = os.path.getsize(path) if exists else 0
    rows = 0
    latest = ""
    if exists and path.lower().endswith(".csv"):
        df = safe_read_csv(path)
        rows = len(df)
        latest = latest_date_in_df(df)
    return {"file": path, "exists": exists, "size_bytes": size, "rows": rows, "latest_date": latest}


def send_telegram(text: str) -> bool:
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        print("WARN Telegram token/chat_id missing, skip health telegram", flush=True)
        return False

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
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
        print("TELEGRAM HEALTH STATUS:", resp.status_code, resp.text[:200], flush=True)
        return resp.status_code == 200
    except Exception as e:
        print("WARN send telegram health failed:", repr(e), flush=True)
        return False


def build_health_report() -> tuple[pd.DataFrame, str, bool]:
    universe = load_universe()
    universe_set = set(universe)

    cache_latest, cache_dates = latest_cache_dates()
    cache_symbols = set(cache_dates.keys())

    all_df = safe_read_csv(ALL_RESULT_PATH)
    ai_df = safe_read_csv(AI_RISK_PATH)
    watch_df = safe_read_csv(INTRADAY_WATCHLIST_PATH)

    ma_col_all = find_col(all_df, ["Ma", "Mã", "Symbol", "Ticker"])
    ma_col_ai = find_col(ai_df, ["Ma", "Mã", "Symbol", "Ticker"])
    ma_col_watch = find_col(watch_df, ["Mã", "Ma", "Symbol", "Ticker"])

    all_symbols = set(all_df[ma_col_all].dropna().astype(str).str.upper().str.strip()) if ma_col_all else set()
    ai_symbols = set(ai_df[ma_col_ai].dropna().astype(str).str.upper().str.strip()) if ma_col_ai else set()
    watch_symbols = set(watch_df[ma_col_watch].dropna().astype(str).str.upper().str.strip()) if ma_col_watch else set()

    missing_in_cache = sorted(universe_set - cache_symbols)
    missing_in_all_result = sorted(universe_set - all_symbols)

    all_latest = latest_date_in_df(all_df)
    ai_latest = latest_date_in_df(ai_df)
    watch_latest = latest_date_in_df(watch_df)

    stale_cache = sorted([s for s, d in cache_dates.items() if cache_latest and d != cache_latest])

    rows = []

    def add(metric, value, status="OK", note=""):
        rows.append({
            "time": now_str(),
            "metric": metric,
            "value": value,
            "status": status,
            "note": note,
        })

    add("universe_count", len(universe), "OK" if len(universe) > 0 else "WARN")
    add("cache_symbol_count", len(cache_symbols), "OK" if len(cache_symbols) >= max(len(universe) - 5, 1) else "WARN")
    add("all_result_symbol_count", len(all_symbols), "OK" if len(all_symbols) >= max(len(universe) - 5, 1) else "WARN")
    add("ai_risk_rows", len(ai_df), "OK" if len(ai_df) > 0 else "WARN")
    add("intraday_watchlist_rows", len(watch_df), "OK" if len(watch_df) > 0 else "WARN")
    add("cache_latest_date", cache_latest, "OK" if cache_latest else "WARN")
    add("all_result_latest_date", all_latest, "OK" if (not cache_latest or all_latest == cache_latest) else "WARN")
    add("ai_risk_latest_date", ai_latest, "OK" if (not cache_latest or ai_latest == cache_latest or ai_latest == "") else "WARN")
    add("watchlist_latest_date", watch_latest, "OK" if watch_latest or len(watch_df) > 0 else "WARN")
    add("missing_in_cache_count", len(missing_in_cache), "OK" if len(missing_in_cache) == 0 else "WARN", ",".join(missing_in_cache[:30]))
    add("missing_in_all_result_count", len(missing_in_all_result), "OK" if len(missing_in_all_result) == 0 else "WARN", ",".join(missing_in_all_result[:30]))
    add("stale_cache_count", len(stale_cache), "OK" if len(stale_cache) == 0 else "WARN", ",".join(stale_cache[:30]))

    for path in [ALL_RESULT_PATH, AI_RISK_PATH, INTRADAY_WATCHLIST_PATH, DASHBOARD_PATH]:
        f = file_status(path)
        add(
            f"file_{path}",
            f"exists={f['exists']} rows={f['rows']} size={f['size_bytes']} latest={f['latest_date']}",
            "OK" if f["exists"] and f["size_bytes"] > 0 else "WARN",
        )

    health_df = pd.DataFrame(rows)
    has_warning = bool((health_df["status"] == "WARN").any())

    status_icon = "⚠️" if has_warning else "✅"
    title = "BOT EOD WARNING" if has_warning else "BOT EOD HOÀN TẤT"

    report_lines = [
        f"{status_icon} <b>{title}</b>",
        "",
        f"Time: <b>{now_str()}</b>",
        f"Cache latest: <b>{cache_latest or 'N/A'}</b>",
        f"All result latest: <b>{all_latest or 'N/A'}</b>",
        f"AI risk latest: <b>{ai_latest or 'N/A'}</b>",
        "",
        f"Universe: <b>{len(universe)}</b>",
        f"Cache symbols: <b>{len(cache_symbols)}</b>",
        f"All result symbols: <b>{len(all_symbols)}</b>",
        f"AI risk rows: <b>{len(ai_df)}</b>",
        f"Intraday watchlist rows: <b>{len(watch_df)}</b>",
        "",
        f"Missing cache: <b>{len(missing_in_cache)}</b>",
        f"Missing output: <b>{len(missing_in_all_result)}</b>",
        f"Stale cache: <b>{len(stale_cache)}</b>",
    ]

    if missing_in_cache:
        report_lines.append("Missing cache sample: " + ", ".join(missing_in_cache[:15]))
    if missing_in_all_result:
        report_lines.append("Missing output sample: " + ", ".join(missing_in_all_result[:15]))
    if stale_cache:
        report_lines.append("Stale cache sample: " + ", ".join(stale_cache[:15]))

    return health_df, "\n".join(report_lines), has_warning


def main():
    print("SYSTEM HEALTH CHECK STARTED", flush=True)
    health_df, report, _ = build_health_report()

    health_df.to_csv(HEALTH_CSV, index=False, encoding="utf-8-sig")
    Path(HEALTH_TXT).write_text(report, encoding="utf-8")

    print(report.replace("<b>", "").replace("</b>", ""), flush=True)
    send_telegram(report)

    print(f"OK wrote {HEALTH_CSV}", flush=True)
    print(f"OK wrote {HEALTH_TXT}", flush=True)
    raise SystemExit(0)


if __name__ == "__main__":
    main()
