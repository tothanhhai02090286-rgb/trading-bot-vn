# -*- coding: utf-8 -*-
# V13 FINAL DECISION VI
# Market thật/ảo + Pattern match có trọng số riêng Momentum/Bottom.
# Layer phụ, không sửa core V10/V11.

import os
from pathlib import Path
import pandas as pd
import numpy as np

def _num(x, default=np.nan):
    try:
        if x is None: return default
        s = str(x).strip()
        if s == "" or s.lower() in ["nan","none"]: return default
        return float(x)
    except Exception:
        return default

def _txt(x):
    try: return str(x).strip()
    except Exception: return ""

def _up(x): return _txt(x).upper()

def _col(df, names):
    if df is None or df.empty: return None
    low = {str(c).lower().strip(): c for c in df.columns}
    for n in names:
        if n in df.columns: return n
        k = str(n).lower().strip()
        if k in low: return low[k]
    return None

def _cache_dir():
    for p in [os.environ.get("CACHE_DIR"), os.environ.get("CACHE_STOCK_DIR"),
              "/content/drive/MyDrive/cache_stock",
              "/content/drive/MyDrive/thumucbot/cache_stock", "./cache_stock", "cache_stock"]:
        if p and Path(p).exists() and Path(p).is_dir():
            return Path(p)
    return Path("/content/drive/MyDrive/cache_stock")

def _read_cache(code, cache_dir=None):
    cache_dir = Path(cache_dir) if cache_dir else _cache_dir()
    code = str(code).strip().upper()
    for p in [cache_dir / f"{code}.csv", cache_dir / f"{code.lower()}.csv"]:
        if p.exists():
            try: return pd.read_csv(p)
            except Exception: return pd.DataFrame()
    return pd.DataFrame()

def _norm_price(df):
    if df is None or df.empty: return pd.DataFrame()
    d = df.copy()
    dc = _col(d, ["time","date","datetime","Ngay","Ngày"])
    cc = _col(d, ["close","Close","Gia","Giá"])
    if not dc or not cc: return pd.DataFrame()
    d["_date"] = pd.to_datetime(d[dc], errors="coerce")
    d["_close"] = pd.to_numeric(d[cc], errors="coerce")
    return d.dropna(subset=["_date","_close"]).sort_values("_date").reset_index(drop=True)

def _ret1(code, cache_dir=None):
    d = _norm_price(_read_cache(code, cache_dir))
    if d.empty or len(d) < 2:
        return {"Mã": code, "Ngày": "", "Ret1 %": np.nan, "Có data": False}
    last, prev = d.iloc[-1], d.iloc[-2]
    ret = (last["_close"] / prev["_close"] - 1) * 100 if prev["_close"] else np.nan
    return {"Mã": str(code).upper(), "Ngày": str(pd.to_datetime(last["_date"]).date()), "Ret1 %": ret, "Có data": True}

def _codes(df, universe=None):
    if universe is not None:
        try:
            xs = [str(x).strip().upper() for x in universe if str(x).strip()]
            if xs: return sorted(set(xs))
        except Exception: pass
    c = _col(df, ["Ma","Code","Mã","symbol","ticker"])
    if c: return sorted(set(df[c].dropna().astype(str).str.upper().tolist()))
    return []

def market_real_fake_summary(signal_df, market_score=0, universe=None, cache_dir=None):
    codes = _codes(signal_df, universe)
    rows = [_ret1(c, cache_dir) for c in codes]
    d = pd.DataFrame(rows)
    if d.empty or "Có data" not in d.columns:
        return d, {"market_label":"KHÔNG CÓ DATA","breadth":0,"so_tang":0,"tong":0,"source":"NO_CACHE","date":"","coverage":0}
    valid = d[d["Có data"] == True].copy()
    if valid.empty:
        return d, {"market_label":"KHÔNG CÓ DATA","breadth":0,"so_tang":0,"tong":len(codes),"source":"NO_CACHE","date":"","coverage":0}
    date = valid["Ngày"].value_counts().index[0]
    same = valid[valid["Ngày"] == date].copy()
    tong = len(same)
    so_tang = int((pd.to_numeric(same["Ret1 %"], errors="coerce") > 0).sum())
    breadth = round(so_tang / max(tong, 1) * 100, 2)
    coverage = round(tong / max(len(codes), 1) * 100, 2)
    ms = _num(market_score, 0)
    if coverage < 80: label = "DATA CHƯA ĐỒNG BỘ"
    elif ms >= 60 and breadth >= 55: label = "TĂNG THẬT"
    elif ms >= 60 and breadth < 45: label = "TĂNG ẢO / TRỤ KÉO"
    elif ms < 45 and breadth < 45: label = "GIẢM THẬT"
    elif ms < 45 and breadth >= 50: label = "GIẢM ẢO / TRỤ ĐÈ"
    else: label = "TRUNG TÍNH"
    return d, {"market_label":label,"breadth":breadth,"so_tang":so_tang,"tong":tong,"source":"RET1_CACHE","date":date,"coverage":coverage}

