import os
import sys
import logging
import asyncio
import html
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from telegram.request import HTTPXRequest
from core.memory import MemoryManager
from core.ai import AIOrchestrator
from core.streaming_ai import StreamingOrchestrator
from core.training import DocumentIndexer
from core.maintenance import MaintenanceManager
from core.setup_wizard import get_setup_wizard, SETTING_KEY, SETTING_VALUE
from telegram import InlineKeyboardButton, InlineKeyboardMarkup 
from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/bot.log")
    ]
)
logger = logging.getLogger(__name__)

# Pre-startup check
print("[CRITICAL DIAGNOSTIC]: Bot script is executing...")

# Core placeholders
memory = None
orchestrator = None
indexer = None
wizard = None
OWNER_ID = os.getenv("OWNER_ID")

async def init_cores():
    """Initialize cores inside the active event loop to avoid AsyncLibraryNotFoundError"""
    global memory, orchestrator, indexer, wizard
    if orchestrator is not None:
        return
    logging.info("[*] Đang khởi tạo các thành phần logic (Memory, Orchestrator, Indexer)...")
    memory = MemoryManager()
    orchestrator = StreamingOrchestrator(memory)
    indexer = DocumentIndexer(memory)
    wizard = get_setup_wizard(memory)
    logging.info("[+] Khởi tạo thành phần logic hoàn tất.")

async def post_init(application):
    await init_cores()

async def admin_check(update: Update):
    user_id = str(update.effective_chat.id)
    if OWNER_ID and user_id != OWNER_ID:
        logging.warning(f"[!] TRUY CẬP BỊ TỪ CHỐI: User {user_id} không khớp với OWNER_ID {OWNER_ID}")
        await update.message.reply_text(f"Xin lỗi, bạn không có quyền. ID của bạn là: {user_id}")
        return False
    return True

async def send_safe_message(update: Update, text: str, parse_mode: str = "HTML"):
    """
    Tiện ích gửi tin nhắn an toàn: 
    1. Tự động chia nhỏ tin nhắn nếu dài > 4000 ký tự.
    2. Fallback sang văn bản thuần túy nếu HTML lỗi.
    """
    MAX_LENGTH = 4000
    # Split text into chunks
    parts = [text[i:i + MAX_LENGTH] for i in range(0, len(text), MAX_LENGTH)]
    
    for part in parts:
        try:
            await update.message.reply_text(part, parse_mode=parse_mode)
        except Exception as e:
            logging.warning(f"[!] Lỗi khi gửi tin nhắn (parse_mode={parse_mode}): {e}")
            # Fallback to plain text if HTML fails or message is still problematic
            try:
                logging.info("[*] Falling back to plain text (HTML failure)...")
                await update.message.reply_text(part[:4000])
            except Exception as e2:
                logging.error(f"[!!] Lỗi nghiêm trọng khi gửi tin nhắn: {e2}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    await update.message.reply_text(
        f"Xin chào {user_name}! Tôi là OpenClaw - Trợ lý Quản lý dự án của bạn.\n"
        "Tôi đã được gia cố để chạy vĩnh cửu và tự bảo trì.\n\n"
        "Gõ /help để xem các lệnh hỗ trợ."
    )

