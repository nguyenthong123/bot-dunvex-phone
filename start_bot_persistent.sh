#!/data/data/com.termux/files/usr/bin/bash
# Script khởi động OpenClaw siêu bền bỉ
export HOME=/data/data/com.termux/files/home
export PATH=$HOME/open-claw-source/venv/bin:/data/data/com.termux/files/usr/bin:$PATH
cd $HOME/open-claw-source

# Dọn dẹp tiến trình cũ
pkill -9 -f python3
sleep 1

# Khởi động Bot ở chế độ tách biệt hoàn toàn
nohup python3 bot.py </dev/null >logs/bot.log 2>&1 &
echo "[*] Bot đã được kích hoạt ngầm với PID: $!"
