import sqlite3
import os
from datetime import datetime

class MemoryManager:
    def __init__(self, db_path="data/memory.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Short-term memory: Chat history
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                role TEXT,
                content TEXT,
                timestamp DATETIME
            )
        ''')
        
        # Long-term memory: Documents (using FTS5 for fast search)
        cursor.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS documents USING fts5(
                title,
                content,
                tags UNINDEXED
            )
        ''')
        
        conn.commit()
        conn.close()

    def add_chat(self, user_id, role, content):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO history (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, role, content, datetime.now())
        )
        conn.commit()
        conn.close()

    def get_chat_history(self, user_id, limit=20):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT role, content FROM history WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
            (user_id, limit)
        )
        rows = cursor.fetchall()
        conn.close()
        # Reverse to get chronological order
        return [{"role": row[0], "content": row[1]} for row in reversed(rows)]

    def index_document(self, title, content, tags=""):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO documents (title, content, tags) VALUES (?, ?, ?)",
            (title, content, tags)
        )
        conn.commit()
        conn.close()

    def search_documents(self, query, limit=3):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT title, content FROM documents WHERE documents MATCH ? ORDER BY rank LIMIT ?",
            (query, limit)
        )
        rows = cursor.fetchall()
        conn.close()
        return [{"title": row[0], "content": row[1]} for row in rows]

    def clear_history(self, user_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM history WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
