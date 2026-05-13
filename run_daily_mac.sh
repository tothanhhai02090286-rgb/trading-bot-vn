#!/bin/bash

echo "🚀 START MAC DAILY PIPELINE"

python3 run_daily_system.py
python3 system_health_check.py
python3 v141_ai_pattern_quality_strict_vi.py
python3 v142_ma20_heat_backtest_vi.py
python3 v143_heat_combo_vi.py
python3 v151_bottom_quality_engine_modular_vi.py
python3 v152_bottom_walkforward_vi.py
python3 v152_momentum_walkforward_vi.py
python3 v16_final_decision_engine_vi.py
python3 v17_regime_breadth_final_engine_vi.py
python3 v17_export_intraday_watchlist_vi.py

echo "✅ DONE MAC DAILY PIPELINE"
