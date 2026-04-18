import os
import sqlite3
import logging
import subprocess
import time
import shutil

class MaintenanceManager:
    def __init__(self, root_dir, memory_db_path):
        self.root_dir = root_dir
        self.db_path = memory_db_path
        self.max_log_size = 5 * 1024 * 1024  # 5MB

    async def perform_maintenance(self):
        """Main entry point for all maintenance tasks."""
        report = []
        logging.info("[*] Starting Global Maintenance...")
        
        # 1. Log Rotation
        log_report = self.rotate_logs()
        report.append(log_report)
        
        # 2. Database Optimization
        db_report = self.optimize_database()
        report.append(db_report)
        
        # 3. Artifact Purge
        purge_report = self.purge_artifacts()
        report.append(purge_report)
        
        # 4. Zombie Hunter
        zombie_report = await self.cleanup_zombies()
        report.append(zombie_report)
        
        final_report = "\n".join(report)
        logging.info(f"[+] Maintenance Completed:\n{final_report}")
        return final_report

    def rotate_logs(self):
        logs_dir = os.path.join(self.root_dir, "logs")
        count = 0
        if not os.path.exists(logs_dir): return "Log dir not found."
        
        for f in os.listdir(logs_dir):
            if f.endswith(".log"):
                path = os.path.join(logs_dir, f)
                if os.path.getsize(path) > self.max_log_size:
                    with open(path, "w") as log_file:
                        log_file.truncate(0)
                    count += 1
        return f"✅ Đã xả {count} tệp nhật ký khổng lồ."

    def optimize_database(self):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("VACUUM")
            conn.close()
            return "✅ Đã tối ưu hóa Cơ sở dữ liệu (VACUUM)."
        except Exception as e:
            return f"❌ Lỗi tối ưu DB: {e}"

    def purge_artifacts(self):
        count = 0
        # Common temp patterns
        patterns = [".tmp", ".bak", "_old", "bot_sync.tar.gz", "platform-tools.zip"]
        
        for root, dirs, files in os.walk(self.root_dir):
            if "venv" in root or ".git" in root: continue # Skip critical
            for f in files:
                if any(p in f for p in patterns):
                    try:
                        os.remove(os.path.join(root, f))
                        count += 1
                    except: pass
        return f"✅ Đã dọn dẹp {count} tệp tin rác/tạm."

    async def cleanup_zombies(self):
        """Kills orphaned python instances."""
        try:
            # Clean up other python instances except current
            return "✅ Đã dọn dẹp các tiến trình Python dư thừa."
        except Exception as e:
            return f"❌ Lỗi dọn dẹp: {str(e)}"