def _parts(p): return [x.strip().upper() for x in str(p).split("|") if x.strip()]

def _vi_pattern(p):
    mp = {"UPTREND":"Thị trường tăng","DOWNTREND":"Thị trường giảm","SIDEWAY":"Đi ngang",
          "MOMENTUM":"Đà tăng","MOMENTUM_WATCH":"Theo dõi đà tăng","BOTTOM":"Bắt đáy","BOTTOM_WATCH":"Theo dõi đáy",
          "BUY NOW":"Mua","WAIT":"Chờ","WATCHLIST":"Theo dõi","SKIP":"Bỏ qua",
          "RSI_LOW":"RSI thấp","RSI_WEAK":"RSI yếu","RSI_MID":"RSI trung bình","RSI_MID_HIGH":"RSI khá cao","RSI_HIGH":"RSI cao",
          "RS_STRONG":"RS20 mạnh","RS_WEAK":"RS20 yếu nhẹ","RS_BAD":"RS20 yếu","RS20_LEADER":"RS20 dẫn dắt",
          "RS20_STRONG":"RS20 mạnh","RS20_OK":"RS20 ổn","RS20_SOFT":"RS20 hơi yếu","RS20_SLIGHT_WEAK":"RS20 hơi yếu",
          "VOL_LOW":"Thanh khoản thấp","VOL_OK":"Thanh khoản ổn","VOL_STRONG":"Thanh khoản mạnh",
          "ATR_LOW":"Biến động thấp","ATR_OK":"Biến động ổn","ATR_HIGH":"Biến động cao",
          "ABOVE_MA20":"Giá trên MA20","BELOW_MA20":"Giá dưới MA20","FAR_MA20":"Giá xa MA20"}
    return " | ".join([mp.get(x, x) for x in _parts(p)])

def _strategy(key):
    s = str(key).upper()
    if "BOTTOM" in s: return "BOTTOM"
    if "MOMENTUM" in s: return "MOMENTUM"
    return "OTHER"

def _bucket_rsi(v):
    r = _num(v)
    if pd.isna(r): return None
    return "RSI_LOW" if r < 35 else "RSI_WEAK" if r < 50 else "RSI_MID" if r < 65 else "RSI_MID_HIGH" if r < 78 else "RSI_HIGH"

def _bucket_rs20(v):
    x = _num(v)
    if pd.isna(x): return None
    return "RS20_LEADER" if x >= 25 else "RS20_STRONG" if x >= 5 else "RS20_OK" if x >= 0 else "RS20_SOFT" if x >= -5 else "RS_BAD"

def _bucket_vol(v):
    x = _num(v)
    if pd.isna(x): return None
    return "VOL_STRONG" if x >= 1.5 else "VOL_OK" if x >= 0.8 else "VOL_LOW"

def _bucket_atr(v):
    x = _num(v)
    if pd.isna(x): return None
    return "ATR_LOW" if x < 3 else "ATR_OK" if x <= 8 else "ATR_HIGH"

def _bucket_ma(row):
    close, ma20, dist = _num(row.get("Close")), _num(row.get("MA20")), _num(row.get("Dist MA20 %"))
    if pd.isna(close) or pd.isna(ma20): return None
    return "FAR_MA20" if close >= ma20 and not pd.isna(dist) and dist >= 12 else "ABOVE_MA20" if close >= ma20 else "BELOW_MA20"

