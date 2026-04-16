import os
import asyncio
from telegram import Bot
from dotenv import load_dotenv

load_dotenv()

async def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN missing in .env")
        return
    
    bot = Bot(token)
    me = await bot.get_me()
    print(f"Bot Username: @{me.username}")
    print(f"Bot ID: {me.id}")

if __name__ == "__main__":
    asyncio.run(main())
