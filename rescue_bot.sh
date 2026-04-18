#!/bin/bash
# Script Cứu hộ Bot OpenClaw - Phiên bản "Chỉ huy" ⚡🚀

echo "🌊 Bắt đầu chiến dịch Sóng Thần: Đưa Bot về vùng lõi..."

# 1. Bảo tồn dữ liệu cũ (Safety First)
DEST_DIR="$HOME/open-claw-source"
TEMP_BACKUP="$HOME/claw_tmp_backup"

if [ -d "$DEST_DIR" ]; then
    echo "🔄 Phát hiện dự án cũ. Đang bảo tồn API Key và Bộ nhớ..."
    mkdir -p "$TEMP_BACKUP"
    [ -f "$DEST_DIR/.env" ] && cp "$DEST_DIR/.env" "$TEMP_BACKUP/"
    [ -d "$DEST_DIR/data" ] && cp -r "$DEST_DIR/data" "$TEMP_BACKUP/"
    
    echo "🧹 Xóa code cũ để chuẩn bị nâng cấp..."
    rm -rf "$DEST_DIR"
fi

# 2. Di chuyển dự án vào bộ diện thực thi
echo "📦 Đang đồng bộ mã nguồn mới từ /sdcard..."
cp -v -r /sdcard/open-claw-source "$HOME/"
cd "$DEST_DIR" || exit 1

# 3. Khôi phục dữ liệu đã bảo tồn
if [ -d "$TEMP_BACKUP" ]; then
    echo "⏪ Đang khôi phục lại các API Key và Bộ nhớ của bạn..."
    [ -f "$TEMP_BACKUP/.env" ] && cp "$TEMP_BACKUP/.env" "$DEST_DIR/"
    [ -d "$TEMP_BACKUP/data" ] && cp -r "$TEMP_BACKUP/data" "$DEST_DIR/"
    rm -rf "$TEMP_BACKUP"
    echo "✅ Toàn bộ Key và Dữ liệu đã được bảo vệ an toàn!"
fi

echo "🛠️ Đang nâng cấp vũ khí (Cài đặt hệ thống)..."
pkg update -y
pkg install -y build-essential rust python-pip nodejs

echo "🐍 Cài đặt thư viện Python (mcp, etc)..."
pip install --upgrade pip
pip install -r requirements.txt

echo "🤖 Tái khởi động Bot..."
pkill -f python3
python3 bot.py
