# -*- coding: utf-8 -*-
"""
global_macro_layer.py - FIXED CLOSE DATA VERSION

Fix:
- yfinance import OK nhưng bảng macro bị trống do cột Close trả về dạng DataFrame/MultiIndex.
- Bản này đọc Close chắc hơn và có fallback qua yf.Ticker().history().
- Macro chỉ hạ BUY NOW xuống WATCHLIST khi RISK OFF/PANIC, không tự nâng WATCH lên BUY.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, Any, Optional, List

import pandas as pd

GLOBAL_TICKERS = {
    "SP500": "^GSPC",
    "NASDAQ": "^IXIC",
    "VIX": "^VIX",
    "US10Y": "^TNX",
    "DXY": "DX-Y.NYB",
    "NIKKEI": "^N225",
    "KOSPI": "^KS11",
    "SHANGHAI": "000001.SS",
    "OIL": "CL=F",
}

@dataclass
class MacroSignal:
    name: str
    ticker: str
    value: Optional[float]
    ret_1d: Optional[float]
    ret_5d: Optional[float]
    above_ma20: Optional[bool]
    score: float
    status: str
    reason: str

@dataclass
class GlobalMacroResult:
    generated_at: str
    data_status: str
    global_score: float
    global_mode: str
    risk_action: str
    signals: List[Dict[str, Any]]
    note: str

def _extract_close(data: pd.DataFrame) -> pd.Series:
    if data is None or data.empty:
        return pd.Series(dtype="float64")

    if isinstance(data.columns, pd.MultiIndex):
        if "Close" in data.columns.get_level_values(0):
            obj = data.xs("Close", axis=1, level=0)
            if isinstance(obj, pd.DataFrame):
                obj = obj.iloc[:, 0]
            return pd.to_numeric(obj, errors="coerce").dropna()
        if "Close" in data.columns.get_level_values(1):
            obj = data.xs("Close", axis=1, level=1)
            if isinstance(obj, pd.DataFrame):
                obj = obj.iloc[:, 0]
            return pd.to_numeric(obj, errors="coerce").dropna()

    for col in ["Close", "Adj Close"]:
        if col in data.columns:
            obj = data[col]
            if isinstance(obj, pd.DataFrame):
                obj = obj.iloc[:, 0]
            return pd.to_numeric(obj, errors="coerce").dropna()

    return pd.Series(dtype="float64")

def _safe_float(x) -> Optional[float]:
    try:
        if x is None or pd.isna(x):
            return None
        return float(x)
    except Exception:
        return None

def _pct_change(s: pd.Series, periods: int) -> Optional[float]:
    try:
        s = pd.to_numeric(s, errors="coerce").dropna()
        if len(s) <= periods:
            return None
        latest = float(s.iloc[-1])
        prev = float(s.iloc[-1 - periods])
        if prev == 0:
            return None
        return (latest / prev - 1.0) * 100.0
    except Exception:
        return None

def _above_ma(s: pd.Series, window: int = 20) -> Optional[bool]:
    try:
        s = pd.to_numeric(s, errors="coerce").dropna()
        if len(s) < window:
            return None
        return float(s.iloc[-1]) > float(s.tail(window).mean())
    except Exception:
        return None

def _mode_from_score(score: float) -> str:
    if score >= 60:
        return "RISK ON MẠNH"
    if score >= 30:
        return "RISK ON"
    if score > -30:
        return "TRUNG TÍNH"
    if score > -60:
        return "RISK OFF"
    return "PANIC / PHÒNG THỦ"

def _risk_action_from_mode(mode: str) -> str:
    if mode == "RISK ON MẠNH":
        return "CHO PHÉP GIỮ TÍN HIỆU MUA - KHÔNG TỰ NÂNG WATCH LÊN BUY"
    if mode == "RISK ON":
        return "CHO PHÉP GIỮ TOP MUA THẬT NẾU BOT VN ĐẠT CHUẨN"
    if mode == "TRUNG TÍNH":
        return "CHỈ MUA THĂM DÒ - ƯU TIÊN MÃ RISK PASS"
    if mode == "RISK OFF":
        return "HẠ BUY NOW XUỐNG WATCHLIST"
    return "KHÔNG MỞ MUA MỚI - HẠ BUY NOW XUỐNG WATCHLIST"

def _status(score: float, good: float = 4, bad: float = -4) -> str:
    if score > good:
        return "TỐT"
    if score < bad:
        return "XẤU"
    return "TRUNG TÍNH"

def _make_signal(name: str, ticker: str, close: pd.Series, kind: str) -> MacroSignal:
    s = pd.to_numeric(close, errors="coerce").dropna()
    value = _safe_float(s.iloc[-1]) if len(s) else None
    ret_1d = _pct_change(s, 1)
    ret_5d = _pct_change(s, 5)
    above_ma20 = _above_ma(s, 20)

    score = 0.0
    reasons = []

    if kind == "vix":
        if value is not None:
            if value < 15:
                score += 8; reasons.append("VIX thấp")
            elif value < 20:
                score += 3; reasons.append("VIX bình thường")
            elif value < 25:
                score -= 6; reasons.append("VIX căng")
            else:
                score -= 14; reasons.append("VIX hoảng sợ")
        if ret_5d is not None:
            if ret_5d > 15:
                score -= 8; reasons.append("VIX tăng mạnh 5D")
            elif ret_5d < -10:
                score += 5; reasons.append("VIX hạ nhiệt")
    elif kind == "us10y":
        if ret_5d is not None:
            if ret_5d < -2:
                score += 7; reasons.append("lợi suất 10Y giảm")
            elif ret_5d > 2:
                score -= 8; reasons.append("lợi suất 10Y tăng")
        if above_ma20 is True:
            score -= 4; reasons.append("10Y trên MA20")
        elif above_ma20 is False:
            score += 3; reasons.append("10Y dưới MA20")
    elif kind == "dxy":
        if ret_5d is not None:
            if ret_5d < -1:
                score += 6; reasons.append("DXY giảm hỗ trợ EM")
            elif ret_5d > 1:
                score -= 7; reasons.append("DXY tăng gây áp lực")
        if above_ma20 is True:
            score -= 3; reasons.append("DXY trên MA20")
        elif above_ma20 is False:
            score += 2; reasons.append("DXY dưới MA20")
    elif kind == "oil":
        if ret_5d is not None:
            if 0 < ret_5d <= 5:
                score += 3; reasons.append("oil tăng vừa")
            elif ret_5d > 8:
                score -= 4; reasons.append("oil tăng sốc")
            elif ret_5d < -8:
                score -= 3; reasons.append("oil giảm sốc")
    else:
        if above_ma20 is True:
            score += 8; reasons.append("trên MA20")
        elif above_ma20 is False:
            score -= 8; reasons.append("dưới MA20")
        if ret_5d is not None:
            if ret_5d > 2:
                score += 6; reasons.append("5D tăng tốt")
            elif ret_5d < -2:
                score -= 6; reasons.append("5D giảm xấu")
        if ret_1d is not None:
            if ret_1d > 1:
                score += 3; reasons.append("1D xanh mạnh")
            elif ret_1d < -1:
                score -= 3; reasons.append("1D đỏ mạnh")

    return MacroSignal(
        name=name, ticker=ticker, value=value, ret_1d=ret_1d, ret_5d=ret_5d,
        above_ma20=above_ma20, score=round(float(score), 2),
        status=_status(score, 2 if kind == "oil" else 4, -2 if kind == "oil" else -4),
        reason="; ".join(reasons) if reasons else "Không đủ tín hiệu mạnh",
    )

def run_global_macro_layer(tickers: Optional[Dict[str, str]] = None) -> GlobalMacroResult:
    tickers = tickers or GLOBAL_TICKERS
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        import yfinance as yf
    except Exception:
        return GlobalMacroResult(generated_at, "NO_YFINANCE", 0.0, "TRUNG TÍNH", "CHỈ MUA THĂM DÒ - ƯU TIÊN MÃ RISK PASS", [], "Không import được yfinance, fallback TRUNG TÍNH.")

    signals: List[MacroSignal] = []

    for name, ticker in tickers.items():
        try:
            data = yf.download(ticker, period="6mo", interval="1d", progress=False, auto_adjust=False, threads=False, group_by="column")
            close = _extract_close(data)

            if close.empty or len(close) < 25:
                hist = yf.Ticker(ticker).history(period="6mo", interval="1d", auto_adjust=False)
                close = _extract_close(hist)

            if close.empty or len(close) < 25:
                continue

            kind = "equity"
            if name == "VIX": kind = "vix"
            elif name == "US10Y": kind = "us10y"
            elif name == "DXY": kind = "dxy"
            elif name == "OIL": kind = "oil"

            signals.append(_make_signal(name, ticker, close, kind))
        except Exception:
            continue

    if not signals:
        return GlobalMacroResult(generated_at, "NO_DATA", 0.0, "TRUNG TÍNH", "CHỈ MUA THĂM DÒ - ƯU TIÊN MÃ RISK PASS", [], "Không tải được dữ liệu liên thị trường, fallback TRUNG TÍNH.")

    global_score = round(max(-100.0, min(100.0, sum(s.score for s in signals))), 1)
    mode = _mode_from_score(global_score)
    return GlobalMacroResult(generated_at, "OK", global_score, mode, _risk_action_from_mode(mode), [asdict(s) for s in signals], "Macro chỉ hạ cấp rủi ro, không tự nâng WATCH lên BUY.")

def _find_action_col(df: pd.DataFrame) -> Optional[str]:
    for col in ["Hành động cuối", "Quyết định cuối", "Hành động hiện tại", "Action", "action"]:
        if col in df.columns:
            return col
    return None

def apply_global_risk_to_decision(df: pd.DataFrame, global_result: GlobalMacroResult, action_col: Optional[str] = None) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    action_col = action_col or _find_action_col(out)
    if not action_col:
        return out
    if "Tín hiệu gốc" not in out.columns:
        out["Tín hiệu gốc"] = out[action_col].astype(str)
    out["Global Macro Mode"] = global_result.global_mode
    if "Global Macro Note" not in out.columns:
        out["Global Macro Note"] = ""
    if global_result.global_mode in ["RISK OFF", "PANIC / PHÒNG THỦ"]:
        mask_buy = out[action_col].astype(str).str.upper().str.contains("BUY NOW|MUA", regex=True, na=False)
        out.loc[mask_buy, action_col] = "WATCHLIST"
        out.loc[mask_buy, "Global Macro Note"] = f"Hạ do {global_result.global_mode}: không mở mua mới"
    return out

def render_global_macro_html(global_result: GlobalMacroResult) -> str:
    color, bg = "#64748b", "#111827"
    if global_result.global_mode in ["RISK ON", "RISK ON MẠNH"]:
        color, bg = "#22c55e", "#052e1b"
    elif global_result.global_mode == "TRUNG TÍNH":
        color, bg = "#facc15", "#3a2f05"
    elif global_result.global_mode == "RISK OFF":
        color, bg = "#fb923c", "#3b1605"
    elif global_result.global_mode == "PANIC / PHÒNG THỦ":
        color, bg = "#ef4444", "#3a0b0b"

    def fmt(x):
        try:
            if x is None: return ""
            if isinstance(x, bool): return "YES" if x else "NO"
            if pd.isna(x): return ""
            return f"{float(x):.2f}"
        except Exception:
            return str(x)

    rows = ""
    for s in global_result.signals:
        rows += f"""
        <tr><td><b>{s.get('name','')}</b></td><td>{s.get('ticker','')}</td><td>{fmt(s.get('value'))}</td><td>{fmt(s.get('ret_1d'))}</td><td>{fmt(s.get('ret_5d'))}</td><td>{fmt(s.get('above_ma20'))}</td><td><b>{fmt(s.get('score'))}</b></td><td>{s.get('status','')}</td><td>{s.get('reason','')}</td></tr>
        """
    if not rows:
        rows = '<tr><td colspan="9">Không có dữ liệu macro. Fallback TRUNG TÍNH.</td></tr>'

    return f"""
    <style>
    .global-macro-card {{background:{bg};border:1px solid {color};border-radius:14px;padding:14px;margin:14px 0 22px 0;color:#f8fafc;overflow-x:auto;}}
    .global-macro-title {{font-size:22px;font-weight:900;color:{color};margin-bottom:6px;}}
    .global-macro-score {{display:inline-block;padding:8px 12px;border-radius:10px;background:{color};color:#0f172a;font-weight:900;margin:6px 0 10px 0;}}
    .global-macro-table {{width:100%;border-collapse:collapse;font-size:12px;margin-top:10px;}}
    .global-macro-table th,.global-macro-table td {{border:1px solid rgba(255,255,255,0.14);padding:7px 8px;white-space:nowrap;}}
    .global-macro-table th {{background:#111827;color:#ffffff;}}
    </style>
    <div class="global-macro-card"><div class="global-macro-title">GLOBAL MACRO MODE</div><div><b>Generated:</b> {global_result.generated_at}</div><div><b>Data status:</b> {global_result.data_status}</div><div class="global-macro-score">{global_result.global_mode} | SCORE: {global_result.global_score}</div><div><b>Risk action:</b> {global_result.risk_action}</div><div><b>Note:</b> {global_result.note}</div><table class="global-macro-table"><thead><tr><th>Chỉ số</th><th>Ticker</th><th>Giá</th><th>Ret 1D %</th><th>Ret 5D %</th><th>Trên MA20</th><th>Điểm</th><th>Trạng thái</th><th>Lý do</th></tr></thead><tbody>{rows}</tbody></table></div>
    """

def render_global_macro_telegram(global_result: GlobalMacroResult) -> str:
    emoji = "⚪"
    if global_result.global_mode in ["RISK ON", "RISK ON MẠNH"]: emoji = "🟢"
    elif global_result.global_mode == "TRUNG TÍNH": emoji = "🟡"
    elif global_result.global_mode == "RISK OFF": emoji = "🟠"
    elif global_result.global_mode == "PANIC / PHÒNG THỦ": emoji = "🔴"
    return f"{emoji} <b>GLOBAL MACRO MODE</b>\nMode: <b>{global_result.global_mode}</b>\nScore: <b>{global_result.global_score}</b>\nAction: {global_result.risk_action}\nNote: {global_result.note}"

if __name__ == "__main__":
    print(run_global_macro_layer())
