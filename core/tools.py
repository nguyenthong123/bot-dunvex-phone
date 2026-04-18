import os
import httpx
import json
import base64
from dotenv import load_dotenv
import subprocess
from core.ollama_manager import OllamaOnDemandManager

load_dotenv()
ollama_manager = OllamaOnDemandManager()

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
        abs_p = os.path.abspath(p)
        
        # Nếu đường dẫn trỏ ra ngoài project (như llama.cpp hay .ollama), ép về root
        if not abs_p.startswith(actual_root):
            # logging.warning(f"[!] Tool Isolation Triggered: {abs_p}") # Optional log
            # Trả về đường dẫn an toàn nhất có thể (thư mục hiện tại của dự án)
            safe_p = os.path.join(actual_root, os.path.basename(abs_p))
            return safe_p
            
        return abs_p

    def get_available_tool_names(self):
        return [
            'internet_search', 'document_search', 'list_files', 
            'read_file', 'edit_file', 'run_command', 'write_file',
            'ask_local_coder', 'analyze_local_image', 'local_llama_reasoning'
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

    async def ask_local_coder(self, prompt):
        print(f'[*] Calling Local Coder (Llama/Ollama)...')
        response = await ollama_manager.generate(
            prompt=prompt, 
            system_prompt='Bạn là mô hình Llama chạy cục bộ, chuyên gia về đọc hiểu và phân tích cấu trúc mã nguồn. Hãy trả lời ngắn gọn, tập trung vào kỹ thuật.'
        )
        return f'[LLAMA ANALYSIS RESPONSE]:\n{response}'

    async def analyze_local_image(self, image_path, prompt='Mô tả ảnh'):
        image_path = self._remap_path(image_path)
        if not os.path.exists(image_path): return f'[ERROR] Không thấy ảnh: {image_path}'
        response = await ollama_manager.generate(f'Phân tích ảnh {image_path}: {prompt}')
        return f'[LOCAL VISION RESPONSE]\n{response}'

    async def local_llama_reasoning(self, prompt):
        response = await ollama_manager.generate(prompt)
        return f'[LOCAL LLAMA RESPONSE]\n{response}'

    async def execute_tool(self, tool_name, args):
        try:
            if tool_name == 'internet_search': return await self.search_web(args[0])
            elif tool_name == 'document_search': return await self.search_docs(args[0])
            elif tool_name == 'list_files': return await self.list_files(args[0] if args else '.')
            elif tool_name == 'read_file': return await self.read_file(args[0])
            elif tool_name == 'edit_file': return await self.edit_file(args[0], args[1], args[2])
            elif tool_name == 'run_command': return await self.run_command(args[0])
            elif tool_name == 'write_file': return await self.write_file(args[0], args[1])
            elif tool_name == 'ask_local_coder': return await self.ask_local_coder(args[0])
            elif tool_name == 'analyze_local_image': return await self.analyze_local_image(args[0], args[1] if len(args) > 1 else 'Mô tả')
            elif tool_name == 'local_llama_reasoning': return await self.local_llama_reasoning(args[0])
            else: return f'[ERROR] Tool "{tool_name}" không tồn tại.'
        except Exception as e: return f'[ERROR] Lỗi thực thi tool: {str(e)}'

    def get_tools_definition(self):
        return """CÔNG CỤ KHẢ DỤNG:
- internet_search(query): Tìm kiếm thông tin mới nhất trên mạng.
- list_files(path): Liệt kê thư mục.
- read_file(path): Đọc nội dung file thô.
- write_file(path, content), edit_file(path, target, replacement): Quản lý file.
- run_command(cmd): Thực thi lệnh terminal.
- ask_local_coder(prompt): [BẮT BUỘC KHI ĐỌC CODE] Gửi yêu cầu để Llama (mô hình AI cục bộ) đọc, hiểu và phân tích logic của các file code. Đây là cộng sự đắc lực của bạn.
- analyze_local_image(image_path, prompt): Phối hợp với Llama-Vision để nhìn và hiểu ảnh.
- local_llama_reasoning(prompt): Hỏi ý kiến Llama về một vấn đề logic bất kỳ.
CÚ PHÁP: [CALL: tool_name("arg1", "arg2", ...)]"""
