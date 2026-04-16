import os
import httpx
import base64
import json
import re
import subprocess
from openai import AsyncOpenAI
from core.tools import Toolset
import logging
from dotenv import load_dotenv

load_dotenv()


class AIOrchestrator:
    def __init__(self, memory_manager):
        self.memory = memory_manager
        self.tools = Toolset(memory_manager)
        self.client = AsyncOpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("OPENAI_API_BASE", "https://api.deepseek.com")
        )

    def _get_system_prompt(self):
        return """BẠN LÀ MỘT 'SYSTEM AGENT' THỰC THI. NHIỆM VỤ CỦA BẠN LÀ LÀM VIỆC VỚI FILE VÀ TERMINAL.

QUY TẮC TRẢ LỜI (BẮT BUỘC):
1. PHONG CÁCH: Trả lời bằng văn bản thuần túy (Plain Text), rõ ràng, gãy gọn. 
2. CẤM EMOJI: Tuyệt đối không sử dụng bất kỳ icon hay biểu tượng cảm xúc nào trong câu trả lời.
3. HẠN CHẾ MARKDOWN: Không dùng dấu # cho tiêu đề, không dùng ** để in đậm. Chỉ dùng dấu xuống dòng để phân tách các ý. Chỉ dùng ``` khi thực sự cần viết code.
4. KHÔNG LỜI HỨA SUÔNG: Tuyệt đối không trả lời "Tôi đã làm..." nếu chưa thực sự gọi [CALL: ...] và có kết quả.

QUY TRÌNH THỰC THI:
- LUÔN gọi 'list_files' trước khi sửa hoặc tạo file.
- GITHUB: Phải luôn 'git add', 'git commit' và 'git push' sau khi thay đổi code. 
- LLM NỘI BỘ: Dùng các công cụ [LOCAL] khi cần phân tích sâu hoặc xem ảnh.

CÔNG CỤ:
- list_files(path), read_file(path), edit_file(path, target, replacement), write_file(path, content), run_command(cmd).
- [LOCAL] ask_local_coder(prompt), analyze_local_image(image_path, prompt).
- internet_search(query), document_search(query).

CÚ PHÁP BẮT BUỘC: [CALL: tool_name("arg1", "arg2")]""" 

    async def get_response(self, user_id, user_text, image_path=None):
        """Unified entry point for AI reasoning with agentic tool usage"""
        # 1. Get History (correct method name)
        history_list = self.memory.get_chat_history(user_id, limit=10)
        
        messages = [{"role": "system", "content": self._get_system_prompt()}]
        
        # history_list is a list of dicts: [{"role": "...", "content": "..."}]
        for msg in history_list:
            messages.append(msg)
        
        # Add current user message
        current_content = user_text
        if image_path:
            try:
                logging.info(f"[*] Proactive Vision: Automatically analyzing image at {image_path}...")
                # Call local vision model proactively
                image_description = await self.tools.analyze_local_image(image_path, "Mô tả chi tiết nội dung hình ảnh này để hỗ trợ trả lời câu hỏi của người dùng.")
                current_content = f"[KẾT QUẢ THỊ GIÁC NỘI BỘ]: {image_description}\n---\nYÊU CẦU NGƯỜI DÙNG: {user_text}"
                logging.info(f"[*] Proactive Vision finished. Description length: {len(image_description)}")
            except Exception as v_e:
                logging.error(f"[!] Proactive Vision Error: {v_e}")
                current_content += f"\n[Lỗi phân tích ảnh nội bộ: {v_e}]"
        
        messages.append({"role": "user", "content": current_content})
        
        max_loops = 10
        for _ in range(max_loops):
            try:
                logging.info(f"[*] Calling AI (DeepSeek R1)... Loop {_ + 1}")
                response = await self.client.chat.completions.create(
                    model="deepseek-reasoner",
                    messages=messages,
                    timeout=120.0
                )
                if not response.choices or len(response.choices) == 0:
                    logging.error("[!] Error: No choices returned from AI.")
                    return "Lỗi: AI không trả về kết quả."

                msg = response.choices[0].message
                ai_output = msg.content or ""
                reasoning = getattr(msg, 'reasoning_content', "")
                
                if reasoning:
                    logging.info(f"[*] DeepSeek Reasoning: {reasoning[:200]}...")
                
                logging.info(f"[*] AI Response received. Length: {len(ai_output)} chars. Preview: {ai_output[:100]}...")
                
                # Robust tool call extraction using string finding instead of regex for large blocks
                logging.info("[*] Searching for tool calls...")
                ai_output_stripped = ai_output.strip()
                call_start = ai_output_stripped.find("[CALL: ")
                call_end = ai_output_stripped.rfind(")]")
                
                if call_start != -1 and call_end != -1 and call_end > call_start:
                    call_content = ai_output_stripped[call_start + 7 : call_end]
                    # Identify tool_name and raw_args
                    first_paren = call_content.find("(")
                    if first_paren != -1:
                        tool_name = call_content[:first_paren].strip()
                        raw_args = call_content[first_paren + 1 :]
                        
                        # Robust parser for "arg1", "arg2" with escaped quotes support
                        args = [a.replace('\\"', '"').replace('\\n', '\n') for a in re.findall(r'"((?:[^"\\]|\\.)*)"', raw_args, re.DOTALL)]
                        
                        logging.info(f"[*] Agentic Action: {tool_name}({len(args)} args)")
                    
                    try:
                        logging.info(f"[*] Executing Tool: {tool_name}")
                        result = ""
                        if tool_name == "internet_search" and len(args) >= 1:
                            result = await self.tools.search_web(args[0])
                        elif tool_name == "document_search" and len(args) >= 1:
                            result = await self.tools.search_docs(args[0])
                        elif tool_name == "list_files" and len(args) >= 1:
                            result = await self.tools.list_files(args[0])
                        elif tool_name == "read_file" and len(args) >= 1:
                            result = await self.tools.read_file(args[0])
                        elif tool_name == "edit_file" and len(args) >= 3:
                            result = await self.tools.edit_file(args[0], args[1], args[2])
                        elif tool_name == "run_command" and len(args) >= 1:
                            result = await self.tools.run_command(args[0])
                        elif tool_name == "write_file" and len(args) >= 2:
                            result = await self.tools.write_file(args[0], args[1])
                        elif tool_name == "ask_local_coder" and len(args) >= 1:
                            result = await self.tools.ask_local_coder(args[0])
                        elif tool_name == "analyze_local_image":
                            # Use image_path from message if not provided in args
                            path = args[0] if len(args) >= 1 and os.sep in args[0] else image_path
                            prompt = args[1] if len(args) >= 2 else "Mô tả hình ảnh này"
                            result = await self.tools.analyze_local_image(path, prompt)
                        
                        print(f"[*] Tool execution finished. Result length: {len(str(result))}")
                    except Exception as tool_e:
                        print(f"[!] Tool Error: {str(tool_e)}")
                        result = f"Lỗi thực thi công cụ: {str(tool_e)}"

                    # Feed result back to AI as a user message (feedback from system)
                    messages.append({"role": "assistant", "content": ai_output})
                    messages.append({"role": "user", "content": f"[KẾT QUẢ HỆ THỐNG]: {result}"})
                    continue 
                
                # No tool calls, save and return
                print("[*] No more tool calls found. Saving to history and returning.")
                self.memory.add_chat(user_id, "user", user_text)
                self.memory.add_chat(user_id, "assistant", ai_output)
                return ai_output

            except Exception as e:
                import traceback
                error_detail = traceback.format_exc()
                print(f"[!] AI Logic Error: {error_detail}")
                return f"Lỗi xử lý AI: {str(e)}"
        
        return "Xin lỗi, tôi không thể xử lý yêu cầu này sau nhiều bước suy luận."


    # Redundant methods removed as logic is now in Toolset using OllamaClient
