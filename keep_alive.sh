#!/data/data/com.termux/files/usr/bin/bash

# OpenClaw Eternal Watchdog Script
# Purpose: Maintain CPU wake-lock and auto-restart bot if it crashes.

# Project directory
CDIR="/data/data/com.termux/files/home/open-claw-source"
cd "$CDIR"

# Ensure logs directory exists
mkdir -p logs

# Acquire Termux Wake-Lock (requires termux-api if available, otherwise stays silent)
if command -v termux-wake-lock > /dev/null; then
    echo "[*] Acquiring Termux Wake-Lock..."
    termux-wake-lock
fi

echo "--- OpenClaw Eternal Watchdog Started ---" >> logs/keep_alive.log

while true
do
    echo "[$(date)] Starting OpenClaw Bot..." >> logs/keep_alive.log
    
    # Run the bot and wait for it to exit
    python3 bot.py >> logs/bot_stdout.log 2>&1
    
    EXIT_CODE=$?
    echo "[$(date)] Bot exited with code $EXIT_CODE. Restarting in 2s..." >> logs/keep_alive.log
    
    sleep 2
done
