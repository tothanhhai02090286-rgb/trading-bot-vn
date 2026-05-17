# -*- coding: utf-8 -*-
"""
v202_context_drilldown_engine_vi.py

V20.2 — CONTEXT DRILLDOWN + RULE GENERATOR VI
=============================================

Mục tiêu:
- Không còn chỉ báo chung chung như "ENTRY TRUNG TÍNH".
- Khoan sâu nguyên nhân fail/win:
  + FOMO: ret5, ret10, ret20, dist MA20, volume spike
  + Entry quality: gần/xa MA20, dưới MA20, quá xa VWAP nếu có dữ liệu
  + Base quality: sideway, range hẹp, volatility co hẹp
  + Volume behavior: volume spike, volume cạn, volume tăng dần
  + Market context: VNINDEX ret5, ret20, dist MA20, risk-on/risk-off, overheating
  + Risk context: drawdown20, range20
  + Combo patterns: kết hợp 2-3 điều kiện

Input ưu tiên:
1. tracker_output/v201_context_replay.csv
2. tracker_output/v20_context_replay.csv
3. tracker_output/v195_weighted_signals.csv

Nếu input là V19.5, engine vẫn chạy nhưng combo sẽ ít hơn vì thiếu context replay.

Output:
- tracker_output/v202_drilldown_patterns.csv
- tracker_output/v202_fail_rules.csv
- tracker_output/v202_win_rules.csv
- tracker_output/v202_realtime_rules_for_v18.csv
- tracker_output/v202_context_report.txt
"""

from __future__ import annotations

import os
import itertools
import warnings
from pathlib import Path
from typing import Any, Optional, List, Dict

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

SYSTEM_VERSION = "V20.2_CONTEXT_DRILLDOWN_RULE_GENERATOR_VI"

OUTPUT_DIR = os.getenv("V202_OUTPUT_DIR", "tracker_output")
INPUT_CANDIDATES = [
    os.getenv("V202_INPUT", "").strip(),
    "tracker_output/v201_context_replay.csv",
    "tracker_output/v20_context_replay.csv",
    "tracker_output/v195_weighted_signals.csv",
]

MIN_ROWS = int(os.getenv("V202_MIN_ROWS", "30"))
FAILRATE_TH = float(os.getenv("V202_FAILRATE_TH", "55"))
WINRATE_TH = float(os.getenv("V202_WINRATE_TH", "45"))
MAX_COMBO_SIZE = int(os.getenv("V202_MAX_COMBO_SIZE", "3"))


def log(msg: str) -> None:
    print(f"[V20.2] {msg}", flush=True)


def read_csv_smart(path: str) -> pd.DataFrame:
    for enc in ["utf-8-sig", "utf-8", "cp1258", "latin1"]:
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            pass
    return pd.read_csv(path)


def to_num(x: Any, default=np.nan) -> float:
    try:
        if x is None:
            return default
        if isinstance(x, str):
            x = x.replace("%", "").replace(",", ".").strip()
            if not x:
                return default
        v = pd.to_numeric(pd.Series([x]), errors="coerce").iloc[0]
        return default if pd.isna(v) else float(v)
    except Exception:
        return default


def find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    lower = {str(c).lower(): c for c in df.columns}
    for c in candidates:
        if c in df.columns:
            return c
        if c.lower() in lower:
            return lower[c.lower()]
    return None


def load_input() -> tuple[pd.DataFrame, str]:
    for path in INPUT_CANDIDATES:
        if path and os.path.exists(path):
            df = read_csv_smart(path)
            if not df.empty:
                log(f"Loaded input {path} rows={len(df)}")
                return df, path
    raise FileNotFoundError("Không tìm thấy input V20.1/V20/V19.5 trong tracker_output")


