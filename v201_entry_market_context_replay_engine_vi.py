# -*- coding: utf-8 -*-
"""
V20.1 FULL — ENTRY + MARKET CONTEXT REPLAY ENGINE

Output:
- tracker_output/v201_context_replay.csv
- tracker_output/v201_entry_context_summary.csv
- tracker_output/v201_market_context_summary.csv
- tracker_output/v201_fail_patterns.csv
- tracker_output/v201_win_patterns.csv
- tracker_output/v201_context_rules_for_v18.csv
- tracker_output/v201_context_report.txt
"""
from __future__ import annotations
import os, warnings
from pathlib import Path
from typing import Any, Optional
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")

CACHE_DIR = os.getenv("V201_CACHE_DIR", "cache_stock")
OUTPUT_DIR = os.getenv("V201_OUTPUT_DIR", "tracker_output")
BENCHMARK_SYMBOL = os.getenv("V201_BENCHMARK_SYMBOL", "VNINDEX")
MIN_ROWS_PER_PATTERN = int(os.getenv("V201_MIN_ROWS_PER_PATTERN", "20"))
SIGNAL_INPUT_CANDIDATES = [
    os.getenv("V201_SIGNAL_INPUT", "").strip(),
    "tracker_output/v195_weighted_signals.csv",
    "tracker_output/v194_historical_signal_validation.csv",
    "tracker_output/v1942_quality_filtered_signals.csv",
]
LOOKBACKS = [5, 10, 20]


def log(msg: str): print(f"[V20.1] {msg}", flush=True)

def to_num(x: Any, default=np.nan) -> float:
    try:
        if x is None: return default
        if isinstance(x, str):
            x = x.replace("%", "").replace(",", ".").strip()
            if not x: return default
        v = pd.to_numeric(pd.Series([x]), errors="coerce").iloc[0]
        return default if pd.isna(v) else float(v)
    except Exception: return default

def normalize_price(x: Any) -> float:
    v = to_num(x)
    if pd.isna(v): return np.nan
    if v > 1000: v /= 1000.0
    return float(v)

def find_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    lower = {str(c).lower(): c for c in df.columns}
    for c in candidates:
        if c in df.columns: return c
        if c.lower() in lower: return lower[c.lower()]
    return None

def read_csv_smart(path: str) -> pd.DataFrame:
    for enc in ["utf-8-sig", "utf-8", "cp1258", "latin1"]:
        try: return pd.read_csv(path, encoding=enc)
        except Exception: pass
    return pd.read_csv(path)