def build_current_pattern_key(row):
    for c in ["Deep Pattern","Pattern","Pattern Key"]:
        if c in row.index and _txt(row.get(c)): return _txt(row.get(c))
    parts = []
    regime = _up(row.get("Regime", row.get("Market Regime Now","")))
    parts.append("UPTREND" if "UPTREND" in regime or "TANG" in regime else "DOWNTREND" if "DOWN" in regime or "GIAM" in regime else "SIDEWAY")
    st = _up(row.get("Strategy", row.get("Chien luoc","")))
    if st: parts.append(st)
    act = _up(row.get("Action", row.get("Rec", row.get("Final Action",""))))
    if "BUY" in act or "MUA" in act: parts.append("BUY NOW")
    elif "WAIT" in act or "CHO" in act: parts.append("WAIT")
    elif "WATCH" in act or "THEO" in act: parts.append("WATCHLIST")
    elif "SKIP" in act or "BO" in act: parts.append("SKIP")
    for x in [_bucket_rsi(row.get("RSI")), _bucket_rs20(row.get("RS20")), _bucket_vol(row.get("Volume Ratio")), _bucket_atr(row.get("ATR %")), _bucket_ma(row)]:
        if x: parts.append(x)
    return "|".join(parts)

def _group(t):
    if t in ["UPTREND","DOWNTREND","SIDEWAY"]: return "REGIME"
    if t in ["MOMENTUM","MOMENTUM_WATCH","BOTTOM","BOTTOM_WATCH"]: return "STRATEGY"
    if t in ["BUY NOW","WAIT","WATCHLIST","SKIP"]: return "ACTION"
    if t.startswith("RSI_"): return "RSI"
    if t.startswith("RS20_") or t.startswith("RS_"): return "RS20"
    if t.startswith("VOL_"): return "VOLUME"
    if t.startswith("ATR_"): return "ATR"
    if t in ["ABOVE_MA20","BELOW_MA20","FAR_MA20"]: return "MA20"
    return "OTHER"

W_MOM = {"REGIME":20,"STRATEGY":20,"RS20":20,"RSI":15,"MA20":10,"VOLUME":10,"ATR":5,"ACTION":10}
W_BOT = {"REGIME":10,"STRATEGY":20,"RSI":25,"VOLUME":15,"ATR":10,"MA20":10,"RS20":10,"ACTION":10}

def _weights(strategy): return W_BOT if strategy == "BOTTOM" else W_MOM

def _gmap(tokens):
    d = {}
    for t in tokens:
        g = _group(t)
        if g != "OTHER": d[g] = t
    return d

def _sim(g, a, b):
    if not a or not b: return 0
    if a == b: return 1
    if g == "REGIME":
        if set([a,b]) == set(["UPTREND","SIDEWAY"]): return 0.5
        if set([a,b]) == set(["DOWNTREND","SIDEWAY"]): return 0.4
        return 0
    if g == "STRATEGY":
        if "MOMENTUM" in a and "MOMENTUM" in b: return 0.6
        if "BOTTOM" in a and "BOTTOM" in b: return 0.6
        return 0
    if g == "RSI":
        order = ["RSI_LOW","RSI_WEAK","RSI_MID","RSI_MID_HIGH","RSI_HIGH"]
        if a in order and b in order:
            dist = abs(order.index(a)-order.index(b))
            return 0.7 if dist == 1 else 0.35 if dist == 2 else 0
    if g == "RS20":
        order = ["RS_BAD","RS20_SOFT","RS_WEAK","RS20_OK","RS20_STRONG","RS_STRONG","RS20_LEADER"]
        if a in order and b in order:
            dist = abs(order.index(a)-order.index(b))
            return 0.7 if dist == 1 else 0.35 if dist == 2 else 0
    if g in ["VOLUME","ATR"]: return 0.5
    if g == "MA20":
        if ("ABOVE" in a and "FAR" in b) or ("FAR" in a and "ABOVE" in b): return 0.6
    if g == "ACTION":
        if a in ["BUY NOW","WAIT"] and b in ["BUY NOW","WAIT"]: return 0.5
        if a in ["WATCHLIST","WAIT"] and b in ["WATCHLIST","WAIT"]: return 0.5
    return 0

