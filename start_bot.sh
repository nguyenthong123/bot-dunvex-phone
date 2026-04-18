#!/bin/bash
# Script to keep the bot running even if the network fails
# Usage: nohup ./start_bot.sh > logs/bot.log 2>&1 &

cd "$(dirname "$0")"

while true; do
    echo "[*] $(date): Starting OpenClaw Bot..."
    export PYTHONUNBUFFERED=1
    python3 bot.py
    echo "[!] $(date): Bot stopped with exit code $?. Restarting in 10 seconds..."
    sleep 10
done
