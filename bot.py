import os
import logging
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from core.memory import MemoryManager
from core.ai import AIOrchestrator
from core.training import DocumentIndexer
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='logs/bot.log'
)

# Core placeholders
memory = None
orchestrator = None
indexer = None
OWNER_ID = os.getenv("OWNER_ID")

async def post_init(application):
    """Initialize cores inside the active event loop to avoid AsyncLibraryNotFoundError"""
    global memory, orchestrator, indexer
    logging.info("[*] Đang khởi tạo các thành phần logic bên trong Event Loop...")
    memory = MemoryManager()
    orchestrator = AIOrchestrator(memory)
    indexer = DocumentIndexer(memory)
    logging.info("[+] Khởi tạo hoàn tất.")

async def admin_check(update: Update):
    user_id = str(update.effective_chat.id)
    if OWNER_ID and user_id != OWNER_ID:
        logging.warning(f"[!] TRUY CẬP BỊ TỪ CHỐI: User {user_id} không khớp với OWNER_ID {OWNER_ID}")
        await update.message.reply_text(f"Xin lỗi, bạn không có quyền. ID của bạn là: {user_id}")
        return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update): return
    user_id = str(update.effective_chat.id)
    logging.info(f"[*] Khởi động hội thoại với User: {user_id}")
    await update.message.reply_text("Chào bạn! Tôi là trợ lý AI Hybrid của bạn. Tôi có thể tư vấn chuyên sâu và xử lý dữ liệu ngay trên điện thoại.")

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
    # Send "typing" action
    await context.bot.send_chat_action(chat_id=user_id, action="typing")
    
    # Get consultation from Orchestrator
    answer = await orchestrator.get_response(user_id, user_text)
    
    if not answer or answer.strip() == "":
        answer = "⚠️ Xin lỗi, AI không thể đưa ra phản hồi lúc này. Vui lòng thử lại sau."
    
    await update.message.reply_text(answer, parse_mode="Markdown")

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
        
    await update.message.reply_text(answer, parse_mode="Markdown")

if __name__ == '__main__':
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not found in .env")
        exit(1)
        
    # Build application with post_init hook
    application = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    
    start_handler = CommandHandler('start', start)
    clear_handler = CommandHandler('clear', clear)
    index_handler = CommandHandler('index', index_docs)
    message_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)
    photo_handler = MessageHandler(filters.PHOTO, handle_photo)
    
    application.add_handler(start_handler)
    application.add_handler(clear_handler)
    application.add_handler(index_handler)
    application.add_handler(message_handler)
    application.add_handler(photo_handler)
    
    print("Bot đang khởi động (Async Mode)...")
    application.run_polling()
