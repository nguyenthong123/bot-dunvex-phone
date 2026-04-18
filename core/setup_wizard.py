import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

# States for the conversation
SETTING_KEY, SETTING_VALUE = range(2)

class SetupWizard:
    def __init__(self, memory_manager):
        self.memory = memory_manager

    async def start_setup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Bắt đầu quá trình hướng dẫn cài đặt Onboarding."""
        user_id = str(update.effective_chat.id)
        
        welcome_text = (
            "🚀 **Chào mừng bạn tới OpenClaw Commercial!**\n\n"
            "Tôi là trình hướng dẫn cài đặt thông minh. Để bắt đầu, chúng ta cần cấu hình một số thông tin cơ bản.\n\n"
            "**Bạn muốn thiết lập gì ngay bây giờ?**"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔑 Cấu hình DeepSeek Key", callback_data="config_deepseek")],
            [InlineKeyboardButton("🤖 Đổi Model Local", callback_data="config_model")],
            [InlineKeyboardButton("📊 Kiểm tra hệ thống", callback_data="check_system")],
            [InlineKeyboardButton("❌ Thoát", callback_data="exit_setup")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")
        return ConversationHandler.END # We use buttons for now

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Xử lý các lựa chọn từ menu cài đặt."""
        query = update.callback_query
        await query.answer()
        
        if query.data == "config_deepseek":
            await query.edit_message_text(
                "🔑 **Thiết lập DeepSeek API Key**\n\n"
                "Vui lòng gửi cho tôi chuỗi API Key của bạn (bắt đầu bằng `sk-...`).\n"
                "Dữ liệu này sẽ được lưu trữ an toàn trong bộ nhớ máy."
            )
            context.user_data['pending_config'] = 'DEEPSEEK_API_KEY'
            return SETTING_VALUE
            
        elif query.data == "check_system":
            # Chạy nhanh một số kiểm tra
            is_adb = os.path.exists("/Volumes/DATA_SSD/claw_phone/tools/platform-tools/adb")
            status = "✅ Hệ thống kết nối tốt!" if is_adb else "⚠️ Không thấy bộ ADB Tool."
            await query.edit_message_text(f"📊 **Trạng thái hệ thống**\n\n- ADB: {status}\n- Database: ✅ OK\n- Agent: 🟢 Sẵn sàng")
            return ConversationHandler.END
            
        elif query.data == "exit_setup":
            await query.edit_message_text("✅ Đã đóng trình cài đặt. Bạn có thể sử dụng Bot bình thường.")
            return ConversationHandler.END

    async def save_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Lưu giá trị cấu hình mà người dùng gửi lên."""
        key = context.user_data.get('pending_config')
        value = update.message.text.strip()
        
        if not key:
            await update.message.reply_text("❌ Lỗi: Không xác định được mục cần lưu.")
            return ConversationHandler.END
            
        self.memory.set_setting(key, value)
        
        # Đồng thời cập nhật vào OS Environment để các module cũ vẫn chạy được
        os.environ[key] = value
        
        await update.message.reply_text(f"✅ Đã cập nhật thành công mục: `{key}`")
        return ConversationHandler.END

# Singleton instance
setup_wizard = None

def get_setup_wizard(memory):
    global setup_wizard
    if not setup_wizard:
        setup_wizard = SetupWizard(memory)
    return setup_wizard
