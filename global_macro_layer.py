# -*- coding: utf-8 -*-
"""
global_macro_layer.py
GLOBAL MACRO / INTERMARKET RISK LAYER cho Trading Bot VN

Mục tiêu:
- Tính GLOBAL RISK SCORE từ các chỉ số liên thị trường.
- Hiển thị block riêng trong dashboard.
- Chỉ hạ cấp rủi ro, KHÔNG tự nâng tín hiệu.
- Không thay đổi core signal gốc của bot.

Cách dùng trong runner:
    from global_macro_layer import run_global_macro_layer, apply_global_risk_to_decision, render_global_macro_html

    global_result = run_global_macro_layer()
    html_global = render_global_macro_html(global_result)

    df = apply_global_risk_to_decision(df, global_result)

Yêu cầu thư viện:
    pip install yfinance pandas numpy
Nếu yfinance lỗi hoặc không có mạng, module sẽ fallback về trạng thái TRUNG TÍNH.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

import pandas as pd


# =========================
# CONFIG
# =========================

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

DEFAULT_LOOKBACK_DAYS = 90


# =========================
# DATA STRUCTURE
# =========================

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


# =========================
# HELPER
# =========================

def _safe_float(x) -> Optional[float]:
    try:
        if x is None:
            return None
        if pd.isna(x):
            return None
        return float(x)
    except Exception:
        return None


def _pct_change(series: pd.Series, periods: int) -> Optional[float]:
    try:
        if len(series.dropna()) <= periods:
            return None
        latest = float(series.dropna().iloc[-1])
        prev = float(series.dropna().iloc[-1 - periods])
        if prev == 0:
            return None
        return (latest / prev - 1.0) * 100.0
    except Exception:
        return None


def _above_ma(series: pd.Series, window: int = 20) -> Optional[bool]:
    try:
        s = series.dropna()
        if len(s) < window:
            return None
        latest = float(s.iloc[-1])
        ma = float(s.tail(window).mean())
        return latest > ma
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


# =========================
# SCORING
# =========================

def _score_equity_index(name: str, ticker: str, close: pd.Series) -> MacroSignal:
    value = _safe_float(close.dropna().iloc[-1]) if len(close.dropna()) else None
    ret_1d = _pct_change(close, 1)
    ret_5d = _pct_change(close, 5)
    above_ma20 = _above_ma(close, 20)

    score = 0.0
    reasons = []

    if above_ma20 is True:
        score += 8
        reasons.append("trên MA20")
    elif above_ma20 is False:
        score -= 8
        reasons.append("dưới MA20")

    if ret_5d is not None:
        if ret_5d > 2:
            score += 6
            reasons.append("5D tăng tốt")
        elif ret_5d < -2:
            score -= 6
            reasons.append("5D giảm xấu")

    if ret_1d is not None:
        if ret_1d > 1:
            score += 3
            reasons.append("1D xanh mạnh")
        elif ret_1d < -1:
            score -= 3
            reasons.append("1D đỏ mạnh")

    return MacroSignal(
        name=name,
        ticker=ticker,
        value=value,
        ret_1d=ret_1d,
        ret_5d=ret_5d,
        above_ma20=above_ma20,
        score=score,
        status="TỐT" if score > 4 else ("XẤU" if score < -4 else "TRUNG TÍNH"),
        reason="; ".join(reasons) if reasons else "Không đủ tín hiệu mạnh",
    )


def _score_vix(name: str, ticker: str, close: pd.Series) -> MacroSignal:
    value = _safe_float(close.dropna().iloc[-1]) if len(close.dropna()) else None
    ret_1d = _pct_change(close, 1)
    ret_5d = _pct_change(close, 5)
    above_ma20 = _above_ma(close, 20)

    score = 0.0
    reasons = []

    if value is not None:
        if value < 15:
            score += 8
            reasons.append("VIX thấp")
        elif value < 20:
            score += 3
            reasons.append("VIX bình thường")
        elif value < 25:
            score -= 6
            reasons.append("VIX căng")
        else:
            score -= 14
            reasons.append("VIX hoảng sợ")

    if ret_5d is not None:
        if ret_5d > 15:
            score -= 8
            reasons.append("VIX tăng mạnh 5D")
        elif ret_5d < -10:
            score += 5
            reasons.append("VIX hạ nhiệt")

    return MacroSignal(
        name=name,
        ticker=ticker,
        value=value,
        ret_1d=ret_1d,
        ret_5d=ret_5d,
        above_ma20=above_ma20,
        score=score,
        status="TỐT" if score > 4 else ("XẤU" if score < -4 else "TRUNG TÍNH"),
        reason="; ".join(reasons) if reasons else "Không đủ tín hiệu mạnh",
    )


def _score_us10y(name: str, ticker: str, close: pd.Series) -> MacroSignal:
    value = _safe_float(close.dropna().iloc[-1]) if len(close.dropna()) else None
    ret_1d = _pct_change(close, 1)
    ret_5d = _pct_change(close, 5)
    above_ma20 = _above_ma(close, 20)

    score = 0.0
    reasons = []

    if ret_5d is not None:
        if ret_5d < -2:
            score += 7
            reasons.append("lợi suất 10Y giảm")
        elif ret_5d > 2:
            score -= 8
            reasons.append("lợi suất 10Y tăng")

    if above_ma20 is True:
        score -= 4
        reasons.append("10Y trên MA20")
    elif above_ma20 is False:
        score += 3
        reasons.append("10Y dưới MA20")

    return MacroSignal(
        name=name,
        ticker=ticker,
        value=value,
        ret_1d=ret_1d,
        ret_5d=ret_5d,
        above_ma20=above_ma20,
        score=score,
        status="TỐT" if score > 4 else ("XẤU" if score < -4 else "TRUNG TÍNH"),
        reason="; ".join(reasons) if reasons else "Không đủ tín hiệu mạnh",
    )


def _score_dxy(name: str, ticker: str, close: pd.Series) -> MacroSignal:
    value = _safe_float(close.dropna().iloc[-1]) if len(close.dropna()) else None
    ret_1d = _pct_change(close, 1)
    ret_5d = _pct_change(close, 5)
    above_ma20 = _above_ma(close, 20)

    score = 0.0
    reasons = []

    if ret_5d is not None:
        if ret_5d < -1:
            score += 6
            reasons.append("DXY giảm hỗ trợ EM")
        elif ret_5d > 1:
            score -= 7
            reasons.append("DXY tăng gây áp lực")

    if above_ma20 is True:
        score -= 3
        reasons.append("DXY trên MA20")
    elif above_ma20 is False:
        score += 2
        reasons.append("DXY dưới MA20")

    return MacroSignal(
        name=name,
        ticker=ticker,
        value=value,
        ret_1d=ret_1d,
        ret_5d=ret_5d,
        above_ma20=above_ma20,
        score=score,
        status="TỐT" if score > 4 else ("XẤU" if score < -4 else "TRUNG TÍNH"),
        reason="; ".join(reasons) if reasons else "Không đủ tín hiệu mạnh",
    )


def _score_oil(name: str, ticker: str, close: pd.Series) -> MacroSignal:
    value = _safe_float(close.dropna().iloc[-1]) if len(close.dropna()) else None
    ret_1d = _pct_change(close, 1)
    ret_5d = _pct_change(close, 5)
    above_ma20 = _above_ma(close, 20)

    score = 0.0
    reasons = []

    if ret_5d is not None:
        if 0 < ret_5d <= 5:
            score += 3
            reasons.append("oil tăng vừa")
        elif ret_5d > 8:
            score -= 4
            reasons.append("oil tăng sốc")
        elif ret_5d < -8:
            score -= 3
            reasons.append("oil giảm sốc")

    return MacroSignal(
        name=name,
        ticker=ticker,
        value=value,
        ret_1d=ret_1d,
        ret_5d=ret_5d,
        above_ma20=above_ma20,
        score=score,
        status="TỐT" if score > 2 else ("XẤU" if score < -2 else "TRUNG TÍNH"),
        reason="; ".join(reasons) if reasons else "Không đủ tín hiệu mạnh",
    )


def _normalize_score(raw_score: float) -> float:
    # raw score thường nằm khoảng -80 đến +80.
    # Giữ trong biên -100 đến 100 cho dễ đọc.
    return float(max(-100.0, min(100.0, raw_score)))


# =========================
# MAIN RUN
# =========================

def run_global_macro_layer(
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    tickers: Optional[Dict[str, str]] = None,
) -> GlobalMacroResult:
    tickers = tickers or GLOBAL_TICKERS
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        import yfinance as yf
    except Exception:
        return GlobalMacroResult(
            generated_at=generated_at,
            data_status="NO_YFINANCE",
            global_score=0.0,
            global_mode="TRUNG TÍNH",
            risk_action="CHỈ MUA THĂM DÒ - ƯU TIÊN MÃ RISK PASS",
            signals=[],
            note="Không import được yfinance, fallback TRUNG TÍNH.",
        )

    start = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    signals: List[MacroSignal] = []

    for name, ticker in tickers.items():
        try:
            data = yf.download(
                ticker,
                period="6mo",
                interval="1d",
                progress=False,
                auto_adjust=False,
                threads=False
            )
            if data is None or data.empty or "Close" not in data.columns:
                continue

            close = data["Close"].dropna()

            if name == "VIX":
                sig = _score_vix(name, ticker, close)
            elif name == "US10Y":
                sig = _score_us10y(name, ticker, close)
            elif name == "DXY":
                sig = _score_dxy(name, ticker, close)
            elif name == "OIL":
                sig = _score_oil(name, ticker, close)
            else:
                sig = _score_equity_index(name, ticker, close)

            signals.append(sig)
        except Exception:
            continue

    if not signals:
        return GlobalMacroResult(
            generated_at=generated_at,
            data_status="NO_DATA",
            global_score=0.0,
            global_mode="TRUNG TÍNH",
            risk_action="CHỈ MUA THĂM DÒ - ƯU TIÊN MÃ RISK PASS",
            signals=[],
            note="Không tải được dữ liệu liên thị trường, fallback TRUNG TÍNH.",
        )

    raw_score = sum(s.score for s in signals)
    global_score = round(_normalize_score(raw_score), 1)
    mode = _mode_from_score(global_score)
    risk_action = _risk_action_from_mode(mode)

    return GlobalMacroResult(
        generated_at=generated_at,
        data_status="OK",
        global_score=global_score,
        global_mode=mode,
        risk_action=risk_action,
        signals=[asdict(s) for s in signals],
        note="Macro chỉ hạ cấp rủi ro, không tự nâng WATCH lên BUY.",
    )


# =========================
# APPLY TO DECISION LAYER
# =========================

def _find_action_col(df: pd.DataFrame) -> Optional[str]:
    candidates = [
        "Hành động cuối",
        "Quyết định cuối",
        "Hành động hiện tại",
        "Action",
        "action",
    ]
    for col in candidates:
        if col in df.columns:
            return col
    return None


def apply_global_risk_to_decision(
    df: pd.DataFrame,
    global_result: GlobalMacroResult,
    action_col: Optional[str] = None,
) -> pd.DataFrame:
    """
    Chỉ hạ cấp:
    - Nếu Global Risk Off hoặc Panic:
      BUY NOW -> WATCHLIST
    - Không tự nâng WATCH lên BUY.
    - Giữ thêm cột tín hiệu gốc để xem lại.
    """
    if df is None or df.empty:
        return df

    out = df.copy()
    action_col = action_col or _find_action_col(out)
    if not action_col:
        return out

    if "Tín hiệu gốc" not in out.columns:
        out["Tín hiệu gốc"] = out[action_col].astype(str)

    if "Global Macro Mode" not in out.columns:
        out["Global Macro Mode"] = global_result.global_mode

    if "Global Macro Note" not in out.columns:
        out["Global Macro Note"] = ""

    mode = global_result.global_mode

    if mode in ["RISK OFF", "PANIC / PHÒNG THỦ"]:
        mask_buy = out[action_col].astype(str).str.upper().str.contains("BUY NOW|MUA", regex=True, na=False)
        out.loc[mask_buy, action_col] = "WATCHLIST"
        out.loc[mask_buy, "Global Macro Note"] = f"Hạ do {mode}: không mở mua mới"

    return out


# =========================
# HTML RENDER
# =========================

def render_global_macro_html(global_result: GlobalMacroResult) -> str:
    color = "#64748b"
    bg = "#111827"
    if global_result.global_mode in ["RISK ON", "RISK ON MẠNH"]:
        color = "#22c55e"
        bg = "#052e1b"
    elif global_result.global_mode == "TRUNG TÍNH":
        color = "#facc15"
        bg = "#3a2f05"
    elif global_result.global_mode == "RISK OFF":
        color = "#fb923c"
        bg = "#3b1605"
    elif global_result.global_mode == "PANIC / PHÒNG THỦ":
        color = "#ef4444"
        bg = "#3a0b0b"

    rows = ""
    for s in global_result.signals:
        name = s.get("name", "")
        ticker = s.get("ticker", "")
        value = s.get("value", "")
        ret_1d = s.get("ret_1d", "")
        ret_5d = s.get("ret_5d", "")
        above = s.get("above_ma20", "")
        score = s.get("score", "")
        status = s.get("status", "")
        reason = s.get("reason", "")

        def fmt(x):
            try:
                if x is None or (isinstance(x, float) and math.isnan(x)):
                    return ""
                if isinstance(x, bool):
                    return "YES" if x else "NO"
                return f"{float(x):.2f}"
            except Exception:
                return str(x)

        rows += f"""
        <tr>
            <td><b>{name}</b></td>
            <td>{ticker}</td>
            <td>{fmt(value)}</td>
            <td>{fmt(ret_1d)}</td>
            <td>{fmt(ret_5d)}</td>
            <td>{fmt(above)}</td>
            <td><b>{fmt(score)}</b></td>
            <td>{status}</td>
            <td>{reason}</td>
        </tr>
        """

    if not rows:
        rows = """
        <tr>
            <td colspan="9">Không có dữ liệu macro. Fallback TRUNG TÍNH.</td>
        </tr>
        """

    html = f"""
    <style>
    .global-macro-card {{
        background: {bg};
        border: 1px solid {color};
        border-radius: 14px;
        padding: 14px;
        margin: 14px 0 22px 0;
        color: #f8fafc;
        overflow-x: auto;
    }}
    .global-macro-title {{
        font-size: 22px;
        font-weight: 900;
        color: {color};
        margin-bottom: 6px;
    }}
    .global-macro-score {{
        display: inline-block;
        padding: 8px 12px;
        border-radius: 10px;
        background: {color};
        color: #0f172a;
        font-weight: 900;
        margin: 6px 0 10px 0;
    }}
    .global-macro-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 12px;
        margin-top: 10px;
    }}
    .global-macro-table th, .global-macro-table td {{
        border: 1px solid rgba(255,255,255,0.14);
        padding: 7px 8px;
        white-space: nowrap;
    }}
    .global-macro-table th {{
        background: #111827;
        color: #ffffff;
    }}
    </style>

    <div class="global-macro-card">
        <div class="global-macro-title">GLOBAL MACRO MODE</div>
        <div><b>Generated:</b> {global_result.generated_at}</div>
        <div><b>Data status:</b> {global_result.data_status}</div>
        <div class="global-macro-score">
            {global_result.global_mode} | SCORE: {global_result.global_score}
        </div>
        <div><b>Risk action:</b> {global_result.risk_action}</div>
        <div><b>Note:</b> {global_result.note}</div>

        <table class="global-macro-table">
            <thead>
                <tr>
                    <th>Chỉ số</th>
                    <th>Ticker</th>
                    <th>Giá</th>
                    <th>Ret 1D %</th>
                    <th>Ret 5D %</th>
                    <th>Trên MA20</th>
                    <th>Điểm</th>
                    <th>Trạng thái</th>
                    <th>Lý do</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
    </div>
    """
    return html


# =========================
# SIMPLE TEXT FOR TELEGRAM
# =========================

def render_global_macro_telegram(global_result: GlobalMacroResult) -> str:
    emoji = "⚪"
    if global_result.global_mode in ["RISK ON", "RISK ON MẠNH"]:
        emoji = "🟢"
    elif global_result.global_mode == "TRUNG TÍNH":
        emoji = "🟡"
    elif global_result.global_mode == "RISK OFF":
        emoji = "🟠"
    elif global_result.global_mode == "PANIC / PHÒNG THỦ":
        emoji = "🔴"

    return (
        f"{emoji} <b>GLOBAL MACRO MODE</b>\n"
        f"Mode: <b>{global_result.global_mode}</b>\n"
        f"Score: <b>{global_result.global_score}</b>\n"
        f"Action: {global_result.risk_action}\n"
        f"Note: {global_result.note}"
    )


if __name__ == "__main__":
    result = run_global_macro_layer()
    print(asdict(result))