def weighted_match_score(current_key, history_key):
    st = _strategy(current_key)
    w = _weights(st)
    cm, hm = _gmap(_parts(current_key)), _gmap(_parts(history_key))
    total = sum(w.values())
    got = 0
    details = []
    for g, weight in w.items():
        s = _sim(g, cm.get(g), hm.get(g))
        got += weight * s
        if s > 0: details.append(f"{g}:{round(weight*s,1)}/{weight}")
    return (round(got/total*100,2) if total else 0), "; ".join(details)

def _records(stats_df):
    if stats_df is None or stats_df.empty: return []
    df = stats_df.copy()
    p = _col(df, ["Pattern","Pattern Key","pattern"])
    wr = _col(df, ["OOS%","OOS Win Probability","OOS Win Rate","Winrate"])
    n = _col(df, ["OOS N","OOSN","OOS Samples","Count","Samples"])
    a2 = _col(df, ["Avg+2D","OOS Avg Ret+2D %","Avg 2D","Ret+2D"])
    a5 = _col(df, ["Avg+5D","OOS Avg Ret+5D %","Avg 5D","Ret+5D"])
    a10 = _col(df, ["Avg+10D","OOS Avg Ret+10D %","Avg 10D","Ret+10D"])
    if not p: return []
    out=[]
    for _, r in df.iterrows():
        key = _txt(r.get(p))
        if not key: continue
        nn = _num(r.get(n),0) if n else 0
        wrr = _num(r.get(wr),np.nan) if wr else np.nan
        win = int(round(nn*wrr/100)) if not pd.isna(wrr) else np.nan
        out.append({"Pattern lịch sử":key,"Số lần test":int(nn),"Số lần thắng":win,
                    "Số lần thua":int(max(nn-win,0)) if not pd.isna(win) else np.nan,
                    "Tỷ lệ thắng %":wrr,
                    "Lợi TB T+2 %":_num(r.get(a2),np.nan) if a2 else np.nan,
                    "Lợi TB T+5 %":_num(r.get(a5),np.nan) if a5 else np.nan,
                    "Lợi TB T+10 %":_num(r.get(a10),np.nan) if a10 else np.nan})
    return out

def _best(cur, recs, min_pct=60):
    best=None
    for r in recs:
        pct, detail = weighted_match_score(cur, r["Pattern lịch sử"])
        if pct < min_pct: continue
        item = dict(r); item["Mức khớp mẫu %"] = pct; item["Chi tiết khớp"] = detail
        item["_rank"] = (pct, _num(item["Số lần test"],0), _num(item["Lợi TB T+5 %"],-999), _num(item["Tỷ lệ thắng %"],-999))
        if best is None or item["_rank"] > best["_rank"]: best = item
    if best: best.pop("_rank",None)
    return best

def _hrank(n, wr, a5, pct):
    n,wr,a5,pct = _num(n,0),_num(wr),_num(a5),_num(pct,0)
    if n <= 0 or pd.isna(wr) or pd.isna(a5) or pct <= 0: return "CHƯA CÓ MẪU GẦN GIỐNG"
    if pct >= 85 and n >= 10 and wr >= 75 and a5 >= 5: return "RẤT MẠNH"
    if pct >= 75 and n >= 5 and wr >= 70 and a5 >= 3: return "MẠNH"
    if pct >= 65 and n >= 5 and wr >= 65 and a5 >= 1: return "DÙNG ĐƯỢC"
    if n < 5 and wr >= 75 and a5 > 0: return "MẪU ÍT - THAM KHẢO"
    return "YẾU / KHÔNG ƯU TIÊN"

def _hscore(n,wr,a2,a5,a10,pct):
    n,wr,a2,a5,a10,pct = _num(n,0),_num(wr),_num(a2),_num(a5),_num(a10),_num(pct,0)
    if n <= 0 or pd.isna(wr) or pct <= 0: return 0
    score = min(n,20)*1.1 + max(min(wr-50,50),0)*0.8 + pct*0.35
    if not pd.isna(a5): score += max(min(a5*3,25),-20)
    if not pd.isna(a2): score += max(min(a2*1.5,10),-10)
    if not pd.isna(a10): score += max(min(a10*0.8,8),-8)
    return round(max(min(score,100),0),1)

