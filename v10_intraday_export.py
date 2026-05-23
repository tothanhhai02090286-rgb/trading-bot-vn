# -*- coding: utf-8 -*-
import os
import pandas as pd


def safe_export_intraday_watchlist(buy_df, watch_df, ui_find_col_func):
    """Xuất watchlist cho bot realtime Render"""
    try:
        frames = []
        if buy_df is not None and not getattr(buy_df, 'empty', True):
            b = buy_df.copy()
            b['Nhóm realtime'] = 'TOP MUA THẬT'
            b['Màu cảnh báo'] = 'GREEN'
            frames.append(b)
        if watch_df is not None and not getattr(watch_df, 'empty', True):
            w = watch_df.copy()
            w['Nhóm realtime'] = 'TOP THEO DÕI'
            w['Màu cảnh báo'] = 'YELLOW'
            frames.append(w)
        
        if not frames:
            out = pd.DataFrame([{
                'Trạng thái': 'KHÔNG CÓ MÃ REALTIME',
                'Ghi chú': 'Không có TOP MUA THẬT/TOP THEO DÕI đủ điều kiện'
            }])
        else:
            out = pd.concat(frames, ignore_index=True, sort=False)
        
        ma_col = ui_find_col_func(out, ['Mã', 'Ma', 'Symbol', 'Ticker'])
        price_col = ui_find_col_func(out, ['Giá', 'Gia', 'Close', 'close'])
        action_col = ui_find_col_func(out, ['Hành động hiện tại', 'Hanh dong hien tai', 'Action'])
        decision_col = ui_find_col_func(out, ['QUYẾT ĐỊNH TỰ ĐỘNG', 'Quyet dinh tu dong'])
        risk_col = ui_find_col_func(out, ['Risk', 'Risk Status'])
        rs20_col = ui_find_col_func(out, ['RS20'])
        t2_col = ui_find_col_func(out, ['Lợi TB T+2 %', 'Loi TB T+2 %', 'Lợi T+2 %', 'Loi T+2 %'])
        t5_col = ui_find_col_func(out, ['Lợi TB T+5 %', 'Loi TB T+5 %', 'Lợi T+5 %', 'Loi T+5 %'])
        score_col = ui_find_col_func(out, ['Score'])
        ai_col = ui_find_col_func(out, ['AI'])
        
        slim = pd.DataFrame()
        if ma_col: slim['Mã'] = out[ma_col].astype(str)
        if price_col: slim['Giá tham chiếu'] = pd.to_numeric(out[price_col], errors='coerce')
        if action_col: slim['Hành động'] = out[action_col].astype(str)
        if decision_col: slim['Quyết định'] = out[decision_col].astype(str)
        if risk_col: slim['Risk'] = out[risk_col].astype(str)
        if rs20_col: slim['RS20'] = out[rs20_col]
        if t2_col: slim['Lợi TB T+2 %'] = out[t2_col]
        if t5_col: slim['Lợi TB T+5 %'] = out[t5_col]
        if score_col: slim['Score'] = out[score_col]
        if ai_col: slim['AI'] = out[ai_col]
        slim['Nhóm realtime'] = out.get('Nhóm realtime', '')
        slim['Màu cảnh báo'] = out.get('Màu cảnh báo', '')
        
        if 'Giá tham chiếu' in slim.columns:
            ref = pd.to_numeric(slim['Giá tham chiếu'], errors='coerce')
            slim['Buy zone thấp'] = (ref * 0.985).round(2)
            slim['Buy zone cao'] = (ref * 1.015).round(2)
            slim['Stoploss tham khảo'] = (ref * 0.970).round(2)
        
        slim.to_csv("top_render_candidates.csv", index=False, encoding='utf-8-sig')
        
        path = os.getenv('INTRADAY_WATCHLIST_PATH', 'intraday_watchlist.csv')
        slim.to_csv(path, index=False, encoding='utf-8-sig')
        
        print(f'OK: exported top_render_candidates.csv rows={len(slim)}')
        print(f'OK: exported intraday watchlist -> {path} rows={len(slim)}')
        return slim
    except Exception as e:
        print('WARN: export intraday_watchlist.csv failed:', repr(e))
        return pd.DataFrame()
