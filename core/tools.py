import os
import httpx
import json
import base64
from dotenv import load_dotenv

load_dotenv()

import subprocess
from core.ollama_client import ollama

class Toolset:
    def __init__(self, memory_manager):
        self.memory = memory_manager
        self.tavily_key = os.getenv("TAVILY_API_KEY")

    def _parse_arg(self, arg, key):
        """Helper to extract a specific key if arg is a dict/JSON string, or return raw arg"""
        if isinstance(arg, dict):
            return arg.get(key, str(arg))
        if isinstance(arg, str) and (arg.startswith('{') or arg.startswith('[')):
            try:
                data = json.loads(arg)
                if isinstance(data, dict):
                    return data.get(key, arg)
            except:
                pass
        return arg

    async def run_command(self, cmd):
        """Runs a terminal command and returns output"""
        cmd = self._parse_arg(cmd, "command")
        try:
            print(f"[*] Executing Command: {cmd}")
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
            output = f"{result.stdout}\n{result.stderr}"
            status = "[SUCCESS]" if result.returncode == 0 else "[FAILED]"
            print(f"[*] Command Result: {status}")
            return f"{status} {output}"
        except Exception as e:
            return f"[ERROR] {str(e)}"

    async def write_file(self, path, content=None):
        """Creates or overwrites a file with content"""
        # Handle dict input where path and content might be inside
        if isinstance(path, dict):
            content = path.get("content", content)
            path = path.get("path")
        else:
            path = self._parse_arg(path, "path")
            content = self._parse_arg(content, "content")

        try:
            abs_path = os.path.abspath(path)
            print(f"[*] Writing File. Path: {path}")
            os.makedirs(os.path.dirname(abs_path), exist_ok=True) if os.path.dirname(abs_path) else None
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"[*] File Written Successfully to: {abs_path}")
            return f"[SUCCESS] Đã tạo/cập nhật file: {abs_path}"
        except Exception as e:
            return f"[ERROR] Không thể tạo file: {str(e)}"

    async def read_file(self, path):
        """Reads a file content for overall reasoning"""
        path = self._parse_arg(path, "path")
        try:
            print(f"[*] Reading File: {path}")
            if not os.path.exists(path):
                return f"[ERROR] File không tồn tại: {path}"
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            return f"[SUCCESS] Nội dung của {path}:\n{content}"
        except Exception as e:
            return f"[ERROR] Không thể đọc file: {str(e)}"

    async def list_files(self, path="."):
        """Lists files recursively to understand project structure (ignoring junk)"""
        path = self._parse_arg(path, "path") or "."
        try:
            print(f"[*] Listing Files in: {path}")
            ignore_list = [".git", "venv", "__pycache__", "node_modules", ".gemini", "data"]
            file_tree = []
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if d not in ignore_list]
                level = root.replace(path, "").count(os.sep)
                indent = "  " * level
                file_tree.append(f"{indent}📁 {os.path.basename(root)}/")
                sub_indent = "  " * (level + 1)
                for f in files:
                    file_tree.append(f"{sub_indent}📄 {f}")
            
            tree_str = "\n".join(file_tree)
            return f"[SUCCESS] Cấu trúc dự án:\n{tree_str}"
        except Exception as e:
            return f"[ERROR] Không thể liệt kê file: {str(e)}"

    async def edit_file(self, path, target_text=None, replacement_text=None):
        """Surgically replaces a specific part of code in a file"""
        if isinstance(path, dict):
            target_text = path.get("target_text", target_text)
            replacement_text = path.get("replacement_text", replacement_text)
            path = path.get("path")
        else:
            path = self._parse_arg(path, "path")

        try:
            print(f"[*] Patching File: {path}")
            if not os.path.exists(path):
                return f"[ERROR] File không tồn tại: {path}"
            
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            
            if target_text not in content:
                return f"[ERROR] Không tìm thấy đoạn mã cần thay thế trong file {path}."
            
            new_content = content.replace(target_text, replacement_text)
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
            
            return f"[SUCCESS] Đã sửa file {path} thành công."
        except Exception as e:
            return f"[ERROR] Lỗi khi sửa file: {str(e)}"

    async def search_web(self, query):
        """Searches the internet using Tavily API"""
        print(f"[*] Searching Web: {query}")
        if not self.tavily_key:
            return "Lỗi: Chưa cấu hình TAVILY_API_KEY."
        
        url = "https://api.tavily.com/search"
        payload = {
            "api_key": self.tavily_key,
            "query": query,
            "search_depth": "basic",
            "max_results": 3
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    results = response.json().get("results", [])
                    if not results:
                        return "Không tìm thấy kết quả nào trên mạng."
                    
                    search_info = "\n".join([f"- {r['title']}: {r['content']} ({r['url']})" for r in results])
                    return f"Kết quả tìm kiếm từ Internet cho '{query}':\n{search_info}"
                return f"Lỗi từ Tavily API: {response.status_code}"
        except Exception as e:
            return f"Không thể kết nối Internet: {str(e)}"

    async def search_docs(self, query):
        """Searches local training documents using RAG"""
        results = self.memory.search_documents(query)
        if not results:
            return f"Không tìm thấy thông tin liên quan đến '{query}' trong tài liệu nội bộ."
        
        doc_info = "\n".join([f"- Tài liệu {r[0]}: {r[1]}..." for r in results])
        return f"Thông tin tìm thấy trong tài liệu đào tạo:\n{doc_info}"

    async def ask_local_coder(self, prompt):
        """Uses the local model for specialized programming tasks"""
        model = os.getenv("LOCAL_CODE_MODEL", "qwen2.5-coder:7b")
        print(f"[*] Calling Local Coder: {model}")
        response = await ollama.generate(
            model=model,
            prompt=prompt,
            system="Bạn là một chuyên gia lập trình tối ưu. Hãy giải quyết vấn đề code của người dùng một cách chính xác và hiệu quả nhất."
        )
        return f"[LOCAL CODER RESPONSE]\n{response}\n[RAM STATUS: Offloaded]"

    async def analyze_local_image(self, image_path, prompt="Mô tả hình ảnh này"):
        """Uses the local vision model to analyze an image"""
        model = os.getenv("LOCAL_VISION_MODEL", "moondream")
        print(f"[*] Calling Local Vision: {model} for {image_path}")
        if not os.path.exists(image_path):
            return f"[ERROR] Không tìm thấy file ảnh: {image_path}"
        
        try:
            with open(image_path, "rb") as image_file:
                image_base64 = base64.b64encode(image_file.read()).decode('utf-8')
            
            response = await ollama.generate(
                model=model,
                prompt=prompt,
                images=[image_base64]
            )
            return f"[LOCAL VISION RESPONSE]\n{response}\n[RAM STATUS: Offloaded]"
            return f"[LOCAL VISION RESPONSE]\n{response}\n[RAM STATUS: Offloaded]"
        except Exception as e:
            return f"[ERROR] Lỗi khi xử lý ảnh qua LLM nội bộ: {str(e)}"

if __name__ == "__main__":
    # Quick test
    import asyncio
    from core.memory import MemoryManager
    async def test():
        tools = Toolset(MemoryManager())
        res = await tools.search_web("thời tiết Hà Nội hôm nay")
        print(res)
    asyncio.run(test())
