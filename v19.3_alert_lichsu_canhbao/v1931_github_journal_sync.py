# -*- coding: utf-8 -*-
"""
V19.3.1 — GitHub Persistent Journal Sync
- Sync alert_journal_v193.csv từ Render local về GitHub.
- Sinh tracker_output/v193_daily_summary.csv
- Sinh tracker_output/v193_alert_stats.csv
"""

from __future__ import annotations

import base64
import os
import time
from io import StringIO
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import requests


SYNC_ENABLE = os.getenv("V193_GITHUB_SYNC_ENABLE", "0").strip() == "1"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.getenv("GITHUB_REPO", "").strip()
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main").strip()

LOCAL_JOURNAL_PATH = os.getenv("V193_JOURNAL_LOCAL_PATH", "alert_journal_v193.csv").strip()
REMOTE_JOURNAL_PATH = os.getenv("V193_JOURNAL_REMOTE_PATH", "tracker_output/alert_journal_v193.csv").strip()
REMOTE_DAILY_SUMMARY_PATH = os.getenv("V193_DAILY_SUMMARY_REMOTE_PATH", "tracker_output/v193_daily_summary.csv").strip()
REMOTE_ALERT_STATS_PATH = os.getenv("V193_ALERT_STATS_REMOTE_PATH", "tracker_output/v193_alert_stats.csv").strip()

MIN_SYNC_INTERVAL_SEC = int(os.getenv("V193_GITHUB_SYNC_MIN_INTERVAL_SEC", "60"))
COMMIT_PREFIX = os.getenv("V193_GITHUB_COMMIT_PREFIX", "V19.3.1 journal sync").strip()

_LAST_SYNC_TS = 0


def _log(msg: str) -> None:
    print(f"[V19.3.1 GITHUB SYNC] {msg}", flush=True)


def _api_url(path: str) -> str:
    clean_path = path.strip().lstrip("/")
    return f"https://api.github.com/repos/{GITHUB_REPO}/contents/{clean_path}"


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _enabled_and_ready() -> bool:
    if not SYNC_ENABLE:
        return False
    if not GITHUB_TOKEN:
        _log("SKIP: thiếu GITHUB_TOKEN")
        return False
    if not GITHUB_REPO or "/" not in GITHUB_REPO:
        _log("SKIP: thiếu GITHUB_REPO dạng owner/repo")
        return False
    return True


def _read_local_text(path: str) -> Optional[str]:
    if not os.path.exists(path):
        _log(f"SKIP: chưa có local journal {path}")
        return None
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return f.read()
    except Exception:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()


def _get_remote_file(path: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        r = requests.get(
            _api_url(path),
            headers=_headers(),
            params={"ref": GITHUB_BRANCH},
            timeout=25,
        )
        if r.status_code == 404:
            return None, None
        if r.status_code >= 400:
            _log(f"WARN get remote {path}: {r.status_code} {r.text[:200]}")
            return None, None

        data = r.json()
        sha = data.get("sha")
        content = data.get("content", "")
        encoding = data.get("encoding", "base64")

        if encoding == "base64" and content:
            decoded = base64.b64decode(content).decode("utf-8-sig", errors="ignore")
        else:
            decoded = ""

        return sha, decoded
    except Exception as e:
        _log(f"WARN get remote exception {path}: {repr(e)}")
        return None, None


def _put_remote_file(path: str, text: str, message: str, sha: Optional[str] = None) -> bool:
    try:
        payload: Dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(text.encode("utf-8-sig")).decode("ascii"),
            "branch": GITHUB_BRANCH,
        }
        if sha:
            payload["sha"] = sha

        r = requests.put(
            _api_url(path),
            headers=_headers(),
            json=payload,
            timeout=30,
        )

        if r.status_code in [200, 201]:
            _log(f"OK pushed {path}")
            return True

        _log(f"WARN push {path}: {r.status_code} {r.text[:300]}")
        return False
    except Exception as e:
        _log(f"WARN push exception {path}: {repr(e)}")
        return False


def _merge_csv_text(remote_text: Optional[str], local_text: str) -> str:
    local_lines = [x.rstrip("\n") for x in (local_text or "").splitlines() if x.strip()]
    remote_lines = [x.rstrip("\n") for x in (remote_text or "").splitlines() if x.strip()]

    if not local_lines and not remote_lines:
        return ""

    header = local_lines[0] if local_lines else remote_lines[0]
    seen = set()
    rows = []

    for lines in [remote_lines, local_lines]:
        for line in lines:
            if not line.strip():
                continue
            if line == header:
                continue
            if line not in seen:
                seen.add(line)
                rows.append(line)

    return "\n".join([header] + rows) + "\n"


def _read_journal_df(text: str) -> pd.DataFrame:
    if not text or not text.strip():
        return pd.DataFrame()
    try:
        return pd.read_csv(StringIO(text))
    except Exception as e:
        _log(f"WARN cannot parse merged journal csv: {repr(e)}")
        return pd.DataFrame()


