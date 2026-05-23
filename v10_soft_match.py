# -*- coding: utf-8 -*-
import pandas as pd


def _soft_to_float(x):
    try:
        if pd.isna(x):
            return float("nan")
        return float(str(x).replace("%", "").replace(",", ".").strip())
    except Exception:
        return float("nan")


def _soft_upper(x):
    return str(x).upper().strip()


def _soft_rsi_zone(x):
    v = _soft_to_float(x)
    if pd.isna(v):
        return "RSI_UNKNOWN"
    if v < 35:
        return "RSI_LOW"
    if v < 50:
        return "RSI_WEAK"
    if v <= 65:
        return "RSI_MID_50_65"
    if v <= 75:
        return "RSI_HIGH_65_75"
    return "RSI_HOT_75_PLUS"


def _soft_rs20_zone(x):
    v = _soft_to_float(x)
    if pd.isna(v):
        return "RS20_UNKNOWN"
    if v < -10:
        return "RS20_BAD_LT_-10"
    if v < 0:
        return "RS20_WEAK_-10_0"
    if v < 10:
        return "RS20_OK_0_10"
    if v < 20:
        return "RS20_STRONG_10_20"
    return "RS20_LEADER_20_PLUS"


def _soft_volume_zone(x):
    v = _soft_to_float(x)
    if pd.isna(v):
        return "VOL_UNKNOWN"
    if v < 0.8:
        return "VOL_LOW"
    if v <= 1.2:
        return "VOL_OK_0.8_1.2"
    return "VOL_STRONG_GT_1.2"


def _soft_market_zone(x):
    t = _soft_upper(x)
    if not t or t in ["NAN", "NONE"]:
        return "MARKET_UNKNOWN"
    if "GIẢM" in t or "GIAM" in t:
        if "ẢO" in t or "AO" in t or "ĐỠ" in t or "DO" in t:
            return "MARKET_GIAM_AO_DO_RONG_OK"
        return "MARKET_GIAM"
    if "TĂNG" in t or "TANG" in t:
        return "MARKET_TANG"
    if "CẨN" in t or "CAN THAN" in t:
        return "MARKET_CAN_THAN"
    return t[:40]


def _hard_sample_strength(n):
    try:
        n = float(n)
    except Exception:
        return "KHÔNG RÕ"
    if n >= 30:
        return "MẠNH"
    if n >= 10:
        return "DÙNG ĐƯỢC"
    return "YẾU"


def _soft_sample_strength(n):
    try:
        n = float(n)
    except Exception:
        return "KHÔNG RÕ"
    if n >= 5000:
        return "RẤT MẠNH"
    if n >= 1000:
        return "MẠNH"
    if n >= 200:
        return "ỔN"
    return "YẾU"


def add_sample_strength_column(df, mode="soft"):
    try:
        if df is None or getattr(df, "empty", True):
            return df
        out = df.copy()
        if mode == "soft":
            from v10_ui_dashboard import _ui_find_col
            col = _ui_find_col(out, ["Số mẫu mềm 3Y", "So mau mem 3Y"])
            if col is not None:
                out["Độ mạnh mẫu mềm"] = out[col].map(_soft_sample_strength)
        else:
            from v10_ui_dashboard import _ui_find_col
            col = _ui_find_col(out, ["Số lần test", "So lan test", "OOS N", "History Samples", "Regime Samples", "Số mẫu", "So mau"])
            if col is not None:
                out["Độ mạnh mẫu cứng"] = out[col].map(_hard_sample_strength)
        return out
    except Exception:
        return df


def _soft_get_date_series(df, date_col):
    if date_col is None or df is None or df.empty:
        return None
    try:
        return pd.to_datetime(df[date_col], errors="coerce")
    except Exception:
        return None


def _soft_pick_return_col(df, candidates):
    from v10_ui_dashboard import _ui_find_col
    col = _ui_find_col(df, candidates)
    return col