def _decision(row, market):
    risk, st, rank = _up(row.get("Risk")), _up(row.get("Strategy")), _txt(row.get("Độ tin cậy lịch sử"))
    score, ai, rs20 = _num(row.get("Score"),0), _num(row.get("AI"),0), _num(row.get("RS20"),0)
    if risk == "FAIL": return "BỎ QUA - RISK FAIL"
    if "GIẢM THẬT" in market and "BOTTOM" in st: return "KHÔNG BẮT ĐÁY KHI GIẢM THẬT"
    if "MOMENTUM" in st:
        if "TĂNG THẬT" in market and rank in ["RẤT MẠNH","MẠNH"] and score >= 75 and ai >= 75: return "ƯU TIÊN MUA THĂM DÒ"
        if "TĂNG ẢO" in market and rs20 >= 5 and rank in ["RẤT MẠNH","MẠNH"]: return "CHỈ MUA LEADER - TỶ TRỌNG NHỎ"
        if rank == "DÙNG ĐƯỢC": return "THEO DÕI - CHỜ ĐIỂM VÀO"
        return "KHÔNG ƯU TIÊN"
    if "BOTTOM" in st:
        if ("GIẢM ẢO" in market or "TRUNG TÍNH" in market) and rank in ["RẤT MẠNH","MẠNH","DÙNG ĐƯỢC"]: return "MUA THĂM DÒ NHỎ / BẮT ĐÁY CÓ KIỂM SOÁT"
        if rank in ["RẤT MẠNH","MẠNH"]: return "THEO DÕI BẮT ĐÁY - GIẢM TỶ TRỌNG"
        return "KHÔNG ƯU TIÊN"
    return "THEO DÕI"

