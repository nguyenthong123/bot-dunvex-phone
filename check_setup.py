import os
import sqlite3
from core.memory import MemoryManager
from dotenv import load_dotenv

load_dotenv()

def check_env():
    print("--- [1] Checking Environment ---")
    keys = ["DEEPSEEK_API_KEY", "TELEGRAM_BOT_TOKEN", "OPENAI_API_BASE"]
    for key in keys:
        val = os.getenv(key)
        if val:
            print(f"✅ {key} is set.")
        else:
            print(f"❌ {key} is missing!")

def check_db():
    print("\n--- [2] Checking Database & Memory ---")
    try:
        memory = MemoryManager()
        # Test Chat History
        memory.add_chat("test_user", "user", "Hello Bot!")
        history = memory.get_chat_history("test_user", limit=1)
        if history and history[0]['content'] == "Hello Bot!":
            print("✅ SQLite Chat History working.")
            
        # Test Document Indexing
        memory.index_document("Test Doc", "This is a secret training manual about AI.", "test")
        results = memory.search_documents("secret training")
        if results and "AI" in results[0]['content']:
            print("✅ SQLite FTS5 Search (RAG) working.")
            
        print("✅ Database initialization successful.")
    except Exception as e:
        print(f"❌ Database error: {str(e)}")

if __name__ == "__main__":
    check_env()
    check_db()
    print("\n--- Stage 1 Readiness Check Complete ---")