def build_v135_soft_history_match_view(current_df, history_df, limit=60, lookback_years=3, min_match_pct=70):
    try:
        if current_df is None or getattr(current_df, "empty", True):
            return pd.DataFrame([{"Trạng thái": "Không có tín hiệu hiện tại để match mềm"}])
        if history_df is None or getattr(history_df, "empty", True):
            return pd.DataFrame([{"Trạng thái": "Chưa có dữ liệu quá khứ để match mềm"}])

        from v10_utils import runner_normalize_columns
        from v10_ui_dashboard import _ui_find_col

        cur = runner_normalize_columns(current_df.copy())
        hist = runner_normalize_columns(history_df.copy())
        if hist is None or hist.empty:
            return pd.DataFrame([{"Trạng thái": "Dữ liệu quá khứ rỗng sau normalize"}])

        ma_col = _ui_find_col(cur, ["Mã", "Ma"])
        price_col = _ui_find_col(cur, ["Giá", "Close", "Gia"])
        action_col = _ui_find_col(cur, ["Hành động hiện tại", "Hanh dong hien tai", "Action"])
        strategy_col = _ui_find_col(cur, ["Strategy", "Chiến lược", "Chien luoc"])
        risk_col = _ui_find_col(cur, ["Risk", "Risk Status", "Rủi ro", "Rui ro"])
        rsi_col = _ui_find_col(cur, ["RSI"])
        rs20_col = _ui_find_col(cur, ["RS20"])
        vol_col = _ui_find_col(cur, ["Volume Ratio", "Vol Ratio", "volume_ratio"])
        market_col = _ui_find_col(cur, ["Market V13", "Market Regime Now", "Market Regime", "Market"])
        date_col_cur = _ui_find_col(cur, ["Ngày", "Ngay", "Date"])

        h_strategy_col = _ui_find_col(hist, ["Strategy", "Chiến lược", "Chien luoc"])
        h_rsi_col = _ui_find_col(hist, ["RSI"])
        h_rs20_col = _ui_find_col(hist, ["RS20"])
        h_vol_col = _ui_find_col(hist, ["Volume Ratio", "Vol Ratio", "volume_ratio"])
        h_market_col = _ui_find_col(hist, ["Market V13", "Market Regime Now", "Market Regime", "Market"])
        h_date_col = _ui_find_col(hist, ["Ngày", "Ngay", "Date"])

        h_t2_col = _soft_pick_return_col(hist, ["Lợi TB T+2 %", "Loi TB T+2 %", "Ret T+2 %", "Ret+2", "Return T+2", "T+2", "future_ret_2"])
        h_t5_col = _soft_pick_return_col(hist, ["Lợi TB T+5 %", "Loi TB T+5 %", "Ret T+5 %", "Ret+5", "Return T+5", "T+5", "future_ret_5"])
        h_t10_col = _soft_pick_return_col(hist, ["Lợi TB T+10 %", "Loi TB T+10 %", "Ret T+10 %", "Ret+10", "Return T+10", "T+10", "future_ret_10"])

        h_dates = _soft_get_date_series(hist, h_date_col)
        if h_dates is not None and h_dates.notna().any():
            cur_dates = _soft_get_date_series(cur, date_col_cur)
            ref_date = None
            try:
                if cur_dates is not None and cur_dates.notna().any():
                    ref_date = cur_dates.max()
            except Exception:
                ref_date = None
            if ref_date is None or pd.isna(ref_date):
                ref_date = h_dates.max()
            try:
                start_date = ref_date - pd.DateOffset(years=lookback_years)
                hist = hist.loc[(h_dates >= start_date) & (h_dates < ref_date)].copy()
            except Exception:
                pass

        if hist.empty:
            return pd.DataFrame([{"Trạng thái": "Không có mẫu quá khứ trong khung 1-3 năm"}])

        hist["__soft_strategy"] = hist[h_strategy_col].map(_soft_upper) if h_strategy_col else ""
        hist["__soft_rsi"] = hist[h_rsi_col].map(_soft_rsi_zone) if h_rsi_col else "RSI_UNKNOWN"
        hist["__soft_rs20"] = hist[h_rs20_col].map(_soft_rs20_zone) if h_rs20_col else "RS20_UNKNOWN"
        hist["__soft_vol"] = hist[h_vol_col].map(_soft_volume_zone) if h_vol_col else "VOL_UNKNOWN"
        hist["__soft_market"] = hist[h_market_col].map(_soft_market_zone) if h_market_col else "MARKET_UNKNOWN"

        rows = []
        for _, r in cur.head(limit).iterrows():
            ma = r.get(ma_col, "") if ma_col else ""
            price = r.get(price_col, "") if price_col else ""
            action = r.get(action_col, "") if action_col else ""
            risk = r.get(risk_col, "") if risk_col else ""
            strategy = _soft_upper(r.get(strategy_col, "")) if strategy_col else ""
            rsi_zone = _soft_rsi_zone(r.get(rsi_col, None)) if rsi_col else "RSI_UNKNOWN"
            rs20_zone = _soft_rs20_zone(r.get(rs20_col, None)) if rs20_col else "RS20_UNKNOWN"
            vol_zone = _soft_volume_zone(r.get(vol_col, None)) if vol_col else "VOL_UNKNOWN"
            market_zone = _soft_market_zone(r.get(market_col, "")) if market_col else "MARKET_UNKNOWN"

            pool = hist.copy()
            checks = []
            if strategy and strategy not in ["NAN", "NONE"]:
                checks.append(pool["__soft_strategy"].eq(strategy))
            if rsi_zone != "RSI_UNKNOWN":
                checks.append(pool["__soft_rsi"].eq(rsi_zone))
            if rs20_zone != "RS20_UNKNOWN":
                checks.append(pool["__soft_rs20"].eq(rs20_zone))
            if vol_zone != "VOL_UNKNOWN":
                checks.append(pool["__soft_vol"].eq(vol_zone))
            if market_zone != "MARKET_UNKNOWN":
                checks.append(pool["__soft_market"].eq(market_zone))

            if checks:
                match_count = sum([c.astype(int) for c in checks])
                pool["__match_pct"] = (match_count / max(len(checks), 1)) * 100.0
                matched = pool[pool["__match_pct"] >= float(min_match_pct)].copy()
            else:
                matched = pd.DataFrame()

            n = int(len(matched)) if matched is not None else 0
            def _avg(col):
                if col is None or n == 0:
                    return float("nan")
                return pd.to_numeric(matched[col], errors="coerce").mean()
            def _win(col):
                if col is None or n == 0:
                    return float("nan")
                vals = pd.to_numeric(matched[col], errors="coerce")
                vals = vals.dropna()
                if len(vals) == 0:
                    return float("nan")
                return (vals.gt(0).mean() * 100.0)

            avg_t2 = _avg(h_t2_col)
            avg_t5 = _avg(h_t5_col)
            avg_t10 = _avg(h_t10_col)
            win_t2 = _win(h_t2_col)
            win_t5 = _win(h_t5_col)

            if n == 0:
                trust = "CHƯA CÓ MẪU GẦN GIỐNG"
            elif n < 5:
                trust = "MẪU ÍT - CHỈ THAM KHẢO"
            elif n < 20:
                trust = "CÓ MẪU - CẦN THẬN TRỌNG"
            else:
                trust = "MẪU ĐỦ DÙNG"

            rows.append({
                "Mã": ma,
                "Giá": price,
                "Hành động": action,
                "Strategy": strategy,
                "Risk": risk,
                "RSI zone mềm": rsi_zone,
                "RS20 zone mềm": rs20_zone,
                "Volume zone mềm": vol_zone,
                "Market zone": market_zone,
                "Số mẫu mềm 3Y": n,
                "Độ mạnh mẫu mềm": _soft_sample_strength(n),
                "Win T+2 %": round(win_t2, 2) if not pd.isna(win_t2) else "",
                "Win T+5 %": round(win_t5, 2) if not pd.isna(win_t5) else "",
                "Lợi TB T+2 %": round(avg_t2, 2) if not pd.isna(avg_t2) else "",
                "Lợi TB T+5 %": round(avg_t5, 2) if not pd.isna(avg_t5) else "",
                "Lợi TB T+10 %": round(avg_t10, 2) if not pd.isna(avg_t10) else "",
                "Độ tin cậy mềm": trust,
            })

        view = pd.DataFrame(rows)
        if not view.empty and "Số mẫu mềm 3Y" in view.columns:
            view = view.sort_values(["Số mẫu mềm 3Y", "Win T+5 %", "Lợi TB T+5 %"], ascending=[False, False, False], na_position="last").reset_index(drop=True)
        return view
    except Exception as e:
        return pd.DataFrame([{"Trạng thái": "Lỗi match mềm nhưng đã bỏ qua để không crash", "Chi tiết": repr(e)}])


