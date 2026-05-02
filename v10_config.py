import os
import re
import time
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
from pandas.errors import EmptyDataError

from universe import UNIVERSE

API_KEY = os.getenv("VNSTOCK_API_KEY")

SYSTEM_VERSION = "PRO_V10_EXPLAINABLE_AI_2026_05_01"

BATCH_SIZE = 50
CACHE_SLEEP_SEC = 0.3
API_SLEEP_SEC = 5
CACHE_DIR = "cache_stock"

STATE_PATH = "progress_state.csv"
ALL_RESULT_PATH = "all_signal_results.csv"

RAW_SIGNAL_PATH = "raw_signal_candidates.csv"
AI_RISK_PATH = "ai_risk_filtered.csv"
BOTTOM_PATH = "bottom_common_priority.csv"
MOMENTUM_PATH = "momentum_common_priority.csv"
ENTRY_PATH = "entry_plan_next_session.csv"
DASHBOARD_PATH = "ai_risk_dashboard.html"

PORTFOLIO_PATH = "portfolio_current.csv"
PORTFOLIO_TRACKER_PATH = "portfolio_tracker.csv"
ACTION_PLAN_PATH = "action_plan.csv"

SIGNAL_HISTORY_PATH = "signal_history.csv"
PATTERN_STATS_PATH = "pattern_stats.csv"

WALK_FORWARD_STATS_PATH = "walk_forward_stats.csv"

BACKFILL_SIGNAL_HISTORY_PATH = "backfill_signal_history.csv"
BACKFILL_WALK_FORWARD_PATH = "backfill_walk_forward_stats.csv"

BACKFILL_ENABLED = True
BACKFILL_MIN_ROWS_PER_SYMBOL = 120
BACKFILL_LOOKBACK_DAYS = 720
BACKFILL_BLOCK_MONTHS = 1
BACKFILL_TRAIN_RATIO = 0.75
BACKFILL_MAX_SYMBOLS_PER_RUN = 80
BACKFILL_STATE_PATH = "backfill_state.csv"

REGIME_STATS_PATH = "regime_stats.csv"

REGIME_SHORT_MA = 20
REGIME_LONG_MA = 50
REGIME_STRONG_RET20 = 5.0
REGIME_WEAK_RET20 = -5.0
REGIME_SIDEWAY_ABS_RET20 = 2.0
REGIME_HIGH_VOL_ATR = 8.0

RECENT_WEIGHT_MIN = 0.20
REGIME_BONUS_STRONG = 6
REGIME_PENALTY_BAD = 10

WF_TRAIN_DAYS = 45
WF_TEST_DAYS = 10
WF_STEP_DAYS = 10
WF_MIN_TEST_SAMPLES = 5
WF_MIN_WINDOWS = 2
WF_MIN_OOS_WIN_PROB = 52.0

HISTORY_LOOKBACK_DAYS = 180
DECAY_HALFLIFE_DAYS = 45
MIN_PATTERN_SAMPLES = 8
BASE_WIN_PROB = 55.0
TP_LEARN_PCT = 4.0
SL_LEARN_PCT = -3.0
HOLD_DAYS_LIST = [3, 5, 10]

TELEGRAM_ENABLED = True