async def clean(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manual maintenance command"""
    msg = await update.message.reply_text("🧼 Đang tiến hành tổng vệ sinh hệ thống...")
    report = await maintainer.perform_maintenance()
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=msg.message_id,
        text=f"✨ <b>KẾT QUẢ BẢO TRÌ:</b>\n\n{report}",
        parse_mode="HTML"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📚 <b>Hướng dẫn sử dụng</b>:\n"
        "- Chat trực tiếp để yêu cầu Agent làm việc\n"
        "- Gửi ảnh để Agent phân tích hình ảnh\n"
        "- <code>/setup</code>: Cấu hình API Key và hệ thống\n"
        "- <code>/clear</code>: Xóa lịch sử chat hiện tại\n"
        "- <code>/index</code>: Nạp lại tài liệu vào bộ nhớ"
    )
    await update.message.reply_text(help_text, parse_mode="HTML")

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update): return
    user_id = str(update.effective_chat.id)
    memory.clear_history(user_id)
    await update.message.reply_text("Đã xóa sạch bộ nhớ ngắn hạn.")

async def index_docs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update): return
    await update.message.reply_text("Đang quét và nạp tài liệu đào tạo vào bộ nhớ dài hạn...")
    count = indexer.index_all()
    await update.message.reply_text(f"Đã nạp xong {count} tài liệu vào database.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update): return
    user_id = str(update.effective_chat.id)
    user_text = update.message.text
    
    logging.info(f"[User {user_id}]: {user_text}")
    
    # 1. Gửi tin nhắn trạng thái ban đầu
    status_msg = await update.message.reply_text("🧠 <b>Agent đang khởi động...</b>", parse_mode="HTML")
    
    # Các biến lưu trữ trạng thái luồng
    full_reasoning = ""
    full_content = ""
    last_update_time = asyncio.get_event_loop().time()
    current_status = "🧠 Đang suy luận..."
    
    try:
        # 2. Bắt đầu nhận luồng từ Orchestrator
        async for event_type, data in orchestrator.get_response_stream(user_id, user_text):
            now = asyncio.get_event_loop().time()
            
            if event_type == 'status':
                current_status = data
            elif event_type == 'thought':
                full_reasoning += data
            elif event_type == 'content':
                full_content += data
            elif event_type == 'tool_start':
                current_status = f"🛠️ Đang thực thi: <code>{html.escape(data)}</code>..."
            elif event_type == 'tool_end':
                current_status = f"✅ Đã xong công cụ: <code>{html.escape(data[:50])}...</code>"
            elif event_type == 'error':
                await context.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=status_msg.message_id,
                    text=f"❌ Lỗi: {data}"
                )
                return

            # 3. Cập nhật UI mỗi 3 giây để tránh bị Telegram rate limit (Flood Control)
            if now - last_update_time > 3.0:
                safe_status = html.escape(current_status)
                display_text = f"<b>{safe_status}</b>\n\n"
                if full_reasoning:
                    # Rút gọn reasoning nếu quá dài để hiển thị live
                    short_reasoning = full_reasoning[-500:] if len(full_reasoning) > 500 else full_reasoning
                    display_text += f"<i>{html.escape(short_reasoning)}...</i>\n\n"
                
                if full_content:
                    display_text += html.escape(full_content[-300:]) # Show last 300 chars of content
                
                try:
                    await context.bot.edit_message_text(
                        chat_id=user_id,
                        message_id=status_msg.message_id,
                        text=display_text[:4000], # Telegram limit
                        parse_mode="HTML"
                    )
                except Exception as e:
                    # Fallback to plain text if HTML fails (very rare now)
                    try:
                        await context.bot.edit_message_text(
                            chat_id=user_id,
                            message_id=status_msg.message_id,
                            text=display_text[:4000]
                        )
                    except Exception as e2:
                        logging.warning(f"UI Update critical skip: {e2}")
                last_update_time = now

        # 4. Gửi kết quả cuối cùng hoàn chỉnh
        # Định dạng: Suy luận trong Spoiler + Câu trả lời
        final_text = ""
        if full_reasoning:
            # HTML Spoiler using <tg-spoiler>
            safe_reasoning = html.escape(full_reasoning[:1000])
            final_text += f"<b>[SUY LUẬN]</b>\n<tg-spoiler>{safe_reasoning}...</tg-spoiler>\n\n"
        
        final_text += html.escape(full_content) if full_content else "Tôi đã xử lý xong yêu cầu của bạn."
        
        # Xóa tin nhắn trạng thái cũ và gửi tin nhắn mới sạch sẽ
        await context.bot.delete_message(chat_id=user_id, message_id=status_msg.message_id)
        await send_safe_message(update, final_text)

    except Exception as e:
        logging.error(f"Error in handle_message: {e}", exc_info=True)
        await update.message.reply_text(f"⚠️ Có lỗi xảy ra trong quá trình xử lý: {str(e)}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_chat.id)
    # Get the highest resolution photo
    photo_file = await update.message.photo[-1].get_file()
    os.makedirs("data/photos", exist_ok=True)
    file_path = f"data/photos/{photo_file.file_id}.jpg"
    await photo_file.download_to_drive(file_path)
    
    await update.message.reply_text("Tôi đã nhận được ảnh. Đang phân tích hình ảnh nội bộ...")
    
    # Call orchestrator with image context
    answer = await orchestrator.get_response(user_id, "Phân tích ảnh này cho tôi", image_path=file_path)
    
    if not answer or answer.strip() == "":
        answer = "⚠️ Không thể phân tích hình ảnh này. Hãy kiểm tra lại tệp tin hoặc thử lại sau."
        
    await send_safe_message(update, answer)

async def main():
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not found in .env")
        return

    # Build application with post_init
    application = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    
    # Initialize cores explicitly
    await init_cores()
    
    # Setup Wizard Handler
    setup_handler = ConversationHandler(
        entry_points=[CommandHandler("setup", wizard.start_setup)],
        states={
            SETTING_VALUE: [
                CallbackQueryHandler(wizard.handle_callback),
                MessageHandler(filters.TEXT & (~filters.COMMAND), wizard.save_config)
            ],
        },
        fallbacks=[CommandHandler("setup", wizard.start_setup)],
        allow_reentry=True
    )
    
    application.add_handler(setup_handler)
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('history_clear', clear)) # Rename clear to history_clear to avoid clash
    application.add_handler(CommandHandler('clean', clean)) # Add our new maintenance command
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('index', index_docs))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(CallbackQueryHandler(wizard.handle_callback)) # General buttons
    
    logging.info("--- OpenClaw Commercial Bot is RUNNING ---")
    
    # Correct lifecycle management for PTB v20+
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    # Keep the bot running until interrupted
    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    finally:
        await application.stop()
        await application.shutdown()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as e:
        logging.error(f"[FATAL ERROR]: {e}", exc_info=True)