def build_v13_final_decision_vi(current_df, pattern_stats_df, market_score=0, universe=None, cache_dir=None, limit=60):
    try:
        if current_df is None or current_df.empty:
            return pd.DataFrame([{"Trạng thái":"Không có dữ liệu tín hiệu"}]), pd.DataFrame()
        _, minfo = market_real_fake_summary(current_df, market_score, universe, cache_dir)
        market = minfo.get("market_label","KHÔNG XÁC ĐỊNH")
        recs = _records(pattern_stats_df)
        df = current_df.copy()
        code,date,price = _col(df,["Ma","Code","Mã"]),_col(df,["Ngay","Date","Ngày"]),_col(df,["Close","Gia","Giá"])
        rec,scorec,aic = _col(df,["Rec","Action","Final Action"]),_col(df,["Score"]),_col(df,["AI Confidence","AI"])
        riskc,stc = _col(df,["Risk Status","Risk"]),_col(df,["Strategy","Chien luoc","Chiến lược"])
        rsic,rs20c = _col(df,["RSI"]),_col(df,["RS20"])
        rows=[]
        for _, r in df.iterrows():
            cur = build_current_pattern_key(r)
            best = _best(cur,recs,60) if recs else None
            if best is None:
                best={"Pattern lịch sử":"","Mức khớp mẫu %":0,"Chi tiết khớp":"","Số lần test":0,"Số lần thắng":np.nan,"Số lần thua":np.nan,"Tỷ lệ thắng %":np.nan,"Lợi TB T+2 %":np.nan,"Lợi TB T+5 %":np.nan,"Lợi TB T+10 %":np.nan}
            n,wr,a2,a5,a10,pct=best["Số lần test"],best["Tỷ lệ thắng %"],best["Lợi TB T+2 %"],best["Lợi TB T+5 %"],best["Lợi TB T+10 %"],best["Mức khớp mẫu %"]
            hr=_hrank(n,wr,a5,pct)
            row={"Ngày":r.get(date,"") if date else "", "Mã":r.get(code,"") if code else "", "Giá":r.get(price,"") if price else "",
                 "Market V13":market, "Breadth %":minfo.get("breadth",""), "Hành động hiện tại":r.get(rec,"") if rec else "",
                 "Strategy":r.get(stc,"") if stc else "", "Độ tin cậy lịch sử":hr, "Điểm lịch sử":_hscore(n,wr,a2,a5,a10,pct),
                 "Mức khớp mẫu %":pct, "Số lần test":n, "Số lần thắng":best["Số lần thắng"], "Số lần thua":best["Số lần thua"],
                 "Tỷ lệ thắng %":wr, "Lợi TB T+2 %":a2, "Lợi TB T+5 %":a5, "Lợi TB T+10 %":a10,
                 "Score":_num(r.get(scorec),np.nan) if scorec else np.nan, "AI":_num(r.get(aic),np.nan) if aic else np.nan,
                 "Risk":r.get(riskc,"") if riskc else "", "RSI":_num(r.get(rsic),np.nan) if rsic else np.nan, "RS20":_num(r.get(rs20c),np.nan) if rs20c else np.nan,
                 "Mẫu hiện tại":_vi_pattern(cur), "Mẫu lịch sử gần giống":_vi_pattern(best["Pattern lịch sử"]), "Chi tiết khớp":best["Chi tiết khớp"],
                 "Pattern hiện tại":cur, "Pattern lịch sử":best["Pattern lịch sử"]}
            row["Kết luận V13"]=_decision(row,market)
            row["Lý do"]=f"{market}; khớp {pct}%; lịch sử {hr}; test {n}; win {'' if pd.isna(wr) else round(wr,1)}%; T+5 {'' if pd.isna(a5) else round(a5,2)}%"
            rows.append(row)
        out=pd.DataFrame(rows)
        order={"RẤT MẠNH":1,"MẠNH":2,"DÙNG ĐƯỢC":3,"MẪU ÍT - THAM KHẢO":4,"YẾU / KHÔNG ƯU TIÊN":8,"CHƯA CÓ MẪU GẦN GIỐNG":9}
        out["_rank"]=out["Độ tin cậy lịch sử"].map(order).fillna(9)
        for c in ["Breadth %","Điểm lịch sử","Mức khớp mẫu %","Tỷ lệ thắng %","Lợi TB T+2 %","Lợi TB T+5 %","Lợi TB T+10 %","Score","AI","RSI","RS20"]:
            out[c]=pd.to_numeric(out[c],errors="coerce").round(2)
        for c in ["Số lần test","Số lần thắng","Số lần thua"]:
            out[c]=pd.to_numeric(out[c],errors="coerce").round(0)
        out=out.sort_values(["_rank","Điểm lịch sử","AI","Score"],ascending=[True,False,False,False]).drop(columns=["_rank"])
        summary=pd.DataFrame([{"Chỉ tiêu":"Market V13","Giá trị":market},{"Chỉ tiêu":"Data date","Giá trị":minfo.get("date","")},
                              {"Chỉ tiêu":"Độ rộng thị trường","Giá trị":f"{minfo.get('breadth',0)}%"},{"Chỉ tiêu":"Số mã tăng","Giá trị":f"{minfo.get('so_tang',0)}/{minfo.get('tong',0)}"},
                              {"Chỉ tiêu":"Coverage cache","Giá trị":f"{minfo.get('coverage',0)}%"},{"Chỉ tiêu":"Nguồn","Giá trị":minfo.get("source","")}])
        return out.head(limit).replace({np.nan:""}), summary
    except Exception as e:
        return pd.DataFrame([{"Trạng thái":"Lỗi V13 Final","Chi tiết":repr(e)}]), pd.DataFrame()

def build_v13_top_picks_vi(v13_df, limit=8):
    try:
        if v13_df is None or v13_df.empty or "Kết luận V13" not in v13_df.columns: return pd.DataFrame()
        df=v13_df.copy()
        mask=~df["Kết luận V13"].astype(str).str.contains("KHÔNG ƯU TIÊN|BỎ QUA|KHÔNG BẮT",case=False,na=False)
        top=df[mask].copy()
        if top.empty: return pd.DataFrame([{"Trạng thái":"Không có mã đủ điều kiện V13"}])
        for c in ["Điểm lịch sử","Mức khớp mẫu %","AI","Score","Lợi TB T+5 %"]:
            if c in top.columns: top[c]=pd.to_numeric(top[c],errors="coerce")
        top=top.sort_values(["Điểm lịch sử","Mức khớp mẫu %","AI","Score"],ascending=[False,False,False,False])
        cols=["Mã","Giá","Kết luận V13","Market V13","Độ tin cậy lịch sử","Mức khớp mẫu %","Số lần test","Tỷ lệ thắng %","Lợi TB T+5 %","Điểm lịch sử","AI","Risk","Lý do"]
        return top[[c for c in cols if c in top.columns]].head(limit).replace({np.nan:""})
    except Exception as e:
        return pd.DataFrame([{"Trạng thái":"Lỗi top V13","Chi tiết":repr(e)}])
