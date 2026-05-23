# -*- coding: utf-8 -*-
import pandas as pd


def print_ai_council_debug(combined, repair_mojibake_func):
    """In debug AI Council và lưu ra file ai_council_debug.txt"""
    print("--- DEBUG: AI COUNCIL REASON (UTF8 SAFE) ---")
    
    if combined is None or combined.empty:
        print("No combined data for AI Council")
        return
    
    try:
        df_debug = combined[['Ma', 'AI Reason', 'AI Warning']].copy()
        
        df_debug['AI Reason'] = df_debug['AI Reason'].fillna('').astype(str)
        df_debug['AI Warning'] = df_debug['AI Warning'].fillna('').astype(str)
        
        # Fix mojibake
        df_debug['AI Reason'] = df_debug['AI Reason'].apply(repair_mojibake_func)
        df_debug['AI Warning'] = df_debug['AI Warning'].apply(repair_mojibake_func)
        
        lines = []
        lines.append("=== AI COUNCIL REASON ===")
        lines.append("")
        
        for _, row in df_debug.head(10).iterrows():
            lines.append(f"Mã: {row['Ma']}")
            lines.append(f"AI Reason: {row['AI Reason']}")
            lines.append(f"AI Warning: {row['AI Warning']}")
            lines.append("")
        
        report = "\n".join(lines)
        
        with open("ai_council_debug.txt", "w", encoding="utf-8") as f:
            f.write(report)
        
        print(report)
    except Exception as e:
        print(f"WARN: Cannot print AI Council debug: {repr(e)}")