def normalize_history(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty: return pd.DataFrame()
    date_col = find_col(df, ["date", "time", "Date", "datetime", "TradingDate", "Ngày"])
    open_col = find_col(df, ["open", "Open", "Giá mở cửa"])
    high_col = find_col(df, ["high", "High", "Giá cao nhất"])
    low_col = find_col(df, ["low", "Low", "Giá thấp nhất"])
    close_col = find_col(df, ["close", "Close", "adj_close", "price", "Giá đóng cửa"])
    vol_col = find_col(df, ["volume", "Volume", "vol", "Khối lượng"])
    if close_col is None: return pd.DataFrame()
    out = pd.DataFrame()
    out["date"] = pd.to_datetime(df[date_col], errors="coerce") if date_col else pd.date_range("2000-01-01", periods=len(df))
    out["close"] = pd.to_numeric(df[close_col], errors="coerce").apply(normalize_price)
    out["open"] = pd.to_numeric(df[open_col], errors="coerce").apply(normalize_price) if open_col else out["close"]
    out["high"] = pd.to_numeric(df[high_col], errors="coerce").apply(normalize_price) if high_col else out["close"]
    out["low"] = pd.to_numeric(df[low_col], errors="coerce").apply(normalize_price) if low_col else out["close"]
    out["volume"] = pd.to_numeric(df[vol_col], errors="coerce").fillna(0) if vol_col else 0
    out = out.dropna(subset=["date", "open", "high", "low", "close"]).copy()
    out = out[out["close"] > 0].copy()
    out["high"] = out[["open", "high", "low", "close"]].max(axis=1)
    out["low"] = out[["open", "high", "low", "close"]].min(axis=1)
    return out.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy(); c = out["close"]; v = out["volume"]
    for ma in [5, 10, 20, 50]:
        out[f"ma{ma}"] = c.rolling(ma).mean()
        out[f"dist_ma{ma}_pct"] = np.where(out[f"ma{ma}"] > 0, (c / out[f"ma{ma}"] - 1) * 100, np.nan)
    out["ma20_slope5"] = out["ma20"].pct_change(5) * 100
    out["vol_ma20"] = v.rolling(20).mean()
    out["volume_ratio"] = np.where(out["vol_ma20"] > 0, v / out["vol_ma20"], np.nan)
    for lb in [1, 2, 3, 5, 10, 20]: out[f"ret{lb}"] = c.pct_change(lb) * 100
    out["high20_prev"] = out["high"].rolling(20).max().shift(1)
    out["low20_prev"] = out["low"].rolling(20).min().shift(1)
    out["drawdown20_pct"] = np.where(out["high20_prev"] > 0, (c / out["high20_prev"] - 1) * 100, np.nan)
    out["range20_pct"] = np.where(out["low20_prev"] > 0, (out["high20_prev"] / out["low20_prev"] - 1) * 100, np.nan)
    out["daily_range_pct"] = np.where(out["low"] > 0, (out["high"] / out["low"] - 1) * 100, np.nan)
    return out

def history_path(symbol: str) -> Optional[str]:
    for p in [Path(CACHE_DIR, f"{symbol}.csv"), Path(CACHE_DIR, f"{symbol.upper()}.csv")]:
        if p.exists(): return str(p)
    return None

def load_benchmark() -> pd.DataFrame:
    for name in [BENCHMARK_SYMBOL, "VNINDEX", "VN30"]:
        p = history_path(name)
        if p:
            df = add_indicators(normalize_history(read_csv_smart(p)))
            if not df.empty:
                log(f"Loaded benchmark: {p}"); return df
    return pd.DataFrame()

def load_signals() -> tuple[pd.DataFrame, str]:
    for path in SIGNAL_INPUT_CANDIDATES:
        if path and os.path.exists(path):
            df = read_csv_smart(path)
            if not df.empty:
                log(f"Loaded signals: {path} rows={len(df)}"); return df, path
    raise FileNotFoundError("Không tìm thấy signal input trong tracker_output")

def normalize_signals(df: pd.DataFrame) -> pd.DataFrame:
    symbol_col = find_col(df, ["symbol", "Mã", "ticker", "Ticker"])
    date_col = find_col(df, ["signal_date", "Ngày signal", "date", "Date"])
    result_col = find_col(df, ["result_t5", "result", "Kết quả"])
    signal_col = find_col(df, ["signal", "Signal", "family", "variant"])
    if symbol_col is None or date_col is None: raise ValueError("Signal file thiếu symbol hoặc signal_date")
    out = df.copy()
    out["symbol_norm"] = out[symbol_col].astype(str).str.upper().str.strip()
    out["signal_date_norm"] = pd.to_datetime(out[date_col], errors="coerce")
    out["signal_name_norm"] = out[signal_col].astype(str) if signal_col else "UNKNOWN"
    if result_col:
        out["result_norm"] = out[result_col].astype(str).str.upper().str.strip()
    else:
        ret_col = find_col(out, ["ret_t5_pct"])
        vals = pd.to_numeric(out[ret_col], errors="coerce") if ret_col else pd.Series([np.nan] * len(out))
        out["result_norm"] = np.where(vals > 1, "WIN", np.where(vals < -1, "FAIL", "FLAT"))
    return out.dropna(subset=["signal_date_norm"]).reset_index(drop=True)

def market_context_for_date(bench: pd.DataFrame, signal_date) -> dict[str, Any]:
    if bench is None or bench.empty: return {"market_context": "UNKNOWN", "market_regime": "UNKNOWN"}
    m = bench[bench["date"] <= signal_date]
    if m.empty: return {"market_context": "UNKNOWN", "market_regime": "UNKNOWN"}
    r = m.iloc[-1]
    ret5, ret20, dist, vr = to_num(r.get("ret5")), to_num(r.get("ret20")), to_num(r.get("dist_ma20_pct")), to_num(r.get("volume_ratio"))
    ma20, ma50, close = to_num(r.get("ma20")), to_num(r.get("ma50")), to_num(r.get("close"))
    score = 0
    if close > ma20: score += 25
    if ma20 > ma50: score += 25
    if ret20 > 0: score += 20
    if ret5 > 0: score += 10
    if not pd.isna(vr) and vr >= 1: score += 10
    if not pd.isna(dist) and dist > 5: score -= 10
    if ret5 > 4: score -= 10
    regime = "TĂNG MẠNH" if score >= 70 else "TÍCH CỰC" if score >= 55 else "BÌNH THƯỜNG" if score >= 40 else "YẾU" if score >= 25 else "RẤT YẾU"
    if regime in ["YẾU", "RẤT YẾU"]: context = "MARKET RISK-OFF"
    elif ret5 > 4 or dist > 5: context = "MARKET HƯNG PHẤN / DỄ FOMO"
    elif regime in ["TĂNG MẠNH", "TÍCH CỰC"] and -1 <= dist <= 4: context = "MARKET ỦNG HỘ"
    else: context = "MARKET TRUNG TÍNH"
    return {"market_date": pd.Timestamp(r["date"]).strftime("%Y-%m-%d"), "market_regime": regime, "market_score": round(score, 3), "market_context": context, "market_ret5": round(ret5, 3) if not pd.isna(ret5) else "", "market_ret20": round(ret20, 3) if not pd.isna(ret20) else "", "market_dist_ma20_pct": round(dist, 3) if not pd.isna(dist) else "", "market_volume_ratio": round(vr, 3) if not pd.isna(vr) else ""}

def window_metrics(df: pd.DataFrame, idx: int, lb: int) -> dict[str, Any]:
    w = df.iloc[max(0, idx-lb):idx+1].copy()
    if len(w) < max(3, lb//2): return {}
    close, volume = w["close"], w["volume"]; base = close.iloc[0]
    ret = (close.iloc[-1]/base - 1)*100 if base > 0 else np.nan
    range_pct = (w["high"].max()/w["low"].min() - 1)*100 if w["low"].min() > 0 else np.nan
    avg_range = w["daily_range_pct"].mean()
    half = max(1, len(w)//2); vol_first = volume.iloc[:half].mean(); vol_second = volume.iloc[half:].mean()
    vol_trend = vol_second/vol_first if vol_first > 0 else np.nan
    vol_spike = volume.iloc[-1]/volume.mean() if volume.mean() > 0 else np.nan
    vol_dry = volume.tail(3).mean()/volume.mean() if volume.mean() > 0 else np.nan
    sideway = int((not pd.isna(range_pct) and range_pct <= 10)) + int((not pd.isna(ret) and abs(ret) <= 5)) + int((not pd.isna(avg_range) and avg_range <= 3))
    n = min(5, len(w)); first_range = w["daily_range_pct"].head(n).mean(); last_range = w["daily_range_pct"].tail(n).mean()
    contraction = last_range/first_range if first_range > 0 else np.nan
    return {f"ret_pre{lb}_pct": round(ret,3) if not pd.isna(ret) else "", f"range_pre{lb}_pct": round(range_pct,3) if not pd.isna(range_pct) else "", f"avg_daily_range_pre{lb}_pct": round(avg_range,3) if not pd.isna(avg_range) else "", f"vol_trend_pre{lb}": round(vol_trend,3) if not pd.isna(vol_trend) else "", f"vol_spike_pre{lb}": round(vol_spike,3) if not pd.isna(vol_spike) else "", f"vol_dry_pre{lb}": round(vol_dry,3) if not pd.isna(vol_dry) else "", f"sideway_score_pre{lb}": sideway, f"volatility_contraction_pre{lb}": round(contraction,3) if not pd.isna(contraction) else ""}

def classify_entry_context(row: dict[str, Any]) -> dict[str, str]:
    labels = {}; dist=to_num(row.get("dist_ma20_pct")); ret20=to_num(row.get("ret_pre20_pct")); vol5=to_num(row.get("vol_spike_pre5")); sideway20=to_num(row.get("sideway_score_pre20")); vc20=to_num(row.get("volatility_contraction_pre20")); dd20=to_num(row.get("drawdown20_pct"))
    if not pd.isna(dist): labels["entry_context"] = "ENTRY GẦN MA20" if -3 <= dist <= 3 else "ENTRY XA MA20 / FOMO" if dist > 8 else "ENTRY LƯNG CHỪNG TRÊN MA20" if dist > 3 else "ENTRY DƯỚI MA20 / YẾU"
    if not pd.isna(ret20): labels["extension_context"] = "TĂNG NÓNG TRƯỚC SIGNAL" if ret20 >= 15 else "SUY YẾU TRƯỚC SIGNAL" if ret20 <= -10 else "KHÔNG QUÁ NÓNG"
    if not pd.isna(vol5): labels["volume_context"] = "VOLUME SPIKE FOMO" if vol5 >= 3 else "VOLUME TĂNG VỪA" if vol5 >= 1.2 else "VOLUME CẠN" if vol5 < 0.8 else "VOLUME TRUNG TÍNH"
    if not pd.isna(sideway20): labels["structure_context"] = "CÓ NỀN / SIDEWAY" if sideway20 >= 2 else "KHÔNG RÕ NỀN"
    if not pd.isna(vc20): labels["volatility_context"] = "VOLATILITY CO HẸP" if vc20 < 0.8 else "VOLATILITY MỞ RỘNG" if vc20 > 1.3 else "VOLATILITY TRUNG TÍNH"
    if not pd.isna(dd20): labels["risk_context"] = "DRAWDOWN SÂU" if dd20 < -15 else "PULLBACK LÀNH MẠNH" if -10 <= dd20 <= 0 else "RISK TRUNG TÍNH"
    return labels

def replay_signal(sig: pd.Series, hist_cache: dict[str, pd.DataFrame], bench: pd.DataFrame) -> Optional[dict[str, Any]]:
    symbol, sig_date = sig["symbol_norm"], sig["signal_date_norm"]
    if symbol not in hist_cache:
        p = history_path(symbol)
        if not p: return None
        hist = add_indicators(normalize_history(read_csv_smart(p)))
        if hist.empty: return None
        hist_cache[symbol] = hist
    df = hist_cache[symbol]; m = df[df["date"] <= sig_date]
    if m.empty: return None
    idx = m.index[-1]; r = df.loc[idx]
    out = {"symbol": symbol, "signal_date": pd.Timestamp(r["date"]).strftime("%Y-%m-%d"), "source_signal_date": pd.Timestamp(sig_date).strftime("%Y-%m-%d"), "signal": sig.get("signal_name_norm", "UNKNOWN"), "result": sig.get("result_norm", "UNKNOWN"), "close": round(float(r["close"]),3), "dist_ma20_pct": round(to_num(r.get("dist_ma20_pct")),3), "drawdown20_pct": round(to_num(r.get("drawdown20_pct")),3), "range20_pct": round(to_num(r.get("range20_pct")),3), "volume_ratio": round(to_num(r.get("volume_ratio")),3), "ret5": round(to_num(r.get("ret5")),3), "ret10": round(to_num(r.get("ret10")),3), "ret20": round(to_num(r.get("ret20")),3)}
    for col in ["ret_t2_pct", "ret_t5_pct", "max_drawdown_t5_pct", "weighted_score", "score_bucket"]:
        if col in sig: out[col] = sig[col]
    for lb in LOOKBACKS: out.update(window_metrics(df, idx, lb))
    out.update(classify_entry_context(out)); out.update(market_context_for_date(bench, sig_date))
    return out

def context_stat(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    if df.empty or group_col not in df.columns: return pd.DataFrame()
    rows=[]
    for key,g in df.groupby(group_col):
        n=len(g); win=int((g["result"]=="WIN").sum()); fail=int((g["result"]=="FAIL").sum()); flat=int((g["result"]=="FLAT").sum())
        ret5=pd.to_numeric(g["ret_t5_pct"], errors="coerce").dropna() if "ret_t5_pct" in g.columns else pd.Series(dtype=float)
        dd=pd.to_numeric(g["max_drawdown_t5_pct"], errors="coerce").dropna() if "max_drawdown_t5_pct" in g.columns else pd.Series(dtype=float)
        rows.append({"context_group":group_col,"context_value":key,"n":n,"win":win,"fail":fail,"flat":flat,"winrate_pct":round(win/n*100,2),"failrate_pct":round(fail/n*100,2),"avg_ret_t5_pct":round(ret5.mean(),3) if len(ret5) else "","avg_drawdown_t5_pct":round(dd.mean(),3) if len(dd) else ""})
    return pd.DataFrame(rows).sort_values(["context_group","failrate_pct"], ascending=[True,False])

def build_summary(replay: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    frames=[context_stat(replay,c) for c in cols]
    frames=[f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

def extract_patterns(summary: pd.DataFrame, mode: str) -> pd.DataFrame:
    if summary.empty: return pd.DataFrame()
    out=summary[summary["n"]>=MIN_ROWS_PER_PATTERN].copy()
    if mode=="FAIL":
        out=out[out["failrate_pct"]>=50].copy(); out["pattern_type"]="FAIL_PATTERN"; out["note"]="Giảm điểm hoặc chặn trong V18.2/V19.5"; return out.sort_values(["failrate_pct","n"], ascending=[False,False])
    out=out[out["winrate_pct"]>=45].copy(); out["pattern_type"]="WIN_PATTERN"; out["note"]="Tăng nhẹ confidence, không tự động BUY lớn"; return out.sort_values(["winrate_pct","n"], ascending=[False,False])

def build_rules_for_v18(fail_patterns: pd.DataFrame) -> pd.DataFrame:
    rows=[]
    for _,r in fail_patterns.iterrows():
        group,value=str(r["context_group"]),str(r["context_value"]); action="DOWNGRADE_TO_WATCH"
        if any(k in value for k in ["FOMO","RISK-OFF","DƯỚI MA20","YẾU"]): action="BLOCK_OR_WATCH"
        rows.append({"rule_name":f"V201_{group}_{value[:30]}","context_group":group,"context_value":value,"action":action,"failrate_pct":r["failrate_pct"],"n":r["n"],"reason":"Rule sinh từ V20.1 replay, chỉ dùng như filter giảm rủi ro"})
    return pd.DataFrame(rows)

def write_report(replay, fail_patterns, win_patterns, rules, source_path):
    lines=["="*96,"V20.1 — ENTRY + MARKET CONTEXT REPLAY ENGINE","="*96,f"Source signals: {source_path}",f"Total replay rows: {len(replay)}"]
    if not replay.empty:
        lines += [f"Symbols: {replay['symbol'].nunique()}", f"Date range: {replay['signal_date'].min()} → {replay['signal_date'].max()}", f"Result counts: {replay['result'].value_counts().to_dict()}"]
    lines += ["","Top FAIL patterns:"]
    if fail_patterns.empty: lines.append("- Chưa có fail pattern đủ mẫu.")
    else:
        for _,r in fail_patterns.head(20).iterrows(): lines.append(f"- {r['context_group']} = {r['context_value']}: n={r['n']}, fail={r['failrate_pct']}%, win={r['winrate_pct']}%")
    lines += ["","Top WIN patterns:"]
    if win_patterns.empty: lines.append("- Chưa có win pattern đủ mẫu.")
    else:
        for _,r in win_patterns.head(20).iterrows(): lines.append(f"- {r['context_group']} = {r['context_value']}: n={r['n']}, win={r['winrate_pct']}%, fail={r['failrate_pct']}%")
    lines += ["","Rules for V18.2:"]
    if rules.empty: lines.append("- Chưa có rule đủ mẫu.")
    else:
        for _,r in rules.head(20).iterrows(): lines.append(f"- {r['context_group']}={r['context_value']} -> {r['action']} | fail={r['failrate_pct']}%, n={r['n']}")
    lines += ["","Cách dùng:","- Replay chạy cuối tuần.","- v201_entry_context_filter.py dùng realtime trong V18.2.","- Rule chỉ dùng để hạ rủi ro, không dùng để tự động BUY lớn."]
    Path(OUTPUT_DIR).mkdir(exist_ok=True); Path(OUTPUT_DIR,"v201_context_report.txt").write_text("\n".join(lines), encoding="utf-8")

def main():
    Path(OUTPUT_DIR).mkdir(exist_ok=True); log("START V20.1")
    sig_raw,source_path=load_signals(); signals=normalize_signals(sig_raw); bench=load_benchmark(); hist_cache={}; rows=[]
    for idx,(_,sig) in enumerate(signals.iterrows(),1):
        try:
            row=replay_signal(sig,hist_cache,bench)
            if row: rows.append(row)
            if idx%500==0: log(f"Processed {idx}/{len(signals)} | replay={len(rows)}")
        except Exception as e: log(f"WARN replay failed row={idx}: {repr(e)}")
    replay=pd.DataFrame(rows)
    entry_cols=["entry_context","extension_context","volume_context","structure_context","volatility_context","risk_context"]
    market_cols=["market_context","market_regime"]
    entry_summary=build_summary(replay,entry_cols); market_summary=build_summary(replay,market_cols)
    all_summary=pd.concat([entry_summary,market_summary], ignore_index=True) if not entry_summary.empty or not market_summary.empty else pd.DataFrame()
    fail_patterns=extract_patterns(all_summary,"FAIL"); win_patterns=extract_patterns(all_summary,"WIN"); rules=build_rules_for_v18(fail_patterns)
    replay.to_csv(Path(OUTPUT_DIR,"v201_context_replay.csv"),index=False,encoding="utf-8-sig")
    entry_summary.to_csv(Path(OUTPUT_DIR,"v201_entry_context_summary.csv"),index=False,encoding="utf-8-sig")
    market_summary.to_csv(Path(OUTPUT_DIR,"v201_market_context_summary.csv"),index=False,encoding="utf-8-sig")
    fail_patterns.to_csv(Path(OUTPUT_DIR,"v201_fail_patterns.csv"),index=False,encoding="utf-8-sig")
    win_patterns.to_csv(Path(OUTPUT_DIR,"v201_win_patterns.csv"),index=False,encoding="utf-8-sig")
    rules.to_csv(Path(OUTPUT_DIR,"v201_context_rules_for_v18.csv"),index=False,encoding="utf-8-sig")
    write_report(replay,fail_patterns,win_patterns,rules,source_path)
    log("DONE")

if __name__ == "__main__": main()
