import os
import asyncio
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot test đã sống!")

async def main():
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    
    print("--- Đang khởi tạo bot test ---")
    async with app:
        await app.initialize()
        await app.start()
        print("--- Bot đang chạy polling ---")
        await app.updater.start_polling()
        # Keep alive
        await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
