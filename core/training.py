import os
import sqlite3
from core.memory import MemoryManager

class DocumentIndexer:
    def __init__(self, memory_manager, training_path="documents/training"):
        self.memory = memory_manager
        self.training_path = training_path
        os.makedirs(self.training_path, exist_ok=True)

    def index_all(self):
        print(f"Bắt đầu quét tài liệu tại: {self.training_path}")
        indexed_count = 0
        
        # Clear existing documents to avoid duplicates during re-indexing
        conn = sqlite3.connect(self.memory.db_path)
        conn.execute("DELETE FROM documents")
        conn.commit()
        conn.close()

        for root, dirs, files in os.walk(self.training_path):
            for file in files:
                if file.endswith(('.txt', '.md', '.py')):
                    try:
                        path = os.path.join(root, file)
                        with open(path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            self.memory.index_document(file, content, tags=root)
                            indexed_count += 1
                            print(f"✅ Đã nạp: {file}")
                    except Exception as e:
                        print(f"❌ Lỗi khi đọc {file}: {str(e)}")
        
        return indexed_count

if __name__ == "__main__":
    # Test locally
    mem = MemoryManager()
    indexer = DocumentIndexer(mem)
    count = indexer.index_all()
    print(f"Hoàn thành! Đã nạp {count} tài liệu vào bộ nhớ dài hạn.")