def build_v135_softmatch_top_view(v135_df, limit=15):
    try:
        if v135_df is None or getattr(v135_df, "empty", True):
            return pd.DataFrame([{"Trạng thái": "Không có dữ liệu V13.5 để lọc TOP"}])
        df = v135_df.copy()
        if "Hành động" not in df.columns:
            return pd.DataFrame([{"Trạng thái": "V13.5 chưa có cột Hành động để lọc TOP"}])

        act = df["Hành động"].astype(str).str.upper()
        mask = act.isin(["BUY NOW", "WATCHLIST"])
        if "Risk" in df.columns:
            risk = df["Risk"].astype(str).str.upper()
            mask = mask & risk.eq("PASS")
        top = df.loc[mask].copy()
        if top.empty:
            return pd.DataFrame([{"Trạng thái": "Không có mã BUY NOW/WATCHLIST Risk PASS trong V13.5"}])

        top["__action_rank"] = top["Hành động"].astype(str).str.upper().map({"BUY NOW": 0, "WATCHLIST": 1}).fillna(9)
        if "Win T+2 %" in top.columns:
            top["__win_t2"] = pd.to_numeric(top["Win T+2 %"], errors="coerce")
        else:
            top["__win_t2"] = float("nan")
        if "Số mẫu mềm 3Y" in top.columns:
            top["__n"] = pd.to_numeric(top["Số mẫu mềm 3Y"], errors="coerce")
        else:
            top["__n"] = float("nan")

        top = top.sort_values(["__action_rank", "__win_t2", "__n"], ascending=[True, False, False], na_position="last")
        top = top.drop(columns=[c for c in ["__action_rank", "__win_t2", "__n"] if c in top.columns])
        keep = [c for c in [
            "Mã", "Giá", "Hành động", "Strategy", "Risk",
            "Số mẫu mềm 3Y", "Độ mạnh mẫu mềm", "Win T+2 %", "Win T+5 %",
            "Lợi TB T+2 %", "Lợi TB T+5 %", "Độ tin cậy mềm",
            "RSI zone mềm", "RS20 zone mềm", "Volume zone mềm", "Market zone"
        ] if c in top.columns]
        return top[keep].head(limit).reset_index(drop=True)
    except Exception as e:
        return pd.DataFrame([{"Trạng thái": "Lỗi lọc TOP V13.5 nhưng đã bỏ qua để không crash", "Chi tiết": repr(e)}])
