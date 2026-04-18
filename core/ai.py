import os
import asyncio
import logging
import json
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
                with open('config/mcp_config.json', 'r') as f:
                    config = json.load(f)
                
                for name, server in config.get("mcpServers", {}).items():
                    success = await self.mcp.connect_to_server(
                        name, 
                        server.get("command"), 
                        server.get("args", [])
                    )
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

        return f"""BẠN LÀ MỘT 'QUẢN LÝ DỰ ÁN AI' (PROJECT MANAGER AGENT) CHUYÊN NGHIỆP TRONG HỆ THỐNG 'OPENCLAW'.

QUY TRÌNH LÀM VIỆC BẮT BUỘC:
1. LẬP KẾ HOẠCH [KẾ HOẠCH]: Trước khi thực thi bất kỳ công cụ nào, bạn PHẢI gửi một khối [KẾ HOẠCH] chi tiết về những gì bạn định làm (Bước 1, Bước 2...).
2. BÁO CÁO TIẾN ĐỘ: Trong quá trình suy luận, hãy báo cáo ngắn gọn bạn đang ở bước nào.
3. TỰ KIỂM TRA & SỬA LỖI (SELF-HEALING): 
   - Sau khi dùng 'write_file', bạn PHẢI tự đặt câu hỏi: "Tệp này có được ghi đầy đủ không?".
   - Nếu kết quả trả về là lỗi hoặc tệp bị rỗng (0-byte), bạn PHẢI TỰ ĐỘNG THỰC HIỆN LẠI với chiến thuật khác (ví dụ: chia nhỏ file).
   - TUYỆT ĐỐI CẤM (VÙNG CẤM ĐỎ): Không bao giờ trả về mã nguồn (HTML, CSS, JS) trong phần văn bản phản hồi. Mọi mã nguồn PHẢI được gửi qua công cụ 'write_file'. Nếu bạn rò rỉ code ra văn bản, bạn sẽ bị hệ thống chặn.

SỨ MỆNH PHỐI HỢP CHIẾN THUẬT:
- Bạn (DeepSeek) đóng vai trò là 'Não bộ Chỉ huy'.
- Llama (Ollama) đóng vai trò là 'Chuyên gia Lập trình' địa phương.
- QUY TẮC VÀNG: BẮT BUỘC dùng công cụ 'ask_local_coder' để phân tích code thực tế. TUYỆT ĐỐI CẤM bịa đặt.

QUY TẮC CÚ PHÁP:
- Luôn dùng định dạng [CALL: tool_name("arg1", "arg2")] cho mọi hành động.
- Trả về phản hồi bằng Tiếng Việt chuyên nghiệp.

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
            try:
                logging.info(f"[*] Proactive Vision: Analyzing {image_path}...")
                image_description = await self.tools.analyze_local_image(image_path, "Mô tả ảnh cho AI.")
                current_content = f"[KẾT QUẢ THỊ GIÁC]: {image_description}\n---\nYÊU CẦU: {user_text}"
            except Exception as v_e:
                logging.error(f"[!] Vision Error: {v_e}")
                current_content += f"\n[Lỗi ảnh: {v_e}]"
        
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
