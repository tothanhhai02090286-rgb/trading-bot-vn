#!/bin/bash

echo "🚀 START MAC REALTIME V18"

cd "$(dirname "$0")"

python3 realtime/intraday_alert_bot.py

echo "✅ STOP MAC REALTIME V18"
