#!/bin/bash
# OpenClaw Commercial Edition - Trình cài đặt Vạn năng (Universal Installer)
# Tự động hóa: Môi trường, Phụ thuộc, Sandbox và Onboarding.

echo "🚀 Bắt đầu quá trình thiết lập OpenClaw Commercial..."

# 1. Kiểm tra môi trường Termux
if [ -z "$TERMUX_VERSION" ]; then
    echo "❌ Lỗi: Vui lòng chạy script này bên trong Termux (tải từ F-Droid)."
    exit 1
fi

# 2. Dò tìm phần cứng (Hardware Probe)
ARCH=$(uname -m)
echo "📊 Phát hiện kiến trúc CPU: $ARCH"

# 3. Cập nhật và Cài đặt hạ tầng hệ thống
echo "🛠️ Đang nâng cấp hạ tầng hệ thống..."
pkg update -y && pkg upgrade -y
pkg install -y python python-pip nodejs git build-essential proot-distro android-tools

# 4. Thiết lập Sandbox (PRoot-Distro) - Hộp Os ảo
echo "📦 Đang tạo Sandbox (Hộp Os ảo)..."
if ! proot-distro list | grep -q "debian"; then
    proot-distro install debian
fi

# 5. Thiết lập Môi trường Python (Hộp thực thi)
echo "🐍 Đang tạo môi trường Python biệt lập..."
python -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 6. Kiểm tra Shizuku (Cầu nối quyền lực)
if ! command -v rish &> /dev/null; then
    echo "⚠️ Lưu ý: Shizuku (rish) chưa được cài đặt. Một số tính năng hệ thống sẽ bị hạn chế."
    echo "👉 Bạn có thể cài đặt Shizuku APK và bật Wireless Debugging sau."
fi

# 7. Khởi động lần đầu (Onboarding)
echo "🎉 Chúc mừng! Cài đặt thành công."
echo "🤖 Đang khởi động Agent để bắt đầu quá trình Onboarding trên Telegram..."

# Tự động tạo file .env mẫu nếu chưa có
if [ ! -f ".env" ]; then
    echo "TELEGRAM_BOT_TOKEN=" > .env
    echo "OWNER_ID=" >> .env
    echo "💡 Đã tạo file .env. Vui lòng nhập TELEGRAM_BOT_TOKEN vào file này hoặc dùng lệnh /setup khi bot chạy."
fi

# Chạy Bot
python bot.py
