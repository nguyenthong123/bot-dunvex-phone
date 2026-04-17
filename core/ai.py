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
    def __init__(self, memory_manager, tools=None):
        self.memory = memory_manager
        self.tools = tools if tools else Toolset(memory_manager)
        self.client = None # Lazy init to avoid loop issues

    def _get_system_prompt(self):
        return f"""BẠN LÀ MỘT 'SYSTEM AGENT' THỰC THI TOÀN QUYỀN. NHIỆM VỤ CỦA BẠN LÀ QUẢN LÝ TỆP TIN VÀ CẬP NHẬT THÔNG TIN TỪ INTERNET.

SỨ MỆNH:
- KHÔNG BAO GIỜ nói "không khả dụng" nếu công cụ đã được liệt kê bên dưới.
- LUÔN LUÔN ưu tiên sử dụng 'internet_search' cho các thông tin biến động: Giá vàng, tỷ giá, thời tiết, tin tức.
- Phải hành động trước, giải thích sau.

QUY TẮC TRẢ LỜI (BẮT BUỘC):
1. QUYẾT ĐOÁN: KHÔNG hỏi ý kiến, KHÔNG xin phép. Nếu người dùng yêu cầu, hãy làm ngay lập tức bằng công cụ.
2. TIẾT KIỆM TOKEN: KHÔNG kiểm tra môi trường thừa thãi.
3. CẤM EMOJI: Tuyệt đối không dùng icon.
4. THỰC TẾ: Chỉ báo cáo SUCCESS khi nhận được phản hồi từ hệ thống.

{self.tools.get_tools_definition()}"""

    async def get_response(self, user_id, user_text, image_path=None):
        """Unified entry point for AI reasoning with agentic tool usage"""
        if not self.client:
            self.client = AsyncOpenAI(
                api_key=os.getenv("DEEPSEEK_API_KEY"),
                base_url=os.getenv("OPENAI_API_BASE", "https://api.deepseek.com")
            )

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
        
        max_loops = 15
        for _ in range(max_loops):
            try:
                logging.info(f"[*] Sending prompt to DeepSeek... Messages count: {len(messages)}")
                # Log first 500 chars of system prompt for verification
                logging.debug(f"[*] System Prompt Preview: {messages[0]['content'][:500]}")
                
                response = await self.client.chat.completions.create(
                    model="deepseek-reasoner",
                    messages=messages,
                    max_tokens=4096
                )
                
                ai_output = response.choices[0].message.content or ""
                reasoning = getattr(response.choices[0].message, 'reasoning_content', "")
                
                logging.info(f"[*] AI Response received. Length: {len(ai_output)} chars.")
                if len(ai_output) == 0:
                    logging.warning("[!] AI returned empty content. Reasoning preview: " + str(reasoning)[:200])
                
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
                            result = await self.tools.execute_tool(tool_name, args)
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