def normalize_result(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    result_col = find_col(out, ["result", "result_t5", "result_norm"])
    if result_col:
        out["result_norm"] = out[result_col].astype(str).str.upper().str.strip()
    else:
        ret_col = find_col(out, ["ret_t5_pct"])
        if ret_col:
            ret = pd.to_numeric(out[ret_col], errors="coerce")
            out["result_norm"] = np.where(ret > 1, "WIN", np.where(ret < -1, "FAIL", "FLAT"))
        else:
            out["result_norm"] = "UNKNOWN"

    if "ret_t5_pct" not in out.columns:
        ret_col = find_col(out, ["avg_ret_t5_pct"])
        if ret_col:
            out["ret_t5_pct"] = out[ret_col]

    return out


def add_numeric_buckets(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    # Ensure aliases from different versions.
    alias_map = {
        "stock_ret5": ["ret5", "ret_pre5_pct"],
        "stock_ret10": ["ret10", "ret_pre10_pct"],
        "stock_ret20": ["ret20", "ret_pre20_pct"],
        "stock_dist_ma20": ["dist_ma20_pct"],
        "stock_volume_ratio": ["volume_ratio"],
        "stock_drawdown20": ["drawdown20_pct"],
        "stock_range20": ["range20_pct", "range_pre20_pct"],
        "market_ret5_x": ["market_ret5"],
        "market_ret20_x": ["market_ret20"],
        "market_dist_ma20": ["market_dist_ma20_pct"],
        "market_volume_ratio_x": ["market_volume_ratio"],
        "vol_spike5": ["vol_spike_pre5"],
        "vol_trend20": ["vol_trend_pre20"],
        "sideway20": ["sideway_score_pre20"],
        "vol_contraction20": ["volatility_contraction_pre20"],
    }

    for new_col, candidates in alias_map.items():
        if new_col not in out.columns:
            src = find_col(out, candidates)
            if src:
                out[new_col] = pd.to_numeric(out[src], errors="coerce")
            else:
                out[new_col] = np.nan

    # FOMO buckets
    out["B_STOCK_RET5_HOT"] = out["stock_ret5"] > 8
    out["B_STOCK_RET20_HOT"] = out["stock_ret20"] > 15
    out["B_STOCK_DIST_MA20_3_8"] = (out["stock_dist_ma20"] > 3) & (out["stock_dist_ma20"] <= 8)
    out["B_STOCK_DIST_MA20_GT8"] = out["stock_dist_ma20"] > 8
    out["B_STOCK_BELOW_MA20"] = out["stock_dist_ma20"] < -3
    out["B_VOLUME_SPIKE_GT3"] = out["stock_volume_ratio"] > 3
    out["B_VOLUME_GOOD_1_2_2"] = (out["stock_volume_ratio"] >= 1.2) & (out["stock_volume_ratio"] <= 2.0)
    out["B_VOLUME_WEAK_LT1"] = out["stock_volume_ratio"] < 1

    # Base quality
    out["B_SIDEWAY20_GOOD"] = out["sideway20"] >= 2
    out["B_RANGE20_TIGHT"] = out["stock_range20"] <= 10
    out["B_VOL_CONTRACTION"] = out["vol_contraction20"] < 0.8
    out["B_VOL_EXPANSION"] = out["vol_contraction20"] > 1.3

    # Market buckets
    out["B_MARKET_RET5_HOT"] = out["market_ret5_x"] > 4
    out["B_MARKET_RET20_NEG"] = out["market_ret20_x"] < -5
    out["B_MARKET_DIST_GT5"] = out["market_dist_ma20"] > 5
    out["B_MARKET_VOLUME_SPIKE"] = out["market_volume_ratio_x"] > 2.5

    if "market_context" in out.columns:
        out["B_MARKET_RISK_OFF"] = out["market_context"].astype(str).str.upper().str.contains("RISK-OFF|RẤT YẾU|YẾU", na=False)
        out["B_MARKET_FOMO"] = out["market_context"].astype(str).str.upper().str.contains("FOMO|HƯNG PHẤN", na=False)
    else:
        out["B_MARKET_RISK_OFF"] = False
        out["B_MARKET_FOMO"] = False

    # Risk buckets
    out["B_DRAWDOWN_DEEP"] = out["stock_drawdown20"] < -15
    out["B_DRAWDOWN_HEALTHY"] = (out["stock_drawdown20"] >= -10) & (out["stock_drawdown20"] <= 0)

    # Existing labels as buckets, if present.
    for col in ["entry_context", "extension_context", "volume_context", "structure_context", "volatility_context", "risk_context", "market_context", "market_regime", "score_bucket"]:
        if col in out.columns:
            safe = out[col].astype(str).str.upper().str.replace(" ", "_", regex=False).str.replace("/", "_", regex=False)
            # Limit number of unique generated labels to avoid explosion.
            for val in safe.dropna().unique()[:30]:
                if val and val != "NAN":
                    out[f"L_{col}_{val[:35]}"] = safe == val

    return out


def bucket_descriptions() -> Dict[str, str]:
    return {
        "B_STOCK_RET5_HOT": "stock_ret5 > 8%",
        "B_STOCK_RET20_HOT": "stock_ret20 > 15%",
        "B_STOCK_DIST_MA20_3_8": "stock_dist_ma20 3-8%",
        "B_STOCK_DIST_MA20_GT8": "stock_dist_ma20 > 8%",
        "B_STOCK_BELOW_MA20": "stock_dist_ma20 < -3%",
        "B_VOLUME_SPIKE_GT3": "volume_ratio > 3x",
        "B_VOLUME_GOOD_1_2_2": "volume_ratio 1.2-2.0x",
        "B_VOLUME_WEAK_LT1": "volume_ratio < 1x",
        "B_SIDEWAY20_GOOD": "sideway_score20 >= 2",
        "B_RANGE20_TIGHT": "range20 <= 10%",
        "B_VOL_CONTRACTION": "volatility_contraction20 < 0.8",
        "B_VOL_EXPANSION": "volatility_contraction20 > 1.3",
        "B_MARKET_RET5_HOT": "market_ret5 > 4%",
        "B_MARKET_RET20_NEG": "market_ret20 < -5%",
        "B_MARKET_DIST_GT5": "market_dist_ma20 > 5%",
        "B_MARKET_VOLUME_SPIKE": "market_volume_ratio > 2.5x",
        "B_MARKET_RISK_OFF": "market_context risk-off",
        "B_MARKET_FOMO": "market_context fomo/hưng phấn",
        "B_DRAWDOWN_DEEP": "drawdown20 < -15%",
        "B_DRAWDOWN_HEALTHY": "drawdown20 -10% to 0%",
    }


def condition_columns(df: pd.DataFrame) -> List[str]:
    cols = [c for c in df.columns if c.startswith("B_") or c.startswith("L_")]
    # Drop buckets with too few trues or too many trues.
    good = []
    n = len(df)
    for c in cols:
        cnt = int(df[c].fillna(False).sum())
        if MIN_ROWS <= cnt <= max(MIN_ROWS, n - MIN_ROWS):
            good.append(c)
    return good


def stats_for_mask(df: pd.DataFrame, mask: pd.Series, pattern_name: str, conditions: List[str]) -> Optional[Dict[str, Any]]:
    g = df[mask].copy()
    n = len(g)
    if n < MIN_ROWS:
        return None

    win = int((g["result_norm"] == "WIN").sum())
    fail = int((g["result_norm"] == "FAIL").sum())
    flat = int((g["result_norm"] == "FLAT").sum())
    ret5 = pd.to_numeric(g.get("ret_t5_pct", pd.Series(dtype=float)), errors="coerce").dropna()
    t2 = pd.to_numeric(g.get("ret_t2_pct", pd.Series(dtype=float)), errors="coerce").dropna()
    dd = pd.to_numeric(g.get("max_drawdown_t5_pct", pd.Series(dtype=float)), errors="coerce").dropna()

    return {
        "pattern": pattern_name,
        "conditions": " + ".join(conditions),
        "n": n,
        "win": win,
        "fail": fail,
        "flat": flat,
        "winrate_pct": round(win / n * 100, 2),
        "failrate_pct": round(fail / n * 100, 2),
        "avg_ret_t2_pct": round(t2.mean(), 3) if len(t2) else "",
        "avg_ret_t5_pct": round(ret5.mean(), 3) if len(ret5) else "",
        "avg_drawdown_t5_pct": round(dd.mean(), 3) if len(dd) else "",
    }


def generate_patterns(df: pd.DataFrame) -> pd.DataFrame:
    desc = bucket_descriptions()
    cols = condition_columns(df)
    rows = []

    for size in range(1, MAX_COMBO_SIZE + 1):
        for combo in itertools.combinations(cols, size):
            # Avoid huge label-only combos.
            if size >= 2 and sum(1 for c in combo if c.startswith("L_")) >= 2:
                continue

            mask = pd.Series(True, index=df.index)
            for c in combo:
                mask = mask & df[c].fillna(False)

            readable = [desc.get(c, c.replace("B_", "").replace("L_", "label:")) for c in combo]
            st = stats_for_mask(df, mask, f"COMBO_{size}", readable)
            if st:
                st["combo_size"] = size
                rows.append(st)

    if not rows:
        return pd.DataFrame()

    out = pd.DataFrame(rows)
    out = out.sort_values(["combo_size", "failrate_pct", "n"], ascending=[True, False, False]).reset_index(drop=True)
    return out


def make_rules(patterns: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if patterns.empty:
        empty = pd.DataFrame()
        return empty, empty, empty

    fail_rules = patterns[
        (patterns["n"] >= MIN_ROWS)
        & (patterns["failrate_pct"] >= FAILRATE_TH)
    ].copy()
    fail_rules["rule_type"] = "FAIL_RULE"
    fail_rules["action"] = np.where(
        fail_rules["failrate_pct"] >= 62,
        "BLOCK_OR_WATCH",
        "DOWNGRADE_TO_WATCH",
    )
    fail_rules["confidence"] = np.where(
        fail_rules["n"] >= 100,
        "HIGH_SAMPLE",
        "MEDIUM_SAMPLE",
    )

    win_rules = patterns[
        (patterns["n"] >= MIN_ROWS)
        & (patterns["winrate_pct"] >= WINRATE_TH)
        & (patterns["failrate_pct"] < 45)
    ].copy()
    win_rules["rule_type"] = "WIN_RULE"
    win_rules["action"] = "ALLOW_KEEP_ONLY"
    win_rules["confidence"] = np.where(
        win_rules["n"] >= 100,
        "HIGH_SAMPLE",
        "MEDIUM_SAMPLE",
    )

    realtime = fail_rules.copy()
    if not realtime.empty:
        realtime = realtime[[
            "conditions", "n", "failrate_pct", "winrate_pct", "avg_ret_t2_pct", "avg_ret_t5_pct",
            "avg_drawdown_t5_pct", "action", "confidence"
        ]].copy()
        realtime.insert(0, "rule_name", [f"V202_RULE_{i+1:03d}" for i in range(len(realtime))])
        realtime["reason"] = "Sinh từ V20.2 drilldown; chỉ dùng để hạ recommendation trong V18.2"
        realtime = realtime.sort_values(["action", "failrate_pct", "n"], ascending=[True, False, False])

    return fail_rules, win_rules, realtime


def write_report(patterns: pd.DataFrame, fail_rules: pd.DataFrame, win_rules: pd.DataFrame, realtime: pd.DataFrame, source: str, n_total: int) -> None:
    lines = []
    lines.append("=" * 96)
    lines.append("V20.2 — CONTEXT DRILLDOWN + RULE GENERATOR")
    lines.append("=" * 96)
    lines.append(f"Source: {source}")
    lines.append(f"Total rows: {n_total}")
    lines.append("")
    lines.append("Mục tiêu:")
    lines.append("- Tách nhỏ nguyên nhân FAIL/WIN.")
    lines.append("- Sinh rule cụ thể cho V18.2 realtime.")
    lines.append("- Rule chỉ dùng để hạ rủi ro, không dùng để tự động nâng BUY.")
    lines.append("")
    lines.append("Top FAIL rules:")
    if fail_rules.empty:
        lines.append("- Chưa có fail rule đủ mẫu/ngưỡng.")
    else:
        for _, r in fail_rules.head(25).iterrows():
            lines.append(
                f"- {r['conditions']} | n={r['n']}, fail={r['failrate_pct']}%, win={r['winrate_pct']}%, "
                f"T+5={r['avg_ret_t5_pct']}%, action={r['action']}"
            )
    lines.append("")
    lines.append("Top WIN rules:")
    if win_rules.empty:
        lines.append("- Chưa có win rule đủ mẫu/ngưỡng.")
    else:
        for _, r in win_rules.head(25).iterrows():
            lines.append(
                f"- {r['conditions']} | n={r['n']}, win={r['winrate_pct']}%, fail={r['failrate_pct']}%, "
                f"T+5={r['avg_ret_t5_pct']}%, action={r['action']}"
            )
    lines.append("")
    lines.append("Cách dùng:")
    lines.append("- Mở v202_realtime_rules_for_v18.csv để xem rule gắn vào V18.2.")
    lines.append("- BLOCK_OR_WATCH: nếu V18.2 báo BUY thì hạ về WATCH hoặc KHÔNG VÀO.")
    lines.append("- DOWNGRADE_TO_WATCH: hạ recommendation về WATCH.")
    lines.append("- ALLOW_KEEP_ONLY: chỉ giữ nguyên, không nâng lên BUY lớn.")
    lines.append("")
    lines.append("Cảnh báo chống học vẹt:")
    lines.append("- Không dùng rule có n quá thấp.")
    lines.append("- Ưu tiên combo 2 điều kiện hơn combo 3 nếu hiệu quả gần nhau.")
    lines.append("- Phải chạy lại định kỳ sau khi có alert_journal live.")
    Path(OUTPUT_DIR).mkdir(exist_ok=True)
    Path(OUTPUT_DIR, "v202_context_report.txt").write_text("\n".join(lines), encoding="utf-8")


def main():
    Path(OUTPUT_DIR).mkdir(exist_ok=True)
    log(f"START {SYSTEM_VERSION}")

    raw, source = load_input()
    df = normalize_result(raw)
    df = add_numeric_buckets(df)

    patterns = generate_patterns(df)
    fail_rules, win_rules, realtime = make_rules(patterns)

    patterns.to_csv(Path(OUTPUT_DIR, "v202_drilldown_patterns.csv"), index=False, encoding="utf-8-sig")
    fail_rules.to_csv(Path(OUTPUT_DIR, "v202_fail_rules.csv"), index=False, encoding="utf-8-sig")
    win_rules.to_csv(Path(OUTPUT_DIR, "v202_win_rules.csv"), index=False, encoding="utf-8-sig")
    realtime.to_csv(Path(OUTPUT_DIR, "v202_realtime_rules_for_v18.csv"), index=False, encoding="utf-8-sig")
    write_report(patterns, fail_rules, win_rules, realtime, source, len(df))

    log(f"Patterns: {len(patterns)} | fail_rules={len(fail_rules)} | win_rules={len(win_rules)}")
    log(f"Output folder: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
