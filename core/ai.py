import os
import asyncio
import logging
import json
from datetime import datetime
import re
from openai import AsyncOpenAI
from core.mcp_manager import MCPManager
from core.tools import Toolset

class AIOrchestrator:
    def __init__(self, memory_manager):
        self.memory = memory_manager
        self.tools = Toolset(memory_manager)
        self.mcp = MCPManager()
        self.mcp_initialized = False
        self.client = None

    async def _ensure_mcp_init(self):
        if not self.mcp_initialized:
            logging.info("[*] Initializing MCP servers from config...")
            try:
                if not os.path.exists('config/mcp_config.json'):
                    logging.warning("[!] No MCP config found. Skipping.")
                    self.mcp_initialized = True
                    return

                with open('config/mcp_config.json', 'r') as f:
                    config = json.load(f)
                
                # Support both 'mcpServers' (standard) and 'servers' (custom) keys
                servers = config.get("mcpServers", config.get("servers", {}))
                
                for name, server in servers.items():
                    cmd = server.get("command")
                    args = server.get("args", [])
                    env = server.get("env", {})
                    
                    # 1. Substitute environment variables in ARGS
                    processed_args = []
                    for arg in args:
                        if isinstance(arg, str):
                            # Handle GITHUB_TOKEN_PLACEHOLDER or ${VAR} or $VAR
                            processed_arg = arg
                            for k, v in os.environ.items():
                                processed_arg = processed_arg.replace(f"${{{k}}}", v).replace(f"${k}", v)
                            # Custom check for our placeholder
                            if "GITHUB_TOKEN_PLACEHOLDER" in processed_arg:
                                processed_arg = processed_arg.replace("GITHUB_TOKEN_PLACEHOLDER", os.getenv("GITHUB_TOKEN", ""))
                            processed_args.append(processed_arg)
                        else:
                            processed_args.append(arg)

                    # 2. Substitute environment variables in ENV dict
                    processed_env = os.environ.copy()
                    for k, v in env.items():
                        if isinstance(v, str):
                            processed_val = v
                            if v == "GITHUB_TOKEN_PLACEHOLDER":
                                processed_val = os.getenv("GITHUB_TOKEN", "")
                            else:
                                for env_k, env_v in os.environ.items():
                                    processed_val = processed_val.replace(f"${{{env_k}}}", env_v).replace(f"${env_k}", env_v)
                            processed_env[k] = processed_val
                        else:
                            processed_env[k] = str(v)

                    # Connect to server
                    success = await self.mcp.connect_to_server(name, cmd, processed_args, env=processed_env)
                    if not success:
                        logging.error(f"[!] Critical: Failed to boot MCP server: {name}")
                
                self.mcp_initialized = True
            except Exception as e:
                logging.error(f"[!] MCP Config Error: {e}")

    def _truncate_text(self, text, max_chars=10000):
        if len(text) <= max_chars:
            return text
        half = max_chars // 2
        return text[:half] + f"\n\n... [Đã lược bớt {len(text) - max_chars} ký tự để tối ưu bộ nhớ] ...\n\n" + text[-half:]

    async def _get_system_prompt(self):
        mcp_tools = []
        if self.mcp_initialized:
            mcp_tools = await self.mcp.get_all_tools()
        
        mcp_defs = ""
        for tool in mcp_tools:
            description = getattr(tool, 'description', "No description")
            mcp_defs += f"\n- {tool.name}: {description}. Trả về chuỗi kết quả."

        now = datetime.now()
        current_time_str = now.strftime("%A, ngày %d tháng %m năm %Y, %H:%M:%S")

        return f"""Bạn là OpenClaw Commercial, phiên bản Agent AI siêu cấp chạy trên nền tảng Android (Termux).
Bối cảnh thời gian thực: {current_time_str}

BẠN LÀ MỘT 'QUẢN LÝ DỰ ÁN AI' (PROJECT MANAGER AGENT) CHUYÊN NGHIỆP TRONG HỆ THỐNG 'OPENCLAW'.

QUY TRÌNH LÀM VIỆC BẮT BUỘC:
1. LẬP KẾ HOẠCH [KẾ HOẠCH]: Trước khi thực thi bất kỳ công cụ nào, bạn PHẢI gửi một khối [KẾ HOẠCH] chi tiết về những gì bạn định làm (Bước 1, Bước 2...).
2. BÁO CÁO TIẾN ĐỘ: Trong quá trình suy luận, hãy báo cáo ngắn gọn bạn đang ở bước nào.
3. QUY TRÌNH NGHIỆM THU (CODE GUARDIAN): 
   - Sau mỗi lệnh 'write_file', bạn BẮT BUỘC phải gọi ngay 'verify_code' để Kỹ sư trưởng (Gemini) kiểm duyệt.
   - Nếu Kỹ sư trưởng báo [LỖI LOGIC] hoặc [LỖI CÚ PHÁP], bạn PHẢI xóa nội dung cũ và thực hiện lại cho đến khi đạt trạng thái [PASSED].
   - Không được coi nhiệm vụ hoàn thành nếu chưa có sự phê duyệt của Kỹ sư trưởng.
4. QUY TRÌNH SỬA LỖI (SELF-HEALING) CƯỠNG CHẾ: 
   - Nếu một công cụ trả về lỗi (tiền tố [ERROR]), bạn CẤM ĐƯỢC PHÉP lướt qua. Bạn PHẢI:
     a. Phân tích nguyên nhân lỗi (đường dẫn sai? tham số thiếu? lỗi hệ thống?).
     b. Báo cáo cho người dùng về việc phát hiện lỗi và phương án thử lại.
     c. Thực hiện hành động khắc phục (ví dụ: dùng list_files để tìm đúng đường dẫn nếu read_file lỗi).
   - Tối đa 10 lượt thử lại cho một lỗi. Nếu quá 10 lượt vẫn hỏng, hãy tóm tắt toàn bộ quá trình và xin ý kiến người dùng.
   - TUYỆT ĐỐI CẤM rò rỉ mã nguồn (HTML, CSS, JS) ra văn bản phản hồi. Mọi mã nguồn PHẢI được gửi qua công cụ 'write_file'.

SỨ MỆNH PHỐI HỢP CHIẾN THUẬT:
- Bạn (DeepSeek) đóng vai trò là 'Não bộ Chỉ huy'.
- QUY TẮC VÀNG: BẮT BUỘC dùng công cụ 'read_file' để đọc và phân tích code thực tế. TUYỆT ĐỐI CẤM bịa đặt.

QUY TẮC CÚ PHÁP:
- Luôn dùng định dạng [CALL: tool_name("arg1", "arg2")] cho mọi hành động.
- Trả về phản hồi bằng Tiếng Việt chuyên nghiệp, tinh gọn. 
- HẠN CHẾ tối đa việc dùng các ký tự tiêu đề (#, ##) và các ký hiệu trang trí (*, **). Hãy dùng xuống dòng để phân tách các ý thay vì lạm dụng ký hiệu.

[CÔNG CỤ HỆ THỐNG]:
{self.tools.get_tools_definition()}
{mcp_defs}"""

    async def get_response(self, user_id, user_text, image_path=None):
        """Unified entry point for AI reasoning with agentic tool usage"""
        await self._ensure_mcp_init()
        
        api_key = self.memory.get_setting("DEEPSEEK_API_KEY", os.getenv("DEEPSEEK_API_KEY"))
        base_url = self.memory.get_setting("OPENAI_API_BASE", os.getenv("OPENAI_API_BASE", "https://api.deepseek.com"))
        
        if not self.client:
            self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

        history_list = self.memory.get_chat_history(user_id, limit=10)
        messages = [{"role": "system", "content": await self._get_system_prompt()}]
        
        for msg in history_list:
            messages.append(msg)
        
        current_content = user_text
        if image_path:
            current_content += f"\n[HÀNH ĐỘNG CẦN THIẾT]: Có một tệp hình ảnh tại {image_path}. Nếu bạn cần biết nội dung ảnh để thực hiện yêu cầu, hãy sử dụng công cụ 'analyze_image(\"{image_path}\")' ngay lập tức."
        
        messages.append({"role": "user", "content": current_content})
        
        max_loops = 10
        for loop_idx in range(max_loops):
            try:
                logging.info(f"[*] AI Request (Step {loop_idx+1}). Messages: {len(messages)}")
                
                response = await asyncio.wait_for(
                    self.client.chat.completions.create(
                        model="deepseek-reasoner",
                        messages=messages,
                        max_tokens=4096,
                        timeout=55.0
                    ),
                    timeout=60.0
                )
                
                msg = response.choices[0].message
                ai_output = msg.content or ""
                reasoning = getattr(msg, 'reasoning_content', "")
                
                if reasoning:
                    logging.info(f"[AI REASONING]: {reasoning[:500]}...") # Log deeper reasoning
                
                # Robust Tool Call Extraction: Match [CALL: name("args")] anywhere in text
                tool_pattern = r'\[CALL:\s*(\w+)\s*\((.*?)\)\]'
                match = re.search(tool_pattern, ai_output, re.DOTALL)
                
                if match:
                    tool_name = match.group(1).strip()
                    raw_args = match.group(2).strip()
                    
                    # Better argument parsing supporting nested/complex strings
                    args = []
                    # Simple regex for strings in quotes
                    for a in re.findall(r'"((?:[^"\\]|\\.)*)"', raw_args, re.DOTALL):
                        args.append(a.replace('\\"', '"').replace('\\n', '\n'))
                    
                    if not args and raw_args: # Fallback for single unquoted arg
                        args = [raw_args.strip().strip('"')]

                    logging.info(f"[*] AI invoked: {tool_name}")
                    try:
                        if tool_name in self.tools.get_available_tool_names():
                            result = await self.tools.execute_tool(tool_name, args)
                        elif tool_name in self.mcp.tools_map:
                            mcp_args = {}
                            available_mcp_tools = await self.mcp.get_all_tools()
                            target_tool = next((t for t in available_mcp_tools if t.name == tool_name), None)
                            if target_tool and hasattr(target_tool, 'inputSchema'):
                                properties = target_tool.inputSchema.get('properties', {})
                                prop_names = list(properties.keys())
                                for i, val in enumerate(args):
                                    if i < len(prop_names): mcp_args[prop_names[i]] = val
                            result = await self.mcp.execute_tool(tool_name, mcp_args)
                        else:
                            result = f"Lỗi: Không thấy '{tool_name}'."
                    except Exception as tool_e:
                        result = f"Lỗi thực thi: {str(tool_e)}"

                    messages.append({"role": "assistant", "content": ai_output})
                    
                    # Force acknowledgment of errors or Reviewer feedback
                    if "Lỗi" in str(result) or "[ERROR]" in str(result) or "[LỖI LOGIC]" in str(result):
                        logging.warning(f"[!] Quality Gate Failure: {result}. Injecting RECOVERY prompt.")
                        messages.append({"role": "user", "content": f"[CẢNH BÁO TỪ KỸ SƯ TRƯỞNG]: Phát hiện sai sót: {result}. Bạn PHẢI giải trình và viết lại code chính xác hơn ngay lập tức."})
                    elif "[PASSED]" in str(result):
                        logging.info("[*] Quality Gate PASSED.")
                        messages.append({"role": "user", "content": f"[HỆ THỐNG]: Kỹ sư trưởng đã phê duyệt code. Kết quả: {result}"})
                    else:
                        messages.append({"role": "user", "content": f"[KẾT QUẢ HỆ THỐNG]: {result}"})
                    continue 
                
                # Save and return final answer
                self.memory.add_chat(user_id, "user", user_text)
                self.memory.add_chat(user_id, "assistant", ai_output)
                return ai_output

            except Exception as e:
                logging.error(f"[!] AI Critical Error: {str(e)}", exc_info=True)
                return f"Lỗi xử lý AI: {str(e)}"
        
        return "Xin lỗi, không thể xử lý sau nhiều bước suy luận."