def _detect_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    lower = {str(c).lower(): c for c in df.columns}
    for c in candidates:
        if c in df.columns:
            return c
        if c.lower() in lower:
            return lower[c.lower()]
    return None


def build_daily_summary_text(journal_text: str) -> str:
    df = _read_journal_df(journal_text)
    if df.empty:
        return "date,total_alerts,v18_entry_alerts,v19_position_alerts,unique_symbols,last_updated\n"

    ts_col = _detect_col(df, ["timestamp", "time", "datetime", "created_at"])
    source_col = _detect_col(df, ["source", "system"])
    symbol_col = _detect_col(df, ["symbol", "Mã", "ticker"])

    if ts_col:
        df["_date"] = pd.to_datetime(df[ts_col], errors="coerce").dt.strftime("%Y-%m-%d")
        df["_date"] = df["_date"].fillna("UNKNOWN")
    else:
        df["_date"] = "UNKNOWN"

    src = df[source_col].astype(str).str.upper() if source_col else pd.Series([""] * len(df))

    rows = []
    for date, g in df.groupby("_date", dropna=False):
        src_g = src.loc[g.index]
        unique_symbols = g[symbol_col].astype(str).str.upper().nunique() if symbol_col else 0

        rows.append({
            "date": date,
            "total_alerts": len(g),
            "v18_entry_alerts": int(src_g.str.contains("V18").sum()),
            "v19_position_alerts": int(src_g.str.contains("V19.2").sum()),
            "unique_symbols": unique_symbols,
            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        })

    out = pd.DataFrame(rows).sort_values("date")
    return out.to_csv(index=False)


def build_alert_stats_text(journal_text: str) -> str:
    df = _read_journal_df(journal_text)
    if df.empty:
        return "symbol,total_alerts,v18_entry_alerts,v19_position_alerts,last_alert_time,last_alert_type\n"

    ts_col = _detect_col(df, ["timestamp", "time", "datetime", "created_at"])
    source_col = _detect_col(df, ["source", "system"])
    symbol_col = _detect_col(df, ["symbol", "Mã", "ticker"])
    type_col = _detect_col(df, ["alert_type", "action", "signal"])

    if not symbol_col:
        return "symbol,total_alerts,v18_entry_alerts,v19_position_alerts,last_alert_time,last_alert_type\n"

    df["_source_upper"] = df[source_col].astype(str).str.upper() if source_col else ""

    rows = []
    for symbol, g in df.groupby(df[symbol_col].astype(str).str.upper(), dropna=False):
        src = g["_source_upper"].astype(str)
        rows.append({
            "symbol": symbol,
            "total_alerts": len(g),
            "v18_entry_alerts": int(src.str.contains("V18").sum()),
            "v19_position_alerts": int(src.str.contains("V19.2").sum()),
            "last_alert_time": str(g[ts_col].iloc[-1]) if ts_col and ts_col in g.columns else "",
            "last_alert_type": str(g[type_col].iloc[-1]) if type_col and type_col in g.columns else "",
        })

    out = pd.DataFrame(rows).sort_values(["total_alerts", "symbol"], ascending=[False, True])
    return out.to_csv(index=False)


def sync_journal_to_github(force: bool = False) -> bool:
    global _LAST_SYNC_TS

    if not _enabled_and_ready():
        return True

    now = int(time.time())
    if not force and _LAST_SYNC_TS and now - _LAST_SYNC_TS < MIN_SYNC_INTERVAL_SEC:
        return True

    local_text = _read_local_text(LOCAL_JOURNAL_PATH)
    if local_text is None:
        return True

    remote_sha, remote_text = _get_remote_file(REMOTE_JOURNAL_PATH)
    merged = _merge_csv_text(remote_text, local_text)

    if remote_text is not None and merged.strip() == remote_text.strip():
        _log("SKIP: remote journal already up to date")
        _LAST_SYNC_TS = now
        return True

    ok1 = _put_remote_file(
        REMOTE_JOURNAL_PATH,
        merged,
        f"{COMMIT_PREFIX}: update alert journal",
        sha=remote_sha,
    )
    if not ok1:
        return False

    daily_text = build_daily_summary_text(merged)
    stats_text = build_alert_stats_text(merged)

    daily_sha, _ = _get_remote_file(REMOTE_DAILY_SUMMARY_PATH)
    stats_sha, _ = _get_remote_file(REMOTE_ALERT_STATS_PATH)

    ok2 = _put_remote_file(
        REMOTE_DAILY_SUMMARY_PATH,
        daily_text,
        f"{COMMIT_PREFIX}: update daily summary",
        sha=daily_sha,
    )
    ok3 = _put_remote_file(
        REMOTE_ALERT_STATS_PATH,
        stats_text,
        f"{COMMIT_PREFIX}: update alert stats",
        sha=stats_sha,
    )

    _LAST_SYNC_TS = now
    return bool(ok1 and ok2 and ok3)


if __name__ == "__main__":
    ok = sync_journal_to_github(force=True)
    print(f"[V19.3.1 GITHUB SYNC] RESULT={'OK' if ok else 'FAIL'}")
