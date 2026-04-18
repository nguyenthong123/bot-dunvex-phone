import os
import httpx
import json
import base64
import logging
from dotenv import load_dotenv
import subprocess

load_dotenv()

class Toolset:
    def __init__(self, memory_manager):
        self.memory = memory_manager
        self.tavily_key = os.getenv('TAVILY_API_KEY')
        # Tự động xác định thư mục dự án hiện tại
        self.actual_home = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # Các đường dẫn ảo/cũ cần bẻ lái
        self.ghost_paths = [
            '/home/agent-workspace',
            '/home/nguyen/bot-dunvex-phone',
            '/data/data/com.termux/files/home/bot-dunvex-phone',
            '~/bot-dunvex-phone'
        ]

    def _remap_path(self, path):
        """
        STRICT ISOLATION: Remaps and validates paths to stay within project boundaries.
        Double-layer protection against the 15GB context bomb.
        """
        if not path: return path
        p = str(path)
        
        # 1. SECURITY: Triệt tiêu path traversal (../)
        p = p.replace("../", "").replace("..\\", "")
        
        # 2. MAPPING: Bẻ lái các đường dẫn ma/cũ
        for ghost in self.ghost_paths:
            if p.startswith(ghost):
                p = p.replace(ghost, self.actual_home)
        
        if p.startswith('~/'):
            p = p.replace('~/', os.path.expanduser('~') + '/')

        # 3. LOCKDOWN: Ép buộc đường dẫn tuyệt đối phải nằm trong project root
        actual_root = self.actual_home.rstrip('/')
        if p.startswith(actual_root):
            return p
        
        abs_p = os.path.abspath(p)
        if not abs_p.startswith(actual_root):
            return os.path.join(actual_root, p.lstrip('/'))
        return abs_p

    def get_available_tool_names(self):
        return [
            'internet_search', 'document_search', 'list_files', 
            'read_file', 'edit_file', 'run_command', 'write_file',
            'google_apps_script', 'analyze_image', 'verify_code'
        ]

    def _parse_arg(self, arg, key):
        if isinstance(arg, dict): return arg.get(key, str(arg))
        if isinstance(arg, str) and (arg.startswith('{') or arg.startswith('[')):
            try:
                data = json.loads(arg)
                if isinstance(data, dict): return data.get(key, arg)
            except: pass
        return arg

    async def run_command(self, cmd):
        cmd = self._parse_arg(cmd, 'command')
        cmd = self._remap_path(cmd)
        try:
            print(f'[*] Executing Command: {cmd}')
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
            output = f'{result.stdout}\n{result.stderr}'
            status = '[SUCCESS]' if result.returncode == 0 else '[FAILED]'
            return f'{status} {output}'
        except Exception as e:
            return f'[ERROR] {str(e)}'

    async def write_file(self, path, content=None):
        if isinstance(path, dict):
            content = path.get('content', content)
            path = path.get('path')
        else:
            path = self._parse_arg(path, 'path')
            content = self._parse_arg(content, 'content')
        
        path = self._remap_path(path)
        try:
            abs_path = os.path.abspath(path)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True) if os.path.dirname(abs_path) else None
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return f'[SUCCESS] Đã tạo/cập nhật file: {abs_path}'
        except Exception as e:
            return f'[ERROR] Không thể tạo file: {str(e)}'

    async def read_file(self, path):
        path = self._remap_path(self._parse_arg(path, 'path'))
        try:
            if not os.path.exists(path): return f'[ERROR] File không tồn tại: {path}'
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            return f'[SUCCESS] Nội dung của {path}:\n{content}'
        except Exception as e:
            return f'[ERROR] Không thể đọc file: {str(e)}'

    async def list_files(self, path='.'):
        path = self._remap_path(self._parse_arg(path, 'path') or '.')
        try:
            print(f'[*] Listing Files in: {path}')
            ignore_list = ['.git', 'venv', '__pycache__', 'node_modules', '.gemini', 'data']
            file_tree = []
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if d not in ignore_list]
                level = root.replace(path, '').count(os.sep)
                indent = '  ' * level
                file_tree.append(f'{indent}📁 {os.path.basename(root)}/')
                sub_indent = '  ' * (level + 1)
                for f in files:
                    file_tree.append(f'{sub_indent}📄 {f}')
            return f'[SUCCESS] Cấu trúc dự án:\n' + '\n'.join(file_tree)
        except Exception as e:
            return f'[ERROR] Không thể liệt kê file: {str(e)}'

    async def edit_file(self, path, target_text=None, replacement_text=None):
        if isinstance(path, dict):
            target_text = path.get('target_text', target_text)
            replacement_text = path.get('replacement_text', replacement_text)
            path = path.get('path')
        else:
            path = self._parse_arg(path, 'path')
        
        path = self._remap_path(path)
        try:
            if not os.path.exists(path): return f'[ERROR] File không tồn tại: {path}'
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            if target_text not in content:
                return f'[ERROR] Không tìm thấy đoạn mã cần thay thế trong file {path}.'
            new_content = content.replace(target_text, replacement_text)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            return f'[SUCCESS] Đã sửa file {path} thành công.'
        except Exception as e:
            return f'[ERROR] Lỗi khi sửa file: {str(e)}'

    async def search_web(self, query):
        if not self.tavily_key: return 'Lỗi: Chưa cấu hình TAVILY_API_KEY.'
        url = 'https://api.tavily.com/search'
        payload = {'api_key': self.tavily_key, 'query': query, 'search_depth': 'basic', 'max_results': 3}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    results = response.json().get('results', [])
                    search_info = '\n'.join([f'- {r["title"]}: {r["content"]} ({r["url"]})' for r in results])
                    return f"Kết quả tìm kiếm cho '{query}':\n{search_info}"
                return f'Lỗi Tavily: {response.status_code}'
        except Exception as e: return f'Lỗi mạng: {str(e)}'

    async def search_docs(self, query):
        results = self.memory.search_documents(query)
        if not results: return f'Không tìm thấy thông tin cho "{query}" trong tài liệu.'
        doc_info = '\n'.join([f'- {r[0]}: {r[1]}...' for r in results])
        return f'Thông tin tài liệu:\n{doc_info}'


    async def google_apps_script(self, action, project_dir="."):
        """Bridge for Google Apps Script using clasp binary."""
        target_dir = self._remap_path(project_dir)
        cmd = f"cd {target_dir} && clasp {action}"
        print(f"[*] Executing Clasp: {cmd}")
        return await self.run_command(cmd)

    async def analyze_image(self, image_path, prompt="Mô tả hình ảnh này một cách chi tiết."):
        """Analyzes an image using Google Gemini 1.5 Flash API."""
        actual_path = self._remap_path(image_path)
        if not os.path.exists(actual_path):
            return f"[ERROR] Không tìm thấy ảnh tại: {image_path}"

        api_key = self.memory.get_setting("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY"))
        if not api_key:
            return "[ERROR] GEMINI_API_KEY chưa được cấu hình trong .env"

        try:
            with open(actual_path, "rb") as f:
                img_data = base64.b64encode(f.read()).decode("utf-8")

            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "image/jpeg", "data": img_data}}
                    ]
                }]
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                
                # Extract text from Gemini response
                if "candidates" in data and data["candidates"]:
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                return "[ERROR] Gemini không trả về kết quả phân tích."

        except Exception as e:
            return f"[ERROR] Lỗi khi phân tích ảnh qua Gemini: {str(e)}"

    async def verify_code(self, path, goal_context="Kiểm tra logic và tính đúng đắn."):
        """Automated Quality Gate: Syntax Linter + Gemini logic review."""
        actual_path = self._remap_path(path)
        if not os.path.exists(actual_path):
            return f"[ERROR] Không tìm thấy file để verify: {path}"

        # 1. Syntax Check (Speed Gate)
        ext = path.split('.')[-1].lower()
        linter_result = "[OK] Syntax hợp lệ."
        if ext == 'py':
            l_check = await self.run_command(f"python3 -m py_compile {actual_path}")
            if "error" in l_check.lower(): linter_result = f"[LỖI CÚ PHÁP PYTHON]: {l_check}"
        elif ext in ['js', 'gs']:
            l_check = await self.run_command(f"node -c {actual_path}")
            if l_check.strip(): linter_result = f"[LỖI CÚ PHÁP JS/GAS]: {l_check}"

        if "[LỖI]" in linter_result:
            return linter_result

        # 2. Logic Review (Gemini Critique)
        api_key = self.memory.get_setting("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY"))
        if not api_key:
            return f"{linter_result} (Lưu ý: Không có Gemini API Key để review logic)."

        try:
            with open(actual_path, "r") as f:
                code_content = f.read()

            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
            prompt = f"""Bạn là một Senior Developer (Kỹ sư trưởng). Hãy review đoạn code sau cho dự án OpenClaw. 
Bối cảnh yêu cầu: {goal_context}
Code:
```{ext}
{code_content}
```
YÊU CẦU: Nếu có lỗi logic, thiếu sót hoặc code rác, hãy trả về kết quả bắt đầu bằng '[LỖI LOGIC]'. Nếu code tốt, hãy trả về '[PASSED]'. Trả lời ngắn gọn."""
            
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.post(url, json=payload)
                res.raise_for_status()
                review = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                return f"{linter_result}\n[REVIEW KỸ SƯ TRƯỞNG]: {review}"
        except Exception as e:
            return f"{linter_result}\n[REVIEW]: Lỗi khi gọi Gemini: {str(e)}"

    async def execute_tool(self, tool_name, args):
        try:
            if tool_name == 'internet_search': return await self.search_web(args[0])
            elif tool_name == 'document_search': return await self.search_docs(args[0])
            elif tool_name == 'list_files': return await self.list_files(args[0] if args else '.')
            elif tool_name == 'read_file': return await self.read_file(args[0])
            elif tool_name == 'edit_file': return await self.edit_file(args[0], args[1], args[2])
            elif tool_name == 'run_command': return await self.run_command(args[0])
            elif tool_name == 'write_file': return await self.write_file(args[0], args[1])
            elif tool_name == 'google_apps_script': return await self.google_apps_script(args[0], args[1] if len(args) > 1 else ".")
            elif tool_name == 'analyze_image': return await self.analyze_image(args[0], args[1] if len(args) > 1 else "Mô tả hình ảnh này.")
            elif tool_name == 'verify_code': return await self.verify_code(args[0], args[1] if len(args) > 1 else "Kiểm tra toàn diện.")
            else: return f'[ERROR] Tool "{tool_name}" không tồn tại.'
        except Exception as e: return f'[ERROR] Lỗi thực thi tool: {str(e)}'

    def get_tools_definition(self):
        return """CÔNG CỤ KHẢ DỤNG:
- internet_search(query): Tìm kiếm thông tin mới nhất trên mạng.
- list_files(path): Liệt kê thư mục.
- read_file(path): Đọc nội dung file thô.
- write_file(path, content), edit_file(path, target, replacement): Quản lý file.
- run_command(cmd): Thực thi lệnh terminal.
- google_apps_script(action, project_dir): Quản lý Apps Script. Action gồm: 'push', 'pull', 'status'.
- analyze_image(path, prompt): Phân tích hình ảnh (Vision). Trả về mô tả nội dung ảnh.
- verify_code(path, context): KIỂM DUYỆT CODE. PHẢI dùng sau khi 'write_file' để Kỹ sư trưởng review logic.
CÚ PHÁP: [CALL: tool_name("arg1", "arg2", ...)]"""
